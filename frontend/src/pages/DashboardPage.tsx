import { Link } from 'react-router-dom';
import { LoopArt, Gauge } from '@/components/art/InstrumentArt';
import { useEffect, useState } from 'react';
import { ArrowRight, ArrowUpRight, Database, CheckCircle2, FileSpreadsheet, Cable, GitBranch, Layers } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useReveal } from '@/hooks/useReveal';
import { NAV_SECTIONS } from '@/components/layout/nav';

/* richer copy for the module index (navigation itself comes from nav.ts) */
const DESC: Record<string, string> = {
  '/validator': 'Validate instrument databases against predefined and custom engineering rules.',
  '/instrument-list': 'Instrument index from IODB data with smart column filters.',
  '/io-list': 'Structured I/O signal lists with per-column filtering and live preview.',
  '/datasheet': 'Datasheet wizard - IODB-assisted, AI spec extraction, engineering approval.',
  '/cable-schedule': 'Cable schedule, drum, gland and lug quantities - or the complete package from one IODB.',
  '/loop-wiring': 'Loop drawings from the I/O Assignment using the 42 approved typicals.',
  '/cover-sheet': 'Cover sheets with WABAG revision control and a connected document register.',
  '/process-data': 'Request process data from Process Engineering for selected instrument types.',
  '/smart-datasheet': 'AI reads tender PDFs by section and pre-fills datasheets per instrument type.',
  '/tbe': 'Compare vendor offers and generate technical bid evaluations.',
};

const MODULES = NAV_SECTIONS.filter((s) => !['Overview', 'Admin'].includes(s.label))
  .flatMap((s) => s.items.map((it, i) => ({ ...it, code: `${s.code}.${String(i + 1).padStart(2, '0')}`, area: s.label })));

const PATH = [
  { code: '01', label: 'IODB', sub: 'Source of truth', icon: Database, path: '/validator' },
  { code: '02', label: 'Validate', sub: 'Rules engine', icon: CheckCircle2, path: '/validator' },
  { code: '03', label: 'Lists', sub: 'Instrument · I/O', icon: FileSpreadsheet, path: '/instrument-list' },
  { code: '04', label: 'Cables', sub: 'Gland · lug · drum', icon: Cable, path: '/cable-schedule' },
  { code: '05', label: 'Loops', sub: '42 typicals', icon: GitBranch, path: '/loop-wiring' },
  { code: '06', label: 'Issue', sub: 'Cover sheet', icon: Layers, path: '/cover-sheet' },
];

function Counter({ to, suffix = '' }: { to: number; suffix?: string }) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    let start: number | null = null;
    let id = 0;
    const step = (ts: number) => {
      if (!start) start = ts;
      const p = Math.min((ts - start) / 1100, 1);
      setVal(Math.round((1 - Math.pow(1 - p, 4)) * to));
      if (p < 1) id = requestAnimationFrame(step);
    };
    id = requestAnimationFrame(step);
    return () => cancelAnimationFrame(id);
  }, [to]);
  return <>{val}{suffix}</>;
}

