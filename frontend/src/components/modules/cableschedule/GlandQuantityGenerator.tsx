/**
 * Cable Gland Quantity Generator (sub-module of the Cable Schedule Generator).
 *
 *   A  Gland Quantity     - upload a cable schedule -> quantities by gland / cable type / location, OD check, exceptions, Excel report
 *   B  Gland Size Advisor - cable OD (+ construction ...) -> Metric / NPT / BSP / ET options with sources and advice
 *   C  Reference          - standards, principles, the reference tables and the vendor-table import
 *
 * Every number and recommendation comes from the backend. The result is an ENGINEERING RECOMMENDATION, never a final selection.
 */
import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, Download, FileText, Info, Upload } from 'lucide-react';
import api from '@/services/api';
import Card from '../../ui/Card';
import Button from '../../ui/Button';
import Alert from '../../ui/Alert';
import FileUploadCard from '../../ui/FileUploadCard';

type Row = Record<string, any>;
const CONSTRUCTIONS = ['UNARMOURED', 'ARMOURED', 'BRAIDED', 'FLEXIBLE', 'FLAT', 'OTHER'];
const STANDARDS = ['METRIC', 'NPT', 'BSP', 'ET'];
const form = (fields: Record<string, File | string | null | undefined>) => {
  const f = new FormData();
  Object.entries(fields).forEach(([k, v]) => { if (v !== null && v !== undefined && v !== '') f.append(k, v as any); });
  return f;
};
const mp = { headers: { 'Content-Type': 'multipart/form-data' } };
const field = 'w-full border rounded-lg px-2 py-1.5 text-sm';
const fieldStyle = { borderColor: 'var(--b1)', background: 'var(--s1)', color: 'var(--t0)' };

