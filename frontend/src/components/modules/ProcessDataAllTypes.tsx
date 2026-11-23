/**
 * Process Data Requisition - "All Instrument Types (From IODB)" mode.
 *
 * The uploaded IODB is analysed once on the server (/process-data/detect-types): every supported instrument type / subtype is
 * listed with its tags. The engineer can switch types and tags on or off and adjust each type's own process parameters; one
 * workbook is then generated (/process-data/generate-all) with a requisition sheet per type. Each type keeps its own
 * parameter profile - changing one never touches another. Records the IODB does not classify (subtype not stated, unsupported
 * types, ambiguous rows) are shown for review and are never forced into a type.
 */
import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronRight, ClipboardList, Download, CheckCircle2 } from 'lucide-react';
import api from '@/services/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';

interface Tag { tag_no: string; equipment_description: string; pid_no: string; service: string; equipment_no: string; line: string; line_size: string; row_index: number; reason?: string }
interface Group { key: string; type_key: string; type_label: string; subtype: string; label: string; needs_review: boolean; reason: string; category: string; count: number; tags: Tag[] }
interface Detect { groups: Group[]; types_found: number; eligible_tags: number; review_tags: number; unsupported: { name: string; count: number; reason: string }[];
  ambiguous: { tag_no: string; types: string[] }[]; ambiguous_count: number; warnings: string[] }
interface Field { name: string; header: string; default_selected: boolean }
interface Profile { verified: boolean; fields: Field[]; default_fields: string[] }
interface Generated { filename: string; message: string; warnings?: string[] }

