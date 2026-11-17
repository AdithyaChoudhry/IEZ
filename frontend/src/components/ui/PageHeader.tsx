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
    <div className="mb-8 pt-1">
      <div className="flex items-center gap-4">
        <div className="w-14 h-14 rounded-[18px] flex items-center justify-center flex-shrink-0 glass-panel"
          style={{ borderRadius: 18 }}>
          <Icon className={`w-6 h-6 ${iconClassName || ''}`} style={!iconClassName ? { color: accentColor } : {}} strokeWidth={1.9} />
        </div>
        <div className="min-w-0">
          <h2 className="text-[34px] font-bold leading-[1.05]" style={{ fontFamily: 'var(--font-display)', color: 'var(--t0)', letterSpacing: '-0.045em' }}>
            {title}
          </h2>
          {description && <p className="text-[15px] mt-1.5 max-w-3xl" style={{ color: 'var(--t1)', lineHeight: 1.45 }}>{description}</p>}
        </div>
      </div>
    </div>
  );
}
