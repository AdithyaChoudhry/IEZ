/* ─────────────────────────────────────────────────────────────────────────────
   Admin Management — Users · Notification Routing
───────────────────────────────────────────────────────────────────────────── */
import { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck, Plus, Edit2, Trash2, UserX, UserCheck,
  KeyRound, X, CheckCircle2, Search, User,
  Loader2, RefreshCw, Bell, BellOff, Route,
} from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import Button from '../ui/Button';
import Alert from '../ui/Alert';

const ROLES = ['Admin', 'Reviewer', 'Lead Engineer', 'Senior Engineer', 'Engineer', 'GET', 'Read Only'];

interface AdminUser {
  id: number;
  employee_id: string;
  employee_name: string;
  designation: string;
  department: string;
  email_id: string;
  role: string;
  status: string;
  created_date: string;
  last_login: string | null;
}

// ── Field helper ───────────────────────────────────────────────────────────────
function Field({ label, required, error, children }: { label: string; required?: boolean; error?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5"
        style={{ color: error ? 'var(--rose)' : 'var(--t2)' }}>
        {label}{required && <span style={{ color: 'var(--rose)' }}> *</span>}
      </label>
      {children}
      {error && <p className="text-[10px] mt-1" style={{ color: 'var(--rose)' }}>{error}</p>}
    </div>
  );
}

function Input({ value, onChange, placeholder, type = 'text', error }: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string; error?: boolean;
}) {
  return (
    <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
      className="w-full px-3 py-2.5 rounded-xl text-sm"
      style={{ background: 'var(--s1)', border: `1px solid ${error ? 'var(--rose)' : 'var(--b2)'}`, color: 'var(--t0)', outline: 'none' }} />
  );
}

function Select({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)}
      className="w-full px-3 py-2.5 rounded-xl text-sm"
      style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }}>
      <option value="">Select…</option>
      {options.map(o => <option key={o} value={o}>{o}</option>)}
    </select>
  );
}

