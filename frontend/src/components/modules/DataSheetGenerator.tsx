/* ─────────────────────────────────────────────────────────────────────────────
   Smart Datasheet Generator — engineering workflow (steps 7-8, vendor match/select, are disconnected: VENDOR_STEPS_ENABLED)
   1. IODB Upload & Type   2. Tag Selection   3. Template & Sheet
   4. Spec Input (AI/Manual)   5. Review   6. Approval & Lock
   7. Vendor Match   8. Vendor Select   9. Generate
───────────────────────────────────────────────────────────────────────────── */
import { useState, useEffect, useMemo, useRef } from 'react';
import { useAuth } from '@/context/AuthContext';
import {
  FileSpreadsheet, Upload, Search, CheckCircle2, ChevronRight,
  X, Download, Loader2, AlertTriangle, Sparkles, SlidersHorizontal,
  Lock, Star, Shield, Thermometer, Gauge, Wifi, ExternalLink, Eye,
  RefreshCw, FileText, ZapIcon, Package, Send,
} from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import { scoreVendors, VendorScore, VendorModel } from '@/data/ltRadarVendors';
import { SharedIodbPanel } from '../ui/SharedIodb';

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
interface DatasheetInfo { sheet: string; eg_sheet: string | null; title: string; annexure_sheet?: string | null; annexure_capacity?: number; missing_annexures?: string[]; }
type GenFormat = 'INDIVIDUAL' | 'CONSOLIDATED';
/* Standard template library (backend: /sop-datasheet/library) */
interface LibField extends FieldSpec { key: string; scope: 'tag' | 'annexure2' | 'common'; origin: string; example: string[]; unit: string }
interface IodbGroup { instrument_type: string; tag_count: number; tags: string[]; duplicates: string[]; template_id: string | null;
  template_name: string | null; status: string; candidates: { id: string; name: string }[]; reason: string; matched_on: string; descriptions: string[] }
interface IodbAnalysis { groups: IodbGroup[]; rows: number; supported: number; unsupported: string[]; columns: Record<string, string | null>;
  hidden?: { instrument_type: string; tag_count: number }[]; hidden_tags?: number }
interface TemplateInfo { id: string; code: string; display_name: string; category: string; version: string; original_filename: string; title: string;
  sheets: { role: string; label: string; sheet: string; in_output: boolean }[]; annexure: { sheet: string; columns: number; capacity: number; generated: boolean };
  field_counts: { total: number; tag: number; common: number; vendor: number }; has_guide: boolean; output_filename: string }
const MATCH_BADGE: Record<string, [string, string]> = {
  exact: ['Exact', 'var(--ok)'], alias: ['Alias', 'var(--ok)'], keyword: ['Keywords - confirm', 'var(--gold)'],
  description: ['From description - confirm', 'var(--gold)'], ambiguous: ['Ambiguous', 'var(--rose)'], unmatched: ['No template', 'var(--rose)'], manual: ['Chosen by you', 'var(--t1)'],
};
const SRC_LABEL: Record<string, [string, string]> = {
  template: ['Engineering Guide', 'var(--t1)'], input: ['Manual', 'var(--em-lt)'], user: ['Manual', 'var(--em-lt)'], ai: ['AI', 'var(--gold)'],
  vendor: ['Vendor (later)', 'var(--t2)'], computed: ['Computed', 'var(--t1)'], optional: ['If tender asks', 'var(--gold)'],
};
/** Template fields are keyed "SECTION::Label": labels such as "Type" repeat in several sections of one datasheet. */
const fieldKey = (f: { section: string; label: string }) => `${f.section}::${f.label}`;
const keyLabel = (k: string) => k.includes('::') ? k.split('::').filter(Boolean).join(' · ') : k;
const FORMAT_INFO: Record<GenFormat, { label: string; desc: string }> = {
  CONSOLIDATED: { label: 'Consolidated Datasheet with Annexure', desc: 'One common instrument datasheet with a tag-wise engineering annexure (one row per selected tag).' },
  INDIVIDUAL: { label: 'Individual Datasheet for Each Tag', desc: 'A separate instrument datasheet for every selected tag, packaged as Datasheets.zip.' },
};
interface VIssue { severity: 'ERROR' | 'REVIEW' | 'INFO'; code: string; message: string; tag?: string; field?: string }
interface VResult { format: string; issues: VIssue[]; counts: { ERROR: number; REVIEW: number }; iodb_columns?: string[];
  annexure?: { sheet: string; capacity: number; rows: number; preview: Record<string, any>[];
    columns: { col: number; label: string; kind: string; hidden: boolean; iodb_column: string | null }[];
    missing?: { tag: string; col: number; label: string }[]; missing_total?: number; manual_filled?: number } }
interface ApprovalInfo { approved_by: string; employee_id: string; role: string; date: string; time_log: string; }
interface GenStatus { job_id: string; status: 'processing' | 'done' | 'error'; result?: { filename: string; tag_count: number; message: string; requested_count?: number; failed_tags?: { tag: string; reason: string }[]; format?: GenFormat }; error?: string; }

type SpecSource = 'iodb' | 'ai' | 'user' | string;

// ── Outer Step Bar (9 steps) ───────────────────────────────────────────────────
const ALL_STEPS = ['IODB & Type', 'Tags', 'Template', 'Spec Input', 'Review', 'Approval', 'Vendor Match', 'Vendor Select', 'Generate'];
// Steps 7 (Vendor Match) and 8 (Vendor Select) are disconnected from the workflow. Their code below is kept intact:
// set this to true to bring them back (the step bar, navigation and saved-session restore all follow it).
const VENDOR_STEPS_ENABLED = false;
const VENDOR_STEP_NOS = [7, 8];
const STEPS = ALL_STEPS.map((label, i) => ({ label, no: i + 1 })).filter((x) => VENDOR_STEPS_ENABLED || !VENDOR_STEP_NOS.includes(x.no));
const nextStep = (n: number) => (!VENDOR_STEPS_ENABLED && VENDOR_STEP_NOS.includes(n + 1) ? 9 : n + 1);
const prevStep = (n: number) => (!VENDOR_STEPS_ENABLED && VENDOR_STEP_NOS.includes(n - 1) ? 6 : n - 1);

