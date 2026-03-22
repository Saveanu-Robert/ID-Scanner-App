"""Pydantic models for the scan API request/response."""

from pydantic import BaseModel


class MRZData(BaseModel):
    """The raw MRZ text and validation result extracted from a document."""

    raw_text: str
    mrz_type: str   # "TD1" (ID cards), "TD2" (some IDs), or "TD3" (passports)
    valid: bool     # True if all ICAO 9303 checksums passed


class ScanResult(BaseModel):
    """Everything we extracted from scanning a document image.

    When MRZ is detected, most fields come from parsing the machine-readable
    zone. When no MRZ is found, we fall back to regex-based text extraction
    and the results will be less reliable (confidence=LOW).
    """

    success: bool
    document_type: str | None = None
    full_name: str | None = None
    surname: str | None = None
    given_names: str | None = None
    date_of_birth: str | None = None
    nationality: str | None = None
    document_number: str | None = None
    expiry_date: str | None = None
    gender: str | None = None
    issuing_country: str | None = None
    mrz_data: MRZData | None = None
    raw_ocr_text: str | None = None
    error: str | None = None
    confidence: str | None = None  # "HIGH" = checksums valid, "MEDIUM" = MRZ found but checksums failed, "LOW" = no MRZ
