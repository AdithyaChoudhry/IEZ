/**
 * Smart Cover Sheet & Revision Control Generator
 * Generates standardized document control / revision sheets from the
 * LT_DS_coversheet.xlsx reference template, with an interactive preview
 * for adjusting cell formatting and image placement before generation.
 */
import { useState, useEffect } from 'react';
import {
  FileSpreadsheet,
  Upload,
  Download,
  Plus,
  Trash2,
  Save,
  Eye,
} from 'lucide-react';
import api from '@/services/api';
import CoverSheetPreview from './coversheet/CoverSheetPreview';
import type { CoverSheetLayout, ImageKey, ImagePlacement, CellOverride } from './coversheet/types';
import PageHeader from '../ui/PageHeader';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';

interface ProjectInfo {
  client: string;
  pmc: string;
  contractor: string;
  project_description: string;
  doc_title_short: string;
  doc_title_full: string;
  job_no: string;
  unit_no: string;
  project_no: string;
  doc_code: string;
  serial_no: string;
  page_no: string;
  doc_class: string;
  discipline: string;
}

interface RevisionEntry {
  rev_no: string;
  date: string;
  description: string;
  prepared_by: string;
  checked_by: string;
  approved_by: string;
}

interface PlacementState {
  x: number;
  y: number;
  width: number;
  height: number;
}

const MASTER_STORAGE_KEY = 'iez_coversheet_project_master';
const MAX_REVISIONS = 7;

const IMAGE_FIELDS: { key: ImageKey; label: string; required?: boolean }[] = [
  { key: 'client_logo', label: 'Client Logo' },
  { key: 'pmc_logo', label: 'PMC Logo' },
  { key: 'wabag_logo', label: 'WABAG Logo (replace, optional)' },
  { key: 'prepared_signature', label: 'Prepared By Signature' },
  { key: 'checked_signature', label: 'Checked By Signature' },
  { key: 'approved_signature', label: 'Approved By Signature' },
];

const emptyProjectInfo: ProjectInfo = {
  client: '',
  pmc: '',
  contractor: '',
  project_description: '',
  doc_title_short: '',
  doc_title_full: '',
  job_no: '',
  unit_no: '',
  project_no: '',
  doc_code: '',
  serial_no: '',
  page_no: '',
  doc_class: 'APPROVAL',
  discipline: 'INSTRUMENTATION',
};

const emptyRevision = (): RevisionEntry => ({
  rev_no: '',
  date: '',
  description: 'ISSUED FOR APPROVAL',
  prepared_by: '',
  checked_by: '',
  approved_by: '',
});

interface ProjectMaster {
  client: string;
  pmc: string;
  contractor: string;
  prepared_by: string;
  checked_by: string;
  approved_by: string;
}

