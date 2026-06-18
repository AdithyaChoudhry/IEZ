import { Outlet } from 'react-router-dom';
import Header from './Header';
import Sidebar from './Sidebar';
import { useState } from 'react';

export default function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="min-h-screen" style={{ background:'var(--s0)' }}>
      <Header onToggleSidebar={() => setSidebarOpen(o => !o)} />
      <div className="flex">
        <Sidebar isOpen={sidebarOpen} />
        <main
          className="flex-1 transition-all duration-300"
          style={{
            marginLeft: sidebarOpen ? '224px' : '0',
            minHeight: 'calc(100vh - 56px)',
          }}
        >
          <div className="p-6 max-w-7xl mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