function Table({ columns, rows, empty, hl }: { columns: [string, string][]; rows: Row[]; empty: string; hl?: (r: Row) => string }) {
  if (!rows.length) return <p className="text-sm py-3" style={{ color: 'var(--t1)' }}>{empty}</p>;
  return (
    <div className="overflow-auto max-h-[26rem] border rounded-lg" style={{ borderColor: 'var(--b1)' }}>
      <table className="w-full text-xs">
        <thead className="sticky top-0" style={{ background: 'var(--s2)' }}>
          <tr>{columns.map(([, h]) => <th key={h} className="px-2 py-1.5 text-left font-medium whitespace-nowrap" style={{ color: 'var(--t1)' }}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={`border-t ${hl ? hl(r) : ''}`} style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }}>
              {columns.map(([k]) => <td key={k} className="px-2 py-1 whitespace-nowrap">{r[k] === null || r[k] === undefined || r[k] === '' ? '-' : String(r[k])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const resultClass = (v: string) =>
  v === 'MATCH' || v === 'VALID' ? 'text-green-600 font-semibold' : v === 'REVIEW' || v === 'BORDERLINE' ? 'text-amber-600 font-semibold' : 'text-red-500 font-semibold';

const Banner = ({ text }: { text: string }) => (
  <div className="flex gap-2 rounded-xl p-3 text-xs" style={{ background: 'var(--s1)', border: '1px solid var(--b1)', color: 'var(--t0)' }}>
    <Info className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: 'var(--em)' }} /> <span>{text}</span>
  </div>
);

export default function GlandQuantityGenerator() {
  const [tab, setTab] = useState<'A' | 'B' | 'C'>('A');
  const [error, setError] = useState<string | null>(null);
  const [refFile, setRefFile] = useState<File | null>(null);
  const [reference, setReference] = useState<any>(null);
  const [rule, setRule] = useState('');

  // project settings (shared by A and B)
  const [proj, setProj] = useState({ manufacturer: '', series: '', material: '', thread: '', hazardous: false, ip: '', gland_type: '', mapping: '' });
  const project = useMemo(() => {
    const mapping: Record<string, string> = {};
    proj.mapping.split('\n').forEach((l) => { const [k, v] = l.split('='); if (k && v) mapping[k.trim()] = v.trim(); });
    return JSON.stringify({ ...proj, hazardous: proj.hazardous || null, mapping });
  }, [proj]);

  useEffect(() => {
    api.get('/cable-schedule/gland/reference').then((r) => { setReference(r.data); setRule(r.data.rule); }).catch(() => undefined);
  }, []);

  return (
    <div className="space-y-6" data-testid="gland-quantity">
      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}
      <Banner text={rule || 'Cable OD -> sealing/clamping compatibility of the gland. Thread standard -> connection to the equipment/enclosure.'} />
      <Banner text={reference?.disclaimer || 'ENGINEERING RECOMMENDATION - final selection must be confirmed against the manufacturer datasheet.'} />

      <div className="flex flex-wrap gap-2">
        {([['A', 'A - Gland Quantity'], ['B', 'B - Gland Size Advisor'], ['C', 'C - Reference / Engineering Database']] as const).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)} className="px-4 py-2 rounded-xl text-sm font-semibold"
                  style={{ background: tab === k ? 'var(--em)' : 'var(--s3)', color: tab === k ? '#fff' : 'var(--t0)', border: '1px solid var(--b1)' }}>{label}</button>
        ))}
      </div>

      <Card title="Project settings" description="Priority: project specification > approved vendor/project gland table > generic reference. Empty fields are not applied.">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-sm" style={{ color: 'var(--t0)' }}>
          {([['manufacturer', 'Preferred manufacturer'], ['series', 'Preferred gland series'], ['material', 'Preferred material'], ['gland_type', 'Preferred gland type'], ['ip', 'Default IP rating (e.g. IP66)']] as const).map(([k, l]) => (
            <label key={k}><span className="block mb-1">{l}</span>
              <input className={field} style={fieldStyle} value={(proj as any)[k]} onChange={(e) => setProj({ ...proj, [k]: e.target.value })} /></label>
          ))}
          <label><span className="block mb-1">Preferred thread standard</span>
            <select className={field} style={fieldStyle} value={proj.thread} onChange={(e) => setProj({ ...proj, thread: e.target.value })}>
              <option value="">-</option>{STANDARDS.map((s) => <option key={s}>{s}</option>)}</select></label>
          <label className="flex items-center gap-2 mt-6"><input type="checkbox" checked={proj.hazardous} onChange={(e) => setProj({ ...proj, hazardous: e.target.checked })} /> Hazardous area by default</label>
          <label className="md:col-span-4"><span className="block mb-1">Project gland mapping / client specification (one per line: <code>cable type = gland</code>, e.g. <code>12PX1.5 Sqmm = M25</code>)</span>
            <textarea className={field} style={fieldStyle} rows={2} value={proj.mapping} onChange={(e) => setProj({ ...proj, mapping: e.target.value })} /></label>
        </div>
        <div className="mt-3 max-w-md">
          <FileUploadCard title="Approved vendor / project gland table (optional)" icon={FileText} file={refFile} onChange={setRefFile}
                          hint="Excel table in the template layout (see tab C). Its rows take priority over the built-in tables." />
        </div>
      </Card>

      {tab === 'A' && <TabA project={project} refFile={refFile} setError={setError} />}
      {tab === 'B' && <TabB project={project} refFile={refFile} setError={setError} proj={proj} />}
      {tab === 'C' && <TabC reference={reference} refFile={refFile} setError={setError} />}
    </div>
  );
}

