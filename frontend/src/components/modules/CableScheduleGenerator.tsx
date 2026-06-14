/**
 * Cable Schedule Generator
 * Upload IODB + Cable Schedule template, pick JB/Tag columns, preview JB summary, generate.
 */
import { useState } from 'react';
import { Cable, Upload, FileText, Download, CheckCircle2 } from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import FileUploadCard from '../ui/FileUploadCard';

interface ColumnsResponse {
  columns: string[];
}

interface JBSummaryRow {
  junction_box: string;
  tag_count: number;
}

interface JBSummaryResponse {
  rows: JBSummaryRow[];
}

interface GenerateResponse {
  filename: string;
  message: string;
}

export default function CableScheduleGenerator() {
  const [iodbFile, setIodbFile] = useState<File | null>(null);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [jbColumn, setJbColumn] = useState('');
  const [tagColumn, setTagColumn] = useState('');
  const [jbSummary, setJbSummary] = useState<JBSummaryRow[] | null>(null);
  const [result, setResult] = useState<GenerateResponse | null>(null);

  const [loadingColumns, setLoadingColumns] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLoadColumns = async () => {
    if (!iodbFile) return;
    setLoadingColumns(true);
    setError(null);
    setColumns([]);
    setJbColumn('');
    setTagColumn('');
    setJbSummary(null);
    setResult(null);

    const formData = new FormData();
    formData.append('file', iodbFile);

    try {
      const response = await api.post<ColumnsResponse>('/cable-schedule/columns', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setColumns(response.data.columns);

      // Pre-select likely JB/Tag columns
      const jbGuess = response.data.columns.find((c) => c.toUpperCase().includes('JUNCTION'));
      const tagGuess = response.data.columns.find((c) => c.toUpperCase().includes('TAG'));
      if (jbGuess) setJbColumn(jbGuess);
      if (tagGuess) setTagColumn(tagGuess);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to read IODB columns');
    } finally {
      setLoadingColumns(false);
    }
  };

  const handlePreview = async () => {
    if (!iodbFile || !jbColumn || !tagColumn) return;
    setLoadingPreview(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', iodbFile);
    formData.append('jb_column', jbColumn);
    formData.append('tag_column', tagColumn);

    try {
      const response = await api.post<JBSummaryResponse>('/cable-schedule/preview', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setJbSummary(response.data.rows);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to build junction box summary');
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleGenerate = async () => {
    if (!iodbFile || !templateFile || !jbColumn || !tagColumn) return;
    setGenerating(true);
    setError(null);

    const formData = new FormData();
    formData.append('iodb_file', iodbFile);
    formData.append('template_file', templateFile);
    formData.append('jb_column', jbColumn);
    formData.append('tag_column', tagColumn);

    try {
      const response = await api.post<GenerateResponse>('/cable-schedule/generate', formData, {
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
      const response = await api.get('/cable-schedule/download', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', result?.filename || 'Cable_Schedule.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Download failed');
    }
  };

  const totalTags = jbSummary?.reduce((sum, r) => sum + r.tag_count, 0) || 0;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Cable}
        iconClassName="text-red-500"
        title="Cable Schedule Generator"
        description="Generate a cable schedule grouped by junction box from your IODB and Cable Schedule template."
      />

      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}

      {/* File Uploads */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FileUploadCard
          title="IODB Source File"
          icon={Upload}
          file={iodbFile}
          onChange={(f) => {
            setIodbFile(f);
            setColumns([]);
            setJbSummary(null);
            setResult(null);
          }}
        >
          <Button onClick={handleLoadColumns} disabled={!iodbFile} loading={loadingColumns} fullWidth className="mt-3 bg-blue-600 hover:bg-blue-700">
            {loadingColumns ? 'Loading Columns...' : 'Load Columns'}
          </Button>
        </FileUploadCard>

        <FileUploadCard
          title="Cable Schedule Template"
          icon={FileText}
          file={templateFile}
          onChange={setTemplateFile}
          hint="Required: provide the Cable Schedule Excel template to generate into."
        />
      </div>

      {/* JB/Tag Column mapping */}
      {columns.length > 0 && (
        <Card title="Junction Box & Tag Column Mapping">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Junction Box Column</label>
              <select
                value={jbColumn}
                onChange={(e) => setJbColumn(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">Select column...</option>
                {columns.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Tag Number Column</label>
              <select
                value={tagColumn}
                onChange={(e) => setTagColumn(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">Select column...</option>
                {columns.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>

          <Button
            onClick={handlePreview}
            disabled={!jbColumn || !tagColumn}
            loading={loadingPreview}
            className="mt-4 bg-blue-600 hover:bg-blue-700"
          >
            {loadingPreview ? 'Building Summary...' : 'Preview Junction Box Summary'}
          </Button>
        </Card>
      )}

      {/* JB Summary */}
      {jbSummary && (
        <Card title={`Junction Box Summary (${jbSummary.length} JBs, ${totalTags} tags)`}>
          <div className="border border-gray-200 rounded-lg overflow-auto max-h-96">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Junction Box</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Tag Count</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {jbSummary.map((row, idx) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="px-3 py-2 text-gray-900 font-medium">{row.junction_box}</td>
                    <td className="px-3 py-2 text-gray-700">{row.tag_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Generate */}
          <Button
            onClick={handleGenerate}
            disabled={!templateFile}
            loading={generating}
            size="lg"
            fullWidth
            className="text-lg py-4 mt-6"
          >
            <Cable className="w-6 h-6" />
            {generating ? 'Generating...' : 'Generate Cable Schedule'}
          </Button>
          {!templateFile && (
            <p className="text-sm text-gray-500 mt-2 text-center">Upload a Cable Schedule template above to enable generation.</p>
          )}
        </Card>
      )}

      {/* Result */}
      {result && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <CheckCircle2 className="w-12 h-12 text-green-500 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="text-xl font-bold text-green-800 mb-2">Cable Schedule Generated!</h3>
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
