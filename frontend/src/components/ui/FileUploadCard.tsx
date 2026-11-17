import { LucideIcon, Upload, CheckCircle2 } from 'lucide-react';

interface FileUploadCardProps {
  title: string;
  icon?: LucideIcon;
  file: File | null;
  onChange: (file: File | null) => void;
  accept?: string;
  hint?: string;
  children?: React.ReactNode;
}

export default function FileUploadCard({ title, icon: Icon = Upload, file, onChange, accept = '.xlsx,.xls', hint, children }: FileUploadCardProps) {
  return (
    <div className="ui-card p-5" style={{ background: 'var(--s2)', border: '1px solid var(--b1)', borderRadius: 18, boxShadow: 'var(--shadow-1)' }}>
      <h3 className="text-[15px] font-semibold flex items-center gap-2.5 mb-4" style={{ color: 'var(--t0)', letterSpacing: '-0.02em' }}>
        <span className="w-7 h-7 rounded-[7px] flex items-center justify-center" style={{ background: 'var(--s3)' }}>
          <Icon className="w-3.5 h-3.5" style={{ color: 'var(--t0)' }} strokeWidth={1.8} />
        </span>
        {title}
      </h3>
      <label
        className="flex flex-col items-center justify-center cursor-pointer"
        style={{
          background: file ? 'color-mix(in srgb, var(--ok) 8%, transparent)' : 'var(--s1)',
          border: `1.5px dashed ${file ? 'color-mix(in srgb, var(--ok) 45%, transparent)' : 'var(--b2)'}`,
          borderRadius: 12,
          padding: '26px 16px',
          transition: 'transform .4s var(--spring), border-color .25s var(--ease), background .25s var(--ease)',
        }}
        onMouseEnter={e => { if (!file) { e.currentTarget.style.borderColor = 'var(--b3)'; e.currentTarget.style.background = 'var(--s3)'; } }}
        onMouseLeave={e => { if (!file) { e.currentTarget.style.borderColor = 'var(--b2)'; e.currentTarget.style.background = 'var(--s1)'; } }}
      >
        {file ? (
          <div className="text-center">
            <CheckCircle2 className="w-7 h-7 mx-auto mb-2" style={{ color: 'var(--ok)' }} />
            <p className="text-[13px] font-semibold mb-0.5" style={{ color: 'var(--ok)' }}>File ready</p>
            <p className="text-xs max-w-[220px] truncate" style={{ color: 'var(--t1)' }}>{file.name}</p>
            <p className="text-[11px] mt-1" style={{ color: 'var(--t2)' }}>Click to replace</p>
          </div>
        ) : (
          <div className="text-center">
            <Upload className="w-6 h-6 mx-auto mb-2" style={{ color: 'var(--t2)' }} />
            <p className="text-[13px] font-semibold" style={{ color: 'var(--t0)' }}>Click to upload</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--t2)' }}>{accept.split(',').join(', ')}</p>
          </div>
        )}
        <input type="file" accept={accept} onChange={e => onChange(e.target.files?.[0] || null)} className="hidden" />
      </label>
      {hint && <p className="text-xs mt-3 leading-relaxed" style={{ color: 'var(--t2)' }}>{hint}</p>}
      {children}
    </div>
  );
}
