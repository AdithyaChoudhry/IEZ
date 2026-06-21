/**
 * Cover Sheet Generator — fully customizable canvas-first editor.
 * Features:
 *  • Click any cell to type its value / change formatting
 *  • Shift+click to select a range → Merge / Unmerge
 *  • Unlimited custom images draggable anywhere on canvas
 *  • Upload your own template OR start with a blank canvas
 *  • Admin Employee ID + Password required before Generate
 */
import { useState, useEffect, useRef } from 'react';
import {
  FileSpreadsheet, Upload, Download, Plus, Trash2, Save,
  Eye, ImagePlus, ChevronDown, ChevronRight, FileUp, X, CheckCircle2,
  Lock, LayoutGrid, AlertTriangle, Loader2, FileUp as FileUpIcon, Send,
} from 'lucide-react';
import api from '@/services/api';
import CoverSheetPreview, { colLetter } from './coversheet/CoverSheetPreview';
import type {
  CoverSheetLayout, ImageKey, ImagePlacement, CellOverride,
  CustomImageSlot, MergeRange, LayoutCell, CellStyle,
} from './coversheet/types';
import PageHeader from '../ui/PageHeader';
import Button from '../ui/Button';
import Alert from '../ui/Alert';

// ── Types ─────────────────────────────────────────────────────────────────────
interface ProjectInfo {
  client: string; pmc: string; contractor: string; project_description: string;
  doc_title_short: string; doc_title_full: string;
  job_no: string; unit_no: string; project_no: string; doc_code: string;
  serial_no: string; page_no: string; doc_class: string; discipline: string;
}
interface RevisionEntry {
  rev_no: string; date: string; description: string;
  prepared_by: string; checked_by: string; approved_by: string;
}
interface PlacementState { x: number; y: number; width: number; height: number; }
interface AuthInfo { employee_name: string; role: string; employee_id: string; }

const MASTER_KEY = 'iez_coversheet_project_master';
const MAX_REVISIONS = 7;
const DOC_CLASSES = ['APPROVAL', 'IFC', 'IFA', 'INFORMATION', 'INTERNAL', 'CONSTRUCTION'];

const PAPER_SIZES = [
  { label: 'A4  (210 × 297 mm)', value: '9' },
  { label: 'A3  (297 × 420 mm)', value: '8' },
  { label: 'A5  (148 × 210 mm)', value: '11' },
  { label: 'Letter  (8.5 × 11 in)', value: '1' },
  { label: 'Legal  (8.5 × 14 in)', value: '5' },
  { label: 'Tabloid  (11 × 17 in)', value: '3' },
];

const FIXED_IMAGE_FIELDS: { key: ImageKey; label: string }[] = [
  { key: 'client_logo', label: 'Client Logo' },
  { key: 'pmc_logo', label: 'PMC Logo' },
  { key: 'wabag_logo', label: 'WABAG / Contractor Logo' },
  { key: 'prepared_signature', label: 'Prepared By Signature' },
  { key: 'checked_signature', label: 'Checked By Signature' },
  { key: 'approved_signature', label: 'Approved By Signature' },
];

const emptyProjectInfo = (): ProjectInfo => ({
  client: '', pmc: '', contractor: '', project_description: '',
  doc_title_short: '', doc_title_full: '',
  job_no: '', unit_no: '', project_no: '', doc_code: '',
  serial_no: '', page_no: '', doc_class: 'APPROVAL', discipline: 'INSTRUMENTATION',
});

const emptyRevision = (): RevisionEntry => ({
  rev_no: '', date: '', description: 'ISSUED FOR APPROVAL',
  prepared_by: '', checked_by: '', approved_by: '',
});

// Default style for blank canvas cells
const BLANK_STYLE: CellStyle = {
  font: { name: 'Calibri', size: 11, bold: false, italic: false, underline: false, color: '#000000' },
  alignment: { horizontal: 'left', vertical: 'bottom', wrapText: false, shrinkToFit: false },
  fill: null,
  border: {
    top: { style: 'thin', color: '#d0d0d0' },
    right: { style: 'thin', color: '#d0d0d0' },
    bottom: { style: 'thin', color: '#d0d0d0' },
    left: { style: 'thin', color: '#d0d0d0' },
  },
};

function createBlankLayout(rows = 30, cols = 20): CoverSheetLayout {
  const colW = 64; const rowH = 20;
  const cells: LayoutCell[] = [];
  for (let r = 1; r <= rows; r++) {
    for (let c = 1; c <= cols; c++) {
      cells.push({ row: r, col: c, coord: `${colLetter(c)}${r}`, value: '', rowspan: 1, colspan: 1, style: BLANK_STYLE });
    }
  }
  return { cols: Array(cols).fill(colW), rows: Array(rowH).fill(rowH), width: cols * colW, height: rows * rowH, cells };
}

// ── Input helpers ──────────────────────────────────────────────────────────────
const ic = 'w-full px-3 py-2 rounded-xl text-sm outline-none';
const icSt = { background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)' };
const lc = 'block text-[10px] font-semibold uppercase tracking-wider mb-1';
const lcSt = { color: 'var(--t2)' };

