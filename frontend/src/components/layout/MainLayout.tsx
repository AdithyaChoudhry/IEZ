import { Outlet, useLocation } from 'react-router-dom';
import { useCallback, useEffect, useState } from 'react';
import Header from './Header';
import CommandPalette, { RECENT_KEY, readRecent } from './CommandPalette';

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
  const [palette, setPalette] = useState(false);
  const closePalette = useCallback(() => setPalette(false), []);

  // every navigation starts at the top; remember recent pages for the palette
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'auto' });
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

  return (
    <div className="min-h-screen" style={{ background: 'var(--s0)' }}>
      <Header mobile={mobile} onOpenPalette={() => setPalette(true)} />
      <div key={`bar-${pathname}`} className="route-bar" aria-hidden />
      <main>
        {/* keyed by route: each page eases in */}
        <div key={pathname} className="page-enter max-w-[1440px] mx-auto px-5 lg:px-8 pt-9 pb-16">
          <Outlet />
        </div>
      </main>
      <CommandPalette open={palette} onClose={closePalette} />
    </div>
  );
}
