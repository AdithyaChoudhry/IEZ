/**
 * CoversheetBuilder - "MDL-Driven Coversheet (Excel / PDF template)" workflow of the Coversheet Generator.
 *
 *   1 Upload MDL (Excel / PDF)  ->  2 Review & select the document  ->  3 Template (Excel / PDF) + field locations
 *   4 Revision  ->  5 Approval  ->  6 Signatures  ->  7 Preview  ->  8 Generate & download
 *
 * Backend: /api/coversheet/builder (routers/coversheet_builder.py). The MDL extraction (with the user's corrections)
 * is kept on the server; document number, name and description are always taken from the selected MDL record there.
 * The two existing Coversheet workflows are not touched by this component.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Download, Eye, FileSpreadsheet, FileText, FileUp, Loader2, Pencil, Plus, Search, Square, Trash2, X } from 'lucide-react';
import api from '@/services/api';
import Alert from '../../ui/Alert';
import Badge from '../../ui/Badge';
import Button from '../../ui/Button';
import { ModelPreview } from './TemplateCoverSheet';

// ── types ──────────────────────────────────────────────────────────────────────
type Level = 'error' | 'warning' | 'info';
interface Flag { level: Level; field: string; message: string }
interface Rec {
  id: string; document_number: string; document_name: string; document_description: string; revision: string;
  document_type: string; discipline: string; source: string; method: string; edited: boolean; flags: Flag[];
  status: 'ok' | 'warning' | 'error'; original?: Record<string, string>;
}
interface Extraction {
  extraction_id: string; source_type: 'excel' | 'pdf'; file_name: string; sheet: string | null; header_row: number | null;
  pages: number | null; method: string; name_from_description: boolean; rows_ignored: number; notes: string[];
  columns: { field: string; header: string; column: number | null }[]; records: Rec[];
  summary: { records: number; errors: number; warnings: number; duplicates: number; missing_description: number };
}
type Conf = 'high' | 'medium' | 'none';
interface Target { cell?: string; page?: number; box?: number[]; confirmed: boolean; clear?: boolean; current?: string; where?: string; label?: string; mode?: string; align?: string; font_size?: number }
interface Part { cell: string; label?: string; current?: string; confirmed: boolean }
interface FieldMap { label: string; required: boolean; kind: 'text' | 'image'; source: string; confidence: Conf; reason: string; targets: Target[]; parts?: Record<string, Part>; skipped?: boolean }
interface PageImg { page: number; width_pt: number; height_pt: number; scale: number; png: string }
interface Analysis {
  kind: 'excel' | 'pdf'; fields: Record<string, FieldMap>;
  sheet?: string; sheets?: string[]; dimensions?: string; merged_ranges?: number; images?: number; orientation?: string; table?: unknown;
  pages?: { page: number; width: number; height: number; rotation: number }[]; notes?: string[]; page_images?: PageImg[];
}

const FIELD_ORDER = ['document_number', 'document_name', 'document_description', 'revision', 'revision_date',
  'prepared_by', 'checked_by', 'approved_by', 'sig_prepared', 'sig_checked', 'sig_approved'];
const SIG_KEYS = ['sig_prepared', 'sig_checked', 'sig_approved'] as const;
const SIG_LABEL: Record<string, string> = { sig_prepared: 'Prepared By', sig_checked: 'Checked By', sig_approved: 'Approved By' };
const PART_LABEL: Record<string, string> = { job_no: 'Job No.', project_no: 'Project', doc_code: 'Doc. Code', serial_no: 'Serial No.' };
const METHOD: Record<string, string> = { excel: 'Excel worksheet', 'pdf-table': 'PDF tables', 'pdf-text': 'PDF text lines', ocr: 'OCR (scanned PDF)' };
const COL_LABEL: Record<string, string> = { document_number: 'Document Number', document_name: 'Document Name', document_description: 'Description', revision: 'Revision', document_type: 'Document Type', discipline: 'Discipline' };
const STORE = 'iez_cs_builder';
const todayIso = () => new Date().toISOString().slice(0, 10);
const errText = (e: any, fb: string) => { const d = e?.response?.data?.detail; return typeof d === 'string' ? d : fb; };
const blobErr = async (e: any, fb: string) => { try { const d = e?.response?.data; if (d instanceof Blob) return JSON.parse(await d.text())?.detail || fb; } catch { /* */ } return errText(e, fb); };
const placed = (f?: FieldMap) => !!f && !f.skipped && (f.targets.some(t => t.confirmed && (t.cell?.trim() || t.box)) || Object.values(f.parts || {}).some(p => p.confirmed && p.cell.trim()));

// ── small pieces ───────────────────────────────────────────────────────────────
function Stage({ n, title, sub, state, children, right }: { n: number; title: string; sub?: string; state: 'done' | 'active' | 'locked'; children?: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="ui-card p-4 sm:p-5" style={{ opacity: state === 'locked' ? 0.55 : 1 }}>
      <div className="flex items-start gap-3">
        <span className="mono text-[11px] font-semibold w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0"
          style={state === 'done' ? { background: 'var(--ink)', color: 'var(--ink-fg)' } : { border: '1px solid var(--b2)', color: state === 'active' ? 'var(--em)' : 'var(--t2)' }}>
          {state === 'done' ? <CheckCircle2 className="w-3.5 h-3.5" /> : String(n).padStart(2, '0')}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[15px] font-semibold flex-1" style={{ color: 'var(--t0)', letterSpacing: '-0.01em' }}>{title}</p>
            {right}
          </div>
          {sub && <p className="text-xs mt-0.5" style={{ color: 'var(--t2)' }}>{sub}</p>}
        </div>
      </div>
      {state !== 'locked' && children && <div className="mt-4 sm:pl-10 space-y-3">{children}</div>}
    </section>
  );
}

function StatusBadge({ r }: { r: Rec }) {
  const tip = r.flags.map(f => f.message).join('\n');
  if (r.status === 'error') return <span title={tip}><Badge variant="error">Incomplete</Badge></span>;
  if (r.status === 'warning') return <span title={tip}><Badge variant="warning">Check</Badge></span>;
  return <span title={tip}><Badge variant="success">OK</Badge></span>;
}

