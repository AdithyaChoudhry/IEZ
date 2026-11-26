/**
 * Confirm Cable Schedule header details (Cable Schedule Generator).
 * Every worksheet of the Cable Schedule carries the approved document header (PROJECT, CLIENT, DOCUMENT NO., PMC, DATE, LOCATION, REVISION). The values come from the
 * linked Cover Sheet. This form only appears when something cannot be taken from it: a missing / unusable value, or a cover that contradicts itself.
 * Verified values are shown read-only; the user types only what is missing. The details are used for this Cable Schedule only - the Cover Sheet and the project
 * master data are never changed. Backend: POST /cable-schedule/header-metadata and /cable-schedule/generate (header_overrides).
 */
import { useMemo } from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import Card from '../../ui/Card';
import Button from '../../ui/Button';
import Alert from '../../ui/Alert';

export interface HeaderField {
  key: string; label: string; value: string; candidate: string; source: '' | 'cover' | 'manual';
  status: 'ok' | 'missing' | 'invalid' | 'conflict'; message: string; input: 'text' | 'date'; allow_na: boolean; suggestions: string[];
}
export interface HeaderMeta {
  complete: boolean; fingerprint: string; cover_available: boolean; fields: HeaderField[];
  cover?: { available: boolean; message: string; document_number?: string | null; revision?: string | null };
}

const NA = 'N/A';

/** dd-mm-yyyy / dd.mm.yyyy / dd/mm/yyyy / yyyy-mm-dd -> true when it is a real calendar date. */
export function isValidDate(text: string): boolean {
  const t = text.trim();
  let m = /^(\d{1,2})[-./](\d{1,2})[-./](\d{4})$/.exec(t);
  let d: number, mo: number, y: number;
  if (m) { d = +m[1]; mo = +m[2]; y = +m[3]; } else {
    m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(t);
    if (!m) return false;
    y = +m[1]; mo = +m[2]; d = +m[3];
  }
  const dt = new Date(Date.UTC(y, mo - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === mo - 1 && dt.getUTCDate() === d && y >= 1990 && y <= 2100;
}

/** What the user still has to supply: the fields that are not verified, with the reason a value is not acceptable yet (empty = fine). */
export function pendingProblems(meta: HeaderMeta, values: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of meta.fields) {
    if (f.status === 'ok') continue;
    const v = (values[f.key] || '').trim();
    if (!v) out[f.key] = `${f.label} is required.`;
    else if (f.input === 'date' && !isValidDate(v)) out[f.key] = 'Enter a valid date (dd-mm-yyyy).';
    else if (v.toUpperCase() === NA && !f.allow_na) out[f.key] = `${f.label} cannot be N/A.`;
  }
  return out;
}

interface Props {
  meta: HeaderMeta;
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
  error?: string | null;
}

export default function HeaderConfirm({ meta, values, onChange, onConfirm, onCancel, busy, error }: Props) {
  const problems = useMemo(() => pendingProblems(meta, values), [meta, values]);
  const pending = meta.fields.filter((f) => f.status !== 'ok');
  const blocked = Object.keys(problems).length > 0;

  return (
    <div data-testid="header-confirm">
    <Card title="Confirm Cable Schedule header details" accentColor="#f59e0b">
      <p className="text-sm mb-1" style={{ color: 'var(--t1)' }}>
        Every worksheet of the Cable Schedule carries the same document header. The details below could not all be taken from the linked Cover Sheet —
        enter only the missing ones. They are used for this Cable Schedule only; the Cover Sheet is not changed.
      </p>
      {!meta.cover_available && (
        <Alert variant="warning" title="No linked Cover Sheet">
          {meta.cover?.message || 'No Cover Sheet is linked.'} Select a project with a resolved Cover Sheet to take these details from it, or enter all of them here.
        </Alert>
      )}
      {error && <div className="mt-2"><Alert variant="error" title="Header details">{error}</Alert></div>}

      <div className="mt-4 rounded-xl overflow-hidden" style={{ border: '1px solid var(--b1)' }}>
        {meta.fields.map((f) => {
          const ok = f.status === 'ok';
          const v = values[f.key] ?? '';
          const problem = problems[f.key];
          const na = v.trim().toUpperCase() === NA;
          return (
            <div key={f.key} className="grid grid-cols-1 sm:grid-cols-[170px_1fr] gap-2 sm:gap-4 px-4 py-3 items-start"
                 style={{ borderTop: '1px solid var(--b1)', background: ok ? 'transparent' : 'color-mix(in srgb, #f59e0b 7%, transparent)' }}>
              <div className="text-sm font-semibold flex items-center gap-2" style={{ color: 'var(--t0)' }}>
                {ok ? <CheckCircle2 className="w-4 h-4 text-green-600 flex-shrink-0" aria-label="verified" />
                    : <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" aria-label="needs input" />}
                {f.label}
              </div>
              <div>
                {ok ? (
                  <div className="text-sm" style={{ color: 'var(--t0)' }} data-testid={`hdr-${f.key}`}>
                    {f.value} <span className="text-xs ml-2" style={{ color: 'var(--t2)' }}>from the Cover Sheet</span>
                  </div>
                ) : (
                  <>
                    <div className="flex flex-wrap items-center gap-3">
                      <input
                        type="text"
                        inputMode={f.input === 'date' ? 'numeric' : undefined}
                        placeholder={f.input === 'date' ? 'dd-mm-yyyy' : f.key === 'pmc' ? 'Enter PMC name' : `Enter ${f.label.toLowerCase().replace(/\.$/, '')}`}
                        value={v}
                        disabled={na && f.allow_na}
                        onChange={(e) => onChange(f.key, e.target.value)}
                        aria-label={f.label}
                        aria-invalid={!!problem}
                        data-testid={`hdr-input-${f.key}`}
                        className="flex-1 min-w-[220px] border rounded-lg px-3 py-2 text-sm"
                        style={{ background: 'var(--s1)', color: 'var(--t0)', borderColor: problem && v ? 'var(--bad)' : 'var(--b2)' }}
                      />
                      {f.allow_na && (
                        <label className="text-sm flex items-center gap-2" style={{ color: 'var(--t1)' }}>
                          <input type="checkbox" checked={na} onChange={(e) => onChange(f.key, e.target.checked ? NA : '')} />
                          Not applicable
                        </label>
                      )}
                    </div>
                    {f.suggestions.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2 items-center text-xs" style={{ color: 'var(--t2)' }}>
                        The cover lists:
                        {f.suggestions.map((s) => (
                          <button key={s} type="button" className="px-2 py-0.5 rounded font-mono underline" style={{ background: 'var(--s3)' }}
                                  onClick={() => onChange(f.key, s)}>{s}</button>
                        ))}
                      </div>
                    )}
                    <div className="mt-1 text-xs" style={{ color: f.status === 'conflict' ? 'var(--warn, #b45309)' : 'var(--t2)' }}>
                      {f.message}
                    </div>
                    {problem && v && <div className="mt-1 text-xs" style={{ color: 'var(--bad)' }}>{problem}</div>}
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap gap-3 mt-5 justify-end">
        <Button variant="secondary" onClick={onCancel} disabled={busy} data-testid="header-cancel">Cancel</Button>
        <Button onClick={onConfirm} disabled={blocked} loading={busy} data-testid="header-confirm-generate">
          Confirm &amp; Generate
        </Button>
      </div>
      {blocked && (
        <p className="text-xs mt-2 text-right" style={{ color: 'var(--t2)' }}>
          Still needed: {pending.filter((f) => problems[f.key]).map((f) => f.label).join(', ')}
        </p>
      )}
    </Card>
    </div>
  );
}
