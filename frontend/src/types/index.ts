export interface MRZData {
  raw_text: string;
  mrz_type: string;
  valid: boolean;
}

export interface ScanResult {
  success: boolean;
  document_type: string | null;
  full_name: string | null;
  surname: string | null;
  given_names: string | null;
  date_of_birth: string | null;
  nationality: string | null;
  document_number: string | null;
  expiry_date: string | null;
  gender: string | null;
  issuing_country: string | null;
  mrz_data: MRZData | null;
  raw_ocr_text: string | null;
  error: string | null;
  confidence: string | null;
}
