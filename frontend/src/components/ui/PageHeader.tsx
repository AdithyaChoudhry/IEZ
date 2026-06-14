/**
 * PageHeader - icon + title + description block used at the top of every module
 */
import { LucideIcon } from 'lucide-react';

interface PageHeaderProps {
  icon: LucideIcon;
  iconClassName?: string;
  title: string;
  description?: string;
}

export default function PageHeader({ icon: Icon, iconClassName, title, description }: PageHeaderProps) {
  return (
    <div className="mb-6">
      <h2 className="text-2xl font-bold text-primary-800 mb-2 flex items-center gap-2">
        <Icon className={`w-7 h-7 ${iconClassName || 'text-primary-600'}`} />
        {title}
      </h2>
      {description && <p className="text-gray-600">{description}</p>}
    </div>
  );
}
