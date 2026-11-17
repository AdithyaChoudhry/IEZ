import { LucideIcon } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { currentPage } from '../layout/nav';

interface PageHeaderProps {
  icon: LucideIcon;
  iconClassName?: string;      // kept for API compatibility; the design uses neutral icons
  title: string;
  description?: string;
  accentColor?: string;
}

export default function PageHeader({ icon: Icon, title, description }: PageHeaderProps) {
  const { pathname } = useLocation();
  const page = currentPage(pathname);
  return (
    <div className="mb-7 sm:mb-9">
      {page && <p className="eyebrow mb-4"><span className="signal">●</span>&nbsp; {page.section.code} · {page.section.label}</p>}
      <div className="flex items-start gap-4">
        <div className="hidden sm:flex w-11 h-11 rounded-[11px] items-center justify-center flex-shrink-0 mt-1"
          style={{ background: 'var(--s2)', border: '1px solid var(--b2)', boxShadow: 'var(--shadow-1)' }}>
          <Icon className="w-5 h-5" style={{ color: 'var(--t0)' }} strokeWidth={1.8} />
        </div>
        <div className="min-w-0">
          <h2 className="text-[28px] sm:text-[34px] font-semibold leading-[1.08]" style={{ fontFamily: 'var(--font-display)', color: 'var(--t0)', letterSpacing: '-0.035em' }}>
            {title}
          </h2>
          {description && <p className="text-[15px] mt-2 max-w-3xl" style={{ color: 'var(--t1)', lineHeight: 1.5 }}>{description}</p>}
        </div>
      </div>
    </div>
  );
}
