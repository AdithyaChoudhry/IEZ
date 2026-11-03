/**
 * Shared IODB client - ONE session-scoped IODB reused by every supported generator.
 * The server keeps it per (authenticated user, browser session id); this file only talks to /shared-iodb.
 */
import api from './api';

export interface SharedIodbInfo {
  available: boolean;
  file_name?: string | null;
  uploaded_at?: string | null;
  uploaded_by?: string | null;
  status?: string | null;
  size?: number | null;
}

const SID_KEY = 'iez_session_id';

/** Browser-session id: created lazily after login, removed on logout, so a new login never sees an old IODB. */
export function getSessionId(): string {
  try {
    let sid = sessionStorage.getItem(SID_KEY);
    if (!sid) {
      sid = (crypto.randomUUID?.() ?? `${Date.now()}${Math.random().toString(36).slice(2)}`).replace(/[^A-Za-z0-9_-]/g, '');
      sessionStorage.setItem(SID_KEY, sid);
    }
    return sid;
  } catch {
    return 'default';
  }
}

const headers = () => ({ 'X-IEZ-Session': getSessionId() });

export const sharedIodb = {
  async info(): Promise<SharedIodbInfo> {
    return (await api.get<SharedIodbInfo>('/shared-iodb', { headers: headers() })).data;
  },

  /** Validates on the server; only a valid IODB becomes the Shared IODB. Throws with the server's reason otherwise. */
  async upload(file: File): Promise<SharedIodbInfo> {
    const form = new FormData();
    form.append('file', file);
    return (await api.post<SharedIodbInfo>('/shared-iodb', form, { headers: headers() })).data;
  },

  /** The stored bytes as a File - handed to the generator exactly like a fresh upload. */
  async fetchFile(name: string): Promise<File> {
    const res = await api.get('/shared-iodb/file', { headers: headers(), responseType: 'blob' });
    return new File([res.data], name || 'IODB.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
  },

  async clear(): Promise<void> {
    await api.delete('/shared-iodb', { headers: headers() });
  },
};

/** Called by the existing logout BEFORE the tokens are removed: clears the server copy, then forgets the session id. */
export function endSharedIodbSession(): void {
  try {
    const token = localStorage.getItem('access_token');
    const sid = sessionStorage.getItem(SID_KEY);
    sessionStorage.removeItem(SID_KEY);
    if (token && sid) {
      api.delete('/shared-iodb', { headers: { Authorization: `Bearer ${token}`, 'X-IEZ-Session': sid } }).catch(() => {});
    }
  } catch {
    /* logout must never fail because of this */
  }
}

export function formatUploaded(iso?: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const mon = d.toLocaleString('en-GB', { month: 'short' });
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getDate())}-${mon}-${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
