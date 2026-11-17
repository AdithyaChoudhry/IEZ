import { Outlet, useLocation } from 'react-router-dom';
import Header from './Header';
import Sidebar from './Sidebar';
import { useEffect, useState } from 'react';

export default function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const { pathname } = useLocation();

  // every navigation starts at the top, like turning to a new page
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'auto' }); }, [pathname]);

  return (
    <div className="min-h-screen" style={{ background: 'var(--s0)' }}>
      <Header onToggleSidebar={() => setSidebarOpen(o => !o)} />
      <div className="flex">
        <Sidebar isOpen={sidebarOpen} />
        <main
          className="flex-1"
          style={{
            marginLeft: sidebarOpen ? '244px' : '0',
            minHeight: 'calc(100vh - 56px)',
            transition: 'margin-left .55s var(--spring)',
          }}
        >
          {/* keyed by route: each page eases in (fade + rise + de-blur) */}
          <div key={pathname} className="page-enter px-8 py-8 max-w-[1320px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
