import React, { useState, useEffect, useCallback } from 'react';
import api from '@/services/api';
import IDCReviewRoom from './idc/IDCReviewRoom';

export type { IDCSessionSummary };

// ── Types ──────────────────────────────────────────────────────────────────────
interface IDCSessionSummary {
  id: number;
  idc_number: string;
  project_name: string;
  document_number: string;
  document_title: string;
  revision_number: string;
  document_category: string;
  due_date: string;
  status: 'active' | 'frozen';
  created_by_name: string;
  created_at: string;
  frozen_at: string | null;
  frozen_by_name: string | null;
  disciplines: string[];
  approvals: Record<string, { employee_name: string; approved_at: string }>;
  all_approved: boolean;
  comment_count: number;
  documents: { id: number; original_filename: string; file_type: string; file_size?: number }[];
}

const DISCIPLINES = [
  'Civil Engineering',
  'Mechanical Engineering',
  'Electrical Engineering',
  'Piping Engineering',
  'Instrumentation Engineering',
  'Technical Coordinator',
];

const DISC_COLOR: Record<string, string> = {
  'Civil Engineering': '#8B4513',
  'Mechanical Engineering': '#1E90FF',
  'Electrical Engineering': '#FF8C00',
  'Piping Engineering': '#9932CC',
  'Instrumentation Engineering': '#228B22',
  'Technical Coordinator': '#555555',
};

const CATEGORIES = [
  'Basic/P&ID/Layout',
  'Mechanical/Process',
  'Electrical',
  'Instrumentation',
  'Civil/Structural',
  'Procurement/Vendor',
  'Safety',
  'QA/QC',
  'General',
];

// ── Status badge ───────────────────────────────────────────────────────────────
const StatusBadge: React.FC<{ status: string }> = ({ status }) => (
  <span style={{
    padding: '2px 10px', borderRadius: 12, fontSize: 11, fontWeight: 700,
    background: status === 'frozen' ? '#1a3a5c' : '#1a4a2a',
    color: status === 'frozen' ? '#60b4ff' : '#4ade80',
    border: `1px solid ${status === 'frozen' ? '#2563eb' : '#16a34a'}`,
  }}>
    {status === 'frozen' ? '❄ Frozen' : '● Active'}
  </span>
);

// ── Discipline chips ───────────────────────────────────────────────────────────
const DisciplineChips: React.FC<{ disciplines: string[]; approvals: Record<string, any> }> = ({ disciplines, approvals }) => (
  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
    {disciplines.map(d => (
      <span key={d} style={{
        padding: '2px 8px', borderRadius: 10, fontSize: 10, fontWeight: 600,
        background: approvals[d] ? '#14532d' : '#1e293b',
        color: approvals[d] ? '#4ade80' : DISC_COLOR[d] || '#aaa',
        border: `1px solid ${approvals[d] ? '#16a34a' : DISC_COLOR[d] || '#555'}`,
      }}>
        {approvals[d] ? '✓ ' : ''}{d.replace(' Engineering', '')}
      </span>
    ))}
  </div>
);

