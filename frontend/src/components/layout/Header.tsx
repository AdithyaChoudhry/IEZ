import { useAuth } from '@/context/AuthContext';
import { Menu, LogOut, User, ChevronDown, Droplets, Bell, CheckCheck, Clock, ThumbsUp, ThumbsDown, Info } from 'lucide-react';
import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '@/services/api';

interface HeaderProps { onToggleSidebar: () => void; }

interface NotifItem {
  id: number;
  title: string;
  body: string;
  notif_type: string;
  related_request_id: number | null;
  is_read: boolean;
  created_at: string;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function NotifIcon({ type }: { type: string }) {
  if (type === 'approved') return <ThumbsUp className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#4ade80' }} />;
  if (type === 'rejected') return <ThumbsDown className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--rose)' }} />;
  if (type === 'approval_submitted') return <Clock className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--gold)' }} />;
  return <Info className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--em-lt)' }} />;
}

export default function Header({ onToggleSidebar }: HeaderProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  // Profile dropdown
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);

  // Bell dropdown
  const [bellOpen, setBellOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifs, setNotifs] = useState<NotifItem[]>([]);
  const [notifsLoaded, setNotifsLoaded] = useState(false);

  // Close on outside click
  useEffect(() => {
    function close(e: MouseEvent) {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) setProfileOpen(false);
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) setBellOpen(false);
    }
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

  // Poll unread count every 30s
  const fetchUnread = useCallback(() => {
    api.get('/notifications/unread/count')
      .then(r => setUnreadCount(r.data.count ?? 0))
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchUnread();
    const t = setInterval(fetchUnread, 30_000);
    return () => clearInterval(t);
  }, [fetchUnread]);

  // Load notifications when bell is opened
  const loadNotifs = useCallback(() => {
    api.get('/notifications?limit=20')
      .then(r => { setNotifs(r.data); setNotifsLoaded(true); })
      .catch(() => { setNotifsLoaded(true); }); // show empty state on error
  }, []);

  function openBell() {
    setBellOpen(b => {
      if (!b) loadNotifs();
      return !b;
    });
  }

  async function markRead(id: number) {
    await api.post(`/notifications/${id}/read`).catch(() => {});
    setNotifs(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n));
    setUnreadCount(c => Math.max(0, c - 1));
  }

  async function markAllRead() {
    await api.post('/notifications/mark-all-read').catch(() => {});
    setNotifs(prev => prev.map(n => ({ ...n, is_read: true })));
    setUnreadCount(0);
  }

  function handleNotifClick(n: NotifItem) {
    if (!n.is_read) markRead(n.id);
    if (n.related_request_id) navigate('/approval-queue');
    setBellOpen(false);
  }

  return (
    <header
      className="sticky top-0 z-50 flex items-center justify-between px-5 h-[56px]"
      style={{ background: 'var(--s1)', borderBottom: '1px solid var(--b1)' }}
    >
      {/* Left */}
      <div className="flex items-center gap-3">
        <button
          onClick={onToggleSidebar}
          className="w-8 h-8 flex items-center justify-center rounded-lg transition-all duration-150"
          style={{ color: 'var(--t2)' }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--s3)'; e.currentTarget.style.color = 'var(--t0)'; }}
          onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--t2)'; }}
        >
          <Menu className="w-4 h-4" />
        </button>

        <div className="flex items-center gap-2.5 select-none">
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, var(--em), #1d4ed8)', boxShadow: '0 0 12px var(--em-glow)' }}
          >
            <Droplets className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span
                className="text-base font-bold leading-none"
                style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)', letterSpacing: '-0.02em' }}
              >
                i<span className="text-gradient">EZ</span>
              </span>
              <span
                className="text-[9px] font-semibold px-1.5 py-0.5 rounded tracking-wider"
                style={{ background: 'rgba(245,158,11,0.1)', color: 'var(--gold)', border: '1px solid rgba(245,158,11,0.2)' }}
              >
                AI
              </span>
            </div>
            <p className="text-[10px] leading-tight tracking-wide" style={{ color: 'var(--t2)' }}>
              WABAG · Instrumentation
            </p>
          </div>
        </div>
      </div>

      {/* Centre */}
      <div className="hidden md:flex items-center gap-1.5 px-3 py-1 rounded-full" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        <span className="ping-dot w-1.5 h-1.5 rounded-full bg-blue-400" />
        <span className="text-[11px] font-medium" style={{ color: 'var(--t1)' }}>Systems operational</span>
      </div>

      {/* Right */}
      <div className="flex items-center gap-2">

        {/* ── Bell ── */}
        <div className="relative" ref={bellRef}>
          <button
            onClick={openBell}
            className="relative w-8 h-8 flex items-center justify-center rounded-lg transition-all duration-150"
            style={{ color: 'var(--t2)' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--s3)'; e.currentTarget.style.color = 'var(--t0)'; }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--t2)'; }}
          >
            <Bell className="w-4 h-4" />
            {unreadCount > 0 && (
              <span
                className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 flex items-center justify-center rounded-full text-[9px] font-black px-1"
                style={{ background: 'var(--rose)', color: '#fff' }}
              >
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </button>

          {bellOpen && (
            <div
              className="glass absolute right-0 mt-1.5 w-80 rounded-xl overflow-hidden shadow-2xl animate-fade-in"
              style={{ zIndex: 100 }}
            >
              {/* Header row */}
              <div className="flex items-center justify-between px-4 py-2.5" style={{ borderBottom: '1px solid var(--b1)' }}>
                <span className="text-xs font-semibold" style={{ color: 'var(--t0)' }}>
                  Notifications {unreadCount > 0 && <span style={{ color: 'var(--rose)' }}>({unreadCount})</span>}
                </span>
                {unreadCount > 0 && (
                  <button
                    onClick={markAllRead}
                    className="flex items-center gap-1 text-[10px] font-medium transition-opacity hover:opacity-70"
                    style={{ color: 'var(--em-lt)' }}
                  >
                    <CheckCheck className="w-3 h-3" />
                    Mark all read
                  </button>
                )}
              </div>

              {/* List */}
              <div className="overflow-y-auto" style={{ maxHeight: '340px' }}>
                {!notifsLoaded && (
                  <div className="py-8 text-center text-xs" style={{ color: 'var(--t2)' }}>Loading…</div>
                )}
                {notifsLoaded && notifs.length === 0 && (
                  <div className="py-8 text-center text-xs" style={{ color: 'var(--t2)' }}>No notifications yet</div>
                )}
                {notifsLoaded && notifs.map(n => (
                  <button
                    key={n.id}
                    onClick={() => handleNotifClick(n)}
                    className="w-full text-left px-4 py-3 flex gap-3 transition-colors"
                    style={{
                      background: n.is_read ? 'transparent' : 'rgba(59,130,246,0.06)',
                      borderBottom: '1px solid var(--b0)',
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = 'var(--s2)')}
                    onMouseLeave={e => (e.currentTarget.style.background = n.is_read ? 'transparent' : 'rgba(59,130,246,0.06)')}
                  >
                    <div className="mt-0.5">
                      <NotifIcon type={n.notif_type} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold truncate" style={{ color: 'var(--t0)' }}>{n.title}</p>
                      <p className="text-[11px] mt-0.5 line-clamp-2" style={{ color: 'var(--t2)' }}>{n.body}</p>
                      <p className="text-[10px] mt-1" style={{ color: 'var(--t2)', opacity: 0.6 }}>{timeAgo(n.created_at)}</p>
                    </div>
                    {!n.is_read && (
                      <span className="w-2 h-2 rounded-full flex-shrink-0 mt-1.5" style={{ background: 'var(--em)' }} />
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Profile dropdown ── */}
        <div className="relative" ref={profileRef}>
          <button
            onClick={() => setProfileOpen(!profileOpen)}
            className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg transition-all duration-150"
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--s3)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            <div
              className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs font-bold"
              style={{ background: 'linear-gradient(135deg, var(--em), #1d4ed8)' }}
            >
              {user?.username?.charAt(0).toUpperCase() || <User className="w-3.5 h-3.5" />}
            </div>
            <span className="hidden sm:block text-xs font-medium" style={{ color: 'var(--t0)' }}>
              {user?.username}
            </span>
            <ChevronDown
              className="w-3 h-3 transition-transform duration-150"
              style={{ color: 'var(--t2)', transform: profileOpen ? 'rotate(180deg)' : 'none' }}
            />
          </button>

          {profileOpen && (
            <div className="glass absolute right-0 mt-1.5 w-52 rounded-xl overflow-hidden shadow-2xl animate-fade-in" style={{ zIndex: 100 }}>
              <div className="px-4 py-3" style={{ borderBottom: '1px solid var(--b1)' }}>
                <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>{user?.username}</p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--t2)' }}>{user?.email}</p>
              </div>
              <button
                onClick={() => { logout(); navigate('/login'); }}
                className="w-full px-4 py-2.5 text-left text-sm flex items-center gap-2.5 transition-colors"
                style={{ color: 'var(--rose)' }}
                onMouseEnter={e => (e.currentTarget.style.background = 'rgba(248,113,113,0.08)')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <LogOut className="w-3.5 h-3.5" />
                Sign Out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
