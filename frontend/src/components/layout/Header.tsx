import { useAuth } from '@/context/AuthContext';
import {
  Menu, LogOut, User, ChevronDown, Droplets, Bell, CheckCheck,
  Clock, ThumbsUp, ThumbsDown, Info, CheckCircle2, XCircle,
  AlertTriangle, Loader2, X, FileText, Tag,
} from 'lucide-react';
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

interface ApprovalReq {
  id: number;
  request_type: string;
  tag_numbers: string | null;
  instrument_type: string | null;
  submitted_by_name: string;
  submitted_by_id: string;
  submitter_notes: string | null;
  status: string;
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

// ── Quick Approve Drawer ───────────────────────────────────────────────────────
function QuickApproveDrawer({
  requestId,
  onClose,
  onDone,
}: {
  requestId: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const [req, setReq] = useState<ApprovalReq | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<'approve' | 'reject' | null>(null);
  const [empId, setEmpId] = useState('');
  const [pass, setPass] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [done, setDone] = useState(false);

  useEffect(() => {
    api.get(`/approvals/${requestId}`)
      .then(r => setReq(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [requestId]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(''); setBusy(true);
    try {
      await api.post(`/approvals/${requestId}/${action}`, {
        employee_id: empId,
        password: pass,
        review_notes: notes || null,
      });
      setDone(true);
      onDone();
    } catch (ex: any) {
      setErr(ex?.response?.data?.detail || 'Failed to submit review');
    } finally {
      setBusy(false);
    }
  };

  const tags: string[] = req?.tag_numbers ? JSON.parse(req.tag_numbers) : [];
  const isPending = req?.status === 'pending';

  return (
    <>
      {/* Backdrop — clicking it closes without losing page state */}
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div
        className="fixed right-0 top-0 bottom-0 z-50 flex flex-col w-full max-w-md shadow-2xl"
        style={{ background: 'var(--s1)', borderLeft: '1px solid var(--b2)' }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4" style={{ borderBottom: '1px solid var(--b1)' }}>
          <div className="flex items-center gap-2.5">
            <Clock className="w-4 h-4" style={{ color: 'var(--gold)' }} />
            <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>
              Quick Review — Request #{requestId}
            </span>
          </div>
          <button onClick={onClose} className="opacity-40 hover:opacity-80 transition-opacity" style={{ color: 'var(--t1)' }}>
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {loading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin" style={{ color: 'var(--em)' }} />
            </div>
          )}

          {!loading && !req && (
            <p className="text-sm text-center py-8" style={{ color: 'var(--t2)' }}>
              Request not found or access denied.
            </p>
          )}

          {done && (
            <div className="flex flex-col items-center py-16 gap-4">
              <CheckCircle2 className="w-12 h-12" style={{ color: '#4ade80' }} />
              <p className="text-sm font-semibold" style={{ color: 'var(--t0)' }}>Review submitted successfully</p>
              <button onClick={onClose} className="btn btn-primary text-xs px-4 py-2">Close</button>
            </div>
          )}

          {!loading && req && !done && (
            <div className="space-y-5">
              {/* Request info card */}
              <div className="rounded-xl p-4 space-y-3" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full"
                    style={{ background: req.request_type === 'spec' ? 'rgba(59,130,246,0.1)' : 'rgba(245,158,11,0.1)', color: req.request_type === 'spec' ? 'var(--em-lt)' : 'var(--gold)' }}>
                    {req.request_type === 'spec' ? 'Spec Extraction' : 'Cover Sheet'}
                  </span>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full capitalize"
                    style={{
                      background: req.status === 'approved' ? 'rgba(74,222,128,0.08)' : req.status === 'rejected' ? 'rgba(248,113,113,0.08)' : 'rgba(245,158,11,0.08)',
                      color: req.status === 'approved' ? '#4ade80' : req.status === 'rejected' ? 'var(--rose)' : 'var(--gold)',
                    }}>
                    {req.status}
                  </span>
                </div>

                {req.instrument_type && (
                  <div className="flex items-start gap-2">
                    <FileText className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" style={{ color: 'var(--t2)' }} />
                    <span className="text-sm font-medium" style={{ color: 'var(--t0)' }}>{req.instrument_type}</span>
                  </div>
                )}

                {tags.length > 0 && (
                  <div className="flex items-start gap-2">
                    <Tag className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" style={{ color: 'var(--t2)' }} />
                    <span className="text-xs" style={{ color: 'var(--t1)' }}>{tags.join(', ')}</span>
                  </div>
                )}

                <div className="text-xs" style={{ color: 'var(--t2)' }}>
                  Submitted by <strong style={{ color: 'var(--t1)' }}>{req.submitted_by_name}</strong> ({req.submitted_by_id})
                  · {new Date(req.created_at).toLocaleString()}
                </div>

                {req.submitter_notes && (
                  <div className="rounded-lg px-3 py-2.5 text-xs" style={{ background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.15)', color: 'var(--t1)' }}>
                    {req.submitter_notes}
                  </div>
                )}
              </div>

              {/* Already reviewed */}
              {!isPending && (
                <div className="rounded-xl px-4 py-3 text-xs text-center" style={{ background: 'var(--s2)', border: '1px solid var(--b1)', color: 'var(--t2)' }}>
                  This request has already been <strong style={{ color: req.status === 'approved' ? '#4ade80' : 'var(--rose)' }}>{req.status}</strong>.
                </div>
              )}

              {/* Action buttons */}
              {isPending && !action && (
                <div className="flex gap-3">
                  <button
                    onClick={() => setAction('approve')}
                    className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-bold"
                    style={{ background: 'rgba(74,222,128,0.1)', color: '#4ade80', border: '1px solid rgba(74,222,128,0.3)' }}
                  >
                    <CheckCircle2 className="w-4 h-4" /> Approve
                  </button>
                  <button
                    onClick={() => setAction('reject')}
                    className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-bold"
                    style={{ background: 'rgba(248,113,113,0.08)', color: 'var(--rose)', border: '1px solid rgba(248,113,113,0.2)' }}
                  >
                    <XCircle className="w-4 h-4" /> Reject
                  </button>
                </div>
              )}

              {/* Review form */}
              {isPending && action && (
                <form onSubmit={submit} className="space-y-4">
                  <div className="flex items-center gap-2 pb-2" style={{ borderBottom: '1px solid var(--b1)' }}>
                    <div className="w-7 h-7 rounded-lg flex items-center justify-center"
                      style={{ background: action === 'approve' ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.12)' }}>
                      {action === 'approve'
                        ? <CheckCircle2 className="w-3.5 h-3.5" style={{ color: '#4ade80' }} />
                        : <XCircle className="w-3.5 h-3.5" style={{ color: 'var(--rose)' }} />}
                    </div>
                    <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>
                      {action === 'approve' ? 'Approving' : 'Rejecting'} Request
                    </span>
                    <button type="button" onClick={() => { setAction(null); setErr(''); }}
                      className="ml-auto text-[10px] opacity-50 hover:opacity-80" style={{ color: 'var(--t1)' }}>
                      ← Back
                    </button>
                  </div>

                  {err && (
                    <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs"
                      style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
                      <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" /> {err}
                    </div>
                  )}

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>
                      Lead Engineer Employee ID
                    </label>
                    <input type="text" required value={empId} onChange={e => setEmpId(e.target.value)}
                      placeholder="e.g. WABAG-LEAD-001"
                      className="w-full px-3 py-2.5 rounded-xl text-sm"
                      style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>
                      Password
                    </label>
                    <input type="password" required value={pass} onChange={e => setPass(e.target.value)}
                      placeholder="••••••••"
                      className="w-full px-3 py-2.5 rounded-xl text-sm"
                      style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>
                      {action === 'approve' ? 'Notes (optional)' : 'Reason for Rejection *'}
                    </label>
                    <textarea
                      rows={3} value={notes} onChange={e => setNotes(e.target.value)}
                      placeholder={action === 'approve' ? 'Any notes for the requester…' : 'Explain why this is being rejected…'}
                      className="w-full resize-none px-3 py-2.5 rounded-xl text-sm"
                      style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
                  </div>

                  <button
                    type="submit"
                    disabled={busy || !empId || !pass || (action === 'reject' && !notes)}
                    className="w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
                    style={{
                      background: action === 'approve' ? 'linear-gradient(135deg,#22c55e,#16a34a)' : 'linear-gradient(135deg,#ef4444,#dc2626)',
                      color: '#fff',
                      opacity: (busy || !empId || !pass || (action === 'reject' && !notes)) ? 0.5 : 1,
                      cursor: 'pointer',
                    }}
                  >
                    {busy
                      ? <Loader2 className="w-4 h-4 animate-spin" />
                      : action === 'approve' ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                    {busy ? 'Processing…' : action === 'approve' ? 'Confirm Approval' : 'Confirm Rejection'}
                  </button>
                </form>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

// ── Header ─────────────────────────────────────────────────────────────────────
export default function Header({ onToggleSidebar }: HeaderProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);

  const [bellOpen, setBellOpen] = useState(false);
  const bellRef = useRef<HTMLDivElement>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifs, setNotifs] = useState<NotifItem[]>([]);
  const [notifsLoaded, setNotifsLoaded] = useState(false);

  // Quick-approve drawer
  const [drawerRequestId, setDrawerRequestId] = useState<number | null>(null);

  useEffect(() => {
    function close(e: MouseEvent) {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) setProfileOpen(false);
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) setBellOpen(false);
    }
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, []);

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

  const loadNotifs = useCallback(() => {
    api.get('/notifications?limit=20')
      .then(r => { setNotifs(r.data); setNotifsLoaded(true); })
      .catch(() => { setNotifsLoaded(true); });
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
    setBellOpen(false);

    if (n.related_request_id && n.notif_type === 'approval_submitted') {
      // Open inline drawer — no navigation, current page state is preserved
      setDrawerRequestId(n.related_request_id);
    } else if (n.related_request_id) {
      navigate('/approval-queue');
    }
  }

  return (
    <>
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

          {/* Bell */}
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
                        {n.notif_type === 'approval_submitted' && n.related_request_id && (
                          <span className="inline-block mt-1 text-[9px] font-semibold px-1.5 py-0.5 rounded"
                            style={{ background: 'rgba(245,158,11,0.1)', color: 'var(--gold)', border: '1px solid rgba(245,158,11,0.2)' }}>
                            Click to review →
                          </span>
                        )}
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

          {/* Profile dropdown */}
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

      {/* Quick-approve drawer — rendered outside header so it overlays the full page */}
      {drawerRequestId !== null && (
        <QuickApproveDrawer
          requestId={drawerRequestId}
          onClose={() => setDrawerRequestId(null)}
          onDone={() => {
            setDrawerRequestId(null);
            fetchUnread();
          }}
        />
      )}
    </>
  );
}
