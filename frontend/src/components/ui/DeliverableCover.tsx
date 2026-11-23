/**
 * Centralised cover sheet + Excel / PDF downloads, shared by the Instrument List, I/O List, Cable Schedule, Loop Wiring
 * and Datasheet generators. The cover sheet comes from the Cover Sheet Generator (project MDL + details entered once);
 * the generator only shows it, lets the engineer pick the MDL document when iEZ is not sure, and offers an optional
 * custom cover template. Backend: /api/deliverables/*.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, Clock, Download, FileText, Layers, RefreshCw } from 'lucide-react';
import api from '@/services/api';
import { getCurrentProject, subscribeProject } from '@/services/projectContext';
import Card from './Card';
import Button from './Button';

export type DeliverableType = 'instrument_list' | 'io_list' | 'cable_schedule' | 'loop_wiring' | 'datasheet' | 'gland_quantity' | 'lug_quantity';

interface MdlItem { mdl_record_id: string; document_number: string; document_name: string; full_match?: boolean }
export interface CoverResolution {
  doc_type: string; doc_label: string; project_id: string | null; status: 'AVAILABLE' | 'APPROVAL_REQUIRED' | 'NOT_AVAILABLE';
  record: MdlItem | null; match: 'keyword' | 'selected' | null; candidates: MdlItem[]; revision: string | null;
  approved: boolean; approval: { id: number; status: string; reviewed_by?: string; current: boolean } | null; message: string;
}
/** What the generator response carries after generation (backend finalize()). */
export interface AppliedCover {
  applied: boolean; draft?: boolean; status?: string; message?: string; document_number?: string; document_title?: string;
  revision?: string | null; cover_sheet?: string; custom_template?: boolean; warnings?: string[];
}

export function useProject(): string {
  const [p, setP] = useState(getCurrentProject());
  useEffect(() => subscribeProject(setP), []);
  return p;
}

const STATUS: Record<CoverResolution['status'], { label: string; color: string; Icon: any }> = {
  AVAILABLE: { label: 'Available', color: 'text-green-600', Icon: CheckCircle2 },
  APPROVAL_REQUIRED: { label: 'Approval Required', color: 'text-amber-600', Icon: Clock },
  NOT_AVAILABLE: { label: 'Not Available', color: 'text-red-500', Icon: AlertTriangle },
};

/** Read-only cover sheet source for a generator (no upload needed). */
export function DeliverableCoverCard({ docType, subKey = '', subLabel = '', customTemplate, onCustomTemplate }: {
  docType: DeliverableType; subKey?: string; subLabel?: string;
  customTemplate?: File | null; onCustomTemplate?: (f: File | null) => void;
}) {
  const project = useProject();
  const [r, setR] = useState<CoverResolution | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [pick, setPick] = useState('');
  const [useCustom, setUseCustom] = useState(false);
  const seq = useRef(0);

  const load = useCallback(() => {
    const n = ++seq.current;
    setLoading(true);
    api.get<CoverResolution>('/deliverables/cover', { params: { doc_type: docType, project_id: project, sub_key: subKey, sub_label: subLabel } })
      .then((x) => { if (n === seq.current) { setR(x.data); setErr(''); } })
      .catch((e) => { if (n === seq.current) setErr(e.response?.data?.detail || 'Could not check the cover sheet.'); })
      .finally(() => { if (n === seq.current) setLoading(false); });
  }, [docType, project, subKey, subLabel]);
  useEffect(() => { load(); }, [load]);

  const choose = async () => {
    if (!pick || !project) return;
    try {
      await api.put('/deliverables/cover', { project_id: project, doc_type: docType, sub_key: subKey, mdl_record_id: pick });
      setPick(''); load();
    } catch (e: any) { setErr(e.response?.data?.detail || 'Could not save the document choice.'); }
  };

  const st = r ? STATUS[r.status] : null;
  const row = (k: string, v: React.ReactNode) => (
    <div className="flex gap-2 text-sm"><span className="w-44 flex-shrink-0" style={{ color: 'var(--t1)' }}>{k}</span><span style={{ color: 'var(--t0)' }}>{v}</span></div>);
  const editLink = `/cover-sheet?deliverable=${docType}${subKey ? `&sub_key=${encodeURIComponent(subKey)}&sub_label=${encodeURIComponent(subLabel)}` : ''}`;

  return (
    <Card title="Cover Sheet" icon={Layers}
          actions={<button onClick={load} className="text-xs flex items-center gap-1 underline" style={{ color: 'var(--t1)' }}>
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />Refresh</button>}>
      <div className="space-y-1.5" data-testid={`cover-${docType}`}>
        {row('Cover Sheet Source', 'iEZ Cover Sheet Generator')}
        {row('Project', project || <span className="text-red-500">No project selected</span>)}
        {row('Document', r?.record ? <span><span className="font-mono">{r.record.document_number}</span> - {r.record.document_name}
          {r.match === 'keyword' && <span className="text-xs ml-1" style={{ color: 'var(--t2)' }}>(matched in the MDL)</span>}</span> : '-')}
        {row('Cover Sheet Status', st ? <span className={`font-semibold flex items-center gap-1 ${st.color}`}><st.Icon className="w-4 h-4" />{st.label}</span> : (loading ? 'Checking…' : '-'))}
        {row('Document Revision', r?.revision || '-')}
        {(err || (r && r.status !== 'AVAILABLE' && r.message)) && (
          <p className={`text-sm pt-1 ${r?.status === 'APPROVAL_REQUIRED' && !err ? 'text-amber-600' : 'text-red-500'}`}>{err || r!.message}</p>)}
        {r && !r.record && r.candidates.length > 0 && project && (
          <div className="flex flex-wrap gap-2 items-center pt-1">
            <select value={pick} onChange={(e) => setPick(e.target.value)} className="border rounded-lg px-2 py-1.5 text-sm max-w-full"
                    style={{ borderColor: 'var(--b1)', background: 'var(--s1)', color: 'var(--t0)' }} aria-label="MDL document">
              <option value="">Choose the MDL document…</option>
              {r.candidates.map((c) => <option key={c.mdl_record_id} value={c.mdl_record_id}>{c.document_number} - {c.document_name}</option>)}
            </select>
            <Button onClick={choose} disabled={!pick} className="bg-blue-600 hover:bg-blue-700">Use this document</Button>
          </div>)}
        <p className="text-xs pt-1"><a href={editLink} className="underline" style={{ color: 'var(--t1)' }}>
          {r?.status === 'NOT_AVAILABLE' ? 'Complete the cover sheet in the Cover Sheet Generator' : 'Open in the Cover Sheet Generator'}</a>
          {r?.status === 'APPROVAL_REQUIRED' && <span style={{ color: 'var(--t2)' }}> · the document is generated as a DRAFT until a Lead Engineer approves the cover sheet</span>}</p>
        {onCustomTemplate && (
          <div className="pt-2 text-sm" style={{ color: 'var(--t0)' }}>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={useCustom} onChange={(e) => { setUseCustom(e.target.checked); if (!e.target.checked) onCustomTemplate(null); }} />
              Use Custom Cover Sheet Template <span className="text-xs" style={{ color: 'var(--t2)' }}>(optional - filled with the same MDL and cover details)</span>
            </label>
            {useCustom && (
              <input type="file" accept=".xlsx,.xlsm" className="mt-1 text-xs" aria-label="Custom cover sheet template"
                     onChange={(e) => onCustomTemplate(e.target.files?.[0] || null)} />)}
            {useCustom && customTemplate && <p className="text-xs mt-1" style={{ color: 'var(--t1)' }}><FileText className="inline w-3 h-3" /> {customTemplate.name}</p>}
          </div>)}
      </div>
    </Card>
  );
}

