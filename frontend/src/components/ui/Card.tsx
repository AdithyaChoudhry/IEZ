/**
 * Card - standard white rounded container with optional header
 */
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
}

export default function Card({ title, description, icon: Icon, iconClassName, actions, className, children }: CardProps) {
  return (
    <div className={clsx('bg-white border border-gray-200 rounded-xl shadow-sm p-6', className)}>
      {(title || actions) && (
        <div className="flex items-start justify-between mb-4 gap-4">
          <div>
            {title && (
              <h3 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
                {Icon && <Icon className={clsx('w-5 h-5', iconClassName || 'text-primary-600')} />}
                {title}
              </h3>
            )}
            {description && <p className="text-sm text-gray-500 mt-1">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
