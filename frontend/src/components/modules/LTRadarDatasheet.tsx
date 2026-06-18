/**
 * LTRadarDatasheet.tsx
 * Full wizard for generating LT Non-Contact Radar instrument datasheets.
 *
 * Wizard steps:
 *  1  Upload IODB → select tag → auto-fill GREEN fields
 *  2  Header info (CLIENT / CONSULTANT / PROJECT / LOCATION / ISSUED FOR)
 *  3  RED specs — AI extraction OR manual dropdown selection + rule validation
 *  4  PURCHASE (Make / Model) + NOTES
 *  5  Review all fields + generate clean xlsx
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import {
  Upload, ChevronRight, ChevronLeft, CheckCircle2, AlertTriangle,
  Sparkles, Download, RefreshCw, X, Info, Zap, FileText,
  Radio, Settings, ShoppingCart, Eye, Loader2,
} from 'lucide-react';
import api from '@/services/api';

// ── Types ─────────────────────────────────────────────────────────────────────
interface SpecField {
  id: string;
  label: string;
  section: string;
  color: string;
  options?: string[];
  default?: string;
  fixed?: string;
}

interface SpecsMeta {
  fields: SpecField[];
  dropdowns: Record<string, string[]>;
  defaults: Record<string, string>;
}

interface AiExtracted {
  label: string;
  field_id: string;
  value: string;
  confidence: number;
  snippet: string;
  selected: boolean;
}

type Values = Record<string, string>;

// ── Constants ─────────────────────────────────────────────────────────────────
const BEAM_ANGLE_MAP: Record<string, string[]> = {
  '80 GHz': ['3°', '4°', '5°', '6°'],
  '26 GHz': ['8°', '10°', '12°', '14°'],
};

const STEPS = [
  { id: 1, label: 'IODB & Tag',     icon: Upload },
  { id: 2, label: 'Header',         icon: FileText },
  { id: 3, label: 'Specifications', icon: Settings },
  { id: 4, label: 'Purchase',       icon: ShoppingCart },
  { id: 5, label: 'Review',         icon: Eye },
];

// ── Sub-components ────────────────────────────────────────────────────────────

function StepBar({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {STEPS.map((s, i) => {
        const Icon = s.icon;
        const done = current > s.id;
        const active = current === s.id;
        return (
          <div key={s.id} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all"
                style={{
                  background: done ? 'var(--em)' : active ? 'var(--em-dim)' : 'var(--s3)',
                  border: `2px solid ${done || active ? 'var(--em)' : 'var(--b2)'}`,
                  color: done ? '#fff' : active ? 'var(--em-lt)' : 'var(--t2)',
                }}
              >
                {done ? <CheckCircle2 className="w-4 h-4" /> : <Icon className="w-4 h-4" />}
              </div>
              <span className="text-[9px] font-semibold whitespace-nowrap" style={{ color: active ? 'var(--em-lt)' : 'var(--t2)' }}>
                {s.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className="flex-1 h-0.5 mx-1 mb-4 rounded" style={{ background: done ? 'var(--em)' : 'var(--b1)' }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function DropZone({ label, accept, onFile, file }: {
  label: string; accept: string;
  onFile: (f: File) => void;
  file: File | null;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const handle = (f: File) => { if (f) onFile(f); };

  return (
    <div
      onClick={() => ref.current?.click()}
      onDragOver={e => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) handle(f); }}
      className="flex flex-col items-center justify-center gap-2 rounded-xl cursor-pointer transition-all p-5"
      style={{
        border: `2px dashed ${drag ? 'var(--em)' : 'var(--b2)'}`,
        background: drag ? 'var(--em-dim)' : 'var(--s1)',
        minHeight: '90px',
      }}
    >
      <input ref={ref} type="file" accept={accept} className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) handle(f); }} />
      {file ? (
        <>
          <CheckCircle2 className="w-5 h-5" style={{ color: 'var(--em)' }} />
          <span className="text-xs font-medium" style={{ color: 'var(--em-lt)' }}>{file.name}</span>
        </>
      ) : (
        <>
          <Upload className="w-5 h-5" style={{ color: 'var(--t2)' }} />
          <span className="text-xs" style={{ color: 'var(--t1)' }}>{label}</span>
        </>
      )}
    </div>
  );
}

function FieldInput({ field, value, onChange, beamOptions }: {
  field: SpecField; value: string;
  onChange: (v: string) => void;
  beamOptions?: string[];
}) {
  if (field.fixed) {
    return (
      <div className="input-field opacity-60 cursor-not-allowed text-xs" style={{ background: 'var(--s0)' }}>
        {field.fixed}
      </div>
    );
  }
  const opts = field.id === 'beam_angle' ? (beamOptions || field.options || []) : (field.options || []);
  if (opts.length > 0) {
    return (
      <select
        value={value || field.default || ''}
        onChange={e => onChange(e.target.value)}
        className="input-field text-xs"
      >
        <option value="">— select —</option>
        {opts.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  }
  return (
    <input
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={`Enter ${field.label}…`}
      className="input-field text-xs"
    />
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function LTRadarDatasheet() {
  const [step, setStep]             = useState(1);
  const [meta, setMeta]             = useState<SpecsMeta | null>(null);
  const [metaLoading, setMetaLoading] = useState(false);

  // Step 1
  const [iodbFile, setIodbFile]     = useState<File | null>(null);
  const [tags, setTags]             = useState<string[]>([]);
  const [tagsLoading, setTagsLoading] = useState(false);
  const [selectedTag, setSelectedTag] = useState('');
  const [iodobValues, setIodbValues] = useState<Values>({});
  const [iodobLoading, setIodbLoading] = useState(false);
  const [missingGreen, setMissingGreen] = useState<string[]>([]);

  // Shared values dict
  const [values, setValues]         = useState<Values>({});

  // Step 3 – AI
  const [tenderFile, setTenderFile] = useState<File | null>(null);
  const [tenderText, setTenderText] = useState('');
  const [aiMode, setAiMode]         = useState<'none' | 'upload' | 'text' | 'done'>('none');
  const [aiLoading, setAiLoading]   = useState(false);
  const [aiResults, setAiResults]   = useState<AiExtracted[]>([]);
  const [showAiPanel, setShowAiPanel] = useState(false);

  // Validation
  const [validErrors, setValidErrors] = useState<string[]>([]);
  const [validWarns, setValidWarns]   = useState<string[]>([]);
  const [validating, setValidating]   = useState(false);

  // Generate
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError]     = useState('');

  const set = useCallback((id: string, v: string) =>
    setValues(prev => ({ ...prev, [id]: v })), []);

  // Load specs metadata on mount
  useEffect(() => {
    setMetaLoading(true);
    api.get('/lt-radar/specs-meta')
      .then(r => {
        setMeta(r.data);
        // Pre-fill defaults
        const defs: Values = {};
        Object.entries(r.data.defaults as Record<string, string>).forEach(([k, v]) => { defs[k] = v; });
        setValues(prev => ({ ...defs, ...prev }));
      })
      .catch(() => {})
      .finally(() => setMetaLoading(false));
  }, []);

  // ── Step 1: Load tags from IODB ──────────────────────────────────────────
  const loadTags = useCallback(async () => {
    if (!iodbFile) return;
    setTagsLoading(true);
    const fd = new FormData();
    fd.append('iodb_file', iodbFile);
    try {
      const r = await api.post('/lt-radar/tags', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setTags(r.data.tags);
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Failed to read IODB tags');
    } finally {
      setTagsLoading(false);
    }
  }, [iodbFile]);

  // ── Step 1: Fetch IODB values for tag ────────────────────────────────────
  const fetchIodbValues = useCallback(async () => {
    if (!iodbFile || !selectedTag) return;
    setIodbLoading(true);
    const fd = new FormData();
    fd.append('iodb_file', iodbFile);
    fd.append('tag_no', selectedTag);
    try {
      const r = await api.post('/lt-radar/iodb-lookup', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setIodbValues(r.data.values);
      setMissingGreen(r.data.missing_fields || []);
      setValues(prev => ({ ...prev, ...r.data.values }));
    } catch (e: any) {
      alert(e.response?.data?.detail || 'IODB lookup failed');
    } finally {
      setIodbLoading(false);
    }
  }, [iodbFile, selectedTag]);

  // ── Step 3: AI extraction ────────────────────────────────────────────────
  const runAiExtract = useCallback(async () => {
    if (!meta) return;
    setAiLoading(true);
    const redFields = meta.fields.filter(f => f.color === 'red' && !f.fixed)
      .map(f => ({ id: f.id, label: f.label }));

    const fd = new FormData();
    fd.append('spec_labels', JSON.stringify(redFields));
    if (tenderFile) fd.append('tender_file', tenderFile);
    fd.append('tender_text', tenderText);

    try {
      const r = await api.post('/lt-radar/ai-extract', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      const extracted: AiExtracted[] = (r.data.fields || []).map((f: any) => ({
        ...f, selected: f.confidence >= 0.5 && f.value !== '',
      }));
      setAiResults(extracted);
      setAiMode('done');
    } catch (e: any) {
      alert(e.response?.data?.detail || 'AI extraction failed');
    } finally {
      setAiLoading(false);
    }
  }, [meta, tenderFile, tenderText]);

  const applyAiResults = useCallback(() => {
    const updates: Values = {};
    aiResults.filter(f => f.selected && f.value).forEach(f => { updates[f.field_id] = f.value; });
    setValues(prev => ({ ...prev, ...updates }));
    setShowAiPanel(false);
  }, [aiResults]);

  // ── Validate ─────────────────────────────────────────────────────────────
  const runValidation = useCallback(async () => {
    setValidating(true);
    const fd = new FormData();
    fd.append('spec_json', JSON.stringify(values));
    try {
      const r = await api.post('/lt-radar/validate', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setValidErrors(r.data.errors || []);
      setValidWarns(r.data.warnings || []);
    } catch {
      setValidErrors(['Validation request failed']);
    } finally {
      setValidating(false);
    }
  }, [values]);

  useEffect(() => {
    if (step === 5) runValidation();
  }, [step]);

  // ── Generate ─────────────────────────────────────────────────────────────
  const generate = useCallback(async () => {
    if (validErrors.length > 0) return;
    setGenerating(true);
    setGenError('');
    try {
      const fd = new FormData();
      fd.append('values_json', JSON.stringify(values));
      const r = await api.post('/lt-radar/generate', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        responseType: 'blob',
      });
      const tag = values.tag_no || 'LT_RADAR';
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `LT_Radar_Datasheet_${tag}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      const msg = e.response?.data?.detail || 'Generation failed';
      setGenError(typeof msg === 'object' ? JSON.stringify(msg) : String(msg));
    } finally {
      setGenerating(false);
    }
  }, [values, validErrors]);

  // ── Field groups ──────────────────────────────────────────────────────────
  const greenFields  = meta?.fields.filter(f => f.color === 'green') ?? [];
  const redFields    = meta?.fields.filter(f => f.color === 'red')   ?? [];
  const beamOpts = BEAM_ANGLE_MAP[values.frequency] ?? BEAM_ANGLE_MAP['80 GHz'];

  // Group red fields by section
  const redBySec = redFields.reduce<Record<string, SpecField[]>>((acc, f) => {
    (acc[f.section] = acc[f.section] || []).push(f);
    return acc;
  }, {});

  // ── Render ────────────────────────────────────────────────────────────────
  if (metaLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin" style={{ color: 'var(--em)' }} />
        <span className="ml-3 text-sm" style={{ color: 'var(--t1)' }}>Loading module…</span>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-rise">
      {/* ── Header ── */}
      <div className="rounded-2xl p-6" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
            style={{ background: 'linear-gradient(135deg, var(--em), #1d4ed8)', boxShadow: '0 6px 20px var(--em-glow)' }}>
            <Radio className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-black mb-1" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)', letterSpacing: '-0.02em' }}>
              LT Non-Contact Radar Datasheet
            </h1>
            <p className="text-sm" style={{ color: 'var(--t1)' }}>
              Generate clean engineering datasheets from IODB data and AI-assisted spec extraction.
            </p>
          </div>
        </div>
      </div>

      {/* ── Wizard ── */}
      <div className="rounded-2xl p-6" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        <StepBar current={step} />

        {/* ════════════════════════ STEP 1 ════════════════════════ */}
        {step === 1 && (
          <div className="space-y-5 animate-fade-in">
            <SectionTitle icon={Upload} title="Upload IODB & Select Tag" />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label>IODB File (.xlsx / .xls)</Label>
                <DropZone label="Drop IODB file here or click to browse"
                  accept=".xls,.xlsx,.xlsm" file={iodbFile}
                  onFile={f => { setIodbFile(f); setTags([]); setSelectedTag(''); }} />
                <button
                  disabled={!iodbFile || tagsLoading}
                  onClick={loadTags}
                  className="btn btn-primary w-full mt-2 py-2 text-xs"
                >
                  {tagsLoading ? <><Loader2 className="w-3 h-3 animate-spin" /> Loading Tags…</> : 'Load Tags from IODB'}
                </button>
              </div>

              <div>
                <Label>Select Instrument Tag</Label>
                {tags.length === 0 ? (
                  <div className="rounded-xl p-4 text-xs text-center" style={{ background: 'var(--s1)', border: '1px solid var(--b1)', color: 'var(--t2)' }}>
                    Upload IODB first to see available tags
                  </div>
                ) : (
                  <select
                    value={selectedTag}
                    onChange={e => setSelectedTag(e.target.value)}
                    className="input-field text-xs"
                    size={Math.min(tags.length, 8)}
                    style={{ height: 'auto' }}
                  >
                    {tags.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                )}
                {selectedTag && (
                  <button
                    onClick={fetchIodbValues}
                    disabled={iodobLoading}
                    className="btn btn-primary w-full mt-2 py-2 text-xs"
                  >
                    {iodobLoading ? <><Loader2 className="w-3 h-3 animate-spin" /> Fetching…</> : `Fetch IODB Data for ${selectedTag}`}
                  </button>
                )}
              </div>
            </div>

            {/* IODB fetch results */}
            {Object.keys(iodobValues).length > 0 && (
              <div className="rounded-xl p-4 space-y-2" style={{ background: 'var(--s1)', border: '1px solid rgba(59,130,246,0.2)' }}>
                <p className="text-xs font-semibold mb-2" style={{ color: 'var(--em-lt)' }}>
                  ✓ {Object.keys(iodobValues).length} IODB fields fetched for <strong>{selectedTag}</strong>
                </p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-1">
                  {Object.entries(iodobValues).slice(0, 12).map(([k, v]) => (
                    <div key={k} className="text-xs">
                      <span style={{ color: 'var(--t2)' }}>{k}: </span>
                      <span style={{ color: 'var(--t0)' }}>{v}</span>
                    </div>
                  ))}
                </div>
                {missingGreen.length > 0 && (
                  <p className="text-xs mt-2" style={{ color: 'var(--gold)' }}>
                    ⚠ {missingGreen.length} field(s) not found in IODB — you'll enter them manually in Step 3.
                  </p>
                )}
              </div>
            )}

            {/* Missing fields manual entry */}
            {missingGreen.length > 0 && (
              <div className="space-y-3">
                <p className="text-xs font-semibold" style={{ color: 'var(--gold)' }}>
                  Value not available in IODB — please enter manually:
                </p>
                {greenFields.filter(f => missingGreen.includes(f.id)).map(f => (
                  <div key={f.id} className="flex items-center gap-3">
                    <label className="text-xs w-48 flex-shrink-0" style={{ color: 'var(--t1)' }}>{f.label} *</label>
                    <input
                      type="text"
                      value={values[f.id] || ''}
                      onChange={e => set(f.id, e.target.value)}
                      placeholder={`Enter ${f.label}…`}
                      className="input-field text-xs"
                    />
                  </div>
                ))}
              </div>
            )}

            <NavButtons
              onNext={() => { if (!selectedTag) { alert('Please select a tag first'); return; } setStep(2); }}
              nextDisabled={!selectedTag}
              nextLabel="Continue →"
            />
          </div>
        )}

        {/* ════════════════════════ STEP 2 ════════════════════════ */}
        {step === 2 && (
          <div className="space-y-5 animate-fade-in">
            <SectionTitle icon={FileText} title="Project Header Information" />
            <p className="text-xs" style={{ color: 'var(--t1)' }}>These fields appear in the header block of the datasheet. All are mandatory.</p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                { id: 'client',      label: 'CLIENT *' },
                { id: 'consultant',  label: 'CONSULTANT *' },
                { id: 'project',     label: 'PROJECT *' },
                { id: 'location_hdr',label: 'LOCATION *' },
                { id: 'issued_for',  label: 'ISSUED FOR *' },
              ].map(f => (
                <div key={f.id}>
                  <Label>{f.label}</Label>
                  <input
                    type="text"
                    value={values[f.id] || ''}
                    onChange={e => set(f.id, e.target.value)}
                    placeholder={`Enter ${f.label.replace(' *', '')}…`}
                    className="input-field text-xs"
                  />
                </div>
              ))}
            </div>

            <NavButtons
              onBack={() => setStep(1)}
              onNext={() => {
                const required = ['client', 'consultant', 'project', 'location_hdr', 'issued_for'];
                const missing = required.filter(k => !values[k]?.trim());
                if (missing.length) { alert(`Required: ${missing.join(', ')}`); return; }
                setStep(3);
              }}
              nextLabel="Next: Specifications →"
            />
          </div>
        )}

        {/* ════════════════════════ STEP 3 ════════════════════════ */}
        {step === 3 && (
          <div className="space-y-5 animate-fade-in">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <SectionTitle icon={Settings} title="Sensor & Transmitter Specifications" />
              <button
                onClick={() => setShowAiPanel(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all"
                style={{ background: 'var(--gold-dim)', color: 'var(--gold)', border: '1px solid rgba(245,158,11,0.25)' }}
              >
                <Sparkles className="w-3.5 h-3.5" /> AI Spec Extraction
              </button>
            </div>

            <p className="text-xs" style={{ color: 'var(--t1)' }}>
              Select values using dropdowns. Use <strong style={{ color: 'var(--gold)' }}>AI Extraction</strong> to auto-fill from a tender PDF.
            </p>

            {Object.entries(redBySec).map(([section, fields]) => (
              <div key={section} className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--b1)' }}>
                <div className="px-4 py-2.5" style={{ background: 'var(--s3)', borderBottom: '1px solid var(--b1)' }}>
                  <span className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--em-lt)' }}>{section}</span>
                </div>
                <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                  {fields.map(f => (
                    <div key={f.id}>
                      <Label>{f.label}{!f.fixed ? '' : ''}</Label>
                      {f.fixed ? (
                        <div className="input-field text-xs opacity-60" style={{ background: 'var(--s0)' }}>
                          {f.fixed} <span className="ml-1 text-[9px]" style={{ color: 'var(--em)' }}>(fixed)</span>
                        </div>
                      ) : (
                        <FieldInput field={f} value={values[f.id] || ''} onChange={v => set(f.id, v)} beamOptions={beamOpts} />
                      )}
                      {/* Inline rule feedback */}
                      {f.id === 'beam_angle' && values.frequency && !(BEAM_ANGLE_MAP[values.frequency] || []).includes(values.beam_angle) && values.beam_angle && (
                        <p className="text-[10px] mt-0.5" style={{ color: 'var(--rose)' }}>
                          ✗ Selected Beam Angle not valid for {values.frequency}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}

            <NavButtons
              onBack={() => setStep(2)}
              onNext={() => setStep(4)}
              nextLabel="Next: Purchase Info →"
            />

            {/* ── AI Panel (slide-in modal) ── */}
            {showAiPanel && (
              <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.7)' }}>
                <div className="w-full max-w-2xl rounded-2xl overflow-hidden animate-rise" style={{ background: 'var(--s2)', border: '1px solid var(--b2)' }}>
                  {/* Header */}
                  <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: '1px solid var(--b1)' }}>
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4" style={{ color: 'var(--gold)' }} />
                      <span className="font-bold text-sm" style={{ color: 'var(--t0)' }}>AI Specification Extraction</span>
                    </div>
                    <button onClick={() => setShowAiPanel(false)} style={{ color: 'var(--t2)' }}>
                      <X className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="p-6 space-y-4 max-h-[75vh] overflow-y-auto">
                    {aiMode === 'none' && (
                      <div className="space-y-3">
                        <p className="text-sm" style={{ color: 'var(--t1)' }}>
                          Upload a tender PDF or paste specification text. AI will extract values for all RED specification fields.
                        </p>
                        <div className="grid grid-cols-2 gap-3">
                          <button
                            onClick={() => setAiMode('upload')}
                            className="btn btn-secondary py-3 flex-col gap-1 h-auto"
                          >
                            <Upload className="w-5 h-5" />
                            <span className="text-xs">Upload File</span>
                            <span className="text-[10px]" style={{ color: 'var(--t2)' }}>PDF, DOCX, XLSX</span>
                          </button>
                          <button
                            onClick={() => setAiMode('text')}
                            className="btn btn-secondary py-3 flex-col gap-1 h-auto"
                          >
                            <FileText className="w-5 h-5" />
                            <span className="text-xs">Paste Text</span>
                            <span className="text-[10px]" style={{ color: 'var(--t2)' }}>Copy from PDF/Doc</span>
                          </button>
                        </div>
                      </div>
                    )}

                    {aiMode === 'upload' && (
                      <div className="space-y-3">
                        <DropZone label="Drop tender PDF / DOCX / XLSX" accept=".pdf,.docx,.xlsx,.txt"
                          file={tenderFile} onFile={f => setTenderFile(f)} />
                        <div className="flex gap-2">
                          <button onClick={() => setAiMode('none')} className="btn btn-secondary text-xs flex-1 py-2">← Back</button>
                          <button
                            onClick={runAiExtract}
                            disabled={!tenderFile || aiLoading}
                            className="btn btn-primary text-xs flex-1 py-2"
                          >
                            {aiLoading ? <><Loader2 className="w-3 h-3 animate-spin" /> Extracting…</> : <><Zap className="w-3 h-3" /> Extract Specs</>}
                          </button>
                        </div>
                      </div>
                    )}

                    {aiMode === 'text' && (
                      <div className="space-y-3">
                        <textarea
                          value={tenderText}
                          onChange={e => setTenderText(e.target.value)}
                          placeholder="Paste tender / specification text here…"
                          className="input-field text-xs"
                          rows={8}
                        />
                        <div className="flex gap-2">
                          <button onClick={() => setAiMode('none')} className="btn btn-secondary text-xs flex-1 py-2">← Back</button>
                          <button
                            onClick={runAiExtract}
                            disabled={!tenderText.trim() || aiLoading}
                            className="btn btn-primary text-xs flex-1 py-2"
                          >
                            {aiLoading ? <><Loader2 className="w-3 h-3 animate-spin" /> Extracting…</> : <><Zap className="w-3 h-3" /> Extract Specs</>}
                          </button>
                        </div>
                      </div>
                    )}

                    {aiMode === 'done' && aiResults.length > 0 && (
                      <div className="space-y-3">
                        <p className="text-xs font-semibold" style={{ color: 'var(--em-lt)' }}>
                          AI extracted {aiResults.filter(f => f.value).length} values. Select which to apply:
                        </p>
                        <div className="space-y-2">
                          {aiResults.filter(f => f.value).map((f, i) => (
                            <div key={i} className="flex items-center gap-3 px-3 py-2 rounded-lg" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
                              <input
                                type="checkbox"
                                checked={f.selected}
                                onChange={e => setAiResults(prev => prev.map((x, j) => j === i ? { ...x, selected: e.target.checked } : x))}
                                className="w-4 h-4 accent-blue-500"
                              />
                              <div className="flex-1 min-w-0">
                                <span className="text-xs font-medium" style={{ color: 'var(--t0)' }}>{f.label}</span>
                                <span className="ml-2 text-xs font-bold" style={{ color: 'var(--em-lt)' }}>{f.value}</span>
                              </div>
                              <div className="flex items-center gap-1">
                                <div className="w-12 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--s3)' }}>
                                  <div className="h-full rounded-full" style={{ width: `${f.confidence * 100}%`, background: f.confidence > 0.7 ? 'var(--em)' : 'var(--gold)' }} />
                                </div>
                                <span className="text-[10px]" style={{ color: 'var(--t2)' }}>{Math.round(f.confidence * 100)}%</span>
                              </div>
                            </div>
                          ))}
                        </div>
                        <div className="flex gap-2 pt-2">
                          <button onClick={() => setAiMode('upload')} className="btn btn-secondary text-xs flex-1 py-2">Re-upload</button>
                          <button onClick={applyAiResults} className="btn btn-primary text-xs flex-1 py-2">
                            <CheckCircle2 className="w-3 h-3" /> Apply Selected
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ════════════════════════ STEP 4 ════════════════════════ */}
        {step === 4 && (
          <div className="space-y-5 animate-fade-in">
            <SectionTitle icon={ShoppingCart} title="Purchase Information & Notes" />

            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--b1)' }}>
              <div className="px-4 py-2.5" style={{ background: 'var(--s3)', borderBottom: '1px solid var(--b1)' }}>
                <span className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--em-lt)' }}>PURCHASE</span>
              </div>
              <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Make / Manufacturer *</Label>
                  <input type="text" value={values.make || ''} onChange={e => set('make', e.target.value)}
                    placeholder="e.g. Endress+Hauser, VEGA, Emerson…" className="input-field text-xs" />
                </div>
                <div>
                  <Label>Model Number *</Label>
                  <input type="text" value={values.model_no || ''} onChange={e => set('model_no', e.target.value)}
                    placeholder="e.g. FMR57-AAACHBAAAA" className="input-field text-xs" />
                </div>
              </div>
            </div>

            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--b1)' }}>
              <div className="px-4 py-2.5" style={{ background: 'var(--s3)', borderBottom: '1px solid var(--b1)' }}>
                <span className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--em-lt)' }}>NOTES</span>
              </div>
              <div className="p-4">
                <textarea
                  value={values.notes || ''}
                  onChange={e => set('notes', e.target.value)}
                  placeholder="Any additional remarks, special requirements, or notes for this instrument…"
                  className="input-field text-xs"
                  rows={4}
                />
              </div>
            </div>

            <NavButtons
              onBack={() => setStep(3)}
              onNext={() => {
                if (!values.make?.trim() || !values.model_no?.trim()) {
                  alert('Make and Model are required for the PURCHASE section.');
                  return;
                }
                setStep(5);
              }}
              nextLabel="Review & Generate →"
            />
          </div>
        )}

        {/* ════════════════════════ STEP 5 ════════════════════════ */}
        {step === 5 && (
          <div className="space-y-5 animate-fade-in">
            <SectionTitle icon={Eye} title="Review & Generate Datasheet" />

            {/* Validation */}
            {validating && (
              <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--t1)' }}>
                <Loader2 className="w-4 h-4 animate-spin" /> Running validation checks…
              </div>
            )}

            {validErrors.length > 0 && (
              <div className="rounded-xl p-4 space-y-1.5" style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.25)' }}>
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="w-4 h-4" style={{ color: 'var(--rose)' }} />
                  <span className="text-sm font-semibold" style={{ color: 'var(--rose)' }}>Validation Errors — fix before generating</span>
                </div>
                {validErrors.map((e, i) => <p key={i} className="text-xs" style={{ color: 'var(--rose)' }}>• {e}</p>)}
              </div>
            )}

            {validWarns.length > 0 && (
              <div className="rounded-xl p-4 space-y-1.5" style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)' }}>
                <div className="flex items-center gap-2 mb-1">
                  <Info className="w-4 h-4" style={{ color: 'var(--gold)' }} />
                  <span className="text-xs font-semibold" style={{ color: 'var(--gold)' }}>Warnings</span>
                </div>
                {validWarns.map((w, i) => <p key={i} className="text-xs" style={{ color: 'var(--gold)' }}>• {w}</p>)}
              </div>
            )}

            {!validating && validErrors.length === 0 && (
              <div className="rounded-xl p-3" style={{ background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)' }}>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4" style={{ color: 'var(--em)' }} />
                  <span className="text-xs font-semibold" style={{ color: 'var(--em-lt)' }}>All validation checks passed.</span>
                </div>
              </div>
            )}

            {/* Values summary */}
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--b1)' }}>
              <div className="px-4 py-2.5" style={{ background: 'var(--s3)', borderBottom: '1px solid var(--b1)' }}>
                <span className="text-xs font-bold uppercase" style={{ color: 'var(--t1)' }}>Datasheet Summary</span>
              </div>
              <div className="p-4 grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2 max-h-72 overflow-y-auto">
                {meta?.fields.filter(f => values[f.id]).map(f => (
                  <div key={f.id} className="text-xs">
                    <div style={{ color: 'var(--t2)' }}>{f.label}</div>
                    <div className="font-medium truncate" style={{ color: 'var(--t0)' }}>
                      {f.fixed || values[f.id]}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {genError && (
              <div className="rounded-xl px-4 py-3 text-xs" style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
                ✗ {genError}
              </div>
            )}

            <div className="flex gap-3 flex-wrap">
              <button onClick={() => setStep(4)} className="btn btn-secondary text-xs px-5 py-2.5">
                <ChevronLeft className="w-3.5 h-3.5" /> Back
              </button>
              <button
                onClick={generate}
                disabled={generating || validErrors.length > 0}
                className="btn btn-primary text-sm px-6 py-2.5 flex-1"
              >
                {generating
                  ? <><Loader2 className="w-4 h-4 animate-spin" /> Generating…</>
                  : <><Download className="w-4 h-4" /> Generate Clean Datasheet (.xlsx)</>}
              </button>
              <button
                onClick={() => { runValidation(); }}
                disabled={validating}
                className="btn btn-secondary text-xs px-4 py-2.5"
                title="Re-run validation"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Shared micro-components ────────────────────────────────────────────────────
function SectionTitle({ icon: Icon, title }: { icon: any; title: string }) {
  return (
    <div className="flex items-center gap-2.5 mb-1">
      <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'var(--em-dim)', border: '1px solid var(--em)' }}>
        <Icon className="w-4 h-4" style={{ color: 'var(--em-lt)' }} />
      </div>
      <h2 className="text-sm font-bold" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)' }}>{title}</h2>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--t2)' }}>{children}</label>;
}

function NavButtons({ onBack, onNext, nextLabel = 'Next →', nextDisabled = false }: {
  onBack?: () => void; onNext?: () => void;
  nextLabel?: string; nextDisabled?: boolean;
}) {
  return (
    <div className="flex justify-between pt-3 border-t" style={{ borderColor: 'var(--b1)' }}>
      {onBack
        ? <button onClick={onBack} className="btn btn-secondary text-xs px-5 py-2.5">
            <ChevronLeft className="w-3.5 h-3.5" /> Back
          </button>
        : <div />}
      {onNext && (
        <button onClick={onNext} disabled={nextDisabled} className="btn btn-primary text-xs px-5 py-2.5">
          {nextLabel} <ChevronRight className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}
