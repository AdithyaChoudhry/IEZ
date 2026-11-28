/**
 * Smart Datasheet Generator - why the number of physical instruments differs from the number of IODB records.
 * The counts come from the server (utils/datasheet_eligibility), which applies the same rule at generation.
 */
export interface InstrumentDiagnostics {
  records: number; soft_excluded: number; not_applicable_excluded: number; not_applicable_by_io: Record<string, number>;
  no_tag_excluded: number; duplicates_excluded: number; eligible: number;
}
export interface TagNote { tag: string; reason: string }

export default function InstrumentSummary({ diagnostics: d, conflicts, deletedTags }: {
  diagnostics: InstrumentDiagnostics; conflicts: TagNote[]; deletedTags: string[];
}) {
  const other = Object.entries(d.not_applicable_by_io).map(([io, n]) => `${io}: ${n}`).join(', ');
  const rows: [string, string | number][] = [
    ['Associated IODB records', d.records],
    ['SOFT records excluded', d.soft_excluded],
    ['Non-applicable I/O types', d.not_applicable_excluded ? `${d.not_applicable_excluded} (${other})` : 0],
    ...(d.no_tag_excluded ? [['Records without a tag number', d.no_tag_excluded] as [string, number]] : []),
    ['Duplicate records excluded', d.duplicates_excluded],
    ['Eligible physical instruments', d.eligible],
  ];
  return (
    <div className="rounded-xl px-3 py-2.5 text-xs" style={{ background: 'var(--s1)', border: '1px solid var(--b1)' }} data-testid="instrument-summary">
      <p className="font-semibold uppercase tracking-wider mb-1.5" style={{ color: 'var(--t2)' }}>Instrument identification summary</p>
      <dl className="grid grid-cols-[1fr_auto] gap-x-6 gap-y-0.5 max-w-md">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt style={{ color: 'var(--t1)' }}>{k}</dt><dd className="font-mono font-bold text-right" style={{ color: 'var(--t0)' }}>{v}</dd>
          </div>))}
      </dl>
      {deletedTags.length > 0 && (
        <p className="mt-1.5" style={{ color: 'var(--gold)' }}>
          {deletedTags.length} eligible tag(s) have STATUS "DELETED" in the IODB. They are marked in the tag list: check before selecting them.
        </p>)}
      {conflicts.length > 0 && (
        <details className="mt-1.5" style={{ color: 'var(--gold)' }}>
          <summary className="cursor-pointer">{conflicts.length} tag(s) to review in the IODB</summary>
          <ul className="mt-1 ml-4 list-disc max-h-32 overflow-y-auto">
            {conflicts.map((c) => <li key={`${c.tag}-${c.reason}`}><span className="font-mono">{c.tag}</span>: {c.reason}</li>)}
          </ul>
        </details>)}
    </div>
  );
}