// ── Collapsible section ────────────────────────────────────────────────────────
function Section({ title, subtitle, defaultOpen = true, badge, children }: {
  title: string; subtitle?: string; defaultOpen?: boolean; badge?: string; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
      <button className="w-full flex items-center gap-3 px-5 py-4 text-left" onClick={() => setOpen(o => !o)}>
        {open ? <ChevronDown className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--t2)' }} />
               : <ChevronRight className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--t2)' }} />}
        <div className="flex-1">
          <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>{title}</p>
          {subtitle && <p className="text-xs mt-0.5" style={{ color: 'var(--t2)' }}>{subtitle}</p>}
        </div>
        {badge && <span className="text-[10px] px-2 py-0.5 rounded-full font-bold"
          style={{ background: 'var(--em-dim)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.2)' }}>{badge}</span>}
      </button>
      {open && <div className="px-5 pb-5">{children}</div>}
    </div>
  );
}

// ── Image drop zone ────────────────────────────────────────────────────────────
function ImgZone({ file, onChange, label }: { file: File | null; onChange: (f: File | null) => void; label: string }) {
  return (
    <label className="flex items-center gap-2 rounded-xl cursor-pointer px-3 py-2 transition-all"
      style={{ background: file ? 'rgba(74,222,128,0.06)' : 'var(--s3)', border: `1.5px dashed ${file ? '#4ade80' : 'var(--b2)'}` }}>
      {file
        ? <><CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#4ade80' }} />
            <span className="text-xs truncate flex-1" style={{ color: '#4ade80' }}>{file.name}</span>
            <button onClick={e => { e.preventDefault(); onChange(null); }} style={{ color: 'var(--t2)' }}>
              <X className="w-3 h-3" /></button></>
        : <><Upload className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--t2)' }} />
            <span className="text-xs" style={{ color: 'var(--t2)' }}>{label}</span></>}
      <input type="file" accept="image/*" className="hidden"
        onChange={e => onChange(e.target.files?.[0] || null)} />
    </label>
  );
}