export default function CoverSheetGenerator() {
  const [projectInfo, setProjectInfo] = useState<ProjectInfo>(emptyProjectInfo);
  const [revisions, setRevisions] = useState<RevisionEntry[]>([emptyRevision()]);
  const [images, setImages] = useState<Partial<Record<ImageKey, File>>>({});
  const [previewLoading, setPreviewLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<{ filename: string; message: string } | null>(null);
  const [masterSaved, setMasterSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [previewLayout, setPreviewLayout] = useState<CoverSheetLayout | null>(null);
  const [previewImages, setPreviewImages] = useState<Partial<Record<ImageKey, ImagePlacement>>>({});
  const [cellOverrides, setCellOverrides] = useState<Record<string, CellOverride>>({});
  const [imagePlacements, setImagePlacements] = useState<Partial<Record<ImageKey, PlacementState>>>({});

  // Load project master on mount
  useEffect(() => {
    const raw = localStorage.getItem(MASTER_STORAGE_KEY);
    if (raw) {
      try {
        const master: ProjectMaster = JSON.parse(raw);
        setProjectInfo((prev) => ({
          ...prev,
          client: master.client,
          pmc: master.pmc,
          contractor: master.contractor,
        }));
        setRevisions((prev) =>
          prev.map((r) => ({
            ...r,
            prepared_by: r.prepared_by || master.prepared_by,
            checked_by: r.checked_by || master.checked_by,
            approved_by: r.approved_by || master.approved_by,
          }))
        );
      } catch {
        // ignore malformed master data
      }
    }
  }, []);

  const handleProjectInfoChange = (field: keyof ProjectInfo, value: string) => {
    setProjectInfo((prev) => ({ ...prev, [field]: value }));
  };

  const handleRevisionChange = (index: number, field: keyof RevisionEntry, value: string) => {
    setRevisions((prev) =>
      prev.map((r, i) => (i === index ? { ...r, [field]: value } : r))
    );
  };

  const addRevision = () => {
    if (revisions.length >= MAX_REVISIONS) return;
    const last = revisions[revisions.length - 1];
    setRevisions((prev) => [
      ...prev,
      {
        ...emptyRevision(),
        prepared_by: last?.prepared_by || '',
        checked_by: last?.checked_by || '',
        approved_by: last?.approved_by || '',
      },
    ]);
  };

  const removeRevision = (index: number) => {
    if (revisions.length <= 1) return;
    setRevisions((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSaveMaster = () => {
    const last = revisions[revisions.length - 1];
    const master: ProjectMaster = {
      client: projectInfo.client,
      pmc: projectInfo.pmc,
      contractor: projectInfo.contractor,
      prepared_by: last?.prepared_by || '',
      checked_by: last?.checked_by || '',
      approved_by: last?.approved_by || '',
    };
    localStorage.setItem(MASTER_STORAGE_KEY, JSON.stringify(master));
    setMasterSaved(true);
    setTimeout(() => setMasterSaved(false), 2000);
  };

  const handleImageChange = (key: ImageKey, e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setImages((prev) => ({ ...prev, [key]: e.target.files![0] }));
    }
  };

  const buildDataPayload = () => ({
    project_info: projectInfo,
    revisions,
    image_placements: imagePlacements,
    cell_overrides: cellOverrides,
  });

  const appendImages = (formData: FormData) => {
    for (const [key, file] of Object.entries(images)) {
      if (file) formData.append(key, file);
    }
  };

  const handlePreview = async () => {
    setPreviewLoading(true);
    setResult(null);
    setError(null);

    const formData = new FormData();
    formData.append('data', JSON.stringify({ project_info: projectInfo, revisions }));
    appendImages(formData);

    try {
      const response = await api.post('/coversheet/preview', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setPreviewLayout(response.data.layout);
      setPreviewImages(response.data.images);
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Preview generation failed');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setResult(null);
    setError(null);

    const formData = new FormData();
    formData.append('data', JSON.stringify(buildDataPayload()));
    appendImages(formData);

    try {
      const response = await api.post('/coversheet/generate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(response.data);
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async () => {
    try {
      const response = await api.get('/coversheet/download', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', result?.filename || 'CoverSheet.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error: any) {
      setError(error.response?.data?.detail || 'Download failed');
    }
  };

  const inputClass =
    'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500';
  const labelClass = 'block text-sm font-medium text-gray-700 mb-1';

  return (
    <div className="space-y-6">
      <PageHeader
        icon={FileSpreadsheet}
        iconClassName="text-orange-500"
        title="Smart Cover Sheet & Revision Control Generator"
        description="Generate standardized document cover sheets with project information, logos, revision history, and approval details."
      />

      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}

      {/* Project Information */}
      <Card
        title="Project Information"
        description="Save Client / PMC / Contractor and the latest approval names as a Project Master so they auto-fill next time."
        actions={
          <Button variant="secondary" size="sm" onClick={handleSaveMaster}>
            <Save className="w-4 h-4" />
            {masterSaved ? 'Saved!' : 'Save as Project Master'}
          </Button>
        }
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className={labelClass}>Client</label>
            <input
              className={inputClass}
              value={projectInfo.client}
              onChange={(e) => handleProjectInfoChange('client', e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>PMC</label>
            <input
              className={inputClass}
              value={projectInfo.pmc}
              onChange={(e) => handleProjectInfoChange('pmc', e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Contractor</label>
            <input
              className={inputClass}
              value={projectInfo.contractor}
              onChange={(e) => handleProjectInfoChange('contractor', e.target.value)}
            />
          </div>
          <div className="md:col-span-3">
            <label className={labelClass}>Project Description</label>
            <textarea
              className={inputClass}
              rows={2}
              value={projectInfo.project_description}
              onChange={(e) => handleProjectInfoChange('project_description', e.target.value)}
            />
          </div>
        </div>
      </Card>

      {/* Document Details */}
      <Card title="Document Details">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-3">
            <label className={labelClass}>Document Title (short, for header)</label>
            <input
              className={inputClass}
              value={projectInfo.doc_title_short}
              onChange={(e) => handleProjectInfoChange('doc_title_short', e.target.value)}
            />
          </div>
          <div className="md:col-span-3">
            <label className={labelClass}>Document Title (full)</label>
            <textarea
              className={inputClass}
              rows={2}
              value={projectInfo.doc_title_full}
              onChange={(e) => handleProjectInfoChange('doc_title_full', e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Document Class</label>
            <select
              className={inputClass}
              value={projectInfo.doc_class}
              onChange={(e) => handleProjectInfoChange('doc_class', e.target.value)}
            >
              <option value="APPROVAL">APPROVAL</option>
              <option value="IFC">IFC</option>
              <option value="IFA">IFA</option>
              <option value="INFORMATION">INFORMATION</option>
            </select>
          </div>
          <div>
            <label className={labelClass}>Discipline</label>
            <input
              className={inputClass}
              value={projectInfo.discipline}
              onChange={(e) => handleProjectInfoChange('discipline', e.target.value)}
            />
          </div>
        </div>
      </Card>

      {/* Document Control Numbers */}
      <Card title="Document Control Numbers">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <label className={labelClass}>Job Number</label>
            <input
              className={inputClass}
              value={projectInfo.job_no}
              onChange={(e) => handleProjectInfoChange('job_no', e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Unit Number</label>
            <input
              className={inputClass}
              value={projectInfo.unit_no}
              onChange={(e) => handleProjectInfoChange('unit_no', e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Project Number</label>
            <input
              className={inputClass}
              value={projectInfo.project_no}
              onChange={(e) => handleProjectInfoChange('project_no', e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Document Code</label>
            <input
              className={inputClass}
              value={projectInfo.doc_code}
              onChange={(e) => handleProjectInfoChange('doc_code', e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Serial Number</label>
            <input
              className={inputClass}
              value={projectInfo.serial_no}
              onChange={(e) => handleProjectInfoChange('serial_no', e.target.value)}
            />
          </div>
          <div>
            <label className={labelClass}>Page Number</label>
            <input
              className={inputClass}
              placeholder="e.g. 1 of 3"
              value={projectInfo.page_no}
              onChange={(e) => handleProjectInfoChange('page_no', e.target.value)}
            />
          </div>
        </div>
      </Card>

      {/* Revision Control */}
      <Card
        title="Revision Control"
        description={`Enter revisions oldest first (Rev 0 at the top). The current revision is the last row. Maximum ${MAX_REVISIONS} revisions.`}
        actions={
          <Button size="sm" onClick={addRevision} disabled={revisions.length >= MAX_REVISIONS}>
            <Plus className="w-4 h-4" />
            Add Revision
          </Button>
        }
      >
        <div className="space-y-3">
          {revisions.map((rev, index) => (
            <div
              key={index}
              className="grid grid-cols-2 md:grid-cols-7 gap-2 items-end border border-gray-100 rounded-lg p-3"
            >
              <div>
                <label className={labelClass}>Rev No.</label>
                <input
                  className={inputClass}
                  value={rev.rev_no}
                  onChange={(e) => handleRevisionChange(index, 'rev_no', e.target.value)}
                />
              </div>
              <div>
                <label className={labelClass}>Date</label>
                <input
                  className={inputClass}
                  placeholder="DD.MM.YYYY"
                  value={rev.date}
                  onChange={(e) => handleRevisionChange(index, 'date', e.target.value)}
                />
              </div>
              <div className="md:col-span-2">
                <label className={labelClass}>Description</label>
                <input
                  className={inputClass}
                  value={rev.description}
                  onChange={(e) => handleRevisionChange(index, 'description', e.target.value)}
                />
              </div>
              <div>
                <label className={labelClass}>Prepared By</label>
                <input
                  className={inputClass}
                  value={rev.prepared_by}
                  onChange={(e) => handleRevisionChange(index, 'prepared_by', e.target.value)}
                />
              </div>
              <div>
                <label className={labelClass}>Checked By</label>
                <input
                  className={inputClass}
                  value={rev.checked_by}
                  onChange={(e) => handleRevisionChange(index, 'checked_by', e.target.value)}
                />
              </div>
              <div className="flex gap-2">
                <div className="flex-1">
                  <label className={labelClass}>Approved By</label>
                  <input
                    className={inputClass}
                    value={rev.approved_by}
                    onChange={(e) => handleRevisionChange(index, 'approved_by', e.target.value)}
                  />
                </div>
                <button
                  onClick={() => removeRevision(index)}
                  disabled={revisions.length <= 1}
                  className="text-red-500 hover:text-red-700 disabled:text-gray-300 p-2 self-end"
                  title="Remove revision"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Images & Signatures */}
      <Card
        title="Logos & Signatures"
        description="All fields are optional. Upload images here, then use the preview below to drag, resize, and position them on the cover sheet."
      >
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {IMAGE_FIELDS.map(({ key, label }) => (
            <div key={key}>
              <label className={labelClass}>{label}</label>
              <input
                type="file"
                accept="image/*"
                onChange={(e) => handleImageChange(key, e)}
                className="block w-full text-sm border border-gray-300 rounded-lg cursor-pointer bg-gray-50"
              />
              {images[key] && (
                <p className="text-xs text-green-600 mt-1">✓ {images[key]!.name}</p>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* Preview */}
      <Card className="flex flex-col md:flex-row items-center gap-4">
        <Button onClick={handlePreview} loading={previewLoading} className="bg-blue-600 hover:bg-blue-700">
          <Eye className="w-4 h-4" />
          {previewLoading ? 'Building Preview...' : 'Generate Preview'}
        </Button>
        <p className="text-sm text-gray-500">
          Preview the cover sheet exactly as it will appear, then adjust formatting and image
          placement below before generating the final file.
        </p>
      </Card>

      {previewLayout && (
        <Card title="Preview & Adjustments">
          <CoverSheetPreview
            layout={previewLayout}
            images={previewImages}
            cellOverrides={cellOverrides}
            onCellOverridesChange={setCellOverrides}
            imagePlacements={imagePlacements}
            onImagePlacementsChange={setImagePlacements}
          />
        </Card>
      )}

      {/* Generate */}
      <Card className="flex flex-col md:flex-row items-center gap-4">
        <Button onClick={handleGenerate} disabled={!previewLayout} loading={generating}>
          <Upload className="w-4 h-4" />
          {generating ? 'Generating...' : 'Generate Final Cover Sheet'}
        </Button>
        {!previewLayout && (
          <p className="text-sm text-gray-500">Generate a preview first.</p>
        )}

        {result && (
          <Button onClick={handleDownload} className="bg-green-600 hover:bg-green-700">
            <Download className="w-4 h-4" />
            Download {result.filename}
          </Button>
        )}
      </Card>
    </div>
  );
}
