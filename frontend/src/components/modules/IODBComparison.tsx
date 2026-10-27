/**
 * IODB Comparison & Revision Report
 * Upload two IODB revisions, compare them by TAG NO, review the changes and download a PDF report.
 * All comparison work is done on the server; this page only pages through the results.
 */
import { useEffect, useMemo, useState } from 'react';
import { GitCompare, FileText, Download, X, ChevronLeft, ChevronRight, AlertTriangle, Info } from 'lucide-react';
import api from '@/services/api';
import { getCurrentProject } from '@/services/projectContext';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import FileUploadCard from '../ui/FileUploadCard';

type Status = 'added' | 'deleted' | 'modified' | 'unchanged' | 'review';

interface CategoryRow { code: string; name: string; count: number }
interface Warn { level: string; code: string; message: string }
interface Comparison {
  id: string;
  file1: { name: string; instruments: number; records: number; columns: number };
  file2: { name: string; instruments: number; records: number; columns: number };
  counts: Record<Status, number>;
  status_counts: Record<Status, number>;
  totals: { iodb1: number; iodb2: number; common: number; changed_instruments: number; field_changes: number };
  totally_different: boolean;
  summary_text: string;
  category_counts: CategoryRow[];
  field_counts: { column: string; count: number }[];
  warnings: Warn[];
  duplicates: { iodb1: Record<string, number>; iodb2: Record<string, number> };
  missing_tag: { iodb1: number; iodb2: number };
  compared_columns: { name: string; category: string }[];
  categories: { code: string; name: string }[];
}
interface RecordRow {
  tag: string; shown_tag: string; type: string; pid: string; service: string; area: string; status: string;
  n_changes: number; changed_fields: string[]; count_1?: number; count_2?: number;
}
interface Change { column: string; category: string; old: string; new: string; change_type: string }
interface RecordDetail {
  tag: string; status: Status; n_changes: number; changes: Change[];
  iodb1: Record<string, string> | null; iodb2: Record<string, string> | null;
  duplicates1: Record<string, string>[]; duplicates2: Record<string, string>[];
}

const STATUS_META: Record<Status, { label: string; color: string }> = {
  added: { label: 'ADDED', color: '#4ade80' },
  deleted: { label: 'DELETED', color: '#f87171' },
  modified: { label: 'MODIFIED', color: '#fbbf24' },
  unchanged: { label: 'UNCHANGED', color: '#94a3b8' },
  review: { label: 'NEEDS REVIEW', color: '#fb923c' },
};
const PAGE_SIZE = 50;

const errText = (e: any, fallback: string) => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (e?.response?.data instanceof Blob) return fallback;
  return fallback;
};

function Badge({ status }: { status: Status }) {
  const m = STATUS_META[status];
  return (
    <span className="inline-block px-2 py-0.5 rounded-md text-[10px] font-bold tracking-wide"
      style={{ color: m.color, border: `1px solid ${m.color}66`, background: `${m.color}14` }}>
      {m.label}
    </span>
  );
}

function Stat({ label, value, color }: { label: string; value: number | string; color?: string }) {
  return (
    <div className="rounded-xl p-4" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
      <p className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--t2)' }}>{label}</p>
      <p className="text-2xl font-bold mt-1" style={{ color: color || 'var(--t0)' }}>{value}</p>
    </div>
  );
}

