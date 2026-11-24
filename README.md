# ID & Passport Scanner

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?logo=fastapi&logoColor=white)
![React 19](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react&logoColor=black)
![Tesseract OCR](https://img.shields.io/badge/OCR-Tesseract-5A5A5A.svg)

A demo application that extracts personal information from ID cards and passports using OCR and MRZ (Machine Readable Zone) parsing.

Upload a photo of an identity document, click **Scan**, and the app pulls out the holder's name, date of birth, nationality, document number, expiry date, and gender.

## How it works

The backend runs a multi-stage extraction pipeline:

1. **MRZ region cropping** — The bottom 30% of the image is cropped out (where the MRZ always sits) and run through multiple preprocessing variants (adaptive threshold, Otsu, strong CLAHE, raw grayscale).

2. **OCR with Tesseract** — Each preprocessed variant is fed to Tesseract with a restricted character whitelist (`A-Z`, `0-9`, `<`). Multiple page segmentation modes are tried and the best result is kept.

3. **MRZ detection** — The OCR text is scanned for lines that look like MRZ data (28-46 characters of only uppercase letters, digits, and `<`). Lines are grouped by length to identify the document format: TD1 (ID cards, 3×30), TD2 (some IDs, 2×36), or TD3 (passports, 2×44).

4. **OCR error correction** — Before parsing, a correction pass fixes common Tesseract mistakes:
   - Characters in digit-only positions (dates, check digits) get letter→digit fixes (`O`→`0`, `S`→`5`, etc.)
   - Characters in letter-only positions (nationality, names) get digit→letter fixes
   - The `<` filler character is frequently misread as `K` or `G` — these are cleaned up using cluster analysis and boundary detection
   - If the check digit position holds a letter, the line is likely shifted left (OCR dropped a leading `0`), so we prepend `0` and re-parse
   - If the country code in line 1 doesn't match the nationality in line 2, we try reconstructing line 1 by inserting the nationality

5. **MRZ parsing** — Fields are extracted from their ICAO 9303 positions and checksums are validated using the `mrz` library.

6. **Regex fallback** — If no MRZ is found, general OCR runs on the full image and regex patterns try to find labeled fields like `NAME:`, `DOB:`, `PASSPORT NO:`, etc. Results from this path are marked as LOW confidence.

### Confidence levels

| Level    | Meaning                                           |
|----------|---------------------------------------------------|
| **HIGH** | MRZ detected and all checksums passed             |
| **MEDIUM** | MRZ detected but checksums failed (OCR errors)  |
| **LOW**  | No MRZ found, fields extracted via regex fallback |

## Tech stack

| Layer      | Technology                                     |
|------------|------------------------------------------------|
| Backend    | Python 3.12+ · FastAPI · Uvicorn               |
| OCR        | Tesseract OCR (via pytesseract)                |
| MRZ        | `mrz` library for checksum validation          |
| Images     | OpenCV (headless) · Pillow · NumPy             |
| Frontend   | React 19 · TypeScript · Vite · Tailwind CSS 3  |
| HTTP       | Axios                                          |

## Prerequisites

- **Python 3.12+**
- **Node.js 18+**
- **Tesseract OCR** — the OCR engine that does the actual text recognition

### Installing Tesseract

**Windows:**
```bash
winget install UB-Mannheim.TesseractOCR
```
This installs to `C:\Program Files\Tesseract-OCR\` — the backend auto-detects this path.

**macOS:**
```bash
brew install tesseract
```

**Ubuntu/Debian:**
```bash
sudo apt install tesseract-ocr
```

## Getting started

Clone the repository:

```bash
git clone https://github.com/Saveanu-Robert/ID-Scanner-App.git
cd ID-Scanner-App
```

### Backend

```bash
cd backend
python -m venv venv

# Activate the virtual environment
# Windows:
.\venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. You can check it's running by visiting `http://localhost:8000/` (health check) or `http://localhost:8000/docs` (Swagger UI).

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser. The Vite dev server proxies `/api` requests to the backend on port 8000.

## Project structure

```
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI app, CORS, health check
│   │   ├── routes/
│   │   │   └── scan.py                 # POST /api/scan endpoint
│   │   ├── services/
│   │   │   ├── image_preprocessor.py   # OpenCV preprocessing pipeline
│   │   │   ├── ocr_service.py          # Tesseract OCR wrapper
│   │   │   ├── mrz_service.py          # MRZ detection, parsing, error correction
│   │   │   └── field_extractor.py      # Regex fallback for non-MRZ documents
│   │   └── models/
│   │       └── schemas.py              # Pydantic request/response models
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx                     # Main layout and state management
│   │   ├── api/
│   │   │   └── scanApi.ts              # API client for /api/scan
│   │   ├── components/
│   │   │   ├── Header.tsx              # Page title and description
│   │   │   ├── ImageUploader.tsx       # Drag-and-drop file upload with preview
│   │   │   ├── ScanButton.tsx          # Scan trigger with loading spinner
│   │   │   ├── ResultsCard.tsx         # Extracted fields display
│   │   │   └── ErrorMessage.tsx        # Error alert
│   │   └── types/
│   │       └── index.ts                # TypeScript interfaces
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── tsconfig.json
└── README.md
```

## API reference

### `POST /api/scan`

Upload a document image and get extracted fields back.

**Request:** `multipart/form-data` with a `file` field containing the image.

**Constraints:**
- Allowed types: JPEG, PNG, BMP, TIFF, WebP
- Max file size: 10 MB

**Response example:**
```json
{
  "success": true,
  "document_type": "Passport",
  "full_name": "MICHELLE DELAPAZ",
  "surname": "DELAPAZ",
  "given_names": "MICHELLE",
  "date_of_birth": "17/01/1964",
  "nationality": "USA",
  "document_number": "910239248",
  "expiry_date": "05/12/2018",
  "gender": "Female",
  "issuing_country": "USA",
  "confidence": "HIGH",
  "mrz_data": {
    "raw_text": "P<USADELAPAZ<<MICHELLE<<<<<<<<<<<<<<<<<<<<<<<<\n9102392482USA6401171F1812051900781200<129676",
    "mrz_type": "TD3",
    "valid": true
  },
  "raw_ocr_text": "...",
  "error": null
}
```

### `GET /`

Health check. Returns `{"status": "healthy", "service": "ID Document Scanner API"}`.

## Known limitations

- **Image quality matters.** Low-resolution images (under ~800px wide) or photos taken at sharp angles will produce worse results. For best accuracy, use a flat scan or a well-lit, straight-on photo.
- **Tesseract is not perfect.** Some characters in the MRZ can be misread, especially `0`/`O`, `1`/`I`, and `<`/`K`. The correction pipeline handles the most common mistakes, but very noisy images may still produce errors.
- **Watermarks and holograms** can interfere with OCR, particularly on passports where a large watermark overlaps the MRZ area.
- **This is a demo application** — not intended for production identity verification. Real-world systems use specialized hardware (infrared/UV scanning) and certified SDKs.

## License

Released under the [MIT License](LICENSE).
