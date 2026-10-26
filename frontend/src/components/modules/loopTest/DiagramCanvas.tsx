/**
 * Interactive loop drawing: drag boxes anywhere, draw / delete / reverse connections, and edit what is
 * inside every box and connection. The drawing is rendered from the same diagram model the server
 * writes to Excel; the engineer's edits go back into the LoopConfiguration (layout.positions, links,
 * components) - source-document values stay read-only and keep their source badge.
 */
import { useMemo, useRef, useState } from 'react';
import { Plus, RotateCcw, Trash2, X } from 'lucide-react';
import { Library, LoopConfig, SOURCE_STYLE } from './types';

interface Props {
  config: LoopConfig;
  model: { blocks: any[]; links: any[] } | null;
  library: Library;
  onChange: (c: LoopConfig) => void;
}

const W = 280, LH = 16, PAD = 8, GRID = 10, MARGIN = 80;
const snap = (v: number) => Math.round(v / GRID) * GRID;
const cut = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const inputSt = { background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)' };
const inp = 'px-2.5 py-1.5 rounded-lg text-xs outline-none w-full';
const lab = 'text-[10px] font-semibold uppercase tracking-wider block mb-1';

const heightOf = (b: any) => 34 + LH * (b.lines.length + (b.terminals.length ? 1 : 0)) + 2 * PAD;

function defaultPositions(blocks: any[]): Record<string, { x: number; y: number }> {
  const pos: Record<string, { x: number; y: number }> = {};
  let y = 90;
  const main = blocks.filter((b) => b.placement === 'main');
  for (const b of main) { pos[b.id] = { x: 340, y }; y += heightOf(b) + 140; }
  for (const b of blocks.filter((x) => x.placement !== 'main')) {
    const t = pos[b.attach_to];
    pos[b.id] = { x: 20, y: (t ? t.y : 90) + 10 };
  }
  return pos;
}

/** the point on the box border facing `toward` (centre line), used to anchor connection ends */
function anchor(a: { x: number; y: number; h: number }, b: { x: number; y: number; h: number }) {
  const ac = { x: a.x + W / 2, y: a.y + a.h / 2 }, bc = { x: b.x + W / 2, y: b.y + b.h / 2 };
  const dx = bc.x - ac.x, dy = bc.y - ac.y;
  if (Math.abs(dy) * 1.6 >= Math.abs(dx) * (a.h / W) * 1.6 && Math.abs(dy) > a.h / 2 + 4) {
    return dy > 0 ? { x: ac.x, y: a.y + a.h } : { x: ac.x, y: a.y };
  }
  return dx > 0 ? { x: a.x + W, y: ac.y } : { x: a.x, y: ac.y };
}