/** What the generated document got, and the Excel / PDF downloads of the same deliverable. */
export function DeliverableDownloads({ module, filename, cover, onExcel }: {
  module: DeliverableType; filename: string; cover?: AppliedCover | null; onExcel: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const pdf = async () => {
    setBusy(true); setErr('');
    try {
      // the conversion runs on the server in the background (a large schedule takes minutes): start, poll, download
      let st = (await api.post(`/deliverables/${module}/pdf`)).data;
      const t0 = Date.now();
      while (st.status === 'running' && Date.now() - t0 < 15 * 60000) {
        await new Promise((res) => setTimeout(res, 3000));
        st = (await api.get(`/deliverables/${module}/pdf/status`)).data;
      }
      if (st.status !== 'done') throw { message: st.error || 'The PDF took too long to prepare.', plain: true };
      const r = await api.get(`/deliverables/${module}/pdf`, { responseType: 'blob' });
      const cd = String(r.headers['content-disposition'] || '');
      const name = /filename="?([^";]+)"?/.exec(cd)?.[1] || filename.replace(/\.(xlsx|zip)$/i, '.pdf');
      const a = document.createElement('a');
      a.href = window.URL.createObjectURL(new Blob([r.data]));
      a.setAttribute('download', name);
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e: any) {
      let msg = e?.plain ? e.message : e?.response?.data?.detail || 'Excel generation completed successfully, but PDF conversion failed.';
      try { const t = await (e.response?.data as Blob)?.text?.(); if (t) msg = JSON.parse(t).detail || msg; } catch { /* keep default */ }
      setErr(msg);
    } finally { setBusy(false); }
  };
  return (
    <div className="space-y-2" data-testid={`downloads-${module}`}>
      {cover && (cover.applied
        ? <p className={`text-sm ${cover.draft ? 'text-amber-700' : 'text-green-700'}`}>
            Cover sheet: {cover.document_number} · Rev {cover.revision}{cover.custom_template ? ' · custom template' : ''}
            {cover.draft ? ' · DRAFT (cover sheet not yet approved - not for client submission)' : ' · approved'}</p>
        : <p className="text-sm text-amber-700">No cover sheet added: {cover.message}</p>)}
      <div className="flex flex-wrap gap-2">
        <Button onClick={onExcel} className="bg-green-600 hover:bg-green-700"><Download className="w-5 h-5" />Download Excel (.xlsx)</Button>
        <Button onClick={pdf} loading={busy} className="bg-red-600 hover:bg-red-700"><Download className="w-5 h-5" />{busy ? 'Preparing PDF…' : 'Download PDF (.pdf)'}</Button>
      </div>
      {err && <p className="text-sm text-red-500">{err}</p>}
    </div>
  );
}