/* ───────────────────────── record detail window ───────────────────────── */
function RecordModal({ cid, tag, categories, onClose }: {
  cid: string; tag: string; categories: Record<string, string>; onClose: () => void;
}) {
  const [data, setData] = useState<RecordDetail | null>(null);
  const [err, setErr] = useState('');
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    api.get<RecordDetail>(`/validator/compare/${cid}/record`, { params: { tag } })
      .then((r) => setData(r.data)).catch((e) => setErr(errText(e, 'Could not load the record')));
  }, [cid, tag]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const changed = new Set((data?.changes || []).map((c) => c.column));
  const full = data?.iodb2 || data?.iodb1 || {};
  const th = 'text-left text-[10px] font-bold uppercase tracking-wider px-3 py-2';

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 overflow-auto"
      style={{ background: 'rgba(0,0,0,0.6)' }} onClick={onClose}>
      <div className="w-full max-w-4xl rounded-2xl my-8" style={{ background: 'var(--s2)', border: '1px solid var(--b2)' }}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between gap-3 px-5 py-4" style={{ borderBottom: '1px solid var(--b1)' }}>
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="text-base font-bold" style={{ color: 'var(--t0)' }}>{data?.tag || tag}</h3>
            {data && <Badge status={data.status} />}
            {data?.status === 'modified' && (
              <span className="text-xs" style={{ color: 'var(--t1)' }}>{data.n_changes} change{data.n_changes === 1 ? '' : 's'}</span>
            )}
          </div>
          <button onClick={onClose} aria-label="Close" style={{ color: 'var(--t2)' }}><X className="w-5 h-5" /></button>
        </div>

        <div className="p-5 space-y-4">
          {err && <Alert variant="error" title="Error">{err}</Alert>}
          {!data && !err && <p className="text-sm" style={{ color: 'var(--t2)' }}>Loading…</p>}

          {data?.status === 'modified' && (
            <div className="overflow-auto rounded-xl" style={{ border: '1px solid var(--b1)' }}>
              <table className="w-full text-sm">
                <thead style={{ background: 'var(--s3)' }}>
                  <tr style={{ color: 'var(--t1)' }}>
                    <th className={th}>Field</th><th className={th}>Category</th>
                    <th className={th}>IODB 1 — OLD VALUE</th><th className={th}>IODB 2 — NEW VALUE</th>
                  </tr>
                </thead>
                <tbody>
                  {data.changes.map((c) => (
                    <tr key={c.column} style={{ borderTop: '1px solid var(--b1)' }}>
                      <td className="px-3 py-2 font-semibold align-top" style={{ color: 'var(--t0)' }}>{c.column}</td>
                      <td className="px-3 py-2 align-top text-xs" style={{ color: 'var(--t2)' }}>{categories[c.category] || ''}</td>
                      <td className="px-3 py-2 align-top break-words" style={{ color: '#f87171' }}>
                        <span className="text-[10px] font-bold mr-1">OLD:</span>{c.old || <em>(empty)</em>}
                      </td>
                      <td className="px-3 py-2 align-top break-words" style={{ color: '#4ade80' }}>
                        <span className="text-[10px] font-bold mr-1">NEW:</span>{c.new || <em>(empty)</em>}
                        {c.change_type !== 'VALUE CHANGED' && (
                          <span className="ml-2 text-[10px]" style={{ color: 'var(--t2)' }}>({c.change_type.toLowerCase()})</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {data?.status === 'review' && (
            <div className="space-y-3">
              <Alert variant="warning" title="Duplicate TAG NO">
                This TAG NO appears more than once, so it was not compared. Resolve the duplicate in the IODB and compare again.
              </Alert>
              {[['IODB 1', data.duplicates1], ['IODB 2', data.duplicates2]].map(([label, rows]) => (
                (rows as Record<string, string>[]).length > 0 && (
                  <p key={label as string} className="text-sm" style={{ color: 'var(--t1)' }}>
                    {label as string}: {(rows as Record<string, string>[]).length} records
                  </p>
                )
              ))}
            </div>
          )}

          {data && data.status !== 'review' && (
            <div>
              {data.status === 'modified' ? (
                <button className="text-xs font-semibold" style={{ color: 'var(--em)' }} onClick={() => setShowAll(!showAll)}>
                  {showAll ? 'Hide' : 'Show'} complete IODB 2 record
                </button>
              ) : (
                <p className="text-xs font-semibold mb-2" style={{ color: 'var(--t2)' }}>
                  Complete record from {data.status === 'added' ? 'IODB 2' : 'IODB 1'}
                </p>
              )}
              {(data.status !== 'modified' || showAll) && (
                <div className="mt-2 rounded-xl overflow-auto max-h-96" style={{ border: '1px solid var(--b1)' }}>
                  <table className="w-full text-sm">
                    <tbody>
                      {Object.entries(full).filter(([k, v]) => v !== '' || changed.has(k)).map(([k, v]) => (
                        <tr key={k} style={{ borderTop: '1px solid var(--b1)', background: changed.has(k) ? 'rgba(251,191,36,0.08)' : undefined }}>
                          <td className="px-3 py-1.5 text-xs font-semibold w-1/3 align-top" style={{ color: 'var(--t2)' }}>
                            {k}{changed.has(k) ? ' (changed)' : ''}
                          </td>
                          <td className="px-3 py-1.5 break-words" style={{ color: 'var(--t0)' }}>{v}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ───────────────────────── records table with filters ───────────────────────── */
function RecordsPanel({ comp }: { comp: Comparison }) {
  const tabs = (['added', 'deleted', 'modified', 'unchanged', 'review'] as Status[])
    .filter((s) => s !== 'review' || comp.status_counts.review > 0);
  const [tab, setTab] = useState<Status>(comp.status_counts.modified > 0 ? 'modified' : 'added');
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [field, setField] = useState('');
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<RecordRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [open, setOpen] = useState<string | null>(null);

  const catNames = useMemo(() => Object.fromEntries(comp.categories.map((c) => [c.code, c.name])), [comp.categories]);

  // debounce the search box
  const [qq, setQq] = useState('');
  useEffect(() => { const t = setTimeout(() => { setQq(q); setPage(1); }, 300); return () => clearTimeout(t); }, [q]);

  useEffect(() => {
    let live = true;
    setLoading(true);
    api.get<{ items: RecordRow[]; total: number }>(`/validator/compare/${comp.id}/records`, {
      params: { status: tab, q: qq, category: tab === 'modified' ? category : '', field: tab === 'modified' ? field : '',
        page, page_size: PAGE_SIZE },
    }).then((r) => { if (live) { setRows(r.data.items); setTotal(r.data.total); setErr(''); } })
      .catch((e) => live && setErr(errText(e, 'Could not load records')))
      .finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [comp.id, tab, qq, category, field, page]);

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const th = 'text-left text-[10px] font-bold uppercase tracking-wider px-3 py-2 whitespace-nowrap';
  const sel = 'px-2 py-1.5 rounded-lg text-xs outline-none';
  const selStyle = { background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)' };

  return (
    <Card title="Detailed Comparison" description="Select a TAG NO to open its record." icon={FileText}>
      <div className="flex gap-1.5 flex-wrap mb-4" role="tablist">
        {tabs.map((s) => (
          <button key={s} role="tab" aria-selected={tab === s}
            onClick={() => { setTab(s); setPage(1); setCategory(''); setField(''); }}
            className="px-3 py-1.5 rounded-lg text-xs font-bold"
            style={{
              color: tab === s ? '#0b1220' : STATUS_META[s].color,
              background: tab === s ? STATUS_META[s].color : 'transparent',
              border: `1px solid ${STATUS_META[s].color}88`,
            }}>
            {STATUS_META[s].label} ({comp.status_counts[s]})
          </button>
        ))}
      </div>

      <div className="flex gap-2 flex-wrap mb-3">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search TAG NO, P&ID, type, service…"
          className={`${sel} flex-1 min-w-[200px]`} style={selStyle} aria-label="Search records" />
        {tab === 'modified' && (
          <>
            <select value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }} className={sel} style={selStyle}
              aria-label="Filter by change category">
              <option value="">All change categories</option>
              {comp.categories.map((c) => <option key={c.code} value={c.code}>{c.code} – {c.name}</option>)}
            </select>
            <select value={field} onChange={(e) => { setField(e.target.value); setPage(1); }} className={sel} style={selStyle}
              aria-label="Filter by changed field">
              <option value="">All changed fields</option>
              {comp.field_counts.map((f) => <option key={f.column} value={f.column}>{f.column} ({f.count})</option>)}
            </select>
          </>
        )}
      </div>

      {err && <Alert variant="error" title="Error">{err}</Alert>}

      <div className="overflow-auto rounded-xl" style={{ border: '1px solid var(--b1)', opacity: loading ? 0.6 : 1 }}>
        <table className="w-full text-sm">
          <thead style={{ background: 'var(--s3)', color: 'var(--t1)' }}>
            <tr>
              <th className={th}>TAG NO</th><th className={th}>Instrument Type</th><th className={th}>P&amp;ID NO.</th>
              {tab === 'modified' ? (<><th className={th}>No. of Changes</th><th className={th}>Changed Fields</th></>)
                : tab === 'review' ? (<><th className={th}>In IODB 1</th><th className={th}>In IODB 2</th></>)
                  : (<><th className={th}>Service</th><th className={th}>Area</th></>)}
              <th className={th}>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.tag} style={{ borderTop: '1px solid var(--b1)' }}>
                <td className="px-3 py-2">
                  <button className="font-semibold underline-offset-2 hover:underline text-left" style={{ color: 'var(--em)' }}
                    onClick={() => setOpen(r.tag)}>{r.shown_tag || r.tag}</button>
                </td>
                <td className="px-3 py-2" style={{ color: 'var(--t1)' }}>{r.type}</td>
                <td className="px-3 py-2 whitespace-nowrap" style={{ color: 'var(--t1)' }}>{r.pid}</td>
                {tab === 'modified' ? (
                  <>
                    <td className="px-3 py-2 font-semibold" style={{ color: 'var(--t0)' }}>{r.n_changes}</td>
                    <td className="px-3 py-2 text-xs" style={{ color: 'var(--t2)' }}>
                      {r.changed_fields.join(', ')}{r.n_changes > r.changed_fields.length ? ' …' : ''}
                    </td>
                  </>
                ) : tab === 'review' ? (
                  <><td className="px-3 py-2">{r.count_1}</td><td className="px-3 py-2">{r.count_2}</td></>
                ) : (
                  <><td className="px-3 py-2" style={{ color: 'var(--t1)' }}>{r.service}</td>
                    <td className="px-3 py-2" style={{ color: 'var(--t1)' }}>{r.area}</td></>
                )}
                <td className="px-3 py-2"><Badge status={tab} /></td>
              </tr>
            ))}
            {rows.length === 0 && !loading && (
              <tr><td colSpan={6} className="px-3 py-8 text-center text-sm" style={{ color: 'var(--t2)' }}>No records</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between mt-3 text-xs" style={{ color: 'var(--t2)' }}>
        <span>{total} record{total === 1 ? '' : 's'}</span>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft className="w-4 h-4" /></Button>
          <span>Page {page} of {pages}</span>
          <Button variant="ghost" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}><ChevronRight className="w-4 h-4" /></Button>
        </div>
      </div>

      {open && <RecordModal cid={comp.id} tag={open} categories={catNames} onClose={() => setOpen(null)} />}
    </Card>
  );
}

/* ───────────────────────── page ───────────────────────── */
export default function IODBComparison() {
  const [file1, setFile1] = useState<File | null>(null);
  const [file2, setFile2] = useState<File | null>(null);
  const [ignoreCase, setIgnoreCase] = useState(true);
  const [comparing, setComparing] = useState(false);
  const [comp, setComp] = useState<Comparison | null>(null);
  const [error, setError] = useState('');
  const [pdfBusy, setPdfBusy] = useState('');

  const compare = async () => {
    if (!file1 || !file2) return;
    setComparing(true); setError(''); setComp(null);
    const fd = new FormData();
    fd.append('file1', file1); fd.append('file2', file2);
    fd.append('ignore_case', String(ignoreCase));
    const pid = getCurrentProject();
    if (pid) fd.append('project_id', pid);
    try {
      const r = await api.post<Comparison>('/validator/compare', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setComp(r.data);
    } catch (e: any) {
      setError(errText(e, 'The comparison failed'));
    } finally {
      setComparing(false);
    }
  };

  const downloadPdf = async (kind: 'summary' | 'detailed' | 'complete') => {
    if (!comp) return;
    setPdfBusy(kind); setError('');
    try {
      const r = await api.get(`/validator/compare/${comp.id}/pdf`, { params: { kind }, responseType: 'blob', timeout: 300000 });
      const url = window.URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url; a.download = `IODB_Comparison_${kind[0].toUpperCase() + kind.slice(1)}_Report.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      setError('PDF generation failed. Please try again.');
    } finally {
      setPdfBusy('');
    }
  };

  const maxCat = Math.max(1, ...(comp?.category_counts.map((c) => c.count) || [1]));
  const dupCount = comp ? Object.keys(comp.duplicates.iodb1).length + Object.keys(comp.duplicates.iodb2).length : 0;

  return (
    <div className="space-y-6">
      {error && <Alert variant="error" title="Error" onClose={() => setError('')}><span className="whitespace-pre-line">{error}</span></Alert>}

      <Card title="IODB Comparison & Revision Report" icon={GitCompare}
        description="Compare two IODB revisions by TAG NO and see exactly what changed. Your files are only read, never modified.">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <FileUploadCard title="IODB 1 — older / reference revision" icon={FileText} file={file1}
            onChange={(f) => { setFile1(f); setComp(null); }} />
          <FileUploadCard title="IODB 2 — newer / current revision" icon={FileText} file={file2}
            onChange={(f) => { setFile2(f); setComp(null); }} />
        </div>
        <div className="flex items-center gap-4 flex-wrap mt-4">
          <Button onClick={compare} disabled={!file1 || !file2} loading={comparing}>
            {comparing ? 'Comparing…' : 'Compare IODB'}
          </Button>
          <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: 'var(--t1)' }}>
            <input type="checkbox" checked={ignoreCase} onChange={(e) => setIgnoreCase(e.target.checked)} />
            Ignore upper/lower-case differences
          </label>
        </div>
      </Card>

      {comp && (
        <>
          {comp.totally_different && (
            <Alert variant="error" title="IODB datasets are totally different">
              Uploaded IODB 1 and IODB 2 are totally different. No common TAG NOs were found, so these files cannot be treated as
              revisions of the same IODB. IODB 1 has {comp.totals.iodb1} instruments and IODB 2 has {comp.totals.iodb2};
              common instruments: 0.
            </Alert>
          )}

          <Card title="IODB Comparison Summary" accentColor="#34d399"
            actions={
              <div className="flex gap-2 flex-wrap justify-end">
                <Button size="sm" onClick={() => downloadPdf('complete')} loading={pdfBusy === 'complete'}>
                  <Download className="w-4 h-4" />Download Complete Report
                </Button>
                <Button size="sm" variant="secondary" onClick={() => downloadPdf('summary')} loading={pdfBusy === 'summary'}>
                  Summary PDF
                </Button>
                <Button size="sm" variant="secondary" onClick={() => downloadPdf('detailed')} loading={pdfBusy === 'detailed'}>
                  Detailed PDF
                </Button>
              </div>
            }>
            <p className="text-xs mb-4" style={{ color: 'var(--t2)' }}>
              IODB 1: <strong style={{ color: 'var(--t1)' }}>{comp.file1.name}</strong> &nbsp;·&nbsp;
              IODB 2: <strong style={{ color: 'var(--t1)' }}>{comp.file2.name}</strong>
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="Total instruments — IODB 1" value={comp.totals.iodb1} />
              <Stat label="Total instruments — IODB 2" value={comp.totals.iodb2} />
              <Stat label="Common instruments" value={comp.totals.common} />
              <Stat label="Field-level changes" value={comp.totals.field_changes} />
              <Stat label="Added" value={comp.counts.added} color={STATUS_META.added.color} />
              <Stat label="Deleted" value={comp.counts.deleted} color={STATUS_META.deleted.color} />
              <Stat label="Modified" value={comp.counts.modified} color={STATUS_META.modified.color} />
              <Stat label="Unchanged" value={comp.counts.unchanged} color={STATUS_META.unchanged.color} />
            </div>
            {comp.counts.review > 0 && (
              <p className="text-xs mt-3" style={{ color: STATUS_META.review.color }}>
                {comp.counts.review} duplicate TAG NO{comp.counts.review === 1 ? '' : 's'} excluded from the counts above — see “Needs review”.
              </p>
            )}
          </Card>

          <Card title="Engineering Change Summary">
            <p className="text-sm leading-relaxed" style={{ color: 'var(--t1)' }}>{comp.summary_text}</p>
          </Card>

          {!comp.totally_different && (
            <Card title="Change Category Distribution">
              <div className="space-y-2">
                {comp.category_counts.map((c) => (
                  <div key={c.code} className="grid grid-cols-12 items-center gap-3 text-xs">
                    <span className="col-span-5 md:col-span-4" style={{ color: 'var(--t1)' }}>{c.code} – {c.name}</span>
                    <div className="col-span-5 md:col-span-7 h-2 rounded-full" style={{ background: 'var(--s0)' }}>
                      <div className="h-2 rounded-full" style={{ width: `${(c.count / maxCat) * 100}%`, background: '#34d399' }} />
                    </div>
                    <span className="col-span-2 md:col-span-1 text-right font-semibold" style={{ color: 'var(--t0)' }}>{c.count}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {(comp.warnings.length > 0 || dupCount > 0) && (
            <Card title="Validation & Warnings">
              <ul className="space-y-2">
                {comp.warnings.map((w, i) => (
                  <li key={i} className="flex gap-2 text-xs" style={{ color: 'var(--t1)' }}>
                    {w.level === 'warning'
                      ? <AlertTriangle className="w-4 h-4 flex-shrink-0" style={{ color: '#fbbf24' }} />
                      : <Info className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--t2)' }} />}
                    <span className="break-words min-w-0">{w.message}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <RecordsPanel comp={comp} />
        </>
      )}
    </div>
  );
}
