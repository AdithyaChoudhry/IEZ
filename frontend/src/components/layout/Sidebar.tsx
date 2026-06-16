/**
 * Sidebar Navigation Component
 */
import { NavLink } from 'react-router-dom';
import {
  Home,
  CheckCircle2,
  FileSpreadsheet,
  Network,
  FileText,
  Cable,
  GitBranch,
  Layers,
  ScanSearch,
} from 'lucide-react';
import clsx from 'clsx';

interface SidebarProps {
  isOpen: boolean;
}

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
    label: 'Smart Tools',
    items: [{ path: '/smart-datasheet', icon: ScanSearch, label: 'Specification Extraction' }],
  },
];

export default function Sidebar({ isOpen }: SidebarProps) {
  return (
    <aside
      className={clsx(
        'fixed left-0 top-[61px] h-[calc(100vh-61px)] bg-white border-r border-gray-200 transition-all duration-200 z-40 overflow-y-auto',
        isOpen ? 'w-64' : 'w-0 -translate-x-full'
      )}
    >
      <div className="p-4">
        {navSections.map((section) => (
          <div key={section.label} className="mb-5">
            <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2 px-3">
              {section.label}
            </h2>
            <nav className="space-y-0.5">
              {section.items.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={'exact' in item ? item.exact : false}
                    className={({ isActive }) =>
                      clsx(
                        'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-sm',
                        isActive
                          ? 'bg-primary-600 text-white shadow-sm'
                          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                      )
                    }
                  >
                    <Icon className="w-4 h-4 flex-shrink-0" />
                    <span className="font-medium">{item.label}</span>
                  </NavLink>
                );
              })}
            </nav>
          </div>
        ))}
      </div>

      <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-100">
        <p className="text-xs text-gray-400 text-center">
          built by Akash B<br />
          Version iEz 1.0
        </p>
      </div>
    </aside>
  );
}
