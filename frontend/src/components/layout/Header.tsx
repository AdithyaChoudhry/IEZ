import { useAuth } from '@/context/AuthContext';
import { Menu, LogOut, User, Zap, ChevronDown } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

interface HeaderProps { onToggleSidebar: () => void; }

export default function Header({ onToggleSidebar }: HeaderProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <header className="sticky top-0 z-50 bg-gradient-to-r from-[#001529] via-[#002766] to-[#001d66] shadow-xl">
      {/* Top accent line */}
      <div className="h-0.5 bg-gradient-to-r from-blue-500 via-cyan-400 to-blue-600" />

      <div className="flex items-center justify-between px-4 py-3">
        {/* Left */}
        <div className="flex items-center gap-3">
          <button
            onClick={onToggleSidebar}
            className="p-2 rounded-lg hover:bg-white/10 transition-colors text-white/70 hover:text-white"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div className="flex items-center gap-3">
            {/* Logo mark */}
            <div className="relative">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center shadow-lg shadow-blue-900/50">
                <Zap className="w-5 h-5 text-white" />
              </div>
              <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-green-400 border-2 border-[#002766]" />
            </div>

            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-black tracking-tight text-white leading-none">
                  i<span className="text-blue-400">EZ</span>
                </h1>
                <span className="px-1.5 py-0.5 text-[9px] font-bold bg-blue-500/30 text-blue-300 rounded border border-blue-400/30 tracking-wider">
                  AI
                </span>
              </div>
              <p className="text-[10px] text-blue-300/60 leading-tight font-medium tracking-wide">
                Instrumentation Engineering Platform
              </p>
            </div>
          </div>
        </div>

        {/* Center — subtle tagline */}
        <div className="hidden md:flex items-center gap-2 text-blue-300/40 text-xs font-medium">
          <div className="w-1 h-1 rounded-full bg-green-400 animate-pulse" />
          Smart Document Automation
        </div>

        {/* Right — user */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl hover:bg-white/10 transition-all duration-200 group"
          >
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center shadow-md">
              <User className="w-4 h-4 text-white" />
            </div>
            <div className="hidden sm:block text-left">
              <p className="text-xs font-semibold text-white leading-tight">{user?.username}</p>
              <p className="text-[10px] text-blue-300/60 leading-tight">Engineer</p>
            </div>
            <ChevronDown className={`w-3.5 h-3.5 text-blue-300/60 transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`} />
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 mt-2 w-56 bg-white rounded-2xl shadow-2xl py-2 text-gray-700 ring-1 ring-black/5 animate-fade-in">
              <div className="px-4 py-3 border-b border-gray-100">
                <p className="text-sm font-semibold text-gray-900">{user?.username}</p>
                <p className="text-xs text-gray-400">{user?.email}</p>
              </div>
              <button
                onClick={() => { logout(); navigate('/login'); }}
                className="w-full px-4 py-2.5 text-left text-sm hover:bg-red-50 flex items-center gap-2 text-red-500 transition-colors"
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
