import { useCallback, useState } from 'react';
import axios from 'axios';
import Header from './components/Header';
import ImageUploader from './components/ImageUploader';
import ScanButton from './components/ScanButton';
import ResultsCard from './components/ResultsCard';
import ErrorMessage from './components/ErrorMessage';
import { scanDocument } from './api/scanApi';
import { ScanResult } from './types';

function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFileSelect = useCallback((file: File | null) => {
    setSelectedFile(file);
    setResult(null);
    setError(null);
  }, []);

  const handleScan = useCallback(async () => {
    if (!selectedFile) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const scanResult = await scanDocument(selectedFile);
      setResult(scanResult);
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const serverMessage =
          err.response?.data?.detail ?? err.response?.data?.error;
        if (typeof serverMessage === 'string') {
          setError(serverMessage);
        } else if (err.message) {
          setError(err.message);
        } else {
          setError('An unexpected error occurred while scanning the document.');
        }
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred while scanning the document.');
      }
    } finally {
      setLoading(false);
    }
  }, [selectedFile]);

  return (
    <div className="min-h-screen bg-gray-100">
      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
        <Header />
        <ImageUploader
          onFileSelect={handleFileSelect}
          selectedFile={selectedFile}
          disabled={loading}
        />
        <ScanButton
          onClick={handleScan}
          disabled={!selectedFile || loading}
          loading={loading}
        />
        {error && <ErrorMessage message={error} />}
        {result && <ResultsCard result={result} />}
      </div>
    </div>
  );
}

export default App;
