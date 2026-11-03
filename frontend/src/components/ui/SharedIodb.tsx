/**
 * Shared IODB UI - the ONLY thing the generators use to obtain an IODB.
 *
 *   IODB Source:  ( ) Use Saved IODB   ( ) Upload New IODB
 *
 * Whatever the source, the generator receives a plain `File` through the same `onChange` its old upload card used,
 * so everything downstream (analyze, filters, templates, generation, download) is untouched.
 */
import { useEffect, useRef, useState } from 'react';
import { Upload, CheckCircle2, Database, Loader2 } from 'lucide-react';
import { useSharedIodb } from '@/context/SharedIodbContext';
import { sharedIodb, formatUploaded } from '@/services/sharedIodb';

type Source = 'saved' | 'upload';

interface PanelProps {
  file: File | null;
  onChange: (file: File | null) => void;
  accept?: string;
  /** Compact drop zone (Datasheet generator). */
  compact?: boolean;
}

const errText = (e: any, fallback: string) => e?.response?.data?.detail || e?.message || fallback;

export function SharedIodbPanel({ file, onChange, accept = '.xlsx,.xls', compact = false }: PanelProps) {
  const { info, publish } = useSharedIodb();
  const [chosen, setChosen] = useState<Source | null>(null);       // null = follow availability
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<File | null>(null);       // new file waiting for the replace confirmation
  const loadedStamp = useRef<string | null>(null);                 // which Shared IODB version `file` was loaded from
  const available = !!info?.available;
  const source: Source = chosen ?? (available ? 'saved' : 'upload');

  // "Use Saved IODB": hand the CURRENT Shared IODB to the generator (re-fetched whenever it changed -> never stale).
  useEffect(() => {
    if (source !== 'saved') return;
    if (!available) { if (loadedStamp.current) { loadedStamp.current = null; onChange(null); } return; }
    if (loadedStamp.current === info!.uploaded_at) return;
    let cancelled = false;
    const stamp = info!.uploaded_at ?? null;
    setBusy(true);
    sharedIodb.fetchFile(info!.file_name || 'IODB.xlsx')
      .then((f) => { if (!cancelled) { loadedStamp.current = stamp; setError(null); onChange(f); } })
      .catch((e) => { if (!cancelled) setError(errText(e, 'Could not load the saved IODB')); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [source, available, info?.uploaded_at, info?.file_name]); // eslint-disable-line react-hooks/exhaustive-deps

  const pickSource = (next: Source) => {
    if (next === source) return;
    setError(null);
    setChosen(next);
    loadedStamp.current = null;
    if (next === 'upload') onChange(null);                          // the generator starts from "no IODB chosen yet"
  };

  const doUpload = async (f: File) => {
    setBusy(true);
    setError(null);
    try {
      const next = await sharedIodb.upload(f);                       // validated server-side; invalid -> throws, nothing replaced
      publish(next);
      loadedStamp.current = next.uploaded_at ?? null;
      setChosen('saved');
      onChange(f);
    } catch (e: any) {
      setError(errText(e, 'IODB upload failed'));
      if (available) { setChosen('saved'); loadedStamp.current = null; }   // keep using the previous Shared IODB
    } finally {
      setBusy(false);
    }
  };

  const choose = (f: File | null) => {
    if (!f) return;
    if (available) setPending(f);                                    // confirm before replacing the Shared IODB
    else doUpload(f);
  };

  const radio = (value: Source, label: string) => (
    <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: 'var(--t0)' }}>
      <input type="radio" name="iodb-source" checked={source === value} onChange={() => pickSource(value)} />
      {label}
    </label>
  );

  return (
    <div className="space-y-3">
      {available ? (
        <div className="rounded-xl p-3" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
          <p className="text-[11px] font-semibold flex items-center gap-1.5" style={{ color: 'var(--em-lt)' }}>
            <Database className="w-3 h-3" /> Shared IODB Available
          </p>
          <p className="text-xs font-semibold mt-1 truncate" style={{ color: 'var(--t0)' }} title={info!.file_name || ''}>{info!.file_name}</p>
          <p className="text-[11px]" style={{ color: 'var(--t2)' }}>
            Uploaded: {formatUploaded(info!.uploaded_at)} · Status: {info!.status === 'Validated' ? 'Available' : info!.status}
          </p>
          <div className="flex gap-5 mt-2.5">
            {radio('saved', 'Use Saved IODB')}
            {radio('upload', 'Upload New IODB')}
          </div>
        </div>
      ) : (
        <p className="text-xs" style={{ color: 'var(--t2)' }}>No Shared IODB available.</p>
      )}

      {source === 'upload' && (
        <label
          className={`flex items-center justify-center rounded-xl cursor-pointer transition-all ${compact ? 'gap-3 px-4 py-3' : 'flex-col'}`}
          style={{ background: file ? 'rgba(74,222,128,0.05)' : 'var(--s1)', border: `1.5px dashed ${file ? 'rgba(74,222,128,0.3)' : 'var(--b2)'}`, padding: compact ? undefined : '20px 16px' }}
        >
          {busy ? <Loader2 className="w-5 h-5 animate-spin" style={{ color: 'var(--em)' }} />
            : file ? <CheckCircle2 className="w-5 h-5" style={{ color: 'var(--em)' }} /> : <Upload className="w-5 h-5" style={{ color: 'var(--t2)' }} />}
          <span className="text-xs font-semibold" style={{ color: file ? 'var(--em-lt)' : 'var(--t1)' }}>
            {busy ? 'Validating IODB…' : file ? file.name : 'Upload New IODB'}
          </span>
          {!file && !busy && <span className="text-[11px]" style={{ color: 'var(--t2)' }}>{accept.split(',').join(', ')}</span>}
          <input type="file" accept={accept} className="hidden" disabled={busy}
            onChange={(e) => { choose(e.target.files?.[0] || null); e.target.value = ''; }} />
        </label>
      )}

      {source === 'saved' && available && (
        <p className="text-[11px] flex items-center gap-1.5" style={{ color: file ? 'var(--em-lt)' : 'var(--t2)' }}>
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : file ? <CheckCircle2 className="w-3 h-3" /> : null}
          {busy ? 'Loading saved IODB…' : file ? `Using ${file.name}` : ''}
        </p>
      )}

      {error && <p className="text-xs" style={{ color: 'var(--rose)' }}>{error}</p>}

      {pending && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.5)' }}>
          <div className="rounded-2xl p-6 max-w-md w-[92%]" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
            <h4 className="text-sm font-bold mb-2" style={{ color: 'var(--t0)' }}>A Shared IODB is already available.</h4>
            <p className="text-xs" style={{ color: 'var(--t1)' }}>Current:</p>
            <p className="text-xs font-semibold mb-2 break-all" style={{ color: 'var(--t0)' }}>{info?.file_name}</p>
            <p className="text-xs" style={{ color: 'var(--t1)' }}>New:</p>
            <p className="text-xs font-semibold mb-3 break-all" style={{ color: 'var(--t0)' }}>{pending.name}</p>
            <p className="text-xs mb-4" style={{ color: 'var(--t1)' }}>Uploading the new IODB will replace the Shared IODB for the current login session.</p>
            <div className="flex justify-end gap-2">
              <button className="px-3 py-1.5 rounded-lg text-xs" style={{ background: 'var(--s3)', color: 'var(--t0)', border: '1px solid var(--b1)' }}
                onClick={() => setPending(null)}>Cancel</button>
              <button className="px-3 py-1.5 rounded-lg text-xs font-semibold" style={{ background: 'var(--em)', color: '#fff' }}
                onClick={() => { const f = pending; setPending(null); doUpload(f); }}>Replace Shared IODB</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface CardProps extends PanelProps {
  title: string;
  icon?: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
  hint?: string;
  children?: React.ReactNode;
}

/** Drop-in replacement for the IODB `FileUploadCard`: same look, same props, same children (e.g. the Analyze button). */
export default function SharedIodbCard({ title, icon: Icon = Upload, hint, children, ...panel }: CardProps) {
  return (
    <div className="rounded-2xl p-5" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
      <h3 className="text-sm font-bold flex items-center gap-2 mb-4" style={{ color: 'var(--t0)' }}>
        <span className="w-6 h-6 rounded-lg flex items-center justify-center" style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
          <Icon className="w-3 h-3" style={{ color: 'var(--em)' }} />
        </span>
        {title}
      </h3>
      <SharedIodbPanel {...panel} />
      {hint && <p className="text-[11px] mt-3 leading-relaxed" style={{ color: 'var(--t2)' }}>{hint}</p>}
      {children}
    </div>
  );
}

/** Small, non-intrusive indicator for the page header. */
export function SharedIodbChip() {
  const { info } = useSharedIodb();
  if (!info?.available) return null;
  return (
    <span className="hidden md:flex items-center gap-1.5 text-[11px] max-w-[220px] px-2 py-1 rounded-lg" title={`Shared IODB: ${info.file_name}`}
      style={{ color: 'var(--t1)', background: 'var(--s2)', border: '1px solid var(--b1)' }}>
      <Database className="w-3 h-3 flex-shrink-0" style={{ color: 'var(--em)' }} />
      <span className="truncate">Shared IODB: {info.file_name}</span>
    </span>
  );
}

/**
 * Loop Wiring: OPTIONAL only. The Loop Wiring input file stays the required input exactly as before; when a Shared
 * IODB exists this offers it as the Loop Wiring input file (its Tag column is read by the existing reader).
 */
export function SharedIodbOptionalInput({ onUse }: { onUse: (file: File) => void }) {
  const { info } = useSharedIodb();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!info?.available) return null;
  return (
    <div className="rounded-xl p-3 flex items-center justify-between gap-3" style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}>
      <div className="min-w-0">
        <p className="text-[11px] font-semibold flex items-center gap-1.5" style={{ color: 'var(--em-lt)' }}><Database className="w-3 h-3" /> Shared IODB Available (optional)</p>
        <p className="text-xs font-semibold truncate" style={{ color: 'var(--t0)' }}>{info.file_name}</p>
        <p className="text-[11px]" style={{ color: 'var(--t2)' }}>Uploaded: {formatUploaded(info.uploaded_at)}. Optional: use it as the Loop Wiring input file instead of uploading one.</p>
        {error && <p className="text-xs" style={{ color: 'var(--rose)' }}>{error}</p>}
      </div>
      <button disabled={busy} className="px-3 py-1.5 rounded-lg text-xs font-semibold flex-shrink-0" style={{ background: 'var(--s3)', color: 'var(--t0)', border: '1px solid var(--b1)' }}
        onClick={async () => {
          setBusy(true); setError(null);
          try { onUse(await sharedIodb.fetchFile(info.file_name || 'IODB.xlsx')); } catch (e: any) { setError(errText(e, 'Could not load the saved IODB')); } finally { setBusy(false); }
        }}>
        {busy ? 'Loading…' : 'Use Saved IODB'}
      </button>
    </div>
  );
}
