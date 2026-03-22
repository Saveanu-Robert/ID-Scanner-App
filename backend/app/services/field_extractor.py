"""Regex-based field extraction fallback.

When no MRZ is found in the document image, this module tries to pull out
personal information by looking for labeled fields in the raw OCR text
(things like "NAME:", "DOB:", "PASSPORT NO:", etc.). Results from this
method are always marked as LOW confidence.
"""

import re

from app.models.schemas import ScanResult


def extract_fields(text: str) -> ScanResult:
    """Try to extract document fields from raw OCR text using regex patterns."""
    full_name = _extract_name(text)
    surname, given_names = _split_name(full_name)
    date_of_birth = _extract_date_near_label(text, r"(?:DOB|DATE\s*OF\s*BIRTH|BIRTH\s*DATE|BORN)")
    expiry_date = _extract_date_near_label(text, r"(?:EXPIRY|EXPIRATION|EXP|VALID\s*UNTIL|VALID\s*THRU)")
    document_number = _extract_document_number(text)
    gender = _extract_gender(text)
    nationality = _extract_nationality(text)

    has_any_field = any([
        full_name, date_of_birth, expiry_date,
        document_number, gender, nationality,
    ])

    return ScanResult(
        success=has_any_field,
        document_type="Unknown",
        full_name=full_name,
        surname=surname,
        given_names=given_names,
        date_of_birth=date_of_birth,
        nationality=nationality,
        document_number=document_number,
        expiry_date=expiry_date,
        gender=gender,
        raw_ocr_text=text,
        confidence="LOW",
    )


def _extract_name(text: str) -> str | None:
    """Look for a name near labels like NAME, SURNAME, GIVEN NAME."""
    patterns = [
        r"(?:FULL\s*NAME|NAME)\s*[:\-]?\s*([A-Za-z\s\-'\.]{2,50})",
        r"(?:SURNAME|LAST\s*NAME)\s*[:\-]?\s*([A-Za-z\s\-'\.]{2,50})",
        r"(?:GIVEN\s*NAME[S]?|FIRST\s*NAME)\s*[:\-]?\s*([A-Za-z\s\-'\.]{2,50})",
    ]

    match = re.search(patterns[0], text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # If there's no full name, try combining surname + given names
    surname_match = re.search(patterns[1], text, re.IGNORECASE)
    given_match = re.search(patterns[2], text, re.IGNORECASE)

    if surname_match and given_match:
        return f"{given_match.group(1).strip()} {surname_match.group(1).strip()}"

    if surname_match:
        return surname_match.group(1).strip()
    if given_match:
        return given_match.group(1).strip()

    return None


def _split_name(full_name: str | None) -> tuple[str | None, str | None]:
    """Split "JOHN MICHAEL SMITH" into surname="SMITH" and given="JOHN MICHAEL"."""
    if not full_name:
        return None, None

    parts = full_name.strip().split()
    if len(parts) == 1:
        return parts[0], None
    return parts[-1], " ".join(parts[:-1])


def _extract_date_near_label(text: str, label_pattern: str) -> str | None:
    """Find a date (DD/MM/YYYY, YYYY-MM-DD, etc.) that appears right after a label."""
    date_patterns = [
        r"(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})",
        r"(\d{4}[/\-\.]\d{2}[/\-\.]\d{2})",
        r"(\d{2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{4})",
    ]

    for date_pattern in date_patterns:
        combined = rf"{label_pattern}\s*[:\-]?\s*{date_pattern}"
        match = re.search(combined, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def _extract_document_number(text: str) -> str | None:
    """Find an alphanumeric string (6-12 chars) near a document number label."""
    patterns = [
        r"(?:DOCUMENT\s*(?:NO|NUMBER|#)|DOC\s*(?:NO|NUMBER|#)|NO\.|PASSPORT\s*NO|ID\s*(?:NO|NUMBER))\s*[:\-]?\s*([A-Z0-9]{6,12})",
        r"(?:NUMBER)\s*[:\-]?\s*([A-Z0-9]{6,12})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def _extract_gender(text: str) -> str | None:
    """Find M or F (or MALE/FEMALE) near a SEX or GENDER label."""
    match = re.search(r"(?:SEX|GENDER)\s*[:\-]?\s*([MF])\b", text, re.IGNORECASE)
    if match:
        return "Male" if match.group(1).upper() == "M" else "Female"

    match_full = re.search(r"(?:SEX|GENDER)\s*[:\-]?\s*(MALE|FEMALE)", text, re.IGNORECASE)
    if match_full:
        return match_full.group(1).capitalize()

    return None


def _extract_nationality(text: str) -> str | None:
    """Find a 2-3 letter country code near a NATIONALITY or CITIZEN label."""
    match = re.search(
        r"(?:NATIONALITY|CITIZEN(?:SHIP)?|NATION)\s*[:\-]?\s*([A-Z]{2,3})\b",
        text, re.IGNORECASE,
    )
    return match.group(1).upper() if match else None
