/**
 * One progress bar for every page: the real percentage while a file is being sent, then a moving bar with the elapsed
 * time while the server processes it (the server does not report how far it is, so no percentage is invented).
 */
import { useEffect, useState } from 'react';
import { Progress, uploadProgress } from '@/services/uploadProgress';

const SHOW_AFTER_MS = 400; // quick requests do not flash a bar

export default function UploadProgressBar() {
  const [items, setItems] = useState<Progress[]>([]);
  const [now, setNow] = useState(Date.now());
  useEffect(() => uploadProgress.subscribe(setItems), []);
  useEffect(() => {
    if (!items.length) return;
    const t = window.setInterval(() => { uploadProgress.prune(); setNow(Date.now()); }, 250);
    return () => window.clearInterval(t);
  }, [items.length]);

  const shown = items.filter((p) => now - p.started >= SHOW_AFTER_MS).slice(-3);
  if (!shown.length) return null;
  return (
    <div className="fixed bottom-4 right-4 z-[100] w-80 max-w-[calc(100vw-2rem)] space-y-2" role="status" aria-live="polite" data-testid="upload-progress">
      <style>{'@keyframes iez-progress{0%{left:-40%}100%{left:100%}}'}</style>
      {shown.map((p) => {
        const seconds = Math.floor((now - p.started) / 1000);
        const uploading = p.percent !== null;
        return (
          <div key={p.id} className="rounded-xl border p-3 shadow-lg" style={{ background: 'var(--s2)', borderColor: 'var(--b2)', color: 'var(--t0)' }}>
            <div className="flex justify-between text-xs mb-1.5">
              <span className="font-semibold">{uploading ? 'Uploading file…' : 'Processing on the server…'}</span>
              <span style={{ color: 'var(--t1)' }}>{uploading ? `${p.percent}%` : `${seconds} s`}</span>
            </div>
            <div className="relative h-2 overflow-hidden rounded-full" style={{ background: 'var(--s4)' }}
                 role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={p.percent ?? undefined}>
              <div className="absolute top-0 h-full rounded-full"
                   style={uploading ? { left: 0, width: `${p.percent}%`, background: 'var(--em)', transition: 'width .2s' }
                     : { width: '40%', background: 'var(--em)', animation: 'iez-progress 1.2s ease-in-out infinite' }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
