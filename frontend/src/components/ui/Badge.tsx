/**
 * Badge - small status pill
 */
import clsx from 'clsx';

type Variant = 'success' | 'error' | 'info' | 'warning' | 'neutral';

interface BadgeProps {
  variant?: Variant;
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<Variant, string> = {
  success: 'bg-green-100 text-green-800',
  error: 'bg-red-100 text-red-800',
  info: 'bg-blue-100 text-blue-800',
  warning: 'bg-orange-100 text-orange-800',
  neutral: 'bg-gray-100 text-gray-700',
};

export default function Badge({ variant = 'neutral', children, className }: BadgeProps) {
  return (
    <span className={clsx('inline-flex items-center px-2 py-1 rounded text-xs font-medium', variantClasses[variant], className)}>
      {children}
    </span>
  );
}
