/**
 * Data Sheet Generator (SOP-driven, interactive) — v2
 * Flow: upload IODB -> pick instrument type -> select tags -> upload SOP ->
 * configuration popup (IODB / dropdowns / mandatory) -> preview -> generate.
 */
import { useMemo, useState } from 'react';
import { FileText, Upload, Download, CheckCircle2, Search, FileSpreadsheet, X } from 'lucide-react';
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
  input_type: 'iodb' | 'dropdown' | 'text';
  options: string[];
  mandatory: boolean;
}

interface DatasheetInfo { sheet: string; eg_sheet: string | null; title: string; }
interface InstrumentTypesResponse { instrument_types: string[]; count: number; }
interface DatasheetsResponse { datasheets: DatasheetInfo[]; }
interface FieldsResponse { datasheet: string; title: string; fields: FieldSpec[]; }
interface TagsResponse { instrument_type: string; tags: string[]; count: number; }
interface GenerateJob { job_id: string; status: string; }
interface GenerateStatus {
  job_id: string;
  status: 'processing' | 'done' | 'error';
  result?: { filename: string; tag_count: number; message: string };
  error?: string;
}

const POLL_INTERVAL_MS = 3000;
const MAX_POLL_ATTEMPTS = 200;
const CUSTOM = 'Custom Value';

