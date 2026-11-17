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
        <div className="w-12 h-12 rounded-[14px] flex items-center justify-center flex-shrink-0"
          style={{ background: 'var(--s2)', border: '1px solid var(--b1)', boxShadow: 'var(--shadow-2)' }}>
          <Icon className={`w-[22px] h-[22px] ${iconClassName || ''}`} style={!iconClassName ? { color: accentColor } : {}} />
        </div>
        <div className="min-w-0">
          <h2 className="text-[30px] font-bold leading-[1.1]" style={{ fontFamily: 'var(--font-display)', color: 'var(--t0)', letterSpacing: '-0.032em' }}>
            {title}
          </h2>
          {description && <p className="text-[15px] mt-1.5 max-w-3xl" style={{ color: 'var(--t1)', lineHeight: 1.45 }}>{description}</p>}
        </div>
      </div>
    </div>
  );
}
