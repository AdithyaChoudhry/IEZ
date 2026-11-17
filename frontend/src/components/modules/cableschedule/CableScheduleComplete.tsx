/**
 * Cable Schedule Complete - ONE IODB -> one workbook (Cable Schedule + I/O Summary + Gland Quantity + Cable Lug Quantity).
 *
 * An orchestration screen over the existing generators. The only primary input is the IODB (the shared IODB mechanism is
 * used as everywhere else). The progress tracker shows the REAL stage states reported by the backend job; nothing is
 * shown as complete before its engine has finished.
 */
import { AnalyserArt } from '../../art/InstrumentArt';
import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Download, FileText, Loader2, MinusCircle, Package, Upload, XCircle } from 'lucide-react';
import api from '@/services/api';
import Card from '../../ui/Card';
import Button from '../../ui/Button';
import Alert from '../../ui/Alert';
import FileUploadCard from '../../ui/FileUploadCard';
import SharedIodbCard from '../../ui/SharedIodb';

type Row = Record<string, any>;
const mp = { headers: { 'Content-Type': 'multipart/form-data' } };
const TABS = ['Complete Summary', 'Cable Schedule', 'I/O Summary', 'Gland Quantity', 'Cable Lug Quantity', 'Exceptions'] as const;
type Tab = (typeof TABS)[number];
const STAGES = [['validate', 'IODB Validation'], ['schedule', 'Cable Schedule Generation'], ['io', 'I/O Summary'], ['gland', 'Gland Quantity Extraction'], ['lug', 'Lug Quantity Extraction'], ['compile', 'Final Workbook Compilation']];

