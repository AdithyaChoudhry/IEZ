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

const sizeClasses: Record<Size, string> = {
  sm: 'px-3 py-1.5 text-xs gap-1.5',
  md: 'px-4 py-2 text-sm gap-2',
  lg: 'px-6 py-3 text-sm gap-2.5',
};

const variantStyles: Record<Variant, React.CSSProperties> = {
  primary: {
    background: 'linear-gradient(135deg, #0ea5e9, #0369a1)',
    color: 'white',
    border: '1px solid transparent',
    boxShadow: '0 4px 14px rgba(14,165,233,0.22)',
  },
  secondary: {
    background: 'rgba(14,165,233,0.08)',
    color: '#38bdf8',
    border: '1px solid rgba(14,165,233,0.22)',
  },
  danger: {
    background: 'rgba(244,63,94,0.12)',
    color: '#fb7185',
    border: '1px solid rgba(244,63,94,0.25)',
  },
  ghost: {
    background: 'transparent',
    color: 'rgba(147,197,253,0.7)',
    border: '1px solid transparent',
  },
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
      className={clsx(
        'inline-flex items-center justify-center font-semibold rounded-xl transition-all duration-200',
        'disabled:opacity-40 disabled:cursor-not-allowed',
        'hover:brightness-110 active:scale-[0.98]',
        sizeClasses[size],
        fullWidth && 'w-full',
        className
      )}
      style={{ ...variantStyles[variant], ...style }}
      {...rest}
    >
      {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
      {children}
    </button>
  );
}
