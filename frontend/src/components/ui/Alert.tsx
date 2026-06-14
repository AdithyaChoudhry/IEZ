/**
 * Alert - inline success/error/info/warning banner
 */
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

const config: Record<Variant, { container: string; icon: React.ElementType; iconClass: string; title: string }> = {
  success: { container: 'bg-green-50 border-green-200', icon: CheckCircle2, iconClass: 'text-green-500', title: 'text-green-800' },
  error: { container: 'bg-red-50 border-red-200', icon: AlertCircle, iconClass: 'text-red-500', title: 'text-red-800' },
  info: { container: 'bg-blue-50 border-blue-200', icon: Info, iconClass: 'text-blue-500', title: 'text-blue-800' },
  warning: { container: 'bg-orange-50 border-orange-200', icon: AlertTriangle, iconClass: 'text-orange-500', title: 'text-orange-800' },
};

export default function Alert({ variant = 'info', title, children, onClose, className }: AlertProps) {
  const { container, icon: Icon, iconClass, title: titleClass } = config[variant];

  return (
    <div className={clsx('border rounded-lg p-4 flex items-start gap-3', container, className)}>
      <Icon className={clsx('w-5 h-5 flex-shrink-0 mt-0.5', iconClass)} />
      <div className="flex-1 text-sm">
        {title && <p className={clsx('font-semibold mb-1', titleClass)}>{title}</p>}
        <div className="text-gray-700">{children}</div>
      </div>
      {onClose && (
        <button onClick={onClose} className="text-gray-400 hover:text-gray-600 flex-shrink-0">
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
