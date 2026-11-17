/**
 * Single source of truth for navigation: the sidebar, the top-bar title / breadcrumb and the ⌘K command palette all read this.
 * Hidden pages (e.g. /loop-test, IDC) are intentionally not listed - their routes still exist in App.tsx.
 */
import {
  Home, CheckCircle2, FileSpreadsheet, Network, FileText, Cable, GitBranch, Layers, ScanSearch,
  ShieldCheck, ClipboardCheck, BarChart2, Radio, ClipboardList,
} from 'lucide-react';

export interface NavItem {
  path: string;
  icon: React.ElementType;
  label: string;
  hint?: string;               // one-line description (command palette)
  keywords?: string;           // extra search words
  color: string;               // app-icon tint
  exact?: boolean;
  badge?: boolean;
  allowedRoles?: string[];
}

export interface NavSection {
  label: string;
  items: NavItem[];
  ai?: boolean;
}

export const ADMIN_ROLES = ['Admin'];
export const LEAD_ROLES = ['Admin', 'Lead Engineer', 'Reviewer'];

export const NAV_SECTIONS: NavSection[] = [
  {
    label: 'Overview',
    items: [{ path: '/', icon: Home, label: 'Dashboard', hint: 'Home - all modules at a glance', exact: true, color: '#4f7cff' }],
  },
  {
    label: 'Validation',
    items: [{ path: '/validator', icon: CheckCircle2, label: 'IODB Validator', hint: 'Check an IODB against engineering rules', keywords: 'rules check iodb', color: '#22c55e' }],
  },
  {
    label: 'Generators',
    items: [
      { path: '/instrument-list', icon: FileSpreadsheet, label: 'Instrument List', hint: 'Instrument index from the IODB', keywords: 'index', color: '#4f7cff' },
      { path: '/io-list', icon: Network, label: 'I/O List', hint: 'Signal list with filters', keywords: 'io signals', color: '#8b5cf6' },
      { path: '/datasheet', icon: FileText, label: 'Data Sheet', hint: 'Smart datasheet wizard', keywords: 'datasheet spec', color: '#f59e0b' },
      { path: '/cable-schedule', icon: Cable, label: 'Cable Schedule', hint: 'Schedule, drum, gland, lug, complete package', keywords: 'gland lug drum cable', color: '#f43f5e' },
      { path: '/loop-wiring', icon: GitBranch, label: 'Loop Wiring', hint: '42 approved typicals from the I/O Assignment', keywords: 'loop typical io assignment', color: '#eab308' },
      { path: '/cover-sheet', icon: Layers, label: 'Cover Sheet', hint: 'Cover sheets and document register', keywords: 'coversheet register', color: '#14b8a6' },
      { path: '/process-data', icon: ClipboardList, label: 'Process Data Requisition', hint: 'Request process data', keywords: 'process requisition', color: '#06b6d4' },
    ],
  },
  {
    label: 'Smart AI',
    ai: true,
    items: [{ path: '/smart-datasheet', icon: ScanSearch, label: 'Spec Extraction', hint: 'AI reads tender PDFs into datasheets', keywords: 'ai pdf ocr tender sdie', color: '#a855f7' }],
  },
  {
    label: 'Procurement',
    items: [{ path: '/tbe', icon: BarChart2, label: 'Vendor Analysis & TBE', hint: 'Technical bid evaluation', keywords: 'vendor bid tbe offer', color: '#0ea5e9' }],
  },
  {
    label: 'Admin',
    items: [
      { path: '/admin', icon: ShieldCheck, label: 'Admin Management', hint: 'Users, roles, vendors', allowedRoles: ADMIN_ROLES, exact: true, color: '#64748b' },
      { path: '/admin/login-activity', icon: Radio, label: 'Login Activity', hint: 'Who signed in, when', allowedRoles: ADMIN_ROLES, color: '#64748b' },
      { path: '/approval-queue', icon: ClipboardCheck, label: 'Approval Queue', hint: 'Requests waiting for you', allowedRoles: LEAD_ROLES, badge: true, color: '#f59e0b' },
    ],
  },
];

export function visibleSections(role: string): NavSection[] {
  return NAV_SECTIONS.map((s) => ({ ...s, items: s.items.filter((i) => !i.allowedRoles || i.allowedRoles.includes(role)) })).filter((s) => s.items.length);
}

export function isActive(item: NavItem, pathname: string): boolean {
  return item.exact ? pathname === item.path : item.path !== '/' && pathname.startsWith(item.path);
}

/** The nav item (and its section) that owns the current route - used for the top-bar title and breadcrumb. */
export function currentPage(pathname: string): { item: NavItem; section: NavSection } | null {
  for (const s of NAV_SECTIONS) {
    for (const i of s.items) {
      if (isActive(i, pathname)) return { item: i, section: s };
    }
  }
  return null;
}
