/**
 * Instrument line art in P&ID language (ISA-5.1): a pressure control loop, a dial gauge and an analyser trend.
 * Drawn as thin SVG line work; signal orange is the only colour. Respects prefers-reduced-motion.
 */
import { useEffect, useId, useRef, useState } from 'react';

const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

interface Tone { line?: string; text?: string; accent?: string; faint?: string; bg?: string }
const DEF: Required<Tone> = { line: 'var(--t1)', text: 'var(--t2)', accent: 'var(--em)', faint: 'var(--b2)', bg: 'var(--s0)' };

/* ── Pressure control loop: PI gauge, PT transmitter → PIC controller → control valve ───────────────────── */
export function LoopArt({ tone = {}, className = '', style, tag = '101' }: { tone?: Tone; className?: string; style?: React.CSSProperties; tag?: string }) {
  const t = { ...DEF, ...tone };
  const anim = !reducedMotion();
  const id = useId().replace(/:/g, '');
  const sig = `M170 112 V62 H430 V176`;            // PT → PIC → valve actuator (passes through the controller)
  const draw = (d: number): React.CSSProperties => ({ ['--d' as any]: `${d}ms` });
  return (
    <svg viewBox="0 0 640 290" className={`ia ${anim ? 'ia-anim' : ''} ${className}`} style={style} role="img" aria-label={`Pressure control loop ${tag}: gauge, transmitter, controller and control valve`}>
      {/* process line + flow */}
      <path className="ia-draw" style={draw(0)} pathLength={1} d="M14 232 H626" stroke={t.line} strokeWidth="2.4" fill="none" />
      {anim && <path d="M14 232 H626" stroke={t.accent} strokeWidth="2.4" strokeDasharray="3 22" fill="none" opacity=".55" className="ia-flow" />}
      <path className="ia-draw" style={draw(150)} pathLength={1} d="M40 224 L52 232 L40 240 M600 224 L612 232 L600 240" stroke={t.line} strokeWidth="1.6" fill="none" />
      <text x="16" y="262" className="ia-t" fill={t.text}>RAW WATER</text>
      <text x="626" y="262" className="ia-t" textAnchor="end" fill={t.text}>TO FILTRATION</text>

      {/* PI · local dial gauge on its tapping */}
      <path className="ia-draw" style={draw(250)} pathLength={1} d="M92 232 V190" stroke={t.line} strokeWidth="1.4" fill="none" />
      <circle className="ia-draw" style={draw(350)} pathLength={1} cx="92" cy="156" r="32" stroke={t.line} strokeWidth="1.6" fill="none" />
      {Array.from({ length: 11 }, (_, i) => {
        const a = (-135 + i * 27) * Math.PI / 180;
        const r1 = i % 5 === 0 ? 22 : 25, r2 = 28;
        return <line key={i} x1={92 + r1 * Math.sin(a)} y1={156 - r1 * Math.cos(a)} x2={92 + r2 * Math.sin(a)} y2={156 - r2 * Math.cos(a)} stroke={t.line} strokeWidth={i % 5 === 0 ? 1.4 : 0.9} className="ia-fade" style={draw(600)} />;
      })}
      <g className={anim ? 'ia-needle' : ''} style={{ transformOrigin: '92px 156px', transform: anim ? undefined : 'rotate(38deg)' }}>
        <line x1="92" y1="156" x2="92" y2="133" stroke={t.accent} strokeWidth="2" strokeLinecap="round" />
      </g>
      <circle cx="92" cy="156" r="3" fill={t.accent} />
      <text x="92" y="108" className="ia-t" textAnchor="middle" fill={t.text}>PI {tag}</text>

      {/* PT · field transmitter bubble */}
      <path className="ia-draw" style={draw(450)} pathLength={1} d="M170 232 V156" stroke={t.line} strokeWidth="1.4" fill="none" />
      <circle className="ia-draw" style={draw(550)} pathLength={1} cx="170" cy="134" r="22" stroke={t.line} strokeWidth="1.6" fill="none" />
      <text x="170" y="131" className="ia-b" textAnchor="middle" fill={t.line}>PT</text>
      <text x="170" y="145" className="ia-s" textAnchor="middle" fill={t.text}>{tag}</text>

      {/* PIC · panel-mounted controller (line through the bubble) */}
      <circle className="ia-draw" style={draw(700)} pathLength={1} cx="300" cy="62" r="22" stroke={t.line} strokeWidth="1.6" fill="none" />
      <line x1="278" y1="62" x2="322" y2="62" stroke={t.line} strokeWidth="1.2" className="ia-fade" style={draw(800)} />
      <text x="300" y="55" className="ia-b" textAnchor="middle" fill={t.line}>PIC</text>
      <text x="300" y="77" className="ia-s" textAnchor="middle" fill={t.text}>{tag}</text>
      <text x="300" y="24" className="ia-t" textAnchor="middle" fill={t.text}>CONTROL ROOM · 4-20 mA</text>

      {/* electrical signal lines (dashed, ISA) */}
      <path d="M170 112 V62 H278" stroke={t.line} strokeWidth="1.2" strokeDasharray="6 5" fill="none" className="ia-fade" style={draw(900)} />
      <path d="M322 62 H430 V176" stroke={t.line} strokeWidth="1.2" strokeDasharray="6 5" fill="none" className="ia-fade" style={draw(1000)} />

      {/* control valve with diaphragm actuator */}
      <g className={anim ? 'ia-stroke' : ''}>
        <path className="ia-draw" style={draw(800)} pathLength={1} d="M412 176 A18 18 0 0 1 448 176 Z" stroke={t.line} strokeWidth="1.6" fill="none" />
        <path className="ia-draw" style={draw(850)} pathLength={1} d="M430 176 V232" stroke={t.line} strokeWidth="1.6" fill="none" />
      </g>
      <path className="ia-draw" style={draw(650)} pathLength={1} d="M408 218 V246 L430 232 Z M452 218 V246 L430 232 Z" stroke={t.line} strokeWidth="1.6" fill={t.bg} />
      <text x="462" y="196" className="ia-t" fill={t.text}>PCV {tag}</text>

      {/* the signal travelling PT → PIC → valve */}
      {anim && (
        <>
          <path id={`sig${id}`} d={sig} fill="none" stroke="none" />
          <circle r="4.2" fill={t.accent}>
            <animateMotion dur="4.8s" repeatCount="indefinite" begin="1.6s" keyPoints="0;1" keyTimes="0;1" calcMode="linear"><mpath href={`#sig${id}`} /></animateMotion>
            <animate attributeName="opacity" values="0;1;1;0" keyTimes="0;.06;.94;1" dur="4.8s" begin="1.6s" repeatCount="indefinite" />
          </circle>
          <circle r="9" fill={t.accent} opacity=".16">
            <animateMotion dur="4.8s" repeatCount="indefinite" begin="1.6s"><mpath href={`#sig${id}`} /></animateMotion>
          </circle>
        </>
      )}
    </svg>
  );
}