// ── Admin Verify Modal ─────────────────────────────────────────────────────────
function AdminVerifyModal({ onSuccess, onClose }: {
  onSuccess: (info: AuthInfo) => void;
  onClose: () => void;
}) {
  const [empId, setEmpId] = useState('');
  const [pass, setPass] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(''); setBusy(true);
    try {
      const res = await api.post('/admin/verify', { employee_id: empId, password: pass });
      onSuccess({ ...res.data, employee_id: empId });
    } catch (ex: any) {
      setErr(ex?.response?.data?.detail || 'Invalid Employee ID or Password');
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-2xl overflow-hidden"
        style={{ background: 'var(--s1)', border: '1px solid var(--b2)' }}>
        <div className="px-6 py-5 flex items-center gap-3" style={{ borderBottom: '1px solid var(--b1)' }}>
          <div className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', boxShadow: '0 0 16px rgba(59,130,246,0.3)' }}>
            <Lock className="w-4 h-4 text-white" />
          </div>
          <div className="flex-1">
            <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Authorization Required</p>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>Enter Admin credentials to generate the cover sheet</p>
          </div>
          <button onClick={onClose} className="opacity-40 hover:opacity-80" style={{ color: 'var(--t1)' }}>
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={submit} className="p-6 space-y-4">
          {err && (
            <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs"
              style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
              <AlertTriangle className="w-3.5 h-3.5" /> {err}
            </div>
          )}
          <div>
            <label className={lc} style={lcSt}>Employee ID</label>
            <input type="text" required value={empId} onChange={e => setEmpId(e.target.value)}
              placeholder="e.g. WABAG-EMP-001" className={ic} style={icSt} />
          </div>
          <div>
            <label className={lc} style={lcSt}>Password</label>
            <input type="password" required value={pass} onChange={e => setPass(e.target.value)}
              placeholder="••••••••" className={ic} style={icSt} />
          </div>
          <button type="submit" disabled={busy || !empId || !pass}
            className="w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
            style={{ background: 'linear-gradient(135deg,var(--em),#1d4ed8)', color: '#fff', opacity: busy || !empId || !pass ? 0.5 : 1, cursor: 'pointer' }}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />}
            {busy ? 'Verifying…' : 'Verify & Generate'}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Cover Sheet Raise Request Modal ───────────────────────────────────────────
function CSRaiseRequestModal({
  projectTitle, projectInfo, onSuccess, onClose,
}: {
  projectTitle: string;
  projectInfo: ProjectInfo;
  onSuccess: (reqId: number) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState('');
  const [empId, setEmpId] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(''); setBusy(true);
    try {
      const res = await api.post('/approvals', {
        request_type: 'coversheet',
        submitted_by_name: name,
        submitted_by_id: empId,
        submitter_notes: notes || null,
        payload: {
          doc_title: projectTitle,
          client: projectInfo.client,
          pmc: projectInfo.pmc,
          contractor: projectInfo.contractor,
          doc_class: projectInfo.doc_class,
          discipline: projectInfo.discipline,
          job_no: projectInfo.job_no,
          doc_code: projectInfo.doc_code,
          serial_no: projectInfo.serial_no,
        },
      });
      onSuccess(res.data.id);
      onClose();
    } catch (ex: any) { setErr(ex?.response?.data?.detail || 'Failed to submit'); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-2xl overflow-hidden"
        style={{ background: 'var(--s1)', border: '1px solid var(--b2)' }}>
        <div className="px-6 py-5 flex items-center gap-3" style={{ borderBottom: '1px solid var(--b1)' }}>
          <div className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.3)' }}>
            <Send className="w-4 h-4" style={{ color: 'var(--gold)' }} />
          </div>
          <div className="flex-1">
            <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Request Cover Sheet Approval</p>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>{projectTitle} · Lead Engineer will review before generation is enabled</p>
          </div>
          <button onClick={onClose} className="opacity-40 hover:opacity-80" style={{ color: 'var(--t1)' }}>
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={submit} className="p-6 space-y-4">
          {err && (
            <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs"
              style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
              <AlertTriangle className="w-3.5 h-3.5" /> {err}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Your Name *</label>
              <input type="text" required value={name} onChange={e => setName(e.target.value)}
                placeholder="Full name" className="w-full px-3 py-2.5 rounded-xl text-sm"
                style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Employee ID *</label>
              <input type="text" required value={empId} onChange={e => setEmpId(e.target.value)}
                placeholder="WABAG-EMP-001" className="w-full px-3 py-2.5 rounded-xl text-sm"
                style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Notes for Lead Engineer</label>
            <textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)}
              placeholder="Any context or clarifications…"
              className="w-full resize-none px-3 py-2.5 rounded-xl text-sm"
              style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
          </div>
          <button type="submit" disabled={busy || !name || !empId}
            className="w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
            style={{ background: 'linear-gradient(135deg,var(--gold),#d97706)', color: '#000', opacity: busy || !name || !empId ? 0.5 : 1, cursor: 'pointer' }}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            {busy ? 'Submitting…' : 'Send to Approval Queue'}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────
export default function CoverSheetGenerator() {
  const [projectInfo, setProjectInfo] = useState<ProjectInfo>(emptyProjectInfo);
  const [revisions, setRevisions] = useState<RevisionEntry[]>([emptyRevision()]);
  const setPI = (k: keyof ProjectInfo, v: string) => setProjectInfo(p => ({ ...p, [k]: v }));
  const setRev = (i: number, k: keyof RevisionEntry, v: string) =>
    setRevisions(p => p.map((r, idx) => idx === i ? { ...r, [k]: v } : r));

  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [isBlank, setIsBlank] = useState(false);
  const [fixedImages, setFixedImages] = useState<Partial<Record<ImageKey, File>>>({});

  const [customImages, setCustomImages] = useState<CustomImageSlot[]>([]);
  const [addingImg, setAddingImg] = useState(false);
  const [pendingLabel, setPendingLabel] = useState('');
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  const [previewLayout, setPreviewLayout] = useState<CoverSheetLayout | null>(null);
  const [previewImages, setPreviewImages] = useState<Partial<Record<ImageKey, ImagePlacement>>>({});
  const [cellOverrides, setCellOverrides] = useState<Record<string, CellOverride>>({});
  const [imagePlacements, setImagePlacements] = useState<Partial<Record<ImageKey, PlacementState>>>({});
  const [mergeRanges, setMergeRanges] = useState<MergeRange[]>([]);
  const [unmergeCoords, setUnmergeCoords] = useState<string[]>([]);
  const [colOverrides, setColOverrides] = useState<Record<number, number>>({});
  const [rowOverrides, setRowOverrides] = useState<Record<number, number>>({});
  const [paperSize, setPaperSize] = useState('9'); // A4 default
  const [orientation, setOrientation] = useState<'portrait' | 'landscape'>('portrait');
  const mdlInputRef = useRef<HTMLInputElement>(null);
  const [mdlFile, setMdlFile] = useState<File | null>(null);

  const [masterSaved, setMasterSaved] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [authInfo, setAuthInfo] = useState<AuthInfo | null>(null);
  const [result, setResult] = useState<{ filename: string; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Cover sheet raise-request flow
  const [showCSRaiseModal, setShowCSRaiseModal] = useState(false);
  const [csPendingReqId, setCSPendingReqId] = useState<number | null>(null);
  const [csReqStatus, setCSReqStatus] = useState<'idle' | 'pending' | 'approved' | 'rejected'>('idle');
  const csPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load project master
  useEffect(() => {
    const raw = localStorage.getItem(MASTER_KEY);
    if (!raw) return;
    try {
      const m = JSON.parse(raw);
      setProjectInfo(p => ({ ...p, client: m.client || p.client, pmc: m.pmc || p.pmc, contractor: m.contractor || p.contractor }));
      setRevisions(prev => prev.map(r => ({
        ...r,
        prepared_by: r.prepared_by || m.prepared_by || '',
        checked_by: r.checked_by || m.checked_by || '',
        approved_by: r.approved_by || m.approved_by || '',
      })));
    } catch { /* ignore */ }
  }, []);

  const saveMaster = () => {
    const last = revisions[revisions.length - 1];
    localStorage.setItem(MASTER_KEY, JSON.stringify({
      client: projectInfo.client, pmc: projectInfo.pmc, contractor: projectInfo.contractor,
      prepared_by: last?.prepared_by || '', checked_by: last?.checked_by || '', approved_by: last?.approved_by || '',
    }));
    setMasterSaved(true); setTimeout(() => setMasterSaved(false), 2000);
  };

  // ── Image helpers ──────────────────────────────────────────────────────────
  const confirmAddCustom = () => {
    if (!pendingFile) return;
    const reader = new FileReader();
    reader.onload = ev => {
      const dataUrl = ev.target?.result as string;
      const id = `custom_${Date.now()}_${Math.random().toString(36).slice(2)}`;
      setCustomImages(p => [...p, { id, label: pendingLabel || pendingFile.name, file: pendingFile, dataUrl, placement: { x: 10, y: 10, width: 150, height: 80 } }]);
      setAddingImg(false); setPendingLabel(''); setPendingFile(null);
    };
    reader.readAsDataURL(pendingFile);
  };

  // ── Build FormData ─────────────────────────────────────────────────────────
  const buildFD = (includeOverrides: boolean, ai?: AuthInfo) => {
    const fd = new FormData();
    const cleanOverrides: Record<string, any> = {};
    if (includeOverrides) {
      Object.entries(cellOverrides).forEach(([coord, ov]) => {
        const clean: Record<string, any> = {};
        if (ov.value !== undefined) clean.value = ov.value;
        if (ov.alignment) clean.alignment = ov.alignment;
        if (ov.font) clean.font = ov.font;
        if (Object.keys(clean).length > 0) cleanOverrides[coord] = clean;
      });
    }
    const customPlacements: Record<string, any> = {};
    customImages.forEach(ci => { customPlacements[ci.id] = ci.placement; });

    // Convert mergeRanges to Excel range strings for backend
    const mergeStrings = mergeRanges.map(mr =>
      `${colLetter(mr.minCol)}${mr.minRow}:${colLetter(mr.maxCol)}${mr.maxRow}`
    );

    // Convert 1-based col/row overrides to string-keyed for JSON
    const colWidthOverrides: Record<string, number> = {};
    const rowHeightOverrides: Record<string, number> = {};
    Object.entries(colOverrides).forEach(([k, v]) => { colWidthOverrides[colLetter(+k)] = v; });
    Object.entries(rowOverrides).forEach(([k, v]) => { rowHeightOverrides[k] = v; });

    fd.append('data', JSON.stringify({
      project_info: projectInfo,
      revisions,
      ...(includeOverrides ? {
        image_placements: imagePlacements,
        cell_overrides: cleanOverrides,
        custom_image_placements: customPlacements,
        merge_ranges: mergeStrings,
        unmerge_coords: unmergeCoords,
        blank_mode: isBlank,
        paper_size: paperSize,
        orientation,
        col_width_overrides: colWidthOverrides,
        row_height_overrides: rowHeightOverrides,
        approved_by: ai?.employee_name || '',
        approver_id: ai?.employee_id || '',
      } : {}),
    }));
    if (templateFile && !isBlank) fd.append('template_file', templateFile);
    Object.entries(fixedImages).forEach(([k, f]) => { if (f) fd.append(k, f); });
    customImages.forEach(ci => fd.append('extra_images', ci.file));
    fd.append('extra_image_meta', JSON.stringify(customImages.map(ci => ({ id: ci.id, label: ci.label }))));
    return fd;
  };

  const handlePreview = async () => {
    if (isBlank) {
      // Blank canvas: build layout on frontend, no API call
      const layout = createBlankLayout();
      setPreviewLayout(layout);
      setPreviewImages({});
      return;
    }
    setPreviewLoading(true); setResult(null); setError(null);
    try {
      const res = await api.post('/coversheet/preview', buildFD(false), {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setPreviewLayout(res.data.layout);
      setPreviewImages(res.data.images);
    } catch (e: any) { setError(e.response?.data?.detail || 'Preview failed'); }
    finally { setPreviewLoading(false); }
  };

  const handleAuthSuccess = (ai: AuthInfo) => {
    setAuthInfo(ai);
    setShowAuthModal(false);
    doGenerate(ai);
  };

  const doGenerate = async (ai: AuthInfo) => {
    setGenerating(true); setResult(null); setError(null);
    try {
      const res = await api.post('/coversheet/generate', buildFD(true, ai), {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(res.data);
    } catch (e: any) { setError(e.response?.data?.detail || 'Generation failed'); }
    finally { setGenerating(false); }
  };

  const handleDownload = async () => {
    try {
      const res = await api.get('/coversheet/download', { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a'); a.href = url;
      a.download = result?.filename || 'CoverSheet.xlsx'; a.click();
      URL.revokeObjectURL(url);
    } catch { setError('Download failed'); }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      {/* ── Top bar with header + Upload MDL ── */}
      <div className="flex items-start gap-4">
        <div className="flex-1">
          <PageHeader icon={FileSpreadsheet}
            title="Cover Sheet Generator"
            description="Click any cell to edit · Shift+click to select range · Merge / Unmerge · Drag images · Admin auth required to generate" />
        </div>

        {/* Upload MDL — top right, no processing yet */}
        <div className="flex-shrink-0 pt-1">
          <input ref={mdlInputRef} type="file" accept=".xlsx,.xls,.csv" className="hidden"
            onChange={e => setMdlFile(e.target.files?.[0] || null)} />
          <button onClick={() => mdlInputRef.current?.click()}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all"
            style={{
              background: mdlFile ? 'rgba(74,222,128,0.08)' : 'var(--s2)',
              color: mdlFile ? '#4ade80' : 'var(--t1)',
              border: `1.5px dashed ${mdlFile ? 'rgba(74,222,128,0.4)' : 'var(--b2)'}`,
            }}>
            <FileUpIcon className="w-3.5 h-3.5" />
            {mdlFile ? mdlFile.name.length > 22 ? mdlFile.name.slice(0, 20) + '…' : mdlFile.name : 'Upload MDL'}
          </button>
          {mdlFile && (
            <button onClick={() => setMdlFile(null)}
              className="text-[10px] mt-1 ml-1 opacity-50 hover:opacity-100"
              style={{ color: 'var(--rose)' }}>✕ Remove</button>
          )}
        </div>
      </div>

      {error && <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>}

      {/* ── Template / Blank canvas ── */}
      <Section title="Canvas Source" subtitle="Upload your own template OR start with a fully blank canvas" defaultOpen
        badge={isBlank ? 'Blank Canvas' : templateFile ? 'Custom Template' : 'Default Template'}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
          {/* Use template */}
          <button onClick={() => { setIsBlank(false); }}
            className="rounded-xl p-4 text-left transition-all"
            style={{ background: !isBlank ? 'rgba(59,130,246,0.06)' : 'var(--s3)', border: `1.5px solid ${!isBlank ? 'var(--em)' : 'var(--b2)'}` }}>
            <FileSpreadsheet className="w-5 h-5 mb-2" style={{ color: !isBlank ? 'var(--em-lt)' : 'var(--t2)' }} />
            <p className="text-sm font-bold" style={{ color: !isBlank ? 'var(--em-lt)' : 'var(--t1)' }}>Use Template</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--t2)' }}>Upload your .xlsx or use the built-in WABAG template</p>
          </button>
          {/* Blank canvas */}
          <button onClick={() => { setIsBlank(true); setTemplateFile(null); }}
            className="rounded-xl p-4 text-left transition-all"
            style={{ background: isBlank ? 'rgba(245,158,11,0.06)' : 'var(--s3)', border: `1.5px solid ${isBlank ? 'rgba(245,158,11,0.5)' : 'var(--b2)'}` }}>
            <LayoutGrid className="w-5 h-5 mb-2" style={{ color: isBlank ? 'var(--gold)' : 'var(--t2)' }} />
            <p className="text-sm font-bold" style={{ color: isBlank ? 'var(--gold)' : 'var(--t1)' }}>Blank Canvas</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--t2)' }}>30×20 empty grid — design your sheet from scratch</p>
          </button>
        </div>
        {!isBlank && (
          <label className="flex items-center gap-3 rounded-xl cursor-pointer px-4 py-3 transition-all"
            style={{ background: templateFile ? 'rgba(74,222,128,0.06)' : 'var(--s3)', border: `1.5px dashed ${templateFile ? '#4ade80' : 'var(--b2)'}` }}>
            {templateFile
              ? <><CheckCircle2 className="w-4 h-4 flex-shrink-0" style={{ color: '#4ade80' }} />
                  <span className="text-xs font-medium truncate" style={{ color: '#4ade80' }}>{templateFile.name}</span>
                  <button className="ml-auto" onClick={e => { e.preventDefault(); setTemplateFile(null); }}>
                    <X className="w-3.5 h-3.5" style={{ color: 'var(--t2)' }} /></button></>
              : <><Upload className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--t2)' }} />
                  <span className="text-xs" style={{ color: 'var(--t1)' }}>Upload custom .xlsx template (optional — leave blank for default)</span></>}
            <input type="file" accept=".xlsx,.xls" className="hidden"
              onChange={e => setTemplateFile(e.target.files?.[0] || null)} />
          </label>
        )}
      </Section>

      {/* ── Page Layout ── */}
      <Section title="Page Layout" subtitle="Paper size and orientation applied to the generated Excel file" defaultOpen={false}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className={lc} style={lcSt}>Paper Size</label>
            <select className={ic} style={icSt} value={paperSize} onChange={e => setPaperSize(e.target.value)}>
              {PAPER_SIZES.map(ps => <option key={ps.value} value={ps.value}>{ps.label}</option>)}
            </select>
          </div>
          <div>
            <label className={lc} style={lcSt}>Orientation</label>
            <div className="flex gap-2">
              {(['portrait', 'landscape'] as const).map(o => (
                <button key={o} onClick={() => setOrientation(o)}
                  className="flex-1 py-2 rounded-xl text-xs font-bold capitalize"
                  style={{
                    background: orientation === o ? 'rgba(59,130,246,0.08)' : 'var(--s3)',
                    color: orientation === o ? 'var(--em-lt)' : 'var(--t1)',
                    border: `1.5px solid ${orientation === o ? 'var(--em)' : 'var(--b2)'}`,
                  }}>
                  {o === 'portrait' ? '⬛ Portrait' : '▬ Landscape'}
                </button>
              ))}
            </div>
          </div>
        </div>
      </Section>

      {/* ── Quick Fill ── */}
      {!isBlank && (
        <Section title="Quick Fill — Project Fields"
          subtitle="Auto-maps to standard WABAG template cells. Skip if editing cells directly on the canvas."
          defaultOpen={false} badge="Optional">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
            {([['Client', 'client'], ['PMC', 'pmc'], ['Contractor', 'contractor']] as [string, keyof ProjectInfo][]).map(([lbl, k]) => (
              <div key={k}>
                <label className={lc} style={lcSt}>{lbl}</label>
                <input className={ic} style={icSt} value={projectInfo[k]} onChange={e => setPI(k, e.target.value)} />
              </div>
            ))}
            <div className="sm:col-span-3">
              <label className={lc} style={lcSt}>Project Description</label>
              <textarea className={ic} style={{ ...icSt, resize: 'none' }} rows={2}
                value={projectInfo.project_description} onChange={e => setPI('project_description', e.target.value)} />
            </div>
            <div>
              <label className={lc} style={lcSt}>Doc Title (short)</label>
              <input className={ic} style={icSt} value={projectInfo.doc_title_short} onChange={e => setPI('doc_title_short', e.target.value)} />
            </div>
            <div>
              <label className={lc} style={lcSt}>Doc Class</label>
              <select className={ic} style={icSt} value={projectInfo.doc_class} onChange={e => setPI('doc_class', e.target.value)}>
                {DOC_CLASSES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className={lc} style={lcSt}>Discipline</label>
              <input className={ic} style={icSt} value={projectInfo.discipline} onChange={e => setPI('discipline', e.target.value)} />
            </div>
            <div className="sm:col-span-3">
              <label className={lc} style={lcSt}>Doc Title (full)</label>
              <textarea className={ic} style={{ ...icSt, resize: 'none' }} rows={2}
                value={projectInfo.doc_title_full} onChange={e => setPI('doc_title_full', e.target.value)} />
            </div>
            {([['Job No.', 'job_no'], ['Unit No.', 'unit_no'], ['Project No.', 'project_no'], ['Doc Code', 'doc_code'], ['Serial No.', 'serial_no'], ['Page No.', 'page_no']] as [string, keyof ProjectInfo][]).map(([lbl, k]) => (
              <div key={k}>
                <label className={lc} style={lcSt}>{lbl}</label>
                <input className={ic} style={icSt} value={projectInfo[k]} onChange={e => setPI(k, e.target.value)} />
              </div>
            ))}
          </div>
          <button onClick={saveMaster}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold"
            style={{ background: masterSaved ? 'rgba(74,222,128,0.1)' : 'var(--s3)', color: masterSaved ? '#4ade80' : 'var(--t1)', border: `1px solid ${masterSaved ? 'rgba(74,222,128,0.3)' : 'var(--b2)'}` }}>
            <Save className="w-3.5 h-3.5" />{masterSaved ? 'Saved!' : 'Save as Project Master'}
          </button>
        </Section>
      )}

      {/* ── Revision history ── */}
      <Section title="Revision History" subtitle={`Oldest first · Max ${MAX_REVISIONS} rows · Last row = current revision`}
        badge={`${revisions.length} rev${revisions.length > 1 ? 's' : ''}`}>
        <div className="space-y-2">
          {revisions.map((rev, i) => (
            <div key={i} className="rounded-xl p-3 grid grid-cols-2 sm:grid-cols-7 gap-2 items-end"
              style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
              {([
                ['Rev No.', 'rev_no', 1], ['Date', 'date', 1], ['Description', 'description', 2],
                ['Prepared By', 'prepared_by', 1], ['Checked By', 'checked_by', 1],
              ] as [string, keyof RevisionEntry, number][]).map(([lbl, k, span]) => (
                <div key={k} className={span > 1 ? `sm:col-span-${span}` : ''}>
                  <label className={lc} style={lcSt}>{lbl}</label>
                  <input className={ic} style={icSt} value={rev[k]}
                    placeholder={k === 'date' ? 'DD.MM.YYYY' : undefined}
                    onChange={e => setRev(i, k, e.target.value)} />
                </div>
              ))}
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <label className={lc} style={lcSt}>Approved By</label>
                  <input className={ic} style={icSt} value={rev.approved_by} onChange={e => setRev(i, 'approved_by', e.target.value)} />
                </div>
                <button disabled={revisions.length <= 1} onClick={() => setRevisions(p => p.filter((_, idx) => idx !== i))}
                  className="p-2 rounded-lg" style={{ color: 'var(--rose)', opacity: revisions.length <= 1 ? 0.3 : 1 }}>
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
        {revisions.length < MAX_REVISIONS && (
          <button onClick={() => {
            const last = revisions[revisions.length - 1];
            setRevisions(p => [...p, { ...emptyRevision(), prepared_by: last?.prepared_by || '', checked_by: last?.checked_by || '', approved_by: last?.approved_by || '' }]);
          }}
            className="mt-3 flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold"
            style={{ background: 'var(--s3)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.3)' }}>
            <Plus className="w-3.5 h-3.5" /> Add Revision
          </button>
        )}
      </Section>

      {/* ── Logos & Images ── */}
      <Section title="Logos & Images" subtitle="Standard slots + add unlimited custom images. Position them on the canvas."
        badge={`${Object.values(fixedImages).filter(Boolean).length + customImages.length} uploaded`}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
          {FIXED_IMAGE_FIELDS.map(({ key, label }) => (
            <div key={key}>
              <label className={lc} style={lcSt}>{label}</label>
              <ImgZone file={fixedImages[key] || null}
                onChange={f => setFixedImages(p => ({ ...p, [key]: f || undefined }))} label="Upload image…" />
            </div>
          ))}
        </div>

        {customImages.length > 0 && (
          <div className="mb-3 space-y-1.5">
            <p className="text-xs font-semibold" style={{ color: 'var(--t2)' }}>Custom Images</p>
            {customImages.map(ci => (
              <div key={ci.id} className="flex items-center gap-3 px-3 py-2 rounded-xl"
                style={{ background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.2)' }}>
                <img src={ci.dataUrl} alt="" className="w-10 h-6 object-contain rounded" style={{ background: '#fff' }} />
                <span className="text-xs flex-1 truncate" style={{ color: 'var(--gold)' }}>{ci.label}</span>
                <button onClick={() => setCustomImages(p => p.filter(x => x.id !== ci.id))} style={{ color: 'var(--rose)' }}>
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        {addingImg ? (
          <div className="rounded-xl p-4 space-y-3" style={{ background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.25)' }}>
            <p className="text-xs font-bold" style={{ color: 'var(--gold)' }}>Add Custom Image</p>
            <div>
              <label className={lc} style={lcSt}>Label</label>
              <input className={ic} style={icSt} placeholder="e.g. Project Logo, North Arrow…"
                value={pendingLabel} onChange={e => setPendingLabel(e.target.value)} />
            </div>
            <ImgZone file={pendingFile} onChange={setPendingFile} label="Select image file" />
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => { setAddingImg(false); setPendingLabel(''); setPendingFile(null); }}>Cancel</Button>
              <Button size="sm" disabled={!pendingFile} onClick={confirmAddCustom}>
                <ImagePlus className="w-3.5 h-3.5" /> Add to Canvas
              </Button>
            </div>
          </div>
        ) : (
          <button onClick={() => setAddingImg(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold"
            style={{ background: 'rgba(245,158,11,0.08)', color: 'var(--gold)', border: '1px dashed rgba(245,158,11,0.4)' }}>
            <ImagePlus className="w-3.5 h-3.5" /> Add Custom Image
          </button>
        )}
      </Section>

      {/* ── Interactive Preview ── */}
      <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        <div className="flex items-center gap-3 px-5 py-4" style={{ borderBottom: '1px solid var(--b1)' }}>
          <FileUp className="w-4 h-4" style={{ color: 'var(--em-lt)' }} />
          <div className="flex-1">
            <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Interactive Preview</p>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>
              {previewLayout
                ? `${isBlank ? 'Blank canvas' : 'Template'} loaded · Click cell to edit · Shift+click to select range · Merge/Unmerge in side panel`
                : 'Build a preview to start editing cells, merge ranges, and position images.'}
            </p>
          </div>
          {mergeRanges.length > 0 && (
            <span className="text-[10px] px-2 py-0.5 rounded-full font-bold"
              style={{ background: 'rgba(59,130,246,0.1)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.2)' }}>
              {mergeRanges.length} custom merge{mergeRanges.length > 1 ? 's' : ''}
            </span>
          )}
          <Button onClick={handlePreview} loading={previewLoading} size="sm">
            <Eye className="w-3.5 h-3.5" />
            {previewLayout ? 'Refresh' : 'Build Preview'}
          </Button>
        </div>

        {previewLayout ? (
          <div className="p-4">
            <CoverSheetPreview
              layout={previewLayout}
              images={previewImages}
              cellOverrides={cellOverrides}
              onCellOverridesChange={setCellOverrides}
              imagePlacements={imagePlacements}
              onImagePlacementsChange={setImagePlacements}
              customImages={customImages}
              onCustomImagesChange={setCustomImages}
              mergeRanges={mergeRanges}
              onMergeRangesChange={setMergeRanges}
              unmergeCoords={unmergeCoords}
              onUnmergeCoordsChange={setUnmergeCoords}
              colOverrides={colOverrides}
              onColOverridesChange={setColOverrides}
              rowOverrides={rowOverrides}
              onRowOverridesChange={setRowOverrides}
            />
          </div>
        ) : (
          <div className="p-10 text-center">
            <Eye className="w-10 h-10 mx-auto mb-3 opacity-20" style={{ color: 'var(--t2)' }} />
            <p className="text-sm" style={{ color: 'var(--t2)' }}>Click "Build Preview" to open the interactive canvas</p>
          </div>
        )}
      </div>

      {/* ── Generate section ── */}
      <div className="rounded-2xl p-5" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        {authInfo ? (
          <div className="flex items-center gap-3 mb-4 px-4 py-3 rounded-xl"
            style={{ background: 'rgba(74,222,128,0.06)', border: '1px solid rgba(74,222,128,0.2)' }}>
            <CheckCircle2 className="w-4 h-4" style={{ color: '#4ade80' }} />
            <p className="text-xs font-semibold" style={{ color: '#4ade80' }}>
              Authorized — {authInfo.employee_name} ({authInfo.role})
            </p>
            <button onClick={() => setAuthInfo(null)} className="ml-auto opacity-50 hover:opacity-100" style={{ color: 'var(--t2)' }}>
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : csReqStatus === 'pending' ? (
          <div className="flex items-center gap-3 mb-4 px-4 py-3 rounded-xl"
            style={{ background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)' }}>
            <Loader2 className="w-4 h-4 animate-spin flex-shrink-0" style={{ color: 'var(--gold)' }} />
            <p className="text-xs flex-1" style={{ color: 'var(--gold)' }}>
              Request #{csPendingReqId} — Awaiting Lead Engineer Approval…
            </p>
            <button onClick={() => { if (csPollRef.current) clearInterval(csPollRef.current); setCSPendingReqId(null); setCSReqStatus('idle'); }}
              className="opacity-40 hover:opacity-80" style={{ color: 'var(--t2)' }}><X className="w-3.5 h-3.5" /></button>
          </div>
        ) : csReqStatus === 'rejected' ? (
          <div className="flex items-center gap-3 mb-4 px-4 py-3 rounded-xl"
            style={{ background: 'rgba(248,113,113,0.06)', border: '1px solid rgba(248,113,113,0.2)' }}>
            <AlertTriangle className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--rose)' }} />
            <p className="text-xs flex-1" style={{ color: 'var(--rose)' }}>Request rejected by Lead Engineer. Please review and resubmit.</p>
            <button onClick={() => { setCSPendingReqId(null); setCSReqStatus('idle'); }}
              className="opacity-40 hover:opacity-80" style={{ color: 'var(--t2)' }}><X className="w-3.5 h-3.5" /></button>
          </div>
        ) : (
          <div className="flex items-center gap-3 mb-4 px-4 py-3 rounded-xl"
            style={{ background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.2)' }}>
            <Lock className="w-4 h-4" style={{ color: 'var(--gold)' }} />
            <p className="text-xs" style={{ color: 'var(--gold)' }}>
              Raise an approval request for Lead Engineer review before generating.
            </p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          {/* Raise Request — shown when not yet pending or rejected */}
          {(csReqStatus === 'idle' || csReqStatus === 'rejected') && !authInfo && (
            <Button onClick={() => setShowCSRaiseModal(true)} disabled={!previewLayout} size="lg"
              style={{ background: 'linear-gradient(135deg,var(--gold),#d97706)', color: '#000' }}>
              <Send className="w-4 h-4" /> Request Lead Approval
            </Button>
          )}
          {/* Generate — enabled once Lead approved OR if admin already authed */}
          {(csReqStatus === 'approved' || authInfo) && (
            <Button onClick={() => {
              if (authInfo) { doGenerate(authInfo); }
              else { setShowAuthModal(true); }
            }} loading={generating} disabled={!previewLayout} size="lg">
              <FileSpreadsheet className="w-4 h-4" />
              {generating ? 'Generating…' : 'Generate Cover Sheet'}
            </Button>
          )}
          {!previewLayout && (
            <p className="text-xs" style={{ color: 'var(--t2)' }}>Build a preview first.</p>
          )}
          {result && (
            <Button onClick={handleDownload} size="lg"
              style={{ background: 'linear-gradient(135deg,#4ade80,#22c55e)', color: '#000' }}>
              <Download className="w-4 h-4" /> Download {result.filename}
            </Button>
          )}
          {result && <p className="text-xs" style={{ color: '#4ade80' }}>{result.message}</p>}
        </div>
      </div>

      {showAuthModal && (
        <AdminVerifyModal onSuccess={handleAuthSuccess} onClose={() => setShowAuthModal(false)} />
      )}
      {showCSRaiseModal && (
        <CSRaiseRequestModal
          projectTitle={projectInfo.doc_title_short || projectInfo.doc_title_full || 'Cover Sheet'}
          projectInfo={projectInfo}
          onSuccess={(reqId) => {
            setCSPendingReqId(reqId); setCSReqStatus('pending');
            if (csPollRef.current) clearInterval(csPollRef.current);
            csPollRef.current = setInterval(async () => {
              try {
                const r = await api.get(`/approvals/${reqId}`);
                if (r.data.status === 'approved') {
                  clearInterval(csPollRef.current!);
                  setCSReqStatus('approved');
                  setAuthInfo({ employee_name: r.data.reviewed_by_name, role: r.data.reviewed_role, employee_id: r.data.reviewed_by_id });
                } else if (r.data.status === 'rejected') {
                  clearInterval(csPollRef.current!);
                  setCSReqStatus('rejected');
                }
              } catch { /* ignore */ }
            }, 15_000);
          }}
          onClose={() => setShowCSRaiseModal(false)} />
      )}
    </div>
  );
}
