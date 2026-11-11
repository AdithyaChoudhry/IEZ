/**
 * Drum Schedule Generator (sub-module of the Cable Schedule Generator).
 *
 * Step 1 IODB (the shared IODB) -> cable demand found   Step 2 Drum Master Excel -> drum lots
 * Step 3 settings               Step 4 generate -> progress by cable type, six preview reports, Excel download.
 * All numbers come from the backend engine; nothing is computed here.
 */
import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Download, FileText, Layers, Upload } from 'lucide-react';
import api from '@/services/api';
import Card from '../../ui/Card';
import Button from '../../ui/Button';
import Alert from '../../ui/Alert';
import FileUploadCard from '../../ui/FileUploadCard';
import SharedIodbCard from '../../ui/SharedIodb';

interface Issue { severity: string; kind: string; ref: string; message: string; source?: string }
interface Demand {
  stats: { rows: number; demand: number; branch: number; main: number; total_length: number };
  issues: Issue[];
  issue_counts: Record<string, number>;
  cable_types: { cable_type: string; is_nis: string; required: number }[];
}
interface Master {
  info: { sheet: string; records: number; cable_types: number; total_drums: number; total_length: number };
  issues: Issue[];
}
type Row = Record<string, any>;
interface Result {
  totals: Record<string, number>;
  progress: { label: string; status: string; detail: string }[];
  schedule: Row[];
  schedule_truncated: boolean;
  summary: Row[];
  utilization: Row[];
  shortage: Row[];
  excess: { unused_drums: Row[]; partial_drums: Row[]; by_type: Row[] };
  exceptions: Issue[];
}

const TABS = ['Drum Schedule', 'Cable Type Summary', 'Drum Utilization', 'Shortage', 'Excess / Balance', 'Exceptions'] as const;
type Tab = (typeof TABS)[number];

