/**
 * TemplateCoverSheet - "Use Uploaded Excel Coversheet Template" workflow of the Coversheet Generator.
 *
 *   MDL          -> WHAT document(s) to generate   (number + description, resolved server-side)
 *   Template     -> HOW the coversheet looks       (layout, logos, merges, formulas, print setup)
 *   User input   -> revision, date, prepared / checked / approved by
 *
 * The template File stays in the browser and is sent with each request; the confirmed field mapping is kept in
 * sessionStorage only (it disappears with the browser session). Nothing is written to a template cell that has
 * not been confirmed here.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle2, Download, Eye, FileUp, Loader2, Search, X, AlertTriangle } from 'lucide-react';
import api from '@/services/api';
import { getCurrentProject, subscribeProject } from '@/services/projectContext';
import Alert from '../../ui/Alert';
import Button from '../../ui/Button';
import type { MdlRecord } from './MdlSelector';

type Confidence = 'high' | 'medium' | 'none';
interface Target { cell: string; mode: string; current?: string; confirmed: boolean; label?: string; where?: string; note?: string; optional?: boolean }
interface Part { cell: string; label?: string; current?: string; confirmed: boolean }
interface FieldMap {
  label: string; required: boolean; confidence: Confidence; reason: string; needs_review: boolean;
  targets: Target[]; parts?: Record<string, Part>; skipped?: boolean;
}
interface Analysis {
  sheet: string; sheets: string[]; dimensions: string; merged_ranges: number; images: number; print_area: string;
  orientation: string; protected: boolean; formulas: number; fields: Record<string, FieldMap>;
  table: { header_row: number; direction: string } | null;
}
interface ModelCell {
  r: number; c: number; rs: number; cs: number; t: string; bg: string | null; h: string; v: string; w: boolean; rot: number;
  b: Record<string, [string, string]>; f: { n: string; s: number; b: boolean; i: boolean; u: boolean; c: string };
}
interface Model {
  width: number; height: number; xs: number[]; ys: number[]; cells: ModelCell[];
  images: { x: number; y: number; w: number; h: number; mime: string; b64: string }[]; orientation: string;
}

const FIELD_ORDER = ['document_number', 'document_description', 'revision', 'date', 'prepared_by', 'checked_by', 'approved_by'];
const PART_ORDER = ['job_no', 'project_no', 'doc_code', 'serial_no'];
const PART_LABEL: Record<string, string> = { job_no: 'Job No.', project_no: 'Project', doc_code: 'Doc. Code', serial_no: 'Serial No.' };
const MAP_KEY = 'iez_cs_template_mapping';
const errText = (e: any, fallback: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return fallback;
};
const blobError = async (e: any, fallback: string) => {
  try {
    const d = e?.response?.data;
    if (d instanceof Blob) return JSON.parse(await d.text())?.detail || fallback;
  } catch { /* fall through */ }
  return errText(e, fallback);
};
const sigOf = (f: File) => `${f.name}|${f.size}|${f.lastModified}`;
const todayIso = () => new Date().toISOString().slice(0, 10);

function ConfBadge({ c }: { c: Confidence }) {
  const m = { high: ['High', '#4ade80', 'rgba(74,222,128,0.12)'], medium: ['Medium - review', 'var(--gold)', 'var(--gold-dim)'],
    none: ['Not found', 'var(--rose)', 'rgba(248,113,113,0.1)'] }[c];
  return <span className="text-[10px] font-bold px-2 py-0.5 rounded-full whitespace-nowrap" style={{ color: m[1], background: m[2] }}>{m[0]}</span>;
}

