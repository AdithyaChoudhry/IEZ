/**
 * Vendor Analysis & Technical Bid Evaluation (TBE) Module
 */
import { useState, useRef, useCallback } from 'react';
import {
  FileSpreadsheet, CheckCircle2, AlertTriangle,
  Loader2, BarChart2, Download, ShieldCheck, ChevronRight,
  Star, TrendingUp, AlertCircle, Award, RefreshCw,
} from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';

// ── types ──────────────────────────────────────────────────────────────────────
interface SpecRow { param: string; value: string; source: string; resolved: boolean; }
interface SpecResult { param: string; wabag_req: string; vendor_offer: string; status: string; auto_reply: string; }
interface VendorResult { vendor: string; abbr: string; model: string; match_pct: number; spec_results: SpecResult[]; }
interface AnalysisResult {
  instrument_type: string; tag_numbers: string[]; specs: SpecRow[];
  sheet_names: string[]; annexure_sheets: string[];
}

type Step = 'upload' | 'analyzing' | 'requirements' | 'matching' | 'vendor_select'
          | 'tbe_table' | 'generating' | 'dashboard' | 'approval' | 'done';

const STATUS_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  'COMPLIES':               { bg: 'rgba(74,222,128,0.12)', text: '#4ade80',       label: 'COMPLIES' },
  'EXCEEDS REQUIREMENT':    { bg: 'rgba(59,130,246,0.12)',  text: 'var(--em-lt)', label: 'EXCEEDS' },
  'DEVIATION':              { bg: 'rgba(248,113,113,0.12)', text: 'var(--rose)',  label: 'DEVIATION' },
  'CLARIFICATION REQUIRED': { bg: 'rgba(245,158,11,0.12)',  text: 'var(--gold)', label: 'CLARIF.' },
};

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_COLORS[status] || { bg: 'var(--s2)', text: 'var(--t2)', label: status };
  return (
    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded whitespace-nowrap"
      style={{ background: s.bg, color: s.text }}>
      {s.label}
    </span>
  );
}

function MatchBar({ pct }: { pct: number }) {
  const color = pct >= 90 ? '#4ade80' : pct >= 75 ? 'var(--gold)' : 'var(--rose)';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full" style={{ background: 'var(--s3)' }}>
        <div className="h-1.5 rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-xs font-bold w-9 text-right" style={{ color }}>{pct}%</span>
    </div>
  );
}

