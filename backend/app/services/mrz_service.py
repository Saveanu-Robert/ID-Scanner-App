"""MRZ detection, parsing, OCR error correction, and checksum validation.

Handles all three ICAO 9303 MRZ formats: TD1 (ID cards, 3x30), TD2 (some
IDs, 2x36), and TD3 (passports, 2x44). Because OCR on MRZ text is never
perfect, each field position gets targeted correction — digits where digits
belong, letters where letters belong — before we attempt checksum validation.
"""

import re
import logging

from mrz.checker.td1 import TD1CodeChecker
from mrz.checker.td2 import TD2CodeChecker
from mrz.checker.td3 import TD3CodeChecker

from app.models.schemas import MRZData, ScanResult

logger = logging.getLogger(__name__)

# Common OCR character confusions in MRZ
_LETTER_TO_DIGIT = str.maketrans("OIZSGB", "012568")
_DIGIT_TO_LETTER = str.maketrans("012568", "OIZSGB")

# Characters OCR most commonly substitutes for '<' in MRZ OCR-B font.
# K and G are the primary offenders due to angular/curved shape similarity.
_FILLER_NOISE = frozenset("KG")


def detect_mrz(text: str) -> list[str] | None:
    """Find MRZ lines in OCR text by looking for lines of uppercase letters,
    digits, and '<' that are close to the expected MRZ lengths.
    """
    pattern = re.compile(r"^[A-Z0-9<]{28,46}$")
    mrz_candidates: list[str] = []

    for line in text.splitlines():
        cleaned = line.strip().replace(" ", "")
        if pattern.match(cleaned):
            mrz_candidates.append(cleaned)

    if not mrz_candidates:
        return None

    # Group by expected lengths: TD1=30, TD2=36, TD3=44
    target_lengths: dict[int, list[str]] = {30: [], 36: [], 44: []}

    for line in mrz_candidates:
        length = len(line)
        for target in target_lengths:
            if abs(length - target) <= 2:
                adjusted = line.ljust(target, "<")[:target]
                target_lengths[target].append(adjusted)
                break

    # Check for valid MRZ format: TD3 (2x44), TD2 (2x36), TD1 (3x30)
    if len(target_lengths[44]) >= 2:
        return target_lengths[44][:2]
    if len(target_lengths[36]) >= 2:
        return target_lengths[36][:2]
    if len(target_lengths[30]) >= 3:
        return target_lengths[30][:3]

    return None


def parse_mrz(mrz_lines: list[str]) -> ScanResult:
    """Apply OCR corrections and extract fields from MRZ lines."""
    num_lines = len(mrz_lines)
    line_length = len(mrz_lines[0])

    if num_lines == 3 and line_length == 30:
        return _parse_td1(mrz_lines)
    elif num_lines == 2 and line_length == 36:
        return _parse_td2(mrz_lines)
    elif num_lines == 2 and line_length == 44:
        return _parse_td3(mrz_lines)
    else:
        return ScanResult(
            success=False,
            error=f"Unrecognized MRZ format: {num_lines} lines of length {line_length}",
            raw_ocr_text="\n".join(mrz_lines),
        )


def _parse_td3(lines: list[str]) -> ScanResult:
    """Parse a TD3 (passport) MRZ: 2 lines of 44 characters."""
    line1 = _fix_name_line(lines[0])
    line2 = _fix_td3_data_line(lines[1])

    # If position 9 (check digit) is a letter, the line is likely
    # left-shifted because OCR dropped a leading character (often '0').
    # Prepend '0' and re-correct to realign all field positions.
    if line2[9].isalpha():
        line2 = _fix_td3_data_line("0" + lines[1][:43])

    doc_type = line1[0:2].strip("<")
    country = line1[2:5].strip("<")
    name_raw = line1[5:44]
    full_name, surname, given_names = _clean_name(name_raw)

    doc_number = line2[0:9].strip("<")
    nationality = line2[10:13].strip("<")
    dob_raw = line2[13:19]
    sex = line2[20]
    expiry_raw = line2[21:27]

    corrected_lines = [line1, line2]
    mrz_raw = "\n".join(corrected_lines)
    valid = _validate_checksum_td3(corrected_lines)

    # If checksums fail and the country code doesn't match nationality,
    # OCR likely missed the country code from line 1 (common with watermarks).
    # Try inserting the nationality into line 1 to reconstruct the correct MRZ.
    if not valid and nationality and country != nationality:
        # Insert nationality at position 2 — the original country chars
        # were actually part of the surname that got shifted left.
        reconstructed_line1 = line1[0:2] + nationality + line1[2:]
        reconstructed_line1 = reconstructed_line1[:44]

        if _validate_checksum_td3([reconstructed_line1, line2]):
            line1 = reconstructed_line1
            country = nationality
            name_raw = line1[5:44]
            full_name, surname, given_names = _clean_name(name_raw)
            corrected_lines = [line1, line2]
            mrz_raw = "\n".join(corrected_lines)
            valid = True
        else:
            # Reconstruction didn't validate either. If the country was
            # 3 chars (like "DEL"), it likely absorbed part of the surname
            # so prepend it back. If it's 1-2 chars (like "O" for "D"),
            # it's just a misread — don't corrupt the name.
            if len(country) >= 3:
                reconstructed_name = country + name_raw
                full_name, surname, given_names = _clean_name(reconstructed_name)
            country = nationality

    confidence = "HIGH" if valid else "MEDIUM"

    return ScanResult(
        success=True,
        document_type=_classify_document(doc_type),
        full_name=full_name,
        surname=surname,
        given_names=given_names,
        date_of_birth=_format_date(dob_raw),
        nationality=nationality,
        document_number=doc_number,
        expiry_date=_format_date(expiry_raw),
        gender=_format_gender(sex),
        issuing_country=country,
        mrz_data=MRZData(raw_text=mrz_raw, mrz_type="TD3", valid=valid),
        raw_ocr_text=mrz_raw,
        confidence=confidence,
    )


