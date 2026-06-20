/**
 * DataSheetGenerator — iEZ SIMRE-driven 5-step wizard
 * Step 1: Upload IODB → pick instrument type
 * Step 2: Select tags → upload SOP → pick datasheet sheet
 * Step 3: Configure specs  (IODB auto | SIMRE | Manual)
 * Step 4: Notes + Vendor Recommendation + Model freeze
 * Step 5: Generate + Download ZIP
 */
import { useMemo, useState, useRef } from 'react';
import {
  FileText, Upload, Download, CheckCircle2, Search, FileSpreadsheet,
  X, ChevronRight, Zap, SlidersHorizontal, Star,
  Lock, Unlock, RefreshCw, ChevronDown, ChevronUp,
} from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import LTRadarWizard from './LTRadarWizard';

const isLTRadar = (type: string) => {
  const result = /\bLT\b|\bNCR\b|non.?contact.*radar|radar.*level|FMCW/i.test(type);
  console.log(`[DSG] isLTRadar("${type}") =`, result);
  return result;
};

// ── Types ──────────────────────────────────────────────────────────────────────
interface FieldSpec {
  section: string; label: string; row: number;
  value_cols: number[]; sub_labels: string[];
  source: 'iodb' | 'predefined'; defaults: string[]; source_note: string;
  color: string; input_type: 'iodb' | 'dropdown' | 'text'; options: string[]; mandatory: boolean;
}
interface DatasheetInfo { sheet: string; eg_sheet: string | null; title: string; }
interface VendorMatch { vendor: string; model: string; match_pct: number; strengths: string[]; gaps: string[]; }
interface GenStatus { job_id: string; status: 'processing' | 'done' | 'error'; result?: { filename: string; tag_count: number; message: string }; error?: string; }
interface ExtractResult { extracted_value: string; confidence: number; raw_snippet: string; error?: string; }

const POLL_MS = 3000;
const CUSTOM = 'Custom Value';

// Field role classification
const role = (f: FieldSpec): 'iodb' | 'simre' | 'manual' => {
  if (f.input_type === 'iodb') return 'iodb';
  if (f.mandatory) return 'simre';
  return 'manual';
};

// ── Step indicator ─────────────────────────────────────────────────────────────
const STEPS_NORMAL = ['IODB & Type', 'Tags & SOP', 'Spec Config', 'Notes & Vendor', 'Generate'];
const STEPS_LT = ['IODB & Type', 'Tag', 'Input', 'Header', 'Specs', 'Vendor', 'Purchase', 'Generate'];

