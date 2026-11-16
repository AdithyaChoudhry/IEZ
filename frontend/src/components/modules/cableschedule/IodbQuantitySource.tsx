/**
 * "Upload an IODB" input for the Gland Quantity and Cable Lug Quantity generators.
 *
 * The IODB is validated at once; the Cable Schedule is then generated from it by the existing Cable Schedule generator (the same
 * generation Cable Schedule Complete uses) and the module's own engine reads that schedule. Nothing else has to be uploaded - a
 * Cable Schedule template is asked for only when the server has none. Re-runs with new settings (OD, overrides, rules) reuse the
 * schedule generated from the same IODB, so they are fast.
 */
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, FileText, Loader2, Package, Upload } from 'lucide-react';
import api from '@/services/api';
import Card from '../../ui/Card';
import Button from '../../ui/Button';
import FileUploadCard from '../../ui/FileUploadCard';
import SharedIodbCard from '../../ui/SharedIodb';

type Row = Record<string, any>;
const mp = { headers: { 'Content-Type': 'multipart/form-data' } };

export interface IodbSourceHandle { run: (reuse?: boolean) => Promise<void>; hasGenerated: () => boolean }
interface Props {
  title: string;
  buttonLabel: string;
  startUrl: string;
  jobUrl: (id: string) => string;
  fields: () => Record<string, any>;           // extra form fields (rules, settings, OD data ...), read at call time
  onResult: (result: any) => void;
  onLive?: (live: any) => void;
  onReset?: () => void;
  setError: (m: string | null) => void;
}

const IodbQuantitySource = forwardRef<IodbSourceHandle, Props>(function IodbQuantitySource(props, ref) {
  const [iodb, setIodb] = useState<File | null>(null);
  const [template, setTemplate] = useState<File | null>(null);
  const [builtin, setBuiltin] = useState<boolean | null>(null);
  const [val, setVal] = useState<Row | null>(null);
  const [stage, setStage] = useState('');
  const [busy, setBusy] = useState(false);
  const generated = useRef(false);
  const timer = useRef<number | null>(null);
  const p = useRef(props);
  p.current = props;

  useEffect(() => { api.get('/cable-schedule/complete/status').then((r) => setBuiltin(r.data.builtin_template)).catch(() => setBuiltin(null)); }, []);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  useEffect(() => {
    setVal(null); generated.current = false; p.current.onReset?.();
    if (!iodb) return;
    let off = false;
    const fd = new FormData(); fd.append('file', iodb);
    api.post('/cable-schedule/complete/validate', fd, mp)
      .then((r) => { if (!off) { setVal(r.data); p.current.setError(null); } })
      .catch((e) => { if (!off) p.current.setError(e.response?.data?.detail || 'Could not validate the IODB'); });
    return () => { off = true; };
  }, [iodb]);

  const run = async (reuse = false) => {
    const cur = p.current;
    if (!reuse && !iodb) return;
    setBusy(true); cur.setError(null); setStage('Starting');
    try {
      const fd = new FormData();
      if (!reuse && iodb) fd.append('iodb_file', iodb);
      if (!reuse && template) fd.append('template_file', template);
      if (reuse) fd.append('reuse', 'true');
      Object.entries(cur.fields()).forEach(([k, v]) => { if (v !== null && v !== undefined) fd.append(k, v as any); });
      const start = await api.post(cur.startUrl, fd, mp);
      const poll = async () => {
        try {
          const r = await api.get(cur.jobUrl(start.data.job_id));
          setStage(r.data.stage || '');
          if (r.data.live) p.current.onLive?.(r.data.live);
          if (r.data.status === 'done') { generated.current = true; setBusy(false); p.current.onResult(r.data.result); return; }
          if (r.data.status === 'error') { setBusy(false); p.current.setError(r.data.error); return; }
          timer.current = window.setTimeout(poll, 800);
        } catch (e: any) { setBusy(false); p.current.setError(e.response?.data?.detail || 'Lost contact with the job'); }
      };
      poll();
    } catch (e: any) { setBusy(false); cur.setError(e.response?.data?.detail || 'Could not start'); }
  };
  useImperativeHandle(ref, () => ({ run, hasGenerated: () => generated.current }));

  const s = val?.stats;
  const needTemplate = builtin === false && !template;
  return (
    <div className="space-y-4" data-testid="iodb-source">
      <SharedIodbCard title={props.title} icon={Upload} file={iodb} onChange={setIodb} />
      {builtin === false && (
        <FileUploadCard title="Cable Schedule template (required once - none is installed on this server)" icon={FileText} file={template} onChange={setTemplate}
                        hint="The same template the Cable Schedule Generator uses; the cable schedule is generated from the IODB with it." />)}
      {val && (
        <Card title="IODB validation">
          {s && <p className="text-sm" style={{ color: 'var(--t0)' }}>{s.rows} rows · {s.unique_tags} unique tags · {s.cable_records} cable records · {s.unique_cable_tags} unique cable tags ({s.main_cable_tags} main, {s.branch_cable_tags} branch) · {s.jb_records} junction boxes</p>}
          <p className={`mt-2 text-sm font-semibold flex items-center gap-2 ${val.status === 'BLOCKED' ? 'text-red-500' : val.status === 'READY' ? 'text-green-600' : 'text-amber-600'}`}>
            {val.status === 'READY' ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
            {val.status === 'READY' ? 'Ready for Cable Schedule generation' : val.status === 'BLOCKED' ? 'Blocked - fix the IODB first' : 'Ready - with warnings'}</p>
          {val.errors?.map((e: string, i: number) => <p key={i} className="text-xs text-red-500 mt-1">{e}</p>)}
          {val.warnings?.map((e: string, i: number) => <p key={i} className="text-xs text-amber-600 mt-1">{e}</p>)}
        </Card>)}
      <Button onClick={() => run(false)} loading={busy} disabled={!iodb || !val?.ok || needTemplate} size="lg" fullWidth className="text-lg py-4">
        <Package className="w-6 h-6" />{busy ? 'Generating...' : props.buttonLabel}
      </Button>
      {busy && <p className="text-sm flex items-center gap-2" style={{ color: 'var(--t0)' }}><Loader2 className="w-4 h-4 animate-spin" style={{ color: 'var(--em)' }} />{stage || 'Working'}</p>}
      <p className="text-xs" style={{ color: 'var(--t1)' }}>Only the IODB is needed: the Cable Schedule is generated from it automatically (existing Cable Schedule generator), then read by this module.</p>
    </div>
  );
});

export default IodbQuantitySource;
