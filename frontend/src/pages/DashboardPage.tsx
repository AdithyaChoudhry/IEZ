import { Link } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import {
  CheckCircle2, FileSpreadsheet, Cable, FileText, Network, GitBranch, Layers, ArrowRight, ArrowUpRight,
  ScanSearch, Sparkles, ShoppingCart, ClipboardList, Database, Search,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useReveal } from '@/hooks/useReveal';

/* ── Modules ──────────────────────────────────────────────────────────────── */
const modules = [
  { id: 'validator',    path: '/validator',       icon: CheckCircle2,    name: 'IODB Validator',           desc: 'Validate instrument databases against predefined and custom engineering rules.',         accent: '#22c55e', tag: 'Validation' },
  { id: 'instrument',   path: '/instrument-list', icon: FileSpreadsheet, name: 'Instrument List',          desc: 'Instrument index from IODB data with smart column filters.',                              accent: '#4f7cff', tag: 'Generator' },
  { id: 'io',           path: '/io-list',         icon: Network,         name: 'I/O List',                 desc: 'Structured I/O signal lists with per-column filtering and live preview.',               accent: '#8b5cf6', tag: 'Generator' },
  { id: 'datasheet',    path: '/datasheet',       icon: FileText,        name: 'Data Sheet',               desc: 'Smart datasheet wizard - IODB-assisted, AI spec extraction, approval workflow.',         accent: '#f59e0b', tag: 'Generator' },
  { id: 'cable',        path: '/cable-schedule',  icon: Cable,           name: 'Cable Schedule',           desc: 'Cable schedule, drum, gland and lug quantities - or the complete package from one IODB.', accent: '#f43f5e', tag: 'Generator' },
  { id: 'loop',         path: '/loop-wiring',     icon: GitBranch,       name: 'Loop Wiring',              desc: 'Loop drawings from the I/O Assignment using the 42 approved typicals.',                 accent: '#eab308', tag: 'Generator' },
  { id: 'cover',        path: '/cover-sheet',     icon: Layers,          name: 'Cover Sheet',              desc: 'Cover sheets with WABAG revision control and a connected document register.',          accent: '#14b8a6', tag: 'Documents' },
  { id: 'tbe',          path: '/tbe',             icon: ShoppingCart,    name: 'Vendor Analysis & TBE',    desc: 'Compare vendor offers and generate technical bid evaluations.',                          accent: '#0ea5e9', tag: 'Procurement' },
  { id: 'process-data', path: '/process-data',    icon: ClipboardList,   name: 'Process Data Requisition', desc: 'Request process data from Process Engineering for selected instrument types.',          accent: '#06b6d4', tag: 'Generator' },
];

const FLOW = [
  { label: 'IODB', sub: 'Source of truth', icon: Database, color: '#22d3ee', path: '/validator' },
  { label: 'Validate', sub: 'Rules engine', icon: CheckCircle2, color: '#22c55e', path: '/validator' },
  { label: 'Lists', sub: 'Instrument · I/O', icon: FileSpreadsheet, color: '#4f7cff', path: '/instrument-list' },
  { label: 'Cables', sub: 'Gland · lug · drum', icon: Cable, color: '#f43f5e', path: '/cable-schedule' },
  { label: 'Loops', sub: '42 typicals', icon: GitBranch, color: '#eab308', path: '/loop-wiring' },
  { label: 'Issue', sub: 'Cover sheet', icon: Layers, color: '#14b8a6', path: '/cover-sheet' },
];

/* ── Animated counter ─────────────────────────────────────────────────────── */
function Counter({ to, suffix = '' }: { to: number; suffix?: string }) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    let start: number | null = null;
    const duration = 1400;
    function step(ts: number) {
      if (!start) start = ts;
      const p = Math.min((ts - start) / duration, 1);
      setVal(Math.round((1 - Math.pow(1 - p, 4)) * to));
      if (p < 1) requestAnimationFrame(step);
    }
    const id = requestAnimationFrame(step);
    return () => cancelAnimationFrame(id);
  }, [to]);
  return <>{val}{suffix}</>;
}

