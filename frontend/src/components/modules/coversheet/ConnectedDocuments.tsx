/**
 * ConnectedDocuments - project-level document control layer for the Coversheet.
 *
 * Reads the document registry (what each generator produced, which revision, which
 * IODB revision it came from) and lets the engineer connect/disconnect documents,
 * see what needs regeneration, and re-run generators from the stored IODB.
 *
 * It never edits engineering data: the IODB is the source, generators create the
 * deliverables, and this panel only coordinates and reports.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, CheckCircle2, Download, FileSpreadsheet, Link2, Loader2, Play,
  RefreshCw, Unlink, Upload, XCircle, FileText,
} from 'lucide-react';
import api from '@/services/api';
import { getCurrentProject, subscribeProject } from '@/services/projectContext';
import ProjectSelector from '../../ui/ProjectSelector';
import Alert from '../../ui/Alert';
import Badge from '../../ui/Badge';
import Button from '../../ui/Button';

export interface DocInfo {
  id: number;
  module: string;
  module_name: string;
  document_name: string;
  document_number: string;
  revision: number;
  revision_label: string;
  status: string;
  generated_at: string | null;
  generated_by: string | null;
  filename: string | null;
  record_count: number | null;
  sheet_count: number | null;
  count_label: string;
  source_kind: string | null;
  source_rev_no: number | null;
  can_regenerate: boolean;
  has_file: boolean;
}

interface ModuleState {
  module: string;
  module_name: string;
  source_kind: 'iodb' | 'loop_input';
  count_label: string;
  state: 'current' | 'not_connected' | 'new_revision_available' | 'regeneration_required' | 'not_generated' | 'failed';
  flags: string[];
  connected: boolean;
  latest: DocInfo | null;
  linked: DocInfo | null;
  last_error: string | null;
  latest_source_rev: number | null;
}

interface Summary {
  current: number;
  regeneration_required: number;
  new_revision_available: number;
  failed: number;
  coversheet_ready: boolean;
}

interface Overview {
  project_id: string;
  sources: { iodb: { rev_no: number; filename: string } | null; loop_input: { rev_no: number; filename: string } | null };
  modules: ModuleState[];
  summary: Summary;
}

interface Step {
  step: string;
  label: string;
  status: 'ok' | 'failed' | 'needs_input';
  message: string;
  document?: DocInfo;
}

const STATE_UI: Record<ModuleState['state'], { label: string; variant: 'success' | 'warning' | 'error' | 'info' | 'neutral' }> = {
  current: { label: 'Connected · Current', variant: 'success' },
  not_connected: { label: 'Generated · Not connected', variant: 'info' },
  new_revision_available: { label: 'New revision available', variant: 'warning' },
  regeneration_required: { label: 'Regeneration required', variant: 'warning' },
  not_generated: { label: 'Not generated', variant: 'neutral' },
  failed: { label: 'Generation failed', variant: 'error' },
};

const fmtDate = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—');
const errText = (e: any, fallback: string) => e?.response?.data?.detail || fallback;

const th = 'text-left text-[10px] font-semibold uppercase tracking-wider px-3 py-2';
const td = 'px-3 py-2 text-xs';

export default function ConnectedDocuments({ onUseDocument }: {
  onUseDocument?: (doc: DocInfo, projectId: string) => void;
}) {
  const [projectId, setProjectId] = useState(getCurrentProject());
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [confirmDisconnect, setConfirmDisconnect] = useState<string | null>(null);
  const [showPlan, setShowPlan] = useState(false);
  const [planModules, setPlanModules] = useState<string[]>([]);
  const [steps, setSteps] = useState<Step[] | null>(null);

  useEffect(() => subscribeProject(setProjectId), []);

  const load = useCallback(async () => {
    if (!projectId) { setData(null); return; }
    setLoading(true);
    try {
      const r = await api.get<Overview>(`/projects/${encodeURIComponent(projectId)}/documents/connected`);
      setData(r.data);
      setError(null);
    } catch (e) {
      setError(errText(e, 'Could not load project documents'));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { setSteps(null); setNotice(null); setSelected([]); load(); }, [load]);

  const base = `/projects/${encodeURIComponent(projectId)}`;
  const modules = data?.modules ?? [];

  const generated = useMemo(() => modules.filter((m) => m.latest), [modules]);
  const needRegen = modules.filter((m) => m.flags.includes('regeneration_required'));
  const anyFailed = modules.some((m) => m.state === 'failed');

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key); setError(null); setNotice(null);
    try { await fn(); } catch (e) { setError(errText(e, 'Request failed')); } finally { setBusy(null); }
  };

  const connectSelected = () => run('connect', async () => {
    const r = await api.post(`${base}/documents/connect`, { modules: selected });
    setData(r.data.overview);
    const skipped: { module: string }[] = r.data.skipped || [];
    setNotice(`Connected ${r.data.connected.length} document(s).` +
      (skipped.length ? ` Skipped (not generated yet): ${skipped.map((s) => s.module).join(', ')}.` : ''));
    setSelected([]);
  });

  const disconnect = (module: string) => run(`disc-${module}`, async () => {
    const r = await api.post(`${base}/documents/disconnect`, { module });
    setData(r.data.overview);
    setNotice(r.data.message);
    setConfirmDisconnect(null);
  });

  const download = (doc: DocInfo) => run(`dl-${doc.id}`, async () => {
    const r = await api.get(`${base}/documents/${doc.id}/download`, { responseType: 'blob' });
    const url = URL.createObjectURL(new Blob([r.data]));
    const a = document.createElement('a');
    a.href = url; a.download = doc.filename || `${doc.document_number}.xlsx`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  const regenerate = (doc: DocInfo) => run(`regen-${doc.id}`, async () => {
    const r = await api.post(`${base}/documents/${doc.id}/regenerate`);
    setData(r.data.overview);
    if (r.data.ok) setNotice(`${doc.module_name} regenerated as ${r.data.document.revision_label}. Connect it to link the new revision.`);
    else setError(`${doc.module_name} generation failed: ${r.data.error}`);
  });

  const uploadSource = (file: File) => run('source', async () => {
    const fd = new FormData();
    fd.append('kind', 'iodb');
    fd.append('file', file);
    const r = await api.post(`${base}/sources`, fd);
    setData(r.data.overview);
    setNotice(`IODB registered as Rev ${r.data.rev_no}. Documents generated from an earlier revision are flagged below.`);
  });

  const openPlan = () => {
    setPlanModules(modules.filter((m) => m.latest?.can_regenerate).map((m) => m.module));
    setSteps(null);
    setShowPlan(true);
  };

  const runPlan = () => run('generate', async () => {
    setShowPlan(false);
    setSteps([]);
    const r = await api.post(`${base}/documents/generate-connected`, { modules: planModules }, { timeout: 600000 });
    setSteps(r.data.steps);
    setData(r.data.overview);
  });

  const toggle = (arr: string[], set: (v: string[]) => void, m: string) =>
    set(arr.includes(m) ? arr.filter((x) => x !== m) : [...arr, m]);

  // ── Render ────────────────────────────────────────────────────────────────
  const card = 'rounded-2xl p-5';
  const cardSt = { background: 'var(--s2)', border: '1px solid var(--b1)' };
  const heading = 'text-[11px] font-bold uppercase tracking-wider mb-3';

  return (
    <div className="space-y-4">
      <ProjectSelector compact />

      {!projectId && (
        <Alert variant="info">
          Select or enter a project above. Documents generated by the Instrument List, I/O List,
          Cable Schedule and Loop Wiring generators while a project is selected appear here automatically.
        </Alert>
      )}
      {error && <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>}
      {notice && <Alert variant="success" onClose={() => setNotice(null)}>{notice}</Alert>}

      {projectId && data && (
        <>
          {/* Source + actions */}
          <div className={card} style={cardSt}>
            <div className="flex flex-wrap items-center gap-3 justify-between">
              <div className="text-xs" style={{ color: 'var(--t1)' }}>
                <span className="font-semibold" style={{ color: 'var(--t0)' }}>Source IODB: </span>
                {data.sources.iodb ? `Rev ${data.sources.iodb.rev_no} · ${data.sources.iodb.filename}` : 'none registered yet'}
                {data.sources.loop_input && (
                  <span className="ml-4">
                    <span className="font-semibold" style={{ color: 'var(--t0)' }}>Loop input: </span>
                    Rev {data.sources.loop_input.rev_no}
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <label className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-bold cursor-pointer"
                  style={{ background: 'var(--s3)', border: '1px solid var(--b2)', color: 'var(--t1)' }}>
                  <Upload className="w-3.5 h-3.5" /> Register new IODB revision
                  <input type="file" accept=".xlsx,.xls,.xlsm" className="hidden"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadSource(f); e.target.value = ''; }} />
                </label>
                <Button variant="secondary" size="sm" onClick={load} loading={loading}>
                  <RefreshCw className="w-3.5 h-3.5" /> Refresh Connections
                </Button>
              </div>
            </div>
          </div>

          {/* Connected engineering documents */}
          <div className={card} style={cardSt}>
            <p className={heading} style={{ color: 'var(--t2)' }}>Connected Engineering Documents</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {modules.map((m) => {
                const ui = STATE_UI[m.state];
                const doc = m.linked ?? m.latest;
                const canSelect = !!m.latest;
                return (
                  <div key={m.module} className="rounded-xl p-4"
                    style={{ background: 'var(--s3)', border: '1px solid var(--b2)', opacity: canSelect ? 1 : 0.75 }}>
                    <div className="flex items-start gap-3">
                      <input type="checkbox" disabled={!canSelect} checked={selected.includes(m.module)}
                        onChange={() => toggle(selected, setSelected, m.module)} className="mt-1" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-sm font-bold" style={{ color: 'var(--t0)' }}>{m.module_name}</p>
                          <Badge variant={ui.variant}>{ui.label}</Badge>
                        </div>
                        {doc ? (
                          <dl className="mt-2 grid grid-cols-[auto,1fr] gap-x-3 gap-y-0.5 text-xs" style={{ color: 'var(--t1)' }}>
                            <dt style={{ color: 'var(--t2)' }}>File</dt><dd className="truncate">{doc.filename}</dd>
                            <dt style={{ color: 'var(--t2)' }}>Revision</dt>
                            <dd>
                              {doc.revision_label}
                              {m.flags.includes('new_revision_available') && m.latest &&
                                <span style={{ color: 'var(--gold)' }}> → {m.latest.revision_label} available</span>}
                            </dd>
                            <dt style={{ color: 'var(--t2)' }}>Status</dt><dd>{doc.status.replace('_', ' ')}</dd>
                            <dt style={{ color: 'var(--t2)' }}>Generated</dt><dd>{fmtDate(doc.generated_at)}</dd>
                            <dt style={{ color: 'var(--t2)' }}>{m.count_label}</dt>
                            <dd>{doc.record_count ?? '—'}</dd>
                          </dl>
                        ) : (
                          <p className="text-xs mt-2" style={{ color: 'var(--t2)' }}>
                            {m.state === 'failed' ? 'No successful revision yet.' : 'Generate this document from its generator page.'}
                          </p>
                        )}
                        {m.last_error && (
                          <p className="text-xs mt-2" style={{ color: 'var(--rose)' }}>Last attempt failed: {m.last_error}</p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex flex-wrap gap-2 mt-4">
              <Button onClick={connectSelected} disabled={selected.length === 0} loading={busy === 'connect'}>
                <Link2 className="w-4 h-4" /> Connect Selected Documents
              </Button>
            </div>
          </div>

          {/* Synchronisation */}
          <div className={card} style={cardSt}>
            <p className={heading} style={{ color: 'var(--t2)' }}>Document Synchronization</p>
            {needRegen.length > 0 && (
              <Alert variant="warning" title="Source IODB revision changed" className="mb-3">
                The following documents were generated from an earlier revision and may require regeneration:
                {' '}{needRegen.map((m) => m.module_name).join(', ')}. Engineering review is still required before use.
              </Alert>
            )}
            <div className="text-xs space-y-1" style={{ color: 'var(--t1)' }}>
              <p className="font-semibold" style={{ color: 'var(--t0)' }}>
                IODB {data.sources.iodb ? `Rev ${data.sources.iodb.rev_no}` : '—'}
              </p>
              {modules.map((m) => {
                const regen = m.flags.includes('regeneration_required');
                const icon = m.state === 'not_generated'
                  ? <span style={{ color: 'var(--t2)' }}>–</span>
                  : m.state === 'failed'
                    ? <XCircle className="w-3.5 h-3.5 inline" style={{ color: 'var(--rose)' }} />
                    : regen
                      ? <AlertTriangle className="w-3.5 h-3.5 inline" style={{ color: 'var(--gold)' }} />
                      : <CheckCircle2 className="w-3.5 h-3.5 inline" style={{ color: '#4ade80' }} />;
                return (
                  <p key={m.module} className="pl-4">
                    ↓ {m.module_name}{' '}{icon}{' '}
                    {m.state === 'not_generated' ? 'Not generated'
                      : m.state === 'failed' ? 'Failed'
                        : regen ? `Regeneration required (built from ${m.source_kind === 'iodb' ? 'IODB' : 'loop input'} Rev ${m.latest?.source_rev_no})`
                          : 'Current'}
                  </p>
                );
              })}
            </div>
            <p className="text-xs mt-3" style={{ color: 'var(--t2)' }}>
              {data.summary.current} current · {data.summary.regeneration_required} require regeneration
              {data.summary.new_revision_available > 0 && ` · ${data.summary.new_revision_available} with a newer revision to connect`}
              {data.summary.failed > 0 && ` · ${data.summary.failed} failed`}
            </p>
          </div>

          {/* Document register */}
          <div className={card} style={cardSt}>
            <p className={heading} style={{ color: 'var(--t2)' }}>Document Register</p>
            {generated.length === 0 ? (
              <p className="text-xs" style={{ color: 'var(--t2)' }}>No generated documents for this project yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead><tr style={{ color: 'var(--t2)' }}>
                    <th className={th}>Document</th><th className={th}>Document No.</th>
                    <th className={th}>Rev</th><th className={th}>Status</th>
                  </tr></thead>
                  <tbody>
                    {generated.map((m) => {
                      const d = m.linked ?? (m.latest as DocInfo);
                      return (
                        <tr key={m.module} style={{ borderTop: '1px solid var(--b1)', color: 'var(--t1)' }}>
                          <td className={td}>{d.document_name}</td>
                          <td className={`${td} font-mono`}>{d.document_number}</td>
                          <td className={td}>{d.revision_label}</td>
                          <td className={td}>{d.status.replace('_', ' ')}{!m.connected && ' (not linked)'}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Linked documents */}
          <div className={card} style={cardSt}>
            <p className={heading} style={{ color: 'var(--t2)' }}>Linked Documents</p>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead><tr style={{ color: 'var(--t2)' }}>
                  <th className={th}>Module</th><th className={th}>Document</th><th className={th}>Rev</th>
                  <th className={th}>IODB Rev</th><th className={th}>Status</th><th className={th}>Actions</th>
                </tr></thead>
                <tbody>
                  {modules.map((m) => {
                    const d = m.linked ?? m.latest;
                    const ui = STATE_UI[m.state];
                    return (
                      <tr key={m.module} style={{ borderTop: '1px solid var(--b1)', color: 'var(--t1)' }}>
                        <td className={td}>{m.module_name}</td>
                        <td className={td}>{d ? d.document_number : '—'}</td>
                        <td className={td}>{d ? d.revision_label : '—'}</td>
                        <td className={td}>{d?.source_rev_no != null ? `R${d.source_rev_no}` : '—'}</td>
                        <td className={td}><Badge variant={ui.variant}>{ui.label}</Badge></td>
                        <td className={td}>
                          <div className="flex flex-wrap gap-1.5">
                            {d?.has_file && (
                              <Button size="sm" variant="secondary" loading={busy === `dl-${d.id}`} onClick={() => download(d)}>
                                <Download className="w-3 h-3" /> Download
                              </Button>
                            )}
                            {m.latest?.can_regenerate && (
                              <Button size="sm" variant="secondary" loading={busy === `regen-${m.latest.id}`}
                                onClick={() => regenerate(m.latest as DocInfo)}>
                                <RefreshCw className="w-3 h-3" /> Regenerate
                              </Button>
                            )}
                            {d && onUseDocument && (
                              <Button size="sm" variant="secondary" onClick={() => onUseDocument(d, projectId)}>
                                <FileText className="w-3 h-3" /> Use in cover sheet
                              </Button>
                            )}
                            {m.connected && (
                              <Button size="sm" variant="ghost" onClick={() => setConfirmDisconnect(m.module)}>
                                <Unlink className="w-3 h-3" /> Disconnect
                              </Button>
                            )}
                          </div>
                          {confirmDisconnect === m.module && (
                            <div className="mt-2 rounded-lg p-3" style={{ background: 'var(--gold-dim)', border: '1px solid rgba(245,158,11,0.3)' }}>
                              <p className="text-xs" style={{ color: 'var(--t0)' }}>
                                Disconnecting this document will remove it from the current Coversheet linkage
                                but will not delete the generated file.
                              </p>
                              <div className="flex gap-2 mt-2">
                                <Button size="sm" variant="danger" loading={busy === `disc-${m.module}`}
                                  onClick={() => disconnect(m.module)}>Confirm</Button>
                                <Button size="sm" variant="secondary" onClick={() => setConfirmDisconnect(null)}>Cancel</Button>
                              </div>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Generate connected documents */}
          <div className={card} style={cardSt}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className={heading} style={{ color: 'var(--t2)', marginBottom: 4 }}>Generate Connected Documents</p>
                <p className="text-xs" style={{ color: 'var(--t2)' }}>
                  Re-runs the selected generators from the project's latest stored IODB using each module's
                  last settings. Nothing is regenerated automatically.
                </p>
              </div>
              <Button onClick={openPlan} loading={busy === 'generate'} disabled={!data.sources.iodb && !data.sources.loop_input}>
                <Play className="w-4 h-4" /> Generate Connected Documents
              </Button>
            </div>

            {showPlan && (
              <div className="mt-4 rounded-xl p-4" style={{ background: 'var(--s3)', border: '1px solid var(--b2)' }}>
                <p className="text-xs font-bold mb-2" style={{ color: 'var(--t0)' }}>Generation plan</p>
                <ul className="text-xs space-y-1" style={{ color: 'var(--t1)' }}>
                  <li>✓ IODB validation (Rev {data.sources.iodb?.rev_no ?? '—'})</li>
                  {modules.map((m) => {
                    const can = !!m.latest?.can_regenerate;
                    return (
                      <li key={m.module}>
                        <label className="inline-flex items-center gap-2">
                          <input type="checkbox" disabled={!can} checked={planModules.includes(m.module)}
                            onChange={() => toggle(planModules, setPlanModules, m.module)} />
                          {m.module_name}
                          {!can && <span style={{ color: 'var(--t2)' }}> — generate once from its own page first</span>}
                        </label>
                      </li>
                    );
                  })}
                  <li style={{ color: 'var(--t2)' }}>Then review the linked documents and generate the Coversheet below.</li>
                </ul>
                <div className="flex gap-2 mt-3">
                  <Button size="sm" onClick={runPlan} disabled={planModules.length === 0}>Run plan</Button>
                  <Button size="sm" variant="secondary" onClick={() => setShowPlan(false)}>Cancel</Button>
                </div>
              </div>
            )}

            {busy === 'generate' && (
              <p className="text-xs mt-4 flex items-center gap-2" style={{ color: 'var(--t1)' }}>
                <Loader2 className="w-4 h-4 animate-spin" /> Generating selected documents in sequence…
              </p>
            )}

            {steps && steps.length > 0 && (
              <div className="mt-4 space-y-1.5">
                {steps.map((s, i) => (
                  <div key={s.step} className="flex items-start gap-2 text-xs" style={{ color: 'var(--t1)' }}>
                    {s.status === 'ok'
                      ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" style={{ color: '#4ade80' }} />
                      : s.status === 'needs_input'
                        ? <AlertTriangle className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--gold)' }} />
                        : <XCircle className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--rose)' }} />}
                    <span>
                      <span className="font-semibold">{i + 1}/{steps.length} {s.label}</span>
                      {' — '}{s.message}
                      {s.status === 'failed' && s.step !== 'iodb_check' && (() => {
                        const m = modules.find((x) => x.module === s.step);
                        const doc = m?.latest;
                        return doc?.can_regenerate ? (
                          <button className="ml-2 underline" style={{ color: 'var(--em-lt)' }}
                            onClick={() => regenerate(doc)}>Retry failed module</button>
                        ) : null;
                      })()}
                    </span>
                  </div>
                ))}
                {steps.every((s) => s.status === 'ok') ? (
                  <Alert variant="success" className="mt-3">
                    All selected documents generated successfully. Connect the new revisions, review them,
                    then generate the Coversheet.
                  </Alert>
                ) : (
                  <Alert variant="error" className="mt-3">
                    {steps.filter((s) => s.status === 'failed').map((s) => s.label.replace(/^Generating /, '')).join(', ') || 'A module'}
                    {' '}did not complete. The Coversheet was not finalized because one connected document is incomplete.
                    Documents that generated successfully were kept.
                  </Alert>
                )}
              </div>
            )}
          </div>

          {/* Overall readiness */}
          <div className={card} style={cardSt}>
            <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--t1)' }}>
              <FileSpreadsheet className="w-4 h-4" style={{ color: 'var(--em)' }} />
              {data.summary.coversheet_ready
                ? 'All connected documents are current - ready to generate the Coversheet.'
                : anyFailed
                  ? 'One or more documents failed - the Coversheet should not be finalized yet.'
                  : needRegen.length > 0
                    ? 'Documents need regeneration - review before finalizing the Coversheet.'
                    : 'Connect the generated documents above to link them to the Coversheet.'}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
