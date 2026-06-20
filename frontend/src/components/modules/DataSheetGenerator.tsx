/* ─────────────────────────────────────────────────────────────────────────────
   Smart Datasheet Generator — 9-step engineering workflow
   1. IODB Upload & Type   2. Tag Selection   3. Template & Sheet
   4. Spec Input (AI/Manual)   5. Review   6. Approval & Lock
   7. Vendor Match   8. Vendor Select   9. Generate
───────────────────────────────────────────────────────────────────────────── */
import { useState, useEffect, useMemo, useRef } from 'react';
import {
  FileSpreadsheet, Upload, Search, CheckCircle2, ChevronRight,
  X, Download, Loader2, AlertTriangle, Sparkles, SlidersHorizontal,
  Lock, Star, Shield, Thermometer, Gauge, Wifi, ExternalLink, Eye,
  RefreshCw, FileText, ZapIcon, Package,
} from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import { scoreVendors, VendorScore, VendorModel } from '@/data/ltRadarVendors';

// ── Engineering Knowledge Base ─────────────────────────────────────────────────
const KB: Record<string, string[]> = {
  'Technology': ['Non Contact Radar', 'FMCW Radar', 'Pulse Radar', 'User Defined'],
  'Frequency': ['6 GHz', '26 GHz', '80 GHz', 'User Defined'],
  'Accuracy': ['±1 mm', '±2 mm', '±3 mm', '±5 mm', 'User Defined'],
  'Output Signal': ['4-20mA', '4-20mA HART', 'FOUNDATION Fieldbus', 'Profibus PA', 'User Defined'],
  'Power Supply': ['24 VDC', '24 VDC Loop Powered', '230 VAC', 'User Defined'],
  'Communication Protocol': ['HART', 'Profibus PA', 'FOUNDATION Fieldbus', 'Modbus', 'User Defined'],
  'Housing Material': ['Aluminium', 'SS304', 'SS316', 'SS316L', 'User Defined'],
  'Wetted Parts': ['PTFE', 'PEEK', 'SS316L', 'Hastelloy C', 'User Defined'],
  'IP Protection': ['IP65', 'IP66', 'IP67', 'IP68', 'User Defined'],
  'Area Certification': ['Safe Area', 'Ex ia IIC T4', 'Ex d IIC T6', 'IECEx', 'ATEX', 'User Defined'],
  'Process Connection': ['Threaded', 'Flanged', 'ANSI 150#', 'ANSI 300#', 'DIN PN16', 'DIN PN40', 'User Defined'],
  'Antenna Type': ['Horn Antenna', 'Lens Antenna', 'Rod Antenna', 'Planar Antenna', 'User Defined'],
};

// ── Types ──────────────────────────────────────────────────────────────────────
interface FieldSpec {
  section: string; label: string; row: number;
  value_cols: number[]; sub_labels: string[];
  source: 'iodb' | 'predefined'; defaults: string[]; source_note: string;
  color: string; input_type: 'iodb' | 'dropdown' | 'text'; options: string[]; mandatory: boolean;
}
interface DatasheetInfo { sheet: string; eg_sheet: string | null; title: string; }
interface ApprovalInfo { approved_by: string; employee_id: string; role: string; date: string; time_log: string; }
interface GenStatus { job_id: string; status: 'processing' | 'done' | 'error'; result?: { filename: string; tag_count: number; message: string }; error?: string; }

type SpecSource = 'iodb' | 'ai' | 'user';

// ── Outer Step Bar (9 steps) ───────────────────────────────────────────────────
const STEPS = ['IODB & Type', 'Tags', 'Template', 'Spec Input', 'Review', 'Approval', 'Vendor Match', 'Vendor Select', 'Generate'];

