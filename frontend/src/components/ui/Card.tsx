import { LucideIcon } from 'lucide-react';
import clsx from 'clsx';

interface CardProps {
  title?: string;
  description?: string;
  icon?: LucideIcon;
  iconClassName?: string;
  actions?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
  accentColor?: string;
}

export default function Card({
  title,
  description,
  icon: Icon,
  iconClassName,
  actions,
  className,
  children,
  accentColor,
}: CardProps) {
  return (
    <div
      className={clsx('relative rounded-2xl p-6 overflow-hidden', className)}
      style={{
        background: 'rgba(10, 24, 50, 0.8)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        border: '1px solid rgba(14,165,233,0.14)',
      }}
    >
      {/* Top accent stripe */}
      {accentColor && (
        <div
          className="absolute top-0 left-0 right-0 h-0.5 rounded-t-2xl"
          style={{ background: `linear-gradient(90deg, ${accentColor}, transparent)` }}
        />
      )}

      {(title || actions) && (
        <div className="flex items-start justify-between mb-5 gap-4">
          <div>
            {title && (
              <h3
                className="text-base font-bold text-sky-100 flex items-center gap-2"
              >
                {Icon && (
                  <div
                    className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: 'rgba(14,165,233,0.12)', border: '1px solid rgba(14,165,233,0.18)' }}
                  >
                    <Icon className={clsx('w-3.5 h-3.5', iconClassName || 'text-sky-400')} />
                  </div>
                )}
                {title}
              </h3>
            )}
            {description && (
              <p className="text-xs mt-1.5" style={{ color: 'rgba(147,197,253,0.55)' }}>{description}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
