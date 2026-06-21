/**
 * Approval Queue — Lead Engineer dashboard.
 * Lists pending spec-extraction and cover-sheet approval requests.
 * Lead Engineers enter their credentials to Approve or Reject each request.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  ClipboardCheck, CheckCircle2, XCircle, Clock, ChevronDown, ChevronRight,
  RefreshCw, X, AlertTriangle, Loader2, Tag, FileText,
} from 'lucide-react';
import api from '@/services/api';
import PageHeader from '../ui/PageHeader';
import Button from '../ui/Button';
import Alert from '../ui/Alert';

interface ApprovalReq {
  id: number;
  request_type: string;
  tag_numbers: string | null;
  instrument_type: string | null;
  payload_json: string | null;
  submitted_by_name: string;
  submitted_by_id: string;
  submitter_notes: string | null;
  status: string;
  reviewed_by_name: string | null;
  reviewed_by_id: string | null;
  reviewed_role: string | null;
  review_notes: string | null;
  created_at: string;
  updated_at: string | null;
}

// ── Lead review modal ──────────────────────────────────────────────────────────
function ReviewModal({
  req, action, onDone, onClose,
}: { req: ApprovalReq; action: 'approve' | 'reject'; onDone: () => void; onClose: () => void }) {
  const [empId, setEmpId] = useState('');
  const [pass, setPass] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(''); setBusy(true);
    try {
      await api.post(`/approvals/${req.id}/${action}`, { employee_id: empId, password: pass, review_notes: notes || null });
      onDone();
      onClose();
    } catch (ex: any) {
      setErr(ex?.response?.data?.detail || 'Failed to submit review');
    } finally { setBusy(false); }
  };

  const isApprove = action === 'approve';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-2xl overflow-hidden"
        style={{ background: 'var(--s1)', border: '1px solid var(--b2)' }}>
        <div className="px-6 py-5 flex items-center gap-3" style={{ borderBottom: '1px solid var(--b1)' }}>
          <div className="w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: isApprove ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.12)', border: `1px solid ${isApprove ? 'rgba(74,222,128,0.3)' : 'rgba(248,113,113,0.3)'}` }}>
            {isApprove ? <CheckCircle2 className="w-4 h-4" style={{ color: '#4ade80' }} />
                       : <XCircle className="w-4 h-4" style={{ color: 'var(--rose)' }} />}
          </div>
          <div className="flex-1">
            <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>
              {isApprove ? 'Approve Request' : 'Reject Request'} #{req.id}
            </p>
            <p className="text-xs" style={{ color: 'var(--t2)' }}>
              {isApprove ? 'Lead Engineer credentials required to approve' : 'Enter credentials and reason for rejection'}
            </p>
          </div>
          <button onClick={onClose} className="opacity-40 hover:opacity-80" style={{ color: 'var(--t1)' }}>
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={submit} className="p-6 space-y-4">
          {err && (
            <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs"
              style={{ background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)', color: 'var(--rose)' }}>
              <AlertTriangle className="w-3.5 h-3.5" /> {err}
            </div>
          )}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>
              Lead Engineer Employee ID
            </label>
            <input type="text" required value={empId} onChange={e => setEmpId(e.target.value)}
              placeholder="e.g. WABAG-LEAD-001" className="w-full px-3 py-2.5 rounded-xl text-sm"
              style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Password</label>
            <input type="password" required value={pass} onChange={e => setPass(e.target.value)}
              placeholder="••••••••" className="w-full px-3 py-2.5 rounded-xl text-sm"
              style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
          </div>
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>
              {isApprove ? 'Notes (optional)' : 'Reason for Rejection'}
            </label>
            <textarea rows={2} value={notes} onChange={e => setNotes(e.target.value)}
              placeholder={isApprove ? 'Any notes for the requester…' : 'Explain why this is being rejected…'}
              className="w-full resize-none px-3 py-2.5 rounded-xl text-sm"
              style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)', outline: 'none' }} />
          </div>
          <button type="submit" disabled={busy || !empId || !pass || (!isApprove && !notes)}
            className="w-full py-3 rounded-xl text-sm font-bold flex items-center justify-center gap-2"
            style={{
              background: isApprove ? 'linear-gradient(135deg,#22c55e,#16a34a)' : 'linear-gradient(135deg,#ef4444,#dc2626)',
              color: '#fff',
              opacity: (busy || !empId || !pass || (!isApprove && !notes)) ? 0.5 : 1,
              cursor: 'pointer',
            }}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : isApprove ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
            {busy ? 'Processing…' : isApprove ? 'Confirm Approval' : 'Confirm Rejection'}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Request Card ───────────────────────────────────────────────────────────────
function RequestCard({ req, onAction }: { req: ApprovalReq; onAction: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [modal, setModal] = useState<'approve' | 'reject' | null>(null);
  const isPending = req.status === 'pending';
  const tags: string[] = req.tag_numbers ? JSON.parse(req.tag_numbers) : [];

  let payload: Record<string, any> = {};
  try { payload = req.payload_json ? JSON.parse(req.payload_json) : {}; } catch { /* ignore */ }

  const statusColor = req.status === 'approved' ? '#4ade80' : req.status === 'rejected' ? 'var(--rose)' : 'var(--gold)';
  const statusBg = req.status === 'approved' ? 'rgba(74,222,128,0.08)' : req.status === 'rejected' ? 'rgba(248,113,113,0.08)' : 'rgba(245,158,11,0.08)';
  const StatusIcon = req.status === 'approved' ? CheckCircle2 : req.status === 'rejected' ? XCircle : Clock;

  return (
    <>
      <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
        {/* Header */}
        <div className="flex items-center gap-4 px-5 py-4">
          <div className="flex-shrink-0 w-9 h-9 rounded-xl flex items-center justify-center"
            style={{ background: statusBg, border: `1px solid ${statusColor}40` }}>
            <StatusIcon className="w-4 h-4" style={{ color: statusColor }} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-bold px-2 py-0.5 rounded-full"
                style={{ background: req.request_type === 'spec' ? 'rgba(59,130,246,0.1)' : 'rgba(245,158,11,0.1)', color: req.request_type === 'spec' ? 'var(--em-lt)' : 'var(--gold)' }}>
                {req.request_type === 'spec' ? 'Spec Extraction' : 'Cover Sheet'}
              </span>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                style={{ background: statusBg, color: statusColor, border: `1px solid ${statusColor}30` }}>
                {req.status.toUpperCase()}
              </span>
              <span className="text-xs" style={{ color: 'var(--t2)' }}>#{req.id}</span>
            </div>
            <p className="text-sm font-semibold mt-0.5 truncate" style={{ color: 'var(--t0)' }}>
              {req.instrument_type || 'Cover Sheet Review'}
              {tags.length > 0 && <span style={{ color: 'var(--t2)' }}> — {tags.slice(0, 3).join(', ')}{tags.length > 3 ? ` +${tags.length - 3}` : ''}</span>}
            </p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--t2)' }}>
              By <strong style={{ color: 'var(--t1)' }}>{req.submitted_by_name}</strong> ({req.submitted_by_id})
              · {new Date(req.created_at).toLocaleString()}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {isPending && (
              <>
                <button onClick={() => setModal('approve')}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold"
                  style={{ background: 'rgba(74,222,128,0.1)', color: '#4ade80', border: '1px solid rgba(74,222,128,0.3)' }}>
                  <CheckCircle2 className="w-3.5 h-3.5" /> Approve
                </button>
                <button onClick={() => setModal('reject')}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold"
                  style={{ background: 'rgba(248,113,113,0.08)', color: 'var(--rose)', border: '1px solid rgba(248,113,113,0.2)' }}>
                  <XCircle className="w-3.5 h-3.5" /> Reject
                </button>
              </>
            )}
            <button onClick={() => setExpanded(e => !e)} className="p-1.5 rounded-lg" style={{ color: 'var(--t2)' }}>
              {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Expanded preview */}
        {expanded && (
          <div className="border-t px-5 pb-5 pt-4 space-y-4" style={{ borderColor: 'var(--b1)' }}>
            {/* Submitter notes */}
            {req.submitter_notes && (
              <div className="rounded-xl px-4 py-3" style={{ background: 'rgba(59,130,246,0.05)', border: '1px solid rgba(59,130,246,0.15)' }}>
                <p className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: 'var(--em-lt)' }}>Submitter Notes</p>
                <p className="text-xs" style={{ color: 'var(--t1)' }}>{req.submitter_notes}</p>
              </div>
            )}

            {/* Tag list */}
            {tags.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--t2)' }}>
                  <Tag className="w-3 h-3 inline mr-1" />Tags ({tags.length})
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {tags.map(t => (
                    <span key={t} className="text-xs px-2.5 py-1 rounded-lg"
                      style={{ background: 'var(--s3)', color: 'var(--t1)', border: '1px solid var(--b2)' }}>{t}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Specs preview */}
            {Object.keys(payload).length > 0 && (
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: 'var(--t2)' }}>
                  <FileText className="w-3 h-3 inline mr-1" />Extracted Specifications
                </p>
                <div className="rounded-xl overflow-hidden" style={{ border: '1px solid var(--b2)' }}>
                  <table className="w-full text-xs" style={{ borderCollapse: 'collapse' }}>
                    <thead>
                      <tr style={{ background: 'var(--s3)' }}>
                        <th className="text-left px-3 py-2 font-semibold" style={{ color: 'var(--t2)', width: '40%' }}>Parameter</th>
                        <th className="text-left px-3 py-2 font-semibold" style={{ color: 'var(--t2)' }}>Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(payload).slice(0, 30).map(([k, v], idx) => (
                        <tr key={k} style={{ background: idx % 2 === 0 ? 'transparent' : 'var(--s3)' }}>
                          <td className="px-3 py-1.5 font-medium" style={{ color: 'var(--t1)', borderRight: '1px solid var(--b1)' }}>{k}</td>
                          <td className="px-3 py-1.5" style={{ color: 'var(--t0)' }}>
                            {Array.isArray(v) ? v.join(', ') : String(v ?? '—')}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Coversheet summary */}
            {req.request_type === 'coversheet' && Object.keys(payload).length > 0 && (
              <div className="grid grid-cols-2 gap-2">
                {Object.entries(payload).map(([k, v]) => (
                  <div key={k} className="rounded-xl px-3 py-2" style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
                    <p className="text-[10px] mb-0.5" style={{ color: 'var(--t2)' }}>{k.replace(/_/g, ' ').toUpperCase()}</p>
                    <p className="text-xs font-medium truncate" style={{ color: 'var(--t0)' }}>{String(v || '—')}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Review details (if acted on) */}
            {req.status !== 'pending' && req.reviewed_by_name && (
              <div className="rounded-xl px-4 py-3" style={{
                background: req.status === 'approved' ? 'rgba(74,222,128,0.06)' : 'rgba(248,113,113,0.06)',
                border: `1px solid ${req.status === 'approved' ? 'rgba(74,222,128,0.2)' : 'rgba(248,113,113,0.2)'}`,
              }}>
                <p className="text-[10px] font-semibold uppercase tracking-wider mb-1" style={{ color: req.status === 'approved' ? '#4ade80' : 'var(--rose)' }}>
                  {req.status === 'approved' ? '✓ Approved' : '✗ Rejected'} by {req.reviewed_by_name} ({req.reviewed_role})
                </p>
                {req.review_notes && <p className="text-xs" style={{ color: 'var(--t1)' }}>{req.review_notes}</p>}
                {req.updated_at && <p className="text-[10px] mt-1" style={{ color: 'var(--t2)' }}>{new Date(req.updated_at).toLocaleString()}</p>}
              </div>
            )}
          </div>
        )}
      </div>

      {modal && (
        <ReviewModal req={req} action={modal}
          onDone={() => { setModal(null); onAction(); }}
          onClose={() => setModal(null)} />
      )}
    </>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function ApprovalQueue() {
  const [requests, setRequests] = useState<ApprovalReq[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await api.get('/approvals/pending');
      setRequests(res.data);
    } catch (e: any) { setError(e?.response?.data?.detail || 'Failed to load requests'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const pending = requests.filter(r => r.status === 'pending');
  const handled = requests.filter(r => r.status !== 'pending');

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-5">
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <PageHeader icon={ClipboardCheck}
            title="Approval Queue"
            description="Review spec extraction and cover sheet requests from engineers. Lead Engineer credentials required to approve." />
        </div>
        <Button onClick={load} loading={loading} size="sm" variant="secondary">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </Button>
      </div>

      {error && <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>}

      {/* Stats bar */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { label: 'Pending', value: pending.length, color: 'var(--gold)', bg: 'rgba(245,158,11,0.06)' },
          { label: 'Total in queue', value: requests.length, color: 'var(--em-lt)', bg: 'rgba(59,130,246,0.06)' },
          { label: 'Reviewed', value: handled.length, color: '#4ade80', bg: 'rgba(74,222,128,0.06)' },
        ].map(({ label, value, color, bg }) => (
          <div key={label} className="rounded-2xl px-5 py-4" style={{ background: bg, border: `1px solid ${color}20` }}>
            <p className="text-2xl font-black" style={{ color }}>{value}</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--t2)' }}>{label}</p>
          </div>
        ))}
      </div>

      {/* Pending section */}
      {pending.length === 0 && !loading && (
        <div className="rounded-2xl p-10 text-center" style={{ background: 'var(--s2)', border: '1px dashed var(--b2)' }}>
          <ClipboardCheck className="w-10 h-10 mx-auto mb-3 opacity-20" style={{ color: 'var(--t2)' }} />
          <p className="text-sm font-semibold" style={{ color: 'var(--t1)' }}>No pending requests</p>
          <p className="text-xs mt-1" style={{ color: 'var(--t2)' }}>All caught up — engineers will see the Approve button enabled once you review their submissions.</p>
        </div>
      )}

      {pending.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--gold)' }}>
            Pending Review ({pending.length})
          </p>
          {pending.map(r => <RequestCard key={r.id} req={r} onAction={load} />)}
        </div>
      )}

      {handled.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--t2)' }}>
            Recently Reviewed
          </p>
          {handled.slice(0, 10).map(r => <RequestCard key={r.id} req={r} onAction={load} />)}
        </div>
      )}
    </div>
  );
}
