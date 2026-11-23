/**
 * Cable Lug Quantity Generator (sub-module of the Cable Schedule Generator).
 *
 * Generated Cable Schedule (from the Cable Schedule Generator, read on the server) -> live extraction (the table and the errors panel update sheet by sheet while the engine reads the schedule)
 * -> preview tabs -> Excel report. All numbers come from the backend engine.
 *
 * Boundaries shown to the engineer:
 *   - Excel row != physical cable (tag + role + cable block; headers and section rows are ignored);
 *   - core count and lugged conductors are separate (14C with 12 lugged at each end = 24 lugs, core count stays 14);
 *   - cable length is shown but never used for lugs; gland size comes from the cable OD and a manufacturer table, not the cable type.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Info, Loader2 } from 'lucide-react';
import api from '@/services/api';
import Card from '../../ui/Card';
import Button from '../../ui/Button';
import Alert from '../../ui/Alert';
import GeneratedScheduleCard, { handleSourceError, useGeneratedSchedule } from './GeneratedScheduleSource';
import IodbQuantitySource, { IodbSourceHandle } from './IodbQuantitySource';
import { DeliverableDownloads } from '../../ui/DeliverableCover';
import { getCurrentProject } from '@/services/projectContext';

const AUTO = 'Auto — Advisor Recommendation';
const LUG_TYPES = [AUTO, 'Ring Type Lug', 'Fork / Spade Type Lug', 'Pin Type Lug', 'Bootlace Ferrule — Single', 'Bootlace Ferrule — Twin',
  'Tubular Compression Lug', 'Bimetallic Lug', 'Mechanical Lug', 'Blade Type Termination', 'Other / Custom', 'No Lug Required'];
const TERMINALS: [string, string][] = [['UNKNOWN', 'Not stated (advisory only)'], ['PLC_DCS', 'PLC / DCS terminal'], ['SCREW', 'Screw terminal block'],
  ['CAGE_CLAMP', 'Cage-clamp / spring terminal'], ['STUD', 'Bolted stud / busbar']];
const statusColor = (s: string) => (s === 'Manual Review' ? 'text-amber-600' : s === 'Manually selected' ? 'text-blue-500' : s === 'Confirmed from source data' ? 'text-green-600' : '');

type Row = Record<string, any>;
const mp = { headers: { 'Content-Type': 'multipart/form-data' } };
const field = 'w-full border rounded-lg px-2 py-1.5 text-sm';
const fieldStyle = { borderColor: 'var(--b1)', background: 'var(--s1)', color: 'var(--t0)' };
const VIEWS = ['Summary', 'Lug Advisor', 'Extraction', 'Cable Type Summary', 'Gland Recommendation', 'Reconciliation', 'Lug Procurement', 'Errors / Review'] as const;
type View = (typeof VIEWS)[number];

function Table({ columns, rows, empty, cls, max = 'max-h-[26rem]' }: { columns: [string, string][]; rows: Row[]; empty: string; cls?: (r: Row) => string; max?: string }) {
  if (!rows.length) return <p className="text-sm py-3" style={{ color: 'var(--t1)' }}>{empty}</p>;
  return (
    <div className={`overflow-auto ${max} border rounded-lg`} style={{ borderColor: 'var(--b1)' }}>
      <table className="w-full text-xs">
        <thead className="sticky top-0" style={{ background: 'var(--s2)' }}>
          <tr>{columns.map(([, h]) => <th key={h} className="px-2 py-1.5 text-left font-medium whitespace-nowrap" style={{ color: 'var(--t1)' }}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`border-t ${cls ? cls(r) : ''}`} style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }}>
              {columns.map(([k]) => <td key={k} className="px-2 py-1 whitespace-nowrap">{r[k] === null || r[k] === undefined || r[k] === '' ? '-' : String(r[k])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const statusCls = (r: Row) => (r.status === 'ERROR' || r.severity === 'ERROR' ? 'text-red-500' : r.status === 'REVIEW' || r.severity === 'REVIEW' ? 'text-amber-600' : r.source === 'USER OVERRIDE' || r.status === 'USER OVERRIDE' ? 'text-blue-500' : '');

const Kpi = ({ label, value, warn, bad }: { label: string; value: any; warn?: boolean; bad?: boolean }) => (
  <div className="rounded-xl p-3" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
    <p className="text-xs" style={{ color: 'var(--t1)' }}>{label}</p>
    <p className={`text-xl font-bold ${bad ? 'text-red-500' : warn ? 'text-amber-600' : ''}`} style={bad || warn ? undefined : { color: 'var(--t0)' }}>{value ?? '-'}</p>
  </div>
);

function ElapsedTime({ started }: { started: number }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(t); }, []);
  return <>{Math.round((now - started) / 1000)} s</>;
}

export default function LugQuantityGenerator() {
  const src = useGeneratedSchedule();
  // the IODB is the primary input (the Cable Schedule is generated from it); the project's generated Cable Schedule is the alternative
  const [source, setSource] = useState<'iodb' | 'generated'>('iodb');
  const iodbRef = useRef<IodbSourceHandle>(null);
  const pend = useRef<{ ov: Record<string, Row>; od: Record<string, Row> } | null>(null);
  const [advisor, setAdvisor] = useState<Row>({ default_type: AUTO, default_scope: 'ALL', terminal_material: 'UNKNOWN', default_material: '',
    terminal: { INSTRUMENTATION: 'UNKNOWN', CONTROL: 'UNKNOWN', POWER: 'UNKNOWN' } });
  const [selections, setSelections] = useState<Record<string, Row>>({});
  const [started, setStarted] = useState<number | null>(null);
  const cancelled = useRef(false);
  const [sheets, setSheets] = useState<Row[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [rules, setRules] = useState<Row>({ count_duplicates_once: true, ferrule_evidence: false, instrumentation_use_lugs: true, control_use_lugs: true, power_use_lugs: true, default_lug_type: '', default_lug_material: '', lug_type_by_size_text: '',
    lugged_ends: 'both', earth_lugged: true, allow_override: true, power_min_mm2: 4, control_max_mm2: 2.5 });
  const [gland, setGland] = useState<Row>({ manufacturer: '', series: '', ip: '', hazardous: false });
  const [overrides, setOverrides] = useState<Record<string, Row>>({});
  const [odData, setOdData] = useState<Record<string, Row>>({});
  const [res, setRes] = useState<any>(null);
  const [live, setLive] = useState<any>(null);
  const [stage, setStage] = useState('');
  const [view, setView] = useState<View>('Summary');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ tag: string; form: Row } | null>(null);
  const [f, setF] = useState<Row>({ search: '', type: '', category: '', lug: '', status: '' });
  const timer = useRef<number | null>(null);
  const sizeMap = useMemo(() => {
    const m: Record<string, string> = {};
    String(rules.lug_type_by_size_text || '').split('\n').forEach((l) => { const [a, b] = l.split('='); if (a && b) m[a.replace(/mm²?|sq\.?\s*mm/gi, '').trim()] = b.trim(); });
    return m;
  }, [rules.lug_type_by_size_text]);

  const post = (url: string, fields: Record<string, any>) => {
    const fd = new FormData();
    Object.entries(fields).forEach(([k, v]) => { if (v !== null && v !== undefined) fd.append(k, v); });
    return api.post(url, fd, mp);
  };
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  // a new generated schedule (or project) clears the sheets, overrides, OD entries and any result from the previous one
  useEffect(() => {
    setRes(null); setLive(null); setSheets([]); setPicked([]); setOverrides({}); setOdData({});
    if (!src.gen?.available) return;
    let off = false;
    post('/cable-schedule/lug/generated/detect', src.fields())
      .then((r) => { if (!off) { setSheets(r.data.sheets.filter((s: Row) => s.used)); setPicked(r.data.default_sheets); setError(null); } })
      .catch((e) => { if (!off) handleSourceError(e, src, setError, 'Could not read the generated Cable Schedule'); });
    return () => { off = true; };
  }, [src.gen?.id, src.gen?.available]); // eslint-disable-line react-hooks/exhaustive-deps

  const advisorJson = (sel: Record<string, Row> = selections) => JSON.stringify({ ...advisor, selections: sel });
  const iodbFields = () => {
    const ov = pend.current?.ov ?? overrides, od = pend.current?.od ?? odData;
    return { rules: JSON.stringify({ ...rules, lug_type_by_size: sizeMap }), overrides: JSON.stringify(ov), od_data: JSON.stringify(od),
      gland: JSON.stringify({ ...gland, hazardous: gland.hazardous || null }), advisor: advisorJson(), project_id: getCurrentProject() || undefined };
  };
  const finish = (msg?: string) => {                        // every end of a run restores the button (no endless loading)
    if (timer.current) window.clearTimeout(timer.current);
    setBusy(false); setStarted(null);
    if (msg) setError(msg);
  };
  const cancel = () => { cancelled.current = true; finish('Generation cancelled. The page no longer waits for it.'); };
  const run = async (ov: Record<string, Row> = overrides, od: Record<string, Row> = odData) => {
    if (source === 'iodb') {
      pend.current = { ov, od }; setRes(null);
      await iodbRef.current?.run(!!iodbRef.current?.hasGenerated());
      return;
    }
    if (!src.gen?.available || busy) return;
    cancelled.current = false;
    setBusy(true); setError(null); setRes(null); setLive(null); setStage('Starting'); setStarted(Date.now());
    try {
      const start = await post('/cable-schedule/lug/generated/start', { ...src.fields(), rules: JSON.stringify({ ...rules, lug_type_by_size: sizeMap, sheets: picked }), overrides: JSON.stringify(ov),
        od_data: JSON.stringify(od), gland: JSON.stringify({ ...gland, hazardous: gland.hazardous || null }), advisor: advisorJson() });
      const t0 = Date.now();
      let failures = 0;
      const poll = async () => {
        if (cancelled.current) return;
        if (Date.now() - t0 > 20 * 60000) { finish('Generation did not finish within 20 minutes. Please try again.'); return; }
        try {
          const r = await api.get(`/cable-schedule/lug/job/${start.data.job_id}`);
          failures = 0;
          if (cancelled.current) return;
          if (r.data.live) setLive(r.data.live);
          setStage(r.data.stage || '');
          if (r.data.status === 'done') { setRes(r.data.result); setView('Summary'); finish(); return; }
          if (r.data.status === 'error') { finish(r.data.error || 'Generation failed.'); return; }
          timer.current = window.setTimeout(poll, 1200);
        } catch (e: any) {
          const detail = e.response?.data?.detail;
          if (detail || ++failures >= 3) { finish(detail || 'Lost contact with the server while generating. Please try again.'); return; }
          timer.current = window.setTimeout(poll, 2500);
        }
      };
      poll();
    } catch (e: any) { finish(); handleSourceError(e, src, setError, 'The cable lug quantity could not be started.'); }
  };
  const recalc = (sel: Record<string, Row>) => { setSelections(sel); };
  const download = async () => {
    try {
      const r = await api.get('/cable-schedule/lug/download', { responseType: 'blob' });
      const a = document.createElement('a'); a.href = window.URL.createObjectURL(new Blob([r.data])); a.setAttribute('download', res?.filename || 'Cable_Lug_Quantity_Report.xlsx');
      document.body.appendChild(a); a.click(); a.remove();
    } catch { setError('Download failed'); }
  };
  const saveOverride = (tag: string, form: Row | null) => {
    const next = { ...overrides };
    if (form) next[`tag:${tag}`] = form; else delete next[`tag:${tag}`];
    setOverrides(next); setEdit(null); run(next);
  };
  const setOd = (key: string, patch: Row) => setOdData({ ...odData, [key]: { ...(odData[key] || {}), ...patch } });

  const k = res?.kpis || live?.kpis;
  const cables: Row[] = res ? res.cable_wise : [];
  const liveRows: Row[] = !res && live ? live.rows : [];
  const errors: Row[] = res ? res.exceptions.filter((e: Row) => e.severity !== 'INFO') : (live?.errors || []);
  const filtered = useMemo(() => cables.filter((c) => {
    const q = f.search.toLowerCase();
    return (!q || c.cable_tag.toLowerCase().includes(q) || c.cable_type.toLowerCase().includes(q) || c.normalized_type.toLowerCase().includes(q))
      && (!f.type || c.normalized_type === f.type) && (!f.category || c.category === f.category)
      && (!f.lug || (f.lug === 'REVIEW' ? c.status !== 'OK' : c.lug_required === f.lug)) && (!f.status || c.status === f.status);
  }), [cables, f]);
  const opts = (key: string) => Array.from(new Set(cables.map((c) => c[key]).filter(Boolean))).sort() as string[];
  const reviewCables = cables.filter((c) => c.status !== 'OK');
  const toggle = (label: string, key: string) => (
    <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--t0)' }}>
      <input type="checkbox" checked={!!rules[key]} onChange={(e) => { setRules({ ...rules, [key]: e.target.checked }); setRes(null); }} />{label}</label>);
  const extractionCols: [string, string][] = [['sheets', 'Source'], ['cable_tag', 'Cable'], ['cable_type', 'Original type'], ['normalized_type', 'Normalized type'], ['core_count', 'Core count'],
    ['lugged_from', 'Lugged from'], ['lugged_to', 'Lugged to'], ['lugs_per_cable', 'Lugs / cable'], ['cable_qty', 'Qty'], ['total', 'Total lugs'], ['status', 'Status']];

  return (
    <div className="space-y-6" data-testid="lug-quantity">
      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}
      <div className="rounded-xl p-3 text-xs space-y-1" style={{ background: 'var(--s1)', border: '1px solid var(--b1)', color: 'var(--t0)' }}>
        <p className="flex gap-2"><Info className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--em)' }} /><span><b>Excel row ≠ physical cable.</b> A cable is identified by tag + role + cable block; repeated signal rows, header rows and section labels never create cables. Cable length is shown but never used for lugs.</span></p>
        <p className="pl-6"><b>Core count</b> (14C = 14) and <b>lugged conductors</b> are separate: lugs per cable = lugged From + lugged To (14C all lugged both ends = 28; 12 lugged each end = 24, core count stays 14). <b>Gland size</b> comes from the cable OD and a manufacturer table, never from the cable type.</p>
      </div>

      <div className="flex flex-wrap gap-2" data-testid="lug-source">
        {([['iodb', 'Upload IODB (primary input)'], ['generated', 'Use the generated Cable Schedule']] as const).map(([k2, label]) => (
          <button key={k2} onClick={() => { setSource(k2); setRes(null); setLive(null); }} className="px-4 py-2 rounded-xl text-sm font-semibold"
                  style={{ background: source === k2 ? 'var(--em)' : 'var(--s3)', color: source === k2 ? '#fff' : 'var(--t0)', border: '1px solid var(--b1)' }}>{label}</button>))}
      </div>

      {source === 'iodb' && (
        <Card title="Step 1 - IODB" description="Upload the IODB: the Cable Schedule is generated from it (existing generator), then the cables and terminations are analysed. Set the rules and the lug advisor below first; changing them re-runs on the same IODB.">
          <IodbQuantitySource ref={iodbRef} title="Upload IODB" buttonLabel="GENERATE CABLE LUG QUANTITY" startUrl="/cable-schedule/lug/start"
            jobUrl={(id) => `/cable-schedule/lug/job/${id}`} setError={setError}
            onReset={() => { setRes(null); setLive(null); setOverrides({}); setOdData({}); setSelections({}); pend.current = null; }}
            onLive={setLive} onResult={(r) => { pend.current = null; setRes(r); setView('Summary'); }} fields={iodbFields} />
        </Card>)}

      {source === 'generated' && <GeneratedScheduleCard state={src} title="Step 1 - Generated Cable Schedule (automatically loaded)">
        {sheets.length > 0 && (
          <div className="mt-3 text-xs" style={{ color: 'var(--t0)' }}>
            <p className="font-semibold mb-1">Cable schedule sheets found (tick the ones to analyse):</p>
            {sheets.map((s) => (
              <label key={s.sheet} className="flex items-center gap-2">
                <input type="checkbox" checked={picked.includes(s.sheet)} onChange={(e) => { setPicked(e.target.checked ? [...picked, s.sheet] : picked.filter((x) => x !== s.sheet)); setRes(null); }} />
                {s.sheet} {s.hidden && <span style={{ color: 'var(--t2)' }}>(hidden in the workbook)</span>}
                {s.has_ferrule && <span style={{ color: 'var(--t2)' }}>ferrule columns</span>}{s.has_lug_columns && <span className="text-blue-500">lug columns</span>}
              </label>))}
          </div>)}
      </GeneratedScheduleCard>}

      <Card title="Cable Lug Advisor" description="The advisor recommends a termination for every cable end from its conductor size, material and terminal type. A recommendation is never a confirmed selection when information is missing - those ends are marked Manual Review.">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm" style={{ color: 'var(--t0)' }}>
          <label><span className="block mb-1 font-medium">Select Cable Lug Type</span>
            <select className={field} style={fieldStyle} value={advisor.default_type} onChange={(e) => { setAdvisor({ ...advisor, default_type: e.target.value }); setRes(null); }} aria-label="Select Cable Lug Type">
              {LUG_TYPES.map((t) => <option key={t}>{t}</option>)}</select></label>
          <label><span className="block mb-1 font-medium">Apply the selected type to</span>
            <select className={field} style={fieldStyle} value={advisor.default_scope} disabled={advisor.default_type === AUTO} onChange={(e) => { setAdvisor({ ...advisor, default_scope: e.target.value }); setRes(null); }}>
              <option value="ALL">All cables needing a lug</option><option value="INSTRUMENTATION">Instrumentation cables only</option>
              <option value="CONTROL">Control cables only</option><option value="POWER">Power cables only</option></select></label>
          <label><span className="block mb-1 font-medium">Conductor material when not in the cable description</span>
            <select className={field} style={fieldStyle} value={advisor.default_material} onChange={(e) => { setAdvisor({ ...advisor, default_material: e.target.value }); setRes(null); }}>
              <option value="">Unknown - confirm per cable</option><option value="COPPER">Copper (project specification)</option><option value="ALUMINIUM">Aluminium (project specification)</option></select></label>
          {(['INSTRUMENTATION', 'CONTROL', 'POWER'] as const).map((cat) => (
            <label key={cat}><span className="block mb-1 font-medium">Terminal type - {cat.toLowerCase()} cables</span>
              <select className={field} style={fieldStyle} value={advisor.terminal[cat]} onChange={(e) => { setAdvisor({ ...advisor, terminal: { ...advisor.terminal, [cat]: e.target.value } }); setRes(null); }}>
                {TERMINALS.map(([k2, l]) => <option key={k2} value={k2}>{l}</option>)}</select></label>))}
          <label><span className="block mb-1 font-medium">Equipment terminal material (power)</span>
            <select className={field} style={fieldStyle} value={advisor.terminal_material} onChange={(e) => { setAdvisor({ ...advisor, terminal_material: e.target.value }); setRes(null); }}>
              <option value="UNKNOWN">Not stated</option><option value="COPPER">Copper</option><option value="ALUMINIUM">Aluminium</option></select></label>
        </div>
        <p className="text-xs mt-2" style={{ color: 'var(--t2)' }}>The selected type never replaces a lug type stated in the source data or a per-cable selection; it does not apply to cables that need no lug. Per-cable and per-end choices are made in the Lug Advisor view after the analysis.</p>
      </Card>

      <Card title="Step 2 - Project rules" description="Used only when the schedule does not state the lug requirement or termination itself.">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {toggle('Count duplicate cable tags once', 'count_duplicates_once')}
          {toggle('Ferrule / terminal-block columns mean terminal-block termination (0 lugs)', 'ferrule_evidence')}
          {toggle('Instrumentation (pair/triad) cables use cable lugs (1 lug per conductor per end)', 'instrumentation_use_lugs')}
          {toggle('Small control cables use cable lugs', 'control_use_lugs')}
          {toggle('Power cables use cable lugs', 'power_use_lugs')}
          {toggle('Earth conductor of "nC + E" is lugged (own line)', 'earth_lugged')}
          {toggle('Allow manual override', 'allow_override')}
          <label className="text-sm" style={{ color: 'var(--t0)' }}><span className="block mb-1">Lugged ends by default</span>
            <select className={field} style={fieldStyle} value={rules.lugged_ends} onChange={(e) => { setRules({ ...rules, lugged_ends: e.target.value }); setRes(null); }}>
              <option value="both">Both ends (From + To)</option><option value="from">From end only</option><option value="to">To end only</option></select></label>
          <label className="text-sm" style={{ color: 'var(--t0)' }}><span className="block mb-1">Control cable: core size up to (mm²)</span>
            <input className={field} style={fieldStyle} value={rules.control_max_mm2} onChange={(e) => { setRules({ ...rules, control_max_mm2: e.target.value }); setRes(null); }} /></label>
          <label className="text-sm" style={{ color: 'var(--t0)' }}><span className="block mb-1">Power cable: core size from (mm²)</span>
            <input className={field} style={fieldStyle} value={rules.power_min_mm2} onChange={(e) => { setRules({ ...rules, power_min_mm2: e.target.value }); setRes(null); }} /></label>
          <label className="text-sm" style={{ color: 'var(--t0)' }}><span className="block mb-1">Default lug type (empty = NOT SPECIFIED)</span>
            <input className={field} style={fieldStyle} value={rules.default_lug_type} onChange={(e) => { setRules({ ...rules, default_lug_type: e.target.value }); setRes(null); }} /></label>
          <label className="text-sm" style={{ color: 'var(--t0)' }}><span className="block mb-1">Default lug material (e.g. Cu)</span>
            <input className={field} style={fieldStyle} value={rules.default_lug_material} onChange={(e) => { setRules({ ...rules, default_lug_material: e.target.value }); setRes(null); }} /></label>
          <label className="text-sm md:col-span-3" style={{ color: 'var(--t0)' }}><span className="block mb-1">Lug type by conductor size (one per line, e.g. <code>1.0 = Pin lug</code>, <code>1.5 = Ring lug</code>)</span>
            <textarea className={field} style={fieldStyle} rows={2} value={rules.lug_type_by_size_text} onChange={(e) => { setRules({ ...rules, lug_type_by_size_text: e.target.value }); setRes(null); }} /></label>
          {([['manufacturer', 'Preferred gland manufacturer'], ['series', 'Preferred gland series'], ['ip', 'Required IP (e.g. IP66)']] as const).map(([key, label]) => (
            <label key={key} className="text-sm" style={{ color: 'var(--t0)' }}><span className="block mb-1">{label}</span>
              <input className={field} style={fieldStyle} value={gland[key]} onChange={(e) => { setGland({ ...gland, [key]: e.target.value }); setRes(null); }} /></label>))}
        </div>
        {source === 'generated' ? <>
          <Button onClick={() => run()} loading={busy} disabled={!src.gen?.available || picked.length === 0} size="lg" fullWidth className="mt-5 text-lg py-4">
            {busy ? 'Generating cable lug quantity…' : 'GENERATE CABLE LUG QUANTITY'}
          </Button>
          {busy && started && <p className="text-xs mt-2 text-center" style={{ color: 'var(--t1)' }}>{stage || 'Working'} · <ElapsedTime started={started} /> <button onClick={cancel} className="underline ml-1">Cancel</button></p>}
        </> : res && <Button onClick={() => run()} className="mt-5 bg-blue-600 hover:bg-blue-700">Recalculate with these rules and selections</Button>}
        {Object.keys(overrides).length > 0 && <p className="text-xs mt-2 text-blue-500">{Object.keys(overrides).length} user override(s) applied.</p>}
      </Card>

      {(busy || live) && !res && (
        <Card title="Live cable / lug extraction">
          <p className="text-sm flex items-center gap-2 mb-3" style={{ color: 'var(--t0)' }}>{busy && <Loader2 className="w-4 h-4 animate-spin" style={{ color: 'var(--em)' }} />}{stage || 'Working'}
            {live && <span className="text-xs" style={{ color: 'var(--t1)' }}>sheet {live.sheets_done} of {live.sheets_total}</span>}</p>
          {k && <div className="grid grid-cols-2 md:grid-cols-7 gap-3 mb-4">
            <Kpi label="Physical cables identified" value={k.cables} /><Kpi label="Cable types identified" value={k.cable_types} /><Kpi label="Recognized types" value={k.recognized_types} />
            <Kpi label="Unrecognized types" value={k.unrecognized_types} bad={k.unrecognized_types > 0} /><Kpi label="Total lugs calculated" value={k.total_lugs} />
            <Kpi label="Errors" value={k.errors} bad={k.errors > 0} /><Kpi label="Review items" value={k.review} warn={k.review > 0} /></div>}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2"><Table empty="Waiting for the first sheet…" rows={liveRows} cls={statusCls} columns={extractionCols} max="max-h-80" /></div>
            <div><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Errors / review (live)</p>
              <div className="space-y-1 max-h-80 overflow-auto">
                {errors.length === 0 ? <p className="text-xs" style={{ color: 'var(--t1)' }}>None so far.</p> : errors.map((e, i) => (
                  <p key={i} className={`text-xs ${e.severity === 'ERROR' ? 'text-red-500' : 'text-amber-600'}`}>{i + 1}. [{e.severity}] {e.kind}: {e.message} <span style={{ color: 'var(--t2)' }}>({e.sheet} row {e.row})</span></p>))}</div></div>
          </div>
        </Card>
      )}

      {res && k && (
        <Card title="Cable Lug Quantity Report">
          <div className="rounded-2xl p-5 mb-4 text-center" style={{ background: 'var(--s1)', border: '1px solid var(--em)' }}>
            <p className="text-xs uppercase tracking-wide" style={{ color: 'var(--t1)' }}>Total lugs required</p>
            <p className="text-5xl font-bold" style={{ color: 'var(--t0)' }} data-testid="total-lugs">{k.total_lugs}</p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-7 gap-3 mb-4">
            <Kpi label="Physical cables" value={k.cables} /><Kpi label="Cable types" value={k.cable_types} /><Kpi label="Recognized types" value={k.recognized_types} />
            <Kpi label="Unrecognized types" value={k.unrecognized_types} bad={k.unrecognized_types > 0} /><Kpi label="Cables with lugs" value={k.with_lugs} />
            <Kpi label="Errors" value={k.error_items} bad={k.error_items > 0} /><Kpi label="Review" value={k.review_items} warn={k.review_items > 0} />
          </div>
          <div className="flex flex-wrap gap-2 mb-3">
            {VIEWS.map((n) => <button key={n} onClick={() => setView(n)} className="px-3 py-1.5 rounded-lg text-xs font-semibold"
              style={{ background: view === n ? 'var(--em)' : 'var(--s3)', color: view === n ? '#fff' : 'var(--t0)', border: '1px solid var(--b1)' }}>
              {n}{n.startsWith('Errors') && ` (${errors.length})`}</button>)}
          </div>

          {view === 'Summary' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="md:col-span-2"><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Lugs by conductor size and lug type (procurement split-up)</p>
                <Table empty="No lugs required." rows={res.procurement} columns={[['conductor_size', 'Conductor size'], ['lug_type', 'Lug type'], ['material', 'Material'], ['use', 'Use'], ['from_qty', 'From-end lugs'], ['to_qty', 'To-end lugs'], ['qty', 'Total lugs'], ['cables', 'Cables']]} /></div>
              <div><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Lugs by conductor size</p><Table empty="No lugs required." rows={res.by_size} columns={[['size', 'Conductor size'], ['qty', 'Lugs']]} /></div>
              <div><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Lugs by material</p><Table empty="No lugs required." rows={res.by_material} columns={[['material', 'Material'], ['qty', 'Lugs']]} /></div>
              <div className="md:col-span-2 text-xs" style={{ color: 'var(--t1)' }}>{res.source?.type === 'GENERATED' && <>Input: {res.source.name} (generated {res.source.generated_at}) · </>}Sheets analysed: {res.used_sheets.join(', ')} · {k.overrides} user override(s)</div>
            </div>)}

          {view === 'Lug Advisor' && res.advisor && (<div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
              <Kpi label="Terminations" value={res.advisor.kpis.terminations} /><Kpi label="Total lugs / ferrules" value={res.advisor.kpis.total_quantity} />
              <Kpi label="Confirmed from source" value={res.advisor.kpis.confirmed} /><Kpi label="Advisor recommended" value={res.advisor.kpis.advisory} />
              <Kpi label="Manually selected" value={res.advisor.kpis.manual_selections} /><Kpi label="Manual review" value={res.advisor.kpis.manual_review} warn={res.advisor.kpis.manual_review > 0} />
            </div>
            <p className="text-xs" style={{ color: 'var(--t1)' }}>Change the type or material of a cable end, then Recalculate. Your choices are kept on every recalculation.</p>
            <div className="overflow-auto max-h-[30rem] border rounded-lg" style={{ borderColor: 'var(--b1)' }}>
              <table className="w-full text-xs"><thead className="sticky top-0" style={{ background: 'var(--s2)' }}><tr>
                {['Cable tag', 'Cable description', 'Application', 'Conductor size', 'Conductor material', 'End', 'Recommended', 'Lug type (override)', 'Lug material', 'Lug size', 'Qty', 'Status'].map((h) =>
                  <th key={h} className="px-2 py-1.5 text-left font-medium whitespace-nowrap" style={{ color: 'var(--t1)' }}>{h}</th>)}</tr></thead>
                <tbody>{res.advisor.ends.slice(0, 600).map((e: Row, i: number) => {
                  const key = `tag:${e.cable_tag}|end:${String(e.end).split(' ')[0].toLowerCase()}`;
                  const sel = selections[key] || {};
                  return (
                    <tr key={i} className="border-t" style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }} title={e.remarks}>
                      <td className="px-2 py-1 whitespace-nowrap">{e.cable_tag}</td><td className="px-2 py-1 whitespace-nowrap">{e.cable_type}</td>
                      <td className="px-2 py-1">{e.application}</td><td className="px-2 py-1 whitespace-nowrap">{e.conductor_size}</td><td className="px-2 py-1">{e.conductor_material}</td>
                      <td className="px-2 py-1 whitespace-nowrap">{e.end}</td><td className="px-2 py-1 whitespace-nowrap">{e.recommended}</td>
                      <td className="px-2 py-1">{String(e.end).includes('EARTH') ? e.lug_type : (
                        <select className={field} style={{ ...fieldStyle, minWidth: '12rem' }} value={sel.type || AUTO} aria-label={`Lug type ${e.cable_tag} ${e.end}`}
                                onChange={(ev) => recalc({ ...selections, [key]: { ...sel, type: ev.target.value === AUTO ? '' : ev.target.value } })}>
                          {LUG_TYPES.map((t) => <option key={t} value={t}>{t === AUTO ? `${AUTO} (${e.lug_type})` : t}</option>)}</select>)}</td>
                      <td className="px-2 py-1"><input className={field} style={{ ...fieldStyle, minWidth: '9rem' }} placeholder={e.lug_material} value={sel.material || ''}
                                                       onChange={(ev) => recalc({ ...selections, [key]: { ...sel, material: ev.target.value } })} /></td>
                      <td className="px-2 py-1 whitespace-nowrap">{e.lug_size}</td><td className="px-2 py-1">{e.quantity ?? 'REVIEW'}</td>
                      <td className={`px-2 py-1 whitespace-nowrap ${statusColor(e.status)}`}>{e.status}{e.warnings?.length > 0 && <AlertTriangle className="inline w-3 h-3 ml-1 text-amber-600" />}</td>
                    </tr>);
                })}</tbody></table>
            </div>
            {res.advisor.ends.length > 600 && <p className="text-xs" style={{ color: 'var(--t2)' }}>Showing the first 600 cable ends; the Excel report has all {res.advisor.ends.length}.</p>}
            <Button onClick={() => run()} loading={busy} className="bg-blue-600 hover:bg-blue-700">Recalculate with these selections ({Object.values(selections).filter((x) => x.type || x.material).length})</Button>
            <div><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Lug quantity summary</p>
              <Table empty="No lugs." rows={res.advisor.summary} columns={[['lug_type', 'Lug type'], ['lug_material', 'Material'], ['conductor_size', 'Conductor size'], ['specification', 'Specification'], ['quantity', 'Quantity'], ['cables', 'Cables']]} /></div>
            <div><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Advisor review ({res.advisor.review.length})</p>
              <Table empty="Nothing needs review." rows={res.advisor.review} max="max-h-64" columns={[['cable_tag', 'Cable'], ['end', 'End'], ['kind', 'Kind'], ['status', 'Status'], ['issue', 'Issue / action']]} /></div>
          </div>)}
          {view === 'Extraction' && (<>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3 text-xs">
              <input className={field} style={fieldStyle} placeholder="Search cable tag / type" value={f.search} onChange={(e) => setF({ ...f, search: e.target.value })} />
              <select className={field} style={fieldStyle} value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}><option value="">All cable types</option>{opts('normalized_type').map((o) => <option key={o}>{o}</option>)}</select>
              <select className={field} style={fieldStyle} value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}><option value="">All categories</option>{opts('category').map((o) => <option key={o}>{o}</option>)}</select>
              <select className={field} style={fieldStyle} value={f.lug} onChange={(e) => setF({ ...f, lug: e.target.value })}><option value="">Lug: all</option><option value="YES">Lug required</option><option value="NO">No lug</option><option value="REVIEW">Review</option></select>
              <select className={field} style={fieldStyle} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}><option value="">All status</option><option>OK</option><option>REVIEW</option><option>ERROR</option></select>
              <span className="self-center" style={{ color: 'var(--t1)' }}>{filtered.length} of {cables.length} cables</span>
            </div>
            <Table empty="No cable matches the filters." rows={filtered} cls={statusCls} columns={[...extractionCols.slice(0, 5), ['role', 'Role'], ...extractionCols.slice(5), ['source', 'Source status'], ['termination', 'Termination'], ['length', 'Length (info)'], ['rows', 'Row(s)'], ['reason', 'Basis']]} />
          </>)}

          {view === 'Cable Type Summary' && <Table empty="-" rows={res.types.map((t: Row) => ({ ...t, ...(res.gland.find((g: Row) => g.type_key === t.type_key) || {}), cable_type: t.cable_type, status: t.status, od: (res.gland.find((g: Row) => g.type_key === t.type_key) || {}).od || 'OD Required' }))}
            cls={statusCls} columns={[['cable_type', 'Cable type'], ['cable_qty', 'Physical qty'], ['core_count', 'Core count'], ['lugged_from', 'Lugged from'], ['lugged_to', 'Lugged to'], ['per_cable', 'Lugs / cable'], ['total', 'Total lugs'],
              ['od', 'Cable OD'], ['metric', 'Metric gland'], ['npt', 'NPT gland'], ['et', 'ET gland'], ['lug_required', 'Lug'], ['termination', 'Termination'], ['status', 'Status']]} />}

          {view === 'Gland Recommendation' && (<div className="space-y-3">
            <p className="text-xs" style={{ color: 'var(--t1)' }}>Gland size is determined from the <b>cable OD</b> and a manufacturer table - not from the core count or cable type. Enter the OD per cable type and re-run. ET is shown only where the reference data supports it.</p>
            <div className="overflow-auto max-h-[26rem] border rounded-lg" style={{ borderColor: 'var(--b1)' }}>
              <table className="w-full text-xs"><thead className="sticky top-0" style={{ background: 'var(--s2)' }}><tr>{['Cable type', 'Qty', 'Construction', 'Cable OD (mm)', 'Bedding (mm)', 'Metric', 'NPT', 'ET', 'Basis / source', 'Status', 'Override metric', 'NPT', 'ET'].map((h) => <th key={h} className="px-2 py-1.5 text-left font-medium whitespace-nowrap" style={{ color: 'var(--t1)' }}>{h}</th>)}</tr></thead>
                <tbody>{res.gland.map((g: Row) => {
                  const v = odData[g.type_key] || {};
                  return (<tr key={g.type_key} className={`border-t ${statusCls(g)}`} style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }}>
                    <td className="px-2 py-1 whitespace-nowrap">{g.cable_type}</td><td className="px-2 py-1">{g.cable_qty}</td>
                    <td className="px-2 py-1"><select className={field} style={{ ...fieldStyle, width: '7.5rem' }} value={v.construction || g.construction} onChange={(e) => setOd(g.type_key, { construction: e.target.value })}>{['UNARMOURED', 'ARMOURED', 'BRAIDED'].map((c) => <option key={c}>{c}</option>)}</select></td>
                    <td className="px-2 py-1"><input className={field} style={{ ...fieldStyle, width: '5rem' }} placeholder={g.od ? String(g.od) : 'mm'} value={v.od ?? ''} onChange={(e) => setOd(g.type_key, { od: e.target.value })} /></td>
                    <td className="px-2 py-1"><input className={field} style={{ ...fieldStyle, width: '4.5rem' }} value={v.bedding ?? ''} disabled={(v.construction || g.construction) !== 'ARMOURED'} onChange={(e) => setOd(g.type_key, { bedding: e.target.value })} /></td>
                    <td className="px-2 py-1 whitespace-nowrap">{g.metric}</td><td className="px-2 py-1 whitespace-nowrap">{g.npt}</td><td className="px-2 py-1 whitespace-nowrap">{g.et}</td>
                    <td className="px-2 py-1" style={{ maxWidth: '22rem' }}>{g.basis || g.advice}{g.source && <span style={{ color: 'var(--t2)' }}> · {g.source}</span>}{g.flags?.length > 0 && <span className="text-amber-600"> · {g.flags.join(' · ')}</span>}</td>
                    <td className="px-2 py-1 whitespace-nowrap">{g.status}{g.auto && <span style={{ color: 'var(--t2)' }}> (auto: {g.auto.metric} / {g.auto.npt} / {g.auto.et})</span>}</td>
                    {(['metric_gland', 'npt_gland', 'et_gland'] as const).map((kk) => <td key={kk} className="px-2 py-1"><input className={field} style={{ ...fieldStyle, width: '5rem' }} value={v[kk] ?? ''} onChange={(e) => setOd(g.type_key, { [kk]: e.target.value })} /></td>)}
                  </tr>);
                })}</tbody></table>
            </div>
            <Button onClick={() => run()} className="bg-blue-600 hover:bg-blue-700">Re-run with these OD values</Button>
            <p className="text-xs" style={{ color: 'var(--t1)' }}>Gland recommendations are advisory - confirm against the manufacturer datasheet. A manual gland entry is marked USER OVERRIDE and the automatic value is kept beside it.</p>
          </div>)}

          {view === 'Reconciliation' && <div className="space-y-2"><p className="text-xs" style={{ color: 'var(--t1)' }}>Every source row mapped to its physical cable - different roles / blocks are not merged.</p>
            <Table empty="-" rows={res.reconciliation} cls={statusCls} columns={[['sheet', 'Original sheet'], ['row', 'Original row'], ['pid', 'Physical cable ID'], ['role', 'Cable role'], ['original_type', 'Original type'], ['normalized_type', 'Normalized type'], ['status', 'Status']]} /></div>}

          {view === 'Lug Procurement' && <Table empty="No lugs required by the analysed cables." rows={res.procurement} columns={[['lug_type', 'Lug type'], ['conductor_size', 'Conductor size'], ['material', 'Material'], ['spec', 'Specification / part no.'],
            ['use', 'Use'], ['from_qty', 'From-end qty'], ['to_qty', 'To-end qty'], ['qty', 'Total qty'], ['cables', 'Cables']]} />}

          {view === 'Errors / Review' && (<div className="space-y-4">
            <Table empty="No exceptions." rows={res.exceptions} cls={statusCls} columns={[['severity', 'Severity'], ['kind', 'Kind'], ['ref', 'Cable / reference'], ['sheet', 'Sheet'], ['row', 'Row'], ['original', 'Original value'], ['message', 'Message']]} />
            {rules.allow_override && reviewCables.length > 0 && (
              <div><p className="text-sm font-semibold mb-1 flex gap-1" style={{ color: 'var(--t0)' }}><AlertTriangle className="w-4 h-4 text-amber-600" /> Cables needing a decision - manual override (marked USER OVERRIDE; the automatic value stays visible)</p>
                <div className="space-y-1 max-h-72 overflow-auto">
                  {reviewCables.slice(0, 200).map((c) => (
                    <div key={c.cable_tag} className="flex items-center gap-2 text-xs rounded-lg px-2 py-1" style={{ background: 'var(--s1)', border: '1px solid var(--b1)', color: 'var(--t0)' }}>
                      <span className="font-semibold">{c.cable_tag}</span><span>{c.cable_type}</span><span className="text-amber-600 truncate flex-1">{c.reason}</span>
                      <button className="underline" onClick={() => setEdit({ tag: c.cable_tag, form: overrides[`tag:${c.cable_tag}`] || { lug_required: 'YES' } })}>Override</button>
                    </div>))}
                </div></div>)}
          </div>)}

          {edit && (
            <div className="mt-4 rounded-xl p-4 space-y-2" style={{ background: 'var(--s1)', border: '1px solid var(--em)' }} data-testid="override-form">
              <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>USER OVERRIDE - {edit.tag}</p>
              <p className="text-xs" style={{ color: 'var(--t1)' }}>Lugged conductors are entered separately from the core count (core count is never changed).</p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs" style={{ color: 'var(--t0)' }}>
                <label>Lug required<select className={field} style={fieldStyle} value={edit.form.lug_required || ''} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, lug_required: e.target.value } })}>
                  <option>YES</option><option>NO</option><option>REVIEW</option></select></label>
                {([['lugged_from', 'Lugged conductors From'], ['lugged_to', 'Lugged conductors To'], ['lug_type', 'Lug type'], ['lug_size', 'Lug size'], ['lug_material', 'Material'], ['remarks', 'Remarks / reason']] as const).map(([key, label]) => (
                  <label key={key}>{label}<input className={field} style={fieldStyle} value={edit.form[key] ?? ''} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, [key]: e.target.value } })} /></label>))}
              </div>
              <div className="flex gap-2">
                <Button onClick={() => saveOverride(edit.tag, edit.form)} className="bg-blue-600 hover:bg-blue-700">Apply override</Button>
                <Button onClick={() => saveOverride(edit.tag, null)} className="bg-gray-500 hover:bg-gray-600">Remove override</Button>
                <Button onClick={() => setEdit(null)} className="bg-gray-400 hover:bg-gray-500">Cancel</Button>
              </div>
            </div>)}

          <div className="mt-5"><DeliverableDownloads module="lug_quantity" filename={res.filename || 'Cable_Lug_Quantity_Report.xlsx'} cover={res.cover} onExcel={download} /></div>
        </Card>
      )}
    </div>
  );
}