// ── Create Session Modal ───────────────────────────────────────────────────────
const CreateSessionModal: React.FC<{ onClose: () => void; onCreated: (s: IDCSessionSummary) => void }> = ({ onClose, onCreated }) => {
  const [form, setForm] = useState({
    idc_number: '', project_name: '', document_number: '',
    document_title: '', revision_number: 'R0', document_category: CATEGORIES[0],
    due_date: '', remarks: '', employee_id: '', password: '',
  });
  const [selectedDisc, setSelectedDisc] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const toggleDisc = (d: string) =>
    setSelectedDisc(prev => prev.includes(d) ? prev.filter(x => x !== d) : [...prev, d]);

  const submit = async () => {
    if (!form.idc_number || !form.project_name || !form.document_number || !form.document_title) {
      setError('Fill all required fields'); return;
    }
    if (selectedDisc.length === 0) { setError('Select at least one discipline'); return; }
    if (!form.employee_id || !form.password) { setError('Employee ID and Password required'); return; }
    setLoading(true); setError('');
    try {
      const fd = new FormData();
      Object.entries(form).forEach(([k, v]) => fd.append(k, v));
      fd.append('disciplines', JSON.stringify(selectedDisc));
      files.forEach(f => fd.append('files', f));
      const res = await api.post('/idc/sessions', fd);
      onCreated(res.data);
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: any) => d.msg).join(', ') : 'Failed to create session');
    } finally { setLoading(false); }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: '#0d1b2a', border: '1px solid #1e3a5f', borderRadius: 12, padding: 32, width: 640, maxHeight: '90vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
          <h2 style={{ color: '#e2e8f0', margin: 0, fontSize: 20 }}>Create IDC Session</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#64748b', fontSize: 20, cursor: 'pointer' }}>✕</button>
        </div>

        {error && <div style={{ background: '#451a1a', border: '1px solid #dc2626', borderRadius: 8, padding: 12, marginBottom: 16, color: '#fca5a5', fontSize: 13 }}>{error}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          {[
            ['IDC Number *', 'idc_number', 'text', 'IDC-2025-001'],
            ['Project Name *', 'project_name', 'text', 'WABAG Phase-II'],
            ['Document Number *', 'document_number', 'text', 'P&ID-001'],
            ['Document Title *', 'document_title', 'text', 'P&ID of Aeration Basin'],
            ['Revision Number', 'revision_number', 'text', 'R0'],
            ['Due Date', 'due_date', 'date', ''],
          ].map(([label, key, type, placeholder]) => (
            <div key={key}>
              <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 4 }}>{label}</label>
              <input
                type={type as string}
                placeholder={placeholder as string}
                value={(form as any)[key]}
                onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '8px 10px', color: '#e2e8f0', fontSize: 13, boxSizing: 'border-box' }}
              />
            </div>
          ))}
        </div>

        <div style={{ marginTop: 14 }}>
          <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 4 }}>Document Category</label>
          <select value={form.document_category} onChange={e => setForm(f => ({ ...f, document_category: e.target.value }))}
            style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '8px 10px', color: '#e2e8f0', fontSize: 13 }}>
            {CATEGORIES.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>

        <div style={{ marginTop: 14 }}>
          <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 6 }}>Disciplines *</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {DISCIPLINES.map(d => (
              <button key={d} onClick={() => toggleDisc(d)}
                style={{
                  padding: '5px 12px', borderRadius: 20, fontSize: 12, cursor: 'pointer', fontWeight: 600,
                  background: selectedDisc.includes(d) ? DISC_COLOR[d] : '#1e293b',
                  color: selectedDisc.includes(d) ? '#fff' : '#94a3b8',
                  border: `1px solid ${selectedDisc.includes(d) ? DISC_COLOR[d] : '#334155'}`,
                }}>
                {selectedDisc.includes(d) ? '✓ ' : ''}{d}
              </button>
            ))}
          </div>
        </div>

        <div style={{ marginTop: 14 }}>
          <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 4 }}>Upload Documents (PDF / DWG / DXF)</label>
          <input type="file" multiple accept=".pdf,.dwg,.dxf,.dgn,.zip"
            onChange={e => setFiles(Array.from(e.target.files || []))}
            style={{ color: '#94a3b8', fontSize: 12 }} />
          {files.length > 0 && <div style={{ color: '#60b4ff', fontSize: 11, marginTop: 4 }}>{files.length} file(s) selected</div>}
        </div>

        <div style={{ marginTop: 14 }}>
          <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 4 }}>Remarks</label>
          <textarea value={form.remarks} onChange={e => setForm(f => ({ ...f, remarks: e.target.value }))} rows={2}
            style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '8px 10px', color: '#e2e8f0', fontSize: 13, boxSizing: 'border-box', resize: 'vertical' }} />
        </div>

        <div style={{ marginTop: 20, padding: 16, background: '#0f172a', borderRadius: 8, border: '1px solid #1e3a5f' }}>
          <div style={{ fontSize: 12, color: '#64748b', marginBottom: 10 }}>Authenticate to create session</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 4 }}>Employee ID</label>
              <input type="text" value={form.employee_id} onChange={e => setForm(f => ({ ...f, employee_id: e.target.value }))}
                style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '8px 10px', color: '#e2e8f0', fontSize: 13, boxSizing: 'border-box' }} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 4 }}>Password</label>
              <input type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '8px 10px', color: '#e2e8f0', fontSize: 13, boxSizing: 'border-box' }} />
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 12, marginTop: 24, justifyContent: 'flex-end' }}>
          <button onClick={onClose} disabled={loading}
            style={{ padding: '10px 24px', background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#94a3b8', cursor: 'pointer', fontSize: 13 }}>
            Cancel
          </button>
          <button onClick={submit} disabled={loading}
            style={{ padding: '10px 24px', background: '#1e40af', border: 'none', borderRadius: 8, color: '#fff', cursor: loading ? 'wait' : 'pointer', fontSize: 13, fontWeight: 600 }}>
            {loading ? 'Creating...' : 'Create IDC Session'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ── Delete confirm modal ────────────────────────────────────────────────────────
const DeleteModal: React.FC<{ session: IDCSessionSummary; onClose: () => void; onDeleted: () => void }> = ({ session, onClose, onDeleted }) => {
  const [empId, setEmpId] = useState('');
  const [pw, setPw] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const doDelete = async () => {
    setLoading(true); setError('');
    try {
      await api.delete(`/idc/sessions/${session.id}`, { params: { employee_id: empId, password: pw } });
      onDeleted();
    } catch (e: any) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to delete');
    } finally { setLoading(false); }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 2000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: '#0d1b2a', border: '1px solid #dc2626', borderRadius: 12, padding: 28, width: 400 }}>
        <h3 style={{ color: '#fca5a5', margin: '0 0 8px' }}>Delete IDC Session?</h3>
        <p style={{ color: '#94a3b8', fontSize: 13, margin: '0 0 16px' }}>
          <strong style={{ color: '#e2e8f0' }}>{session.idc_number}</strong> — {session.document_title}<br />
          This will permanently delete all comments, annotations and uploaded files.
        </p>
        {error && <div style={{ color: '#fca5a5', fontSize: 12, marginBottom: 12, background: '#450a0a', padding: 8, borderRadius: 6 }}>{error}</div>}
        <input placeholder="Employee ID" value={empId} onChange={e => setEmpId(e.target.value)}
          style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '8px 10px', color: '#e2e8f0', fontSize: 13, marginBottom: 8, boxSizing: 'border-box' }} />
        <input type="password" placeholder="Password" value={pw} onChange={e => setPw(e.target.value)}
          style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '8px 10px', color: '#e2e8f0', fontSize: 13, marginBottom: 16, boxSizing: 'border-box' }} />
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '8px 18px', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 13 }}>Cancel</button>
          <button onClick={doDelete} disabled={loading || !empId || !pw}
            style={{ padding: '8px 18px', background: '#dc2626', border: 'none', borderRadius: 6, color: '#fff', cursor: loading ? 'wait' : 'pointer', fontSize: 13, fontWeight: 600 }}>
            {loading ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
};

