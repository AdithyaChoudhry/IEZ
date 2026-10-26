/** Step 1 - upload IODB + I/O Assignment, show how both were read, let the engineer correct the I/O mapping. */
import { useState } from 'react';
import { CheckCircle2, FileSpreadsheet, Network } from 'lucide-react';
import Alert from '../../ui/Alert';
import Badge from '../../ui/Badge';
import Button from '../../ui/Button';
import Card from '../../ui/Card';
import FileUploadCard from '../../ui/FileUploadCard';
import { IO_FIELD_LABELS, IodbInfo, IoInfo } from './types';

interface Props {
  iodb: IodbInfo | null;
  io: IoInfo | null;
  busy: boolean;
  onUploadIodb: (file: File, revision: string) => void;
  onUploadIo: (file: File, revision: string) => void;
  onConfirmMapping: (mapping: Record<string, string | null>) => void;
}

export default function InputsStep({ iodb, io, busy, onUploadIodb, onUploadIo, onConfirmMapping }: Props) {
  const [iodbFile, setIodbFile] = useState<File | null>(null);
  const [ioFile, setIoFile] = useState<File | null>(null);
  const [iodbRev, setIodbRev] = useState('');
  const [ioRev, setIoRev] = useState('');
  const [edits, setEdits] = useState<Record<string, string>>({});
  const input = 'px-3 py-1.5 rounded-xl text-sm outline-none w-full';
  const inputSt = { background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)' };

  const columnFor = (field: string) => edits[field] ?? io?.mapping[field]?.column ?? '';
  const mappingPayload = () => {
    const payload: Record<string, string | null> = {};
    Object.keys(IO_FIELD_LABELS).forEach((f) => {
      const col = columnFor(f);
      if (col || io?.mapping[f]) payload[f] = col || null;
    });
    return payload;
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FileUploadCard title="1 · IODB" icon={FileSpreadsheet} file={iodbFile} onChange={setIodbFile}
          hint="Tags, loops, JB, cables and instrument data. Columns are matched by name, not position.">
          <input className={`${input} mt-3`} style={inputSt} placeholder="IODB revision (optional, e.g. R3)" value={iodbRev}
            onChange={(e) => setIodbRev(e.target.value)} />
          <Button className="mt-3" fullWidth disabled={!iodbFile} loading={busy && !iodb} onClick={() => iodbFile && onUploadIodb(iodbFile, iodbRev)}>
            {iodb ? 'Upload a different IODB (starts a new session)' : 'Upload IODB'}
          </Button>
          {iodb && (
            <p className="text-xs mt-2 flex items-center gap-1" style={{ color: '#4ade80' }}>
              <CheckCircle2 className="w-3.5 h-3.5" /> {iodb.file_name} · {iodb.rows.toLocaleString()} rows
            </p>
          )}
        </FileUploadCard>

        <FileUploadCard title="2 · I/O Assignment" icon={Network} file={ioFile} onChange={setIoFile}
          hint="PLC/DCS rack, slot, module, channel and terminals. The layout can differ per project.">
          <input className={`${input} mt-3`} style={inputSt} placeholder="I/O Assignment revision (optional)" value={ioRev}
            onChange={(e) => setIoRev(e.target.value)} />
          <Button className="mt-3" fullWidth disabled={!ioFile || !iodb} loading={busy && !!iodb && !io}
            onClick={() => ioFile && onUploadIo(ioFile, ioRev)}>
            {io ? 'Replace I/O Assignment' : 'Upload I/O Assignment'}
          </Button>
          {!iodb && <p className="text-[11px] mt-2" style={{ color: 'var(--t2)' }}>Upload the IODB first.</p>}
          {io && (
            <p className="text-xs mt-2 flex items-center gap-1" style={{ color: '#4ade80' }}>
              <CheckCircle2 className="w-3.5 h-3.5" /> {io.file_name} · {io.tags} tags
            </p>
          )}
        </FileUploadCard>
      </div>

      {iodb && (
        <Card title="How the IODB was read" description="Columns found by name. Fields an IODB revision does not have are simply unavailable - nothing fails.">
          <div className="flex flex-wrap gap-1.5 mb-2">
            {Object.keys(iodb.fields_resolved).map((k) => <Badge key={k} variant="success">{k.replace(/_/g, ' ')}</Badge>)}
          </div>
          {iodb.fields_unavailable.length > 0 && (
            <p className="text-xs" style={{ color: 'var(--t2)' }}>
              Not in this IODB: {iodb.fields_unavailable.map((f) => f.replace(/_/g, ' ')).join(', ')}
            </p>
          )}
        </Card>
      )}

      {io && (
        <Card title="I/O Assignment mapping" description="Detected columns. Correct any wrong mapping, then confirm.">
          {io.sheets.map((s) => (
            <p key={s.sheet} className="text-xs mb-1" style={{ color: 'var(--t2)' }}>
              Sheet <b>{s.sheet}</b>: header row {s.header_row}, {s.rows} rows
            </p>
          ))}
          {io.warnings.map((w) => <Alert key={w} variant="warning" className="mb-2">{w}</Alert>)}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 mt-2">
            {Object.entries(IO_FIELD_LABELS).map(([field, label]) => (
              <div key={field} className="flex items-center gap-2">
                <span className="text-xs w-32 flex-shrink-0" style={{ color: 'var(--t1)' }}>{label}</span>
                <select className={input} style={inputSt} value={columnFor(field)}
                  onChange={(e) => setEdits((p) => ({ ...p, [field]: e.target.value }))}>
                  <option value="">— not mapped —</option>
                  {io.headers.map((h) => (
                    <option key={`${h.sheet}-${h.column}`} value={h.column}>{h.column} · {h.header}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-3 mt-4">
            <Button onClick={() => onConfirmMapping(mappingPayload())} loading={busy} disabled={!columnFor('TAG_NO')}>
              Confirm mapping
            </Button>
            {io.confirmed && <span className="text-xs" style={{ color: '#4ade80' }}>✓ Mapping confirmed</span>}
            {!columnFor('TAG_NO') && <span className="text-xs" style={{ color: 'var(--rose)' }}>The tag column must be mapped.</span>}
          </div>
        </Card>
      )}
    </div>
  );
}
