/**
 * IO_BASIS review (I/O List Generator).
 * IO_BASIS is generated from the IODB: one representative configuration per motor / valve loop type, per field-instrument type and per other
 * multi-signal equipment. Consistent classes need no action. Where the loops of a class disagree ("Review Required") the engineer confirms the
 * recommended loop or picks another real loop; the equipment wording can be edited. Nothing here changes the IODB, the I/O List or the I/O Summary.
 */
import { useEffect, useState } from 'react';
import api from '@/services/api';
import Card from '../../ui/Card';
import Button from '../../ui/Button';
import Alert from '../../ui/Alert';

export interface BasisClass {
  key: string; category: string; type: string; equipment: string; loops: number; representative: string; status: string;
  candidates: string[]; configs: { count: number; loops: string[]; signals: [string, string][] }[]; notes: string[];
}
interface BasisPreview { classes: BasisClass[]; issues: { severity: string; category: string; message: string }[]; stats: Record<string, number>; error: string; }

const LABEL: Record<string, string> = { motor: 'Motor', valve: 'Valve', instrument: 'Field instrument', other: 'Other equipment' };

interface Props {
  iodbFile: File | null;
  filters: Record<string, string[]>;
  overrides: Record<string, string>;
  names: Record<string, string>;
  onChange: (overrides: Record<string, string>, names: Record<string, string>) => void;
}

export default function IoBasisReview({ iodbFile, filters, overrides, names, onChange }: Props) {
  const [data, setData] = useState<BasisPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    if (!iodbFile) return;
    setLoading(true);
    setError(null);
    const fd = new FormData();
    fd.append('iodb_file', iodbFile);
    fd.append('filters', JSON.stringify(filters));
    fd.append('basis_overrides', JSON.stringify(overrides));
    fd.append('basis_names', JSON.stringify(names));
    try {
      const r = await api.post<BasisPreview>('/io-list/basis', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setData(r.data);
    } catch (e: any) {
      setError(e.response?.data?.detail || 'IO_BASIS could not be analysed');
    } finally {
      setLoading(false);
    }
  };

  // the first look is automatic; later changes of filters / choices are applied with the button
  useEffect(() => { setData(null); if (iodbFile) void load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [iodbFile]);

  const review = (data?.classes || []).filter((c) => c.status !== 'Consistent').length;
  const setLoop = (key: string, loop: string, recommended: string) => {
    const next = { ...overrides };
    if (loop === recommended) delete next[key]; else next[key] = loop;
    onChange(next, names);
  };
  const setName = (key: string, value: string, original: string) => {
    const next = { ...names };
    if (!value.trim() || value === original) delete next[key]; else next[key] = value;
    onChange(overrides, next);
  };

  return (
    <Card
      title="IO_BASIS (generated from the IODB)"
      description="One representative configuration per motor / valve loop type, per field-instrument type and per other equipment. Only classes marked Review Required need a decision; the recommended loop is used otherwise."
    >
      {error && <Alert variant="error">{error}</Alert>}
      {data?.error && <Alert variant="warning" title="IO_BASIS cannot be generated">{data.error}</Alert>}
      {!data && loading && <p className="text-sm text-gray-500">Analysing the IODB…</p>}
      {data && !data.error && (
        <>
          <p className="text-sm mb-3 text-gray-600">
            {data.classes.length} equipment classes · {review === 0 ? 'all consistent' : `${review} to review`}
          </p>
          <div className="border border-gray-200 rounded-lg overflow-auto max-h-96">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  {['Category', 'Type', 'Equipment (editable)', 'Loops', 'Representative loop', 'Status'].map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-medium text-gray-700 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {data.classes.map((c) => {
                  const recommended = c.configs[0]?.loops[0] || c.representative;
                  return (
                    <tr key={c.key} className="align-top">
                      <td className="px-3 py-2 whitespace-nowrap">{LABEL[c.category] || c.category}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{c.type}</td>
                      <td className="px-3 py-2">
                        <input
                          className="w-full min-w-[14rem] border border-gray-300 rounded px-2 py-1 text-sm"
                          defaultValue={names[c.key] ?? c.equipment}
                          onBlur={(e) => setName(c.key, e.target.value, c.equipment)}
                        />
                      </td>
                      <td className="px-3 py-2 text-right">{c.loops}</td>
                      <td className="px-3 py-2">
                        {c.candidates.length > 1 ? (
                          <select
                            className="border border-gray-300 rounded px-2 py-1 text-sm max-w-[11rem]"
                            value={overrides[c.key] ?? recommended}
                            onChange={(e) => setLoop(c.key, e.target.value, recommended)}
                          >
                            {c.candidates.map((l) => <option key={l} value={l}>{l}{l === recommended ? ' (recommended)' : ''}</option>)}
                          </select>
                        ) : (c.representative || '—')}
                      </td>
                      <td className="px-3 py-2">
                        <span className={c.status === 'Consistent' ? 'text-green-700' : 'text-amber-700 font-medium'}>{c.status}</span>
                        {c.notes.map((n, i) => <p key={i} className="text-xs text-gray-500 mt-1 max-w-xs">{n}</p>)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {data.issues.length > 0 && (
            <details className="mt-3 text-sm">
              <summary className="cursor-pointer text-gray-700">{data.issues.length} IODB observation(s) for review</summary>
              <ul className="list-disc ml-5 mt-2 space-y-1 text-gray-600">
                {data.issues.map((i, k) => <li key={k}><span className="font-medium">{i.category}:</span> {i.message}</li>)}
              </ul>
            </details>
          )}
          <Button onClick={load} loading={loading} className="mt-3 bg-blue-600 hover:bg-blue-700">Update IO_BASIS preview</Button>
        </>
      )}
    </Card>
  );
}
