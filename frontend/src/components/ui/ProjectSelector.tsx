/**
 * ProjectSelector - picks the project that generated documents are registered under.
 * Shared by the four generators and the Coversheet via services/projectContext.
 */
import { useEffect, useState } from 'react';
import { FolderKanban } from 'lucide-react';
import api from '@/services/api';
import {
  PROJECT_ID_PATTERN, getCurrentProject, setCurrentProject, subscribeProject,
} from '@/services/projectContext';

interface ProjectRow { project_id: string; name: string }

export default function ProjectSelector({ compact = false }: { compact?: boolean }) {
  const [value, setValue] = useState(getCurrentProject());
  const [draft, setDraft] = useState(getCurrentProject());
  const [projects, setProjects] = useState<ProjectRow[]>([]);
  const [error, setError] = useState('');

  useEffect(() => subscribeProject((id) => { setValue(id); setDraft(id); }), []);

  useEffect(() => {
    api.get<ProjectRow[]>('/projects').then((r) => setProjects(r.data)).catch(() => { /* optional */ });
  }, [value]);

  const commit = async () => {
    const id = draft.trim();
    if (id === value) return;
    if (!id) { setCurrentProject(''); setError(''); return; }
    if (!PROJECT_ID_PATTERN.test(id)) {
      setError('Use letters, digits, ".", "_" or "-" (max 40), e.g. 10P211');
      return;
    }
    try {
      await api.post('/projects', { project_id: id });
      setError('');
      setCurrentProject(id);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Could not select project');
    }
  };

  return (
    <div className={compact ? '' : 'mb-4'}>
      <div className="flex items-center gap-2 flex-wrap">
        <FolderKanban className="w-4 h-4" style={{ color: 'var(--em)' }} />
        <label className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: 'var(--t2)' }}>
          Project
        </label>
        <input
          list="iez-projects"
          value={draft}
          placeholder="e.g. 10P211"
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
          className="px-3 py-1.5 rounded-xl text-sm outline-none w-40"
          style={{ background: 'var(--s0)', border: '1px solid var(--b2)', color: 'var(--t0)' }}
        />
        <datalist id="iez-projects">
          {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.name}</option>)}
        </datalist>
        <span className="text-xs" style={{ color: 'var(--t2)' }}>
          {value
            ? `Generated documents are registered under ${value}`
            : 'Select a project to register generated documents for the Coversheet'}
        </span>
      </div>
      {error && <p className="text-xs mt-1" style={{ color: 'var(--rose)' }}>{error}</p>}
    </div>
  );
}