// ── Session Card ───────────────────────────────────────────────────────────────
const SessionCard: React.FC<{ session: IDCSessionSummary; onOpen: () => void; onDelete: () => void }> = ({ session, onOpen, onDelete }) => {
  const approvedCount = Object.keys(session.approvals).length;
  const totalDisc = session.disciplines.length;
  const pct = totalDisc > 0 ? Math.round((approvedCount / totalDisc) * 100) : 0;
  const [showDelete, setShowDelete] = useState(false);

  return (
    <>
    {showDelete && <DeleteModal session={session} onClose={() => setShowDelete(false)} onDeleted={() => { setShowDelete(false); onDelete(); }} />}
    <div onClick={onOpen} style={{
      background: '#0d1b2a', border: '1px solid #1e3a5f', borderRadius: 10, padding: 18,
      cursor: 'pointer', transition: 'border-color 0.2s', position: 'relative',
    }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = '#3b82f6')}
      onMouseLeave={e => (e.currentTarget.style.borderColor = '#1e3a5f')}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#60b4ff' }}>{session.idc_number}</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#e2e8f0', marginTop: 2 }}>{session.document_title}</div>
          <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{session.document_number} | Rev {session.revision_number}</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <StatusBadge status={session.status} />
          <button onClick={e => { e.stopPropagation(); setShowDelete(true); }}
            style={{ padding: '3px 8px', background: '#450a0a', border: '1px solid #dc2626', borderRadius: 6, color: '#fca5a5', cursor: 'pointer', fontSize: 11 }}>
            ✕
          </button>
        </div>
      </div>

      <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 8 }}>
        {session.project_name} · {session.document_category}
      </div>

      <DisciplineChips disciplines={session.disciplines} approvals={session.approvals} />

      <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 16, fontSize: 11, color: '#64748b' }}>
          <span>💬 {session.comment_count} comments</span>
          <span>📎 {session.documents.length} docs</span>
          {session.due_date && <span>📅 Due {session.due_date}</span>}
        </div>
        <div style={{ fontSize: 11, color: '#64748b' }}>
          Approvals: <span style={{ color: pct === 100 ? '#4ade80' : '#f59e0b', fontWeight: 600 }}>{approvedCount}/{totalDisc}</span>
        </div>
      </div>

      {/* progress bar */}
      <div style={{ marginTop: 8, height: 4, background: '#1e293b', borderRadius: 2 }}>
        <div style={{ height: '100%', width: `${pct}%`, background: pct === 100 ? '#16a34a' : '#2563eb', borderRadius: 2, transition: 'width 0.3s' }} />
      </div>
    </div>
    </>
  );
};