// ── main component ─────────────────────────────────────────────────────────────
export default function VendorTBE() {
  const [step, setStep] = useState<Step>('upload');
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [vendors, setVendors] = useState<VendorResult[]>([]);
  const [selectedVendors, setSelectedVendors] = useState<Set<string>>(new Set());
  const [tbeReplies, setTbeReplies] = useState<Record<string, Record<string, string>>>({});
  const [sessionId, setSessionId] = useState('');
  const [approvalResult, setApprovalResult] = useState<any>(null);
  const [empId, setEmpId] = useState('');
  const [empPass, setEmpPass] = useState('');
  const [approving, setApproving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const reset = () => {
    setStep('upload'); setFile(null); setError(''); setAnalysis(null);
    setVendors([]); setSelectedVendors(new Set()); setTbeReplies({});
    setSessionId(''); setApprovalResult(null); setEmpId(''); setEmpPass('');
  };

  // ── file selection ──
  const handleFile = (f: File) => {
    if (!f.name.match(/\.(xlsx|xlsm)$/i)) { setError('Only .xlsx / .xlsm files are supported'); return; }
    setFile(f); setError('');
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0]; if (f) handleFile(f);
  }, []);

  // ── Step 1 → 2: analyze ──
  const runAnalysis = async () => {
    if (!file) return;
    setStep('analyzing'); setError('');
    const fd = new FormData(); fd.append('file', file);
    try {
      const r = await api.post('/tbe/analyze', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setAnalysis(r.data);
      setStep('requirements');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Analysis failed');
      setStep('upload');
    }
  };

  // ── Step 3 → 4: match vendors ──
  const runMatching = async () => {
    if (!analysis) return;
    setStep('matching'); setError('');
    try {
      const r = await api.post('/tbe/match', {
        instrument_type: analysis.instrument_type,
        specs: analysis.specs,
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

  // ── Step 5 → 6: build TBE table ──
  const buildTBE = () => {
    const active = vendors.filter(v => selectedVendors.has(v.abbr));
    // init replies from auto_reply
    const replies: Record<string, Record<string, string>> = {};
    for (const v of active) {
      replies[v.abbr] = {};
      for (const sr of v.spec_results) {
        replies[v.abbr][sr.param] = sr.auto_reply;
      }
    }
    setTbeReplies(replies);
    setStep('tbe_table');
  };

  // ── Step 6 → 7: generate Excel ──
  const generateReports = async () => {
    setStep('generating'); setError('');
    const active = vendors.filter(v => selectedVendors.has(v.abbr));
    try {
      const r = await api.post('/tbe/generate', {
        instrument_type: analysis?.instrument_type,
        vendors: active,
        tbe_replies: tbeReplies,
      });
      setSessionId(r.data.session_id);
      setStep('dashboard');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Report generation failed');
      setStep('tbe_table');
    }
  };

  // ── Step 8: approve ──
  const submitApproval = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setApproving(true);
    const best = vendors.filter(v => selectedVendors.has(v.abbr)).sort((a, b) => b.match_pct - a.match_pct)[0];
    try {
      const r = await api.post('/tbe/approve', {
        session_id: sessionId,
        employee_id: empId,
        password: empPass,
        instrument_type: analysis?.instrument_type || '',
        recommended_vendor: best?.vendor || '',
        recommended_model: best?.model || '',
      });
      setApprovalResult(r.data);
      setStep('done');
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Approval failed');
    } finally { setApproving(false); }
  };

  const downloadFile = (type: 'tbe' | 'deviation' | 'compliance') => {
    const token = localStorage.getItem('access_token');
    const a = document.createElement('a');
    a.href = `/api/tbe/download/${sessionId}/${type}`;
    // append token as query won't work with FileResponse easily, use fetch+blob instead
    fetch(`/api/tbe/download/${sessionId}/${type}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then(res => res.blob()).then(blob => {
      const names = { tbe: 'TBE_Report.xlsx', deviation: 'Deviation_Report.xlsx', compliance: 'Compliance_Summary.xlsx' };
      const url = URL.createObjectURL(blob);
      a.href = url; a.download = names[type]; a.click(); URL.revokeObjectURL(url);
    }).catch(() => setError('Download failed'));
  };

  const activeVendors = vendors.filter(v => selectedVendors.has(v.abbr));
  const bestVendor = [...activeVendors].sort((a, b) => b.match_pct - a.match_pct)[0];

  const allParams = activeVendors[0]?.spec_results.map(r => r.param) || [];

  // ── step bar ──
  const STEPS = [
    { key: 'upload',       label: 'Upload' },
    { key: 'requirements', label: 'Requirements' },
    { key: 'vendor_select',label: 'Vendor Selection' },
    { key: 'tbe_table',    label: 'TBE Table' },
    { key: 'dashboard',    label: 'Dashboard' },
    { key: 'approval',     label: 'Approval' },
    { key: 'done',         label: 'Download' },
  ];
  const stepIdx = STEPS.findIndex(s => s.key === step);

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--s0)' }}>
      <PageHeader
        icon={BarChart2}
        title="Vendor Analysis & TBE"
        description="Upload instrument datasheet · Match vendors · Generate Technical Bid Evaluation"
      />

      {/* Step bar */}
      <div className="px-6 pt-4 pb-2">
        <div className="flex items-center gap-0 overflow-x-auto">
          {STEPS.map((s, i) => {
            const done = stepIdx > i;
            const active = stepIdx === i;
            return (
              <div key={s.key} className="flex items-center">
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
                  style={{
                    background: active ? 'var(--em-dim)' : done ? 'rgba(74,222,128,0.08)' : 'transparent',
                  }}>
                  <span className={`text-[10px] font-bold ${active ? '' : done ? '' : 'opacity-40'}`}
                    style={{ color: active ? 'var(--em-lt)' : done ? '#4ade80' : 'var(--t2)' }}>
                    {i + 1}. {s.label}
                  </span>
                  {done && <CheckCircle2 className="w-3 h-3" style={{ color: '#4ade80' }} />}
                </div>
                {i < STEPS.length - 1 && (
                  <ChevronRight className="w-3 h-3 flex-shrink-0 mx-0.5 opacity-30" style={{ color: 'var(--t2)' }} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="mx-6 mt-2 flex items-center gap-2 px-4 py-3 rounded-xl text-sm"
          style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
          <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-6 pb-8 pt-4">

        {/* ── STEP 1: Upload ── */}
        {step === 'upload' && (
          <div className="max-w-2xl mx-auto space-y-6">
            <div
              className="rounded-2xl p-12 text-center cursor-pointer transition-all"
              style={{
                border: `2px dashed ${dragging ? 'var(--em)' : 'var(--b2)'}`,
                background: dragging ? 'var(--em-dim)' : 'var(--s1)',
              }}
              onDragOver={e => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
              onClick={() => fileRef.current?.click()}
            >
              <input ref={fileRef} type="file" accept=".xlsx,.xlsm" className="hidden"
                onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])} />
              <FileSpreadsheet className="w-12 h-12 mx-auto mb-4" style={{ color: 'var(--em-lt)', opacity: 0.7 }} />
              <p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>
                {file ? file.name : 'Drop Instrument Datasheet here'}
              </p>
              <p className="text-xs" style={{ color: 'var(--t2)' }}>
                {file ? `${(file.size / 1024).toFixed(1)} KB · Ready to analyze` : 'Supports .xlsx and .xlsm — Generated or SOP datasheets'}
              </p>
            </div>
            {file && (
              <button onClick={runAnalysis}
                className="w-full py-3.5 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
                style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
                <BarChart2 className="w-4 h-4" /> Analyze Datasheet
              </button>
            )}
          </div>
        )}

        {/* ── STEP: analyzing / matching / generating ── */}
        {(step === 'analyzing' || step === 'matching' || step === 'generating') && (
          <div className="flex flex-col items-center justify-center py-24 gap-4">
            <Loader2 className="w-10 h-10 animate-spin" style={{ color: 'var(--em)' }} />
            <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>
              {step === 'analyzing' && 'Analyzing datasheet & resolving annexures…'}
              {step === 'matching' && 'Matching specifications against vendor database…'}
              {step === 'generating' && 'Generating TBE, Deviation & Compliance reports…'}
            </p>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>This may take a few seconds</p>
          </div>
        )}

        {/* ── STEP 3: Requirements Review ── */}
        {step === 'requirements' && analysis && (
          <div className="space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-3">
                <span className="text-xs font-bold px-3 py-1 rounded-full capitalize"
                  style={{ background: 'var(--em-dim)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.2)' }}>
                  {analysis.instrument_type}
                </span>
                <span className="text-xs" style={{ color: 'var(--t2)' }}>
                  {analysis.tag_numbers.length} sheet(s) · {analysis.specs.length} parameters
                  {analysis.annexure_sheets.length > 0 && ` · ${analysis.annexure_sheets.length} annexure(s)`}
                </span>
              </div>
              <button onClick={runMatching}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold"
                style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff' }}>
                Run Vendor Analysis <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid var(--b1)' }}>
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ background: 'var(--s2)' }}>
                    {['#', 'Parameter', 'WABAG Requirement', 'Source'].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 font-semibold" style={{ color: 'var(--t2)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {analysis.specs.filter(r => r.param && r.value).map((row, i) => (
                    <tr key={i} style={{ borderTop: '1px solid var(--b0)', background: i % 2 ? 'var(--s1)' : 'transparent' }}>
                      <td className="px-4 py-2 opacity-40" style={{ color: 'var(--t2)' }}>{i + 1}</td>
                      <td className="px-4 py-2 font-medium" style={{ color: 'var(--t0)' }}>{row.param}</td>
                      <td className="px-4 py-2" style={{ color: 'var(--t1)' }}>{row.value}</td>
                      <td className="px-4 py-2">
                        {row.resolved
                          ? <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: 'rgba(74,222,128,0.1)', color: '#4ade80' }}>✓ {row.source}</span>
                          : <span className="text-[9px] opacity-50" style={{ color: 'var(--t2)' }}>{row.source}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── STEP 5: Vendor Selection ── */}
        {step === 'vendor_select' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>
                Top {vendors.length} vendors matched — select which to include in TBE
              </p>
              <button onClick={buildTBE} disabled={selectedVendors.size === 0}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold"
                style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff', opacity: selectedVendors.size ? 1 : 0.4 }}>
                Generate TBE <ChevronRight className="w-4 h-4" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-3">
              {vendors.map((v, i) => {
                const sel = selectedVendors.has(v.abbr);
                const complies = v.spec_results.filter(r => r.status === 'COMPLIES').length;
                const devs = v.spec_results.filter(r => r.status === 'DEVIATION').length;
                const total = v.spec_results.length;
                return (
                  <div key={v.abbr}
                    className="rounded-2xl p-4 cursor-pointer transition-all"
                    style={{
                      border: `1px solid ${sel ? 'rgba(59,130,246,0.4)' : 'var(--b1)'}`,
                      background: sel ? 'rgba(59,130,246,0.06)' : 'var(--s1)',
                    }}
                    onClick={() => setSelectedVendors(prev => {
                      const n = new Set(prev);
                      if (n.has(v.abbr)) n.delete(v.abbr); else n.add(v.abbr);
                      return n;
                    })}>
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center font-black text-xs flex-shrink-0"
                        style={{ background: sel ? 'var(--em-dim)' : 'var(--s2)', color: sel ? 'var(--em-lt)' : 'var(--t2)' }}>
                        {i === 0 ? <Star className="w-4 h-4" style={{ color: 'var(--gold)' }} /> : i + 1}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>{v.vendor}</span>
                          <span className="text-xs px-2 py-0.5 rounded font-semibold" style={{ background: 'var(--s2)', color: 'var(--t2)' }}>{v.model}</span>
                          {i === 0 && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded" style={{ background: 'rgba(245,158,11,0.1)', color: 'var(--gold)' }}>RECOMMENDED</span>}
                        </div>
                        <MatchBar pct={v.match_pct} />
                        <div className="flex gap-3 mt-1.5 text-[10px]" style={{ color: 'var(--t2)' }}>
                          <span style={{ color: '#4ade80' }}>✓ {complies}/{total} comply</span>
                          {devs > 0 && <span style={{ color: 'var(--rose)' }}>✗ {devs} deviation{devs > 1 ? 's' : ''}</span>}
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

        {/* ── STEP 6: TBE Table ── */}
        {step === 'tbe_table' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <p className="text-xs" style={{ color: 'var(--t2)' }}>
                <span className="font-semibold px-1.5 py-0.5 rounded mr-2" style={{ background: 'rgba(255,249,196,0.1)', color: 'var(--gold)', border: '1px solid rgba(255,249,196,0.2)' }}>Yellow</span>
                WABAG Reply columns are editable
              </p>
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
                    <th className="text-left px-3 py-2.5 text-white font-bold w-8">#</th>
                    <th className="text-left px-3 py-2.5 text-white font-bold min-w-[150px]">Specification</th>
                    <th className="text-left px-3 py-2.5 text-white font-bold min-w-[140px]">WABAG Requirement</th>
                    {activeVendors.map(v => (
                      <>
                        <th key={`${v.abbr}-o`} className="text-left px-3 py-2.5 text-white font-bold min-w-[140px]">{v.abbr} Offer</th>
                        <th key={`${v.abbr}-r`} className="text-left px-3 py-2.5 font-bold min-w-[150px]" style={{ color: 'var(--gold)', background: 'rgba(245,158,11,0.15)' }}>WABAG Reply ({v.abbr})</th>
                      </>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {allParams.map((param, ri) => {
                    const wabag = activeVendors[0]?.spec_results.find(r => r.param === param)?.wabag_req || '';
                    return (
                      <tr key={param} style={{ borderTop: '1px solid var(--b0)', background: ri % 2 ? 'var(--s1)' : 'transparent' }}>
                        <td className="px-3 py-2 opacity-40" style={{ color: 'var(--t2)' }}>{ri + 1}</td>
                        <td className="px-3 py-2 font-medium" style={{ color: 'var(--t0)' }}>{param}</td>
                        <td className="px-3 py-2" style={{ color: 'var(--t1)' }}>{wabag}</td>
                        {activeVendors.map(v => {
                          const sr = v.spec_results.find(r => r.param === param);
                          const status = sr?.status || 'CLARIFICATION REQUIRED';
                          const sc = STATUS_COLORS[status] || STATUS_COLORS['CLARIFICATION REQUIRED'];
                          return (
                            <>
                              <td key={`${v.abbr}-o`} className="px-3 py-2" style={{ background: sc.bg }}>
                                <div className="flex items-center gap-1.5">
                                  <span style={{ color: 'var(--t1)' }}>{sr?.vendor_offer || '—'}</span>
                                  <StatusBadge status={status} />
                                </div>
                              </td>
                              <td key={`${v.abbr}-r`} className="px-2 py-1.5" style={{ background: 'rgba(255,249,196,0.08)' }}>
                                <input
                                  type="text"
                                  className="w-full px-2 py-1.5 rounded-lg text-xs"
                                  style={{ background: 'rgba(255,249,196,0.1)', border: '1px solid rgba(245,158,11,0.2)', color: 'var(--t0)', outline: 'none', minWidth: 130 }}
                                  value={tbeReplies[v.abbr]?.[param] || ''}
                                  onChange={e => setTbeReplies(prev => ({
                                    ...prev,
                                    [v.abbr]: { ...prev[v.abbr], [param]: e.target.value },
                                  }))}
                                />
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

        {/* ── STEP 7: Dashboard ── */}
        {step === 'dashboard' && (
          <div className="space-y-5">
            {/* Summary cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { label: 'Total Specs', value: allParams.length, icon: FileSpreadsheet, color: 'var(--em-lt)' },
                { label: 'Avg Compliance', value: `${Math.round(activeVendors.reduce((s, v) => s + v.match_pct, 0) / (activeVendors.length || 1))}%`, icon: TrendingUp, color: '#4ade80' },
                { label: 'Best Vendor', value: bestVendor?.abbr || '—', icon: Star, color: 'var(--gold)' },
                { label: 'Total Deviations', value: activeVendors.reduce((s, v) => s + v.spec_results.filter(r => r.status === 'DEVIATION').length, 0), icon: AlertCircle, color: 'var(--rose)' },
              ].map(c => (
                <div key={c.label} className="rounded-2xl p-4" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
                  <c.icon className="w-4 h-4 mb-2" style={{ color: c.color }} />
                  <p className="text-lg font-black" style={{ color: c.color }}>{c.value}</p>
                  <p className="text-[10px] mt-0.5" style={{ color: 'var(--t2)' }}>{c.label}</p>
                </div>
              ))}
            </div>

            {/* Vendor compliance table */}
            <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid var(--b1)' }}>
              <div className="px-4 py-3 flex items-center gap-2" style={{ borderBottom: '1px solid var(--b1)', background: 'var(--s1)' }}>
                <BarChart2 className="w-4 h-4" style={{ color: 'var(--em)' }} />
                <span className="text-xs font-bold" style={{ color: 'var(--t0)' }}>Vendor Compliance Overview</span>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ background: 'var(--s2)' }}>
                    {['Vendor', 'Model', 'Compliance', 'Complies', 'Exceeds', 'Deviations', 'Clarifications'].map(h => (
                      <th key={h} className="text-left px-4 py-2.5 font-semibold" style={{ color: 'var(--t2)' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {activeVendors.map((v, i) => {
                    const sr = v.spec_results;
                    return (
                      <tr key={v.abbr} style={{ borderTop: '1px solid var(--b0)', background: i === 0 ? 'rgba(245,158,11,0.04)' : 'transparent' }}>
                        <td className="px-4 py-3 font-semibold" style={{ color: 'var(--t0)' }}>
                          {v.vendor} {i === 0 && <Award className="w-3 h-3 inline ml-1" style={{ color: 'var(--gold)' }} />}
                        </td>
                        <td className="px-4 py-3" style={{ color: 'var(--t2)' }}>{v.model}</td>
                        <td className="px-4 py-3 min-w-[120px]"><MatchBar pct={v.match_pct} /></td>
                        <td className="px-4 py-3 font-bold" style={{ color: '#4ade80' }}>{sr.filter(r => r.status === 'COMPLIES').length}</td>
                        <td className="px-4 py-3 font-bold" style={{ color: 'var(--em-lt)' }}>{sr.filter(r => r.status === 'EXCEEDS REQUIREMENT').length}</td>
                        <td className="px-4 py-3 font-bold" style={{ color: 'var(--rose)' }}>{sr.filter(r => r.status === 'DEVIATION').length}</td>
                        <td className="px-4 py-3 font-bold" style={{ color: 'var(--gold)' }}>{sr.filter(r => r.status === 'CLARIFICATION REQUIRED').length}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Recommendation */}
            {bestVendor && (
              <div className="rounded-2xl p-5" style={{ background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)' }}>
                <div className="flex items-center gap-2 mb-3">
                  <Award className="w-4 h-4" style={{ color: 'var(--gold)' }} />
                  <span className="text-xs font-bold" style={{ color: 'var(--gold)' }}>RECOMMENDED VENDOR</span>
                </div>
                <p className="text-lg font-black" style={{ color: 'var(--t0)' }}>{bestVendor.vendor} — {bestVendor.model}</p>
                <p className="text-xs mt-1" style={{ color: 'var(--t2)' }}>
                  Highest compliance score ({bestVendor.match_pct}%) among evaluated vendors.
                  {bestVendor.spec_results.filter(r => r.status === 'DEVIATION').length === 0 && ' No critical deviations detected.'}
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

        {/* ── STEP 8: Approval ── */}
        {step === 'approval' && (
          <div className="max-w-md mx-auto">
            <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--s1)', border: '1px solid var(--b2)' }}>
              <div className="px-6 py-5 flex items-center gap-3" style={{ borderBottom: '1px solid var(--b1)' }}>
                <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.2)' }}>
                  <ShieldCheck className="w-4 h-4" style={{ color: 'var(--em-lt)' }} />
                </div>
                <div>
                  <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>TBE Approval</p>
                  <p className="text-xs" style={{ color: 'var(--t2)' }}>Lead Engineer / Admin credentials required</p>
                </div>
              </div>

              {bestVendor && (
                <div className="px-6 py-3 mx-0 my-0" style={{ background: 'rgba(245,158,11,0.06)', borderBottom: '1px solid var(--b1)' }}>
                  <p className="text-xs" style={{ color: 'var(--t2)' }}>
                    Recommending: <strong style={{ color: 'var(--gold)' }}>{bestVendor.vendor} — {bestVendor.model}</strong> ({bestVendor.match_pct}% compliance)
                  </p>
                </div>
              )}

              <form onSubmit={submitApproval} className="p-6 space-y-4">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Employee ID</label>
                  <input type="text" required value={empId} onChange={e => setEmpId(e.target.value)}
                    placeholder="e.g. LEAD001"
                    className="w-full px-3 py-2.5 rounded-xl text-sm"
                    style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Password</label>
                  <input type="password" required value={empPass} onChange={e => setEmpPass(e.target.value)}
                    placeholder="••••••••"
                    className="w-full px-3 py-2.5 rounded-xl text-sm"
                    style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                </div>
                <button type="submit" disabled={approving || !empId || !empPass}
                  className="w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
                  style={{ background: 'linear-gradient(135deg,#22c55e,#16a34a)', color: '#fff', opacity: approving || !empId || !empPass ? 0.5 : 1 }}>
                  {approving ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                  {approving ? 'Validating…' : 'Approve & Finalize TBE'}
                </button>
              </form>
            </div>
          </div>
        )}

        {/* ── STEP 9: Done / Download ── */}
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
                { type: 'tbe' as const, label: 'Download TBE Report', desc: 'Full Technical Bid Evaluation with vendor comparison', color: 'var(--em)' },
                { type: 'deviation' as const, label: 'Download Deviation Report', desc: 'Only deviations, clarifications and exceedances', color: 'var(--rose)' },
                { type: 'compliance' as const, label: 'Download Compliance Summary', desc: 'Overall vendor compliance scorecard', color: '#4ade80' },
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
    </div>
  );
}
