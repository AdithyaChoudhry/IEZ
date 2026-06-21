/**
 * Vendor Analysis & Technical Bid Evaluation (TBE) Module
 * Supports all instrument types — universal datasheet analysis engine.
 */
import { useState, useRef, useCallback, useEffect } from 'react';
import {
  FileSpreadsheet, CheckCircle2, AlertTriangle,
  Loader2, BarChart2, Download, ShieldCheck, ChevronRight,
  Star, TrendingUp, AlertCircle, Award, RefreshCw,
  Pencil, Plus, Trash2, XCircle, Database, X, Save,
} from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import { useAuth } from '@/context/AuthContext';

// ── types ──────────────────────────────────────────────────────────────────────
interface VendorEntry {
  id: number;
  instrument_type: string;
  vendor_name: string;
  abbr: string;
  model: string;
  specs: Record<string, string>;
  is_active: boolean;
}

const EMPTY_VENDOR: Omit<VendorEntry, 'id'> = {
  instrument_type: '', vendor_name: '', abbr: '', model: '', specs: {}, is_active: true,
};

interface SpecRow { param: string; value: string; source: string; resolved: boolean; }

// Keywords that classify a spec as Project Information (not used for vendor matching)
const PI_KEYWORDS = [
  'tag number', 'tag no', 'tag #', 'tag',
  'service description', 'service name', 'service',
  'pid number', 'pid no', 'p&id number', 'p&id no', 'pid', 'p&id', 'p & id',
  'tank number', 'tank no', 'tank id',
  'equipment number', 'equipment no', 'equipment id',
  'plant area', 'plant location', 'location', 'area',
  'line number', 'line no', 'line size', 'line material', 'line id',
  'piping class', 'pipe class', 'line schedule', 'line spec',
  'requisition number', 'requisition no', 'po number', 'purchase order',
  'fluid name', 'fluid description',
  'equipment description', 'instrument description',
  'document number', 'drawing number', 'doc no', 'drg no',
  'unit number', 'unit no',
];

function classifySpec(param: string): 'project' | 'technical' {
  const p = param.toLowerCase().trim();
  for (const kw of PI_KEYWORDS) {
    if (p === kw || p.startsWith(kw + ' ') || p.endsWith(' ' + kw) || p.includes(kw)) return 'project';
  }
  return 'technical';
}

const NA_VALUES = new Set(['na', 'n/a', 'n.a', 'n.a.', 'not applicable', 'not available', 'none', '-', '--', '—', '', 'nil', 'null', 'tbd', 'tbc']);
function isNA(val: string): boolean {
  return NA_VALUES.has(val.toLowerCase().trim());
}

const ANNEXURE_PATTERNS = /^refer\s+annexure/i;
function isAnnexureRef(val: string): boolean {
  return ANNEXURE_PATTERNS.test(val.trim());
}
interface SpecResult {
  param: string; wabag_req: string; vendor_offer: string;
  status: string; auto_reply: string;
}
interface VendorResult {
  vendor: string; abbr: string; model: string;
  match_pct: number; spec_results: SpecResult[];
}
interface AnalysisResult {
  instrument_type: string; tag_numbers: string[]; specs: SpecRow[];
  sheet_names: string[]; annexure_sheets: string[];
}

type Step =
  | 'upload' | 'analyzing' | 'requirements' | 'spec_edit'
  | 'matching' | 'vendor_select' | 'tbe_table'
  | 'generating' | 'dashboard' | 'approval' | 'done';

const STATUS_META: Record<string, { bg: string; text: string; chip: string; severity: string }> = {
  'COMPLIES':               { bg: 'rgba(74,222,128,0.10)',  text: '#4ade80',      chip: 'COMPLIES',   severity: '' },
  'EXCEEDS REQUIREMENT':    { bg: 'rgba(59,130,246,0.10)',  text: '#60a5fa',      chip: 'EXCEEDS',    severity: 'Minor' },
  'DEVIATION':              { bg: 'rgba(248,113,113,0.10)', text: '#f87171',      chip: 'DEVIATION',  severity: 'Major' },
  'CLARIFICATION REQUIRED': { bg: 'rgba(245,158,11,0.10)',  text: '#fbbf24',      chip: 'CLARIF.',    severity: 'Minor' },
  'NOT ACCEPTABLE':         { bg: 'rgba(220,38,38,0.15)',   text: '#ef4444',      chip: 'NOT ACC.',   severity: 'Critical' },
  'TECHNICALLY ACCEPTABLE': { bg: 'rgba(20,184,166,0.10)',  text: '#2dd4bf',      chip: 'TECH. ACC.', severity: 'Minor' },
};
const SEVERITY_OPTIONS = ['Critical', 'Major', 'Minor'];

function StatusChip({ status }: { status: string }) {
  const m = STATUS_META[status] || { bg: 'var(--s2)', text: 'var(--t2)', chip: status, severity: '' };
  return (
    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded whitespace-nowrap"
      style={{ background: m.bg, color: m.text }}>
      {m.chip}
    </span>
  );
}

function MatchBar({ pct }: { pct: number }) {
  const color = pct >= 90 ? '#4ade80' : pct >= 75 ? '#fbbf24' : '#f87171';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full" style={{ background: 'var(--s3)' }}>
        <div className="h-1.5 rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-xs font-bold w-9 text-right" style={{ color }}>{pct}%</span>
    </div>
  );
}

