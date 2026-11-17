import { Link } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import {
  CheckCircle2, FileSpreadsheet, Cable, FileText, Network,
  GitBranch, Layers, ArrowRight, ArrowUpRight,
  ScanSearch, Sparkles, Gauge, Zap, BarChart3,
  ShoppingCart, ClipboardList,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useReveal } from '@/hooks/useReveal';

/* ── Module definitions (iOS system colours) ─────────────────────────────── */
const modules = [
  { id: 'validator',   path: '/validator',       icon: CheckCircle2,  name: 'IODB Validator',    desc: 'Validate instrument databases against predefined and custom engineering rules.', accent: '#34c759', tag: 'Validation' },
  { id: 'instrument',  path: '/instrument-list',  icon: FileSpreadsheet,name: 'Instrument List',  desc: 'Generate instrument lists from IODB data with smart column filters.',            accent: '#0a84ff', tag: 'Generator'  },
  { id: 'io',          path: '/io-list',           icon: Network,       name: 'I/O List',          desc: 'Create structured I/O signal lists with per-column filtering and live preview.', accent: '#af52de', tag: 'Generator'  },
  { id: 'datasheet',   path: '/datasheet',         icon: FileText,      name: 'Data Sheet',        desc: 'Generate technical datasheets per tag with intelligent column matching.',          accent: '#ff9f0a', tag: 'Generator'  },
  { id: 'cover',       path: '/cover-sheet',       icon: Layers,        name: 'Cover Sheet',       desc: 'Build cover sheets with custom branding and WABAG revision control.',              accent: '#00c7be', tag: 'Documents'  },
  { id: 'cable',       path: '/cable-schedule',    icon: Cable,         name: 'Cable Schedule',    desc: 'Create cable schedules, gland and lug quantities from field instrument data.',     accent: '#ff453a', tag: 'Generator'  },
  { id: 'loop',        path: '/loop-wiring',       icon: GitBranch,     name: 'Loop Wiring',       desc: 'Generate loop wiring drawings from the I/O Assignment using the 42 approved typicals.', accent: '#ffcc00', tag: 'Generator'  },
  { id: 'tbe',         path: '/tbe',               icon: ShoppingCart,  name: 'Vendor Analysis & TBE', desc: 'Compare vendor offers and generate technical bid evaluations.',              accent: '#32ade6', tag: 'Procurement' },
  { id: 'process-data', path: '/process-data',     icon: ClipboardList, name: 'Process Data Requisition', desc: 'Request process data from Process Engineering for selected instrument types.', accent: '#30b0c7', tag: 'Generator' },
];

/* ── Animated counter ─────────────────────────────────────────────────────── */
function Counter({ to, suffix = '' }: { to: number; suffix?: string }) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    let start: number | null = null;
    const duration = 900;
    function step(ts: number) {
      if (!start) start = ts;
      const p = Math.min((ts - start) / duration, 1);
      setVal(Math.round((1 - Math.pow(1 - p, 3)) * to));
      if (p < 1) requestAnimationFrame(step);
    }
    const id = requestAnimationFrame(step);
    return () => cancelAnimationFrame(id);
  }, [to]);
  return <>{val}{suffix}</>;
}

/* ── Mouse-tracking glow hook ─────────────────────────────────────────────── */
function useMouseGlow<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const move = (e: MouseEvent) => {
      const r = el.getBoundingClientRect();
      el.style.setProperty('--mx', `${e.clientX - r.left}px`);
      el.style.setProperty('--my', `${e.clientY - r.top}px`);
    };
    el.addEventListener('mousemove', move);
    return () => el.removeEventListener('mousemove', move);
  }, []);
  return ref;
}

