/**
 * Loop Wiring (Test) - block-based loop designer.
 *
 *   IODB + I/O Assignment + the engineer's graph  ->  validation  ->  drawing / Excel
 *
 * Left: component library. Centre: canvas (drag blocks, drag port -> port to wire). Right: properties of the
 * selected block / wire / cable. Every change goes to the server, which validates and renders the SAME graph
 * for the preview and for the workbook. Nothing is connected unless the engineer connects it.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { AlignCenterHorizontal, AlignCenterVertical, AlignHorizontalJustifyStart, AlignVerticalJustifyStart, Copy, Download, Plus, Redo2, Save, Trash2, Undo2, X } from 'lucide-react';
import api from '@/services/api';
import Alert from '../../ui/Alert';
import Button from '../../ui/Button';
import Card from '../../ui/Card';
import GraphCanvas, { Scene, Selection } from './GraphCanvas';
import { Check, Library, TagDetail, Validation } from './types';

type G = Record<string, any>;
interface GLib {
  templates: { id: string; name: string; kind: string }[];
  palette: { group: string; items: { id: string; label: string; zone: string }[] }[];
  shield_types: Record<string, string>; shield_terminations: Record<string, string>;
  kinds: string[]; families: string[]; orientations: string[]; profiles: Record<string, string>; default_zones: any[];
}
interface Props {
  sid: string; tag: string; library: Library; selectedTags: string[];
  onBack: () => void; onLibraryChanged: () => void; onDecisionMade: () => void;
}

const inputSt = { background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)' };
const inp = 'px-2 py-1.5 rounded-lg text-xs outline-none w-full';
const lab = 'text-[10px] font-semibold uppercase tracking-wider block mb-1';
const btn = 'text-xs px-2 py-1.5 rounded-lg flex items-center gap-1 disabled:opacity-40';
const btnSt = { background: 'var(--s3)', color: 'var(--t0)', border: '1px solid var(--b2)' };
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));

function TagPicker({ sid, mode, onPick, onClose }: { sid: string; mode: 'tag' | 'jb'; onPick: (v: any) => void; onClose: () => void }) {
  const [q, setQ] = useState('');
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    const t = setTimeout(() => {
      api.get(`/loop-wiring-test/sessions/${sid}/${mode === 'tag' ? 'iodb-tags' : 'iodb-jbs'}`, { params: { q } }).then((r) => setRows(r.data)).catch(() => setRows([]));
    }, 200);
    return () => clearTimeout(t);
  }, [q, sid, mode]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,.55)' }} onClick={onClose}>
      <div className="rounded-xl p-4 w-[760px] max-w-[95vw]" style={{ background: 'var(--s2)', border: '1px solid var(--b2)' }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>{mode === 'tag' ? 'Select a tag from the IODB' : 'Select a junction box from the IODB'}</p>
          <button onClick={onClose}><X className="w-4 h-4" style={{ color: 'var(--t2)' }} /></button>
        </div>
        <input autoFocus className={inp} style={inputSt} placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="mt-2 overflow-auto" style={{ maxHeight: 380 }}>
          {mode === 'tag' && <p className="text-[10px] grid grid-cols-[1.2fr,1fr,1.6fr,.5fr,1.2fr,1fr] gap-2 mb-1" style={{ color: 'var(--t2)' }}><span>TAG</span><span>LOOP</span><span>INSTRUMENT TYPE</span><span>SIGNAL</span><span>SERVICE</span><span>JB</span></p>}
          {rows.map((r) => mode === 'tag' ? (
            <button key={r.tag} className="grid grid-cols-[1.2fr,1fr,1.6fr,.5fr,1.2fr,1fr] gap-2 w-full text-left text-xs py-1 px-1 rounded hover:opacity-80" style={{ color: 'var(--t0)', borderTop: '1px solid var(--b1)' }} onClick={() => onPick(r)}>
              <span className="font-mono">{r.tag}</span><span>{r.loop}</span><span>{r.type}</span><span>{r.signal}</span><span className="truncate">{r.service}</span><span>{r.jb}</span>
            </button>
          ) : (
            <button key={r} className="block w-full text-left text-xs py-1 px-1 font-mono" style={{ color: 'var(--t0)', borderTop: '1px solid var(--b1)' }} onClick={() => onPick(r)}>{r}</button>
          ))}
          {rows.length === 0 && <p className="text-xs p-3" style={{ color: 'var(--t2)' }}>Nothing found.</p>}
        </div>
      </div>
    </div>
  );
}

export default function GraphDesigner({ sid, tag, library, selectedTags, onBack, onLibraryChanged, onDecisionMade }: Props) {
  const base = `/loop-wiring-test/sessions/${sid}`;
  const gbase = `${base}/graph`;
  const [glib, setGlib] = useState<GLib | null>(null);
  const [detail, setDetail] = useState<TagDetail | null>(null);
  const [graph, setGraph] = useState<G | null>(null);
  const [scene, setScene] = useState<Scene | null>(null);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [cables, setCables] = useState<Record<string, any>>({});
  const [sel, setSel] = useState<Selection>({ kind: 'none', ids: [] });
  const [error, setError] = useState('');
  const [invalid, setInvalid] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<any | null>(null);
  const [picker, setPicker] = useState<null | { mode: 'tag' | 'jb'; apply: (v: any) => void }>(null);
  const [catalog, setCatalog] = useState<any[]>([]);
  const [ioRows, setIoRows] = useState<Record<string, any[]>>({});
  const [tplName, setTplName] = useState('');
  const [dup, setDup] = useState<null | { tags: string[]; out: any | null }>(null);
  const [, bump] = useState(0);
  const [rfState, setRfState] = useState<any>(null);
  const [allWires, setAllWires] = useState(true);
  const past = useRef<G[]>([]);
  const future = useRef<G[]>([]);
  const lastPush = useRef(0);
  const seq = useRef(0);
  const timer = useRef<any>(null);
  const graphRef = useRef<G | null>(null);
  graphRef.current = graph;

  const err = (e: any, fb: string) => setError(typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : fb);
  const cfgOf = (g: G, t = tag) => ({ tag_no: t, loop_number: g.loop || detail?.loop || '', project_id: '', loop_type: 'GRAPH', graph: g });

  // ── load ──────────────────────────────────────────────────────────────────
  const loadDetail = useCallback(async () => {
    const r = await api.get<TagDetail>(`${base}/tags/${encodeURIComponent(tag)}`);
    setDetail(r.data);
    return r.data;
  }, [base, tag]);
  useEffect(() => {
    api.get('/loop-wiring-test/graph/library').then((r) => setGlib(r.data)).catch((e) => err(e, 'Could not load the component library.'));
    setGraph(null); setScene(null); setValidation(null); setSel({ kind: 'none', ids: [] }); setResults(null); past.current = []; future.current = [];
    loadDetail().then((d) => { if (d.saved_config?.graph) refresh(d.saved_config.graph); }).catch((e) => err(e, 'Could not load the tag.'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tag, sid]);

  const applyBundle = (b: any) => {
    setGraph(b.graph); setScene(b.scene); setValidation(b.validation); setCables(b.cables || {});
  };
  const refresh = useCallback(async (g: G) => {
    const mine = ++seq.current;
    try {
      const r = await api.post(`${gbase}/view`, { graph: g });
      if (mine !== seq.current) return;
      applyBundle(r.data);
    } catch (e) { if (mine === seq.current) err(e, 'Could not draw the loop.'); }
  }, [gbase]);

  const pushHistory = (g: G, coalesce = false) => {
    const now = Date.now();
    if (coalesce && now - lastPush.current < 1500) return;
    lastPush.current = now;
    past.current.push(clone(g)); if (past.current.length > 80) past.current.shift();
    future.current = [];
    bump((x) => x + 1);
  };
  /** local edit with debounced redraw */
  const edit = (mutate: (g: G) => void, coalesce = false) => {
    const cur = graphRef.current; if (!cur) return;
    pushHistory(cur, coalesce);
    const g = clone(cur); mutate(g);
    setGraph(g); graphRef.current = g;
    clearTimeout(timer.current);
    timer.current = setTimeout(() => refresh(g), 350);
  };
  const undo = () => {
    const cur = graphRef.current; const g = past.current.pop(); if (!cur || !g) return;
    future.current.push(clone(cur)); setGraph(g); graphRef.current = g; refresh(g); bump((x) => x + 1);
  };
  const redo = () => {
    const cur = graphRef.current; const g = future.current.pop(); if (!cur || !g) return;
    past.current.push(clone(cur)); setGraph(g); graphRef.current = g; refresh(g); bump((x) => x + 1);
  };
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(t?.tagName)) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); }
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); }
      else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') { e.preventDefault(); duplicateNodes(); }
      else if (e.key === 'Delete' || e.key === 'Backspace') { deleteSelection(); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  });

  // server operations that return a new bundle
  const serverOp = async (path: string, body: any) => {
    const cur = graphRef.current;
    try {
      const r = await api.post(`${gbase}/${path}`, { graph: cur || { nodes: [], edges: [], cables: [], zones: [], tag }, ...body });
      if (cur) pushHistory(cur);
      applyBundle(r.data); graphRef.current = r.data.graph;
      return r.data;
    } catch (e) { err(e, 'The server rejected that change.'); return null; }
  };

  // ── templates ─────────────────────────────────────────────────────────────
  const startTemplate = async (id: string) => {
    if (!id) return;
    if (graphRef.current?.nodes?.length && !window.confirm('Replace the current canvas with this template? (Undo brings it back.)')) return;
    setBusy(true); setError(''); setResults(null);
    try {
      if (id.startsWith('saved:')) {
        const r = await api.post(`${base}/config/from-template`, { template_id: id, tag });
        if (graphRef.current) pushHistory(graphRef.current);
        await refresh(r.data.graph);
      } else {
        const cur = graphRef.current;
        const r = await api.post(`${gbase}/new`, { tag, template_id: id, params: {} });
        if (cur) pushHistory(cur);
        applyBundle(r.data); graphRef.current = r.data.graph;
      }
      setSel({ kind: 'none', ids: [] });
    } catch (e) { err(e, 'Could not load that template.'); } finally { setBusy(false); }
  };
  useEffect(() => {
    if (graph?.params && (graph.params.starter || graph.params.valve_type)) {
      api.post('/loop-wiring-test/graph/catalog', { graph }).then((r) => setCatalog(r.data)).catch(() => setCatalog([]));
    } else setCatalog([]);
  }, [graph?.params?.starter, graph?.params?.valve_type]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── canvas gestures ───────────────────────────────────────────────────────
  const onMove = (pos: Record<string, { x: number; y: number }>) => edit((g) => { g.nodes.forEach((n: G) => { if (pos[n.id]) { n.x = pos[n.id].x; n.y = pos[n.id].y; } }); });
  const onConnect = async (from: any, to: any) => {
    setInvalid('');
    const cur = graphRef.current; if (!cur) return;
    try {
      const r = await api.post(`${gbase}/connect`, { graph: cur, from_node: from.node, from_port: from.port, to_node: to.node, to_port: to.port });
      if (!r.data.ok) { setInvalid(r.data.reason); return; }
      pushHistory(cur); applyBundle(r.data); graphRef.current = r.data.graph;
      setSel({ kind: 'edge', ids: [r.data.edge_id] });
    } catch (e) { err(e, 'Could not connect.'); }
  };
  const addNode = async (component: string, x?: number, y?: number) => {
    const cur = graphRef.current;
    const bottom = Math.max(160, ...(scene ? Object.values(scene.nodes).map((n) => n.y + n.h) : [160]));
    const r = await serverOp('add-node', { component, x: x ?? 40, y: y ?? bottom + 30 });
    if (r) setSel({ kind: 'node', ids: [r.node_id] });
    void cur;
  };
  const deleteSelection = () => {
    if (!graphRef.current || sel.kind === 'none') return;
    if (sel.kind === 'node') edit((g) => { g.nodes = g.nodes.filter((n: G) => !sel.ids.includes(n.id)); g.edges = g.edges.filter((e: G) => !sel.ids.includes(e.from_node) && !sel.ids.includes(e.to_node)); });
    else edit((g) => { g.edges = g.edges.filter((e: G) => !sel.ids.includes(e.id)); });
    setSel({ kind: 'none', ids: [] });
  };
  const duplicateNodes = () => {
    if (sel.kind !== 'node' || !graphRef.current) return;
    const ids: string[] = [];
    edit((g) => {
      for (const id of sel.ids) {
        const n = g.nodes.find((x: G) => x.id === id); if (!n) continue;
        let k = 1; while (g.nodes.some((x: G) => x.id === `n${k}`)) k++;
        const c = clone(n); c.id = `n${k}`; c.x += 30; c.y += 30; c.ports.forEach((p: G) => { p.io_index = p.io_index ?? null; });
        g.nodes.push(c); ids.push(c.id);
      }
    });
    setSel({ kind: 'node', ids });
  };
  const align = (how: string) => {
    if (sel.kind !== 'node' || sel.ids.length < 2 || !scene) return;
    const ns = sel.ids.map((id) => ({ id, ...scene.nodes[id] })).filter((n) => n.w);
    const minX = Math.min(...ns.map((n) => n.x)), minY = Math.min(...ns.map((n) => n.y));
    const cx = ns.reduce((a, n) => a + n.x + n.w / 2, 0) / ns.length, cy = ns.reduce((a, n) => a + n.y + n.h / 2, 0) / ns.length;
    const pos: Record<string, { x: number; y: number }> = {};
    if (how === 'left') ns.forEach((n) => { pos[n.id] = { x: minX, y: n.y }; });
    if (how === 'top') ns.forEach((n) => { pos[n.id] = { x: n.x, y: minY }; });
    if (how === 'centerx') ns.forEach((n) => { pos[n.id] = { x: cx - n.w / 2, y: n.y }; });
    if (how === 'centery') ns.forEach((n) => { pos[n.id] = { x: n.x, y: cy - n.h / 2 }; });
    if (how === 'distx' || how === 'disty') {
      const key = how === 'distx' ? 'x' : 'y'; const size = how === 'distx' ? 'w' : 'h';
      const s = [...ns].sort((a, b) => a[key] - b[key]);
      const span = s[s.length - 1][key] - s[0][key];
      s.forEach((n, i) => { pos[n.id] = how === 'distx' ? { x: s[0].x + (span * i) / (s.length - 1), y: n.y } : { x: n.x, y: s[0].y + (span * i) / (s.length - 1) }; });
      void size;
    }
    onMove(pos);
  };

  // ── derived helpers ───────────────────────────────────────────────────────
  const nodeById = (id: string) => graph?.nodes.find((n: G) => n.id === id);
  const nodeName = (id: string) => { const sn = scene?.nodes[id]; return sn ? `${sn.tag}` : id; };
  const loadIo = async (t: string) => {
    if (ioRows[t]) return;
    try { const r = await api.get(`${base}/io-rows/${encodeURIComponent(t)}`); setIoRows((m) => ({ ...m, [t]: r.data })); } catch { /* none */ }
  };
  useEffect(() => { if (tag) loadIo(tag); }, [tag, sid]); // eslint-disable-line react-hooks/exhaustive-deps
  const selEdgeObj = sel.kind === 'edge' ? graph?.edges.find((x: G) => x.id === sel.ids[0]) : null;
  useEffect(() => {
    setRfState(selEdgeObj ? { fn: selEdgeObj.from_node, fp: selEdgeObj.from_port, tn: selEdgeObj.to_node, tp: selEdgeObj.to_port } : null);
  }, [sel.ids[0], selEdgeObj?.from_node, selEdgeObj?.from_port, selEdgeObj?.to_node, selEdgeObj?.to_port]); // eslint-disable-line react-hooks/exhaustive-deps
  const selNodeObj = sel.kind === 'node' && sel.ids.length === 1 ? graph?.nodes.find((x: G) => x.id === sel.ids[0]) : null;
  useEffect(() => { if (selNodeObj) loadIo(selNodeObj.bind_tag || tag); }, [selNodeObj?.id, selNodeObj?.bind_tag]); // eslint-disable-line react-hooks/exhaustive-deps
  const ioLabel = (r: any) => `${r.plc || 'PLC?'} · R${r.rack || '?'}/S${r.slot || '?'}/${r.module || 'module?'}/CH${r.channel || '?'} · ${r.io_type || ''}`;

  // ── actions ───────────────────────────────────────────────────────────────
  const decide = async (field: string, choice: string) => {
    await api.post(`${base}/decisions`, { kind: 'conflict', tag, field, choice });
    await loadDetail(); onDecisionMade();
    if (graph) refresh(graph);
  };
  const save = async () => {
    if (!graph) return;
    try { await api.put(`${base}/config`, { config: cfgOf(graph) }); setNotice('Loop design saved for this tag.'); } catch (e) { err(e, 'Save failed.'); }
  };
  const saveTemplate = async () => {
    if (!graph) return;
    try {
      await api.post('/loop-wiring-test/templates', { name: tplName, description: 'Graph design', config: cfgOf(graph) });
      setNotice(`Template "${tplName}" saved.`); setTplName(''); onLibraryChanged();
    } catch (e) { err(e, 'Could not save the template.'); }
  };
  const generate = async (tags: string[], configs?: Record<string, any>) => {
    if (!graph) return;
    setBusy(true); setError(''); setResults(null);
    try {
      const cf: Record<string, any> = configs ? { ...configs } : {};
      for (const t of tags) { if (cf[t]) continue; cf[t] = t === tag ? cfgOf(graph) : (await api.post(`${base}/config/clone`, { config: cfgOf(graph), tag: t })).data; }
      const r = await api.post(`${base}/generate`, { tags, configs: cf, allow_warnings: true });
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
  const downloadImage = async (fmt: 'png' | 'pdf') => {
    if (!graph) return;
    try {
      const r = await api.post(`${gbase}/image`, { graph, fmt }, { responseType: 'blob' });
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement('a'); a.href = url; a.download = `Loop_${tag.replace(/[^A-Za-z0-9._-]+/g, '_')}.${fmt}`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { err(e, 'Could not create the image.'); }
  };
  const resetToSaved = async () => {
    if (!window.confirm('Discard unsaved changes and reload the last saved design for this tag? (Undo brings it back.)')) return;
    const d = await loadDetail();
    if (graphRef.current) pushHistory(graphRef.current);
    if (d.saved_config?.graph) await refresh(d.saved_config.graph); else { setGraph(null); setScene(null); graphRef.current = null; }
    setSel({ kind: 'none', ids: [] });
  };
  const runDuplicate = async () => {
    if (!graph || !dup) return;
    try { const r = await api.post(`${gbase}/duplicate`, { graph, tags: dup.tags }); setDup({ ...dup, out: r.data }); } catch (e) { err(e, 'Duplicate failed.'); }
  };
  const statusColor = (s: Check['status']) => (s === 'PASS' ? '#4ade80' : s === 'WARNING' ? 'var(--gold)' : 'var(--rose)');

  // ── properties: block ─────────────────────────────────────────────────────
  const renderNode = (id: string) => {
    const n = nodeById(id); if (!n || !graph) return null;
    const spec = glib?.palette.flatMap((g) => g.items).find((i) => i.id === n.type);
    const props = n.props || {};
    const isDevice = !!glib?.palette[0]?.items.some((i) => i.id === n.type);
    const isSystem = n.type.startsWith('plc_') || ['plc', 'dcs', 'remote_io', 'vendor_plc', 'controller'].includes(n.type);
    const multi = n.ports.some((p: G) => p.signal_id);
    const setN = (ch: Record<string, any>, co = true) => edit((g) => { Object.assign(g.nodes.find((x: G) => x.id === id), ch); }, co);
    const setProps = (ch: Record<string, any>) => edit((g) => { const x = g.nodes.find((y: G) => y.id === id); x.props = { ...(x.props || {}), ...ch }; }, true);
    const setPort = (pi: number, ch: Record<string, any>) => edit((g) => { Object.assign(g.nodes.find((x: G) => x.id === id).ports[pi], ch); }, true);
    const bound = n.bind_tag || tag;
    return (
      <div className="space-y-3">
        <p className="text-xs font-bold" style={{ color: 'var(--t0)' }}>{spec?.label || n.type} <span className="font-mono">{nodeName(id)}</span></p>
        <div className="grid grid-cols-2 gap-2">
          <div><label className={lab} style={{ color: 'var(--t2)' }}>Heading</label><input className={inp} style={inputSt} value={n.label || ''} onChange={(e) => setN({ label: e.target.value })} /></div>
          <div><label className={lab} style={{ color: 'var(--t2)' }}>Tag / name</label><input className={inp} style={inputSt} value={n.tag || ''} placeholder="from the source" onChange={(e) => setN({ tag: e.target.value })} /></div>
        </div>
        <div><label className={lab} style={{ color: 'var(--t2)' }}>Description</label><input className={inp} style={inputSt} value={n.description || ''} placeholder="from the IODB" onChange={(e) => setN({ description: e.target.value })} /></div>
        {isDevice && (
          <>
            <button className={btn} style={btnSt} onClick={() => setPicker({ mode: 'tag', apply: (r) => setN({ bind_tag: r.tag === tag ? '' : r.tag, tag: '' }, false) })}>Select Tag from IODB</button>
            {n.bind_tag && <p className="text-[11px]" style={{ color: 'var(--t2)' }}>Reads its data from IODB tag <b>{n.bind_tag}</b> <button className="underline ml-1" onClick={() => setN({ bind_tag: '' })}>reset</button></p>}
            <div className="grid grid-cols-2 gap-2">
              <div><label className={lab} style={{ color: 'var(--t2)' }}>Wiring mode</label>
                <select className={inp} style={inputSt} value={props.profile || ''} onChange={(e) => e.target.value && serverOp('profile', { node_id: id, profile: e.target.value })}>
                  <option value="">— as created —</option>{Object.entries(glib?.profiles || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select></div>
              <div><label className={lab} style={{ color: 'var(--t2)' }}>HART</label>
                <select className={inp} style={inputSt} value={props.hart === undefined ? '' : props.hart ? 'yes' : 'no'} onChange={(e) => setProps({ hart: e.target.value === '' ? undefined : e.target.value === 'yes' })}>
                  <option value="">as in IODB</option><option value="yes">Yes</option><option value="no">No</option></select></div>
            </div>
          </>
        )}
        {n.type === 'junction_box' && (
          <>
            <button className={btn} style={btnSt} onClick={() => setPicker({ mode: 'jb', apply: (jb) => setProps({ jb_tag: jb }) })}>Select JB from IODB</button>
            <div><label className={lab} style={{ color: 'var(--t2)' }}>JB tag</label><input className={inp} style={inputSt} value={props.jb_tag || ''} onChange={(e) => setProps({ jb_tag: e.target.value })} /></div>
            <label className="text-xs flex items-center gap-2" style={{ color: 'var(--t1)' }}><input type="checkbox" checked={!!props.accept_difference} onChange={(e) => setProps({ accept_difference: e.target.checked })} /> Accept that this JB differs from the IODB</label>
          </>
        )}
        {['marshalling_cabinet', 'terminal_strip', 'terminal_block'].includes(n.type) && (
          <div className="grid grid-cols-2 gap-2">
            <div><label className={lab} style={{ color: 'var(--t2)' }}>Terminal strip</label><input className={inp} style={inputSt} value={props.strip || ''} onChange={(e) => setProps({ strip: e.target.value })} /></div>
            <div><label className={lab} style={{ color: 'var(--t2)' }}>Terminal type</label>
              <select className={inp} style={inputSt} value={props.terminal_type || ''} onChange={(e) => setProps({ terminal_type: e.target.value })}>
                <option value="">—</option>{['Normal terminal', 'IS terminal', 'Fuse terminal', 'Disconnect terminal', 'Marshalling terminal'].map((t) => <option key={t}>{t}</option>)}</select></div>
          </div>
        )}
        {n.type === 'power_supply' && (
          <div><label className={lab} style={{ color: 'var(--t2)' }}>Output voltage</label><input className={inp} style={inputSt} value={props.voltage || ''} placeholder="e.g. 24 VDC" onChange={(e) => setProps({ voltage: e.target.value })} /></div>
        )}
        {isSystem && !multi && (
          <div>
            <label className={lab} style={{ color: 'var(--t2)' }}>I/O Assignment channel for {bound}</label>
            <select className={inp} style={inputSt} value={props.io_index ?? ''} onChange={(e) => setProps({ io_index: e.target.value === '' ? null : Number(e.target.value) })}>
              <option value="">— select the assigned card / channel —</option>
              {(ioRows[bound] || []).map((r, i) => <option key={i} value={i}>{ioLabel(r)}</option>)}
            </select>
            <p className="text-[10px] mt-1" style={{ color: 'var(--t2)' }}>Rack, slot, module and channel come from the I/O Assignment - never typed.</p>
          </div>
        )}
        {isSystem && multi && (
          <div>
            <label className={lab} style={{ color: 'var(--t2)' }}>I/O channel per signal</label>
            {Array.from(new Map(n.ports.filter((p: G) => p.signal_id).map((p: G) => [p.signal_id, p])).values()).map((p: any) => (
              <div key={p.signal_id} className="grid grid-cols-[1fr,1.6fr] gap-1 mb-1 items-center">
                <span className="text-[11px]" style={{ color: 'var(--t1)' }}>{p.group}</span>
                <select className={inp} style={inputSt} value={p.io_index ?? ''} onChange={(e) => edit((g) => { g.nodes.find((x: G) => x.id === id).ports.filter((q: G) => q.signal_id === p.signal_id).forEach((q: G) => { q.io_index = e.target.value === '' ? null : Number(e.target.value); }); }, true)}>
                  <option value="">— select —</option>{(ioRows[bound] || []).map((r, i) => <option key={i} value={i}>{ioLabel(r)}</option>)}</select>
              </div>
            ))}
          </div>
        )}
        <div><label className={lab} style={{ color: 'var(--t2)' }}>Extra text lines inside the block</label>
          <textarea className={inp} style={{ ...inputSt, minHeight: 50 }} value={(props.lines || []).join('\n')} onChange={(e) => setProps({ lines: e.target.value.split('\n') })} /></div>
        <div>
          <div className="flex items-center justify-between"><label className={lab} style={{ color: 'var(--t2)' }}>Ports & terminals</label>
            <button className="text-[11px] underline" style={{ color: 'var(--t1)' }} onClick={() => edit((g) => {
              const x = g.nodes.find((y: G) => y.id === id); let k = 1; while (x.ports.some((p: G) => p.id === `p${k}`)) k++;
              x.ports.push({ id: `p${k}`, label: 'PORT', terminal: '', kind: 'signal', pol: '', sig: 'ANY', side: n.ports[0]?.side || 'right', required: false, multi: false, pair: '', io_index: null });
            })}>+ Add port</button></div>
          {n.ports.map((p: G, pi: number) => (
            <div key={p.id} className="grid grid-cols-[1.1fr,.8fr,.9fr,.5fr,.7fr,.6fr,18px] gap-1 mb-1 items-center">
              <input className={inp} style={inputSt} value={p.label} title="Port name" onChange={(e) => setPort(pi, { label: e.target.value })} />
              <input className={inp} style={inputSt} value={p.terminal || ''} placeholder="Term." title="Terminal number" onChange={(e) => setPort(pi, { terminal: e.target.value })} />
              <select className={inp} style={inputSt} value={p.kind} title="Kind" onChange={(e) => setPort(pi, { kind: e.target.value })}>{(glib?.kinds || []).map((k) => <option key={k}>{k}</option>)}</select>
              <select className={inp} style={inputSt} value={p.pol} title="Polarity" onChange={(e) => setPort(pi, { pol: e.target.value })}><option value="">·</option><option>+</option><option>-</option></select>
              <select className={inp} style={inputSt} value={p.sig} title="Signal family" onChange={(e) => setPort(pi, { sig: e.target.value })}>{(glib?.families || []).map((k) => <option key={k}>{k}</option>)}</select>
              <select className={inp} style={inputSt} value={p.side} title="Side" onChange={(e) => setPort(pi, { side: e.target.value, multi: e.target.value === 'both' ? true : p.multi })}><option>left</option><option>right</option><option>both</option></select>
              <button title="Remove port (its wires are removed)" onClick={() => edit((g) => { const x = g.nodes.find((y: G) => y.id === id); x.ports = x.ports.filter((_: G, k: number) => k !== pi); g.edges = g.edges.filter((e: G) => !((e.from_node === id && e.from_port === p.id) || (e.to_node === id && e.to_port === p.id))); })}><X className="w-3 h-3" style={{ color: 'var(--t2)' }} /></button>
            </div>
          ))}
        </div>
        <div className="flex gap-3">
          <button className={btn} style={btnSt} onClick={duplicateNodes}><Copy className="w-3 h-3" /> Duplicate block</button>
          <button className={btn} style={{ ...btnSt, color: 'var(--rose)' }} onClick={deleteSelection}><Trash2 className="w-3 h-3" /> Delete block</button>
        </div>
      </div>
    );
  };

  // ── properties: wire ──────────────────────────────────────────────────────
  const renderEdge = (id: string) => {
    const e = graph?.edges.find((x: G) => x.id === id); if (!e || !graph) return null;
    const setE = (ch: Record<string, any>) => edit((g) => { Object.assign(g.edges.find((x: G) => x.id === id), ch); }, true);
    const portLabel = (n: string, p: string) => nodeById(n)?.ports.find((x: G) => x.id === p)?.label || p;
    const rf = rfState || { fn: e.from_node, fp: e.from_port, tn: e.to_node, tp: e.to_port };
    const setRf = (v: any) => setRfState(v);
    const changed = rf.fn !== e.from_node || rf.fp !== e.from_port || rf.tn !== e.to_node || rf.tp !== e.to_port;
    const reconnect = async () => {
      setInvalid('');
      const without = clone(graph); without.edges = without.edges.filter((x: G) => x.id !== id);
      try {
        const r = await api.post(`${gbase}/connect`, { graph: without, from_node: rf.fn, from_port: rf.fp, to_node: rf.tn, to_port: rf.tp });
        if (!r.data.ok) { setInvalid(r.data.reason); return; }
        const g2 = r.data.graph; const ne = g2.edges.find((x: G) => x.id === r.data.edge_id);
        Object.assign(ne, { cable_id: e.cable_id, core: e.core, wire_no: e.wire_no, remarks: e.remarks, signal: e.signal });
        pushHistory(graph); setGraph(g2); graphRef.current = g2; refresh(g2); setSel({ kind: 'edge', ids: [ne.id] });
      } catch (ex) { err(ex, 'Could not reconnect.'); }
    };
    const portsOf = (nid: string) => nodeById(nid)?.ports || [];
    const sameLink = graph.edges.filter((x: G) => new Set([x.from_node, x.to_node]).size && ((x.from_node === e.from_node && x.to_node === e.to_node) || (x.from_node === e.to_node && x.to_node === e.from_node)));
    const assignCable = (cid: string) => edit((g) => { g.edges.forEach((x: G) => { if (x.id === id || (allWires && sameLink.some((s: G) => s.id === x.id))) x.cable_id = cid; }); });
    const newCable = (iodb: string) => edit((g) => {
      let k = 1; while (g.cables.some((c: G) => c.id === `c${k}`)) k++;
      g.cables.push({ id: `c${k}`, iodb, tag: '', type: '', length: '', route: '', cores: '', pairs: '', override: {}, shield: { type: '', items: [] } });
      g.edges.forEach((x: G) => { if (x.id === id || (allWires && sameLink.some((s: G) => s.id === x.id))) x.cable_id = `c${k}`; });
    });
    return (
      <div className="space-y-3">
        <p className="text-xs font-bold" style={{ color: 'var(--t0)' }}>Wire {e.wire_no} <span style={{ color: 'var(--t2)' }}>· {e.kind}</span></p>
        <div className="grid grid-cols-2 gap-2">
          {[['From', 'fn', 'fp'], ['To', 'tn', 'tp']].map(([title, nk, pk]) => (
            <div key={title}>
              <label className={lab} style={{ color: 'var(--t2)' }}>{title}</label>
              <select className={inp} style={inputSt} value={(rf as any)[nk]} onChange={(ev) => { const nn = ev.target.value; setRf({ ...rf, [nk]: nn, [pk]: portsOf(nn)[0]?.id || '' }); }}>
                {graph.nodes.map((n: G) => <option key={n.id} value={n.id}>{nodeName(n.id)}</option>)}</select>
              <select className={`${inp} mt-1`} style={inputSt} value={(rf as any)[pk]} onChange={(ev) => setRf({ ...rf, [pk]: ev.target.value })}>
                {portsOf((rf as any)[nk]).map((p: G) => <option key={p.id} value={p.id}>{p.terminal ? `${p.terminal} · ` : ''}{p.label}</option>)}</select>
            </div>
          ))}
        </div>
        {changed && <button className={btn} style={btnSt} onClick={reconnect}>Reconnect to the new ports</button>}
        <p className="text-[11px]" style={{ color: 'var(--t2)' }}>Currently: {nodeName(e.from_node)} / {portLabel(e.from_node, e.from_port)} → {nodeName(e.to_node)} / {portLabel(e.to_node, e.to_port)}</p>
        <div className="grid grid-cols-3 gap-2">
          <div><label className={lab} style={{ color: 'var(--t2)' }}>Wire no.</label><input className={inp} style={inputSt} value={e.wire_no || ''} onChange={(ev) => setE({ wire_no: ev.target.value })} /></div>
          <div><label className={lab} style={{ color: 'var(--t2)' }}>Core / pair</label><input className={inp} style={inputSt} value={e.core || ''} onChange={(ev) => setE({ core: ev.target.value })} /></div>
          <div><label className={lab} style={{ color: 'var(--t2)' }}>Signal</label><input className={inp} style={inputSt} value={e.signal || ''} onChange={(ev) => setE({ signal: ev.target.value })} /></div>
        </div>
        <div><label className={lab} style={{ color: 'var(--t2)' }}>Remarks</label><input className={inp} style={inputSt} value={e.remarks || ''} onChange={(ev) => setE({ remarks: ev.target.value })} /></div>
        <div>
          <label className={lab} style={{ color: 'var(--t2)' }}>Cable</label>
          <select className={inp} style={inputSt} value={e.cable_id || ''} onChange={(ev) => assignCable(ev.target.value)}>
            <option value="">— no cable —</option>{graph.cables.map((c: G) => <option key={c.id} value={c.id}>{cables[c.id]?.tag || c.id}{cables[c.id]?.type ? ` · ${cables[c.id].type}` : ''}</option>)}</select>
          <label className="text-[11px] flex items-center gap-2 mt-1" style={{ color: 'var(--t2)' }}><input type="checkbox" checked={allWires} onChange={(ev) => setAllWires(ev.target.checked)} /> apply to all {sameLink.length} wire(s) between these two blocks</label>
          <div className="flex gap-3 mt-1 flex-wrap">
            <button className="text-[11px] underline" style={{ color: 'var(--t1)' }} onClick={() => newCable('branch')}>+ IODB branch cable</button>
            <button className="text-[11px] underline" style={{ color: 'var(--t1)' }} onClick={() => newCable('main')}>+ IODB main cable</button>
            <button className="text-[11px] underline" style={{ color: 'var(--t1)' }} onClick={() => newCable('')}>+ New cable</button>
          </div>
        </div>
        {e.cable_id && renderCable(e.cable_id)}
        <button className={btn} style={{ ...btnSt, color: 'var(--rose)' }} onClick={deleteSelection}><Trash2 className="w-3 h-3" /> Delete wire</button>
      </div>
    );
  };

  const renderCable = (id: string) => {
    const c = graph?.cables.find((x: G) => x.id === id); const r = cables[id]; if (!c || !graph) return null;
    const setC = (ch: Record<string, any>) => edit((g) => { Object.assign(g.cables.find((x: G) => x.id === id), ch); }, true);
    const setOv = (k: string, v: string) => setC({ override: { ...(c.override || {}), [k]: v } });
    const shield = c.shield || { type: '', items: [] };
    const setSh = (ch: Record<string, any>) => setC({ shield: { ...shield, ...ch } });
    return (
      <div className="rounded-lg p-2 space-y-2" style={{ background: 'var(--s3)', border: '1px solid var(--b2)' }}>
        <p className="text-[11px] font-bold" style={{ color: 'var(--t0)' }}>Cable {id} {c.iodb ? `· from IODB (${c.iodb})` : '· manual'}</p>
        <div className="grid grid-cols-2 gap-2">
          {(['tag', 'type', 'length', 'route'] as const).map((k) => (
            <div key={k}><label className={lab} style={{ color: 'var(--t2)' }}>{k === 'tag' ? 'Cable tag' : k}{r?.[`${k}_src`] ? ` · ${r[`${k}_src`] === 'USER' ? 'USER' : 'IODB'}` : ''}</label>
              <input className={inp} style={inputSt} value={(c.override || {})[k] ?? (c.iodb ? '' : c[k] || '')} placeholder={c.iodb ? (r?.[k] || 'MISSING in IODB') : ''}
                onChange={(ev) => (c.iodb ? setOv(k, ev.target.value) : setC({ [k]: ev.target.value }))} /></div>
          ))}
          <div><label className={lab} style={{ color: 'var(--t2)' }}>No. of cores</label><input className={inp} style={inputSt} value={c.cores || ''} onChange={(ev) => setC({ cores: ev.target.value })} /></div>
          <div><label className={lab} style={{ color: 'var(--t2)' }}>No. of pairs</label><input className={inp} style={inputSt} value={c.pairs || ''} onChange={(ev) => setC({ pairs: ev.target.value })} /></div>
        </div>
        <div>
          <label className={lab} style={{ color: 'var(--t2)' }}>Shielding</label>
          <div className="flex flex-wrap gap-3">
            {Object.entries(glib?.shield_types || {}).map(([k, v]) => (
              <label key={k} className="text-[11px] flex items-center gap-1" style={{ color: 'var(--t1)' }}><input type="radio" name={`sh-${id}`} checked={shield.type === k} onChange={() => setSh({ type: k })} />{v}</label>
            ))}
          </div>
          {shield.type && shield.type !== 'none' && (
            <div className="mt-1">
              {(shield.items || []).map((it: G, i: number) => (
                <div key={i} className="grid grid-cols-[.7fr,1fr,1fr,1fr,1fr,16px] gap-1 mb-1">
                  <input className={inp} style={inputSt} value={it.id} placeholder="Shield ID" onChange={(ev) => setSh({ items: shield.items.map((x: G, k: number) => (k === i ? { ...x, id: ev.target.value } : x)) })} />
                  <input className={inp} style={inputSt} value={it.source} placeholder="Source" onChange={(ev) => setSh({ items: shield.items.map((x: G, k: number) => (k === i ? { ...x, source: ev.target.value } : x)) })} />
                  <input className={inp} style={inputSt} value={it.destination} placeholder="Destination" onChange={(ev) => setSh({ items: shield.items.map((x: G, k: number) => (k === i ? { ...x, destination: ev.target.value } : x)) })} />
                  <select className={inp} style={inputSt} value={it.termination} onChange={(ev) => setSh({ items: shield.items.map((x: G, k: number) => (k === i ? { ...x, termination: ev.target.value } : x)) })}>
                    {Object.entries(glib?.shield_terminations || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
                  <input className={inp} style={inputSt} value={it.grounding} placeholder="Earth point" onChange={(ev) => setSh({ items: shield.items.map((x: G, k: number) => (k === i ? { ...x, grounding: ev.target.value } : x)) })} />
                  <button onClick={() => setSh({ items: shield.items.filter((_: G, k: number) => k !== i) })}><X className="w-3 h-3" style={{ color: 'var(--t2)' }} /></button>
                </div>
              ))}
              <button className="text-[11px] underline" style={{ color: 'var(--t1)' }} onClick={() => setSh({ items: [...(shield.items || []), { id: `S${(shield.items || []).length + 1}`, source: '', destination: '', termination: '', grounding: '' }] })}>+ Shield termination</button>
              <p className="text-[10px]" style={{ color: 'var(--t2)' }}>No earthing philosophy is imposed - define each shield end yourself.</p>
            </div>
          )}
        </div>
        <label className="text-[11px] flex items-center gap-2" style={{ color: 'var(--t1)' }}><input type="checkbox" checked={!!c.accept_difference} onChange={(ev) => setC({ accept_difference: ev.target.checked })} /> Accept that this cable differs from the IODB</label>
        <button className="text-[11px] underline" style={{ color: 'var(--rose)' }} onClick={() => edit((g) => { g.cables = g.cables.filter((x: G) => x.id !== id); g.edges.forEach((x: G) => { if (x.cable_id === id) x.cable_id = ''; }); })}>Delete cable</button>
      </div>
    );
  };

  const renderGraph = () => {
    if (!graph) return null;
    return (
      <div className="space-y-3">
        <p className="text-xs font-bold" style={{ color: 'var(--t0)' }}>Drawing</p>
        <div className="grid grid-cols-2 gap-2">
          <div><label className={lab} style={{ color: 'var(--t2)' }}>Layout</label>
            <select className={inp} style={inputSt} value={graph.orientation} onChange={(e) => edit((g) => { g.orientation = e.target.value; })}>
              {(glib?.orientations || []).map((o) => <option key={o} value={o}>{o[0].toUpperCase() + o.slice(1)}</option>)}</select></div>
        </div>
        <div>
          <label className={lab} style={{ color: 'var(--t2)' }}>Zones</label>
          {graph.zones.map((z: G, i: number) => (
            <div key={z.id} className="grid grid-cols-[18px,1.4fr,1.2fr,36px] gap-1 mb-1 items-center">
              <input type="checkbox" title="Show zone" checked={z.visible !== false} onChange={(e) => edit((g) => { g.zones[i].visible = e.target.checked; })} />
              <input className={inp} style={inputSt} value={z.name} onChange={(e) => edit((g) => { g.zones[i].name = e.target.value; }, true)} />
              <input className={inp} style={inputSt} value={z.sub || ''} placeholder="sub-title" onChange={(e) => edit((g) => { g.zones[i].sub = e.target.value; }, true)} />
              <span className="flex gap-1">
                <button title="Move earlier" onClick={() => i > 0 && edit((g) => { [g.zones[i - 1], g.zones[i]] = [g.zones[i], g.zones[i - 1]]; })}>↑</button>
                <button title="Move later" onClick={() => i < graph.zones.length - 1 && edit((g) => { [g.zones[i + 1], g.zones[i]] = [g.zones[i], g.zones[i + 1]]; })}>↓</button>
              </span>
            </div>
          ))}
          <button className="text-[11px] underline" style={{ color: 'var(--t1)' }} onClick={() => edit((g) => { let k = 1; while (g.zones.some((z: G) => z.id === `z${k}`)) k++; g.zones.push({ id: `z${k}`, name: 'NEW ZONE', sub: '', visible: true }); })}>+ Add zone</button>
          <p className="text-[10px]" style={{ color: 'var(--t2)' }}>A block belongs to the zone it is dropped in. Reordering zones moves the columns, not the wires.</p>
        </div>
        {catalog.length > 0 && (
          <div>
            <label className={lab} style={{ color: 'var(--t2)' }}>Signals of this loop (choose the ones that exist)</label>
            <div className="grid grid-cols-1 gap-0.5">
              {catalog.map((s) => (
                <label key={s.id} className="text-[11px] flex items-center gap-2" style={{ color: 'var(--t1)' }}>
                  <input type="checkbox" checked={(graph.signals || []).includes(s.id)} onChange={(e) => serverOp('signals', { selected: e.target.checked ? [...(graph.signals || []), s.id] : (graph.signals || []).filter((x: string) => x !== s.id) })} />
                  {s.name} <span style={{ color: 'var(--t2)' }}>({s.signal_type})</span></label>
              ))}
            </div>
            <p className="text-[10px]" style={{ color: 'var(--t2)' }}>Each selected signal becomes its own pair of ports - connect each one.</p>
          </div>
        )}
        {graph.cables.length > 0 && (
          <div><label className={lab} style={{ color: 'var(--t2)' }}>Cables</label>
            {graph.cables.map((c: G) => <p key={c.id} className="text-[11px]" style={{ color: 'var(--t1)' }}>{cables[c.id]?.tag || c.id} · {cables[c.id]?.type || '—'} · {graph.edges.filter((e: G) => e.cable_id === c.id).length} wires</p>)}</div>
        )}
        <p className="text-[11px]" style={{ color: 'var(--t2)' }}>Click a block or a wire to edit it. Shift-click selects several blocks.</p>
      </div>
    );
  };

  const savedGraphTemplates = library.saved_templates.filter((t) => (t.config as any)?.graph);
  const nSel = sel.kind === 'node' ? sel.ids.length : 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <Button variant="ghost" size="sm" onClick={onBack}>← Back to matching</Button>
        <h3 className="text-base font-bold" style={{ color: 'var(--t0)' }}>Loop design · <span className="font-mono">{tag}</span></h3>
        {detail && <span className="text-xs" style={{ color: 'var(--t2)' }}>loop {detail.loop || '—'} · {detail.status}</span>}
      </div>
      {error && <Alert variant="error" onClose={() => setError('')}>{error}</Alert>}
      {notice && <Alert variant="success" onClose={() => setNotice('')}>{notice}</Alert>}
      {detail?.conflicts.map((c) => (
        <Alert key={c.field} variant={c.decision ? 'info' : 'warning'} title={`${c.label} conflict`}>
          IODB <b>{c.iodb}</b> · I/O Assignment <b>{c.io}</b>
          {c.decision ? <span> — decided: {c.decision === 'iodb' ? 'IODB' : 'I/O Assignment'} <button className="underline ml-1" onClick={() => decide(c.field, '')}>undo</button></span>
            : <div className="mt-1"><button className="underline mr-3" onClick={() => decide(c.field, 'iodb')}>Accept IODB</button><button className="underline" onClick={() => decide(c.field, 'io')}>Accept I/O Assignment</button></div>}
        </Alert>
      ))}

      {/* toolbar */}
      <div className="flex flex-wrap items-end gap-2 rounded-xl p-3" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        <div className="min-w-[230px]">
          <label className={lab} style={{ color: 'var(--t2)' }}>Template (starting point only)</label>
          <select className={inp} style={inputSt} value="" onChange={(e) => startTemplate(e.target.value)}>
            <option value="">— choose a template —</option>
            <optgroup label="Standard">{(glib?.templates || []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</optgroup>
            {savedGraphTemplates.length > 0 && <optgroup label="Saved by users">{savedGraphTemplates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</optgroup>}
          </select>
        </div>
        <button className={btn} style={btnSt} disabled={!past.current.length} onClick={undo}><Undo2 className="w-3.5 h-3.5" /> Undo</button>
        <button className={btn} style={btnSt} disabled={!future.current.length} onClick={redo}><Redo2 className="w-3.5 h-3.5" /> Redo</button>
        <button className={btn} style={btnSt} disabled={nSel < 1} onClick={duplicateNodes}><Copy className="w-3.5 h-3.5" /> Duplicate block</button>
        <button className={btn} style={btnSt} disabled={sel.kind === 'none'} onClick={deleteSelection}><Trash2 className="w-3.5 h-3.5" /> Delete</button>
        <button className={btn} style={btnSt} disabled={nSel !== 2} title="Select two blocks, then wire matching ports (+ to +, − to −, shield to shield). Creates ordinary editable wires." onClick={() => serverOp('connect-blocks', { a: sel.ids[0], b: sel.ids[1] })}>Connect the two selected blocks</button>
        <span className="flex gap-1">
          {[[AlignHorizontalJustifyStart, 'left', 'Align left'], [AlignVerticalJustifyStart, 'top', 'Align top'], [AlignCenterVertical, 'centerx', 'Align centres (vertical axis)'], [AlignCenterHorizontal, 'centery', 'Align centres (horizontal axis)']].map(([Icon, k, t]: any) => (
            <button key={k} className={btn} style={btnSt} disabled={nSel < 2} title={t} onClick={() => align(k)}><Icon className="w-3.5 h-3.5" /></button>))}
          <button className={btn} style={btnSt} disabled={nSel < 3} onClick={() => align('distx')}>Distribute ↔</button>
          <button className={btn} style={btnSt} disabled={nSel < 3} onClick={() => align('disty')}>Distribute ↕</button>
        </span>
      </div>
      {invalid && (
        <Alert variant="error" title="INVALID CONNECTION" onClose={() => setInvalid('')}>{invalid} Choose compatible ports.</Alert>
      )}

      <Card title="Component library" description="Click to add, or drag onto the canvas.">
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          {glib?.palette.map((g) => (
            <div key={g.group} className="min-w-[200px] flex-1">
              <p className="text-[10px] font-bold tracking-wider mb-1" style={{ color: 'var(--t2)' }}>{g.group}</p>
              <div className="flex flex-wrap gap-1">
                {g.items.map((it) => (
                  <button key={it.id} draggable onDragStart={(e) => e.dataTransfer.setData('component', it.id)} onClick={() => addNode(it.id)}
                    className="text-[11px] px-2 py-1 rounded hover:opacity-80" style={{ background: 'var(--s3)', color: 'var(--t0)', border: '1px solid var(--b1)' }}>{it.label}</button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr,360px] gap-4">
        <Card title="Loop canvas" description="The drawing is generated from exactly what is wired here. Missing data is red.">
          {graph && graph.nodes.length === 0 && <p className="text-xs mb-2" style={{ color: 'var(--t2)' }}>Empty canvas - choose a template above or add blocks from the library.</p>}
          <GraphCanvas scene={graph ? scene : null} selection={sel} onSelect={setSel} onMove={onMove} onConnect={onConnect}
            onDropComponent={(c, x, y) => addNode(c, x, y)} />
          {!graph && <p className="text-sm p-6" style={{ color: 'var(--t2)' }}>Choose a template (a starting set of blocks and ports) to begin. Nothing is wired until you connect it.</p>}
        </Card>

        <Card title="Properties">
          {!graph ? <p className="text-xs" style={{ color: 'var(--t2)' }}>—</p>
            : sel.kind === 'node' && sel.ids.length === 1 ? renderNode(sel.ids[0])
              : sel.kind === 'node' ? <p className="text-xs" style={{ color: 'var(--t1)' }}>{sel.ids.length} blocks selected - align / distribute / delete from the toolbar.</p>
                : sel.kind === 'edge' ? renderEdge(sel.ids[0]) : renderGraph()}
        </Card>
      </div>

      {graph && (
        <div className="grid grid-cols-1 xl:grid-cols-[1fr,1fr] gap-4">
          <Card title={validation ? `Validation · ${validation.passed}/${validation.total} passed` : 'Validation'}>
            {validation?.checks.map((c) => (
              <p key={c.id} className="text-xs mb-1.5" style={{ color: statusColor(c.status) }}>
                {c.status === 'PASS' ? '✓' : c.status === 'WARNING' ? '⚠' : '✗'} <b>{c.label}</b>
                {c.detail && <span style={{ color: 'var(--t1)' }}> — {c.detail}</span>}
              </p>
            ))}
            {validation && !validation.can_generate && <Alert variant="error" className="mt-3">{validation.errors} error(s) must be resolved first. Warnings alone do not block generation.</Alert>}
          </Card>
          <Card title="Output">
            <div className="flex flex-wrap gap-2 items-center mb-3">
              <Button variant="secondary" onClick={save}><Save className="w-4 h-4" /> Save loop design</Button>
              <Button onClick={() => generate([tag])} disabled={!validation?.can_generate} loading={busy}>
                Generate loop diagram{validation && validation.warnings > 0 ? ` (${validation.warnings} warning${validation.warnings > 1 ? 's' : ''})` : ''}</Button>
              <Button variant="secondary" onClick={resetToSaved}>Reset to saved</Button>
              <Button variant="secondary" onClick={() => downloadImage('png')}>PNG</Button>
              <Button variant="secondary" onClick={() => downloadImage('pdf')}>PDF</Button>
              <Button variant="secondary" onClick={() => setDup({ tags: selectedTags, out: null })}><Copy className="w-4 h-4" /> Duplicate loop to other tags…</Button>
            </div>
            {results && (
              <div className="mb-3">
                <p className="text-sm font-bold mb-1" style={{ color: 'var(--t0)' }}>{results.generated} loop(s) generated</p>
                {results.results.map((r: any) => (
                  <p key={r.tag} className="text-xs" style={{ color: r.status === 'GENERATED' ? '#4ade80' : 'var(--rose)' }}>
                    {r.status === 'GENERATED' ? '✓' : '✗'} {r.tag} — {r.status}{r.reason ? `: ${r.reason}` : ''}{r.warnings ? ` (${r.warnings} warning(s))` : ''}</p>
                ))}
                {results.filename && <Button className="mt-2" onClick={download}><Download className="w-4 h-4" /> Download {results.filename}</Button>}
              </div>
            )}
            <div className="flex gap-2 items-end pt-3" style={{ borderTop: '1px solid var(--b1)' }}>
              <div className="flex-1"><label className={lab} style={{ color: 'var(--t2)' }}>Save as template - name</label>
                <input className={inp} style={inputSt} value={tplName} onChange={(e) => setTplName(e.target.value)} placeholder="e.g. AI 2-wire + barrier + isolator" /></div>
              <Button variant="secondary" disabled={!tplName.trim()} onClick={saveTemplate}>Save template</Button>
            </div>
          </Card>
        </div>
      )}

      {picker && <TagPicker sid={sid} mode={picker.mode} onClose={() => setPicker(null)} onPick={(v) => { picker.apply(v); setPicker(null); }} />}

      {dup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,.55)' }} onClick={() => setDup(null)}>
          <div className="rounded-xl p-4 w-[820px] max-w-[95vw] max-h-[88vh] overflow-auto" style={{ background: 'var(--s2)', border: '1px solid var(--b2)' }} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-2"><p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Duplicate this loop design to other tags</p>
              <button onClick={() => setDup(null)}><X className="w-4 h-4" style={{ color: 'var(--t2)' }} /></button></div>
            <p className="text-xs mb-2" style={{ color: 'var(--t2)' }}>Source values (tag, loop, JB, cables, I/O channel) are re-read for each target. Terminals and manual cable tags/lengths of this loop are cleared, never copied. Every result is validated.</p>
            <div className="flex flex-wrap gap-1 mb-2">
              {dup.tags.map((t) => <span key={t} className="text-xs px-2 py-1 rounded font-mono" style={{ background: 'var(--s3)', color: 'var(--t0)' }}>{t} <button onClick={() => setDup({ ...dup, tags: dup.tags.filter((x) => x !== t), out: null })}>×</button></span>)}
              <button className={btn} style={btnSt} onClick={() => setPicker({ mode: 'tag', apply: (r) => setDup((d) => (d && !d.tags.includes(r.tag) ? { ...d, tags: [...d.tags, r.tag], out: null } : d)) })}><Plus className="w-3 h-3" /> Add tag from IODB</button>
            </div>
            <Button disabled={dup.tags.length === 0} onClick={runDuplicate}>Duplicate & validate</Button>
            {dup.out?.results.map((r: any) => (
              <div key={r.tag} className="mt-3 p-2 rounded-lg" style={{ background: 'var(--s3)' }}>
                <p className="text-xs font-bold" style={{ color: r.ok ? 'var(--t0)' : 'var(--rose)' }}>{r.tag} — {r.ok ? `${r.errors} error(s), ${r.warnings} warning(s)` : r.reason}</p>
                {r.report?.map((x: string, i: number) => <p key={i} className="text-[11px]" style={{ color: 'var(--t1)' }}>• {x}</p>)}
                {r.problems?.map((c: Check) => <p key={c.id} className="text-[11px]" style={{ color: 'var(--rose)' }}>✗ {c.label}{c.detail ? ` — ${c.detail}` : ''}</p>)}
              </div>
            ))}
            {dup.out && (
              <div className="flex gap-2 mt-3">
                <Button variant="secondary" onClick={async () => {
                  for (const r of dup.out.results.filter((x: any) => x.ok)) await api.put(`${base}/config`, { config: cfgOf(r.graph, r.tag) });
                  setNotice('Designs saved for the duplicated tags - open each tag from the match list to finish its terminals.'); setDup(null);
                }}>Save these designs</Button>
                <Button onClick={() => { const ok = dup.out.results.filter((x: any) => x.ok); const cf: Record<string, any> = {}; ok.forEach((r: any) => { cf[r.tag] = cfgOf(r.graph, r.tag); }); generate(ok.map((r: any) => r.tag), cf); setDup(null); }}>Generate these (blocked ones are reported)</Button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
