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
      className={clsx('ui-card relative p-6 overflow-hidden', className)}
      style={{ background: 'var(--s2)', border: '1px solid var(--b1)', borderRadius: 22, boxShadow: 'var(--shadow-1)' }}
    >
      {accentColor && (
        <div className="absolute top-0 left-0 right-0 h-px" style={{ background: `linear-gradient(90deg, ${accentColor}66, transparent)` }} />
      )}
      {(title || actions) && (
        <div className="flex items-start justify-between mb-5 gap-4">
          <div>
            {title && (
              <h3 className="text-[16px] font-semibold flex items-center gap-3" style={{ color: 'var(--t0)', letterSpacing: '-0.015em', fontFamily: 'var(--font-display)' }}>
                {Icon && (
                  <span className="w-8 h-8 rounded-[8px] flex items-center justify-center flex-shrink-0" style={{ background: 'var(--s3)' }}>
                    <Icon className={clsx('w-4 h-4', iconClassName || '')} style={!iconClassName ? { color: 'var(--t0)' } : {}} strokeWidth={1.8} />
                  </span>
                )}
                {title}
              </h3>
            )}
            {description && <p className="text-[13px] mt-1.5 leading-relaxed" style={{ color: 'var(--t1)' }}>{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