/* ── Module card ──────────────────────────────────────────────────────────── */
function ModuleCard({ mod, delay }: { mod: typeof modules[0]; delay: number }) {
  const Icon = mod.icon;
  const cardRef = useMouseGlow<HTMLDivElement>();

  return (
    <Link to={mod.path} className="block group reveal" style={{ '--d': `${delay}ms` } as React.CSSProperties}>
      <div ref={cardRef} className="module-card h-full p-6 flex flex-col" style={{ '--mx': '50%', '--my': '50%', minHeight: 208 } as React.CSSProperties}>
        {/* spotlight that follows the cursor */}
        <div
          className="pointer-events-none absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500"
          style={{ background: 'radial-gradient(260px circle at var(--mx) var(--my), color-mix(in srgb, var(--em) 9%, transparent) 0%, transparent 70%)' }}
        />
        <div className="relative flex items-start justify-between mb-5">
          <div
            className="w-12 h-12 rounded-[14px] flex items-center justify-center flex-shrink-0 transition-transform duration-500 group-hover:scale-110 group-hover:-rotate-3"
            style={{ background: `linear-gradient(160deg, ${mod.accent}, color-mix(in srgb, ${mod.accent} 72%, #000))`, boxShadow: `0 8px 20px -8px ${mod.accent}` }}
          >
            <Icon className="text-white" style={{ width: 23, height: 23 }} />
          </div>
          <span className="text-[11px] font-medium" style={{ color: 'var(--t2)' }}>{mod.tag}</span>
        </div>

        <h3 className="relative text-[19px] font-semibold mb-1.5 leading-snug" style={{ color: 'var(--t0)', letterSpacing: '-0.025em' }}>
          {mod.name}
        </h3>
        <p className="relative text-[14px] leading-relaxed flex-1" style={{ color: 'var(--t1)' }}>
          {mod.desc}
        </p>

        <div className="relative flex items-center gap-1 text-[14px] font-medium mt-4 transition-all duration-500 opacity-0 translate-y-1 group-hover:opacity-100 group-hover:translate-y-0" style={{ color: 'var(--em)' }}>
          Open <ArrowRight className="w-3.5 h-3.5 transition-transform duration-500 group-hover:translate-x-1" />
        </div>
      </div>
    </Link>
  );
}

