/**
 * Engineering scope of the Cable Schedule: AREA, AREA CODE and tag STATUS filters.
 * Values and counts come from the uploaded IODB (server side); the filtering itself happens in the generation engine.
 * null = default (every area / code; every status except deleted); a list = exactly what is ticked.
 */
import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import api from '@/services/api';
import Card from '../../ui/Card';
import Button from '../../ui/Button';

export interface ScopeSelection { areas: string[] | null; area_codes: string[] | null; statuses: string[] | null }
export const DEFAULT_SCOPE: ScopeSelection = { areas: null, area_codes: null, statuses: null };
/** The request value: only what differs from the default is sent. */
export const scopeParam = (s: ScopeSelection) => JSON.stringify(Object.fromEntries(Object.entries(s).filter(([, v]) => v !== null)));

interface Option { value: string; count: number; areas?: string[] }
interface StatusOption { value: string; count: number; label: string; default: boolean }
export interface ScopeSummary { total: number; excluded_status: number; excluded_area: number; excluded_area_code: number; eligible: number;
  deleted_excluded: number; deleted_included: number; review: number; loops: number | null; junction_boxes: number | null }
interface ScopeData { columns: Record<string, string | null>; areas: Option[]; area_codes: Option[]; statuses: StatusOption[]; summary: ScopeSummary; notes: string[] }

const field = 'w-full border rounded-lg px-2 py-1 text-sm';
const fieldStyle = { borderColor: 'var(--b1)', background: 'var(--s1)', color: 'var(--t0)' };

function MultiSelect({ label, allLabel, options, selected, onChange }: {
  label: string; allLabel: string; options: Option[]; selected: string[] | null; onChange: (v: string[] | null) => void;
}) {
  const [query, setQuery] = useState('');
  const shown = options.filter((o) => o.value.toLowerCase().includes(query.toLowerCase()));
  const chosen = new Set(selected ?? options.map((o) => o.value));
  const toggle = (v: string) => {
    const next = new Set(chosen);
    if (next.has(v)) next.delete(v); else next.add(v);
    onChange(options.map((o) => o.value).filter((x) => next.has(x)));
  };
  return (
    <details className="border rounded-lg p-2" style={{ borderColor: 'var(--b1)' }} data-testid={`scope-${label}`}>
      <summary className="cursor-pointer text-sm font-medium" style={{ color: 'var(--t0)' }}>{label}: {selected === null ? allLabel : selected.length ? selected.join(', ') : 'none selected'}</summary>
      <div className="mt-2 space-y-2">
        <input className={field} style={fieldStyle} placeholder="Search" aria-label={`Search ${label}`} value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="flex gap-3 text-xs">
          <button type="button" className="underline" onClick={() => onChange(null)}>Select all</button>
          <button type="button" className="underline" onClick={() => onChange([])}>Clear selection</button>
        </div>
        <div className="max-h-40 overflow-auto space-y-1">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={selected === null} onChange={(e) => onChange(e.target.checked ? null : [])} />{allLabel}</label>
          {shown.map((o) => (
            <label key={o.value} className="flex items-center gap-2 text-sm" style={{ color: 'var(--t0)' }}>
              <input type="checkbox" checked={chosen.has(o.value)} onChange={() => toggle(o.value)} />{o.value}<span className="text-xs" style={{ color: 'var(--t2)' }}>({o.count})</span>
            </label>))}
        </div>
      </div>
    </details>
  );
}

