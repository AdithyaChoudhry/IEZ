/* ─────────────────────────────────────────────────────────────────────────────
   LT Non-Contact Radar Wizard — integrated inside Datasheet Generator
   7 steps: Tag → Input Method → Header → Specs → Purchase/Vendor → Preview+Auth → Generate
───────────────────────────────────────────────────────────────────────────── */
import { useState, useCallback, useEffect } from 'react';
import {
  Search, ChevronRight, ChevronLeft, CheckCircle2, AlertTriangle,
  Sparkles, Download, RefreshCw, X, Zap, FileText, Radio,
  Settings, Eye, Loader2, Lock, ExternalLink,
  Star, Shield, Thermometer, Gauge, Wifi, Package,
  Upload, User, KeyRound,
} from 'lucide-react';
import api from '@/services/api';
import { scoreVendors, VendorScore } from '@/data/ltRadarVendors';

// ── Props ──────────────────────────────────────────────────────────────────────
interface Props {
  iodbFile: File;
  instrumentType: string;
  onBack: () => void;
  onStepChange?: (step: number) => void; // notifies parent of internal step (1-6)
}

// ── Types ──────────────────────────────────────────────────────────────────────
type Values = Record<string, string>;

interface ITag { tag: string; iodb_data: Record<string, string> }

interface SpecField {
  id: string; label: string; section: string; color: string;
  options?: string[] | null; default?: string | null; fixed?: string | null;
}

interface SpecMeta {
  fields: SpecField[];
  dropdowns: Record<string, string[]>;
  defaults: Record<string, string>;
}

// ── LT Wizard Step Bar (6 internal steps) ─────────────────────────────────────
const LT_WIZARD_STEPS = [
  { id: 1, label: 'Tag' },
  { id: 2, label: 'Input' },
  { id: 3, label: 'Header' },
  { id: 4, label: 'Specs' },
  { id: 5, label: 'Vendor' },
  { id: 6, label: 'Preview & Generate' },
];

