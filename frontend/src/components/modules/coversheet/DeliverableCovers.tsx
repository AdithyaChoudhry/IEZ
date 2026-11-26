/**
 * Cover Sheet Generator - "Engineering Deliverable Covers": the cover sheet details of the Instrument List, I/O List,
 * Cable Schedule, Loop Wiring and Datasheet documents, entered ONCE per document and reused by those generators.
 * The MDL decides the document number and title (matched by keyword, or picked here); revisions and signatories are
 * entered here and used as entered. There is no approval step: saved details are available to the generators at once.
 */
import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Plus, Save, Search, Trash2 } from 'lucide-react';
import api from '@/services/api';
import Card from '../../ui/Card';
import Button from '../../ui/Button';
import Alert from '../../ui/Alert';
import { DeliverableCoverCard, useProject, type DeliverableType } from '../../ui/DeliverableCover';

const TYPES: [DeliverableType, string][] = [['instrument_list', 'Instrument List'], ['io_list', 'I/O List'], ['cable_schedule', 'Cable Schedule'],
  ['loop_wiring', 'Loop Wiring'], ['datasheet', 'Datasheet (per instrument type)']];
const INFO_FIELDS: [string, string][] = [['project_description', 'Project description'], ['client', 'Client'], ['pmc', 'PMC'],
  ['contractor', 'Contractor'], ['unit_no', 'Unit No.'], ['discipline', 'Discipline'], ['doc_class', 'Document class'], ['page_no', 'Page No.']];
const REV_FIELDS: [string, string][] = [['rev_no', 'Rev'], ['date', 'Date'], ['description', 'Description'], ['prepared_by', 'Prepared by'],
  ['checked_by', 'Checked by'], ['approved_by', 'Approved by']];
type Rev = Record<string, string>;
const emptyRev = (): Rev => ({ rev_no: '', date: new Date().toLocaleDateString('en-CA'), description: 'ISSUED FOR REVIEW', prepared_by: '', checked_by: '', approved_by: '' });
const field = 'w-full border rounded-lg px-2 py-1.5 text-sm';
const fs = { borderColor: 'var(--b1)', background: 'var(--s1)', color: 'var(--t0)' };

