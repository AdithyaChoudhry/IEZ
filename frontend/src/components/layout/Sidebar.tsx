import { NavLink } from 'react-router-dom';
import {
  Home, CheckCircle2, FileSpreadsheet, Network,
  FileText, Cable, GitBranch, Layers, ScanSearch, Zap,
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
      { path: '/io-list', icon: Network, label: 'I/O List' },
      { path: '/datasheet', icon: FileText, label: 'Data Sheet' },
      { path: '/cable-schedule', icon: Cable, label: 'Cable Schedule' },
      { path: '/loop-wiring', icon: GitBranch, label: 'Loop Wiring' },
    ],
  },
  {
    label: 'Document Control',
    items: [{ path: '/cover-sheet', icon: Layers, label: 'Cover Sheet' }],
  },
  {
    label: 'Smart AI Tools',
    items: [{ path: '/smart-datasheet', icon: ScanSearch, label: 'Spec Extraction' }],
    highlight: true,
  },
];

export default function Sidebar({ isOpen }: SidebarProps) {
  return (
    <aside
      className={clsx(
        'fixed left-0 top-[61px] h-[calc(100vh-61px)] transition-all duration-300 z-40 overflow-hidden',
        'bg-gradient-to-b from-[#001529] via-[#002766] to-[#001d66]',
        isOpen ? 'w-64' : 'w-0 -translate-x-full'
      )}
    >
      {/* Decorative top glow */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-blue-400/40 to-transparent" />

      <div className="p-4 overflow-y-auto h-full flex flex-col">
        <div className="flex-1">
          {navSections.map((section, si) => (
            <div key={section.label} className={clsx('mb-6', si > 0 && 'border-t border-white/5 pt-4')}>
              <div className="flex items-center gap-2 mb-2 px-3">
                {section.highlight && <Zap className="w-3 h-3 text-yellow-400" />}
                <h2 className={clsx(
                  'text-[10px] font-bold uppercase tracking-widest',
                  section.highlight ? 'text-yellow-400' : 'text-blue-300/60'
                )}>
                  {section.label}
                </h2>
              </div>
              <nav className="space-y-0.5">
                {section.items.map((item) => {
                  const Icon = item.icon;
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      end={'exact' in item ? item.exact : false}
                      className={({ isActive }) => clsx(
                        'flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200 text-sm group relative overflow-hidden',
                        isActive
                          ? 'bg-gradient-to-r from-blue-500/30 to-blue-600/20 text-white shadow-lg border border-blue-400/20'
                          : 'text-blue-200/70 hover:text-white hover:bg-white/8'
                      )}
                    >
                      {({ isActive }) => (
                        <>
                          {isActive && (
                            <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-blue-400 rounded-r-full" />
                          )}
                          <div className={clsx(
                            'w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 transition-all duration-200',
                            isActive
                              ? 'bg-blue-500/40 text-blue-200'
                              : 'bg-white/5 text-blue-300/60 group-hover:bg-white/10 group-hover:text-blue-200'
                          )}>
                            <Icon className="w-3.5 h-3.5" />
                          </div>
                          <span className="font-medium text-xs">{item.label}</span>
                          {isActive && (
                            <div className="ml-auto w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
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
        <div className="border-t border-white/10 pt-4 pb-2">
          <div className="px-3 py-2 rounded-xl bg-white/5">
            <p className="text-[10px] text-blue-300/50 font-medium">iEZ Platform</p>
            <p className="text-[10px] text-blue-300/30">v2.0 · AI-Powered</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