// ── Vendor Library ─────────────────────────────────────────────────────────────
function VendorLibrary() {
  const [vendors, setVendors] = useState<VendorEntry[]>([]);
  const [types, setTypes] = useState<string[]>([]);
  const [filterType, setFilterType] = useState('');
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<{ open: boolean; data: Omit<VendorEntry, 'id'> & { id?: number }; specRows: [string, string][] }>({
    open: false, data: { ...EMPTY_VENDOR }, specRows: [],
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [vr, tr] = await Promise.all([
        api.get('/tbe/vendors'),
        api.get('/tbe/vendors/types'),
      ]);
      setVendors(vr.data);
      setTypes(tr.data.types);
    } catch { setError('Failed to load vendors'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const openCreate = () => setModal({ open: true, data: { ...EMPTY_VENDOR }, specRows: [] });
  const openEdit = (v: VendorEntry) => setModal({
    open: true,
    data: { id: v.id, instrument_type: v.instrument_type, vendor_name: v.vendor_name, abbr: v.abbr, model: v.model, specs: v.specs, is_active: v.is_active },
    specRows: Object.entries(v.specs || {}),
  });

  const saveModal = async () => {
    setSaving(true); setError('');
    const specs: Record<string, string> = {};
    for (const [k, v] of modal.specRows) { if (k.trim()) specs[k.trim()] = v; }
    const payload = { ...modal.data, specs };
    try {
      if (modal.data.id) await api.put(`/tbe/vendors/${modal.data.id}`, payload);
      else await api.post('/tbe/vendors', payload);
      setModal(m => ({ ...m, open: false }));
      load();
    } catch (e: any) { setError(e?.response?.data?.detail || 'Save failed'); }
    finally { setSaving(false); }
  };

  const deleteVendor = async (id: number) => {
    if (!confirm('Delete this vendor?')) return;
    try { await api.delete(`/tbe/vendors/${id}`); load(); }
    catch (e: any) { setError(e?.response?.data?.detail || 'Delete failed'); }
  };

  const filtered = filterType ? vendors.filter(v => v.instrument_type === filterType) : vendors;

  return (
    <div className="space-y-4">
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-sm"
          style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: '#f87171' }}>
          <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
          <button onClick={() => setError('')} className="ml-auto"><XCircle className="w-4 h-4" /></button>
        </div>
      )}

      <div className="flex items-center gap-3 flex-wrap">
        <select
          className="px-3 py-2 rounded-xl text-xs"
          style={{ background: 'var(--s2)', border: '1px solid var(--b2)', color: 'var(--t1)', outline: 'none', minWidth: 220 }}
          value={filterType}
          onChange={e => setFilterType(e.target.value)}>
          <option value="">All Instrument Types ({vendors.length})</option>
          {types.map(t => (
            <option key={t} value={t}>{t} ({vendors.filter(v => v.instrument_type === t).length})</option>
          ))}
        </select>
        <button onClick={openCreate}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold ml-auto"
          style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
          <Plus className="w-3.5 h-3.5" /> Add Vendor
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin" style={{ color: 'var(--em)' }} />
        </div>
      ) : (
        <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid var(--b1)' }}>
          <table className="w-full text-xs">
            <thead>
              <tr style={{ background: 'var(--s2)' }}>
                {['Instrument Type', 'Vendor', 'Abbr', 'Model', 'Specs', 'Status', ''].map(h => (
                  <th key={h} className="text-left px-4 py-2.5 font-semibold whitespace-nowrap" style={{ color: 'var(--t2)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((v, i) => (
                <tr key={v.id} style={{ borderTop: '1px solid var(--b0)', background: i % 2 ? 'var(--s1)' : 'transparent' }}>
                  <td className="px-4 py-2.5 capitalize" style={{ color: 'var(--t2)' }}>{v.instrument_type}</td>
                  <td className="px-4 py-2.5 font-semibold" style={{ color: 'var(--t0)' }}>{v.vendor_name}</td>
                  <td className="px-4 py-2.5" style={{ color: 'var(--t1)' }}>{v.abbr}</td>
                  <td className="px-4 py-2.5" style={{ color: 'var(--t1)' }}>{v.model}</td>
                  <td className="px-4 py-2.5" style={{ color: 'var(--t2)' }}>{Object.keys(v.specs || {}).length} specs</td>
                  <td className="px-4 py-2.5">
                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded"
                      style={{ background: v.is_active ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)', color: v.is_active ? '#4ade80' : '#f87171' }}>
                      {v.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-1.5">
                      <button onClick={() => openEdit(v)} className="p-1.5 rounded-lg hover:bg-[var(--s2)]">
                        <Pencil className="w-3.5 h-3.5" style={{ color: 'var(--em-lt)' }} />
                      </button>
                      <button onClick={() => deleteVendor(v.id)} className="p-1.5 rounded-lg hover:bg-red-500/10">
                        <Trash2 className="w-3.5 h-3.5" style={{ color: '#f87171' }} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-xs" style={{ color: 'var(--t2)' }}>No vendors found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal */}
      {modal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.6)' }}>
          <div className="w-full max-w-2xl rounded-2xl overflow-hidden flex flex-col max-h-[90vh]" style={{ background: 'var(--s0)', border: '1px solid var(--b2)' }}>
            <div className="px-5 py-4 flex items-center justify-between flex-shrink-0" style={{ borderBottom: '1px solid var(--b1)' }}>
              <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>{modal.data.id ? 'Edit Vendor' : 'Add Vendor'}</p>
              <button onClick={() => setModal(m => ({ ...m, open: false }))}><X className="w-4 h-4" style={{ color: 'var(--t2)' }} /></button>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {error && <p className="text-xs text-red-400">{error}</p>}

              <div className="grid grid-cols-2 gap-3">
                {([['instrument_type', 'Instrument Type'], ['vendor_name', 'Vendor Name'], ['abbr', 'Abbreviation'], ['model', 'Model']] as [keyof typeof modal.data, string][]).map(([field, label]) => (
                  <div key={field}>
                    <label className="block text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--t2)' }}>{label}</label>
                    <input
                      className="w-full px-3 py-2 rounded-xl text-xs"
                      style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }}
                      value={modal.data[field] as string}
                      onChange={e => setModal(m => ({ ...m, data: { ...m.data, [field]: e.target.value } }))}
                    />
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-2">
                <input type="checkbox" id="is_active" checked={modal.data.is_active}
                  onChange={e => setModal(m => ({ ...m, data: { ...m.data, is_active: e.target.checked } }))} />
                <label htmlFor="is_active" className="text-xs" style={{ color: 'var(--t1)' }}>Active (included in matching)</label>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--t2)' }}>Specifications</label>
                  <button onClick={() => setModal(m => ({ ...m, specRows: [...m.specRows, ['', '']] }))}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold"
                    style={{ background: 'var(--s2)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
                    <Plus className="w-3 h-3" /> Add Spec
                  </button>
                </div>
                <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
                  {modal.specRows.map(([k, v], idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <input placeholder="Spec name (e.g. Accuracy)"
                        className="flex-1 px-2.5 py-1.5 rounded-lg text-xs"
                        style={{ background: 'var(--s1)', border: '1px solid var(--b1)', color: 'var(--t0)', outline: 'none' }}
                        value={k}
                        onChange={e => setModal(m => { const r = [...m.specRows]; r[idx] = [e.target.value, r[idx][1]]; return { ...m, specRows: r }; })}
                      />
                      <input placeholder="Value (e.g. ±1 mm)"
                        className="flex-1 px-2.5 py-1.5 rounded-lg text-xs"
                        style={{ background: 'var(--s1)', border: '1px solid var(--b1)', color: 'var(--t1)', outline: 'none' }}
                        value={v}
                        onChange={e => setModal(m => { const r = [...m.specRows]; r[idx] = [r[idx][0], e.target.value]; return { ...m, specRows: r }; })}
                      />
                      <button onClick={() => setModal(m => ({ ...m, specRows: m.specRows.filter((_, i) => i !== idx) }))}
                        className="p-1 rounded hover:bg-red-500/10">
                        <Trash2 className="w-3.5 h-3.5" style={{ color: '#f87171' }} />
                      </button>
                    </div>
                  ))}
                  {modal.specRows.length === 0 && (
                    <p className="text-[10px] text-center py-4" style={{ color: 'var(--t2)' }}>No specs yet — click "Add Spec" to add rows</p>
                  )}
                </div>
              </div>
            </div>

            <div className="px-5 py-4 flex items-center justify-end gap-3 flex-shrink-0" style={{ borderTop: '1px solid var(--b1)' }}>
              <button onClick={() => setModal(m => ({ ...m, open: false }))}
                className="px-4 py-2 rounded-xl text-xs font-semibold"
                style={{ background: 'var(--s2)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
                Cancel
              </button>
              <button onClick={saveModal} disabled={saving}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold"
                style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff', opacity: saving ? 0.6 : 1 }}>
                {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                {saving ? 'Saving…' : 'Save Vendor'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── main component ─────────────────────────────────────────────────────────────
export default function VendorTBE() {
  const { role } = useAuth();
  const canManageVendors = role === 'Admin' || role === 'Lead Engineer';
  const [mode, setMode] = useState<'wizard' | 'library'>('wizard');

  const [step, setStep] = useState<Step>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');

  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  // project information (display only, not sent to vendor matching)
  const [projectInfo, setProjectInfo] = useState<SpecRow[]>([]);
  // annexure-resolved specs (Part C, display only, not sent to vendor matching)
  const [annexureSpecs, setAnnexureSpecs] = useState<SpecRow[]>([]);
  // technical requirements (Part B, sent to vendor matching engine only)
  const [editedSpecs, setEditedSpecs] = useState<SpecRow[]>([]);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [piEditingIdx, setPiEditingIdx] = useState<number | null>(null);

  const [vendors, setVendors] = useState<VendorResult[]>([]);
  const [selectedVendors, setSelectedVendors] = useState<Set<string>>(new Set());

  // {abbr: {param: reply}}
  const [tbeReplies, setTbeReplies] = useState<Record<string, Record<string, string>>>({});
  // {abbr: {param: severity}}
  const [devSeverities, setDevSeverities] = useState<Record<string, Record<string, string>>>({});

  const [sessionId, setSessionId] = useState('');
  const [approvalResult, setApprovalResult] = useState<any>(null);
  const [approvalReqId, setApprovalReqId] = useState<number | null>(null);
  const [approvalStatus, setApprovalStatus] = useState<'idle' | 'pending' | 'approved' | 'rejected'>('idle');
  const [tbeNotes, setTbeNotes] = useState('');
  const [approving, setApproving] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fileRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setStep('upload'); setFile(null); setError(''); setAnalysis(null);
    setProjectInfo([]); setAnnexureSpecs([]); setEditedSpecs([]); setVendors([]); setSelectedVendors(new Set());
    setTbeReplies({}); setDevSeverities({}); setSessionId('');
    setApprovalResult(null); setApprovalReqId(null); setApprovalStatus('idle'); setTbeNotes('');
  };

  const handleFile = (f: File) => {
    if (!f.name.match(/\.(xlsx|xlsm|xls)$/i)) { setError('Only .xlsx, .xlsm, or .xls files are supported'); return; }
    setFile(f); setError('');
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0]; if (f) handleFile(f);
  }, []);

  // ── analyze ──────────────────────────────────────────────────────────────────
  const runAnalysis = async () => {
    if (!file) return;
    setStep('analyzing'); setError('');
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await api.post('/tbe/analyze', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      const result: AnalysisResult = r.data;
      setAnalysis(result);
      // Classify into Part A / Part B / Part C
      const meaningful = result.specs.filter(s => s.param);
      const pi: SpecRow[] = [];   // Part A – project info
      const ann: SpecRow[] = [];  // Part C – annexure resolved
      const tr: SpecRow[] = [];   // Part B – technical requirements
      for (const s of meaningful) {
        if (!s.value || isNA(s.value)) {
          // NA values → Part A (reference only)
          pi.push(s);
        } else if (s.resolved || isAnnexureRef(s.value)) {
          // Annexure-resolved specs → Part C
          ann.push(s);
        } else if (classifySpec(s.param) === 'project') {
          // Project information keywords → Part A
          pi.push(s);
        } else {
          // Everything else with a real value → Part B
          tr.push(s);
        }
      }
      setProjectInfo(pi);
      setAnnexureSpecs(ann);
      setEditedSpecs(tr);
      setStep('requirements');
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Analysis failed — check the file and try again';
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg));
      setStep('upload');
    }
  };

  // ── spec edit helpers ─────────────────────────────────────────────────────────
  const updateSpec = (idx: number, field: 'param' | 'value', val: string) => {
    setEditedSpecs(prev => prev.map((r, i) => i === idx ? { ...r, [field]: val } : r));
  };
  const addSpec = () => {
    setEditedSpecs(prev => [...prev, { param: '', value: '', source: 'Manual', resolved: false }]);
    setEditingIdx(editedSpecs.length);
  };
  const deleteSpec = (idx: number) => {
    setEditedSpecs(prev => prev.filter((_, i) => i !== idx));
    if (editingIdx === idx) setEditingIdx(null);
  };

  // ── match vendors ─────────────────────────────────────────────────────────────
  const runMatching = async () => {
    setStep('matching'); setError('');
    try {
      const r = await api.post('/tbe/match', {
        instrument_type: analysis?.instrument_type,
        specs: editedSpecs,
      });
      const v: VendorResult[] = r.data.vendors;
      setVendors(v);
      setSelectedVendors(new Set(v.map(x => x.abbr)));
      setStep('vendor_select');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Vendor matching failed');
      setStep('requirements');
    }
  };

  // ── build TBE table ───────────────────────────────────────────────────────────
  const buildTBE = () => {
    const active = vendors.filter(v => selectedVendors.has(v.abbr));
    const replies: Record<string, Record<string, string>> = {};
    const severities: Record<string, Record<string, string>> = {};
    for (const v of active) {
      replies[v.abbr] = {};
      severities[v.abbr] = {};
      for (const sr of v.spec_results) {
        replies[v.abbr][sr.param] = sr.auto_reply;
        if (sr.status !== 'COMPLIES') {
          severities[v.abbr][sr.param] = STATUS_META[sr.status]?.severity || 'Minor';
        }
      }
    }
    setTbeReplies(replies);
    setDevSeverities(severities);
    setStep('tbe_table');
  };

  // ── generate reports ──────────────────────────────────────────────────────────
  const generateReports = async () => {
    setStep('generating'); setError('');
    const active = vendors.filter(v => selectedVendors.has(v.abbr));
    const best = [...active].sort((a, b) => b.match_pct - a.match_pct)[0];
    try {
      const r = await api.post('/tbe/generate', {
        instrument_type: analysis?.instrument_type,
        vendors: active,
        tbe_replies: tbeReplies,
        deviation_severities: devSeverities,
        recommended_vendor: best?.vendor || '',
        recommended_model: best?.model || '',
        recommendation_reason: '',
      });
      setSessionId(r.data.session_id);
      setStep('dashboard');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Report generation failed');
      setStep('tbe_table');
    }
  };

  // ── approve ───────────────────────────────────────────────────────────────────
  const submitApproval = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setApproving(true);
    const best = [...activeVendors].sort((a, b) => b.match_pct - a.match_pct)[0];
    const empId   = localStorage.getItem('user_employee_id') || '';
    const empName = localStorage.getItem('user_employee_name') || '';
    try {
      const r = await api.post('/approvals', {
        request_type: 'tbe',
        submitted_by_name: empName,
        submitted_by_id: empId,
        submitter_notes: tbeNotes || null,
        instrument_type: analysis?.instrument_type || '',
        payload: {
          session_id: sessionId,
          instrument_type: analysis?.instrument_type || '',
          recommended_vendor: best?.vendor || '',
          recommended_model: best?.model || '',
        },
      });
      const reqId: number = r.data.id;
      setApprovalReqId(reqId);
      setApprovalStatus('pending');
      // Poll every 12 s for Lead Engineer approval
      pollRef.current = setInterval(async () => {
        try {
          const poll = await api.get(`/approvals/${reqId}`);
          const st: string = poll.data.status;
          if (st === 'approved') {
            clearInterval(pollRef.current!);
            const payload = JSON.parse(poll.data.payload_json || '{}');
            setApprovalResult({
              tbe_number: payload.tbe_number || '—',
              approved_by: payload.approved_by || poll.data.reviewed_by_name || '—',
              employee_id: payload.approved_employee_id || poll.data.reviewed_by_id || '—',
              timestamp: poll.data.updated_at,
            });
            setApprovalStatus('approved');
            setStep('done');
          } else if (st === 'rejected') {
            clearInterval(pollRef.current!);
            setApprovalStatus('rejected');
            setError('TBE approval was rejected by Lead Engineer. Please review and resubmit.');
          }
        } catch { /* ignore poll errors */ }
      }, 12000);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to submit approval request');
    } finally { setApproving(false); }
  };

  // ── download ──────────────────────────────────────────────────────────────────
  const downloadFile = (type: 'tbe' | 'deviation' | 'compliance') => {
    const token = localStorage.getItem('access_token');
    const names = { tbe: 'TBE_Report.xlsx', deviation: 'Deviation_Report.xlsx', compliance: 'Compliance_Summary.xlsx' };
    fetch(`/api/tbe/download/${sessionId}/${type}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then(res => res.blob()).then(blob => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = names[type]; a.click();
      URL.revokeObjectURL(url);
    }).catch(() => setError('Download failed'));
  };

  const activeVendors = vendors.filter(v => selectedVendors.has(v.abbr));
  const bestVendor = [...activeVendors].sort((a, b) => b.match_pct - a.match_pct)[0];
  const allParams = activeVendors[0]?.spec_results.map(r => r.param) || [];

  // ── step bar ──────────────────────────────────────────────────────────────────
  const STEPS = [
    { key: 'upload',        label: 'Upload' },
    { key: 'requirements',  label: 'Req. Builder' },
    { key: 'vendor_select', label: 'Vendors' },
    { key: 'tbe_table',     label: 'TBE Table' },
    { key: 'dashboard',     label: 'Dashboard' },
    { key: 'approval',      label: 'Approval' },
    { key: 'done',          label: 'Download' },
  ];
  const stepIdx = STEPS.findIndex(s => s.key === step);

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--s0)' }}>
      <PageHeader
        icon={BarChart2}
        title="Vendor Analysis & TBE"
        description="Upload instrument datasheet · Analyze & review specs · Match vendors · Generate TBE"
      />

      {/* Mode toggle */}
      {canManageVendors && (
        <div className="px-6 pt-3 flex items-center gap-2">
          {([['wizard', BarChart2, 'TBE Wizard'], ['library', Database, 'Vendor Library']] as const).map(([m, Icon, label]) => (
            <button key={m} onClick={() => setMode(m)}
              className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all"
              style={{
                background: mode === m ? 'var(--em-dim)' : 'var(--s2)',
                color: mode === m ? 'var(--em-lt)' : 'var(--t2)',
                border: `1px solid ${mode === m ? 'rgba(59,130,246,0.3)' : 'var(--b1)'}`,
              }}>
              <Icon className="w-3.5 h-3.5" /> {label}
            </button>
          ))}
        </div>
      )}

      {/* Vendor Library mode */}
      {mode === 'library' && (
        <div className="flex-1 overflow-y-auto px-6 pb-8 pt-4">
          <VendorLibrary />
        </div>
      )}

      {/* Step bar */}
      {mode === 'wizard' && <div className="px-6 pt-4 pb-2 overflow-x-auto">
        <div className="flex items-center gap-0 min-w-max">
          {STEPS.map((s, i) => {
            const done = stepIdx > i;
            const active = stepIdx === i || (s.key === 'requirements' && (step === 'analyzing' || step === 'spec_edit')) || (s.key === 'vendor_select' && step === 'matching') || (s.key === 'dashboard' && step === 'generating');
            return (
              <div key={s.key} className="flex items-center">
                <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg"
                  style={{ background: active ? 'var(--em-dim)' : done ? 'rgba(74,222,128,0.06)' : 'transparent' }}>
                  <span className="text-[10px] font-bold whitespace-nowrap"
                    style={{ color: active ? 'var(--em-lt)' : done ? '#4ade80' : 'var(--t2)', opacity: active || done ? 1 : 0.45 }}>
                    {i + 1}. {s.label}
                  </span>
                  {done && <CheckCircle2 className="w-3 h-3 flex-shrink-0" style={{ color: '#4ade80' }} />}
                </div>
                {i < STEPS.length - 1 && (
                  <ChevronRight className="w-3 h-3 flex-shrink-0 mx-0.5 opacity-25" style={{ color: 'var(--t2)' }} />
                )}
              </div>
            );
          })}
        </div>
      </div>}

      {mode === 'wizard' && <>
      {/* Error */}
      {error && (
        <div className="mx-6 mt-2 flex items-center gap-2 px-4 py-3 rounded-xl text-sm"
          style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: '#f87171' }}>
          <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
          <button onClick={() => setError('')} className="ml-auto"><XCircle className="w-4 h-4" /></button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-6 pb-8 pt-4">

        {/* ── UPLOAD ── */}
        {step === 'upload' && (
          <div className="max-w-2xl mx-auto space-y-5">
            <div
              className="rounded-2xl p-14 text-center cursor-pointer transition-all"
              style={{
                border: `2px dashed ${dragging ? 'var(--em)' : 'var(--b2)'}`,
                background: dragging ? 'var(--em-dim)' : 'var(--s1)',
              }}
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => fileRef.current?.click()}
            >
              <input ref={fileRef} type="file" accept=".xlsx,.xlsm,.xls" className="hidden"
                onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />
              <FileSpreadsheet className="w-12 h-12 mx-auto mb-4" style={{ color: 'var(--em-lt)', opacity: 0.7 }} />
              <p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>
                {file ? file.name : 'Drop Instrument Datasheet here'}
              </p>
              <p className="text-xs mt-1" style={{ color: 'var(--t2)' }}>
                {file
                  ? `${(file.size / 1024).toFixed(1)} KB · Ready to analyze`
                  : 'Supports .xlsx, .xlsm, .xls · SOP & generated datasheets'}
              </p>
            </div>
            {file && (
              <button onClick={runAnalysis}
                className="w-full py-3.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
                style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
                <BarChart2 className="w-4 h-4" /> Analyze Datasheet
              </button>
            )}
            <div className="flex flex-wrap gap-2 justify-center">
              {['Radar LT', 'Pressure Tx', 'Flow Meter', 'Temperature', 'Control Valve', 'Analyzer', 'Level Switch', 'Any type…'].map(t => (
                <span key={t} className="text-[10px] px-2.5 py-1 rounded-full"
                  style={{ background: 'var(--s2)', color: 'var(--t2)', border: '1px solid var(--b1)' }}>{t}</span>
              ))}
            </div>
          </div>
        )}

        {/* ── SPINNERS ── */}
        {(step === 'analyzing' || step === 'matching' || step === 'generating') && (
          <div className="flex flex-col items-center justify-center py-24 gap-4">
            <Loader2 className="w-10 h-10 animate-spin" style={{ color: 'var(--em)' }} />
            <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>
              {step === 'analyzing' && 'Parsing datasheet & resolving annexure values…'}
              {step === 'matching' && 'Matching specifications against vendor database…'}
              {step === 'generating' && 'Generating TBE, Deviation & Compliance reports…'}
            </p>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>This may take a few seconds</p>
          </div>
        )}

        {/* ── REQUIREMENT DATABASE BUILDER ── */}
        {step === 'requirements' && analysis && (
          <div className="space-y-5">
            {/* Header */}
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-bold px-3 py-1 rounded-full capitalize"
                  style={{ background: 'var(--em-dim)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.2)' }}>
                  {analysis.instrument_type}
                </span>
                <span className="text-xs" style={{ color: 'var(--t2)' }}>
                  {projectInfo.length} project fields · {editedSpecs.length} technical requirements · {annexureSpecs.length} annexure specs
                </span>
              </div>
              <button onClick={runMatching}
                disabled={editedSpecs.filter(s => s.param && s.value).length === 0}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold"
                style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff', opacity: editedSpecs.filter(s => s.param && s.value).length ? 1 : 0.4 }}>
                <ShieldCheck className="w-3.5 h-3.5" /> Lock & Run Vendor Analysis <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            {/* Section A – Project Information Database */}
            <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid rgba(99,102,241,0.25)', background: 'rgba(99,102,241,0.03)' }}>
              <div className="flex items-center justify-between px-4 py-3"
                style={{ background: 'rgba(99,102,241,0.08)', borderBottom: '1px solid rgba(99,102,241,0.15)' }}>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold px-2.5 py-1 rounded-full"
                    style={{ background: 'rgba(99,102,241,0.15)', color: '#a5b4fc' }}>Part A</span>
                  <span className="text-sm font-bold" style={{ color: '#a5b4fc' }}>Project Information Database</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[9px] font-bold px-2 py-1 rounded"
                    style={{ background: 'rgba(99,102,241,0.12)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.2)' }}>
                    REFERENCE ONLY
                  </span>
                  <span className="text-[9px] font-bold px-2 py-1 rounded"
                    style={{ background: 'rgba(248,113,113,0.1)', color: '#f87171', border: '1px solid rgba(248,113,113,0.2)' }}>
                    NOT USED FOR VENDOR MATCHING
                  </span>
                </div>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ background: 'rgba(99,102,241,0.05)' }}>
                    {['#', 'Parameter', 'Value', 'Source'].map(h => (
                      <th key={h} className="text-left px-4 py-2 font-semibold" style={{ color: '#818cf8', fontSize: 10 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {projectInfo.length === 0 && (
                    <tr><td colSpan={4} className="px-4 py-4 text-center text-xs" style={{ color: 'var(--t2)', opacity: 0.5 }}>No project information fields extracted</td></tr>
                  )}
                  {projectInfo.map((row, i) => (
                    <tr key={i} style={{ borderTop: '1px solid rgba(99,102,241,0.08)', background: i % 2 ? 'rgba(99,102,241,0.03)' : 'transparent' }}>
                      <td className="px-4 py-2 opacity-40 w-8" style={{ color: '#818cf8' }}>{i + 1}</td>
                      <td className="px-4 py-2 font-medium" style={{ color: '#c7d2fe' }}>{row.param}</td>
                      <td className="px-2 py-1.5">
                        {piEditingIdx === i ? (
                          <input
                            autoFocus
                            className="w-full px-2 py-1 rounded-lg text-xs"
                            style={{ background: 'var(--s0)', border: '1px solid rgba(99,102,241,0.4)', color: 'var(--t0)', outline: 'none' }}
                            value={row.value}
                            onChange={e => setProjectInfo(prev => prev.map((r, j) => j === i ? { ...r, value: e.target.value } : r))}
                            onBlur={() => setPiEditingIdx(null)}
                          />
                        ) : (
                          <span className="cursor-pointer block px-2 py-1 rounded hover:bg-[rgba(99,102,241,0.08)]"
                            style={{ color: 'var(--t1)' }}
                            onClick={() => setPiEditingIdx(i)}>
                            {row.value}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2">
                        {row.resolved
                          ? <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: 'rgba(74,222,128,0.1)', color: '#4ade80' }}>✓ {row.source}</span>
                          : <span className="text-[9px] opacity-40" style={{ color: 'var(--t2)' }}>{row.source}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Section B – Technical Requirement Database */}
            <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid rgba(59,130,246,0.3)', background: 'rgba(59,130,246,0.02)' }}>
              <div className="flex items-center justify-between px-4 py-3"
                style={{ background: 'rgba(59,130,246,0.08)', borderBottom: '1px solid rgba(59,130,246,0.15)' }}>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold px-2.5 py-1 rounded-full"
                    style={{ background: 'rgba(59,130,246,0.15)', color: '#60a5fa' }}>Part B</span>
                  <span className="text-sm font-bold" style={{ color: '#60a5fa' }}>Technical Requirement Database</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[9px] font-bold px-2 py-1 rounded"
                    style={{ background: 'rgba(74,222,128,0.1)', color: '#4ade80', border: '1px solid rgba(74,222,128,0.2)' }}>
                    USED FOR VENDOR MATCHING
                  </span>
                  <span className="text-[9px] font-bold px-2 py-1 rounded"
                    style={{ background: 'rgba(74,222,128,0.08)', color: '#4ade80', border: '1px solid rgba(74,222,128,0.15)' }}>
                    100% WEIGHT
                  </span>
                  <button onClick={addSpec}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold"
                    style={{ background: 'var(--s2)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
                    <Plus className="w-3 h-3" /> Add Requirement
                  </button>
                </div>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ background: 'rgba(59,130,246,0.05)' }}>
                    <th className="text-left px-3 py-2 font-semibold w-8" style={{ color: '#60a5fa', fontSize: 10 }}>#</th>
                    <th className="text-left px-3 py-2 font-semibold" style={{ color: '#60a5fa', fontSize: 10 }}>Parameter</th>
                    <th className="text-left px-3 py-2 font-semibold" style={{ color: '#60a5fa', fontSize: 10 }}>Value / Requirement</th>
                    <th className="text-left px-3 py-2 font-semibold w-20" style={{ color: '#60a5fa', fontSize: 10 }}>Source</th>
                    <th className="w-10" />
                  </tr>
                </thead>
                <tbody>
                  {editedSpecs.length === 0 && (
                    <tr><td colSpan={5} className="px-4 py-4 text-center text-xs" style={{ color: 'var(--t2)', opacity: 0.5 }}>No technical requirements extracted — add them manually</td></tr>
                  )}
                  {editedSpecs.map((row, i) => {
                    const isEditing = editingIdx === i;
                    return (
                      <tr key={i} style={{ borderTop: '1px solid rgba(59,130,246,0.07)', background: i % 2 ? 'rgba(59,130,246,0.03)' : 'transparent' }}>
                        <td className="px-3 py-2 opacity-40" style={{ color: '#60a5fa' }}>{i + 1}</td>
                        <td className="px-2 py-1.5">
                          {isEditing ? (
                            <input
                              autoFocus
                              className="w-full px-2 py-1.5 rounded-lg text-xs"
                              style={{ background: 'var(--s0)', border: '1px solid var(--em)', color: 'var(--t0)', outline: 'none', minWidth: 140 }}
                              value={row.param}
                              onChange={e => updateSpec(i, 'param', e.target.value)}
                              onBlur={() => setEditingIdx(null)}
                            />
                          ) : (
                            <span className="cursor-pointer font-medium block px-2 py-1.5 rounded hover:bg-[rgba(59,130,246,0.06)]"
                              style={{ color: 'var(--t0)' }}
                              onClick={() => setEditingIdx(i)}>
                              {row.param || <span className="opacity-30 italic">Click to edit</span>}
                            </span>
                          )}
                        </td>
                        <td className="px-2 py-1.5">
                          <input
                            className="w-full px-2 py-1.5 rounded-lg text-xs"
                            style={{ background: isEditing ? 'var(--s0)' : 'transparent', border: `1px solid ${isEditing ? 'var(--em)' : 'transparent'}`, color: 'var(--t1)', outline: 'none', minWidth: 160 }}
                            value={row.value}
                            onChange={e => updateSpec(i, 'value', e.target.value)}
                            onFocus={() => setEditingIdx(i)}
                            onBlur={() => setEditingIdx(null)}
                          />
                        </td>
                        <td className="px-3 py-2">
                          <span className="text-[9px] px-1.5 py-0.5 rounded" style={{
                            background: row.resolved ? 'rgba(74,222,128,0.1)' : 'var(--s3)',
                            color: row.resolved ? '#4ade80' : 'var(--t2)',
                          }}>
                            {row.source}
                          </span>
                        </td>
                        <td className="px-2 py-2">
                          <button onClick={() => deleteSpec(i)}
                            className="p-1 rounded hover:bg-red-500/10 transition-colors">
                            <Trash2 className="w-3.5 h-3.5" style={{ color: '#f87171', opacity: 0.6 }} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="px-4 py-2.5 flex items-center justify-between"
                style={{ borderTop: '1px solid rgba(59,130,246,0.1)', background: 'rgba(59,130,246,0.04)' }}>
                <span className="text-[10px]" style={{ color: 'var(--t2)' }}>
                  {editedSpecs.filter(s => s.param && s.value).length} requirements · Vendor matching weight: 100%
                </span>
                <span className="text-[10px]" style={{ color: '#f87171' }}>
                  Part A & Part C are excluded from vendor analysis
                </span>
              </div>
            </div>

            {/* Section C – Annexure-resolved specs */}
            {annexureSpecs.length > 0 && (
              <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid rgba(20,184,166,0.25)', background: 'rgba(20,184,166,0.02)' }}>
                <div className="flex items-center justify-between px-4 py-3"
                  style={{ background: 'rgba(20,184,166,0.08)', borderBottom: '1px solid rgba(20,184,166,0.15)' }}>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold px-2.5 py-1 rounded-full"
                      style={{ background: 'rgba(20,184,166,0.15)', color: '#2dd4bf' }}>Part C</span>
                    <span className="text-sm font-bold" style={{ color: '#2dd4bf' }}>Annexure Specifications</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] font-bold px-2 py-1 rounded"
                      style={{ background: 'rgba(20,184,166,0.1)', color: '#2dd4bf', border: '1px solid rgba(20,184,166,0.2)' }}>
                      VALUES FROM ANNEXURE SHEET
                    </span>
                    <span className="text-[9px] font-bold px-2 py-1 rounded"
                      style={{ background: 'rgba(248,113,113,0.1)', color: '#f87171', border: '1px solid rgba(248,113,113,0.2)' }}>
                      NOT USED FOR VENDOR MATCHING
                    </span>
                  </div>
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr style={{ background: 'rgba(20,184,166,0.05)' }}>
                      {['#', 'Parameter', 'Value (from Annexure)', 'Annexure Source'].map(h => (
                        <th key={h} className="text-left px-4 py-2 font-semibold" style={{ color: '#2dd4bf', fontSize: 10 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {annexureSpecs.map((row, i) => (
                      <tr key={i} style={{ borderTop: '1px solid rgba(20,184,166,0.08)', background: i % 2 ? 'rgba(20,184,166,0.03)' : 'transparent' }}>
                        <td className="px-4 py-2 opacity-40 w-8" style={{ color: '#2dd4bf' }}>{i + 1}</td>
                        <td className="px-4 py-2 font-medium" style={{ color: '#99f6e4' }}>{row.param}</td>
                        <td className="px-4 py-2 font-semibold" style={{ color: 'var(--t0)' }}>{row.value}</td>
                        <td className="px-4 py-2">
                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded"
                            style={{ background: 'rgba(20,184,166,0.12)', color: '#2dd4bf' }}>
                            ✓ {row.source || 'Annexure'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="px-4 py-2.5" style={{ borderTop: '1px solid rgba(20,184,166,0.1)', background: 'rgba(20,184,166,0.04)' }}>
                  <span className="text-[10px]" style={{ color: 'var(--t2)' }}>
                    {annexureSpecs.length} specifications resolved from Annexure · Displayed for reference only
                  </span>
                </div>
              </div>
            )}
          </div>
        )}


        {/* ── VENDOR SELECTION ── */}
        {step === 'vendor_select' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>
                Standard shortlist ({vendors.length} vendors) · Match % against {editedSpecs.filter(s => s.param && s.value).length} Part B technical requirements
              </p>
              <button onClick={buildTBE} disabled={selectedVendors.size === 0}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold"
                style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff', opacity: selectedVendors.size ? 1 : 0.4 }}>
                Build TBE Table <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3">
              {vendors.map((v, i) => {
                const sel = selectedVendors.has(v.abbr);
                const srs = v.spec_results;
                const complies = srs.filter(r => r.status === 'COMPLIES' || r.status === 'EXCEEDS REQUIREMENT').length;
                const notAcc = srs.filter(r => r.status === 'NOT ACCEPTABLE').length;
                const devs = srs.filter(r => r.status === 'DEVIATION').length;
                return (
                  <div key={v.abbr}
                    className="rounded-2xl p-4 cursor-pointer transition-all"
                    style={{ border: `1px solid ${sel ? 'rgba(59,130,246,0.4)' : 'var(--b1)'}`, background: sel ? 'rgba(59,130,246,0.04)' : 'var(--s1)' }}
                    onClick={() => setSelectedVendors(prev => {
                      const n = new Set(prev);
                      if (n.has(v.abbr)) n.delete(v.abbr); else n.add(v.abbr);
                      return n;
                    })}>
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center font-black text-xs flex-shrink-0"
                        style={{ background: sel ? 'var(--em-dim)' : 'var(--s2)', color: sel ? 'var(--em-lt)' : 'var(--t2)' }}>
                        {i === 0 ? <Star className="w-4 h-4" style={{ color: '#fbbf24' }} /> : i + 1}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>{v.vendor}</span>
                          <span className="text-xs px-2 py-0.5 rounded font-semibold" style={{ background: 'var(--s2)', color: 'var(--t2)' }}>{v.model}</span>
                          {i === 0 && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: 'rgba(245,158,11,0.1)', color: '#fbbf24' }}>RECOMMENDED</span>}
                        </div>
                        <MatchBar pct={v.match_pct} />
                        <div className="flex gap-3 mt-1.5 text-[10px]" style={{ color: 'var(--t2)' }}>
                          <span style={{ color: '#4ade80' }}>✓ {complies}/{srs.length} compliant</span>
                          {devs > 0 && <span style={{ color: '#fbbf24' }}>⚠ {devs} deviation{devs > 1 ? 's' : ''}</span>}
                          {notAcc > 0 && <span style={{ color: '#ef4444' }}>✗ {notAcc} not acceptable</span>}
                        </div>
                      </div>
                      <div className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0"
                        style={{ border: `2px solid ${sel ? 'var(--em)' : 'var(--b2)'}`, background: sel ? 'var(--em)' : 'transparent' }}>
                        {sel && <CheckCircle2 className="w-3 h-3 text-white" />}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ── TBE TABLE ── */}
        {step === 'tbe_table' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-3 flex-wrap text-xs" style={{ color: 'var(--t2)' }}>
                <span className="px-2 py-0.5 rounded font-semibold" style={{ background: 'rgba(255,249,196,0.1)', color: '#fbbf24', border: '1px solid rgba(255,249,196,0.15)' }}>Yellow = WABAG Reply (editable)</span>
                <span className="px-2 py-0.5 rounded font-semibold" style={{ background: 'rgba(248,113,113,0.1)', color: '#f87171', border: '1px solid rgba(248,113,113,0.15)' }}>Red = deviation severity</span>
              </div>
              <button onClick={generateReports}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold"
                style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
                Generate Reports <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            <div className="overflow-x-auto rounded-2xl" style={{ border: '1px solid var(--b1)' }}>
              <table className="w-full text-xs min-w-max">
                <thead>
                  <tr style={{ background: '#1e3a5f' }}>
                    <th className="text-left px-3 py-2.5 text-white font-bold w-8 sticky left-0" style={{ background: '#1e3a5f' }}>#</th>
                    <th className="text-left px-3 py-2.5 text-white font-bold min-w-[150px] sticky left-8" style={{ background: '#1e3a5f' }}>Specification</th>
                    <th className="text-left px-3 py-2.5 text-white font-bold min-w-[140px]">WABAG Requirement</th>
                    {activeVendors.map(v => (
                      <th key={`${v.abbr}-h`} colSpan={3}
                        className="text-center px-3 py-2.5 text-white font-bold min-w-[120px]"
                        style={{ background: '#1e3a5f', borderLeft: '2px solid rgba(255,255,255,0.1)' }}>
                        {v.abbr} — {v.model}
                      </th>
                    ))}
                  </tr>
                  <tr style={{ background: '#162d4a' }}>
                    <th colSpan={3} />
                    {activeVendors.map(v => (
                      <>
                        <th key={`${v.abbr}-oh`} className="text-left px-3 py-2 text-white font-semibold min-w-[130px]" style={{ fontSize: 9, borderLeft: '2px solid rgba(255,255,255,0.1)' }}>Vendor Offer</th>
                        <th key={`${v.abbr}-rh`} className="text-left px-3 py-2 font-semibold min-w-[140px]" style={{ fontSize: 9, color: '#fbbf24', background: 'rgba(245,158,11,0.15)' }}>WABAG Reply</th>
                        <th key={`${v.abbr}-sh`} className="text-left px-3 py-2 font-semibold min-w-[90px]" style={{ fontSize: 9, color: '#f87171', background: 'rgba(248,113,113,0.08)' }}>Severity</th>
                      </>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {allParams.map((param, ri) => {
                    const wabag = activeVendors[0]?.spec_results.find(r => r.param === param)?.wabag_req || '';
                    return (
                      <tr key={param} style={{ borderTop: '1px solid var(--b0)', background: ri % 2 ? 'var(--s1)' : 'transparent' }}>
                        <td className="px-3 py-2 opacity-40 sticky left-0" style={{ color: 'var(--t2)', background: ri % 2 ? 'var(--s1)' : 'var(--s0)' }}>{ri + 1}</td>
                        <td className="px-3 py-2 font-medium sticky left-8" style={{ color: 'var(--t0)', background: ri % 2 ? 'var(--s1)' : 'var(--s0)' }}>{param}</td>
                        <td className="px-3 py-2" style={{ color: 'var(--t1)' }}>{wabag}</td>
                        {activeVendors.map(v => {
                          const sr = v.spec_results.find(r => r.param === param);
                          const status = sr?.status || 'CLARIFICATION REQUIRED';
                          const meta = STATUS_META[status] || STATUS_META['CLARIFICATION REQUIRED'];
                          const isNonCompliant = status !== 'COMPLIES';
                          return (
                            <>
                              <td key={`${v.abbr}-o`} className="px-3 py-2"
                                style={{ background: meta.bg, borderLeft: '2px solid rgba(255,255,255,0.04)' }}>
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <span style={{ color: 'var(--t1)' }}>{sr?.vendor_offer || '—'}</span>
                                  <StatusChip status={status} />
                                </div>
                              </td>
                              <td key={`${v.abbr}-r`} className="px-2 py-1.5" style={{ background: 'rgba(255,249,196,0.06)' }}>
                                <input
                                  type="text"
                                  className="w-full px-2 py-1.5 rounded-lg text-xs"
                                  style={{ background: 'rgba(255,249,196,0.08)', border: '1px solid rgba(245,158,11,0.15)', color: 'var(--t0)', outline: 'none', minWidth: 130 }}
                                  value={tbeReplies[v.abbr]?.[param] || ''}
                                  onChange={e => setTbeReplies(prev => ({ ...prev, [v.abbr]: { ...prev[v.abbr], [param]: e.target.value } }))}
                                />
                              </td>
                              <td key={`${v.abbr}-sev`} className="px-2 py-1.5" style={{ background: 'rgba(248,113,113,0.04)' }}>
                                {isNonCompliant ? (
                                  <select
                                    className="w-full px-2 py-1.5 rounded-lg text-[10px] font-semibold"
                                    style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: '#f87171', outline: 'none', minWidth: 80 }}
                                    value={devSeverities[v.abbr]?.[param] || meta.severity || 'Minor'}
                                    onChange={e => setDevSeverities(prev => ({ ...prev, [v.abbr]: { ...prev[v.abbr], [param]: e.target.value } }))}
                                  >
                                    {SEVERITY_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                                  </select>
                                ) : (
                                  <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: 'rgba(74,222,128,0.08)', color: '#4ade80' }}>—</span>
                                )}
                              </td>
                            </>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── DASHBOARD ── */}
        {step === 'dashboard' && (
          <div className="space-y-5">
            {/* Summary cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: 'Total Specs', value: allParams.length, icon: FileSpreadsheet, color: 'var(--em-lt)' },
                { label: 'Avg Compliance', value: `${Math.round(activeVendors.reduce((s, v) => s + v.match_pct, 0) / (activeVendors.length || 1))}%`, icon: TrendingUp, color: '#4ade80' },
                { label: 'Best Vendor', value: bestVendor?.abbr || '—', icon: Star, color: '#fbbf24' },
                { label: 'Critical Deviations', value: activeVendors.reduce((s, v) => s + v.spec_results.filter(r => r.status === 'NOT ACCEPTABLE').length, 0), icon: AlertCircle, color: '#ef4444' },
              ].map(c => (
                <div key={c.label} className="rounded-2xl p-4" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
                  <c.icon className="w-4 h-4 mb-2" style={{ color: c.color }} />
                  <p className="text-lg font-black" style={{ color: c.color }}>{c.value}</p>
                  <p className="text-[10px] mt-0.5" style={{ color: 'var(--t2)' }}>{c.label}</p>
                </div>
              ))}
            </div>

            {/* Vendor table */}
            <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid var(--b1)' }}>
              <div className="px-4 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid var(--b1)', background: 'var(--s1)' }}>
                <BarChart2 className="w-4 h-4" style={{ color: 'var(--em)' }} />
                <span className="text-xs font-bold" style={{ color: 'var(--t0)' }}>Compliance Overview</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr style={{ background: 'var(--s2)' }}>
                      {['Vendor', 'Model', 'Compliance', 'Complies', 'Exceeds', 'Deviations', 'Clarif.', 'Not Acceptable'].map(h => (
                        <th key={h} className="text-left px-4 py-2.5 font-semibold whitespace-nowrap" style={{ color: 'var(--t2)' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {activeVendors.map((v, i) => {
                      const sr = v.spec_results;
                      return (
                        <tr key={v.abbr} style={{ borderTop: '1px solid var(--b0)', background: i === 0 ? 'rgba(245,158,11,0.03)' : 'transparent' }}>
                          <td className="px-4 py-3 font-semibold" style={{ color: 'var(--t0)' }}>
                            {v.vendor} {i === 0 && <Award className="w-3 h-3 inline ml-1" style={{ color: '#fbbf24' }} />}
                          </td>
                          <td className="px-4 py-3" style={{ color: 'var(--t2)' }}>{v.model}</td>
                          <td className="px-4 py-3 min-w-[120px]"><MatchBar pct={v.match_pct} /></td>
                          <td className="px-4 py-3 font-bold" style={{ color: '#4ade80' }}>{sr.filter(r => r.status === 'COMPLIES').length}</td>
                          <td className="px-4 py-3 font-bold" style={{ color: '#60a5fa' }}>{sr.filter(r => r.status === 'EXCEEDS REQUIREMENT').length}</td>
                          <td className="px-4 py-3 font-bold" style={{ color: '#fbbf24' }}>{sr.filter(r => r.status === 'DEVIATION').length}</td>
                          <td className="px-4 py-3 font-bold" style={{ color: '#fbbf24' }}>{sr.filter(r => r.status === 'CLARIFICATION REQUIRED').length}</td>
                          <td className="px-4 py-3 font-bold" style={{ color: '#ef4444' }}>{sr.filter(r => r.status === 'NOT ACCEPTABLE').length}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Recommendation */}
            {bestVendor && (
              <div className="rounded-2xl p-5" style={{ background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.2)' }}>
                <div className="flex items-center gap-2 mb-3">
                  <Award className="w-4 h-4" style={{ color: '#fbbf24' }} />
                  <span className="text-xs font-bold" style={{ color: '#fbbf24' }}>RECOMMENDED VENDOR</span>
                </div>
                <p className="text-lg font-black mb-1" style={{ color: 'var(--t0)' }}>
                  {bestVendor.vendor} — {bestVendor.model}
                </p>
                <p className="text-xs" style={{ color: 'var(--t2)' }}>
                  Highest compliance score ({bestVendor.match_pct}%) among evaluated vendors.
                  {bestVendor.spec_results.filter(r => r.status === 'NOT ACCEPTABLE').length === 0
                    ? ' No critical deviations detected.'
                    : ` ${bestVendor.spec_results.filter(r => r.status === 'NOT ACCEPTABLE').length} item(s) flagged as not acceptable — review before finalizing.`}
                </p>
              </div>
            )}

            <button onClick={() => setStep('approval')}
              className="w-full py-3.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
              style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
              <ShieldCheck className="w-4 h-4" /> Submit for Approval
            </button>
          </div>
        )}

        {/* ── APPROVAL ── */}
        {step === 'approval' && (
          <div className="max-w-md mx-auto space-y-4">
            <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--s1)', border: '1px solid var(--b2)' }}>
              <div className="px-6 py-5 flex items-center gap-3" style={{ borderBottom: '1px solid var(--b1)' }}>
                <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.2)' }}>
                  <ShieldCheck className="w-4 h-4" style={{ color: 'var(--em-lt)' }} />
                </div>
                <div>
                  <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Submit TBE for Approval</p>
                  <p className="text-xs" style={{ color: 'var(--t2)' }}>Request will go to Lead Engineer / Admin for review</p>
                </div>
              </div>

              {bestVendor && (
                <div className="px-6 py-3" style={{ background: 'rgba(245,158,11,0.06)', borderBottom: '1px solid var(--b1)' }}>
                  <p className="text-xs" style={{ color: 'var(--t2)' }}>
                    Recommended: <strong style={{ color: '#fbbf24' }}>{bestVendor.vendor} — {bestVendor.model}</strong> ({bestVendor.match_pct}% match)
                  </p>
                </div>
              )}

              {approvalStatus === 'idle' && (
                <form onSubmit={submitApproval} className="p-6 space-y-4">
                  <div className="rounded-xl px-4 py-3 text-xs" style={{ background: 'var(--s2)', color: 'var(--t2)' }}>
                    Submitting as: <strong style={{ color: 'var(--t0)' }}>
                      {localStorage.getItem('user_employee_name') || '—'}
                    </strong> ({localStorage.getItem('user_employee_id') || '—'})
                  </div>
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Notes for Reviewer (optional)</label>
                    <textarea rows={3} value={tbeNotes} onChange={e => setTbeNotes(e.target.value)}
                      placeholder="Any notes or context for the Lead Engineer…"
                      className="w-full px-3 py-2.5 rounded-xl text-sm resize-none"
                      style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                  </div>
                  <button type="submit" disabled={approving}
                    className="w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
                    style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff', opacity: approving ? 0.6 : 1 }}>
                    {approving ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                    {approving ? 'Submitting…' : 'Submit for Lead Engineer Approval'}
                  </button>
                </form>
              )}

              {approvalStatus === 'pending' && (
                <div className="p-6 flex flex-col items-center gap-4">
                  <Loader2 className="w-8 h-8 animate-spin" style={{ color: 'var(--em)' }} />
                  <div className="text-center">
                    <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>Awaiting Lead Engineer Approval</p>
                    <p className="text-xs mt-1" style={{ color: 'var(--t2)' }}>
                      Request #{approvalReqId} submitted · Lead Engineer will approve from the Approval Queue
                    </p>
                  </div>
                  <div className="flex gap-2 flex-wrap justify-center">
                    <span className="text-[10px] px-2.5 py-1 rounded-full font-semibold"
                      style={{ background: 'rgba(245,158,11,0.1)', color: '#fbbf24', border: '1px solid rgba(245,158,11,0.2)' }}>
                      Checking every 12 s…
                    </span>
                  </div>
                </div>
              )}

              {approvalStatus === 'rejected' && (
                <div className="p-6 text-center space-y-3">
                  <AlertTriangle className="w-8 h-8 mx-auto" style={{ color: '#f87171' }} />
                  <p className="text-sm font-semibold" style={{ color: '#f87171' }}>Approval Rejected</p>
                  <p className="text-xs" style={{ color: 'var(--t2)' }}>The Lead Engineer has rejected this TBE. Review feedback in the Approval Queue and resubmit.</p>
                  <button onClick={() => { setApprovalStatus('idle'); setTbeNotes(''); }}
                    className="px-4 py-2 rounded-xl text-xs font-bold"
                    style={{ background: 'var(--s2)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>
                    Revise & Resubmit
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── DONE / DOWNLOAD ── */}
        {step === 'done' && approvalResult && (
          <div className="max-w-lg mx-auto space-y-5">
            <div className="rounded-2xl p-6 text-center" style={{ background: 'rgba(74,222,128,0.08)', border: '1px solid rgba(74,222,128,0.2)' }}>
              <CheckCircle2 className="w-12 h-12 mx-auto mb-3" style={{ color: '#4ade80' }} />
              <p className="text-base font-black mb-1" style={{ color: 'var(--t0)' }}>TBE Approved</p>
              <p className="text-xs" style={{ color: 'var(--t2)' }}>
                {approvalResult.tbe_number} · Approved by {approvalResult.approved_by} ({approvalResult.employee_id})
              </p>
            </div>

            <div className="space-y-3">
              {[
                { type: 'tbe' as const, label: 'Download TBE Report', desc: 'Full Technical Bid Evaluation with all vendors', color: 'var(--em-lt)' },
                { type: 'deviation' as const, label: 'Download Deviation Report', desc: 'Deviations, clarifications, not-acceptable items with severity', color: '#f87171' },
                { type: 'compliance' as const, label: 'Download Compliance Summary', desc: 'Scorecard + Recommended Vendor sheet', color: '#4ade80' },
              ].map(btn => (
                <button key={btn.type} onClick={() => downloadFile(btn.type)}
                  className="w-full flex items-center gap-3 px-5 py-4 rounded-xl text-left transition-all"
                  style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}
                  onMouseEnter={e => (e.currentTarget.style.borderColor = btn.color)}
                  onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--b1)')}>
                  <Download className="w-5 h-5 flex-shrink-0" style={{ color: btn.color }} />
                  <div>
                    <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>{btn.label}</p>
                    <p className="text-xs" style={{ color: 'var(--t2)' }}>{btn.desc}</p>
                  </div>
                </button>
              ))}
            </div>

            <button onClick={reset}
              className="w-full flex items-center justify-center gap-2 py-3 rounded-xl text-sm font-semibold"
              style={{ background: 'var(--s2)', color: 'var(--t1)', border: '1px solid var(--b1)' }}>
              <RefreshCw className="w-4 h-4" /> Start New TBE
            </button>
          </div>
        )}

      </div>
      </>}
    </div>
  );
}
