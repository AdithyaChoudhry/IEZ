/**
 * Smart Datasheet Intelligence Engine (SDIE) — Phase 1
 * Upload a vendor datasheet (PDF/image), OCR it, and preview extracted
 * specifications mapped to canonical WABAG field names with confidence scores.
 */
import { useState } from 'react';
import { ScanSearch, Upload, FileSpreadsheet, CheckCircle2, Download } from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import FileUploadCard from '../ui/FileUploadCard';

interface ExtractedSpec {
  raw_label: string;
  value: string;
  canonical_field: string | null;
  match_score: number;
  confidence: number;
  page: number;
}

interface ExtractionResponse {
  specs: ExtractedSpec[];
  page_count: number;
  message: string;
}

interface ExtractionJob {
  job_id: string;
  status: string;
}

interface ExtractionStatus {
  job_id: string;
  status: 'processing' | 'done' | 'error';
  result?: ExtractionResponse;
  error?: string;
}

interface MappingLogEntry {
  heading: string;
  canonical_field: string | null;
  score: number;
  value: string;
  status: 'MATCHED' | 'UNMATCHED';
}

interface GenerateResponse extends ExtractionResponse {
  mapping_log: MappingLogEntry[];
  filename: string;
}

interface GenerateJob {
  job_id: string;
  status: string;
}

interface GenerateStatus {
  job_id: string;
  status: 'processing' | 'done' | 'error';
  result?: GenerateResponse;
  error?: string;
}

const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 200; // ~10 minutes