function greeting(d: Date): string {
  const h = d.getHours();
  return h < 5 ? 'Working late' : h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

/** Live date + time with seconds; only this component re-renders every second. */
function LiveClock() {
  const [t, setT] = useState(new Date());
  useEffect(() => {
    let id = 0;
    const tick = () => { setT(new Date()); id = window.setTimeout(tick, 1000 - (Date.now() % 1000)); };   // aligned to the second
    id = window.setTimeout(tick, 1000 - (Date.now() % 1000));
    return () => window.clearTimeout(id);
  }, []);
  const date = t.toLocaleDateString(undefined, { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase();
  const two = (n: number) => String(n).padStart(2, '0');
  const hh = two(t.getHours()), mm = two(t.getMinutes()), ss = two(t.getSeconds());
  return (
    <p className="eyebrow flex items-center gap-2" aria-label={`${date} ${hh}:${mm}:${ss}`}>
      <span className="signal live-dot">●</span>
      <span>{date}</span><span>·</span>
      <span className="clock" style={{ color: 'var(--t1)' }}>
        {hh}<span className="clock-colon">:</span>{mm}<span className="clock-colon">:</span>
        <span className="clock-sec"><span key={ss} className="clock-roll">{ss}</span></span>
      </span>
    </p>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const root = useReveal<HTMLDivElement>();
  const [now, setNow] = useState(new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 60_000); return () => clearInterval(t); }, []);
  const name = (user as any)?.employee_name || user?.username || 'Engineer';

  const figures: { label: string; val: number; suffix?: string; note: string }[] = [
    { label: 'Modules', val: MODULES.length, note: 'in one workspace' },
    { label: 'Generators', val: 6, note: 'IODB-driven outputs' },
    { label: 'Uptime', val: 100, suffix: '%', note: 'all systems operational' },
  ];

  return (
    <div ref={root}>
      {/* ── Masthead ── */}
      <section className="reveal in grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] items-center gap-6 pb-10">
        <div className="min-w-0">
          <LiveClock />
          <h1 className="mt-5 font-semibold" style={{ fontFamily: 'var(--font-display)', color: 'var(--t0)', letterSpacing: '-0.045em', lineHeight: 1.02, fontSize: 'clamp(40px, 5vw, 64px)' }}>
            <span className="line-reveal"><span style={{ animationDelay: '80ms' }}>{greeting(now)},</span></span>
            <span className="line-reveal"><span style={{ animationDelay: '200ms' }}>{name}<span className="signal">.</span></span></span>
          </h1>
          <p className="mt-5 max-w-xl text-[17px] fade-up" style={{ color: 'var(--t1)', lineHeight: 1.55, animationDelay: '360ms' }}>
            Instrumentation documents, engineered end to end - from one IODB to issued drawings.
          </p>
        </div>
        <div className="hidden lg:flex justify-center items-center fade-up" style={{ animationDelay: '220ms' }}>
          <div className="w-full max-w-[640px]"><LoopArt tag="101" controller="plc" tone={{ line: 'var(--t1)', text: 'var(--t2)' }} /></div>
        </div>
      </section>

      {/* ── Figures ── */}
      <section className="reveal grid grid-cols-1 sm:grid-cols-3" style={{ borderTop: '1px solid var(--b2)', borderBottom: '1px solid var(--b1)' }}>
        {figures.map((f, i) => (
          <div key={f.label} className="relative py-7 pr-6 fade-up" style={{ paddingLeft: i === 0 ? 0 : 24, borderLeft: i === 0 ? 'none' : '1px solid var(--b1)', animationDelay: `${420 + i * 90}ms` }}>
            {f.label === 'Uptime' && <div className="absolute right-2 top-1/2 -translate-y-1/2"><Gauge value={f.val} size={78} label="Uptime %" /></div>}
            <p className="eyebrow">{f.label}</p>
            <p className="mt-3 font-semibold leading-none" style={{ fontFamily: 'var(--font-display)', fontSize: 46, letterSpacing: '-0.045em', color: 'var(--t0)' }}>
              <Counter to={f.val} suffix={f.suffix} />
            </p>
            <p className="mt-2 text-[13px]" style={{ color: 'var(--t2)' }}>{f.note}</p>
          </div>
        ))}
      </section>

      {/* ── Signal path + AI ── */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 mt-10">
        <section className="xl:col-span-8 reveal ui-card p-7" style={{ '--d': '60ms' } as React.CSSProperties}>
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="eyebrow">Signal path</p>
              <h2 className="mt-2 text-[24px] font-semibold" style={{ color: 'var(--t0)', letterSpacing: '-0.03em' }}>One IODB. Every document.</h2>
            </div>
            <p className="hidden md:block text-[13px]" style={{ color: 'var(--t2)' }}>Select a stage to open it</p>
          </div>
          <div className="mt-9 overflow-x-auto pb-1">
            <div className="relative min-w-[640px] grid grid-cols-6">
              {/* the line and the travelling signal */}
              <div className="absolute left-[8.33%] right-[8.33%] top-[21px] h-px" style={{ background: 'var(--b3)' }}>
                <span className="absolute -top-[3px] w-[7px] h-[7px] rounded-full" style={{ background: 'var(--em)', boxShadow: '0 0 0 4px var(--em-dim)', animation: 'travel 5.5s cubic-bezier(.45,0,.55,1) infinite' }} />
              </div>
              {PATH.map((p) => {
                const Icon = p.icon;
                return (
                  <Link key={p.code} to={p.path} className="relative group flex flex-col items-center text-center">
                    <span className="w-[43px] h-[43px] rounded-[10px] flex items-center justify-center transition-colors duration-200 group-hover:!bg-[var(--ink)] group-hover:!text-[var(--ink-fg)]"
                      style={{ background: 'var(--s2)', border: '1px solid var(--b3)', color: 'var(--t0)' }}>
                      <Icon className="w-[18px] h-[18px]" strokeWidth={1.8} />
                    </span>
                    <span className="mono text-[10.5px] mt-3" style={{ color: 'var(--t2)' }}>{p.code}</span>
                    <span className="text-[14px] font-semibold mt-0.5" style={{ color: 'var(--t0)' }}>{p.label}</span>
                    <span className="text-[12px]" style={{ color: 'var(--t2)' }}>{p.sub}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        </section>

        <Link to="/smart-datasheet" className="xl:col-span-4 block group reveal" style={{ '--d': '120ms' } as React.CSSProperties}>
          <section className="h-full p-7 flex flex-col transition-transform duration-300 group-hover:-translate-y-0.5"
            style={{ background: 'var(--tile-bg)', color: 'var(--tile-fg)', borderRadius: 'var(--r-xl)', boxShadow: 'var(--shadow-2)', minHeight: 240 }}>
            <div className="flex items-center justify-between">
              <p className="mono text-[11px] tracking-[.1em]" style={{ color: 'var(--tile-fg2)' }}>03 · SMART AI</p>
              <span className="flex items-center gap-1.5 mono text-[11px]" style={{ color: 'var(--em)' }}>
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--em)', animation: 'blink 2s ease-in-out infinite' }} />LIVE
              </span>
            </div>
            <h3 className="mt-auto text-[28px] font-semibold" style={{ letterSpacing: '-0.035em', lineHeight: 1.1 }}>Spec Extraction</h3>
            <p className="mt-2 text-[14px]" style={{ color: 'var(--tile-fg2)', lineHeight: 1.5 }}>Tender PDFs in. Pre-filled datasheets out - grouped per instrument type.</p>
            <span className="mt-5 inline-flex items-center gap-1.5 text-[14px] font-medium">
              Open <ArrowUpRight className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </span>
          </section>
        </Link>
      </div>

      {/* ── Module index ── */}
      <section className="mt-16">
        <div className="flex items-end justify-between mb-6 reveal">
          <div>
            <p className="eyebrow">Index</p>
            <h2 className="mt-2 text-[30px] font-semibold" style={{ color: 'var(--t0)', letterSpacing: '-0.035em' }}>Modules</h2>
          </div>
          <p className="mono text-[12px]" style={{ color: 'var(--t2)' }}>{String(MODULES.length).padStart(2, '0')} TOOLS</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {MODULES.map((m, i) => {
            const Icon = m.icon;
            return (
              <Link key={m.path} to={m.path} className="reveal block group" style={{ '--d': `${(i % 3) * 70}ms` } as React.CSSProperties}>
                <div className="module-card h-full p-6 flex flex-col" style={{ minHeight: 196 }}>
                  <span className="bar" />
                  <div className="flex items-center justify-between">
                    <span className="w-10 h-10 rounded-[9px] flex items-center justify-center transition-colors duration-200 group-hover:!bg-[var(--ink)] group-hover:!text-[var(--ink-fg)]"
                      style={{ background: 'var(--s3)', color: 'var(--t0)' }}>
                      <Icon className="w-[18px] h-[18px]" strokeWidth={1.8} />
                    </span>
                    <span className="mono text-[11px]" style={{ color: 'var(--t2)' }}>{m.code} · {m.area.toUpperCase()}</span>
                  </div>
                  <h3 className="mt-6 text-[18px] font-semibold" style={{ color: 'var(--t0)', letterSpacing: '-0.02em' }}>{m.label}</h3>
                  <p className="mt-1.5 text-[14px] leading-relaxed flex-1" style={{ color: 'var(--t1)' }}>{DESC[m.path] || m.hint}</p>
                  <span className="mt-5 inline-flex items-center gap-1.5 text-[13.5px] font-medium" style={{ color: 'var(--t0)' }}>
                    Open <ArrowRight className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-1" />
                  </span>
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      <p className="mono text-center text-[11px] mt-16" style={{ color: 'var(--t2)' }}>
        IEZ PLATFORM · VA TECH WABAG · BUILT BY AKASH BALAJI · V3.1
      </p>
    </div>
  );
}