def _parse_td1(lines: list[str]) -> ScanResult:
    """Parse a TD1 (ID card) MRZ: 3 lines of 30 characters."""
    line1 = _fix_td1_line1(lines[0])
    line2 = _fix_td1_line2(lines[1])
    line3 = _fix_name_line(lines[2])

    doc_type = line1[0:2].strip("<")
    country = line1[2:5].strip("<")
    doc_number = line1[5:14].strip("<")

    dob_raw = line2[0:6]
    sex = line2[7]
    expiry_raw = line2[8:14]
    nationality = line2[15:18].strip("<")

    name_raw = line3[0:30]
    full_name, surname, given_names = _clean_name(name_raw)

    corrected_lines = [line1, line2, line3]
    mrz_raw = "\n".join(corrected_lines)
    valid = _validate_checksum_td1(corrected_lines)

    if not valid and nationality and country != nationality:
        country = nationality

    confidence = "HIGH" if valid else "MEDIUM"

    return ScanResult(
        success=True,
        document_type=_classify_document(doc_type),
        full_name=full_name,
        surname=surname,
        given_names=given_names,
        date_of_birth=_format_date(dob_raw),
        nationality=nationality,
        document_number=doc_number,
        expiry_date=_format_date(expiry_raw),
        gender=_format_gender(sex),
        issuing_country=country,
        mrz_data=MRZData(raw_text=mrz_raw, mrz_type="TD1", valid=valid),
        raw_ocr_text=mrz_raw,
        confidence=confidence,
    )


def _parse_td2(lines: list[str]) -> ScanResult:
    """Parse a TD2 MRZ: 2 lines of 36 characters."""
    line1 = _fix_name_line(lines[0])
    line2 = _fix_td2_data_line(lines[1])

    # Detect left-shift: position 9 should be a check digit (number)
    if line2[9].isalpha():
        line2 = _fix_td2_data_line("0" + lines[1][:35])

    doc_type = line1[0:2].strip("<")
    country = line1[2:5].strip("<")
    name_raw = line1[5:36]
    full_name, surname, given_names = _clean_name(name_raw)

    doc_number = line2[0:9].strip("<")
    nationality = line2[10:13].strip("<")
    dob_raw = line2[13:19]
    sex = line2[20]
    expiry_raw = line2[21:27]

    corrected_lines = [line1, line2]
    mrz_raw = "\n".join(corrected_lines)
    valid = _validate_checksum_td2(corrected_lines)

    if not valid and nationality and country != nationality:
        reconstructed_name = country + name_raw
        full_name, surname, given_names = _clean_name(reconstructed_name)
        country = nationality

    confidence = "HIGH" if valid else "MEDIUM"

    return ScanResult(
        success=True,
        document_type=_classify_document(doc_type),
        full_name=full_name,
        surname=surname,
        given_names=given_names,
        date_of_birth=_format_date(dob_raw),
        nationality=nationality,
        document_number=doc_number,
        expiry_date=_format_date(expiry_raw),
        gender=_format_gender(sex),
        issuing_country=country,
        mrz_data=MRZData(raw_text=mrz_raw, mrz_type="TD2", valid=valid),
        raw_ocr_text=mrz_raw,
        confidence=confidence,
    )


# ── OCR Post-Correction ──────────────────────────────────────────────

