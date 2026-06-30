import { NavLink, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import {
  Home, CheckCircle2, FileSpreadsheet, Network,
  FileText, Cable, GitBranch, Layers, ScanSearch,
  Sparkles, Droplets, ShieldCheck, ClipboardCheck, BarChart2, GitMerge,
  Radio,
} from 'lucide-react';
import clsx from 'clsx';
import api from '@/services/api';
import { useAuth } from '@/context/AuthContext';

interface SidebarProps { isOpen: boolean; }

interface SidebarItem {
  path: string;
  icon: React.ElementType;
  label: string;
  exact?: boolean;
  badge?: boolean;
  allowedRoles?: string[];
}

const ADMIN_ROLES = ['Admin'];
const LEAD_ROLES  = ['Admin', 'Lead Engineer', 'Reviewer'];

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
      { path: '/cover-sheet',     icon: Layers,          label: 'Cover Sheet' },
    ],
  },
  {
    label: 'Smart AI',
    items: [{ path: '/smart-datasheet', icon: ScanSearch, label: 'Spec Extraction' }],
    ai: true,
  },
  {
    label: 'Procurement',
    items: [
      { path: '/tbe', icon: BarChart2, label: 'Vendor Analysis & TBE' },
    ],
  },
  {
    label: 'Review',
    items: [
      { path: '/idc', icon: GitMerge, label: 'Inter Discipline Check' },
    ],
  },
  {
    label: 'Admin',
    items: [
      { path: '/admin',          icon: ShieldCheck,   label: 'Admin Management', allowedRoles: ADMIN_ROLES, exact: true },
      { path: '/admin/login-activity', icon: Radio,   label: 'Login Activity',   allowedRoles: ADMIN_ROLES },
      { path: '/approval-queue', icon: ClipboardCheck, label: 'Approval Queue',  allowedRoles: LEAD_ROLES, badge: true },
    ],
  },
];

export default function Sidebar({ isOpen }: SidebarProps) {
  const location = useLocation();
  const { role } = useAuth();
  const [pendingCount, setPendingCount] = useState(0);

  useEffect(() => {
    const fetchCount = () => {
      api.get('/approvals/pending/count')
        .then(r => setPendingCount(r.data.count ?? 0))
        .catch(() => {/* ignore */});
    };
    fetchCount();
    const interval = setInterval(fetchCount, 30_000); // refresh every 30 s
    return () => clearInterval(interval);
  }, []);

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
        {sections.map((section, si) => {
          const visibleItems = (section.items as SidebarItem[]).filter(
            item => !item.allowedRoles || item.allowedRoles.includes(role)
          );
          if (visibleItems.length === 0) return null;
          return (
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
              {visibleItems.map((item) => {
                const Icon = item.icon;
                const isActive = item.exact
                  ? location.pathname === item.path
                  : (location.pathname.startsWith(item.path) && item.path !== '/');
                const showBadge = item.badge && pendingCount > 0;

                return (
                  <NavLink key={item.path} to={item.path} end={item.exact ?? false}>
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
                      {showBadge && (
                        <span className="ml-auto text-[9px] font-black px-1.5 py-0.5 rounded-full min-w-[18px] text-center"
                          style={{ background: 'rgba(245,158,11,0.15)', color: 'var(--gold)', border: '1px solid rgba(245,158,11,0.3)' }}>
                          {pendingCount > 99 ? '99+' : pendingCount}
                        </span>
                      )}
                      {!showBadge && isActive && (
                        <span className="ml-auto w-1 h-1 rounded-full" style={{ background: 'var(--em)' }} />
                      )}
                    </div>
                  </NavLink>
                );
              })}
            </nav>
          </div>
          );
        })}
      </div>

      <div className="p-2 flex-shrink-0" style={{ borderTop: '1px solid var(--b0)' }}>
        <div className="flex items-center gap-2 px-2.5 py-2 rounded-lg" style={{ background: 'var(--s1)' }}>
          <Droplets className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--em-lt)' }} />
          <div>
            <p className="text-[10px] font-semibold" style={{ color: 'var(--t1)' }}>iEZ v3.1 <span style={{ color: 'var(--gold)', fontSize: 9 }}>Under Development</span></p>
            <p className="text-[9px]" style={{ color: 'var(--t2)' }}>Built by Akash Balaji</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
