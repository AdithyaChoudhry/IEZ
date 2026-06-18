import { useAuth } from '@/context/AuthContext';
import { Menu, LogOut, User, ChevronDown, Droplets } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

interface HeaderProps { onToggleSidebar: () => void; }

export default function Header({ onToggleSidebar }: HeaderProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function close(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  return (
    <header
      className="sticky top-0 z-50 flex items-center justify-between px-5 h-[56px]"
      style={{ background: 'var(--s1)', borderBottom: '1px solid var(--b1)' }}
    >
      {/* ── Left ── */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="w-8 h-8 flex items-center justify-center rounded-lg transition-colors"
          style={{ color: 'var(--t2)' }}
          onMouseEnter={e => { e.currentTarget.style.background='var(--s3)'; e.currentTarget.style.color='var(--t0)'; }}
          onMouseLeave={e => { e.currentTarget.style.background='transparent'; e.currentTarget.style.color='var(--t2)'; }}
        >
          <Menu className="w-4 h-4" />
        </button>

        {/* Brand */}
        <div className="flex items-center gap-2.5 select-none">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center shadow-md"
            style={{ background: 'linear-gradient(135deg, var(--teal), #0d9488)' }}
          >
            <Droplets className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span
                className="text-base font-bold leading-none"
                style={{ fontFamily:"'Space Grotesk',sans-serif", color:'var(--t0)', letterSpacing:'-0.02em' }}
              >
                i<span className="text-gradient">EZ</span>
              </span>
              <span
                className="text-[9px] font-semibold px-1.5 py-0.5 rounded tracking-wider"
                style={{ background:'var(--violet-dim)', color:'var(--violet)', border:'1px solid rgba(167,139,250,0.2)' }}
              >
                AI
              </span>
            </div>
            <p className="text-[10px] leading-tight tracking-wide" style={{ color:'var(--t2)' }}>
              WABAG · Instrumentation
            </p>
          </div>
        </div>
      </div>

      {/* ── Center live badge ── */}
      <div className="hidden md:flex items-center gap-1.5 px-3 py-1 rounded-full" style={{ background:'var(--s2)', border:'1px solid var(--b1)' }}>
        <span className="relative flex h-1.5 w-1.5">
          <span className="status-dot absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-400"></span>
        </span>
        <span className="text-[11px] font-medium" style={{ color:'var(--t1)' }}>Systems operational</span>
      </div>

      {/* ── Right ── */}
      <div className="relative" ref={ref}>
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg transition-all duration-150"
          style={{ color:'var(--t0)' }}
          onMouseEnter={e => (e.currentTarget.style.background='var(--s3)')}
          onMouseLeave={e => (e.currentTarget.style.background='transparent')}
        >
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold"
            style={{ background:'linear-gradient(135deg,var(--teal),#0d9488)' }}
          >
            {user?.username?.charAt(0).toUpperCase() || <User className="w-3.5 h-3.5" />}
          </div>
          <span className="hidden sm:block text-xs font-medium" style={{ color:'var(--t0)' }}>
            {user?.username}
          </span>
          <ChevronDown className="w-3 h-3 transition-transform duration-150" style={{ color:'var(--t2)', transform: open ? 'rotate(180deg)' : 'rotate(0deg)' }} />
        </button>

        {open && (
          <div
            className="glass absolute right-0 mt-1.5 w-52 rounded-xl overflow-hidden shadow-2xl animate-fade-in"
            style={{ zIndex:100 }}
          >
            <div className="px-4 py-3" style={{ borderBottom:'1px solid var(--b1)' }}>
              <p className="text-sm font-semibold" style={{ color:'var(--t0)' }}>{user?.username}</p>
              <p className="text-xs mt-0.5" style={{ color:'var(--t2)' }}>{user?.email}</p>
            </div>
            <button
              onClick={() => { logout(); navigate('/login'); }}
              className="w-full px-4 py-2.5 text-left text-sm flex items-center gap-2.5 transition-colors"
              style={{ color:'var(--rose)' }}
              onMouseEnter={e => (e.currentTarget.style.background='rgba(248,113,113,0.08)')}
              onMouseLeave={e => (e.currentTarget.style.background='transparent')}
            >
              <LogOut className="w-3.5 h-3.5" />
              Sign Out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