function confidenceBadge(value: number) {
  let color = 'bg-red-50 text-red-700 border-red-200';
  if (value >= 80) {
    color = 'bg-green-50 text-green-700 border-green-200';
  } else if (value >= 50) {
    color = 'bg-yellow-50 text-yellow-700 border-yellow-200';
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded border font-medium ${color}`}>
      {value.toFixed(0)}%
    </span>
  );
}

export default function SmartDatasheetExtractor() {
  const [file, setFile] = useState<File | null>(null);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [result, setResult] = useState<ExtractionResponse | null>(null);
  const [generateResult, setGenerateResult] = useState<GenerateResponse | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExtract = async () => {
    if (!file) return;
    setExtracting(true);
    setError(null);
    setResult(null);
    setGenerateResult(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const kickoff = await api.post<ExtractionJob>('/sdie/extract', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const jobId = kickoff.data.job_id;

      for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));

        const statusResponse = await api.get<ExtractionStatus>(`/sdie/extract/status/${jobId}`);
        const { status: jobStatus, result: jobResult, error: jobError } = statusResponse.data;

        if (jobStatus === 'done') {
          setResult(jobResult!);
          return;
        }
        if (jobStatus === 'error') {
          setError(jobError || 'Extraction failed');
          return;
        }
      }

      setError('Extraction is taking longer than expected. Please try again later.');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Extraction failed');
    } finally {
      setExtracting(false);
    }
  };

  const handleGenerate = async () => {
    if (!file || !templateFile) return;
    setGenerating(true);
    setError(null);
    setResult(null);
    setGenerateResult(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('template_file', templateFile);

    try {
      const kickoff = await api.post<GenerateJob>('/sdie/generate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const jobId = kickoff.data.job_id;

      for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));

        const statusResponse = await api.get<GenerateStatus>(`/sdie/generate/status/${jobId}`);
        const { status: jobStatus, result: jobResult, error: jobError } = statusResponse.data;

        if (jobStatus === 'done') {
          setGenerateResult(jobResult!);
          return;
        }
        if (jobStatus === 'error') {
          setError(jobError || 'Generation failed');
          return;
        }
      }

      setError('Generation is taking longer than expected. Please try again later.');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async () => {
    try {
      const response = await api.get('/sdie/download', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', generateResult?.filename || 'Datasheet_Populated.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Download failed');
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        icon={ScanSearch}
        iconClassName="text-purple-500"
        title="Smart Datasheet Intelligence"
        description="Upload a vendor datasheet (PDF/JPG/PNG/TIFF) to OCR-extract specifications and map them to WABAG field names."
      />

      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FileUploadCard
          title="Vendor Datasheet"
          icon={Upload}
          file={file}
          accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff"
          onChange={(f) => {
            setFile(f);
            setResult(null);
            setGenerateResult(null);
          }}
        >
          <Button
            onClick={handleExtract}
            disabled={!file}
            loading={extracting}
            size="lg"
            fullWidth
            className="mt-3"
          >
            <ScanSearch className="w-5 h-5" />
            {extracting ? 'Extracting Specifications...' : 'Extract Specifications'}
          </Button>
        </FileUploadCard>

        <FileUploadCard
          title="WABAG Datasheet Template (Optional)"
          icon={FileSpreadsheet}
          file={templateFile}
          accept=".xlsx,.xlsm"
          onChange={(f) => {
            setTemplateFile(f);
            setGenerateResult(null);
          }}
          hint="Provide a WABAG template to auto-fill its 'Refer Annexure' placeholders with the extracted specs."
        >
          <Button
            onClick={handleGenerate}
            disabled={!file || !templateFile}
            loading={generating}
            size="lg"
            fullWidth
            className="mt-3 bg-purple-600 hover:bg-purple-700"
          >
            <FileSpreadsheet className="w-5 h-5" />
            {generating ? 'Generating Datasheet...' : 'Generate Populated Datasheet'}
          </Button>
        </FileUploadCard>
      </div>

      {generateResult && (
        <Card title={`Template Mapping (${generateResult.mapping_log.length} field(s))`}>
          <div className="flex items-start gap-4 mb-4 bg-green-50 border border-green-200 rounded-lg p-4">
            <CheckCircle2 className="w-6 h-6 text-green-500 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-green-700 mb-3">{generateResult.message}</p>
              <Button onClick={handleDownload} className="bg-green-600 hover:bg-green-700">
                <Download className="w-5 h-5" />
                Download {generateResult.filename}
              </Button>
            </div>
          </div>

          {generateResult.mapping_log.length > 0 && (
            <div className="border border-gray-200 rounded-lg overflow-auto max-h-[32rem]">
              <table className="w-full text-sm whitespace-nowrap">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-gray-700">Template Heading</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700">Mapped Field</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700">Match</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700">Value</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {generateResult.mapping_log.map((entry, idx) => (
                    <tr key={idx} className="hover:bg-gray-50">
                      <td className="px-3 py-2 text-gray-700">{entry.heading}</td>
                      <td className="px-3 py-2 text-gray-700">
                        {entry.canonical_field ?? <span className="text-gray-400 italic">—</span>}
                      </td>
                      <td className="px-3 py-2">{confidenceBadge(entry.score)}</td>
                      <td className="px-3 py-2 text-gray-700">{entry.value}</td>
                      <td className="px-3 py-2">
                        <span
                          className={`text-xs px-2 py-0.5 rounded border font-medium ${
                            entry.status === 'MATCHED'
                              ? 'bg-green-50 text-green-700 border-green-200'
                              : 'bg-gray-50 text-gray-500 border-gray-200'
                          }`}
                        >
                          {entry.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {result && (
        <Card title={`Extracted Specifications (${result.specs.length})`}>
          <div className="flex items-start gap-3 mb-4 bg-green-50 border border-green-200 rounded-lg p-4">
            <CheckCircle2 className="w-6 h-6 text-green-500 flex-shrink-0" />
            <p className="text-green-700">{result.message}</p>
          </div>

          {result.specs.length > 0 ? (
            <div className="border border-gray-200 rounded-lg overflow-auto max-h-[32rem]">
              <table className="w-full text-sm whitespace-nowrap">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-gray-700">Raw Label</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700">Value</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700">Mapped Field</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700">Match</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700">OCR Confidence</th>
                    <th className="px-3 py-2 text-left font-medium text-gray-700">Page</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {result.specs.map((spec, idx) => (
                    <tr key={idx} className="hover:bg-gray-50">
                      <td className="px-3 py-2 text-gray-700">{spec.raw_label}</td>
                      <td className="px-3 py-2 text-gray-700">{spec.value}</td>
                      <td className="px-3 py-2 text-gray-700">
                        {spec.canonical_field ?? (
                          <span className="text-gray-400 italic">Other technical specification</span>
                        )}
                      </td>
                      <td className="px-3 py-2">{confidenceBadge(spec.match_score)}</td>
                      <td className="px-3 py-2">{confidenceBadge(spec.confidence)}</td>
                      <td className="px-3 py-2 text-gray-700">{spec.page}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-gray-500 text-center py-6">No specifications could be extracted from this file.</p>
          )}
        </Card>
      )}
    </div>
  );
}