function StepBar({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {STEPS.map((label, i) => {
        const idx = i + 1; const done = idx < current; const active = idx === current;
        return (
          <div key={i} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1.5">
              <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300"
                style={{
                  background: done ? 'var(--em)' : active ? 'var(--em-dim)' : 'var(--s3)',
                  border: `1.5px solid ${done || active ? 'var(--em)' : 'var(--b2)'}`,
                  color: done ? '#fff' : active ? 'var(--em-lt)' : 'var(--t2)',
                }}>
                {done ? <CheckCircle2 className="w-4 h-4" /> : idx}
              </div>
              <span className="text-[9px] font-medium whitespace-nowrap" style={{ color: active ? 'var(--em-lt)' : done ? 'var(--t1)' : 'var(--t2)' }}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className="flex-1 h-px mx-1.5 mb-5" style={{ background: done ? 'var(--em)' : 'var(--b2)', transition: 'background 0.3s' }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Drop Zone ──────────────────────────────────────────────────────────────────
function DropZone({ file, onChange, accept, label }: { file: File | null; onChange: (f: File | null) => void; accept: string; label: string }) {
  return (
    <label className="flex items-center gap-3 rounded-xl cursor-pointer px-4 py-3 transition-all"
      style={{ background: file ? 'rgba(16,185,129,0.06)' : 'var(--s1)', border: `1.5px dashed ${file ? 'var(--em)' : 'var(--b2)'}` }}>
      {file
        ? <><CheckCircle2 className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--em)' }} /><span className="text-xs font-medium truncate" style={{ color: 'var(--em-lt)' }}>{file.name}</span><span className="ml-auto text-[10px]" style={{ color: 'var(--t2)' }}>Replace</span></>
        : <><Upload className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--t2)' }} /><span className="text-xs" style={{ color: 'var(--t1)' }}>{label}</span><span className="ml-auto text-[10px]" style={{ color: 'var(--t2)' }}>{accept}</span></>}
      <input type="file" accept={accept} className="hidden" onChange={e => onChange(e.target.files?.[0] || null)} />
    </label>
  );
}

// ── Card helper ────────────────────────────────────────────────────────────────
const card = (children: React.ReactNode, cls = '') => (
  <div className={`rounded-2xl p-6 ${cls}`} style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>{children}</div>
);

// ── Approval Modal ─────────────────────────────────────────────────────────────
function ApprovalModal({
  tags, instrumentType, onSuccess, onClose,
}: { tags: string[]; instrumentType: string; onSuccess: (info: ApprovalInfo) => void; onClose: () => void }) {
  const [empId, setEmpId] = useState('');
  const [pass, setPass] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(''); setBusy(true);
    try {
      const res = await api.post('/admin/approve', {
        employee_id: empId, password: pass,
        tag_numbers: tags, instrument_type: instrumentType,
      });
      onSuccess(res.data);
    } catch (e: any) { setErr(e?.response?.data?.detail || 'Invalid credentials'); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-2xl overflow-hidden" style={{ background: 'var(--s1)', border: '1px solid var(--b2)' }}>
        <div className="px-6 py-5" style={{ borderBottom: '1px solid var(--b1)' }}>
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', boxShadow: '0 0 16px rgba(59,130,246,0.3)' }}>
              <Lock className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Engineering Approval Required</p>
              <p className="text-xs" style={{ color: 'var(--t2)' }}>Locking specifications for {tags.length} tag(s)</p>
            </div>
            <button onClick={onClose} className="ml-auto opacity-40 hover:opacity-80" style={{ color: 'var(--t1)' }}><X className="w-4 h-4" /></button>
          </div>
        </div>
        <form onSubmit={submit} className="p-6 space-y-4">
          {err && <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs"
            style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
            <AlertTriangle className="w-3.5 h-3.5" /> {err}
          </div>}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Employee ID</label>
            <input type="text" required value={empId} onChange={e => setEmpId(e.target.value)} placeholder="e.g. WABAG-EMP-001"
              className="w-full px-3 py-2.5 rounded-xl text-sm"
              style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Password</label>
            <input type="password" required value={pass} onChange={e => setPass(e.target.value)} placeholder="••••••••"
              className="w-full px-3 py-2.5 rounded-xl text-sm"
              style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
          </div>
          <button type="submit" disabled={busy || !empId || !pass}
            className="w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
            style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff', opacity: busy || !empId || !pass ? 0.5 : 1, cursor: 'pointer' }}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
            {busy ? 'Verifying…' : 'Confirm & Lock Specifications'}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Vendor Card ────────────────────────────────────────────────────────────────
function VendorCard({ vs, rank, selected, onSelect }: {
  vs: VendorScore; rank: number; selected: boolean; onSelect: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const m: VendorModel = vs.model;
  const col = vs.score >= 80 ? '#4ade80' : vs.score >= 65 ? 'var(--gold)' : 'var(--rose)';

  return (
    <div className="rounded-xl overflow-hidden transition-all"
      style={{ border: `1.5px solid ${selected ? 'var(--em)' : 'var(--b1)'}`, background: selected ? 'rgba(59,130,246,0.05)' : 'var(--s3)' }}>
      <div className="flex items-center gap-4 p-4 cursor-pointer" onClick={onSelect}>
        <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 text-sm font-black"
          style={{ background: rank === 1 ? 'rgba(245,158,11,0.15)' : 'var(--s4)', color: rank === 1 ? 'var(--gold)' : 'var(--t2)', border: `1px solid ${rank === 1 ? 'rgba(245,158,11,0.35)' : 'var(--b1)'}` }}>
          {rank === 1 ? <Star className="w-4 h-4" style={{ color: 'var(--gold)' }} /> : rank}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold" style={{ color: selected ? 'var(--em-lt)' : 'var(--t0)' }}>{m.vendor}</span>
            {rank === 1 && <span className="text-[10px] px-1.5 py-0.5 rounded-full font-bold" style={{ background: 'rgba(245,158,11,0.15)', color: 'var(--gold)' }}>RECOMMENDED</span>}
            {selected && <span className="text-[10px] px-1.5 py-0.5 rounded-full font-bold" style={{ background: 'var(--em-dim)', color: 'var(--em-lt)' }}>SELECTED</span>}
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-xs" style={{ color: 'var(--t2)' }}>
            <span className="font-mono font-bold" style={{ color: 'var(--t1)' }}>{m.modelNo}</span>
            <span>·</span><span>{m.freqGHz} GHz</span><span>·</span><span>Range {m.rangeMaxM}m</span>
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <div className="text-2xl font-black" style={{ color: col }}>{vs.score}%</div>
          <div className="text-[10px]" style={{ color: 'var(--t2)' }}>match</div>
        </div>
      </div>

      <div className="mx-4 mb-3 h-1.5 rounded-full" style={{ background: 'var(--s4)' }}>
        <div className="h-full rounded-full transition-all duration-700" style={{ width: `${vs.score}%`, background: col }} />
      </div>

      <div className="px-4 pb-3 flex items-center gap-2 flex-wrap">
        <button onClick={e => { e.stopPropagation(); setExpanded(x => !x); }}
          className="text-xs px-3 py-1.5 rounded-lg flex items-center gap-1"
          style={{ background: 'var(--s2)', color: 'var(--em-lt)', border: '1px solid var(--b2)' }}>
          <Eye className="w-3 h-3" /> {expanded ? 'Hide' : 'All Specs'}
        </button>
        <a href={m.catalogPageUrl} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
          className="text-xs px-3 py-1.5 rounded-lg flex items-center gap-1"
          style={{ background: 'var(--s2)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
          <ExternalLink className="w-3 h-3" /> Product Page
        </a>
        <a href={m.catalogPdfUrl} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
          className="text-xs px-3 py-1.5 rounded-lg flex items-center gap-1"
          style={{ background: 'rgba(59,130,246,0.08)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.2)' }}>
          <Download className="w-3 h-3" /> Datasheet PDF
        </a>
      </div>

      {expanded && (
        <div className="px-4 pb-5 border-t space-y-3" style={{ borderColor: 'var(--b1)' }}>
          <div className="pt-4 grid grid-cols-2 gap-2 text-xs">
            {[
              ['Frequency', `${m.freqGHz} GHz`, <Wifi className="w-3 h-3" style={{ color: 'var(--em)' }} />],
              ['Max Range', `${m.rangeMaxM} m`, <Gauge className="w-3 h-3" style={{ color: 'var(--gold)' }} />],
              ['Max Temp', `${m.tempMaxC} °C`, <Thermometer className="w-3 h-3" style={{ color: 'var(--rose)' }} />],
              ['Max Pressure', `${m.pressMaxBar} bar`, <Gauge className="w-3 h-3" style={{ color: '#a78bfa' }} />],
              ['Accuracy', `±${m.accuracyMM} mm`, <CheckCircle2 className="w-3 h-3" style={{ color: '#4ade80' }} />],
              ['Country', m.country, <Shield className="w-3 h-3" style={{ color: 'var(--sky)' }} />],
            ].map(([lbl, val, ic]) => (
              <div key={lbl as string} className="rounded-lg px-3 py-2" style={{ background: 'var(--s4)' }}>
                <div className="flex items-center gap-1.5 mb-0.5" style={{ color: 'var(--t2)' }}>{ic}<span className="text-[10px]">{lbl}</span></div>
                <p className="font-bold" style={{ color: 'var(--t0)' }}>{val as string}</p>
              </div>
            ))}
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Outputs</p>
            <div className="flex flex-wrap gap-1">{m.outputs.map(o => <span key={o} className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(59,130,246,0.1)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.2)' }}>{o}</span>)}</div>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Protection</p>
            <div className="flex flex-wrap gap-1">{m.protection.map(p => <span key={p} className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(74,222,128,0.08)', color: '#4ade80', border: '1px solid rgba(74,222,128,0.2)' }}>{p}</span>)}</div>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Key Features</p>
            <div className="flex flex-wrap gap-1">{m.features.map(f => <span key={f} className="text-[10px] px-2 py-0.5 rounded" style={{ background: 'var(--s4)', color: 'var(--t1)', border: '1px solid var(--b1)' }}>{f}</span>)}</div>
          </div>
          <p className="text-[11px]" style={{ color: 'var(--t2)', lineHeight: '1.55' }}>{m.description}</p>
        </div>
      )}
    </div>
  );
}

// ── Spec Input Popup ───────────────────────────────────────────────────────────
function SpecPopup({ onClose, onConfirm, initial }: {
  onClose: () => void;
  onConfirm: (vals: Record<string, string>) => void;
  initial: Record<string, string>;
}) {
  const [vals, setVals] = useState<Record<string, string>>({ ...initial });
  const [customVals, setCustomVals] = useState<Record<string, string>>({});
  const set = (k: string, v: string) => setVals(p => ({ ...p, [k]: v }));
  const setCustom = (k: string, v: string) => setCustomVals(p => ({ ...p, [k]: v }));

  const resolve = (k: string) => vals[k] === 'User Defined' ? (customVals[k] || '') : (vals[k] || '');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-2xl rounded-2xl overflow-hidden max-h-[90vh] flex flex-col"
        style={{ background: 'var(--s1)', border: '1px solid var(--b2)' }}>
        <div className="px-6 py-5 flex items-center gap-3 flex-shrink-0" style={{ borderBottom: '1px solid var(--b1)' }}>
          <SlidersHorizontal className="w-4 h-4" style={{ color: 'var(--gold)' }} />
          <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Specification Entry</p>
          <p className="ml-1 text-xs" style={{ color: 'var(--t2)' }}>Select from predefined engineering values</p>
          <button onClick={onClose} className="ml-auto opacity-50 hover:opacity-90" style={{ color: 'var(--t1)' }}><X className="w-4 h-4" /></button>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="grid grid-cols-2 gap-4">
            {Object.entries(KB).map(([label, options]) => (
              <div key={label}>
                <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>{label}</label>
                <select value={vals[label] || ''} onChange={e => { set(label, e.target.value); }}
                  className="w-full px-3 py-2 rounded-xl text-sm"
                  style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }}>
                  <option value="">Select…</option>
                  {options.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
                {vals[label] === 'User Defined' && (
                  <input value={customVals[label] || ''} onChange={e => setCustom(label, e.target.value)}
                    placeholder={`Enter custom ${label.toLowerCase()}…`}
                    className="w-full mt-1.5 px-3 py-2 rounded-xl text-sm"
                    style={{ background: 'var(--s0)', border: '1px solid var(--gold)', color: 'var(--t0)', outline: 'none' }} />
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="px-6 pb-6 flex gap-3 flex-shrink-0" style={{ borderTop: '1px solid var(--b1)', paddingTop: '16px' }}>
          <Button variant="secondary" onClick={onClose} fullWidth>Cancel</Button>
          <Button onClick={() => {
            const final: Record<string, string> = {};
            Object.keys(KB).forEach(k => { final[k] = resolve(k); });
            onConfirm(final);
          }} fullWidth>
            <CheckCircle2 className="w-3.5 h-3.5" /> Apply Specifications
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Validation ─────────────────────────────────────────────────────────────────
function validateSpecs(vals: Record<string, string>): string[] {
  const errs: string[] = [];
  if (vals['Frequency'] === '80 GHz') {
    const ant = vals['Antenna Type'] || '';
    if (ant && !['Horn Antenna', 'Lens Antenna', 'Planar Antenna'].includes(ant))
      errs.push('Rule 1: 80 GHz frequency requires Horn, Lens, or Planar antenna');
  }
  const area = vals['Area Certification'] || '';
  if (area && area !== 'Safe Area' && !area.includes('User Defined') && !area.trim()) {
    errs.push('Rule 2: Hazardous area requires certification');
  }
  if (vals['Communication Protocol'] === 'HART') {
    const out = vals['Output Signal'] || '';
    if (out && !out.toLowerCase().includes('hart'))
      errs.push('Rule 3: HART protocol requires HART-capable output signal');
  }
  return errs;
}

// ── Main Component ─────────────────────────────────────────────────────────────
export default function DataSheetGenerator() {
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const clearError = () => setError('');

  // Step 1
  const [iodbFile, setIodbFile] = useState<File | null>(null);
  const [instrumentTypes, setInstrumentTypes] = useState<string[]>([]);
  const [selectedType, setSelectedType] = useState('');
  const [typeSearch, setTypeSearch] = useState('');

  // Step 2
  const [tags, setTags] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [tagSearch, setTagSearch] = useState('');

  // Step 3
  const [sopFile, setSopFile] = useState<File | null>(null);
  const [datasheets, setDatasheets] = useState<DatasheetInfo[]>([]);
  const [selectedDatasheet, setSelectedDatasheet] = useState('');
  const [fields, setFields] = useState<FieldSpec[]>([]);

  // Step 4 — spec input
  const [specMode, setSpecMode] = useState<'ai' | 'manual' | null>(null);
  const [tenderFiles, setTenderFiles] = useState<File[]>([]);
  const [aiResults, setAiResults] = useState<{ label: string; value: string; confidence: number }[]>([]);
  const [aiRunning, setAiRunning] = useState(false);
  const [showSpecPopup, setShowSpecPopup] = useState(false);
  const [kbValues, setKbValues] = useState<Record<string, string>>({});
  const [iodbGreen, setIodbGreen] = useState<Record<string, string>>({});
  const [iodbConfirmed, setIodbConfirmed] = useState(false);

  // Step 5 — review
  const [specValues, setSpecValues] = useState<Record<string, string>>({});
  const [specSources, setSpecSources] = useState<Record<string, SpecSource>>({});
  const [validErrs, setValidErrs] = useState<string[]>([]);
  const [overrides, setOverrides] = useState<Record<string, string[]>>({});

  // Step 6 — approval
  const [showApproval, setShowApproval] = useState(false);
  const [approval, setApproval] = useState<ApprovalInfo | null>(null);
  const [_locked, setLocked] = useState(false);

  // Step 7 — vendor matching
  const [vendorScores, setVendorScores] = useState<VendorScore[] | null>(null);

  // Step 8 — vendor selection
  const [selectedVS, setSelectedVS] = useState<VendorScore | null>(null);
  const [purchaseNotes, setPurchaseNotes] = useState('');

  // Step 9 — generate
  const [genStatus, setGenStatus] = useState<GenStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const filteredTypes = useMemo(() => instrumentTypes.filter(t => t.toLowerCase().includes(typeSearch.toLowerCase())), [instrumentTypes, typeSearch]);
  const filteredTags = useMemo(() => tags.filter(t => t.toLowerCase().includes(tagSearch.toLowerCase())), [tags, tagSearch]);
  const iodbFields = useMemo(() => fields.filter(f => f.input_type === 'iodb'), [fields]);
  const userFields = useMemo(() => fields.filter(f => f.input_type !== 'iodb'), [fields]);

  // ── Step 1: load instrument types ────────────────────────────────────────────
  const loadTypes = async () => {
    if (!iodbFile) return;
    setBusy(true); clearError();
    try {
      const fd = new FormData(); fd.append('iodb_file', iodbFile);
      const res = await api.post('/sop-datasheet/instrument-types', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setInstrumentTypes(res.data.instrument_types || []);
      setSelectedType('');
    } catch (e: any) { setError(e?.response?.data?.detail || 'Failed to read IODB'); }
    finally { setBusy(false); }
  };

  // ── Step 2: load tags for selected type ──────────────────────────────────────
  const loadTags = async (type: string) => {
    if (!iodbFile) return;
    setBusy(true); clearError();
    try {
      const fd = new FormData(); fd.append('iodb_file', iodbFile); fd.append('instrument_type', type);
      const res = await api.post('/sop-datasheet/tags', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setTags(res.data.tags || []); setSelectedTags([]);
    } catch (e: any) { setError(e?.response?.data?.detail || 'Failed to load tags'); }
    finally { setBusy(false); }
  };

  // ── Step 3: load datasheets from SOP ────────────────────────────────────────
  const loadDatasheets = async (file: File) => {
    setSopFile(file); setDatasheets([]); setSelectedDatasheet(''); setFields([]);
    setBusy(true); clearError();
    try {
      const fd = new FormData(); fd.append('sop_file', file);
      const res = await api.post('/sop-datasheet/datasheets', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setDatasheets(res.data.datasheets || []);
    } catch (e: any) { setError(e?.response?.data?.detail || 'Failed to read template'); }
    finally { setBusy(false); }
  };

  const loadFields = async (sheet: string) => {
    if (!sopFile) return;
    setSelectedDatasheet(sheet); setFields([]); setOverrides({});
    setBusy(true); clearError();
    try {
      const fd = new FormData(); fd.append('sop_file', sopFile); fd.append('datasheet_sheet', sheet);
      const res = await api.post('/sop-datasheet/fields', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      const f: FieldSpec[] = res.data.fields || [];
      setFields(f);
      const init: Record<string, string[]> = {};
      f.forEach(spec => { init[spec.label] = [...spec.defaults]; });
      setOverrides(init);
    } catch (e: any) { setError(e?.response?.data?.detail || 'Failed to load fields'); }
    finally { setBusy(false); }
  };

  // ── Step 4: IODB green-field pre-load ────────────────────────────────────────
  useEffect(() => {
    if (step !== 4 || !iodbFile || !selectedTags.length || iodbFields.length === 0) return;
    (async () => {
      try {
        const fd = new FormData();
        fd.append('iodb_file', iodbFile);
        fd.append('instrument_type', selectedType);
        fd.append('selected_tags', JSON.stringify(selectedTags));
        fd.append('sop_file', sopFile!);
        fd.append('datasheet_sheet', selectedDatasheet);
        fd.append('overrides', JSON.stringify({}));
        // We piggy-back on generate endpoint to preview iodb values
        // Instead, just mark green fields with placeholder labels
        const greens: Record<string, string> = {};
        iodbFields.forEach(f => { greens[f.label] = `[From IODB — ${selectedTags[0]}]`; });
        setIodbGreen(greens);
      } catch { /* non-critical */ }
    })();
  }, [step]);

  // ── AI extraction ─────────────────────────────────────────────────────────────
  const runAi = async () => {
    if (!tenderFiles.length) return;
    setAiRunning(true); clearError();
    try {
      const fd = new FormData();
      tenderFiles.forEach(f => fd.append('tender_file', f));
      fd.append('label', 'All specifications');
      const res = await api.post('/sop-datasheet/extract-spec', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      const extracted = Object.entries(KB).map(([label]) => ({
        label,
        value: res.data.extracted_value || '',
        confidence: res.data.confidence || 0,
      }));
      setAiResults(extracted);
    } catch (e: any) { setError(e?.response?.data?.detail || 'AI extraction failed'); }
    finally { setAiRunning(false); }
  };

  // ── Build review data ─────────────────────────────────────────────────────────
  const buildReview = () => {
    const vals: Record<string, string> = {};
    const srcs: Record<string, SpecSource> = {};

    // From IODB green fields
    iodbFields.forEach(f => {
      vals[f.label] = iodbGreen[f.label] || '—';
      srcs[f.label] = 'iodb';
    });

    // From AI results
    aiResults.forEach(r => {
      if (r.value) { vals[r.label] = r.value; srcs[r.label] = 'ai'; }
    });

    // From knowledge base (manual)
    Object.entries(kbValues).forEach(([k, v]) => {
      if (v) { vals[k] = v; srcs[k] = 'user'; }
    });

    // From template fields overrides
    userFields.forEach(f => {
      const v = overrides[f.label]?.filter(Boolean).join(' / ');
      if (v && !vals[f.label]) { vals[f.label] = v; srcs[f.label] = 'user'; }
    });

    setSpecValues(vals);
    setSpecSources(srcs);
    setStep(5);
  };

  // ── Approval ──────────────────────────────────────────────────────────────────
  const handleApproval = (info: ApprovalInfo) => {
    setApproval(info);
    setLocked(true);
    setShowApproval(false);
    const scores = scoreVendors(specValues);
    setVendorScores(scores);
    if (scores.length > 0) setSelectedVS(scores[0]);
    setStep(7);
  };

  // ── Generate ──────────────────────────────────────────────────────────────────
  const startGenerate = async () => {
    if (!sopFile || !iodbFile || !selectedDatasheet || !selectedTags.length) return;
    setBusy(true); setGenStatus(null); clearError();
    try {
      const out: Record<string, string[]> = { ...overrides };
      Object.entries(kbValues).forEach(([k, v]) => { if (v) out[k] = [v]; });
      aiResults.forEach(r => { if (r.value && !out[r.label]) out[r.label] = [r.value]; });
      if (selectedVS) {
        out['Manufacturer'] = [selectedVS.model.vendor];
        out['Model Number'] = [selectedVS.model.modelNo];
      }
      if (approval) {
        out['Approved By'] = [approval.approved_by];
        out['Employee ID'] = [approval.employee_id];
        out['Approval Date'] = [`${approval.date} ${approval.time_log}`];
      }
      if (purchaseNotes) out['Purchase Notes'] = [purchaseNotes];

      const fd = new FormData();
      fd.append('sop_file', sopFile);
      fd.append('iodb_file', iodbFile);
      fd.append('datasheet_sheet', selectedDatasheet);
      fd.append('instrument_type', selectedType);
      fd.append('selected_tags', JSON.stringify(selectedTags));
      fd.append('overrides', JSON.stringify(out));
      const res = await api.post('/sop-datasheet/generate', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setGenStatus({ job_id: res.data.job_id, status: 'processing' });
      pollRef.current = setInterval(async () => {
        try {
          const s = await api.get(`/sop-datasheet/generate/status/${res.data.job_id}`);
          setGenStatus(s.data);
          if (s.data.status !== 'processing') { clearInterval(pollRef.current!); setBusy(false); }
        } catch { /* keep polling */ }
      }, 3000);
    } catch (e: any) { setError(e?.response?.data?.detail || 'Generation failed'); setBusy(false); }
  };

  const downloadZip = async () => {
    try {
      const res = await api.get('/sop-datasheet/download', { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/zip' }));
      const a = document.createElement('a'); a.href = url; a.download = 'Datasheets.zip'; a.click();
      URL.revokeObjectURL(url);
    } catch { setError('Download failed'); }
  };

  // ── Render ─────────────────────────────────────────────────────────────────────
  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <PageHeader icon={FileSpreadsheet} title="Smart Datasheet Generator"
        description="IODB-assisted · AI spec extraction · Engineering approval workflow · SIMRE vendor matching" />

      <StepBar current={step} />
      {error && <Alert variant="error" onClose={clearError}>{error}</Alert>}

      {/* ── STEP 1: IODB Upload + Instrument Type ── */}
      {step === 1 && (
        <div className="space-y-4">
          {card(<>
            <div className="flex items-center gap-2 mb-4">
              <FileSpreadsheet className="w-4 h-4" style={{ color: 'var(--em)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Upload IODB</span>
            </div>
            <p className="text-xs mb-3" style={{ color: 'var(--t2)' }}>
              Only records with <strong>SIGNAL I/O TYPE = AI</strong> and <strong>SUB SYSTEM containing "-"</strong> are considered.
            </p>
            <DropZone file={iodbFile} onChange={f => { setIodbFile(f); setInstrumentTypes([]); setSelectedType(''); }} accept=".xlsx,.xls" label="Upload IODB spreadsheet (.xlsx / .xls)" />
            {iodbFile && instrumentTypes.length === 0 && (
              <Button onClick={loadTypes} loading={busy} fullWidth className="mt-3">
                <Search className="w-3.5 h-3.5" /> Analyse IODB
              </Button>
            )}
            {instrumentTypes.length > 0 && (
              <Alert variant="info" className="mt-3">Found <strong>{instrumentTypes.length}</strong> instrument types</Alert>
            )}
          </>)}

          {instrumentTypes.length > 0 && card(<>
            <div className="flex items-center gap-2 mb-3">
              <SlidersHorizontal className="w-4 h-4" style={{ color: 'var(--gold)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--gold)' }}>Select Instrument Type</span>
            </div>
            <div className="relative mb-3">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: 'var(--t2)' }} />
              <input value={typeSearch} onChange={e => setTypeSearch(e.target.value)} placeholder="Search types…"
                className="w-full pl-9 pr-4 py-2 rounded-lg text-sm"
                style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
            </div>
            <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
              {filteredTypes.map(t => (
                <button key={t} onClick={() => { setSelectedType(t); loadTags(t); }}
                  className="w-full text-left px-3 py-2.5 rounded-xl text-sm transition-all"
                  style={{ background: selectedType === t ? 'var(--em-dim)' : 'var(--s3)', border: `1px solid ${selectedType === t ? 'var(--em)' : 'var(--b1)'}`, color: selectedType === t ? 'var(--em-lt)' : 'var(--t1)' }}>
                  {t}
                </button>
              ))}
            </div>
            {selectedType && (
              <Button onClick={() => setStep(2)} className="mt-4 w-full">
                Continue to Tag Selection <ChevronRight className="w-3.5 h-3.5" />
              </Button>
            )}
          </>)}
        </div>
      )}

      {/* ── STEP 2: Tag Selection ── */}
      {step === 2 && (
        <div className="space-y-4">
          {card(<>
            <div className="flex items-center gap-2 mb-3">
              <Search className="w-4 h-4" style={{ color: 'var(--em)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>{selectedType} — Select Tags</span>
              <span className="ml-auto text-xs" style={{ color: 'var(--t2)' }}>{tags.length} tags</span>
            </div>

            <div className="flex items-center gap-2 mb-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3 h-3" style={{ color: 'var(--t2)' }} />
                <input value={tagSearch} onChange={e => setTagSearch(e.target.value)} placeholder="Filter tags…"
                  className="w-full pl-8 pr-3 py-1.5 rounded-lg text-xs"
                  style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
              </div>
              <button onClick={() => setSelectedTags(selectedTags.length === filteredTags.length ? [] : [...filteredTags])}
                className="text-xs font-semibold px-3 py-1.5 rounded-lg whitespace-nowrap"
                style={{ background: 'var(--s3)', color: 'var(--em-lt)', border: '1px solid var(--b2)' }}>
                {selectedTags.length === filteredTags.length ? 'Deselect All' : 'Select All'}
              </button>
            </div>

            <div className="space-y-1 max-h-64 overflow-y-auto pr-1">
              {filteredTags.map(tag => {
                const checked = selectedTags.includes(tag);
                return (
                  <label key={tag} className="flex items-center gap-2.5 px-3 py-2.5 rounded-xl cursor-pointer transition-all"
                    style={{ background: checked ? 'var(--em-dim)' : 'var(--s3)', border: `1px solid ${checked ? 'rgba(59,130,246,0.3)' : 'transparent'}` }}>
                    <input type="checkbox" checked={checked} onChange={() => setSelectedTags(s => checked ? s.filter(x => x !== tag) : [...s, tag])} className="accent-emerald-500 w-3.5 h-3.5" />
                    <span className="text-xs font-mono font-bold flex-1" style={{ color: checked ? 'var(--em-lt)' : 'var(--t1)' }}>{tag}</span>
                    {checked && <CheckCircle2 className="w-3.5 h-3.5" style={{ color: 'var(--em)' }} />}
                  </label>
                );
              })}
            </div>

            {selectedTags.length > 0 && (
              <div className="mt-2 px-3 py-2 rounded-lg text-xs font-semibold"
                style={{ background: 'var(--em-dim)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.2)' }}>
                {selectedTags.length} tag(s) selected: {selectedTags.join(', ')}
              </div>
            )}
          </>)}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(1)}>← Back</Button>
            <Button onClick={() => setStep(3)} disabled={selectedTags.length === 0} className="flex-1">
              Upload Template <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 3: Template Upload + Sheet Selection ── */}
      {step === 3 && (
        <div className="space-y-4">
          {card(<>
            <div className="flex items-center gap-2 mb-4">
              <FileText className="w-4 h-4" style={{ color: 'var(--gold)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--gold)' }}>Upload SOP Datasheet Template</span>
            </div>
            <p className="text-xs mb-3" style={{ color: 'var(--t2)' }}>
              Sheets named <strong>Cover Sheet, Index, Checklist, Spare</strong> are automatically ignored.
              All other sheets are analyzed for spec fields.
            </p>
            <DropZone file={sopFile} onChange={f => f && loadDatasheets(f)} accept=".xlsx,.xls" label="Upload SOP template workbook" />

            {datasheets.length > 0 && (
              <div className="mt-4 space-y-2">
                <p className="text-xs font-semibold mb-2" style={{ color: 'var(--t2)' }}>Select datasheet sheet:</p>
                {datasheets.map(d => (
                  <button key={d.sheet} onClick={() => loadFields(d.sheet)}
                    className="w-full text-left px-3 py-2.5 rounded-xl text-xs transition-all"
                    style={{ background: selectedDatasheet === d.sheet ? 'rgba(245,158,11,0.08)' : 'var(--s3)', border: `1px solid ${selectedDatasheet === d.sheet ? 'rgba(245,158,11,0.4)' : 'var(--b1)'}`, color: selectedDatasheet === d.sheet ? 'var(--gold)' : 'var(--t1)' }}>
                    <span className="font-semibold">{d.title || d.sheet}</span>
                    {d.eg_sheet && <span className="ml-2 opacity-60">{d.sheet}</span>}
                  </button>
                ))}
                {fields.length > 0 && (
                  <Alert variant="success">
                    Loaded <strong>{fields.length}</strong> spec fields — {iodbFields.length} auto (green), {userFields.length} manual
                  </Alert>
                )}
              </div>
            )}
          </>)}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(2)}>← Back</Button>
            <Button onClick={() => setStep(4)} disabled={!selectedDatasheet || fields.length === 0} className="flex-1">
              Select Input Mode <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 4: Spec Input Mode ── */}
      {step === 4 && (
        <div className="space-y-4">
          {/* IODB Green Fields */}
          {iodbFields.length > 0 && card(<>
            <div className="flex items-center gap-2 mb-3">
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#4ade80' }} />
              <span className="text-sm font-bold" style={{ color: '#4ade80' }}>IODB Auto-Populated Fields ({iodbFields.length})</span>
            </div>
            <p className="text-xs mb-3" style={{ color: 'var(--t2)' }}>
              The following fields will be automatically fetched from IODB for the selected tag(s).
              Review before mapping.
            </p>
            <div className="grid grid-cols-2 gap-2 max-h-40 overflow-y-auto">
              {iodbFields.map(f => (
                <div key={f.label} className="rounded-lg px-3 py-2" style={{ background: 'rgba(74,222,128,0.06)', border: '1px solid rgba(74,222,128,0.2)' }}>
                  <p className="text-[10px] mb-0.5" style={{ color: 'var(--t2)' }}>{f.section}</p>
                  <p className="text-xs font-semibold" style={{ color: '#4ade80' }}>{f.label}</p>
                  <p className="text-[10px] mt-0.5" style={{ color: 'rgba(74,222,128,0.6)' }}>● Auto from IODB</p>
                </div>
              ))}
            </div>
            {!iodbConfirmed && (
              <button onClick={() => setIodbConfirmed(true)}
                className="mt-3 w-full py-2 rounded-xl text-xs font-bold flex items-center justify-center gap-2"
                style={{ background: 'rgba(74,222,128,0.1)', color: '#4ade80', border: '1px solid rgba(74,222,128,0.3)' }}>
                <CheckCircle2 className="w-3.5 h-3.5" /> Confirm IODB Fields
              </button>
            )}
            {iodbConfirmed && (
              <div className="mt-3 flex items-center gap-2 text-xs font-semibold" style={{ color: '#4ade80' }}>
                <CheckCircle2 className="w-3.5 h-3.5" /> IODB fields confirmed
              </div>
            )}
          </>)}

          {/* Mode selection */}
          <div className="grid grid-cols-2 gap-4">
            <button onClick={() => setSpecMode('ai')}
              className="rounded-2xl p-6 text-left transition-all"
              style={{ background: specMode === 'ai' ? 'rgba(245,158,11,0.08)' : 'var(--s2)', border: `1.5px solid ${specMode === 'ai' ? 'var(--gold)' : 'var(--b1)'}` }}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
                style={{ background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.25)' }}>
                <Sparkles className="w-5 h-5" style={{ color: 'var(--gold)' }} />
              </div>
              <p className="text-sm font-bold mb-1.5" style={{ color: 'var(--t0)' }}>Smart AI Extraction</p>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--t1)' }}>
                Upload tender PDF, technical specs, scanned docs — AI reads text, tables, images and extracts all specifications.
              </p>
            </button>

            <button onClick={() => setSpecMode('manual')}
              className="rounded-2xl p-6 text-left transition-all"
              style={{ background: specMode === 'manual' ? 'rgba(59,130,246,0.08)' : 'var(--s2)', border: `1.5px solid ${specMode === 'manual' ? 'var(--em)' : 'var(--b1)'}` }}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
                style={{ background: 'var(--em-dim)', border: '1px solid rgba(59,130,246,0.25)' }}>
                <SlidersHorizontal className="w-5 h-5" style={{ color: 'var(--em-lt)' }} />
              </div>
              <p className="text-sm font-bold mb-1.5" style={{ color: 'var(--t0)' }}>Manual Entry</p>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--t1)' }}>
                Select from predefined engineering values. Spec popup opens automatically with validated dropdown options for all fields.
              </p>
            </button>
          </div>

          {/* AI mode sub-panel */}
          {specMode === 'ai' && (
            <div className="rounded-2xl p-5 space-y-4" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
              <p className="text-xs font-semibold" style={{ color: 'var(--t2)' }}>Upload Tender Documents (PDF, images, scanned docs)</p>
              <label className="flex items-center gap-3 rounded-xl px-4 py-3 cursor-pointer"
                style={{ background: 'var(--s1)', border: '1.5px dashed var(--b2)' }}>
                <Upload className="w-4 h-4" style={{ color: 'var(--t2)' }} />
                <span className="text-xs" style={{ color: 'var(--t1)' }}>
                  {tenderFiles.length > 0 ? `${tenderFiles.length} file(s) selected` : 'Upload Tender PDF / Technical Specification / Scanned Document'}
                </span>
                <input type="file" accept=".pdf,.docx,.txt,.jpg,.png" multiple className="hidden"
                  onChange={e => setTenderFiles(Array.from(e.target.files || []))} />
              </label>
              {tenderFiles.length > 0 && (
                <>
                  <div className="space-y-1">
                    {tenderFiles.map((f, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs" style={{ color: 'var(--em-lt)' }}>
                        <CheckCircle2 className="w-3 h-3" /> {f.name}
                      </div>
                    ))}
                  </div>
                  <button onClick={runAi} disabled={aiRunning}
                    className="w-full py-2.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
                    style={{ background: 'linear-gradient(135deg,rgba(245,158,11,0.8),rgba(234,88,12,0.8))', color: '#fff' }}>
                    {aiRunning ? <><Loader2 className="w-4 h-4 animate-spin" />Extracting…</> : <><Sparkles className="w-4 h-4" />Run AI Extraction</>}
                  </button>
                </>
              )}
              {aiResults.length > 0 && (
                <div className="space-y-2 max-h-52 overflow-y-auto">
                  <p className="text-xs font-semibold" style={{ color: 'var(--t2)' }}>Extracted Specifications:</p>
                  {aiResults.filter(r => r.value).map((r, i) => (
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
              )}
            </div>
          )}

          {/* Manual mode — spec popup trigger */}
          {specMode === 'manual' && (
            <div className="rounded-2xl p-5" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
              {Object.keys(kbValues).filter(k => kbValues[k]).length > 0 ? (
                <>
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-xs font-semibold" style={{ color: '#4ade80' }}>
                      <CheckCircle2 className="inline w-3 h-3 mr-1" />{Object.values(kbValues).filter(Boolean).length} specifications configured
                    </p>
                    <button onClick={() => setShowSpecPopup(true)}
                      className="text-xs px-3 py-1.5 rounded-lg"
                      style={{ background: 'var(--em-dim)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.3)' }}>
                      Edit Specs
                    </button>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {Object.entries(kbValues).filter(([_, v]) => v).map(([k, v]) => (
                      <div key={k} className="rounded-lg px-2 py-1.5" style={{ background: 'var(--s3)' }}>
                        <p className="text-[10px]" style={{ color: 'var(--t2)' }}>{k}</p>
                        <p className="text-xs font-semibold truncate" style={{ color: 'var(--t0)' }}>{v}</p>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="text-center py-4">
                  <p className="text-sm mb-3" style={{ color: 'var(--t2)' }}>
                    Specification popup will open with all predefined engineering values
                  </p>
                  <button onClick={() => setShowSpecPopup(true)}
                    className="px-5 py-2.5 rounded-xl text-sm font-bold flex items-center gap-2 mx-auto"
                    style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
                    <ZapIcon className="w-4 h-4" /> Open Specification Popup
                  </button>
                </div>
              )}
            </div>
          )}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(3)}>← Back</Button>
            <Button onClick={buildReview}
              disabled={specMode === null || (specMode === 'ai' && aiResults.length === 0) || (specMode === 'manual' && Object.values(kbValues).every(v => !v))}
              className="flex-1">
              Review Specifications <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 5: Review Specifications ── */}
      {step === 5 && (
        <div className="space-y-4">
          {card(<>
            <div className="flex items-center gap-2 mb-4">
              <Eye className="w-4 h-4" style={{ color: 'var(--sky)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--sky)' }}>Review Specifications</span>
              <span className="ml-auto text-xs" style={{ color: 'var(--t2)' }}>Source: IODB · AI · Manual</span>
            </div>

            {validErrs.length > 0 && (
              <div className="mb-4 rounded-xl p-3 space-y-1.5" style={{ background: 'rgba(248,113,113,0.06)', border: '1px solid rgba(248,113,113,0.2)' }}>
                <p className="text-xs font-bold flex items-center gap-1.5" style={{ color: 'var(--rose)' }}>
                  <AlertTriangle className="w-3.5 h-3.5" /> Validation Issues
                </p>
                {validErrs.map((e, i) => <p key={i} className="text-xs" style={{ color: 'var(--rose)' }}>• {e}</p>)}
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--b1)' }}>
                    {['Specification', 'Value', 'Source'].map(h => (
                      <th key={h} className="text-left px-3 py-2.5 font-semibold uppercase tracking-wider" style={{ color: 'var(--t2)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(specValues).map(([label, val], i) => {
                    const src = specSources[label] || 'user';
                    const srcColor = src === 'iodb' ? '#4ade80' : src === 'ai' ? 'var(--gold)' : 'var(--em-lt)';
                    const srcLabel = src === 'iodb' ? '● IODB' : src === 'ai' ? '✦ AI' : '✎ Manual';
                    return (
                      <tr key={label} style={{ borderBottom: i < Object.keys(specValues).length - 1 ? '1px solid var(--b1)' : 'none', background: i % 2 === 0 ? 'transparent' : 'var(--s3)' }}>
                        <td className="px-3 py-2.5 font-semibold" style={{ color: 'var(--t1)' }}>{label}</td>
                        <td className="px-3 py-2.5" style={{ color: 'var(--t0)' }}>
                          <input value={val} onChange={e => setSpecValues(v => ({ ...v, [label]: e.target.value }))}
                            className="w-full px-2 py-1 rounded-lg text-xs bg-transparent"
                            style={{ border: '1px solid transparent', color: 'var(--t0)', outline: 'none' }}
                            onFocus={e => e.currentTarget.style.borderColor = 'var(--b2)'}
                            onBlur={e => e.currentTarget.style.borderColor = 'transparent'} />
                        </td>
                        <td className="px-3 py-2.5">
                          <span className="text-[10px] font-bold" style={{ color: srcColor }}>{srcLabel}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>)}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(4)}>← Back</Button>
            <Button onClick={() => {
              const errs = validateSpecs(specValues);
              setValidErrs(errs);
              if (errs.length === 0) setShowApproval(true);
            }} className="flex-1">
              <Lock className="w-3.5 h-3.5" /> Engineering Approval <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 6: Locked confirmation ── */}
      {step === 6 && approval && (
        <div className="space-y-4">
          {card(<>
            <div className="flex items-center gap-3 mb-5">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center"
                style={{ background: 'rgba(74,222,128,0.12)', border: '1px solid rgba(74,222,128,0.3)' }}>
                <Lock className="w-5 h-5" style={{ color: '#4ade80' }} />
              </div>
              <div>
                <p className="text-base font-bold" style={{ color: '#4ade80' }}>Specifications Locked</p>
                <p className="text-xs" style={{ color: 'var(--t2)' }}>No further modifications are allowed after engineering approval</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {[
                ['Approved By', approval.approved_by],
                ['Employee ID', approval.employee_id],
                ['Role', approval.role],
                ['Date & Time', `${approval.date} ${approval.time_log}`],
                ['Tags', selectedTags.join(', ')],
                ['Instrument Type', selectedType],
              ].map(([k, v]) => (
                <div key={k} className="rounded-xl px-4 py-3" style={{ background: 'var(--s3)', border: '1px solid rgba(74,222,128,0.15)' }}>
                  <p className="text-[10px] mb-0.5" style={{ color: 'var(--t2)' }}>{k}</p>
                  <p className="text-sm font-semibold" style={{ color: '#4ade80' }}>{v}</p>
                </div>
              ))}
            </div>
          </>)}

          <div className="flex gap-3">
            <Button onClick={() => setStep(7)} className="w-full">
              SIMRE Vendor Matching <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 7: Vendor Matching ── */}
      {step === 7 && (
        <div className="space-y-4">
          {card(<>
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl flex items-center justify-center"
                  style={{ background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.25)' }}>
                  <Star className="w-4 h-4" style={{ color: 'var(--gold)' }} />
                </div>
                <div>
                  <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>SIMRE Vendor Matching</p>
                  <p className="text-xs" style={{ color: 'var(--t2)' }}>Locked specifications compared against vendor database</p>
                </div>
              </div>
              <button onClick={() => { const s = scoreVendors(specValues); setVendorScores(s); if (s.length > 0) setSelectedVS(s[0]); }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold"
                style={{ background: 'var(--s3)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
                <RefreshCw className="w-3 h-3" /> Re-score
              </button>
            </div>

            {vendorScores ? (
              <div className="space-y-3">
                {vendorScores.map((vs, i) => (
                  <VendorCard key={vs.model.id} vs={vs} rank={i + 1}
                    selected={selectedVS?.model.id === vs.model.id}
                    onSelect={() => setSelectedVS(vs)} />
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-sm mb-3" style={{ color: 'var(--t2)' }}>Specs locked — ready to run vendor analysis</p>
                <button onClick={() => { const s = scoreVendors(specValues); setVendorScores(s); if (s.length > 0) setSelectedVS(s[0]); }}
                  className="px-5 py-2.5 rounded-xl text-sm font-bold flex items-center gap-2 mx-auto"
                  style={{ background: 'linear-gradient(135deg,rgba(245,158,11,0.8),rgba(234,88,12,0.8))', color: '#fff' }}>
                  <Sparkles className="w-4 h-4" /> Run SIMRE Analysis
                </button>
              </div>
            )}
          </>)}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(6)}>← Back</Button>
            <Button onClick={() => setStep(8)} disabled={!selectedVS} className="flex-1">
              Select Vendor <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 8: Vendor Selection ── */}
      {step === 8 && selectedVS && (
        <div className="space-y-4">
          {card(<>
            <div className="flex items-center gap-2 mb-4">
              <Package className="w-4 h-4" style={{ color: 'var(--sky)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--sky)' }}>Vendor Selection</span>
            </div>

            <div className="rounded-xl p-4" style={{ background: 'rgba(59,130,246,0.05)', border: '1px solid rgba(59,130,246,0.2)' }}>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--t2)' }}>Manufacturer</p>
                  <p className="text-base font-black" style={{ color: 'var(--em-lt)' }}>{selectedVS.model.vendor}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider mb-1" style={{ color: 'var(--t2)' }}>Model Number</p>
                  <p className="text-base font-black font-mono" style={{ color: 'var(--em-lt)' }}>{selectedVS.model.modelNo}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--t2)' }}>
                <span>{selectedVS.model.freqGHz} GHz</span>
                <span>·</span><span>Range {selectedVS.model.rangeMaxM}m</span>
                <span>·</span><span>±{selectedVS.model.accuracyMM}mm</span>
                <span>·</span><span className="font-bold" style={{ color: '#4ade80' }}>{selectedVS.score}% match</span>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--t2)' }}>
                Choose a different vendor
              </label>
              {vendorScores && (
                <div className="space-y-2">
                  {vendorScores.map((vs, i) => (
                    <label key={vs.model.id} className="flex items-center gap-3 px-4 py-3 rounded-xl cursor-pointer transition-all"
                      style={{ background: selectedVS.model.id === vs.model.id ? 'var(--em-dim)' : 'var(--s3)', border: `1px solid ${selectedVS.model.id === vs.model.id ? 'var(--em)' : 'var(--b1)'}` }}>
                      <input type="radio" checked={selectedVS.model.id === vs.model.id} onChange={() => setSelectedVS(vs)} className="accent-emerald-500" />
                      <div className="flex-1">
                        <span className="text-sm font-bold" style={{ color: selectedVS.model.id === vs.model.id ? 'var(--em-lt)' : 'var(--t0)' }}>
                          {vs.model.vendor} — {vs.model.modelNo}
                        </span>
                        <span className="ml-2 text-xs" style={{ color: 'var(--t2)' }}>{vs.score}% match</span>
                      </div>
                      {i === 0 && <Star className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--gold)' }} />}
                    </label>
                  ))}
                </div>
              )}
            </div>
          </>)}

          {card(<>
            <div className="flex items-center gap-2 mb-3">
              <FileText className="w-4 h-4" style={{ color: 'var(--t1)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--t1)' }}>Purchase Notes</span>
            </div>
            <textarea value={purchaseNotes} onChange={e => setPurchaseNotes(e.target.value)}
              placeholder="Add purchasing requirements, spares, accessories, delivery terms, FAT requirements…"
              rows={3} className="w-full rounded-xl resize-none text-sm p-3"
              style={{ background: 'var(--s3)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
          </>)}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(7)}>← Back</Button>
            <Button onClick={() => setStep(9)} className="flex-1">
              Generate Datasheets <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 9: Generate ── */}
      {step === 9 && (
        <div className="space-y-4">
          {/* Traceability Summary */}
          {card(<>
            <div className="flex items-center gap-2 mb-4">
              <Shield className="w-4 h-4" style={{ color: 'var(--em)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Traceability Summary</span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              {[
                ['Tags', selectedTags.join(', ')],
                ['Instrument Type', selectedType],
                ['Approved By', approval?.approved_by || '—'],
                ['Employee ID', approval?.employee_id || '—'],
                ['Approval Date', approval ? `${approval.date} ${approval.time_log}` : '—'],
                ['Vendor', selectedVS?.model.vendor || '—'],
                ['Model No.', selectedVS?.model.modelNo || '—'],
                ['Match Score', selectedVS ? `${selectedVS.score}%` : '—'],
              ].map(([k, v]) => (
                <div key={k} className="rounded-lg px-3 py-2" style={{ background: 'var(--s3)' }}>
                  <p className="text-[10px]" style={{ color: 'var(--t2)' }}>{k}</p>
                  <p className="font-semibold truncate" style={{ color: 'var(--t0)' }}>{v}</p>
                </div>
              ))}
            </div>
          </>)}

          {/* Expected output */}
          <div className="rounded-xl p-4" style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
            <p className="text-xs font-semibold mb-2" style={{ color: 'var(--t2)' }}>Output files:</p>
            <div className="space-y-1">
              {selectedTags.map(t => (
                <p key={t} className="text-xs font-mono" style={{ color: 'var(--em-lt)' }}>📄 {t}.xlsx</p>
              ))}
              <p className="text-xs font-mono mt-2" style={{ color: 'var(--gold)' }}>📦 Datasheets.zip (all files)</p>
            </div>
          </div>

          {/* Generation status */}
          {card(
            <div className="text-center py-6">
              {genStatus?.status === 'processing' && (
                <>
                  <Loader2 className="w-10 h-10 animate-spin mx-auto mb-3" style={{ color: 'var(--em-lt)' }} />
                  <p className="text-base font-bold" style={{ color: 'var(--t0)' }}>Generating {selectedTags.length} datasheet(s)…</p>
                  <p className="text-xs mt-1" style={{ color: 'var(--t2)' }}>Filling templates with IODB + approved specs + vendor data</p>
                </>
              )}
              {genStatus?.status === 'done' && (
                <>
                  <CheckCircle2 className="w-10 h-10 mx-auto mb-3" style={{ color: '#4ade80' }} />
                  <p className="text-base font-bold mb-1" style={{ color: '#4ade80' }}>Datasheets Ready!</p>
                  <p className="text-xs mb-5" style={{ color: 'var(--t2)' }}>{genStatus.result?.message}</p>
                  <Button onClick={downloadZip} size="lg">
                    <Download className="w-4 h-4" /> Download ZIP
                  </Button>
                </>
              )}
              {genStatus?.status === 'error' && (
                <Alert variant="error">{genStatus.error || 'Generation failed'}</Alert>
              )}
              {!genStatus && (
                <Button onClick={startGenerate} loading={busy} size="lg" className="mx-auto">
                  <Download className="w-4 h-4" /> Generate {selectedTags.length} Datasheet(s)
                </Button>
              )}
            </div>
          )}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => { setStep(8); setGenStatus(null); if (pollRef.current) clearInterval(pollRef.current); setBusy(false); }}>← Back</Button>
            {genStatus?.status === 'done' && (
              <Button variant="ghost" className="flex-1" onClick={() => {
                setStep(1); setIodbFile(null); setSopFile(null); setInstrumentTypes([]); setSelectedType('');
                setTags([]); setSelectedTags([]); setDatasheets([]); setSelectedDatasheet(''); setFields([]);
                setSpecMode(null); setAiResults([]); setKbValues({}); setIodbGreen({}); setIodbConfirmed(false);
                setSpecValues({}); setSpecSources({}); setApproval(null); setLocked(false);
                setVendorScores(null); setSelectedVS(null); setGenStatus(null);
              }}>
                New Datasheet
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Modals */}
      {showSpecPopup && (
        <SpecPopup initial={kbValues} onClose={() => setShowSpecPopup(false)}
          onConfirm={(vals) => { setKbValues(vals); setShowSpecPopup(false); }} />
      )}
      {showApproval && (
        <ApprovalModal tags={selectedTags} instrumentType={selectedType}
          onSuccess={handleApproval} onClose={() => setShowApproval(false)} />
      )}
    </div>
  );
}