function LTStepBar({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-0 mb-6">
      {LT_WIZARD_STEPS.map((s, i) => {
        const done   = current > s.id;
        const active = current === s.id;
        return (
          <div key={s.id} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1">
              <div className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold transition-all"
                style={{
                  background: done ? 'var(--em)' : active ? 'var(--em-dim)' : 'var(--s3)',
                  border: `2px solid ${done || active ? 'var(--em)' : 'var(--b2)'}`,
                  color: done ? '#fff' : active ? 'var(--em-lt)' : 'var(--t2)',
                }}>
                {done ? <CheckCircle2 className="w-3 h-3" /> : s.id}
              </div>
              <span className="text-[9px] font-medium whitespace-nowrap"
                style={{ color: active ? 'var(--em-lt)' : done ? 'var(--t1)' : 'var(--t2)' }}>
                {s.label}
              </span>
            </div>
            {i < LT_WIZARD_STEPS.length - 1 && (
              <div className="flex-1 h-px mx-1 mb-4"
                style={{ background: done ? 'var(--em)' : 'var(--b2)', transition: 'background 0.3s' }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Validation rules ───────────────────────────────────────────────────────────
const BEAM_ANGLE_MAP: Record<string, string[]> = {
  '80 GHz': ['3°', '4°', '5°', '6°'],
  '26 GHz': ['8°', '10°', '12°', '14°'],
};

function validate(v: Values): string[] {
  const errs: string[] = [];
  const freq = v['Frequency'] || '';
  const beam = v['Beam Angle'] || '';
  if (freq && beam && BEAM_ANGLE_MAP[freq]) {
    if (!BEAM_ANGLE_MAP[freq].includes(beam))
      errs.push(`Beam angle ${beam} is not valid for ${freq} — use ${BEAM_ANGLE_MAP[freq].join(' / ')}`);
  }
  const output = v['Output'] || '';
  if (output.includes('PROFIBUS') && output.includes('Foundation Fieldbus'))
    errs.push('Cannot select both PROFIBUS and Foundation Fieldbus simultaneously');
  if (v['Process Temperature'] && parseFloat(v['Process Temperature']) > 200)
    errs.push('Process temperature exceeds 200°C — verify transmitter suitability');
  if (v['Process Pressure'] && parseFloat(v['Process Pressure']) > 40)
    errs.push('Process pressure exceeds 40 bar — check pressure-rated antenna selection');
  return errs;
}

// ── Helpers ────────────────────────────────────────────────────────────────────
const card = (children: React.ReactNode, extra = '') => (
  <div className={`rounded-2xl p-6 ${extra}`} style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
    {children}
  </div>
);

const pill = (label: string, color: string) => (
  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full"
    style={{ background: `${color}18`, color, border: `1px solid ${color}30` }}>
    {label}
  </span>
);

// ── Auth Modal ─────────────────────────────────────────────────────────────────
function AuthModal({ onSuccess, onClose }: { onSuccess: () => void; onClose: () => void }) {
  const [empId, setEmpId] = useState('');
  const [pass, setPass] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(''); setBusy(true);
    try {
      const fd = new FormData();
      fd.append('username', empId);
      fd.append('password', pass);
      await api.post('/auth/login', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      onSuccess();
    } catch {
      setErr('Invalid Employee ID or Password. Please try again.');
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-2xl overflow-hidden animate-rise"
        style={{ background: 'var(--s1)', border: '1px solid var(--b2)' }}>
        {/* Header */}
        <div className="px-6 py-5" style={{ background: 'linear-gradient(135deg,rgba(29,78,216,0.15),transparent)', borderBottom: '1px solid var(--b1)' }}>
          <div className="flex items-center gap-3 mb-1">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', boxShadow: '0 0 18px rgba(59,130,246,0.3)' }}>
              <Lock className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Authorisation Required</p>
              <p className="text-xs" style={{ color: 'var(--t2)' }}>Verify identity before generating document</p>
            </div>
            <button onClick={onClose} className="ml-auto opacity-40 hover:opacity-80 transition-opacity" style={{ color: 'var(--t1)' }}>
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <form onSubmit={submit} className="p-6 space-y-4">
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>
              Employee ID
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: 'var(--t2)' }} />
              <input type="text" required value={empId} onChange={e => setEmpId(e.target.value)}
                placeholder="e.g. WABAG-EMP-0042"
                className="w-full pl-10 pr-4 py-2.5 rounded-xl text-sm"
                style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>
              Password
            </label>
            <div className="relative">
              <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: 'var(--t2)' }} />
              <input type="password" required value={pass} onChange={e => setPass(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-10 pr-4 py-2.5 rounded-xl text-sm"
                style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
            </div>
          </div>
          {err && (
            <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs"
              style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
              <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" /> {err}
            </div>
          )}
          <button type="submit" disabled={busy || !empId || !pass}
            className="w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all"
            style={{
              background: 'linear-gradient(135deg,var(--em),#1d4ed8)',
              color: '#fff',
              opacity: busy || !empId || !pass ? 0.5 : 1,
              cursor: busy || !empId || !pass ? 'not-allowed' : 'pointer',
            }}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
            {busy ? 'Verifying…' : 'Verify & Unlock Generate'}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Vendor Card ────────────────────────────────────────────────────────────────
function VendorCard({
  vs, rank, selected, frozen,
  onSelect, onLock, onUnlock,
}: {
  vs: VendorScore; rank: number; selected: boolean; frozen: boolean;
  onSelect: () => void; onLock: () => void; onUnlock: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const m = vs.model;
  const scoreColor = vs.score >= 80 ? '#4ade80' : vs.score >= 65 ? 'var(--gold)' : 'var(--rose)';

  return (
    <div className="rounded-xl overflow-hidden transition-all duration-200"
      style={{
        border: `1.5px solid ${selected ? 'var(--em)' : 'var(--b1)'}`,
        background: selected ? 'rgba(59,130,246,0.05)' : 'var(--s3)',
      }}>
      {/* Main row */}
      <div className="flex items-center gap-4 p-4 cursor-pointer" onClick={() => !frozen && onSelect()}>
        {/* Rank badge */}
        <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 text-sm font-black"
          style={{ background: rank === 1 ? 'rgba(245,158,11,0.15)' : 'var(--s4)', color: rank === 1 ? 'var(--gold)' : 'var(--t2)', border: `1px solid ${rank === 1 ? 'rgba(245,158,11,0.35)' : 'var(--b1)'}` }}>
          {rank === 1 ? <Star className="w-4 h-4" style={{ color: 'var(--gold)' }} /> : rank}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold" style={{ color: selected ? 'var(--em-lt)' : 'var(--t0)', fontFamily: "'Space Grotesk',sans-serif" }}>
              {m.vendor}
            </span>
            {rank === 1 && pill('RECOMMENDED', 'var(--gold)')}
            {selected && pill('SELECTED', 'var(--em)')}
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-xs" style={{ color: 'var(--t2)' }}>
            <span className="font-mono font-bold" style={{ color: 'var(--t1)' }}>{m.modelNo}</span>
            <span>·</span><span>{m.country}</span>
            <span>·</span><span>{m.freqGHz} GHz</span>
            <span>·</span><span>Range: {m.rangeMaxM}m</span>
          </div>
        </div>

        {/* Score */}
        <div className="text-right flex-shrink-0">
          <div className="text-2xl font-black" style={{ color: scoreColor, fontFamily: "'Space Grotesk',sans-serif" }}>
            {vs.score}%
          </div>
          <div className="text-[10px]" style={{ color: 'var(--t2)' }}>match</div>
        </div>
      </div>

      {/* Score bar */}
      <div className="mx-4 mb-3 h-1.5 rounded-full" style={{ background: 'var(--s4)' }}>
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${vs.score}%`, background: scoreColor }} />
      </div>

      {/* Strengths / Gaps summary */}
      <div className="px-4 pb-3 grid grid-cols-2 gap-x-4 gap-y-0.5">
        {vs.strengths.slice(0, 2).map((s, i) => (
          <div key={i} className="flex items-center gap-1 text-[11px]" style={{ color: '#4ade80' }}>
            <CheckCircle2 className="w-3 h-3 flex-shrink-0" /><span className="truncate">{s}</span>
          </div>
        ))}
        {vs.gaps.slice(0, 2).map((g, i) => (
          <div key={i} className="flex items-center gap-1 text-[11px]" style={{ color: 'var(--rose)' }}>
            <AlertTriangle className="w-3 h-3 flex-shrink-0" /><span className="truncate">{g}</span>
          </div>
        ))}
      </div>

      {/* Action bar */}
      <div className="px-4 pb-4 flex items-center gap-2">
        <button onClick={() => setExpanded(x => !x)}
          className="text-xs font-semibold px-3 py-1.5 rounded-lg transition-all"
          style={{ background: 'var(--s2)', color: 'var(--em-lt)', border: '1px solid var(--b2)' }}>
          {expanded ? 'Hide Details' : 'View Details'}
        </button>
        <a href={m.catalogPageUrl} target="_blank" rel="noopener noreferrer"
          className="text-xs font-semibold px-3 py-1.5 rounded-lg transition-all flex items-center gap-1"
          style={{ background: 'var(--s2)', color: 'var(--t1)', border: '1px solid var(--b2)' }}
          onClick={e => e.stopPropagation()}>
          <ExternalLink className="w-3 h-3" /> Product Page
        </a>
        <a href={m.catalogPdfUrl} target="_blank" rel="noopener noreferrer"
          className="text-xs font-semibold px-3 py-1.5 rounded-lg transition-all flex items-center gap-1"
          style={{ background: 'rgba(59,130,246,0.08)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.2)' }}
          onClick={e => e.stopPropagation()}>
          <Download className="w-3 h-3" /> Datasheet PDF
        </a>
        {selected && (
          <button onClick={frozen ? onUnlock : onLock}
            className="ml-auto text-xs font-semibold px-3 py-1.5 rounded-lg flex items-center gap-1 transition-all"
            style={{
              background: frozen ? 'rgba(16,185,129,0.1)' : 'var(--s2)',
              color: frozen ? '#4ade80' : 'var(--t1)',
              border: `1px solid ${frozen ? 'rgba(16,185,129,0.3)' : 'var(--b2)'}`,
            }}>
            <Lock className="w-3 h-3" /> {frozen ? 'Model Locked ✓' : 'Lock Model'}
          </button>
        )}
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="px-4 pb-4 border-t" style={{ borderColor: 'var(--b1)' }}>
          <div className="pt-4 grid grid-cols-2 gap-3 text-xs">
            <div className="space-y-1.5">
              <div className="flex items-center gap-2" style={{ color: 'var(--t1)' }}>
                <Wifi className="w-3 h-3" style={{ color: 'var(--em)' }} />
                <span>{m.freqGHz} GHz · Range {m.rangeMaxM}m</span>
              </div>
              <div className="flex items-center gap-2" style={{ color: 'var(--t1)' }}>
                <Thermometer className="w-3 h-3" style={{ color: 'var(--rose)' }} />
                <span>Max {m.tempMaxC}°C</span>
              </div>
              <div className="flex items-center gap-2" style={{ color: 'var(--t1)' }}>
                <Gauge className="w-3 h-3" style={{ color: 'var(--gold)' }} />
                <span>Max {m.pressMaxBar} bar · ±{m.accuracyMM}mm</span>
              </div>
              <div className="flex items-center gap-2" style={{ color: 'var(--t1)' }}>
                <Shield className="w-3 h-3" style={{ color: '#a78bfa' }} />
                <span>{m.protection.join(' · ')}</span>
              </div>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Key Features</p>
              <div className="flex flex-wrap gap-1">
                {m.features.map(f => (
                  <span key={f} className="text-[10px] px-1.5 py-0.5 rounded"
                    style={{ background: 'var(--s4)', color: 'var(--t1)', border: '1px solid var(--b1)' }}>{f}</span>
                ))}
              </div>
              <p className="mt-3 text-[11px]" style={{ color: 'var(--t2)', lineHeight: '1.55' }}>{m.description}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Wizard ────────────────────────────────────────────────────────────────
export default function LTRadarWizard({ iodbFile, instrumentType, onBack, onStepChange }: Props) {
  const [step, setStep]       = useState(1);

  useEffect(() => { onStepChange?.(step); }, [step, onStepChange]);
  const [busy, setBusy]       = useState(false);
  const [error, setError]     = useState('');

  // Step 1 — tags
  const [tags, setTags]             = useState<ITag[]>([]);
  const [tagSearch, setTagSearch]   = useState('');
  const [selectedTag, setSelectedTag] = useState<ITag | null>(null);

  // Step 2 — input method
  const [inputMethod, setInputMethod] = useState<'ai' | 'manual' | null>(null);
  const [tenderFile, setTenderFile] = useState<File | null>(null);
  const [aiResults, setAiResults]   = useState<{ label: string; value: string; confidence: number }[]>([]);
  const [aiRunning, setAiRunning]   = useState(false);

  // Step 3 — header
  const [header, setHeader] = useState<Values>({
    client: '', consultant: '', project: '', doc_no: '', rev_no: '0',
    date: new Date().toISOString().split('T')[0], issued_for: 'IFA', location: '',
  });

  // Step 4 — specs
  const [specMeta, setSpecMeta] = useState<SpecMeta | null>(null);
  const [specValues, setSpecValues] = useState<Values>({});
  const [validErrs, setValidErrs] = useState<string[]>([]);

  // Step 5 — vendor
  const [vendorScores, setVendorScores]     = useState<VendorScore[] | null>(null);
  const [selectedVS, setSelectedVS]         = useState<VendorScore | null>(null);
  const [modelFrozen, setModelFrozen]       = useState(false);
  const [purchaseNotes, setPurchaseNotes]   = useState('');

  // Step 6 — auth
  const [showAuth, setShowAuth]   = useState(false);
  const [authed, setAuthed]       = useState(false);

  // Step 7 — generate
  const [downloadUrl, setDownloadUrl] = useState('');
  const [genDone, setGenDone]         = useState(false);

  // ── Load tags on mount ─────────────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      setBusy(true);
      try {
        const fd = new FormData();
        fd.append('iodb_file', iodbFile);
        // Backend /lt-radar/tags returns { tags: string[], count: number }
        const res = await api.post('/lt-radar/tags', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
        const rawTags: string[] = res.data.tags || [];
        // Wrap into ITag shape; iodb_data populated later on selection
        setTags(rawTags.map(t => ({ tag: t, iodb_data: {} })));
      } catch { setError('Failed to load tags from IODB'); }
      finally { setBusy(false); }
    })();
  }, [iodbFile]);

  // ── Load spec meta when tag selected ──────────────────────────────────────
  const loadSpecMeta = useCallback(async (tag: ITag) => {
    setBusy(true);
    try {
      // Step 1: get field definitions (GET, no auth body — uses cookie/bearer)
      const metaRes = await api.get('/lt-radar/specs-meta');
      const meta: SpecMeta = metaRes.data;
      setSpecMeta(meta);

      // Step 2: fetch IODB values for this tag
      const fd = new FormData();
      fd.append('iodb_file', iodbFile);
      fd.append('tag_no', tag.tag);
      const lookupRes = await api.post('/lt-radar/iodb-lookup', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      const iodbVals: Record<string, string> = lookupRes.data.values || {};

      const init: Values = {};
      meta.fields.forEach(f => { init[f.id] = f.fixed || iodbVals[f.id] || f.default || ''; });
      setSpecValues(init);

      // Store IODB data on the tag for preview
      setSelectedTag(prev => prev ? { ...prev, iodb_data: iodbVals } : prev);
    } catch { setError('Failed to load spec fields'); }
    finally { setBusy(false); }
  }, [iodbFile]);

  // Tag select: just store the tag, NO auto-fill here
  const handleTagSelect = (t: ITag) => { setSelectedTag(t); };

  // Called when user clicks Continue from Header → Specs
  const proceedToSpecs = async () => {
    if (!selectedTag) return;
    await loadSpecMeta(selectedTag);
    setStep(4);
  };

  // ── AI extraction ──────────────────────────────────────────────────────────
  const runAiExtract = async () => {
    if (!tenderFile || !specMeta) return;
    setAiRunning(true); setError('');
    try {
      const specLabels = specMeta.fields
        .filter(f => !f.fixed)
        .map(f => ({ id: f.id, label: f.label }));
      const fd = new FormData();
      fd.append('tender_file', tenderFile);
      fd.append('spec_labels', JSON.stringify(specLabels));
      const res = await api.post('/lt-radar/ai-extract', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      // Backend returns { fields: [{label, field_id, value, confidence, snippet}] }
      const extracted = (res.data.fields || []).map((f: { label: string; value: string; confidence: number }) => ({
        label: f.label, value: f.value, confidence: f.confidence,
      }));
      setAiResults(extracted);
    } catch { setError('AI extraction failed. Check the tender file and try again.'); }
    finally { setAiRunning(false); }
  };

  const applyAiResults = () => {
    const next = { ...specValues };
    aiResults.forEach(r => { if (r.value) next[r.label] = r.value; });
    setSpecValues(next);
    setStep(3);
  };

  // ── Vendor scoring ─────────────────────────────────────────────────────────
  const runVendorScore = () => {
    const scores = scoreVendors(specValues);
    setVendorScores(scores);
    if (scores.length > 0 && !selectedVS) setSelectedVS(scores[0]);
  };

  // ── Spec validation ────────────────────────────────────────────────────────
  const validateAndNext = () => {
    const errs = validate(specValues);
    setValidErrs(errs);
    if (errs.length === 0) { setStep(5); runVendorScore(); }
  };

  // ── Generate ───────────────────────────────────────────────────────────────
  const generate = async () => {
    setBusy(true); setError('');
    try {
      const payload: Values = {
        ...specValues,
        ...header,
        make: selectedVS?.model.vendor || '',
        model_no: selectedVS?.model.modelNo || '',
        notes: purchaseNotes,
      };
      const fd = new FormData();
      fd.append('values_json', JSON.stringify(payload));
      const res = await api.post('/lt-radar/generate', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      const url = URL.createObjectURL(blob);
      setDownloadUrl(url);
      setGenDone(true);
    } catch { setError('Generation failed. Please try again.'); }
    finally { setBusy(false); }
  };

  const filteredTags = tags.filter(t => t.tag.toLowerCase().includes(tagSearch.toLowerCase()));

  // ── STEP 1 — Tag Selection ─────────────────────────────────────────────────
  const renderStep1 = () => (
    <div className="space-y-4">
      {card(<>
        <div className="flex items-center gap-3 mb-5">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'var(--em-dim)', border: '1px solid var(--em)' }}>
            <Radio className="w-4 h-4" style={{ color: 'var(--em-lt)' }} />
          </div>
          <div>
            <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Select LT Tag</p>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>{instrumentType} · {tags.length} tags found in IODB</p>
          </div>
        </div>
        {busy && tags.length === 0 && (
          <div className="flex items-center gap-2 py-4" style={{ color: 'var(--t2)' }}>
            <Loader2 className="w-4 h-4 animate-spin" /><span className="text-sm">Loading tags…</span>
          </div>
        )}
        {tags.length > 0 && <>
          <div className="relative mb-3">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: 'var(--t2)' }} />
            <input value={tagSearch} onChange={e => setTagSearch(e.target.value)}
              placeholder="Filter tags…"
              className="w-full pl-9 pr-4 py-2 rounded-lg text-sm"
              style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
          </div>
          <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
            {filteredTags.map(t => (
              <button key={t.tag} onClick={() => handleTagSelect(t)}
                className="w-full text-left px-4 py-3 rounded-xl transition-all"
                style={{
                  background: selectedTag?.tag === t.tag ? 'var(--em-dim)' : 'var(--s3)',
                  border: `1px solid ${selectedTag?.tag === t.tag ? 'var(--em)' : 'var(--b1)'}`,
                  color: selectedTag?.tag === t.tag ? 'var(--em-lt)' : 'var(--t1)',
                }}>
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-sm">{t.tag}</span>
                  {selectedTag?.tag === t.tag && <CheckCircle2 className="w-4 h-4" style={{ color: 'var(--em)' }} />}
                </div>
                {Object.keys(t.iodb_data || {}).length > 0 && (
                  <p className="text-[11px] mt-0.5" style={{ color: 'var(--t2)' }}>
                    {Object.entries(t.iodb_data || {}).slice(0, 3).map(([k, v]) => `${k}: ${v}`).join(' · ')}
                  </p>
                )}
              </button>
            ))}
          </div>
        </>}
      </>)}

      <div className="flex gap-3">
        <button onClick={onBack} className="px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 transition-all"
          style={{ background: 'var(--s3)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
          <ChevronLeft className="w-4 h-4" /> Back to Type
        </button>
        <button onClick={() => setStep(2)} disabled={!selectedTag}
          className="flex-1 py-2.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all"
          style={{
            background: selectedTag ? 'linear-gradient(135deg,var(--em),#1d4ed8)' : 'var(--s3)',
            color: selectedTag ? '#fff' : 'var(--t2)',
            cursor: selectedTag ? 'pointer' : 'not-allowed',
          }}>
          Continue <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );

  // ── STEP 2 — Input Method ──────────────────────────────────────────────────
  const renderStep2 = () => (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {/* AI Extraction */}
        <button onClick={() => setInputMethod('ai')}
          className="rounded-2xl p-6 text-left transition-all duration-200"
          style={{
            background: inputMethod === 'ai' ? 'rgba(245,158,11,0.08)' : 'var(--s2)',
            border: `1.5px solid ${inputMethod === 'ai' ? 'var(--gold)' : 'var(--b1)'}`,
          }}>
          <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
            style={{ background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.25)' }}>
            <Sparkles className="w-5 h-5" style={{ color: 'var(--gold)' }} />
          </div>
          <p className="text-sm font-bold mb-1.5" style={{ color: 'var(--t0)', fontFamily: "'Space Grotesk',sans-serif" }}>
            AI Tender Extraction
          </p>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--t1)' }}>
            Upload a tender PDF — AI reads all spec clauses and pre-fills every field automatically.
          </p>
        </button>

        {/* Manual */}
        <button onClick={() => setInputMethod('manual')}
          className="rounded-2xl p-6 text-left transition-all duration-200"
          style={{
            background: inputMethod === 'manual' ? 'rgba(59,130,246,0.08)' : 'var(--s2)',
            border: `1.5px solid ${inputMethod === 'manual' ? 'var(--em)' : 'var(--b1)'}`,
          }}>
          <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
            style={{ background: 'var(--em-dim)', border: '1px solid rgba(59,130,246,0.25)' }}>
            <Settings className="w-5 h-5" style={{ color: 'var(--em-lt)' }} />
          </div>
          <p className="text-sm font-bold mb-1.5" style={{ color: 'var(--t0)', fontFamily: "'Space Grotesk',sans-serif" }}>
            Manual Entry
          </p>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--t1)' }}>
            IODB auto-fills process conditions. You manually select remaining spec values from validated dropdowns.
          </p>
        </button>
      </div>

      {/* AI sub-panel */}
      {inputMethod === 'ai' && (
        <div className="rounded-2xl p-5 space-y-4" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
          <p className="text-xs font-semibold" style={{ color: 'var(--t2)' }}>Upload Tender Document</p>
          <label className="flex items-center gap-3 rounded-xl px-4 py-3 cursor-pointer"
            style={{ background: tenderFile ? 'rgba(16,185,129,0.06)' : 'var(--s1)', border: `1.5px dashed ${tenderFile ? 'var(--em)' : 'var(--b2)'}` }}>
            {tenderFile
              ? <><CheckCircle2 className="w-4 h-4" style={{ color: 'var(--em)' }} /><span className="text-xs font-medium truncate" style={{ color: 'var(--em-lt)' }}>{tenderFile.name}</span></>
              : <><Upload className="w-4 h-4" style={{ color: 'var(--t2)' }} /><span className="text-xs" style={{ color: 'var(--t1)' }}>Upload PDF / DOCX tender document</span></>}
            <input type="file" accept=".pdf,.docx" className="hidden" onChange={e => setTenderFile(e.target.files?.[0] || null)} />
          </label>
          {tenderFile && (
            <button onClick={runAiExtract} disabled={aiRunning}
              className="w-full py-2.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
              style={{ background: 'linear-gradient(135deg,rgba(245,158,11,0.8),rgba(234,88,12,0.8))', color: '#fff' }}>
              {aiRunning ? <><Loader2 className="w-4 h-4 animate-spin" />Extracting…</> : <><Sparkles className="w-4 h-4" />Run AI Extraction</>}
            </button>
          )}
          {aiResults.length > 0 && (
            <>
              <div className="space-y-2 max-h-52 overflow-y-auto">
                {aiResults.map((r, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg"
                    style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
                    <span className="text-xs" style={{ color: 'var(--t2)' }}>{r.label}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold" style={{ color: 'var(--t0)' }}>{r.value}</span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full"
                        style={{ background: r.confidence > 0.75 ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)', color: r.confidence > 0.75 ? '#4ade80' : 'var(--gold)' }}>
                        {Math.round(r.confidence * 100)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
              <button onClick={applyAiResults}
                className="w-full py-2.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
                style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
                <CheckCircle2 className="w-4 h-4" /> Apply & Continue to Header
              </button>
            </>
          )}
        </div>
      )}

      <div className="flex gap-3">
        <button onClick={() => setStep(1)} className="px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2"
          style={{ background: 'var(--s3)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
          <ChevronLeft className="w-4 h-4" /> Back
        </button>
        {inputMethod === 'manual' && (
          <button onClick={() => setStep(3)}
            className="flex-1 py-2.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
            style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
            Enter Header Info <ChevronRight className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  );

  // ── STEP 3 — Header ────────────────────────────────────────────────────────
  const renderStep3 = () => {
    const hField = (key: keyof typeof header, label: string, placeholder = '') => (
      <div key={key}>
        <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>{label}</label>
        <input value={header[key]} onChange={e => setHeader(h => ({ ...h, [key]: e.target.value }))}
          placeholder={placeholder || label} className="w-full px-3 py-2.5 rounded-xl text-sm"
          style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
      </div>
    );
    return (
      <div className="space-y-4">
        {card(<>
          <div className="flex items-center gap-2 mb-5">
            <FileText className="w-4 h-4" style={{ color: 'var(--sky)' }} />
            <span className="text-sm font-bold" style={{ color: 'var(--sky)' }}>Project Header Information</span>
          </div>
          <div className="grid grid-cols-2 gap-4">
            {hField('client', 'Client', 'e.g. VA Tech WABAG')}
            {hField('consultant', 'Consultant / PMC')}
            {hField('project', 'Project Name')}
            {hField('doc_no', 'Document No.', 'e.g. WABAG-DS-LT-001')}
            {hField('location', 'Location / Plant')}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Issued For</label>
              <select value={header.issued_for} onChange={e => setHeader(h => ({ ...h, issued_for: e.target.value }))}
                className="w-full px-3 py-2.5 rounded-xl text-sm"
                style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }}>
                {['IFA', 'IFC', 'IFR', 'IFB', 'Approval'].map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Revision No.</label>
              <input value={header.rev_no} onChange={e => setHeader(h => ({ ...h, rev_no: e.target.value }))}
                placeholder="0" className="w-full px-3 py-2.5 rounded-xl text-sm"
                style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Date</label>
              <input type="date" value={header.date} onChange={e => setHeader(h => ({ ...h, date: e.target.value }))}
                className="w-full px-3 py-2.5 rounded-xl text-sm"
                style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
            </div>
          </div>
        </>)}
        <div className="flex gap-3">
          <button onClick={() => setStep(2)} className="px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2" style={{ background: 'var(--s3)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
            <ChevronLeft className="w-4 h-4" /> Back
          </button>
          <button onClick={proceedToSpecs} disabled={busy}
            className="flex-1 py-2.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
            style={{ background: busy ? 'var(--s3)' : 'linear-gradient(135deg,var(--em),#1d4ed8)', color: busy ? 'var(--t2)' : '#fff' }}>
            {busy ? <><Loader2 className="w-4 h-4 animate-spin" /> Loading specs…</> : <>Configure Specifications <ChevronRight className="w-4 h-4" /></>}
          </button>
        </div>
      </div>
    );
  };

  // ── STEP 4 — Specifications ────────────────────────────────────────────────
  const renderStep4 = () => {
    if (!specMeta) return <div className="text-sm" style={{ color: 'var(--t2)' }}>Loading spec fields…</div>;
    const sections: Record<string, typeof specMeta.fields> = {};
    specMeta.fields.forEach(f => { (sections[f.section] ??= []).push(f); });
    const sectionColors: Record<string, string> = {
      'GENERAL': 'var(--em)', 'PROCESS CONDITIONS': '#f97316', 'TRANSMITTER': 'var(--gold)',
      'OPTIONS': '#a78bfa', 'CERTIFICATION': '#4ade80', 'PURCHASE': 'var(--sky)',
    };
    return (
      <div className="space-y-4">
        {validErrs.length > 0 && (
          <div className="rounded-xl p-4 space-y-2" style={{ background: 'rgba(248,113,113,0.06)', border: '1px solid rgba(248,113,113,0.2)' }}>
            <p className="text-xs font-bold flex items-center gap-2" style={{ color: 'var(--rose)' }}>
              <AlertTriangle className="w-3.5 h-3.5" /> Validation Issues
            </p>
            {validErrs.map((e, i) => <p key={i} className="text-xs" style={{ color: 'var(--rose)' }}>• {e}</p>)}
          </div>
        )}

        {Object.entries(sections).map(([sec, fields]) => (
          card(
            <>
              <div className="flex items-center gap-2 mb-4">
                <div className="w-2 h-2 rounded-full" style={{ background: sectionColors[sec] || 'var(--em)' }} />
                <span className="text-xs font-bold uppercase tracking-wider" style={{ color: sectionColors[sec] || 'var(--em)' }}>{sec}</span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {fields.map(f => {
                  if (f.fixed) return (
                    <div key={f.id} className="rounded-lg px-3 py-2.5" style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
                      <p className="text-[10px]" style={{ color: 'var(--t2)' }}>{f.label}</p>
                      <p className="text-sm font-semibold mt-0.5" style={{ color: 'var(--em-lt)' }}>{f.fixed}</p>
                      <p className="text-[10px]" style={{ color: 'var(--t2)' }}>Fixed</p>
                    </div>
                  );
                  const isIodb = f.color === 'GREEN';
                  return (
                    <div key={f.id} className="rounded-lg px-3 py-2.5" style={{ background: 'var(--s3)', border: `1px solid ${isIodb ? 'rgba(74,222,128,0.2)' : 'var(--b1)'}` }}>
                      <p className="text-[10px] mb-1.5" style={{ color: 'var(--t2)' }}>
                        {f.label} {isIodb && <span style={{ color: '#4ade80' }}>● IODB</span>}
                      </p>
                      {f.options && f.options.length > 0 ? (
                        <select value={specValues[f.id] || ''} onChange={e => setSpecValues(v => ({ ...v, [f.id]: e.target.value }))}
                          className="w-full px-2 py-1.5 rounded-lg text-xs"
                          style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }}>
                          <option value="">Select…</option>
                          {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : (
                        <input value={specValues[f.id] || ''} onChange={e => setSpecValues(v => ({ ...v, [f.id]: e.target.value }))}
                          placeholder={f.default || f.label} readOnly={isIodb}
                          className="w-full px-2 py-1.5 rounded-lg text-xs"
                          style={{ background: isIodb ? 'rgba(74,222,128,0.04)' : 'var(--s1)', border: `1px solid ${isIodb ? 'rgba(74,222,128,0.2)' : 'var(--b2)'}`, color: isIodb ? '#4ade80' : 'var(--t0)', outline: 'none' }} />
                      )}
                    </div>
                  );
                })}
              </div>
            </>,
            'mb-0'
          )
        ))}

        <div className="flex gap-3">
          <button onClick={() => setStep(3)} className="px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2" style={{ background: 'var(--s3)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
            <ChevronLeft className="w-4 h-4" /> Back
          </button>
          <button onClick={validateAndNext}
            className="flex-1 py-2.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
            style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
            Vendor Recommendation <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  };

  // ── STEP 5 — Vendor ────────────────────────────────────────────────────────
  const renderStep5 = () => (
    <div className="space-y-4">
      {card(<>
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.25)' }}>
              <Star className="w-4 h-4" style={{ color: 'var(--gold)' }} />
            </div>
            <div>
              <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Vendor Recommendation</p>
              <p className="text-xs" style={{ color: 'var(--t2)' }}>Top 5 vendors ranked by spec compatibility</p>
            </div>
          </div>
          <button onClick={runVendorScore} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
            style={{ background: 'var(--s3)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
            <RefreshCw className="w-3 h-3" /> Re-score
          </button>
        </div>

        {vendorScores ? (
          <div className="space-y-3">
            {vendorScores.map((vs, i) => (
              <VendorCard key={vs.model.id} vs={vs} rank={i + 1}
                selected={selectedVS?.model.id === vs.model.id}
                frozen={modelFrozen && selectedVS?.model.id === vs.model.id}
                onSelect={() => { if (!modelFrozen) setSelectedVS(vs); }}
                onLock={() => setModelFrozen(true)}
                onUnlock={() => setModelFrozen(false)} />
            ))}
          </div>
        ) : (
          <div className="text-center py-8">
            <p className="text-sm mb-3" style={{ color: 'var(--t2)' }}>Click Re-score to run vendor analysis</p>
            <button onClick={runVendorScore}
              className="px-5 py-2.5 rounded-xl text-sm font-bold flex items-center gap-2 mx-auto"
              style={{ background: 'linear-gradient(135deg,rgba(245,158,11,0.8),rgba(234,88,12,0.8))', color: '#fff' }}>
              <Zap className="w-4 h-4" /> Run Analysis
            </button>
          </div>
        )}
      </>)}

      {card(<>
        <div className="flex items-center gap-2 mb-3">
          <Package className="w-4 h-4" style={{ color: 'var(--sky)' }} />
          <span className="text-sm font-bold" style={{ color: 'var(--sky)' }}>Purchase Notes</span>
        </div>
        <textarea value={purchaseNotes} onChange={e => setPurchaseNotes(e.target.value)}
          placeholder="Add any purchasing requirements, spares, accessories, or remarks…"
          rows={3} className="w-full rounded-xl resize-none text-sm p-3"
          style={{ background: 'var(--s3)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
      </>)}

      <div className="flex gap-3">
        <button onClick={() => setStep(4)} className="px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2" style={{ background: 'var(--s3)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
          <ChevronLeft className="w-4 h-4" /> Back
        </button>
        <button onClick={() => setStep(6)}
          className="flex-1 py-2.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
          style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
          Preview Datasheet <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );

  // ── STEP 6 — Preview + Auth ────────────────────────────────────────────────
  const renderStep6 = () => {
    const previewRows = [
      ['Tag Number', selectedTag?.tag || '—'],
      ['Instrument Type', instrumentType],
      ['Client', header.client || '—'],
      ['Project', header.project || '—'],
      ['Document No.', header.doc_no || '—'],
      ['Issued For', header.issued_for],
      ['Revision', header.rev_no],
      ...(specMeta?.fields.slice(0, 12).map(f => [f.label, specValues[f.id] || f.fixed || '—']) || []),
      ['Vendor (Make)', selectedVS?.model.vendor || '—'],
      ['Model No.', selectedVS?.model.modelNo || '—'],
    ];
    return (
      <div className="space-y-4">
        {card(<>
          <div className="flex items-center gap-2 mb-5">
            <Eye className="w-4 h-4" style={{ color: 'var(--violet)' }} />
            <span className="text-sm font-bold" style={{ color: 'var(--violet)' }}>Datasheet Preview</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {previewRows.map(([k, v], i) => (
              <div key={i} className="rounded-lg px-3 py-2" style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
                <p className="text-[10px]" style={{ color: 'var(--t2)' }}>{k}</p>
                <p className="text-xs font-semibold truncate mt-0.5" style={{ color: 'var(--t0)' }}>{v || '—'}</p>
              </div>
            ))}
          </div>
        </>)}

        {authed ? (
          <div className="rounded-xl p-4 flex items-center gap-3" style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.25)' }}>
            <CheckCircle2 className="w-5 h-5" style={{ color: '#4ade80' }} />
            <p className="text-sm font-semibold" style={{ color: '#4ade80' }}>Identity verified — ready to generate</p>
          </div>
        ) : (
          <div className="rounded-xl p-4 flex items-center justify-between gap-4" style={{ background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.2)' }}>
            <div>
              <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>Authorisation required</p>
              <p className="text-xs" style={{ color: 'var(--t2)' }}>Enter your Employee ID and password to unlock document generation</p>
            </div>
            <button onClick={() => setShowAuth(true)}
              className="px-5 py-2.5 rounded-xl text-sm font-bold whitespace-nowrap flex items-center gap-2"
              style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
              <Lock className="w-4 h-4" /> Verify Identity
            </button>
          </div>
        )}

        {/* Generation result — shown inline after generate is triggered */}
        {(busy || genDone) && card(
          <div className="text-center py-6">
            {busy && !genDone && (
              <>
                <Loader2 className="w-8 h-8 animate-spin mx-auto mb-3" style={{ color: 'var(--em-lt)' }} />
                <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Generating Datasheet…</p>
                <p className="text-xs mt-1" style={{ color: 'var(--t2)' }}>
                  {selectedTag?.tag} · {selectedVS?.model.vendor} {selectedVS?.model.modelNo}
                </p>
              </>
            )}
            {genDone && (
              <>
                <CheckCircle2 className="w-8 h-8 mx-auto mb-3" style={{ color: '#4ade80' }} />
                <p className="text-sm font-bold mb-1" style={{ color: '#4ade80' }}>Datasheet Ready!</p>
                <p className="text-xs mb-4" style={{ color: 'var(--t2)' }}>
                  {selectedTag?.tag} · {header.project || 'WABAG Project'} · Rev {header.rev_no}
                </p>
                <a href={downloadUrl} download={`${selectedTag?.tag}_LT_Radar_Datasheet.xlsx`}
                  className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-bold"
                  style={{ background: 'linear-gradient(135deg,#16a34a,#15803d)', color: '#fff' }}>
                  <Download className="w-4 h-4" /> Download XLSX
                </a>
              </>
            )}
          </div>
        )}

        <div className="flex gap-3">
          <button onClick={() => setStep(5)} disabled={busy} className="px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2" style={{ background: 'var(--s3)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
            <ChevronLeft className="w-4 h-4" /> Back
          </button>
          {!genDone && (
            <button onClick={generate} disabled={!authed || busy}
              className="flex-1 py-2.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2 transition-all"
              style={{
                background: authed && !busy ? 'linear-gradient(135deg,#16a34a,#15803d)' : 'var(--s3)',
                color: authed && !busy ? '#fff' : 'var(--t2)',
                cursor: authed && !busy ? 'pointer' : 'not-allowed',
              }}>
              {busy ? <><Loader2 className="w-4 h-4 animate-spin" />Generating…</> : <><Download className="w-4 h-4" />Generate Datasheet</>}
            </button>
          )}
          {genDone && (
            <button onClick={onBack} className="flex-1 py-2.5 rounded-xl text-sm font-semibold"
              style={{ background: 'var(--s3)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
              ← Back to Instrument Type
            </button>
          )}
        </div>

        {showAuth && (
          <AuthModal
            onSuccess={() => { setAuthed(true); setShowAuth(false); }}
            onClose={() => setShowAuth(false)} />
        )}
      </div>
    );
  };

  // ── Layout ─────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      {/* LT wizard step bar */}
      <div className="rounded-2xl px-5 py-4" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        <div className="flex items-center gap-2 mb-4">
          <Radio className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--em-lt)' }} />
          <span className="text-xs font-semibold" style={{ color: 'var(--em-lt)' }}>
            LT Non-Contact Radar
            {selectedTag ? ` · Tag: ${selectedTag.tag}` : ''}
          </span>
        </div>
        <LTStepBar current={step} />
      </div>

      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-sm"
          style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
          <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
          <button onClick={() => setError('')} className="ml-auto opacity-60 hover:opacity-100"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}

      {step === 1 && renderStep1()}
      {step === 2 && renderStep2()}
      {step === 3 && renderStep3()}
      {step === 4 && renderStep4()}
      {step === 5 && renderStep5()}
      {step === 6 && renderStep6()}
    </div>
  );
}
