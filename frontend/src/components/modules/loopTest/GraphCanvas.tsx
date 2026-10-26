/**
 * Block canvas: draws the SCENE the server built from the graph (the same scene the Excel image uses) and adds the
 * interaction: drag blocks, drag from a port to another port to create a wire, select, zoom, pan.
 * Wires are attached to (block, port) in the graph - the canvas only reports gestures; it never decides connections.
 */
import { useEffect, useRef, useState } from 'react';
import { Maximize2, ZoomIn, ZoomOut } from 'lucide-react';

export interface Scene {
  w: number; h: number; items: any[];
  nodes: Record<string, { x: number; y: number; w: number; h: number; zone: string; tag: string; label: string; type: string }>;
  ports: Record<string, { node: string; port: string; side: string; x: number; y: number }>;
  edges: Record<string, { from: { node: string; port: string; side: string }; to: { node: string; port: string; side: string }; pts: number[][]; kind: string }>;
  bands: any[]; zone_geometry: { ML: number; ZW: number; ZH: number; TOP: number; orientation: string };
}
export interface Selection { kind: 'none' | 'node' | 'edge'; ids: string[] }

interface Props {
  scene: Scene | null;
  selection: Selection;
  onSelect: (s: Selection) => void;
  onMove: (positions: Record<string, { x: number; y: number }>) => void;
  onConnect: (from: { node: string; port: string }, to: { node: string; port: string }) => void;
  onDropComponent: (component: string, x: number, y: number) => void;
  height?: number;
}

const HEIGHT = 700;

