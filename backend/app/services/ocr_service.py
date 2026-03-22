"""Tesseract OCR integration.

Provides two OCR modes: general-purpose text extraction and MRZ-optimized
extraction with a restricted character whitelist (A-Z, 0-9, <).
The MRZ mode tries multiple Tesseract page segmentation modes and picks
whichever produces the most MRZ-like output.
"""

import os
import logging

import numpy as np
import pytesseract

logger = logging.getLogger(__name__)

# Try to find Tesseract in the standard Windows install locations.
# On Linux/macOS it's usually already on PATH so this isn't needed.
_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

for _path in _TESSERACT_PATHS:
    if os.path.isfile(_path):
        pytesseract.pytesseract.tesseract_cmd = _path
        logger.info("Tesseract found at: %s", _path)
        break
else:
    logger.warning(
        "Tesseract not found in standard Windows paths. "
        "Ensure it is installed and available on PATH."
    )

# Only these characters can appear in a valid MRZ line
_MRZ_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"


def extract_text(image: np.ndarray) -> str:
    """Run general-purpose OCR on an image. Used as a fallback when no MRZ is found."""
    config = "--oem 3 --psm 6"
    text: str = pytesseract.image_to_string(image, config=config)
    return text.strip()


def extract_text_for_mrz(image: np.ndarray) -> str:
    """Run MRZ-optimized OCR using a restricted character whitelist.

    Tries three different page segmentation modes (PSM 6, 4, and 12)
    because different document layouts respond better to different modes.
    Returns whichever attempt produces the most MRZ-looking lines.
    """
    configs = [
        f"--oem 3 --psm 6 -c tessedit_char_whitelist={_MRZ_WHITELIST}",
        f"--oem 3 --psm 4 -c tessedit_char_whitelist={_MRZ_WHITELIST}",
        f"--oem 3 --psm 12 -c tessedit_char_whitelist={_MRZ_WHITELIST}",
    ]

    best_text = ""
    best_score = 0

    for config in configs:
        text: str = pytesseract.image_to_string(image, config=config).strip()
        score = _mrz_line_score(text)
        if score > best_score:
            best_score = score
            best_text = text

    return best_text


def _mrz_line_score(text: str) -> int:
    """Score how "MRZ-like" a block of OCR text looks.

    Lines that are all valid MRZ characters and close to the expected
    lengths (30, 36, or 44 chars) score highest. This lets us pick the
    best result when we try multiple Tesseract configurations.
    """
    score = 0
    for line in text.splitlines():
        cleaned = line.strip().replace(" ", "")
        if not cleaned:
            continue
        if all(c in _MRZ_WHITELIST for c in cleaned):
            length = len(cleaned)
            for target in (30, 36, 44):
                if abs(length - target) <= 2:
                    score += 10 + length
                    break
            else:
                if length >= 20:
                    score += 1
    return score
