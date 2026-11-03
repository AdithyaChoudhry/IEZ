/**
 * Single source of truth for the current Shared IODB reference (never a copy of the file).
 * Every selector, indicator and generator reads this one state; nothing keeps its own IODB store.
 */
import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from 'react';
import { useAuth } from './AuthContext';
import { sharedIodb, SharedIodbInfo } from '@/services/sharedIodb';

interface Ctx {
  info: SharedIodbInfo | null;
  loading: boolean;
  refresh: () => Promise<SharedIodbInfo | null>;
  /** Make `next` the current Shared IODB everywhere (after a successful, validated upload). */
  publish: (next: SharedIodbInfo) => void;
}

const SharedIodbContext = createContext<Ctx>({ info: null, loading: false, refresh: async () => null, publish: () => {} });

export function SharedIodbProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [info, setInfo] = useState<SharedIodbInfo | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) { setInfo(null); return null; }
    setLoading(true);
    try {
      const i = await sharedIodb.info();
      setInfo(i);
      return i;
    } catch {
      setInfo({ available: false });
      return null;
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  // Logged out -> nothing remains in memory; logged in -> ask the server what this session has.
  useEffect(() => { if (isAuthenticated) { refresh(); } else { setInfo(null); } }, [isAuthenticated, refresh]);

  return (
    <SharedIodbContext.Provider value={{ info, loading, refresh, publish: setInfo }}>
      {children}
    </SharedIodbContext.Provider>
  );
}

export const useSharedIodb = () => useContext(SharedIodbContext);