// ───────────────────────────── A: gland quantity ─────────────────────────────
function TabA({ project, refFile, setError }: { project: string; refFile: File | null; setError: (m: string | null) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [detect, setDetect] = useState<any>(null);
  const [sheets, setSheets] = useState<string[]>([]);
  const [cd, setCd] = useState<Record<string, Row>>({});
  const [defaultQty, setDefaultQty] = useState('');
  const [repeated, setRepeated] = useState('once');
  const [res, setRes] = useState<any>(null);
  const [view, setView] = useState('Gland Summary');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setDetect(null); setRes(null); setSheets([]); setCd({});
    if (!file) return;
    let off = false;
    api.post('/cable-schedule/gland/detect', form({ file }), mp)
      .then((r) => { if (!off) { setDetect(r.data); setSheets(r.data.default_sheets); setError(null); } })
      .catch((e) => { if (!off) setError(e.response?.data?.detail || 'Could not read the cable schedule'); });
    return () => { off = true; };
  }, [file]);

  const setType = (key: string, patch: Row) => { setCd({ ...cd, [key]: { ...(cd[key] || {}), ...patch } }); setRes(null); };

  const run = async () => {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const data: Record<string, Row> = {};
      Object.entries(cd).forEach(([k, v]) => { data[k] = v; });
      const r = await api.post('/cable-schedule/gland/analyze', form({
        file, reference_file: refFile, project,
        settings: JSON.stringify({ sheets, default_qty: defaultQty, repeated_rows: repeated }), cable_data: JSON.stringify(data),
      }), mp);
      setRes(r.data); setView('Gland Summary');
    } catch (e: any) { setError(e.response?.data?.detail || 'Analysis failed'); } finally { setBusy(false); }
  };
  const download = async () => {
    try {
      const r = await api.get('/cable-schedule/gland/download', { responseType: 'blob' });
      const a = document.createElement('a'); a.href = window.URL.createObjectURL(new Blob([r.data])); a.setAttribute('download', 'Gland_Quantity_Report.xlsx');
      document.body.appendChild(a); a.click(); a.remove();
    } catch { setError('Download failed'); }
  };
  const S = res?.summary;
  const VIEWS = ['Gland Summary', 'By Cable Type', 'Cable-wise', 'By Location', 'OD Advisory', 'Exceptions'];

  return (
    <div className="space-y-6">
      <FileUploadCard title="Step 1 - Cable Schedule (Excel)" icon={Upload} file={file} onChange={setFile}
                      hint="The workbook is only read. Cable schedule sheets are found by their gland columns; the file is never changed.">
        {detect && (
          <div className="mt-3 text-xs" style={{ color: 'var(--t0)' }}>
            <p className="font-semibold mb-1">Sheets with gland columns (tick the ones to count):</p>
            {detect.sheets.filter((s: Row) => s.used).map((s: Row) => (
              <label key={s.sheet} className="flex items-center gap-2">
                <input type="checkbox" checked={sheets.includes(s.sheet)} onChange={(e) => { setSheets(e.target.checked ? [...sheets, s.sheet] : sheets.filter((x) => x !== s.sheet)); setRes(null); }} />
                {s.sheet} {s.hidden && <span style={{ color: 'var(--t2)' }}>(hidden in the workbook)</span>}
              </label>
            ))}
            <p className="mt-1" style={{ color: 'var(--t1)' }}>{detect.cable_types.length} cable types · {detect.occurrences} gland entries</p>
          </div>
        )}
      </FileUploadCard>

      {detect && (
        <Card title="Step 2 - Cable OD and construction per cable type" description="Optional but needed for the gland check. The schedule's own gland is shown and is never overwritten.">
          <div className="overflow-auto max-h-96 border rounded-lg" style={{ borderColor: 'var(--b1)' }}>
            <table className="w-full text-xs">
              <thead style={{ background: 'var(--s2)' }}><tr>{['Cable type', 'Cables', 'Existing gland (schedule)', 'Cable OD (mm)', 'Construction', 'Bedding (mm)', 'Armour min', 'Armour max'].map((h) =>
                <th key={h} className="px-2 py-1.5 text-left font-medium" style={{ color: 'var(--t1)' }}>{h}</th>)}</tr></thead>
              <tbody>
                {detect.cable_types.map((t: Row) => {
                  const v = cd[t.key] || {};
                  const cons = v.construction || t.construction;
                  return (
                    <tr key={t.key} className="border-t" style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }}>
                      <td className="px-2 py-1">{t.cable_type}</td><td className="px-2 py-1">{t.cables}</td>
                      <td className="px-2 py-1">{t.existing_glands.join(', ') || '-'}</td>
                      <td className="px-2 py-1"><input className={field} style={{ ...fieldStyle, width: '6rem' }} placeholder={t.od ? String(t.od) : 'mm'} value={v.od ?? ''} onChange={(e) => setType(t.key, { od: e.target.value })} /></td>
                      <td className="px-2 py-1"><select className={field} style={{ ...fieldStyle, width: '8rem' }} value={cons} onChange={(e) => setType(t.key, { construction: e.target.value })}>
                        {CONSTRUCTIONS.map((c) => <option key={c}>{c}</option>)}</select>{!t.construction_stated && !v.construction && <span className="ml-1 text-amber-600">assumed</span>}</td>
                      {['bedding', 'armour_min', 'armour_max'].map((k) => (
                        <td key={k} className="px-2 py-1"><input disabled={cons !== 'ARMOURED'} className={field} style={{ ...fieldStyle, width: '5rem' }} value={v[k] ?? ''} onChange={(e) => setType(t.key, { [k]: e.target.value })} /></td>))}
                    </tr>);
                })}
              </tbody>
            </table>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 text-sm" style={{ color: 'var(--t0)' }}>
            <label><span className="block mb-1 font-medium">Default gland quantity when a size has none (project rule)</span>
              <input className={field} style={fieldStyle} placeholder="empty = flag MISSING GLAND QUANTITY" value={defaultQty} onChange={(e) => { setDefaultQty(e.target.value); setRes(null); }} /></label>
            <label><span className="block mb-1 font-medium">Identical termination rows of one cable</span>
              <select className={field} style={fieldStyle} value={repeated} onChange={(e) => { setRepeated(e.target.value); setRes(null); }}>
                <option value="once">Count once (shared cable - default)</option><option value="sum">Add the quantities</option></select></label>
          </div>
          <Button onClick={run} loading={busy} disabled={!file || sheets.length === 0} size="lg" fullWidth className="mt-5 text-lg py-4">
            {busy ? 'Analysing...' : 'GENERATE GLAND QUANTITY'}
          </Button>
        </Card>
      )}

      {res && S && (
        <Card title="Gland Quantity Report">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4 text-sm" style={{ color: 'var(--t0)' }}>
            {([['Total glands', res.totals.glands], ['Cable types', res.totals.cable_types], ['Cables', res.totals.cables], ['Errors', res.totals.errors], ['Warnings', res.totals.warnings]] as [string, any][]).map(([k, v]) => (
              <div key={k} className="rounded-xl p-3" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}><p className="text-xs" style={{ color: 'var(--t1)' }}>{k}</p>
                <p className={`text-lg font-bold ${k === 'Errors' && v > 0 ? 'text-red-500' : ''}`}>{v}</p></div>))}
          </div>
          <div className="flex flex-wrap gap-2 mb-3">
            {VIEWS.map((n) => <button key={n} onClick={() => setView(n)} className="px-3 py-1.5 rounded-lg text-xs font-semibold"
              style={{ background: view === n ? 'var(--em)' : 'var(--s3)', color: view === n ? '#fff' : 'var(--t0)', border: '1px solid var(--b1)' }}>
              {n}{n === 'Exceptions' && ` (${res.exceptions.length})`}</button>)}
          </div>
          {view === 'Gland Summary' && <Table empty="No glands counted." rows={S.by_gland} columns={[['gland_type', 'Gland type'], ['thread', 'Thread standard'], ['gland_size', 'Gland size'], ['material', 'Material'], ['certification', 'Certification'], ['qty', 'Quantity']]} />}
          {view === 'By Cable Type' && <Table empty="-" rows={S.by_cable_type} columns={[['cable_type', 'Cable type'], ['gland_type', 'Gland type'], ['thread', 'Thread'], ['gland_size', 'Gland size'], ['qty', 'Quantity'], ['cables', 'Cables']]} />}
          {view === 'Cable-wise' && <>
            <Table empty="-" rows={res.cable_wise} hl={(r) => (r.result === 'MISMATCH' ? 'text-red-500' : '')} columns={[['cable_type', 'Cable type'], ['cable_tag', 'Cable tag'], ['location', 'Location'], ['gland_type', 'Gland type'], ['thread', 'Thread'], ['od', 'OD (mm)'], ['existing', 'Existing gland'], ['qty', 'Qty'], ['recommended', 'Recommended'], ['result', 'Result']]} />
            {res.cable_wise_truncated && <p className="text-xs mt-1" style={{ color: 'var(--t2)' }}>Preview shows the first rows; the Excel report has all of them.</p>}</>}
          {view === 'By Location' && <div className="space-y-3">
            <Table empty="-" rows={S.location_totals} columns={[['location', 'Location'], ['qty', 'Total quantity']]} />
            <Table empty="-" rows={S.by_location} columns={[['location', 'Location'], ['thread', 'Thread'], ['gland_size', 'Gland size'], ['qty', 'Quantity']]} /></div>}
          {view === 'OD Advisory' && <Table empty="-" rows={res.advisory.map((a: Row) => ({ ...a, existing: a.existing.join(', '), alternatives: (a.alternatives || []).join(', '), src: a.source ? `${a.source.manufacturer} ${a.source.series}` : '' }))}
            columns={[['cable_type', 'Cable type'], ['construction', 'Construction'], ['od', 'OD (mm)'], ['existing', 'Existing (schedule)'], ['recommended', 'Recommended'], ['alternatives', 'Alternatives'], ['result', 'Result'], ['src', 'Source'], ['message', 'Message']]} />}
          {view === 'Exceptions' && <Table empty="No exceptions." rows={res.exceptions} hl={(r) => (r.severity === 'ERROR' ? 'text-red-500' : r.severity === 'WARNING' ? 'text-amber-600' : '')}
            columns={[['severity', 'Severity'], ['kind', 'Kind'], ['ref', 'Reference'], ['message', 'Message']]} />}
          <Button onClick={download} className="mt-5 bg-green-600 hover:bg-green-700"><Download className="w-5 h-5" /> DOWNLOAD GLAND QUANTITY REPORT</Button>
        </Card>
      )}
    </div>
  );
}

