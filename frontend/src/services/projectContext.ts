/**
 * Current project selection, shared by every generator and the Coversheet.
 * Stored in localStorage (a per-viewer convenience); the document registry on
 * the server is the source of truth for what was generated.
 */
const KEY = 'iez_project_id';
const EVENT = 'iez-project-changed';

export const PROJECT_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$/;

export function getCurrentProject(): string {
  try {
    return localStorage.getItem(KEY) || '';
  } catch {
    return '';
  }
}

export function setCurrentProject(projectId: string): void {
  try {
    if (projectId) localStorage.setItem(KEY, projectId);
    else localStorage.removeItem(KEY);
  } catch { /* storage unavailable - selection just won't persist */ }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: projectId }));
}

export function subscribeProject(cb: (projectId: string) => void): () => void {
  const handler = () => cb(getCurrentProject());
  window.addEventListener(EVENT, handler);
  window.addEventListener('storage', handler);
  return () => {
    window.removeEventListener(EVENT, handler);
    window.removeEventListener('storage', handler);
  };
}
