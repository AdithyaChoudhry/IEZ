import { NavLink, useLocation } from 'react-router-dom';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Droplets, Sparkles } from 'lucide-react';
import api from '@/services/api';
import { useAuth } from '@/context/AuthContext';
import { visibleSections, isActive } from './nav';

interface SidebarProps {
  rail: boolean;              // collapsed to an icon rail
  mobile: boolean;            // small screen: the sidebar is an overlay drawer
  mobileOpen: boolean;
  onNavigate?: () => void;
}

export const SIDEBAR_W = 264;
export const RAIL_W = 76;

export default function Sidebar({ rail, mobile, mobileOpen, onNavigate }: SidebarProps) {
  const location = useLocation();
  const { role } = useAuth();
  const [pendingCount, setPendingCount] = useState(0);
  const navRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Record<string, HTMLAnchorElement | null>>({});
  const [ind, setInd] = useState<{ y: number; h: number; on: boolean }>({ y: 0, h: 40, on: false });
  const sections = visibleSections(role);
  const compact = rail && !mobile;

  useEffect(() => {
    const fetchCount = () => {
      api.get('/approvals/pending/count')
        .then(r => setPendingCount(r.data.count ?? 0))
        .catch(() => {/* ignore */});
    };
    fetchCount();
    const interval = setInterval(fetchCount, 30_000);
    return () => clearInterval(interval);
  }, []);

  // the active pill glides to the active item
  const measure = () => {
    const active = sections.flatMap(s => s.items).find(i => isActive(i, location.pathname));
    const el = active ? itemRefs.current[active.path] : null;
    if (!el || !navRef.current) { setInd(i => ({ ...i, on: false })); return; }
    setInd({ y: el.offsetTop, h: el.offsetHeight, on: true });
  };
  useLayoutEffect(measure, [location.pathname, role, compact]);
  useEffect(() => {
    const t = window.setTimeout(measure, 650);           // after the rail/expand width animation settles
    window.addEventListener('resize', measure);
    return () => { window.clearTimeout(t); window.removeEventListener('resize', measure); };
  });

  const hidden = mobile && !mobileOpen;
  return (
    <aside
      className={`sb glass-panel ${compact ? 'rail' : ''}`}
      style={{
        width: compact ? RAIL_W : SIDEBAR_W,
        transform: hidden ? 'translateX(calc(-100% - 24px))' : 'none',
        opacity: hidden ? 0 : 1,
        pointerEvents: hidden ? 'none' : 'auto',
      }}
      aria-label="Main navigation"
    >
      {/* Brand */}
      <div className="flex items-center gap-3 px-[18px] pt-[18px] pb-4 flex-shrink-0">
        <div className="w-10 h-10 rounded-[13px] flex items-center justify-center flex-shrink-0 relative overflow-hidden"
          style={{ background: 'var(--grad)', boxShadow: 'inset 0 1px 0 rgba(255,255,255,.35), 0 10px 22px -8px var(--em-glow)' }}>
          <Droplets className="w-5 h-5 text-white relative" />
        </div>
        <div className="sb-label min-w-0">
          <p className="text-[19px] font-bold leading-none" style={{ fontFamily: 'var(--font-display)', letterSpacing: '-0.04em', color: 'var(--t0)' }}>
            i<span className="text-grad">EZ</span>
          </p>
          <p className="text-[11px] mt-1 truncate" style={{ color: 'var(--t2)' }}>WABAG · Instrumentation</p>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex-1 overflow-y-auto px-3 pb-3" style={compact ? { overflow: 'visible' } : { overflowX: 'hidden', maskImage: 'linear-gradient(to bottom, #000 calc(100% - 28px), transparent)', WebkitMaskImage: 'linear-gradient(to bottom, #000 calc(100% - 28px), transparent)' }}>
        <div ref={navRef} className="relative">
          <span className="sb-ind" aria-hidden style={{ transform: `translateY(${ind.y}px)`, height: ind.h, opacity: ind.on ? 1 : 0, top: 0 }} />
          {sections.map((section) => (
            <div key={section.label} className="mb-3">
              <div className="sb-sec flex items-center gap-1.5 px-3 pt-2 pb-1.5 overflow-hidden">
                {section.ai && <Sparkles className="w-3 h-3 flex-shrink-0" style={{ color: 'var(--gold)' }} />}
                <span className="text-[11px] font-semibold uppercase whitespace-nowrap" style={{ letterSpacing: '.08em', color: section.ai ? 'var(--gold)' : 'var(--t2)' }}>
                  {section.label}
                </span>
              </div>
              <nav className="space-y-0.5">
                {section.items.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(item, location.pathname);
                  const showBadge = item.badge && pendingCount > 0;
                  return (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      end={item.exact ?? false}
                      ref={(el) => { itemRefs.current[item.path] = el; }}
                      className={`sb-item ${active ? 'active' : ''}`}
                      data-tip={compact ? item.label : undefined}
                      onClick={onNavigate}
                    >
                      <Icon className="ico" style={{ color: active ? '#fff' : item.color }} strokeWidth={2} />
                      <span className="sb-label flex-1 truncate">{item.label}</span>
                      {showBadge && (
                        <span className={compact ? 'absolute top-1.5 right-2 w-2 h-2 rounded-full' : 'sb-label text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[20px] text-center'}
                          style={{ background: active ? 'rgba(255,255,255,.25)' : 'var(--gold)', color: '#fff' }}>
                          {compact ? '' : pendingCount > 99 ? '99+' : pendingCount}
                        </span>
                      )}
                    </NavLink>
                  );
                })}
              </nav>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="p-3 flex-shrink-0">
        <div className="sb-foot flex items-center gap-3 px-3 py-2.5 rounded-[14px]" style={{ background: 'color-mix(in srgb, var(--t0) 4%, transparent)', border: '1px solid var(--b0)' }}
          data-tip={compact ? 'All systems operational · iEZ v3.1' : undefined}>
          <span className="dot relative flex w-2.5 h-2.5 flex-shrink-0 ml-[3px]">
            <span className="absolute inset-0 rounded-full" style={{ background: 'var(--ok)', animation: 'ping-sm 2.4s cubic-bezier(0,0,.2,1) infinite', opacity: .45 }} />
            <span className="relative w-2.5 h-2.5 rounded-full" style={{ background: 'var(--ok)' }} />
          </span>
          <div className="sb-label min-w-0">
            <p className="text-[12px] font-semibold truncate" style={{ color: 'var(--t0)' }}>All systems operational</p>
            <p className="text-[11px] truncate" style={{ color: 'var(--t2)' }}>iEZ v3.1 · <span style={{ color: 'var(--gold)' }}>Under development</span> · Akash Balaji</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
