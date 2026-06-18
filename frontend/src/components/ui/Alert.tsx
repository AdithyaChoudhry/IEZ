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

const config: Record<Variant, {
  bg: string; border: string; icon: React.ElementType; iconColor: string; titleColor: string; textColor: string;
}> = {
  success: {
    bg: 'rgba(16,185,129,0.08)', border: 'rgba(16,185,129,0.25)',
    icon: CheckCircle2, iconColor: '#34d399', titleColor: '#34d399', textColor: 'rgba(52,211,153,0.8)',
  },
  error: {
    bg: 'rgba(244,63,94,0.08)', border: 'rgba(244,63,94,0.25)',
    icon: AlertCircle, iconColor: '#fb7185', titleColor: '#fb7185', textColor: 'rgba(251,113,133,0.8)',
  },
  info: {
    bg: 'rgba(14,165,233,0.08)', border: 'rgba(14,165,233,0.25)',
    icon: Info, iconColor: '#38bdf8', titleColor: '#38bdf8', textColor: 'rgba(56,189,248,0.8)',
  },
  warning: {
    bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.25)',
    icon: AlertTriangle, iconColor: '#fbbf24', titleColor: '#fbbf24', textColor: 'rgba(251,191,36,0.8)',
  },
};

export default function Alert({ variant = 'info', title, children, onClose, className }: AlertProps) {
  const { bg, border, icon: Icon, iconColor, titleColor, textColor } = config[variant];

  return (
    <div
      className={clsx('rounded-xl p-4 flex items-start gap-3', className)}
      style={{ background: bg, border: `1px solid ${border}` }}
    >
      <Icon className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: iconColor }} />
      <div className="flex-1 text-sm">
        {title && (
          <p className="font-semibold mb-1 text-xs uppercase tracking-wide" style={{ color: titleColor }}>
            {title}
          </p>
        )}
        <div style={{ color: textColor }}>{children}</div>
      </div>
      {onClose && (
        <button
          onClick={onClose}
          className="flex-shrink-0 transition-opacity hover:opacity-100 opacity-60"
          style={{ color: iconColor }}
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