/* ── 3D tilt toward the cursor ────────────────────────────────────────────── */
function useTilt<T extends HTMLElement>(max = 7) {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const move = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width - 0.5, py = (e.clientY - r.top) / r.height - 0.5;
      el.style.transition = 'transform .18s cubic-bezier(.16,1,.3,1), box-shadow .6s';
      el.style.transform = `perspective(900px) rotateX(${(-py * max).toFixed(2)}deg) rotateY(${(px * max).toFixed(2)}deg) translateY(-6px)`;
    };
    const leave = () => { el.style.transition = ''; el.style.transform = ''; };
    el.addEventListener('pointermove', move);
    el.addEventListener('pointerleave', leave);
    return () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerleave', leave); };
  }, [max]);
  return ref;
}

function greeting(d: Date): string {
  const h = d.getHours();
  return h < 5 ? 'Working late' : h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

const openPalette = () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true, ctrlKey: true }));

/* ── Module card ──────────────────────────────────────────────────────────── */
function ModuleCard({ mod, delay }: { mod: typeof modules[0]; delay: number }) {
  const Icon = mod.icon;
  const ref = useTilt<HTMLDivElement>();
  return (
    <Link to={mod.path} className="block group reveal" style={{ '--d': `${delay}ms` } as React.CSSProperties}>
      <div ref={ref} className="module-card h-full p-6 flex flex-col" style={{ minHeight: 214 }}>
        <div className="flex items-start justify-between mb-6">
          <div className="w-[52px] h-[52px] rounded-[16px] flex items-center justify-center flex-shrink-0 transition-transform duration-700 group-hover:scale-110"
            style={{ background: `linear-gradient(150deg, color-mix(in srgb, ${mod.accent} 85%, #fff), ${mod.accent} 45%, color-mix(in srgb, ${mod.accent} 65%, #000))`,
                     boxShadow: `inset 0 1px 0 rgba(255,255,255,.35), 0 14px 26px -12px ${mod.accent}`, transitionTimingFunction: 'var(--pop)' }}>
            <Icon className="text-white" style={{ width: 24, height: 24 }} strokeWidth={2} />
          </div>
          <span className="text-[11px] font-semibold px-2.5 py-1 rounded-full" style={{ color: 'var(--t1)', background: 'color-mix(in srgb, var(--t0) 5%, transparent)' }}>{mod.tag}</span>
        </div>
        <h3 className="text-[19px] font-semibold mb-1.5 leading-snug" style={{ color: 'var(--t0)', letterSpacing: '-0.028em' }}>{mod.name}</h3>
        <p className="text-[14px] leading-relaxed flex-1" style={{ color: 'var(--t1)' }}>{mod.desc}</p>
        <div className="flex items-center gap-1.5 text-[14px] font-semibold mt-5" style={{ color: mod.accent }}>
          <span className="transition-all duration-500 opacity-70 group-hover:opacity-100">Open</span>
          <ArrowRight className="w-4 h-4 transition-transform duration-500 group-hover:translate-x-1.5" style={{ transitionTimingFunction: 'var(--spring)' }} />
        </div>
      </div>
    </Link>
  );
}