// ── Create / Edit Modal ────────────────────────────────────────────────────────
function UserModal({
  user, onClose, onSave,
}: { user: AdminUser | null; onClose: () => void; onSave: () => void }) {
  const isEdit = !!user;
  const [form, setForm] = useState({
    employee_id: user?.employee_id || '',
    employee_name: user?.employee_name || '',
    designation: user?.designation || '',
    department: user?.department || '',
    email_id: user?.email_id || '',
    role: user?.role || '',
    password: '',
    confirm_password: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const set = (k: string) => (v: string) => setForm(f => ({ ...f, [k]: v }));

  const validate = () => {
    const e: Record<string, string> = {};
    if (!form.employee_id.trim()) e.employee_id = 'Required';
    if (!form.employee_name.trim()) e.employee_name = 'Required';
    if (!form.designation.trim()) e.designation = 'Required';
    if (!form.department.trim()) e.department = 'Required';
    if (!form.email_id.trim()) e.email_id = 'Required';
    if (!form.role) e.role = 'Required';
    if (!isEdit) {
      if (!form.password) e.password = 'Required';
      if (form.password !== form.confirm_password) e.confirm_password = 'Passwords do not match';
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const save = async () => {
    if (!validate()) return;
    setBusy(true); setErr('');
    try {
      if (isEdit) {
        await api.put(`/admin/users/${user!.employee_id}`, {
          employee_name: form.employee_name,
          designation: form.designation,
          department: form.department,
          email_id: form.email_id,
          role: form.role,
        });
      } else {
        await api.post('/admin/users', form);
      }
      onSave();
      onClose();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Failed to save user');
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg rounded-2xl overflow-hidden max-h-[90vh] overflow-y-auto"
        style={{ background: 'var(--s1)', border: '1px solid var(--b2)' }}>
        <div className="px-6 py-5 flex items-center gap-3" style={{ borderBottom: '1px solid var(--b1)' }}>
          <div className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: 'var(--em-dim)', border: '1px solid rgba(59,130,246,0.3)' }}>
            <User className="w-4 h-4" style={{ color: 'var(--em-lt)' }} />
          </div>
          <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>
            {isEdit ? `Edit — ${user!.employee_name}` : 'Create New Admin User'}
          </p>
          <button onClick={onClose} className="ml-auto opacity-50 hover:opacity-90" style={{ color: 'var(--t1)' }}>
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {err && <Alert variant="error">{err}</Alert>}

          <div className="grid grid-cols-2 gap-4">
            <Field label="Employee ID" required error={errors.employee_id}>
              <Input value={form.employee_id} onChange={set('employee_id')} placeholder="e.g. WABAG-EMP-001"
                error={!!errors.employee_id} />
            </Field>
            <Field label="Employee Name" required error={errors.employee_name}>
              <Input value={form.employee_name} onChange={set('employee_name')} placeholder="Full name"
                error={!!errors.employee_name} />
            </Field>
            <Field label="Designation" required error={errors.designation}>
              <Input value={form.designation} onChange={set('designation')} placeholder="e.g. Senior Engineer"
                error={!!errors.designation} />
            </Field>
            <Field label="Department" required error={errors.department}>
              <Input value={form.department} onChange={set('department')} placeholder="e.g. Instrumentation"
                error={!!errors.department} />
            </Field>
            <Field label="Email ID" required error={errors.email_id}>
              <Input value={form.email_id} onChange={set('email_id')} placeholder="email@wabag.com" type="email"
                error={!!errors.email_id} />
            </Field>
            <Field label="User Role" required error={errors.role}>
              <Select value={form.role} onChange={set('role')} options={ROLES} />
              {errors.role && <p className="text-[10px] mt-1" style={{ color: 'var(--rose)' }}>{errors.role}</p>}
            </Field>

            {!isEdit && (
              <>
                <Field label="Password" required error={errors.password}>
                  <Input value={form.password} onChange={set('password')} type="password" placeholder="••••••••"
                    error={!!errors.password} />
                </Field>
                <Field label="Confirm Password" required error={errors.confirm_password}>
                  <Input value={form.confirm_password} onChange={set('confirm_password')} type="password" placeholder="••••••••"
                    error={!!errors.confirm_password} />
                </Field>
              </>
            )}
          </div>
        </div>

        <div className="px-6 pb-6 flex gap-3">
          <Button variant="secondary" onClick={onClose} fullWidth>Cancel</Button>
          <Button onClick={save} loading={busy} fullWidth>
            <CheckCircle2 className="w-3.5 h-3.5" /> {isEdit ? 'Save Changes' : 'Create User'}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Reset Password Modal ───────────────────────────────────────────────────────
function ResetPasswordModal({ user, onClose, onSave }: { user: AdminUser; onClose: () => void; onSave: () => void }) {
  const [newPass, setNewPass] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const save = async () => {
    if (!newPass || newPass !== confirm) { setErr('Passwords do not match or are empty'); return; }
    setBusy(true); setErr('');
    try {
      await api.post(`/admin/users/${user.employee_id}/reset-password`, { new_password: newPass, confirm_password: confirm });
      onSave(); onClose();
    } catch (e: any) { setErr(e?.response?.data?.detail || 'Failed to reset password'); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-2xl overflow-hidden"
        style={{ background: 'var(--s1)', border: '1px solid var(--b2)' }}>
        <div className="px-6 py-5 flex items-center gap-3" style={{ borderBottom: '1px solid var(--b1)' }}>
          <KeyRound className="w-4 h-4" style={{ color: 'var(--gold)' }} />
          <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Reset Password — {user.employee_name}</p>
          <button onClick={onClose} className="ml-auto opacity-50"><X className="w-4 h-4" style={{ color: 'var(--t1)' }} /></button>
        </div>
        <div className="p-6 space-y-4">
          {err && <Alert variant="error">{err}</Alert>}
          <Field label="New Password" required>
            <Input value={newPass} onChange={setNewPass} type="password" placeholder="••••••••" />
          </Field>
          <Field label="Confirm Password" required>
            <Input value={confirm} onChange={setConfirm} type="password" placeholder="••••••••" />
          </Field>
        </div>
        <div className="px-6 pb-6 flex gap-3">
          <Button variant="secondary" onClick={onClose} fullWidth>Cancel</Button>
          <Button onClick={save} loading={busy} fullWidth>Reset Password</Button>
        </div>
      </div>
    </div>
  );
}

// ── Notification Route types ──────────────────────────────────────────────────
interface NotifRoute {
  id: number;
  trigger_event: string;
  notify_type: string;
  notify_value: string | null;
  same_department_only: boolean;
  description: string | null;
  priority: number;
  is_active: boolean;
  created_at: string;
}

const NOTIFY_TYPE_LABELS: Record<string, string> = {
  reporting_authority: "Reporting Authority",
  role: "By Role",
  employee: "Specific Employee",
};

const EVENT_LABELS: Record<string, string> = {
  approval_submitted: "Approval Submitted",
  approved: "Request Approved",
  rejected: "Request Rejected",
};

// ── Notification Routing Panel ────────────────────────────────────────────────
function NotificationRoutingPanel() {
  const [routes, setRoutes] = useState<NotifRoute[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<number | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [err, setErr] = useState('');
  const [success, setSuccess] = useState('');

  const [form, setForm] = useState({
    trigger_event: 'approval_submitted',
    notify_type: 'reporting_authority',
    notify_value: '',
    same_department_only: false,
    description: '',
    priority: 10,
    is_active: true,
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/notification-routes');
      setRoutes(r.data);
    } catch { setErr('Failed to load routes'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const toast = (msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(''), 3000); };

  const toggleActive = async (route: NotifRoute) => {
    setBusy(route.id);
    try {
      await api.patch(`/notification-routes/${route.id}`, { is_active: !route.is_active });
      toast(route.is_active ? 'Route disabled' : 'Route enabled');
      void load();
    } catch { setErr('Failed to update route'); }
    finally { setBusy(null); }
  };

  const deleteRoute = async (route: NotifRoute) => {
    if (!confirm('Delete this notification route?')) return;
    setBusy(route.id);
    try {
      await api.delete(`/notification-routes/${route.id}`);
      toast('Route deleted');
      void load();
    } catch { setErr('Failed to delete route'); }
    finally { setBusy(null); }
  };

  const addRoute = async () => {
    try {
      await api.post('/notification-routes', {
        ...form,
        notify_value: form.notify_value || null,
        description: form.description || null,
      });
      toast('Route added');
      setShowAdd(false);
      setForm({ trigger_event: 'approval_submitted', notify_type: 'reporting_authority', notify_value: '', same_department_only: false, description: '', priority: 10, is_active: true });
      void load();
    } catch (e: any) { setErr(e?.response?.data?.detail || 'Failed to add route'); }
  };

  const set = (k: string) => (v: string | boolean | number) =>
    setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="space-y-4">
      {err && <Alert variant="error" onClose={() => setErr('')}>{err}</Alert>}
      {success && <Alert variant="success">{success}</Alert>}

      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Notification Routing Rules</p>
          <p className="text-xs mt-0.5" style={{ color: 'var(--t2)' }}>
            Define who receives notifications for each event. Rules are applied in priority order.
          </p>
        </div>
        <Button size="sm" onClick={() => setShowAdd(s => !s)}>
          <Plus className="w-3.5 h-3.5" /> Add Rule
        </Button>
      </div>

      {/* Add rule form */}
      {showAdd && (
        <div className="rounded-2xl p-5 space-y-4" style={{ background: 'var(--s2)', border: '1px solid var(--b2)' }}>
          <p className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--t2)' }}>New Routing Rule</p>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Trigger Event">
              <Select value={form.trigger_event} onChange={set('trigger_event')}
                options={['approval_submitted', 'approved', 'rejected']} />
            </Field>
            <Field label="Notify Type">
              <Select value={form.notify_type} onChange={set('notify_type')}
                options={['reporting_authority', 'role', 'employee']} />
            </Field>
            {form.notify_type !== 'reporting_authority' && (
              <Field label={form.notify_type === 'role' ? 'Role Name' : 'Employee ID'}>
                <Input value={form.notify_value} onChange={v => set('notify_value')(v)}
                  placeholder={form.notify_type === 'role' ? 'e.g. Lead Engineer' : 'e.g. EMP-001'} />
              </Field>
            )}
            <Field label="Priority (lower = first)">
              <input type="number" value={form.priority}
                onChange={e => set('priority')(parseInt(e.target.value) || 10)}
                className="w-full px-3 py-2.5 rounded-xl text-sm"
                style={{ background: 'var(--s1)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
            </Field>
            <Field label="Description (optional)">
              <Input value={form.description} onChange={v => set('description')(v)}
                placeholder="e.g. Notify dept lead for new requests" />
            </Field>
            <Field label="Filters">
              <label className="flex items-center gap-2 mt-2 cursor-pointer">
                <input type="checkbox" checked={form.same_department_only}
                  onChange={e => set('same_department_only')(e.target.checked)}
                  className="rounded" />
                <span className="text-xs" style={{ color: 'var(--t1)' }}>Same department only</span>
              </label>
            </Field>
          </div>
          <div className="flex gap-3">
            <Button variant="secondary" size="sm" onClick={() => setShowAdd(false)}>Cancel</Button>
            <Button size="sm" onClick={addRoute}>Save Rule</Button>
          </div>
        </div>
      )}

      {/* Routes table */}
      <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        {loading ? (
          <div className="flex items-center justify-center py-12 gap-2" style={{ color: 'var(--t2)' }}>
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : routes.length === 0 ? (
          <div className="text-center py-12" style={{ color: 'var(--t2)' }}>
            <Route className="w-8 h-8 mx-auto mb-2 opacity-30" />
            <p className="text-sm">No routing rules yet</p>
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--b1)' }}>
                {['Pri', 'Event', 'Notify Type', 'Recipient', 'Dept Filter', 'Description', 'Status', 'Actions'].map(h => (
                  <th key={h} className="text-left px-4 py-3 font-semibold uppercase tracking-wider"
                    style={{ color: 'var(--t2)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {routes.map((r, i) => (
                <tr key={r.id} style={{ borderBottom: i < routes.length - 1 ? '1px solid var(--b1)' : 'none', opacity: r.is_active ? 1 : 0.5 }}>
                  <td className="px-4 py-3 font-mono font-bold" style={{ color: 'var(--em-lt)' }}>{r.priority}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold"
                      style={{ background: 'var(--em-dim)', color: 'var(--em-lt)', border: '1px solid rgba(59,130,246,0.3)' }}>
                      {EVENT_LABELS[r.trigger_event] || r.trigger_event}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-medium" style={{ color: 'var(--t0)' }}>
                    {NOTIFY_TYPE_LABELS[r.notify_type] || r.notify_type}
                  </td>
                  <td className="px-4 py-3" style={{ color: 'var(--t1)' }}>
                    {r.notify_value || <span style={{ color: 'var(--t2)' }}>— (auto)</span>}
                  </td>
                  <td className="px-4 py-3">
                    {r.same_department_only
                      ? <span style={{ color: '#4ade80' }}>Same dept</span>
                      : <span style={{ color: 'var(--t2)' }}>All</span>}
                  </td>
                  <td className="px-4 py-3 max-w-[200px] truncate" style={{ color: 'var(--t2)' }}>
                    {r.description || '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold"
                      style={{
                        background: r.is_active ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)',
                        color: r.is_active ? '#4ade80' : 'var(--rose)',
                        border: `1px solid ${r.is_active ? 'rgba(74,222,128,0.3)' : 'rgba(248,113,113,0.3)'}`,
                      }}>
                      {r.is_active ? '● Active' : '○ Disabled'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button title={r.is_active ? 'Disable' : 'Enable'} onClick={() => toggleActive(r)}
                        disabled={busy === r.id}
                        className="p-1.5 rounded-lg hover:opacity-80"
                        style={{ background: r.is_active ? 'rgba(248,113,113,0.1)' : 'rgba(74,222,128,0.1)', color: r.is_active ? 'var(--rose)' : '#4ade80' }}>
                        {busy === r.id ? <Loader2 className="w-3 h-3 animate-spin" /> : r.is_active ? <BellOff className="w-3 h-3" /> : <Bell className="w-3 h-3" />}
                      </button>
                      <button title="Delete" onClick={() => deleteRoute(r)}
                        disabled={busy === r.id}
                        className="p-1.5 rounded-lg hover:opacity-80"
                        style={{ background: 'rgba(248,113,113,0.08)', color: 'var(--rose)' }}>
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Legend */}
      <div className="rounded-xl p-4 space-y-2" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        <p className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--t2)' }}>How routing works</p>
        <div className="grid grid-cols-3 gap-3 text-[11px]" style={{ color: 'var(--t2)' }}>
          <div><span className="font-semibold" style={{ color: 'var(--t1)' }}>Reporting Authority</span> — Sends to the direct manager set on the submitter's employee profile.</div>
          <div><span className="font-semibold" style={{ color: 'var(--t1)' }}>By Role</span> — Sends to all active users with the specified role. Enable "Same dept" to restrict to submitter's department.</div>
          <div><span className="font-semibold" style={{ color: 'var(--t1)' }}>Specific Employee</span> — Always sends to one named employee by their Employee ID.</div>
        </div>
      </div>
    </div>
  );
}

// ── Role badge ─────────────────────────────────────────────────────────────────
const roleColors: Record<string, string> = {
  'Admin': '#f97316', 'Reviewer': '#a78bfa', 'Lead Engineer': 'var(--em)',
  'Senior Engineer': '#4ade80', 'Engineer': 'var(--gold)', 'GET': 'var(--sky)', 'Read Only': 'var(--t2)',
};

// ── Main Component ─────────────────────────────────────────────────────────────
export default function AdminManagement() {
  const [tab, setTab] = useState<'users' | 'routing'>('users');
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [modal, setModal] = useState<'create' | 'edit' | 'reset' | null>(null);
  const [selected, setSelected] = useState<AdminUser | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [success, setSuccess] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get('/admin/users');
      setUsers(res.data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to load users');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const toast = (msg: string) => { setSuccess(msg); setTimeout(() => setSuccess(''), 3000); };

  const toggleStatus = async (u: AdminUser) => {
    setBusy(u.employee_id);
    try {
      const action = u.status === 'active' ? 'disable' : 'enable';
      await api.post(`/admin/users/${u.employee_id}/${action}`);
      toast(`User ${u.status === 'active' ? 'disabled' : 'enabled'} successfully`);
      load();
    } catch (e: any) { setError(e?.response?.data?.detail || 'Action failed'); }
    finally { setBusy(null); }
  };

  const deleteUser = async (u: AdminUser) => {
    if (!confirm(`Delete user ${u.employee_name}? This cannot be undone.`)) return;
    setBusy(u.employee_id + '-del');
    try {
      await api.delete(`/admin/users/${u.employee_id}`);
      toast('User deleted');
      load();
    } catch (e: any) { setError(e?.response?.data?.detail || 'Delete failed'); }
    finally { setBusy(null); }
  };

  const filtered = users.filter(u =>
    u.employee_name.toLowerCase().includes(search.toLowerCase()) ||
    u.employee_id.toLowerCase().includes(search.toLowerCase()) ||
    u.role.toLowerCase().includes(search.toLowerCase()) ||
    u.department.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <PageHeader
        icon={ShieldCheck}
        title="Admin Management"
        description="Create and manage engineering team users, roles, and access control"
      />

      {/* Tab bar */}
      <div className="flex gap-1 p-1 rounded-xl w-fit" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        {([['users', ShieldCheck, 'Users'], ['routing', Bell, 'Notification Routing']] as const).map(([key, Icon, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition-all"
            style={{
              background: tab === key ? 'var(--em-dim)' : 'transparent',
              color: tab === key ? 'var(--em-lt)' : 'var(--t2)',
              border: tab === key ? '1px solid rgba(59,130,246,0.3)' : '1px solid transparent',
            }}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
          </button>
        ))}
      </div>

      {tab === 'routing' && <NotificationRoutingPanel />}

      {tab === 'users' && <>
      {error && <Alert variant="error" onClose={() => setError('')}>{error}</Alert>}
      {success && <Alert variant="success">{success}</Alert>}

      {/* Controls */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: 'var(--t2)' }} />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search by name, ID, role, or department…"
            className="w-full pl-9 pr-4 py-2.5 rounded-xl text-sm"
            style={{ background: 'var(--s2)', border: '1px solid var(--b1)', color: 'var(--t0)', outline: 'none' }} />
        </div>
        <Button variant="ghost" size="sm" onClick={load}>
          <RefreshCw className="w-3.5 h-3.5" />
        </Button>
        <Button onClick={() => setModal('create')}>
          <Plus className="w-3.5 h-3.5" /> Create User
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-3">
        {[
          ['Total Users', users.length, 'var(--em)'],
          ['Active', users.filter(u => u.status === 'active').length, '#4ade80'],
          ['Disabled', users.filter(u => u.status === 'disabled').length, 'var(--rose)'],
          ['Admins', users.filter(u => u.role === 'Admin').length, '#f97316'],
        ].map(([label, count, color]) => (
          <div key={label as string} className="rounded-2xl p-4" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
            <p className="text-2xl font-black mb-0.5" style={{ color: color as string }}>{count}</p>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>{label}</p>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        <div className="px-5 py-4 flex items-center gap-2" style={{ borderBottom: '1px solid var(--b1)' }}>
          <ShieldCheck className="w-4 h-4" style={{ color: 'var(--em)' }} />
          <span className="text-sm font-bold" style={{ color: 'var(--t0)' }}>Engineering Users</span>
          <span className="ml-auto text-xs" style={{ color: 'var(--t2)' }}>{filtered.length} user(s)</span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16 gap-2" style={{ color: 'var(--t2)' }}>
            <Loader2 className="w-5 h-5 animate-spin" /> Loading…
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16">
            <User className="w-10 h-10 mx-auto mb-3 opacity-30" style={{ color: 'var(--t2)' }} />
            <p className="text-sm" style={{ color: 'var(--t2)' }}>
              {users.length === 0 ? 'No users yet — create your first admin user' : 'No users match your search'}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--b1)' }}>
                  {['Employee ID', 'Name', 'Designation', 'Department', 'Email', 'Role', 'Status', 'Last Login', 'Actions'].map(h => (
                    <th key={h} className="text-left px-4 py-3 font-semibold uppercase tracking-wider"
                      style={{ color: 'var(--t2)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((u, i) => (
                  <tr key={u.id} style={{ borderBottom: i < filtered.length - 1 ? '1px solid var(--b1)' : 'none', background: i % 2 === 0 ? 'transparent' : 'var(--s3)' }}>
                    <td className="px-4 py-3 font-mono font-bold" style={{ color: 'var(--em-lt)' }}>{u.employee_id}</td>
                    <td className="px-4 py-3 font-semibold" style={{ color: 'var(--t0)' }}>{u.employee_name}</td>
                    <td className="px-4 py-3" style={{ color: 'var(--t1)' }}>{u.designation}</td>
                    <td className="px-4 py-3" style={{ color: 'var(--t1)' }}>{u.department}</td>
                    <td className="px-4 py-3" style={{ color: 'var(--t2)' }}>{u.email_id}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold"
                        style={{ background: `${roleColors[u.role] || 'var(--t2)'}18`, color: roleColors[u.role] || 'var(--t2)', border: `1px solid ${roleColors[u.role] || 'var(--t2)'}30` }}>
                        {u.role}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold"
                        style={{ background: u.status === 'active' ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)', color: u.status === 'active' ? '#4ade80' : 'var(--rose)', border: `1px solid ${u.status === 'active' ? 'rgba(74,222,128,0.3)' : 'rgba(248,113,113,0.3)'}` }}>
                        {u.status === 'active' ? '● Active' : '○ Disabled'}
                      </span>
                    </td>
                    <td className="px-4 py-3" style={{ color: 'var(--t2)' }}>
                      {u.last_login ? new Date(u.last_login).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button title="Edit" onClick={() => { setSelected(u); setModal('edit'); }}
                          className="p-1.5 rounded-lg hover:opacity-80" style={{ background: 'var(--em-dim)', color: 'var(--em-lt)' }}>
                          <Edit2 className="w-3 h-3" />
                        </button>
                        <button title="Reset Password" onClick={() => { setSelected(u); setModal('reset'); }}
                          className="p-1.5 rounded-lg hover:opacity-80" style={{ background: 'rgba(245,158,11,0.1)', color: 'var(--gold)' }}>
                          <KeyRound className="w-3 h-3" />
                        </button>
                        <button title={u.status === 'active' ? 'Disable' : 'Enable'} onClick={() => toggleStatus(u)}
                          disabled={busy === u.employee_id}
                          className="p-1.5 rounded-lg hover:opacity-80"
                          style={{ background: u.status === 'active' ? 'rgba(248,113,113,0.1)' : 'rgba(74,222,128,0.1)', color: u.status === 'active' ? 'var(--rose)' : '#4ade80' }}>
                          {busy === u.employee_id ? <Loader2 className="w-3 h-3 animate-spin" /> : u.status === 'active' ? <UserX className="w-3 h-3" /> : <UserCheck className="w-3 h-3" />}
                        </button>
                        <button title="Delete" onClick={() => deleteUser(u)}
                          disabled={busy === u.employee_id + '-del'}
                          className="p-1.5 rounded-lg hover:opacity-80" style={{ background: 'rgba(248,113,113,0.08)', color: 'var(--rose)' }}>
                          {busy === u.employee_id + '-del' ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modals */}
      {modal === 'create' && (
        <UserModal user={null} onClose={() => setModal(null)} onSave={() => { load(); toast('User created successfully'); }} />
      )}
      {modal === 'edit' && selected && (
        <UserModal user={selected} onClose={() => { setModal(null); setSelected(null); }} onSave={() => { load(); toast('User updated successfully'); }} />
      )}
      {modal === 'reset' && selected && (
        <ResetPasswordModal user={selected} onClose={() => { setModal(null); setSelected(null); }} onSave={() => toast('Password reset successfully')} />
      )}
      </>}
    </div>
  );
}