/** Draws the layout model the server built from the generated workbook (the same model the fallback PDF uses). */
function ModelPreview({ model }: { model: Model }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const fit = () => { if (wrap.current) setScale(Math.min(1, (wrap.current.clientWidth - 2) / model.width)); };
    fit(); window.addEventListener('resize', fit); return () => window.removeEventListener('resize', fit);
  }, [model.width]);
  const edge = (s: [string, string] | undefined) => s ? `${/medium|thick|double/.test(s[0]) ? 2 : 1}px ${s[0] === 'dashed' || s[0] === 'mediumDashed' ? 'dashed' : s[0] === 'dotted' ? 'dotted' : 'solid'} ${s[1]}` : undefined;
  return (
    <div ref={wrap} className="w-full overflow-hidden rounded-lg" style={{ background: '#e5e7eb', padding: 1 }}>
      <div style={{ width: model.width * scale, height: model.height * scale, position: 'relative', background: '#fff', margin: '0 auto' }}>
        <div style={{ width: model.width, height: model.height, transform: `scale(${scale})`, transformOrigin: 'top left', position: 'absolute' }}>
          {model.cells.map((c, i) => {
            const x = model.xs[c.c], y = model.ys[c.r];
            const w = model.xs[Math.min(c.c + c.cs, model.xs.length - 1)] - x, h = model.ys[Math.min(c.r + c.rs, model.ys.length - 1)] - y;
            return (
              <div key={i} style={{
                position: 'absolute', left: x, top: y, width: w, height: h, boxSizing: 'border-box', overflow: 'hidden',
                background: c.bg || undefined, borderLeft: edge(c.b.l), borderRight: edge(c.b.r), borderTop: edge(c.b.t), borderBottom: edge(c.b.b),
                display: 'flex', padding: '0 3px',
                alignItems: c.v === 'center' || c.v === 'centre' ? 'center' : c.v === 'top' ? 'flex-start' : 'flex-end',
                justifyContent: c.h === 'center' || c.h === 'centerContinuous' ? 'center' : c.h === 'right' ? 'flex-end' : 'flex-start',
                textAlign: c.h === 'center' ? 'center' : c.h === 'right' ? 'right' : 'left',
                fontFamily: `${c.f.n}, Arial, sans-serif`, fontSize: c.f.s * 1.333, fontWeight: c.f.b ? 700 : 400, fontStyle: c.f.i ? 'italic' : 'normal',
                textDecoration: c.f.u ? 'underline' : undefined, color: c.f.c, whiteSpace: c.w || c.t.includes('\n') ? 'pre-wrap' : 'pre', lineHeight: 1.15,
              }}>{c.t}</div>
            );
          })}
          {model.images.map((im, i) => (
            <img key={i} src={`data:${im.mime};base64,${im.b64}`} alt="" style={{ position: 'absolute', left: im.x, top: im.y, width: im.w, height: im.h }} />
          ))}
        </div>
      </div>
    </div>
  );
}

interface Props {
  /** Admin / approved authorisation of the existing workflow is reused: generation needs it too. */
  authorized: boolean;
  requestAuth: () => void;
  mdlActive: boolean;
}