export default function DiagramCanvas({ config, model, library, onChange }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [drag, setDrag] = useState<{ id: string; dx: number; dy: number; x: number; y: number } | null>(null);
  const [wire, setWire] = useState<{ from: string; x: number; y: number } | null>(null);
  const [sel, setSel] = useState<{ kind: 'box' | 'link'; id: string } | null>(null);
  const [newKind, setNewKind] = useState('custom_box');

  const blocks = model?.blocks || [];
  const links = model?.links || [];
  const saved: Record<string, { x: number; y: number }> = config.layout?.positions || {};
  const defaults = useMemo(() => defaultPositions(blocks), [blocks]);
  const basePos = (id: string) => saved[id] || defaults[id] || { x: 40, y: 90 };
  const geo = (b: any) => {
    const p = drag && drag.id === b.id ? { x: drag.x, y: drag.y } : basePos(b.id);
    return { ...p, h: heightOf(b) };
  };
  const byId: Record<string, any> = {};
  blocks.forEach((b) => { byId[b.id] = geo(b); });

  const committed = blocks.map((b) => ({ ...basePos(b.id), h: heightOf(b) }));
  const vbW = Math.max(900, ...committed.map((g) => g.x + W + 360)) + MARGIN;
  const vbH = Math.max(520, ...committed.map((g) => g.y + g.h + 160)) + MARGIN;

  const svgPoint = (e: React.PointerEvent) => {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    const r = pt.matrixTransform(svg.getScreenCTM()!.inverse());
    return { x: r.x, y: r.y };
  };
  const boxAt = (x: number, y: number, except: string) =>
    blocks.find((b) => b.id !== except && x >= byId[b.id].x && x <= byId[b.id].x + W && y >= byId[b.id].y && y <= byId[b.id].y + byId[b.id].h);

  const setPositions = (positions: Record<string, { x: number; y: number }>) =>
    onChange({ ...config, layout: { ...(config.layout || {}), positions } });
  const allPositions = () => { const o: Record<string, { x: number; y: number }> = {}; blocks.forEach((b) => { o[b.id] = basePos(b.id); }); return o; };

  // ── dragging boxes ────────────────────────────────────────────────────────
  const startDrag = (e: React.PointerEvent, b: any) => {
    if (e.button !== 0) return;
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    const p = svgPoint(e), g = basePos(b.id);
    setSel({ kind: 'box', id: b.id });
    setDrag({ id: b.id, dx: p.x - g.x, dy: p.y - g.y, x: g.x, y: g.y });
  };
  const moveDrag = (e: React.PointerEvent) => {
    if (!drag) return;
    const p = svgPoint(e);
    setDrag({ ...drag, x: Math.max(0, snap(p.x - drag.dx)), y: Math.max(0, snap(p.y - drag.dy)) });
  };
  const endDrag = () => {
    if (!drag) return;
    const moved = basePos(drag.id).x !== drag.x || basePos(drag.id).y !== drag.y;
    if (moved) setPositions({ ...allPositions(), [drag.id]: { x: drag.x, y: drag.y } });
    setDrag(null);
  };

  // ── drawing connections: drag from a box's port onto another box ──────────
  const startWire = (e: React.PointerEvent, b: any) => {
    e.stopPropagation();
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    const p = svgPoint(e);
    setWire({ from: b.id, x: p.x, y: p.y });
  };
  const moveWire = (e: React.PointerEvent) => { if (wire) setWire({ ...wire, ...svgPoint(e) }); };
  const endWire = () => {
    if (!wire) return;
    const target = boxAt(wire.x, wire.y, wire.from);
    setWire(null);
    if (!target) return;
    if (links.some((l) => l.from_id === wire.from && l.to_id === target.id)) return;
    const roles: string[] = library.loop_types[config.loop_type]?.wires || [];
    const link = {
      from_id: wire.from, to_id: target.id, auto_wires: false,
      wires: roles.map((r) => ({ role: r, label: library.wire_roles[r] || r, colour: '', number: '', terminal_from: '', terminal_to: '' })),
      cable: { source: 'none', tag: '', type: '', length: '', cores: '', pairs: '', shield_type: null, shield_termination: null, termination_note: '' },
    };
    onChange({ ...config, manual_links: true, links: [...config.links, link] });
    setSel({ kind: 'link', id: `${link.from_id}>${link.to_id}` });
  };

  // ── editing ───────────────────────────────────────────────────────────────
  const updateComp = (id: string, ch: Record<string, any>) =>
    onChange({ ...config, components: config.components.map((c: any) => (c.id === id ? { ...c, ...ch } : c)) });
  const removeBox = (id: string) => {
    const positions = { ...(config.layout?.positions || {}) }; delete positions[id];
    onChange({
      ...config, components: config.components.filter((c: any) => c.id !== id),
      links: config.links.filter((l: any) => l.from_id !== id && l.to_id !== id),
      layout: { ...(config.layout || {}), positions },
    });
    setSel(null);
  };
  const addBox = () => {
    const n = Math.max(0, ...config.components.map((c: any) => parseInt(String(c.id).slice(1)) || 0)) + 1;
    const comp = { id: `c${n}`, kind: newKind, label: library.components[newKind]?.label || newKind, tag: '', placement: 'main', attach_to: '', terminals: [], notes: '' };
    const ys = blocks.map((b) => basePos(b.id).y + heightOf(b));
    onChange({
      ...config, components: [...config.components, comp],
      layout: { ...(config.layout || {}), positions: { ...allPositions(), [comp.id]: { x: 700, y: snap(Math.min(...ys, 200)) } } },
      ...(config.manual_links ? {} : { manual_links: true }),
    });
    setSel({ kind: 'box', id: comp.id });
  };
  const linkKey = (l: any) => `${l.from_id}>${l.to_id}`;
  const linkIdx = (key: string) => config.links.findIndex((l: any) => linkKey(l) === key);
  const updateLink = (key: string, ch: Record<string, any>) =>
    onChange({ ...config, manual_links: true, links: config.links.map((l: any) => (linkKey(l) === key ? { ...l, ...ch } : l)) });
  const updateCable = (key: string, ch: Record<string, any>) => {
    const l = config.links[linkIdx(key)];
    updateLink(key, { cable: { ...l.cable, ...ch } });
  };
  const updateWire = (key: string, wi: number, ch: Record<string, any>) => {
    const l = config.links[linkIdx(key)];
    updateLink(key, { auto_wires: false, wires: l.wires.map((w: any, k: number) => (k === wi ? { ...w, ...ch } : w)) });
  };
  const removeLink = (key: string) => { onChange({ ...config, manual_links: true, links: config.links.filter((l: any) => linkKey(l) !== key) }); setSel(null); };
  const reverseLink = (key: string) => {
    onChange({ ...config, manual_links: true, links: config.links.map((l: any) => (linkKey(l) === key ? { ...l, from_id: l.to_id, to_id: l.from_id } : l)) });
    const [a, b] = key.split('>'); setSel({ kind: 'link', id: `${b}>${a}` });
  };
  const resetLayout = () => {
    const layout = { ...(config.layout || {}) }; delete layout.positions;
    onChange({ ...config, layout });
  };

  // ── rendering ─────────────────────────────────────────────────────────────
  const selBlock = sel?.kind === 'box' ? blocks.find((b) => b.id === sel.id) : null;
  const selComp = sel?.kind === 'box' ? config.components.find((c: any) => c.id === sel.id) : null;
  const selLinkIdx = sel?.kind === 'link' ? linkIdx(sel.id) : -1;
  const selLink = selLinkIdx >= 0 ? config.links[selLinkIdx] : null;
  const name = (id: string) => { const b = blocks.find((x) => x.id === id); return b ? (b.title || b.heading) : id; };

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <select className={inp} style={{ ...inputSt, maxWidth: 200 }} value={newKind} onChange={(e) => setNewKind(e.target.value)}>
          {Object.entries(library.components).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <button className="text-xs px-2.5 py-1.5 rounded-lg flex items-center gap-1" style={{ background: 'var(--s3)', color: 'var(--t0)', border: '1px solid var(--b2)' }} onClick={addBox}>
          <Plus className="w-3 h-3" /> Add box
        </button>
        <button className="text-xs px-2.5 py-1.5 rounded-lg flex items-center gap-1" style={{ background: 'var(--s3)', color: 'var(--t0)', border: '1px solid var(--b2)' }} onClick={resetLayout}>
          <RotateCcw className="w-3 h-3" /> Reset layout
        </button>
        <span className="text-[11px]" style={{ color: 'var(--t2)' }}>
          Drag a box to move it · drag its ● handle onto another box to connect · click a box or a connection to edit it
        </span>
      </div>

      <div className="rounded-lg overflow-auto" style={{ background: '#fff', border: '1px solid #d0d0d0', maxHeight: 760 }}>
        <svg ref={svgRef} width={vbW} height={vbH} viewBox={`0 0 ${vbW} ${vbH}`} fontFamily="Arial, Helvetica, sans-serif" fontSize={12}
          style={{ touchAction: 'none', userSelect: 'none', display: 'block' }}
          onPointerMove={(e) => { moveDrag(e); moveWire(e); }} onPointerUp={() => { endDrag(); endWire(); }}
          onPointerDown={(e) => { if (e.target === e.currentTarget) setSel(null); }}>
          <defs><marker id="arr" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#000" /></marker></defs>
          <rect width="100%" height="100%" fill="#fff" onPointerDown={() => setSel(null)} />
          <text x={20} y={28} fontSize={16} fontWeight="bold">LOOP WIRING (TEST) — {config.tag_no}</text>

          {links.map((l) => {
            const a = byId[l.from_id], c = byId[l.to_id];
            if (!a || !c) return null;
            const p1 = anchor(a, c), p2 = anchor(c, a);
            const key = `${l.from_id}>${l.to_id}`;
            const on = sel?.kind === 'link' && sel.id === key;
            const mx = (p1.x + p2.x) / 2, my = (p1.y + p2.y) / 2;
            const text: { t: string; red: boolean }[] = [
              ...l.lines.map((x: any) => ({ t: x.text, red: x.missing })),
              ...(l.wires.length ? [{ t: `${l.wires.length} wires: ${cut(l.wires.map((w: any) => w.label).join(', '), 44)}`, red: false }] : []),
              { t: `Shield: ${l.shield.type || 'NOT DEFINED'}${l.shield.termination ? ` · ${l.shield.termination}` : ''}`, red: !l.shield.defined },
            ];
            return (
              <g key={key} style={{ cursor: 'pointer' }} onPointerDown={(e) => { e.stopPropagation(); setSel({ kind: 'link', id: key }); }}>
                <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke="transparent" strokeWidth={16} />
                <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke={on ? '#2563eb' : '#000'} strokeWidth={on ? 2.5 : 1.5} markerEnd="url(#arr)" strokeDasharray={l.has_cable ? undefined : '6 4'} />
                {text.map((x, i) => (
                  <text key={i} x={mx + 10} y={my - (text.length * 14) / 2 + 12 + i * 14} fontSize={11} fill={x.red ? '#c00000' : '#222'}
                    fontStyle={x.red ? 'italic' : 'normal'} stroke="#fff" strokeWidth={3} paintOrder="stroke">{x.t}</text>
                ))}
              </g>
            );
          })}

          {blocks.map((b) => {
            const g = geo(b);
            const on = sel?.kind === 'box' && sel.id === b.id;
            let ty = g.y + 34 + PAD + 4;
            return (
              <g key={b.id} style={{ cursor: drag?.id === b.id ? 'grabbing' : 'grab' }} onPointerDown={(e) => startDrag(e, b)}>
                <rect x={g.x} y={g.y} width={W} height={g.h} fill="#fff" stroke={on ? '#2563eb' : '#000'} strokeWidth={on ? 2.5 : 1.5} />
                <text x={g.x + PAD} y={g.y + 15} fontSize={10} fill="#555">{String(b.heading).toUpperCase()}</text>
                <text x={g.x + PAD} y={g.y + 33} fontSize={14} fontWeight="bold">{cut(b.title || '—', 30)}</text>
                {b.lines.map((ln: any, i: number) => {
                  const y = ty + 8; ty += LH;
                  return <text key={i} x={g.x + PAD} y={y} fill={ln.missing ? '#c00000' : '#000'} fontStyle={ln.missing ? 'italic' : 'normal'}>{cut(ln.text, 42)}</text>;
                })}
                {b.terminals.length > 0 && (
                  <text x={g.x + PAD} y={ty + 8} fontFamily="monospace" fontSize={11}>▸ {cut(b.terminals.map((t: any) => `${t.label}:${t.value}`).join('  '), 36)}</text>
                )}
                <circle cx={g.x + W} cy={g.y + g.h / 2} r={6} fill={on ? '#2563eb' : '#555'} stroke="#fff" strokeWidth={1.5}
                  style={{ cursor: 'crosshair' }} onPointerDown={(e) => startWire(e, b)}><title>Drag onto another box to connect</title></circle>
              </g>
            );
          })}

          {wire && byId[wire.from] && (
            <line x1={byId[wire.from].x + W} y1={byId[wire.from].y + byId[wire.from].h / 2} x2={wire.x} y2={wire.y} stroke="#2563eb" strokeWidth={2} strokeDasharray="5 4" />
          )}
        </svg>
      </div>

      {selBlock && selComp && (
        <div className="rounded-xl p-3 mt-3" style={{ background: 'var(--s3)', border: '1px solid var(--b2)' }}>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-bold" style={{ color: 'var(--t0)' }}>Edit box · {selBlock.heading} {selBlock.title && <span className="font-mono">{selBlock.title}</span>}</p>
            <button className="text-xs flex items-center gap-1" style={{ color: 'var(--rose)' }} onClick={() => removeBox(selComp.id)}><Trash2 className="w-3 h-3" /> Delete box</button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-2">
            <div><label className={lab} style={{ color: 'var(--t2)' }}>Heading</label>
              <input className={inp} style={inputSt} value={selComp.label || ''} onChange={(e) => updateComp(selComp.id, { label: e.target.value })} /></div>
            <div><label className={lab} style={{ color: 'var(--t2)' }}>Name / tag (empty = value from the source documents)</label>
              <input className={inp} style={inputSt} value={selComp.tag || ''} onChange={(e) => updateComp(selComp.id, { tag: e.target.value })} /></div>
          </div>
          {selBlock.lines.some((l: any) => l.source !== 'USER CONFIGURATION') && (
            <div className="mb-2">
              <label className={lab} style={{ color: 'var(--t2)' }}>From the source documents (read-only)</label>
              {selBlock.lines.filter((l: any) => l.source !== 'USER CONFIGURATION').map((l: any, i: number) => (
                <p key={i} className="text-xs" style={{ color: l.missing ? 'var(--rose)' : 'var(--t1)' }}>
                  {l.text}{l.source && <span className="text-[9px] font-bold px-1.5 py-0.5 rounded ml-2" style={{ background: `${SOURCE_STYLE[l.source] || 'var(--t2)'}22`, color: SOURCE_STYLE[l.source] || 'var(--t2)' }}>{l.source === 'I/O ASSIGNMENT' ? 'I/O' : l.source}</span>}
                </p>
              ))}
            </div>
          )}
          <label className={lab} style={{ color: 'var(--t2)' }}>Text lines inside the box (one per line)</label>
          <textarea className={inp} style={{ ...inputSt, minHeight: 64 }} value={selComp.notes || ''} onChange={(e) => updateComp(selComp.id, { notes: e.target.value })} />
          <label className={`${lab} mt-2`} style={{ color: 'var(--t2)' }}>Terminals</label>
          {(selComp.terminals || []).map((t: any, i: number) => (
            <div key={i} className="grid grid-cols-[1fr,1fr,2fr,24px] gap-1.5 mb-1 items-center">
              <input className={inp} style={inputSt} placeholder="Terminal no." value={t.number || ''} onChange={(e) => updateComp(selComp.id, { terminals: selComp.terminals.map((x: any, k: number) => (k === i ? { ...x, number: e.target.value } : x)) })} />
              <input className={inp} style={inputSt} placeholder="+ / -" value={t.polarity || ''} onChange={(e) => updateComp(selComp.id, { terminals: selComp.terminals.map((x: any, k: number) => (k === i ? { ...x, polarity: e.target.value } : x)) })} />
              <input className={inp} style={inputSt} placeholder="Description" value={t.description || ''} onChange={(e) => updateComp(selComp.id, { terminals: selComp.terminals.map((x: any, k: number) => (k === i ? { ...x, description: e.target.value } : x)) })} />
              <button title="Remove" onClick={() => updateComp(selComp.id, { terminals: selComp.terminals.filter((_: any, k: number) => k !== i) })}><X className="w-3.5 h-3.5" style={{ color: 'var(--t2)' }} /></button>
            </div>
          ))}
          <button className="text-xs underline" style={{ color: 'var(--t1)' }} onClick={() => updateComp(selComp.id, { terminals: [...(selComp.terminals || []), { number: '', polarity: '', description: '' }] })}>+ Add terminal</button>
        </div>
      )}

      {selLink && sel && (
        <div className="rounded-xl p-3 mt-3" style={{ background: 'var(--s3)', border: '1px solid var(--b2)' }}>
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-bold" style={{ color: 'var(--t0)' }}>Edit connection · {name(selLink.from_id)} → {name(selLink.to_id)}</p>
            <div className="flex gap-3">
              <button className="text-xs underline" style={{ color: 'var(--t1)' }} onClick={() => reverseLink(sel.id)}>Reverse direction</button>
              <button className="text-xs flex items-center gap-1" style={{ color: 'var(--rose)' }} onClick={() => removeLink(sel.id)}><Trash2 className="w-3 h-3" /> Delete connection</button>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-2 mb-2">
            <div><label className={lab} style={{ color: 'var(--t2)' }}>Cable data from</label>
              <select className={inp} style={inputSt} value={selLink.cable.source} onChange={(e) => updateCable(sel.id, { source: e.target.value })}>
                <option value="none">No cable</option><option value="branch">Branch cable (IODB)</option>
                <option value="main">Main cable (IODB)</option><option value="custom">Custom</option>
              </select></div>
            <div><label className={lab} style={{ color: 'var(--t2)' }}>Shield</label>
              <select className={inp} style={inputSt} value={selLink.cable.shield_type ?? ''} onChange={(e) => updateCable(sel.id, { shield_type: e.target.value || null })}>
                <option value="">— not set —</option>{Object.entries(library.shield_types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></div>
            <div><label className={lab} style={{ color: 'var(--t2)' }}>Shield termination</label>
              <select className={inp} style={inputSt} value={selLink.cable.shield_termination ?? ''} disabled={!selLink.cable.shield_type || selLink.cable.shield_type === 'none'}
                onChange={(e) => updateCable(sel.id, { shield_termination: e.target.value || null })}>
                <option value="">— not set —</option>{Object.entries(library.shield_terminations).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></div>
            <div className="grid grid-cols-2 gap-2">
              <div><label className={lab} style={{ color: 'var(--t2)' }}>Cores</label><input className={inp} style={inputSt} value={selLink.cable.cores} placeholder="auto" onChange={(e) => updateCable(sel.id, { cores: e.target.value })} /></div>
              <div><label className={lab} style={{ color: 'var(--t2)' }}>Pairs</label><input className={inp} style={inputSt} value={selLink.cable.pairs} placeholder="auto" onChange={(e) => updateCable(sel.id, { pairs: e.target.value })} /></div>
            </div>
          </div>
          {selLink.cable.source === 'custom' && (
            <div className="grid grid-cols-3 gap-2 mb-2">
              {(['tag', 'type', 'length'] as const).map((k) => (
                <input key={k} className={inp} style={inputSt} placeholder={`Cable ${k}`} value={selLink.cable[k]} onChange={(e) => updateCable(sel.id, { [k]: e.target.value })} />
              ))}
            </div>
          )}
          {selLink.wires.map((w: any, wi: number) => (
            <div key={wi} className="grid grid-cols-[1.4fr,1fr,1fr,1fr,1fr,24px] gap-1.5 mb-1 items-center">
              <input className={inp} style={inputSt} value={w.label} onChange={(e) => updateWire(sel.id, wi, { label: e.target.value })} />
              <input className={inp} style={inputSt} value={w.colour} placeholder="Colour" onChange={(e) => updateWire(sel.id, wi, { colour: e.target.value })} />
              <input className={inp} style={inputSt} value={w.number} placeholder="Wire no." onChange={(e) => updateWire(sel.id, wi, { number: e.target.value })} />
              <input className={inp} style={inputSt} value={w.terminal_from} placeholder="Terminal from" onChange={(e) => updateWire(sel.id, wi, { terminal_from: e.target.value })} />
              <input className={inp} style={inputSt} value={w.terminal_to} placeholder="Terminal to" onChange={(e) => updateWire(sel.id, wi, { terminal_to: e.target.value })} />
              <button title="Remove wire" onClick={() => updateLink(sel.id, { auto_wires: false, wires: selLink.wires.filter((_: any, k: number) => k !== wi) })}><X className="w-3.5 h-3.5" style={{ color: 'var(--t2)' }} /></button>
            </div>
          ))}
          <button className="text-xs underline" style={{ color: 'var(--t1)' }} onClick={() => updateLink(sel.id, { auto_wires: false, wires: [...selLink.wires, { role: 'SPARE', label: 'Spare', colour: '', number: '', terminal_from: '', terminal_to: '' }] })}>+ Add wire</button>
        </div>
      )}
    </div>
  );
}
