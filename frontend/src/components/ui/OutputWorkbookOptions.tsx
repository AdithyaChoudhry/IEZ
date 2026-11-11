/**
 * Output option + live preview of the workbook that will be generated.
 *
 * The sheet list is NOT hard-coded: it is fetched from the backend (`composition` endpoint), which plans it from the
 * actual template and the selected mode - the same plan the generator is checked against after generation, so the
 * downloaded workbook has exactly the sheets shown here.
 */
import { useEffect, useState } from 'react';
import { Check, EyeOff, Loader2 } from 'lucide-react';
import api from '@/services/api';
import Card from './Card';

export type OutputMode = 'WITHOUT_SUMMARY' | 'WITH_SUMMARY';

interface CompositionSheet {
  name: string;
  hidden: boolean;
  kind: 'template' | 'generated' | 'summary' | 'extra';
}

interface Props {
  /** e.g. '/io-list/composition' */
  endpoint: string;
  templateFile: File | null;
  mode: OutputMode;
  onModeChange: (mode: OutputMode) => void;
  /** "I/O Summary" / "Cable Summary" */
  summaryLabel: string;
  /** "I/O List" / "Cable Schedule" */
  listLabel: string;
  /** Shown when no template is uploaded (I/O List only). */
  noTemplateNote?: string;
  /** Extra form fields sent to the composition endpoint (Cable Schedule: selected extra sheets). */
  extraFields?: Record<string, string>;
}

export default function OutputWorkbookOptions({ endpoint, templateFile, mode, onModeChange, summaryLabel, listLabel, noTemplateNote, extraFields }: Props) {
  const [sheets, setSheets] = useState<CompositionSheet[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const form = new FormData();
    if (templateFile) form.append('template_file', templateFile);
    form.append('output_mode', mode);
    Object.entries(extraFields || {}).forEach(([k, v]) => form.append(k, v));
    api
      .post<{ sheets: CompositionSheet[] }>(endpoint, form, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((r) => { if (!cancelled) setSheets(r.data.sheets); })
      .catch((e) => { if (!cancelled) { setSheets(null); setError(e.response?.data?.detail || 'Could not read the template sheets'); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [endpoint, templateFile, mode, JSON.stringify(extraFields || {})]);

  const option = (value: OutputMode, title: string, text: string) => (
    <label
      className="flex items-start gap-3 rounded-xl p-3 cursor-pointer"
      style={{ background: mode === value ? 'var(--s3)' : 'transparent', border: `1px solid ${mode === value ? 'var(--em)' : 'var(--b1)'}` }}
    >
      <input type="radio" name={`output-mode-${endpoint}`} checked={mode === value} onChange={() => onModeChange(value)} className="mt-1" />
      <span>
        <span className="block text-sm font-semibold" style={{ color: 'var(--t0)' }}>{title}</span>
        <span className="block text-xs mt-0.5" style={{ color: 'var(--t1)' }}>{text}</span>
      </span>
    </label>
  );

  return (
    <Card title="Output Workbook" description={`Every sheet of the template is kept. The option only controls whether the ${summaryLabel} sheet is added.`}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {option('WITHOUT_SUMMARY', `${listLabel} without ${summaryLabel}`, `Template sheets + ${listLabel}`)}
        {option('WITH_SUMMARY', `${listLabel} with ${summaryLabel}`, `Template sheets + ${listLabel} + ${summaryLabel}`)}
      </div>

      <div className="mt-4 rounded-xl p-4" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }}>
        <p className="text-xs font-semibold mb-2" style={{ color: 'var(--t0)' }}>
          Output Workbook {loading && <Loader2 className="inline w-3 h-3 animate-spin ml-1" />}
        </p>
        {error && <p className="text-xs text-red-500">{error}</p>}
        {sheets && (
          <ul className="space-y-1" data-testid="output-workbook-sheets">
            {sheets.map((s) => (
              <li key={s.name} className="flex items-center gap-2 text-sm" style={{ color: 'var(--t0)' }}>
                <Check className="w-4 h-4 text-green-500 flex-shrink-0" />
                <span className={s.kind === 'template' ? '' : 'font-semibold'}>
                  {s.kind === 'generated' && !templateFile && noTemplateNote ? `${listLabel} (${noTemplateNote})` : s.name}
                </span>
                {s.kind === 'template' && <span className="text-xs" style={{ color: 'var(--t2)' }}>template sheet</span>}
                {s.kind === 'generated' && <span className="text-xs text-blue-500">generated</span>}
                {s.kind === 'summary' && <span className="text-xs text-blue-500">generated</span>}
                {s.kind === 'extra' && <span className="text-xs text-blue-500">generated</span>}
                {s.hidden && <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--t2)' }}><EyeOff className="w-3 h-3" />hidden in template</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