function ConfBadge({ c }: { c: Conf }) {
  return c === 'high' ? <Badge variant="success">Detected</Badge> : c === 'medium' ? <Badge variant="warning">Review</Badge> : <Badge variant="neutral">Not found</Badge>;
}

/** Draw / redraw a field's box on a PDF page image. Coordinates are PDF points, origin top-left. */
function BoxPicker({ pages, fields, fieldKey, initial, onSave, onClose }: {
  pages: PageImg[]; fields: Record<string, FieldMap>; fieldKey: string; initial?: Target;
  onSave: (page: number, box: number[]) => void; onClose: () => void;
}) {
  const [page, setPage] = useState(initial?.page || 1);
  const [box, setBox] = useState<number[] | null>(initial?.box || null);
  const [drag, setDrag] = useState<{ x: number; y: number } | null>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const pg = pages.find(p => p.page === page) || pages[0];
  const toPt = (e: React.PointerEvent) => {
    const r = imgRef.current!.getBoundingClientRect();
    const k = pg.width_pt / r.width;
    return { x: Math.max(0, Math.min(pg.width_pt, (e.clientX - r.left) * k)), y: Math.max(0, Math.min(pg.height_pt, (e.clientY - r.top) * k)) };
  };
  const pct = (b: number[]) => ({ left: `${(b[0] / pg.width_pt) * 100}%`, top: `${(b[1] / pg.height_pt) * 100}%`, width: `${((b[2] - b[0]) / pg.width_pt) * 100}%`, height: `${((b[3] - b[1]) / pg.height_pt) * 100}%` });
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-3" style={{ background: 'rgba(10,9,8,.6)' }}>
      <div className="ui-card w-full max-w-4xl max-h-[94dvh] flex flex-col" style={{ background: 'var(--s1)' }}>
        <div className="flex flex-wrap items-center gap-3 p-4" style={{ borderBottom: '1px solid var(--b1)' }}>
          <p className="text-sm font-semibold flex-1" style={{ color: 'var(--t0)' }}>Draw the box for <span style={{ color: 'var(--em)' }}>{fields[fieldKey]?.label}</span></p>
          {pages.length > 1 && <select className="text-xs rounded-lg px-2 py-1" style={{ background: 'var(--s3)', border: '1px solid var(--b1)', color: 'var(--t0)' }}
            value={page} onChange={e => { setPage(Number(e.target.value)); setBox(null); }}>{pages.map(p => <option key={p.page} value={p.page}>Page {p.page}</option>)}</select>}
          <Button size="sm" onClick={() => box && onSave(page, box.map(v => Math.round(v * 10) / 10))} disabled={!box || box[2] - box[0] < 6 || box[3] - box[1] < 6}>Use this box</Button>
          <button onClick={onClose} aria-label="Close" style={{ color: 'var(--t2)' }}><X className="w-4 h-4" /></button>
        </div>
        <p className="px-4 pt-3 text-xs" style={{ color: 'var(--t2)' }}>Drag on the page to draw where the value goes. Other fields' boxes are outlined for reference.</p>
        <div className="overflow-auto p-4">
          <div className="relative select-none touch-none" style={{ cursor: 'crosshair' }}
            onPointerDown={e => { (e.target as Element).setPointerCapture?.(e.pointerId); const p = toPt(e); setDrag(p); setBox([p.x, p.y, p.x, p.y]); }}
            onPointerMove={e => { if (!drag) return; const p = toPt(e); setBox([Math.min(drag.x, p.x), Math.min(drag.y, p.y), Math.max(drag.x, p.x), Math.max(drag.y, p.y)]); }}
            onPointerUp={() => setDrag(null)}>
            <img ref={imgRef} src={`data:image/png;base64,${pg.png}`} alt={`Page ${pg.page}`} className="w-full block" draggable={false} style={{ border: '1px solid var(--b2)' }} />
            {Object.entries(fields).filter(([k]) => k !== fieldKey).flatMap(([k, f]) => f.targets.filter(t => t.page === page && t.box).map((t, i) =>
              <div key={`${k}${i}`} className="absolute pointer-events-none" style={{ ...pct(t.box!), border: '1px dashed rgba(100,100,100,.6)' }}>
                <span className="absolute -top-3.5 left-0 text-[9px] mono whitespace-nowrap" style={{ color: '#666' }}>{f.label}</span></div>))}
            {box && <div className="absolute pointer-events-none" style={{ ...pct(box), border: '2px solid var(--em)', background: 'rgba(229,84,27,.12)' }} />}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function CoversheetBuilder() {
  const [error, setError] = useState<string | null>(null);
  // stage 1-2
  const [mdl, setMdl] = useState<Extraction | null>(null);
  const [mdlBusy, setMdlBusy] = useState(false);
  const [q, setQ] = useState({ num: '', name: '', desc: '' });
  const [filter, setFilter] = useState('all');
  const [selectedId, setSelectedId] = useState('');
  const [editing, setEditing] = useState<{ id: string; draft: Partial<Rec> } | null>(null);
  const [adding, setAdding] = useState<Partial<Rec> | null>(null);
  // stage 3
  const [tplFile, setTplFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [tplBusy, setTplBusy] = useState(false);
  const [picker, setPicker] = useState<{ key: string; index: number } | null>(null);
  const [clearHistory, setClearHistory] = useState(true);
  // stage 4-6
  const [vals, setVals] = useState({ revision: '', revision_date: todayIso(), prepared_by: '', checked_by: '', approved_by: '' });
  const [sigs, setSigs] = useState<Record<string, File | null>>({ sig_prepared: null, sig_checked: null, sig_approved: null });
  const sigUrls = useMemo(() => Object.fromEntries(Object.entries(sigs).map(([k, f]) => [k, f ? URL.createObjectURL(f) : ''])), [sigs]);
  useEffect(() => () => Object.values(sigUrls).forEach(u => u && URL.revokeObjectURL(u)), [sigUrls]);
  // stage 7-8
  const [formats, setFormats] = useState({ xlsx: true, pdf: true });
  const [preview, setPreview] = useState<{ kind: string; model?: any; pages?: PageImg[]; warnings: string[] } | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [done, setDone] = useState<{ filename: string; files: string[]; kind: string; warnings: string[]; message: string; pdf_engine: string | null } | null>(null);
  const stale = () => { setPreview(null); setDone(null); };

  // restore the session's MDL + selection + inputs (files cannot be kept by the browser)
  useEffect(() => {
    try {
      const s = JSON.parse(sessionStorage.getItem(STORE) || 'null');
      if (!s?.eid) return;
      if (s.vals) setVals(s.vals);
      api.get<Extraction>(`/coversheet/builder/mdl/${s.eid}`).then(r => { setMdl(r.data); if (s.sel) setSelectedId(s.sel); }).catch(() => sessionStorage.removeItem(STORE));
    } catch { /* optional */ }
  }, []);
  useEffect(() => { try { if (mdl) sessionStorage.setItem(STORE, JSON.stringify({ eid: mdl.extraction_id, sel: selectedId, vals })); } catch { /* optional */ } }, [mdl, selectedId, vals]);

  const selected = useMemo(() => mdl?.records.find(r => r.id === selectedId) || null, [mdl, selectedId]);

  // ── stage 1 ──
  const uploadMdl = async (f: File) => {
    setMdlBusy(true); setError(null); setSelectedId(''); setEditing(null); stale();
    try {
      const fd = new FormData(); fd.append('file', f);
      const r = await api.post<Extraction>('/coversheet/builder/mdl/extract', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setMdl(r.data);
    } catch (e: any) { setMdl(null); setError(errText(e, 'The MDL could not be analysed.')); }
    finally { setMdlBusy(false); }
  };

  // ── stage 2 ──
  const types = useMemo(() => [...new Set((mdl?.records || []).map(r => r.document_type).filter(Boolean))].sort(), [mdl]);
  const rows = useMemo(() => {
    if (!mdl) return [];
    const n = q.num.toLowerCase(), m = q.name.toLowerCase(), d = q.desc.toLowerCase();
    return mdl.records.filter(r => (!n || r.document_number.toLowerCase().includes(n)) && (!m || r.document_name.toLowerCase().includes(m))
      && (!d || r.document_description.toLowerCase().includes(d))
      && (filter === 'all' || (filter === 'flagged' && r.status !== 'ok') || (filter === 'errors' && r.status === 'error')
        || (filter === 'dup' && r.flags.some(f => f.message.includes('appears'))) || (filter === 'edited' && r.edited) || filter === `t:${r.document_type}`));
  }, [mdl, q, filter]);
  const replaceRec = (rec: Rec, summary: Extraction['summary']) => setMdl(m => m && { ...m, summary, records: m.records.some(r => r.id === rec.id) ? m.records.map(r => r.id === rec.id ? rec : r) : [...m.records, rec] });
  const saveEdit = async () => {
    if (!editing || !mdl) return;
    try {
      const r = await api.put(`/coversheet/builder/mdl/${mdl.extraction_id}/records/${editing.id}`, editing.draft);
      replaceRec(r.data.record, r.data.summary); setEditing(null); stale();
    } catch (e: any) { setError(errText(e, 'The correction could not be saved.')); }
  };
  const saveAdd = async () => {
    if (!adding || !mdl) return;
    try {
      const r = await api.post(`/coversheet/builder/mdl/${mdl.extraction_id}/records`, adding);
      replaceRec(r.data.record, r.data.summary); setAdding(null); setSelectedId(r.data.record.id); stale();
    } catch (e: any) { setError(errText(e, 'The document could not be added.')); }
  };

  // ── stage 3 ──
  const analyzeTpl = useCallback(async (f: File, kind: 'excel' | 'pdf', sheet?: string) => {
    setTplBusy(true); setError(null); stale();
    try {
      const fd = new FormData(); fd.append('file', f); fd.append('kind', kind); if (sheet) fd.append('sheet', sheet);
      const r = await api.post<Analysis>('/coversheet/builder/template/analyze', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setAnalysis(r.data); setTplFile(f);
      if (kind === 'pdf') setFormats({ xlsx: false, pdf: true });
    } catch (e: any) { setAnalysis(null); setTplFile(null); setError(errText(e, 'The template could not be analysed.')); }
    finally { setTplBusy(false); }
  }, []);
  const patchField = (k: string, p: Partial<FieldMap>) => { if (!analysis) return; setAnalysis({ ...analysis, fields: { ...analysis.fields, [k]: { ...analysis.fields[k], ...p } } }); stale(); };
  const patchTarget = (k: string, i: number, p: Partial<Target>) => analysis && patchField(k, { targets: analysis.fields[k].targets.map((t, j) => j === i ? { ...t, ...p } : t) });
  const confirmDetected = () => {
    if (!analysis) return;
    const next = Object.fromEntries(Object.entries(analysis.fields).map(([k, f]) => [k, { ...f,
      targets: f.targets.map(t => ({ ...t, confirmed: !!(t.cell?.trim() || t.box) })),
      parts: f.parts && Object.fromEntries(Object.entries(f.parts).map(([p, v]) => [p, { ...v, confirmed: !!v.cell.trim() }])) }]));
    setAnalysis({ ...analysis, fields: next }); stale();
  };

  // ── readiness ──
  const problems = useMemo(() => {
    const p: string[] = [];
    if (!mdl) return ['Upload and analyse the MDL (stage 1).'];
    if (!selected) p.push('Select a document from the MDL (stage 2).');
    else if (selected.status === 'error') p.push('The selected document is incomplete - correct it in stage 2.');
    if (!analysis) { p.push('Upload a coversheet template (stage 3).'); return p; }
    const f = analysis.fields;
    for (const k of ['document_number', 'document_name']) if (!placed(f[k])) p.push(`${f[k].label}: confirm or assign its location (stage 3).`);
    if (!vals.revision.trim()) p.push('Enter the revision number (stage 4).');
    if (!vals.revision_date) p.push('Pick the revision date (stage 4).');
    if (selected && placed(f.document_description) && !selected.document_description) p.push('Document Description: the selected record has none - correct it or skip the field.');
    for (const k of ['prepared_by', 'checked_by', 'approved_by'] as const) if (placed(f[k]) && !vals[k].trim()) p.push(`${f[k].label}: enter a name or skip the field (stage 5).`);
    for (const k of SIG_KEYS) if (sigs[k] && !placed(f[k])) p.push(`${f[k].label}: assign and confirm its location in stage 3, or remove the signature.`);
    if (analysis.kind === 'excel' && !formats.xlsx && !formats.pdf) p.push('Choose Excel and/or PDF output (stage 8).');
    return p;
  }, [mdl, selected, analysis, vals, sigs, formats]);

  const formData = () => {
    const fd = new FormData();
    fd.append('file', tplFile!);
    fd.append('data', JSON.stringify({ extraction_id: mdl!.extraction_id, record_id: selectedId, sheet: analysis?.sheet, mapping: analysis!.fields,
      values: vals, clear_history: clearHistory, formats: [formats.xlsx && 'xlsx', formats.pdf && 'pdf'].filter(Boolean) }));
    for (const k of SIG_KEYS) if (sigs[k]) fd.append(k, sigs[k]!);
    return fd;
  };
  const runPreview = async () => {
    setPreviewing(true); setError(null);
    try {
      const r = await api.post('/coversheet/builder/preview', formData(), { headers: { 'Content-Type': 'multipart/form-data' } });
      setPreview({ kind: r.data.kind, model: r.data.model, pages: r.data.pages, warnings: r.data.warnings || [] });
    } catch (e: any) { setPreview(null); setError(errText(e, 'Preview failed.')); }
    finally { setPreviewing(false); }
  };
  const runGenerate = useCallback(async () => {
    setGenerating(true); setError(null); setDone(null);
    try {
      const r = await api.post('/coversheet/builder/generate', formData(), { headers: { 'Content-Type': 'multipart/form-data' } });
      setDone(r.data);
    } catch (e: any) { setError(errText(e, 'Generation failed.')); }
    finally { setGenerating(false); }
  }, [tplFile, mdl, selectedId, analysis, vals, clearHistory, formats, sigs]); // eslint-disable-line react-hooks/exhaustive-deps
  const onGenerate = () => { if (problems.length) return; runGenerate(); };
  const download = async (kind?: string) => {
    try {
      const r = await api.get('/coversheet/builder/download', { params: kind ? { kind } : {}, responseType: 'blob' });
      const name = /filename="?([^";]+)"?/.exec(r.headers['content-disposition'] || '')?.[1] || done?.filename || 'Coversheet';
      const url = URL.createObjectURL(r.data); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url);
    } catch (e: any) { setError(await blobErr(e, 'Download failed.')); }
  };

  const inp = 'rounded-lg px-2.5 py-1.5 text-sm outline-none w-full';
  const inpS = { background: 'var(--s0)', color: 'var(--t0)', border: '1px solid var(--b2)' } as const;
  const st = (ok: boolean, prev: boolean): 'done' | 'active' | 'locked' => (ok ? 'done' : prev ? 'active' : 'locked');
  const s1 = !!mdl, s2 = !!selected && selected.status !== 'error', s3 = !!analysis && placed(analysis.fields.document_number) && placed(analysis.fields.document_name);
  const s4 = !!vals.revision.trim() && !!vals.revision_date;

  return (
    <div className="space-y-4">
      {error && <Alert variant="error" onClose={() => setError(null)}><span style={{ whiteSpace: 'pre-line' }}>{error}</span></Alert>}

      {/* 1 ─ MDL */}
      <Stage n={1} title="Upload MDL" sub="Excel (.xlsx, .xlsm, .xls) or PDF - scanned PDFs are read by OCR" state={st(s1, true)}
        right={mdl && <Badge variant="neutral">{mdl.summary.records} documents</Badge>}>
        <label className="flex items-center gap-3 rounded-xl px-4 py-3 cursor-pointer" style={{ border: '1px dashed var(--b2)', color: 'var(--t1)' }}>
          {mdlBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileUp className="w-4 h-4" />}
          <span className="text-sm flex-1 truncate">{mdlBusy ? 'Analysing the MDL…' : mdl ? `${mdl.file_name} - replace` : 'Choose the Master Document List'}</span>
          <input type="file" accept=".xlsx,.xlsm,.xls,.pdf" className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) uploadMdl(f); e.target.value = ''; }} />
        </label>
        {mdl && (<>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {([['Documents', mdl.summary.records, 'var(--t0)'], ['Incomplete', mdl.summary.errors, 'var(--rose)'], ['To check', mdl.summary.warnings, 'var(--gold)'],
              ['Duplicate nos.', mdl.summary.duplicates, 'var(--gold)'], ['No description', mdl.summary.missing_description, 'var(--t2)']] as const).map(([l, v, c]) => (
              <div key={l} className="rounded-lg px-3 py-2" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
                <p className="text-lg font-semibold leading-tight" style={{ color: v ? c : 'var(--t2)' }}>{v}</p>
                <p className="mono text-[10px] uppercase tracking-wider" style={{ color: 'var(--t2)' }}>{l}</p>
              </div>))}
          </div>
          <p className="text-xs" style={{ color: 'var(--t2)' }}>
            Read from <b style={{ color: 'var(--t1)' }}>{METHOD[mdl.method] || mdl.method}</b>
            {mdl.sheet && <> · sheet "{mdl.sheet}", header row {mdl.header_row}</>}{mdl.pages && <> · {mdl.pages} page(s)</>}
            {mdl.rows_ignored > 0 && <> · {mdl.rows_ignored} heading / non-document row(s) ignored</>}
          </p>
          {mdl.columns.length > 0 && <div className="flex flex-wrap gap-1.5">{mdl.columns.map(c => (
            <span key={c.field} className="text-[11px] px-2 py-0.5 rounded-full" style={{ border: '1px solid var(--b1)', color: c.header ? 'var(--t1)' : 'var(--t2)' }}>
              {COL_LABEL[c.field]}: {c.header ? `"${c.header}"` : 'not in MDL'}</span>))}</div>}
          {mdl.notes.map(n => <p key={n} className="text-xs flex gap-1.5" style={{ color: 'var(--gold)' }}><AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />{n}</p>)}
        </>)}
      </Stage>

      {/* 2 ─ review + select */}
      <Stage n={2} title="Review and select the document" sub="Correct any extracted value before using it - flagged rows need a look" state={st(s2, s1)}
        right={selected && <Badge variant={selected.status === 'error' ? 'error' : 'success'}>{selected.document_number}</Badge>}>
        {mdl && (<>
          <div className="grid gap-2 sm:grid-cols-[1fr_1fr_1fr_auto]">
            {([['num', 'Document number'], ['name', 'Document name'], ['desc', 'Description']] as const).map(([k, l]) => (
              <div key={k} className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--t2)' }} />
                <input className={`${inp} pl-8`} style={inpS} placeholder={`Search ${l.toLowerCase()}`} value={q[k]} onChange={e => setQ(s => ({ ...s, [k]: e.target.value }))} />
              </div>))}
            <select className={inp} style={inpS} value={filter} onChange={e => setFilter(e.target.value)}>
              <option value="all">All documents</option><option value="flagged">Flagged</option><option value="errors">Incomplete</option>
              <option value="dup">Duplicate numbers</option><option value="edited">Corrected</option>
              {types.map(t => <option key={t} value={`t:${t}`}>Type: {t}</option>)}
            </select>
          </div>
          <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--b1)' }}>
            <div className="max-h-[420px] overflow-auto">
              <table className="w-full text-xs min-w-[760px]">
                <thead className="sticky top-0" style={{ background: 'var(--s2)' }}>
                  <tr className="text-left" style={{ color: 'var(--t2)' }}>
                    <th className="px-2 py-2 w-8" /><th className="px-2">Document No.</th><th className="px-2">Document Name</th><th className="px-2">Description</th>
                    <th className="px-2">Rev</th><th className="px-2">Type</th><th className="px-2">Status</th><th className="px-2 w-8" />
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 300).map(r => editing?.id === r.id ? (
                    <tr key={r.id} style={{ borderTop: '1px solid var(--b1)', background: 'var(--em-dim)' }}>
                      <td />
                      {(['document_number', 'document_name', 'document_description', 'revision', 'document_type'] as const).map(k => (
                        <td key={k} className="px-1 py-1"><input className="w-full rounded px-1.5 py-1 text-xs" style={inpS} value={(editing.draft[k] ?? r[k]) as string}
                          onChange={e => setEditing({ ...editing, draft: { ...editing.draft, [k]: e.target.value } })} /></td>))}
                      <td colSpan={2} className="px-1 whitespace-nowrap"><Button size="sm" onClick={saveEdit}>Save</Button> <button className="text-xs ml-1 underline" style={{ color: 'var(--t2)' }} onClick={() => setEditing(null)}>Cancel</button></td>
                    </tr>
                  ) : (
                    <tr key={r.id} onClick={() => { setSelectedId(r.id); stale(); }} className="cursor-pointer align-top"
                      style={{ borderTop: '1px solid var(--b1)', background: r.id === selectedId ? 'var(--em-dim)' : undefined, color: 'var(--t1)' }}>
                      <td className="px-2 py-1.5"><input type="radio" checked={r.id === selectedId} readOnly aria-label={`Select ${r.document_number}`} /></td>
                      <td className="px-2 py-1.5 font-mono whitespace-nowrap" style={{ color: 'var(--t0)' }}>{r.document_number || <i style={{ color: 'var(--rose)' }}>missing</i>}</td>
                      <td className="px-2 py-1.5">{r.document_name || <i style={{ color: 'var(--rose)' }}>missing</i>}</td>
                      <td className="px-2 py-1.5" style={{ color: r.document_description ? 'var(--t1)' : 'var(--t2)' }}>{r.document_description || '-'}</td>
                      <td className="px-2 py-1.5">{r.revision || '-'}</td>
                      <td className="px-2 py-1.5">{r.document_type || '-'}</td>
                      <td className="px-2 py-1.5"><StatusBadge r={r} />{r.edited && <span className="ml-1 text-[10px]" style={{ color: 'var(--t2)' }}>corrected</span>}</td>
                      <td className="px-2 py-1.5"><button title="Correct this record" onClick={e => { e.stopPropagation(); setEditing({ id: r.id, draft: {} }); }} style={{ color: 'var(--t2)' }}><Pencil className="w-3.5 h-3.5" /></button></td>
                    </tr>))}
                  {adding && (
                    <tr style={{ borderTop: '1px solid var(--b1)', background: 'var(--s1)' }}>
                      <td />
                      {(['document_number', 'document_name', 'document_description', 'revision', 'document_type'] as const).map(k => (
                        <td key={k} className="px-1 py-1"><input className="w-full rounded px-1.5 py-1 text-xs" style={inpS} placeholder={COL_LABEL[k]} value={(adding[k] as string) || ''}
                          onChange={e => setAdding({ ...adding, [k]: e.target.value })} /></td>))}
                      <td colSpan={2} className="px-1 whitespace-nowrap"><Button size="sm" onClick={saveAdd}>Add</Button> <button className="text-xs ml-1 underline" style={{ color: 'var(--t2)' }} onClick={() => setAdding(null)}>Cancel</button></td>
                    </tr>)}
                  {!rows.length && <tr><td colSpan={8} className="p-4 text-center" style={{ color: 'var(--t2)' }}>No documents match.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs" style={{ color: 'var(--t2)' }}>
            <span>{rows.length > 300 ? `Showing 300 of ${rows.length} - narrow the search` : `${rows.length} shown`}</span>
            <button className="underline" onClick={() => { setSelectedId(''); stale(); }}>Clear selection</button>
            <button className="underline flex items-center gap-1" onClick={() => setAdding({})}><Plus className="w-3 h-3" />Add a document the MDL reading missed</button>
          </div>
          {selected && (
            <div className="rounded-xl p-3" style={{ background: 'var(--s1)', border: `1px solid ${selected.status === 'error' ? 'var(--rose)' : 'var(--b2)'}` }}>
              <p className="eyebrow mb-2">Selected document · source of the coversheet</p>
              <dl className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm" style={{ color: 'var(--t1)' }}>
                <dt style={{ color: 'var(--t2)' }}>Number</dt><dd className="font-mono" style={{ color: 'var(--t0)' }}>{selected.document_number || '—'}</dd>
                <dt style={{ color: 'var(--t2)' }}>Name</dt><dd style={{ color: 'var(--t0)' }}>{selected.document_name || '—'}</dd>
                <dt style={{ color: 'var(--t2)' }}>Description</dt><dd>{selected.document_description || <span style={{ color: 'var(--t2)' }}>not in the MDL</span>}</dd>
                {selected.revision && <><dt style={{ color: 'var(--t2)' }}>MDL revision</dt><dd>{selected.revision}</dd></>}
                <dt style={{ color: 'var(--t2)' }}>Source</dt><dd>{selected.source}{selected.edited ? ' · corrected by you' : ''}</dd>
              </dl>
              {selected.flags.filter(f => f.message !== 'Corrected by the user').map(f => (
                <p key={f.message} className="text-xs mt-1 flex gap-1.5" style={{ color: f.level === 'error' ? 'var(--rose)' : f.level === 'warning' ? 'var(--gold)' : 'var(--t2)' }}>
                  <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />{f.message}</p>))}
            </div>)}
        </>)}
      </Stage>

      {/* 3 ─ template */}
      <Stage n={3} title="Upload the coversheet template" sub="The template is the base document - only the mapped fields are filled" state={st(s3, s2)}
        right={analysis && <Badge variant="neutral">{analysis.kind === 'excel' ? 'Excel' : 'PDF'} template</Badge>}>
        <div className="grid gap-2 sm:grid-cols-2">
          {([['excel', 'Upload Excel Template', '.xlsx, .xlsm', '.xlsx,.xlsm', FileSpreadsheet], ['pdf', 'Upload PDF Template', '.pdf', '.pdf', FileText]] as const).map(([k, l, hint, acc, Icon]) => (
            <label key={k} className="flex items-center gap-3 rounded-xl px-4 py-3 cursor-pointer" style={{ border: `1px ${analysis?.kind === k ? 'solid var(--em)' : 'dashed var(--b2)'}`, color: 'var(--t1)' }}>
              {tplBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Icon className="w-4 h-4" />}
              <span className="flex-1 min-w-0"><span className="block text-sm font-medium" style={{ color: 'var(--t0)' }}>{l}</span>
                <span className="block text-xs truncate" style={{ color: 'var(--t2)' }}>{analysis?.kind === k && tplFile ? tplFile.name : hint}</span></span>
              <input type="file" accept={acc} className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) analyzeTpl(f, k); e.target.value = ''; }} />
            </label>))}
        </div>
        {analysis && (<>
          <p className="text-xs" style={{ color: 'var(--t2)' }}>
            {analysis.kind === 'excel' ? <>Sheet {(analysis.sheets?.length || 0) > 1
              ? <select className="rounded px-1.5 py-0.5" style={inpS} value={analysis.sheet} onChange={e => tplFile && analyzeTpl(tplFile, 'excel', e.target.value)}>{analysis.sheets!.map(s => <option key={s}>{s}</option>)}</select>
              : <b style={{ color: 'var(--t1)' }}>{analysis.sheet}</b>} · {analysis.dimensions} · {analysis.merged_ranges} merged ranges · {analysis.images} image(s) · {analysis.orientation}</>
              : <>{analysis.pages?.length} page(s) · {analysis.pages?.map(p => `${Math.round(p.width)} × ${Math.round(p.height)} pt`).join(', ')}</>}
          </p>
          {analysis.notes?.map(n => <p key={n} className="text-xs flex gap-1.5" style={{ color: 'var(--gold)' }}><AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />{n}</p>)}
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs flex-1 min-w-[240px]" style={{ color: 'var(--t2)' }}>Only confirmed locations are written. Detections marked Review need your decision; assign anything not found{analysis.kind === 'excel' ? ' (cell like C5, or a range like C20:E22 for a signature)' : ' by drawing its box on the page'}.</p>
            <Button size="sm" variant="secondary" onClick={confirmDetected}><CheckCircle2 className="w-3.5 h-3.5" /> Confirm detected locations</Button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs min-w-[720px]">
              <thead><tr className="text-left" style={{ color: 'var(--t2)' }}><th className="py-1.5 pr-3">Field</th><th className="pr-3">Detection</th><th className="pr-3">Location in the template</th><th>Value from</th></tr></thead>
              <tbody>
                {FIELD_ORDER.map(k => {
                  const f = analysis.fields[k]; if (!f) return null;
                  return (
                    <tr key={k} className="align-top" style={{ borderTop: '1px solid var(--b1)' }}>
                      <td className="py-2 pr-3 font-semibold whitespace-nowrap" style={{ color: 'var(--t0)' }}>{f.label}{f.required && <span style={{ color: 'var(--rose)' }}> *</span>}</td>
                      <td className="py-2 pr-3 max-w-[220px]"><ConfBadge c={f.confidence} /><p className="mt-1" style={{ color: 'var(--t2)' }}>{f.reason}</p></td>
                      <td className="py-2 pr-3 space-y-1.5">
                        {f.skipped ? <span style={{ color: 'var(--t2)' }}>Skipped - not written</span> : (<>
                          {f.targets.map((t, i) => (
                            <div key={i} className="flex flex-wrap items-center gap-2">
                              <input type="checkbox" checked={t.confirmed} disabled={!(t.cell?.trim() || t.box)} title="Confirmed - write here" onChange={e => patchTarget(k, i, { confirmed: e.target.checked })} />
                              {analysis.kind === 'excel'
                                ? <input className="rounded px-1.5 py-1 w-24 font-mono uppercase" style={inpS} value={t.cell || ''} placeholder="Cell"
                                    onChange={e => patchTarget(k, i, { cell: e.target.value.toUpperCase().replace(/[^A-Z0-9:]/g, ''), confirmed: false })} />
                                : <button className="rounded px-2 py-1 mono" style={inpS} onClick={() => setPicker({ key: k, index: i })}>
                                    {t.box ? `p${t.page} · ${Math.round(t.box[0])},${Math.round(t.box[1])} · ${Math.round(t.box[2] - t.box[0])}×${Math.round(t.box[3] - t.box[1])}` : 'Draw box'}</button>}
                              <span className="truncate max-w-[220px]" style={{ color: 'var(--t2)' }} title={t.current}>{t.where || ''}{t.current ? ` · "${t.current.replace(/\s+/g, ' ').slice(0, 28)}"` : ''}</span>
                              {analysis.kind === 'pdf' && f.kind === 'text' && t.box && (
                                <label className="flex items-center gap-1" style={{ color: 'var(--t2)' }} title="Paint the box white before writing (hides an old value)">
                                  <input type="checkbox" checked={!!t.clear} onChange={e => patchTarget(k, i, { clear: e.target.checked })} />cover old text</label>)}
                              <button onClick={() => patchField(k, { targets: f.targets.filter((_, j) => j !== i) })} title="Remove" style={{ color: 'var(--t2)' }}><X className="w-3 h-3" /></button>
                            </div>))}
                          {f.parts && Object.entries(f.parts).map(([p, v]) => (
                            <div key={p} className="flex items-center gap-2">
                              <input type="checkbox" checked={v.confirmed} disabled={!v.cell.trim()} onChange={e => patchField(k, { parts: { ...f.parts!, [p]: { ...v, confirmed: e.target.checked } } })} />
                              <input className="rounded px-1.5 py-1 w-24 font-mono uppercase" style={inpS} value={v.cell}
                                onChange={e => patchField(k, { parts: { ...f.parts!, [p]: { ...v, cell: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''), confirmed: false } } })} />
                              <span style={{ color: 'var(--t2)' }}>{PART_LABEL[p]} box</span>
                            </div>))}
                          <button className="underline" style={{ color: 'var(--t2)' }} onClick={() => {
                            if (analysis.kind === 'pdf') setPicker({ key: k, index: f.targets.length });
                            else patchField(k, { targets: [...f.targets, { cell: '', confirmed: false, mode: f.kind === 'image' ? 'image' : 'replace' }] });
                          }}>+ {analysis.kind === 'pdf' ? 'draw a box' : 'add a cell'}</button>
                        </>)}
                        {!f.required && <label className="flex items-center gap-1.5" style={{ color: 'var(--t2)' }}>
                          <input type="checkbox" checked={!!f.skipped} onChange={e => patchField(k, { skipped: e.target.checked })} /> Skip this field</label>}
                      </td>
                      <td className="py-2 whitespace-nowrap" style={{ color: 'var(--t2)' }}>{f.source === 'mdl' ? 'Selected MDL record' : f.source === 'signature' ? 'Stage 6 upload' : k === 'revision' || k === 'revision_date' ? 'Stage 4' : 'Stage 5'}</td>
                    </tr>);
                })}
              </tbody>
            </table>
          </div>
          {analysis.kind === 'excel' && !!analysis.table && (
            <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--t1)' }}>
              <input type="checkbox" checked={clearHistory} onChange={e => { setClearHistory(e.target.checked); stale(); }} />
              Clear the template's own revision-history rows (they belong to the template's document)</label>)}
        </>)}
      </Stage>

      {/* 4 ─ revision */}
      <Stage n={4} title="Revision details" state={st(s4, s3)}>
        <div className="grid gap-3 sm:grid-cols-2 max-w-xl">
          <label className="text-xs space-y-1" style={{ color: 'var(--t2)' }}>Revision number *
            <input className={inp} style={inpS} value={vals.revision} placeholder="e.g. 0, 1, A, R2" onChange={e => { setVals(v => ({ ...v, revision: e.target.value })); stale(); }} /></label>
          <label className="text-xs space-y-1" style={{ color: 'var(--t2)' }}>Revision date *
            <input type="date" className={inp} style={inpS} value={vals.revision_date} onChange={e => { setVals(v => ({ ...v, revision_date: e.target.value })); stale(); }} /></label>
        </div>
        {selected?.revision && selected.revision !== vals.revision && (
          <p className="text-xs" style={{ color: 'var(--t2)' }}>The MDL lists revision <b style={{ color: 'var(--t1)' }}>{selected.revision}</b> for this document.
            <button className="underline ml-1.5" onClick={() => { setVals(v => ({ ...v, revision: selected.revision })); stale(); }}>Use it</button></p>)}
        <p className="text-xs" style={{ color: 'var(--t2)' }}>Excel templates show the date in their own date format; PDF templates use DD.MM.YYYY. The revision is written exactly as typed.</p>
      </Stage>

      {/* 5 ─ approval */}
      <Stage n={5} title="Approval details" sub="Leave a name empty only when its field is skipped in stage 3" state={st(s4 && !problems.some(p => p.includes('stage 5')), s4)}>
        <div className="grid gap-3 sm:grid-cols-3">
          {(['prepared_by', 'checked_by', 'approved_by'] as const).map(k => (
            <label key={k} className="text-xs space-y-1" style={{ color: 'var(--t2)' }}>{analysis?.fields[k]?.label || k}
              <input className={inp} style={inpS} value={vals[k]} onChange={e => { setVals(v => ({ ...v, [k]: e.target.value })); stale(); }} /></label>))}
        </div>
      </Stage>

      {/* 6 ─ signatures */}
      <Stage n={6} title="Signatures" sub="Optional - PNG or JPG, placed inside its box without stretching" state={st(s4 && SIG_KEYS.every(k => !sigs[k] || placed(analysis?.fields[k])), s4)}>
        <div className="grid gap-3 sm:grid-cols-3">
          {SIG_KEYS.map(k => {
            const loc = placed(analysis?.fields[k]);
            return (
              <div key={k} className="rounded-xl p-3 space-y-2" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
                <p className="text-xs font-semibold" style={{ color: 'var(--t0)' }}>{SIG_LABEL[k]} signature</p>
                <div className="h-20 rounded-lg flex items-center justify-center" style={{ background: '#fff', border: '1px solid var(--b1)' }}>
                  {sigs[k] ? <img src={sigUrls[k]} alt={`${SIG_LABEL[k]} signature`} className="max-h-[72px] max-w-full object-contain" />
                    : <Square className="w-5 h-5" style={{ color: '#bbb' }} />}
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs underline cursor-pointer" style={{ color: 'var(--t1)' }}>{sigs[k] ? 'Replace' : 'Upload'}
                    <input type="file" accept=".png,.jpg,.jpeg,image/png,image/jpeg" className="hidden" onChange={e => {
                      const f = e.target.files?.[0]; e.target.value = '';
                      if (!f) return;
                      if (!/\.(png|jpe?g)$/i.test(f.name)) { setError('Signatures must be PNG or JPG images.'); return; }
                      if (f.size > 5 * 1024 * 1024) { setError('A signature image must be smaller than 5 MB.'); return; }
                      setSigs(s => ({ ...s, [k]: f })); stale();
                    }} /></label>
                  {sigs[k] && <button className="text-xs flex items-center gap-1" style={{ color: 'var(--t2)' }} onClick={() => { setSigs(s => ({ ...s, [k]: null })); stale(); }}><Trash2 className="w-3 h-3" />Remove</button>}
                </div>
                <p className="text-[11px]" style={{ color: loc ? 'var(--t2)' : sigs[k] ? 'var(--rose)' : 'var(--t2)' }}>
                  {loc ? 'Location confirmed in stage 3' : 'No confirmed location - assign it in stage 3'}</p>
              </div>);
          })}
        </div>
      </Stage>

      {mdl && !!problems.length && (
        <div className="rounded-xl px-4 py-3" style={{ background: 'var(--s1)', border: '1px dashed var(--b2)' }}>
          <p className="eyebrow mb-1.5">Still needed before preview and generation</p>
          <ul className="text-xs list-disc pl-5 space-y-0.5" style={{ color: 'var(--t1)' }}>{problems.map(p => <li key={p}>{p}</li>)}</ul>
        </div>)}

      {/* 7 ─ preview */}
      <Stage n={7} title="Preview" sub="The populated coversheet exactly as it will be generated" state={st(!!preview, !problems.length)}>
        <Button variant="secondary" onClick={runPreview} loading={previewing} disabled={!!problems.length}><Eye className="w-4 h-4" /> Build preview</Button>
        {preview && (<>
          {preview.warnings.map(w => <p key={w} className="text-xs flex gap-1.5" style={{ color: 'var(--gold)' }}><AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />{w}</p>)}
          {preview.kind === 'excel' && preview.model && <ModelPreview model={preview.model} />}
          {preview.kind === 'pdf' && preview.pages?.map(p => (
            <img key={p.page} src={`data:image/png;base64,${p.png}`} alt={`Preview page ${p.page}`} className="w-full rounded-lg" style={{ border: '1px solid var(--b2)' }} />))}
        </>)}
      </Stage>

      {/* 8 ─ generate */}
      <Stage n={8} title="Generate" state={st(!!done, !problems.length)}>
        {analysis?.kind === 'excel' && (
          <div className="flex flex-wrap gap-4 text-xs" style={{ color: 'var(--t1)' }}>
            <label className="flex items-center gap-1.5"><input type="checkbox" checked={formats.xlsx} onChange={e => { setFormats(f => ({ ...f, xlsx: e.target.checked })); setDone(null); }} /> Excel (.xlsx)</label>
            <label className="flex items-center gap-1.5"><input type="checkbox" checked={formats.pdf} onChange={e => { setFormats(f => ({ ...f, pdf: e.target.checked })); setDone(null); }} /> PDF</label>
          </div>)}
        {analysis?.kind === 'pdf' && <p className="text-xs" style={{ color: 'var(--t2)' }}>A PDF template produces a PDF coversheet.</p>}
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={onGenerate} loading={generating} disabled={!!problems.length}>Generate coversheet</Button>
          {done && done.files.length > 1 && done.files.map(n => (
            <Button key={n} variant="secondary" onClick={() => download(n.split('.').pop())}><Download className="w-4 h-4" /> {n}</Button>))}
          {done && done.files.length === 1 && <Button variant="secondary" onClick={() => download()}><Download className="w-4 h-4" /> {done.filename}</Button>}
        </div>
        {done && <Alert variant="success">{done.message}{done.pdf_engine ? ` PDF via ${done.pdf_engine === 'libreoffice' ? 'LibreOffice' : 'built-in renderer'}.` : ''}</Alert>}
        {done?.warnings.map(w => <p key={w} className="text-xs flex gap-1.5" style={{ color: 'var(--gold)' }}><AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />{w}</p>)}
      </Stage>

      {picker && analysis?.page_images && (
        <BoxPicker pages={analysis.page_images} fields={analysis.fields} fieldKey={picker.key} initial={analysis.fields[picker.key].targets[picker.index]}
          onClose={() => setPicker(null)}
          onSave={(page, box) => {
            const f = analysis.fields[picker.key];
            const t: Target = { ...(f.targets[picker.index] || { clear: false }), page, box, confirmed: true, where: 'drawn by you', current: '' };
            const targets = [...f.targets]; targets[picker.index] = t;
            patchField(picker.key, { targets, skipped: false }); setPicker(null);
          }} />)}
    </div>
  );
}
