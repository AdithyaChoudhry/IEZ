/**
 * Process Data Requisition Generator
 * Upload an IODB, pick an instrument type, match tags, optionally seed with IODB process
 * data, then generate a process data requisition document for Process Engineering.
 */
import { useState, useMemo, useEffect, useRef } from 'react';
import { ClipboardList, Upload, Download, CheckCircle2, ChevronDown, ChevronRight } from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import ProjectSelector from '../ui/ProjectSelector';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import SharedIodbCard from '../ui/SharedIodb';
import ProcessDataAllTypes from './ProcessDataAllTypes';

interface InstrumentType {
  key: string;
  label: string;
  category: string;
  subtypes: string[];
  verified_subtypes?: string[];
}

interface ProfileField {
  name: string;
  header: string;
  mandatory: boolean;
  unit: string;
  category: string;
  default_selected: boolean;
  source_annexure_label: string;
}

interface ProfileResponse {
  instrument_type: string;
  subtype: string;
  verified: boolean;
  template: string;
  sheet: string;
  note: string;
  fields: ProfileField[];
  default_fields: string[];
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
  process_fields: { name: string; header: string; mandatory: boolean }[];
  default_fields?: string[];
  warnings: string[];
  subtype?: string;
  unresolved_tags?: (MatchedTag & { reason?: string })[];   // records of the type whose subtype is not established (not in matched_tags)
  excluded_counts?: Record<string, number>;
}

interface GenerateResponse {
  filename: string;
  message: string;
  registry?: unknown;
  warnings?: string[];
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
  const [mode, setMode] = useState<'single' | 'all'>('single');   // Individual Instrument Type (default) / All Instrument Types
  const matchSeq = useRef(0);                                     // only the latest tag search may fill Step 3
  const matchAbort = useRef<AbortController | null>(null);

  const [matchResult, setMatchResult] = useState<MatchTagsResponse | null>(null);
  const [selectedTagNos, setSelectedTagNos] = useState<string[]>([]);
  const [tagSearch, setTagSearch] = useState('');

  const [selectedFieldNames, setSelectedFieldNames] = useState<string[]>([]);
  // The datasheet profile of the chosen type / subtype (the backend is the source of the defaults), and the selection
  // the user made for each type / subtype during this session.
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [selectionByKey, setSelectionByKey] = useState<Record<string, string[]>>({});
  const [showOptional, setShowOptional] = useState(false);
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
  const profileKey = `${selectedTypeKey}|${selectedSubtype}`;

  const updateSelection = (names: string[]) => {
    setSelectedFieldNames(names);
    setSelectionByKey((prev) => ({ ...prev, [profileKey]: names }));
  };

  // Load the verified default parameters whenever the instrument type or subtype changes. Each type / subtype keeps
  // its own selection for the session; a type seen for the first time starts from its recommended defaults.
  useEffect(() => {
    setProfile(null);
    setProfileError(null);
    setShowOptional(false);
    if (!selectedTypeKey || isCustomType) { setSelectedFieldNames([]); return; }
    let cancelled = false;
    api
      .get<ProfileResponse>('/process-data/profile', {
        params: { instrument_type: selectedTypeKey, ...(selectedSubtype ? { subtype: selectedSubtype } : {}) },
      })
      .then((r) => {
        if (cancelled) return;
        setProfile(r.data);
        setSelectedFieldNames(selectionByKey[profileKey] ?? r.data.default_fields);
      })
      .catch((err: any) => {
        if (!cancelled) setProfileError(err.response?.data?.detail || 'Failed to load the parameter profile');
      });
    return () => { cancelled = true; };
  }, [selectedTypeKey, selectedSubtype, isCustomType]); // eslint-disable-line react-hooks/exhaustive-deps

  const defaultFields = useMemo(
    () => (profile ? profile.fields.filter((f) => profile.default_fields.includes(f.name)) : []),
    [profile]);
  const optionalFields = useMemo(
    () => (profile ? profile.fields.filter((f) => !profile.default_fields.includes(f.name)) : []),
    [profile]);
  const optionalSelectedCount = optionalFields.filter((f) => selectedFieldNames.includes(f.name)).length;
  const hasVerifiedSubtypes = !!selectedType?.verified_subtypes?.some((s) => s);

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
    matchAbort.current?.abort();                                  // an outdated search is cancelled; its answer is ignored
    const ctl = new AbortController();
    matchAbort.current = ctl;
    const seq = ++matchSeq.current;
    setMatching(true);
    setError(null);
    setResult(null);
    setMatchResult(null);
    setSelectedTagNos([]);                                        // nothing from a previous type / subtype stays selected

    const formData = new FormData();
    formData.append('file', iodbFile);
    formData.append('instrument_type', selectedTypeKey);
    if (selectedSubtype) formData.append('subtype', selectedSubtype);

