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

export default function Card({ title, description, icon: Icon, iconClassName, actions, className, children, accentColor }: CardProps) {
  return (
    <div
      className={clsx('relative rounded-2xl p-6 overflow-hidden', className)}
      style={{ background: 'var(--s2)', border: '1px solid var(--b1)' }}
    >
      {accentColor && (
        <div className="absolute top-0 left-0 right-0 h-px" style={{ background: `linear-gradient(90deg, ${accentColor}55, transparent)` }} />
      )}
      {(title || actions) && (
        <div className="flex items-start justify-between mb-5 gap-4">
          <div>
            {title && (
              <h3 className="text-sm font-bold flex items-center gap-2.5" style={{ color: 'var(--t0)' }}>
                {Icon && (
                  <span className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: 'var(--s3)', border: '1px solid var(--b1)' }}>
                    <Icon className={clsx('w-3.5 h-3.5', iconClassName || '')} style={!iconClassName ? { color: 'var(--em)' } : {}} />
                  </span>
                )}
                {title}
              </h3>
            )}
            {description && <p className="text-xs mt-1.5 leading-relaxed" style={{ color: 'var(--t1)' }}>{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