function Table({ columns, rows, empty }: { columns: [string, string][]; rows: Row[]; empty: string }) {
  if (!rows.length) return <p className="text-sm py-3" style={{ color: 'var(--t1)' }}>{empty}</p>;
  return (
    <div className="overflow-auto max-h-[26rem] border rounded-lg" style={{ borderColor: 'var(--b1)' }}>
      <table className="w-full text-xs">
        <thead className="sticky top-0" style={{ background: 'var(--s2)' }}>
          <tr>{columns.map(([, h]) => <th key={h} className="px-2 py-1.5 text-left font-medium whitespace-nowrap" style={{ color: 'var(--t1)' }}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`border-t ${r.severity === 'Error' || r.status === 'ERROR' ? 'text-red-500' : r.severity === 'Warning' || r.severity === 'Review' ? 'text-amber-600' : ''}`}
                style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }}>
              {columns.map(([k]) => <td key={k} className="px-2 py-1 whitespace-nowrap">{r[k] === null || r[k] === undefined || r[k] === '' ? '-' : String(r[k])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const Stat = ({ label, value, warn }: { label: string; value: any; warn?: boolean }) => (
  <div className="rounded-xl p-3" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
    <p className="text-xs" style={{ color: 'var(--t1)' }}>{label}</p>
    <p className={`text-xl font-bold ${warn ? 'text-amber-600' : ''}`} style={warn ? undefined : { color: 'var(--t0)' }}>{value === null || value === undefined ? 'n/a' : typeof value === 'number' ? value.toLocaleString() : value}</p>
  </div>
);

function StageIcon({ state }: { state: string }) {
  if (state === 'done') return <CheckCircle2 className="w-4 h-4 text-green-500" />;
  if (state === 'warning') return <AlertTriangle className="w-4 h-4 text-amber-600" />;
  if (state === 'failed') return <XCircle className="w-4 h-4 text-red-500" />;
  if (state === 'running') return <Loader2 className="w-4 h-4 animate-spin" style={{ color: 'var(--em)' }} />;
  if (state === 'skipped') return <MinusCircle className="w-4 h-4" style={{ color: 'var(--t2)' }} />;
  return <span className="w-4 h-4 rounded-full border inline-block" style={{ borderColor: 'var(--b2)' }} />;
}

export default function CableScheduleComplete() {
  const [iodb, setIodb] = useState<File | null>(null);
  const [template, setTemplate] = useState<File | null>(null);
  const [builtin, setBuiltin] = useState<boolean | null>(null);
  const [val, setVal] = useState<Row | null>(null);
  const [stages, setStages] = useState<Record<string, Row>>({});
  const [res, setRes] = useState<Row | null>(null);
  const [tab, setTab] = useState<Tab>('Complete Summary');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const timer = useRef<number | null>(null);

  useEffect(() => { api.get('/cable-schedule/complete/status').then((r) => setBuiltin(r.data.builtin_template)).catch(() => setBuiltin(null)); }, []);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  useEffect(() => {
    setVal(null); setRes(null); setStages({}); setError(null);
    if (!iodb) return;
    let off = false;
    const fd = new FormData(); fd.append('file', iodb);
    api.post('/cable-schedule/complete/validate', fd, mp)
      .then((r) => { if (!off) setVal(r.data); })
      .catch((e) => { if (!off) setError(e.response?.data?.detail || 'Could not validate the IODB'); });
    return () => { off = true; };
  }, [iodb]);

  const generate = async () => {
    if (!iodb) return;
    setBusy(true); setError(null); setRes(null); setStages({});
    try {
      const fd = new FormData(); fd.append('file', iodb); if (template) fd.append('template_file', template);
      const start = await api.post('/cable-schedule/complete/generate', fd, mp);
      const poll = async () => {
        try {
          const r = await api.get(`/cable-schedule/complete/job/${start.data.job_id}`);
          setStages(r.data.stages || {});
          if (r.data.status === 'done') { setRes(r.data.result); setTab('Complete Summary'); setBusy(false); return; }
          if (r.data.status === 'error') { setError(r.data.error); setBusy(false); return; }
          timer.current = window.setTimeout(poll, 2000);
        } catch (e: any) { setError(e.response?.data?.detail || 'Lost contact with the generation job'); setBusy(false); }
      };
      poll();
    } catch (e: any) { setError(e.response?.data?.detail || 'Generation could not be started'); setBusy(false); }
  };

  const download = async () => {
    try {
      const r = await api.get('/cable-schedule/complete/download', { responseType: 'blob' });
      const a = document.createElement('a'); a.href = window.URL.createObjectURL(new Blob([r.data])); a.setAttribute('download', 'Cable_Schedule_Complete.xlsx');
      document.body.appendChild(a); a.click(); a.remove();
    } catch { setError('Download failed'); }
  };

  const s = val?.stats;
  const needTemplate = builtin === false && !template;
  const stageRows = res ? res.stages : STAGES.map(([k, l]) => ({ key: k, label: l, state: stages[k]?.state || 'pending', message: stages[k]?.message || '' }));
  const k = res?.kpis;
  const cables = (res?.cables || []).filter((c: Row) => !search || c.cable_tag.toLowerCase().includes(search.toLowerCase()) || c.cable_type.toLowerCase().includes(search.toLowerCase()));
  const overall = res ? (res.stages.some((x: Row) => x.state === 'failed') ? 'FAILED' : res.stages.some((x: Row) => x.state === 'warning') ? 'READY - REVIEW ITEMS' : 'READY') : '';

  return (
    <div className="space-y-6" data-testid="cable-schedule-complete">
      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}
      <p className="text-sm" style={{ color: 'var(--t0)' }}>Upload IODB to generate the complete Cable Schedule package.</p>

      <SharedIodbCard title="Upload IODB" icon={Upload} file={iodb} onChange={setIodb} />

      {builtin === false && (
        <FileUploadCard title="Cable Schedule template (required once - none is installed on this server)" icon={FileText} file={template} onChange={setTemplate}
                        hint="The same template the Cable Schedule Generator uses. Its formats are preserved." />
      )}

      {val && (
        <Card title="IODB validation">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <Stat label="File" value={iodb?.name} />
            {s && <><Stat label="Rows" value={s.rows} /><Stat label="Unique instrument tags" value={s.unique_tags} /><Stat label="Cable records" value={s.cable_records} />
              <Stat label="JB records" value={s.jb_records} /><Stat label="Unique cable tags" value={s.unique_cable_tags} /><Stat label="Main cable tags" value={s.main_cable_tags} /><Stat label="Branch cable tags" value={s.branch_cable_tags} /></>}
          </div>
          <p className={`mt-3 text-sm font-semibold flex items-center gap-2 ${val.status === 'BLOCKED' ? 'text-red-500' : val.status === 'READY' ? 'text-green-600' : 'text-amber-600'}`}>
            {val.status === 'READY' ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
            {val.status === 'READY' ? 'Ready for Cable Schedule Generation' : val.status === 'BLOCKED' ? 'Blocked - the complete package cannot be generated' : 'Ready - with warnings'}
          </p>
          {val.errors.map((e: string, i: number) => <p key={i} className="text-xs text-red-500 mt-1">{e}</p>)}
          {val.warnings.map((e: string, i: number) => <p key={i} className="text-xs text-amber-600 mt-1">{e}</p>)}
          {val.missing_fields?.length > 0 && <p className="text-xs mt-2" style={{ color: 'var(--t1)' }}>Fields not found in the IODB: {val.missing_fields.join(', ')}</p>}
          {val.issues?.length > 0 && <p className="text-xs mt-1" style={{ color: 'var(--t1)' }}>{val.issues.filter((i: Row) => i.severity === 'ERROR').length} cable data error(s), {val.issues.filter((i: Row) => i.severity === 'WARNING').length} warning(s) - listed in the Exceptions tab after generation.</p>}
        </Card>
      )}

      <Card title="Generate">
        <Button onClick={generate} loading={busy} disabled={!iodb || !val?.ok || needTemplate} size="lg" fullWidth className="text-lg py-4">
          <Package className="w-6 h-6" />{busy ? 'Generating...' : 'GENERATE COMPLETE CABLE SCHEDULE'}
        </Button>
        {!val?.ok && iodb && val && <p className="text-xs text-red-500 mt-2 text-center">Fix the IODB errors above first.</p>}
        {busy && <div className="mt-5 max-w-[360px]"><AnalyserArt tag="FIT 101" unit="m³/h" base={42} label="Building the package" /></div>}
        {(busy || res || Object.keys(stages).length > 0) && (
          <ul className="mt-4 space-y-1" data-testid="progress">
            {stageRows.map((st: Row, i: number) => (
              <li key={st.key} className="flex items-center gap-2 text-sm" style={{ color: 'var(--t0)' }}>
                <StageIcon state={st.state} /><span className="font-medium">{i + 1}. {st.label}</span>
                {st.message && <span className="text-xs truncate" style={{ color: st.state === 'failed' ? '#ef4444' : 'var(--t1)' }}>{st.message}</span>}
              </li>))}
          </ul>)}
      </Card>

      {res && k && (
        <Card title={`Cable Schedule Complete - ${res.iodb_name}`}>
          <p className={`text-sm font-bold mb-3 ${overall === 'READY' ? 'text-green-600' : 'text-amber-600'}`} data-testid="overall">Status: {overall}</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <Stat label="Instrument tags" value={k.tags} /><Stat label="Cable tags (physical)" value={k.cable_tags} /><Stat label="Cable types" value={k.cable_types} />
            <Stat label="Cable length (m)" value={k.cable_length} /><Stat label="Total I/O" value={k.io} /><Stat label="Glands" value={k.glands} />
            <Stat label="Lugs" value={k.lugs} /><Stat label="Exceptions" value={k.exceptions} warn={k.exceptions > 0} />
          </div>
          <div className="flex flex-wrap gap-2 mb-3">
            {TABS.map((n) => <button key={n} onClick={() => setTab(n)} className="px-3 py-1.5 rounded-lg text-xs font-semibold"
              style={{ background: tab === n ? 'var(--em)' : 'var(--s3)', color: tab === n ? '#fff' : 'var(--t0)', border: '1px solid var(--b1)' }}>
              {n}{n === 'Exceptions' && ` (${res.exceptions.length})`}</button>)}
          </div>

          {tab === 'Complete Summary' && (
            <div className="space-y-4">
              <div><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Workbook contents ({res.sheets.length} sheets)</p>
                <Table empty="-" rows={res.sheets} columns={[['section', 'Section'], ['sheet', 'Sheet'], ['note', 'Note']]} /></div>
              <div><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Cross-module consistency</p>
                {res.checks.length === 0 ? <p className="text-xs" style={{ color: 'var(--t1)' }}>No cross-checks were possible.</p> :
                  res.checks.map((c: Row, i: number) => (
                    <p key={i} className="text-xs flex gap-2 mb-1" style={{ color: 'var(--t0)' }}>{c.ok ? <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" /> : <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />}
                      <span><b>{c.check}</b> - {c.detail}</span></p>))}</div>
            </div>)}

          {tab === 'Cable Schedule' && (<div className="space-y-3">
            <p className="text-xs" style={{ color: 'var(--t1)' }}>Generated with the existing Cable Schedule Generator ({res.schedule.template} template){res.schedule.instrument_schedule ? '' : ' - no junction-box rows, so no Instrument Cable Schedule sheet'}. Extra sheets: {(res.schedule.sheets || []).join(', ') || 'none'}.</p>
            <Table empty="-" rows={res.schedule.stats || []} columns={[['label', 'Sheet'], ['records', 'Signals'], ['devices', 'Devices'], ['cables', 'Cables'], ['rows', 'Rows']]} />
            <input className="border rounded-lg px-2 py-1.5 text-sm w-72" style={{ borderColor: 'var(--b1)', background: 'var(--s1)', color: 'var(--t0)' }} placeholder="Search cable tag / type" value={search} onChange={(e) => setSearch(e.target.value)} />
            <Table empty="No cables." rows={cables} columns={[['cable_tag', 'Cable tag'], ['cable_type', 'Cable type'], ['category', 'Category'], ['from', 'From'], ['to', 'To'], ['length', 'Length'], ['sheets', 'Sheet'], ['occurrences', 'Rows']]} /></div>)}

          {tab === 'I/O Summary' && <Table empty={res.io_summary.reason || 'No signals to count.'} rows={res.io_summary.rows} columns={[['type', 'Signal I/O type'], ['total', 'No. of signals'], ...(res.io_summary.has_isnis ? [['IS', 'IS'], ['NIS', 'NIS'], ['NOT SET', 'IS/NIS not set']] as [string, string][] : [])]} />}

          {tab === 'Gland Quantity' && (res.gland ? (<div className="space-y-3">
            <p className="text-sm" style={{ color: 'var(--t0)' }}>Total glands: <b>{res.gland.totals.glands}</b> on {res.gland.totals.cables} cables</p>
            <Table empty="No glands counted." rows={res.gland.by_gland} columns={[['gland_type', 'Gland type'], ['thread', 'Thread'], ['gland_size', 'Size'], ['material', 'Material'], ['certification', 'Certification'], ['qty', 'Quantity']]} />
            <Table empty="-" rows={res.gland.by_location} columns={[['location', 'Location'], ['qty', 'Quantity']]} /></div>) : <p className="text-sm text-amber-600">Gland quantity was not generated - see the Exceptions tab.</p>)}

          {tab === 'Cable Lug Quantity' && (res.lug ? (<div className="space-y-3">
            <p className="text-sm" style={{ color: 'var(--t0)' }}>Total lugs required: <b>{res.lug.kpis.total_lugs}</b> · {res.lug.kpis.cables} physical cables · {res.lug.kpis.with_lugs} with lugs · {res.lug.kpis.without_lugs} without · {res.lug.kpis.review} to review</p>
            <Table empty="-" rows={res.lug.types} columns={[['cable_type', 'Cable type'], ['cable_qty', 'Cable qty'], ['cores', 'Cores'], ['lug_required', 'Lug required'], ['lug_from', 'Lug from'], ['lug_to', 'Lug to'], ['per_cable', 'Lugs / cable'], ['total', 'Total lugs'], ['lug_type', 'Lug type'], ['material', 'Material'], ['status', 'Status']]} /></div>)
            : <p className="text-sm text-amber-600">Cable lug quantity was not generated - see the Exceptions tab.</p>)}

          {tab === 'Exceptions' && <Table empty="No exceptions." rows={res.exceptions} columns={[['module', 'Module'], ['severity', 'Severity'], ['ref', 'Tag / cable'], ['sheet', 'Sheet'], ['field', 'Field'], ['issue', 'Issue'], ['action', 'Recommended action']]} />}

          <Button onClick={download} className="mt-5 bg-green-600 hover:bg-green-700"><Download className="w-5 h-5" /> DOWNLOAD COMPLETE CABLE SCHEDULE</Button>
        </Card>
      )}
    </div>
  );
}