export default function TemplateCoverSheet({ authorized, requestAuth, mdlActive }: Props) {
  const [projectId, setProjectId] = useState(getCurrentProject());
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MdlRecord[]>([]);
  const [searching, setSearching] = useState(false);
  const [picked, setPicked] = useState<Record<string, MdlRecord>>({});

  const [vals, setVals] = useState({ revision: '', date: todayIso(), prepared_by: '', checked_by: '', approved_by: '' });
  const [formats, setFormats] = useState({ xlsx: true, pdf: true });
  const [clearHistory, setClearHistory] = useState(true);

  const [preview, setPreview] = useState<{ model: Model; warnings: string[]; doc: string } | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewDoc, setPreviewDoc] = useState('');
  const [generating, setGenerating] = useState(false);
  const [pendingGenerate, setPendingGenerate] = useState(false);
  const [done, setDone] = useState<{ filename: string; kind: string; files: string[]; warnings: string[]; engine: string | null; message: string } | null>(null);

  useEffect(() => subscribeProject(setProjectId), []);
  const pickedList = useMemo(() => Object.values(picked), [picked]);

  // ── template upload + analysis ──
  const analyze = useCallback(async (f: File, sheet?: string) => {
    setAnalyzing(true); setError(null); setPreview(null); setDone(null);
    try {
      const fd = new FormData(); fd.append('file', f); if (sheet) fd.append('sheet', sheet);
      const r = await api.post<Analysis>('/coversheet/template/analyze', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      let a = r.data;
      try {                                                      // confirmed mapping of this browser session
        const saved = JSON.parse(sessionStorage.getItem(MAP_KEY) || 'null');
        if (saved && saved.sig === sigOf(f) && saved.sheet === a.sheet) a = { ...a, fields: saved.fields };
      } catch { /* optional */ }
      setAnalysis(a);
    } catch (e: any) { setAnalysis(null); setError(errText(e, 'The template could not be analysed.')); }
    finally { setAnalyzing(false); }
  }, []);

  const onFile = (f: File | null) => { setFile(f); setAnalysis(null); if (f) analyze(f); };

  const updateFields = (next: Record<string, FieldMap>) => {
    if (!analysis || !file) return;
    setAnalysis({ ...analysis, fields: next }); setPreview(null); setDone(null);
    try { sessionStorage.setItem(MAP_KEY, JSON.stringify({ sig: sigOf(file), sheet: analysis.sheet, fields: next })); } catch { /* optional */ }
  };
  const patchField = (k: string, patch: Partial<FieldMap>) => analysis && updateFields({ ...analysis.fields, [k]: { ...analysis.fields[k], ...patch } });
  const patchTarget = (k: string, i: number, patch: Partial<Target>) => {
    if (!analysis) return;
    const f = analysis.fields[k];
    patchField(k, { targets: f.targets.map((t, j) => j === i ? { ...t, ...patch } : t) });
  };
  const addTarget = (k: string) => analysis && patchField(k, { targets: [...analysis.fields[k].targets, { cell: '', mode: 'replace', confirmed: false }] });
  const removeTarget = (k: string, i: number) => analysis && patchField(k, { targets: analysis.fields[k].targets.filter((_, j) => j !== i) });
  const patchPart = (k: string, p: string, patch: Partial<Part>) => {
    if (!analysis) return;
    const f = analysis.fields[k];
    patchField(k, { parts: { ...(f.parts || {}), [p]: { ...(f.parts?.[p] || { cell: '', confirmed: false }), ...patch } } });
  };

  const confirmAllHigh = () => {
    if (!analysis) return;
    const next: Record<string, FieldMap> = {};
    for (const [k, f] of Object.entries(analysis.fields)) {
      next[k] = f.confidence === 'none' ? f : { ...f, targets: f.targets.map(t => ({ ...t, confirmed: !!t.cell })), parts: f.parts && Object.fromEntries(Object.entries(f.parts).map(([p, v]) => [p, { ...v, confirmed: !!v.cell }])) };
    }
    updateFields(next);
  };

  // ── MDL search / multi-select ──
  useEffect(() => {
    if (!mdlActive || !projectId) { setResults([]); return; }
    let cancelled = false;
    const h = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await api.get(`/projects/${encodeURIComponent(projectId)}/coversheet/mdl/search`, { params: { q: query, limit: 50 } });
        if (!cancelled) setResults(r.data.items || []);
      } catch { if (!cancelled) setResults([]); }
      finally { if (!cancelled) setSearching(false); }
    }, 250);
    return () => { cancelled = true; clearTimeout(h); };
  }, [query, projectId, mdlActive]);
  useEffect(() => { setPicked({}); setPreview(null); }, [projectId]);

  const toggle = (r: MdlRecord) => { setPicked(p => { const n = { ...p }; if (n[r.mdl_record_id]) delete n[r.mdl_record_id]; else n[r.mdl_record_id] = r; return n; }); setPreview(null); setDone(null); };

  // ── readiness ──
  const problems = useMemo(() => {
    const out: string[] = [];
    if (!file || !analysis) return ['Upload a coversheet template.'];
    const f = analysis.fields;
    for (const k of FIELD_ORDER) {
      const fm = f[k];
      const has = fm.targets.some(t => t.confirmed && t.cell.trim()) || Object.values(fm.parts || {}).some(p => p.confirmed && p.cell.trim());
      if (fm.required && !has) out.push(`${fm.label}: confirm or assign the template cell.`);
      else if (!fm.required && !has && !fm.skipped && fm.confidence !== 'none') out.push(`${fm.label}: confirm the detected cell or skip the field.`);
    }
    if (!pickedList.length) out.push('Select at least one document from the MDL.');
    for (const [k, label] of [['revision', 'Revision'], ['date', 'Date'], ['prepared_by', 'Prepared By'], ['checked_by', 'Checked By'], ['approved_by', 'Approved By']] as const) {
      const fm = f[k];
      const has = fm.targets.some(t => t.confirmed && t.cell.trim());
      if (has && !fm.skipped && !(vals as any)[k].trim()) out.push(`${label} is required (or skip the field).`);
    }
    if (!formats.xlsx && !formats.pdf) out.push('Choose Excel and/or PDF output.');
    return out;
  }, [file, analysis, pickedList.length, vals, formats]);

  const body = (docs: MdlRecord[]) => JSON.stringify({
    project_id: projectId, record_ids: docs.map(d => d.mdl_record_id), sheet: analysis?.sheet,
    mapping: analysis?.fields, values: vals, clear_history: clearHistory,
    formats: [formats.xlsx && 'xlsx', formats.pdf && 'pdf'].filter(Boolean),
  });

  const runPreview = async () => {
    if (!file || !analysis || !pickedList.length) return;
    const doc = pickedList.find(d => d.mdl_record_id === previewDoc) || pickedList[0];
    setPreviewing(true); setError(null);
    try {
      const fd = new FormData(); fd.append('file', file); fd.append('data', body([doc]));
      const r = await api.post('/coversheet/template/preview', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setPreview({ model: r.data.model, warnings: r.data.warnings || [], doc: doc.document_number });
    } catch (e: any) { setPreview(null); setError(errText(e, 'Preview failed.')); }
    finally { setPreviewing(false); }
  };

  const runGenerate = useCallback(async () => {
    if (!file || !analysis) return;
    setGenerating(true); setError(null); setDone(null);
    try {
      const fd = new FormData(); fd.append('file', file); fd.append('data', body(pickedList));
      const r = await api.post('/coversheet/template/generate', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setDone(r.data);
    } catch (e: any) { setError(errText(e, 'Generation failed.')); }
    finally { setGenerating(false); }
  }, [file, analysis, pickedList, vals, formats, clearHistory, projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const onGenerate = () => { if (problems.length) return; if (!authorized) { setPendingGenerate(true); requestAuth(); } else runGenerate(); };
  useEffect(() => { if (pendingGenerate && authorized) { setPendingGenerate(false); runGenerate(); } }, [pendingGenerate, authorized, runGenerate]);

  const download = async (kind?: string) => {
    try {
      const r = await api.get('/coversheet/template/download', { params: kind ? { kind } : {}, responseType: 'blob' });
      const cd: string = r.headers['content-disposition'] || '';
      const name = /filename="?([^";]+)"?/.exec(cd)?.[1] || done?.filename || 'Coversheet';
      const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
    } catch (e: any) { setError(await blobError(e, 'Download failed.')); }
  };

  const card = { background: 'var(--s2)', border: '1px solid var(--b1)' } as const;
  const input = 'rounded-lg px-2.5 py-1.5 text-xs outline-none';
  const inputStyle = { background: 'var(--s3)', color: 'var(--t0)', border: '1px solid var(--b1)' } as const;

  return (
    <div className="space-y-5">
      {error && <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>}

      {/* 1. template */}
      <div className="rounded-2xl p-5 space-y-3" style={card}>
        <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>1 · Coversheet template (Excel)</p>
        <label className="flex items-center gap-3 rounded-xl px-4 py-3 cursor-pointer" style={{ border: '1px dashed var(--b1)', color: 'var(--t1)' }}>
          <FileUp className="w-4 h-4" />
          <span className="text-sm">{file ? file.name : 'Upload your Excel coversheet template (.xlsx)'}</span>
          <input type="file" accept=".xlsx" className="hidden" onChange={e => { onFile(e.target.files?.[0] || null); e.target.value = ''; }} />
          {analyzing && <Loader2 className="w-4 h-4 animate-spin ml-auto" />}
        </label>
        {analysis && (
          <div className="text-xs grid gap-1 sm:grid-cols-2" style={{ color: 'var(--t2)' }}>
            <p>Sheet: {analysis.sheets.length > 1 ? (
              <select className={input} style={inputStyle} value={analysis.sheet} onChange={e => file && analyze(file, e.target.value)}>
                {analysis.sheets.map(s => <option key={s}>{s}</option>)}</select>) : <b style={{ color: 'var(--t0)' }}>{analysis.sheet}</b>}</p>
            <p>Range {analysis.dimensions} · {analysis.merged_ranges} merged ranges · {analysis.images} image(s) · {analysis.orientation}
              {analysis.print_area ? ` · print area ${analysis.print_area}` : ''}{analysis.protected ? ' · protected sheet' : ''}{analysis.formulas ? ` · ${analysis.formulas} formula(s)` : ''}</p>
          </div>
        )}
        <p className="text-xs" style={{ color: 'var(--t2)' }}>Your master template is only read - every output is a new file. The field mapping you confirm below is kept for this browser session only.</p>
      </div>

      {/* 2. mapping review */}
      {analysis && (
        <div className="rounded-2xl p-5 space-y-3" style={card}>
          <div className="flex items-center gap-3">
            <p className="text-sm font-bold flex-1" style={{ color: 'var(--t0)' }}>2 · Field mapping review</p>
            <Button size="sm" variant="secondary" onClick={confirmAllHigh}><CheckCircle2 className="w-3.5 h-3.5" /> Confirm detected cells</Button>
          </div>
          <p className="text-xs" style={{ color: 'var(--t2)' }}>Only confirmed cells are written. Correct any cell address that is wrong (e.g. <span className="font-mono">C5</span>); fields shown as Medium or Not found need your decision.</p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr style={{ color: 'var(--t2)' }} className="text-left"><th className="py-1.5 pr-3">Field</th><th className="pr-3">Confidence</th><th className="pr-3">Template cell(s)</th><th>Source</th></tr></thead>
              <tbody>
                {FIELD_ORDER.map(k => {
                  const f = analysis.fields[k];
                  return (
                    <tr key={k} className="align-top" style={{ borderTop: '1px solid var(--b1)' }}>
                      <td className="py-2 pr-3 font-semibold" style={{ color: 'var(--t0)' }}>{f.label}{f.required && <span style={{ color: 'var(--rose)' }}> *</span>}</td>
                      <td className="pr-3 py-2"><ConfBadge c={f.confidence} /><p className="mt-1 max-w-[210px]" style={{ color: 'var(--t2)' }}>{f.reason}</p></td>
                      <td className="py-2 pr-3 space-y-1.5">
                        {f.skipped ? <span style={{ color: 'var(--t2)' }}>Skipped</span> : (<>
                          {f.targets.map((t, i) => (
                            <div key={i} className="flex items-center gap-2">
                              <input type="checkbox" checked={t.confirmed} disabled={!t.cell.trim()} onChange={e => patchTarget(k, i, { confirmed: e.target.checked })} title="Confirmed - write to this cell" />
                              <input className={`${input} w-20 font-mono uppercase`} style={inputStyle} value={t.cell} placeholder="Cell"
                                onChange={e => patchTarget(k, i, { cell: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''), confirmed: false })} />
                              <span className="truncate max-w-[200px]" style={{ color: 'var(--t2)' }} title={t.current}>{t.where || t.note || ''}{t.current ? ` · "${t.current.replace(/\s+/g, ' ').slice(0, 30)}"` : ''}</span>
                              <button onClick={() => removeTarget(k, i)} title="Remove" style={{ color: 'var(--t2)' }}><X className="w-3 h-3" /></button>
                            </div>
                          ))}
                          {f.parts && PART_ORDER.filter(p => f.parts![p]).map(p => (
                            <div key={p} className="flex items-center gap-2">
                              <input type="checkbox" checked={f.parts![p].confirmed} disabled={!f.parts![p].cell.trim()} onChange={e => patchPart(k, p, { confirmed: e.target.checked })} />
                              <input className={`${input} w-20 font-mono uppercase`} style={inputStyle} value={f.parts![p].cell}
                                onChange={e => patchPart(k, p, { cell: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''), confirmed: false })} />
                              <span style={{ color: 'var(--t2)' }}>{PART_LABEL[p]} box</span>
                            </div>
                          ))}
                          <button className="underline" style={{ color: 'var(--t2)' }} onClick={() => addTarget(k)}>+ add cell</button>
                        </>)}
                        {!f.required && <label className="flex items-center gap-1.5" style={{ color: 'var(--t2)' }}>
                          <input type="checkbox" checked={!!f.skipped} onChange={e => patchField(k, { skipped: e.target.checked })} /> Skip this field</label>}
                      </td>
                      <td className="py-2" style={{ color: 'var(--t2)' }}>{k === 'document_number' || k === 'document_description' ? 'MDL' : k === 'date' ? 'Date below' : 'Input below'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {analysis.table && (
            <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--t1)' }}>
              <input type="checkbox" checked={clearHistory} onChange={e => { setClearHistory(e.target.checked); setPreview(null); }} />
              Clear the template's existing revision-history rows (they belong to the template's own document)
            </label>
          )}
        </div>
      )}

      {/* 3. documents */}
      <div className="rounded-2xl p-5 space-y-3" style={card}>
        <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>3 · Documents from the MDL</p>
        {!mdlActive ? <Alert variant="warning">Upload this project's Master Document List in the section above to select documents.</Alert> : (<>
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--t2)' }} />
            <input className={`${input} w-full pl-8`} style={inputStyle} placeholder="Search by document number, description or discipline" value={query} onChange={e => setQuery(e.target.value)} />
            {searching && <Loader2 className="w-3.5 h-3.5 animate-spin absolute right-3 top-1/2 -translate-y-1/2" />}
          </div>
          <div className="flex gap-2 text-xs">
            <button className="underline" style={{ color: 'var(--t2)' }} onClick={() => setPicked(p => ({ ...p, ...Object.fromEntries(results.map(r => [r.mdl_record_id, r])) }))}>Select all shown</button>
            <button className="underline" style={{ color: 'var(--t2)' }} onClick={() => setPicked({})}>Clear selection</button>
            <span className="ml-auto" style={{ color: 'var(--t2)' }}>{pickedList.length} selected</span>
          </div>
          <div className="max-h-56 overflow-y-auto rounded-lg" style={{ border: '1px solid var(--b1)' }}>
            {results.length === 0 && <p className="p-3 text-xs" style={{ color: 'var(--t2)' }}>No documents match.</p>}
            {results.map(r => (
              <label key={r.mdl_record_id} className="flex items-start gap-2 px-3 py-1.5 text-xs cursor-pointer" style={{ borderBottom: '1px solid var(--b1)', color: 'var(--t1)' }}>
                <input type="checkbox" className="mt-0.5" checked={!!picked[r.mdl_record_id]} onChange={() => toggle(r)} />
                <span className="font-mono whitespace-nowrap" style={{ color: 'var(--t0)' }}>{r.document_number}</span>
                <span className="flex-1">{r.document_name}{r.duplicate_document_number && <span style={{ color: 'var(--gold)' }}> · duplicate number</span>}</span>
                <span style={{ color: 'var(--t2)' }}>{r.discipline}</span>
              </label>
            ))}
          </div>
        </>)}
      </div>

      {/* 4. user input */}
      <div className="rounded-2xl p-5 space-y-3" style={card}>
        <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>4 · Revision, date and sign-off</p>
        <div className="grid gap-3 sm:grid-cols-3">
          {([['revision', 'Revision'], ['date', 'Date'], ['prepared_by', 'Prepared By'], ['checked_by', 'Checked By'], ['approved_by', 'Approved By']] as const).map(([k, label]) => (
            <label key={k} className="text-xs space-y-1" style={{ color: 'var(--t2)' }}>{label}
              <input className={`${input} w-full`} style={inputStyle} type={k === 'date' ? 'date' : 'text'} value={(vals as any)[k]}
                onChange={e => { setVals(v => ({ ...v, [k]: e.target.value })); setPreview(null); setDone(null); }} /></label>
          ))}
        </div>
        <p className="text-xs" style={{ color: 'var(--t2)' }}>The date is written in the template's own date format.</p>
      </div>

      {/* 5. output + preview + generate */}
      <div className="rounded-2xl p-5 space-y-4" style={card}>
        <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>5 · Output</p>
        <div className="flex flex-wrap gap-4 text-xs" style={{ color: 'var(--t1)' }}>
          <label className="flex items-center gap-1.5"><input type="checkbox" checked={formats.xlsx} onChange={e => setFormats(f => ({ ...f, xlsx: e.target.checked }))} /> Excel (.xlsx)</label>
          <label className="flex items-center gap-1.5"><input type="checkbox" checked={formats.pdf} onChange={e => setFormats(f => ({ ...f, pdf: e.target.checked }))} /> PDF (A4)</label>
          {pickedList.length > 1 && <span style={{ color: 'var(--t2)' }}>Several documents are delivered as one ZIP.</span>}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {pickedList.length > 1 && (
            <select className={input} style={inputStyle} value={previewDoc} onChange={e => { setPreviewDoc(e.target.value); setPreview(null); }}>
              <option value="">Preview: {pickedList[0].document_number}</option>
              {pickedList.map(d => <option key={d.mdl_record_id} value={d.mdl_record_id}>{d.document_number}</option>)}
            </select>)}
          <Button variant="secondary" onClick={runPreview} loading={previewing} disabled={!!problems.length}><Eye className="w-4 h-4" /> Preview</Button>
          <Button onClick={onGenerate} loading={generating} disabled={!!problems.length}>
            {authorized ? 'Generate' : 'Verify & Generate'}
          </Button>
          {done && done.kind !== 'zip' && done.files.length > 1 && <>
            <Button variant="secondary" onClick={() => download('xlsx')}><Download className="w-4 h-4" /> Excel</Button>
            <Button variant="secondary" onClick={() => download('pdf')}><Download className="w-4 h-4" /> PDF</Button></>}
          {done && !(done.kind !== 'zip' && done.files.length > 1) && <Button variant="secondary" onClick={() => download()}><Download className="w-4 h-4" /> Download {done.filename}</Button>}
        </div>
        {!!problems.length && <ul className="text-xs list-disc pl-5" style={{ color: 'var(--t2)' }}>{problems.slice(0, 6).map(p => <li key={p}>{p}</li>)}</ul>}
        {!authorized && <p className="text-xs" style={{ color: 'var(--t2)' }}>Generating needs the same admin verification as the standard workflow.</p>}
        {done && <Alert variant="success">{done.message} {done.filename}{done.engine ? ` · PDF via ${done.engine === 'libreoffice' ? 'LibreOffice' : 'built-in renderer'}` : ''}</Alert>}
        {done?.warnings?.map(w => <p key={w} className="text-xs flex gap-1.5" style={{ color: 'var(--gold)' }}><AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />{w}</p>)}
        {preview && (
          <div className="space-y-2">
            <p className="text-xs" style={{ color: 'var(--t2)' }}>Preview of {preview.doc} - the generated sheet, not an approximation.</p>
            {preview.warnings.map(w => <p key={w} className="text-xs" style={{ color: 'var(--gold)' }}>{w}</p>)}
            <ModelPreview model={preview.model} />
          </div>
        )}
      </div>
    </div>
  );
}
