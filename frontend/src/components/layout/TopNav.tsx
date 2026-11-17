/**
 * Top navigation: brand, the six work areas, a sliding signal indicator under the active area, a structured
 * "Generate" menu (and role-filtered Admin menu), and a full-screen sheet on small screens.
 */
import { NavLink, Link, useLocation } from 'react-router-dom';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ChevronDown, Menu, X, ArrowRight } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { visibleSections, isActive, NavSection } from './nav';

/** The mark: a dotless "ı" whose dot is the signal lamp. */
export function BrandMark({ ink = 'var(--ink)', fg = 'var(--ink-fg)', size = 32 }: { ink?: string; fg?: string; size?: number }) {
  return (
    <span className="relative flex items-center justify-center flex-shrink-0" style={{ width: size, height: size, borderRadius: size * 0.28, background: ink }}>
      <span className="font-bold leading-none" style={{ fontFamily: 'var(--font-display)', color: fg, fontSize: size * 0.62, marginTop: size * 0.14 }}>ı</span>
      <span className="absolute rounded-full" style={{ width: size * 0.17, height: size * 0.17, top: size * 0.19, left: '50%', transform: 'translateX(-50%)', background: '#ff6a2b' }} />
    </span>
  );
}

export function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2.5 flex-shrink-0 group" aria-label="iEZ home">
      <BrandMark />
      <span className="leading-none hidden sm:block">
        <span className="block text-[17px] font-bold" style={{ fontFamily: 'var(--font-display)', color: 'var(--t0)', letterSpacing: '-0.035em' }}>iEZ</span>
        <span className="block mono text-[9.5px] mt-[3px] tracking-[.12em]" style={{ color: 'var(--t2)' }}>WABAG · INSTR</span>
      </span>
    </Link>
  );
}

function MenuPanel({ section, pathname, onPick, wide }: { section: NavSection; pathname: string; onPick: () => void; wide: boolean }) {
  return (
    <div className="mega glass" style={{ width: wide ? 640 : 300, left: 0 }} role="menu">
      <div className={wide ? 'grid grid-cols-2 gap-0.5' : 'grid gap-0.5'}>
        {section.items.map((it, i) => {
          const Icon = it.icon;
          const active = isActive(it, pathname);
          return (
            <NavLink key={it.path} to={it.path} end={it.exact ?? false} onClick={onPick} className={`mega-row ${active ? 'active' : ''}`} role="menuitem">
              <span className="ic"><Icon className="w-[17px] h-[17px]" strokeWidth={1.8} /></span>
              <span className="min-w-0">
                <span className="flex items-center gap-2">
                  <span className="text-[13.5px] font-semibold" style={{ color: 'var(--t0)' }}>{it.label}</span>
                  {active && <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--em)' }} />}
                </span>
                <span className="block text-[12.5px] leading-snug mt-0.5" style={{ color: 'var(--t1)' }}>{it.hint}</span>
              </span>
              <span className="ml-auto mono text-[10px] pt-1" style={{ color: 'var(--t2)' }}>{section.code}.{String(i + 1).padStart(2, '0')}</span>
            </NavLink>
          );
        })}
      </div>
      {wide && (
        <Link to="/cable-schedule" onClick={onPick} className="mt-2 flex items-center gap-3 px-4 py-3 rounded-[10px] group" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: 'var(--em)', animation: 'blink 2.4s ease-in-out infinite' }} />
          <span className="text-[12.5px]" style={{ color: 'var(--t1)' }}><b style={{ color: 'var(--t0)' }}>Cable Schedule Complete</b> - one IODB to one workbook: schedule, I/O summary, gland and lug quantities.</span>
          <ArrowRight className="w-4 h-4 ml-auto transition-transform group-hover:translate-x-1" style={{ color: 'var(--t1)' }} />
        </Link>
      )}
    </div>
  );
}

