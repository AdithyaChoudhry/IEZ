/**
 * Cable Lug Quantity Generator (sub-module of the Cable Schedule Generator).
 *
 * Upload a cable schedule -> Analyze -> Preview (summary / cable-wise / cable types / procurement / review) -> Download Excel.
 * All quantities come from the backend engine. Boundaries shown to the engineer:
 *   - physical cable quantity = unique cable tag (a tag repeated on signal rows is one cable);
 *   - cable length is shown but never used to calculate lugs;
 *   - ferrule / terminal-block terminations give 0 lugs; unknown arrangements are REVIEW, never guessed.
 */
import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Download, Info, Upload } from 'lucide-react';
import api from '@/services/api';
import Card from '../../ui/Card';
import Button from '../../ui/Button';
import Alert from '../../ui/Alert';
import FileUploadCard from '../../ui/FileUploadCard';

type Row = Record<string, any>;
const mp = { headers: { 'Content-Type': 'multipart/form-data' } };
const field = 'w-full border rounded-lg px-2 py-1.5 text-sm';
const fieldStyle = { borderColor: 'var(--b1)', background: 'var(--s1)', color: 'var(--t0)' };
const VIEWS = ['Summary', 'Cable-wise', 'Cable Type Summary', 'Lug Procurement', 'Review / Exceptions'] as const;
type View = (typeof VIEWS)[number];