/* ── Page ─────────────────────────────────────────────────────────────────── */
export default function DashboardPage() {
  const { user } = useAuth();
  const root = useReveal<HTMLDivElement>();
  const [now, setNow] = useState(new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 30_000); return () => clearInterval(t); }, []);
  const name = (user as any)?.employee_name || user?.username || 'Engineer';

  const stats = [
    { label: 'Modules', val: modules.length, suffix: '' },
    { label: 'Loop typicals', val: 42, suffix: '' },
    { label: 'Auto-generators', val: 6, suffix: '' },
    { label: 'Uptime', val: 100, suffix: '%' },
  ];

  return (
    <div ref={root} className="space-y-6">
      {/* ── Bento row ── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Hero */}
        <section className="lg:col-span-8 relative overflow-hidden spot reveal in" style={{ borderRadius: 32, background: 'var(--card)', border: '1px solid var(--b1)', boxShadow: 'var(--shadow-2)', minHeight: 420 }}>
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute -top-40 -left-32 w-[38rem] h-[38rem] rounded-full blur-3xl mesh-blob-a" style={{ background: 'var(--hero-a)' }} />
            <div className="absolute -bottom-48 right-[-6rem] w-[34rem] h-[34rem] rounded-full blur-3xl mesh-blob-b" style={{ background: 'var(--hero-b)' }} />
            <div className="absolute inset-0 dot-grid opacity-60" style={{ maskImage: 'radial-gradient(ellipse at 75% 30%, #000 0%, transparent 65%)', WebkitMaskImage: 'radial-gradient(ellipse at 75% 30%, #000 0%, transparent 65%)' }} />
          </div>
          <div className="relative h-full flex flex-col justify-between px-10 pt-11 pb-10">
            <div>
              <p className="eyebrow flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--ok)' }} />
                {now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</p>
              <h1 className="mt-5 font-bold" style={{ fontFamily: 'var(--font-display)', color: 'var(--t0)', letterSpacing: '-0.05em', lineHeight: 0.98, fontSize: 'clamp(42px, 5.4vw, 74px)' }}>
                {greeting(now)},<br /><span className="text-grad">{name}.</span>
              </h1>
              <p className="mt-5 max-w-lg" style={{ color: 'var(--t1)', fontSize: 19, lineHeight: 1.45, letterSpacing: '-0.012em' }}>
                Instrumentation documents, engineered end to end - from one IODB to issued drawings.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3 mt-9">
              <Link to="/cable-schedule" className="btn btn-primary px-6 py-3 text-[15px]">Open Cable Schedule <ArrowRight className="w-4 h-4" /></Link>
              <button onClick={openPalette} className="btn btn-secondary px-5 py-3 text-[15px]"><Search className="w-4 h-4" />Search everything
                <span className="ml-1 text-[12px] font-semibold px-1.5 py-0.5 rounded-md" style={{ background: 'var(--s2)', color: 'var(--t2)' }}>⌘K</span></button>
            </div>
          </div>
        </section>

        {/* Right column */}
        <div className="lg:col-span-4 grid gap-6">
          <section className="spot reveal grid grid-cols-2" style={{ '--d': '90ms', borderRadius: 28, background: 'var(--card)', border: '1px solid var(--b1)', boxShadow: 'var(--shadow-1)' } as React.CSSProperties}>
            {stats.map((s, i) => (
              <div key={s.label} className="p-6" style={{ borderRight: i % 2 === 0 ? '1px solid var(--b1)' : 'none', borderBottom: i < 2 ? '1px solid var(--b1)' : 'none' }}>
                <div className="font-bold leading-none" style={{ fontFamily: 'var(--font-display)', fontSize: 40, letterSpacing: '-0.05em', color: 'var(--t0)' }}>
                  <Counter to={s.val} suffix={s.suffix} />
                </div>
                <p className="text-[12.5px] mt-2" style={{ color: 'var(--t1)' }}>{s.label}</p>
              </div>
            ))}
          </section>

          <Link to="/smart-datasheet" className="block group reveal" style={{ '--d': '180ms' } as React.CSSProperties}>
            <section className="relative overflow-hidden h-full transition-transform duration-700 group-hover:-translate-y-1"
              style={{ borderRadius: 28, background: 'var(--tile-bg)', boxShadow: 'var(--shadow-2)', minHeight: 196, transitionTimingFunction: 'var(--spring)' }}>
              <div className="absolute -top-20 -right-20 w-72 h-72 rounded-full blur-3xl opacity-80 transition-opacity duration-700 group-hover:opacity-100" style={{ background: 'rgba(168,85,247,.45)' }} />
              <div className="absolute -bottom-24 -left-10 w-64 h-64 rounded-full blur-3xl" style={{ background: 'rgba(34,211,238,.28)' }} />
              <div className="relative p-6 h-full flex flex-col">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1.5 text-[12px] font-semibold" style={{ color: '#fcd34d' }}><Sparkles className="w-3.5 h-3.5" />AI · Featured</span>
                  <span className="w-9 h-9 rounded-full flex items-center justify-center transition-transform duration-500 group-hover:rotate-45" style={{ background: 'rgba(255,255,255,.1)' }}>
                    <ArrowUpRight className="w-4 h-4 text-white" />
                  </span>
                </div>
                <div className="mt-auto pt-6">
                  <ScanSearch className="w-8 h-8 mb-3" style={{ color: '#fff' }} strokeWidth={1.6} />
                  <h3 className="font-bold" style={{ fontFamily: 'var(--font-display)', fontSize: 26, letterSpacing: '-0.04em', color: 'var(--tile-fg)', lineHeight: 1.05 }}>Smart Spec Extraction</h3>
                  <p className="text-[14px] mt-1.5" style={{ color: 'var(--tile-fg2)' }}>Tender PDFs in, pre-filled datasheets out.</p>
                </div>
              </div>
            </section>
          </Link>
        </div>
      </div>

      {/* ── Signal flow ── */}
      <section className="spot reveal relative overflow-hidden" style={{ borderRadius: 28, background: 'var(--card)', border: '1px solid var(--b1)', boxShadow: 'var(--shadow-1)' }}>
        <div className="px-8 pt-7 flex flex-wrap items-end justify-between gap-2">
          <div>
            <p className="eyebrow">The iEZ flow</p>
            <h2 className="mt-1.5 font-bold" style={{ fontFamily: 'var(--font-display)', fontSize: 26, letterSpacing: '-0.04em', color: 'var(--t0)' }}>One IODB. Every document.</h2>
          </div>
          <p className="text-[13px]" style={{ color: 'var(--t2)' }}>Click a stage to jump in</p>
        </div>
        <div className="px-8 pb-8 pt-7 overflow-x-auto">
          <div className="flex items-center min-w-[760px]">
            {FLOW.map((f, i) => {
              const Icon = f.icon;
              return (
                <div key={f.label} className="flex items-center flex-1 last:flex-none">
                  <Link to={f.path} className="group flex flex-col items-center text-center w-[118px] flex-shrink-0">
                    <span className="relative w-14 h-14 rounded-[18px] flex items-center justify-center transition-transform duration-500 group-hover:-translate-y-1 group-hover:scale-105"
                      style={{ background: `linear-gradient(150deg, color-mix(in srgb, ${f.color} 85%, #fff), ${f.color} 50%, color-mix(in srgb, ${f.color} 65%, #000))`,
                               boxShadow: `inset 0 1px 0 rgba(255,255,255,.35), 0 16px 30px -14px ${f.color}`, transitionTimingFunction: 'var(--pop)' }}>
                      <span className="absolute inset-0 rounded-[18px]" style={{ boxShadow: `0 0 0 6px color-mix(in srgb, ${f.color} 14%, transparent)`, animation: `breathe 3s ${i * 0.35}s ease-in-out infinite` }} />
                      <Icon className="w-6 h-6 text-white relative" />
                    </span>
                    <span className="mt-3 text-[14px] font-semibold" style={{ color: 'var(--t0)', letterSpacing: '-0.02em' }}>{f.label}</span>
                    <span className="text-[12px]" style={{ color: 'var(--t2)' }}>{f.sub}</span>
                  </Link>
                  {i < FLOW.length - 1 && (
                    <svg className="flex-1 w-0 min-w-[24px] h-3 -mt-12 mx-1" preserveAspectRatio="none" viewBox="0 0 100 4" aria-hidden>
                      <defs>
                        <linearGradient id={`fg${i}`} x1="0" x2="1"><stop offset="0" stopColor={f.color} /><stop offset="1" stopColor={FLOW[i + 1].color} /></linearGradient>
                      </defs>
                      <line x1="0" y1="2" x2="100" y2="2" stroke="var(--b2)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
                      <line x1="0" y1="2" x2="100" y2="2" stroke={`url(#fg${i})`} strokeWidth="2.5" strokeLinecap="round" strokeDasharray="6 14" vectorEffect="non-scaling-stroke"
                        style={{ animation: `flow 1.${4 + i}s linear infinite` }} />
                    </svg>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Modules ── */}
      <section className="pt-8">
        <div className="flex items-end justify-between mb-6 reveal">
          <div>
            <p className="eyebrow">Engineering modules</p>
            <h2 className="mt-1.5 font-bold" style={{ fontFamily: 'var(--font-display)', fontSize: 34, letterSpacing: '-0.045em', color: 'var(--t0)' }}>Every tool. One place.</h2>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {modules.map((mod, i) => <ModuleCard key={mod.id} mod={mod} delay={(i % 3) * 90} />)}
        </div>
      </section>

      <p className="text-center text-[12px] pt-6 pb-2" style={{ color: 'var(--t2)' }}>
        iEZ Platform · Developed for VA TECH WABAG · Built by Akash Balaji · v3.1
      </p>
    </div>
  );
}
