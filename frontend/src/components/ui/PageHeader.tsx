import { LucideIcon } from 'lucide-react';

interface PageHeaderProps {
  icon: LucideIcon;
  iconClassName?: string;
  title: string;
  description?: string;
  accentColor?: string;
}

export default function PageHeader({
  icon: Icon,
  iconClassName,
  title,
  description,
  accentColor = '#0ea5e9',
}: PageHeaderProps) {
  return (
    <div className="mb-7">
      <div className="flex items-start gap-4">
        <div
          className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 shadow-lg"
          style={{
            background: `linear-gradient(135deg, ${accentColor}30, ${accentColor}15)`,
            border: `1px solid ${accentColor}30`,
            boxShadow: `0 0 20px ${accentColor}15`,
          }}
        >
          <Icon className={`w-5 h-5 ${iconClassName || ''}`} style={!iconClassName ? { color: accentColor } : {}} />
        </div>
        <div>
          <h2
            className="text-2xl font-black text-sky-100 leading-tight"
            style={{ fontFamily: "'Space Grotesk', sans-serif" }}
          >
            {title}
          </h2>
          {description && (
            <p className="text-sm mt-1" style={{ color: 'rgba(147,197,253,0.6)' }}>
              {description}
            </p>
          )}
        </div>
      </div>
      {/* Accent divider */}
      <div
        className="mt-5 h-px"
        style={{
          background: `linear-gradient(90deg, ${accentColor}40, transparent)`,
        }}
      />
    </div>
  );
}
