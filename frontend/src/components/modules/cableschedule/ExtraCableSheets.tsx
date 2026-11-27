/**
 * Instrument Cable Schedule group: choose the sheets of the workbook.
 *
 *   [x] Instrument Cable Schedule   (existing generator, unchanged)
 *   [ ] MCC DI  [ ] MCC DO  [ ] VFD  [ ] MOV  [ ] LCP
 *
 * Availability, counts, warnings and the row preview all come from the backend, computed from the IODB that will be
 * used for generation (nothing here is hard-coded). A sheet whose source data is missing is disabled with the reason.
 */
import { useEffect, useState } from 'react';
import { AlertTriangle, Eye, Loader2 } from 'lucide-react';
import api from '@/services/api';
import Card from '../../ui/Card';
import Button from '../../ui/Button';

export const EXTRA_LABELS = ['MCC DI', 'MCC DO', 'VFD', 'MOV', 'LCP'] as const;

/** The optional I/O Assignment and the confirmed terminal sources, added to a preview or generate request. */
export function appendTerminals(form: FormData, t: { file: File | null; equipment: string; panel: string }) {
  if (!t.file) return;
  form.append('io_assignment_file', t.file);
  form.append('terminal_options', JSON.stringify({ equipment: t.equipment, panel: t.panel }));
}
const KEYS: Record<string, string> = { 'MCC DI': 'mcc_di', 'MCC DO': 'mcc_do', VFD: 'vfd', MOV: 'mov', LCP: 'lcp' };

interface Availability {
  label: string;
  available: boolean;
  reason: string | null;
  records: number;
  devices: number;
  cables: number;
  warnings: string[];
}

interface PreviewSheet {
  label: string;
  available: boolean;
  reason: string | null;
  records: number;
  devices: number;
  cables: number;
  warnings: string[];
  rows: { sl: number; tag: string; description: string; cable: string; cable_size: string; signal: string; device: string }[];
}

export interface TerminalReport {
  assignment: { used: number; spare_ignored: number };
  total: Record<string, number>;
  sheets: ({ sheet: string; issues: string[] } & Record<string, any>)[];
  warnings: string[];
}
export interface TerminalSource { file: File | null; equipment: 'device' | 'ts'; panel: 'none' | 'ts' }

const COUNTS: [string, string][] = [['eligible', 'IODB signals'], ['resolved', 'Resolved'], ['partial', 'Partial'], ['unmatched', 'Unmatched'],
  ['conflicts', 'Conflicts'], ['equipment_available', 'Equipment-side terminals available'], ['panel_available', 'Panel-side terminals available']];

/** The terminal matching summary of the preview or of the generated workbook. */
export function TerminalSummary({ report }: { report: TerminalReport }) {
  const rows = [...report.sheets, { sheet: 'Total', issues: [], ...report.total }];
  return (
    <div className="space-y-1.5" data-testid="terminal-summary">
      <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>Terminal matching
        <span className="ml-2 text-xs font-normal" style={{ color: 'var(--t1)' }}>{report.assignment.used} used I/O Assignment rows · {report.assignment.spare_ignored} spare rows ignored</span></p>
      {report.warnings.map((w, i) => <p key={i} className="flex items-start gap-2 text-xs text-amber-600"><AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />{w}</p>)}
      <div className="overflow-auto border rounded-lg" style={{ borderColor: 'var(--b1)' }}>
        <table className="w-full text-xs">
          <thead style={{ background: 'var(--s2)' }}><tr>{['Sheet', ...COUNTS.map(([, l]) => l)].map((h) => <th key={h} className="px-2 py-1 text-left font-medium" style={{ color: 'var(--t1)' }}>{h}</th>)}</tr></thead>
          <tbody>{rows.map((s) => (
            <tr key={s.sheet} className="border-t" style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }}>
              <td className="px-2 py-1 font-medium">{s.sheet}</td>{COUNTS.map(([k]) => <td key={k} className="px-2 py-1">{(s as any)[k] ?? 0}</td>)}
            </tr>))}</tbody>
        </table>
      </div>
      {report.sheets.some((s) => s.issues.length > 0) && (
        <details className="text-xs" style={{ color: 'var(--t1)' }}><summary className="cursor-pointer">Items to review</summary>
          <ul className="list-disc pl-5 max-h-48 overflow-auto">{report.sheets.flatMap((s) => s.issues.map((m, i) => <li key={`${s.sheet}${i}`}>{s.sheet} - {m}</li>))}</ul></details>)}
    </div>
  );
}

interface Props {
  scope: string;                       // the engineering scope filters (request value)
  terminals: TerminalSource;
  onTerminalsChange: (t: TerminalSource) => void;
  iodbFile: File | null;
  includeSchedule: boolean;
  onIncludeScheduleChange: (v: boolean) => void;
  selected: string[];
  onSelectedChange: (labels: string[]) => void;
}

