import { useEffect, useState } from 'react';
import { Users, Radio, History, Loader2, UserCheck } from 'lucide-react';
import api from '@/services/api';

interface ActiveSession {
  employee_id: string | null;
  employee_name: string;
  role: string | null;
  login_at: string;
  expires_at: string;
}

interface RecentLogin {
  employee_id: string | null;
  employee_name: string;
  role: string | null;
  login_at: string;
}

type SessionStatus = 'active_now' | 'logged_out' | 'never_logged_in';

interface AllUser {
  employee_id: string | null;
  employee_name: string;
  email: string;
  role: string;
  account_status: string;
  session_status: SessionStatus;
  last_login_at: string | null;
  in_admin_roster: boolean;
  has_login_account: boolean;
}

interface LoginActivityResponse {
  total_users_logged_in: number;
  active_session_count: number;
  active_sessions: ActiveSession[];
  recent_logins: RecentLogin[];
  all_users: AllUser[];
}

const SESSION_BADGE: Record<SessionStatus, { label: string; bg: string; color: string }> = {
  active_now:       { label: 'Active now',       bg: 'rgba(74,222,128,0.1)', color: '#4ade80' },
  logged_out:       { label: 'Logged out',       bg: 'rgba(147,175,212,0.1)', color: 'var(--t2)' },
  never_logged_in:  { label: 'Never logged in',  bg: 'rgba(251,191,36,0.08)', color: '#fbbf24' },
};

function fmt(iso: string): string {
  return new Date(iso).toLocaleString();
}

