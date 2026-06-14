/**
 * Loop Wiring Generator
 * Upload Loop Wiring input + template, preview tags, generate per-tag sheets.
 */
import { useState } from 'react';
import { GitBranch, Upload, FileText, Download, CheckCircle2 } from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import FileUploadCard from '../ui/FileUploadCard';

interface PreviewResponse {
  tags: string[];
  count: number;
  preview: Record<string, any>[];
}

interface GenerateResponse {
  filename: string;
  message: string;
  sheet_count: number;
}

export default function LoopWiringGenerator() {
  const [inputFile, setInputFile] = useState<File | null>(null);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [result, setResult] = useState<GenerateResponse | null>(null);

  const [loadingPreview, setLoadingPreview] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePreview = async () => {
    if (!inputFile) return;
    setLoadingPreview(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append('file', inputFile);

    try {
      const response = await api.post<PreviewResponse>('/loop-wiring/preview', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setPreview(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to read Loop Wiring input file');
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleGenerate = async () => {
    if (!inputFile || !templateFile) return;
    setGenerating(true);
    setError(null);

    const formData = new FormData();
    formData.append('loop_input_file', inputFile);
    formData.append('template_file', templateFile);

    try {
      const response = await api.post<GenerateResponse>('/loop-wiring/generate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async () => {
    try {
      const response = await api.get('/loop-wiring/download', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', result?.filename || 'Loop_Wiring.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Download failed');
    }
  };

  const previewColumns = preview && preview.preview.length > 0 ? Object.keys(preview.preview[0]) : [];

  return (
    <div className="space-y-6">
      <PageHeader
        icon={GitBranch}
        iconClassName="text-indigo-500"
        title="Loop Wiring Generator"
        description="Generate one loop wiring sheet per tag from your Loop Wiring input file and template."
      />

      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}

      {/* File Uploads */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FileUploadCard
          title="Loop Wiring Input File"
          icon={Upload}
          file={inputFile}
          onChange={(f) => {
            setInputFile(f);
            setPreview(null);
            setResult(null);
          }}
        >
          <Button onClick={handlePreview} disabled={!inputFile} loading={loadingPreview} fullWidth className="mt-3 bg-blue-600 hover:bg-blue-700">
            {loadingPreview ? 'Reading File...' : 'Preview Tags'}
          </Button>
        </FileUploadCard>

        <FileUploadCard
          title="Loop Wiring Template"
          icon={FileText}
          file={templateFile}
          onChange={setTemplateFile}
          hint="Required: provide the Loop Wiring Excel template to generate into."
        />
      </div>

      {/* Preview */}
      {preview && (
        <Card title={`${preview.count} Tag(s) Found`}>
          <div className="flex flex-wrap gap-2 mb-4">
            {preview.tags.map((tag) => (
              <span key={tag} className="text-xs px-2 py-1 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
                {tag}
              </span>
            ))}
          </div>

          {previewColumns.length > 0 && (
            <div className="border border-gray-200 rounded-lg overflow-auto max-h-80">
              <table className="w-full text-sm whitespace-nowrap">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    {previewColumns.map((col) => (
                      <th key={col} className="px-3 py-2 text-left font-medium text-gray-700">{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {preview.preview.map((row, idx) => (
                    <tr key={idx} className="hover:bg-gray-50">
                      {previewColumns.map((col) => (
                        <td key={col} className="px-3 py-2 text-gray-700">{row[col] ?? ''}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Generate */}
          <Button
            onClick={handleGenerate}
            disabled={!templateFile}
            loading={generating}
            size="lg"
            fullWidth
            className="text-lg py-4 mt-6"
          >
            <GitBranch className="w-6 h-6" />
            {generating ? `Generating ${preview.count} Sheets...` : `Generate Loop Wiring (${preview.count} tags)`}
          </Button>
          {!templateFile && (
            <p className="text-sm text-gray-500 mt-2 text-center">Upload a Loop Wiring template above to enable generation.</p>
          )}
        </Card>
      )}

      {/* Result */}
      {result && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <CheckCircle2 className="w-12 h-12 text-green-500 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="text-xl font-bold text-green-800 mb-2">Loop Wiring Generated!</h3>
              <p className="text-green-700 mb-4">{result.message}</p>
              <Button onClick={handleDownload} className="bg-green-600 hover:bg-green-700">
                <Download className="w-5 h-5" />
                Download {result.filename}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