// ── Main IDC Dashboard ─────────────────────────────────────────────────────────
const IDCModule: React.FC = () => {
  const [sessions, setSessions] = useState<IDCSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [activeSession, setActiveSession] = useState<IDCSessionSummary | null>(null);
  const [search, setSearch] = useState('');
  const [filterStatus, setFilterStatus] = useState<'all' | 'active' | 'frozen'>('all');

  const loadSessions = useCallback(async () => {
    try {
      const res = await api.get('/idc/sessions');
      setSessions(res.data);
    } catch (e) {
      console.error('Failed to load IDC sessions', e);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  if (activeSession) {
    return (
      <IDCReviewRoom
        session={activeSession}
        onBack={() => { setActiveSession(null); loadSessions(); }}
      />
    );
  }

  const filtered = sessions.filter(s => {
    const matchSearch = !search || [s.idc_number, s.project_name, s.document_title, s.document_number]
      .some(v => v.toLowerCase().includes(search.toLowerCase()));
    const matchStatus = filterStatus === 'all' || s.status === filterStatus;
    return matchSearch && matchStatus;
  });

  const activeCount = sessions.filter(s => s.status === 'active').length;
  const frozenCount = sessions.filter(s => s.status === 'frozen').length;
  const totalComments = sessions.reduce((acc, s) => acc + s.comment_count, 0);

  return (
    <div style={{ padding: '24px', maxWidth: 1200, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 26, fontWeight: 800, color: '#e2e8f0', margin: 0 }}>
            Inter Discipline Check
          </h1>
          <p style={{ color: '#64748b', fontSize: 13, marginTop: 4 }}>
            Real-time multi-discipline document review and annotation
          </p>
        </div>
        <button onClick={() => setShowCreate(true)} style={{
          padding: '10px 20px', background: 'linear-gradient(135deg, #1e40af, #2563eb)', border: 'none',
          borderRadius: 8, color: '#fff', cursor: 'pointer', fontSize: 13, fontWeight: 600,
          boxShadow: '0 4px 12px rgba(37,99,235,0.3)',
        }}>
          + New IDC Session
        </button>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
        {[
          { label: 'Active Sessions', value: activeCount, color: '#4ade80', icon: '●' },
          { label: 'Frozen Sessions', value: frozenCount, color: '#60b4ff', icon: '❄' },
          { label: 'Total Comments', value: totalComments, color: '#f59e0b', icon: '💬' },
        ].map(({ label, value, color, icon }) => (
          <div key={label} style={{ background: '#0d1b2a', border: '1px solid #1e3a5f', borderRadius: 10, padding: '16px 20px' }}>
            <div style={{ fontSize: 28, fontWeight: 800, color }}>{icon} {value}</div>
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
        <input
          type="text" placeholder="Search by IDC number, project, document..."
          value={search} onChange={e => setSearch(e.target.value)}
          style={{ flex: 1, background: '#0d1b2a', border: '1px solid #1e3a5f', borderRadius: 8, padding: '9px 14px', color: '#e2e8f0', fontSize: 13 }}
        />
        {(['all', 'active', 'frozen'] as const).map(f => (
          <button key={f} onClick={() => setFilterStatus(f)}
            style={{
              padding: '9px 18px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer',
              background: filterStatus === f ? '#1e40af' : '#0d1b2a',
              border: `1px solid ${filterStatus === f ? '#2563eb' : '#1e3a5f'}`,
              color: filterStatus === f ? '#fff' : '#64748b',
            }}>
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {/* Session grid */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#64748b' }}>Loading IDC sessions...</div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#64748b' }}>
          {sessions.length === 0 ? 'No IDC sessions yet. Create your first one!' : 'No sessions match your filter.'}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 16 }}>
          {filtered.map(s => (
            <SessionCard key={s.id} session={s} onOpen={() => setActiveSession(s)} onDelete={loadSessions} />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateSessionModal
          onClose={() => setShowCreate(false)}
          onCreated={s => { setSessions(prev => [s, ...prev]); setShowCreate(false); setActiveSession(s); }}
        />
      )}
    </div>
  );
};

export default IDCModule;
