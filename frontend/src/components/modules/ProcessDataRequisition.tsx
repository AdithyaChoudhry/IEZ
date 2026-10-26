/**
 * Process Data Requisition Generator
 * Upload an IODB, pick an instrument type, match tags, optionally seed with IODB process
 * data, then generate a process data requisition document for Process Engineering.
 */
import { useState, useMemo, useEffect } from 'react';
import { ClipboardList, Upload, Download, CheckCircle2 } from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import ProjectSelector from '../ui/ProjectSelector';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import FileUploadCard from '../ui/FileUploadCard';

interface InstrumentType {
  key: string;
  label: string;
  category: string;
  subtypes: string[];
}

interface MatchedTag {
  tag_no: string;
  equipment_description: string;
  pid_no: string;
  service: string;
  equipment_no: string;
  line: string;
  line_size: string;
  row_index: number;
}

interface MatchTagsResponse {
  instrument_type: string;
  matched_tags: MatchedTag[];
  tag_count: number;
  identification_columns: string[];
  process_columns: string[];
  warnings: string[];
}

interface GenerateResponse {
  filename: string;
  message: string;
  registry?: unknown;
}

interface CustomRow {
  parameter: string;
  unit: string;
}

const emptyCustomRow = (): CustomRow => ({ parameter: '', unit: '' });

