/**
 * ListDefaultsNotice - explains the DEFAULT column / filter selection of the Instrument List
 * and I/O List generators. Defaults are only an initial state: nothing here is locked.
 */
import { RotateCcw, FilterX } from 'lucide-react';
import Alert from './Alert';
import Badge from './Badge';
import Button from './Button';

export const BLANK_TOKEN = '(blank)';

export interface ListDefaults {
  list_type: string;
  columns: string[];
  missing_columns: string[];
  filters: Record<string, string[]>;
  filter_summary: { column: string; mode: string; selected: string[]; deselected: string[] }[];
  warnings: string[];
}

/** Value used to compare a preview cell with filter options (empty cells match "(blank)"). */
export const filterValueOf = (v: unknown): string =>
  v === null || v === undefined || String(v).trim() === '' ? BLANK_TOKEN : String(v);

const sameFilters = (a: Record<string, string[]>, b: Record<string, string[]>) => {
  const ka = Object.keys(a).sort(); const kb = Object.keys(b).sort();
  if (ka.join('\u0000') !== kb.join('\u0000')) return false;
  return ka.every((k) => [...a[k]].sort().join('\u0000') === [...b[k]].sort().join('\u0000'));
};

interface Props {
  defaults: ListDefaults | null | undefined;
  selectedColumns: string[];
  filters: Record<string, string[]>;
  onReset: () => void;
  onClearFilters: () => void;
}

export default function ListDefaultsNotice({ defaults, selectedColumns, filters, onReset, onClearFilters }: Props) {
  if (!defaults) return null;
  const columnsAreDefault = selectedColumns.join('\u0000') === defaults.columns.join('\u0000');
  const filtersAreDefault = sameFilters(filters, defaults.filters);
  const shownWarnings = defaults.warnings.slice(0, 6);

  return (
    <div className="space-y-3">
      {defaults.warnings.length > 0 && (
        <Alert variant="warning" title="Some defaults could not be applied">
          <ul className="text-xs space-y-0.5">
            {shownWarnings.map((w) => <li key={w}>{w}</li>)}
            {defaults.warnings.length > shownWarnings.length && (
              <li>…and {defaults.warnings.length - shownWarnings.length} more</li>
            )}
          </ul>
        </Alert>
      )}
      <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600">
        <Badge variant={columnsAreDefault ? 'info' : 'neutral'}>
          {columnsAreDefault ? 'Default columns' : 'Columns customised'}
        </Badge>
        <Badge variant={filtersAreDefault ? 'info' : 'neutral'}>
          {Object.keys(filters).length === 0 ? 'No filters' : filtersAreDefault ? 'Default filters' : 'Filters customised'}
        </Badge>
        <span>
          Default columns selected. You may add or remove columns. Default filters applied. You may modify
          the selections before generating.
        </span>
      </div>
      {defaults.filter_summary.length > 0 && filtersAreDefault && (
        <ul className="text-xs text-gray-600 space-y-0.5">
          {defaults.filter_summary.map((s) => (
            <li key={s.column}>
              <span className="font-medium text-gray-700">{s.column}:</span>{' '}
              {s.deselected.length > 0 ? <>deselected <span className="font-mono">{s.deselected.join(', ')}</span></> : 'all values selected'}
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={onReset} disabled={columnsAreDefault && filtersAreDefault}>
          <RotateCcw className="w-3.5 h-3.5" /> Reset to defaults
        </Button>
        <Button size="sm" variant="ghost" onClick={onClearFilters} disabled={Object.keys(filters).length === 0}>
          <FilterX className="w-3.5 h-3.5" /> Clear all filters
        </Button>
      </div>
    </div>
  );
}
