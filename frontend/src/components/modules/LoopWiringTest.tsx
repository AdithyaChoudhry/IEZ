/**
 * LOOP WIRING (TEST) - experimental module, independent of the production Loop Wiring Generator.
 *
 *   IODB + I/O ASSIGNMENT + USER LOOP CONFIGURATION
 *     -> matching & validation -> generic renderer -> preview -> generated loops
 */
import { useCallback, useEffect, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import api from '@/services/api';
import { getCurrentProject } from '@/services/projectContext';
import Alert from '../ui/Alert';
import PageHeader from '../ui/PageHeader';
import ProjectSelector from '../ui/ProjectSelector';
import InputsStep from './loopTest/InputsStep';
import GraphDesigner from './loopTest/GraphDesigner';
import MatchStep from './loopTest/MatchStep';
import { IodbInfo, IoInfo, Library, MatchSummary } from './loopTest/types';

const SID_KEY = 'iez_loop_test_session';
const errText = (e: any, fb: string) => (typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : fb);

function SectionTitle({ n, title, done }: { n: number; title: string; done?: boolean }) {
  return (
    <h3 className="text-sm font-bold flex items-center gap-2 mt-2 mb-2" style={{ color: 'var(--t0)' }}>
      <span className="w-6 h-6 rounded-full text-[11px] flex items-center justify-center font-bold"
        style={{ background: done ? 'rgba(74,222,128,0.2)' : 'var(--s3)', color: done ? '#4ade80' : 'var(--t1)', border: '1px solid var(--b2)' }}>{done ? '✓' : n}</span>
      {title}
    </h3>
  );
}

export default function LoopWiringTest() {
  const [sid, setSid] = useState('');
  const [iodb, setIodb] = useState<IodbInfo | null>(null);
  const [io, setIo] = useState<IoInfo | null>(null);
  const [summary, setSummary] = useState<MatchSummary | null>(null);
  const [library, setLibrary] = useState<Library | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [designTag, setDesignTag] = useState('');
  const [version, setVersion] = useState(0);

  const loadLibrary = useCallback(() => {
    api.get<Library>('/loop-wiring-test/library').then((r) => setLibrary(r.data)).catch(() => setError('Could not load the loop library.'));
  }, []);
  useEffect(loadLibrary, [loadLibrary]);

  // restore the server-side session after a refresh / deploy
  useEffect(() => {
    let saved = '';
    try { saved = sessionStorage.getItem(SID_KEY) || ''; } catch { /* optional */ }
    if (!saved) return;
    api.get(`/loop-wiring-test/sessions/${saved}`).then((r) => {
      setSid(saved); setIodb(r.data.iodb); setIo(r.data.io);
      if (r.data.io) api.post(`/loop-wiring-test/sessions/${saved}/match`).then((m) => setSummary(m.data.summary)).catch(() => undefined);
    }).catch(() => { try { sessionStorage.removeItem(SID_KEY); } catch { /* optional */ } });
  }, []);

  const guard = async (fn: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(errText(e, 'Request failed.')); } finally { setBusy(false); }
  };

  const uploadIodb = (file: File, revision: string) => guard(async () => {
    const fd = new FormData();
    fd.append('iodb_file', file); fd.append('project_id', getCurrentProject()); fd.append('iodb_revision', revision);
    const r = await api.post('/loop-wiring-test/sessions', fd);
    setSid(r.data.session_id); setIodb(r.data.iodb); setIo(null); setSummary(null); setSelected([]); setDesignTag('');
    try { sessionStorage.setItem(SID_KEY, r.data.session_id); } catch { /* optional */ }
  });

  const uploadIo = (file: File, revision: string) => guard(async () => {
    const fd = new FormData();
    fd.append('io_file', file); fd.append('io_revision', revision);
    const r = await api.post(`/loop-wiring-test/sessions/${sid}/io`, fd);
    setIo({ ...r.data, confirmed: false }); setSummary(null); setSelected([]); setDesignTag('');
  });

  const confirmMapping = (mapping: Record<string, string | null>) => guard(async () => {
    const r = await api.put(`/loop-wiring-test/sessions/${sid}/io-mapping`, { mapping, confirm: true });
    setIo({ ...r.data, confirmed: true }); setSummary(null);
  });

  const runMatch = () => guard(async () => {
    const r = await api.post(`/loop-wiring-test/sessions/${sid}/match`);
    setSummary(r.data.summary);
  });

  const decide = async (body: Record<string, string>) => {
    try {
      const r = await api.post(`/loop-wiring-test/sessions/${sid}/decisions`, body);
      setSummary(r.data.summary); setVersion((v) => v + 1);
    } catch (e) { setError(errText(e, 'Could not save the decision.')); }
  };

  const ready = !!io?.confirmed;

  return (
    <div className="space-y-4">
      <PageHeader icon={FlaskConical} iconClassName="text-amber-500" title="Loop Wiring (Test)"
        description="Experimental: match the IODB with the I/O Assignment, design the loop, preview it and generate loop sheets. The production Loop Wiring Generator is not affected." />
      <ProjectSelector compact />
      <Alert variant="info">
        Nothing is guessed: values come from the IODB or the I/O Assignment (badged), conflicts need your decision, and anything missing is shown as MISSING.
      </Alert>
      {error && <Alert variant="error" onClose={() => setError('')}>{error}</Alert>}

      <SectionTitle n={1} title="Input files" done={ready} />
      <InputsStep iodb={iodb} io={io} busy={busy} onUploadIodb={uploadIodb} onUploadIo={uploadIo} onConfirmMapping={confirmMapping} />

      {ready && sid && (
        <>
          <SectionTitle n={2} title="Match tags / loops" done={!!summary} />
          <MatchStep sid={sid} summary={summary} busy={busy} version={version} selected={selected} onSelectedChange={setSelected}
            onMatch={runMatch} onDecision={decide} onDesign={(t) => { setDesignTag(t); window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }); }} />
        </>
      )}

      {ready && sid && summary && designTag && library && (
        <>
          <SectionTitle n={3} title="Design, preview and generate" />
          <GraphDesigner sid={sid} tag={designTag} library={library} selectedTags={selected.filter((t) => t !== designTag)}
            onBack={() => setDesignTag('')} onLibraryChanged={loadLibrary} onDecisionMade={() => { setVersion((v) => v + 1); runMatch(); }} />
        </>
      )}
    </div>
  );
}
