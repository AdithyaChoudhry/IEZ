import { useAuth } from '@/context/AuthContext';
import { Menu, LogOut, User, ChevronDown, Droplets, Activity } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

interface HeaderProps { onToggleSidebar: () => void; }

export default function Header({ onToggleSidebar }: HeaderProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <header
      className="sticky top-0 z-50 shadow-2xl"
      style={{ background: 'linear-gradient(135deg, #020d1a 0%, #061428 50%, #020d1a 100%)' }}
    >
      {/* Top animated accent stripe */}
      <div
        className="h-[2px] animate-water-flow"
        style={{
          background: 'linear-gradient(90deg, #0ea5e9, #06b6d4, #3b82f6, #0ea5e9)',
          backgroundSize: '200% 100%',
        }}
      />

      <div className="flex items-center justify-between px-4 py-2.5">
        {/* ── Left ── */}
        <div className="flex items-center gap-3">
          <button
            onClick={onToggleSidebar}
            className="p-2 rounded-xl transition-all duration-200 hover:bg-white/8 text-sky-300/60 hover:text-sky-300"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div className="flex items-center gap-3 select-none">
            {/* Logo mark */}
            <div className="relative group">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center shadow-lg"
                style={{
                  background: 'linear-gradient(135deg, #0ea5e9, #0369a1)',
                  boxShadow: '0 0 20px rgba(14,165,233,0.3)',
                }}
              >
                <Droplets className="w-5 h-5 text-white" />
              </div>
              <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-emerald-400 border-2 border-[#020d1a] animate-pulse" />
            </div>

            {/* Brand text */}
            <div>
              <div className="flex items-center gap-2">
                <h1
                  className="text-lg font-black tracking-tight leading-none"
                  style={{ fontFamily: "'Space Grotesk', sans-serif" }}
                >
                  <span className="text-white">i</span>
                  <span className="text-gradient">EZ</span>
                </h1>
                <span className="px-1.5 py-0.5 text-[9px] font-bold rounded tracking-wider border"
                  style={{
                    background: 'rgba(14,165,233,0.12)',
                    borderColor: 'rgba(14,165,233,0.3)',
                    color: '#38bdf8',
                  }}>
                  AI
                </span>
              </div>
              <p className="text-[10px] leading-tight font-medium tracking-wider" style={{ color: 'var(--text-muted)' }}>
                WABAG · Instrumentation Platform
              </p>
            </div>
          </div>
        </div>

        {/* ── Center ── */}
        <div className="hidden lg:flex items-center gap-4">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full" style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}>
            <Activity className="w-3 h-3 text-emerald-400" />
            <span className="text-[11px] font-medium text-emerald-400">Systems Online</span>
          </div>
        </div>

        {/* ── Right ── */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2.5 px-3 py-2 rounded-xl transition-all duration-200 group"
            style={{ border: '1px solid transparent' }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(14,165,233,0.2)')}
            onMouseLeave={e => (e.currentTarget.style.borderColor = 'transparent')}
          >
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center shadow-md"
              style={{ background: 'linear-gradient(135deg, #0ea5e9, #0369a1)' }}
            >
              <User className="w-4 h-4 text-white" />
            </div>
            <div className="hidden sm:block text-left">
              <p className="text-xs font-semibold text-sky-100 leading-tight">{user?.username}</p>
              <p className="text-[10px] leading-tight" style={{ color: 'var(--text-muted)' }}>Engineer</p>
            </div>
            <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`} style={{ color: 'var(--text-muted)' }} />
          </button>

          {dropdownOpen && (
            <div
              className="absolute right-0 mt-2 w-56 rounded-2xl shadow-2xl py-2 animate-fade-in"
              style={{
                background: 'rgba(6,20,40,0.96)',
                backdropFilter: 'blur(20px)',
                border: '1px solid rgba(14,165,233,0.2)',
              }}
            >
              <div className="px-4 py-3" style={{ borderBottom: '1px solid rgba(14,165,233,0.12)' }}>
                <p className="text-sm font-semibold text-sky-100">{user?.username}</p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{user?.email}</p>
              </div>
              <button
                onClick={() => { logout(); navigate('/login'); }}
                className="w-full px-4 py-2.5 text-left text-sm flex items-center gap-2 transition-colors"
                style={{ color: '#fb7185' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(244,63,94,0.08)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <LogOut className="w-4 h-4" />
                Sign Out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
