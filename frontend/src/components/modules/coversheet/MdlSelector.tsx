/**
 * MdlSelector - "MASTER DOCUMENT LIST" panel of the Coversheet Generator.
 *
 * Upload the project's MDL, search it (document name / number / discipline) and pick
 * the document the cover sheet is for. The MDL is the authoritative source: the chosen
 * record supplies the document title and document number; this component never lets
 * those be typed when an MDL is active.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { CheckCircle2, FileUp, Loader2, Search, Trash2, XCircle } from 'lucide-react';
import api from '@/services/api';
import { getCurrentProject, subscribeProject } from '@/services/projectContext';
import ProjectSelector from '../../ui/ProjectSelector';
import Alert from '../../ui/Alert';
import Badge from '../../ui/Badge';
import Button from '../../ui/Button';

export interface MdlRecord {
  mdl_record_id: string;
  s_no: string;
  discipline: string;
  document_number: string;
  document_name: string;
  document_category: string;
  remarks: string;
  source_file: string;
  source_sheet: string;
  duplicate_document_number: boolean;
}

export interface MdlSummary {
  uploaded: boolean;
  valid?: boolean;
  file_name?: string;
  sheet?: string;
  revision?: string | null;
  revision_label?: string;
  revision_source?: string | null;
  document_count?: number;
  section_rows_ignored?: number;
  duplicate_doc_numbers?: number;
  warnings?: string[];
  uploaded_at?: string;
  disciplines?: { name: string; count: number }[];
  previous?: { file_name: string; revision_label: string } | null;
}

export interface MdlSelection {
  record: MdlRecord;
  /** Cover sheet fields derived from the record (title + the document-number boxes). */
  fields: Record<string, string>;
  warnings: string[];
}

interface Props {
  selected: MdlSelection | null;
  onSelect: (s: MdlSelection | null) => void;
  onSummary: (s: MdlSummary | null) => void;
  /** Set when an uploaded MDL is invalid: generation must stay blocked until fixed or removed. */
  onInvalid: (message: string | null) => void;
}

const selKey = (projectId: string) => `iez_mdl_selected:${projectId}`;
const errText = (e: any, fallback: string) => {
  const d = e?.response?.data?.detail;
  return typeof d === 'string' ? d : fallback;
};