    try {
      const response = await api.post<MatchTagsResponse>('/process-data/match-tags', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        signal: ctl.signal,
      });
      if (seq !== matchSeq.current) return;
      setMatchResult(response.data);
      setSelectedTagNos(response.data.matched_tags.map((t) => t.tag_no));   // the verified tags only; review records stay unselected
      // The selection is driven by the profile effect above; this only fills an empty selection (e.g. profile failed to load).
      setSelectedFieldNames((prev) => (prev.length ? prev : response.data.default_fields ?? (response.data.process_fields || []).map((f) => f.name)));
      setTagSearch('');
    } catch (err: any) {
      if (seq !== matchSeq.current || err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
      setError(err.response?.data?.detail || 'Failed to match tags');
    } finally {
      if (seq === matchSeq.current) setMatching(false);
    }
  };

  // IODB uploaded and a type chosen: find the tags straight away, so Generate is available without extra clicks.
  useEffect(() => {
    if (iodbFile && selectedTypeKey) handleMatchTags();
  }, [iodbFile, selectedTypeKey, selectedSubtype]); // eslint-disable-line react-hooks/exhaustive-deps

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
  const canGenerate = selectedTagNos.length > 0 &&
    (isCustomType ? validCustomRows.length > 0 : selectedFieldNames.length > 0 && (!!profile || !!profileError));

  const toggleField = (name: string) =>
    updateSelection(selectedFieldNames.includes(name) ? selectedFieldNames.filter((n) => n !== name) : [...selectedFieldNames, name]);
  const restoreDefaults = () => updateSelection(profile ? [...profile.default_fields] : []);
  const selectAllParameters = () => updateSelection((profile?.fields ?? matchResult?.process_fields ?? []).map((f) => f.name));
  const clearOptional = () => updateSelection(selectedFieldNames.filter((n) => profile?.default_fields.includes(n)));

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
    if (!isCustomType) formData.append('selected_fields', JSON.stringify(selectedFieldNames));
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
  const processColumnCount = isCustomType ? validCustomRows.length * 4 : selectedFieldNames.length;
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
        <SharedIodbCard
          title="IODB Source File"
          icon={Upload}
          file={iodbFile}
          onChange={(f) => {
            matchAbort.current?.abort();                 // a search for the previous IODB must not fill the page
            matchSeq.current += 1;
            setIodbFile(f);
            setMatchResult(null);
            setSelectedTagNos([]);
            setResult(null);
          }}
        />
      </Card>

      {/* Selection mode: one instrument type (default) or every supported type found in the IODB */}
      <Card title="Instrument Selection Mode" description="Prepare one instrument type, or every supported instrument type in the IODB in one operation.">
        <div className="flex flex-wrap gap-4 text-sm" style={{ color: 'var(--t1)' }}>
          {([['single', 'Individual Instrument Type'], ['all', 'All Instrument Types (From IODB)']] as const).map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="pdr-mode" checked={mode === k} onChange={() => { setMode(k); setResult(null); setError(null); }} />{label}
            </label>))}
        </div>
      </Card>

      {mode === 'all' && <ProcessDataAllTypes iodbFile={iodbFile} />}

      {mode === 'single' && (<>
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
                onChange={(e) => { setSelectedSubtype(e.target.value); setMatchResult(null); setResult(null); setSelectedTagNos([]); }}
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
            {matchResult.subtype ? <> &middot; Subtype: <strong>{matchResult.subtype}</strong></> : null}
          </p>
          {matchResult.excluded_counts && Object.keys(matchResult.excluded_counts).length > 0 && (
            <p className="text-xs mb-2" style={{ color: 'var(--t2)' }}>
              Not shown (other subtypes): {Object.entries(matchResult.excluded_counts).map(([k, n]) => `${n} ${k}`).join(', ')}.
            </p>)}

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
          {(matchResult.unresolved_tags?.length ?? 0) > 0 && (
            <details className="mt-4" data-testid="unresolved-tags">
              <summary className="cursor-pointer text-sm font-medium text-amber-700">
                Needs classification review ({matchResult.unresolved_tags!.length}) — the IODB does not state their subtype, so they are not selected
              </summary>
              <p className="text-xs my-2" style={{ color: 'var(--t2)' }}>Tick a record only if you know it is a {selectedSubtype || 'matching'} instrument; it is then included in this requisition.</p>
              <div className="border border-amber-200 rounded-lg overflow-auto max-h-64">
                <table className="w-full text-xs whitespace-nowrap">
                  <tbody className="divide-y divide-gray-200">
                    {matchResult.unresolved_tags!.map((tag) => (
                      <tr key={`u-${tag.row_index}`}>
                        <td className="px-3 py-1.5 w-10"><input type="checkbox" checked={selectedTagNos.includes(tag.tag_no)} onChange={() => toggleTag(tag.tag_no)} aria-label={`Include ${tag.tag_no}`} /></td>
                        <td className="px-3 py-1.5">{tag.tag_no}</td>
                        <td className="px-3 py-1.5">{tag.equipment_description}</td>
                        <td className="px-3 py-1.5 text-amber-700">{tag.reason}</td>
                      </tr>))}
                  </tbody>
                </table>
              </div>
            </details>)}
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
        <Card title="Step 5 — Preview & Columns" description="The recommended parameters for this instrument are already selected - generate, or adjust them first.">
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
          {!isCustomType && profileError && (
            <p className="text-xs mt-3 text-red-500">{profileError}</p>
          )}
          {!isCustomType && profile && profile.fields.length > 0 && (
            <div className="mt-4 space-y-4" data-testid="parameter-selection">
              {profile.verified ? (
                <p className="text-xs" style={{ color: 'var(--t2)' }}>
                  Recommended parameters come from the verified datasheet <strong>{profile.template}</strong> ({profile.sheet}).
                  Units are the ones printed on that datasheet.
                </p>
              ) : (
                <Alert variant="warning" title="No verified datasheet profile for this type yet">
                  {profile.note} Choose the parameters to request below.
                </Alert>
              )}
              {profile.verified && profile.note && (
                <p className="text-xs" style={{ color: 'var(--t2)' }}>{profile.note}</p>
              )}
              {hasVerifiedSubtypes && !selectedSubtype && (
                <p className="text-xs text-amber-600">
                  Select a subtype in Step 2 to load its verified datasheet parameters.
                </p>
              )}

              {/* Default parameters - already selected */}
              <div>
                <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
                  <p className="text-sm font-medium" style={{ color: 'var(--t0)' }}>
                    {profile.verified ? 'Default Parameters — Automatically Selected' : 'Parameters'}
                    {' '}({defaultFields.filter((f) => selectedFieldNames.includes(f.name)).length} of {defaultFields.length} selected)
                  </p>
                  <div className="flex gap-2 flex-wrap">
                    <Button variant="ghost" size="sm" onClick={restoreDefaults}>Restore Recommended Defaults</Button>
                    <Button variant="ghost" size="sm" onClick={selectAllParameters}>Select All Available Parameters</Button>
                    {optionalFields.length > 0 && (
                      <Button variant="ghost" size="sm" onClick={clearOptional}>Clear Optional Selections</Button>
                    )}
                  </div>
                </div>
                <div className="border border-gray-200 rounded-lg p-3 max-h-80 overflow-auto grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">
                  {defaultFields.map((f) => (
                    <label key={f.name} className="flex items-start gap-2 text-sm cursor-pointer" style={{ color: 'var(--t1)' }}>
                      <input
                        type="checkbox"
                        checked={selectedFieldNames.includes(f.name)}
                        onChange={() => toggleField(f.name)}
                        className="w-4 h-4 mt-0.5 text-primary-600 border-gray-300 rounded"
                      />
                      <span>{f.header}</span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Additional parameters - optional, collapsed by default */}
              {optionalFields.length > 0 && (
                <div>
                  <button
                    type="button"
                    onClick={() => setShowOptional((v) => !v)}
                    className="flex items-center gap-1 text-sm font-medium"
                    style={{ color: 'var(--t0)' }}
                    aria-expanded={showOptional}
                  >
                    {showOptional ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    Additional Parameters — Optional ({optionalSelectedCount} of {optionalFields.length} selected)
                  </button>
                  {!showOptional && (
                    <Button variant="ghost" size="sm" className="mt-1" onClick={() => setShowOptional(true)}>Add Parameters</Button>
                  )}
                  {showOptional && (
                    <div className="border border-gray-200 rounded-lg p-3 mt-2 max-h-80 overflow-auto grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">
                      {optionalFields.map((f) => (
                        <label key={f.name} className="flex items-start gap-2 text-sm cursor-pointer" style={{ color: 'var(--t1)' }}>
                          <input
                            type="checkbox"
                            checked={selectedFieldNames.includes(f.name)}
                            onChange={() => toggleField(f.name)}
                            className="w-4 h-4 mt-0.5 text-primary-600 border-gray-300 rounded"
                          />
                          <span>{f.header}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {selectedFieldNames.length === 0 && (
                <p className="text-xs text-red-500">Select at least one process data column.</p>
              )}
            </div>
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
              {result.warnings && result.warnings.length > 0 && (
                <ul className="list-disc pl-5 text-sm text-amber-700 mb-4 space-y-0.5">
                  {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}
              <Button onClick={handleDownload} className="bg-green-600 hover:bg-green-700">
                <Download className="w-5 h-5" />
                Download {result.filename}
              </Button>
            </div>
          </div>
        </div>
      )}
      </>)}
    </div>
  );
}
