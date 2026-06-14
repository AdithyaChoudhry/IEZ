/**
 * I/O List Generator
 * Upload an IODB file, pick columns (with I/O-relevant columns pre-suggested) + per-column filters, preview, and generate.
 */
import { useState, useMemo } from 'react';
import { Network, Upload, FileText, Download, CheckCircle2 } from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import MultiSelect from '../ui/MultiSelect';
import FileUploadCard from '../ui/FileUploadCard';

interface AnalyzeResponse {
  columns: string[];
  unique_values: Record<string, string[]>;
  preview: Record<string, any>[];
}

interface GenerateResponse {
  filename: string;
  message: string;
}

const IO_KEYWORDS = ['signal', 'i/o', 'io', 'type', 'tag', 'loop', 'rack', 'slot', 'channel', 'panel'];

export default function IOListGenerator() {
  const [iodbFile, setIodbFile] = useState<File | null>(null);
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [filters, setFilters] = useState<Record<string, string[]>>({});
  const [filterColumn, setFilterColumn] = useState<string>('');

  const [analyzing, setAnalyzing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async () => {
    if (!iodbFile) return;
    setAnalyzing(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append('file', iodbFile);

    try {
      const response = await api.post<AnalyzeResponse>('/io-list/analyze', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setAnalysis(response.data);

      // Pre-suggest I/O-relevant columns
      const suggested = response.data.columns.filter((c) =>
        IO_KEYWORDS.some((k) => c.toLowerCase().includes(k))
      );
      setSelectedColumns(suggested.length > 0 ? suggested : response.data.columns);
      setFilters({});
      setFilterColumn('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to analyze IODB file');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleGenerate = async () => {
    if (!iodbFile || selectedColumns.length === 0) return;
    setGenerating(true);
    setError(null);

    const formData = new FormData();
    formData.append('iodb_file', iodbFile);
    if (templateFile) formData.append('template_file', templateFile);
    formData.append('selected_columns', JSON.stringify(selectedColumns));
    formData.append('filters', JSON.stringify(filters));

    try {
      const response = await api.post<GenerateResponse>('/io-list/generate', formData, {
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
      const response = await api.get('/io-list/download', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', result?.filename || 'IO_List.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Download failed');
    }
  };

  const setColumnFilter = (column: string, values: string[]) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (values.length === 0) {
        delete next[column];
      } else {
        next[column] = values;
      }
      return next;
    });
  };

  const filteredPreview = useMemo(() => {
    if (!analysis) return [];
    const activeFilters = Object.entries(filters);
    if (activeFilters.length === 0) return analysis.preview;
    return analysis.preview.filter((row) =>
      activeFilters.every(([col, values]) => values.includes(String(row[col] ?? '')))
    );
  }, [analysis, filters]);

  const previewColumns = useMemo(() => {
    if (!analysis) return [];
    return analysis.columns.filter((c) => selectedColumns.includes(c));
  }, [analysis, selectedColumns]);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Network}
        iconClassName="text-purple-500"
        title="I/O List Generator"
        description="Generate an I/O list from your IODB with I/O-relevant columns pre-suggested, plus per-column filters."
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
            setAnalysis(null);
            setResult(null);
          }}
        >
          <Button onClick={handleAnalyze} disabled={!iodbFile} loading={analyzing} fullWidth className="mt-3 bg-blue-600 hover:bg-blue-700">
            {analyzing ? 'Analyzing...' : 'Analyze IODB'}
          </Button>
        </FileUploadCard>

        <FileUploadCard
          title="I/O List Template (optional)"
          icon={FileText}
          file={templateFile}
          onChange={setTemplateFile}
          hint="If omitted, a default formatted I/O list will be generated."
        />
      </div>

      {/* Column Selection & Filters */}
      {analysis && (
        <>
          <Card title={`Select Columns (${selectedColumns.length} of ${analysis.columns.length})`}
            description="I/O-relevant columns are pre-selected based on common keywords (signal, I/O, type, loop, rack, slot, channel, panel...)."
          >
            <MultiSelect
              options={analysis.columns}
              selected={selectedColumns}
              onChange={setSelectedColumns}
              columns={4}
            />
          </Card>

          <Card title="Column Filters" description="Optionally restrict the preview/output to specific values in a column.">
            <div className="flex flex-wrap gap-2 mb-4">
              {analysis.columns.map((col) => (
                <button
                  key={col}
                  onClick={() => setFilterColumn(col)}
                  className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                    filterColumn === col
                      ? 'bg-primary-600 text-white border-primary-600'
                      : filters[col]
                      ? 'bg-primary-50 text-primary-700 border-primary-300'
                      : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  {col} {filters[col] ? `(${filters[col].length})` : ''}
                </button>
              ))}
            </div>

            {filterColumn && (
              <MultiSelect
                options={analysis.unique_values[filterColumn] || []}
                selected={filters[filterColumn] || []}
                onChange={(values) => setColumnFilter(filterColumn, values)}
                columns={3}
              />
            )}
          </Card>

          {/* Preview */}
          <Card title={`Preview (${filteredPreview.length} of ${analysis.preview.length} rows shown)`}>
            <div className="border border-gray-200 rounded-lg overflow-auto max-h-96">
              <table className="w-full text-sm whitespace-nowrap">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    {previewColumns.map((col) => (
                      <th key={col} className="px-3 py-2 text-left font-medium text-gray-700">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {filteredPreview.map((row, idx) => (
                    <tr key={idx} className="hover:bg-gray-50">
                      {previewColumns.map((col) => (
                        <td key={col} className="px-3 py-2 text-gray-700">
                          {row[col] ?? ''}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Generate */}
          <Button
            onClick={handleGenerate}
            disabled={selectedColumns.length === 0}
            loading={generating}
            size="lg"
            fullWidth
            className="text-lg py-4"
          >
            <Network className="w-6 h-6" />
            {generating ? 'Generating...' : 'Generate I/O List'}
          </Button>
        </>
      )}

      {/* Result */}
      {result && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <CheckCircle2 className="w-12 h-12 text-green-500 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="text-xl font-bold text-green-800 mb-2">I/O List Generated!</h3>
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
