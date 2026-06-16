/**
 * Data Sheet Generator (SOP-driven, interactive)
 * Upload a SOP datasheet workbook + IODB, pick an instrument type, confirm the
 * predefined specs in an editable form, and generate one datasheet per tag.
 */
import { useMemo, useState } from 'react';
import { FileText, Upload, Download, CheckCircle2, Search, FileSpreadsheet } from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import FileUploadCard from '../ui/FileUploadCard';

interface FieldSpec {
  section: string;
  label: string;
  row: number;
  value_cols: number[];
  sub_labels: string[];
  source: 'iodb' | 'predefined';
  defaults: string[];
  source_note: string;
  color: string;
}

interface DatasheetInfo {
  sheet: string;
  eg_sheet: string | null;
  title: string;
}

interface AnalyzeResponse {
  datasheets: DatasheetInfo[];
  instrument_types: string[];
  message: string;
}

interface FieldsResponse {
  datasheet: string;
  title: string;
  fields: FieldSpec[];
}

interface TagsResponse {
  instrument_type: string;
  tags: string[];
  count: number;
}

interface GenerateJob {
  job_id: string;
  status: string;
}

interface GenerateStatus {
  job_id: string;
  status: 'processing' | 'done' | 'error';
  result?: { filename: string; tag_count: number; message: string };
  error?: string;
}

const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 200;