// ───────────────────────────── B: advisor ─────────────────────────────
function TabB({ project, refFile, setError, proj }: { project: string; refFile: File | null; setError: (m: string | null) => void; proj: any }) {
  const [f, setF] = useState<Row>({ cable_type: '', od: '', construction: 'UNARMOURED', hazardous: !!proj.hazardous, ip: proj.ip || '', standards: [...STANDARDS] });
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const set = (patch: Row) => setF({ ...f, ...patch });
  const run = async () => {
    setBusy(true); setError(null); setRes(null);
    try { setRes((await api.post('/cable-schedule/gland/advise', form({ inputs: JSON.stringify(f), project, reference_file: refFile }), mp)).data); }
    catch (e: any) { setError(e.response?.data?.detail || 'Advice failed'); } finally { setBusy(false); }
  };
  const inp = (k: string, label: string, ph = '') => (
    <label key={k}><span className="block mb-1">{label}</span><input className={field} style={fieldStyle} placeholder={ph} value={f[k] ?? ''} onChange={(e) => set({ [k]: e.target.value })} /></label>);
  const cand = (c: Row, tag: string) => (
    <div key={tag + c.gland_size + c.thread} className="rounded-xl p-3 text-xs space-y-1" style={{ background: 'var(--s1)', border: '1px solid var(--b1)', color: 'var(--t0)' }}>
      <p className="text-sm font-semibold">{tag}: {c.manufacturer} {c.series} - size {c.gland_size} <span className="font-normal">({c.thread})</span></p>
      <p>{c.gland_type} · {c.construction.toLowerCase()} · cable OD range {c.od_range[0]}-{c.od_range[1]} mm{c.bedding_range ? ` · bedding ${c.bedding_range[0]}-${c.bedding_range[1]} mm` : ''}{c.armour_ranges?.length ? ` · armour ${c.armour_ranges.map((a: number[]) => a.join('-')).join(' / ')} mm` : ''}</p>
      <p>IP: {c.ip} · Ex: {c.ex} · material: {c.material} · temperature: {c.temperature}</p>
      {c.checks.map((x: string, i: number) => <p key={i}>{x}</p>)}
      <p className="text-amber-600">{c.flags.join(' · ')}</p>
      <p style={{ color: 'var(--t1)' }}>Source: {c.source.manufacturer} {c.source.series} - {c.source.document || 'n/a'} {c.source.url && <a className="underline" href={c.source.url} target="_blank" rel="noreferrer">{c.source.url}</a>} ({c.source.revision || 'no revision'}) · tier {c.source.tier}</p>
    </div>);
  return (
    <div className="space-y-6">
      <Card title="Cable data" description="Required: cable OD, construction. Everything else refines the check.">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-sm" style={{ color: 'var(--t0)' }}>
          {inp('cable_type', 'Cable type', 'e.g. 12P x 1.5 Sq.mm')}{inp('od', 'Cable OD (mm) *', 'e.g. 14.2')}
          <label><span className="block mb-1">Construction *</span><select className={field} style={fieldStyle} value={f.construction} onChange={(e) => set({ construction: e.target.value })}>{CONSTRUCTIONS.map((c) => <option key={c}>{c}</option>)}</select></label>
          {inp('entry_thread', 'Enclosure entry thread', 'e.g. 1/2" NPT')}
          {inp('bedding', 'Bedding diameter (mm)')}{inp('armour_min', 'Armour min (mm)')}{inp('armour_max', 'Armour max (mm)')}{inp('armour_type', 'Armour type')}
          {inp('cores', 'Number of cores')}{inp('csa', 'Cross-section (mm²)')}{inp('voltage', 'Voltage class')}
          <label><span className="block mb-1">IS / NIS</span><select className={field} style={fieldStyle} value={f.is_nis || ''} onChange={(e) => set({ is_nis: e.target.value })}><option value="">-</option><option>IS</option><option>NIS</option></select></label>
          {inp('ip', 'Required IP rating', 'IP66')}{inp('material', 'Material requirement')}{inp('temperature', 'Temperature requirement')}
          <label className="flex items-center gap-2 mt-6"><input type="checkbox" checked={!!f.hazardous} onChange={(e) => set({ hazardous: e.target.checked })} /> Hazardous area</label>
          {f.hazardous && <>{inp('zone', 'Zone / EPL', 'Zone 1 / Gb')}{inp('gas_group', 'Gas / dust group', 'IIC')}{inp('temp_class', 'Temperature class', 'T4')}{inp('protection', 'Protection concept', 'Ex d / Ex e / Ex t')}{inp('certification', 'Required certification', 'ATEX / IECEx')}
            <label className="flex items-center gap-2 mt-6"><input type="checkbox" checked={!!f.barrier} onChange={(e) => set({ barrier: e.target.checked })} /> Barrier gland required</label></>}
        </div>
        <div className="flex flex-wrap gap-4 mt-3 text-sm" style={{ color: 'var(--t0)' }}>
          {STANDARDS.map((s) => <label key={s} className="flex items-center gap-1"><input type="checkbox" checked={f.standards.includes(s)} onChange={(e) => set({ standards: e.target.checked ? [...f.standards, s] : f.standards.filter((x: string) => x !== s) })} />{s}</label>)}
        </div>
        <Button onClick={run} loading={busy} className="mt-4 bg-blue-600 hover:bg-blue-700">{busy ? 'Calculating...' : 'RECOMMEND GLAND'}</Button>
      </Card>

      {res && (
        <Card title="Gland recommendation" description={res.disclaimer}>
          <div className="space-y-5">
            {res.results.map((r: Row) => (
              <div key={r.standard} data-testid={`result-${r.standard}`}>
                <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>{r.standard} <span className={resultClass(r.status)}>{r.status}</span></p>
                {r.notice && <p className="text-xs text-amber-600 flex gap-1 mt-1"><AlertTriangle className="w-3 h-3 mt-0.5" />{r.notice}</p>}
                <p className="text-xs mt-1" style={{ color: 'var(--t1)' }}>{r.message}</p>
                {r.reason && <p className="text-xs mt-1" style={{ color: 'var(--t0)' }}>{r.reason}</p>}
                <div className="space-y-2 mt-2">
                  {r.preferred && cand(r.preferred, 'Preferred')}
                  {r.alternatives.map((a: Row) => cand(a, 'Alternative'))}
                </div>
              </div>))}
            <div><p className="text-sm font-bold mb-1" style={{ color: 'var(--t0)' }}>Engineering advice</p>
              {res.advice.map((a: string, i: number) => <p key={i} className="text-xs mb-1" style={{ color: 'var(--t0)' }}><CheckCircle2 className="inline w-3 h-3 mr-1 text-green-500" />{a}</p>)}</div>
            <div><p className="text-sm font-bold mb-1" style={{ color: 'var(--t0)' }}>Standards basis</p>
              {res.standards.map((s: Row) => <p key={s.id} className="text-xs mb-1" style={{ color: 'var(--t1)' }}><b>{s.id}</b> - {s.use}</p>)}</div>
          </div>
        </Card>
      )}
    </div>
  );
}

