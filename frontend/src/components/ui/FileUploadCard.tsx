/**
 * FileUploadCard - icon + label + file input + selected-file confirmation
 */
import { LucideIcon, Upload, CheckCircle2 } from 'lucide-react';

interface FileUploadCardProps {
  title: string;
  icon?: LucideIcon;
  file: File | null;
  onChange: (file: File | null) => void;
  accept?: string;
  hint?: string;
  children?: React.ReactNode;
}

export default function FileUploadCard({
  title,
  icon: Icon = Upload,
  file,
  onChange,
  accept = '.xlsx,.xls',
  hint,
  children,
}: FileUploadCardProps) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6">
      <h3 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
        <Icon className="w-5 h-5 text-primary-600" />
        {title}
      </h3>
      <input
        type="file"
        accept={accept}
        onChange={(e) => onChange(e.target.files?.[0] || null)}
        className="block w-full text-sm text-gray-900 border border-gray-300 rounded-lg cursor-pointer bg-gray-50 file:mr-4 file:py-2 file:px-4 file:border-0 file:bg-primary-50 file:text-primary-700 file:font-medium"
      />
      {file && (
        <p className="text-sm text-green-600 mt-3 flex items-center gap-1.5">
          <CheckCircle2 className="w-4 h-4" />
          Selected: <strong>{file.name}</strong>
        </p>
      )}
      {hint && <p className="text-xs text-gray-500 mt-3">{hint}</p>}
      {children}
    </div>
  );
}