export default function ScopeFilters({ iodbFile, value, onChange, onEligible }: {
  iodbFile: File | null; value: ScopeSelection; onChange: (s: ScopeSelection) => void; onEligible: (n: number | null) => void;
}) {
  const [data, setData] = useState<ScopeData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);

  useEffect(() => { setData(null); }, [iodbFile]);
  useEffect(() => {
    setError(null);
    onEligible(null);
    if (!iodbFile) return;
    const n = ++seq.current;
    const timer = window.setTimeout(() => {
      setLoading(true);
      const form = new FormData();
      form.append('iodb_file', iodbFile);
      form.append('scope_filters', scopeParam(value));
      api.post<ScopeData>('/cable-schedule/scope', form, { headers: { 'Content-Type': 'multipart/form-data' } })
        .then((r) => { if (n === seq.current) { setData(r.data); onEligible(r.data.summary.eligible); } })
        .catch((e) => { if (n === seq.current) { setError(e.response?.data?.detail || 'The IODB filters could not be read.'); onEligible(0); } })
        .finally(() => { if (n === seq.current) setLoading(false); });
    }, 400);
    return () => window.clearTimeout(timer);
  }, [iodbFile, value]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!iodbFile) return null;
  // only the codes of the selected areas are offered; codes that no longer apply are cleared when the areas change
  const codesFor = (areas: string[] | null) => (data?.area_codes ?? []).filter((c) => areas === null || !c.areas?.length || c.areas.some((a) => areas.includes(a)));
  const setAreas = (areas: string[] | null) => {
    const applicable = new Set(codesFor(areas).map((c) => c.value));
    const codes = value.area_codes?.filter((c) => applicable.has(c)) ?? null;
    onChange({ ...value, areas, area_codes: codes && codes.length ? codes : null });
  };
  const statuses = data?.statuses ?? [];
  const ticked = new Set(value.statuses ?? statuses.filter((s) => s.default).map((s) => s.value));
  const toggleStatus = (v: string) => {
    const next = new Set(ticked);
    if (next.has(v)) next.delete(v); else next.add(v);
    onChange({ ...value, statuses: statuses.map((s) => s.value).filter((x) => next.has(x)) });
  };
  const s = data?.summary;

  return (
    <Card title="Engineering Scope Filters" description="Applied to the IODB before anything is calculated. The uploaded file is never changed.">
      <div className="space-y-3" data-testid="scope-filters">
        {error && <p className="text-sm text-red-500">{error}</p>}
        {!data && loading && <p className="text-sm" style={{ color: 'var(--t1)' }}><Loader2 className="inline w-4 h-4 animate-spin mr-1" />Reading areas and statuses…</p>}
        {data && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {data.columns.area ? <MultiSelect label="Select Area" allLabel="All Areas" options={data.areas} selected={value.areas} onChange={setAreas} />
                : <p className="text-sm" style={{ color: 'var(--t2)' }}>Select Area: this IODB has no AREA column.</p>}
              {data.columns.area_code ? <MultiSelect label="Select Area Code" allLabel={value.areas ? 'All Applicable Area Codes' : 'All Area Codes'} options={codesFor(value.areas)}
                  selected={value.area_codes} onChange={(area_codes) => onChange({ ...value, area_codes })} />
                : <p className="text-sm" style={{ color: 'var(--t2)' }}>Select Area Code: this IODB has no AREA CODE column.</p>}
            </div>
            {data.columns.status ? (
              <div data-testid="scope-status">
                <p className="text-sm font-medium mb-1" style={{ color: 'var(--t0)' }}>Select Tag Status</p>
                <div className="flex gap-3 text-xs mb-1">
                  <button type="button" className="underline" onClick={() => onChange({ ...value, statuses: statuses.map((x) => x.value) })}>Select all</button>
                  <button type="button" className="underline" onClick={() => onChange({ ...value, statuses: [] })}>Clear selection</button>
                  <button type="button" className="underline" onClick={() => onChange({ ...value, statuses: null })}>Reset to default</button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-4 max-h-48 overflow-auto">
                  {statuses.map((x) => (
                    <label key={x.value} className="flex items-center gap-2 text-sm" style={{ color: 'var(--t0)' }}>
                      <input type="checkbox" checked={ticked.has(x.value)} onChange={() => toggleStatus(x.value)} />
                      {x.value}<span className="text-xs" style={{ color: 'var(--t2)' }}>({x.count}) · {x.label}</span>
                    </label>))}
                </div>
              </div>) : <p className="text-sm" style={{ color: 'var(--t2)' }}>Select Tag Status: this IODB has no STATUS column.</p>}
          </>)}
        <Button variant="secondary" size="sm" onClick={() => onChange(DEFAULT_SCOPE)}>Reset Filters</Button>
        {s && !error && (
          <div className="text-sm rounded-lg p-3" style={{ background: 'var(--s1)', border: '1px solid var(--b1)', color: 'var(--t0)' }} data-testid="scope-summary">
            <p className="font-semibold mb-1">IODB record summary{loading && <Loader2 className="inline w-3 h-3 animate-spin ml-2" />}</p>
            <p>Total records: {s.total} · Excluded by status: {s.excluded_status} (deleted: {s.deleted_excluded}) · Outside selected area: {s.excluded_area} · Outside selected area code: {s.excluded_area_code}</p>
            <p><strong>Eligible records: {s.eligible}</strong>{s.loops !== null && ` · loops: ${s.loops}`}{s.junction_boxes !== null && ` · junction boxes: ${s.junction_boxes}`}
              {s.deleted_included > 0 && ` · deleted records included: ${s.deleted_included}`}{s.review > 0 && ` · needing status review: ${s.review}`}</p>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>Each excluded record is counted once (status first, then area, then area code).</p>
            {s.eligible === 0 && <p className="text-red-500">No records match this selection. Change the filters to generate.</p>}
            {data!.notes.map((n, i) => <p key={i} className="flex items-start gap-2 text-xs mt-1 text-amber-600"><AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />{n}</p>)}
          </div>)}
      </div>
    </Card>
  );
}
