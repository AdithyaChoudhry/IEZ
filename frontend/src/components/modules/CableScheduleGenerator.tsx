/**
 * Cable Schedule Generator
 * Upload IODB + Cable Schedule template, pick JB/Tag columns, preview JB summary, generate.
 */
import { useEffect, useRef, useState } from 'react';
import { Cable, Upload, FileText, CheckCircle2 } from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import ProjectSelector from '../ui/ProjectSelector';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';
import FileUploadCard from '../ui/FileUploadCard';
import SharedIodbCard from '../ui/SharedIodb';
import OutputWorkbookOptions, { type OutputMode } from '../ui/OutputWorkbookOptions';
import ExtraCableSheets, { appendTerminals, TerminalSummary, type TerminalReport, type TerminalSource } from './cableschedule/ExtraCableSheets';
import ScopeFilters, { DEFAULT_SCOPE, scopeParam, type ScopeSelection, type ScopeSummary } from './cableschedule/ScopeFilters';
import DrumScheduleGenerator from './cableschedule/DrumScheduleGenerator';
import GlandQuantityGenerator from './cableschedule/GlandQuantityGenerator';
import LugQuantityGenerator from './cableschedule/LugQuantityGenerator';
import JunctionBoxScheduleGenerator from './cableschedule/JunctionBoxScheduleGenerator';
import CableScheduleComplete from './cableschedule/CableScheduleComplete';
import { DeliverableCoverCard, DeliverableDownloads, useProject, type AppliedCover } from '../ui/DeliverableCover';
import HeaderConfirm, { type HeaderMeta } from './cableschedule/HeaderConfirm';
import { getCurrentProject } from '@/services/projectContext';

interface ColumnsResponse {
  columns: string[];
}

interface JBSummaryRow {
  junction_box: string;
  tag_count: number;
  tags?: string[];          // every tag of the JB, in IODB order (written consecutively in the schedule)
}

interface JBSummaryResponse {
  rows: JBSummaryRow[];
}

interface GenerateResponse {
  filename: string;
  message: string;
  output_mode?: OutputMode;
  sheets?: string[];   // sheets of the generated workbook, read from the output file
  extra_sheets?: string[] | null;
  terminals?: TerminalReport | null;
  scope?: { selection: ScopeSelection; summary: ScopeSummary; notes: string[] } | null;
  extra_warnings?: string[] | null;
  cover?: AppliedCover | null;
  header?: { values: Record<string, string>; sources: Record<string, string>; sheets: Record<string, { mode: string }> } | null;
}