def _fix_name_line(line: str) -> str:
    """Fix OCR errors in an MRZ name line (line 1 for TD2/TD3, line 3 for TD1)."""
    # Positions 0-4 are doc type + country (letters only)
    prefix = _force_letters(line[0:5])
    # Position 5 onwards is the name field (letters and < only)
    name_field = line[5:]

    # Fix digits that landed in the name — names never contain digits
    name_field = "".join(
        ch.translate(_DIGIT_TO_LETTER) if ch.isdigit() else ch
        for ch in name_field
    )

    chars = list(name_field)

    # Phase 1: Work right-to-left through letter clusters. Replace noise
    # clusters (made entirely of K/G filler misreads) with '<' until we
    # hit a cluster that looks like a real name, then stop.
    clusters = _find_letter_clusters(chars)

    for start, end in reversed(clusters):
        cluster_text = chars[start:end]
        # A real name cluster has at least 2 distinct characters that are
        # NOT common filler misreads (K, G). This filters out noise like
        # "GGGG", "KK", "GGKGKGKGKB" while keeping real names like
        # "MICHELLE", "JAMES", "BECK".
        non_noise = set(ch for ch in cluster_text if ch not in _FILLER_NOISE)
        if len(non_noise) >= 2:
            break
        for k in range(start, end):
            chars[k] = "<"

    # Phase 2: Fix K/G runs at name-filler boundaries.
    # One or more K/G preceded by a real letter and followed by 3+ '<'
    # are almost certainly misread '<' characters.
    result = "".join(chars)
    result = re.sub(
        r"(?<=[A-FHIJLMNOPQRSTUVWYZ])[KG]+(?=<{3,})",
        lambda m: "<" * len(m.group()),
        result,
    )

    # Phase 3: Fix <K< patterns (K sandwiched between fillers).
    # This pattern never occurs in valid MRZ names, so it's always noise.
    while "<K<" in result:
        result = result.replace("<K<", "<<<")

    # Phase 4: Fix K/G right after the << name separator.
    # In "<<KERIKA", the K before a real name is almost always a misread '<'.
    result = re.sub(r"(<<)[KG]([A-FHIJLMNOPQRSTUVWYZ])", r"\1<\2", result)

    return prefix + result


def _find_letter_clusters(chars: list[str]) -> list[tuple[int, int]]:
    """Find contiguous runs of non-'<' characters. Returns (start, end) pairs."""
    clusters: list[tuple[int, int]] = []
    i = 0
    while i < len(chars):
        if chars[i] != "<":
            j = i
            while j < len(chars) and chars[j] != "<":
                j += 1
            clusters.append((i, j))
            i = j
        else:
            i += 1
    return clusters


def _fix_digits_only(s: str) -> str:
    return s.translate(_LETTER_TO_DIGIT)


def _fix_letters_only(s: str) -> str:
    return s.translate(_DIGIT_TO_LETTER)


def _force_letters(s: str) -> str:
    result = []
    for ch in s:
        if ch.isdigit():
            result.append(ch.translate(_DIGIT_TO_LETTER))
        else:
            result.append(ch)
    return "".join(result)


def _fix_sex_field(ch: str) -> str:
    if ch in ("M", "F", "<"):
        return ch
    if ch in ("W", "H", "N"):  # common misreads of M
        return "M"
    if ch in ("E", "P"):  # common misreads of F
        return "F"
    return ch


def _fix_td2_data_line(line: str) -> str:
    """Apply position-aware corrections to TD2 line 2.

    TD2 Line 2 layout (36 chars):
        0-8:   Document number (alphanumeric)
        9:     Check digit (digit)
        10-12: Nationality (letters)
        13-18: Date of birth YYMMDD (digits)
        19:    Check digit (digit)
        20:    Sex (M/F/<)
        21-26: Expiry YYMMDD (digits)
        27:    Check digit (digit)
        28-34: Optional data (alphanumeric)
        35:    Overall check digit (digit)
    """
    chars = list(line)

    chars[9] = _fix_digits_only(chars[9])
    for i in range(10, 13):
        if chars[i] != "<":
            chars[i] = _fix_letters_only(chars[i])
    for i in range(13, 19):
        chars[i] = _fix_digits_only(chars[i])
    chars[19] = _fix_digits_only(chars[19])
    chars[20] = _fix_sex_field(chars[20])
    for i in range(21, 27):
        chars[i] = _fix_digits_only(chars[i])
    chars[27] = _fix_digits_only(chars[27])
    chars[35] = _fix_digits_only(chars[35])

    return "".join(chars)


