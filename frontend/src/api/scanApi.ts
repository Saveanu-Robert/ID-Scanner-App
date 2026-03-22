import axios from 'axios';
import { ScanResult } from '../types';

export async function scanDocument(file: File): Promise<ScanResult> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await axios.post<ScanResult>('/api/scan', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  });

  return response.data;
}
