/**
 * Configure Validation Rules (IODB Validator).
 *
 * The iEZ default rules are protected: edits are held in a draft and saved as a custom profile of the current project
 * (Lead Engineer / Reviewer / Admin). Only structured settings are sent; the backend validates and executes them.
 */
import { useEffect, useMemo, useState } from 'react';
import api from '@/services/api';
import Card from '../ui/Card';
import Button from '../ui/Button';
import Alert from '../ui/Alert';

export interface RuleProfile { id: number; project_id: string; name: string; version: number; config: Config; updated_by?: string; updated_at?: string }
type Cond = { field: string; operator: string; value: string };
type Override = { enabled?: boolean; severity?: string; message?: string; apply_when?: { match: 'all' | 'any'; conditions: Cond[] }; exceptions?: Cond[]; params?: Record<string, any> };
export type Config = { rules: Record<string, Override> };
interface Param { name: string; label: string; type: 'text' | 'list' | 'map'; default: any }
interface Rule { id: string; name: string; category: string; description: string; note: string; default_severity: string; params: Param[] }
interface Catalogue { default_name: string; rules: Rule[]; severities: string[]; operators: { key: string; label: string; needs_value: boolean }[]; protected: string[]; can_edit: boolean }

const field = 'w-full border rounded-lg px-2 py-1 text-sm';
const fieldStyle = { borderColor: 'var(--b1)', background: 'var(--s1)', color: 'var(--t0)' };
const title = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const asText = (p: Param, v: any) => (p.type === 'map' ? Object.entries(v || {}).map(([k, x]) => `${k} = ${x}`).join('\n') : p.type === 'list' ? (v || []).join(', ') : v ?? '');
const fromText = (p: Param, t: string) => p.type === 'map'
  ? Object.fromEntries(t.split('\n').map((l) => l.split('=')).filter((a) => a.length === 2 && a[0].trim() && a[1].trim()).map(([k, v]) => [k.trim(), v.trim()]))
  : p.type === 'list' ? t.split(',').map((x) => x.trim()).filter(Boolean) : t;
/** drop settings that equal the default, so "Modified" means something differs */
const tidy = (o: Override): Override => {
  const out: Override = { ...o };
  if (out.enabled !== false) delete out.enabled;
  if (!out.severity || out.severity === 'error') delete out.severity;
  if (!out.message) delete out.message;
  if (!out.apply_when?.conditions.length) delete out.apply_when;
  if (!out.exceptions?.length) delete out.exceptions;
  if (!out.params || !Object.keys(out.params).length) delete out.params;
  return out;
};

