import { LucideIcon } from 'lucide-react';

interface PageHeaderProps {
  icon: LucideIcon;
  iconClassName?: string;
  title: string;
  description?: string;
  accentColor?: string;
}

export default function PageHeader({ icon: Icon, iconClassName, title, description, accentColor = 'var(--em)' }: PageHeaderProps) {
  return (
    <div className="mb-7">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'var(--s2)', border: '1px solid var(--b2)' }}>
          <Icon className={`w-[18px] h-[18px] ${iconClassName || ''}`} style={!iconClassName ? { color: accentColor } : {}} />
        </div>
        <div>
          <h2 className="text-xl font-bold leading-tight" style={{ fontFamily: "'Space Grotesk', sans-serif", color: 'var(--t0)' }}>
            {title}
          </h2>
          {description && <p className="text-sm mt-0.5" style={{ color: 'var(--t1)' }}>{description}</p>}
        </div>
      </div>
      <div className="mt-4 h-px" style={{ background: 'var(--b0)' }} />
    </div>
  );
}
