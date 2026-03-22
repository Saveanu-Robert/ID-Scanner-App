"""Image preprocessing for OCR.

Handles decoding, resizing (up and down), grayscale conversion, denoising,
contrast enhancement (CLAHE), binarization, and deskewing. Small images are
automatically upscaled so Tesseract can read the MRZ characters.
"""

import cv2
import numpy as np

_MIN_MRZ_WIDTH = 1200


def preprocess_image(image_bytes: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Run the full preprocessing pipeline on a document image.

    Returns (binary_image, enhanced_grayscale) — two versions of the same
    image optimized for different OCR scenarios.
    """
    image = _decode_and_normalize(image_bytes)

    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(grayscale, h=10)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)

    binary = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, blockSize=11, C=2,
    )
    binary = _deskew(binary)

    return binary, enhanced


def extract_mrz_region(image_bytes: bytes) -> list[np.ndarray]:
    """Crop the bottom 30% of the image (where the MRZ lives) and produce
    multiple binarization variants to give OCR the best chance of reading it.

    We generate four variants because different images respond better to
    different thresholding methods depending on lighting, contrast, and
    background patterns (watermarks, holograms, etc.).
    """
    image = _decode_and_normalize(image_bytes)
    height, width = image.shape[:2]

    mrz_region = image[int(height * 0.70):height, 0:width]

    # The MRZ crop can be very small on low-res images. Upscale it so
    # Tesseract has enough pixels to distinguish individual characters.
    mrz_h, mrz_w = mrz_region.shape[:2]
    if mrz_w < _MIN_MRZ_WIDTH:
        scale = _MIN_MRZ_WIDTH / mrz_w
        mrz_region = cv2.resize(
            mrz_region,
            (int(mrz_w * scale), int(mrz_h * scale)),
            interpolation=cv2.INTER_CUBIC,
        )

    grayscale = cv2.cvtColor(mrz_region, cv2.COLOR_BGR2GRAY)
    variants: list[np.ndarray] = []

    # Variant 1 — CLAHE + adaptive threshold: handles uneven lighting well
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(cv2.fastNlMeansDenoising(grayscale, h=10))
    binary_adaptive = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, blockSize=11, C=2,
    )
    variants.append(binary_adaptive)

    # Variant 2 — Otsu threshold: works best on clean, high-contrast MRZ
    blurred = cv2.GaussianBlur(grayscale, (3, 3), 0)
    _, binary_otsu = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    variants.append(binary_otsu)

    # Variant 3 — Aggressive CLAHE + Otsu: pulls out faint MRZ text
    clahe_strong = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    strong_enhanced = clahe_strong.apply(grayscale)
    _, binary_strong = cv2.threshold(
        strong_enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    variants.append(binary_strong)

    # Variant 4 — Enhanced grayscale without binarization: lets Tesseract
    # apply its own internal thresholding, which sometimes works better
    variants.append(enhanced)

    return variants


def _decode_and_normalize(image_bytes: bytes) -> np.ndarray:
    """Decode raw bytes into an OpenCV image and normalize the size.

    Small images get upscaled for better OCR accuracy. Very large images
    get downscaled to keep processing time reasonable.
    """
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError("Failed to decode image from provided bytes")

    height, width = image.shape[:2]

    if width < _MIN_MRZ_WIDTH:
        scale = _MIN_MRZ_WIDTH / width
        image = cv2.resize(
            image,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_CUBIC,
        )

    height, width = image.shape[:2]
    max_dimension = 2500
    if max(height, width) > max_dimension:
        scale = max_dimension / max(height, width)
        image = cv2.resize(
            image,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_AREA,
        )

    return image


def _deskew(image: np.ndarray) -> np.ndarray:
    """Straighten a slightly tilted document by finding the largest contour
    and rotating to correct its angle. Only fixes small tilts (< 15 degrees).
    """
    contours, _ = cv2.findContours(
        cv2.bitwise_not(image), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
    )
    if not contours:
        return image

    largest_contour = max(contours, key=cv2.contourArea)
    angle = cv2.minAreaRect(largest_contour)[2]

    if angle < -45:
        angle = 90 + angle
    elif angle > 45:
        angle = angle - 90

    if abs(angle) > 15 or abs(angle) < 0.5:
        return image

    height, width = image.shape[:2]
    center = (width // 2, height // 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image, rotation_matrix, (width, height),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )
