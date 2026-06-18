import { LucideIcon, Upload, CheckCircle2, FileCheck } from 'lucide-react';

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
    <div
      className="rounded-2xl p-5"
      style={{
        background: 'rgba(10, 24, 50, 0.8)',
        backdropFilter: 'blur(12px)',
        border: '1px solid rgba(14,165,233,0.14)',
      }}
    >
      <h3 className="text-sm font-bold text-sky-100 flex items-center gap-2 mb-4">
        <div
          className="w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{ background: 'rgba(14,165,233,0.12)', border: '1px solid rgba(14,165,233,0.2)' }}
        >
          <Icon className="w-3 h-3 text-sky-400" />
        </div>
        {title}
      </h3>

      <label
        className="flex flex-col items-center justify-center w-full rounded-xl cursor-pointer transition-all duration-200 group"
        style={{
          background: file ? 'rgba(16,185,129,0.06)' : 'rgba(14,165,233,0.04)',
          border: `2px dashed ${file ? 'rgba(16,185,129,0.3)' : 'rgba(14,165,233,0.2)'}`,
          padding: '20px 16px',
        }}
        onMouseEnter={e => {
          if (!file) e.currentTarget.style.borderColor = 'rgba(14,165,233,0.4)';
        }}
        onMouseLeave={e => {
          if (!file) e.currentTarget.style.borderColor = 'rgba(14,165,233,0.2)';
        }}
      >
        {file ? (
          <div className="flex flex-col items-center gap-2 text-center">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(16,185,129,0.15)' }}
            >
              <FileCheck className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <p className="text-xs font-semibold text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                File selected
              </p>
              <p className="text-[11px] mt-0.5 max-w-[200px] truncate" style={{ color: 'rgba(52,211,153,0.7)' }}>
                {file.name}
              </p>
            </div>
            <p className="text-[10px]" style={{ color: 'rgba(125,211,252,0.4)' }}>Click to change</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 text-center">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(14,165,233,0.1)' }}
            >
              <Upload className="w-4 h-4 text-sky-400" />
            </div>
            <div>
              <p className="text-xs font-semibold text-sky-300">
                Click to upload
              </p>
              <p className="text-[11px] mt-0.5" style={{ color: 'rgba(125,211,252,0.45)' }}>
                {accept.split(',').join(', ')}
              </p>
            </div>
          </div>
        )}
        <input
          type="file"
          accept={accept}
          onChange={e => onChange(e.target.files?.[0] || null)}
          className="hidden"
        />
      </label>

      {hint && (
        <p className="text-[11px] mt-3 leading-relaxed" style={{ color: 'rgba(125,211,252,0.4)' }}>
          {hint}
        </p>
      )}
      {children}
    </div>
  );
}