/* ── Dial gauge: needle sweeps to the value and keeps a living signal flutter ───────────────────────────── */
export function Gauge({ value, max = 100, size = 64, label, tone = {} }: { value: number; max?: number; size?: number; label?: string; tone?: Tone }) {
  const t = { ...DEF, ...tone };
  const [v, setV] = useState(0);
  useEffect(() => { const id = window.setTimeout(() => setV(value), 120); return () => window.clearTimeout(id); }, [value]);
  const ang = -135 + (Math.max(0, Math.min(v, max)) / max) * 270;
  const c = 50, r = 40;
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} role="img" aria-label={label ? `${label}: ${value}` : `${value}`}>
      <circle cx={c} cy={c} r={r + 6} fill="none" stroke={t.faint} strokeWidth="1.2" />
      {Array.from({ length: 28 }, (_, i) => {
        const a = (-135 + i * 10) * Math.PI / 180;
        const major = i % 5 === 0 || i === 27;
        const r1 = major ? r - 9 : r - 5;
        return <line key={i} x1={c + r1 * Math.sin(a)} y1={c - r1 * Math.cos(a)} x2={c + r * Math.sin(a)} y2={c - r * Math.cos(a)} stroke={t.line} strokeWidth={major ? 1.8 : 0.9} opacity={major ? 1 : 0.6} />;
      })}
      <path d={`M ${c + (r + 1) * Math.sin(1.4)} ${c - (r + 1) * Math.cos(1.4)} A ${r + 1} ${r + 1} 0 0 1 ${c + (r + 1) * Math.sin(2.356)} ${c - (r + 1) * Math.cos(2.356)}`} stroke={t.accent} strokeWidth="2.4" fill="none" opacity=".75" />
      <g style={{ transform: `rotate(${ang}deg)`, transformOrigin: '50px 50px', transition: 'transform 1.6s cubic-bezier(.34,1.3,.64,1)' }}>
        <g className={reducedMotion() ? '' : 'ia-jitter'} style={{ transformOrigin: '50px 50px' }}>
          <line x1={c} y1={c + 8} x2={c} y2={c - r + 6} stroke={t.accent} strokeWidth="2.6" strokeLinecap="round" />
        </g>
      </g>
      <circle cx={c} cy={c} r="4.5" fill={t.accent} />
      <circle cx={c} cy={c} r="1.6" fill="var(--s2)" />
    </svg>
  );
}