export default function ValidationRulesConfig({ projectId, profiles, selected, columns, onSelect, onChanged, onDirty }: {
  projectId: string; profiles: RuleProfile[]; selected: RuleProfile | null; columns: string[];
  onSelect: (id: number | null) => void; onChanged: () => Promise<void>; onDirty: (dirty: boolean) => void;
}) {
  const [cat, setCat] = useState<Catalogue | null>(null);
  const [draft, setDraft] = useState<Config>({ rules: {} });
  const [name, setName] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.get<Catalogue>('/validator/rules-catalogue').then((r) => setCat(r.data)).catch(() => setError('The rule list could not be loaded.')); }, []);
  useEffect(() => { setDraft(JSON.parse(JSON.stringify(selected?.config ?? { rules: {} }))); setName(selected?.name ?? ''); setEditing(null); }, [selected?.id, selected?.version]);
  const dirty = JSON.stringify(draft.rules) !== JSON.stringify(selected?.config.rules ?? {});
  useEffect(() => { onDirty(dirty); }, [dirty]); // eslint-disable-line react-hooks/exhaustive-deps

  const setRule = (id: string, patch: Partial<Override>) => {
    setDone('');
    setDraft((d) => {
      const o = tidy({ ...(d.rules[id] || {}), ...patch });
      const rules = { ...d.rules };
      if (Object.keys(o).length) rules[id] = o; else delete rules[id];
      return { rules };
    });
  };
  const restore = (id: string) => setDraft((d) => { const rules = { ...d.rules }; delete rules[id]; return { rules }; });

  const call = async (what: () => Promise<void>, ok: string) => {
    setBusy(true); setError(null); setDone('');
    try { await what(); setDone(ok); }
    catch (e: any) { const d = e.response?.data?.detail; setError(typeof d === 'string' ? d : 'The request failed.'); }
    finally { setBusy(false); }
  };
  const body = (n: string) => ({ name: n, project_id: projectId, config: draft, expected_version: selected?.version });
  const saveNew = () => {
    const n = window.prompt('Name of the new custom profile', selected ? `${selected.name} (copy)` : `${projectId} rules`);
    if (!n) return;
    call(async () => { const r = await api.post<RuleProfile>('/validator/profiles', body(n)); await onChanged(); onSelect(r.data.id); }, 'Custom profile saved.');
  };
  const save = () => call(async () => { await api.put(`/validator/profiles/${selected!.id}`, body(name)); await onChanged(); }, 'Profile saved.');
  const remove = () => {
    if (!selected || !window.confirm(`Delete the custom profile "${selected.name}"? Its saved versions are kept for old reports.`)) return;
    call(async () => { await api.delete(`/validator/profiles/${selected.id}`, { params: { project_id: projectId } }); onSelect(null); await onChanged(); }, 'Profile deleted.');
  };

  const categories = useMemo(() => Array.from(new Set((cat?.rules ?? []).map((r) => r.category))), [cat]);
  const shown = (cat?.rules ?? []).filter((r) => (!category || r.category === category) && `${r.id} ${r.name} ${r.description}`.toLowerCase().includes(query.toLowerCase()));
  if (!cat) return <Card title="Configure Validation Rules">{error ? <Alert variant="error" title="Error">{error}</Alert> : <p className="text-sm" style={{ color: 'var(--t1)' }}>Loading…</p>}</Card>;
  const canSave = cat.can_edit && !!projectId;
  const modified = Object.keys(draft.rules).length;

  return (
    <Card title="Configure Validation Rules">
      <div className="space-y-3 text-sm" style={{ color: 'var(--t0)' }} data-testid="rules-config">
        <p style={{ color: 'var(--t1)' }}>
          {selected ? <>Custom profile <strong>{selected.name}</strong>, version {selected.version}, last changed by {selected.updated_by || '-'}.</>
            : <><strong>{cat.default_name}</strong> is protected. Changes you make here can be saved as a custom profile of this project.</>}
          {' '}{modified} rule(s) differ from the default.
        </p>
        {!cat.can_edit && <p className="text-amber-600">You can view the rules and run validation. A Lead Engineer, Reviewer or Admin can save rule profiles.</p>}
        {cat.can_edit && !projectId && <p className="text-amber-600">Select a project to save a custom profile.</p>}
        {error && <Alert variant="error" title="Error" onClose={() => setError(null)}>{error}</Alert>}
        {done && <p className="text-green-600">{done}</p>}
        <div className="flex flex-wrap gap-2">
          <input className={`${field} max-w-xs`} style={fieldStyle} placeholder="Search rules" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search rules" />
          <select className={`${field} max-w-xs`} style={fieldStyle} value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Rule category">
            <option value="">All categories</option>{categories.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
        <div className="overflow-x-auto border rounded-lg" style={{ borderColor: 'var(--b1)' }}>
          <table className="w-full text-xs min-w-[40rem]">
            <thead style={{ background: 'var(--s2)' }}><tr>{['Rule', 'Validation rule', 'Category', 'Severity', 'Enabled', ''].map((h, i) => <th key={i} className="px-2 py-1.5 text-left font-medium" style={{ color: 'var(--t1)' }}>{h}</th>)}</tr></thead>
            <tbody>
              {shown.map((r) => {
                const o = draft.rules[r.id] || {};
                return [
                  <tr key={r.id} className="border-t" style={{ borderColor: 'var(--b1)' }} data-testid={`rule-${r.id}`}>
                    <td className="px-2 py-1">R{r.id}</td>
                    <td className="px-2 py-1">{r.name}{draft.rules[r.id] && <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 text-[10px] font-semibold">Modified</span>}</td>
                    <td className="px-2 py-1">{r.category}</td>
                    <td className="px-2 py-1"><select className={field} style={fieldStyle} aria-label={`Severity of rule ${r.id}`} value={o.severity || 'error'} onChange={(e) => setRule(r.id, { severity: e.target.value })}>
                      {cat.severities.map((s) => <option key={s} value={s}>{title(s)}</option>)}</select></td>
                    <td className="px-2 py-1"><label className="flex items-center gap-1"><input type="checkbox" aria-label={`Enable rule ${r.id}`} checked={o.enabled !== false} onChange={(e) => setRule(r.id, { enabled: e.target.checked })} />{o.enabled === false ? 'Off' : 'On'}</label></td>
                    <td className="px-2 py-1"><button className="underline" onClick={() => setEditing(editing === r.id ? null : r.id)}>{editing === r.id ? 'Close' : 'Edit'}</button></td>
                  </tr>,
                  editing === r.id && (
                    <tr key={`${r.id}-edit`} style={{ background: 'var(--s2)' }}><td colSpan={6} className="px-4 py-3">
                      <RuleEditor rule={r} value={o} cat={cat} columns={columns} draft={draft} onChange={(p) => setRule(r.id, p)} onRestore={() => restore(r.id)} />
                    </td></tr>),
                ];
              })}
            </tbody>
          </table>
        </div>
        <details><summary className="cursor-pointer font-medium">Protected system checks (cannot be disabled)</summary>
          <ul className="list-disc pl-5 mt-1" style={{ color: 'var(--t1)' }}>{cat.protected.map((p) => <li key={p}>{p}</li>)}</ul></details>
        <p style={{ color: 'var(--t2)' }}>Rules created in the Dynamic Rules Manager are shared by all projects and run with every profile.</p>
        <div className="flex flex-wrap gap-2 items-center">
          {selected && <input className={`${field} max-w-xs`} style={fieldStyle} value={name} onChange={(e) => setName(e.target.value)} aria-label="Profile name" disabled={!canSave} />}
          {selected && <Button size="sm" onClick={save} loading={busy} disabled={!canSave || (!dirty && name === selected.name)}>Save Profile</Button>}
          <Button size="sm" variant="secondary" onClick={saveNew} disabled={!canSave || busy}>{selected ? 'Duplicate as new profile' : 'Save as custom profile'}</Button>
          <Button size="sm" variant="secondary" onClick={() => setDraft({ rules: {} })} disabled={!modified}>Restore all default rules</Button>
          {selected && <Button size="sm" variant="danger" onClick={remove} disabled={!canSave || busy}>Delete profile</Button>}
        </div>
        {dirty && <p className="text-amber-600">Unsaved changes are not used by Run Validation. Save the profile first.</p>}
        <p style={{ color: 'var(--t2)' }}>{profiles.length} custom profile(s) in this project.</p>
      </div>
    </Card>
  );
}

function RuleEditor({ rule, value, cat, columns, draft, onChange, onRestore }: {
  rule: Rule; value: Override; cat: Catalogue; columns: string[]; draft: Config; onChange: (p: Partial<Override>) => void; onRestore: () => void;
}) {
  const [texts, setTexts] = useState<Record<string, string>>(() => Object.fromEntries(rule.params.map((p) => [p.name, asText(p, value.params?.[p.name] ?? p.default)])));
  const [showDefault, setShowDefault] = useState(false);
  const [sample, setSample] = useState('TAG NO = PIT-101\nSIGNAL I/O TYPE = AI\nSUB SYSTEM = -\nJUNCTION BOX TAG NO. = ');
  const [preview, setPreview] = useState('');
  const setParam = (p: Param, t: string) => {
    setTexts({ ...texts, [p.name]: t });
    const v = fromText(p, t); const params = { ...(value.params || {}) };
    if (JSON.stringify(v) === JSON.stringify(p.default)) delete params[p.name]; else params[p.name] = v;
    onChange({ params });
  };
  const run = async () => {
    setPreview('Checking…');
    const record = Object.fromEntries(sample.split('\n').map((l) => { const i = l.indexOf('='); return i < 0 ? ['', ''] : [l.slice(0, i).trim(), l.slice(i + 1).trim()]; }).filter(([k]) => k));
    try {
      const r = await api.post('/validator/preview-rule', { rule_id: rule.id, config: draft, record });
      setPreview(`${r.data.result}${r.data.findings.map((f: any) => ` - ${f.message}`).join('')}`);
    } catch (e: any) { setPreview(e.response?.data?.detail || 'Preview failed.'); }
  };
  const group = value.apply_when ?? { match: 'all' as const, conditions: [] };
  return (
    <div className="space-y-3">
      <p style={{ color: 'var(--t1)' }}>{rule.description} {rule.note}</p>
      <datalist id={`cols-${rule.id}`}>{columns.map((c) => <option key={c} value={c} />)}</datalist>
      <Conditions heading="Apply this rule only when" list={group.conditions} rule={rule} cat={cat} onChange={(conditions) => onChange({ apply_when: { match: group.match, conditions } })}
        extra={group.conditions.length > 1 && <select className={`${field} w-24`} style={fieldStyle} value={group.match} aria-label="Combine conditions with" onChange={(e) => onChange({ apply_when: { ...group, match: e.target.value as 'all' | 'any' } })}><option value="all">AND</option><option value="any">OR</option></select>} />
      <Conditions heading="Exceptions (a record matching any of these is exempt)" list={value.exceptions ?? []} rule={rule} cat={cat} onChange={(exceptions) => onChange({ exceptions })} />
      {rule.params.length > 0 && <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {rule.params.map((p) => (
          <label key={p.name} className="block"><span className="block mb-0.5">{p.label}{p.type === 'list' && ' (comma separated)'}</span>
            {p.type === 'map' ? <textarea className={`${field} font-mono`} style={fieldStyle} rows={6} value={texts[p.name]} onChange={(e) => setParam(p, e.target.value)} />
              : <input className={field} style={fieldStyle} value={texts[p.name]} onChange={(e) => setParam(p, e.target.value)} />}
          </label>))}
      </div>}
      <label className="block"><span className="block mb-0.5">Validation message (blank = default message)</span>
        <input className={field} style={fieldStyle} maxLength={500} value={value.message ?? ''} onChange={(e) => onChange({ message: e.target.value })} /></label>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={() => setShowDefault(!showDefault)}>{showDefault ? 'Hide' : 'View'} default rule</Button>
        <Button size="sm" variant="secondary" onClick={() => { onRestore(); setTexts(Object.fromEntries(rule.params.map((p) => [p.name, asText(p, p.default)]))); }}>Restore default</Button>
      </div>
      {showDefault && <pre className="text-[11px] whitespace-pre-wrap p-2 rounded border" style={{ borderColor: 'var(--b1)' }}>{`Enabled, severity Error, no extra conditions or exceptions.\n${rule.params.map((p) => `${p.label}: ${asText(p, p.default) || '(none)'}`).join('\n')}`}</pre>}
      <div className="border-t pt-2" style={{ borderColor: 'var(--b1)' }}>
        <p className="font-semibold mb-1">Rule preview (one sample record, not an IODB validation)</p>
        <textarea className={`${field} font-mono`} style={fieldStyle} rows={4} value={sample} onChange={(e) => setSample(e.target.value)} aria-label="Sample record, one FIELD = value per line" />
        <div className="flex items-center gap-3 mt-1"><Button size="sm" onClick={run}>Preview</Button>{preview && <span data-testid="rule-preview">{preview}</span>}</div>
      </div>
    </div>
  );
}

function Conditions({ heading, list, rule, cat, onChange, extra }: { heading: string; list: Cond[]; rule: Rule; cat: Catalogue; onChange: (l: Cond[]) => void; extra?: React.ReactNode }) {
  const set = (i: number, p: Partial<Cond>) => onChange(list.map((c, n) => (n === i ? { ...c, ...p } : c)));
  return (
    <div>
      <div className="flex items-center gap-3 mb-1"><span className="font-semibold">{heading}</span>{extra}
        <button className="underline" onClick={() => onChange([...list, { field: '', operator: 'equals', value: '' }])}>+ Add</button></div>
      {list.map((c, i) => {
        const needs = cat.operators.find((o) => o.key === c.operator)?.needs_value;
        return (
          <div key={i} className="grid grid-cols-1 md:grid-cols-[1fr_14rem_1fr_auto] gap-2 mb-1">
            <input className={field} style={fieldStyle} list={`cols-${rule.id}`} placeholder="IODB field" aria-label="Condition field" value={c.field} onChange={(e) => set(i, { field: e.target.value })} />
            <select className={field} style={fieldStyle} aria-label="Condition operator" value={c.operator} onChange={(e) => set(i, { operator: e.target.value })}>{cat.operators.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}</select>
            <input className={field} style={fieldStyle} placeholder={needs ? 'Value' : '-'} aria-label="Condition value" disabled={!needs} value={needs ? c.value : ''} onChange={(e) => set(i, { value: e.target.value })} />
            <button className="underline text-red-600" onClick={() => onChange(list.filter((_, n) => n !== i))}>Remove</button>
          </div>);
      })}
    </div>
  );
}
