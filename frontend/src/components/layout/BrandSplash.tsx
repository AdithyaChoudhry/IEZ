/**
 * Brand intro: played when the iEZ mark (top-left) is clicked. ~6 s: the mark lands, its signal lamp drops in
 * and pulses, sparks radiate, "iEZ" rises, then "Built by Akash Balaji" is written on in script with a pen nib
 * and a flourish. Click or Esc closes it early. Reduced-motion users get a static card.
 */
import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { BrandMark } from './TopNav';

const SPARKS = 18;

export default function BrandSplash({ onDone }: { onDone: () => void }) {
  useEffect(() => {
    const id = window.setTimeout(onDone, 6100);
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') onDone(); };
    window.addEventListener('keydown', key);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { window.clearTimeout(id); window.removeEventListener('keydown', key); document.body.style.overflow = prev; };
  }, [onDone]);

  return createPortal(
    <div className="bs" onClick={onDone} role="dialog" aria-label="iEZ - built by Akash Balaji">
      <div className="bs-grid" />
      <div className="bs-glow" />
      <div className="bs-stage">
        {/* mark + lamp + rings + sparks */}
        <div className="bs-markwrap">
          <div className="bs-mark"><BrandMark size={96} ink="#f6f5f2" fg="#100f0e" /></div>
          <span className="bs-ring" style={{ animationDelay: '.8s' }} />
          <span className="bs-ring" style={{ animationDelay: '1.15s' }} />
          <span className="bs-ring" style={{ animationDelay: '1.5s' }} />
          {Array.from({ length: SPARKS }, (_, i) => (
            <span key={i} className="bs-spark" style={{ ['--a' as any]: `${(360 / SPARKS) * i + (i % 2 ? 7 : 0)}deg`, ['--r' as any]: `${130 + (i % 3) * 38}px`, animationDelay: `${0.8 + (i % 4) * 0.05}s` }} />
          ))}
        </div>

        {/* wordmark */}
        <h1 className="bs-word" aria-hidden>
          {['i', 'E', 'Z'].map((c, i) => <span key={c} style={{ animationDelay: `${1.0 + i * 0.14}s` }}>{c}</span>)}
          <span className="bs-dot" style={{ animationDelay: '1.5s' }}>.</span>
        </h1>

        {/* signature */}
        <div className="bs-sigwrap">
          <span className="bs-sig">Built by Akash Balaji</span>
          <span className="bs-nib" />
          <svg className="bs-flourish" viewBox="0 0 520 40" preserveAspectRatio="none" aria-hidden>
            <path d="M8 22 C 120 38, 230 6, 330 20 S 470 34, 512 10" pathLength={1} />
          </svg>
        </div>

        {/* caption + 4-20 mA trace */}
        <div className="bs-cap">
          <span>INSTRUMENTATION ENGINEERING EZ</span>
          <svg viewBox="0 0 120 16" aria-hidden><path d="M0 8 H24 L30 2 L36 14 L42 8 H62 C70 8 72 3 80 3 S92 13 100 13 H120" pathLength={1} /></svg>
          <span>VA TECH WABAG</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