// ───────────────────────────── C: reference ─────────────────────────────
function TabC({ reference, refFile, setError }: { reference: any; refFile: File | null; setError: (m: string | null) => void }) {
  const [check, setCheck] = useState<any>(null);
  useEffect(() => {
    setCheck(null);
    if (!refFile) return;
    api.post('/cable-schedule/gland/reference/check', form({ reference_file: refFile }), mp).then((r) => setCheck(r.data)).catch((e) => setError(e.response?.data?.detail || 'Could not read the table'));
  }, [refFile]); // eslint-disable-line react-hooks/exhaustive-deps
  const template = async () => {
    const r = await api.get('/cable-schedule/gland/reference/template', { responseType: 'blob' });
    const a = document.createElement('a'); a.href = window.URL.createObjectURL(new Blob([r.data])); a.setAttribute('download', 'Gland_Reference_Table_Template.xlsx');
    document.body.appendChild(a); a.click(); a.remove();
  };
  if (!reference) return <p className="text-sm" style={{ color: 'var(--t1)' }}>Loading the reference database…</p>;
  return (
    <div className="space-y-6">
      <Card title="Selection basis">
        {reference.principles.map((p: string, i: number) => <p key={i} className="text-sm mb-2" style={{ color: 'var(--t0)' }}>• {p}</p>)}
        <p className="text-sm font-semibold mt-2" style={{ color: 'var(--t0)' }}>{reference.priority}</p>
      </Card>
      <Card title="Standards">
        {reference.standards.map((s: Row) => <p key={s.id} className="text-sm mb-2" style={{ color: 'var(--t0)' }}><b>{s.id}</b> - {s.title}. {s.use}</p>)}
      </Card>
      <Card title="What the built-in tables contain">
        {reference.limits.map((l: string, i: number) => <p key={i} className="text-sm mb-1 flex gap-2" style={{ color: 'var(--t0)' }}><AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0" />{l}</p>)}
      </Card>
      <Card title="Vendor / project gland table" description="Upload your approved table (project settings card above). ET, BSP, IP, Ex, material and temperature come only from here.">
        <Button onClick={template} className="bg-blue-600 hover:bg-blue-700"><Download className="w-4 h-4" /> Download table template</Button>
        {check && (
          <div className="mt-3 text-sm" style={{ color: 'var(--t0)' }}>
            <p className="font-semibold">{check.rows} gland rows read · thread standards offered: {check.standards_offered.join(', ') || 'none'}</p>
            {check.problems.map((p: string, i: number) => <p key={i} className="text-xs text-amber-600">{p}</p>)}
          </div>)}
      </Card>
      <Card title={`Reference gland table (${reference.rows.length} rows, CMP Products published example tables)`}>
        <Table empty="-" rows={reference.rows.map((r: Row) => ({ ...r, od: `${r.od_min}-${r.od_max}`, bed: r.bed_min != null ? `${r.bed_min}-${r.bed_max}` : '', arm: (r.armour_ranges || []).map((a: number[]) => a.join('-')).join(' / '), npt: r.npt.join(' / ') }))}
          columns={[['manufacturer', 'Manufacturer'], ['series', 'Series'], ['construction', 'Construction'], ['size', 'Size'], ['od', 'Cable OD (mm)'], ['bed', 'Bedding (mm)'], ['arm', 'Armour (mm)'], ['metric', 'Metric'], ['npt', 'NPT options'], ['ip', 'IP'], ['ex', 'Ex'], ['revision', 'Revision']]} />
        <p className="text-xs mt-2" style={{ color: 'var(--t1)' }}>Source: {reference.rows[0]?.source_doc} - {reference.rows[0]?.source_url}</p>
      </Card>
    </div>
  );
}