export default function GraphCanvas({ scene, selection, onSelect, onMove, onConnect, onDropComponent, height = HEIGHT }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const inited = useRef(false);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [drag, setDrag] = useState<null | { kind: 'nodes'; ids: string[]; sx: number; sy: number; dx: number; dy: number }
    | { kind: 'wire'; from: { node: string; port: string; side: string }; x: number; y: number }
    | { kind: 'pan'; sx: number; sy: number; vx: number; vy: number }>(null);

  // first drawing: open at a readable zoom (not the whole 5-column sheet squeezed into the window)
  useEffect(() => {
    if (!scene) { inited.current = false; return; }
    if (inited.current || !wrapRef.current) return;
    inited.current = true;
    const cw = wrapRef.current.clientWidth || 800;
    const fit = Math.min(cw / scene.w, height / scene.h);
    setView({ x: 0, y: 0, k: Math.min(4, Math.max(1, 0.75 / fit)) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene === null]);

  if (!scene) return <div className="p-8 text-sm" style={{ color: 'var(--t2)' }}>Building drawing…</div>;

  const toScene = (e: { clientX: number; clientY: number }) => {
    const svg = svgRef.current!;
    const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    const r = pt.matrixTransform(svg.getScreenCTM()!.inverse());
    return { x: r.x, y: r.y };
  };
  const vbW = scene.w / view.k, vbH = scene.h / view.k;
  const zoom = (f: number) => setView((v) => {
    const k = Math.min(4, Math.max(0.25, v.k * f));
    const cx = v.x + scene.w / v.k / 2, cy = v.y + scene.h / v.k / 2;
    return { k, x: cx - scene.w / k / 2, y: cy - scene.h / k / 2 };
  });

  const moving = drag?.kind === 'nodes' ? new Set(drag.ids) : new Set<string>();
  const dx = drag?.kind === 'nodes' ? drag.dx : 0, dy = drag?.kind === 'nodes' ? drag.dy : 0;

  const startNode = (e: React.PointerEvent, id: string) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    const additive = e.shiftKey || e.ctrlKey || e.metaKey;
    let ids = selection.kind === 'node' ? selection.ids : [];
    if (additive) ids = ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
    else if (!ids.includes(id)) ids = [id];
    onSelect({ kind: 'node', ids });
    const p = toScene(e);
    setDrag({ kind: 'nodes', ids: ids.length ? ids : [id], sx: p.x, sy: p.y, dx: 0, dy: 0 });
  };
  const startWire = (e: React.PointerEvent, pr: { node: string; port: string; side: string }) => {
    e.stopPropagation();
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    const p = toScene(e);
    setDrag({ kind: 'wire', from: pr, x: p.x, y: p.y });
  };
  const startPan = (e: React.PointerEvent) => {
    if (e.target !== e.currentTarget && !(e.target as Element).hasAttribute('data-bg')) return;
    onSelect({ kind: 'none', ids: [] });
    const p = toScene(e);
    setDrag({ kind: 'pan', sx: p.x, sy: p.y, vx: view.x, vy: view.y });
  };
  const onMoveEv = (e: React.PointerEvent) => {
    if (!drag) return;
    const p = toScene(e);
    if (drag.kind === 'nodes') setDrag({ ...drag, dx: p.x - drag.sx, dy: p.y - drag.sy });
    else if (drag.kind === 'wire') setDrag({ ...drag, x: p.x, y: p.y });
    else if (drag.kind === 'pan') setView((v) => ({ ...v, x: drag.vx - (p.x - drag.sx), y: drag.vy - (p.y - drag.sy) }));
  };
  const onUp = (e: React.PointerEvent) => {
    if (!drag) return;
    if (drag.kind === 'nodes' && (Math.abs(drag.dx) > 2 || Math.abs(drag.dy) > 2)) {
      const pos: Record<string, { x: number; y: number }> = {};
      drag.ids.forEach((id) => { const n = scene.nodes[id]; if (n) pos[id] = { x: Math.max(0, n.x + drag.dx), y: Math.max(0, n.y + drag.dy) }; });
      onMove(pos);
    } else if (drag.kind === 'wire') {
      const el = document.elementsFromPoint(e.clientX, e.clientY).find((x) => x.getAttribute?.('data-port'));
      const key = el?.getAttribute('data-port');
      if (key) {
        const [node, port] = key.split(':');
        if (node !== drag.from.node || port !== drag.from.port) onConnect({ node: drag.from.node, port: drag.from.port }, { node, port });
      }
    }
    setDrag(null);
  };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const comp = e.dataTransfer.getData('component');
    if (!comp) return;
    const p = toScene(e);
    onDropComponent(comp, p.x - 120, p.y - 20);
  };

  const selNodes = new Set(selection.kind === 'node' ? selection.ids : []);
  const selEdge = selection.kind === 'edge' ? selection.ids[0] : '';
  const anchorOf = (a: { node: string; port: string; side: string }) => {
    const pt = scene.ports[`${a.node}:${a.port}:${a.side}`];
    return pt ? { x: pt.x + (moving.has(a.node) ? dx : 0), y: pt.y + (moving.has(a.node) ? dy : 0) } : null;
  };
  const linkedToMoving = (eid: string) => { const e = scene.edges[eid]; return !!e && (moving.has(e.from.node) || moving.has(e.to.node)); };

  const render = (it: any, i: number) => {
    const shift = it.n && moving.has(it.n) ? `translate(${dx},${dy})` : undefined;
    const onNode = it.n ? { onPointerDown: (e: React.PointerEvent) => startNode(e, it.n), style: { cursor: drag?.kind === 'nodes' ? 'grabbing' : 'grab' } as React.CSSProperties } : {};
    switch (it.t) {
      case 'rect':
        return <rect key={i} x={it.x} y={it.y} width={it.w} height={it.h} fill={it.fill} stroke={it.stroke} strokeWidth={it.sw} transform={shift}
          data-bg={!it.n && it.fill === 'none' ? undefined : (!it.n ? '1' : undefined)} {...onNode} />;
      case 'line':
        return <line key={i} x1={it.x1} y1={it.y1} x2={it.x2} y2={it.y2} stroke={it.stroke} strokeWidth={it.sw} strokeDasharray={it.dash} transform={shift} pointerEvents="none" />;
      case 'text':
        if (it.e && linkedToMoving(it.e)) return null;
        return <text key={i} x={it.x} y={it.y} fontSize={it.size} fontWeight={it.bold ? 700 : 400} fontStyle={it.italic ? 'italic' : 'normal'} fill={it.fill || '#000'}
          textAnchor={it.anchor || 'start'} transform={shift} stroke="#fff" strokeWidth={it.e ? 3 : 0} paintOrder="stroke" {...onNode} pointerEvents={it.n ? 'auto' : 'none'}>{it.s}</text>;
      case 'poly': {
        if (linkedToMoving(it.e)) return null;
        const pts = it.pts.map((p: number[]) => p.join(',')).join(' ');
        const on = selEdge === it.e;
        return (
          <g key={i} style={{ cursor: 'pointer' }} onPointerDown={(e) => { e.stopPropagation(); onSelect({ kind: 'edge', ids: [it.e] }); }}>
            <polyline points={pts} fill="none" stroke="transparent" strokeWidth={12} />
            <polyline points={pts} fill="none" stroke={on ? '#2563eb' : it.stroke} strokeWidth={on ? it.sw + 1.4 : it.sw} strokeDasharray={it.dash} />
          </g>
        );
      }
      case 'circle': {
        const key = it.port ? `${it.port.node}:${it.port.port}:${it.port.side}` : '';
        return <circle key={i} cx={it.cx} cy={it.cy} r={it.r + 1} fill={it.fill} stroke={it.stroke} strokeWidth={it.sw} transform={shift}
          data-port={it.port ? `${it.port.node}:${it.port.port}` : undefined} style={{ cursor: 'crosshair' }}
          onPointerDown={(e) => it.port && startWire(e, it.port)}><title>{key.replace(/:/g, ' / ')} - drag to another port to connect</title></circle>;
      }
      default: return null;
    }
  };

  return (
    <div className="relative">
      <div className="absolute right-2 top-2 z-10 flex gap-1">
        {[[ZoomIn, 1.25, 'Zoom in'], [ZoomOut, 0.8, 'Zoom out']].map(([Icon, f, t]: any) => (
          <button key={t} title={t} className="p-1.5 rounded-lg" style={{ background: 'var(--s3)', border: '1px solid var(--b2)', color: 'var(--t0)' }} onClick={() => zoom(f)}><Icon className="w-4 h-4" /></button>
        ))}
        <button title="Fit to window" className="p-1.5 rounded-lg" style={{ background: 'var(--s3)', border: '1px solid var(--b2)', color: 'var(--t0)' }} onClick={() => setView({ x: 0, y: 0, k: 1 })}><Maximize2 className="w-4 h-4" /></button>
      </div>
      <div ref={wrapRef} className="rounded-lg overflow-hidden" style={{ background: '#fff', border: '1px solid #d0d0d0' }}
        onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
        <svg ref={svgRef} width="100%" height={height} viewBox={`${view.x} ${view.y} ${vbW} ${vbH}`} preserveAspectRatio="xMinYMin meet"
          fontFamily="Arial, Helvetica, sans-serif" style={{ touchAction: 'none', userSelect: 'none', display: 'block' }}
          onPointerDown={startPan} onPointerMove={onMoveEv} onPointerUp={onUp}
          onWheel={(e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); zoom(e.deltaY < 0 ? 1.1 : 0.9); } }}>
          <rect x={-5000} y={-5000} width={12000} height={12000} fill="#fff" data-bg="1" />
          {scene.items.map(render)}
          {Array.from(selNodes).map((id) => {
            const n = scene.nodes[id];
            return n ? <rect key={`sel-${id}`} x={n.x - 4} y={n.y - 4} width={n.w + 8} height={n.h + 8} fill="none" stroke="#2563eb" strokeWidth={2} strokeDasharray="6 3"
              transform={moving.has(id) ? `translate(${dx},${dy})` : undefined} pointerEvents="none" /> : null;
          })}
          {drag?.kind === 'nodes' && Object.entries(scene.edges).filter(([id]) => linkedToMoving(id)).map(([id, e]) => {
            const a = anchorOf(e.from), b = anchorOf(e.to);
            return a && b ? <line key={`m-${id}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#2563eb" strokeWidth={1.5} strokeDasharray="4 3" pointerEvents="none" /> : null;
          })}
          {drag?.kind === 'wire' && (() => {
            const a = scene.ports[`${drag.from.node}:${drag.from.port}:${drag.from.side}`];
            return a ? <line x1={a.x} y1={a.y} x2={drag.x} y2={drag.y} stroke="#2563eb" strokeWidth={2} strokeDasharray="5 4" pointerEvents="none" /> : null;
          })()}
        </svg>
      </div>
    </div>
  );
}
