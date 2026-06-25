import React, { useState, useEffect, useRef, useCallback } from 'react';
import * as pdfjsLib from 'pdfjs-dist';
import api from '@/services/api';

// Set worker — use CDN for pdfjs-dist 6.x
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.worker.min.mjs`;

// ── Types ──────────────────────────────────────────────────────────────────────
interface IDCSession {
  id: number;
  idc_number: string;
  project_name: string;
  document_number: string;
  document_title: string;
  revision_number: string;
  document_category: string;
  status: 'active' | 'frozen';
  disciplines: string[];
  approvals: Record<string, { employee_name: string; approved_at: string }>;
  all_approved: boolean;
  documents: { id: number; original_filename: string; file_type: string; file_size?: number }[];
  comment_count: number;
  frozen_by_name?: string | null;
  frozen_at?: string | null;
}

interface Annotation {
  id: number;
  ann_uuid: string;
  document_id: number;
  tool_type: string;
  page_number: number;
  x: number; y: number; width: number; height: number;
  data_json: any;
  color: string;
  author_emp: string; author_name: string; discipline: string;
  created_at: string;
}

interface Comment {
  id: number;
  comment_number: string;
  ann_uuid: string | null;
  page_number: number;
  author_emp: string; author_name: string; discipline: string;
  comment_text: string;
  priority: string; status: string; category: string;
  created_at: string;
  resolved_by?: string;
  resolved_at?: string;
  replies: { id: number; author_name: string; discipline: string; reply_text: string; created_at: string }[];
}

interface OnlineUser { emp_id: string; emp_name: string; discipline: string }

const DISC_COLOR: Record<string, string> = {
  'Civil Engineering': '#8B4513',
  'Mechanical Engineering': '#1E90FF',
  'Electrical Engineering': '#FF8C00',
  'Piping Engineering': '#9932CC',
  'Instrumentation Engineering': '#228B22',
  'Technical Coordinator': '#555555',
};

const PRIORITY_COLOR: Record<string, string> = {
  Critical: '#dc2626', High: '#f59e0b', Normal: '#3b82f6', Low: '#64748b',
};

const STATUS_COLOR: Record<string, string> = {
  Open: '#ef4444', 'Under Review': '#f59e0b', Resolved: '#22c55e',
  Closed: '#64748b', Rejected: '#dc2626', 'Need Clarification': '#a855f7',
};

// ── Auth Gate Modal ────────────────────────────────────────────────────────────
const AuthGate: React.FC<{ title: string; onAuth: (id: string, pw: string) => void; onClose: () => void; loading?: boolean; error?: string }> =
  ({ title, onAuth, onClose, loading, error }) => {
    const [id, setId] = useState('');
    const [pw, setPw] = useState('');
    return (
      <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 2000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ background: '#0d1b2a', border: '1px solid #1e3a5f', borderRadius: 12, padding: 28, width: 380 }}>
          <h3 style={{ color: '#e2e8f0', margin: '0 0 16px' }}>{title}</h3>
          {error && <div style={{ background: '#450a0a', border: '1px solid #dc2626', borderRadius: 6, padding: 10, marginBottom: 14, color: '#fca5a5', fontSize: 12 }}>{error}</div>}
          <input placeholder="Employee ID" value={id} onChange={e => setId(e.target.value)}
            style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '8px 10px', color: '#e2e8f0', fontSize: 13, marginBottom: 10, boxSizing: 'border-box' }} />
          <input type="password" placeholder="Password" value={pw} onChange={e => setPw(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && onAuth(id, pw)}
            style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '8px 10px', color: '#e2e8f0', fontSize: 13, marginBottom: 16, boxSizing: 'border-box' }} />
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button onClick={onClose} style={{ padding: '8px 18px', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 12 }}>Cancel</button>
            <button onClick={() => onAuth(id, pw)} disabled={loading}
              style={{ padding: '8px 18px', background: '#1e40af', border: 'none', borderRadius: 6, color: '#fff', cursor: loading ? 'wait' : 'pointer', fontSize: 12, fontWeight: 600 }}>
              {loading ? 'Verifying…' : 'Confirm'}
            </button>
          </div>
        </div>
      </div>
    );
  };

// ── Comment Card ───────────────────────────────────────────────────────────────
const CommentCard: React.FC<{
  comment: Comment;
  sessionId: number;
  sessionFrozen: boolean;
  onStatusChange: () => void;
  highlighted: boolean;
  onClick: () => void;
}> = ({ comment, sessionId, sessionFrozen, onStatusChange, highlighted, onClick }) => {
  const [showReply, setShowReply] = useState(false);
  const [replyText, setReplyText] = useState('');
  const [authGate, setAuthGate] = useState<'reply' | 'status' | null>(null);
  const [newStatus, setNewStatus] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleReply = async (empId: string, pw: string) => {
    setLoading(true); setError('');
    try {
      const fd = new FormData();
      fd.append('employee_id', empId); fd.append('password', pw); fd.append('reply_text', replyText);
      await api.post(`/api/idc/sessions/${sessionId}/comments/${comment.id}/reply`, fd);
      setReplyText(''); setShowReply(false); setAuthGate(null);
      onStatusChange();
    } catch (e: any) { setError(e.response?.data?.detail || 'Failed'); } finally { setLoading(false); }
  };

  const handleStatusChange = async (empId: string, pw: string) => {
    setLoading(true); setError('');
    try {
      const fd = new FormData();
      fd.append('employee_id', empId); fd.append('password', pw); fd.append('status', newStatus);
      await api.patch(`/api/idc/sessions/${sessionId}/comments/${comment.id}`, fd);
      setAuthGate(null); onStatusChange();
    } catch (e: any) { setError(e.response?.data?.detail || 'Failed'); } finally { setLoading(false); }
  };

  return (
    <div onClick={onClick} style={{
      background: highlighted ? '#0f2a45' : '#0a1628',
      border: `1px solid ${highlighted ? '#2563eb' : '#1e3a5f'}`,
      borderRadius: 8, padding: 12, marginBottom: 10, cursor: 'pointer',
      borderLeft: `3px solid ${DISC_COLOR[comment.discipline] || '#555'}`,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: '#60b4ff' }}>{comment.comment_number}</span>
          <span style={{ fontSize: 10, padding: '1px 7px', borderRadius: 10, background: '#1e293b', color: PRIORITY_COLOR[comment.priority] || '#aaa', fontWeight: 700 }}>{comment.priority}</span>
          <span style={{ fontSize: 10, padding: '1px 7px', borderRadius: 10, background: '#1e293b', color: STATUS_COLOR[comment.status] || '#aaa', fontWeight: 600 }}>{comment.status}</span>
        </div>
        <span style={{ fontSize: 10, color: '#475569' }}>Pg {comment.page_number}</span>
      </div>
      <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 4, fontStyle: 'italic' }}>{comment.category}</div>
      <div style={{ fontSize: 13, color: '#cbd5e1', lineHeight: 1.5, marginBottom: 8 }}>{comment.comment_text}</div>
      <div style={{ fontSize: 11, color: '#475569' }}>
        {comment.author_name} · {comment.discipline.replace(' Engineering', '')} · {new Date(comment.created_at).toLocaleDateString()}
      </div>

      {comment.replies.length > 0 && (
        <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #1e293b' }}>
          {comment.replies.map(r => (
            <div key={r.id} style={{ padding: '6px 8px', background: '#0f172a', borderRadius: 6, marginBottom: 4 }}>
              <div style={{ fontSize: 11, color: '#60b4ff', fontWeight: 600 }}>{r.author_name}</div>
              <div style={{ fontSize: 12, color: '#94a3b8' }}>{r.reply_text}</div>
            </div>
          ))}
        </div>
      )}

      {!sessionFrozen && (
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }} onClick={e => e.stopPropagation()}>
          <button onClick={() => setShowReply(!showReply)}
            style={{ fontSize: 11, padding: '3px 10px', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, color: '#94a3b8', cursor: 'pointer' }}>
            ↩ Reply
          </button>
          <select value="" onChange={e => { if (e.target.value) { setNewStatus(e.target.value); setAuthGate('status'); } }}
            style={{ fontSize: 11, padding: '3px 8px', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, color: '#94a3b8', cursor: 'pointer' }}>
            <option value="">Change status...</option>
            {['Open', 'Under Review', 'Resolved', 'Rejected', 'Need Clarification', 'Closed'].map(s => <option key={s}>{s}</option>)}
          </select>
        </div>
      )}

      {showReply && !sessionFrozen && (
        <div style={{ marginTop: 8 }} onClick={e => e.stopPropagation()}>
          <textarea value={replyText} onChange={e => setReplyText(e.target.value)} rows={2} placeholder="Write reply..."
            style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '6px 8px', color: '#e2e8f0', fontSize: 12, boxSizing: 'border-box', resize: 'none' }} />
          <button onClick={() => setAuthGate('reply')} disabled={!replyText.trim()}
            style={{ marginTop: 6, padding: '5px 14px', background: '#1e40af', border: 'none', borderRadius: 6, color: '#fff', cursor: 'pointer', fontSize: 11 }}>
            Post Reply
          </button>
        </div>
      )}

      {authGate === 'reply' && (
        <AuthGate title="Post Reply" onClose={() => setAuthGate(null)} onAuth={handleReply} loading={loading} error={error} />
      )}
      {authGate === 'status' && (
        <AuthGate title={`Mark as ${newStatus}`} onClose={() => setAuthGate(null)} onAuth={handleStatusChange} loading={loading} error={error} />
      )}
    </div>
  );
};

// ── Add Comment Form ───────────────────────────────────────────────────────────
const AddCommentForm: React.FC<{ sessionId: number; annUuid?: string; page: number; onAdded: () => void; onClose: () => void }> =
  ({ sessionId, annUuid, page, onAdded, onClose }) => {
    const [form, setForm] = useState({ employee_id: '', password: '', comment_text: '', priority: 'Normal', category: 'General' });
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const submit = async () => {
      if (!form.comment_text.trim()) { setError('Comment text required'); return; }
      setLoading(true); setError('');
      try {
        const fd = new FormData();
        Object.entries(form).forEach(([k, v]) => fd.append(k, v));
        fd.append('page_number', String(page));
        if (annUuid) fd.append('ann_uuid', annUuid);
        await api.post(`/api/idc/sessions/${sessionId}/comments`, fd);
        onAdded();
      } catch (e: any) { setError(e.response?.data?.detail || 'Failed'); } finally { setLoading(false); }
    };

    return (
      <div style={{ background: '#0d1b2a', border: '1px solid #1e3a5f', borderRadius: 8, padding: 14, marginBottom: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0' }}>Add Comment</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 16 }}>✕</button>
        </div>
        {error && <div style={{ color: '#fca5a5', fontSize: 12, marginBottom: 8 }}>{error}</div>}
        <textarea value={form.comment_text} onChange={e => setForm(f => ({ ...f, comment_text: e.target.value }))} rows={3}
          placeholder="Comment text..."
          style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '8px', color: '#e2e8f0', fontSize: 13, boxSizing: 'border-box', resize: 'vertical', marginBottom: 8 }} />
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
          <select value={form.priority} onChange={e => setForm(f => ({ ...f, priority: e.target.value }))}
            style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '6px', color: '#e2e8f0', fontSize: 12 }}>
            {['Critical', 'High', 'Normal', 'Low'].map(p => <option key={p}>{p}</option>)}
          </select>
          <select value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
            style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '6px', color: '#e2e8f0', fontSize: 12 }}>
            {['General', 'Design', 'Safety', 'Constructability', 'Vendor', 'Drawing Correction', 'Documentation', 'LLR Related', 'SOP Related', 'IDC Observation'].map(c => <option key={c}>{c}</option>)}
          </select>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 10 }}>
          <input placeholder="Employee ID" value={form.employee_id} onChange={e => setForm(f => ({ ...f, employee_id: e.target.value }))}
            style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '6px 8px', color: '#e2e8f0', fontSize: 12 }} />
          <input type="password" placeholder="Password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
            style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 6, padding: '6px 8px', color: '#e2e8f0', fontSize: 12 }} />
        </div>
        <button onClick={submit} disabled={loading}
          style={{ width: '100%', padding: '8px', background: '#1e40af', border: 'none', borderRadius: 6, color: '#fff', cursor: loading ? 'wait' : 'pointer', fontSize: 13, fontWeight: 600 }}>
          {loading ? 'Posting...' : 'Post Comment'}
        </button>
      </div>
    );
  };

// ── Approval Panel ─────────────────────────────────────────────────────────────
const ApprovalPanel: React.FC<{ session: IDCSession; onUpdate: () => void }> = ({ session, onUpdate }) => {
  const [showApproveFor, setShowApproveFor] = useState<string | null>(null);
  const [showFreeze, setShowFreeze] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const doApprove = async (disc: string, empId: string, pw: string) => {
    setLoading(true); setError('');
    try {
      const fd = new FormData();
      fd.append('discipline', disc); fd.append('employee_id', empId); fd.append('password', pw);
      await api.post(`/api/idc/sessions/${session.id}/approve`, fd);
      setShowApproveFor(null); onUpdate();
    } catch (e: any) { setError(e.response?.data?.detail || 'Failed'); } finally { setLoading(false); }
  };

  const doFreeze = async (empId: string, pw: string) => {
    setLoading(true); setError('');
    try {
      const fd = new FormData();
      fd.append('employee_id', empId); fd.append('password', pw);
      await api.post(`/api/idc/sessions/${session.id}/freeze`, fd);
      setShowFreeze(false); onUpdate();
    } catch (e: any) { setError(e.response?.data?.detail || 'Failed'); } finally { setLoading(false); }
  };

  return (
    <div style={{ padding: '16px 0' }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: '#94a3b8', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>
        Discipline Approvals
      </div>
      {session.disciplines.map(d => {
        const approval = session.approvals[d];
        return (
          <div key={d} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, padding: '8px 12px', background: '#0a1628', borderRadius: 8, border: `1px solid ${approval ? '#16a34a' : '#1e3a5f'}` }}>
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: DISC_COLOR[d] || '#aaa' }}>{d}</div>
              {approval && <div style={{ fontSize: 11, color: '#4ade80', marginTop: 2 }}>✓ {approval.employee_name} · {new Date(approval.approved_at).toLocaleDateString()}</div>}
            </div>
            {!approval && session.status !== 'frozen' && (
              <button onClick={() => { setError(''); setShowApproveFor(d); }}
                style={{ padding: '5px 14px', background: '#14532d', border: '1px solid #16a34a', borderRadius: 6, color: '#4ade80', cursor: 'pointer', fontSize: 11, fontWeight: 600 }}>
                Approve
              </button>
            )}
            {approval && <span style={{ fontSize: 18 }}>✅</span>}
          </div>
        );
      })}

      {session.all_approved && session.status !== 'frozen' && (
        <button onClick={() => { setError(''); setShowFreeze(true); }}
          style={{ width: '100%', marginTop: 12, padding: '10px', background: 'linear-gradient(135deg, #1e3a8a, #1e40af)', border: '1px solid #2563eb', borderRadius: 8, color: '#93c5fd', cursor: 'pointer', fontSize: 13, fontWeight: 700 }}>
          ❄ Freeze IDC Session
        </button>
      )}

      {session.status === 'frozen' && (
        <div style={{ marginTop: 12, padding: 12, background: '#0f1f3d', border: '1px solid #2563eb', borderRadius: 8, textAlign: 'center' }}>
          <div style={{ fontSize: 16 }}>❄</div>
          <div style={{ color: '#60b4ff', fontSize: 13, fontWeight: 700, marginTop: 4 }}>Session Frozen</div>
          <div style={{ color: '#475569', fontSize: 11, marginTop: 4 }}>by {session.frozen_by_name}</div>
        </div>
      )}

      {showApproveFor && (
        <AuthGate title={`Approve for ${showApproveFor}`} error={error} loading={loading}
          onClose={() => setShowApproveFor(null)}
          onAuth={(id, pw) => doApprove(showApproveFor, id, pw)} />
      )}
      {showFreeze && (
        <AuthGate title="Freeze IDC Session" error={error} loading={loading}
          onClose={() => setShowFreeze(false)}
          onAuth={(id, pw) => doFreeze(id, pw)} />
      )}
    </div>
  );
};

// ── PDF Viewer with annotation canvas ─────────────────────────────────────────
interface AnnotationDraft {
  startX: number; startY: number; endX: number; endY: number;
  tool: string; color: string;
}

const PDFViewer: React.FC<{
  docId: number;
  sessionId: number;
  sessionFrozen: boolean;
  activeTool: string;
  activeColor: string;
  currentPage: number;
  annotations: Annotation[];
  highlightedAnn?: string;
  onPageChange: (p: number) => void;
  onAnnotationCreated: () => void;
  onAnnotationClick: (ann: Annotation) => void;
}> = ({ docId, sessionFrozen, activeTool, activeColor, currentPage, annotations, highlightedAnn, onPageChange, onAnnotationCreated, onAnnotationClick }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const [pdf, setPdf] = useState<any>(null);
  const [totalPages, setTotalPages] = useState(0);
  const [scale, setScale] = useState(1.5);
  const [drawing, setDrawing] = useState(false);
  const [draft, setDraft] = useState<AnnotationDraft | null>(null);
  const [loading, setLoading] = useState(true);

  // Load PDF
  useEffect(() => {
    if (!docId) return;
    setLoading(true);
    const token = localStorage.getItem('access_token');
    const url = `${import.meta.env.VITE_API_URL || ''}/api/idc/documents/${docId}/file`;
    pdfjsLib.getDocument({ url, httpHeaders: { Authorization: `Bearer ${token}` } }).promise
      .then(doc => { setPdf(doc); setTotalPages(doc.numPages); setLoading(false); })
      .catch(err => { console.error('PDF load error', err); setLoading(false); });
  }, [docId]);

  // Render page
  useEffect(() => {
    if (!pdf || !canvasRef.current) return;
    pdf.getPage(currentPage).then((page: any) => {
      const viewport = page.getViewport({ scale });
      const canvas = canvasRef.current!;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      const overlay = overlayRef.current!;
      overlay.width = viewport.width;
      overlay.height = viewport.height;
      const ctx = canvas.getContext('2d')!;
      page.render({ canvasContext: ctx, viewport }).promise.then(() => {
        drawAnnotations();
      });
    });
  }, [pdf, currentPage, scale, annotations]);

  const drawAnnotations = useCallback(() => {
    const canvas = overlayRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    annotations.filter(a => a.page_number === currentPage).forEach(ann => {
      ctx.strokeStyle = ann.ann_uuid === highlightedAnn ? '#ffffff' : ann.color;
      ctx.lineWidth = ann.ann_uuid === highlightedAnn ? 3 : 2;
      ctx.setLineDash([]);
      if (ann.tool_type === 'rect') {
        ctx.strokeRect(ann.x, ann.y, ann.width, ann.height);
        ctx.fillStyle = ann.color + '22';
        ctx.fillRect(ann.x, ann.y, ann.width, ann.height);
      } else if (ann.tool_type === 'cloud') {
        ctx.setLineDash([8, 4]);
        ctx.strokeRect(ann.x, ann.y, ann.width, ann.height);
      } else if (ann.tool_type === 'circle') {
        ctx.beginPath();
        ctx.ellipse(ann.x + ann.width / 2, ann.y + ann.height / 2, Math.abs(ann.width / 2), Math.abs(ann.height / 2), 0, 0, 2 * Math.PI);
        ctx.stroke();
      } else if (ann.tool_type === 'line' && ann.data_json) {
        ctx.beginPath();
        ctx.moveTo(ann.data_json.x1, ann.data_json.y1);
        ctx.lineTo(ann.data_json.x2, ann.data_json.y2);
        ctx.stroke();
      } else if (ann.tool_type === 'text' && ann.data_json?.text) {
        ctx.font = '13px sans-serif';
        ctx.fillStyle = ann.color;
        ctx.fillText(ann.data_json.text, ann.x, ann.y);
      }
      // author label
      ctx.font = '10px sans-serif';
      ctx.fillStyle = ann.color;
      ctx.fillText(ann.author_name.split(' ')[0], ann.x + 2, ann.y - 4);
    });
  }, [annotations, currentPage, highlightedAnn]);

  useEffect(() => { drawAnnotations(); }, [drawAnnotations]);

  const getPos = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = overlayRef.current!.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  const mouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (sessionFrozen || activeTool === 'cursor') return;
    const { x, y } = getPos(e);
    setDrawing(true);
    setDraft({ startX: x, startY: y, endX: x, endY: y, tool: activeTool, color: activeColor });
  };

  const mouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawing || !draft || !overlayRef.current) return;
    const { x, y } = getPos(e);
    setDraft(d => d ? { ...d, endX: x, endY: y } : null);
    // live preview
    const canvas = overlayRef.current;
    const ctx = canvas.getContext('2d')!;
    drawAnnotations();
    ctx.strokeStyle = activeColor;
    ctx.lineWidth = 2;
    const dx = x - draft.startX, dy = y - draft.startY;
    if (activeTool === 'rect') ctx.strokeRect(draft.startX, draft.startY, dx, dy);
    else if (activeTool === 'cloud') { ctx.setLineDash([8, 4]); ctx.strokeRect(draft.startX, draft.startY, dx, dy); ctx.setLineDash([]); }
    else if (activeTool === 'circle') { ctx.beginPath(); ctx.ellipse(draft.startX + dx / 2, draft.startY + dy / 2, Math.abs(dx / 2), Math.abs(dy / 2), 0, 0, 2 * Math.PI); ctx.stroke(); }
    else if (activeTool === 'line') { ctx.beginPath(); ctx.moveTo(draft.startX, draft.startY); ctx.lineTo(x, y); ctx.stroke(); }
  };

  const mouseUp = async () => {
    if (!drawing || !draft) return;
    setDrawing(false);
    const dx = draft.endX - draft.startX, dy = draft.endY - draft.startY;
    if (Math.abs(dx) < 5 && Math.abs(dy) < 5) { setDraft(null); return; }
    // Broadcast annotation via WebSocket
    try {
      onAnnotationCreated();
    } catch (e) { console.error(e); }
    setDraft(null);
  };

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (activeTool !== 'cursor') return;
    const { x, y } = getPos(e);
    const hit = annotations.find(a => a.page_number === currentPage &&
      x >= a.x && x <= a.x + a.width && y >= a.y && y <= a.y + a.height);
    if (hit) onAnnotationClick(hit);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#060d18' }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', gap: 8, padding: '8px 12px', background: '#0d1b2a', borderBottom: '1px solid #1e3a5f', alignItems: 'center', flexWrap: 'wrap' }}>
        <button onClick={() => onPageChange(Math.max(1, currentPage - 1))} disabled={currentPage <= 1}
          style={{ padding: '4px 10px', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 12 }}>◀</button>
        <span style={{ fontSize: 12, color: '#94a3b8', minWidth: 80, textAlign: 'center' }}>Page {currentPage} / {totalPages}</span>
        <button onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))} disabled={currentPage >= totalPages}
          style={{ padding: '4px 10px', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 12 }}>▶</button>
        <div style={{ width: 1, height: 20, background: '#1e3a5f', margin: '0 4px' }} />
        <button onClick={() => setScale(s => Math.min(3, s + 0.25))} style={{ padding: '4px 10px', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 12 }}>+</button>
        <span style={{ fontSize: 11, color: '#64748b' }}>{Math.round(scale * 100)}%</span>
        <button onClick={() => setScale(s => Math.max(0.5, s - 0.25))} style={{ padding: '4px 10px', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 12 }}>–</button>
      </div>

      {/* Canvas area */}
      <div style={{ flex: 1, overflow: 'auto', display: 'flex', justifyContent: 'center', padding: 16, position: 'relative' }}>
        {loading && <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', color: '#64748b' }}>Loading PDF...</div>}
        <div style={{ position: 'relative' }}>
          <canvas ref={canvasRef} style={{ display: 'block' }} />
          <canvas ref={overlayRef}
            style={{ position: 'absolute', top: 0, left: 0, cursor: activeTool === 'cursor' ? 'default' : 'crosshair' }}
            onMouseDown={mouseDown} onMouseMove={mouseMove} onMouseUp={mouseUp}
            onClick={handleCanvasClick}
          />
        </div>
      </div>
    </div>
  );
};

// ── Main Review Room ───────────────────────────────────────────────────────────
interface Props { session: IDCSession; onBack: () => void }

const IDCReviewRoom: React.FC<Props> = ({ session: initialSession, onBack }) => {
  const [session, setSession] = useState<IDCSession>(initialSession);
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [currentDocId, setCurrentDocId] = useState<number>(initialSession.documents[0]?.id || 0);
  const [currentPage, setCurrentPage] = useState(1);
  const [activeTool, setActiveTool] = useState('cursor');
  const [activeColor, setActiveColor] = useState('#1E90FF');
  const [activeTab, setActiveTab] = useState<'comments' | 'approvals' | 'online'>('comments');
  const [showAddComment, setShowAddComment] = useState(false);
  const [highlightedAnn, setHighlightedAnn] = useState<string | undefined>();
  const [highlightedComment, setHighlightedComment] = useState<number | undefined>();
  const [onlineUsers, setOnlineUsers] = useState<OnlineUser[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [annRes, comRes, sessRes] = await Promise.all([
        api.get(`/api/idc/sessions/${session.id}/annotations`),
        api.get(`/api/idc/sessions/${session.id}/comments`),
        api.get(`/api/idc/sessions/${session.id}`),
      ]);
      setAnnotations(annRes.data);
      setComments(comRes.data);
      setSession(sessRes.data);
    } catch (e) { console.error(e); }
  }, [session.id]);

  useEffect(() => { loadData(); }, [loadData]);

  // WebSocket connection
  useEffect(() => {
    const wsUrl = (import.meta.env.VITE_API_URL || window.location.origin).replace(/^http/, 'ws');
    const ws = new WebSocket(`${wsUrl}/api/idc/ws/${session.id}`);
    wsRef.current = ws;

    ws.onopen = () => {
      const empId = localStorage.getItem('employee_id') || '';
      const empName = localStorage.getItem('employee_name') || 'Unknown';
      const discipline = localStorage.getItem('discipline') || 'Instrumentation Engineering';
      ws.send(JSON.stringify({ type: 'join', session_id: session.id, emp_id: empId, emp_name: empName, discipline }));
    };

    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === 'roster') setOnlineUsers(msg.users);
      else if (msg.type === 'annotation' || msg.type === 'comment' || msg.type === 'approve' || msg.type === 'freeze') {
        loadData();
      }
    };

    return () => { ws.close(); };
  }, [session.id, loadData]);

  const broadcastAnnotation = (data: any) => {
    wsRef.current?.send(JSON.stringify({ type: 'annotation', action: 'add', data }));
  };

  const filteredComments = comments.filter(c =>
    currentDocId === 0 || annotations.find(a => a.ann_uuid === c.ann_uuid)?.document_id === currentDocId || !c.ann_uuid
  );

  const TOOLS = [
    { id: 'cursor', icon: '↖', label: 'Select' },
    { id: 'rect', icon: '▭', label: 'Rectangle' },
    { id: 'cloud', icon: '⬟', label: 'Cloud' },
    { id: 'circle', icon: '◯', label: 'Circle' },
    { id: 'line', icon: '/', label: 'Line' },
  ];

  const COLORS = ['#1E90FF', '#FF8C00', '#8B4513', '#9932CC', '#228B22', '#ef4444', '#000000'];

  const currentDoc = session.documents.find(d => d.id === currentDocId);
  const isPdf = currentDoc?.file_type === 'pdf';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#060d18', overflow: 'hidden' }}>
      {/* Top bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px', background: '#0d1b2a', borderBottom: '1px solid #1e3a5f', flexShrink: 0 }}>
        <button onClick={onBack} style={{ padding: '5px 12px', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 12 }}>← Back</button>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e8f0' }}>{session.idc_number} — {session.document_title}</div>
          <div style={{ fontSize: 11, color: '#64748b' }}>{session.project_name} | Rev {session.revision_number} | {session.document_category}</div>
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {onlineUsers.map(u => (
            <span key={u.emp_id} title={`${u.emp_name} (${u.discipline})`}
              style={{ width: 28, height: 28, borderRadius: '50%', background: DISC_COLOR[u.discipline] || '#555', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: '#fff' }}>
              {u.emp_name.charAt(0)}
            </span>
          ))}
        </div>
        <span style={{ padding: '3px 10px', borderRadius: 12, fontSize: 11, fontWeight: 700, background: session.status === 'frozen' ? '#1a3a5c' : '#1a4a2a', color: session.status === 'frozen' ? '#60b4ff' : '#4ade80', border: `1px solid ${session.status === 'frozen' ? '#2563eb' : '#16a34a'}` }}>
          {session.status === 'frozen' ? '❄ Frozen' : '● Active'}
        </span>
        {/* export */}
        <a href={`${import.meta.env.VITE_API_URL || ''}/api/idc/sessions/${session.id}/export/comments`}
          style={{ padding: '5px 12px', background: '#0f2a1a', border: '1px solid #16a34a', borderRadius: 6, color: '#4ade80', cursor: 'pointer', fontSize: 11, textDecoration: 'none', fontWeight: 600 }}>
          ↓ Export
        </a>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left: document list + annotation tools */}
        <div style={{ width: 200, background: '#0d1b2a', borderRight: '1px solid #1e3a5f', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
          <div style={{ padding: '10px 12px', fontSize: 11, color: '#64748b', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1 }}>Documents</div>
          <div style={{ flex: 1, overflowY: 'auto' }}>
            {session.documents.map(doc => (
              <div key={doc.id} onClick={() => { setCurrentDocId(doc.id); setCurrentPage(1); }}
                style={{ padding: '8px 12px', cursor: 'pointer', background: doc.id === currentDocId ? '#1e3a5f' : 'transparent', borderLeft: doc.id === currentDocId ? '2px solid #2563eb' : '2px solid transparent' }}>
                <div style={{ fontSize: 11, color: '#e2e8f0', wordBreak: 'break-word', lineHeight: 1.3 }}>{doc.original_filename}</div>
                <div style={{ fontSize: 10, color: '#475569', marginTop: 2 }}>{doc.file_type.toUpperCase()}{doc.file_size ? ` · ${(doc.file_size / 1024).toFixed(0)}KB` : ''}</div>
              </div>
            ))}
            {session.documents.length === 0 && <div style={{ padding: 12, fontSize: 11, color: '#475569' }}>No documents uploaded</div>}
          </div>

          {/* Annotation tools */}
          <div style={{ padding: '10px 12px', borderTop: '1px solid #1e3a5f' }}>
            <div style={{ fontSize: 11, color: '#64748b', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>Tools</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              {TOOLS.map(t => (
                <button key={t.id} onClick={() => setActiveTool(t.id)} title={t.label}
                  style={{ padding: '6px', background: activeTool === t.id ? '#1e40af' : '#1e293b', border: `1px solid ${activeTool === t.id ? '#2563eb' : '#334155'}`, borderRadius: 6, color: activeTool === t.id ? '#fff' : '#94a3b8', cursor: 'pointer', fontSize: 14 }}>
                  {t.icon}
                </button>
              ))}
            </div>
            <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {COLORS.map(c => (
                <div key={c} onClick={() => setActiveColor(c)}
                  style={{ width: 20, height: 20, borderRadius: '50%', background: c, cursor: 'pointer', border: activeColor === c ? '2px solid #fff' : '1px solid #334155' }} />
              ))}
            </div>
          </div>
        </div>

        {/* Center: PDF viewer */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {isPdf ? (
            <PDFViewer
              docId={currentDocId} sessionId={session.id}
              sessionFrozen={session.status === 'frozen'}
              activeTool={activeTool} activeColor={activeColor}
              currentPage={currentPage} annotations={annotations}
              highlightedAnn={highlightedAnn}
              onPageChange={setCurrentPage}
              onAnnotationCreated={() => { loadData(); broadcastAnnotation({}); }}
              onAnnotationClick={ann => {
                setHighlightedAnn(ann.ann_uuid);
                const c = comments.find(c => c.ann_uuid === ann.ann_uuid);
                if (c) setHighlightedComment(c.id);
              }}
            />
          ) : (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 16 }}>
              <div style={{ fontSize: 48 }}>📐</div>
              <div style={{ color: '#64748b', fontSize: 14 }}>
                {currentDoc ? `${currentDoc.file_type.toUpperCase()} file — download to view in CAD` : 'Select a document'}
              </div>
              {currentDoc && (
                <a href={`${import.meta.env.VITE_API_URL || ''}/api/idc/documents/${currentDocId}/file`}
                  style={{ padding: '8px 20px', background: '#1e293b', border: '1px solid #334155', borderRadius: 8, color: '#60b4ff', textDecoration: 'none', fontSize: 13 }}>
                  ↓ Download {currentDoc.original_filename}
                </a>
              )}
            </div>
          )}
        </div>

        {/* Right panel */}
        <div style={{ width: 340, background: '#0d1b2a', borderLeft: '1px solid #1e3a5f', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
          {/* Tabs */}
          <div style={{ display: 'flex', borderBottom: '1px solid #1e3a5f' }}>
            {(['comments', 'approvals', 'online'] as const).map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                style={{ flex: 1, padding: '10px 4px', background: activeTab === tab ? '#1e3a5f' : 'transparent', border: 'none', borderBottom: activeTab === tab ? '2px solid #2563eb' : '2px solid transparent', color: activeTab === tab ? '#e2e8f0' : '#64748b', cursor: 'pointer', fontSize: 12, fontWeight: activeTab === tab ? 700 : 400, textTransform: 'capitalize' }}>
                {tab === 'comments' ? `Comments (${comments.length})` : tab === 'online' ? `Online (${onlineUsers.length})` : 'Approvals'}
              </button>
            ))}
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
            {activeTab === 'comments' && (
              <>
                {!session.status || session.status !== 'frozen' ? (
                  <button onClick={() => setShowAddComment(!showAddComment)}
                    style={{ width: '100%', padding: '8px', background: '#1e293b', border: '1px dashed #334155', borderRadius: 8, color: '#60b4ff', cursor: 'pointer', fontSize: 12, marginBottom: 12 }}>
                    + Add Comment
                  </button>
                ) : null}
                {showAddComment && (
                  <AddCommentForm sessionId={session.id} page={currentPage} annUuid={highlightedAnn}
                    onAdded={() => { loadData(); setShowAddComment(false); wsRef.current?.send(JSON.stringify({ type: 'comment', action: 'add' })); }}
                    onClose={() => setShowAddComment(false)} />
                )}
                {filteredComments.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '32px 16px', color: '#475569', fontSize: 13 }}>No comments yet</div>
                ) : filteredComments.map(c => (
                  <CommentCard key={c.id} comment={c} sessionId={session.id}
                    sessionFrozen={session.status === 'frozen'}
                    highlighted={c.id === highlightedComment}
                    onClick={() => { setHighlightedComment(c.id); if (c.ann_uuid) setHighlightedAnn(c.ann_uuid); }}
                    onStatusChange={loadData} />
                ))}
              </>
            )}
            {activeTab === 'approvals' && (
              <ApprovalPanel session={session} onUpdate={loadData} />
            )}
            {activeTab === 'online' && (
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#94a3b8', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 1 }}>Online Now</div>
                {onlineUsers.length === 0 ? (
                  <div style={{ color: '#475569', fontSize: 13 }}>No other users online</div>
                ) : onlineUsers.map(u => (
                  <div key={u.emp_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid #0f172a' }}>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: DISC_COLOR[u.discipline] || '#555', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, color: '#fff' }}>
                      {u.emp_name.charAt(0)}
                    </div>
                    <div>
                      <div style={{ fontSize: 13, color: '#e2e8f0', fontWeight: 600 }}>{u.emp_name}</div>
                      <div style={{ fontSize: 11, color: DISC_COLOR[u.discipline] || '#64748b' }}>{u.discipline}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default IDCReviewRoom;
