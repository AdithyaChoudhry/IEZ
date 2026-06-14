/**
 * Dashboard Home Page - Module selector
 */
import { Link } from 'react-router-dom';
import {
  CheckCircle2,
  FileSpreadsheet,
  Cable,
  FileText,
  Network,
  GitBranch,
  Layers,
  ArrowRight,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';

const modules = [
  {
    id: 'validator',
    name: 'IODB Validator',
    icon: CheckCircle2,
    description: 'Validate IODB files against predefined and custom rules',
    path: '/validator',
    color: 'bg-blue-500',
  },
  {
    id: 'instrument',
    name: 'Instrument List',
    icon: FileSpreadsheet,
    description: 'Generate instrument lists from IODB data with column filters',
    path: '/instrument-list',
    color: 'bg-green-500',
  },
  {
    id: 'io',
    name: 'I/O List',
    icon: Network,
    description: 'Create I/O lists with per-column filtering and preview',
    path: '/io-list',
    color: 'bg-purple-500',
  },
  {
    id: 'datasheet',
    name: 'Data Sheet',
    icon: FileText,
    description: 'Generate datasheets per tag with intelligent column matching',
    path: '/datasheet',
    color: 'bg-orange-500',
  },
  {
    id: 'cover',
    name: 'Cover Sheet',
    icon: Layers,
    description: 'Build document cover sheets with custom branding',
    path: '/cover-sheet',
    color: 'bg-teal-500',
  },
  {
    id: 'cable',
    name: 'Cable Schedule',
    icon: Cable,
    description: 'Create cable schedules grouped by junction box',
    path: '/cable-schedule',
    color: 'bg-red-500',
  },
  {
    id: 'loop',
    name: 'Loop Wiring',
    icon: GitBranch,
    description: 'Generate loop wiring diagrams from input files',
    path: '/loop-wiring',
    color: 'bg-indigo-500',
  },
];

export default function DashboardPage() {
  const { user } = useAuth();

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-1">
          Welcome back{user?.username ? `, ${user.username}` : ''}
        </h1>
        <p className="text-gray-500">
          Select a module to start generating engineering documents
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {modules.map((module) => {
          const Icon = module.icon;
          return (
            <Link key={module.id} to={module.path} className="block group">
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200 p-6 h-full flex flex-col">
                <div className={`inline-flex p-3 rounded-lg ${module.color} text-white mb-4 w-fit`}>
                  <Icon className="w-6 h-6" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-1.5 group-hover:text-primary-600 transition-colors">
                  {module.name}
                </h3>
                <p className="text-gray-500 text-sm flex-1">{module.description}</p>
                <div className="flex items-center gap-1.5 text-sm font-medium text-primary-600 mt-4 opacity-0 group-hover:opacity-100 transition-opacity">
                  Open module <ArrowRight className="w-4 h-4" />
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
