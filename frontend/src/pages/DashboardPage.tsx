import { Link } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import {
  CheckCircle2, FileSpreadsheet, Cable, FileText, Network,
  GitBranch, Layers, ArrowRight, ArrowUpRight,
  ScanSearch, Sparkles, Gauge, Zap, BarChart3, Radio,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

/* ── Module definitions ───────────────────────────────────────────────────── */
const modules = [
  { id: 'validator',   path: '/validator',       icon: CheckCircle2,  name: 'IODB Validator',    desc: 'Validate instrument databases against predefined and custom engineering rules.', accent: '#4ade80', tag: 'Validation' },
  { id: 'instrument',  path: '/instrument-list',  icon: FileSpreadsheet,name: 'Instrument List',  desc: 'Generate instrument lists from IODB data with smart column filters.',            accent: '#60a5fa', tag: 'Generator'  },
  { id: 'io',          path: '/io-list',           icon: Network,       name: 'I/O List',          desc: 'Create structured I/O signal lists with per-column filtering and live preview.', accent: '#a78bfa', tag: 'Generator'  },
  { id: 'datasheet',   path: '/datasheet',         icon: FileText,      name: 'Data Sheet',        desc: 'Generate technical datasheets per tag with intelligent column matching.',          accent: '#fb923c', tag: 'Generator'  },
  { id: 'cover',       path: '/cover-sheet',       icon: Layers,        name: 'Cover Sheet',       desc: 'Build cover sheets with custom branding and WABAG revision control.',              accent: '#34d399', tag: 'Documents'  },
  { id: 'cable',       path: '/cable-schedule',    icon: Cable,         name: 'Cable Schedule',    desc: 'Create cable schedules grouped by junction box from field instrument data.',       accent: '#f87171', tag: 'Generator'  },
  { id: 'loop',        path: '/loop-wiring',       icon: GitBranch,     name: 'Loop Wiring',       desc: 'Generate loop wiring diagrams automatically from input files.',                   accent: '#fbbf24', tag: 'Generator'  },
  { id: 'lt-radar',   path: '/lt-radar',           icon: Radio,         name: 'LT Non-Contact Radar', desc: 'Generate clean engineering datasheets for LT Non-Contact Radar instruments with IODB auto-fill and AI spec extraction.', accent: '#60a5fa', tag: 'Instruments' },
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
    <Link to={mod.path} className="block group">
      <div
        ref={cardRef}
        className="module-card h-full p-5 flex flex-col animate-rise"
        style={{ animationDelay: `${delay}ms`, '--mx': '50%', '--my': '50%' } as React.CSSProperties}
      >
        {/* Mouse-following inner glow */}
        <div
          className="pointer-events-none absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300"
          style={{ background: 'radial-gradient(180px circle at var(--mx) var(--my), rgba(255,255,255,0.025) 0%, transparent 70%)' }}
        />

        <div className="flex items-start justify-between mb-4">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
            style={{ background: `${mod.accent}18`, border: `1px solid ${mod.accent}30` }}
          >
            <Icon style={{ color: mod.accent, width: '17px', height: '17px' }} />
          </div>
          <span
            className="text-[10px] font-semibold px-2 py-0.5 rounded-full tracking-wide"
            style={{ background: `${mod.accent}14`, color: mod.accent, border: `1px solid ${mod.accent}28` }}
          >
            {mod.tag}
          </span>
        </div>

        <h3
          className="text-sm font-bold mb-1.5 leading-snug"
          style={{ color: 'var(--t0)', fontFamily: "'Space Grotesk', sans-serif" }}
        >
          {mod.name}
        </h3>
        <p className="text-xs leading-relaxed flex-1" style={{ color: 'var(--t1)' }}>
          {mod.desc}
        </p>

        <div
          className="flex items-center gap-1 text-xs font-semibold mt-4 transition-all duration-200 opacity-0 group-hover:opacity-100 translate-x-0 group-hover:translate-x-0.5"
          style={{ color: mod.accent }}
        >
          Open <ArrowRight className="w-3 h-3" />
        </div>
      </div>
    </Link>
  );
}

