/**
 * Data Sheet Generator Component
 * Generate individual datasheets with fuzzy column matching
 */
import { useState } from 'react';
import {
  FileText,
  Upload,
  Download,
  CheckCircle2,
  AlertCircle,
  Search
} from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';

interface MappingLog {
  tag: string;
  heading: string;
  iodb_col?: string;
  score?: number;
  value?: string;
  status: string;
}

interface DataSheetResult {
  filename: string;
  tag_count: number;
  mapping_logs: MappingLog[];
  message: string;
}

interface TagsResponse {
  tags: string[];
  count: number;
  message?: string;
}

export default function DataSheetGenerator() {
  const [iodbFile, setIodbFile] = useState<File | null>(null);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [availableTags, setAvailableTags] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [twoRowHeader, setTwoRowHeader] = useState(true);
  const [fuzzyThreshold, setFuzzyThreshold] = useState(70);
  const [loading, setLoading] = useState(false);
  const [loadingTags, setLoadingTags] = useState(false);
  const [result, setResult] = useState<DataSheetResult | null>(null);
  const [showMappingLog, setShowMappingLog] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const handleIodbFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setIodbFile(e.target.files[0]);
      setAvailableTags([]);
      setSelectedTags([]);
      setResult(null);
    }
  };

  const handleTemplateFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setTemplateFile(e.target.files[0]);
    }
  };

  const handleLoadTags = async () => {
    if (!iodbFile) return;

    setLoadingTags(true);
    setError(null);
    setInfo(null);
    const formData = new FormData();
    formData.append('file', iodbFile);
    formData.append('two_row_header', twoRowHeader.toString());

    try {
      const response = await api.post<TagsResponse>('/datasheet/tags', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setAvailableTags(response.data.tags);
      if (response.data.message) {
        setInfo(response.data.message);
      }
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Failed to load tags');
    } finally {
      setLoadingTags(false);
    }
  };

  const handleGenerate = async () => {
    if (!iodbFile || !templateFile || selectedTags.length === 0) return;

    setLoading(true);
    setError(null);
    const formData = new FormData();
    formData.append('iodb_file', iodbFile);
    formData.append('template_file', templateFile);
    formData.append('selected_tags', JSON.stringify(selectedTags));
    formData.append('two_row_header', twoRowHeader.toString());
    formData.append('fuzzy_threshold', fuzzyThreshold.toString());

    try {
      const response = await api.post<DataSheetResult>('/datasheet/generate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(response.data);
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Generation failed');
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    try {
      const response = await api.get('/datasheet/download', {
        responseType: 'blob',
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', result?.filename || 'datasheets.zip');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Download failed');
    }
  };

  const handleSelectAll = () => {
    setSelectedTags(availableTags);
  };

  const handleDeselectAll = () => {
    setSelectedTags([]);
  };

  const handleTagToggle = (tag: string) => {
    if (selectedTags.includes(tag)) {
      setSelectedTags(selectedTags.filter(t => t !== tag));
    } else {
      setSelectedTags([...selectedTags, tag]);
    }
  };

  // Calculate mapping stats
  const matchedLogs = result?.mapping_logs.filter(l => l.status === 'MATCHED') || [];
  const unmatchedLogs = result?.mapping_logs.filter(l => l.status === 'UNMATCHED') || [];

  return (
    <div className="space-y-6">
      <PageHeader
        icon={FileText}
        iconClassName="text-orange-500"
        title="Data Sheet Generator"
        description="Generate individual datasheet Excel files per instrument tag with intelligent column matching."
      />

      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}
      {info && <Alert variant="info" onClose={() => setInfo(null)}>{info}</Alert>}

      {/* File Uploads */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* IODB File */}
        <Card title="IODB Source File" icon={Upload}>
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={handleIodbFileChange}
            className="block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 mb-3 file:mr-4 file:py-2 file:px-4 file:border-0 file:bg-primary-50 file:text-primary-700 file:font-medium"
          />
          {iodbFile && (
            <p className="text-sm text-green-600 mb-3">
              ✓ Selected: <strong>{iodbFile.name}</strong>
            </p>
          )}

          <div className="space-y-3">
            <div className="flex items-center">
              <input
                type="checkbox"
                id="twoRowHeader"
                checked={twoRowHeader}
                onChange={(e) => setTwoRowHeader(e.target.checked)}
                className="w-4 h-4 text-primary-600 border-gray-300 rounded"
              />
              <label htmlFor="twoRowHeader" className="ml-2 text-sm text-gray-700">
                Two-row combined header
              </label>
            </div>

            <Button
              onClick={handleLoadTags}
              disabled={!iodbFile}
              loading={loadingTags}
              fullWidth
              className="bg-blue-600 hover:bg-blue-700"
            >
              <Search className="w-4 h-4" />
              {loadingTags ? 'Loading Tags...' : 'Load AI Tags'}
            </Button>
          </div>
        </Card>

        {/* Template File */}
        <Card title="Datasheet Template" icon={FileText}>
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={handleTemplateFileChange}
            className="block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 file:mr-4 file:py-2 file:px-4 file:border-0 file:bg-primary-50 file:text-primary-700 file:font-medium"
          />
          {templateFile && (
            <p className="text-sm text-green-600 mt-3">
              ✓ Selected: <strong>{templateFile.name}</strong>
            </p>
          )}
          <p className="text-xs text-gray-500 mt-3">
            Template must contain a sheet named "Datasheet" with headings in column D.
          </p>
        </Card>
      </div>

      {/* Advanced Settings */}
      <Card title="Advanced Settings">
        <div className="flex items-center gap-6">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Fuzzy Match Threshold: <strong>{fuzzyThreshold}%</strong>
            </label>
            <input
              type="range"
              min="30"
              max="100"
              step="5"
              value={fuzzyThreshold}
              onChange={(e) => setFuzzyThreshold(parseInt(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
            />
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>Loose (30%)</span>
              <span>Strict (100%)</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Tag Selection */}
      {availableTags.length > 0 && (
        <Card title={`Tag Selection (${availableTags.length} AI tags found)`}
          actions={
            <>
              <Button variant="secondary" size="sm" onClick={handleSelectAll}>Select All</Button>
              <Button variant="ghost" size="sm" onClick={handleDeselectAll}>Deselect All</Button>
            </>
          }
        >
          <div className="max-h-64 overflow-y-auto border border-gray-200 rounded-lg p-4">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
              {availableTags.map((tag) => (
                <label key={tag} className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 p-2 rounded">
                  <input
                    type="checkbox"
                    checked={selectedTags.includes(tag)}
                    onChange={() => handleTagToggle(tag)}
                    className="w-4 h-4 text-primary-600 border-gray-300 rounded"
                  />
                  <span className="text-sm text-gray-700">{tag}</span>
                </label>
              ))}
            </div>
          </div>

          <p className="text-sm text-gray-600 mt-3">
            <strong>{selectedTags.length}</strong> tag(s) selected → will generate{' '}
            <strong>{selectedTags.length}</strong> datasheet(s) packaged as a ZIP file
          </p>
        </Card>
      )}

      {/* Generate Button */}
      <Button
        onClick={handleGenerate}
        disabled={!iodbFile || !templateFile || selectedTags.length === 0}
        loading={loading}
        size="lg"
        fullWidth
        className="text-lg py-4"
      >
        <FileText className="w-6 h-6" />
        {loading ? `Generating ${selectedTags.length} Datasheets...` : 'Generate Datasheets'}
      </Button>

      {/* Results */}
      {result && (
        <>
          <div className="bg-green-50 border border-green-200 rounded-lg p-6">
            <div className="flex items-start gap-4">
              <CheckCircle2 className="w-12 h-12 text-green-500 flex-shrink-0" />
              <div className="flex-1">
                <h3 className="text-xl font-bold text-green-800 mb-2">
                  Datasheets Generated Successfully!
                </h3>
                <p className="text-green-700 mb-4">{result.message}</p>
                <Button onClick={handleDownload} className="bg-green-600 hover:bg-green-700">
                  <Download className="w-5 h-5" />
                  Download {result.filename}
                </Button>
              </div>
            </div>
          </div>

          {/* Mapping Log */}
          <Card title="Column Mapping Log"
            actions={
              <button
                onClick={() => setShowMappingLog(!showMappingLog)}
                className="text-sm text-blue-600 hover:text-blue-800"
              >
                {showMappingLog ? 'Hide' : 'Show'} Details
              </button>
            }
          >

            <div className="flex gap-4 mb-4">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
                <span className="text-sm font-medium text-green-700">
                  {matchedLogs.length} Matched
                </span>
              </div>
              <div className="flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-orange-500" />
                <span className="text-sm font-medium text-orange-700">
                  {unmatchedLogs.length} Unmatched
                </span>
              </div>
            </div>

            {showMappingLog && (
              <div className="border border-gray-200 rounded-lg overflow-hidden">
                <div className="max-h-96 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 sticky top-0">
                      <tr>
                        <th className="px-3 py-2 text-left font-medium text-gray-700">Tag</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-700">Heading</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-700">IODB Column</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-700">Score</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-700">Value</th>
                        <th className="px-3 py-2 text-left font-medium text-gray-700">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {result.mapping_logs.map((log, idx) => (
                        <tr key={idx} className={log.status === 'MATCHED' ? 'bg-green-50' : 'bg-orange-50'}>
                          <td className="px-3 py-2 text-gray-900">{log.tag}</td>
                          <td className="px-3 py-2 text-gray-900">{log.heading}</td>
                          <td className="px-3 py-2 text-gray-700">{log.iodb_col || '-'}</td>
                          <td className="px-3 py-2 text-gray-700">{log.score?.toFixed(0) || '-'}</td>
                          <td className="px-3 py-2 text-gray-700 truncate max-w-xs">{log.value || '-'}</td>
                          <td className="px-3 py-2">
                            <span className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${
                              log.status === 'MATCHED'
                                ? 'bg-green-100 text-green-800'
                                : 'bg-orange-100 text-orange-800'
                            }`}>
                              {log.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
