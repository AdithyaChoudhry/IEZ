import { CheckCircle2, AlertCircle, Info, AlertTriangle, X } from 'lucide-react';
import clsx from 'clsx';

type Variant = 'success' | 'error' | 'info' | 'warning';

interface AlertProps {
  variant?: Variant;
  title?: string;
  children: React.ReactNode;
  onClose?: () => void;
  className?: string;
}

const cfg: Record<Variant, { bg: string; border: string; icon: React.ElementType; accent: string }> = {
  success: { bg: 'rgba(74,222,128,0.06)',  border: 'rgba(74,222,128,0.2)',  icon: CheckCircle2, accent: '#4ade80' },
  error:   { bg: 'rgba(248,113,113,0.06)', border: 'rgba(248,113,113,0.2)', icon: AlertCircle,  accent: 'var(--rose)' },
  info:    { bg: 'var(--em-dim)',           border: 'rgba(16,185,129,0.2)',  icon: Info,          accent: 'var(--em-lt)' },
  warning: { bg: 'var(--gold-dim)',         border: 'rgba(245,158,11,0.2)',  icon: AlertTriangle, accent: 'var(--gold)' },
};

export default function Alert({ variant = 'info', title, children, onClose, className }: AlertProps) {
  const { bg, border, icon: Icon, accent } = cfg[variant];
  return (
    <div className={clsx('rounded-xl p-4 flex items-start gap-3', className)} style={{ background: bg, border: `1px solid ${border}` }}>
      <Icon className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: accent }} />
      <div className="flex-1 text-sm">
        {title && <p className="font-semibold text-xs uppercase tracking-wide mb-1" style={{ color: accent }}>{title}</p>}
        <div style={{ color: 'var(--t1)' }}>{children}</div>
      </div>
      {onClose && (
        <button onClick={onClose} className="opacity-40 hover:opacity-80 transition-opacity flex-shrink-0" style={{ color: accent }}>
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
