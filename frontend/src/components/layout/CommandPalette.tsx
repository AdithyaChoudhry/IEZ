/**
 * ⌘K / Ctrl+K command palette: jump to any module, run quick actions. Keyboard first: ↑ ↓ to move, ↵ to open, Esc to close.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, CornerDownLeft, Moon, Sun, PanelLeft, LogOut, Clock, ArrowUp, ArrowDown } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { useTheme } from '@/context/ThemeContext';
import { visibleSections, NAV_SECTIONS } from './nav';

export const RECENT_KEY = 'iez-recent';

interface Cmd {
  id: string;
  group: string;
  label: string;
  hint?: string;
  icon: React.ElementType;
  color: string;
  run: () => void;
  text: string;
}

function score(q: string, text: string): number {
  if (!q) return 1;
  const t = text.toLowerCase();
  const idx = t.indexOf(q);
  if (idx === 0) return 100;
  if (idx > 0) return 80 - Math.min(idx, 40) / 2;
  let i = 0, run = 0, best = 0;
  for (const ch of t) {
    if (ch === q[i]) { i++; run++; best = Math.max(best, run); if (i === q.length) return 30 + best * 3; } else run = 0;
  }
  return 0;
}

export function readRecent(): string[] {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch { return []; }
}

export default function CommandPalette({ open, onClose, onToggleRail }: { open: boolean; onClose: () => void; onToggleRail: () => void }) {
  const navigate = useNavigate();
  const { role, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => { if (open) { setQ(''); setSel(0); window.setTimeout(() => inputRef.current?.focus(), 10); } }, [open]);

  const cmds = useMemo<Cmd[]>(() => {
    const go = (path: string) => () => { onClose(); navigate(path); };
    const nav: Cmd[] = visibleSections(role).flatMap((s) => s.items.map((i) => ({
      id: i.path, group: 'Go to', label: i.label, hint: i.hint, icon: i.icon, color: i.color, run: go(i.path),
      text: `${i.label} ${i.hint || ''} ${i.keywords || ''} ${s.label}`,
    })));
    const actions: Cmd[] = [
      { id: 'theme', group: 'Actions', label: theme === 'dark' ? 'Switch to light appearance' : 'Switch to dark appearance', icon: theme === 'dark' ? Sun : Moon, color: '#f59e0b',
        run: () => { onClose(); window.setTimeout(toggleTheme, 120); }, text: 'theme appearance dark light mode' },
      { id: 'rail', group: 'Actions', label: 'Collapse / expand sidebar', icon: PanelLeft, color: '#64748b', run: () => { onClose(); onToggleRail(); }, text: 'sidebar collapse expand rail' },
      { id: 'logout', group: 'Actions', label: 'Sign out', icon: LogOut, color: '#f43f5e', run: () => { onClose(); logout(); navigate('/login'); }, text: 'sign out logout exit' },
    ];
    return [...nav, ...actions];
  }, [role, theme, navigate, onClose, onToggleRail, toggleTheme, logout]);

  const results = useMemo(() => {
    const query = q.trim().toLowerCase();
    if (!query) {
      const all = NAV_SECTIONS.flatMap((s) => s.items);
      const recent = readRecent().map((p) => cmds.find((c) => c.id === p)).filter(Boolean).slice(0, 4) as Cmd[];
      const rec = recent.map((c) => ({ ...c, group: 'Recent' }));
      return [...rec, ...cmds.filter((c) => !recent.includes(c) && (c.group !== 'Go to' || all.some((i) => i.path === c.id)))];
    }
    return cmds.map((c) => ({ c, s: Math.max(score(query, c.label.toLowerCase()) + 10, score(query, c.text.toLowerCase())) }))
      .filter((x) => x.s > 10).sort((a, b) => b.s - a.s).map((x) => x.c);
  }, [q, cmds]);

  useEffect(() => { setSel(0); }, [q]);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-i="${sel}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [sel]);

  if (!open) return null;
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(s + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); results[sel]?.run(); }
    else if (e.key === 'Escape') { e.preventDefault(); onClose(); }
  };

  let lastGroup = '';
  return (
    <div className="cmdk-overlay" onMouseDown={onClose} role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="cmdk glass" onMouseDown={(e) => e.stopPropagation()} onKeyDown={onKey}>
        <div className="flex items-center gap-3 px-5 h-[62px]" style={{ borderBottom: '1px solid var(--b1)' }}>
          <Search className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--em)' }} />
          <input ref={inputRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Where do you want to go?"
            className="flex-1 bg-transparent outline-none text-[17px]" style={{ color: 'var(--t0)', letterSpacing: '-0.01em' }} />
          <kbd className="k">esc</kbd>
        </div>
        <div ref={listRef} className="max-h-[52vh] overflow-y-auto p-2">
          {results.length === 0 && <p className="px-4 py-10 text-center text-[14px]" style={{ color: 'var(--t2)' }}>No match for “{q}”.</p>}
          {results.map((c, i) => {
            const head = c.group !== lastGroup ? c.group : '';
            lastGroup = c.group;
            const Icon = c.icon;
            return (
              <div key={c.group + c.id}>
                {head && <p className="eyebrow px-3 pt-3 pb-1.5 flex items-center gap-1.5">{head === 'Recent' && <Clock className="w-3 h-3" />}{head}</p>}
                <div data-i={i} className={`cmdk-row ${i === sel ? 'on' : ''}`} onMouseMove={() => setSel(i)} onClick={() => c.run()}>
                  <span className="w-9 h-9 rounded-[11px] flex items-center justify-center flex-shrink-0"
                    style={{ background: `linear-gradient(160deg, ${c.color}, color-mix(in srgb, ${c.color} 70%, #000))`, boxShadow: 'inset 0 1px 0 rgba(255,255,255,.25)' }}>
                    <Icon className="w-[18px] h-[18px] text-white" />
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-[14.5px] font-medium truncate" style={{ color: 'var(--t0)' }}>{c.label}</p>
                    {c.hint && <p className="text-[12.5px] truncate" style={{ color: 'var(--t2)' }}>{c.hint}</p>}
                  </div>
                  {i === sel && <CornerDownLeft className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--em)' }} />}
                </div>
              </div>
            );
          })}
        </div>
        <div className="flex items-center gap-4 px-5 h-11 text-[12px]" style={{ borderTop: '1px solid var(--b1)', color: 'var(--t2)' }}>
          <span className="flex items-center gap-1.5"><kbd className="k"><ArrowUp className="w-3 h-3" /></kbd><kbd className="k"><ArrowDown className="w-3 h-3" /></kbd>move</span>
          <span className="flex items-center gap-1.5"><kbd className="k"><CornerDownLeft className="w-3 h-3" /></kbd>open</span>
          <span className="ml-auto">iEZ</span>
        </div>
      </div>
    </div>
  );
}