export default function DeliverableCovers() {
  const project = useProject();
  const q = new URLSearchParams(window.location.search);
  const [docType, setDocType] = useState<DeliverableType>((q.get('deliverable') as DeliverableType) || 'instrument_list');
  const [library, setLibrary] = useState<{ id: string; display_name: string }[]>([]);
  const [subKey, setSubKey] = useState(q.get('sub_key') || '');
  const [info, setInfo] = useState<Record<string, string>>({});
  const [revs, setRevs] = useState<Rev[]>([emptyRev()]);
  const [search, setSearch] = useState('');
  const [found, setFound] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);
  const [reload, setReload] = useState(0);
  const subLabel = useMemo(() => (docType === 'datasheet' ? library.find((t) => t.id === subKey)?.display_name || q.get('sub_label') || subKey : ''),
    [docType, subKey, library]); // eslint-disable-line react-hooks/exhaustive-deps
  const key = docType === 'datasheet' ? subKey : '';

  useEffect(() => {
    if (docType === 'datasheet' && !library.length)
      api.get('/sop-datasheet/library').then((r) => setLibrary((r.data.templates || []).map((t: any) => ({ id: t.id, display_name: t.display_name })))).catch(() => {});
  }, [docType]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {                                         // the entered details of this document
    setMsg(null); setFound([]);
    if (!project || (docType === 'datasheet' && !subKey)) { setInfo({}); setRevs([emptyRev()]); return; }
    api.get('/deliverables/cover/details', { params: { project_id: project, doc_type: docType, sub_key: key } })
      .then((r) => { setInfo(r.data.project_info || {}); setRevs(r.data.revisions?.length ? r.data.revisions : [emptyRev()]); })
      .catch(() => {});
  }, [project, docType, subKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async (extra: Record<string, any> = {}) => {
    setBusy(true); setMsg(null);
    try {
      await api.put('/deliverables/cover', { project_id: project, doc_type: docType, sub_key: key, project_info: info, revisions: revs, ...extra });
      setMsg({ kind: 'success', text: 'Cover sheet details saved. Every generator of this document now uses them.' });
      setReload((n) => n + 1);
    } catch (e: any) { setMsg({ kind: 'error', text: e.response?.data?.detail || 'Could not save.' }); }
    finally { setBusy(false); }
  };
  const findDocs = async () => {
    try { setFound((await api.get('/deliverables/cover/mdl', { params: { project_id: project, q: search } })).data.items || []); }
    catch (e: any) { setMsg({ kind: 'error', text: e.response?.data?.detail || 'MDL search failed.' }); }
  };
  const choose = async (id: string) => {
    try {
      await api.put('/deliverables/cover', { project_id: project, doc_type: docType, sub_key: key, mdl_record_id: id });
      setFound([]); setReload((n) => n + 1);
    } catch (e: any) { setMsg({ kind: 'error', text: e.response?.data?.detail || 'Could not use that document.' }); }
  };
  const setRev = (i: number, k: string, v: string) => setRevs(revs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  if (!project) return <Alert variant="warning" title="No project selected">Select a project (top of the Instrument List, I/O List or Cable Schedule page) to enter its deliverable cover sheets.</Alert>;

  return (
    <div className="space-y-5" data-testid="deliverable-covers">
      <Card title="Engineering deliverable" description="One cover sheet per document, entered once - the Instrument List, I/O List, Cable Schedule, Loop Wiring and Datasheet generators reuse it automatically.">
        <div className="flex flex-wrap gap-2">
          {TYPES.map(([k, label]) => (
            <button key={k} onClick={() => { setDocType(k); if (k !== 'datasheet') setSubKey(''); }} className="px-3 py-1.5 rounded-lg text-sm font-semibold"
                    style={{ background: docType === k ? 'var(--em)' : 'var(--s3)', color: docType === k ? '#fff' : 'var(--t0)', border: '1px solid var(--b1)' }}>{label}</button>))}
        </div>
        {docType === 'datasheet' && (
          <select value={subKey} onChange={(e) => setSubKey(e.target.value)} className={`${field} mt-3 max-w-md`} style={fs} aria-label="Instrument type">
            <option value="">Choose the instrument type (datasheet template)…</option>
            {library.map((t) => <option key={t.id} value={t.id}>{t.display_name}</option>)}
          </select>)}
      </Card>

      {(docType !== 'datasheet' || subKey) && <>
        <DeliverableCoverCard key={`${docType}-${subKey}-${reload}`} docType={docType} subKey={key} subLabel={subLabel} />

        <Card title="Document in the MDL" description="iEZ matches the document by its title. Search the MDL to choose another one.">
          <div className="flex gap-2">
            <input className={field} style={fs} placeholder="Search document name or number…" value={search} onChange={(e) => setSearch(e.target.value)}
                   onKeyDown={(e) => { if (e.key === 'Enter') findDocs(); }} />
            <Button onClick={findDocs} className="bg-blue-600 hover:bg-blue-700"><Search className="w-4 h-4" />Search</Button>
          </div>
          {found.length > 0 && (
            <ul className="mt-3 max-h-60 overflow-auto text-sm border rounded-lg" style={{ borderColor: 'var(--b1)' }}>
              {found.map((d) => (
                <li key={d.mdl_record_id} className="flex justify-between gap-3 px-3 py-1.5 border-t first:border-t-0" style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }}>
                  <span><span className="font-mono">{d.document_number}</span> - {d.document_name}</span>
                  <button className="underline text-xs flex-shrink-0" onClick={() => choose(d.mdl_record_id)}>Use</button>
                </li>))}
            </ul>)}
        </Card>

        <Card title="Cover sheet details" description="Document number and title come from the MDL. Prepared / Checked / Approved by are printed exactly as you enter them; a saved cover sheet is available to the generators immediately.">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {INFO_FIELDS.map(([k, label]) => (
              <label key={k} className="text-sm" style={{ color: 'var(--t0)' }}><span className="block mb-1">{label}</span>
                <input className={field} style={fs} value={info[k] || ''} onChange={(e) => setInfo({ ...info, [k]: e.target.value })} /></label>))}
          </div>
          <p className="text-sm font-semibold mt-5 mb-1" style={{ color: 'var(--t0)' }}>Revisions (oldest first)</p>
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead><tr>{REV_FIELDS.map(([, h]) => <th key={h} className="text-left px-1 py-1" style={{ color: 'var(--t1)' }}>{h}</th>)}<th /></tr></thead>
              <tbody>{revs.map((r, i) => (
                <tr key={i}>{REV_FIELDS.map(([k]) => (
                  <td key={k} className="px-1 py-1"><input className={field} style={fs} value={r[k] || ''} onChange={(e) => setRev(i, k, e.target.value)} aria-label={`${k} ${i + 1}`} /></td>))}
                  <td><button onClick={() => setRevs(revs.filter((_, j) => j !== i))} disabled={revs.length === 1} aria-label="Remove revision"><Trash2 className="w-4 h-4" style={{ color: 'var(--t2)' }} /></button></td>
                </tr>))}</tbody>
            </table>
          </div>
          <button onClick={() => setRevs([...revs, emptyRev()])} className="text-xs underline mt-2 flex items-center gap-1" style={{ color: 'var(--t1)' }}><Plus className="w-3.5 h-3.5" />Add revision</button>
          {msg && <div className="mt-3"><Alert variant={msg.kind} title={msg.kind === 'success' ? 'Done' : 'Error'} onClose={() => setMsg(null)}>{msg.text}</Alert></div>}
          <div className="flex flex-wrap gap-2 mt-4">
            <Button onClick={() => save()} loading={busy} disabled={revs.some((r) => !r.rev_no.trim())}><Save className="w-4 h-4" />Save cover sheet details</Button>
          </div>
          <p className="text-xs mt-2 flex items-center gap-1" style={{ color: 'var(--t2)' }}><CheckCircle2 className="w-3.5 h-3.5" />Saved details are used by every generator of this document straight away.</p>
        </Card>
      </>}
    </div>
  );
}
