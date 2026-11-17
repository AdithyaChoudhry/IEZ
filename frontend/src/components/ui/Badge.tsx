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

const tone: Record<Variant, string> = {
  success: 'var(--ok)',
  error: 'var(--bad)',
  info: 'var(--info)',
  warning: 'var(--gold)',
  neutral: 'var(--t1)',
};

export default function Badge({ variant = 'neutral', children, className }: BadgeProps) {
  const c = tone[variant];
  return (
    <span className={clsx('inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium', className)}
      style={{ color: c, background: `color-mix(in srgb, ${c} 13%, transparent)` }}>
      {children}
    </span>
  );
}