export default function LoginActivity() {
  const [data, setData] = useState<LoginActivityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');

  useEffect(() => {
    api.get('/admin/login-activity')
      .then(r => setData(r.data))
      .catch(ex => setErr(ex?.response?.data?.detail || 'Failed to load login activity'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black mb-1" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)' }}>
          Login Activity
        </h1>
        <p className="text-sm" style={{ color: 'var(--t1)' }}>
          Total users who have logged in, and who's currently active.
        </p>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-6 h-6 animate-spin" style={{ color: 'var(--em)' }} />
        </div>
      )}

      {err && (
        <div className="rounded-xl px-4 py-3 text-sm" style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
          {err}
        </div>
      )}

      {data && (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="rounded-xl p-5 flex items-center gap-4" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'var(--em-dim)' }}>
                <Users className="w-5 h-5" style={{ color: 'var(--em-lt)' }} />
              </div>
              <div>
                <div className="text-2xl font-black" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)' }}>
                  {data.total_users_logged_in}
                </div>
                <div className="text-xs" style={{ color: 'var(--t2)' }}>Total users logged in</div>
              </div>
            </div>

            <div className="rounded-xl p-5 flex items-center gap-4" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(74,222,128,0.1)' }}>
                <Radio className="w-5 h-5" style={{ color: '#4ade80' }} />
              </div>
              <div>
                <div className="text-2xl font-black" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)' }}>
                  {data.active_session_count}
                </div>
                <div className="text-xs" style={{ color: 'var(--t2)' }}>Active sessions now</div>
              </div>
            </div>

            <div className="rounded-xl p-5 flex items-center gap-4" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
              <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'var(--gold-dim)' }}>
                <UserCheck className="w-5 h-5" style={{ color: 'var(--gold)' }} />
              </div>
              <div>
                <div className="text-2xl font-black" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)' }}>
                  {data.all_users.length}
                </div>
                <div className="text-xs" style={{ color: 'var(--t2)' }}>Total created accounts</div>
              </div>
            </div>
          </div>

          {/* All users — every created account */}
          <div>
            <p className="text-[10px] font-semibold tracking-widest uppercase mb-3 flex items-center gap-1.5" style={{ color: 'var(--t2)' }}>
              <UserCheck className="w-3 h-3" />
              All Users
            </p>
            <div className="rounded-xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
              {data.all_users.length === 0 ? (
                <div className="py-10 text-center text-sm" style={{ color: 'var(--t2)' }}>No accounts created yet.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ background: 'var(--s1)' }}>
                      <th className="text-left px-4 py-2.5 text-xs font-semibold" style={{ color: 'var(--t1)' }}>User</th>
                      <th className="text-left px-4 py-2.5 text-xs font-semibold" style={{ color: 'var(--t1)' }}>Role</th>
                      <th className="text-left px-4 py-2.5 text-xs font-semibold" style={{ color: 'var(--t1)' }}>Source</th>
                      <th className="text-left px-4 py-2.5 text-xs font-semibold" style={{ color: 'var(--t1)' }}>Account</th>
                      <th className="text-left px-4 py-2.5 text-xs font-semibold" style={{ color: 'var(--t1)' }}>Session</th>
                      <th className="text-left px-4 py-2.5 text-xs font-semibold" style={{ color: 'var(--t1)' }}>Last login</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.all_users.map((u) => {
                      const badge = SESSION_BADGE[u.session_status];
                      return (
                        <tr key={u.email} style={{ borderTop: '1px solid var(--b0)' }}>
                          <td className="px-4 py-2.5">
                            <div className="font-medium" style={{ color: 'var(--t0)' }}>{u.employee_name}</div>
                            <div className="text-xs" style={{ color: 'var(--t2)' }}>{u.employee_id || u.email}</div>
                          </td>
                          <td className="px-4 py-2.5" style={{ color: 'var(--t1)' }}>{u.role}</td>
                          <td className="px-4 py-2.5">
                            <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
                              style={{
                                background: u.in_admin_roster ? 'var(--em-dim)' : 'rgba(167,139,250,0.1)',
                                color: u.in_admin_roster ? 'var(--em-lt)' : 'var(--violet)',
                              }}>
                              {u.in_admin_roster ? 'Admin-created' : 'Self-registered'}
                            </span>
                          </td>
                          <td className="px-4 py-2.5">
                            <span className="text-xs font-semibold px-2 py-0.5 rounded-full capitalize"
                              style={{
                                background: u.account_status === 'active' ? 'rgba(74,222,128,0.08)' : 'rgba(248,113,113,0.08)',
                                color: u.account_status === 'active' ? '#4ade80' : 'var(--rose)',
                              }}>
                              {u.account_status}
                            </span>
                          </td>
                          <td className="px-4 py-2.5">
                            {u.has_login_account ? (
                              <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
                                style={{ background: badge.bg, color: badge.color }}>
                                {badge.label}
                              </span>
                            ) : (
                              <span className="text-xs font-semibold px-2 py-0.5 rounded-full"
                                style={{ background: 'rgba(248,113,113,0.08)', color: 'var(--rose)' }}>
                                No login account
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-2.5" style={{ color: 'var(--t1)' }}>
                            {u.last_login_at ? fmt(u.last_login_at) : '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Active sessions */}
          <div>
            <p className="text-[10px] font-semibold tracking-widest uppercase mb-3 flex items-center gap-1.5" style={{ color: 'var(--t2)' }}>
              <Radio className="w-3 h-3" style={{ color: '#4ade80' }} />
              Active Sessions
            </p>
            <div className="rounded-xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
              {data.active_sessions.length === 0 ? (
                <div className="py-10 text-center text-sm" style={{ color: 'var(--t2)' }}>No active sessions right now.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ background: 'var(--s1)' }}>
                      <th className="text-left px-4 py-2.5 text-xs font-semibold" style={{ color: 'var(--t1)' }}>Employee</th>
                      <th className="text-left px-4 py-2.5 text-xs font-semibold" style={{ color: 'var(--t1)' }}>Role</th>
                      <th className="text-left px-4 py-2.5 text-xs font-semibold" style={{ color: 'var(--t1)' }}>Logged in</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.active_sessions.map((s, i) => (
                      <tr key={i} style={{ borderTop: '1px solid var(--b0)' }}>
                        <td className="px-4 py-2.5">
                          <div className="font-medium" style={{ color: 'var(--t0)' }}>{s.employee_name}</div>
                          <div className="text-xs" style={{ color: 'var(--t2)' }}>{s.employee_id || '—'}</div>
                        </td>
                        <td className="px-4 py-2.5" style={{ color: 'var(--t1)' }}>{s.role || '—'}</td>
                        <td className="px-4 py-2.5" style={{ color: 'var(--t1)' }}>{fmt(s.login_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Recent login history */}
          <div>
            <p className="text-[10px] font-semibold tracking-widest uppercase mb-3 flex items-center gap-1.5" style={{ color: 'var(--t2)' }}>
              <History className="w-3 h-3" />
              Recent Login History
            </p>
            <div className="rounded-xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
              {data.recent_logins.length === 0 ? (
                <div className="py-10 text-center text-sm" style={{ color: 'var(--t2)' }}>No logins recorded yet.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ background: 'var(--s1)' }}>
                      <th className="text-left px-4 py-2.5 text-xs font-semibold" style={{ color: 'var(--t1)' }}>Employee</th>
                      <th className="text-left px-4 py-2.5 text-xs font-semibold" style={{ color: 'var(--t1)' }}>Role</th>
                      <th className="text-left px-4 py-2.5 text-xs font-semibold" style={{ color: 'var(--t1)' }}>Login time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_logins.map((l, i) => (
                      <tr key={i} style={{ borderTop: '1px solid var(--b0)' }}>
                        <td className="px-4 py-2.5">
                          <div className="font-medium" style={{ color: 'var(--t0)' }}>{l.employee_name}</div>
                          <div className="text-xs" style={{ color: 'var(--t2)' }}>{l.employee_id || '—'}</div>
                        </td>
                        <td className="px-4 py-2.5" style={{ color: 'var(--t1)' }}>{l.role || '—'}</td>
                        <td className="px-4 py-2.5" style={{ color: 'var(--t1)' }}>{fmt(l.login_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
