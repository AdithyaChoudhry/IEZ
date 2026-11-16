/**
 * Loop Wiring Generator
 *
 *   I/O Assignment -> validate -> group by LOOP_NAME -> LOOP TYPE + SPD + TERM = TYPICAL -> one of 42 approved templates
 *   -> FIELD CODE mapping -> DATA BLOCK -> formula-driven drawing -> trace + validate -> preview -> LOOP_WIRING_GENERATED.xlsx
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { GitBranch, Upload, Download, CheckCircle2, AlertTriangle, XCircle, ChevronRight, Loader2, FlaskConical, Library } from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import ProjectSelector from '../ui/ProjectSelector';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import FileUploadCard from '../ui/FileUploadCard';
import { getCurrentProject } from '@/services/projectContext';

type Row = Record<string, any>;
const mp = { headers: { 'Content-Type': 'multipart/form-data' } };
const BASE = '/loop-wiring/engine';

const STATUS_STYLE: Record<string, { bg: string; fg: string }> = {
  PASS: { bg: 'rgba(34,197,94,0.15)', fg: '#16a34a' },
  REVIEW: { bg: 'rgba(245,158,11,0.18)', fg: '#d97706' },
  ERROR: { bg: 'rgba(239,68,68,0.16)', fg: '#dc2626' },
  FAIL: { bg: 'rgba(239,68,68,0.16)', fg: '#dc2626' },
};
const Status = ({ s }: { s: string }) => {
  const st = STATUS_STYLE[s] || { bg: 'var(--s3)', fg: 'var(--t1)' };
  const Icon = s === 'PASS' ? CheckCircle2 : s === 'REVIEW' ? AlertTriangle : XCircle;
  return <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-semibold" style={{ background: st.bg, color: st.fg }}><Icon className="w-3 h-3" />{s}</span>;
};

const STEPS = ['1 · I/O Assignment source', '2 · Selected typical', '3 · Field Code mapping', '4 · Data Block', '5 · Field drawing', '6 · Control room drawing', '7 · Trace & validation'];

const th = 'px-2 py-1.5 text-left font-medium whitespace-nowrap';
const td = 'px-2 py-1';
const selectStyle: React.CSSProperties = { background: 'var(--s3)', color: 'var(--t0)', border: '1px solid var(--b1)', borderRadius: 8, padding: '4px 8px', fontSize: 12 };

function Table({ head, children, max = 'max-h-80' }: { head: string[]; children: React.ReactNode; max?: string }) {
  return (
    <div className={`overflow-auto ${max} border rounded-lg`} style={{ borderColor: 'var(--b1)' }}>
      <table className="w-full text-xs">
        <thead className="sticky top-0" style={{ background: 'var(--s2)' }}><tr>{head.map((h) => <th key={h} className={th} style={{ color: 'var(--t1)' }}>{h}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function Chain({ nodes }: { nodes: Row[] }) {
  return (
    <div className="flex items-stretch gap-1 overflow-x-auto pb-1">
      {nodes.map((n, i) => (
        <div key={i} className="flex items-center gap-1">
          <div className="rounded-lg px-2.5 py-1.5 text-xs min-w-[110px]" style={{ border: `1px ${n.broken ? 'dashed' : 'solid'} ${n.broken ? '#dc2626' : 'var(--b1)'}`, background: n.broken ? 'rgba(239,68,68,0.08)' : 'var(--s1)', color: 'var(--t0)' }}>
            <div className="font-semibold text-[10px] uppercase tracking-wide" style={{ color: 'var(--t1)' }}>{n.node}</div>
            <div className="font-mono">{n.id || <span style={{ color: '#dc2626' }}>— missing —</span>}</div>
            {Object.entries(n.terminals || {}).map(([k, v]) => (
              <div key={k} className="text-[10px]" style={{ color: v ? 'var(--t1)' : '#dc2626' }}>{k.replace(/^[A-Z]+_/, '')}: {(v as string) || '—'}</div>))}
          </div>
          {i < nodes.length - 1 && <ChevronRight className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--t2)' }} />}
        </div>))}
    </div>
  );
}

export default function LoopWiringGenerator() {
  const [file, setFile] = useState<File | null>(null);
  const [validating, setValidating] = useState(false);
  const [an, setAn] = useState<Row | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [flt, setFlt] = useState<Row>({ q: '', type: '', inst: '', area: '', term: '', spd: '', system: '', cab: '', status: '' });
  const [open, setOpen] = useState<string | null>(null);
  const [detail, setDetail] = useState<Row | null>(null);
  const [step, setStep] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<Row | null>(null);
  const [library, setLibrary] = useState<Row | null>(null);
  const [selftest, setSelftest] = useState<Row | null>(null);
  const [testing, setTesting] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => { api.get(`${BASE}/library`).then((r) => setLibrary(r.data)).catch(() => undefined); return () => { if (timer.current) window.clearTimeout(timer.current); }; }, []);
  useEffect(() => { setAn(null); setResult(null); setOpen(null); setDetail(null); setPicked(new Set()); }, [file]);

  const validate = async () => {
    if (!file) return;
    setValidating(true); setError(null); setResult(null); setOpen(null); setDetail(null);
    try {
      const fd = new FormData(); fd.append('file', file);
      const r = await api.post(`${BASE}/validate`, fd, mp);
      setAn(r.data);
      setPicked(new Set(r.data.loops.filter((l: Row) => l.status !== 'ERROR').map((l: Row) => l.loop)));
    } catch (e: any) { setAn(null); setError(e.response?.data?.detail || 'Could not read the I/O Assignment'); }
    setValidating(false);
  };

  const loops: Row[] = an?.loops || [];
  const opts = (k: string) => Array.from(new Set(loops.map((l) => l[k]).filter(Boolean))).sort() as string[];
  const filtered = useMemo(() => loops.filter((l) => {
    const q = flt.q.toLowerCase();
    return (!q || l.loop.toLowerCase().includes(q) || (l.service || '').toLowerCase().includes(q))
      && (!flt.type || l.loop_type === flt.type) && (!flt.inst || l.instrument === flt.inst) && (!flt.area || l.area === flt.area) && (!flt.term || l.term === flt.term)
      && (!flt.spd || l.spd === flt.spd) && (!flt.system || l.system === flt.system) && (!flt.cab || l.cabinet === flt.cab) && (!flt.status || l.status === flt.status);
  }), [loops, flt]);
  const selected = loops.filter((l) => picked.has(l.loop));
  const generable = selected.filter((l) => l.status !== 'ERROR');
  const toggle = (name: string) => { const n = new Set(picked); n.has(name) ? n.delete(name) : n.add(name); setPicked(n); };
  const setMany = (names: string[], on: boolean) => { const n = new Set(picked); names.forEach((x) => (on ? n.add(x) : n.delete(x))); setPicked(n); };

  const showLoop = async (name: string) => {
    if (open === name) { setOpen(null); setDetail(null); return; }
    setOpen(name); setDetail(null); setStep(0);
    try { const r = await api.get(`${BASE}/analysis/${an!.analysis_id}/loop/${encodeURIComponent(name)}`); setDetail(r.data); }
    catch (e: any) { setError(e.response?.data?.detail || 'Could not load the loop preview'); }
  };

  const generate = async () => {
    setGenerating(true); setError(null); setResult(null);
    try {
      const k = await api.post(`${BASE}/generate`, { analysis_id: an!.analysis_id, loops: selected.map((l) => l.loop), project_id: getCurrentProject() || undefined });
      const poll = async () => {
        try {
          const r = await api.get(`${BASE}/job/${k.data.job_id}`);
          if (r.data.status === 'done') { setResult(r.data.result); setGenerating(false); return; }
          if (r.data.status === 'error') { setError(r.data.error); setGenerating(false); return; }
          timer.current = window.setTimeout(poll, 800);
        } catch (e: any) { setError(e.response?.data?.detail || 'Lost contact with the generation job'); setGenerating(false); }
      };
      poll();
    } catch (e: any) { setError(e.response?.data?.detail || 'Generation could not be started'); setGenerating(false); }
  };

  const save = async (path: string, name: string) => {
    try {
      const r = await api.get(`${BASE}/${path}`, { responseType: 'blob' });
      const a = document.createElement('a'); a.href = window.URL.createObjectURL(new Blob([r.data])); a.setAttribute('download', name);
      document.body.appendChild(a); a.click(); a.remove();
    } catch { setError('Download failed'); }
  };

  const runSelftest = async () => {
    setTesting(true); setError(null);
    try { setSelftest((await api.get(`${BASE}/selftest`)).data); } catch (e: any) { setError(e.response?.data?.detail || 'Acceptance test could not run'); }
    setTesting(false);
  };

  const counts = an?.counts || {};
  return (
    <div className="space-y-6" data-testid="loop-wiring">
      <PageHeader icon={GitBranch} iconClassName="text-indigo-500" title="Loop Wiring Generator"
        description="I/O Assignment → LOOP TYPE + SPD + TERMINATION = typical → one of 42 approved templates → FIELD CODE mapping → DATA BLOCK → formula-driven loop drawing." />
      <ProjectSelector />
      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}

      <FileUploadCard title="Step 1 - I/O Assignment (STANDARD_IO_ASSIGNMENT_TEMPLATE)" icon={Upload} file={file} onChange={setFile}
        hint="The filled IO_ASSIGNMENT sheet. Columns are read by FIELD CODE (LOOP_NAME, TAG, IO_TYPE, LOOP_TYPE, SPD_ARR, TERM_ARR ...), never by position. The file is only read.">
        <div className="flex flex-wrap gap-2 mt-3">
          <Button size="sm" variant="secondary" onClick={() => save('master/io', 'STANDARD_IO_ASSIGNMENT_TEMPLATE_Final.xlsx')}><Download className="w-3.5 h-3.5" />I/O Assignment master</Button>
          <Button size="sm" variant="secondary" onClick={() => save('master/templates', 'LOOP_TYPICAL_TEMPLATES_FINAL_CORRECTED.xlsx')}><Download className="w-3.5 h-3.5" />Loop typical templates (42)</Button>
          <Button size="sm" variant="secondary" onClick={() => save('fixture', 'LOOP_WIRING_TEST_FIXTURE_IO_ASSIGNMENT.xlsx')}><FlaskConical className="w-3.5 h-3.5" />Test fixture (all 42 typicals)</Button>
        </div>
      </FileUploadCard>

      <Button onClick={validate} loading={validating} disabled={!file} size="lg" fullWidth className="text-lg py-4"><CheckCircle2 className="w-6 h-6" />{validating ? 'Validating...' : 'VALIDATE I/O ASSIGNMENT'}</Button>

      {an && (
        <>
          <Card title="Step 3 - Validation result" description={`Sheet ${an.sheet} (field codes in row ${an.header_row}) · ${an.rows} signal rows · ${an.spares} spare row(s) skipped`}>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {[['Loops', loops.length, ''], ['PASS', counts.PASS, 'PASS'], ['REVIEW', counts.REVIEW, 'REVIEW'], ['ERROR (not generated)', counts.ERROR, 'ERROR'], ['Template library', an.library_ok ? '42 / 42' : 'INCOMPLETE', an.library_ok ? 'PASS' : 'ERROR']].map(([k, v, s]) => (
                <div key={k as string} className="rounded-xl p-3" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
                  <div className="text-xs" style={{ color: 'var(--t1)' }}>{k}</div>
                  <div className="text-xl font-bold" style={{ color: s ? STATUS_STYLE[s as string].fg : 'var(--t0)' }}>{v}</div>
                </div>))}
            </div>
            {an.warnings?.map((w: string, i: number) => <p key={i} className="text-xs mt-2 text-amber-600">{w}</p>)}
            {an.global_issues?.map((g: Row, i: number) => <p key={i} className="text-xs mt-2 text-red-500">{g.text}</p>)}
          </Card>

          <Card title="Step 4 - Loop selection preview" description="One row per LOOP_NAME (all signals of a loop are one drawing). Tick the loops to generate; click a row for the 7-step preview.">
            <div className="flex flex-wrap gap-2 mb-3 items-center">
              <input placeholder="Search loop / service" value={flt.q} onChange={(e) => setFlt({ ...flt, q: e.target.value })} style={{ ...selectStyle, minWidth: 180 }} />
              {([['type', 'Loop type', 'loop_type'], ['inst', 'Instrument', 'instrument'], ['area', 'Area', 'area'], ['term', 'M / D', 'term'], ['spd', 'SPD A/B/C', 'spd'], ['system', 'System', 'system'], ['cab', 'Cabinet', 'cabinet'], ['status', 'Status', 'status']] as const).map(([k, label, key]) => (
                <select key={k} value={flt[k]} onChange={(e) => setFlt({ ...flt, [k]: e.target.value })} style={selectStyle}>
                  <option value="">{label}: all</option>{opts(key).map((o) => <option key={o} value={o}>{o}</option>)}</select>))}
              <span className="text-xs" style={{ color: 'var(--t1)' }}>{filtered.length} of {loops.length} shown</span>
            </div>
            <div className="flex flex-wrap gap-2 mb-3">
              <Button size="sm" variant="secondary" onClick={() => setMany(loops.filter((l) => l.status !== 'ERROR').map((l) => l.loop), true)}>Select all</Button>
              <Button size="sm" variant="secondary" onClick={() => setMany(filtered.map((l) => l.loop), true)}>Select filtered</Button>
              <Button size="sm" variant="secondary" onClick={() => setMany(filtered.map((l) => l.loop), false)}>Deselect filtered</Button>
              <Button size="sm" variant="ghost" onClick={() => setPicked(new Set())}>Clear</Button>
            </div>
            <Table head={['', 'Loop', 'Service', 'Loop type', 'SPD', 'Term', 'Calculated typical', 'Template', 'Signals', 'Status', 'Issues']} max="max-h-[28rem]">
              {filtered.map((l) => (
                <tr key={l.loop} className="border-t cursor-pointer" style={{ borderColor: 'var(--b1)', color: 'var(--t0)', background: open === l.loop ? 'var(--s2)' : undefined }} onClick={() => showLoop(l.loop)}>
                  <td className={td} onClick={(e) => e.stopPropagation()}><input type="checkbox" checked={picked.has(l.loop)} onChange={() => toggle(l.loop)} /></td>
                  <td className={`${td} font-mono`}>{l.loop}</td><td className={td}>{l.service}</td><td className={td}>{l.loop_type || '—'}</td><td className={td}>{l.spd || '—'}</td><td className={td}>{l.term || '—'}</td>
                  <td className={`${td} font-semibold`}>{l.typical || '—'}</td><td className={`${td} font-mono`}>{l.template || '—'}</td><td className={td}>{l.signals}</td>
                  <td className={td}><Status s={l.status} /></td><td className={td}>{l.errors ? <span className="text-red-500">{l.errors} error</span> : ''} {l.reviews ? <span className="text-amber-600">{l.reviews} review</span> : ''}</td>
                </tr>))}
            </Table>

            {open && (
              <div className="mt-4 rounded-xl p-4" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
                <div className="flex flex-wrap gap-1 mb-3">
                  {STEPS.map((s, i) => (
                    <button key={s} onClick={() => setStep(i)} className="px-2.5 py-1 rounded-lg text-xs font-semibold"
                      style={{ background: step === i ? 'var(--em)' : 'var(--s3)', color: step === i ? '#fff' : 'var(--t0)', border: '1px solid var(--b1)' }}>{s}</button>))}
                </div>
                {!detail ? <p className="text-sm flex items-center gap-2" style={{ color: 'var(--t0)' }}><Loader2 className="w-4 h-4 animate-spin" />Loading {open}...</p> : <Detail d={detail} step={step} />}
              </div>)}
          </Card>

          <Card title="Step 6 - Generate">
            <p className="text-sm mb-3" style={{ color: 'var(--t0)' }}>
              {selected.length} loop(s) selected · {generable.length} can be generated{selected.length - generable.length > 0 && <span className="text-red-500"> · {selected.length - generable.length} with ERROR will be skipped (listed in the report)</span>}
            </p>
            <Button onClick={generate} loading={generating} disabled={generable.length === 0} size="lg" fullWidth className="text-lg py-4"><GitBranch className="w-6 h-6" />{generating ? 'Generating...' : 'GENERATE LOOP WIRING'}</Button>
            {result && (
              <div className="mt-4 rounded-xl p-4" style={{ background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.3)' }}>
                <p className="text-sm font-semibold flex items-center gap-2 text-green-600"><CheckCircle2 className="w-4 h-4" />{result.message}</p>
                {result.skipped?.length > 0 && <ul className="text-xs mt-2 text-red-500">{result.skipped.map((s: Row) => <li key={s.loop}>{s.loop}: {s.errors[0]}</li>)}</ul>}
                <div className="flex flex-wrap gap-2 mt-3">
                  <Button onClick={() => save('download', 'LOOP_WIRING_GENERATED.xlsx')}><Download className="w-4 h-4" />Download LOOP_WIRING_GENERATED.xlsx</Button>
                  <Button variant="secondary" onClick={() => save('report', 'LOOP_WIRING_GENERATION_REPORT.xlsx')}><Download className="w-4 h-4" />Generation &amp; traceability report</Button>
                </div>
              </div>)}
          </Card>
        </>)}

      <Card title="Template library & acceptance test" description="The 42 approved typicals are read from LOOP_TYPICAL_TEMPLATES_FINAL_CORRECTED.xlsx; the acceptance test runs the controlled fixture (tests A-J).">
        {library && (
          <p className="text-sm flex items-center gap-2 mb-3" style={{ color: library.complete ? '#16a34a' : '#dc2626' }}>
            <Library className="w-4 h-4" />{library.complete ? `Template library complete - ${library.count} / ${library.expected}` : library.error}
          </p>)}
        <Button variant="secondary" onClick={runSelftest} loading={testing}><FlaskConical className="w-4 h-4" />Run acceptance test (42 combinations + A-J)</Button>
        {selftest && (
          <div className="mt-4 space-y-3">
            <p className="text-sm font-semibold" style={{ color: selftest.passed ? '#16a34a' : '#dc2626' }}>{selftest.passed ? 'ALL ACCEPTANCE TESTS PASS' : 'ACCEPTANCE TEST FAILURES'} · {selftest.matrix.filter((m: Row) => m.result === 'PASS').length} / 42 template selections · {selftest.loops} loops · {selftest.signals} signals</p>
            <Table head={['Test', 'Name', 'Result', 'Detail']} max="max-h-64">
              {selftest.tests.map((t: Row) => <tr key={t.test} className="border-t" style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }}><td className={`${td} font-semibold`}>{t.test}</td><td className={td}>{t.name}</td><td className={td}><Status s={t.result} /></td><td className={td}>{t.detail}</td></tr>)}
            </Table>
            <Table head={['Test', 'Loop type', 'SPD', 'Term', 'Expected', 'Actual', 'Template', 'Result']} max="max-h-80">
              {selftest.matrix.map((m: Row) => <tr key={m.test} className="border-t" style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }}><td className={td}>{m.test}</td><td className={td}>{m.loop_type}</td><td className={td}>{m.spd}</td><td className={td}>{m.term}</td>
                <td className={`${td} font-semibold`}>{m.expected}</td><td className={td}>{m.actual}</td><td className={`${td} font-mono`}>{m.template}</td><td className={td}><Status s={m.result} /></td></tr>)}
            </Table>
          </div>)}
      </Card>
    </div>
  );
}

function Detail({ d, step }: { d: Row; step: number }) {
  const l = d.loop;
  const s2 = d.step2;
  return (
    <div className="space-y-3 text-sm" style={{ color: 'var(--t0)' }}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-semibold font-mono">{l.loop}</span><Status s={l.status} />
        <span className="text-xs" style={{ color: 'var(--t1)' }}>{l.loop_type} · SPD {l.spd} · {l.term} → {l.typical || 'no typical'} {l.template && <>· <span className="font-mono">{l.template}</span></>}</span>
      </div>
      {d.issues.length > 0 && (
        <div className="space-y-1">{d.issues.map((i: Row, k: number) => (
          <p key={k} className="text-xs flex gap-2" style={{ color: STATUS_STYLE[i.severity].fg }}>{i.severity === 'ERROR' ? <XCircle className="w-3.5 h-3.5 flex-shrink-0" /> : <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />}<span>{i.text}</span></p>))}</div>)}

      {step === 0 && (
        <Table head={['Row', 'Tag', 'Signal', 'IO', 'IS/NIS', 'Loop type', 'SPD', 'Term', 'JB', 'Marshalling', 'System cab.', 'Module', 'Ch.']}>
          {d.step1.map((r: Row) => <tr key={r.row} className="border-t" style={{ borderColor: 'var(--b1)' }}>
            <td className={td}>{r.row}</td><td className={`${td} font-mono`}>{r.key.TAG}</td><td className={td}>{r.key.SIG_DESC}</td><td className={td}>{r.key.IO_TYPE}</td><td className={td}>{r.key.ISNIS}</td><td className={td}>{r.key.LOOP_TYPE}</td>
            <td className={td}>{r.key.SPD_ARR}</td><td className={td}>{r.key.TERM_ARR}</td><td className={td}>{r.key.JB_TAG}</td><td className={td}>{r.key.MARSH_CAB}</td><td className={td}>{r.key.SYS_CAB}</td><td className={td}>{r.key.MODULE_TAG}</td><td className={td}>{r.key.CHANNEL}</td></tr>)}
        </Table>)}

      {step === 1 && (
        <div className="space-y-2">
          <p><b>LOOP TYPE</b> {s2.loop_type} (no. {s2.loop_type_no}) + <b>SPD_ARR</b> {s2.spd} ({s2.spd_name}) + "-" + <b>TERM_ARR</b> {s2.term} ({s2.term_name})</p>
          <p className="text-lg font-bold">{s2.formula} <span className="text-xs font-normal" style={{ color: 'var(--t1)' }}>calculated typical{s2.manual ? ` · entered TYPICAL: ${s2.manual}${s2.manual === s2.calculated ? ' (matches)' : ' (MISMATCH - calculated is authoritative)'}` : ''}</span></p>
          <p>Template: <span className="font-mono font-semibold">{s2.template || 'NOT FOUND'}</span></p>
          <Table head={['Signal block', 'Row', 'IO type', 'Typical signal', 'Filled by']} max="max-h-60">
            {s2.slots.map((sl: Row) => { const f = d.step4.rows.find((x: Row) => x.sig === sl.sig); return (
              <tr key={sl.sig} className="border-t" style={{ borderColor: 'var(--b1)' }}><td className={`${td} font-semibold`}>{sl.sig}</td><td className={td}>{sl.row}</td><td className={td}>{sl.io_type}</td><td className={td}>{sl.description}</td>
                <td className={td}>{f ? <span className="font-mono">{f.values.TAG}</span> : <span className="text-amber-600">not present</span>}</td></tr>); })}
          </Table>
        </div>)}

      {step === 2 && d.step3.map((x: Row) => (
        <div key={x.sig}>
          <p className="font-semibold text-xs mb-1">{x.sig} · {x.tag} · source row {x.source_row}</p>
          <Table head={['Field code (destination)', 'Source field code', 'Source value', 'Destination cell', 'State', 'Note']} max="max-h-72">
            {x.mapping.map((m: Row) => <tr key={m.field} className="border-t" style={{ borderColor: 'var(--b1)' }}>
              <td className={`${td} font-mono`}>{m.field}</td><td className={`${td} font-mono`}>{m.source}</td><td className={td}>{m.value ?? ''}</td><td className={`${td} font-mono`}>{m.destination.split('· ')[1]}</td>
              <td className={td} style={{ color: m.state === 'MAPPED' || m.state === 'DERIVED' ? '#16a34a' : m.state === 'BLANK' && m.note === 'required' ? '#dc2626' : 'var(--t1)' }}>{m.state}</td><td className={td} style={{ color: 'var(--t1)' }}>{m.note}</td></tr>)}
          </Table>
        </div>))}
      {step === 2 && (
        <div className="grid md:grid-cols-3 gap-3 text-xs">
          <div><p className="font-semibold mb-1">Mapped fields: {d.report.mapped}</p><p className="font-semibold">Missing required: {d.report.missing_required?.length || 0}</p>{d.report.missing_required?.map((m: Row, i: number) => <p key={i} className="text-red-500">{m.sig} {m.field}</p>)}</div>
          <div><p className="font-semibold mb-1">Unused source fields (not an error)</p><p style={{ color: 'var(--t1)' }}>{Array.from(new Set((d.report.unused_source || []).map((u: Row) => u.code))).join(', ') || '—'}</p></div>
          <div><p className="font-semibold mb-1">Template fields without source</p><p style={{ color: 'var(--t1)' }}>{(d.report.template_without_source || []).join(', ') || '—'}</p></div>
        </div>)}

      {step === 3 && (
        <div className="space-y-2">
          <p className="text-xs">Loop fields: {Object.entries(d.step4.loop_fields).map(([k, v]) => <span key={k} className="mr-3"><b>{k}</b> {String(v ?? '')}</span>)}</p>
          <Table head={['Row', ...d.step4.columns]} max="max-h-96">
            {d.step4.rows.map((r: Row) => <tr key={r.sig} className="border-t" style={{ borderColor: 'var(--b1)' }}><td className={`${td} font-semibold`}>{r.sig}</td>
              {d.step4.columns.map((c: string) => <td key={c} className={`${td} whitespace-nowrap`}>{c === 'SIG' ? r.sig : String(r.values[c] ?? '')}</td>)}</tr>)}
          </Table>
        </div>)}

      {step === 4 && d.step5.map((x: Row) => <div key={x.sig}><p className="font-semibold text-xs mb-1">{x.sig} · {x.tag} ({x.io_type}) - field side</p><Chain nodes={x.nodes} /></div>)}
      {step === 5 && d.step6.map((x: Row) => <div key={x.sig}><p className="font-semibold text-xs mb-1">{x.sig} · {x.tag} ({x.io_type}) - control room / system side</p><Chain nodes={x.nodes} /></div>)}

      {step === 6 && d.step7.map((x: Row) => (
        <div key={x.sig} className="rounded-lg p-3" style={{ border: '1px solid var(--b1)' }}>
          <p className="font-semibold text-xs flex items-center gap-2">{x.sig} · {x.tag} <Status s={x.status} /> <span style={{ color: x.complete ? '#16a34a' : '#dc2626' }}>{x.complete ? 'trace complete' : `trace broken: ${x.broken.join(', ')}`}</span></p>
          <p className="text-xs mt-1" style={{ color: 'var(--t1)' }}>{x.topology}</p>
          <div className="mt-2 grid md:grid-cols-2 gap-x-6 gap-y-1">
            {x.conductors.map((c: Row, i: number) => <p key={i} className="text-xs"><b>{c.role}</b>: <span className="font-mono">{c.path.join(' → ') || '—'}</span></p>)}
          </div>
        </div>))}
    </div>
  );
}
