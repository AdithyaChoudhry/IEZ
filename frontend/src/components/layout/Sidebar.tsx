import { NavLink, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import {
  Home, CheckCircle2, FileSpreadsheet, Network,
  FileText, Cable, GitBranch, Layers, ScanSearch,
  Sparkles, Droplets, ShieldCheck, ClipboardCheck, BarChart2,
  Radio, ClipboardList,
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
      // Loop Wiring (Test) is hidden from the sidebar; the /loop-test route and component are kept.
      { path: '/cover-sheet',     icon: Layers,          label: 'Cover Sheet' },
      { path: '/process-data',    icon: ClipboardList,   label: 'Process Data Requisition' },
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
      className={clsx('fixed left-0 z-40 flex flex-col overflow-hidden bar-glass')}
      style={{
        top: '56px',
        width: 244,
        height: 'calc(100vh - 56px)',
        borderRight: '1px solid var(--b1)',
        transform: isOpen ? 'none' : 'translateX(-100%)',
        opacity: isOpen ? 1 : 0,
        pointerEvents: isOpen ? 'auto' : 'none',
        transition: 'transform .55s var(--spring), opacity .35s var(--ease)',
      }}
    >
      <div className="flex-1 overflow-y-auto py-4 px-3">
        {sections.map((section) => {
          const visibleItems = (section.items as SidebarItem[]).filter(
            item => !item.allowedRoles || item.allowedRoles.includes(role)
          );
          if (visibleItems.length === 0) return null;
          return (
          <div
            key={section.label}
            className="mb-5"
          >
            <div className="flex items-center gap-1.5 px-3 mb-1.5">
              {section.ai && <Sparkles className="w-3 h-3" style={{ color: 'var(--gold)' }} />}
              <span
                className="text-[11px] font-semibold"
                style={{ color: section.ai ? 'var(--gold)' : 'var(--t2)', letterSpacing: '0.01em' }}
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
                      className="flex items-center gap-3 px-3 py-[9px] rounded-[10px] text-[13px] font-medium relative"
                      style={{
                        background: isActive ? 'var(--em)' : 'transparent',
                        color: isActive ? '#fff' : 'var(--t0)',
                        transition: 'background .25s var(--ease), color .25s var(--ease), transform .35s var(--spring)',
                        boxShadow: isActive ? '0 6px 16px -8px var(--em-glow)' : 'none',
                      }}
                      onMouseEnter={e => {
                        if (!isActive) {
                          e.currentTarget.style.background = 'var(--s3)';
                          e.currentTarget.style.transform = 'translateX(2px)';
                        }
                      }}
                      onMouseLeave={e => {
                        if (!isActive) {
                          e.currentTarget.style.background = 'transparent';
                          e.currentTarget.style.transform = 'none';
                        }
                      }}
                    >
                      <Icon
                        className="w-[17px] h-[17px] flex-shrink-0"
                        style={{ color: isActive ? '#fff' : 'var(--em)', opacity: isActive ? 1 : 0.9 }}
                      />
                      <span>{item.label}</span>
                      {showBadge && (
                        <span className="ml-auto text-[9px] font-black px-1.5 py-0.5 rounded-full min-w-[18px] text-center"
                          style={{ background: 'var(--gold)', color: '#fff' }}>
                          {pendingCount > 99 ? '99+' : pendingCount}
                        </span>
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

      <div className="p-3 flex-shrink-0" style={{ borderTop: '1px solid var(--b1)' }}>
        <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-[12px]" style={{ background: 'var(--s3)' }}>
          <Droplets className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--em)' }} />
          <div>
            <p className="text-[11px] font-semibold" style={{ color: 'var(--t0)' }}>iEZ v3.1 <span style={{ color: 'var(--gold)', fontSize: 10, fontWeight: 500 }}>Under Development</span></p>
            <p className="text-[10px]" style={{ color: 'var(--t2)' }}>Built by Akash Balaji</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
