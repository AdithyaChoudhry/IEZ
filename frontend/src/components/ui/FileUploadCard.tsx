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

export default function FileUploadCard({
  title,
  icon: Icon = Upload,
  file,
  onChange,
  accept = '.xlsx,.xls',
  hint,
  children,
}: FileUploadCardProps) {
  return (
    <div className="rounded-2xl p-5" style={{ background:'var(--s2)', border:'1px solid var(--b1)' }}>
      <h3 className="text-sm font-bold flex items-center gap-2 mb-4" style={{ color:'var(--t0)' }}>
        <span className="w-6 h-6 rounded-lg flex items-center justify-center" style={{ background:'var(--s3)', border:'1px solid var(--b1)' }}>
          <Icon className="w-3 h-3" style={{ color:'var(--teal)' }} />
        </span>
        {title}
      </h3>

      <label
        className="flex flex-col items-center justify-center rounded-xl cursor-pointer transition-all duration-200"
        style={{
          background: file ? 'rgba(74,222,128,0.05)' : 'var(--s1)',
          border: `1.5px dashed ${file ? 'rgba(74,222,128,0.3)' : 'var(--b2)'}`,
          padding: '20px 16px',
        }}
        onMouseEnter={e => {
          if (!file) e.currentTarget.style.borderColor = 'var(--teal)';
        }}
        onMouseLeave={e => {
          if (!file) e.currentTarget.style.borderColor = 'var(--b2)';
        }}
      >
        {file ? (
          <div className="text-center">
            <CheckCircle2 className="w-6 h-6 mx-auto mb-2" style={{ color:'var(--green)' }} />
            <p className="text-xs font-semibold mb-0.5" style={{ color:'var(--green)' }}>File ready</p>
            <p className="text-[11px] max-w-[180px] truncate" style={{ color:'rgba(74,222,128,0.6)' }}>{file.name}</p>
            <p className="text-[10px] mt-1" style={{ color:'var(--t2)' }}>Click to replace</p>
          </div>
        ) : (
          <div className="text-center">
            <Upload className="w-5 h-5 mx-auto mb-2" style={{ color:'var(--t2)' }} />
            <p className="text-xs font-semibold" style={{ color:'var(--t1)' }}>Click to upload</p>
            <p className="text-[11px] mt-0.5" style={{ color:'var(--t2)' }}>{accept.split(',').join(', ')}</p>
          </div>
        )}
        <input type="file" accept={accept} onChange={e => onChange(e.target.files?.[0] || null)} className="hidden" />
      </label>

      {hint && <p className="text-[11px] mt-3 leading-relaxed" style={{ color:'var(--t2)' }}>{hint}</p>}
      {children}
    </div>
  );
}
