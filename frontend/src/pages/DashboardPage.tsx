import { Link } from 'react-router-dom';
import {
  CheckCircle2, FileSpreadsheet, Cable, FileText,
  Network, GitBranch, Layers, ArrowRight,
  ScanSearch, Sparkles, Gauge, Waves,
  BarChart3, Zap, Activity,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

const featuredModule = {
  id: 'smart-datasheet',
  name: 'Smart Spec Extraction',
  shortName: 'SDIE',
  icon: ScanSearch,
  description: 'Upload tender PDFs — AI reads section headings, groups specs per instrument type, and generates pre-filled datasheets. No manual copying.',
  path: '/smart-datasheet',
  badge: 'AI-Powered',
};

const modules = [
  {
    id: 'validator',
    name: 'IODB Validator',
    icon: CheckCircle2,
    description: 'Validate Instrument & Operations Database files against predefined and custom engineering rules.',
    path: '/validator',
    accent: '#0ea5e9',
    accentBg: 'rgba(14,165,233,0.08)',
    tag: 'Validation',
  },
  {
    id: 'instrument',
    name: 'Instrument List',
    icon: FileSpreadsheet,
    description: 'Generate instrument lists from IODB data with smart column filters and export.',
    path: '/instrument-list',
    accent: '#10b981',
    accentBg: 'rgba(16,185,129,0.08)',
    tag: 'Generator',
  },
  {
    id: 'io',
    name: 'I/O List',
    icon: Network,
    description: 'Create structured I/O signal lists with per-column filtering and live preview.',
    path: '/io-list',
    accent: '#a78bfa',
    accentBg: 'rgba(167,139,250,0.08)',
    tag: 'Generator',
  },
  {
    id: 'datasheet',
    name: 'Data Sheet',
    icon: FileText,
    description: 'Generate technical datasheets per tag with intelligent column matching to SOP templates.',
    path: '/datasheet',
    accent: '#f59e0b',
    accentBg: 'rgba(245,158,11,0.08)',
    tag: 'Generator',
  },
  {
    id: 'cover',
    name: 'Cover Sheet',
    icon: Layers,
    description: 'Build document cover sheets with custom branding, revision control, and WABAG formatting.',
    path: '/cover-sheet',
    accent: '#14b8a6',
    accentBg: 'rgba(20,184,166,0.08)',
    tag: 'Documents',
  },
  {
    id: 'cable',
    name: 'Cable Schedule',
    icon: Cable,
    description: 'Create cable schedules grouped by junction box from field instrument data.',
    path: '/cable-schedule',
    accent: '#f43f5e',
    accentBg: 'rgba(244,63,94,0.08)',
    tag: 'Generator',
  },
  {
    id: 'loop',
    name: 'Loop Wiring',
    icon: GitBranch,
    description: 'Generate loop wiring diagrams automatically from input files and instrument data.',
    path: '/loop-wiring',
    accent: '#3b82f6',
    accentBg: 'rgba(59,130,246,0.08)',
    tag: 'Generator',
  },
];

const stats = [
  { label: 'Total Modules', value: '8', icon: Gauge, color: '#0ea5e9' },
  { label: 'AI-Powered Tools', value: '1', icon: Sparkles, color: '#f59e0b' },
  { label: 'Auto Generators', value: '6', icon: Zap, color: '#10b981' },
  { label: 'System Status', value: 'Live', icon: Activity, color: '#a78bfa' },
];

export default function DashboardPage() {
  const { user } = useAuth();
  const FeaturedIcon = featuredModule.icon;

  return (
    <div className="space-y-8">

      {/* ── Hero Section ── */}
      <div
        className="relative rounded-2xl overflow-hidden"
        style={{
          background: 'linear-gradient(135deg, rgba(6,20,40,0.95) 0%, rgba(10,28,56,0.9) 100%)',
          border: '1px solid rgba(14,165,233,0.18)',
        }}
      >
        {/* Background ambient elements */}
        <div className="absolute inset-0 dot-grid opacity-40 pointer-events-none" />
        <div
          className="absolute top-0 right-0 w-96 h-96 rounded-full blur-3xl pointer-events-none"
          style={{ background: 'radial-gradient(circle, rgba(14,165,233,0.12) 0%, transparent 70%)' }}
        />
        <div
          className="absolute bottom-0 left-0 w-72 h-72 rounded-full blur-3xl pointer-events-none"
          style={{ background: 'radial-gradient(circle, rgba(6,182,212,0.08) 0%, transparent 70%)' }}
        />

        <div className="relative px-8 py-10">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
            <div className="animate-slide-up">
              <div className="flex items-center gap-2 mb-3">
                <Waves className="w-4 h-4 text-sky-400" />
                <span className="text-xs font-medium tracking-widest uppercase text-sky-400/70">
                  WABAG Water Treatment · iEZ Platform
                </span>
              </div>
              <h1
                className="text-4xl font-black leading-tight mb-2"
                style={{ fontFamily: "'Space Grotesk', sans-serif" }}
              >
                <span className="text-white">Welcome back, </span>
                <span className="text-gradient">{user?.username || 'Engineer'}</span>
              </h1>
              <p className="text-base max-w-lg" style={{ color: 'rgba(147,197,253,0.7)' }}>
                Intelligent document automation for water treatment plant instrumentation.
                Select a module below to get started.
              </p>
            </div>

            {/* Stats row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4 gap-3 animate-slide-up animation-delay-200">
              {stats.map((s) => {
                const Icon = s.icon;
                return (
                  <div
                    key={s.label}
                    className="px-4 py-3 rounded-xl flex flex-col gap-1"
                    style={{
                      background: 'rgba(255,255,255,0.03)',
                      border: `1px solid ${s.color}22`,
                    }}
                  >
                    <div className="flex items-center gap-1.5">
                      <Icon className="w-3.5 h-3.5" style={{ color: s.color }} />
                      <span className="text-[10px] font-medium tracking-wide uppercase" style={{ color: `${s.color}99` }}>
                        {s.label}
                      </span>
                    </div>
                    <span className="text-2xl font-black" style={{ color: s.color, fontFamily: "'Space Grotesk', sans-serif" }}>
                      {s.value}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* ── Featured: SDIE ── */}
      <div className="animate-slide-up animation-delay-200">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles className="w-4 h-4 text-amber-400" />
          <h2 className="text-xs font-bold uppercase tracking-widest" style={{ color: 'rgba(125,211,252,0.5)' }}>
            Featured Tool
          </h2>
        </div>

        <Link to={featuredModule.path} className="block group">
          <div
            className="relative rounded-2xl overflow-hidden transition-all duration-300 group-hover:scale-[1.01]"
            style={{
              background: 'linear-gradient(135deg, rgba(14,165,233,0.12) 0%, rgba(6,182,212,0.08) 50%, rgba(59,130,246,0.1) 100%)',
              border: '1px solid rgba(14,165,233,0.3)',
            }}
          >
            <div className="absolute inset-0 dot-grid opacity-20 pointer-events-none" />
            <div
              className="absolute top-0 right-0 w-64 h-64 rounded-full blur-3xl pointer-events-none"
              style={{ background: 'radial-gradient(circle, rgba(14,165,233,0.15) 0%, transparent 70%)' }}
            />

            <div className="relative p-6 flex flex-col sm:flex-row sm:items-center gap-6">
              <div
                className="w-14 h-14 rounded-2xl flex items-center justify-center flex-shrink-0 shadow-xl"
                style={{
                  background: 'linear-gradient(135deg, #0ea5e9, #0369a1)',
                  boxShadow: '0 0 24px rgba(14,165,233,0.35)',
                }}
              >
                <FeaturedIcon className="w-7 h-7 text-white" />
              </div>

              <div className="flex-1">
                <div className="flex flex-wrap items-center gap-2 mb-1.5">
                  <h3
                    className="text-xl font-bold text-white"
                    style={{ fontFamily: "'Space Grotesk', sans-serif" }}
                  >
                    {featuredModule.name}
                  </h3>
                  <span
                    className="px-2 py-0.5 text-[10px] font-bold rounded-full tracking-wider"
                    style={{
                      background: 'rgba(245,158,11,0.15)',
                      border: '1px solid rgba(245,158,11,0.35)',
                      color: '#fbbf24',
                    }}
                  >
                    {featuredModule.badge}
                  </span>
                  <span
                    className="px-2 py-0.5 text-[10px] font-bold rounded-full tracking-wider"
                    style={{
                      background: 'rgba(14,165,233,0.12)',
                      border: '1px solid rgba(14,165,233,0.25)',
                      color: '#38bdf8',
                    }}
                  >
                    {featuredModule.shortName}
                  </span>
                </div>
                <p className="text-sm max-w-2xl" style={{ color: 'rgba(147,197,253,0.75)' }}>
                  {featuredModule.description}
                </p>
              </div>

              <div
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-semibold text-sm flex-shrink-0 transition-all duration-200 group-hover:shadow-lg"
                style={{
                  background: 'linear-gradient(135deg, #0ea5e9, #0369a1)',
                  color: 'white',
                  boxShadow: '0 4px 16px rgba(14,165,233,0.25)',
                }}
              >
                Launch
                <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </div>
            </div>
          </div>
        </Link>
      </div>

      {/* ── Engineering Modules Grid ── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <BarChart3 className="w-4 h-4 text-sky-400/60" />
          <h2 className="text-xs font-bold uppercase tracking-widest" style={{ color: 'rgba(125,211,252,0.5)' }}>
            Engineering Modules
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {modules.map((mod, i) => {
            const Icon = mod.icon;
            return (
              <Link key={mod.id} to={mod.path} className="block group">
                <div
                  className="interactive-card p-5 h-full flex flex-col animate-slide-up"
                  style={{ animationDelay: `${i * 60 + 300}ms` }}
                >
                  {/* Top accent line */}
                  <div
                    className="absolute top-0 left-0 right-0 h-0.5 rounded-t-2xl"
                    style={{ background: `linear-gradient(90deg, ${mod.accent}, transparent)` }}
                  />

                  <div className="flex items-start justify-between mb-4">
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                      style={{ background: mod.accentBg, border: `1px solid ${mod.accent}30` }}
                    >
                      <Icon className="w-5 h-5" style={{ color: mod.accent }} />
                    </div>
                    <span
                      className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                      style={{
                        background: `${mod.accent}14`,
                        color: mod.accent,
                        border: `1px solid ${mod.accent}22`,
                      }}
                    >
                      {mod.tag}
                    </span>
                  </div>

                  <h3
                    className="font-bold text-base text-sky-100 mb-2 leading-tight group-hover:text-white transition-colors"
                    style={{ fontFamily: "'Space Grotesk', sans-serif" }}
                  >
                    {mod.name}
                  </h3>
                  <p className="text-xs leading-relaxed flex-1" style={{ color: 'rgba(147,197,253,0.6)' }}>
                    {mod.description}
                  </p>

                  <div
                    className="flex items-center gap-1.5 text-xs font-semibold mt-4 opacity-0 group-hover:opacity-100 transition-all duration-200 group-hover:translate-x-1"
                    style={{ color: mod.accent }}
                  >
                    Open module <ArrowRight className="w-3.5 h-3.5" />
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      </div>

      {/* ── Footer note ── */}
      <div className="pb-2 text-center">
        <p className="text-[11px]" style={{ color: 'rgba(125,211,252,0.3)' }}>
          iEZ Platform · WABAG Water Treatment Solutions · AI-Powered Engineering Automation
        </p>
      </div>
    </div>
  );
}