export default function ProcessDataAllTypes({ iodbFile }: { iodbFile: File | null }) {
  const [det, setDet] = useState<Detect | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [on, setOn] = useState<Record<string, boolean>>({});                 // instrument group switched on
  const [tagSel, setTagSel] = useState<Record<string, string[]>>({});        // group key -> selected tag numbers
  const [fields, setFields] = useState<Record<string, string[]>>({});        // group key -> selected parameters (own per group)
  const [profiles, setProfiles] = useState<Record<string, Profile>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [showOptional, setShowOptional] = useState<Record<string, boolean>>({});
  const [filterKey, setFilterKey] = useState('');
  const [search, setSearch] = useState('');
  const [useIodb, setUseIodb] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<Generated | null>(null);
  const seq = useRef(0);
  const ctl = useRef<AbortController | null>(null);

  // a new / changed IODB invalidates everything below it; an outdated analysis is cancelled and ignored
  useEffect(() => {
    ctl.current?.abort();
    setDet(null); setOn({}); setTagSel({}); setFields({}); setProfiles({}); setOpen(null); setResult(null); setError(null); setFilterKey(''); setSearch('');
    if (!iodbFile) return;
    const c = new AbortController(); ctl.current = c;
    const n = ++seq.current;
    setLoading(true);
    const f = new FormData(); f.append('file', iodbFile);
    api.post<Detect>('/process-data/detect-types', f, { headers: { 'Content-Type': 'multipart/form-data' }, signal: c.signal })
      .then((r) => {
        if (n !== seq.current) return;
        setDet(r.data);
        const eligible = r.data.groups.filter((g) => !g.needs_review);          // every eligible type and tag is selected by default
        setOn(Object.fromEntries(eligible.map((g) => [g.key, true])));
        setTagSel(Object.fromEntries(eligible.map((g) => [g.key, g.tags.map((t) => t.tag_no)])));
      })
      .catch((e: any) => { if (n === seq.current && e?.code !== 'ERR_CANCELED') setError(e.response?.data?.detail || 'Could not analyse the IODB.'); })
      .finally(() => { if (n === seq.current) setLoading(false); });
    return () => c.abort();
  }, [iodbFile]);

  const loadProfile = (g: Group) => {
    if (profiles[g.key]) return;
    api.get<Profile>('/process-data/profile', { params: { instrument_type: g.type_key, ...(g.subtype ? { subtype: g.subtype } : {}) } })
      .then((r) => { setProfiles((p) => ({ ...p, [g.key]: r.data })); setFields((f) => (f[g.key] ? f : { ...f, [g.key]: r.data.default_fields })); })
      .catch((e: any) => setError(e.response?.data?.detail || 'Could not load the parameters.'));
  };

  const toggleGroup = (g: Group) => {
    const next = !on[g.key];
    setOn((o) => ({ ...o, [g.key]: next }));
    setTagSel((t) => ({ ...t, [g.key]: next ? g.tags.map((x) => x.tag_no) : [] }));
    setResult(null);
  };
  const toggleTag = (g: Group, tag: string) => {
    const cur = tagSel[g.key] || [];
    const next = cur.includes(tag) ? cur.filter((x) => x !== tag) : [...cur, tag];
    setTagSel((t) => ({ ...t, [g.key]: next }));
    setOn((o) => ({ ...o, [g.key]: next.length > 0 }));
    setResult(null);
  };

  const groups = det?.groups ?? [];
  const activeGroups = groups.filter((g) => on[g.key]);
  const selectedCount = activeGroups.reduce((n, g) => n + (tagSel[g.key]?.length || 0), 0);

  // tag table: the tags of the groups that are switched on, filtered by type and search (selection is per group, never global)
  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return activeGroups.filter((g) => !filterKey || g.key === filterKey).flatMap((g) => g.tags.map((t) => ({ g, t })))
      .filter(({ t }) => !q || [t.tag_no, t.service, t.pid_no, t.equipment_no, t.equipment_description, t.line].some((v) => (v || '').toLowerCase().includes(q)));
  }, [activeGroups, filterKey, search]);

  const setShown = (select: boolean) => {
    setTagSel((cur) => {
      const next = { ...cur };
      const shown = new Map<string, Set<string>>();
      rows.forEach(({ g, t }) => { (shown.get(g.key) || shown.set(g.key, new Set()).get(g.key)!).add(t.tag_no); });
      shown.forEach((set, key) => {
        const have = new Set(next[key] || []);
        set.forEach((t) => (select ? have.add(t) : have.delete(t)));
        next[key] = Array.from(have);
      });
      return next;
    });
    setResult(null);
  };

  const restore = (g: Group) => { const p = profiles[g.key]; if (p) setFields((f) => ({ ...f, [g.key]: [...p.default_fields] })); };
  const restoreAll = () => activeGroups.forEach(restore);
  const toggleField = (g: Group, name: string) =>
    setFields((f) => { const cur = f[g.key] || []; return { ...f, [g.key]: cur.includes(name) ? cur.filter((n) => n !== name) : [...cur, name] }; });

  const generate = async () => {
    setGenerating(true); setError(null); setResult(null);
    try {
      const picks = activeGroups.filter((g) => (tagSel[g.key]?.length || 0) > 0)
        .map((g) => ({ key: g.key, tags: tagSel[g.key], selected_fields: fields[g.key] ?? null }));   // null = the type's verified defaults
      const f = new FormData();
      f.append('iodb_file', iodbFile as File);
      f.append('selections', JSON.stringify(picks));
      f.append('use_iodb_values', String(useIodb));
      const r = await api.post<Generated>('/process-data/generate-all', f, { headers: { 'Content-Type': 'multipart/form-data' } });
      setResult(r.data);
    } catch (e: any) { setError(e.response?.data?.detail || 'Generation failed'); }
    finally { setGenerating(false); }
  };
  const download = async () => {
    try {
      const r = await api.get('/process-data/download', { responseType: 'blob' });
      const a = document.createElement('a');
      a.href = window.URL.createObjectURL(new Blob([r.data]));
      a.setAttribute('download', result?.filename || 'Process_Data_Requisition.xlsx');
      document.body.appendChild(a); a.click(); a.remove();
    } catch (e: any) { setError(e.response?.data?.detail || 'Download failed'); }
  };

  if (!iodbFile) return <Alert variant="info" title="Upload the IODB first">The instrument types are detected from the uploaded IODB.</Alert>;
  return (
    <div className="space-y-6" data-testid="all-types">
      {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}
      {loading && <p className="text-sm" style={{ color: 'var(--t1)' }}>Analysing the IODB…</p>}
      {det && (
        <>
          <Card title="Instrument Types Found" description="Every supported instrument type in the IODB, grouped. Uncheck a type to leave it out.">
            <p className="text-sm mb-3" style={{ color: 'var(--t1)' }} data-testid="all-summary">
              Instrument types found: <strong>{det.types_found}</strong> &middot; Eligible tags: <strong>{det.eligible_tags}</strong> &middot;
              Selected tags: <strong>{selectedCount}</strong>{det.review_tags > 0 && <> &middot; Needs review: <strong>{det.review_tags}</strong></>}
            </p>
            {det.warnings.map((w, i) => <p key={i} className="text-xs text-amber-600 mb-1">{w}</p>)}
            <div className="border rounded-lg overflow-auto" style={{ borderColor: 'var(--b1)' }}>
              <table className="w-full text-sm">
                <thead style={{ background: 'var(--s2)' }}><tr>{['Select', 'Instrument type', 'Quantity', 'Selected tags', 'Parameters'].map((h) =>
                  <th key={h} className="px-3 py-1.5 text-left font-medium text-xs" style={{ color: 'var(--t1)' }}>{h}</th>)}</tr></thead>
                <tbody>
                  {groups.map((g) => {
                    const p = profiles[g.key];
                    const sel = fields[g.key] ?? p?.default_fields ?? [];
                    const optional = (p?.fields ?? []).filter((f) => !p!.default_fields.includes(f.name));
                    return (
                      <Fragment key={g.key}>
                        <tr className="border-t" style={{ borderColor: 'var(--b1)', color: 'var(--t0)' }} data-testid={`group-${g.key}`}>
                          <td className="px-3 py-1.5"><input type="checkbox" checked={!!on[g.key]} onChange={() => toggleGroup(g)} aria-label={`Select ${g.label}`} /></td>
                          <td className="px-3 py-1.5">{g.label}{g.needs_review && <span className="ml-2 text-xs text-amber-600" title={g.tags[0]?.reason || g.reason}>needs review — not selected by default</span>}</td>
                          <td className="px-3 py-1.5">{g.count}</td>
                          <td className="px-3 py-1.5">{tagSel[g.key]?.length || 0}</td>
                          <td className="px-3 py-1.5"><button className="flex items-center gap-1 text-xs underline" onClick={() => { const n = open === g.key ? null : g.key; setOpen(n); if (n) loadProfile(g); }}>
                            {open === g.key ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}Review parameters</button></td>
                        </tr>
                        {open === g.key && (
                          <tr style={{ background: 'var(--s2)' }}><td colSpan={5} className="px-4 py-3 text-xs" style={{ color: 'var(--t1)' }}>
                            {!p ? 'Loading…' : (
                              <div className="space-y-2">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <p className="font-medium" style={{ color: 'var(--t0)' }}>{g.label} — {g.count} tags · default parameters selected automatically ({p.default_fields.filter((n) => sel.includes(n)).length} of {p.default_fields.length})</p>
                                  <Button variant="ghost" size="sm" onClick={() => restore(g)}>Restore recommended defaults</Button>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">
                                  {p.fields.filter((f) => p.default_fields.includes(f.name)).map((f) => (
                                    <label key={f.name} className="flex items-start gap-2 cursor-pointer"><input type="checkbox" checked={sel.includes(f.name)} onChange={() => toggleField(g, f.name)} /><span>{f.header}</span></label>))}
                                </div>
                                {optional.length > 0 && (
                                  <div>
                                    <button className="underline" onClick={() => setShowOptional((o) => ({ ...o, [g.key]: !o[g.key] }))}>
                                      {showOptional[g.key] ? 'Hide' : 'Add'} additional parameters ({optional.filter((f) => sel.includes(f.name)).length} of {optional.length} selected)</button>
                                    {showOptional[g.key] && (
                                      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1 mt-2 max-h-56 overflow-auto">
                                        {optional.map((f) => (
                                          <label key={f.name} className="flex items-start gap-2 cursor-pointer"><input type="checkbox" checked={sel.includes(f.name)} onChange={() => toggleField(g, f.name)} /><span>{f.header}</span></label>))}
                                      </div>)}
                                  </div>)}
                              </div>)}
                          </td></tr>)}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap gap-2 mt-3">
              <Button variant="ghost" size="sm" onClick={() => { activeGroups.forEach(loadProfile); restoreAll(); }}>Restore defaults for all selected types</Button>
            </div>
            {(det.unsupported.length > 0 || det.ambiguous_count > 0) && (
              <details className="mt-3 text-xs" style={{ color: 'var(--t1)' }}>
                <summary className="cursor-pointer font-medium">Not generated automatically ({det.unsupported.length} unsupported type(s){det.ambiguous_count > 0 ? `, ${det.ambiguous_count} ambiguous record(s)` : ''})</summary>
                <ul className="list-disc pl-5 mt-1 space-y-0.5">
                  {det.unsupported.map((u) => <li key={u.name}>{u.name} — {u.count} tag(s): {u.reason}</li>)}
                  {det.ambiguous.map((a) => <li key={a.tag_no}>{a.tag_no} fits several types ({a.types.join(', ')}) and was not classified.</li>)}
                </ul>
              </details>)}
          </Card>

          <Card title="Select Tags" description="Tags of the selected instrument types. Select all / Clear all act on the tags currently shown (after the type filter and search).">
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <input className="flex-1 min-w-[180px] px-3 py-1.5 text-sm border border-gray-300 rounded-lg" placeholder="Search tag, service, P&ID, equipment, line..."
                     value={search} onChange={(e) => setSearch(e.target.value)} />
              <select className="px-2 py-1.5 text-sm border border-gray-300 rounded-lg" value={filterKey} onChange={(e) => setFilterKey(e.target.value)} aria-label="Filter by instrument type">
                <option value="">All selected types</option>
                {activeGroups.map((g) => <option key={g.key} value={g.key}>{g.label}</option>)}
              </select>
              <Button variant="ghost" size="sm" onClick={() => setShown(true)}>Select all shown</Button>
              <Button variant="ghost" size="sm" onClick={() => setShown(false)}>Clear all shown</Button>
            </div>
            <p className="text-sm mb-2" style={{ color: 'var(--t1)' }}>Tags shown: <strong>{rows.length}</strong> &middot; Selected (all types): <strong>{selectedCount}</strong></p>
            <div className="border border-gray-200 rounded-lg overflow-auto max-h-96">
              <table className="w-full text-sm whitespace-nowrap">
                <thead className="bg-gray-50 sticky top-0"><tr>{['', 'INSTRUMENT TYPE', 'TAG NO', 'EQUIPMENT DESCRIPTION', 'P&ID NO.', 'SERVICE', 'EQUIPMENT NO', 'LINE', 'LINE SIZE'].map((h) =>
                  <th key={h} className="px-3 py-2 text-left font-medium text-gray-700">{h}</th>)}</tr></thead>
                <tbody className="divide-y divide-gray-200">
                  {rows.map(({ g, t }) => (
                    <tr key={`${g.key}-${t.tag_no}`} className="hover:bg-gray-50">
                      <td className="px-3 py-1.5"><input type="checkbox" checked={(tagSel[g.key] || []).includes(t.tag_no)} onChange={() => toggleTag(g, t.tag_no)} aria-label={`Select ${t.tag_no}`} /></td>
                      <td className="px-3 py-1.5 text-gray-700">{g.label}</td><td className="px-3 py-1.5 text-gray-700">{t.tag_no}</td>
                      <td className="px-3 py-1.5 text-gray-700">{t.equipment_description}</td><td className="px-3 py-1.5 text-gray-700">{t.pid_no}</td>
                      <td className="px-3 py-1.5 text-gray-700">{t.service}</td><td className="px-3 py-1.5 text-gray-700">{t.equipment_no}</td>
                      <td className="px-3 py-1.5 text-gray-700">{t.line}</td><td className="px-3 py-1.5 text-gray-700">{t.line_size}</td>
                    </tr>))}
                  {rows.length === 0 && <tr><td colSpan={9} className="px-3 py-8 text-center text-gray-400">No tags to show</td></tr>}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="Generate" description="One workbook with a requisition sheet per selected instrument type, each with its own process parameters.">
            <label className="flex items-center gap-2 cursor-pointer text-sm mb-3" style={{ color: 'var(--t1)' }}>
              <input type="checkbox" checked={useIodb} onChange={(e) => setUseIodb(e.target.checked)} />Use available IODB process data as initial values
            </label>
            <Button onClick={generate} loading={generating} disabled={selectedCount === 0} size="lg" fullWidth className="text-lg py-4" data-testid="all-generate">
              <ClipboardList className="w-6 h-6" />{generating ? 'Generating...' : 'Generate Process Data Requisition'}
            </Button>
            {result && (
              <div className="mt-4 bg-green-50 border border-green-200 rounded-lg p-5">
                <div className="flex items-start gap-3"><CheckCircle2 className="w-8 h-8 text-green-500 flex-shrink-0" />
                  <div className="flex-1"><p className="text-green-800 font-semibold mb-1">Process Data Requisition Generated!</p>
                    <p className="text-green-700 mb-3">{result.message}</p>
                    {result.warnings && result.warnings.length > 0 && <ul className="list-disc pl-5 text-sm text-amber-700 mb-3">{result.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
                    <Button onClick={download} className="bg-green-600 hover:bg-green-700"><Download className="w-5 h-5" />Download {result.filename}</Button>
                  </div></div>
              </div>)}
          </Card>
        </>
      )}
    </div>
  );
}