function StepBar({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {STEPS.map(({ label, no }, i) => {
        const idx = i + 1; const done = no < current; const active = no === current;
        return (
          <div key={i} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1.5">
              <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all duration-300 flex-shrink-0"
                style={{
                  background: done ? 'var(--em)' : active ? 'var(--em-dim)' : 'var(--s3)',
                  border: `1.5px solid ${done || active ? 'var(--em)' : 'var(--b2)'}`,
                  color: done ? '#fff' : active ? 'var(--em-lt)' : 'var(--t2)',
                }}>
                {done ? <CheckCircle2 className="w-4 h-4" /> : idx}
              </div>
              <span className={`text-[9px] font-medium whitespace-nowrap ${active ? '' : 'hidden sm:block'}`} style={{ color: active ? 'var(--em-lt)' : done ? 'var(--t1)' : 'var(--t2)' }}>
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

// ── Card helper ────────────────────────────────────────────────────────────────
const card = (children: React.ReactNode, cls = '') => (
  <div className={`rounded-2xl p-4 sm:p-6 ${cls}`} style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>{children}</div>
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

// ── Raise Approval Request Modal ──────────────────────────────────────────────
function RaiseRequestModal({
  tags, instrumentType, specValues, extra,
  onSuccess, onClose,
}: {
  tags: string[];
  instrumentType: string;
  specValues: Record<string, string>;
  extra?: Record<string, any>;
  onSuccess: (reqId: number) => void;
  onClose: () => void;
}) {
  const { user } = useAuth();
  const empId = localStorage.getItem('user_employee_id') || '';
  const empName = localStorage.getItem('user_employee_name') || user?.username || '';

  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(''); setBusy(true);
    try {
      const res = await api.post('/approvals', {
        request_type: 'spec',
        submitted_by_name: empName,
        submitted_by_id: empId,
        submitter_notes: notes || null,
        tag_numbers: tags,
        instrument_type: instrumentType,
        payload: { ...(extra?.display || {}), ...Object.fromEntries(Object.entries(specValues).map(([k, v]) => [keyLabel(k), v])), __iez: extra?.machine },
      });
      onSuccess(res.data.id);
      onClose();
    } catch (ex: any) { setErr(ex?.response?.data?.detail || 'Failed to submit request'); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-2xl overflow-hidden"
        style={{ background: 'var(--s1)', border: '1px solid var(--b2)' }}>
        <div className="px-6 py-5 flex items-center gap-3" style={{ borderBottom: '1px solid var(--b1)' }}>
          <div className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.3)' }}>
            <Send className="w-4 h-4" style={{ color: 'var(--gold)' }} />
          </div>
          <div className="flex-1">
            <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Raise Approval Request</p>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>
              {tags.length} tag(s) — {instrumentType} · Sent to Lead Engineer queue
            </p>
          </div>
          <button onClick={onClose} className="opacity-40 hover:opacity-80" style={{ color: 'var(--t1)' }}>
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={submit} className="p-6 space-y-4">
          {err && (
            <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs"
              style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
              <AlertTriangle className="w-3.5 h-3.5" /> {err}
            </div>
          )}
          {/* Submitter identity — read-only, from session */}
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
            style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
            <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
              style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)' }}>
              {empName.charAt(0).toUpperCase()}
            </div>
            <div>
              <p className="text-xs font-semibold" style={{ color: 'var(--t0)' }}>{empName}</p>
              <p className="text-[10px]" style={{ color: 'var(--t2)' }}>{empId || 'No employee ID'}</p>
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Notes for Lead Engineer</label>
            <textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="Any context or clarifications for the reviewer…"
              className="w-full resize-none px-3 py-2.5 rounded-xl text-sm"
              style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
          </div>
          <div className="rounded-xl px-3 py-2.5 text-xs" style={{ background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)', color: 'var(--gold)' }}>
            The Lead Engineer will review your extracted specs and approve or reject the request. The OK button will enable once approved.
          </div>
          <button type="submit" disabled={busy}
            className="w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
            style={{ background: 'linear-gradient(135deg,var(--gold),#d97706)', color: '#000', opacity: busy ? 0.5 : 1, cursor: 'pointer' }}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            {busy ? 'Submitting…' : 'Send to Approval Queue'}
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

// ── Library templates: manual entry with dropdowns + checks ─────────────────────
const CUSTOM = 'Custom Value';
const isNA = (v: string) => /^\s*(n\.?a\.?|not applicable|-)\s*$/i.test(v);
/** Format and consistency checks of the common specifications ({field key: error}). Blank values are not errors here -
 *  they are flagged as "missing" in the review table and in the engineering validation. */
function libSpecErrors(fields: LibField[], vals: Record<string, string[]>): Record<string, string> {
  const errs: Record<string, string> = {};
  const live = fields.filter(f => f.scope === 'common' && f.origin !== 'computed');
  const valueOf = (f: LibField) => (vals[f.key] || f.defaults || []).map(v => String(v ?? '').trim());
  const find = (re: RegExp) => live.find(f => re.test(f.label.toLowerCase()));
  for (const f of live) {
    const vs = valueOf(f);
    const v = vs.filter(Boolean).join(' / ');
    const lab = f.label.toLowerCase().replace(/\s+/g, ' ');
    if (vs.some(x => x === CUSTOM)) { errs[f.key] = 'Enter the custom value.'; continue; }
    if (!v || isNA(v)) continue;
    if (/protection class|enclosure class|ingress|^enclosure$|ip rating/.test(lab) && !/\bIP\s?[0-6X][0-9X]\b|NEMA/i.test(v))
      errs[f.key] = 'Enter an IP rating, e.g. IP 66 / IP 67 / IP 68.';
    else if (/power supply|supply voltage/.test(lab) && !/\d\s*(-|–|to)?\s*\d*\s*V|loop\s*powered|battery/i.test(v))
      errs[f.key] = 'A power supply needs a voltage, e.g. 24 VDC or 230 VAC.';
    else if (/^output( signal)?$/.test(lab) && !/mA|HART|field\s*bus|profibus|modbus|pulse|relay|contact|digital|ethernet|profinet|SPDT|DPDT|\bNO\b|\bNC\b/i.test(v))
      errs[f.key] = 'Output should be a signal, e.g. 4-20 mA HART, Foundation Fieldbus, Profibus PA or a relay contact.';
    else if (/^(accuracy|repeatability)$/.test(lab) && !/\d/.test(v))
      errs[f.key] = `${f.label} needs a number, e.g. ± 0.075% of span or ± 2 mm.`;
    else if (/^(qty|quantity|spare qty|spare quantity)$/.test(lab) && !/^\d+(\.\d+)?\s*(nos?\.?|sets?|pcs)?$/i.test(v))
      errs[f.key] = 'Quantity must be a number.';
    else if (/frequency/.test(lab) && !/\d\s*(G|M|k)?Hz/i.test(v))
      errs[f.key] = 'Frequency needs a value with its unit, e.g. 80 GHz.';
    else if (/cable entry/.test(lab) && !/NPT|M\s?\d|PG\s?\d|"|inch|ET/i.test(v))
      errs[f.key] = 'Cable entry should be a thread size, e.g. 1/2" NPT(F) or M20 x 1.5.';
    else if (f.unit && !/\d/.test(v))
      errs[f.key] = `Enter a number in ${f.unit}.`;
  }
  // consistency rules (kept from the original specification entry)
  const proto = find(/communication|protocol/), out = find(/^output( signal)?$/);
  if (proto && out && !errs[out.key]) {
    const pv = valueOf(proto).join(' '), ov = valueOf(out).join(' ');
    if (/hart/i.test(pv) && ov && !/hart/i.test(ov)) errs[out.key] = 'The HART protocol needs a HART output (e.g. 4-20 mA HART).';
  }
  const freq = find(/frequency/), ant = find(/antenna/);
  if (freq && ant && !errs[ant.key]) {
    const fv = valueOf(freq).join(' '), av = valueOf(ant).join(' ');
    if (/80\s*GHz/i.test(fv) && av && !/horn|lens|planar/i.test(av)) errs[ant.key] = '80 GHz radar needs a horn, lens or planar antenna.';
  }
  const area = find(/area (certification|classification)|hazardous/);
  if (area && !errs[area.key]) {
    const v = valueOf(area).join(' ');
    if (/zone\s*[0-2]|hazard|div(ision)?\s*[12]/i.test(v) && !/ex\s*[a-z]|atex|iecex|ccoe|peso|\bfm\b|csa|certif/i.test(v))
      errs[area.key] = 'A hazardous area needs its certification (e.g. Ex ia IIC T4, ATEX, IECEx, CCOE).';
  }
  return errs;
}

/** One specification value: a dropdown of engineering options with "Custom Value" for anything else. */
function SpecInput({ field, value, onChange, error, placeholder, compact }: {
  field: LibField; value: string; onChange: (v: string) => void; error?: string; placeholder?: string; compact?: boolean;
}) {
  const opts = (field.options || []).filter(o => o !== CUSTOM);
  const inList = !value || opts.some(o => o === value);
  const [custom, setCustom] = useState(!inList || value === CUSTOM);
  const border = error ? 'var(--rose)' : 'var(--b2)';
  const cls = compact ? 'w-full px-2 py-1 rounded-md text-xs' : 'w-full px-3 py-2 rounded-xl text-sm';
  const style = { background: 'var(--s1)', border: `1px solid ${border}`, color: 'var(--t0)', outline: 'none' } as const;
  if (!opts.length) return <input value={value} placeholder={placeholder} onChange={e => onChange(e.target.value)} className={cls} style={style} />;
  return (
    <div className="space-y-1">
      <select value={custom ? CUSTOM : value} className={cls} style={style}
        onChange={e => { const v = e.target.value; if (v === CUSTOM) { setCustom(true); onChange(inList ? '' : value); } else { setCustom(false); onChange(v); } }}>
        <option value="">Select…</option>
        {opts.map(o => <option key={o} value={o}>{o.length > 90 ? `${o.slice(0, 88)}…` : o}</option>)}
        <option value={CUSTOM}>Custom Value…</option>
      </select>
      {custom && <input value={value === CUSTOM ? '' : value} autoFocus placeholder={`Enter ${field.label.toLowerCase()}…`}
        onChange={e => onChange(e.target.value)} className={cls} style={{ ...style, border: `1px solid ${error ? 'var(--rose)' : 'var(--gold)'}` }} />}
    </div>
  );
}

function LibSpecPopup({ fields, initial, onClose, onConfirm, title }: {
  fields: LibField[]; initial: Record<string, string[]>; title: string;
  onClose: () => void; onConfirm: (vals: Record<string, string[]>, changed: string[]) => void;
}) {
  const live = fields.filter(f => f.scope === 'common' && f.origin !== 'computed');
  const [vals, setVals] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(live.map(f => [f.key, [...(initial[f.key] || f.defaults).map(v => String(v ?? ''))]])));
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const errs = useMemo(() => libSpecErrors(live, vals), [vals]); // eslint-disable-line react-hooks/exhaustive-deps
  const nErr = Object.keys(errs).length;
  const set = (k: string, i: number, v: string) => {
    setVals(p => { const a = [...(p[k] || [])]; a[i] = v; return { ...p, [k]: a }; });
    setTouched(t => new Set(t).add(k));
  };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-3xl rounded-2xl overflow-hidden max-h-[92vh] flex flex-col" style={{ background: 'var(--s1)', border: '1px solid var(--b2)' }}>
        <div className="px-5 py-4 flex items-center gap-3 flex-shrink-0" style={{ borderBottom: '1px solid var(--b1)' }}>
          <SlidersHorizontal className="w-4 h-4" style={{ color: 'var(--gold)' }} />
          <div className="min-w-0">
            <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Specification Entry - {title}</p>
            <p className="text-[11px]" style={{ color: 'var(--t2)' }}>Select from the engineering values or choose "Custom Value". Tag-wise data comes from the IODB (Annexure-I).</p>
          </div>
          <button onClick={onClose} className="ml-auto opacity-50 hover:opacity-90" style={{ color: 'var(--t1)' }} aria-label="Close"><X className="w-4 h-4" /></button>
        </div>
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {[...new Set(live.map(f => f.section))].map(sec => (
            <div key={sec}>
              <p className="eyebrow mb-2">{sec}</p>
              <div className="grid sm:grid-cols-2 gap-x-4 gap-y-3">
                {live.filter(f => f.section === sec).map(f => (
                  <div key={f.key}>
                    <label className="block text-[11px] font-semibold mb-1" style={{ color: 'var(--t1)' }}>
                      {f.label}{f.origin === 'vendor' && <span className="font-normal" style={{ color: 'var(--t2)' }}> · vendor (optional now)</span>}
                      {f.origin === 'optional' && <span className="font-normal" style={{ color: 'var(--gold)' }}> · only if the tender asks</span>}
                    </label>
                    {f.value_cols.length > 1
                      ? <div className="grid grid-cols-3 gap-1">{f.value_cols.map((_, i) => (
                          <input key={i} value={vals[f.key]?.[i] ?? ''} placeholder={f.sub_labels[i] || ''} onChange={e => set(f.key, i, e.target.value)}
                            className="w-full px-2 py-2 rounded-xl text-xs" style={{ background: 'var(--s1)', border: `1px solid ${errs[f.key] ? 'var(--rose)' : 'var(--b2)'}`, color: 'var(--t0)', outline: 'none' }} />))}</div>
                      : <SpecInput field={f} value={vals[f.key]?.[0] ?? ''} error={errs[f.key]} onChange={v => set(f.key, 0, v)}
                          placeholder={f.origin === 'vendor' && f.example[0] ? `e.g. ${f.example[0]}` : ''} />}
                    {errs[f.key] && <p className="text-[10px] mt-0.5" style={{ color: 'var(--rose)' }}><AlertTriangle className="inline w-2.5 h-2.5 mr-0.5" />{errs[f.key]}</p>}
                  </div>))}
              </div>
            </div>))}
        </div>
        <div className="px-5 py-4 flex flex-wrap items-center gap-3 flex-shrink-0" style={{ borderTop: '1px solid var(--b1)' }}>
          {nErr > 0 && <p className="text-xs w-full" style={{ color: 'var(--rose)' }}>{nErr} value(s) need correcting before they can be applied.</p>}
          <Button variant="secondary" onClick={onClose} className="flex-1">Cancel</Button>
          <Button disabled={nErr > 0} onClick={() => onConfirm(vals, [...touched])} className="flex-1">
            <CheckCircle2 className="w-3.5 h-3.5" /> Apply Specifications
          </Button>
        </div>
      </div>
    </div>
  );
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
  const [, setDatasheets] = useState<DatasheetInfo[]>([]);
  const [selectedDatasheet, setSelectedDatasheet] = useState('');
  const [fields, setFields] = useState<FieldSpec[]>([]);

  // Template library
  const [iodbAnalysis, setIodbAnalysis] = useState<IodbAnalysis | null>(null);
  const [typeTemplate, setTypeTemplate] = useState<Record<string, string>>({});      // user corrections: type -> template id
  const [libraryList, setLibraryList] = useState<{ id: string; display_name: string }[]>([]);
  const [templateId, setTemplateId] = useState('');
  const [templateInfo, setTemplateInfo] = useState<TemplateInfo | null>(null);
  const [headerFields, setHeaderFields] = useState<Record<string, string>>({});
  const [header, setHeader] = useState<Record<string, string>>({});
  const [fieldScope, setFieldScope] = useState<Record<string, 'tag' | 'common'>>({});
  const [aiConf, setAiConf] = useState<Record<string, number>>({});

  // Step 4 — spec input
  const [specMode, setSpecMode] = useState<'ai' | 'manual' | null>(null);
  const [tenderFiles, setTenderFiles] = useState<File[]>([]);
  const [aiResults, setAiResults] = useState<{ label: string; value: string; confidence: number; snippet?: string }[]>([]);
  // Generation format + consolidated annexure mapping + the exact package that was approved
  const [genFormat, setGenFormat] = useState<GenFormat | ''>('');
  const [annexMap, setAnnexMap] = useState<Record<string, string>>({});
  const [validation, setValidation] = useState<VResult | null>(null);
  const [validating, setValidating] = useState(false);
  const [requestedFp, setRequestedFp] = useState<string | null>(null);
  const [approvedFp, setApprovedFp] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [aiRunning, setAiRunning] = useState(false);
  const [showSpecPopup, setShowSpecPopup] = useState(false);
  const [kbValues, setKbValues] = useState<Record<string, string>>({});
  const [iodbGreen, setIodbGreen] = useState<Record<string, string>>({});
  const [iodbConfirmed, setIodbConfirmed] = useState(false);

  // Step 5 — review
  const [specValues, setSpecValues] = useState<Record<string, string>>({});
  const [specSources, setSpecSources] = useState<Record<string, SpecSource>>({});
  const [validErrs, setValidErrs] = useState<string[]>([]);
  const [showLibPopup, setShowLibPopup] = useState(false);
  const [annexValues, setAnnexValues] = useState<Record<string, Record<string, string>>>({});
  const [overrides, setOverrides] = useState<Record<string, string[]>>({});

  // Step 6 — approval
  const [showApproval, setShowApproval] = useState(false);
  const [approval, setApproval] = useState<ApprovalInfo | null>(null);
  const [_locked, setLocked] = useState(false);
  // Raise-request flow
  const [showRaiseModal, setShowRaiseModal] = useState(false);
  const [pendingReqId, setPendingReqId] = useState<number | null>(null);
  const [reqStatus, setReqStatus] = useState<'idle' | 'pending' | 'approved' | 'rejected'>('idle');
  const reqPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Step 7 — vendor matching
  const [vendorScores, setVendorScores] = useState<VendorScore[] | null>(null);

  // Step 8 — vendor selection
  const [selectedVS, setSelectedVS] = useState<VendorScore | null>(null);
  const [purchaseNotes, setPurchaseNotes] = useState('');

  // Step 9 — generate
  const [genStatus, setGenStatus] = useState<GenStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Restore persisted state on mount
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem('datasheet_state');
      if (saved) {
        const s = JSON.parse(saved);
        if (s.step) setStep(!VENDOR_STEPS_ENABLED && VENDOR_STEP_NOS.includes(s.step) ? 9 : s.step);
        if (s.instrumentTypes) setInstrumentTypes(s.instrumentTypes);
        if (s.selectedType) setSelectedType(s.selectedType);
        if (s.tags) setTags(s.tags);
        if (s.selectedTags) setSelectedTags(s.selectedTags);
        if (s.selectedDatasheet) setSelectedDatasheet(s.selectedDatasheet);
        if (s.fields) setFields(s.fields);
        if (s.specValues) setSpecValues(s.specValues);
        if (s.specSources) setSpecSources(s.specSources);
        if (s.kbValues) setKbValues(s.kbValues);
        if (s.iodbGreen) setIodbGreen(s.iodbGreen);
        if (s.iodbConfirmed) setIodbConfirmed(s.iodbConfirmed);
        if (s.overrides) setOverrides(s.overrides);
        if (s.vendorScores) setVendorScores(s.vendorScores);
        if (s.selectedVS) setSelectedVS(s.selectedVS);
        if (s.approval) setApproval(s.approval);
        if (s.pendingReqId) setPendingReqId(s.pendingReqId);
        if (s.reqStatus) setReqStatus(s.reqStatus);
        // A 'processing' job can't be resumed after a reload, so only restore finished ones.
        if (s.genStatus && s.genStatus.status !== 'processing') setGenStatus(s.genStatus);
        if (s.genFormat) setGenFormat(s.genFormat);
        if (s.annexMap) setAnnexMap(s.annexMap);
        if (s.aiResults) setAiResults(s.aiResults);
        if (s.requestedFp) setRequestedFp(s.requestedFp);
        if (s.approvedFp) setApprovedFp(s.approvedFp);
        if (s.templateId) setTemplateId(s.templateId);
        if (s.templateInfo) setTemplateInfo(s.templateInfo);
        if (s.headerFields) setHeaderFields(s.headerFields);
        if (s.header) setHeader(s.header);
        if (s.fieldScope) setFieldScope(s.fieldScope);
        if (s.annexValues) setAnnexValues(s.annexValues);
        if (s.aiConf) setAiConf(s.aiConf);
        if (s.typeTemplate) setTypeTemplate(s.typeTemplate);
      }
    } catch { /* ignore */ }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (reqPollRef.current) clearInterval(reqPollRef.current);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Persist state to sessionStorage on every change
  useEffect(() => {
    if (step === 1 && instrumentTypes.length === 0) return; // nothing worth saving yet
    try {
      sessionStorage.setItem('datasheet_state', JSON.stringify({
        step, instrumentTypes, selectedType, tags, selectedTags,
        selectedDatasheet, fields, specValues, specSources,
        kbValues, iodbGreen, iodbConfirmed, overrides,
        vendorScores, selectedVS, approval, pendingReqId, reqStatus, genStatus,
        genFormat, annexMap, aiResults, requestedFp, approvedFp,
        templateId, templateInfo, headerFields, header, fieldScope, aiConf, typeTemplate, annexValues,
      }));
    } catch { /* ignore */ }
  }, [step, instrumentTypes, selectedType, tags, selectedTags, selectedDatasheet,
      fields, specValues, specSources, kbValues, iodbGreen, iodbConfirmed, overrides,
      vendorScores, selectedVS, approval, pendingReqId, reqStatus, genStatus,
      genFormat, annexMap, aiResults, requestedFp, approvedFp,
      templateId, templateInfo, headerFields, header, fieldScope, aiConf, typeTemplate, annexValues]);

  const filteredTags = useMemo(() => tags.filter(t => t.toLowerCase().includes(tagSearch.toLowerCase())), [tags, tagSearch]);
  const iodbFields = useMemo(() => fields.filter(f => f.input_type === 'iodb'), [fields]);
  const userFields = useMemo(() => fields.filter(f => f.input_type !== 'iodb'), [fields]);

  // ── Template library ─────────────────────────────────────────────────────────
  useEffect(() => {
    api.get('/sop-datasheet/library').then(r => setLibraryList((r.data.templates || []).map((t: any) => ({ id: t.id, display_name: t.display_name })))).catch(() => {});
  }, []);
  const analyseIodb = async () => {
    if (!iodbFile) return;
    if (!libraryList.length) api.get('/sop-datasheet/library').then(r => setLibraryList((r.data.templates || []).map((t: any) => ({ id: t.id, display_name: t.display_name })))).catch(() => {});
    setBusy(true); clearError();
    try {
      const fd = new FormData(); fd.append('iodb_file', iodbFile);
      const res = await api.post('/sop-datasheet/library/analyze-iodb', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setIodbAnalysis(res.data); setInstrumentTypes(res.data.groups.map((g: IodbGroup) => g.instrument_type));
      setSelectedType(''); setTypeTemplate({});
    } catch (e: any) { setIodbAnalysis(null); setError(e?.response?.data?.detail || 'The IODB could not be analysed.'); }
    finally { setBusy(false); }
  };
  const templateFor = (g: IodbGroup) => typeTemplate[g.instrument_type] ?? g.template_id ?? '';
  const loadTemplate = async (id: string, scope?: Record<string, string>) => {
    setTemplateId(id); setTemplateInfo(null); setFields([]); setOverrides({}); setAiConf({}); setAnnexValues({});
    if (!id) return;
    setBusy(true); clearError();
    try {
      const res = await api.get(`/sop-datasheet/library/${id}`, { params: scope && Object.keys(scope).length ? { field_scope: JSON.stringify(scope) } : {} });
      const f: LibField[] = res.data.fields || [];
      setFields(f); setTemplateInfo(res.data.template); setHeaderFields(res.data.header_fields || {});
      setSelectedDatasheet(res.data.template.sheets.find((x: any) => x.role === 'main')?.sheet || '');
      setGenFormat('CONSOLIDATED');
      const init: Record<string, string[]> = {}; const src: Record<string, SpecSource> = {};
      f.filter(x => x.scope === 'common').forEach(x => { init[x.key] = [...x.defaults]; src[x.key] = (x.origin as SpecSource); });
      setOverrides(init); setSpecSources(src);
      if (res.data.notes?.length) setNotice(res.data.notes.join(' '));
    } catch (e: any) { setError(e?.response?.data?.detail || 'The datasheet template could not be loaded.'); }
    finally { setBusy(false); }
  };
  const chooseGroup = (g: IodbGroup) => {
    if (selectedType !== g.instrument_type) invalidateApproval('The instrument type was changed.');
    setSelectedType(g.instrument_type); setTags(g.tags); setSelectedTags([]); setValidation(null);
    const tid = templateFor(g);
    if (tid !== templateId || !templateInfo) loadTemplate(tid);
  };
  const libFields = fields as LibField[];
  const libErrs = useMemo(() => (templateId ? libSpecErrors(libFields, overrides) : {}), [templateId, fields, overrides]); // eslint-disable-line react-hooks/exhaustive-deps
  const annexValuesClean = () => Object.fromEntries(Object.entries(annexValues).map(([t, m]) => [t, Object.fromEntries(Object.entries(m).filter(([, v]) => String(v).trim()))]).filter(([, m]) => Object.keys(m as object).length));

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
      // every field of the selected datasheet is extracted on its own (value, confidence, supporting text)
      const byName: Record<string, string> = {};
      (userFields.length ? userFields : Object.keys(KB).map(k => ({ section: '', label: k }))).forEach(f => { byName[keyLabel(fieldKey(f))] = f.section ? fieldKey(f) : f.label; });
      fd.append('labels', JSON.stringify(Object.keys(byName)));
      const res = await api.post('/sop-datasheet/extract-spec', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      if (res.data.error) { setError(res.data.error); }
      const extracted = (res.data.fields || []).map((f: any) => ({ label: byName[f.label] || f.label, value: f.value || '', confidence: f.confidence || 0, snippet: f.snippet || '' }));
      setAiResults(extracted);
    } catch (e: any) { setError(e?.response?.data?.detail || 'AI extraction failed'); }
    finally { setAiRunning(false); }
  };

  // ── Build review data ─────────────────────────────────────────────────────────
  const buildReview = () => {
    if (templateId) {
      // AI values are proposals: they fill the review table (marked AI, with confidence) and stay editable
      const ov = { ...overrides }; const src = { ...specSources }; const conf = { ...aiConf };
      const common = new Set(libFields.filter(f => f.scope === 'common').map(f => f.key));
      aiResults.forEach(r => { if (r.value && common.has(r.label) && src[r.label] !== 'user') {
        const f = libFields.find(x => x.key === r.label)!;
        ov[r.label] = f.value_cols.length > 1 ? [r.value, ...Array(f.value_cols.length - 1).fill('')] : [r.value];
        src[r.label] = 'ai'; conf[r.label] = r.confidence; } });
      setOverrides(ov); setSpecSources(src); setAiConf(conf);
      setSpecValues(Object.fromEntries(libFields.filter(f => f.scope === 'common').map(f => [f.key, (ov[f.key] || []).filter(Boolean).join(' / ')])));
      setStep(5);
      return;
    }
    const vals: Record<string, string> = {};
    const srcs: Record<string, SpecSource> = {};

    // From IODB green fields
    iodbFields.forEach(f => {
      vals[fieldKey(f)] = iodbGreen[f.label] || '—';
      srcs[fieldKey(f)] = 'iodb';
    });

    // From AI results
    aiResults.forEach(r => {
      if (r.value) { vals[r.label] = r.value; srcs[r.label] = 'ai'; }
    });

    // From knowledge base (manual)
    Object.entries(kbValues).forEach(([k, v]) => {
      if (!v) return;
      // a popup value belongs to the template field of the same name when exactly one exists
      const same = userFields.filter(f => f.label.trim().toLowerCase() === k.trim().toLowerCase());
      const key = same.length === 1 ? fieldKey(same[0]) : k;
      vals[key] = v; srcs[key] = 'user';
    });

    // From template fields overrides
    userFields.forEach(f => {
      const k = fieldKey(f);
      const v = overrides[k]?.filter(Boolean).join(' / ');
      if (v && !vals[k]) { vals[k] = v; srcs[k] = 'user'; }
    });

    setSpecValues(vals);
    setSpecSources(srcs);
    setStep(5);
  };

  // ── Reviewed values -> overrides (exactly what is approved and generated) ──────
  const effectiveOverrides = (): Record<string, string[]> => {
    if (templateId) {                                         // library: the reviewed common specifications, keyed SECTION::Label
      const o: Record<string, string[]> = {};
      libFields.filter(f => f.scope === 'common').forEach(f => { o[f.key] = (overrides[f.key] || f.defaults).map(v => String(v ?? '')); });
      return o;
    }
    const out: Record<string, string[]> = { ...overrides };
    Object.entries(specValues).forEach(([label, val]) => {
      if (specSources[label] === 'iodb' || !val || val === '—') return;
      out[label] = String(val).split(' / ').map(x => x.trim());
    });
    return out;
  };
  const currentMapping = (): Record<string, string> => {
    const m: Record<string, string> = {};
    (validation?.annexure?.columns || []).filter(c => c.kind === 'data').forEach(c => { m[String(c.col)] = annexMap[String(c.col)] ?? (c.iodb_column || ''); });
    return m;
  };
  const fingerprint = () => JSON.stringify({ f: genFormat, t: [...selectedTags].sort(), d: selectedDatasheet, o: effectiveOverrides(),
    m: genFormat === 'CONSOLIDATED' ? currentMapping() : {}, tid: templateId, h: header, sc: fieldScope, av: annexValuesClean() });
  const invalidateApproval = (why: string) => {
    if (!approval && reqStatus === 'idle' && !pendingReqId) return;
    if (reqPollRef.current) clearInterval(reqPollRef.current);
    setApproval(null); setReqStatus('idle'); setPendingReqId(null); setRequestedFp(null); setApprovedFp(null); setGenStatus(null);
    setNotice(`${why} The previous approval no longer applies - raise a new approval request.`);
  };
  const runValidation = async (mapping?: Record<string, string>) => {
    if (!iodbFile || !selectedDatasheet || !genFormat || (!sopFile && !templateId)) return;
    setValidating(true);
    try {
      const fd = new FormData();
      if (templateId) {
        fd.append('template_id', templateId); fd.append('header', JSON.stringify(header)); fd.append('field_scope', JSON.stringify(fieldScope));
        fd.append('ai_confidence', JSON.stringify(Object.fromEntries(Object.entries(aiConf).filter(([k]) => specSources[k] === 'ai'))));
        fd.append('annexure_values', JSON.stringify(annexValuesClean()));
      } else fd.append('sop_file', sopFile!);
      fd.append('iodb_file', iodbFile);
      fd.append('datasheet_sheet', selectedDatasheet); fd.append('instrument_type', selectedType);
      fd.append('selected_tags', JSON.stringify(selectedTags)); fd.append('generation_format', genFormat);
      fd.append('overrides', JSON.stringify(effectiveOverrides()));
      fd.append('annexure_mapping', JSON.stringify(mapping ?? annexMap));
      const res = await api.post('/sop-datasheet/validate', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      if (!res.data || !res.data.counts) throw new Error('Unexpected validation response');
      setValidation(res.data);
    } catch (e: any) { setError(e?.response?.data?.detail || e?.message || 'Validation failed'); }
    finally { setValidating(false); }
  };
  useEffect(() => { if (step === 5 && (sopFile || templateId) && iodbFile) runValidation(); }, [step, genFormat]); // eslint-disable-line react-hooks/exhaustive-deps
  // A pending approval keeps being checked after a page refresh
  useEffect(() => {
    if (reqStatus !== 'pending' || !pendingReqId || reqPollRef.current) return;
    const fp = requestedFp;
    reqPollRef.current = setInterval(async () => {
      try {
        const r = await api.get(`/approvals/${pendingReqId}`);
        if (r.data.status === 'approved') {
          clearInterval(reqPollRef.current!);
          setReqStatus('approved'); setApprovedFp(fp);
          setApproval({ approved_by: r.data.reviewed_by_name, employee_id: r.data.reviewed_by_id, role: r.data.reviewed_role,
            date: new Date(r.data.updated_at).toLocaleDateString(), time_log: new Date(r.data.updated_at).toLocaleTimeString() });
        } else if (r.data.status === 'rejected') { clearInterval(reqPollRef.current!); setReqStatus('rejected'); }
      } catch { /* keep polling */ }
    }, 15_000);
  }, [reqStatus, pendingReqId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Approval ──────────────────────────────────────────────────────────────────
  const handleApproval = (info: ApprovalInfo) => {
    setApproval(info);
    setLocked(true);
    setShowApproval(false);
    if (VENDOR_STEPS_ENABLED) {
      const scores = scoreVendors(specValues);
      setVendorScores(scores);
      if (scores.length > 0) setSelectedVS(scores[0]);
    }
    setStep(nextStep(6));
  };

  // ── Generate ──────────────────────────────────────────────────────────────────
  const startGenerate = async () => {
    if ((!sopFile && !templateId) || !iodbFile || !selectedDatasheet || !selectedTags.length) return;
    if (!genFormat) { setError('Select the datasheet generation format first.'); return; }
    if (!pendingReqId || reqStatus !== 'approved' || !approvedFp) { setError('Lead Engineer approval is required before generation.'); return; }
    if (approvedFp !== fingerprint()) {
      invalidateApproval('The format, tags, template, specification values or annexure mapping changed after approval.');
      return;
    }
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
      if (templateId) fd.append('template_id', templateId); else fd.append('sop_file', sopFile!);
      fd.append('iodb_file', iodbFile);
      fd.append('datasheet_sheet', selectedDatasheet);
      fd.append('instrument_type', selectedType);
      fd.append('selected_tags', JSON.stringify(selectedTags));
      fd.append('overrides', JSON.stringify(templateId ? effectiveOverrides() : { ...out, ...effectiveOverrides() }));
      fd.append('generation_format', genFormat);
      fd.append('approval_id', String(pendingReqId));
      if (genFormat === 'CONSOLIDATED') fd.append('annexure_mapping', JSON.stringify(currentMapping()));
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
      const fname = genStatus?.result?.filename || templateInfo?.output_filename || 'Datasheets.zip';
      const url = URL.createObjectURL(new Blob([res.data], { type: String(res.headers['content-type'] || 'application/octet-stream') }));
      const a = document.createElement('a');
      a.href = url; a.download = fname;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e: any) {
      if (e?.response?.status === 404) {
        // Server no longer has the file (e.g. it restarted) — let the user generate again.
        setGenStatus(null);
        setError('The generated file is no longer available on the server. Please click Generate again.');
      } else {
        setError(`Download failed${e?.response?.status ? ` (HTTP ${e.response.status})` : ''}. Please try again.`);
      }
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────────
  return (
    <div className="sm:p-6 max-w-5xl mx-auto space-y-6">
      <PageHeader icon={FileSpreadsheet} title="Smart Datasheet Generator"
        description="IODB → standard template library → consolidated datasheet with tag-wise annexure · AI spec extraction · Lead Engineer approval" />

      <StepBar current={step} />
      {error && <Alert variant="error" onClose={clearError}>{error}</Alert>}
      {notice && <Alert variant="warning" onClose={() => setNotice('')}>{notice}</Alert>}
      {genFormat && step >= 3 && !templateId && (
        <div className="flex items-center gap-2 text-xs" data-testid="format-badge">
          <span className="eyebrow">Format</span>
          <span className="px-2.5 py-1 rounded-full font-semibold" style={{ background: 'var(--s3)', color: 'var(--t0)', border: '1px solid var(--b2)' }}>{FORMAT_INFO[genFormat].label}</span>
        </div>
      )}

      {/* ── STEP 1: IODB Upload + Instrument Type → template ── */}
      {step === 1 && (
        <div className="space-y-4">
          {card(<>
            <div className="flex items-center gap-2 mb-3">
              <FileSpreadsheet className="w-4 h-4" style={{ color: 'var(--em)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Upload IODB</span>
            </div>
            <p className="text-xs mb-3" style={{ color: 'var(--t2)' }}>
              iEZ reads every instrument row (tag, instrument type, name / description) and matches each instrument type to the
              standard datasheet template library ({libraryList.length || 11} templates). The IODB is only read.
            </p>
            <SharedIodbPanel compact file={iodbFile} onChange={f => { setIodbFile(f); setIodbAnalysis(null); setInstrumentTypes([]); setSelectedType(''); }} />
            {iodbFile && !iodbAnalysis && (
              <Button onClick={analyseIodb} loading={busy} fullWidth className="mt-3">
                <Search className="w-3.5 h-3.5" /> Analyse IODB
              </Button>
            )}
            {iodbAnalysis && (
              <p className="text-xs mt-3" style={{ color: 'var(--t2)' }}>
                {iodbAnalysis.rows} rows · {iodbAnalysis.groups.length} instrument type(s) · <b style={{ color: 'var(--ok)' }}>{iodbAnalysis.supported} with a template</b>
                {(iodbAnalysis.hidden?.length ?? 0) > 0 && <> · <span title={iodbAnalysis.hidden!.map(h => `${h.instrument_type} (${h.tag_count})`).join('\n')}>{iodbAnalysis.hidden!.length} non-instrument type(s) hidden (motors, valves, alarms, commands)</span></>}
                {iodbAnalysis.unsupported.length > 0 && <> · <b style={{ color: 'var(--rose)' }}>{iodbAnalysis.unsupported.length} without</b></>}
                {' '}· columns: {Object.entries(iodbAnalysis.columns).filter(([, v]) => v).map(([k, v]) => `${k} "${v}"`).join(', ')}
              </p>
            )}
          </>)}

          {iodbAnalysis && card(<>
            <div className="flex items-center gap-2 mb-3">
              <SlidersHorizontal className="w-4 h-4" style={{ color: 'var(--gold)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Select the instrument type</span>
              <div className="relative ml-auto w-48">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3" style={{ color: 'var(--t2)' }} />
                <input value={typeSearch} onChange={e => setTypeSearch(e.target.value)} placeholder="Filter types…"
                  className="w-full pl-7 pr-2 py-1.5 rounded-lg text-xs" style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
              </div>
            </div>
            <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid var(--b1)' }}>
              <table className="w-full text-xs min-w-[640px]">
                <thead style={{ background: 'var(--s2)' }}><tr className="text-left" style={{ color: 'var(--t2)' }}>
                  <th className="px-3 py-2 w-8" /><th className="px-3">Instrument type (IODB)</th><th className="px-3">Tags</th><th className="px-3">Datasheet template</th><th className="px-3">Match</th>
                </tr></thead>
                <tbody>
                  {iodbAnalysis.groups.filter(g => g.instrument_type.toLowerCase().includes(typeSearch.toLowerCase())).map(g => {
                    const tid = templateFor(g); const manual = typeTemplate[g.instrument_type] !== undefined && typeTemplate[g.instrument_type] !== g.template_id;
                    const badge = MATCH_BADGE[manual ? 'manual' : (tid ? g.status : (g.status === 'ambiguous' ? 'ambiguous' : 'unmatched'))];
                    const active = selectedType === g.instrument_type;
                    return (
                      <tr key={g.instrument_type} className="align-top" style={{ borderTop: '1px solid var(--b1)', background: active ? 'var(--em-dim)' : undefined }}>
                        <td className="px-3 py-2"><input type="radio" checked={active} disabled={!tid} onChange={() => chooseGroup(g)} aria-label={`Select ${g.instrument_type}`} /></td>
                        <td className="px-3 py-2"><span className="font-semibold" style={{ color: 'var(--t0)' }}>{g.instrument_type}</span>
                          {g.duplicates.length > 0 && <span className="block text-[10px]" style={{ color: 'var(--gold)' }}>{g.duplicates.length} tag(s) on several IODB rows</span>}
                          {g.matched_on === 'description' && <span className="block text-[10px]" style={{ color: 'var(--t2)' }}>matched from the description</span>}</td>
                        <td className="px-3 py-2 font-mono">{g.tag_count}</td>
                        <td className="px-3 py-2">
                          <select value={tid} onChange={e => {
                            const v = e.target.value; setTypeTemplate(m => ({ ...m, [g.instrument_type]: v }));
                            if (active) { invalidateApproval('The datasheet template was changed.'); loadTemplate(v); }
                          }} className="w-full px-2 py-1 rounded-md text-xs" style={{ background: 'var(--s1)', border: `1px solid ${tid ? 'var(--b2)' : 'var(--rose)'}`, color: 'var(--t0)' }}>
                            <option value="">- no template -</option>
                            {tid && !libraryList.some(t => t.id === tid) && <option value={tid}>{g.template_name || tid}</option>}
                            {libraryList.map(t => <option key={t.id} value={t.id}>{t.display_name}</option>)}
                          </select>
                          {!tid && g.candidates.length > 0 && <span className="block text-[10px] mt-0.5" style={{ color: 'var(--t2)' }}>Closest: {g.candidates.map(c => c.name).join(', ')}</span>}
                        </td>
                        <td className="px-3 py-2"><span className="text-[11px] font-semibold" style={{ color: badge[1] }} title={g.reason}>{badge[0]}</span></td>
                      </tr>);
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] mt-2" style={{ color: 'var(--t2)' }}>A type without a template cannot be generated until you pick its template. Matches made by key words or from the description are listed for you to confirm - nothing is assigned silently.</p>
            {selectedType && templateId && (
              <Button onClick={() => setStep(2)} className="mt-4 w-full" disabled={busy || !templateInfo}>
                Continue - {tags.length} tag(s) of {selectedType} <ChevronRight className="w-3.5 h-3.5" />
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
              Datasheet template <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 3: Template from the library (loaded automatically) ── */}
      {step === 3 && (
        <div className="space-y-4">
          {card(<>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <FileText className="w-4 h-4" style={{ color: 'var(--gold)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Datasheet template</span>
              <span className="text-xs ml-auto" style={{ color: 'var(--t2)' }}>Consolidated datasheet: main datasheet + tag-wise Annexure-I</span>
            </div>
            {!templateInfo && <p className="text-xs" style={{ color: 'var(--t2)' }}>{busy ? 'Loading the template…' : 'Select an instrument type with a template in step 1.'}</p>}
            {templateInfo && (<>
              <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-xs mb-4" style={{ color: 'var(--t1)' }}>
                <dt style={{ color: 'var(--t2)' }}>Instrument type</dt><dd className="font-semibold" style={{ color: 'var(--t0)' }}>{selectedType}</dd>
                <dt style={{ color: 'var(--t2)' }}>Template</dt><dd className="font-semibold" style={{ color: 'var(--t0)' }}>{templateInfo.display_name}
                  <span className="font-normal" style={{ color: 'var(--t2)' }}> · {templateInfo.version} · {templateInfo.original_filename}</span></dd>
                {templateInfo.title && <><dt style={{ color: 'var(--t2)' }}>Datasheet title</dt><dd>{templateInfo.title}</dd></>}
                <dt style={{ color: 'var(--t2)' }}>Fields</dt><dd>{templateInfo.field_counts.common} common specifications · {templateInfo.field_counts.tag} tag-wise (Annexure-I){templateInfo.field_counts.vendor ? ` · ${templateInfo.field_counts.vendor} vendor` : ''}</dd>
                <dt style={{ color: 'var(--t2)' }}>Annexure-I</dt><dd>{templateInfo.annexure.generated
                  ? <span style={{ color: 'var(--gold)' }}>not in this template - iEZ builds it from the tag-wise rows ({templateInfo.annexure.columns} columns)</span>
                  : <>{templateInfo.annexure.columns} columns · {templateInfo.annexure.capacity} formatted row(s) - expands to {selectedTags.length} tag row(s)</>}</dd>
                <dt style={{ color: 'var(--t2)' }}>Output</dt><dd className="font-mono">{templateInfo.output_filename}</dd>
              </dl>
              <div className="flex flex-wrap gap-1.5">
                {templateInfo.sheets.map(sh => (
                  <span key={sh.role} className="text-[11px] px-2 py-0.5 rounded-full" title={sh.in_output ? 'Included in the generated workbook' : 'Used by iEZ, not part of the document'}
                    style={{ border: '1px solid var(--b2)', color: sh.in_output ? 'var(--t0)' : 'var(--t2)', background: sh.in_output ? 'var(--s1)' : undefined }}>
                    {sh.label}: "{sh.sheet}"{sh.in_output ? '' : ' · reference'}</span>))}
              </div>
              {!templateInfo.has_guide && (
                <div className="mt-4">
                  <p className="text-xs font-semibold mb-1" style={{ color: 'var(--t0)' }}>Tag-wise or common? <span className="font-normal" style={{ color: 'var(--t2)' }}>This template has no Engineering Guide - confirm where each field belongs.</span></p>
                  <div className="max-h-56 overflow-y-auto rounded-lg" style={{ border: '1px solid var(--b1)' }}>
                    {libFields.map(f => (
                      <div key={f.key} className="flex items-center gap-2 px-3 py-1.5 text-xs" style={{ borderTop: '1px solid var(--b1)' }}>
                        <span className="flex-1" style={{ color: 'var(--t1)' }}>{keyLabel(f.key)}</span>
                        {(['tag', 'common'] as const).map(v => (
                          <label key={v} className="flex items-center gap-1" style={{ color: 'var(--t2)' }}>
                            <input type="radio" checked={(fieldScope[f.key] || f.scope) === v} onChange={() => {
                              const sc = { ...fieldScope, [f.key]: v }; setFieldScope(sc); invalidateApproval('A field was moved between the datasheet and the annexure.'); loadTemplate(templateId, sc);
                            }} />{v === 'tag' ? 'Annexure (per tag)' : 'Datasheet (common)'}</label>))}
                      </div>))}
                  </div>
                </div>)}
            </>)}
          </>)}
          {templateInfo && card(<>
            <p className="text-sm font-bold mb-1" style={{ color: 'var(--t0)' }}>Document header</p>
            <p className="text-xs mb-3" style={{ color: 'var(--t2)' }}>Replaces the template's XXXXXX placeholders (cover, index, datasheet, annexures). Leave a field empty to keep the placeholder.</p>
            <div className="grid gap-2 sm:grid-cols-3">
              {Object.entries(headerFields).map(([k, label]) => (
                <label key={k} className="text-xs space-y-1" style={{ color: 'var(--t2)' }}>{label}
                  <input value={header[k] || ''} onChange={e => setHeader(h => ({ ...h, [k]: e.target.value }))} className="w-full px-2.5 py-1.5 rounded-lg text-sm"
                    style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} /></label>))}
            </div>
          </>)}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(2)}>← Back</Button>
            <Button onClick={() => setStep(4)} className="flex-1" disabled={!templateInfo || fields.length === 0 || busy}>
              Specifications <ChevronRight className="w-3.5 h-3.5" />
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

            <button onClick={() => { setSpecMode('manual'); if (templateId && libFields.length) setShowLibPopup(true); }}
              className="rounded-2xl p-6 text-left transition-all"
              style={{ background: specMode === 'manual' ? 'rgba(59,130,246,0.08)' : 'var(--s2)', border: `1.5px solid ${specMode === 'manual' ? 'var(--em)' : 'var(--b1)'}` }}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
                style={{ background: 'var(--em-dim)', border: '1px solid rgba(59,130,246,0.25)' }}>
                <SlidersHorizontal className="w-5 h-5" style={{ color: 'var(--em-lt)' }} />
              </div>
              <p className="text-sm font-bold mb-1.5" style={{ color: 'var(--t0)' }}>Manual Entry</p>
              <p className="text-xs leading-relaxed" style={{ color: 'var(--t1)' }}>
                {templateId ? 'Select each specification from predefined engineering values (dropdowns with Custom Value). Wrong entries are flagged before they are applied.' : 'Select from predefined engineering values. Spec popup opens automatically with validated dropdown options for all fields.'}
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
                      <span className="text-xs" style={{ color: 'var(--t2)' }} title={r.snippet || ''}>{keyLabel(r.label)}{r.snippet ? <span className="block text-[10px] italic truncate max-w-[260px]" style={{ color: 'var(--t2)' }}>“{r.snippet}”</span> : null}</span>
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

          {specMode === 'manual' && templateId && (() => {
            const live = libFields.filter(f => f.scope === 'common' && f.origin !== 'computed');
            const filled = live.filter(f => (overrides[f.key] || f.defaults).some(v => String(v || '').trim())).length;
            const nErr = Object.keys(libErrs).length;
            return (
              <div className="rounded-2xl p-5 flex flex-wrap items-center gap-3" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
                <div className="text-xs" style={{ color: 'var(--t1)' }}>
                  <p><CheckCircle2 className="inline w-3 h-3 mr-1" style={{ color: 'var(--ok)' }} />{filled} of {live.length} specifications have a value</p>
                  {nErr > 0 && <p className="mt-1" style={{ color: 'var(--rose)' }}><AlertTriangle className="inline w-3 h-3 mr-1" />{nErr} value(s) are wrongly entered - open the entry to correct them.</p>}
                  <p className="mt-1" style={{ color: 'var(--t2)' }}>Tag-wise values (Annexure-I) come from the IODB; anything missing there is asked in the review step.</p>
                </div>
                <button onClick={() => setShowLibPopup(true)} className="ml-auto px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-2"
                  style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
                  <SlidersHorizontal className="w-3.5 h-3.5" /> {filled ? 'Edit Specifications' : 'Open Specification Entry'}
                </button>
              </div>);
          })()}
          {/* Manual mode — spec popup trigger */}
          {specMode === 'manual' && !templateId && (
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
              disabled={specMode === null || (specMode === 'ai' && aiResults.length === 0) || (!templateId && specMode === 'manual' && Object.values(kbValues).every(v => !v))}
              className="flex-1">
              Review Specifications <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      {/* ── STEP 5: Review Specifications ── */}
      {step === 5 && (
        <div className="space-y-4">
          {templateId && templateInfo && card(<>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <Eye className="w-4 h-4" style={{ color: 'var(--em)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Review - {templateInfo.display_name}</span>
              <span className="text-xs ml-auto" style={{ color: 'var(--t2)' }}>{selectedType} · {selectedTags.length} tag(s) · {templateInfo.output_filename}</span>
            </div>
            <div className="flex flex-wrap gap-1 mb-4 max-h-16 overflow-y-auto">{selectedTags.map(t => <span key={t} className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--s3)', color: 'var(--t1)' }}>{t}</span>)}</div>
            {validErrs.length > 0 && (
              <div className="rounded-xl p-3 mb-3" style={{ background: 'rgba(244,63,94,0.08)', border: '1px solid rgba(244,63,94,0.3)' }}>
                <p className="text-xs font-semibold mb-1 flex items-center gap-1.5" style={{ color: 'var(--rose)' }}><AlertTriangle className="w-3.5 h-3.5" /> Correct these values before raising the approval</p>
                {validErrs.map((e, k) => <p key={k} className="text-xs" style={{ color: 'var(--rose)' }}>• {e}</p>)}
              </div>)}
            <p className="text-[11px] mb-2" style={{ color: 'var(--t2)' }}>Main datasheet - common specifications. These exact values go for approval and into the datasheet; tag-wise rows show "REFER ANNEXURE-I".</p>
            <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid var(--b1)' }}>
              <table className="w-full text-xs sm:min-w-[640px]">
                <thead style={{ background: 'var(--s2)' }}><tr className="text-left" style={{ color: 'var(--t2)' }}>
                  <th className="px-3 py-2 w-40 hidden sm:table-cell">Section</th><th className="px-3 py-2">Field</th><th className="px-3">Value</th><th className="px-3 w-32">Source</th></tr></thead>
                <tbody>
                  {libFields.map((f, i) => {
                    const newSec = i === 0 || libFields[i - 1].section !== f.section;
                    const vals = overrides[f.key] || f.defaults;
                    const src = specSources[f.key] || f.origin;
                    const [sl, sc] = SRC_LABEL[src] || [src, 'var(--t1)'];
                    const empty = f.scope === 'common' && f.origin !== 'computed' && vals.every(v => !String(v || '').trim());
                    return (
                      <tr key={f.key} className="align-top" style={{ borderTop: newSec ? '1px solid var(--b2)' : '1px solid var(--b0, var(--b1))', opacity: f.scope === 'common' ? 1 : 0.7 }}>
                        <td className="px-3 py-1.5 font-semibold hidden sm:table-cell" style={{ color: 'var(--t2)' }}>{newSec ? f.section : ''}</td>
                        <td className="px-3 py-1.5" style={{ color: 'var(--t0)' }}>{newSec && <span className="sm:hidden block eyebrow mb-0.5">{f.section}</span>}{f.label}{f.source_note && <span className="block text-[10px]" style={{ color: 'var(--t2)' }} title="Engineering Guide source note">{f.source_note}</span>}</td>
                        <td className="px-3 py-1.5">
                          {f.scope !== 'common' ? <span className="font-mono text-[11px]" style={{ color: 'var(--t2)' }}>{f.scope === 'tag' ? 'REFER ANNEXURE-I (per tag)' : 'REFER ANNEXURE-II (spares)'}</span> : (
                            <div className={f.value_cols.length > 1 ? 'grid grid-cols-3 gap-1' : ''}>
                              {f.value_cols.map((_, k) => {
                                const setV = (nv: string) => { const v = [...(overrides[f.key] || f.defaults)]; v[k] = nv; setOverrides(o => ({ ...o, [f.key]: v })); setSpecSources(s2 => ({ ...s2, [f.key]: 'user' })); };
                                const ph = f.sub_labels[k] || (f.origin === 'vendor' ? `e.g. ${f.example[0] || ''}` : f.origin === 'computed' ? `auto: ${selectedTags.length} NOS` : '');
                                return f.value_cols.length === 1 && f.origin !== 'computed'
                                  ? <SpecInput key={`${f.key}-${k}`} compact field={f} value={vals[k] ?? ''} onChange={setV} error={libErrs[f.key]} placeholder={ph} />
                                  : <input key={k} value={vals[k] ?? ''} placeholder={ph} onChange={e => setV(e.target.value)}
                                      className="w-full px-2 py-1 rounded-md text-xs" style={{ background: 'var(--s1)', border: `1px solid ${libErrs[f.key] ? 'var(--rose)' : empty && f.origin !== 'vendor' ? 'var(--gold)' : 'var(--b2)'}`, color: 'var(--t0)', outline: 'none' }} />;
                              })}
                            </div>)}
                          {libErrs[f.key] && <span className="block text-[10px]" style={{ color: 'var(--rose)' }}><AlertTriangle className="inline w-2.5 h-2.5 mr-0.5" />{libErrs[f.key]}</span>}
                          {empty && <span className="text-[10px]" style={{ color: f.origin === 'vendor' ? 'var(--t2)' : 'var(--gold)' }}>{f.origin === 'vendor' ? 'filled after vendor selection' : 'missing - enter it or leave blank on purpose'}</span>}
                        </td>
                        <td className="px-3 py-1.5"><span className="text-[10px] font-bold" style={{ color: f.scope === 'common' ? sc : 'var(--ok)' }}>
                          {f.scope === 'common' ? sl : 'IODB → Annexure'}{src === 'ai' && aiConf[f.key] !== undefined ? ` ${Math.round(aiConf[f.key] * 100)}%` : ''}</span></td>
                      </tr>);
                  })}
                </tbody>
              </table>
            </div>
          </>)}
          {!templateId && card(<>
            <div className="flex items-center gap-2 mb-4">
              <Eye className="w-4 h-4" style={{ color: 'var(--sky)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--sky)' }}>Review Specifications</span>
              <span className="ml-auto text-xs" style={{ color: 'var(--t2)' }}>Source: IODB · AI · Manual</span>
            </div>
            <p className="text-[11px] mb-3" style={{ color: 'var(--t2)' }}>Values edited here are the ones sent for approval and written to the datasheet.</p>

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
                        <td className="px-3 py-2.5 font-semibold" style={{ color: 'var(--t1)' }}>{keyLabel(label)}</td>
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

          {/* Engineering validation (+ annexure mapping for the consolidated format) */}
          {card(<>
            <div className="flex items-center gap-2 mb-3">
              <Shield className="w-4 h-4" style={{ color: 'var(--em)' }} />
              <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Engineering validation</span>
              {validation && <span className="text-xs ml-2" style={{ color: validation.counts.ERROR ? 'var(--rose)' : 'var(--t2)' }}>{validation.counts.ERROR} error(s) · {validation.counts.REVIEW} review item(s){(validation.counts as any).INFO ? ` · ${(validation.counts as any).INFO} info` : ''}</span>}
              <button onClick={() => runValidation()} className="ml-auto text-xs px-3 py-1.5 rounded-lg flex items-center gap-1.5" style={{ background: 'var(--s3)', border: '1px solid var(--b2)', color: 'var(--t0)' }}>
                {validating ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} Re-check
              </button>
            </div>
            {!validation && <p className="text-xs" style={{ color: 'var(--t2)' }}>{validating ? 'Checking tags, IODB data and template…' : ((!sopFile && !templateId) || !iodbFile)
              ? 'The IODB and the SOP workbook have to be selected again after a page refresh (steps 1 and 3) - files are not kept by the browser.' : 'Not checked yet.'}</p>}
            {validation && validation.issues.length === 0 && <p className="text-xs" style={{ color: 'var(--ok)' }}>All checks passed.</p>}
            {validation && validation.issues.length > 0 && (
              <ul className="space-y-1 max-h-56 overflow-y-auto">
                {validation.issues.map((i, k) => (
                  <li key={k} className="text-xs flex gap-2" style={{ color: i.severity === 'ERROR' ? 'var(--rose)' : i.severity === 'REVIEW' ? 'var(--gold)' : 'var(--t2)' }}>
                    <span className="font-semibold flex-shrink-0">{i.severity}</span><span style={{ color: 'var(--t1)' }}>{i.message}</span>
                  </li>))}
              </ul>
            )}
            {validation?.annexure && (
              <div className="mt-4">
                <p className="text-xs font-semibold mb-1" style={{ color: 'var(--t0)' }}>Annexure {validation.annexure.sheet} - {validation.annexure.rows} tag row(s) · column mapping (confirm before approval)</p>
                <div className="overflow-auto max-h-72 rounded-lg" style={{ border: '1px solid var(--b1)' }}>
                  <table className="w-full text-xs">
                    <thead><tr><th className="text-left px-2 py-1.5">Annexure column</th><th className="text-left px-2 py-1.5">IODB column</th><th className="text-left px-2 py-1.5">{selectedTags[0] || 'First tag'}</th></tr></thead>
                    <tbody>
                      {validation.annexure.columns.map(c => (
                        <tr key={c.col}>
                          <td className="px-2 py-1">{c.label}{c.hidden ? ' (hidden column)' : ''}</td>
                          <td className="px-2 py-1">
                            {c.kind === 'data' ? (
                              <select value={annexMap[String(c.col)] ?? (c.iodb_column || '')}
                                onChange={e => { const m = { ...annexMap, [String(c.col)]: e.target.value }; setAnnexMap(m); runValidation(m); }}
                                className="w-full px-2 py-1 rounded-md text-xs">
                                <option value="">- none (left blank) -</option>
                                {(validation.iodb_columns || []).map(o => <option key={o} value={o}>{o}</option>)}
                              </select>
                            ) : <span style={{ color: 'var(--t2)' }}>{c.kind === 'tag' ? 'selected tag' : 'serial number'}</span>}
                          </td>
                          <td className="px-2 py-1 font-mono">{String(validation.annexure!.preview[0]?.[String(c.col)] ?? '')}</td>
                        </tr>))}
                    </tbody>
                  </table>
                </div>
                {validation.annexure.preview.length > 0 && (<>
                  <p className="text-xs font-semibold mt-4 mb-1" style={{ color: 'var(--t0)' }}>Annexure preview - first {validation.annexure.preview.length} of {validation.annexure.rows} tag row(s)</p>
                  <div className="overflow-auto max-h-72 rounded-lg" style={{ border: '1px solid var(--b1)' }}>
                    <table className="text-[11px] whitespace-nowrap">
                      <thead style={{ background: 'var(--s2)' }}><tr>{validation.annexure.columns.map(c => <th key={c.col} className="text-left px-2 py-1.5 font-semibold" style={{ color: 'var(--t2)' }}>{c.label}</th>)}</tr></thead>
                      <tbody>{validation.annexure.preview.map((r, k) => (
                        <tr key={k} style={{ borderTop: '1px solid var(--b1)' }}>{validation.annexure!.columns.map(c => {
                          const v = r[String(c.col)];
                          return <td key={c.col} className="px-2 py-1 font-mono" style={{ color: v === null || v === undefined || v === '' ? 'var(--gold)' : 'var(--t0)' }}>{v === null || v === undefined || v === '' ? (c.kind === 'data' ? '—' : '') : String(v)}</td>;
                        })}</tr>))}</tbody>
                    </table>
                  </div>
                </>)}
                {templateId && (() => {
                  const ann = validation.annexure!;
                  const gaps = ann.missing || [];
                  const colSet = new Set<number>(gaps.map(g => g.col));
                  const tagSet = new Set<string>(gaps.map(g => g.tag));
                  Object.entries(annexValues).forEach(([t, m]) => Object.entries(m).forEach(([c, v]) => { if (String(v).trim()) { colSet.add(Number(c)); tagSet.add(t); } }));
                  if (!colSet.size) return null;
                  const cols = ann.columns.filter(c => colSet.has(c.col));
                  const gapKey = new Set(gaps.map(g => `${g.tag}|${g.col}`));
                  const tagsShown = selectedTags.filter(t => tagSet.has(t));
                  const setCell = (t: string, c: number, v: string) => setAnnexValues(a => ({ ...a, [t]: { ...(a[t] || {}), [String(c)]: v } }));
                  return (<>
                    <p className="text-xs font-semibold mt-5 mb-1 flex items-center gap-1.5" style={{ color: 'var(--gold)' }}>
                      <AlertTriangle className="w-3.5 h-3.5" /> Annexure details not found in the IODB - {ann.missing_total ?? gaps.length} blank cell(s)
                      {ann.manual_filled ? <span style={{ color: 'var(--ok)' }}> · {ann.manual_filled} entered by you</span> : null}
                    </p>
                    <p className="text-[11px] mb-2" style={{ color: 'var(--t2)' }}>Enter the missing values for each tag (leave a cell empty to keep it blank). Values from the IODB are never replaced. They go for approval with the datasheet.</p>
                    <div className="overflow-auto max-h-80 rounded-lg" style={{ border: '1px solid var(--gold)' }}>
                      <table className="text-[11px]">
                        <thead style={{ background: 'var(--s2)' }}><tr>
                          <th className="text-left px-2 py-1.5 sticky left-0" style={{ background: 'var(--s2)', color: 'var(--t2)' }}>TAG NO.</th>
                          {cols.map(c => <th key={c.col} className="text-left px-2 py-1.5 font-semibold whitespace-nowrap" style={{ color: 'var(--t2)' }}>{c.label}</th>)}
                        </tr></thead>
                        <tbody>{tagsShown.map(t => (
                          <tr key={t} style={{ borderTop: '1px solid var(--b1)' }}>
                            <td className="px-2 py-1 font-mono sticky left-0 whitespace-nowrap" style={{ background: 'var(--s1)', color: 'var(--t0)' }}>{t}</td>
                            {cols.map(c => {
                              const v = annexValues[t]?.[String(c.col)] ?? '';
                              const ask = gapKey.has(`${t}|${c.col}`) || v !== '';
                              return <td key={c.col} className="px-1 py-0.5">{ask
                                ? <input value={v} onChange={e => setCell(t, c.col, e.target.value)} placeholder="enter…" aria-label={`${c.label} for ${t}`}
                                    className="w-32 px-1.5 py-1 rounded text-[11px]" style={{ background: 'var(--s1)', border: `1px solid ${v ? 'var(--b2)' : 'var(--gold)'}`, color: 'var(--t0)', outline: 'none' }} />
                                : <span className="px-1.5" style={{ color: 'var(--t2)' }}>from IODB</span>}</td>;
                            })}
                          </tr>))}</tbody>
                      </table>
                    </div>
                    <div className="flex flex-wrap gap-2 mt-2">
                      <Button variant="secondary" onClick={() => runValidation()} loading={validating}><RefreshCw className="w-3.5 h-3.5" /> Apply entries &amp; re-check</Button>
                      {tagsShown.length > 1 && <Button variant="secondary" onClick={() => {
                        const first = tagsShown[0];
                        setAnnexValues(a => {
                          const n = { ...a };
                          tagsShown.slice(1).forEach(t => cols.forEach(c => {
                            const fv = a[first]?.[String(c.col)];
                            if (fv && gapKey.has(`${t}|${c.col}`) && !(a[t]?.[String(c.col)])) n[t] = { ...(n[t] || {}), [String(c.col)]: fv };
                          }));
                          return n;
                        });
                      }} title="Copy the first tag's entries into the blank cells below">Copy first row down</Button>}
                    </div>
                  </>);
                })()}
              </div>
            )}
          </>)}

          {/* Request status banner */}
          {reqStatus === 'pending' && pendingReqId && (
            <div className="flex items-center gap-3 px-4 py-3 rounded-xl"
              style={{ background: 'rgba(245,158,11,0.07)', border: '1px solid rgba(245,158,11,0.25)' }}>
              <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" style={{ color: 'var(--gold)' }} />
              <div className="flex-1">
                <p className="text-xs font-bold" style={{ color: 'var(--gold)' }}>
                  Approval Request #{pendingReqId} — Awaiting Lead Engineer Review
                </p>
                <p className="text-[10px]" style={{ color: 'var(--t2)' }}>Auto-refreshing every 15 s… Lead Engineer will see this in their Approval Queue.</p>
              </div>
              <button onClick={() => {
                if (reqPollRef.current) clearInterval(reqPollRef.current);
                setPendingReqId(null); setReqStatus('idle');
              }} className="opacity-40 hover:opacity-80" style={{ color: 'var(--t2)' }}><X className="w-3.5 h-3.5" /></button>
            </div>
          )}
          {reqStatus === 'rejected' && (
            <div className="flex items-center gap-3 px-4 py-3 rounded-xl"
              style={{ background: 'rgba(248,113,113,0.07)', border: '1px solid rgba(248,113,113,0.2)' }}>
              <AlertTriangle className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--rose)' }} />
              <div className="flex-1">
                <p className="text-xs font-bold" style={{ color: 'var(--rose)' }}>Request Rejected by Lead Engineer</p>
                <p className="text-[10px]" style={{ color: 'var(--t2)' }}>Review the specs and raise a new request.</p>
              </div>
              <button onClick={() => { setPendingReqId(null); setReqStatus('idle'); }}
                className="opacity-40 hover:opacity-80" style={{ color: 'var(--t2)' }}><X className="w-3.5 h-3.5" /></button>
            </div>
          )}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(4)}>← Back</Button>
            {/* Raise request button — always available */}
            {reqStatus !== 'pending' && (
              <Button variant="secondary" disabled={!validation || validation.counts.ERROR > 0 || validating}
                title={!validation ? 'Run the engineering validation first' : validation.counts.ERROR ? 'Resolve the validation errors first' : ''}
                onClick={() => {
                const errs = templateId
                  ? Object.entries(libErrs).map(([k, m]) => `${keyLabel(k)}: ${m}`)
                  : validateSpecs(specValues);
                setValidErrs(errs);
                if (errs.length === 0) setShowRaiseModal(true);
              }} className="flex-1">
                <Send className="w-3.5 h-3.5" /> Raise Approval Request
              </Button>
            )}
            {/* OK / Engineering Approval — disabled until Lead approves */}
            <Button disabled={reqStatus !== 'approved'}
              onClick={() => {
                if (reqStatus === 'approved' && approval) {
                  setLocked(true);
                  setStep(6);
                }
              }}
              className="flex-1"
              title={reqStatus !== 'approved' ? 'Raise a request and wait for Lead Engineer approval' : 'Proceed to next step'}>
              <Lock className="w-3.5 h-3.5" />
              {reqStatus === 'approved' ? 'OK — Proceed' : 'OK (Awaiting Approval)'}
              <ChevronRight className="w-3.5 h-3.5" />
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
                ['Format', genFormat ? FORMAT_INFO[genFormat].label : '—'],
              ].map(([k, v]) => (
                <div key={k} className="rounded-xl px-4 py-3" style={{ background: 'var(--s3)', border: '1px solid rgba(74,222,128,0.15)' }}>
                  <p className="text-[10px] mb-0.5" style={{ color: 'var(--t2)' }}>{k}</p>
                  <p className="text-sm font-semibold" style={{ color: '#4ade80' }}>{v}</p>
                </div>
              ))}
            </div>
          </>)}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => setStep(5)}>← Back</Button>
            <Button onClick={() => setStep(nextStep(6))} className="flex-1">
              {VENDOR_STEPS_ENABLED ? 'SIMRE Vendor Matching' : 'Continue to Generate'} <ChevronRight className="w-3.5 h-3.5" />
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
            {genFormat === 'CONSOLIDATED' ? (
              <div className="space-y-1">
                <p className="text-xs font-mono" style={{ color: 'var(--em-lt)' }}>📄 {templateInfo?.output_filename || `${selectedDatasheet.replace(/[^A-Za-z0-9_-]+/g, '_')}_CONSOLIDATED_DATASHEET.xlsx`}</p>
                <p className="text-xs" style={{ color: 'var(--t2)' }}>Main datasheet (common specifications) + annexure with {selectedTags.length} tag row(s)</p>
              </div>
            ) : (
            <div className="space-y-1">
              {selectedTags.map(t => (
                <p key={t} className="text-xs font-mono" style={{ color: 'var(--em-lt)' }}>📄 {t}.xlsx</p>
              ))}
              <p className="text-xs font-mono mt-2" style={{ color: 'var(--gold)' }}>📦 Datasheets.zip (all files)</p>
            </div>)}
          </div>

          {/* Generation status */}
          {card(
            <div className="text-center py-6">
              {genStatus?.status === 'processing' && (
                <>
                  <Loader2 className="w-10 h-10 animate-spin mx-auto mb-3" style={{ color: 'var(--em-lt)' }} />
                  <p className="text-base font-bold" style={{ color: 'var(--t0)' }}>{genFormat === 'CONSOLIDATED' ? `Generating the consolidated datasheet for ${selectedTags.length} tag(s)…` : `Generating ${selectedTags.length} datasheet(s)…`}</p>
                  <p className="text-xs mt-1" style={{ color: 'var(--t2)' }}>Filling templates with IODB + approved specs + vendor data</p>
                </>
              )}
              {genStatus?.status === 'done' && (
                <>
                  <CheckCircle2 className="w-10 h-10 mx-auto mb-3" style={{ color: '#4ade80' }} />
                  <p className="text-base font-bold mb-1" style={{ color: '#4ade80' }}>
                    {(genStatus.result?.failed_tags?.length ?? 0) > 0
                      ? `${genStatus.result?.tag_count} of ${(genStatus.result?.tag_count ?? 0) + (genStatus.result?.failed_tags?.length ?? 0)} Datasheets Generated`
                      : genStatus.result?.format === 'CONSOLIDATED' ? `Consolidated datasheet ready - ${genStatus.result?.tag_count} tag(s)` : (genStatus.result?.tag_count ?? 0) === 1 ? '1 Datasheet Ready!' : `${genStatus.result?.tag_count ?? ''} Datasheets Ready!`}
                  </p>
                  <p className="text-xs mb-5" style={{ color: 'var(--t2)' }}>{genStatus.result?.message}</p>
                  {(genStatus.result?.failed_tags?.length ?? 0) > 0 && (
                    <div className="text-left mb-5 mx-auto max-w-xl">
                      <Alert variant="warning" title="Some datasheets were not generated">
                        <ul className="text-xs space-y-0.5">
                          {genStatus.result!.failed_tags!.map(f => (
                            <li key={f.tag}><span className="font-mono">{f.tag}</span> — {f.reason}</li>
                          ))}
                        </ul>
                        <p className="text-xs mt-2">{genFormat === 'CONSOLIDATED' ? 'These tags are not in the datasheet. Download it before retrying.' : 'The ZIP below contains only the successful datasheets. Download it before retrying.'}</p>
                        <Button variant="secondary" size="sm" className="mt-2" onClick={() => {
                          setSelectedTags(genStatus.result!.failed_tags!.map(f => f.tag));
                          setGenStatus(null);
                        }}>
                          Retry Failed Tags
                        </Button>
                      </Alert>
                    </div>
                  )}
                  <Button onClick={downloadZip} size="lg">
                    <Download className="w-4 h-4" /> {genStatus.result?.filename?.endsWith('.xlsx') ? `Download ${genStatus.result.filename}` : (genStatus.result?.tag_count ?? 0) === 1 ? 'Download Datasheet (ZIP)' : 'Download Datasheets (ZIP)'}
                  </Button>
                </>
              )}
              {genStatus?.status === 'error' && (
                <Alert variant="error">{genStatus.error || 'Generation failed'}</Alert>
              )}
              {!genStatus && (
                <Button onClick={startGenerate} loading={busy} size="lg" className="mx-auto">
                  <Download className="w-4 h-4" /> {genFormat === 'CONSOLIDATED' ? `Generate consolidated datasheet (${selectedTags.length} tag(s))` : `Generate ${selectedTags.length} Datasheet(s)`}
                </Button>
              )}
            </div>
          )}

          <div className="flex gap-3">
            <Button variant="secondary" onClick={() => { setStep(prevStep(9)); setGenStatus(null); if (pollRef.current) clearInterval(pollRef.current); setBusy(false); }}>← Back</Button>
            {genStatus?.status === 'done' && (
              <Button variant="ghost" className="flex-1" onClick={() => {
                sessionStorage.removeItem('datasheet_state');
                setStep(1); setIodbFile(null); setSopFile(null); setInstrumentTypes([]); setSelectedType('');
                setTags([]); setSelectedTags([]); setDatasheets([]); setSelectedDatasheet(''); setFields([]);
                setSpecMode(null); setAiResults([]); setKbValues({}); setIodbGreen({}); setIodbConfirmed(false);
                setSpecValues({}); setSpecSources({}); setApproval(null); setLocked(false);
                setVendorScores(null); setSelectedVS(null); setGenStatus(null);
                setGenFormat(''); setAnnexMap({}); setValidation(null); setRequestedFp(null); setApprovedFp(null); setPendingReqId(null); setReqStatus('idle');
                setIodbAnalysis(null); setTypeTemplate({}); setTemplateId(''); setTemplateInfo(null); setHeader({}); setFieldScope({}); setAiConf({}); setOverrides({});
              }}>
                New Datasheet
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Modals */}
      {showLibPopup && templateId && (
        <LibSpecPopup fields={libFields} initial={overrides} title={templateInfo?.display_name || selectedType}
          onClose={() => setShowLibPopup(false)}
          onConfirm={(vals, changed) => {
            setOverrides(o => ({ ...o, ...vals }));
            if (changed.length) setSpecSources(s2 => ({ ...s2, ...Object.fromEntries(changed.map(k => [k, 'user' as SpecSource])) }));
            setValidErrs([]); setShowLibPopup(false);
          }} />
      )}
      {showSpecPopup && (
        <SpecPopup initial={kbValues} onClose={() => setShowSpecPopup(false)}
          onConfirm={(vals) => { setKbValues(vals); setShowSpecPopup(false); }} />
      )}
      {showApproval && (
        <ApprovalModal tags={selectedTags} instrumentType={selectedType}
          onSuccess={handleApproval} onClose={() => setShowApproval(false)} />
      )}
      {showRaiseModal && (
        <RaiseRequestModal
          tags={selectedTags} instrumentType={selectedType}
          specValues={templateId ? Object.fromEntries(libFields.filter(f => f.scope === 'common').map(f => [f.key, (overrides[f.key] || f.defaults).filter(Boolean).join(' / ')])) : specValues}
          extra={{
            display: { 'Datasheet Format': genFormat ? FORMAT_INFO[genFormat].label : '', 'Datasheet': selectedDatasheet,
                       ...(templateInfo ? { 'Template': `${templateInfo.display_name} (${templateInfo.version})`, 'Output': templateInfo.output_filename } : {}),
                       'Validation': validation ? `${validation.counts.ERROR} error(s), ${validation.counts.REVIEW} review item(s)` : 'not run' },
            machine: { format: genFormat, datasheet: selectedDatasheet, overrides: effectiveOverrides(),
                       template_id: templateId || null, instrument_type: selectedType, header, field_scope: fieldScope, annexure_values: annexValuesClean(),
                       annexure_mapping: genFormat === 'CONSOLIDATED' ? currentMapping() : null,
                       review_items: (validation?.issues || []).map(i => i.message) },
          }}
          onSuccess={(reqId) => {
            const fp = fingerprint();
            setRequestedFp(fp);
            setPendingReqId(reqId); setReqStatus('pending');
            // Poll for approval every 15 s
            if (reqPollRef.current) clearInterval(reqPollRef.current);
            reqPollRef.current = setInterval(async () => {
              try {
                const r = await api.get(`/approvals/${reqId}`);
                const st = r.data.status;
                if (st === 'approved') {
                  clearInterval(reqPollRef.current!);
                  setReqStatus('approved');
                  setApprovedFp(fp);
                  // Build approval info from the request data
                  setApproval({
                    approved_by: r.data.reviewed_by_name,
                    employee_id: r.data.reviewed_by_id,
                    role: r.data.reviewed_role,
                    date: new Date(r.data.updated_at).toLocaleDateString(),
                    time_log: new Date(r.data.updated_at).toLocaleTimeString(),
                  });
                } else if (st === 'rejected') {
                  clearInterval(reqPollRef.current!);
                  setReqStatus('rejected');
                }
              } catch { /* ignore polling errors */ }
            }, 15_000);
          }}
          onClose={() => setShowRaiseModal(false)} />
      )}
    </div>
  );
}
