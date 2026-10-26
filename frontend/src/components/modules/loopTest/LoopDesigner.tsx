/**
 * Steps 3-8 - choose a template / loop type, configure the loop (components, wires, shielding, cables,
 * signals, special cases), preview the drawing, validate, and generate one or many loops.
 *
 * Source data (IODB / I/O Assignment) is shown with badges and is never re-typed; the engineer only
 * decides HOW the loop is presented. Nothing engineering-critical is decided silently.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, Download, Plus, Save, Trash2, X } from 'lucide-react';
import api from '@/services/api';
import Alert from '../../ui/Alert';
import Button from '../../ui/Button';
import Card from '../../ui/Card';
import { Check, Library, LoopConfig, SOURCE_STYLE, TagDetail, Validation } from './types';

interface Props {
  sid: string;
  tag: string;
  library: Library;
  selectedTags: string[];
  onBack: () => void;
  onLibraryChanged: () => void;
  onDecisionMade: () => void;
}

const FIELD_ORDER: [string, string][] = [
  ['TAG_NO', 'Tag'], ['LOOP_NO', 'Loop'], ['INSTRUMENT_TYPE', 'Instrument type'], ['SIGNAL_IO_TYPE', 'Signal'],
  ['POWER_SUPPLY', 'Power'], ['IS_NIS', 'IS / NIS'], ['HART', 'HART'], ['JB_TAG', 'Junction box'],
  ['BRANCH_CABLE_TAG', 'Branch cable'], ['BRANCH_CABLE_TYPE', 'Branch cable type'], ['BRANCH_CABLE_LENGTH', 'Branch length'],
  ['MAIN_CABLE_TAG', 'Main cable'], ['MAIN_CABLE_TYPE', 'Main cable type'], ['MAIN_CABLE_LENGTH', 'Main length'],
  ['PLC', 'PLC / DCS'], ['RACK', 'Rack'], ['SLOT', 'Slot'], ['MODULE', 'Module'], ['CHANNEL', 'Channel'], ['IO_TYPE', 'I/O type'],
  ['TERMINAL_STRIP', 'Terminal strip'], ['TERMINAL_CMN', 'Terminal CMN'], ['TERMINAL_SIGNAL', 'Terminal signal'],
  ['TERMINAL_ZERO', 'Terminal zero'], ['JB_TB1', 'JB TB1'], ['JB_TB2', 'JB TB2'], ['JB_TB3', 'JB TB3'],
];
const OVERRIDABLE = ['PLC', 'RACK', 'SLOT', 'MODULE', 'CHANNEL', 'JB_TAG', 'BRANCH_CABLE_LENGTH', 'MAIN_CABLE_LENGTH'];
const isReal = (v: string) => !!v && !['-', '--', 'TBA', 'NA', 'N/A', 'NIL', 'NONE'].includes(v.trim().toUpperCase());
const TC_TYPES = ['K', 'J', 'T', 'E', 'N', 'R', 'S', 'B'];

const inputSt = { background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)' };
const inp = 'px-2.5 py-1.5 rounded-lg text-xs outline-none w-full';
const label = 'text-[10px] font-semibold uppercase tracking-wider block mb-1';

function Badge2({ src }: { src: string }) {
  const color = SOURCE_STYLE[src] || 'var(--t2)';
  return <span className="text-[9px] font-bold px-1.5 py-0.5 rounded ml-2" style={{ background: `${color}22`, color }}>{src === 'I/O ASSIGNMENT' ? 'I/O' : src === 'USER CONFIGURATION' ? 'USER' : src}</span>;
}

export default function LoopDesigner({ sid, tag, library, selectedTags, onBack, onLibraryChanged, onDecisionMade }: Props) {
  const base = `/loop-wiring-test/sessions/${sid}`;
  const [detail, setDetail] = useState<TagDetail | null>(null);
  const [config, setConfig] = useState<LoopConfig | null>(null);
  const [svg, setSvg] = useState('');
  const [validation, setValidation] = useState<Validation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [templateId, setTemplateId] = useState('');
  const [tplName, setTplName] = useState('');
  const [tplDesc, setTplDesc] = useState('');
  const [results, setResults] = useState<any | null>(null);
  const [newKind, setNewKind] = useState('zener_barrier');
  const seq = useRef(0);

  const err = (e: any, fallback: string) => setError(typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : fallback);

  const loadDetail = useCallback(async () => {
    try {
      const r = await api.get<TagDetail>(`${base}/tags/${encodeURIComponent(tag)}`);
      setDetail(r.data);
      return r.data;
    } catch (e) { err(e, 'Could not load the tag.'); return null; }
  }, [base, tag]);

  useEffect(() => {
    setConfig(null); setSvg(''); setValidation(null); setResults(null); setNotice(''); setError(''); setTemplateId('');
    loadDetail().then((d) => { if (d?.saved_config) setConfig(d.saved_config); });
  }, [loadDetail]);

  // live preview (debounced); the server re-links segments after the engineer reorders components
  useEffect(() => {
    if (!config) return;
    const mine = ++seq.current;
    const t = setTimeout(async () => {
      try {
        const r = await api.post(`${base}/preview`, { config });
        if (mine !== seq.current) return;
        setSvg(r.data.svg); setValidation(r.data.validation);
        const ends = (c: LoopConfig) => (c.links || []).map((l: any) => `${l.from_id}>${l.to_id}`).join('|');
        if (ends(r.data.config) !== ends(config)) setConfig((c) => (c ? { ...c, links: r.data.config.links } : c));
      } catch (e) { if (mine === seq.current) err(e, 'Preview failed.'); }
    }, 450);
    return () => clearTimeout(t);
  }, [config, base]);

  const patch = (changes: Partial<LoopConfig>) => setConfig((c) => (c ? { ...c, ...changes } : c));
  const patchParams = (changes: Record<string, any>) => setConfig((c) => (c ? { ...c, params: { ...c.params, ...changes } } : c));

  // ── choosing the starting point ───────────────────────────────────────────
  const startFromTemplate = async (id: string) => {
    setTemplateId(id); setBusy(true); setError('');
    try {
      if (id.startsWith('type:')) {
        const r = await api.post(`${base}/config/default`, { tag, loop_type: id.slice(5), params: {}, signals: [] });
        setConfig(r.data);
      } else if (id) {
        const r = await api.post(`${base}/config/from-template`, { template_id: id, tag });
        setConfig(r.data);
      }
    } catch (e) { err(e, 'Could not start from that template.'); } finally { setBusy(false); }
  };

  // ── loop-type specific editors ────────────────────────────────────────────
  const wireEntry = (role: string) => ({ role, label: library.wire_roles[role] || role, colour: '', number: '', terminal_from: '', terminal_to: '' });
  const setRtdWires = (n: string) => {
    const roles: string[] = (library as any).rtd_wires?.[n] || [];
    setConfig((c) => c && ({ ...c, params: { ...c.params, rtd_wires: n }, links: c.links.map((l: any) => ({ ...l, auto_wires: false, wires: roles.map(wireEntry) })) }));
  };
  const catalog = (): { id: string; name: string; signal_type: string }[] => {
    if (!config) return [];
    if (config.loop_type === 'MOTOR') return library.motor_starters[config.params.starter]?.signals || [];
    if (config.loop_type === 'VALVE') return library.valve_types[config.params.valve_type]?.signals || [];
    return [];
  };
  const setKindParam = (key: 'starter' | 'valve_type', value: string) => {
    setConfig((c) => {
      if (!c) return c;
      const ids = new Set((key === 'starter' ? library.motor_starters[value] : library.valve_types[value])?.signals.map((s) => s.id) || []);
      return { ...c, params: { ...c.params, [key]: value }, signals: c.signals.filter((s: any) => ids.has(s.id)) };
    });
  };
  const toggleSignal = (s: { id: string; name: string; signal_type: string }) => {
    setConfig((c) => {
      if (!c) return c;
      const has = c.signals.some((x: any) => x.id === s.id);
      const dir = ['DO', 'AO'].includes(s.signal_type) ? 'system_to_field' : 'field_to_system';
      return { ...c, signals: has ? c.signals.filter((x: any) => x.id !== s.id) : [...c.signals, { id: s.id, name: s.name, signal_type: s.signal_type, direction: dir, io_index: null }] };
    });
  };
  const addCustomSignal = () => patch({ signals: [...(config?.signals || []), { id: `custom_${Date.now()}`, name: 'New signal', signal_type: 'DI', direction: 'field_to_system', io_index: null }] });
  const updateSignal = (i: number, changes: Record<string, any>) => patch({ signals: config!.signals.map((s: any, k: number) => (k === i ? { ...s, ...changes } : s)) });

  // ── components ────────────────────────────────────────────────────────────
  const nextId = () => `c${Math.max(0, ...config!.components.map((c: any) => parseInt(String(c.id).slice(1)) || 0)) + 1}`;
  const addComponent = () => {
    const kind = newKind;
    const comp = { id: nextId(), kind, label: library.components[kind]?.label || kind, tag: '', placement: kind === 'power_supply' ? 'side' : 'main',
      attach_to: kind === 'power_supply' ? (config!.components.find((c: any) => library.components[c.kind]?.group === 'field')?.id || '') : '', terminals: [], notes: '' };
    const comps = [...config!.components];
    const sysIdx = comps.findIndex((c: any) => library.components[c.kind]?.group === 'system');
    comps.splice(comp.placement === 'main' && sysIdx > 0 ? sysIdx : comps.length, 0, comp);   // before the PLC end by default
    patch({ components: comps });
  };
  const moveComp = (i: number, d: number) => {
    const comps = [...config!.components]; const j = i + d;
    if (j < 0 || j >= comps.length) return;
    [comps[i], comps[j]] = [comps[j], comps[i]];
    patch({ components: comps });
  };
  const updateComp = (i: number, changes: Record<string, any>) => patch({ components: config!.components.map((c: any, k: number) => (k === i ? { ...c, ...changes } : c)) });
  const removeComp = (i: number) => patch({ components: config!.components.filter((_: any, k: number) => k !== i) });

  // ── links ─────────────────────────────────────────────────────────────────
  const updateLink = (i: number, changes: Record<string, any>) => patch({ links: config!.links.map((l: any, k: number) => (k === i ? { ...l, ...changes } : l)) });
  const updateCable = (i: number, changes: Record<string, any>) => updateLink(i, { cable: { ...config!.links[i].cable, ...changes } });
  const updateWire = (li: number, wi: number, changes: Record<string, any>) =>
    updateLink(li, { auto_wires: false, wires: config!.links[li].wires.map((w: any, k: number) => (k === wi ? { ...w, ...changes } : w)) });
  const compName = (id: string) => { const c = config!.components.find((x: any) => x.id === id); return c ? (c.tag || c.label) : id; };

  // ── actions ───────────────────────────────────────────────────────────────
  const decide = async (field: string, choice: string) => {
    await api.post(`${base}/decisions`, { kind: 'conflict', tag, field, choice });
    await loadDetail(); onDecisionMade();
    if (config) setConfig({ ...config });                                  // re-run preview/validation
  };
  const saveConfig = async () => {
    try { await api.put(`${base}/config`, { config }); setNotice('Configuration saved for this tag.'); } catch (e) { err(e, 'Save failed.'); }
  };
  const saveTemplate = async () => {
    try {
      await api.post('/loop-wiring-test/templates', { name: tplName, description: tplDesc, config });
      setNotice(`Template "${tplName}" saved - it is now in the template list.`); setTplName(''); setTplDesc(''); onLibraryChanged();
    } catch (e) { err(e, 'Could not save the template.'); }
  };
  const generate = async (tags: string[]) => {
    setBusy(true); setError(''); setResults(null);
    try {
      const configs: Record<string, any> = {};
      for (const t of tags) {
        configs[t] = t === tag ? config : (await api.post(`${base}/config/clone`, { config, tag: t })).data;
      }
      const r = await api.post(`${base}/generate`, { tags, configs, allow_warnings: true });
      setResults(r.data);
    } catch (e) { err(e, 'Generation failed.'); } finally { setBusy(false); }
  };
  const download = async () => {
    const r = await api.get(`${base}/download`, { responseType: 'blob' });
    const url = URL.createObjectURL(new Blob([r.data]));
    const a = document.createElement('a'); a.href = url; a.download = results?.filename || 'Loop_Wiring_Test.xlsx';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const mainTypes = Object.values(library.loop_types).filter((t) => t.status === 'available');
  const plannedTypes = Object.values(library.loop_types).filter((t) => t.status !== 'available');
  const cat = catalog();
  const missingOverridable = detail ? OVERRIDABLE.filter((k) => !isReal(detail.fields[k]?.value || '') && !(config?.overrides?.[k])) : [];
  const statusColor = (s: Check['status']) => (s === 'PASS' ? '#4ade80' : s === 'WARNING' ? 'var(--gold)' : 'var(--rose)');

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack}>← Back to matching</Button>
        <h3 className="text-base font-bold" style={{ color: 'var(--t0)' }}>Loop design · <span className="font-mono">{tag}</span></h3>
        {detail && <span className="text-xs" style={{ color: 'var(--t2)' }}>loop {detail.loop || '—'} · {detail.status}</span>}
      </div>
      {error && <Alert variant="error" onClose={() => setError('')}>{error}</Alert>}
      {notice && <Alert variant="success" onClose={() => setNotice('')}>{notice}</Alert>}

      <div className="grid grid-cols-1 xl:grid-cols-[340px,1fr] gap-4">
        {/* ── source data ── */}
        <Card title="Tag details" description="Values come from the source documents - badges show which.">
          {detail?.conflicts.map((c) => (
            <Alert key={c.field} variant={c.decision ? 'info' : 'warning'} className="mb-2" title={`${c.label} conflict`}>
              IODB <b>{c.iodb}</b> · I/O Assignment <b>{c.io}</b>
              {c.decision ? <span> — decided: {c.decision === 'iodb' ? 'IODB' : 'I/O Assignment'} <button className="underline ml-1" onClick={() => decide(c.field, '')}>undo</button></span>
                : <div className="mt-1"><button className="underline mr-3" onClick={() => decide(c.field, 'iodb')}>Accept IODB</button>
                  <button className="underline" onClick={() => decide(c.field, 'io')}>Accept I/O Assignment</button></div>}
            </Alert>
          ))}
          <dl className="text-xs space-y-1">
            {FIELD_ORDER.map(([k, lab]) => {
              const f = detail?.fields[k];
              if (!f || !f.available) return null;
              const real = isReal(f.value);
              return (
                <div key={k} className="flex justify-between gap-2" style={{ borderBottom: '1px solid var(--b1)', paddingBottom: 3 }}>
                  <dt style={{ color: 'var(--t2)' }}>{lab}</dt>
                  <dd className="text-right" style={{ color: real ? 'var(--t0)' : 'var(--rose)' }}>{real ? f.value : 'not available'}<Badge2 src={f.source} /></dd>
                </div>
              );
            })}
          </dl>
          {detail && detail.signals.length > 0 && (
            <div className="mt-3">
              <p className={label} style={{ color: 'var(--t2)' }}>I/O assignment rows ({detail.signals.length})</p>
              {detail.signals.map((s, i) => (
                <p key={i} className="text-[11px] font-mono" style={{ color: 'var(--t1)' }}>#{i + 1} {s.io_type} · R{s.rack || '?'}/S{s.slot || '?'}/CH{s.channel || '?'} · {s.terminal_strip}</p>
              ))}
            </div>
          )}
        </Card>

        <div className="space-y-4">
          {/* ── template / loop type ── */}
          <Card title="Loop template">
            <div className="flex flex-wrap gap-3 items-end">
              <div className="flex-1 min-w-[260px]">
                <label className={label} style={{ color: 'var(--t2)' }}>Template or loop type</label>
                <select className={inp} style={inputSt} value={templateId} onChange={(e) => startFromTemplate(e.target.value)}>
                  <option value="">— choose —</option>
                  {detail?.suggested_loop_type && <option value={`type:${detail.suggested_loop_type}`}>Suggested for this signal: {library.loop_types[detail.suggested_loop_type]?.label}</option>}
                  <optgroup label="Built-in templates">
                    {Object.values(library.builtin_templates).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </optgroup>
                  {library.saved_templates.length > 0 && (
                    <optgroup label="Saved templates">{library.saved_templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</optgroup>
                  )}
                  <optgroup label="Loop types (start from scratch)">
                    {mainTypes.map((t) => <option key={t.id} value={`type:${t.id}`}>{t.label}</option>)}
                  </optgroup>
                </select>
              </div>
              {plannedTypes.length > 0 && (
                <p className="text-[11px]" style={{ color: 'var(--t2)' }}>Planned (not yet available): {plannedTypes.map((t) => t.label.replace(' (planned)', '')).join(', ')}</p>
              )}
            </div>
            {detail?.suggested_loop_type && !config && (
              <p className="text-[11px] mt-2" style={{ color: 'var(--t2)' }}>The assigned I/O channel looks like a {detail.suggested_loop_type} signal - this is only a suggestion.</p>
            )}
          </Card>

          {config && (
            <>
              <Card title={`Configuration · ${library.loop_types[config.loop_type]?.label || config.loop_type}`}>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <label className={label} style={{ color: 'var(--t2)' }}>Layout</label>
                    <select className={inp} style={inputSt} value={config.layout.orientation}
                      onChange={(e) => patch({ layout: { ...config.layout, orientation: e.target.value } })}>
                      <option value="vertical">Vertical</option><option value="horizontal">Horizontal</option>
                    </select>
                  </div>
                  <div>
                    <label className={label} style={{ color: 'var(--t2)' }}>Flow direction</label>
                    <select className={inp} style={inputSt} value={config.layout.flow_direction}
                      onChange={(e) => patch({ layout: { ...config.layout, flow_direction: e.target.value } })}>
                      {Object.entries(library.flow_directions).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                    </select>
                  </div>
                  {['AI_2WIRE', 'AI_4WIRE', 'AO', 'ANALYZER'].includes(config.loop_type) && (
                    <div>
                      <label className={label} style={{ color: 'var(--t2)' }}>HART</label>
                      <select className={inp} style={inputSt} value={config.params.hart === undefined ? '' : String(config.params.hart)}
                        onChange={(e) => patchParams({ hart: e.target.value === '' ? undefined : e.target.value === 'true' })}>
                        <option value="">As in IODB</option><option value="true">Yes</option><option value="false">No</option>
                      </select>
                    </div>
                  )}
                  {config.loop_type === 'RTD' && (
                    <div>
                      <label className={label} style={{ color: 'var(--t2)' }}>RTD wiring (required)</label>
                      <div className="flex gap-3 text-xs" style={{ color: 'var(--t1)' }}>
                        {['2', '3', '4'].map((n) => (
                          <label key={n}><input type="radio" checked={String(config.params.rtd_wires) === n} onChange={() => setRtdWires(n)} /> {n}-wire</label>
                        ))}
                      </div>
                    </div>
                  )}
                  {config.loop_type === 'TC' && (
                    <>
                      <div>
                        <label className={label} style={{ color: 'var(--t2)' }}>Thermocouple type (required)</label>
                        <select className={inp} style={inputSt} value={config.params.tc_type || ''} onChange={(e) => patchParams({ tc_type: e.target.value })}>
                          <option value="">— choose —</option>{TC_TYPES.map((t) => <option key={t} value={t}>Type {t}</option>)}
                        </select>
                      </div>
                      <label className="text-xs flex items-center gap-2" style={{ color: 'var(--t1)' }}>
                        <input type="checkbox" checked={!!config.params.extension_cable} onChange={(e) => patchParams({ extension_cable: e.target.checked })} /> Extension / compensating cable
                      </label>
                    </>
                  )}
                  {config.loop_type === 'DI' && (
                    <div>
                      <label className={label} style={{ color: 'var(--t2)' }}>Contact</label>
                      <select className={inp} style={inputSt} value={config.params.contact || ''} onChange={(e) => patchParams({ contact: e.target.value })}>
                        <option value="">—</option><option value="NO">NO</option><option value="NC">NC</option><option value="dry">Dry</option><option value="powered">Powered</option>
                      </select>
                    </div>
                  )}
                  {config.loop_type === 'DO' && (
                    <div>
                      <label className={label} style={{ color: 'var(--t2)' }}>Load</label>
                      <select className={inp} style={inputSt} value={config.params.load || ''} onChange={(e) => patchParams({ load: e.target.value })}>
                        <option value="">—</option>{['solenoid', 'relay', 'contactor', 'actuator', 'other'].map((x) => <option key={x} value={x}>{x}</option>)}
                      </select>
                    </div>
                  )}
                </div>

                {(config.loop_type === 'MOTOR' || config.loop_type === 'VALVE') && (
                  <div className="mt-4">
                    <label className={label} style={{ color: 'var(--t2)' }}>{config.loop_type === 'MOTOR' ? 'Motor starter (required)' : 'Valve type (required)'}</label>
                    <div className="flex flex-wrap gap-4 text-xs mb-3" style={{ color: 'var(--t1)' }}>
                      {Object.entries(config.loop_type === 'MOTOR' ? library.motor_starters : library.valve_types).map(([k, v]) => (
                        <label key={k}><input type="radio" checked={(config.loop_type === 'MOTOR' ? config.params.starter : config.params.valve_type) === k}
                          onChange={() => setKindParam(config.loop_type === 'MOTOR' ? 'starter' : 'valve_type', k)} /> {v.label}</label>
                      ))}
                    </div>
                    {cat.length > 0 && (
                      <>
                        <label className={label} style={{ color: 'var(--t2)' }}>Signals in this loop - tick only what exists (nothing is pre-selected)</label>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-1.5">
                          {cat.map((s) => (
                            <label key={s.id} className="text-xs flex items-center gap-2" style={{ color: 'var(--t1)' }}>
                              <input type="checkbox" checked={config.signals.some((x: any) => x.id === s.id)} onChange={() => toggleSignal(s)} />
                              {s.name} <span style={{ color: 'var(--t2)' }}>[{s.signal_type}]</span>
                            </label>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                )}

                <div className="mt-4">
                  <div className="flex items-center justify-between">
                    <label className={label} style={{ color: 'var(--t2)' }}>Signals & I/O rows ({config.signals.length})</label>
                    <Button size="sm" variant="ghost" onClick={addCustomSignal}><Plus className="w-3 h-3" /> Add signal</Button>
                  </div>
                  {config.signals.map((s: any, i: number) => (
                    <div key={s.id} className="grid grid-cols-[1.4fr,70px,1.6fr,24px] gap-2 mb-1.5 items-center">
                      <input className={inp} style={inputSt} value={s.name} onChange={(e) => updateSignal(i, { name: e.target.value })} />
                      <select className={inp} style={inputSt} value={s.signal_type} onChange={(e) => updateSignal(i, { signal_type: e.target.value })}>
                        {['AI', 'AO', 'DI', 'DO', 'RTD', 'TC', 'PI'].map((x) => <option key={x}>{x}</option>)}
                      </select>
                      <select className={inp} style={inputSt} value={s.io_index ?? ''} onChange={(e) => updateSignal(i, { io_index: e.target.value === '' ? null : Number(e.target.value) })}>
                        <option value="">— not linked —</option>
                        {detail?.signals.map((io, k) => <option key={k} value={k}>#{k + 1} {io.io_type} R{io.rack}/S{io.slot}/CH{io.channel}</option>)}
                      </select>
                      <button title="Remove signal" onClick={() => patch({ signals: config.signals.filter((_: any, k: number) => k !== i) })}><X className="w-3.5 h-3.5" style={{ color: 'var(--t2)' }} /></button>
                    </div>
                  ))}
                  {config.signals.length > 1 && <p className="text-[11px]" style={{ color: 'var(--t2)' }}>Channels are never assigned automatically - link each signal to its I/O Assignment row.</p>}
                </div>
              </Card>

              <Card title="Components & order" description="Field → system order. Add, remove or reorder; segments between them follow.">
                {config.components.map((c: any, i: number) => (
                  <div key={c.id} className="grid grid-cols-[130px,1fr,1fr,auto] gap-2 items-center mb-1.5">
                    <span className="text-xs font-semibold" style={{ color: 'var(--t1)' }}>{library.components[c.kind]?.label || c.kind}{c.placement === 'side' && ' (side)'}</span>
                    <input className={inp} style={inputSt} value={c.label} placeholder="Label" onChange={(e) => updateComp(i, { label: e.target.value })} />
                    <input className={inp} style={inputSt} value={c.tag} placeholder="Tag / reference (optional)" onChange={(e) => updateComp(i, { tag: e.target.value })} />
                    <span className="flex gap-1">
                      <button title="Up" onClick={() => moveComp(i, -1)}><ArrowUp className="w-3.5 h-3.5" style={{ color: 'var(--t2)' }} /></button>
                      <button title="Down" onClick={() => moveComp(i, 1)}><ArrowDown className="w-3.5 h-3.5" style={{ color: 'var(--t2)' }} /></button>
                      <button title="Remove" onClick={() => removeComp(i)}><Trash2 className="w-3.5 h-3.5" style={{ color: 'var(--rose)' }} /></button>
                    </span>
                  </div>
                ))}
                <div className="flex gap-2 mt-2">
                  <select className={inp} style={{ ...inputSt, maxWidth: 260 }} value={newKind} onChange={(e) => setNewKind(e.target.value)}>
                    {Object.entries(library.components).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                  <Button size="sm" variant="secondary" onClick={addComponent}><Plus className="w-3 h-3" /> Add component</Button>
                </div>
              </Card>

              <Card title="Wires, cables & shielding" description="One block per segment. Cable tag/type/length come from the IODB when the source is Branch or Main.">
                {config.links.map((l: any, i: number) => (
                  <div key={`${l.from_id}-${l.to_id}`} className="rounded-xl p-3 mb-3" style={{ background: 'var(--s3)', border: '1px solid var(--b2)' }}>
                    <p className="text-xs font-bold mb-2" style={{ color: 'var(--t0)' }}>{compName(l.from_id)} → {compName(l.to_id)} <span style={{ color: 'var(--t2)' }}>· {l.wires.length} wires</span></p>
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-2 mb-2">
                      <div>
                        <label className={label} style={{ color: 'var(--t2)' }}>Cable data from</label>
                        <select className={inp} style={inputSt} value={l.cable.source} onChange={(e) => updateCable(i, { source: e.target.value })}>
                          <option value="none">No cable</option><option value="branch">Branch cable (IODB)</option>
                          <option value="main">Main cable (IODB)</option><option value="custom">Custom</option>
                        </select>
                      </div>
                      <div>
                        <label className={label} style={{ color: 'var(--t2)' }}>Shield</label>
                        <select className={inp} style={inputSt} value={l.cable.shield_type ?? ''} onChange={(e) => updateCable(i, { shield_type: e.target.value || null })}>
                          <option value="">— not set —</option>{Object.entries(library.shield_types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className={label} style={{ color: 'var(--t2)' }}>Shield termination</label>
                        <select className={inp} style={inputSt} value={l.cable.shield_termination ?? ''} disabled={!l.cable.shield_type || l.cable.shield_type === 'none'}
                          onChange={(e) => updateCable(i, { shield_termination: e.target.value || null })}>
                          <option value="">— not set —</option>{Object.entries(library.shield_terminations).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                        </select>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div><label className={label} style={{ color: 'var(--t2)' }}>Cores</label><input className={inp} style={inputSt} value={l.cable.cores} placeholder="auto" onChange={(e) => updateCable(i, { cores: e.target.value })} /></div>
                        <div><label className={label} style={{ color: 'var(--t2)' }}>Pairs</label><input className={inp} style={inputSt} value={l.cable.pairs} placeholder="auto" onChange={(e) => updateCable(i, { pairs: e.target.value })} /></div>
                      </div>
                    </div>
                    {l.cable.source === 'custom' && (
                      <div className="grid grid-cols-3 gap-2 mb-2">
                        {(['tag', 'type', 'length'] as const).map((k) => (
                          <input key={k} className={inp} style={inputSt} placeholder={`Cable ${k}`} value={l.cable[k]} onChange={(e) => updateCable(i, { [k]: e.target.value })} />
                        ))}
                      </div>
                    )}
                    {l.wires.map((w: any, wi: number) => (
                      <div key={wi} className="grid grid-cols-[1.4fr,1fr,1fr,1fr,1fr,24px] gap-1.5 mb-1 items-center">
                        <input className={inp} style={inputSt} value={w.label} onChange={(e) => updateWire(i, wi, { label: e.target.value })} />
                        <input className={inp} style={inputSt} value={w.colour} placeholder="Colour" onChange={(e) => updateWire(i, wi, { colour: e.target.value })} />
                        <input className={inp} style={inputSt} value={w.number} placeholder="Wire no." onChange={(e) => updateWire(i, wi, { number: e.target.value })} />
                        <input className={inp} style={inputSt} value={w.terminal_from} placeholder="Terminal from" onChange={(e) => updateWire(i, wi, { terminal_from: e.target.value })} />
                        <input className={inp} style={inputSt} value={w.terminal_to} placeholder="Terminal to" onChange={(e) => updateWire(i, wi, { terminal_to: e.target.value })} />
                        <button title="Remove wire" onClick={() => updateLink(i, { auto_wires: false, wires: l.wires.filter((_: any, k: number) => k !== wi) })}><X className="w-3.5 h-3.5" style={{ color: 'var(--t2)' }} /></button>
                      </div>
                    ))}
                    <div className="flex items-center gap-2 mt-1">
                      <select className={inp} style={{ ...inputSt, maxWidth: 220 }} id={`role-${i}`} defaultValue="SPARE">
                        {Object.entries(library.wire_roles).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                      </select>
                      <Button size="sm" variant="ghost" onClick={() => {
                        const role = (document.getElementById(`role-${i}`) as HTMLSelectElement).value;
                        updateLink(i, { auto_wires: false, wires: [...l.wires, wireEntry(role)] });
                      }}><Plus className="w-3 h-3" /> Add wire</Button>
                    </div>
                  </div>
                ))}
              </Card>

              {missingOverridable.length > 0 && (
                <Card title="Supply missing data yourself" description="Only for values that are absent from both documents. They are marked USER CONFIGURATION in the drawing.">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {missingOverridable.map((k) => (
                      <div key={k}><label className={label} style={{ color: 'var(--t2)' }}>{detail?.fields[k]?.label || k}</label>
                        <input className={inp} style={inputSt} onChange={(e) => patch({ overrides: { ...(config.overrides || {}), [k]: e.target.value } })} /></div>
                    ))}
                  </div>
                </Card>
              )}
            </>
          )}
        </div>
      </div>

      {config && (
        <>
          <div className="grid grid-cols-1 xl:grid-cols-[1fr,360px] gap-4">
            <Card title="Loop preview" description="The same model that is written to the workbook. Missing data is shown in red, never invented.">
              <div className="rounded-lg overflow-auto" style={{ background: '#fff', border: '1px solid #d0d0d0', maxHeight: 760 }}
                dangerouslySetInnerHTML={{ __html: svg || '<p style="padding:24px;color:#777;font-family:Arial">Building preview…</p>' }} />
            </Card>
            <Card title={validation ? `Validation · ${validation.passed}/${validation.total} passed` : 'Validation'}>
              {validation?.checks.map((c) => (
                <p key={c.id} className="text-xs mb-1.5" style={{ color: statusColor(c.status) }}>
                  {c.status === 'PASS' ? '✓' : c.status === 'WARNING' ? '⚠' : '✗'} <b>{c.label}</b>
                  {c.detail && <span style={{ color: 'var(--t1)' }}> — {c.detail}</span>}
                </p>
              ))}
              {validation && !validation.can_generate && (
                <Alert variant="error" className="mt-3">{validation.errors} error(s) must be resolved first. Warnings alone do not block generation.</Alert>
              )}
            </Card>
          </div>

          <Card title="Output">
            <div className="flex flex-wrap gap-3 items-end mb-4">
              <Button variant="secondary" onClick={saveConfig}><Save className="w-4 h-4" /> Save configuration</Button>
              <Button onClick={() => generate([tag])} disabled={!validation?.can_generate} loading={busy}>
                Generate this loop{validation && validation.warnings > 0 ? ` (${validation.warnings} warning${validation.warnings > 1 ? 's' : ''})` : ''}
              </Button>
              <Button variant="secondary" onClick={() => generate(Array.from(new Set([tag, ...selectedTags])))} disabled={!validation?.can_generate || selectedTags.length === 0} loading={busy}>
                Generate selected loops ({selectedTags.length}) with this design
              </Button>
              <p className="text-[11px] w-full" style={{ color: 'var(--t2)' }}>
                Each selected tag gets its own data and its own validation; loops with errors are skipped and reported, never drawn incompletely.
              </p>
            </div>
            {results && (
              <div className="mb-4">
                <p className="text-sm font-bold mb-2" style={{ color: 'var(--t0)' }}>{results.generated} loop(s) generated</p>
                {results.results.map((r: any) => (
                  <p key={r.tag} className="text-xs" style={{ color: r.status === 'GENERATED' ? '#4ade80' : 'var(--rose)' }}>
                    {r.status === 'GENERATED' ? '✓' : '✗'} {r.tag} — {r.status}{r.reason ? `: ${r.reason}` : ''}{r.warnings ? ` (${r.warnings} warning(s))` : ''}
                  </p>
                ))}
                {results.filename && <Button className="mt-3" onClick={download}><Download className="w-4 h-4" /> Download {results.filename}</Button>}
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-[1fr,1.4fr,auto] gap-2 items-end pt-3" style={{ borderTop: '1px solid var(--b1)' }}>
              <div><label className={label} style={{ color: 'var(--t2)' }}>Save as template - name</label>
                <input className={inp} style={inputSt} value={tplName} onChange={(e) => setTplName(e.target.value)} placeholder="e.g. AI 2-wire + individual shield + barrier" /></div>
              <div><label className={label} style={{ color: 'var(--t2)' }}>Description</label>
                <input className={inp} style={inputSt} value={tplDesc} onChange={(e) => setTplDesc(e.target.value)} /></div>
              <Button variant="secondary" disabled={!tplName.trim()} onClick={saveTemplate}>Save template</Button>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
