import { NavLink, useLocation } from 'react-router-dom';
import {
  Home, CheckCircle2, FileSpreadsheet, Network,
  FileText, Cable, GitBranch, Layers, ScanSearch, Sparkles,
  Droplets,
} from 'lucide-react';
import clsx from 'clsx';

interface SidebarProps { isOpen: boolean; }

const navSections = [
  {
    label: 'Overview',
    items: [{ path: '/', icon: Home, label: 'Dashboard', exact: true }],
  },
  {
    label: 'Validation',
    items: [{ path: '/validator', icon: CheckCircle2, label: 'IODB Validator' }],
  },
  {
    label: 'Generators',
    items: [
      { path: '/instrument-list', icon: FileSpreadsheet, label: 'Instrument List' },
      { path: '/io-list',         icon: Network,         label: 'I/O List' },
      { path: '/datasheet',       icon: FileText,        label: 'Data Sheet' },
      { path: '/cable-schedule',  icon: Cable,           label: 'Cable Schedule' },
      { path: '/loop-wiring',     icon: GitBranch,       label: 'Loop Wiring' },
    ],
  },
  {
    label: 'Document Control',
    items: [{ path: '/cover-sheet', icon: Layers, label: 'Cover Sheet' }],
  },
  {
    label: 'Smart AI',
    items: [{ path: '/smart-datasheet', icon: ScanSearch, label: 'Spec Extraction' }],
    highlight: true,
  },
];

export default function Sidebar({ isOpen }: SidebarProps) {
  const location = useLocation();

  return (
    <aside
      className={clsx(
        'fixed left-0 h-[calc(100vh-57px)] transition-all duration-300 z-40 overflow-hidden flex flex-col',
        isOpen ? 'w-64' : 'w-0 -translate-x-full'
      )}
      style={{
        top: '57px',
        background: 'linear-gradient(180deg, #061428 0%, #020d1a 100%)',
        borderRight: '1px solid rgba(14,165,233,0.1)',
      }}
    >
      {/* Animated top accent */}
      <div
        className="absolute top-0 left-0 right-0 h-px animate-water-flow"
        style={{ background: 'linear-gradient(90deg, transparent, rgba(14,165,233,0.4), transparent)', backgroundSize: '200% 100%' }}
      />

      {/* Subtle dot grid */}
      <div className="absolute inset-0 dot-grid opacity-30 pointer-events-none" />

      <div className="relative flex-1 overflow-y-auto py-4 px-3">
        {navSections.map((section, si) => (
          <div key={section.label} className={clsx('mb-5', si > 0 && 'border-t pt-4')} style={si > 0 ? { borderColor: 'rgba(14,165,233,0.08)' } : {}}>
            {/* Section label */}
            <div className="flex items-center gap-1.5 mb-2 px-2">
              {section.highlight && <Sparkles className="w-3 h-3 text-amber-400 animate-data-pulse" />}
              <h2
                className={clsx(
                  'text-[10px] font-bold uppercase tracking-[0.12em]',
                  section.highlight ? 'text-amber-400' : ''
                )}
                style={!section.highlight ? { color: 'rgba(125,211,252,0.4)' } : {}}
              >
                {section.label}
              </h2>
            </div>

            <nav className="space-y-0.5">
              {section.items.map((item) => {
                const Icon = item.icon;
                void ('exact' in item && item.exact
                  ? location.pathname === item.path
                  : location.pathname.startsWith(item.path) && item.path !== '/');

                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={'exact' in item ? item.exact : false}
                    className="flex items-center gap-3 px-2 py-2.5 rounded-xl transition-all duration-200 text-sm group relative overflow-hidden"
                    style={({ isActive: navActive }) => {
                      const active = navActive;
                      return {
                        background: active ? 'rgba(14,165,233,0.12)' : 'transparent',
                        border: active ? '1px solid rgba(14,165,233,0.22)' : '1px solid transparent',
                        color: active ? '#7dd3fc' : 'rgba(147,197,253,0.55)',
                      };
                    }}
                    onMouseEnter={e => {
                      if (!e.currentTarget.style.background.includes('0.12')) {
                        e.currentTarget.style.background = 'rgba(14,165,233,0.06)';
                        e.currentTarget.style.color = '#93c5fd';
                      }
                    }}
                    onMouseLeave={e => {
                      if (!e.currentTarget.style.background.includes('0.12')) {
                        e.currentTarget.style.background = 'transparent';
                        e.currentTarget.style.color = 'rgba(147,197,253,0.55)';
                      }
                    }}
                  >
                    {({ isActive: navActive }) => (
                      <>
                        {navActive && (
                          <div
                            className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-r-full"
                            style={{ background: 'linear-gradient(180deg, #38bdf8, #0ea5e9)' }}
                          />
                        )}
                        <div
                          className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 transition-all duration-200"
                          style={{
                            background: navActive
                              ? 'rgba(14,165,233,0.2)'
                              : 'rgba(255,255,255,0.04)',
                          }}
                        >
                          <Icon className="w-3.5 h-3.5" />
                        </div>
                        <span className="font-medium text-xs">{item.label}</span>
                        {navActive && (
                          <div className="ml-auto w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
                        )}
                        {section.highlight && !navActive && (
                          <div className="ml-auto w-1.5 h-1.5 rounded-full bg-amber-400/60" />
                        )}
                      </>
                    )}
                  </NavLink>
                );
              })}
            </nav>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="p-3 flex-shrink-0" style={{ borderTop: '1px solid rgba(14,165,233,0.08)' }}>
        <div
          className="px-3 py-2.5 rounded-xl flex items-center gap-2"
          style={{ background: 'rgba(14,165,233,0.06)', border: '1px solid rgba(14,165,233,0.1)' }}
        >
          <Droplets className="w-3.5 h-3.5 text-sky-400 flex-shrink-0" />
          <div>
            <p className="text-[10px] font-semibold text-sky-300/70">iEZ Platform</p>
            <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>WABAG · v2.0 · AI-Powered</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