function StepBar({ current, ltMode }: { current: number; ltMode?: boolean }) {
  const steps = ltMode ? STEPS_LT : STEPS_NORMAL;
  return (
    <div className="flex items-center gap-0 mb-8">
      {steps.map((label, i) => {
        const idx = i + 1;
        const done = idx < current;
        const active = idx === current;
        return (
          <div key={i} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300"
                style={{
                  background: done ? 'var(--em)' : active ? 'var(--em-dim)' : 'var(--s3)',
                  border: `1.5px solid ${done || active ? 'var(--em)' : 'var(--b2)'}`,
                  color: done ? '#fff' : active ? 'var(--em-lt)' : 'var(--t2)',
                }}
              >
                {done ? <CheckCircle2 className="w-4 h-4" /> : idx}
              </div>
              <span className="text-[10px] font-medium whitespace-nowrap" style={{ color: active ? 'var(--em-lt)' : done ? 'var(--t1)' : 'var(--t2)' }}>
                {label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div className="flex-1 h-px mx-2 mb-5" style={{ background: done ? 'var(--em)' : 'var(--b2)', transition: 'background 0.3s' }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Inline file drop zone ──────────────────────────────────────────────────────
function DropZone({ file, onChange, accept, label }: { file: File | null; onChange: (f: File | null) => void; accept: string; label: string }) {
  const id = `dz-${label.replace(/\s/g, '-')}`;
  return (
    <label htmlFor={id} className="flex items-center gap-3 rounded-xl cursor-pointer px-4 py-3 transition-all duration-200"
      style={{
        background: file ? 'rgba(16,185,129,0.06)' : 'var(--s1)',
        border: `1.5px dashed ${file ? 'var(--em)' : 'var(--b2)'}`,
      }}
      onMouseEnter={e => { if (!file) e.currentTarget.style.borderColor = 'var(--em)'; }}
      onMouseLeave={e => { if (!file) e.currentTarget.style.borderColor = 'var(--b2)'; }}
    >
      {file
        ? <><CheckCircle2 className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--em)' }} /><span className="text-xs font-medium truncate" style={{ color: 'var(--em-lt)' }}>{file.name}</span><span className="ml-auto text-[10px]" style={{ color: 'var(--t2)' }}>Replace</span></>
        : <><Upload className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--t2)' }} /><span className="text-xs" style={{ color: 'var(--t1)' }}>{label}</span><span className="ml-auto text-[10px]" style={{ color: 'var(--t2)' }}>{accept}</span></>
      }
      <input id={id} type="file" accept={accept} className="hidden" onChange={e => onChange(e.target.files?.[0] || null)} />
    </label>
  );
}

// ── SIMRE extraction panel (slide-in drawer) ───────────────────────────────────
function SimrePanel({
  field, onClose, onConfirm,
}: { field: FieldSpec; onClose: () => void; onConfirm: (values: string[]) => void; }) {
  const [tab, setTab] = useState<'upload' | 'manual'>('upload');
  const [tenderFile, setTenderFile] = useState<File | null>(null);
  const [tenderText, setTenderText] = useState('');
  const [manualValues, setManualValues] = useState<string[]>(field.defaults.map(() => ''));
  const [extracted, setExtracted] = useState<ExtractResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const extract = async () => {
    setBusy(true); setErr(''); setExtracted(null);
    try {
      const fd = new FormData();
      fd.append('label', field.label);
      if (tab === 'upload' && tenderFile) fd.append('tender_file', tenderFile);
      else fd.append('tender_text', tenderText);
      const res = await api.post('/sop-datasheet/extract-spec', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      if (res.data.error) setErr(res.data.error);
      else setExtracted(res.data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Extraction failed');
    } finally { setBusy(false); }
  };

  const handleConfirm = () => {
    if (tab === 'upload' && extracted?.extracted_value) {
      onConfirm(field.value_cols.map(() => extracted.extracted_value));
    } else {
      onConfirm(manualValues);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg rounded-2xl overflow-hidden animate-rise" style={{ background: 'var(--s2)', border: '1px solid var(--b2)' }}>
        {/* Header */}
        <div className="px-5 py-4 flex items-center gap-3" style={{ borderBottom: '1px solid var(--b1)' }}>
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.2)' }}>
            <Zap className="w-4 h-4" style={{ color: 'var(--rose)' }} />
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-wide" style={{ color: 'var(--rose)' }}>SIMRE Extraction</p>
            <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>{field.label}</p>
          </div>
          <button onClick={onClose} className="ml-auto opacity-50 hover:opacity-90 transition-opacity" style={{ color: 'var(--t1)' }}>
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex" style={{ borderBottom: '1px solid var(--b1)' }}>
          {(['upload', 'manual'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)} className="flex-1 py-2.5 text-xs font-semibold capitalize transition-all"
              style={{
                background: tab === t ? 'var(--em-dim)' : 'transparent',
                color: tab === t ? 'var(--em-lt)' : 'var(--t2)',
                borderBottom: tab === t ? '2px solid var(--em)' : '2px solid transparent',
              }}
            >
              {t === 'upload' ? '📄 Upload Tender' : '✏️ Manual Entry'}
            </button>
          ))}
        </div>

        <div className="p-5 space-y-4">
          {tab === 'upload' ? (
            <>
              <DropZone file={tenderFile} onChange={setTenderFile} accept=".pdf,.txt,.csv" label="Upload tender document (PDF/TXT)" />
              <div>
                <p className="text-xs mb-1.5" style={{ color: 'var(--t2)' }}>Or paste tender text directly:</p>
                <textarea
                  value={tenderText} onChange={e => setTenderText(e.target.value)}
                  placeholder="Paste relevant specification excerpt..."
                  rows={4} className="w-full rounded-lg resize-none text-xs p-3"
                  style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }}
                />
              </div>
              <Button variant="secondary" onClick={extract} loading={busy} fullWidth>
                <Zap className="w-3.5 h-3.5" /> Extract with AI
              </Button>
              {extracted && (
                <div className="rounded-xl p-3 space-y-2" style={{ background: 'var(--s3)', border: '1px solid var(--b2)' }}>
                  <div className="flex items-center justify-between">
                    <span className="text-xs" style={{ color: 'var(--t2)' }}>Extracted value</span>
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full" style={{
                      background: extracted.confidence > 0.7 ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)',
                      color: extracted.confidence > 0.7 ? 'var(--em)' : 'var(--gold)',
                    }}>
                      {Math.round(extracted.confidence * 100)}% confidence
                    </span>
                  </div>
                  <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>{extracted.extracted_value || '—'}</p>
                  {extracted.raw_snippet && <p className="text-[11px] italic" style={{ color: 'var(--t2)' }}>"{extracted.raw_snippet}"</p>}
                </div>
              )}
              {err && <Alert variant="error">{err}</Alert>}
            </>
          ) : (
            <>
              {field.value_cols.map((_, i) => (
                <div key={i}>
                  {field.sub_labels[i] && <p className="text-xs mb-1" style={{ color: 'var(--t2)' }}>{field.sub_labels[i]}</p>}
                  <input
                    type="text" value={manualValues[i] || ''}
                    onChange={e => setManualValues(v => v.map((x, j) => j === i ? e.target.value : x))}
                    placeholder={field.defaults[i] || `Enter ${field.label}`}
                    className="w-full rounded-lg px-3 py-2 text-sm"
                    style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }}
                  />
                </div>
              ))}
            </>
          )}
        </div>

        <div className="px-5 pb-5 flex gap-2">
          <Button variant="secondary" onClick={onClose} fullWidth>Cancel</Button>
          <Button onClick={handleConfirm} fullWidth
            disabled={tab === 'upload' ? !extracted?.extracted_value : manualValues.every(v => !v.trim())}
          >
            <CheckCircle2 className="w-3.5 h-3.5" /> Confirm
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function DataSheetGenerator() {
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // LT radar sub-flow tracking
  const [ltStep, setLtStep] = useState(1); // wizard internal step 1-6, maps to outer step 2-7

  // Step 1
  const [iodbFile, setIodbFile] = useState<File | null>(null);
  const [instrumentTypes, setInstrumentTypes] = useState<string[]>([]);
  const [selectedType, setSelectedType] = useState('');
  const [typeSearch, setTypeSearch] = useState('');

  // Step 2
  const [tags, setTags] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagSearch, setTagSearch] = useState('');
  const [sopFile, setSopFile] = useState<File | null>(null);
  const [datasheets, setDatasheets] = useState<DatasheetInfo[]>([]);
  const [selectedDatasheet, setSelectedDatasheet] = useState('');
  const [fields, setFields] = useState<FieldSpec[]>([]);

  // Step 3 — field configuration
  const [overrides, setOverrides] = useState<Record<string, string[]>>({});
  const [customMode, setCustomMode] = useState<Record<string, boolean>>({});
  const [simreField, setSimreField] = useState<FieldSpec | null>(null);
  const [iodbExpanded, setIodbExpanded] = useState(false);

  // Step 4
  const [notes, setNotes] = useState('');
  const [vendors, setVendors] = useState<VendorMatch[] | null>(null);
  const [vendorLoading, setVendorLoading] = useState(false);
  const [selectedVendor, setSelectedVendor] = useState<VendorMatch | null>(null);
  const [modelFrozen, setModelFrozen] = useState(false);

  // Step 5
  const [genStatus, setGenStatus] = useState<GenStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearError = () => setError('');

  // ── Derived lists ──────────────────────────────────────────────────────────
  const iodbFields = useMemo(() => fields.filter(f => role(f) === 'iodb'), [fields]);
  const simreFields = useMemo(() => fields.filter(f => role(f) === 'simre'), [fields]);
  const manualFields = useMemo(() => fields.filter(f => role(f) === 'manual'), [fields]);

  const filteredTypes = useMemo(() =>
    instrumentTypes.filter(t => t.toLowerCase().includes(typeSearch.toLowerCase())),
    [instrumentTypes, typeSearch]);

  const filteredTags = useMemo(() =>
    tags.filter(t => t.toLowerCase().includes(tagSearch.toLowerCase())),
    [tags, tagSearch]);

  const simreConfigured = useMemo(() =>
    simreFields.filter(f => overrides[f.label]?.some(v => v.trim())).length,
    [simreFields, overrides]);

  // ── Step 1: load instrument types ──────────────────────────────────────────
  const loadInstrumentTypes = async () => {
    if (!iodbFile) return;
    setBusy(true); clearError();
    try {
      const fd = new FormData();
      fd.append('iodb_file', iodbFile);
      const res = await api.post('/sop-datasheet/instrument-types', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setInstrumentTypes(res.data.instrument_types || []);
      setSelectedType('');
      setTags([]);
      setSelectedTags([]);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to read IODB');
    } finally { setBusy(false); }
  };

  // ── Step 2a: load tags ──────────────────────────────────────────────────────
  const loadTags = async (type: string) => {
    if (!iodbFile || !type) return;
    setBusy(true); clearError();
    try {
      const fd = new FormData();
      fd.append('iodb_file', iodbFile);
      fd.append('instrument_type', type);
      const res = await api.post('/sop-datasheet/tags', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setTags(res.data.tags || []);
      setSelectedTags([]);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load tags');
    } finally { setBusy(false); }
  };

  const handleTypeSelect = (t: string) => {
    console.log('[DSG] handleTypeSelect:', t);
    setSelectedType(t);
    loadTags(t);
  };

  // ── Step 2b: load datasheets ───────────────────────────────────────────────
  const loadDatasheets = async (file: File) => {
    setSopFile(file);
    setDatasheets([]); setSelectedDatasheet(''); setFields([]);
    setBusy(true); clearError();
    try {
      const fd = new FormData();
      fd.append('sop_file', file);
      const res = await api.post('/sop-datasheet/datasheets', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setDatasheets(res.data.datasheets || []);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to read SOP template');
    } finally { setBusy(false); }
  };

  // ── Step 2c: load fields ───────────────────────────────────────────────────
  const loadFields = async (sheet: string) => {
    if (!sopFile) return;
    setSelectedDatasheet(sheet); setFields([]); setOverrides({}); setCustomMode({});
    setBusy(true); clearError();
    try {
      const fd = new FormData();
      fd.append('sop_file', sopFile);
      fd.append('datasheet_sheet', sheet);
      const res = await api.post('/sop-datasheet/fields', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      const f: FieldSpec[] = res.data.fields || [];
      setFields(f);
      // Pre-populate overrides with defaults
      const init: Record<string, string[]> = {};
      f.forEach(spec => { init[spec.label] = [...spec.defaults]; });
      setOverrides(init);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load field specs');
    } finally { setBusy(false); }
  };

  const canProceedStep2 = selectedTags.length > 0 && selectedDatasheet && fields.length > 0;

  // ── Step 3: helpers ────────────────────────────────────────────────────────
  const setFieldValues = (label: string, values: string[]) => {
    setOverrides(o => ({ ...o, [label]: values }));
  };

  const handleSimreConfirm = (values: string[]) => {
    if (simreField) setFieldValues(simreField.label, values);
    setSimreField(null);
  };

  // ── Step 4: vendor recommendation ─────────────────────────────────────────
  const fetchVendors = async () => {
    setVendorLoading(true); clearError();
    try {
      const specObj: Record<string, string> = {};
      [...simreFields, ...manualFields].forEach(f => {
        const vals = overrides[f.label];
        if (vals?.some(v => v.trim())) specObj[f.label] = vals.filter(Boolean).join(' / ');
      });
      const fd = new FormData();
      fd.append('instrument_type', selectedType);
      fd.append('spec_json', JSON.stringify(specObj));
      const res = await api.post('/sop-datasheet/vendor-recommend', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setVendors(res.data.vendors || []);
      if (res.data.recommended) {
        const top = (res.data.vendors as VendorMatch[]).find(v => v.vendor === res.data.recommended);
        if (top) setSelectedVendor(top);
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Vendor recommendation failed');
    } finally { setVendorLoading(false); }
  };

  // ── Step 5: generate ───────────────────────────────────────────────────────
  const startGenerate = async () => {
    if (!sopFile || !iodbFile || !selectedDatasheet || !selectedTags.length) return;
    setBusy(true); setGenStatus(null); clearError();
    try {
      const fd = new FormData();
      fd.append('sop_file', sopFile);
      fd.append('iodb_file', iodbFile);
      fd.append('datasheet_sheet', selectedDatasheet);
      fd.append('instrument_type', selectedType);
      fd.append('selected_tags', JSON.stringify(selectedTags));
      // Build overrides excluding IODB fields (backend auto-fills those)
      const out: Record<string, string[]> = {};
      [...simreFields, ...manualFields].forEach(f => {
        const v = overrides[f.label];
        if (v) out[f.label] = v;
      });
      if (selectedVendor) {
        out['Selected Vendor'] = [selectedVendor.vendor];
        out['Selected Model'] = [selectedVendor.model];
      }
      if (notes.trim()) out['Notes'] = [notes];
      fd.append('overrides', JSON.stringify(out));
      const res = await api.post('/sop-datasheet/generate', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setGenStatus({ job_id: res.data.job_id, status: 'processing' });
      pollRef.current = setInterval(async () => {
        try {
          const s = await api.get(`/sop-datasheet/generate/status/${res.data.job_id}`);
          setGenStatus(s.data);
          if (s.data.status !== 'processing') {
            clearInterval(pollRef.current!);
            setBusy(false);
          }
        } catch { /* keep polling */ }
      }, POLL_MS);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Generation failed');
      setBusy(false);
    }
  };

  const downloadZip = async () => {
    try {
      const res = await api.get('/sop-datasheet/download', { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/zip' }));
      const a = document.createElement('a'); a.href = url; a.download = 'Datasheets.zip'; a.click();
      URL.revokeObjectURL(url);
    } catch { setError('Download failed'); }
  };

  // ── Render helpers ─────────────────────────────────────────────────────────
  const card = (children: React.ReactNode, className = '') => (
    <div className={`rounded-2xl p-6 ${className}`} style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
      {children}
    </div>
  );

  const sectionTitle = (icon: React.ReactNode, title: string, color = 'var(--t0)') => (
    <div className="flex items-center gap-2 mb-4">
      {icon}
      <span className="text-sm font-bold" style={{ color }}>{title}</span>
    </div>
  );

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <PageHeader
        icon={FileSpreadsheet}
        title="Datasheet Generator"
        description="SIMRE-driven, IODB-linked instrument datasheet creation for water treatment plants"
      />

      <StepBar
        current={isLTRadar(selectedType) && step > 1 ? ltStep + 1 : step}
        ltMode={isLTRadar(selectedType)}
      />

      {error && <Alert variant="error" onClose={clearError}>{error}</Alert>}

      {/* ── STEP 1: IODB + Instrument Type ── */}
      {step === 1 && (
        <div className="space-y-4">
          {card(
            <>
              {sectionTitle(<FileText className="w-4 h-4" style={{ color: 'var(--em)' }} />, 'Upload IODB File')}
              <DropZone file={iodbFile} onChange={f => { setIodbFile(f); setInstrumentTypes([]); setSelectedType(''); }} accept=".xlsx,.xls" label="Upload IODB spreadsheet" />
              {iodbFile && instrumentTypes.length === 0 && (
                <Button onClick={loadInstrumentTypes} loading={busy} fullWidth className="mt-3">
                  <Search className="w-3.5 h-3.5" /> Analyse IODB
                </Button>
              )}
              {instrumentTypes.length > 0 && (
                <Alert variant="info" className="mt-3">
                  Found <strong>{instrumentTypes.length}</strong> AI instrument types with sub-systems
                </Alert>
              )}
            </>
          )}

          {instrumentTypes.length > 0 && card(
            <>
              {sectionTitle(<SlidersHorizontal className="w-4 h-4" style={{ color: 'var(--gold)' }} />, 'Select Instrument Type', 'var(--gold)')}
              <div className="relative mb-3">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: 'var(--t2)' }} />
                <input
                  value={typeSearch} onChange={e => setTypeSearch(e.target.value)}
                  placeholder="Search instrument types..."
                  className="w-full pl-9 pr-4 py-2 rounded-lg text-sm"
                  style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }}
                />
              </div>
              <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
                {filteredTypes.map(t => (
                  <button key={t} onClick={() => handleTypeSelect(t)}
                    className="w-full text-left px-3 py-2.5 rounded-xl text-sm transition-all duration-150"
                    style={{
                      background: selectedType === t ? 'var(--em-dim)' : 'var(--s3)',
                      border: `1px solid ${selectedType === t ? 'var(--em)' : 'var(--b1)'}`,
                      color: selectedType === t ? 'var(--em-lt)' : 'var(--t1)',
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>

              {selectedType && (
                <Button onClick={() => {
                  console.log(`[DSG] Continue clicked. selectedType="${selectedType}" isLT=${isLTRadar(selectedType)}`);
                  setLtStep(1); setStep(2);
                }} className="mt-4 w-full">
                  Continue <ChevronRight className="w-3.5 h-3.5" />
                </Button>
              )}
            </>
          )}
        </div>
      )}

      {/* ── LT RADAR SUB-FLOW (steps 2-7 when LT type selected) ── */}
      {step >= 2 && (() => { console.log(`[DSG] step=${step} selectedType="${selectedType}" isLT=${isLTRadar(selectedType)} iodbFile=${!!iodbFile} → LTWizard renders=${step >= 2 && isLTRadar(selectedType) && !!iodbFile}`); return true; })() && isLTRadar(selectedType) && iodbFile && (
        <LTRadarWizard
          iodbFile={iodbFile}
          instrumentType={selectedType}
          onBack={() => { setStep(1); setLtStep(1); }}
          onStepChange={s => setLtStep(s)}
        />
      )}

      {/* ── STEP 2: Tags + SOP (normal flow only) ── */}
      {step === 2 && !isLTRadar(selectedType) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Left: Tags */}
          {card(
            <>
              {sectionTitle(<Search className="w-4 h-4" style={{ color: 'var(--em)' }} />, `Tags — ${selectedType}`)}
              {busy && tags.length === 0 && <p className="text-xs" style={{ color: 'var(--t2)' }}>Loading tags…</p>}
              {tags.length > 0 && (
                <>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs" style={{ color: 'var(--t2)' }}>{tags.length} AI tags found</span>
                    <button onClick={() => setSelectedTags(selectedTags.length === tags.length ? [] : [...tags])}
                      className="text-[11px] font-semibold" style={{ color: 'var(--em)' }}>
                      {selectedTags.length === tags.length ? 'Deselect all' : 'Select all'}
                    </button>
                  </div>
                  <div className="relative mb-2">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3 h-3" style={{ color: 'var(--t2)' }} />
                    <input value={tagSearch} onChange={e => setTagSearch(e.target.value)} placeholder="Filter tags..." className="w-full pl-8 pr-3 py-1.5 rounded-lg text-xs"
                      style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                  </div>
                  <div className="space-y-1 max-h-52 overflow-y-auto pr-1">
                    {filteredTags.map(tag => {
                      const checked = selectedTags.includes(tag);
                      return (
                        <label key={tag} className="flex items-center gap-2.5 px-3 py-2 rounded-lg cursor-pointer transition-all"
                          style={{ background: checked ? 'var(--em-dim)' : 'var(--s3)', border: `1px solid ${checked ? 'rgba(16,185,129,0.3)' : 'transparent'}` }}>
                          <input type="checkbox" checked={checked} onChange={() => setSelectedTags(s => checked ? s.filter(x => x !== tag) : [...s, tag])} className="accent-emerald-500" />
                          <span className="text-xs font-mono" style={{ color: checked ? 'var(--em-lt)' : 'var(--t1)' }}>{tag}</span>
                        </label>
                      );
                    })}
                  </div>
                  {selectedTags.length > 0 && (
                    <div className="mt-3 text-xs font-semibold" style={{ color: 'var(--em)' }}>{selectedTags.length} tag(s) selected</div>
                  )}
                </>
              )}
            </>
          )}

          {/* Right: SOP + Datasheet */}
          {card(
            <>
              {sectionTitle(<FileSpreadsheet className="w-4 h-4" style={{ color: 'var(--gold)' }} />, 'SOP Template', 'var(--gold)')}
              <DropZone file={sopFile} onChange={f => f && loadDatasheets(f)} accept=".xlsx,.xls" label="Upload SOP template workbook" />

              {datasheets.length > 0 && (
                <div className="mt-4 space-y-1.5">
                  <p className="text-xs mb-2" style={{ color: 'var(--t2)' }}>Select datasheet:</p>
                  {datasheets.map(d => (
                    <button key={d.sheet} onClick={() => loadFields(d.sheet)}
                      className="w-full text-left px-3 py-2.5 rounded-xl text-xs transition-all"
                      style={{
                        background: selectedDatasheet === d.sheet ? 'rgba(245,158,11,0.08)' : 'var(--s3)',
                        border: `1px solid ${selectedDatasheet === d.sheet ? 'rgba(245,158,11,0.4)' : 'var(--b1)'}`,
                        color: selectedDatasheet === d.sheet ? 'var(--gold)' : 'var(--t1)',
                      }}>
                      <span className="font-semibold">{d.title || d.sheet}</span>
                      {d.eg_sheet && <span className="ml-2 opacity-60 text-[10px]">{d.sheet}</span>}
                    </button>
                  ))}
                </div>
              )}

              {fields.length > 0 && (
                <Alert variant="success" className="mt-3">
                  Loaded <strong>{fields.length}</strong> spec fields — {iodbFields.length} auto, {simreFields.length} SIMRE, {manualFields.length} manual
                </Alert>
              )}
            </>
          )}

          <div className="lg:col-span-2 flex gap-3">
            <Button variant="secondary" onClick={() => setStep(1)}>← Back</Button>
            <Button onClick={() => setStep(3)} disabled={!canProceedStep2} className="flex-1">
              Configure Specs <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 3: Spec Configuration ── */}
      {step === 3 && !isLTRadar(selectedType) && (
        <div className="space-y-4">
          {/* IODB auto section (collapsible) */}
          {card(
            <>
              <button className="w-full flex items-center gap-2" onClick={() => setIodbExpanded(x => !x)}>
                <div className="w-2.5 h-2.5 rounded-full" style={{ background: 'var(--em)' }} />
                <span className="text-sm font-bold flex-1 text-left" style={{ color: 'var(--em-lt)' }}>
                  Auto-filled from IODB ({iodbFields.length} fields)
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--em-dim)', color: 'var(--em)' }}>Auto</span>
                {iodbExpanded ? <ChevronUp className="w-4 h-4" style={{ color: 'var(--t2)' }} /> : <ChevronDown className="w-4 h-4" style={{ color: 'var(--t2)' }} />}
              </button>
              {iodbExpanded && (
                <div className="mt-4 grid grid-cols-2 gap-2">
                  {iodbFields.map(f => (
                    <div key={f.label} className="rounded-lg px-3 py-2" style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
                      <p className="text-[10px]" style={{ color: 'var(--t2)' }}>{f.section}</p>
                      <p className="text-xs font-semibold" style={{ color: 'var(--t1)' }}>{f.label}</p>
                      <p className="text-[11px] mt-0.5 italic" style={{ color: 'var(--em)' }}>From IODB</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* SIMRE required fields */}
          {simreFields.length > 0 && card(
            <>
              {sectionTitle(
                <div className="w-2.5 h-2.5 rounded-full" style={{ background: 'var(--rose)' }} />,
                `SIMRE Required (${simreConfigured}/${simreFields.length} configured)`,
                'var(--rose)'
              )}
              <div className="space-y-2">
                {simreFields.map(f => {
                  const vals = overrides[f.label] || [];
                  const done = vals.some(v => v.trim());
                  return (
                    <div key={f.label} className="flex items-center gap-3 rounded-xl px-4 py-3" style={{ background: 'var(--s3)', border: `1px solid ${done ? 'rgba(16,185,129,0.25)' : 'rgba(248,113,113,0.15)'}` }}>
                      <div>
                        <p className="text-[10px]" style={{ color: 'var(--t2)' }}>{f.section}</p>
                        <p className="text-sm font-semibold" style={{ color: done ? 'var(--t0)' : 'var(--t1)' }}>{f.label}</p>
                        {done && <p className="text-xs mt-0.5 truncate max-w-xs" style={{ color: 'var(--em)' }}>{vals.filter(Boolean).join(' / ')}</p>}
                      </div>
                      <button onClick={() => setSimreField(f)}
                        className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all"
                        style={{
                          background: done ? 'var(--em-dim)' : 'rgba(248,113,113,0.1)',
                          color: done ? 'var(--em-lt)' : 'var(--rose)',
                          border: `1px solid ${done ? 'rgba(16,185,129,0.3)' : 'rgba(248,113,113,0.2)'}`,
                        }}>
                        {done ? <><CheckCircle2 className="w-3 h-3" /> Edit</> : <><Zap className="w-3 h-3" /> Configure</>}
                      </button>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {/* Manual fields */}
          {manualFields.length > 0 && card(
            <>
              {sectionTitle(
                <div className="w-2.5 h-2.5 rounded-full" style={{ background: 'var(--t2)' }} />,
                `Manual Entry (${manualFields.length} fields)`,
                'var(--t1)'
              )}
              <div className="space-y-3">
                {manualFields.map(f => {
                  const vals = overrides[f.label] || f.defaults;
                  const isCustom = customMode[f.label];
                  return (
                    <div key={f.label} className="rounded-xl p-3" style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
                      <p className="text-[10px] mb-1" style={{ color: 'var(--t2)' }}>{f.section} · {f.label}</p>
                      {f.input_type === 'dropdown' && !isCustom ? (
                        <div className="flex gap-2">
                          <select
                            value={vals[0] || ''} onChange={e => {
                              if (e.target.value === CUSTOM) setCustomMode(m => ({ ...m, [f.label]: true }));
                              else setFieldValues(f.label, [e.target.value]);
                            }}
                            className="flex-1 rounded-lg px-3 py-1.5 text-xs"
                            style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }}>
                            {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                          </select>
                        </div>
                      ) : (
                        <div className="flex gap-2 items-center">
                          {f.value_cols.map((_, i) => (
                            <div key={i} className="flex-1">
                              {f.sub_labels[i] && <p className="text-[10px] mb-0.5" style={{ color: 'var(--t2)' }}>{f.sub_labels[i]}</p>}
                              <input type="text" value={vals[i] || ''} onChange={e => {
                                const next = [...(overrides[f.label] || f.defaults)];
                                next[i] = e.target.value;
                                setFieldValues(f.label, next);
                              }} placeholder={f.defaults[i] || f.label} className="w-full rounded-lg px-3 py-1.5 text-xs"
                                style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                            </div>
                          ))}
                          {isCustom && (
                            <button onClick={() => { setCustomMode(m => ({ ...m, [f.label]: false })); setFieldValues(f.label, f.defaults); }}
                              className="text-[10px] px-2 py-1 rounded" style={{ color: 'var(--t2)', background: 'var(--s2)' }}>Reset</button>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(2)}>← Back</Button>
            <Button onClick={() => setStep(4)} className="flex-1">
              Notes & Vendor <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 4: Notes + Vendor ── */}
      {step === 4 && !isLTRadar(selectedType) && (
        <div className="space-y-4">
          {card(
            <>
              {sectionTitle(<FileText className="w-4 h-4" style={{ color: 'var(--sky)' }} />, 'Notes', 'var(--sky)')}
              <textarea value={notes} onChange={e => setNotes(e.target.value)}
                placeholder="Add any notes, special requirements, or remarks for these datasheets…"
                rows={4} className="w-full rounded-xl resize-none text-sm p-3"
                style={{ background: 'var(--s3)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
            </>
          )}

          {card(
            <>
              {sectionTitle(<Star className="w-4 h-4" style={{ color: 'var(--gold)' }} />, 'Vendor Recommendation (SIMRE)', 'var(--gold)')}
              {!vendors && (
                <div className="text-center py-4">
                  <p className="text-sm mb-4" style={{ color: 'var(--t2)' }}>
                    AI-powered vendor match analysis based on your specification profile
                  </p>
                  <Button variant="secondary" onClick={fetchVendors} loading={vendorLoading}>
                    <Zap className="w-3.5 h-3.5" /> Run Vendor Analysis
                  </Button>
                </div>
              )}
              {vendors && (
                <div className="space-y-3">
                  {vendors.map(v => {
                    const picked = selectedVendor?.vendor === v.vendor;
                    return (
                      <div key={v.vendor}
                        className="rounded-xl p-4 cursor-pointer transition-all"
                        style={{
                          background: picked ? 'rgba(245,158,11,0.06)' : 'var(--s3)',
                          border: `1px solid ${picked ? 'rgba(245,158,11,0.5)' : 'var(--b1)'}`,
                        }}
                        onClick={() => { if (!modelFrozen) setSelectedVendor(v); }}
                      >
                        <div className="flex items-center gap-3 mb-2">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-bold" style={{ color: picked ? 'var(--gold)' : 'var(--t0)' }}>{v.vendor}</span>
                              {picked && <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ background: 'rgba(245,158,11,0.15)', color: 'var(--gold)' }}>Selected</span>}
                            </div>
                            <span className="text-xs" style={{ color: 'var(--t2)' }}>{v.model}</span>
                          </div>
                          <div className="text-right">
                            <span className="text-lg font-bold" style={{ color: v.match_pct >= 80 ? 'var(--em)' : v.match_pct >= 60 ? 'var(--gold)' : 'var(--rose)' }}>
                              {v.match_pct}%
                            </span>
                            <p className="text-[10px]" style={{ color: 'var(--t2)' }}>match</p>
                          </div>
                        </div>
                        {/* Match bar */}
                        <div className="h-1.5 rounded-full mb-3" style={{ background: 'var(--s4)' }}>
                          <div className="h-full rounded-full transition-all duration-500" style={{
                            width: `${v.match_pct}%`,
                            background: v.match_pct >= 80 ? 'var(--em)' : v.match_pct >= 60 ? 'var(--gold)' : 'var(--rose)',
                          }} />
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-[11px]">
                          <div>
                            {v.strengths.map((s, i) => <div key={i} className="flex gap-1.5 mb-0.5"><span style={{ color: 'var(--em)' }}>+</span><span style={{ color: 'var(--t1)' }}>{s}</span></div>)}
                          </div>
                          <div>
                            {v.gaps.map((g, i) => <div key={i} className="flex gap-1.5 mb-0.5"><span style={{ color: 'var(--rose)' }}>−</span><span style={{ color: 'var(--t1)' }}>{g}</span></div>)}
                          </div>
                        </div>
                      </div>
                    );
                  })}

                  <div className="flex gap-2 items-center">
                    <Button variant="ghost" size="sm" onClick={fetchVendors} loading={vendorLoading}>
                      <RefreshCw className="w-3 h-3" /> Re-run
                    </Button>
                    {selectedVendor && (
                      <button
                        onClick={() => setModelFrozen(f => !f)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ml-auto"
                        style={{
                          background: modelFrozen ? 'rgba(16,185,129,0.1)' : 'var(--s3)',
                          border: `1px solid ${modelFrozen ? 'var(--em)' : 'var(--b2)'}`,
                          color: modelFrozen ? 'var(--em-lt)' : 'var(--t1)',
                        }}
                      >
                        {modelFrozen ? <><Lock className="w-3 h-3" /> Model locked</> : <><Unlock className="w-3 h-3" /> Lock model</>}
                      </button>
                    )}
                  </div>
                  {modelFrozen && selectedVendor && (
                    <Alert variant="success">
                      Model locked: <strong>{selectedVendor.vendor} — {selectedVendor.model}</strong>. This selection will be included in all generated datasheets.
                    </Alert>
                  )}
                </div>
              )}
            </>
          )}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(3)}>← Back</Button>
            <Button onClick={() => { setStep(5); startGenerate(); }} className="flex-1">
              Generate Datasheets <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 5: Generate & Download ── */}
      {step === 5 && !isLTRadar(selectedType) && (
        <div className="space-y-4">
          {card(
            <div className="text-center py-6">
              {genStatus?.status === 'processing' && (
                <>
                  <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4" style={{ background: 'var(--em-dim)', border: '1px solid var(--em)' }}>
                    <RefreshCw className="w-6 h-6 animate-spin" style={{ color: 'var(--em)' }} />
                  </div>
                  <p className="text-base font-bold mb-1" style={{ color: 'var(--t0)' }}>Generating datasheets…</p>
                  <p className="text-sm" style={{ color: 'var(--t2)' }}>Creating {selectedTags.length} Excel file(s) for {selectedType}</p>
                </>
              )}
              {genStatus?.status === 'done' && (
                <>
                  <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4" style={{ background: 'var(--em-dim)', border: '1px solid var(--em)' }}>
                    <CheckCircle2 className="w-6 h-6" style={{ color: 'var(--em)' }} />
                  </div>
                  <p className="text-base font-bold mb-1" style={{ color: 'var(--t0)' }}>Datasheets ready!</p>
                  <p className="text-sm mb-6" style={{ color: 'var(--t2)' }}>{genStatus.result?.message}</p>
                  <Button onClick={downloadZip} size="lg">
                    <Download className="w-4 h-4" /> Download ZIP
                  </Button>
                </>
              )}
              {genStatus?.status === 'error' && (
                <Alert variant="error">{genStatus.error || 'Generation failed'}</Alert>
              )}
              {!genStatus && busy && (
                <p className="text-sm" style={{ color: 'var(--t2)' }}>Starting job…</p>
              )}
            </div>
          )}

          {/* Summary */}
          {card(
            <>
              {sectionTitle(<FileText className="w-4 h-4" style={{ color: 'var(--t1)' }} />, 'Generation Summary')}
              <div className="grid grid-cols-2 gap-3 text-sm">
                {[
                  ['Instrument Type', selectedType],
                  ['Tags', `${selectedTags.length} selected`],
                  ['Datasheet', selectedDatasheet],
                  ['IODB Fields', `${iodbFields.length} auto`],
                  ['SIMRE Fields', `${simreConfigured}/${simreFields.length} configured`],
                  ['Selected Vendor', selectedVendor ? `${selectedVendor.vendor}` : 'None'],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-lg px-3 py-2" style={{ background: 'var(--s3)' }}>
                    <p className="text-[10px]" style={{ color: 'var(--t2)' }}>{k}</p>
                    <p className="text-xs font-semibold truncate" style={{ color: 'var(--t0)' }}>{v}</p>
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => { setStep(4); setGenStatus(null); if (pollRef.current) clearInterval(pollRef.current); setBusy(false); }}>
              ← Back
            </Button>
            {genStatus?.status === 'done' && (
              <Button variant="ghost" onClick={() => { setStep(1); setIodbFile(null); setSopFile(null); setInstrumentTypes([]); setSelectedType(''); setTags([]); setSelectedTags([]); setDatasheets([]); setSelectedDatasheet(''); setFields([]); setOverrides({}); setVendors(null); setSelectedVendor(null); setModelFrozen(false); setNotes(''); setGenStatus(null); }} className="flex-1">
                Start New
              </Button>
            )}
          </div>
        </div>
      )}

      {/* SIMRE extraction panel */}
      {simreField && (
        <SimrePanel field={simreField} onClose={() => setSimreField(null)} onConfirm={handleSimreConfirm} />
      )}
    </div>
  );
}