export default function TopNav({ mobile }: { mobile: boolean }) {
  const { pathname } = useLocation();
  const { role } = useAuth();
  const sections = visibleSections(role);
  const [open, setOpen] = useState<string | null>(null);
  const [sheet, setSheet] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const refs = useRef<Record<string, HTMLElement | null>>({});
  const timer = useRef<number | null>(null);
  const [ind, setInd] = useState({ x: 0, w: 0, on: false });

  const activeSection = sections.find((s) => s.items.some((i) => isActive(i, pathname)));
  const measure = () => {
    const el = activeSection ? refs.current[activeSection.label] : null;
    if (!el || !wrap.current) { setInd((v) => ({ ...v, on: false })); return; }
    const pad = 12;
    setInd({ x: el.offsetLeft + pad, w: el.offsetWidth - pad * 2, on: true });
  };
  useLayoutEffect(measure, [pathname, role, mobile]);
  useEffect(() => { window.addEventListener('resize', measure); const t = window.setTimeout(measure, 300); return () => { window.removeEventListener('resize', measure); window.clearTimeout(t); }; });
  useEffect(() => { setOpen(null); setSheet(false); }, [pathname]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') { setOpen(null); setSheet(false); } };
    const click = (e: MouseEvent) => { if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(null); };
    window.addEventListener('keydown', key); document.addEventListener('mousedown', click);
    return () => { window.removeEventListener('keydown', key); document.removeEventListener('mousedown', click); };
  }, []);

  const hover = (label: string | null, delay: number) => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(label), delay);
  };

  if (mobile) {
    return (
      <>
        <button onClick={() => setSheet(true)} className="tn-item !px-2.5" aria-label="Open navigation"><Menu className="w-5 h-5" /></button>
        <Brand />
        {sheet && (
          <div className="sheet">
            <div className="flex items-center justify-between px-5 h-16" style={{ borderBottom: '1px solid var(--b1)' }}>
              <Brand />
              <button onClick={() => setSheet(false)} className="tn-item !px-2.5" aria-label="Close navigation"><X className="w-5 h-5" /></button>
            </div>
            <div className="px-5 py-6 space-y-7">
              {sections.map((s) => (
                <div key={s.label}>
                  <p className="eyebrow mb-2">{s.code} · {s.label}</p>
                  {s.items.map((it) => {
                    const Icon = it.icon;
                    const active = isActive(it, pathname);
                    return (
                      <NavLink key={it.path} to={it.path} end={it.exact ?? false} className="flex items-center gap-3 py-3" style={{ borderBottom: '1px solid var(--b0)' }}>
                        <Icon className="w-5 h-5" style={{ color: active ? 'var(--em)' : 'var(--t1)' }} />
                        <span className="text-[17px] font-medium" style={{ color: 'var(--t0)', fontFamily: 'var(--font-display)' }}>{it.label}</span>
                        {active && <span className="ml-auto w-2 h-2 rounded-full" style={{ background: 'var(--em)' }} />}
                      </NavLink>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        )}
      </>
    );
  }

  return (
    <div className="flex items-center gap-7 h-full min-w-0">
      <Brand />
      <nav ref={wrap} className="relative flex items-center gap-0.5 h-full" aria-label="Main">
        <span className="tn-ind" style={{ transform: `translateX(${ind.x}px)`, width: ind.w, opacity: ind.on ? 1 : 0, left: 0 }} />
        {sections.map((s) => {
          const single = s.items.length === 1;
          const active = activeSection?.label === s.label;
          if (single) {
            const it = s.items[0];
            return (
              <NavLink key={s.label} to={it.path} end={it.exact ?? false} ref={(el) => { refs.current[s.label] = el; }}
                className={`tn-item ${active ? 'active' : ''}`} onMouseEnter={() => hover(null, 80)}>
                {s.top}
              </NavLink>
            );
          }
          return (
            <div key={s.label} ref={(el) => { refs.current[s.label] = el; }} className="relative h-full flex items-center" onMouseEnter={() => hover(s.label, 110)} onMouseLeave={() => hover(null, 160)}>
              <button className={`tn-item ${active ? 'active' : ''} ${open === s.label ? 'open' : ''}`}
                aria-expanded={open === s.label} aria-haspopup="menu" onClick={() => setOpen(open === s.label ? null : s.label)}>
                {s.top}
                <ChevronDown className="w-3.5 h-3.5 transition-transform duration-200" style={{ transform: open === s.label ? 'rotate(180deg)' : 'none', color: 'var(--t2)' }} />
              </button>
              {open === s.label && <MenuPanel section={s} pathname={pathname} wide={s.items.length > 4} onPick={() => setOpen(null)} />}
            </div>
          );
        })}
      </nav>
    </div>
  );
}