export default function ProcessDataRequisition() {
  const [instrumentTypes, setInstrumentTypes] = useState<InstrumentType[]>([]);
  const [typesError, setTypesError] = useState<string | null>(null);

  const [iodbFile, setIodbFile] = useState<File | null>(null);
  const [selectedTypeKey, setSelectedTypeKey] = useState('');
  const [selectedSubtype, setSelectedSubtype] = useState('');

  const [matchResult, setMatchResult] = useState<MatchTagsResponse | null>(null);
  const [selectedTagNos, setSelectedTagNos] = useState<string[]>([]);
  const [tagSearch, setTagSearch] = useState('');

  const [useIodbValues, setUseIodbValues] = useState(false);
  const [customRows, setCustomRows] = useState<CustomRow[]>([]);
  const [customName, setCustomName] = useState('');

  const [matching, setMatching] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<{ instrument_types: InstrumentType[] }>('/process-data/instrument-types')
      .then((r) => setInstrumentTypes(r.data.instrument_types))
      .catch((err: any) => setTypesError(err.response?.data?.detail || 'Failed to load instrument types'));
  }, []);

  const selectedType = useMemo(
    () => instrumentTypes.find((t) => t.key === selectedTypeKey) || null,
    [instrumentTypes, selectedTypeKey]
  );
  const isCustomType = selectedType?.category === 'Custom';

  const groupedTypes = useMemo(() => {
    const groups: Record<string, InstrumentType[]> = {};
    instrumentTypes.forEach((t) => {
      if (!groups[t.category]) groups[t.category] = [];
      groups[t.category].push(t);
    });
    return groups;
  }, [instrumentTypes]);

  const handleMatchTags = async () => {
    if (!iodbFile || !selectedTypeKey) return;
    setMatching(true);
    setError(null);
    setResult(null);
    setMatchResult(null);

    const formData = new FormData();
    formData.append('file', iodbFile);
    formData.append('instrument_type', selectedTypeKey);
    if (selectedSubtype) formData.append('subtype', selectedSubtype);

    try {
      const response = await api.post<MatchTagsResponse>('/process-data/match-tags', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setMatchResult(response.data);
      setSelectedTagNos(response.data.matched_tags.map((t) => t.tag_no));
      setTagSearch('');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to match tags');
    } finally {
      setMatching(false);
    }
  };

  const filteredTags = useMemo(() => {
    if (!matchResult) return [];
    if (!tagSearch.trim()) return matchResult.matched_tags;
    const q = tagSearch.toLowerCase();
    return matchResult.matched_tags.filter((t) =>
      [t.tag_no, t.service, t.pid_no, t.equipment_no, t.equipment_description, t.line]
        .some((v) => (v || '').toLowerCase().includes(q)));
  }, [matchResult, tagSearch]);

  const toggleTag = (tagNo: string) => {
    setSelectedTagNos((prev) =>
      prev.includes(tagNo) ? prev.filter((t) => t !== tagNo) : [...prev, tagNo]
    );
  };

  // Select All acts on the rows currently shown (all of them when no search is active).
  const selectAllTags = () => {
    setSelectedTagNos((prev) => Array.from(new Set([...prev, ...filteredTags.map((t) => t.tag_no)])));
  };
  const clearAllTags = () => setSelectedTagNos([]);

  const addCustomRow = () => setCustomRows((prev) => [...prev, emptyCustomRow()]);
  const removeCustomRow = (idx: number) => setCustomRows((prev) => prev.filter((_, i) => i !== idx));
  const updateCustomRow = (idx: number, field: keyof CustomRow, value: string) => {
    setCustomRows((prev) => prev.map((row, i) => (i === idx ? { ...row, [field]: value } : row)));
  };

  const validCustomRows = customRows.filter((r) => r.parameter.trim());
  const canGenerate = selectedTagNos.length > 0 && (!isCustomType || validCustomRows.length > 0);

  const handleGenerate = async () => {
    if (!iodbFile || !selectedTypeKey || !canGenerate) return;
    setGenerating(true);
    setError(null);

    const formData = new FormData();
    formData.append('iodb_file', iodbFile);
    formData.append('instrument_type', selectedTypeKey);
    if (selectedSubtype) formData.append('subtype', selectedSubtype);
    formData.append('selected_tags', JSON.stringify(selectedTagNos));
    formData.append('use_iodb_values', String(useIodbValues));
    if (isCustomType) {
      formData.append('custom_fields', JSON.stringify(validCustomRows));
      formData.append('custom_name', customName.trim());
    }

    try {
      const response = await api.post<GenerateResponse>('/process-data/generate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async () => {
    try {
      const response = await api.get('/process-data/download', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', result?.filename || 'Process_Data_Requisition.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Download failed');
    }
  };

  // each custom parameter becomes Minimum / Normal / Maximum / Remarks columns
  const processColumnCount = isCustomType ? validCustomRows.length * 4 : matchResult?.process_columns.length || 0;
  const totalColumns = 8 + processColumnCount;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={ClipboardList}
        iconClassName="text-teal-500"
        title="Process Data Requisition"
        description="Request process data from Process Engineering for selected instrument types."
      />
      <ProjectSelector />

      {typesError && <Alert variant="error" title="Error" onClose={() => setTypesError(null)}>{typesError}</Alert>}
      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}
      {matchResult && matchResult.warnings.length > 0 && (
        <Alert variant="warning" title="Warnings">
          <ul className="list-disc pl-4 space-y-0.5">
            {matchResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </Alert>
      )}

      {/* Step 1: Upload IODB */}
      <Card title="Step 1 — Upload IODB" description="Upload the instrument database to source tags from.">
        <FileUploadCard
          title="IODB Source File"
          icon={Upload}
          file={iodbFile}
          onChange={(f) => {
            setIodbFile(f);
            setMatchResult(null);
            setResult(null);
          }}
        />
      </Card>

      {/* Step 2: Select Instrument Type */}
      <Card title="Step 2 — Select Instrument Type" description="Choose the instrument type to request process data for.">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--t2)' }}>
              Instrument Type
            </label>
            <select
              value={selectedTypeKey}
              onChange={(e) => {
                setSelectedTypeKey(e.target.value);
                setSelectedSubtype('');
                setMatchResult(null);
                setResult(null);
                setCustomRows([]);
                setSelectedTagNos([]);
              }}
              className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="">Select an instrument type...</option>
              {Object.entries(groupedTypes).map(([category, types]) => (
                <optgroup key={category} label={category}>
                  {types.map((t) => (
                    <option key={t.key} value={t.key}>{t.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>

          {selectedType && selectedType.subtypes.length > 0 && (
            <div>
              <label className="block text-xs font-semibold mb-1.5" style={{ color: 'var(--t2)' }}>
                Subtype
              </label>
              <select
                value={selectedSubtype}
                onChange={(e) => { setSelectedSubtype(e.target.value); setMatchResult(null); setResult(null); }}
                className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">Select a subtype...</option>
                {selectedType.subtypes.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        <Button
          onClick={handleMatchTags}
          disabled={!iodbFile || !selectedTypeKey}
          loading={matching}
          className="mt-4"
        >
          {matching ? 'Finding Tags...' : 'Find Matching Tags'}
        </Button>
      </Card>

      {/* Step 3: Tag table (custom types list every IODB tag) */}
      {matchResult && (
        <Card
          title="Step 3 — Select Tags"
          description="Choose which matched tags to include in the requisition."
        >
          <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
            <input
              type="text"
              placeholder="Search tag, service, P&ID, equipment, line..."
              value={tagSearch}
              onChange={(e) => setTagSearch(e.target.value)}
              className="flex-1 min-w-[180px] px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={selectAllTags}>Select All</Button>
              <Button variant="ghost" size="sm" onClick={clearAllTags}>Clear All</Button>
            </div>
          </div>

          <p className="text-sm text-gray-500 mb-2">
            Tags found: <strong>{matchResult.tag_count}</strong> &middot; Selected: <strong>{selectedTagNos.length}</strong>
          </p>

          <div className="border border-gray-200 rounded-lg overflow-auto max-h-96">
            <table className="w-full text-sm whitespace-nowrap">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-3 py-2 w-10"></th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">TAG NO</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">EQUIPMENT DESCRIPTION</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">P&amp;ID NO.</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">SERVICE</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">EQUIPMENT NO</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">LINE</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">LINE SIZE</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {filteredTags.map((tag) => (
                  <tr key={tag.row_index} className="hover:bg-gray-50">
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={selectedTagNos.includes(tag.tag_no)}
                        onChange={() => toggleTag(tag.tag_no)}
                        className="w-4 h-4 text-primary-600 border-gray-300 rounded"
                      />
                    </td>
                    <td className="px-3 py-2 text-gray-700">{tag.tag_no}</td>
                    <td className="px-3 py-2 text-gray-700">{tag.equipment_description}</td>
                    <td className="px-3 py-2 text-gray-700">{tag.pid_no}</td>
                    <td className="px-3 py-2 text-gray-700">{tag.service}</td>
                    <td className="px-3 py-2 text-gray-700">{tag.equipment_no}</td>
                    <td className="px-3 py-2 text-gray-700">{tag.line}</td>
                    <td className="px-3 py-2 text-gray-700">{tag.line_size}</td>
                  </tr>
                ))}
                {filteredTags.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-3 py-8 text-center text-gray-400">
                      No tags match the current search
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Step 4: Options */}
      {matchResult && !isCustomType && (
        <Card title="Step 4 — Options" description="Choose how to seed the requisition.">
          <label className="flex items-center gap-2 cursor-pointer text-sm" style={{ color: 'var(--t1)' }}>
            <input
              type="checkbox"
              checked={useIodbValues}
              onChange={(e) => setUseIodbValues(e.target.checked)}
              className="w-4 h-4 text-primary-600 border-gray-300 rounded"
            />
            Use available IODB process data as initial values
          </label>
        </Card>
      )}

      {/* Step 4b: Custom fields editor */}
      {matchResult && isCustomType && (
        <Card
          title="Step 4b — Custom Process Parameters"
          description="Each parameter becomes blank Minimum / Normal / Maximum / Remarks columns for the Process team."
        >
          <div className="space-y-2">
            <input
              type="text"
              placeholder="Analyzer / instrument name (e.g. H2O2 Analyzer)"
              value={customName}
              onChange={(e) => setCustomName(e.target.value)}
              className="w-full mb-2 px-2 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            {customRows.map((row, idx) => (
              <div key={idx} className="grid grid-cols-1 md:grid-cols-5 gap-2 items-center">
                <input
                  type="text"
                  placeholder="Process parameter (e.g. Residual Hydrogen Peroxide)"
                  value={row.parameter}
                  onChange={(e) => updateCustomRow(idx, 'parameter', e.target.value)}
                  className="md:col-span-3 px-2 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <input
                  type="text"
                  placeholder="Unit (e.g. mg/L)"
                  value={row.unit}
                  onChange={(e) => updateCustomRow(idx, 'unit', e.target.value)}
                  className="px-2 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
                <button
                  onClick={() => removeCustomRow(idx)}
                  className="px-2 text-gray-400 hover:text-red-500 text-left"
                  aria-label="Remove parameter"
                >
                  &times;
                </button>
              </div>
            ))}
            {customRows.length === 0 && (
              <p className="text-sm text-gray-400">No custom parameters added yet.</p>
            )}
          </div>
          <Button variant="secondary" size="sm" onClick={addCustomRow} className="mt-3">
            + Add Parameter
          </Button>
        </Card>
      )}

      {/* Step 5: Preview */}
      {matchResult && (
        <Card title="Step 5 — Preview" description="Summary of the requisition that will be generated.">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div>
              <p className="text-xs" style={{ color: 'var(--t2)' }}>Instrument Type</p>
              <p className="font-semibold" style={{ color: 'var(--t0)' }}>{selectedType?.label}</p>
            </div>
            <div>
              <p className="text-xs" style={{ color: 'var(--t2)' }}>Tags Selected</p>
              <p className="font-semibold" style={{ color: 'var(--t0)' }}>{selectedTagNos.length} tags selected</p>
            </div>
            <div>
              <p className="text-xs" style={{ color: 'var(--t2)' }}>Identification Columns</p>
              <p className="font-semibold" style={{ color: 'var(--t0)' }}>8 identification columns</p>
            </div>
            <div>
              <p className="text-xs" style={{ color: 'var(--t2)' }}>Process Columns</p>
              <p className="font-semibold" style={{ color: 'var(--t0)' }}>{processColumnCount} process columns</p>
            </div>
          </div>
          <p className="text-sm mt-3" style={{ color: 'var(--t1)' }}>
            Total columns: <strong>{totalColumns}</strong>
          </p>
          {!isCustomType && matchResult.process_columns.length > 0 && (
            <details className="mt-3 text-sm" style={{ color: 'var(--t1)' }}>
              <summary className="cursor-pointer font-medium">Process data columns to be requested</summary>
              <ol className="list-decimal pl-6 mt-2 columns-1 md:columns-2 gap-6">
                {matchResult.process_columns.map((c) => <li key={c}>{c}</li>)}
              </ol>
            </details>
          )}
        </Card>
      )}

      {/* Generate */}
      {matchResult && (
        <Button
          onClick={handleGenerate}
          disabled={!canGenerate}
          loading={generating}
          size="lg"
          fullWidth
          className="text-lg py-4"
        >
          <ClipboardList className="w-6 h-6" />
          {generating ? 'Generating...' : 'Generate Process Data Requisition'}
        </Button>
      )}

      {/* Result */}
      {result && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <CheckCircle2 className="w-12 h-12 text-green-500 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="text-xl font-bold text-green-800 mb-2">Process Data Requisition Generated!</h3>
              <p className="text-green-700 mb-4">{result.message}</p>
              <Button onClick={handleDownload} className="bg-green-600 hover:bg-green-700">
                <Download className="w-5 h-5" />
                Download {result.filename}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