def _fix_td3_data_line(line: str) -> str:
    """Apply position-aware corrections to TD3 line 2.

    TD3 Line 2 layout (44 chars):
        0-8:   Document number (alphanumeric)
        9:     Check digit (digit)
        10-12: Nationality (letters)
        13-18: Date of birth YYMMDD (digits)
        19:    Check digit (digit)
        20:    Sex (M/F/<)
        21-26: Expiry YYMMDD (digits)
        27:    Check digit (digit)
        28-41: Optional data (alphanumeric)
        42:    Check digit (digit)
        43:    Overall check digit (digit)
    """
    chars = list(line)

    chars[9] = _fix_digits_only(chars[9])
    for i in range(10, 13):
        if chars[i] != "<":
            chars[i] = _fix_letters_only(chars[i])
    for i in range(13, 19):
        chars[i] = _fix_digits_only(chars[i])
    chars[19] = _fix_digits_only(chars[19])
    chars[20] = _fix_sex_field(chars[20])
    for i in range(21, 27):
        chars[i] = _fix_digits_only(chars[i])
    chars[27] = _fix_digits_only(chars[27])
    chars[42] = _fix_digits_only(chars[42])
    chars[43] = _fix_digits_only(chars[43])

    return "".join(chars)


def _fix_td1_line1(line: str) -> str:
    """Apply position-aware corrections to TD1 line 1.

    TD1 Line 1 layout (30 chars):
        0-1:   Document type (letters)
        2-4:   Issuing country (letters)
        5-13:  Document number (alphanumeric)
        14:    Check digit (digit)
        15-29: Optional data (alphanumeric)
    """
    chars = list(line)

    for i in range(0, 5):
        if chars[i] != "<":
            chars[i] = _fix_letters_only(chars[i])
    chars[14] = _fix_digits_only(chars[14])

    return "".join(chars)


def _fix_td1_line2(line: str) -> str:
    """Apply position-aware corrections to TD1 line 2.

    TD1 Line 2 layout (30 chars):
        0-5:   Date of birth YYMMDD (digits)
        6:     Check digit (digit)
        7:     Sex (M/F/<)
        8-13:  Expiry YYMMDD (digits)
        14:    Check digit (digit)
        15-17: Nationality (letters)
        18-28: Optional data (alphanumeric)
        29:    Overall check digit (digit)
    """
    chars = list(line)

    for i in range(0, 7):
        chars[i] = _fix_digits_only(chars[i])
    chars[7] = _fix_sex_field(chars[7])
    for i in range(8, 15):
        chars[i] = _fix_digits_only(chars[i])
    for i in range(15, 18):
        if chars[i] != "<":
            chars[i] = _fix_letters_only(chars[i])
    chars[29] = _fix_digits_only(chars[29])

    return "".join(chars)


# ── Name / Date / Gender helpers ─────────────────────────────────────

def _clean_name(raw: str) -> tuple[str, str, str]:
    """Convert MRZ name encoding to human-readable form.

    In MRZ, '<<' separates surname from given names, and single '<'
    acts as a space within each part.
    """
    parts = raw.split("<<", 1)
    surname = parts[0].replace("<", " ").strip()

    if len(parts) > 1:
        given_names = parts[1].replace("<", " ").strip()
    else:
        given_names = ""

    full_name = f"{given_names} {surname}".strip() if given_names else surname
    return full_name, surname, given_names


def _format_date(yymmdd: str) -> str:
    """Convert YYMMDD to DD/MM/YYYY. Years >= 50 map to 19xx, < 50 to 20xx."""
    if len(yymmdd) != 6 or not yymmdd.isdigit():
        return yymmdd

    yy = int(yymmdd[0:2])
    mm = yymmdd[2:4]
    dd = yymmdd[4:6]

    year = 1900 + yy if yy >= 50 else 2000 + yy

    return f"{dd}/{mm}/{year}"


def _format_gender(code: str) -> str:
    mapping = {"M": "Male", "F": "Female"}
    return mapping.get(code.upper(), "Unknown")


def _classify_document(type_code: str) -> str:
    code = type_code.upper()
    if code.startswith("P"):
        return "Passport"
    if code in ("I", "ID"):
        return "ID Card"
    if code in ("AC",):
        return "Crew Member Certificate"
    if code.startswith("V"):
        return "Visa"
    return f"Document ({code})"


# ── Checksum Validation ──────────────────────────────────────────────

def _validate_checksum_td3(lines: list[str]) -> bool:
    try:
        checker = TD3CodeChecker("\n".join(lines))
        return bool(checker.result)
    except Exception:
        logger.debug("TD3 checksum validation failed", exc_info=True)
        return False


def _validate_checksum_td1(lines: list[str]) -> bool:
    try:
        checker = TD1CodeChecker("\n".join(lines))
        return bool(checker.result)
    except Exception:
        logger.debug("TD1 checksum validation failed", exc_info=True)
        return False


def _validate_checksum_td2(lines: list[str]) -> bool:
    try:
        checker = TD2CodeChecker("\n".join(lines))
        return bool(checker.result)
    except Exception:
        logger.debug("TD2 checksum validation failed", exc_info=True)
        return False
