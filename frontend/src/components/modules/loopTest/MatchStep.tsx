/** Step 2 - match tags/loops between the two documents; the engineer reviews conflicts and look-alike suggestions. */
import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Search, XCircle } from 'lucide-react';
import api from '@/services/api';
import Alert from '../../ui/Alert';
import Button from '../../ui/Button';
import Card from '../../ui/Card';
import { MatchItem, MatchSummary, STATUS_STYLE } from './types';

interface Props {
  sid: string;
  summary: MatchSummary | null;
  busy: boolean;
  version: number;                       // bumps when decisions change so the list reloads
  selected: string[];
  onSelectedChange: (tags: string[]) => void;
  onMatch: () => void;
  onDecision: (body: Record<string, string>) => Promise<void>;
  onDesign: (tag: string) => void;
}

const STATUSES = ['', 'MATCHED', 'IO NOT FOUND', 'IODB NOT FOUND', 'CONFLICT', 'DUPLICATE', 'REVIEW REQUIRED'];
const PAGE = 50;

export default function MatchStep({ sid, summary, busy, version, selected, onSelectedChange, onMatch, onDecision, onDesign }: Props) {
  const [items, setItems] = useState<MatchItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState('');
  const [q, setQ] = useState('');
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!summary) return;
    setLoading(true);
    try {
      const r = await api.get(`/loop-wiring-test/sessions/${sid}/matches`, { params: { status_filter: status, q, limit: PAGE, offset } });
      setItems(r.data.items); setTotal(r.data.total);
    } finally { setLoading(false); }
  }, [sid, summary, status, q, offset]);

  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [load, version]);
  useEffect(() => setOffset(0), [status, q]);

  const toggle = (tag: string) => onSelectedChange(selected.includes(tag) ? selected.filter((t) => t !== tag) : [...selected, tag]);
  const tile = (label: string, value: number | string, color = 'var(--t0)') => (
    <div className="rounded-xl px-4 py-3" style={{ background: 'var(--s3)', border: '1px solid var(--b2)' }}>
      <p className="text-[10px] uppercase tracking-wider" style={{ color: 'var(--t2)' }}>{label}</p>
      <p className="text-xl font-bold" style={{ color }}>{value}</p>
    </div>
  );
  const cell = 'px-3 py-2 text-xs align-top';

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button onClick={onMatch} loading={busy}>Match tags / loops</Button>
        <span className="text-xs" style={{ color: 'var(--t2)' }}>
          Order: exact tag → normalised tag → loop number. Loop-number and look-alike matches are only suggestions you must approve.
        </span>
      </div>

      {summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
            {tile('IODB tags', summary.iodb_tags)}
            {tile('I/O Assignment tags', summary.io_assignment_tags)}
            {tile('Matched', summary.matched, '#4ade80')}
            {tile('Not matched', summary.not_matched, summary.not_matched ? 'var(--rose)' : 'var(--t0)')}
            {tile('Conflicts', summary.conflicts, summary.conflicts ? 'var(--gold)' : 'var(--t0)')}
            {tile('Review required', summary.review_required, summary.review_required ? '#60a5fa' : 'var(--t0)')}
            {tile('Warnings', summary.warnings)}
          </div>
          {summary.conflicts > 0 && (
            <Alert variant="warning" title="Conflicts need a decision">
              Loops with an unresolved signal-type or junction-box conflict cannot be generated until you choose which document is right.
            </Alert>
          )}

          <Card title="Match results">
            <div className="flex flex-wrap gap-2 mb-3">
              <div className="relative flex-1 min-w-[200px]">
                <Search className="w-3.5 h-3.5 absolute left-3 top-2.5" style={{ color: 'var(--t2)' }} />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search tag or loop…"
                  className="w-full pl-9 pr-3 py-2 rounded-xl text-sm outline-none"
                  style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)' }} />
              </div>
              <select value={status} onChange={(e) => setStatus(e.target.value)} className="px-3 py-2 rounded-xl text-sm outline-none"
                style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)' }}>
                {STATUSES.map((s) => <option key={s} value={s}>{s || 'All statuses'}</option>)}
              </select>
              <Button size="sm" variant="secondary" disabled={!items.some((i) => i.status === 'MATCHED')}
                onClick={() => onSelectedChange(Array.from(new Set([...selected, ...items.filter((i) => i.status === 'MATCHED').map((i) => i.tag)])))}>
                Select matched on this page
              </Button>
              <Button size="sm" variant="ghost" disabled={selected.length === 0} onClick={() => onSelectedChange([])}>
                Clear selection ({selected.length})
              </Button>
            </div>
            <div className="rounded-xl overflow-auto max-h-[28rem]" style={{ border: '1px solid var(--b1)' }}>
              <table className="w-full">
                <thead style={{ background: 'var(--s3)', position: 'sticky', top: 0 }}>
                  <tr style={{ color: 'var(--t2)' }}>
                    {['', 'TAG', 'LOOP', 'IODB', 'I/O ASSIGNMENT', 'STATUS', 'DETAILS / ACTIONS'].map((h) => (
                      <th key={h} className="text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-2">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((m) => {
                    const st = STATUS_STYLE[m.status] || { bg: 'var(--s3)', fg: 'var(--t1)' };
                    return (
                      <tr key={m.tag + m.io_tag} style={{ borderTop: '1px solid var(--b1)', color: 'var(--t1)' }}>
                        <td className={cell}><input type="checkbox" checked={selected.includes(m.tag)} disabled={!m.in_iodb || !m.in_io}
                          onChange={() => toggle(m.tag)} /></td>
                        <td className={`${cell} font-mono font-semibold`} style={{ color: 'var(--t0)' }}>{m.tag}
                          {m.signals > 1 && <span className="ml-2 text-[10px]" style={{ color: 'var(--t2)' }}>{m.signals} signals</span>}</td>
                        <td className={cell}>{m.loop || '—'}</td>
                        <td className={cell}>{m.in_iodb ? <CheckCircle2 className="w-4 h-4" style={{ color: '#4ade80' }} /> : <XCircle className="w-4 h-4" style={{ color: 'var(--rose)' }} />}</td>
                        <td className={cell}>{m.in_io ? <CheckCircle2 className="w-4 h-4" style={{ color: '#4ade80' }} /> : <XCircle className="w-4 h-4" style={{ color: 'var(--rose)' }} />}</td>
                        <td className={cell}><span className="px-2 py-0.5 rounded text-[10px] font-bold whitespace-nowrap" style={{ background: st.bg, color: st.fg }}>{m.status}</span></td>
                        <td className={cell}>
                          {m.conflicts.map((c) => (
                            <div key={c.field} className="mb-1.5">
                              <span style={{ color: c.severity === 'error' ? 'var(--gold)' : 'var(--t2)' }}>
                                <AlertTriangle className="w-3 h-3 inline mr-1" />{c.label}: IODB <b>{c.iodb}</b> vs I/O Assignment <b>{c.io}</b>
                              </span>
                              {c.decision
                                ? <span className="ml-2" style={{ color: '#4ade80' }}>decided: {c.decision === 'iodb' ? 'IODB' : 'I/O Assignment'}
                                    <button className="ml-2 underline" onClick={() => onDecision({ kind: 'conflict', tag: m.tag, field: c.field, choice: '' })}>undo</button></span>
                                : <span className="ml-2">
                                    <button className="underline mr-2" onClick={() => onDecision({ kind: 'conflict', tag: m.tag, field: c.field, choice: 'iodb' })}>Accept IODB</button>
                                    <button className="underline" onClick={() => onDecision({ kind: 'conflict', tag: m.tag, field: c.field, choice: 'io' })}>Accept I/O Assignment</button>
                                  </span>}
                            </div>
                          ))}
                          {m.suggestions.map((s) => (
                            <div key={s.iodb_tag} className="mb-1.5">
                              Possible match ({s.method}, {Math.round(s.score * 100)}%): IODB <b>{s.iodb_tag}</b>
                              <button className="underline ml-2" onClick={() => onDecision({ kind: 'suggestion', tag: m.io_tag, iodb_tag: s.iodb_tag, choice: 'accept' })}>Accept match</button>
                              <button className="underline ml-2" onClick={() => onDecision({ kind: 'suggestion', tag: m.io_tag, iodb_tag: s.iodb_tag, choice: 'reject' })}>Reject</button>
                            </div>
                          ))}
                          {m.in_iodb && m.in_io && (
                            <Button size="sm" variant="secondary" onClick={() => onDesign(m.tag)}>Design loop</Button>
                          )}
                          {m.method && <span className="ml-2 text-[10px]" style={{ color: 'var(--t2)' }}>{m.method}</span>}
                        </td>
                      </tr>
                    );
                  })}
                  {!loading && items.length === 0 && (
                    <tr><td colSpan={7} className="px-3 py-6 text-center text-xs" style={{ color: 'var(--t2)' }}>No tags match this filter.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between mt-2 text-xs" style={{ color: 'var(--t2)' }}>
              <span>{total.toLocaleString()} result(s){loading ? ' · loading…' : ''}</span>
              <span className="flex gap-2">
                <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>← Prev</Button>
                <Button size="sm" variant="ghost" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Next →</Button>
              </span>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