export default function MdlSelector({ selected, onSelect, onSummary, onInvalid }: Props) {
  const [projectId, setProjectId] = useState(getCurrentProject());
  const [summary, setSummary] = useState<MdlSummary | null>(null);
  const [uploading, setUploading] = useState(false);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: 'success' | 'warning'; text: string } | null>(null);
  const [query, setQuery] = useState('');
  const [discipline, setDiscipline] = useState('');
  const [results, setResults] = useState<{ total: number; items: MdlRecord[] } | null>(null);
  const [searching, setSearching] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const base = `/projects/${encodeURIComponent(projectId)}/coversheet/mdl`;

  useEffect(() => subscribeProject(setProjectId), []);

  const publish = useCallback((s: MdlSummary | null) => { setSummary(s); onSummary(s); }, [onSummary]);

  const choose = useCallback(async (recordId: string) => {
    const r = await api.get(`${base}/document/${encodeURIComponent(recordId)}`);
    const { coversheet, ...record } = r.data;
    try { localStorage.setItem(selKey(projectId), record.mdl_record_id); } catch { /* optional */ }
    onSelect({ record, fields: coversheet.fields, warnings: coversheet.warnings });
    setPickerOpen(false);
  }, [base, onSelect, projectId]);

  const clearSelection = useCallback(() => {
    try { localStorage.removeItem(selKey(projectId)); } catch { /* optional */ }
    onSelect(null);
  }, [onSelect, projectId]);

  // Load the project's MDL status; revalidate the remembered selection against it.
  useEffect(() => {
    setResults(null); setQuery(''); setDiscipline(''); setInvalid(null); onInvalid(null); setNotice(null);
    if (!projectId) { publish(null); onSelect(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get<MdlSummary>(base);
        if (cancelled) return;
        publish(r.data);
        if (!r.data.uploaded) { onSelect(null); return; }
        let remembered = '';
        try { remembered = localStorage.getItem(selKey(projectId)) || ''; } catch { /* optional */ }
        if (remembered) {
          try { await choose(remembered); }
          catch {
            if (!cancelled) {
              clearSelection();
              setNotice({ kind: 'warning', text: 'Previously selected document is not available in this MDL. Select another document.' });
            }
          }
        } else { onSelect(null); }
      } catch (e) {
        if (!cancelled) setNotice({ kind: 'warning', text: errText(e, 'Could not load the MDL status.') });
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Debounced server-side search (the MDL can hold well over a thousand documents).
  useEffect(() => {
    if (!pickerOpen || !summary?.uploaded) return;
    const t = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await api.get(`${base}/search`, { params: { q: query, discipline, limit: 50 } });
        setResults({ total: r.data.total, items: r.data.items });
      } catch { setResults({ total: 0, items: [] }); }
      finally { setSearching(false); }
    }, 250);
    return () => clearTimeout(t);
  }, [query, discipline, pickerOpen, summary?.uploaded, base]);

  const upload = async (file: File) => {
    setUploading(true); setNotice(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      if (selected) fd.append('selected_record_id', selected.record.mdl_record_id);
      const r = await api.post<MdlSummary & { selection: { status: string; message?: string; record?: MdlRecord }; replaced: boolean; unchanged: boolean }>(
        `${base}/upload`, fd);
      setInvalid(null); onInvalid(null);
      publish(r.data);
      setResults(null);
      const sel = r.data.selection;
      if (sel.status === 'preserved' && selected) {
        await choose(selected.record.mdl_record_id);              // refresh the displayed record
        setNotice({ kind: 'success', text: 'MDL replaced. The previously selected document still exists and was kept.' });
      } else if (sel.status === 'missing') {
        clearSelection();
        setNotice({ kind: 'warning', text: sel.message || 'Previously selected document is not available in the newly uploaded MDL.' });
      } else {
        setNotice({ kind: 'success', text: r.data.unchanged ? 'This MDL is already the active one.' : 'MDL uploaded and validated.' });
      }
    } catch (e: any) {
      const msg = errText(e, 'The MDL could not be uploaded.');
      setInvalid(msg); onInvalid(msg);
    } finally { setUploading(false); }
  };

  const removeMdl = async () => {
    try {
      await api.delete(base);
      clearSelection(); publish({ uploaded: false }); setInvalid(null); onInvalid(null);
      setNotice({ kind: 'success', text: 'MDL removed. You can enter the document details manually.' });
    } catch (e) { setNotice({ kind: 'warning', text: errText(e, 'Could not remove the MDL.') }); }
  };

  const card = { background: 'var(--s3)', border: '1px solid var(--b2)' };
  const label = 'text-[10px] font-semibold uppercase tracking-wider';

  return (
    <div className="space-y-3">
      <ProjectSelector compact />
      <input ref={fileRef} type="file" accept=".xlsx,.xlsm" className="hidden"
        onChange={e => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ''; }} />

      {!projectId && (
        <Alert variant="info">
          Select a project to use its Master Document List. Without an MDL you can still enter the
          document title and number manually below.
        </Alert>
      )}

      {invalid && (
        <Alert variant="error" title="MDL not accepted">
          <span style={{ whiteSpace: 'pre-line' }}>{invalid}</span>
          <span className="block text-xs mt-1">Generation stays blocked until a valid MDL is uploaded or the MDL is removed.</span>
        </Alert>
      )}
      {notice && <Alert variant={notice.kind}>{notice.text}</Alert>}

      {projectId && !summary?.uploaded && !invalid && (
        <div className="rounded-xl p-4 flex items-center justify-between gap-3" style={card}>
          <div>
            <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>No MDL uploaded</p>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>
              Upload the project MDL (.xlsx) to pick the document name and number from it.
            </p>
          </div>
          <Button onClick={() => fileRef.current?.click()} loading={uploading}>
            <FileUp className="w-4 h-4" /> Upload MDL
          </Button>
        </div>
      )}

      {projectId && summary?.uploaded && (
        <div className="rounded-xl p-4 space-y-3" style={card}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-sm font-bold flex items-center gap-2" style={{ color: '#4ade80' }}>
                <CheckCircle2 className="w-4 h-4" /> MDL uploaded · Valid MDL
              </p>
              <dl className="mt-2 grid grid-cols-[auto,1fr] gap-x-4 gap-y-0.5 text-xs" style={{ color: 'var(--t1)' }}>
                <dt style={{ color: 'var(--t2)' }}>File</dt><dd className="break-all">{summary.file_name}</dd>
                <dt style={{ color: 'var(--t2)' }}>Sheet</dt><dd>{summary.sheet}</dd>
                <dt style={{ color: 'var(--t2)' }}>Documents detected</dt>
                <dd>{summary.document_count?.toLocaleString()} <span style={{ color: 'var(--t2)' }}>
                  ({summary.section_rows_ignored} heading rows ignored)</span></dd>
                <dt style={{ color: 'var(--t2)' }}>MDL revision</dt>
                <dd>{summary.revision_label}
                  {summary.revision_source && <span style={{ color: 'var(--t2)' }}> (from {summary.revision_source})</span>}</dd>
                {summary.previous && (<><dt style={{ color: 'var(--t2)' }}>Previous MDL</dt>
                  <dd>{summary.previous.revision_label} · {summary.previous.file_name}</dd></>)}
              </dl>
            </div>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => fileRef.current?.click()} loading={uploading}>
                <FileUp className="w-3.5 h-3.5" /> Replace MDL
              </Button>
              <Button size="sm" variant="ghost" onClick={removeMdl}>
                <Trash2 className="w-3.5 h-3.5" /> Remove
              </Button>
            </div>
          </div>
          {(summary.warnings || []).map(w => (
            <p key={w} className="text-xs" style={{ color: 'var(--gold)' }}>⚠ {w}</p>
          ))}
        </div>
      )}

      {projectId && summary?.uploaded && (
        <div className="rounded-xl p-4 space-y-3" style={card}>
          <p className={label} style={{ color: 'var(--t2)' }}>Document name / title</p>
          {!pickerOpen ? (
            <Button variant="secondary" onClick={() => setPickerOpen(true)}>
              <Search className="w-4 h-4" /> {selected ? 'Change document' : 'Select from MDL'}
            </Button>
          ) : (
            <div className="space-y-2">
              <div className="flex flex-wrap gap-2">
                <div className="relative flex-1 min-w-[220px]">
                  <Search className="w-3.5 h-3.5 absolute left-3 top-2.5" style={{ color: 'var(--t2)' }} />
                  <input autoFocus value={query} onChange={e => setQuery(e.target.value)}
                    placeholder="Search document name, number or discipline…"
                    className="w-full pl-9 pr-3 py-2 rounded-xl text-sm outline-none"
                    style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)' }} />
                </div>
                <select value={discipline} onChange={e => setDiscipline(e.target.value)}
                  className="px-3 py-2 rounded-xl text-sm outline-none"
                  style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)' }}>
                  <option value="">All disciplines</option>
                  {(summary.disciplines || []).map(d => <option key={d.name} value={d.name}>{d.name} ({d.count})</option>)}
                </select>
                <Button size="sm" variant="ghost" onClick={() => setPickerOpen(false)}>Close</Button>
              </div>
              <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--b1)' }}>
                <div className="max-h-72 overflow-y-auto">
                  <table className="w-full text-xs">
                    <thead style={{ background: 'var(--s2)', position: 'sticky', top: 0 }}>
                      <tr style={{ color: 'var(--t2)' }}>
                        <th className="text-left px-3 py-2">DOC NO</th><th className="text-left px-3 py-2">DESCRIPTION</th>
                        <th className="text-left px-3 py-2">DISCIPLINE</th><th className="text-left px-3 py-2">CAT.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(results?.items || []).map(rec => {
                        const active = selected?.record.mdl_record_id === rec.mdl_record_id;
                        return (
                          <tr key={rec.mdl_record_id} onClick={() => choose(rec.mdl_record_id).catch(e => setNotice({ kind: 'warning', text: errText(e, 'Could not load the document.') }))}
                            className="cursor-pointer"
                            style={{ borderTop: '1px solid var(--b1)', color: 'var(--t1)', background: active ? 'var(--em-dim)' : undefined }}>
                            <td className="px-3 py-1.5 font-mono whitespace-nowrap">{rec.document_number}
                              {rec.duplicate_document_number && <Badge variant="warning" className="ml-2">duplicate no.</Badge>}</td>
                            <td className="px-3 py-1.5">{rec.document_name}</td>
                            <td className="px-3 py-1.5 whitespace-nowrap">{rec.discipline}</td>
                            <td className="px-3 py-1.5">{rec.document_category}</td>
                          </tr>
                        );
                      })}
                      {results && results.items.length === 0 && (
                        <tr><td colSpan={4} className="px-3 py-4 text-center" style={{ color: 'var(--t2)' }}>No matching documents.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
              <p className="text-[11px] flex items-center gap-2" style={{ color: 'var(--t2)' }}>
                {searching && <Loader2 className="w-3 h-3 animate-spin" />}
                {results ? `Showing ${results.items.length} of ${results.total.toLocaleString()} matching documents` : 'Type to search'}
              </p>
            </div>
          )}

          {selected && (
            <div className="rounded-lg p-3" style={{ background: 'var(--s2)', border: '1px solid rgba(74,222,128,0.25)' }}>
              <p className={label} style={{ color: '#4ade80' }}>Coversheet document details</p>
              <dl className="mt-1.5 grid grid-cols-[auto,1fr] gap-x-4 gap-y-0.5 text-xs" style={{ color: 'var(--t1)' }}>
                <dt style={{ color: 'var(--t2)' }}>Document Name</dt><dd className="font-semibold">{selected.record.document_name}</dd>
                <dt style={{ color: 'var(--t2)' }}>Document Number</dt><dd className="font-mono font-semibold">{selected.record.document_number}</dd>
                <dt style={{ color: 'var(--t2)' }}>Discipline</dt><dd>{selected.record.discipline || '—'}</dd>
                <dt style={{ color: 'var(--t2)' }}>Source</dt><dd>MDL · {selected.record.source_file}</dd>
              </dl>
              {selected.warnings.map(w => <p key={w} className="text-xs mt-1" style={{ color: 'var(--gold)' }}>⚠ {w}</p>)}
              <button className="text-[11px] mt-2 underline" style={{ color: 'var(--t2)' }} onClick={clearSelection}>
                <XCircle className="w-3 h-3 inline mr-1" />Clear selection
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