export default function DataSheetGenerator() {
  const [sopFile, setSopFile] = useState<File | null>(null);
  const [iodbFile, setIodbFile] = useState<File | null>(null);

  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [selectedDatasheet, setSelectedDatasheet] = useState<string>('');
  const [selectedType, setSelectedType] = useState<string>('');

  const [fields, setFields] = useState<FieldSpec[]>([]);
  const [fieldValues, setFieldValues] = useState<Record<string, string[]>>({});
  const [tags, setTags] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  const [analyzing, setAnalyzing] = useState(false);
  const [loadingFields, setLoadingFields] = useState(false);
  const [loadingTags, setLoadingTags] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<GenerateStatus['result'] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleAnalyze = async () => {
    if (!sopFile || !iodbFile) return;
    setAnalyzing(true);
    setError(null);
    setAnalysis(null);
    setFields([]);
    setTags([]);
    setResult(null);

    const fd = new FormData();
    fd.append('sop_file', sopFile);
    fd.append('iodb_file', iodbFile);
    try {
      const res = await api.post<AnalyzeResponse>('/sop-datasheet/analyze', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setAnalysis(res.data);
      // Auto-select the single datasheet if there's only one.
      if (res.data.datasheets.length === 1) {
        await loadFields(res.data.datasheets[0].sheet);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Analysis failed');
    } finally {
      setAnalyzing(false);
    }
  };

  const loadFields = async (sheet: string) => {
    if (!sopFile) return;
    setSelectedDatasheet(sheet);
    setLoadingFields(true);
    setError(null);

    const fd = new FormData();
    fd.append('sop_file', sopFile);
    fd.append('datasheet_sheet', sheet);
    try {
      const res = await api.post<FieldsResponse>('/sop-datasheet/fields', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setFields(res.data.fields);
      // Initialize editable values for predefined fields with their defaults.
      const init: Record<string, string[]> = {};
      for (const f of res.data.fields) {
        if (f.source === 'predefined') init[f.label] = [...f.defaults];
      }
      setFieldValues(init);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load fields');
    } finally {
      setLoadingFields(false);
    }
  };

  const loadTags = async (type: string) => {
    if (!iodbFile) return;
    setSelectedType(type);
    setLoadingTags(true);
    setError(null);
    setSelectedTags([]);

    const fd = new FormData();
    fd.append('iodb_file', iodbFile);
    fd.append('instrument_type', type);
    try {
      const res = await api.post<TagsResponse>('/sop-datasheet/tags', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setTags(res.data.tags);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load tags');
    } finally {
      setLoadingTags(false);
    }
  };

  const setFieldValue = (label: string, idx: number, value: string) => {
    setFieldValues((prev) => {
      const arr = [...(prev[label] || [])];
      arr[idx] = value;
      return { ...prev, [label]: arr };
    });
  };

  const handleGenerate = async () => {
    if (!sopFile || !iodbFile || !selectedDatasheet || !selectedType || selectedTags.length === 0) return;
    setGenerating(true);
    setError(null);
    setResult(null);

    const fd = new FormData();
    fd.append('sop_file', sopFile);
    fd.append('iodb_file', iodbFile);
    fd.append('datasheet_sheet', selectedDatasheet);
    fd.append('instrument_type', selectedType);
    fd.append('selected_tags', JSON.stringify(selectedTags));
    fd.append('overrides', JSON.stringify(fieldValues));

    try {
      const kickoff = await api.post<GenerateJob>('/sop-datasheet/generate', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const jobId = kickoff.data.job_id;
      for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        const st = await api.get<GenerateStatus>(`/sop-datasheet/generate/status/${jobId}`);
        if (st.data.status === 'done') {
          setResult(st.data.result!);
          return;
        }
        if (st.data.status === 'error') {
          setError(st.data.error || 'Generation failed');
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
      const res = await api.get('/sop-datasheet/download', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', result?.filename || 'Datasheets.zip');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Download failed');
    }
  };

  // Group fields by section for display.
  const grouped = useMemo(() => {
    const out: { section: string; fields: FieldSpec[] }[] = [];
    for (const f of fields) {
      const last = out[out.length - 1];
      if (last && last.section === f.section) last.fields.push(f);
      else out.push({ section: f.section, fields: [f] });
    }
    return out;
  }, [fields]);

  const predefinedCount = fields.filter((f) => f.source === 'predefined').length;
  const iodbCount = fields.length - predefinedCount;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={FileText}
        iconClassName="text-orange-500"
        title="Data Sheet Generator"
        description="Upload a SOP datasheet workbook + IODB, confirm the predefined specs, and generate one datasheet per tag."
      />

      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}

      {/* Step 1: Uploads */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FileUploadCard
          title="SOP Datasheet Workbook"
          icon={FileSpreadsheet}
          file={sopFile}
          accept=".xls,.xlsx,.xlsm"
          onChange={(f) => { setSopFile(f); setAnalysis(null); setFields([]); }}
          hint="The SOP workbook containing the instrument datasheet template + example (-EG) sheets."
        />
        <FileUploadCard
          title="IODB Source File"
          icon={Upload}
          file={iodbFile}
          accept=".xls,.xlsx,.xlsm"
          onChange={(f) => { setIodbFile(f); setAnalysis(null); setTags([]); }}
        >
          <Button onClick={handleAnalyze} disabled={!sopFile || !iodbFile} loading={analyzing} fullWidth className="mt-3 bg-blue-600 hover:bg-blue-700">
            <Search className="w-4 h-4" />
            {analyzing ? 'Analyzing...' : 'Analyze SOP + IODB'}
          </Button>
        </FileUploadCard>
      </div>

      {/* Step 2: Select datasheet + instrument type */}
      {analysis && (
        <Card title="Select Datasheet & Instrument Type">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Datasheet to prepare</label>
              <select
                value={selectedDatasheet}
                onChange={(e) => loadFields(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white"
              >
                <option value="">— Select datasheet —</option>
                {analysis.datasheets.map((d) => (
                  <option key={d.sheet} value={d.sheet}>{d.title} ({d.sheet})</option>
                ))}
              </select>
              {loadingFields && <p className="text-xs text-gray-500 mt-1">Loading fields…</p>}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Instrument type (from IODB)</label>
              <select
                value={selectedType}
                onChange={(e) => loadTags(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white"
              >
                <option value="">— Select instrument type —</option>
                {analysis.instrument_types.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              {loadingTags && <p className="text-xs text-gray-500 mt-1">Loading tags…</p>}
            </div>
          </div>
        </Card>
      )}

      {/* Step 3: Tag selection */}
      {tags.length > 0 && (
        <Card
          title={`Tags (${tags.length} match "${selectedType}")`}
          actions={
            <>
              <Button variant="secondary" size="sm" onClick={() => setSelectedTags(tags)}>Select All</Button>
              <Button variant="ghost" size="sm" onClick={() => setSelectedTags([])}>Clear</Button>
            </>
          }
        >
          <div className="max-h-56 overflow-y-auto border border-gray-200 rounded-lg p-3">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
              {tags.map((tag) => (
                <label key={tag} className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 p-1.5 rounded">
                  <input
                    type="checkbox"
                    checked={selectedTags.includes(tag)}
                    onChange={() =>
                      setSelectedTags((prev) =>
                        prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
                      )
                    }
                    className="w-4 h-4 text-primary-600 border-gray-300 rounded"
                  />
                  <span className="text-sm text-gray-700">{tag}</span>
                </label>
              ))}
            </div>
          </div>
          <p className="text-sm text-gray-600 mt-3">
            <strong>{selectedTags.length}</strong> tag(s) selected → <strong>{selectedTags.length}</strong> datasheet(s) will be generated.
          </p>
        </Card>
      )}

      {/* Step 4: Interactive spec form */}
      {fields.length > 0 && (
        <Card title="Specifications">
          <div className="flex flex-wrap gap-4 mb-4 text-xs">
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-[#C6EFCE] border border-green-300" /> Predefined (editable) · {predefinedCount}</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-[#FFFF00] border border-yellow-400" /> From IODB (auto) · {iodbCount}</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-[#FFC7CE] border border-red-300" /> Mandatory left blank</span>
          </div>

          <div className="space-y-5">
            {grouped.map((g) => (
              <div key={g.section}>
                <h4 className="text-sm font-semibold text-gray-800 bg-gray-100 px-3 py-1.5 rounded mb-2">{g.section}</h4>
                <div className="space-y-2">
                  {g.fields.map((f) => {
                    const isIodb = f.source === 'iodb';
                    const vals = isIodb ? f.defaults : (fieldValues[f.label] || f.defaults);
                    return (
                      <div key={`${f.row}-${f.label}`} className="grid grid-cols-1 md:grid-cols-3 gap-2 items-center">
                        <label className="text-sm text-gray-700 md:col-span-1">
                          {f.label}
                          {f.source_note && <span className="block text-xs text-gray-400">{f.source_note}</span>}
                        </label>
                        <div className="md:col-span-2 flex gap-2">
                          {(f.sub_labels.length ? f.sub_labels : ['']).map((sub, idx) => (
                            <div key={idx} className="flex-1">
                              {sub && <span className="text-xs text-gray-500">{sub}</span>}
                              {isIodb ? (
                                <div className="px-3 py-2 rounded-md text-sm bg-[#FFF9C4] border border-yellow-300 text-gray-600">
                                  {vals[idx] || 'From IODB'}
                                </div>
                              ) : (
                                <input
                                  type="text"
                                  value={vals[idx] ?? ''}
                                  onChange={(e) => setFieldValue(f.label, idx, e.target.value)}
                                  className={`w-full px-3 py-2 rounded-md text-sm border ${
                                    (vals[idx] ?? '').trim()
                                      ? 'bg-[#EAF7EA] border-green-300'
                                      : 'bg-[#FDEEF0] border-red-300'
                                  }`}
                                />
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Generate */}
      {fields.length > 0 && (
        <Button
          onClick={handleGenerate}
          disabled={!selectedDatasheet || !selectedType || selectedTags.length === 0}
          loading={generating}
          size="lg"
          fullWidth
          className="text-lg py-4"
        >
          <FileText className="w-6 h-6" />
          {generating ? `Generating ${selectedTags.length} Datasheets...` : `Generate ${selectedTags.length} Datasheet(s)`}
        </Button>
      )}

      {/* Result */}
      {result && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <CheckCircle2 className="w-12 h-12 text-green-500 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="text-xl font-bold text-green-800 mb-2">Datasheets Generated!</h3>
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
