import { useState } from 'react';
import { ScanResult } from '../types';

interface ResultsCardProps {
  result: ScanResult;
}

interface FieldDisplayProps {
  label: string;
  value: string | null;
}

function FieldDisplay({ label, value }: FieldDisplayProps) {
  return (
    <div className="py-2">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">
        {label}
      </p>
      {value ? (
        <p className="text-base text-gray-900 font-medium">{value}</p>
      ) : (
        <p className="text-base text-gray-400 italic">Not detected</p>
      )}
    </div>
  );
}

function getConfidenceBadgeClasses(confidence: string): string {
  switch (confidence.toUpperCase()) {
    case 'HIGH':
      return 'bg-green-100 text-green-800';
    case 'MEDIUM':
      return 'bg-yellow-100 text-yellow-800';
    case 'LOW':
      return 'bg-red-100 text-red-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
}

function ResultsCard({ result }: ResultsCardProps) {
  const [showMrz, setShowMrz] = useState(false);
  const [showRawOcr, setShowRawOcr] = useState(false);

  if (!result.success) {
    return (
      <div className="bg-white rounded-2xl shadow-lg p-8">
        <h2 className="text-2xl font-bold text-gray-900 mb-4">Scan Results</h2>
        <div className="bg-red-50 border border-red-200 rounded-xl p-6">
          <div className="flex items-center gap-3">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-6 w-6 text-red-500 flex-shrink-0"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            <p className="text-red-700 font-medium">
              {result.error ?? 'An unknown error occurred during scanning.'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl shadow-lg p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Scan Results</h2>

      {/* Badges */}
      <div className="flex flex-wrap gap-3 mb-6">
        {result.document_type && (
          <span className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-semibold bg-blue-100 text-blue-800">
            {result.document_type}
          </span>
        )}
        {result.confidence && (
          <span
            className={`inline-flex items-center px-3 py-1.5 rounded-full text-sm font-semibold ${getConfidenceBadgeClasses(result.confidence)}`}
          >
            Confidence: {result.confidence}
          </span>
        )}
      </div>

      {/* Fields Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2 mb-6 border-t border-gray-100 pt-4">
        <FieldDisplay label="Full Name" value={result.full_name} />
        <FieldDisplay label="Date of Birth" value={result.date_of_birth} />
        <FieldDisplay label="Gender" value={result.gender} />
        <FieldDisplay label="Nationality" value={result.nationality} />
        <FieldDisplay label="Document Number" value={result.document_number} />
        <FieldDisplay label="Expiry Date" value={result.expiry_date} />
        <FieldDisplay label="Issuing Country" value={result.issuing_country} />
      </div>

      {/* MRZ Data Collapsible */}
      {result.mrz_data && (
        <div className="border-t border-gray-100 pt-4 mb-4">
          <button
            onClick={() => setShowMrz(!showMrz)}
            className="flex items-center gap-2 w-full text-left text-sm font-semibold text-gray-700 hover:text-gray-900 transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className={`h-4 w-4 transition-transform duration-200 ${showMrz ? 'rotate-90' : ''}`}
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                clipRule="evenodd"
              />
            </svg>
            MRZ Data
            <span
              className={`ml-2 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                result.mrz_data.valid
                  ? 'bg-green-100 text-green-700'
                  : 'bg-red-100 text-red-700'
              }`}
            >
              {result.mrz_data.valid ? 'Valid' : 'Invalid'}
            </span>
          </button>
          {showMrz && (
            <div className="mt-3 bg-gray-50 rounded-lg p-4">
              <p className="text-xs text-gray-500 mb-2">
                Type: {result.mrz_data.mrz_type}
              </p>
              <pre className="font-mono text-sm text-gray-800 whitespace-pre-wrap break-all">
                {result.mrz_data.raw_text}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Raw OCR Text Collapsible */}
      {result.raw_ocr_text && (
        <div className="border-t border-gray-100 pt-4">
          <button
            onClick={() => setShowRawOcr(!showRawOcr)}
            className="flex items-center gap-2 w-full text-left text-sm font-semibold text-gray-700 hover:text-gray-900 transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className={`h-4 w-4 transition-transform duration-200 ${showRawOcr ? 'rotate-90' : ''}`}
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                clipRule="evenodd"
              />
            </svg>
            Raw OCR Text
          </button>
          {showRawOcr && (
            <div className="mt-3 bg-gray-50 rounded-lg p-4">
              <pre className="font-mono text-sm text-gray-800 whitespace-pre-wrap break-all">
                {result.raw_ocr_text}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ResultsCard;
