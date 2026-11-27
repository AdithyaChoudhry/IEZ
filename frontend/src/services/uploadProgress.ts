/** What the progress bar shows: file uploads in flight and the server work that follows them. */
export interface Progress { id: string; percent: number | null; started: number; touched: number; job: boolean }

let items: Progress[] = [];
const listeners = new Set<(list: Progress[]) => void>();
const emit = () => listeners.forEach((l) => l(items));
let counter = 0;

export const uploadProgress = {
  subscribe(listener: (list: Progress[]) => void): () => void {
    listeners.add(listener);
    listener(items);
    return () => { listeners.delete(listener); };
  },
  /** A request that carries a file. */
  start(): string {
    const id = `upload-${++counter}`;
    items = [...items, { id, percent: 0, started: Date.now(), touched: Date.now(), job: false }];
    emit();
    return id;
  },
  /** Bytes sent so far; at 100 % the server is processing (percent null). */
  sent(id: string, loaded: number, total?: number) {
    const percent = total ? Math.min(100, Math.round((loaded / total) * 100)) : 0;
    items = items.map((p) => (p.id === id ? { ...p, percent: percent >= 100 ? null : percent, touched: Date.now() } : p));
    emit();
  },
  /** A background job the page is still polling. */
  job(id: string) {
    const now = Date.now();
    items = items.some((p) => p.id === id)
      ? items.map((p) => (p.id === id ? { ...p, touched: now } : p))
      : [...items, { id, percent: null, started: now, touched: now, job: true }];
    emit();
  },
  finish(id: string) {
    if (!items.some((p) => p.id === id)) return;
    items = items.filter((p) => p.id !== id);
    emit();
  },
  /** Drops jobs nobody polls any more (the page was left). */
  prune(maxIdleMs = 15000) {
    const now = Date.now();
    const kept = items.filter((p) => !p.job || now - p.touched < maxIdleMs);
    if (kept.length !== items.length) { items = kept; emit(); }
  },
};