export default function DataSheetGenerator() {
  const [iodbFile, setIodbFile] = useState<File | null>(null);
  const [sopFile, setSopFile] = useState<File | null>(null);

  const [instrumentTypes, setInstrumentTypes] = useState<string[]>([]);
  const [selectedType, setSelectedType] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  const [datasheets, setDatasheets] = useState<DatasheetInfo[]>([]);
  const [selectedDatasheet, setSelectedDatasheet] = useState('');
  const [fields, setFields] = useState<FieldSpec[]>([]);

  // overrides[label] = array of values (aligned to value_cols); customMode tracks "Custom Value".
  const [overrides, setOverrides] = useState<Record<string, string[]>>({});
  const [customMode, setCustomMode] = useState<Record<string, boolean[]>>({});

  const [showConfig, setShowConfig] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  const [loadingTypes, setLoadingTypes] = useState(false);
  const [loadingTags, setLoadingTags] = useState(false);
  const [loadingFields, setLoadingFields] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<GenerateStatus['result'] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ── Step 1: IODB -> instrument types ──────────────────────────────────────
  const handleLoadTypes = async () => {
    if (!iodbFile) return;
    setLoadingTypes(true); setError(null);
    setInstrumentTypes([]); setTags([]); setSelectedType(''); setResult(null);
    const fd = new FormData(); fd.append('iodb_file', iodbFile);
    try {
      const res = await api.post<InstrumentTypesResponse>('/sop-datasheet/instrument-types', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setInstrumentTypes(res.data.instrument_types);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to read instrument types');
    } finally { setLoadingTypes(false); }
  };

  // ── Step 2: type -> tags ──────────────────────────────────────────────────
  const handleSelectType = async (type: string) => {
    setSelectedType(type); setSelectedTags([]); setTags([]);
    if (!iodbFile || !type) return;
    setLoadingTags(true); setError(null);
    const fd = new FormData(); fd.append('iodb_file', iodbFile); fd.append('instrument_type', type);
    try {
      const res = await api.post<TagsResponse>('/sop-datasheet/tags', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setTags(res.data.tags);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load tags');
    } finally { setLoadingTags(false); }
  };

  // ── Step 3: SOP -> datasheets -> fields ───────────────────────────────────
  const handleLoadDatasheets = async () => {
    if (!sopFile) return;
    setError(null); setDatasheets([]); setFields([]);
    const fd = new FormData(); fd.append('sop_file', sopFile);
    try {
      const res = await api.post<DatasheetsResponse>('/sop-datasheet/datasheets', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setDatasheets(res.data.datasheets);
      if (res.data.datasheets.length === 1) await loadFields(res.data.datasheets[0].sheet);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to analyze SOP workbook');
    }
  };

  const loadFields = async (sheet: string) => {
    if (!sopFile) return;
    setSelectedDatasheet(sheet); setLoadingFields(true); setError(null);
    const fd = new FormData(); fd.append('sop_file', sopFile); fd.append('datasheet_sheet', sheet);
    try {
      const res = await api.post<FieldsResponse>('/sop-datasheet/fields', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setFields(res.data.fields);
      // Initialize overrides for editable fields (dropdown + text) with defaults.
      const initVals: Record<string, string[]> = {};
      const initCustom: Record<string, boolean[]> = {};
      for (const f of res.data.fields) {
        if (f.input_type === 'iodb') continue;
        initVals[f.label] = [...f.defaults];
        initCustom[f.label] = f.value_cols.map(() => false);
      }
      setOverrides(initVals);
      setCustomMode(initCustom);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load fields');
    } finally { setLoadingFields(false); }
  };

  const setVal = (label: string, idx: number, value: string) => {
    setOverrides((prev) => {
      const arr = [...(prev[label] || [])]; arr[idx] = value; return { ...prev, [label]: arr };
    });
  };

  const onDropdownChange = (label: string, idx: number, value: string) => {
    if (value === CUSTOM) {
      setCustomMode((p) => { const a = [...(p[label] || [])]; a[idx] = true; return { ...p, [label]: a }; });
      setVal(label, idx, '');
    } else {
      setCustomMode((p) => { const a = [...(p[label] || [])]; a[idx] = false; return { ...p, [label]: a }; });
      setVal(label, idx, value);
    }
  };

  // Mandatory validation: text+mandatory fields must have a non-empty value.
  const missingMandatory = useMemo(
    () => fields.filter((f) => f.input_type === 'text' && f.mandatory)
      .filter((f) => !(overrides[f.label] || []).some((v) => (v || '').trim())),
    [fields, overrides]
  );

  const grouped = useMemo(() => {
    const out: { section: string; fields: FieldSpec[] }[] = [];
    for (const f of fields) {
      const last = out[out.length - 1];
      if (last && last.section === f.section) last.fields.push(f);
      else out.push({ section: f.section, fields: [f] });
    }
    return out;
  }, [fields]);

  const iodbFields = fields.filter((f) => f.input_type === 'iodb');
  const dropdownFields = fields.filter((f) => f.input_type === 'dropdown');
  const textFields = fields.filter((f) => f.input_type === 'text');

  const readyToConfigure = !!selectedType && selectedTags.length > 0 && fields.length > 0;

  // ── Generate ──────────────────────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!sopFile || !iodbFile || !selectedDatasheet || !selectedType || selectedTags.length === 0) return;
    setShowPreview(false);
    setGenerating(true); setError(null); setResult(null);
    const fd = new FormData();
    fd.append('sop_file', sopFile);
    fd.append('iodb_file', iodbFile);
    fd.append('datasheet_sheet', selectedDatasheet);
    fd.append('instrument_type', selectedType);
    fd.append('selected_tags', JSON.stringify(selectedTags));
    fd.append('overrides', JSON.stringify(overrides));
    try {
      const kickoff = await api.post<GenerateJob>('/sop-datasheet/generate', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const jobId = kickoff.data.job_id;
      for (let i = 0; i < MAX_POLL_ATTEMPTS; i++) {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        const st = await api.get<GenerateStatus>(`/sop-datasheet/generate/status/${jobId}`);
        if (st.data.status === 'done') { setResult(st.data.result!); return; }
        if (st.data.status === 'error') { setError(st.data.error || 'Generation failed'); return; }
      }
      setError('Generation is taking longer than expected. Please try again later.');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Generation failed');
    } finally { setGenerating(false); }
  };

  const handleDownload = async () => {
    try {
      const res = await api.get('/sop-datasheet/download', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url; link.setAttribute('download', result?.filename || 'Datasheets.zip');
      document.body.appendChild(link); link.click(); link.remove();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Download failed');
    }
  };

  const valueOf = (label: string, idx: number, fallback: string) => {
    const v = overrides[label]?.[idx];
    return (v && v.trim()) ? v : fallback;
  };

  return (
    <div className="space-y-6">
      <PageHeader
        icon={FileText}
        iconClassName="text-orange-500"
        title="Data Sheet Generator"
        description="Upload IODB, select an instrument type & tags, upload the SOP template, configure specs, preview, and generate one datasheet per tag."
      />

      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}

      {/* Step 1: IODB */}
      <FileUploadCard
        title="Step 1 — Upload IODB"
        icon={Upload}
        file={iodbFile}
        accept=".xls,.xlsx,.xlsm"
        onChange={(f) => { setIodbFile(f); setInstrumentTypes([]); setTags([]); setSelectedType(''); }}
      >
        <Button onClick={handleLoadTypes} disabled={!iodbFile} loading={loadingTypes} fullWidth className="mt-3 bg-blue-600 hover:bg-blue-700">
          <Search className="w-4 h-4" />
          {loadingTypes ? 'Reading...' : 'Show Instrument Types'}
        </Button>
      </FileUploadCard>

      {/* Step 2: Instrument type + tags */}
      {instrumentTypes.length > 0 && (
        <Card title="Step 2 — Select Instrument Type">
          <select
            value={selectedType}
            onChange={(e) => handleSelectType(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white"
          >
            <option value="">— Select instrument type —</option>
            {instrumentTypes.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          {loadingTags && <p className="text-xs text-gray-500 mt-2">Loading tags…</p>}

          {tags.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-700">{tags.length} matching tag(s)</span>
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" onClick={() => setSelectedTags(tags)}>Select All</Button>
                  <Button variant="ghost" size="sm" onClick={() => setSelectedTags([])}>Clear</Button>
                </div>
              </div>
              <div className="max-h-56 overflow-y-auto border border-gray-200 rounded-lg p-3">
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                  {tags.map((tag) => (
                    <label key={tag} className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 p-1.5 rounded">
                      <input type="checkbox" checked={selectedTags.includes(tag)}
                        onChange={() => setSelectedTags((p) => p.includes(tag) ? p.filter((t) => t !== tag) : [...p, tag])}
                        className="w-4 h-4 text-primary-600 border-gray-300 rounded" />
                      <span className="text-sm text-gray-700">{tag}</span>
                    </label>
                  ))}
                </div>
              </div>
              <p className="text-sm text-gray-600 mt-2"><strong>{selectedTags.length}</strong> tag(s) selected.</p>
            </div>
          )}
        </Card>
      )}

      {/* Step 3: SOP template */}
      {selectedTags.length > 0 && (
        <FileUploadCard
          title="Step 3 — Upload SOP Datasheet Template"
          icon={FileSpreadsheet}
          file={sopFile}
          accept=".xls,.xlsx,.xlsm"
          onChange={(f) => { setSopFile(f); setDatasheets([]); setFields([]); }}
          hint="Upload .xlsx for full logo/formula/page-setup preservation (.xls is best-effort)."
        >
          <Button onClick={handleLoadDatasheets} disabled={!sopFile} fullWidth className="mt-3 bg-blue-600 hover:bg-blue-700">
            <Search className="w-4 h-4" /> Analyze Template
          </Button>
        </FileUploadCard>
      )}

      {datasheets.length > 1 && (
        <Card title="Select Datasheet">
          <select value={selectedDatasheet} onChange={(e) => loadFields(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md bg-white">
            <option value="">— Select datasheet —</option>
            {datasheets.map((d) => <option key={d.sheet} value={d.sheet}>{d.title} ({d.sheet})</option>)}
          </select>
          {loadingFields && <p className="text-xs text-gray-500 mt-2">Loading fields…</p>}
        </Card>
      )}

      {/* Step 4: Configure */}
      {readyToConfigure && (
        <Button onClick={() => setShowConfig(true)} size="lg" fullWidth className="text-lg py-4">
          <FileText className="w-6 h-6" /> Configure Specifications ({fields.length} fields)
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
                <Download className="w-5 h-5" /> Download {result.filename}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Configuration Popup ─────────────────────────────────────────────── */}
      {showConfig && (
        <Modal title="Datasheet Configuration" onClose={() => setShowConfig(false)}>
          <Legend />
          {/* Section 1 — IODB */}
          {iodbFields.length > 0 && (
            <ConfigSection title="IODB Mapped Fields" tint="bg-[#FFF9C4]" note="Auto-filled per tag from the IODB.">
              {iodbFields.map((f) => (
                <Row key={`${f.row}`} label={f.label} note={f.source_note}>
                  <div className="px-3 py-2 rounded-md text-sm bg-[#FFF9C4] border border-yellow-300 text-gray-600">
                    {f.defaults.join(' / ') || 'From IODB'}
                  </div>
                </Row>
              ))}
            </ConfigSection>
          )}
          {/* Section 2 — dropdowns */}
          {dropdownFields.length > 0 && (
            <ConfigSection title="Predefined Dropdown Fields" tint="bg-[#EAF7EA]" note="Pick a value or choose 'Custom Value'.">
              {dropdownFields.map((f) => (
                <Row key={`${f.row}`} label={f.label} note={f.source_note}>
                  {f.value_cols.map((_c, idx) => {
                    const isCustom = customMode[f.label]?.[idx];
                    return (
                      <div key={idx} className="flex-1 space-y-1">
                        {f.sub_labels[idx] && <span className="text-xs text-gray-500">{f.sub_labels[idx]}</span>}
                        <select
                          value={isCustom ? CUSTOM : (overrides[f.label]?.[idx] ?? '')}
                          onChange={(e) => onDropdownChange(f.label, idx, e.target.value)}
                          className="w-full px-3 py-2 rounded-md text-sm border border-green-300 bg-[#EAF7EA]"
                        >
                          {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                        </select>
                        {isCustom && (
                          <input type="text" placeholder="Enter custom value"
                            value={overrides[f.label]?.[idx] ?? ''}
                            onChange={(e) => setVal(f.label, idx, e.target.value)}
                            className="w-full px-3 py-2 rounded-md text-sm border border-green-400 bg-white" />
                        )}
                      </div>
                    );
                  })}
                </Row>
              ))}
            </ConfigSection>
          )}
          {/* Section 3 — mandatory text */}
          {textFields.length > 0 && (
            <ConfigSection title="User Input Fields" tint="bg-[#FDEEF0]" note="Mandatory fields must be filled (or have a default).">
              {textFields.map((f) => (
                <Row key={`${f.row}`} label={f.label + (f.mandatory ? ' *' : '')} note={f.source_note}>
                  {f.value_cols.map((_c, idx) => {
                    const v = overrides[f.label]?.[idx] ?? '';
                    const blank = f.mandatory && !v.trim();
                    return (
                      <div key={idx} className="flex-1 space-y-1">
                        {f.sub_labels[idx] && <span className="text-xs text-gray-500">{f.sub_labels[idx]}</span>}
                        <input type="text" value={v} onChange={(e) => setVal(f.label, idx, e.target.value)}
                          className={`w-full px-3 py-2 rounded-md text-sm border ${blank ? 'bg-[#FDEEF0] border-red-400' : 'bg-white border-gray-300'}`} />
                      </div>
                    );
                  })}
                </Row>
              ))}
            </ConfigSection>
          )}

          <div className="flex items-center justify-between pt-4 border-t mt-4">
            <span className="text-sm text-gray-500">
              {missingMandatory.length > 0
                ? `${missingMandatory.length} mandatory field(s) need a value`
                : `Ready · ${selectedTags.length} datasheet(s)`}
            </span>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setShowConfig(false)}>Cancel</Button>
              <Button onClick={() => { setShowConfig(false); setShowPreview(true); }} disabled={missingMandatory.length > 0}>
                Preview →
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Preview Popup ───────────────────────────────────────────────────── */}
      {showPreview && (
        <Modal title="Datasheet Preview" onClose={() => setShowPreview(false)}>
          <p className="text-sm text-gray-600 mb-3">
            Common specifications below apply to all <strong>{selectedTags.length}</strong> selected tag(s).
            IODB fields are filled individually per tag at generation.
          </p>
          <div className="border border-gray-200 rounded-lg overflow-auto max-h-[26rem]">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Section</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Field</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Value</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {grouped.map((g) => g.fields.map((f) => (
                  <tr key={`${f.row}`} className={f.input_type === 'iodb' ? 'bg-[#FFFDE7]' : f.input_type === 'dropdown' ? 'bg-[#F4FBF4]' : 'bg-[#FDF5F6]'}>
                    <td className="px-3 py-2 text-gray-500">{g.fields[0] === f ? g.section : ''}</td>
                    <td className="px-3 py-2 text-gray-800">{f.label}</td>
                    <td className="px-3 py-2 text-gray-700">
                      {f.input_type === 'iodb'
                        ? <span className="italic text-gray-400">From IODB (per tag)</span>
                        : f.value_cols.map((_c, idx) => valueOf(f.label, idx, f.defaults[idx] || '')).join(' / ')}
                    </td>
                    <td className="px-3 py-2 text-xs uppercase text-gray-400">{f.input_type}</td>
                  </tr>
                )))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-end gap-2 pt-4 border-t mt-4">
            <Button variant="ghost" onClick={() => { setShowPreview(false); setShowConfig(true); }}>← Back to Edit</Button>
            <Button onClick={handleGenerate} loading={generating} className="bg-green-600 hover:bg-green-700">
              <FileText className="w-5 h-5" /> Confirm & Generate {selectedTags.length}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

/* ── Small presentational helpers ────────────────────────────────────────── */
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h3 className="text-lg font-bold text-gray-900">{title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-6 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-4 mb-4 text-xs">
      <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-[#FFF9C4] border border-yellow-400" /> IODB (auto per tag)</span>
      <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-[#EAF7EA] border border-green-300" /> Predefined dropdown</span>
      <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-[#FDEEF0] border border-red-300" /> Mandatory input</span>
    </div>
  );
}

function ConfigSection({ title, tint, note, children }: { title: string; tint: string; note: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <h4 className={`text-sm font-semibold text-gray-800 px-3 py-1.5 rounded mb-1 ${tint}`}>{title}</h4>
      <p className="text-xs text-gray-500 mb-2">{note}</p>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Row({ label, note, children }: { label: string; note?: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-2 items-start">
      <label className="text-sm text-gray-700 md:col-span-1 pt-2">
        {label}
        {note && <span className="block text-xs text-gray-400">{note}</span>}
      </label>
      <div className="md:col-span-2 flex gap-2">{children}</div>
    </div>
  );
}