/* ── Page ─────────────────────────────────────────────────────────────────── */
export default function DashboardPage() {
  const { user } = useAuth();
  const root = useReveal<HTMLDivElement>();

  const stats = [
    { label: 'Modules',  val: modules.length, suffix: '',  icon: Gauge },
    { label: 'AI tools', val: 1,   suffix: '',  icon: Sparkles },
    { label: 'Auto-generators', val: 6,   suffix: '',  icon: Zap },
    { label: 'Uptime',   val: 100, suffix: '%', icon: BarChart3 },
  ];

  return (
    <div ref={root} className="space-y-14">

      {/* ── Hero ── */}
      <section className="relative overflow-hidden" style={{ borderRadius: 32, background: 'var(--s2)', border: '1px solid var(--b1)', boxShadow: 'var(--shadow-2)' }}>
        <div className="absolute inset-0 pointer-events-none overflow-hidden">
          <div className="mesh-blob-a absolute -top-32 -left-24 w-[34rem] h-[34rem] rounded-full blur-3xl" style={{ background: 'var(--hero-a)' }} />
          <div className="mesh-blob-b absolute -bottom-40 right-0 w-[30rem] h-[30rem] rounded-full blur-3xl" style={{ background: 'var(--hero-b)' }} />
        </div>
        <div className="relative px-12 pt-16 pb-12 reveal in">
          <p className="text-[15px] font-semibold mb-4" style={{ color: 'var(--em)', letterSpacing: '-0.01em' }}>iEZ · Instrumentation Engineering EZ</p>
          <h1 className="font-bold leading-[1.02]" style={{ fontFamily: 'var(--font-display)', color: 'var(--t0)', letterSpacing: '-0.045em', fontSize: 'clamp(40px, 6vw, 68px)' }}>
            Welcome,<br /><span className="text-gradient">{user?.username || 'Engineer'}.</span>
          </h1>
          <p className="mt-5 max-w-xl" style={{ color: 'var(--t1)', fontSize: 21, lineHeight: 1.38, letterSpacing: '-0.015em' }}>
            Intelligent document automation for instrumentation teams. Every module runs on live data from your IODB.
          </p>

          <div className="mt-12 grid grid-cols-2 md:grid-cols-4 gap-y-6">
            {stats.map((s, i) => {
              const Icon = s.icon;
              return (
                <div key={s.label} className="pr-6" style={{ borderLeft: i === 0 ? 'none' : '1px solid var(--b1)', paddingLeft: i === 0 ? 0 : 24 }}>
                  <div className="font-bold leading-none" style={{ fontFamily: 'var(--font-display)', color: 'var(--t0)', fontSize: 44, letterSpacing: '-0.04em' }}>
                    <Counter to={s.val} suffix={s.suffix} />
                  </div>
                  <div className="flex items-center gap-1.5 mt-2.5 text-[13px]" style={{ color: 'var(--t1)' }}>
                    <Icon className="w-3.5 h-3.5" style={{ color: 'var(--em)' }} />{s.label}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Featured: SDIE ── */}
      <section className="reveal">
        <Link to="/smart-datasheet" className="block group">
          <div
            className="relative overflow-hidden transition-all duration-700 group-hover:-translate-y-1"
            style={{ borderRadius: 32, background: 'var(--tile-bg)', boxShadow: 'var(--shadow-2)', transitionTimingFunction: 'var(--spring)' }}
          >
            <div className="absolute -top-24 -right-16 w-[26rem] h-[26rem] rounded-full blur-3xl pointer-events-none transition-opacity duration-700 group-hover:opacity-100" style={{ background: 'var(--hero-a)', opacity: .7 }} />
            <div className="absolute -bottom-32 left-1/3 w-[22rem] h-[22rem] rounded-full blur-3xl pointer-events-none" style={{ background: 'var(--hero-b)' }} />
            <div className="relative flex flex-col md:flex-row md:items-center gap-8 px-12 py-12">
              <div className="flex-1">
                <p className="flex items-center gap-1.5 text-[13px] font-semibold mb-3" style={{ color: 'var(--gold-lt)' }}><Sparkles className="w-3.5 h-3.5" />AI-powered · Featured</p>
                <h3 className="font-bold leading-[1.05]" style={{ fontFamily: 'var(--font-display)', color: 'var(--tile-fg)', fontSize: 40, letterSpacing: '-0.04em' }}>
                  Smart Spec Extraction.
                </h3>
                <p className="mt-3 max-w-2xl" style={{ color: 'var(--tile-fg2)', fontSize: 18, lineHeight: 1.4, letterSpacing: '-0.012em' }}>
                  Upload tender PDFs. AI reads the section headings, groups specs per instrument type, and pre-fills your datasheets. Zero manual copying.
                </p>
                <div className="mt-7 inline-flex items-center gap-2 px-6 py-3 rounded-full text-[15px] font-medium text-white transition-all duration-500 group-hover:gap-3"
                  style={{ background: 'var(--em)', boxShadow: '0 10px 28px -8px var(--em-glow)' }}>
                  Launch <ArrowUpRight className="w-4 h-4" />
                </div>
              </div>
              <div className="hidden md:flex w-40 h-40 rounded-[40px] items-center justify-center flex-shrink-0 transition-transform duration-700 group-hover:scale-105 group-hover:-rotate-3"
                style={{ background: 'linear-gradient(160deg, var(--em-lt), var(--em))', boxShadow: '0 30px 60px -20px var(--em-glow)', transitionTimingFunction: 'var(--spring)' }}>
                <ScanSearch className="text-white" style={{ width: 76, height: 76 }} strokeWidth={1.5} />
              </div>
            </div>
          </div>
        </Link>
      </section>

      {/* ── Module Grid ── */}
      <section>
        <h2 className="reveal font-bold mb-6" style={{ fontFamily: 'var(--font-display)', color: 'var(--t0)', fontSize: 32, letterSpacing: '-0.035em' }}>
          Engineering modules.
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {modules.map((mod, i) => <ModuleCard key={mod.id} mod={mod} delay={(i % 3) * 90} />)}
        </div>
      </section>

      <p className="text-center text-[12px] pb-4" style={{ color: 'var(--t2)' }}>
        iEZ Platform · Developed for VA TECH WABAG · Built by Akash Balaji · v3.1
      </p>
    </div>
  );
}