export default function ExtraCableSheets({ scope, terminals, onTerminalsChange, iodbFile, includeSchedule, onIncludeScheduleChange, selected, onSelectedChange }: Props) {
  const [avail, setAvail] = useState<Record<string, Availability> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<PreviewSheet[] | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [report, setReport] = useState<TerminalReport | null>(null);

  useEffect(() => {
    setPreview(null);
    if (!iodbFile) { setAvail(null); setError(null); return; }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const form = new FormData();
    form.append('iodb_file', iodbFile);
    form.append('scope_filters', scope);
    api
      .post<Record<string, Availability>>('/cable-schedule/extra/availability', form, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((r) => {
        if (cancelled) return;
        setAvail(r.data);
        // a selected sheet that this IODB cannot produce is dropped, not silently generated blank
        onSelectedChange(selected.filter((l) => r.data[KEYS[l]]?.available));
      })
      .catch((e) => { if (!cancelled) { setAvail(null); setError(e.response?.data?.detail || 'Could not check the IODB for MCC / VFD / MOV / LCP data'); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [iodbFile, scope]);

  useEffect(() => { setPreview(null); setReport(null); }, [selected.join(','), iodbFile, scope, terminals.file, terminals.equipment, terminals.panel]);

  const toggle = (label: string) =>
    onSelectedChange(selected.includes(label) ? selected.filter((l) => l !== label) : EXTRA_LABELS.filter((l) => l === label || selected.includes(l)));

  const availableLabels = EXTRA_LABELS.filter((l) => avail?.[KEYS[l]]?.available);
  const allSelected = includeSchedule && availableLabels.length > 0 && availableLabels.every((l) => selected.includes(l));
  const toggleAll = (on: boolean) => {
    onIncludeScheduleChange(on || false);
    onSelectedChange(on ? [...availableLabels] : []);
  };

  const runPreview = async () => {
    if (!iodbFile || selected.length === 0) return;
    setPreviewing(true);
    setError(null);
    const form = new FormData();
    form.append('iodb_file', iodbFile);
    form.append('extra_sheets', selected.join(','));
    form.append('scope_filters', scope);
    appendTerminals(form, terminals);
    try {
      const r = await api.post<{ sheets: PreviewSheet[]; terminals?: TerminalReport }>('/cable-schedule/extra/preview', form, { headers: { 'Content-Type': 'multipart/form-data' } });
      setPreview(r.data.sheets);
      setReport(r.data.terminals ?? null);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Preview failed');
    } finally {
      setPreviewing(false);
    }
  };

  return (
    <Card title="Instrument Cable Schedule Group" description="Choose the sheets to generate. Every sheet of the template is kept; the IODB is never modified.">
      <div className="space-y-2" data-testid="cable-group-sheets">
        <label className="flex items-center gap-3 text-sm font-semibold pb-2 mb-1 border-b" style={{ color: 'var(--t0)', borderColor: 'var(--b1)' }}>
          <input type="checkbox" data-testid="select-all-sheets" checked={allSelected} disabled={!iodbFile || loading || !avail} onChange={(e) => toggleAll(e.target.checked)} />
          Select all
        </label>
        <label className="flex items-center gap-3 text-sm font-medium" style={{ color: 'var(--t0)' }}>
          <input type="checkbox" checked={includeSchedule} onChange={(e) => onIncludeScheduleChange(e.target.checked)} />
          Instrument Cable Schedule
        </label>
        {EXTRA_LABELS.map((label) => {
          const a = avail?.[KEYS[label]];
          const disabled = !iodbFile || loading || !a || !a.available;
          return (
            <div key={label}>
              <label className="flex items-center gap-3 text-sm" style={{ color: disabled ? 'var(--t2)' : 'var(--t0)' }}>
                <input type="checkbox" disabled={disabled} checked={selected.includes(label)} onChange={() => toggle(label)} />
                <span className="font-medium">{label}</span>
                {a && a.available && (
                  <span className="text-xs" style={{ color: 'var(--t1)' }}>
                    {a.records} signals · {a.devices} {label === 'MOV' ? 'MOVs' : label === 'VFD' ? 'VFDs' : label === 'LCP' ? 'LCPs' : 'motors'}
                    {a.cables ? ` · ${a.cables} cables` : ''}
                  </span>
                )}
              </label>
              {a && !a.available && a.reason && <p className="text-xs ml-7 mt-0.5" style={{ color: 'var(--t2)' }}>{a.reason}</p>}
            </div>
          );
        })}
        {!iodbFile && <p className="text-xs" style={{ color: 'var(--t2)' }}>Upload or select the IODB to see which sheets can be generated.</p>}
        {loading && <p className="text-xs" style={{ color: 'var(--t1)' }}><Loader2 className="inline w-3 h-3 animate-spin mr-1" />Checking the IODB…</p>}
        {error && <p className="text-xs text-red-500">{error}</p>}
        {!includeSchedule && selected.length === 0 && (
          <p className="text-xs text-red-500">Select the Instrument Cable Schedule or at least one other sheet.</p>
        )}
      </div>

      <div className="mt-4 space-y-2 border-t pt-3 text-sm" style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }} data-testid="io-assignment">
        <label className="block font-semibold">Upload I/O Assignment <span className="font-normal text-xs" style={{ color: 'var(--t2)' }}>(optional, .xlsx)</span>
          <input type="file" accept=".xlsx" className="block mt-1 text-xs" onChange={(e) => onTerminalsChange({ ...terminals, file: e.target.files?.[0] ?? null })} />
        </label>
        <p className="text-xs" style={{ color: 'var(--t1)' }}>Upload the Standard I/O Assignment Excel workbook to automatically populate available terminal details for MCC, VFD, MOV and applicable LCP connections.</p>
        {!terminals.file ? <p className="text-xs" style={{ color: 'var(--t2)' }}>No I/O Assignment: supplementary terminal assignment information is unavailable, and those terminals stay TBA.</p> : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <label>TB details at the equipment (MCC / VFD / MOV / LCP) come from
              <select className="block w-full border rounded-lg px-2 py-1 mt-1" style={{ borderColor: 'var(--b1)', background: 'var(--s1)', color: 'var(--t0)' }} value={terminals.equipment}
                      onChange={(e) => onTerminalsChange({ ...terminals, equipment: e.target.value as TerminalSource['equipment'] })}>
                <option value="device">Device terminals (default)</option>
                <option value="ts">Field terminal strip (TS) - I confirm these are the equipment's terminals</option>
              </select></label>
            <label>MOV control desk terminals come from
              <select className="block w-full border rounded-lg px-2 py-1 mt-1" style={{ borderColor: 'var(--b1)', background: 'var(--s1)', color: 'var(--t0)' }} value={terminals.panel}
                      onChange={(e) => onTerminalsChange({ ...terminals, panel: e.target.value as TerminalSource['panel'] })}>
                <option value="none">The IODB only (default)</option>
                <option value="ts">Field terminal strip (TS) - I confirm it is the control desk</option>
              </select></label>
          </div>)}
        {terminals.file && selected.length === 0 && <p className="text-xs text-amber-600">Terminal details apply to the MCC, VFD, MOV and LCP sheets. Select at least one.</p>}
      </div>

      {selected.length > 0 && (
        <div className="mt-4">
          <Button onClick={runPreview} loading={previewing} className="bg-blue-600 hover:bg-blue-700">
            <Eye className="w-4 h-4" />
            {previewing ? 'Building preview…' : 'Preview selected sheets'}
          </Button>
        </div>
      )}

      {report && <div className="mt-4"><TerminalSummary report={report} /></div>}

      {preview && (
        <div className="mt-4 space-y-4" data-testid="cable-group-preview">
          {preview.map((s) => (
            <div key={s.label} className="rounded-xl p-3" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
              <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>
                {s.label} <span className="text-xs font-normal" style={{ color: 'var(--t1)' }}>{s.records} signal rows · {s.devices} devices · {s.cables} cables</span>
              </p>
              {s.warnings.map((w, i) => (
                <p key={i} className="flex items-start gap-2 text-xs mt-1 text-amber-600"><AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />{w}</p>
              ))}
              <div className="overflow-auto max-h-60 mt-2 border rounded-lg" style={{ borderColor: 'var(--b1)' }}>
                <table className="w-full text-xs">
                  <thead className="sticky top-0" style={{ background: 'var(--s2)' }}>
                    <tr>{['SL', 'Tag No', 'Description', 'Device', 'Signal', 'Cable', 'Cable size'].map((h) => (
                      <th key={h} className="px-2 py-1 text-left font-medium" style={{ color: 'var(--t1)' }}>{h}</th>))}</tr>
                  </thead>
                  <tbody>
                    {s.rows.map((r, i) => (
                      <tr key={i} className="border-t" style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }}>
                        <td className="px-2 py-1">{r.sl}</td><td className="px-2 py-1">{r.tag}</td><td className="px-2 py-1">{r.description}</td>
                        <td className="px-2 py-1">{r.device}</td><td className="px-2 py-1">{r.signal}</td>
                        <td className="px-2 py-1">{r.cable}</td><td className="px-2 py-1">{r.cable_size}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {s.records > s.rows.length && <p className="text-xs mt-1" style={{ color: 'var(--t2)' }}>Showing the first {s.rows.length} of {s.records} rows.</p>}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
