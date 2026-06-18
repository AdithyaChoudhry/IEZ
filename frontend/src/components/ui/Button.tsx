import { Loader2 } from 'lucide-react';
import clsx from 'clsx';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  fullWidth?: boolean;
}

const sizes: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs gap-1.5',
  md: 'px-4 py-2 text-sm gap-2',
  lg: 'px-5 py-2.5 text-sm gap-2',
};

const variants: Record<Variant, string> = {
  primary:   'btn btn-primary',
  secondary: 'btn btn-secondary',
  danger:    'btn',
  ghost:     'btn',
};

const variantExtra: Record<Variant, React.CSSProperties> = {
  primary:   {},
  secondary: {},
  danger:    { background:'rgba(248,113,113,0.1)', color:'var(--rose)', border:'1px solid rgba(248,113,113,0.2)' },
  ghost:     { background:'transparent', color:'var(--t1)', border:'1px solid transparent' },
};

export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  fullWidth = false,
  disabled,
  className,
  children,
  style,
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={clsx(variants[variant], sizes[size], fullWidth && 'w-full', className)}
      style={{ ...variantExtra[variant], ...style }}
      {...rest}
    >
      {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
      {children}
    </button>
  );
}