export default function CableScheduleGenerator() {
  const [iodbFile, setIodbFile] = useState<File | null>(null);
  const [templateFile, setTemplateFileState] = useState<File | null>(null);
  // Explicit output state - drives the preview, the generated workbook and the download (default = behaviour before the option existed).
  const [cableOutputMode, setCableOutputMode] = useState<OutputMode>('WITH_SUMMARY');
  const [columns, setColumns] = useState<string[]>([]);
  const [jbColumn, setJbColumn] = useState('');
  const [tagColumn, setTagColumn] = useState('');
  const [jbSummary, setJbSummary] = useState<JBSummaryRow[] | null>(null);
  const [selectedJbs, setSelectedJbs] = useState<string[]>([]);
  const [openJb, setOpenJb] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  // Instrument Cable Schedule group: the schedule (default on) + optional MCC DI / MCC DO / VFD / MOV / LCP sheets
  const [view, setView] = useState<'schedule' | 'drum' | 'gland' | 'lug' | 'jb' | 'complete'>('schedule');
  const [includeSchedule, setIncludeSchedule] = useState(true);
  const [extraSheets, setExtraSheets] = useState<string[]>([]);
  const [terminals, setTerminals] = useState<TerminalSource>({ file: null, equipment: 'device', panel: 'none' });
  const [coverTemplate, setCoverTemplate] = useState<File | null>(null);
  // AREA / AREA CODE / STATUS scope of the next generation; `eligible` = records it leaves (null while being counted)
  const [scope, setScope] = useState<ScopeSelection>(DEFAULT_SCOPE);
  const [eligible, setEligible] = useState<number | null>(null);
  const changeScope = (s: ScopeSelection) => { setScope(s); setJbSummary(null); setResult(null); };

  const [loadingColumns, setLoadingColumns] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Header details (approved Cable Schedule header): taken from the linked Cover Sheet; the form below appears only for what it cannot supply.
  const project = useProject();
  const [headerMeta, setHeaderMeta] = useState<HeaderMeta | null>(null);
  const [headerValues, setHeaderValues] = useState<Record<string, string>>({});
  const [headerError, setHeaderError] = useState<string | null>(null);
  const headerRef = useRef<HTMLDivElement | null>(null);
  // Confirmed details belong to one project + cover: another project or cover template invalidates them.
  useEffect(() => { setHeaderMeta(null); setHeaderValues({}); setHeaderError(null); }, [project, coverTemplate]);
  useEffect(() => { if (headerMeta) headerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, [headerMeta]);

  const handleLoadColumns = async () => {
    if (!iodbFile) return;
    setLoadingColumns(true);
    setError(null);
    setColumns([]);
    setJbColumn('');
    setTagColumn('');
    setJbSummary(null);
    setResult(null);

    const formData = new FormData();
    formData.append('file', iodbFile);

    try {
      const response = await api.post<ColumnsResponse>('/cable-schedule/columns', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setColumns(response.data.columns);

      // Pre-select likely JB/Tag columns
      // the plain heading wins; a "PREV TAG" / "PREV JUNCTION BOX" history column is never preselected
      const plain = (c: string) => c.toUpperCase().replace(/[^A-Z0-9]+/g, ' ').trim();
      const guess = (names: string[], word: string) =>
        names.map((n) => response.data.columns.find((c) => plain(c) === n)).find(Boolean)
        ?? response.data.columns.find((c) => plain(c).includes(word) && !/\b(PREV|PREVIOUS|OLD)\b/.test(plain(c)) && !plain(c).includes('CABLE'));
      const jbGuess = guess(['JUNCTION BOX TAG NO', 'JUNCTION BOX TAG', 'JB TAG NO', 'JUNCTION BOX NO', 'JUNCTION BOX'], 'JUNCTION');
      const tagGuess = guess(['TAG NO', 'TAG NUMBER'], 'TAG');
      if (jbGuess) setJbColumn(jbGuess);
      if (tagGuess) setTagColumn(tagGuess);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to read IODB columns');
    } finally {
      setLoadingColumns(false);
    }
  };

  const handlePreview = async () => {
    if (!iodbFile || !jbColumn || !tagColumn) return;
    setLoadingPreview(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', iodbFile);
    formData.append('jb_column', jbColumn);
    formData.append('tag_column', tagColumn);
    formData.append('output_mode', cableOutputMode);
    formData.append('scope_filters', scopeParam(scope));

    try {
      const response = await api.post<JBSummaryResponse>('/cable-schedule/preview', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setJbSummary(response.data.rows);
      setSelectedJbs(response.data.rows.map(r => r.junction_box));
      setOpenJb(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to build junction box summary');
    } finally {
      setLoadingPreview(false);
    }
  };

  // A result belongs to one template + one mode: changing either clears it so the download always matches the preview.
  const setTemplateFile = (f: File | null) => { setTemplateFileState(f); setResult(null); };
  const changeOutputMode = (m: OutputMode) => { setCableOutputMode(m); setResult(null); };
  const changeExtraSheets = (labels: string[]) => { setExtraSheets(labels); setResult(null); };
  const changeIncludeSchedule = (v: boolean) => { setIncludeSchedule(v); setResult(null); };
  const extraOnly = !includeSchedule && extraSheets.length > 0;

  const showHeaderForm = (meta: HeaderMeta, message: string | null = null) => {
    setHeaderMeta(meta);
    setHeaderError(message);
    // a contradictory cover value is offered for confirmation; typed values survive a refresh of the form
    setHeaderValues((cur) => {
      const next: Record<string, string> = {};
      for (const f of meta.fields) if (f.status !== 'ok') next[f.key] = cur[f.key] ?? (f.status === 'conflict' ? f.candidate : '');
      return next;
    });
  };

  const generateError = (err: any): string => {
    const st = err.response?.status;
    const detail = err.response?.data?.detail;
    return typeof detail === 'string' && detail ? detail
      : (detail && typeof detail === 'object' && detail.message) ? String(detail.message)
      : st === 502 || st === 503 ? `Generation failed: the server stopped while generating (error ${st}). Please try again; if it repeats, send the template so it can be checked.`
      : st === 504 || err.code === 'ECONNABORTED' ? 'Generation failed: the server took too long to respond (timeout). Please try again with fewer junction boxes selected.'
      : st === 413 ? 'Generation failed: the uploaded file is too large for the server.'
      : st ? `Generation failed (server error ${st}).` : `Generation failed: no response from the server (${err.message || 'network error'}).`;
  };

  /** Ask the server what the linked Cover Sheet supplies for the header. */
  const fetchHeaderMeta = async (): Promise<HeaderMeta> => {
    const fd = new FormData();
    const pid = getCurrentProject();
    if (pid) fd.append('project_id', pid);
    if (coverTemplate) fd.append('cover_template_file', coverTemplate);
    return (await api.post<HeaderMeta>('/cable-schedule/header-metadata', fd)).data;
  };

  const postGenerate = async (overrides?: Record<string, string>, fingerprint?: string) => {
    if (!iodbFile) return;
    setGenerating(true);
    setError(null);
    setHeaderError(null);

    const formData = new FormData();
    formData.append('iodb_file', iodbFile);
    if (templateFile) formData.append('template_file', templateFile);
    formData.append('jb_column', jbColumn);
    formData.append('tag_column', tagColumn);
    formData.append('output_mode', cableOutputMode);
    formData.append('extra_sheets', extraSheets.join(','));
    formData.append('include_schedule', String(includeSchedule));
    appendTerminals(formData, terminals);
    formData.append('scope_filters', scopeParam(scope));
    if (includeSchedule && jbSummary && selectedJbs.length < jbSummary.length) formData.append('selected_jbs', JSON.stringify(selectedJbs));
    if (coverTemplate) formData.append('cover_template_file', coverTemplate);
    if (overrides && Object.keys(overrides).length) {
      formData.append('header_overrides', JSON.stringify(overrides));
      formData.append('header_fingerprint', fingerprint || '');
    }

    try {
      const response = await api.post<GenerateResponse>('/cable-schedule/generate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 330000,                                    // just past the server proxy limit: never spin forever
      });
      setResult(response.data);
      setHeaderMeta(null);
    } catch (err: any) {
      const st = err.response?.status;
      const detail = err.response?.data?.detail;
      if (st === 422 && detail && typeof detail === 'object' && detail.code === 'HEADER_METADATA_INCOMPLETE') {
        showHeaderForm(detail.header as HeaderMeta, String(detail.message || ''));      // the server re-checked: show exactly what is still needed
      } else if (st === 409 && overrides) {
        try { showHeaderForm(await fetchHeaderMeta(), String(detail || 'The project or its cover sheet changed. Check the header details again.')); }
        catch { setError(generateError(err)); }
      } else {
        setError(generateError(err));
      }
    } finally {
      setGenerating(false);
    }
  };

  const handleGenerate = async () => {
    if (!iodbFile) return;
    if (includeSchedule && (!jbColumn || !tagColumn)) return;
    if (!includeSchedule && extraSheets.length === 0) return;
    setGenerating(true);
    setError(null);
    setResult(null);
    try {
      const meta = await fetchHeaderMeta();
      if (!meta.complete) {                                  // something the cover cannot supply: ask for exactly that
        showHeaderForm(meta);
        setGenerating(false);
        return;
      }
      setHeaderMeta(null);
    } catch (err: any) {
      setError(generateError(err));
      setGenerating(false);
      return;
    }
    await postGenerate();
  };

  const confirmHeader = async () => {
    if (!headerMeta) return;
    const overrides: Record<string, string> = {};
    for (const f of headerMeta.fields) if (f.status !== 'ok') overrides[f.key] = (headerValues[f.key] || '').trim();
    await postGenerate(overrides, headerMeta.fingerprint);
  };

  const handleDownload = async () => {
    try {
      const response = await api.get('/cable-schedule/download', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', result?.filename || 'Cable_Schedule.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Download failed');
    }
  };

  const handleDiagnostics = async () => {
    try {
      const response = await api.get('/cable-schedule/diagnostics', { responseType: 'blob' });
      const link = document.createElement('a');
      link.href = window.URL.createObjectURL(new Blob([response.data]));
      link.setAttribute('download', (result?.filename || 'Cable_Schedule.xlsx').replace(/\.[^.]+$/, '') + '_Diagnostics.xlsx');
      document.body.appendChild(link); link.click(); link.remove();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'The diagnostics could not be downloaded');
    }
  };

  const totalTags = jbSummary?.reduce((sum, r) => sum + r.tag_count, 0) || 0;

  const viewTabs = (
    <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-4 px-4 sm:mx-0 sm:px-0 sm:flex-wrap" data-testid="cable-views">
      {([['schedule', 'Cable Schedule'], ['drum', 'Drum Schedule Generator'], ['gland', 'Cable Gland Quantity Generator'], ['lug', 'Cable Lug Quantity Generator'], ['jb', 'Junction Box Schedule'], ['complete', 'Cable Schedule Complete ⭐']] as const).map(([k, label]) => (
        <button key={k} onClick={() => setView(k)} className="px-4 py-2 rounded-xl text-sm font-semibold whitespace-nowrap flex-shrink-0"
                style={{ background: view === k ? 'var(--em)' : 'var(--s3)', color: view === k ? '#fff' : 'var(--t0)', border: '1px solid var(--b1)' }}>
          {label}
        </button>
      ))}
    </div>
  );

  if (view === 'drum') {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={Cable}
          iconClassName="text-red-500"
          title="Drum Schedule Generator"
          description="Allocate the cables of the generated Cable Schedule against the drums of a Drum Master, drum by drum, with a running balance."
        />
        {viewTabs}
        <DrumScheduleGenerator />
      </div>
    );
  }

  if (view === 'complete') {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={Cable}
          iconClassName="text-red-500"
          title="Cable Schedule Complete"
          description="Generate Cable Schedule, I/O Summary, Gland Quantity and Cable Lug Quantity from one IODB."
        />
        {viewTabs}
        <CableScheduleComplete />
      </div>
    );
  }

  if (view === 'jb') {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={Cable}
          iconClassName="text-red-500"
          title="Junction Box Schedule Generator"
          description="Junction boxes, connected instruments, cables and terminal capacity from the generated Cable Schedule, on the standard Junction Box Schedule template."
        />
        {viewTabs}
        <JunctionBoxScheduleGenerator />
      </div>
    );
  }

  if (view === 'lug') {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={Cable}
          iconClassName="text-red-500"
          title="Cable Lug Quantity Generator"
          description="Physical cable quantities and cable lug quantities from the generated Cable Schedule, with an engineering view and a procurement view."
        />
        {viewTabs}
        <LugQuantityGenerator />
      </div>
    );
  }

  if (view === 'gland') {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={Cable}
          iconClassName="text-red-500"
          title="Cable Gland Quantity Generator"
          description="Gland quantities from the generated Cable Schedule, and an OD-based gland size advisor (Metric / NPT / BSP / ET)."
        />
        {viewTabs}
        <GlandQuantityGenerator />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Cable}
        iconClassName="text-red-500"
        title="Cable Schedule Generator"
        description="Generate a cable schedule grouped by junction box from your IODB and Cable Schedule template."
      />
      {viewTabs}
      <ProjectSelector />

      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}

      {/* File Uploads */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <SharedIodbCard
          title="IODB Source File"
          icon={Upload}
          file={iodbFile}
          onChange={(f) => {
            setIodbFile(f);
            setColumns([]);
            setJbSummary(null);
            setResult(null);
            setScope(DEFAULT_SCOPE);
          }}
        >
          <Button onClick={handleLoadColumns} disabled={!iodbFile} loading={loadingColumns} fullWidth className="mt-3 bg-blue-600 hover:bg-blue-700">
            {loadingColumns ? 'Loading Columns...' : 'Load Columns'}
          </Button>
        </SharedIodbCard>

        <FileUploadCard
          title="Cable Schedule Template"
          icon={FileText}
          file={templateFile}
          onChange={setTemplateFile}
          hint="Optional: leave empty to use the built-in iEZ default template (blank cover, standard header). Upload a template to use its own layout and cover."
        />
      </div>

      <ScopeFilters iodbFile={iodbFile} value={scope} onChange={changeScope} onEligible={setEligible} />

      <ExtraCableSheets
        scope={scopeParam(scope)}
        terminals={terminals}
        onTerminalsChange={(t) => { setTerminals(t); setResult(null); }}
        iodbFile={iodbFile}
        includeSchedule={includeSchedule}
        onIncludeScheduleChange={changeIncludeSchedule}
        selected={extraSheets}
        onSelectedChange={changeExtraSheets}
      />

      <OutputWorkbookOptions
        endpoint="/cable-schedule/composition"
        templateFile={templateFile}
        mode={cableOutputMode}
        onModeChange={changeOutputMode}
        summaryLabel="Cable Summary"
        listLabel="Cable Schedule"
        extraFields={{ extra_sheets: extraSheets.join(','), include_schedule: String(includeSchedule) }}
      />

      <DeliverableCoverCard docType="cable_schedule" customTemplate={coverTemplate} onCustomTemplate={(f) => { setCoverTemplate(f); setResult(null); }} />

      {extraOnly && (
        <Card title="Generate">
          <Button onClick={handleGenerate} disabled={!iodbFile || !eligible} loading={generating} size="lg" fullWidth className="text-lg py-4">
            <Cable className="w-6 h-6" />
            {generating ? 'Generating...' : `Generate ${extraSheets.join(' + ')}`}
          </Button>
        </Card>
      )}

      {/* JB/Tag Column mapping */}
      {includeSchedule && columns.length > 0 && (
        <Card title="Junction Box & Tag Column Mapping">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Junction Box Column</label>
              <select
                value={jbColumn}
                onChange={(e) => setJbColumn(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">Select column...</option>
                {columns.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Tag Number Column</label>
              <select
                value={tagColumn}
                onChange={(e) => setTagColumn(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              >
                <option value="">Select column...</option>
                {columns.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>

          <Button
            onClick={handlePreview}
            disabled={!jbColumn || !tagColumn}
            loading={loadingPreview}
            className="mt-4 bg-blue-600 hover:bg-blue-700"
          >
            {loadingPreview ? 'Building Summary...' : 'Preview Junction Box Summary'}
          </Button>
        </Card>
      )}

      {/* JB Summary */}
      {includeSchedule && jbSummary && (
        <Card title={`Junction Boxes (${selectedJbs.length} of ${jbSummary.length} selected · ${jbSummary.filter(r => selectedJbs.includes(r.junction_box)).reduce((n, r) => n + r.tag_count, 0)} of ${totalTags} tags)`}>
          <p className="text-xs mb-2" style={{ color: 'var(--t2)' }}>
            Every tag of a selected junction box is written, one after another (IODB order), each with TB 1-2-3, 4-5-6, ... at that JB.
          </p>
          <div className="flex gap-3 mb-2 text-xs">
            <button className="underline" style={{ color: 'var(--t1)' }} onClick={() => { setSelectedJbs(jbSummary.map(r => r.junction_box)); setResult(null); }}>Select all</button>
            <button className="underline" style={{ color: 'var(--t1)' }} onClick={() => { setSelectedJbs([]); setResult(null); }}>Clear</button>
          </div>
          <div className="border border-gray-200 rounded-lg overflow-auto max-h-96">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-3 py-2 w-8" />
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Junction Box</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-700">Tags</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {jbSummary.map((row) => {
                  const on = selectedJbs.includes(row.junction_box);
                  const open = openJb === row.junction_box;
                  return (
                    <tr key={row.junction_box} className="align-top hover:bg-gray-50">
                      <td className="px-3 py-2"><input type="checkbox" checked={on} aria-label={`Include ${row.junction_box}`}
                        onChange={() => { setSelectedJbs(s => on ? s.filter(x => x !== row.junction_box) : [...s, row.junction_box]); setResult(null); }} /></td>
                      <td className="px-3 py-2 text-gray-900 font-medium">{row.junction_box}</td>
                      <td className="px-3 py-2 text-gray-700">
                        <button className="underline" onClick={() => setOpenJb(open ? null : row.junction_box)}>{row.tag_count} tag{row.tag_count === 1 ? '' : 's'}</button>
                        {open && row.tags && <div className="mt-1 flex flex-wrap gap-1">{row.tags.map((t, i) => (
                          <span key={`${t}-${i}`} className="font-mono text-[11px] px-1.5 py-0.5 rounded" style={{ background: 'var(--s3)' }}>{t} · TB {3 * i + 1}-{3 * i + 3}</span>))}</div>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Generate */}
          <Button
            onClick={handleGenerate}
            disabled={selectedJbs.length === 0 || !eligible}
            loading={generating}
            size="lg"
            fullWidth
            className="text-lg py-4 mt-6"
          >
            <Cable className="w-6 h-6" />
            {generating ? 'Generating...' : 'Generate Cable Schedule'}
          </Button>
        </Card>
      )}

      {headerMeta && (
        <div ref={headerRef}>
          <HeaderConfirm
            meta={headerMeta}
            values={headerValues}
            onChange={(k, v) => setHeaderValues((cur) => ({ ...cur, [k]: v }))}
            onConfirm={confirmHeader}
            onCancel={() => { setHeaderMeta(null); setHeaderValues({}); setHeaderError(null); }}
            busy={generating}
            error={headerError}
          />
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-6">
          <div className="flex items-start gap-4">
            <CheckCircle2 className="w-12 h-12 text-green-500 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="text-xl font-bold text-green-800 mb-2">Cable Schedule Generated!</h3>
              <p className="text-green-700 mb-2">{result.message}</p>
              {result.sheets && (
                <p className="text-sm text-green-800 mb-4">
                  Workbook sheets: {result.sheets.join(' · ')}
                </p>
              )}
              {result.extra_warnings && result.extra_warnings.length > 0 && (
                <ul className="text-sm text-amber-700 mb-4 list-disc ml-5">
                  {result.extra_warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              )}
              {result.scope && (
                <div className="text-sm text-green-800 mb-3" data-testid="result-scope">
                  <p>Area: {result.scope.selection.areas?.join(', ') || 'All'} · Area code: {result.scope.selection.area_codes?.join(', ') || 'All'} ·
                    Tag status: {result.scope.selection.statuses?.join(', ') || 'All except deleted'}</p>
                  <p>Records used: {result.scope.summary.eligible} of {result.scope.summary.total}</p>
                  <button className="underline" onClick={handleDiagnostics}>Download diagnostics (excluded records, shared cables, terminal trace)</button>
                </div>
              )}
              {result.terminals && <div className="mb-4"><TerminalSummary report={result.terminals} /></div>}
              <p className="text-sm text-green-800 mb-2 font-mono">{result.filename}</p>
              <DeliverableDownloads module="cable_schedule" filename={result.filename} cover={result.cover} onExcel={handleDownload} />
              <p className="text-sm text-green-800 mt-3">
                This Cable Schedule is now the input of the Drum Schedule, Cable Gland Quantity and Cable Lug Quantity generators (tabs above).
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
