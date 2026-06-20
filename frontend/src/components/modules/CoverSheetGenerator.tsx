/**
 * Smart Cover Sheet Generator — fully customizable canvas-first editor.
 * - Click any cell in the preview to type a value or change formatting
 * - Add unlimited images and drag / resize them anywhere on the canvas
 * - Upload your own Excel template (optional – uses the default WABAG template otherwise)
 * - Collapsible Quick-Fill section for common fields (auto-populates standard cells)
 */
import { useState, useEffect } from 'react';
import {
  FileSpreadsheet, Upload, Download, Plus, Trash2, Save,
  Eye, ImagePlus, ChevronDown, ChevronRight, FileUp, X, CheckCircle2,
} from 'lucide-react';
import api from '@/services/api';
import CoverSheetPreview from './coversheet/CoverSheetPreview';
import type { CoverSheetLayout, ImageKey, ImagePlacement, CellOverride, CustomImageSlot } from './coversheet/types';
import PageHeader from '../ui/PageHeader';
import Button from '../ui/Button';
import Alert from '../ui/Alert';

// ── Types ────────────────────────────────────────────────────────────────────
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

const MASTER_KEY = 'iez_coversheet_project_master';
const MAX_REVISIONS = 7;

const DOC_CLASSES = ['APPROVAL', 'IFC', 'IFA', 'INFORMATION', 'INTERNAL', 'CONSTRUCTION'];

const FIXED_IMAGE_FIELDS: { key: ImageKey; label: string }[] = [
  { key: 'client_logo', label: 'Client Logo' },
  { key: 'pmc_logo', label: 'PMC Logo' },
  { key: 'wabag_logo', label: 'WABAG / Contractor Logo (replaces embedded)' },
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

// ── Input helpers ─────────────────────────────────────────────────────────────
const ic = 'w-full px-3 py-2 rounded-xl text-sm outline-none';
const icStyle = { background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)' };
const lc = 'block text-[10px] font-semibold uppercase tracking-wider mb-1.5';
const lcStyle = { color: 'var(--t2)' };

function Field({
  label, value, onChange, textarea, rows, type, children,
}: {
  label: string; value: string; onChange: (v: string) => void;
  textarea?: boolean; rows?: number; type?: string; children?: React.ReactNode;
}) {
  return (
    <div>
      <label className={lc} style={lcStyle}>{label}</label>
      {children
        ? children
        : textarea
          ? <textarea className={ic} style={{ ...icStyle, resize: 'none' }} rows={rows || 2}
              value={value} onChange={e => onChange(e.target.value)} />
          : <input type={type || 'text'} className={ic} style={icStyle}
              value={value} onChange={e => onChange(e.target.value)} />}
    </div>
  );
}

// ── Collapsible Section ───────────────────────────────────────────────────────
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
        {badge && (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-bold"
            style={{ background: 'var(--em-dim)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.2)' }}>
            {badge}
          </span>
        )}
      </button>
      {open && <div className="px-5 pb-5">{children}</div>}
    </div>
  );
}

