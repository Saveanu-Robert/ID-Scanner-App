"""Document scanning endpoint.

Handles image upload, validates the file, then runs a multi-stage
extraction pipeline: MRZ region crop -> full image MRZ -> regex fallback.
"""

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.schemas import ScanResult
from app.services.image_preprocessor import extract_mrz_region, preprocess_image
from app.services.ocr_service import extract_text, extract_text_for_mrz
from app.services.mrz_service import detect_mrz, parse_mrz
from app.services.field_extractor import extract_fields

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/bmp",
    "image/tiff",
    "image/webp",
}

ALLOWED_EXTENSIONS = {"jpeg", "jpg", "png", "bmp", "tiff", "webp"}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/scan", response_model=ScanResult)
async def scan_document(file: UploadFile = File(...)) -> ScanResult:
    """Accept an uploaded document image and extract personal information from it."""

    if file.filename:
        extension = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type '.{extension}'. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type '{file.content_type}'. Allowed types: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}",
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum of {MAX_FILE_SIZE // (1024 * 1024)}MB",
        )

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        best_result: ScanResult | None = None
        best_score = -1

        # Step 1 — Crop the MRZ region (bottom 30% of the image) and try
        # multiple preprocessing variants. Cropping first avoids non-MRZ
        # text bleeding into the OCR output.
        mrz_region_variants = extract_mrz_region(file_bytes)
        for variant in mrz_region_variants:
            mrz_text = extract_text_for_mrz(variant)
            mrz_lines = detect_mrz(mrz_text)
            if mrz_lines:
                result = parse_mrz(mrz_lines)
                if result.success and result.mrz_data and result.mrz_data.valid:
                    logger.info("MRZ detected from cropped region with valid checksums")
                    return result
                score = _result_quality_score(result)
                if score > best_score:
                    best_score = score
                    best_result = result

        # Step 2 — If the cropped region didn't work, try the full image.
        # Some documents have MRZ text that extends beyond the bottom 30%.
        binary_image, grayscale_image = preprocess_image(file_bytes)

        for image in (binary_image, grayscale_image):
            mrz_text = extract_text_for_mrz(image)
            mrz_lines = detect_mrz(mrz_text)
            if mrz_lines:
                result = parse_mrz(mrz_lines)
                if result.success and result.mrz_data and result.mrz_data.valid:
                    logger.info("MRZ detected from full image with valid checksums")
                    return result
                score = _result_quality_score(result)
                if score > best_score:
                    best_score = score
                    best_result = result

        if best_result is not None:
            logger.info("Returning best MRZ result (checksums did not validate)")
            return best_result

        # Step 3 — No MRZ found at all. Fall back to general OCR and try
        # to pull out fields using regex patterns (name, dates, etc.).
        logger.info("No MRZ detected, falling back to general OCR")
        general_text = extract_text(grayscale_image)
        return extract_fields(general_text)

    except ValueError as exc:
        logger.error("Image processing error: %s", exc)
        return ScanResult(
            success=False,
            error=f"Image processing error: {str(exc)}",
        )
    except Exception as exc:
        logger.exception("Unexpected error during document scan")
        return ScanResult(
            success=False,
            error=f"An unexpected error occurred: {str(exc)}",
        )


def _result_quality_score(result: ScanResult) -> int:
    """Rank non-validating MRZ results so we can pick the cleanest one.

    When multiple preprocessing variants detect an MRZ but none pass
    checksum validation, we need a way to choose the least noisy result.
    """
    score = 0

    for field in (result.full_name, result.date_of_birth, result.gender,
                  result.nationality, result.document_number, result.expiry_date):
        if field:
            score += 10

    # Properly formatted dates are a good signal that fields are aligned correctly
    for date_field in (result.date_of_birth, result.expiry_date):
        if date_field and "/" in date_field:
            score += 5

    if result.gender in ("Male", "Female"):
        score += 5

    # Extremely long names usually mean OCR noise leaked into the name field
    if result.full_name:
        score -= max(0, len(result.full_name) - 40)

    return score
