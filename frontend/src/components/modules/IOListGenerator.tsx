/**
 * I/O List Generator
 * Upload an IODB file, pick columns (with I/O-relevant columns pre-suggested) + per-column filters, preview, and generate.
 */
import { useState, useMemo, useEffect } from 'react';
import { Network, Upload, FileText, CheckCircle2, ChevronLeft, ChevronRight } from 'lucide-react';
import { DeliverableCoverCard, DeliverableDownloads, useProject, type AppliedCover } from '../ui/DeliverableCover';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import ProjectSelector from '../ui/ProjectSelector';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import MultiSelect from '../ui/MultiSelect';
import FileUploadCard from '../ui/FileUploadCard';
import SharedIodbCard from '../ui/SharedIodb';
import ListDefaultsNotice, { filterValueOf, type ListDefaults } from '../ui/ListDefaultsNotice';
import OutputWorkbookOptions, { type OutputMode } from '../ui/OutputWorkbookOptions';
import IoBasisReview from './iolist/IoBasisReview';

interface AnalyzeResponse {
  columns: string[];
  unique_values: Record<string, string[]>;
  preview: Record<string, any>[];
  total_rows: number;
  defaults?: ListDefaults | null;
}

interface GenerateResponse {
  filename: string;
  message: string;
  cover?: AppliedCover | null;
  output_mode?: OutputMode;
  sheets?: string[];   // sheets of the generated workbook, read from the output file
  basis?: {            // standard I/O List document: printed pages per section, warnings, IODB observations
    pages?: Record<string, number>; warnings?: string[]; issues?: { severity: string; category: string; message: string }[]; pages_verified?: boolean;
    total_pages?: number | null; location?: { value: string; source: string };
    sections?: { sheet: string; pages: number; size: string; expected: string }[];
  } | null;
}