function Table({ columns, rows, empty, cls }: { columns: [string, string][]; rows: Row[]; empty: string; cls?: (r: Row) => string }) {
  if (!rows.length) return <p className="text-sm py-3" style={{ color: 'var(--t1)' }}>{empty}</p>;
  return (
    <div className="overflow-auto max-h-[28rem] border rounded-lg" style={{ borderColor: 'var(--b1)' }}>
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

const statusCls = (r: Row) => (r.status === 'ERROR' || r.severity === 'ERROR' ? 'text-red-500' : r.status === 'REVIEW' || r.severity === 'REVIEW' ? 'text-amber-600' : r.source === 'USER OVERRIDE' ? 'text-blue-500' : '');

export default function LugQuantityGenerator() {
  const [file, setFile] = useState<File | null>(null);
  const [sheets, setSheets] = useState<Row[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [rules, setRules] = useState<Row>({ count_duplicates_once: true, instrumentation_use_lugs: false, control_use_lugs: false, power_use_lugs: true,
    lugged_ends: 'both', earth_lugged: true, allow_override: true, power_min_mm2: 4, control_max_mm2: 2.5 });
  const [overrides, setOverrides] = useState<Record<string, Row>>({});
  const [res, setRes] = useState<any>(null);
  const [view, setView] = useState<View>('Summary');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<{ tag: string; form: Row } | null>(null);
  const [f, setF] = useState<Row>({ search: '', type: '', category: '', lug: '', size: '', material: '', status: '' });

  const post = (url: string, fields: Record<string, any>) => {
    const fd = new FormData();
    Object.entries(fields).forEach(([k, v]) => { if (v !== null && v !== undefined) fd.append(k, v); });
    return api.post(url, fd, mp);
  };

  useEffect(() => {
    setRes(null); setSheets([]); setPicked([]); setOverrides({});
    if (!file) return;
    let off = false;
    post('/cable-schedule/lug/detect', { file })
      .then((r) => { if (!off) { setSheets(r.data.sheets.filter((s: Row) => s.used)); setPicked(r.data.default_sheets); setError(null); } })
      .catch((e) => { if (!off) setError(e.response?.data?.detail || 'Could not read the cable schedule'); });
    return () => { off = true; };
  }, [file]);

  const run = async (ov: Record<string, Row> = overrides) => {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const r = await post('/cable-schedule/lug/analyze', { file, rules: JSON.stringify({ ...rules, sheets: picked }), overrides: JSON.stringify(ov) });
      setRes(r.data);
    } catch (e: any) { setError(e.response?.data?.detail || 'Analysis failed'); } finally { setBusy(false); }
  };
  const download = async () => {
    try {
      const r = await api.get('/cable-schedule/lug/download', { responseType: 'blob' });
      const a = document.createElement('a'); a.href = window.URL.createObjectURL(new Blob([r.data])); a.setAttribute('download', 'Cable_Lug_Quantity_Report.xlsx');
      document.body.appendChild(a); a.click(); a.remove();
    } catch { setError('Download failed'); }
  };
  const saveOverride = (tag: string, form: Row | null) => {
    const next = { ...overrides };
    if (form) next[`tag:${tag}`] = form; else delete next[`tag:${tag}`];
    setOverrides(next); setEdit(null); run(next);
  };

  const k = res?.kpis;
  const cables: Row[] = res?.cable_wise || [];
  const filtered = useMemo(() => cables.filter((c) => {
    const q = f.search.toLowerCase();
    return (!q || c.cable_tag.toLowerCase().includes(q) || c.cable_type.toLowerCase().includes(q))
      && (!f.type || c.cable_type === f.type) && (!f.category || c.category === f.category)
      && (!f.lug || (f.lug === 'REVIEW' ? c.status !== 'OK' : c.lug_required === f.lug))
      && (!f.size || c.lug_size === f.size) && (!f.material || c.material === f.material) && (!f.status || c.status === f.status);
  }), [cables, f]);
  const opts = (key: string) => Array.from(new Set(cables.map((c) => c[key]).filter(Boolean))).sort() as string[];
  const reviewCables = cables.filter((c) => c.status !== 'OK');

  const toggle = (label: string, key: string) => (
    <label className="flex items-center gap-2 text-sm" style={{ color: 'var(--t0)' }}>
      <input type="checkbox" checked={!!rules[key]} onChange={(e) => { setRules({ ...rules, [key]: e.target.checked }); setRes(null); }} />{label}</label>);

  return (
    <div className="space-y-6" data-testid="lug-quantity">
      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}
      <div className="rounded-xl p-3 text-xs space-y-1" style={{ background: 'var(--s1)', border: '1px solid var(--b1)', color: 'var(--t0)' }}>
        <p className="flex gap-2"><Info className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--em)' }} /><span><b>Cable quantity</b> = unique cable tags (a tag repeated on several signal rows is one physical cable). <b>Cable length</b> is shown but never used for lugs: one cable = one termination set, whatever its length.</span></p>
        <p className="pl-6">Ferrule / terminal-block terminations give <b>0 lugs</b>. Where the arrangement cannot be established the cable is <b>REVIEW</b> and no quantity is invented. Lug type, material and part number are only taken from the schedule or your override.</p>
      </div>

      <FileUploadCard title="Step 1 - Cable Schedule (Excel)" icon={Upload} file={file} onChange={setFile}
                      hint="The generated Cable Schedule workbook can be used as is. It is only read - never changed.">
        {sheets.length > 0 && (
          <div className="mt-3 text-xs" style={{ color: 'var(--t0)' }}>
            <p className="font-semibold mb-1">Cable schedule sheets found (tick the ones to analyse):</p>
            {sheets.map((s) => (
              <label key={s.sheet} className="flex items-center gap-2">
                <input type="checkbox" checked={picked.includes(s.sheet)} onChange={(e) => { setPicked(e.target.checked ? [...picked, s.sheet] : picked.filter((x) => x !== s.sheet)); setRes(null); }} />
                {s.sheet} {s.hidden && <span style={{ color: 'var(--t2)' }}>(hidden in the workbook)</span>}
                {s.has_lug_columns && <span className="text-blue-500">lug columns</span>}
              </label>))}
          </div>)}
      </FileUploadCard>

      <Card title="Step 2 - Project rules" description="Used only when the schedule does not state the lug requirement or termination itself.">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {toggle('Count duplicate cable tags once', 'count_duplicates_once')}
          {toggle('Instrumentation (pair/triad) cables use cable lugs', 'instrumentation_use_lugs')}
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
        </div>
        <Button onClick={() => run()} loading={busy} disabled={!file || picked.length === 0} size="lg" fullWidth className="mt-5 text-lg py-4">
          {busy ? 'Analysing...' : 'ANALYZE CABLE SCHEDULE'}
        </Button>
        {Object.keys(overrides).length > 0 && <p className="text-xs mt-2 text-blue-500">{Object.keys(overrides).length} user override(s) applied.</p>}
      </Card>

      {res && k && (
        <Card title="Cable Lug Quantity Report">
          <div className="rounded-2xl p-5 mb-4 text-center" style={{ background: 'var(--s1)', border: '1px solid var(--em)' }}>
            <p className="text-xs uppercase tracking-wide" style={{ color: 'var(--t1)' }}>Total lugs required</p>
            <p className="text-5xl font-bold" style={{ color: 'var(--t0)' }} data-testid="total-lugs">{k.total_lugs}</p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4 text-sm" style={{ color: 'var(--t0)' }}>
            {([['Physical cables analysed', k.cables], ['Cable types', k.cable_types], ['Cables requiring lugs', k.with_lugs], ['Cables not requiring lugs', k.without_lugs], ['Cables requiring review', k.review]] as [string, number][]).map(([a, v]) => (
              <div key={a} className="rounded-xl p-3" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}><p className="text-xs" style={{ color: 'var(--t1)' }}>{a}</p>
                <p className={`text-lg font-bold ${a.includes('review') && v > 0 ? 'text-amber-600' : ''}`}>{v}</p></div>))}
          </div>
          <div className="flex flex-wrap gap-2 mb-3">
            {VIEWS.map((n) => <button key={n} onClick={() => setView(n)} className="px-3 py-1.5 rounded-lg text-xs font-semibold"
              style={{ background: view === n ? 'var(--em)' : 'var(--s3)', color: view === n ? '#fff' : 'var(--t0)', border: '1px solid var(--b1)' }}>
              {n}{n.startsWith('Review') && ` (${res.exceptions.length})`}</button>)}
          </div>

          {view === 'Summary' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Lugs by size</p><Table empty="No lugs required." rows={res.by_size} columns={[['size', 'Conductor size'], ['qty', 'Lugs']]} /></div>
              <div><p className="text-sm font-semibold mb-1" style={{ color: 'var(--t0)' }}>Lugs by material</p><Table empty="No lugs required." rows={res.by_material} columns={[['material', 'Material'], ['qty', 'Lugs']]} /></div>
              <div className="md:col-span-2 text-xs" style={{ color: 'var(--t1)' }}>Sheets analysed: {res.used_sheets.join(', ')} · {k.overrides} user override(s) · {k.errors} cable(s) with errors</div>
            </div>)}

          {view === 'Cable-wise' && (<>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3 text-xs">
              <input className={field} style={fieldStyle} placeholder="Search cable tag / type" value={f.search} onChange={(e) => setF({ ...f, search: e.target.value })} />
              <select className={field} style={fieldStyle} value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}><option value="">All cable types</option>{opts('cable_type').map((o) => <option key={o}>{o}</option>)}</select>
              <select className={field} style={fieldStyle} value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}><option value="">All categories</option>{opts('category').map((o) => <option key={o}>{o}</option>)}</select>
              <select className={field} style={fieldStyle} value={f.lug} onChange={(e) => setF({ ...f, lug: e.target.value })}><option value="">Lug: all</option><option value="YES">Lug required</option><option value="NO">No lug</option><option value="REVIEW">Review</option></select>
              <select className={field} style={fieldStyle} value={f.size} onChange={(e) => setF({ ...f, size: e.target.value })}><option value="">All lug sizes</option>{opts('lug_size').map((o) => <option key={o}>{o}</option>)}</select>
              <select className={field} style={fieldStyle} value={f.material} onChange={(e) => setF({ ...f, material: e.target.value })}><option value="">All materials</option>{opts('material').map((o) => <option key={o}>{o}</option>)}</select>
              <select className={field} style={fieldStyle} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}><option value="">All status</option><option>OK</option><option>REVIEW</option><option>ERROR</option></select>
              <span className="self-center" style={{ color: 'var(--t1)' }}>{filtered.length} of {cables.length} cables</span>
            </div>
            <Table empty="No cable matches the filters." rows={filtered} cls={statusCls} columns={[['cable_tag', 'Cable tag'], ['cable_type', 'Cable type'], ['category', 'Category'], ['cores', 'Cores'], ['from', 'From'], ['to', 'To'], ['length', 'Length (info)'],
              ['lug_required', 'Lug'], ['termination', 'Termination'], ['lug_from', 'Lug from'], ['lug_to', 'Lug to'], ['total', 'Total lugs'], ['lug_size', 'Size'], ['material', 'Material'], ['status', 'Status'], ['source', 'Source'], ['sheets', 'Sheet'], ['rows', 'Row'], ['reason', 'Basis']]} />
          </>)}

          {view === 'Cable Type Summary' && <Table empty="-" rows={res.types} cls={statusCls} columns={[['cable_type', 'Cable type'], ['is_nis', 'IS/NIS'], ['cable_qty', 'Cable qty'], ['cores', 'Cores'], ['lug_required', 'Lug required'],
            ['lug_from', 'Lug from / cable'], ['lug_to', 'Lug to / cable'], ['per_cable', 'Lugs / cable'], ['total', 'Total lugs'], ['lug_size', 'Size'], ['lug_type', 'Lug type'], ['material', 'Material'], ['source', 'Source'], ['reason', 'Reason']]} />}

          {view === 'Lug Procurement' && <Table empty="No lugs required by the analysed cables." rows={res.procurement} columns={[['lug_type', 'Lug type'], ['conductor_size', 'Conductor size'], ['material', 'Material'], ['spec', 'Specification / part no.'],
            ['use', 'Use'], ['from_qty', 'From-end qty'], ['to_qty', 'To-end qty'], ['qty', 'Total qty'], ['cables', 'Cables']]} />}

          {view === 'Review / Exceptions' && (<div className="space-y-4">
            <Table empty="No exceptions." rows={res.exceptions} cls={statusCls} columns={[['severity', 'Severity'], ['kind', 'Kind'], ['ref', 'Cable / reference'], ['sheet', 'Sheet'], ['row', 'Row'], ['message', 'Message']]} />
            {rules.allow_override && reviewCables.length > 0 && (
              <div><p className="text-sm font-semibold mb-1 flex gap-1" style={{ color: 'var(--t0)' }}><AlertTriangle className="w-4 h-4 text-amber-600" /> Cables needing a decision - manual override (marked USER OVERRIDE, never silent)</p>
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
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs" style={{ color: 'var(--t0)' }}>
                <label>Lug required<select className={field} style={fieldStyle} value={edit.form.lug_required || ''} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, lug_required: e.target.value } })}>
                  <option>YES</option><option>NO</option><option>REVIEW</option></select></label>
                {([['lug_from', 'Lug from qty'], ['lug_to', 'Lug to qty'], ['lug_type', 'Lug type'], ['lug_size', 'Lug size'], ['lug_material', 'Material'], ['remarks', 'Remarks']] as const).map(([key, label]) => (
                  <label key={key}>{label}<input className={field} style={fieldStyle} value={edit.form[key] ?? ''} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, [key]: e.target.value } })} /></label>))}
              </div>
              <div className="flex gap-2">
                <Button onClick={() => saveOverride(edit.tag, edit.form)} className="bg-blue-600 hover:bg-blue-700">Apply override</Button>
                <Button onClick={() => saveOverride(edit.tag, null)} className="bg-gray-500 hover:bg-gray-600">Remove override</Button>
                <Button onClick={() => setEdit(null)} className="bg-gray-400 hover:bg-gray-500">Cancel</Button>
              </div>
            </div>)}

          <Button onClick={download} className="mt-5 bg-green-600 hover:bg-green-700"><Download className="w-5 h-5" /> DOWNLOAD CABLE LUG QUANTITY REPORT</Button>
        </Card>
      )}
    </div>
  );
}
