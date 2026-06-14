/**
 * MultiSelect - searchable checkbox list with select all / clear
 */
import { useState, useMemo } from 'react';
import { Search } from 'lucide-react';
import Button from './Button';

interface MultiSelectProps {
  options: string[];
  selected: string[];
  onChange: (selected: string[]) => void;
  searchable?: boolean;
  maxHeight?: string;
  columns?: 1 | 2 | 3 | 4;
}

export default function MultiSelect({
  options,
  selected,
  onChange,
  searchable = true,
  maxHeight = 'max-h-64',
  columns = 3,
}: MultiSelectProps) {
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return options;
    const q = search.toLowerCase();
    return options.filter((o) => o.toLowerCase().includes(q));
  }, [options, search]);

  const toggle = (opt: string) => {
    if (selected.includes(opt)) {
      onChange(selected.filter((o) => o !== opt));
    } else {
      onChange([...selected, opt]);
    }
  };

  const gridColsClass = {
    1: 'grid-cols-1',
    2: 'grid-cols-1 md:grid-cols-2',
    3: 'grid-cols-2 md:grid-cols-3',
    4: 'grid-cols-2 md:grid-cols-4',
  }[columns];

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-3">
        {searchable && (
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
        )}
        <div className="flex gap-2 flex-shrink-0">
          <Button variant="ghost" size="sm" onClick={() => onChange(options)}>
            Select All
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onChange([])}>
            Clear
          </Button>
        </div>
      </div>

      <div className={`${maxHeight} overflow-y-auto border border-gray-200 rounded-lg p-3`}>
        {filtered.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">No options found</p>
        ) : (
          <div className={`grid ${gridColsClass} gap-1.5`}>
            {filtered.map((opt) => (
              <label key={opt} className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 px-2 py-1.5 rounded text-sm">
                <input
                  type="checkbox"
                  checked={selected.includes(opt)}
                  onChange={() => toggle(opt)}
                  className="w-4 h-4 text-primary-600 border-gray-300 rounded flex-shrink-0"
                />
                <span className="text-gray-700 truncate">{opt}</span>
              </label>
            ))}
          </div>
        )}
      </div>

      <p className="text-sm text-gray-500 mt-2">
        <strong>{selected.length}</strong> of {options.length} selected
      </p>
    </div>
  );
}