export default function IOListGenerator() {
  const [iodbFile, setIodbFile] = useState<File | null>(null);
  const [templateFile, setTemplateFileState] = useState<File | null>(null);
  const [coverTemplate, setCoverTemplate] = useState<File | null>(null);
  // Explicit output state - drives the preview, the generated workbook and the download.
  const [ioListOutputMode, setIoListOutputMode] = useState<OutputMode>('WITHOUT_SUMMARY');
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [filters, setFilters] = useState<Record<string, string[]>>({});
  const [filterColumn, setFilterColumn] = useState<string>('');
  const [basisOverrides, setBasisOverrides] = useState<Record<string, string>>({});   // IO_BASIS review: chosen representative loops
  const [basisNames, setBasisNames] = useState<Record<string, string>>({});           // IO_BASIS review: edited equipment wording

  const [location, setLocation] = useState('');                                      // document LOCATION of the headers
  const project = useProject();
  useEffect(() => { setLocation(''); setResult(null); }, [project]);                  // never carried over to another project

  const [page, setPage] = useState(0);
  const PAGE_SIZE = 25;

  const [analyzing, setAnalyzing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A result belongs to one template + one mode: changing either clears it so the download always matches the preview.
  const setTemplateFile = (f: File | null) => { setTemplateFileState(f); setResult(null); };
  const changeOutputMode = (m: OutputMode) => { setIoListOutputMode(m); setResult(null); };

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
      // Default columns / filters are only an initial state - the user can change them freely.
      const d = response.data.defaults;
      setSelectedColumns(d && d.columns.length > 0 ? d.columns : response.data.columns);
      setFilters(d ? { ...d.filters } : {});
      setFilterColumn('');
      setPage(0);
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
    if (coverTemplate) formData.append('cover_template_file', coverTemplate);
    formData.append('selected_columns', JSON.stringify(selectedColumns));
    formData.append('filters', JSON.stringify(filters));
    formData.append('output_mode', ioListOutputMode);
    formData.append('basis_overrides', JSON.stringify(basisOverrides));
    formData.append('basis_names', JSON.stringify(basisNames));
    if (!templateFile) formData.append('location', location.trim());

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
      activeFilters.every(([col, values]) => values.includes(filterValueOf(row[col])))
    );
  }, [analysis, filters]);

  const resetToDefaults = () => {
    if (!analysis) return;
    const d = analysis.defaults;
    setSelectedColumns(d && d.columns.length > 0 ? d.columns : analysis.columns);
    setFilters(d ? { ...d.filters } : {});
    setPage(0);
  };
  const clearAllFilters = () => { setFilters({}); setPage(0); };

  const totalPages = Math.ceil(filteredPreview.length / PAGE_SIZE);
  const pagedRows = filteredPreview.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

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
        description="Generate an I/O list from your IODB with default columns preselected, plus per-column filters."
      />
      <ProjectSelector />

      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}

      {/* File Uploads */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <SharedIodbCard
          title="IODB Source File"
          icon={Upload}
          file={iodbFile}
          onChange={(f) => {
            setIodbFile(f);
            setAnalysis(null);
            setResult(null);
            setBasisOverrides({});
            setBasisNames({});
          }}
        >
          <Button onClick={handleAnalyze} disabled={!iodbFile} loading={analyzing} fullWidth className="mt-3 bg-blue-600 hover:bg-blue-700">
            {analyzing ? 'Analyzing...' : 'Analyze IODB'}
          </Button>
        </SharedIodbCard>

        <FileUploadCard
          title="I/O List Template (optional)"
          icon={FileText}
          file={templateFile}
          onChange={setTemplateFile}
          hint="Leave empty to use the iEZ standard I/O List: the linked cover sheet, table of contents, abbreviations, IO_BASIS (generated from the IODB), I/O List and I/O Summary. A template uploaded here is used as before (without IO_BASIS)."
        />
      </div>

      <OutputWorkbookOptions
        endpoint="/io-list/composition"
        templateFile={templateFile}
        mode={ioListOutputMode}
        onModeChange={changeOutputMode}
        summaryLabel="I/O Summary"
        listLabel="I/O List"
      />

      {/* Column Selection & Filters */}
      {analysis && (
        <>
          <ListDefaultsNotice
            defaults={analysis.defaults}
            selectedColumns={selectedColumns}
            filters={filters}
            onReset={resetToDefaults}
            onClearFilters={clearAllFilters}
          />

          <Card title={`Select Columns (${selectedColumns.length} of ${analysis.columns.length})`}
            description="Default columns selected. You may add or remove columns.">
            <MultiSelect
              options={analysis.columns}
              selected={selectedColumns}
              onChange={setSelectedColumns}
              columns={4}
            />
          </Card>

          <Card title="Column Filters" description="Default filters applied. You may modify the selections before generating. Only the selected values of a filtered column are kept; empty cells are shown as (blank).">
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
          <Card>
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="font-semibold text-gray-800">Preview</h3>
                <p className="text-sm text-gray-500 mt-0.5">
                  Showing {filteredPreview.length} of{' '}
                  <span className="font-semibold text-purple-600">{analysis.total_rows} total rows</span>
                  {Object.keys(filters).length > 0 && ' (filtered)'}
                  {analysis.total_rows > analysis.preview.length && (
                    <span className="text-orange-600 ml-2">
                      · First {analysis.preview.length} rows loaded — generate to get all rows
                    </span>
                  )}
                </p>
              </div>
              {totalPages > 1 && (
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <button
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="p-1 rounded hover:bg-gray-100 disabled:opacity-40"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <span>Page {page + 1} of {totalPages}</span>
                  <button
                    onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                    disabled={page === totalPages - 1}
                    className="p-1 rounded hover:bg-gray-100 disabled:opacity-40"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
            <div className="border border-gray-200 rounded-lg overflow-auto max-h-96">
              <table className="w-full text-sm whitespace-nowrap">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium text-gray-400 w-10">#</th>
                    {previewColumns.map((col) => (
                      <th key={col} className="px-3 py-2 text-left font-medium text-gray-700">
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {pagedRows.map((row, idx) => (
                    <tr key={idx} className="hover:bg-gray-50">
                      <td className="px-3 py-2 text-gray-400 text-xs">{page * PAGE_SIZE + idx + 1}</td>
                      {previewColumns.map((col) => (
                        <td key={col} className="px-3 py-2 text-gray-700">
                          {row[col] ?? ''}
                        </td>
                      ))}
                    </tr>
                  ))}
                  {pagedRows.length === 0 && (
                    <tr>
                      <td colSpan={previewColumns.length + 1} className="px-3 py-8 text-center text-gray-400">
                        No rows match the current filters
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {totalPages > 1 && (
              <p className="text-xs text-gray-400 mt-2 text-right">
                Rows {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filteredPreview.length)} of {filteredPreview.length}
              </p>
            )}
          </Card>

          {!templateFile && (
            <IoBasisReview
              iodbFile={iodbFile}
              filters={filters}
              overrides={basisOverrides}
              names={basisNames}
              onChange={(o, n) => { setBasisOverrides(o); setBasisNames(n); setResult(null); }}
            />
          )}

          <DeliverableCoverCard docType="io_list" customTemplate={coverTemplate} onCustomTemplate={(f) => { setCoverTemplate(f); setResult(null); }} />

          {!templateFile && (
            <Card title="Document Location" description="Printed in the LOCATION field of the Table of Contents, Abbreviation and IO Basis headers. If the linked cover sheet states a Location, that one is used. It does not change the LOCATION column of the I/O List.">
              <input
                type="text" value={location} maxLength={200} aria-label="Document location" data-testid="io-location"
                placeholder="Enter the project / document location"
                onChange={(e) => { setLocation(e.target.value); setResult(null); }}
                className="w-full border rounded-lg px-3 py-2 text-sm"
                style={{ background: 'var(--s1)', color: 'var(--t0)', borderColor: 'var(--b2)' }}
              />
            </Card>
          )}

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
              <p className="text-green-700 mb-2">{result.message}</p>
              {result.sheets && (
                <p className="text-sm text-green-800 mb-4">
                  Workbook sheets: {result.sheets.join(' · ')}
                </p>
              )}
              {result.basis?.sections && result.basis.sections.length > 0 && (
                <p className="text-sm text-green-800 mb-2" data-testid="io-pages">
                  Printed pages: {result.basis.sections.map((x) => `${x.sheet} ${x.pages} (${x.size})`).join(' · ')}
                  {' '}— total {result.basis.total_pages}{result.basis.pages_verified ? ', verified on the rendered document' : ', NOT verified'}
                </p>
              )}
              {result.basis?.location?.value && (
                <p className="text-sm text-green-800 mb-2">Location in the headers: {result.basis.location.value} ({result.basis.location.source})</p>
              )}
              {(result.basis?.warnings || []).map((w, i) => <p key={i} className="text-sm text-amber-800 mb-1">• {w}</p>)}
              <p className="text-sm text-green-800 mb-2 font-mono">{result.filename}</p>
              <DeliverableDownloads module="io_list" filename={result.filename} cover={result.cover} onExcel={handleDownload} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