/* ── Analyser: a transmitter head with a live reading and a trend being written (for processing screens) ── */
export function AnalyserArt({ tag = 'AIT 201', unit = 'pH', base = 7.2, label = 'Working', tone = {}, className = '' }:
  { tag?: string; unit?: string; base?: number; label?: string; tone?: Tone; className?: string }) {
  const t = { ...DEF, ...tone };
  const anim = !reducedMotion();
  const N = 48;
  const [pts, setPts] = useState<number[]>(() => Array.from({ length: N }, (_, i) => base + Math.sin(i / 5) * 0.12));
  const raf = useRef<number | null>(null);
  useEffect(() => {
    if (!anim) return;
    const id = window.setInterval(() => {
      setPts((p) => {
        const last = p[p.length - 1];
        const next = last + (base - last) * 0.18 + (Math.random() - 0.5) * 0.16;
        return [...p.slice(1), next];
      });
    }, 260);
    return () => { window.clearInterval(id); if (raf.current) cancelAnimationFrame(raf.current); };
  }, [anim, base]);
  const lo = base - 0.6, hi = base + 0.6;
  const W = 220, H = 70, X0 = 108;
  const path = pts.map((v, i) => `${i ? 'L' : 'M'}${(X0 + (i / (N - 1)) * W).toFixed(1)} ${(14 + (1 - (v - lo) / (hi - lo)) * H).toFixed(1)}`).join(' ');
  const cur = pts[pts.length - 1];
  return (
    <svg viewBox="0 0 340 104" className={`ia ${className}`} role="img" aria-label={`${label} - analyser ${tag}`}>
      {/* transmitter head */}
      <rect x="6" y="10" width="86" height="64" rx="9" fill="none" stroke={t.line} strokeWidth="1.5" />
      <rect x="16" y="20" width="66" height="28" rx="4" fill="none" stroke={t.faint} strokeWidth="1.2" />
      <text x="49" y="40" textAnchor="middle" className="ia-num" fill={t.line}>{cur.toFixed(2)}</text>
      <text x="16" y="64" className="ia-s" fill={t.text}>{unit}</text>
      <circle cx="78" cy="61" r="3" fill={t.accent} className={anim ? 'ia-blink' : ''} />
      <path d="M49 74 V96" stroke={t.line} strokeWidth="1.4" />
      <text x="6" y="100" className="ia-s" fill={t.text}>{tag}</text>
      {/* trend */}
      {[0, 1, 2].map((i) => <line key={i} x1={X0} x2={X0 + W} y1={14 + i * (H / 2)} y2={14 + i * (H / 2)} stroke={t.faint} strokeWidth=".8" strokeDasharray="2 4" />)}
      <path d={path} fill="none" stroke={t.accent} strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx={X0 + W} cy={14 + (1 - (cur - lo) / (hi - lo)) * H} r="3" fill={t.accent} />
      <text x={X0} y="100" className="ia-s" fill={t.text}>{label.toUpperCase()}</text>
    </svg>
  );
}