// ── Drop zone for file uploads ────────────────────────────────────────────────
function DropZone({ file, onChange, accept, label, accent }: {
  file: File | null; onChange: (f: File | null) => void;
  accept: string; label: string; accent?: string;
}) {
  return (
    <label className="flex items-center gap-3 rounded-xl cursor-pointer px-4 py-3 transition-all"
      style={{ background: file ? 'rgba(16,185,129,0.06)' : 'var(--s3)', border: `1.5px dashed ${file ? '#4ade80' : accent || 'var(--b2)'}` }}>
      {file
        ? <><CheckCircle2 className="w-4 h-4 flex-shrink-0" style={{ color: '#4ade80' }} />
            <span className="text-xs font-medium truncate" style={{ color: '#4ade80' }}>{file.name}</span>
            <button className="ml-auto" style={{ color: 'var(--t2)' }}
              onClick={e => { e.preventDefault(); onChange(null); }}>
              <X className="w-3.5 h-3.5" />
            </button></>
        : <><Upload className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--t2)' }} />
            <span className="text-xs" style={{ color: 'var(--t1)' }}>{label}</span>
            <span className="ml-auto text-[10px]" style={{ color: 'var(--t2)' }}>{accept}</span></>}
      <input type="file" accept={accept} className="hidden"
        onChange={e => onChange(e.target.files?.[0] || null)} />
    </label>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function CoverSheetGenerator() {
  // Data state
  const [projectInfo, setProjectInfo] = useState<ProjectInfo>(emptyProjectInfo);
  const [revisions, setRevisions] = useState<RevisionEntry[]>([emptyRevision()]);
  const setPI = (k: keyof ProjectInfo, v: string) => setProjectInfo(p => ({ ...p, [k]: v }));
  const setRev = (i: number, k: keyof RevisionEntry, v: string) =>
    setRevisions(prev => prev.map((r, idx) => idx === i ? { ...r, [k]: v } : r));

  // Template
  const [templateFile, setTemplateFile] = useState<File | null>(null);

  // Fixed images (6 slots)
  const [fixedImages, setFixedImages] = useState<Partial<Record<ImageKey, File>>>({});

  // Custom images (unlimited)
  const [customImages, setCustomImages] = useState<CustomImageSlot[]>([]);
  const [pendingLabel, setPendingLabel] = useState('');
  const [addingImage, setAddingImage] = useState(false);
  const [pendingFile, setPendingFile] = useState<File | null>(null);

  // Preview state
  const [previewLayout, setPreviewLayout] = useState<CoverSheetLayout | null>(null);
  const [previewImages, setPreviewImages] = useState<Partial<Record<ImageKey, ImagePlacement>>>({});
  const [cellOverrides, setCellOverrides] = useState<Record<string, CellOverride>>({});
  const [imagePlacements, setImagePlacements] = useState<Partial<Record<ImageKey, PlacementState>>>({});

  // Status
  const [previewLoading, setPreviewLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [masterSaved, setMasterSaved] = useState(false);
  const [result, setResult] = useState<{ filename: string; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load saved master on mount
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
    setMasterSaved(true);
    setTimeout(() => setMasterSaved(false), 2000);
  };

  // ── Image helpers ──────────────────────────────────────────────────────────
  const handleFixedImage = (key: ImageKey, e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    setFixedImages(prev => ({ ...prev, [key]: f || undefined }));
  };

  const startAddCustom = () => { setAddingImage(true); setPendingLabel(''); setPendingFile(null); };
  const cancelAddCustom = () => { setAddingImage(false); setPendingLabel(''); setPendingFile(null); };

  const confirmAddCustom = () => {
    if (!pendingFile) return;
    const reader = new FileReader();
    reader.onload = ev => {
      const dataUrl = ev.target?.result as string;
      const id = `custom_${Date.now()}_${Math.random().toString(36).slice(2)}`;
      setCustomImages(prev => [...prev, {
        id, label: pendingLabel || pendingFile.name,
        file: pendingFile, dataUrl,
        placement: { x: 10, y: 10, width: 150, height: 80 },
      }]);
      cancelAddCustom();
    };
    reader.readAsDataURL(pendingFile);
  };

  // ── FormData builder ───────────────────────────────────────────────────────
  const buildFormData = (includeOverrides: boolean) => {
    const fd = new FormData();
    const data: Record<string, any> = { project_info: projectInfo, revisions };
    if (includeOverrides) {
      data.image_placements = imagePlacements;
      // Serialize cell_overrides but remove undefined values
      const cleanOverrides: Record<string, any> = {};
      Object.entries(cellOverrides).forEach(([coord, ov]) => {
        const clean: Record<string, any> = {};
        if (ov.value !== undefined) clean.value = ov.value;
        if (ov.alignment) clean.alignment = ov.alignment;
        if (ov.font) clean.font = ov.font;
        if (Object.keys(clean).length > 0) cleanOverrides[coord] = clean;
      });
      data.cell_overrides = cleanOverrides;
      // Custom image placements
      const customPlacements: Record<string, any> = {};
      customImages.forEach(ci => { customPlacements[ci.id] = ci.placement; });
      data.custom_image_placements = customPlacements;
    }
    fd.append('data', JSON.stringify(data));
    if (templateFile) fd.append('template_file', templateFile);
    // Fixed images
    Object.entries(fixedImages).forEach(([key, file]) => { if (file) fd.append(key, file); });
    // Custom images
    customImages.forEach(ci => fd.append('extra_images', ci.file));
    const extraMeta = customImages.map(ci => ({ id: ci.id, label: ci.label }));
    fd.append('extra_image_meta', JSON.stringify(extraMeta));
    return fd;
  };

  const handlePreview = async () => {
    setPreviewLoading(true); setResult(null); setError(null);
    try {
      const res = await api.post('/coversheet/preview', buildFormData(false), {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setPreviewLayout(res.data.layout);
      setPreviewImages(res.data.images);
    } catch (e: any) { setError(e.response?.data?.detail || 'Preview failed'); }
    finally { setPreviewLoading(false); }
  };

  const handleGenerate = async () => {
    setGenerating(true); setResult(null); setError(null);
    try {
      const res = await api.post('/coversheet/generate', buildFormData(true), {
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
      <PageHeader icon={FileSpreadsheet}
        title="Cover Sheet Generator"
        description="Click any cell to edit · Drag & resize images · Upload your own template" />

      {error && <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>}

      {/* ── Template upload ── */}
      <Section title="Template" subtitle="Optional — upload your own .xlsx cover sheet instead of the default WABAG template" defaultOpen={false}
        badge={templateFile ? 'Custom' : 'Default'}>
        <DropZone file={templateFile} onChange={setTemplateFile}
          accept=".xlsx,.xls" label="Upload custom Excel template"
          accent="rgba(245,158,11,0.6)" />
        {!templateFile && (
          <p className="text-xs mt-2" style={{ color: 'var(--t2)' }}>
            Using default WABAG LT_DS_coversheet.xlsx template. Upload above to replace.
          </p>
        )}
      </Section>

      {/* ── Quick Fill ── */}
      <Section title="Quick Fill — Project Information"
        subtitle="Fill standard fields; they auto-map to cells in the template. Or skip this and edit cells directly on the canvas."
        defaultOpen badge="Optional">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          <Field label="Client" value={projectInfo.client} onChange={v => setPI('client', v)} />
          <Field label="PMC" value={projectInfo.pmc} onChange={v => setPI('pmc', v)} />
          <Field label="Contractor" value={projectInfo.contractor} onChange={v => setPI('contractor', v)} />
          <div className="sm:col-span-3">
            <Field label="Project Description" value={projectInfo.project_description}
              onChange={v => setPI('project_description', v)} textarea rows={2} />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
          <Field label="Document Title (short / header)" value={projectInfo.doc_title_short}
            onChange={v => setPI('doc_title_short', v)} />
          <div>
            <Field label="Document Class" value={projectInfo.doc_class} onChange={v => setPI('doc_class', v)}>
              <select className={ic} style={icStyle} value={projectInfo.doc_class}
                onChange={e => setPI('doc_class', e.target.value)}>
                {DOC_CLASSES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="Document Title (full)" value={projectInfo.doc_title_full}
              onChange={v => setPI('doc_title_full', v)} textarea rows={2} />
          </div>
          <Field label="Discipline" value={projectInfo.discipline} onChange={v => setPI('discipline', v)} />
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-5">
          {([
            ['Job Number', 'job_no'], ['Unit Number', 'unit_no'],
            ['Project Number', 'project_no'], ['Document Code', 'doc_code'],
            ['Serial Number', 'serial_no'], ['Page Number', 'page_no'],
          ] as [string, keyof ProjectInfo][]).map(([lbl, key]) => (
            <Field key={key} label={lbl} value={projectInfo[key]} onChange={v => setPI(key, v)} />
          ))}
        </div>

        <button onClick={saveMaster}
          className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold"
          style={{ background: masterSaved ? 'rgba(74,222,128,0.1)' : 'var(--s3)', color: masterSaved ? '#4ade80' : 'var(--t1)', border: `1px solid ${masterSaved ? 'rgba(74,222,128,0.3)' : 'var(--b2)'}` }}>
          <Save className="w-3.5 h-3.5" /> {masterSaved ? 'Saved to browser!' : 'Save as Project Master'}
        </button>
      </Section>

      {/* ── Revision table ── */}
      <Section title="Revision History" subtitle={`Oldest revision first · Maximum ${MAX_REVISIONS} rows · Current revision = last row`}
        badge={`${revisions.length} rev${revisions.length !== 1 ? 's' : ''}`}>
        <div className="space-y-2">
          {revisions.map((rev, i) => (
            <div key={i} className="rounded-xl p-3 grid grid-cols-2 sm:grid-cols-7 gap-2 items-end"
              style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
              {([
                ['Rev No.', 'rev_no', 1],
                ['Date', 'date', 1],
                ['Description', 'description', 2],
                ['Prepared By', 'prepared_by', 1],
                ['Checked By', 'checked_by', 1],
              ] as [string, keyof RevisionEntry, number][]).map(([lbl, key, span]) => (
                <div key={key} className={span > 1 ? `sm:col-span-${span}` : ''}>
                  <label className={lc} style={lcStyle}>{lbl}</label>
                  <input className={ic} style={icStyle}
                    placeholder={key === 'date' ? 'DD.MM.YYYY' : undefined}
                    value={rev[key]} onChange={e => setRev(i, key, e.target.value)} />
                </div>
              ))}
              <div className="flex gap-2 items-end">
                <div className="flex-1">
                  <label className={lc} style={lcStyle}>Approved By</label>
                  <input className={ic} style={icStyle}
                    value={rev.approved_by} onChange={e => setRev(i, 'approved_by', e.target.value)} />
                </div>
                <button disabled={revisions.length <= 1} onClick={() => setRevisions(prev => prev.filter((_, idx) => idx !== i))}
                  className="p-2 rounded-lg mb-0.5 transition-opacity"
                  style={{ color: 'var(--rose)', opacity: revisions.length <= 1 ? 0.3 : 1 }}>
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
        {revisions.length < MAX_REVISIONS && (
          <button onClick={() => {
            const last = revisions[revisions.length - 1];
            setRevisions(prev => [...prev, { ...emptyRevision(), prepared_by: last?.prepared_by || '', checked_by: last?.checked_by || '', approved_by: last?.approved_by || '' }]);
          }}
            className="mt-3 flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold"
            style={{ background: 'var(--s3)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.3)' }}>
            <Plus className="w-3.5 h-3.5" /> Add Revision
          </button>
        )}
      </Section>

      {/* ── Images ── */}
      <Section title="Logos & Images"
        subtitle="Upload standard slots OR click 'Add Image' to place any image anywhere on the canvas"
        badge={`${Object.values(fixedImages).filter(Boolean).length + customImages.length} uploaded`}>

        {/* Fixed 6 slots */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
          {FIXED_IMAGE_FIELDS.map(({ key, label }) => (
            <div key={key}>
              <label className={lc} style={lcStyle}>{label}</label>
              <label className="flex items-center gap-2 rounded-xl cursor-pointer px-3 py-2"
                style={{ background: fixedImages[key] ? 'rgba(74,222,128,0.06)' : 'var(--s3)', border: `1.5px dashed ${fixedImages[key] ? '#4ade80' : 'var(--b2)'}` }}>
                {fixedImages[key]
                  ? <><CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#4ade80' }} />
                      <span className="text-xs truncate" style={{ color: '#4ade80' }}>{fixedImages[key]!.name}</span>
                      <button className="ml-auto" onClick={e => { e.preventDefault(); setFixedImages(p => ({ ...p, [key]: undefined })); }}>
                        <X className="w-3 h-3" style={{ color: 'var(--t2)' }} />
                      </button></>
                  : <><Upload className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--t2)' }} />
                      <span className="text-xs" style={{ color: 'var(--t2)' }}>Upload image…</span></>}
                <input type="file" accept="image/*" className="hidden"
                  onChange={e => handleFixedImage(key, e)} />
              </label>
            </div>
          ))}
        </div>

        {/* Custom images */}
        {customImages.length > 0 && (
          <div className="mb-3 space-y-2">
            <p className="text-xs font-semibold mb-1.5" style={{ color: 'var(--t2)' }}>Custom Images (position on canvas below)</p>
            {customImages.map(ci => (
              <div key={ci.id} className="flex items-center gap-3 px-3 py-2 rounded-xl"
                style={{ background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.2)' }}>
                <img src={ci.dataUrl} alt="" className="w-10 h-7 object-contain rounded"
                  style={{ background: '#fff' }} />
                <span className="text-xs flex-1 truncate" style={{ color: 'var(--gold)' }}>{ci.label}</span>
                <button onClick={() => setCustomImages(p => p.filter(x => x.id !== ci.id))}
                  style={{ color: 'var(--rose)' }}>
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Add custom image */}
        {addingImage ? (
          <div className="rounded-xl p-4 space-y-3" style={{ background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.25)' }}>
            <p className="text-xs font-bold" style={{ color: 'var(--gold)' }}>Add Custom Image</p>
            <div>
              <label className={lc} style={lcStyle}>Image Label</label>
              <input className={ic} style={icStyle} placeholder="e.g. Project Logo, North Arrow…"
                value={pendingLabel} onChange={e => setPendingLabel(e.target.value)} />
            </div>
            <div>
              <label className={lc} style={lcStyle}>Image File</label>
              <label className="flex items-center gap-2 rounded-xl cursor-pointer px-3 py-2"
                style={{ background: pendingFile ? 'rgba(74,222,128,0.06)' : 'var(--s3)', border: `1.5px dashed ${pendingFile ? '#4ade80' : 'var(--b2)'}` }}>
                {pendingFile
                  ? <><CheckCircle2 className="w-3.5 h-3.5" style={{ color: '#4ade80' }} /><span className="text-xs truncate" style={{ color: '#4ade80' }}>{pendingFile.name}</span></>
                  : <><Upload className="w-3.5 h-3.5" style={{ color: 'var(--t2)' }} /><span className="text-xs" style={{ color: 'var(--t2)' }}>Select image file</span></>}
                <input type="file" accept="image/*" className="hidden"
                  onChange={e => setPendingFile(e.target.files?.[0] || null)} />
              </label>
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" onClick={cancelAddCustom} size="sm">Cancel</Button>
              <Button onClick={confirmAddCustom} disabled={!pendingFile} size="sm">
                <ImagePlus className="w-3.5 h-3.5" /> Add to Canvas
              </Button>
            </div>
          </div>
        ) : (
          <button onClick={startAddCustom}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold"
            style={{ background: 'rgba(245,158,11,0.08)', color: 'var(--gold)', border: '1px dashed rgba(245,158,11,0.4)' }}>
            <ImagePlus className="w-3.5 h-3.5" /> Add Custom Image
          </button>
        )}
      </Section>

      {/* ── Preview ── */}
      <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        <div className="flex items-center gap-3 px-5 py-4" style={{ borderBottom: '1px solid var(--b1)' }}>
          <FileUp className="w-4 h-4" style={{ color: 'var(--em-lt)' }} />
          <div className="flex-1">
            <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Interactive Preview</p>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>
              {previewLayout
                ? 'Click any cell to edit its value or formatting. Drag images to reposition.'
                : 'Build a preview first to enable direct cell editing and image placement.'}
            </p>
          </div>
          <Button onClick={handlePreview} loading={previewLoading} size="sm">
            <Eye className="w-3.5 h-3.5" />
            {previewLayout ? 'Refresh Preview' : 'Build Preview'}
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
            />
          </div>
        ) : (
          <div className="p-8 text-center">
            <Eye className="w-10 h-10 mx-auto mb-3 opacity-20" style={{ color: 'var(--t2)' }} />
            <p className="text-sm" style={{ color: 'var(--t2)' }}>Click "Build Preview" to open the interactive canvas</p>
          </div>
        )}
      </div>

      {/* ── Generate ── */}
      <div className="rounded-2xl p-5 flex flex-wrap items-center gap-4"
        style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        <Button onClick={handleGenerate} disabled={!previewLayout} loading={generating} size="lg">
          <FileSpreadsheet className="w-4 h-4" />
          {generating ? 'Generating…' : 'Generate Cover Sheet'}
        </Button>
        {!previewLayout && (
          <p className="text-xs" style={{ color: 'var(--t2)' }}>Build a preview first to confirm the layout.</p>
        )}
        {result && (
          <Button onClick={handleDownload} size="lg"
            style={{ background: 'linear-gradient(135deg,#4ade80,#22c55e)', color: '#000' }}>
            <Download className="w-4 h-4" /> Download {result.filename}
          </Button>
        )}
        {result && (
          <p className="text-xs" style={{ color: '#4ade80' }}>{result.message}</p>
        )}
      </div>
    </div>
  );
}