function Table({ columns, rows, empty }: { columns: [string, string][]; rows: Row[]; empty: string }) {
  if (!rows.length) return <p className="text-sm py-4" style={{ color: 'var(--t1)' }}>{empty}</p>;
  return (
    <div className="overflow-auto max-h-[28rem] border rounded-lg" style={{ borderColor: 'var(--b1)' }}>
      <table className="w-full text-xs">
        <thead className="sticky top-0" style={{ background: 'var(--s2)' }}>
          <tr>{columns.map(([, h]) => <th key={h} className="px-2 py-1.5 text-left font-medium whitespace-nowrap" style={{ color: 'var(--t1)' }}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t" style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }}>
              {columns.map(([k]) => (
                <td key={k} className={`px-2 py-1 whitespace-nowrap ${/shortage|status/.test(k) && /SHORTAGE|NOT MATCHED|ERROR/.test(String(r[k])) ? 'text-red-500 font-semibold' : ''}`}>
                  {r[k] === null || r[k] === undefined || r[k] === '' ? '-' : String(r[k])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DrumScheduleGenerator() {
  const [iodb, setIodb] = useState<File | null>(null);
  const [masterFile, setMasterFile] = useState<File | null>(null);
  const [demand, setDemand] = useState<Demand | null>(null);
  const [master, setMaster] = useState<Master | null>(null);
  const [minResidual, setMinResidual] = useState(10);
  const [useSplit, setUseSplit] = useState(true);
  const [result, setResult] = useState<Result | null>(null);
  const [tab, setTab] = useState<Tab>('Drum Schedule');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const post = <T,>(url: string, fields: Record<string, File | string>) => {
    const f = new FormData();
    Object.entries(fields).forEach(([k, v]) => f.append(k, v));
    return api.post<T>(url, f, { headers: { 'Content-Type': 'multipart/form-data' } });
  };

  useEffect(() => {
    setDemand(null); setResult(null);
    if (!iodb) return;
    let off = false;
    post<Demand>('/cable-schedule/drum/demand', { iodb_file: iodb })
      .then((r) => { if (!off) { setDemand(r.data); setError(null); } })
      .catch((e) => { if (!off) setError(e.response?.data?.detail || 'Could not read the cable demand from the IODB'); });
    return () => { off = true; };
  }, [iodb]);

  useEffect(() => {
    setMaster(null); setResult(null);
    if (!masterFile) return;
    let off = false;
    post<Master>('/cable-schedule/drum/master', { drum_master_file: masterFile })
      .then((r) => { if (!off) { setMaster(r.data); setError(null); } })
      .catch((e) => { if (!off) setError(e.response?.data?.detail || 'Could not read the Drum Master'); });
    return () => { off = true; };
  }, [masterFile]);

  const generate = async () => {
    if (!iodb || !masterFile) return;
    setBusy(true); setError(null); setResult(null);
    try {
      const r = await post<Result>('/cable-schedule/drum/generate', {
        iodb_file: iodb, drum_master_file: masterFile, min_residual: String(minResidual), use_master_split: String(useSplit),
      });
      setResult(r.data); setTab('Drum Schedule');
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Drum schedule generation failed');
    } finally { setBusy(false); }
  };

  const download = async () => {
    try {
      const r = await api.get('/cable-schedule/drum/download', { responseType: 'blob' });
      const a = document.createElement('a');
      a.href = window.URL.createObjectURL(new Blob([r.data]));
      a.setAttribute('download', 'Drum_Schedule.xlsx');
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e: any) { setError('Download failed'); }
  };

  const issueList = (issues: Issue[]) => issues.slice(0, 6).map((i, n) => (
    <p key={n} className={`text-xs flex gap-1.5 mt-1 ${i.severity === 'ERROR' ? 'text-red-500' : i.severity === 'WARNING' ? 'text-amber-600' : ''}`}
       style={i.severity === 'INFO' ? { color: 'var(--t1)' } : undefined}>
      <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />{i.ref}: {i.message}
    </p>
  ));

  const ready = !!iodb && !!masterFile && !!demand && !!master && minResidual >= 0 && minResidual <= 15;
  const t = result?.totals;

  return (
    <div className="space-y-6" data-testid="drum-schedule">
      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <SharedIodbCard title="Step 1 - IODB" icon={Upload} file={iodb} onChange={setIodb}>
          {demand && (
            <div className="mt-3 text-xs" style={{ color: 'var(--t0)' }}>
              <p className="flex items-center gap-1.5 font-semibold"><CheckCircle2 className="w-4 h-4 text-green-500" />
                {demand.stats.demand} cable requirements ({demand.stats.branch} branch, {demand.stats.main} main, shared main cables counted once)</p>
              <p style={{ color: 'var(--t1)' }}>{demand.stats.total_length} m in total · {Object.entries(demand.issue_counts).map(([k, v]) => `${v} ${k.toLowerCase()}${v > 1 ? 's' : ''}`).join(' · ') || 'no validation issues'}</p>
              {issueList(demand.issues.filter((i) => i.severity !== 'INFO'))}
            </div>
          )}
        </SharedIodbCard>

        <FileUploadCard title="Step 2 - Drum Master" icon={FileText} file={masterFile} onChange={setMasterFile}
                        hint="Drum Master Excel: cable type, IS/NIS, standard drum length, drum quantity, split allowed, vendor ...">
          {master && (
            <div className="mt-3 text-xs" style={{ color: 'var(--t0)' }}>
              <p className="flex items-center gap-1.5 font-semibold"><CheckCircle2 className="w-4 h-4 text-green-500" />
                {master.info.records} drum records · {master.info.cable_types} cable types · {master.info.total_drums} drums</p>
              <p style={{ color: 'var(--t1)' }}>{master.info.total_length} m of cable in total</p>
              {issueList(master.issues)}
            </div>
          )}
        </FileUploadCard>
      </div>

      <Card title="Step 3 - Scheduling Settings">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm" style={{ color: 'var(--t0)' }}>
          <label className="block">
            <span className="block font-medium mb-1">Minimum residual drum length (m)</span>
            <input type="number" min={0} max={15} step={1} value={minResidual} data-testid="min-residual"
                   onChange={(e) => { setMinResidual(Number(e.target.value)); setResult(null); }}
                   className="w-full border rounded-lg px-3 py-2 text-sm" style={{ borderColor: 'var(--b1)', background: 'var(--s1)', color: 'var(--t0)' }} />
            <span className="text-xs" style={{ color: 'var(--t1)' }}>Default 10 m, maximum 15 m. A drum is closed when this much or less is left.</span>
          </label>
          <label className="flex items-start gap-2 mt-6">
            <input type="checkbox" checked={useSplit} onChange={(e) => { setUseSplit(e.target.checked); setResult(null); }} className="mt-1" />
            <span><span className="block font-medium">Use Drum Master split rule</span>
              <span className="text-xs" style={{ color: 'var(--t1)' }}>Off = no cable tag is ever split across drums.</span></span>
          </label>
          <label className="flex items-start gap-2 mt-6 opacity-80">
            <input type="checkbox" checked disabled className="mt-1" />
            <span><span className="block font-medium">Exact cable type + IS/NIS matching</span>
              <span className="text-xs" style={{ color: 'var(--t1)' }}>Always on: no cable is allocated to another type or IS/NIS.</span></span>
          </label>
        </div>
        {(minResidual < 0 || minResidual > 15) && <p className="text-xs text-red-500 mt-2">The minimum residual must be between 0 and 15 m.</p>}
      </Card>

      <Card title="Step 4 - Generate">
        <Button onClick={generate} disabled={!ready} loading={busy} size="lg" fullWidth className="text-lg py-4">
          <Layers className="w-6 h-6" />
          {busy ? 'Generating...' : 'GENERATE DRUM SCHEDULE'}
        </Button>
        {!ready && <p className="text-sm mt-2 text-center" style={{ color: 'var(--t1)' }}>Choose the IODB and the Drum Master (both must be read successfully).</p>}
        {result && (
          <ul className="mt-4 space-y-1" data-testid="drum-progress">
            {result.progress.map((p) => (
              <li key={p.label} className="text-sm flex gap-2" style={{ color: 'var(--t0)' }}>
                <span className="font-medium">{p.label}</span>
                <span className={p.status === 'Completed' ? 'text-green-600' : 'text-red-500 font-semibold'}>- {p.status}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {result && t && (
        <Card title="Drum Schedule">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4 text-sm" style={{ color: 'var(--t0)' }}>
            {([['Required', t.required], ['Allocated', t.allocated], ['Shortage', t.shortage], ['Drums used', `${t.drums_used} of ${t.drums}`], ['Left on drums', t.remaining]] as [string, any][]).map(([k, v]) => (
              <div key={k} className="rounded-xl p-3" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
                <p className="text-xs" style={{ color: 'var(--t1)' }}>{k}{typeof v === 'number' ? ' (m)' : ''}</p>
                <p className={`text-lg font-bold ${k === 'Shortage' && Number(v) > 0 ? 'text-red-500' : ''}`}>{v}</p>
              </div>
            ))}
          </div>
          <div className="flex flex-wrap gap-2 mb-3">
            {TABS.map((n) => (
              <button key={n} onClick={() => setTab(n)} className="px-3 py-1.5 rounded-lg text-xs font-semibold"
                      style={{ background: tab === n ? 'var(--em)' : 'var(--s3)', color: tab === n ? '#fff' : 'var(--t0)', border: '1px solid var(--b1)' }}>
                {n}
                {n === 'Shortage' && result.shortage.length > 0 && ` (${result.shortage.length})`}
                {n === 'Exceptions' && result.exceptions.length > 0 && ` (${result.exceptions.length})`}
              </button>
            ))}
          </div>

          {tab === 'Drum Schedule' && (<>
            <Table empty="Nothing to schedule." rows={result.schedule} columns={[
              ['drum_id', 'Drum ID'], ['cable_type', 'Cable type'], ['cable_tag', 'Cable tag'], ['category', 'Category'], ['is_nis', 'IS/NIS'],
              ['manufacturer', 'Manufacturer'], ['usable', 'Usable (m)'], ['before', 'Before (m)'], ['allocated', 'Allocated (m)'],
              ['after', 'After (m)'], ['unallocated', 'Unallocated (m)'], ['status', 'Status'], ['source', 'IODB ref'], ['remarks', 'Remarks']]} />
            {result.schedule_truncated && <p className="text-xs mt-1" style={{ color: 'var(--t2)' }}>Preview shows the first rows; the Excel file has all of them.</p>}
          </>)}
          {tab === 'Cable Type Summary' && <Table empty="-" rows={result.summary} columns={[
            ['cable_type', 'Cable type'], ['is_nis', 'IS/NIS'], ['required', 'Required (m)'], ['available', 'Available (m)'], ['allocated', 'Allocated (m)'],
            ['balance', 'Balance (m)'], ['shortage', 'Shortage (m)'], ['excess', 'Excess (m)'], ['status', 'Status']]} />}
          {tab === 'Drum Utilization' && <Table empty="-" rows={result.utilization} columns={[
            ['drum_id', 'Drum ID'], ['cable_type', 'Cable type'], ['is_nis', 'IS/NIS'], ['original', 'Original (m)'], ['usable', 'Usable (m)'],
            ['allocated', 'Allocated (m)'], ['remaining', 'Remaining (m)'], ['status', 'Status']]} />}
          {tab === 'Shortage' && <Table empty="No shortage: every required metre is covered by the drums." rows={result.shortage} columns={[
            ['cable_type', 'Cable type'], ['is_nis', 'IS/NIS'], ['required', 'Required (m)'], ['available', 'Available (m)'], ['allocated', 'Allocated (m)'],
            ['shortage', 'Shortage (m)'], ['drums_consumed', 'Drums consumed'], ['remaining_balance', 'Remaining balance (m)'], ['message', 'Message']]} />}
          {tab === 'Excess / Balance' && (
            <div className="space-y-4">
              <div><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Excess by cable type</p>
                <Table empty="No excess." rows={result.excess.by_type} columns={[['cable_type', 'Cable type'], ['is_nis', 'IS/NIS'], ['excess', 'Excess (m)'], ['message', 'Message']]} /></div>
              <div><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Partly used drums</p>
                <Table empty="None." rows={result.excess.partial_drums} columns={[['drum_id', 'Drum ID'], ['cable_type', 'Cable type'], ['usable', 'Usable (m)'], ['allocated', 'Allocated (m)'], ['remaining', 'Remaining (m)'], ['status', 'Status']]} /></div>
              <div><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Unused drums</p>
                <Table empty="None." rows={result.excess.unused_drums} columns={[['drum_id', 'Drum ID'], ['cable_type', 'Cable type'], ['is_nis', 'IS/NIS'], ['usable', 'Length (m)']]} /></div>
            </div>
          )}
          {tab === 'Exceptions' && <Table empty="No exceptions." rows={result.exceptions} columns={[
            ['severity', 'Severity'], ['source', 'Source'], ['kind', 'Kind'], ['ref', 'Reference'], ['message', 'Message']]} />}

          <Button onClick={download} className="mt-5 bg-green-600 hover:bg-green-700">
            <Download className="w-5 h-5" />
            DOWNLOAD DRUM SCHEDULE
          </Button>
        </Card>
      )}
    </div>
  );
}
