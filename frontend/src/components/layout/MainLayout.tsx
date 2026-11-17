import { Outlet, useLocation } from 'react-router-dom';
import { useCallback, useEffect, useState } from 'react';
import Header from './Header';
import Sidebar, { RAIL_W, SIDEBAR_W } from './Sidebar';
import CommandPalette, { RECENT_KEY, readRecent } from './CommandPalette';

const RAIL_KEY = 'iez-rail';
const GAP = 12;

function useIsMobile(): boolean {
  const q = '(max-width: 1023px)';
  const [m, setM] = useState(() => typeof window !== 'undefined' && window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const on = () => setM(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return m;
}

export default function MainLayout() {
  const { pathname } = useLocation();
  const mobile = useIsMobile();
  const [rail, setRail] = useState<boolean>(() => { try { return localStorage.getItem(RAIL_KEY) === '1'; } catch { return false; } });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [palette, setPalette] = useState(false);

  const toggleRail = useCallback(() => setRail((r) => { try { localStorage.setItem(RAIL_KEY, r ? '0' : '1'); } catch { /* ignore */ } return !r; }), []);
  const toggleSidebar = () => (mobile ? setMobileOpen((o) => !o) : toggleRail());
  const closePalette = useCallback(() => setPalette(false), []);

  // every navigation starts at the top; remember recent pages for the palette; close the mobile drawer
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'auto' });
    setMobileOpen(false);
    try { localStorage.setItem(RECENT_KEY, JSON.stringify([pathname, ...readRecent().filter((p) => p !== pathname)].slice(0, 8))); } catch { /* ignore */ }
  }, [pathname]);

  // ⌘K / Ctrl+K
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette((p) => !p); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // one pointer tracker drives the edge light on every card (cheap: one rAF per frame, only the hovered card is touched)
  useEffect(() => {
    let raf = 0;
    let last: PointerEvent | null = null;
    const apply = () => {
      raf = 0;
      const e = last;
      if (!e) return;
      const el = (e.target as Element | null)?.closest?.('.ui-card, .module-card, .spot') as HTMLElement | null;
      if (!el) return;
      const r = el.getBoundingClientRect();
      el.style.setProperty('--mx', `${e.clientX - r.left}px`);
      el.style.setProperty('--my', `${e.clientY - r.top}px`);
    };
    const onMove = (e: PointerEvent) => { last = e; if (!raf) raf = requestAnimationFrame(apply); };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => { window.removeEventListener('pointermove', onMove); if (raf) cancelAnimationFrame(raf); };
  }, []);

  const left = mobile ? GAP : (rail ? RAIL_W : SIDEBAR_W) + GAP * 2;
  return (
    <div className="min-h-screen" style={{ background: 'var(--s0)' }}>
      <div className="ambient" aria-hidden><i /><i /><i /></div>
      <div className="shell">
        <Sidebar rail={rail} mobile={mobile} mobileOpen={mobileOpen} onNavigate={() => mobile && setMobileOpen(false)} />
        {mobile && mobileOpen && <div className="scrim" onClick={() => setMobileOpen(false)} />}
        <main style={{ paddingLeft: left, paddingRight: GAP, minHeight: '100vh', transition: 'padding-left .6s var(--spring)' }}>
          <Header onToggleSidebar={toggleSidebar} onOpenPalette={() => setPalette(true)} />
          {/* keyed by route: each page eases in (rise + de-blur) */}
          <div key={pathname} className="page-enter px-2 sm:px-6 pt-8 pb-12 max-w-[1360px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
      <CommandPalette open={palette} onClose={closePalette} onToggleRail={toggleRail} />
    </div>
  );
}