/* ── Page ─────────────────────────────────────────────────────────────────── */
export default function DashboardPage() {
  const { user } = useAuth();

  const stats = [
    { label: 'Modules',  val: 8,   suffix: '',  icon: Gauge,    color: 'var(--em)' },
    { label: 'AI Tools', val: 1,   suffix: '',  icon: Sparkles, color: 'var(--gold)' },
    { label: 'Auto-Gen', val: 6,   suffix: '',  icon: Zap,      color: 'var(--sky)' },
    { label: 'Uptime',   val: 100, suffix: '%', icon: BarChart3, color: '#4ade80' },
  ];

  return (
    <div className="space-y-8">

      {/* ── Hero ── */}
      <div
        className="relative overflow-hidden rounded-2xl animate-rise"
        style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}
      >
        {/* Animated mesh blobs — blue + amber */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="mesh-blob-a absolute -top-24 -left-24 w-80 h-80 rounded-full blur-3xl" style={{ background: 'rgba(59,130,246,0.09)' }} />
          <div className="mesh-blob-b absolute -bottom-16 right-0 w-72 h-72 rounded-full blur-3xl"  style={{ background: 'rgba(245,158,11,0.05)' }} />
          <div className="mesh-blob-c absolute top-6 right-1/3 w-48 h-48 rounded-full blur-3xl"    style={{ background: 'rgba(59,130,246,0.05)' }} />
        </div>
        <div className="absolute inset-0 dot-grid opacity-25 pointer-events-none" />

        <div className="relative px-8 py-10 flex flex-col lg:flex-row lg:items-center gap-8">
          {/* Greeting */}
          <div className="flex-1">
            <p className="text-[11px] font-semibold tracking-widest uppercase mb-3" style={{ color: 'var(--t2)' }}>
              WABAG Water Treatment · Engineering Platform
            </p>
            <h1
              className="text-4xl font-black leading-tight mb-3"
              style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)', letterSpacing: '-0.025em' }}
            >
              Welcome,{' '}
              <span className="text-gradient">{user?.username || 'Engineer'}</span>
            </h1>
            <p className="text-sm max-w-md" style={{ color: 'var(--t1)', lineHeight: '1.7' }}>
              Intelligent document automation for instrumentation teams.
              Every module runs on live data from your IODB.
            </p>
          </div>

          {/* Stat cards */}
          <div className="grid grid-cols-2 gap-3 animate-rise animation-delay-200">
            {stats.map(s => {
              const Icon = s.icon;
              return (
                <div key={s.label} className="px-4 py-3 rounded-xl" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
                  <div className="flex items-center gap-1.5 mb-2">
                    <Icon className="w-3 h-3" style={{ color: s.color }} />
                    <span className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--t2)' }}>{s.label}</span>
                  </div>
                  <span className="text-2xl font-black" style={{ fontFamily: "'Space Grotesk', sans-serif", color: s.color }}>
                    <Counter to={s.val} suffix={s.suffix} />
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Featured: SDIE ── */}
      <div>
        <p className="text-[10px] font-semibold tracking-widest uppercase mb-3 flex items-center gap-1.5" style={{ color: 'var(--t2)' }}>
          <Sparkles className="w-3 h-3" style={{ color: 'var(--gold)' }} />
          Featured · AI-Powered Tool
        </p>

        <Link to="/smart-datasheet" className="block group">
          <div
            className="relative rounded-2xl overflow-hidden transition-all duration-300 group-hover:-translate-y-1 group-hover:shadow-2xl"
            style={{ background: 'linear-gradient(135deg, rgba(59,130,246,0.08) 0%, rgba(245,158,11,0.04) 60%, var(--s2) 100%)', border: '1px solid var(--b2)' }}
          >
            <div className="absolute top-0 left-0 w-64 h-32 rounded-full blur-3xl pointer-events-none" style={{ background: 'rgba(59,130,246,0.1)' }} />
            <div className="relative flex flex-col sm:flex-row sm:items-center gap-5 p-6">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center flex-shrink-0"
                style={{ background: 'linear-gradient(135deg, var(--em), #1d4ed8)', boxShadow: '0 8px 24px rgba(59,130,246,0.25)' }}
              >
                <ScanSearch className="w-7 h-7 text-white" />
              </div>
              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2 mb-1.5">
                  <h3 className="text-lg font-bold" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)' }}>
                    Smart Spec Extraction
                  </h3>
                  <span className="px-2 py-0.5 text-[9px] font-bold rounded-full tracking-wider" style={{ background: 'var(--gold-dim)', color: 'var(--gold)', border: '1px solid rgba(245,158,11,0.2)' }}>AI · GROQ</span>
                  <span className="px-2 py-0.5 text-[9px] font-bold rounded-full tracking-wider" style={{ background: 'var(--em-dim)', color: 'var(--em-lt)', border: '1px solid rgba(16,185,129,0.2)' }}>SDIE</span>
                </div>
                <p className="text-sm max-w-2xl" style={{ color: 'var(--t1)', lineHeight: '1.65' }}>
                  Upload tender PDFs — AI reads section headings, groups specs per instrument type, and generates pre-filled datasheets. Zero manual copying.
                </p>
              </div>
              <div
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-bold text-sm flex-shrink-0 text-white transition-all duration-200"
                style={{ background: 'linear-gradient(135deg, var(--em), #1d4ed8)', boxShadow: '0 4px 14px rgba(59,130,246,0.25)' }}
              >
                Launch <ArrowUpRight className="w-4 h-4" />
              </div>
            </div>
          </div>
        </Link>
      </div>

      {/* ── Module Grid ── */}
      <div>
        <p className="text-[10px] font-semibold tracking-widest uppercase mb-4 flex items-center gap-1.5" style={{ color: 'var(--t2)' }}>
          <BarChart3 className="w-3 h-3" />
          Engineering Modules
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {modules.map((mod, i) => <ModuleCard key={mod.id} mod={mod} delay={i * 50 + 100} />)}
        </div>
      </div>

      <p className="text-center text-[11px] pb-4" style={{ color: 'var(--t2)' }}>
        iEZ Platform · WABAG Water Treatment Solutions · AI-Powered Engineering Automation
      </p>
    </div>
  );
}
