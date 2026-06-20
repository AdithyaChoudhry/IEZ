import { NavLink, useLocation } from 'react-router-dom';
import {
  Home, CheckCircle2, FileSpreadsheet, Network,
  FileText, Cable, GitBranch, Layers, ScanSearch,
  Sparkles, Droplets, ShieldCheck,
} from 'lucide-react';
import clsx from 'clsx';

interface SidebarProps { isOpen: boolean; }

const sections = [
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
    ai: true,
  },
  {
    label: 'Admin',
    items: [{ path: '/admin', icon: ShieldCheck, label: 'Admin Management' }],
  },
];

export default function Sidebar({ isOpen }: SidebarProps) {
  const location = useLocation();

  return (
    <aside
      className={clsx(
        'fixed left-0 z-40 flex flex-col overflow-hidden transition-all duration-300',
        isOpen ? 'w-56' : 'w-0 -translate-x-full'
      )}
      style={{
        top: '56px',
        height: 'calc(100vh - 56px)',
        background: 'var(--s0)',
        borderRight: '1px solid var(--b0)',
      }}
    >
      <div className="flex-1 overflow-y-auto py-3 px-2">
        {sections.map((section, si) => (
          <div
            key={section.label}
            className={clsx('mb-4', si > 0 && 'border-t pt-3')}
            style={si > 0 ? { borderColor: 'var(--b0)' } : {}}
          >
            <div className="flex items-center gap-1.5 px-2 mb-1.5">
              {section.ai && <Sparkles className="w-2.5 h-2.5" style={{ color: 'var(--gold)' }} />}
              <span
                className="text-[10px] font-semibold uppercase tracking-widest"
                style={{ color: section.ai ? 'var(--gold)' : 'var(--t2)' }}
              >
                {section.label}
              </span>
            </div>

            <nav className="space-y-0.5">
              {section.items.map((item) => {
                const Icon = item.icon;
                const isActive = 'exact' in item && item.exact
                  ? location.pathname === item.path
                  : (location.pathname.startsWith(item.path) && item.path !== '/');

                return (
                  <NavLink key={item.path} to={item.path} end={'exact' in item ? item.exact : false}>
                    <div
                      className="flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-xs font-medium transition-all duration-150 relative"
                      style={{
                        background: isActive ? 'var(--em-dim)' : 'transparent',
                        color: isActive ? 'var(--em-lt)' : 'var(--t1)',
                      }}
                      onMouseEnter={e => {
                        if (!isActive) {
                          e.currentTarget.style.background = 'var(--s2)';
                          e.currentTarget.style.color = 'var(--t0)';
                        }
                      }}
                      onMouseLeave={e => {
                        if (!isActive) {
                          e.currentTarget.style.background = 'transparent';
                          e.currentTarget.style.color = 'var(--t1)';
                        }
                      }}
                    >
                      {isActive && (
                        <span
                          className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 rounded-r-full"
                          style={{ background: 'var(--em)' }}
                        />
                      )}
                      <Icon
                        className="w-3.5 h-3.5 flex-shrink-0"
                        style={{ color: isActive ? 'var(--em)' : 'inherit', opacity: isActive ? 1 : 0.65 }}
                      />
                      <span>{item.label}</span>
                      {isActive && (
                        <span className="ml-auto w-1 h-1 rounded-full" style={{ background: 'var(--em)' }} />
                      )}
                    </div>
                  </NavLink>
                );
              })}
            </nav>
          </div>
        ))}
      </div>

      <div className="p-2 flex-shrink-0" style={{ borderTop: '1px solid var(--b0)' }}>
        <div className="flex items-center gap-2 px-2.5 py-2 rounded-lg" style={{ background: 'var(--s1)' }}>
          <Droplets className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--em-lt)' }} />
          <div>
            <p className="text-[10px] font-semibold" style={{ color: 'var(--t1)' }}>iEZ v2.0</p>
            <p className="text-[9px]" style={{ color: 'var(--t2)' }}>Akash</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
