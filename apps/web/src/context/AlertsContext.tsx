/**
 * Shared alerts state: the unread count, the five most recent, and mark-read.
 *
 * THREE RULES KEEP THE BELL AND THE PAGE FROM FIGHTING:
 *
 *  1. The bell never fetches. NotificationBell and NotificationPopover are pure
 *     consumers of this context, so opening the popover costs no request.
 *  2. The page never reads `recent`. AlertsPage owns its own paginated, filtered
 *     state. The two arrays never try to be the same thing, so there is nothing
 *     to merge and nothing to disagree about.
 *  3. The page reacts to `revision`, it does not run its own timer. This
 *     provider bumps `revision` only when a poll comes back with a different
 *     unread count or newest timestamp, so a quiet minute costs the page
 *     nothing and one new alert refreshes both surfaces off a single request.
 *
 * The app has no react-query, so this is a hand-rolled context + setInterval,
 * following the polling precedent in IngestionRunsPage.
 */
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react';
import type { ReactNode } from 'react';

import { api } from '../api';
import { isAbortError } from '../api/httpClient';
import type { AlertEvent } from '../types';
import { alertsEnabledFor } from '../alerts/alertsAccess';
import { useSession } from './SessionContext';

/** The data is capture-batch driven, not real-time — a faster poll buys
 *  nothing and multiplies load by every open tab. */
const POLL_MS = 60_000;
/** After this many consecutive failures, back off so a down backend does not
 *  produce a request-per-minute-per-tab error storm. */
const FAILURE_LIMIT = 3;
const BACKOFF_MS = 300_000;

interface AlertsContextValue {
  enabled: boolean;
  unreadCount: number;
  capped: boolean;
  recent: AlertEvent[];
  loading: boolean;
  error: string | null;
  /** Bumps only when something actually changed. AlertsPage refetches on it. */
  revision: number;
  refresh: () => Promise<void>;
  markRead: (ids: string[]) => Promise<void>;
  markUnread: (ids: string[]) => Promise<void>;
  markAllRead: () => Promise<void>;
}

const AlertsContext = createContext<AlertsContextValue | null>(null);

export function AlertsProvider({ children }: { children: ReactNode }) {
  const { session } = useSession();
  const enabled = alertsEnabledFor(session);

  const [unreadCount, setUnreadCount] = useState(0);
  const [capped, setCapped] = useState(false);
  const [recent, setRecent] = useState<AlertEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  const inFlight = useRef(false);
  const failures = useRef(0);
  const lastSignature = useRef<string>('');
  const firstLoadDone = useRef(false);

  const poll = useCallback(async (force = false) => {
    if (!enabled) return;
    if (inFlight.current && !force) return;
    inFlight.current = true;
    if (!firstLoadDone.current) setLoading(true);

    const controller = new AbortController();
    try {
      const s = await api.alerts.getSummary({ signal: controller.signal });
      setUnreadCount(s.unread_count);
      setCapped(s.capped);
      setRecent(s.recent);
      setError(null);
      failures.current = 0;

      // Only wake the page when something moved.
      const sig = `${s.unread_count}|${s.newest_triggered_at ?? ''}`;
      if (sig !== lastSignature.current) {
        lastSignature.current = sig;
        if (firstLoadDone.current) setRevision(r => r + 1);
      }
    } catch (err) {
      if (!isAbortError(err)) {
        failures.current += 1;
        if (failures.current >= FAILURE_LIMIT) {
          setError(err instanceof Error ? err.message : 'Could not load alerts');
        }
      }
    } finally {
      inFlight.current = false;
      firstLoadDone.current = true;
      setLoading(false);
    }
  }, [enabled]);

  // Poll, paused while the tab is hidden. A backgrounded tab left open
  // overnight would otherwise make ~500 pointless requests.
  useEffect(() => {
    if (!enabled) return;
    let timer: ReturnType<typeof setInterval> | null = null;

    const start = () => {
      if (timer) return;
      const period = failures.current >= FAILURE_LIMIT ? BACKOFF_MS : POLL_MS;
      timer = setInterval(() => { void poll(); }, period);
    };
    const stop = () => { if (timer) { clearInterval(timer); timer = null; } };

    const onVisibility = () => {
      if (document.hidden) { stop(); return; }
      void poll();          // catch up immediately on return
      start();
    };

    void poll();
    start();
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, [enabled, poll]);

  /** Optimistic, with a snapshot restore if the write fails. */
  const applyOptimistic = useCallback(
    async (ids: string[], read: boolean, call: () => Promise<unknown>) => {
      const snapshot = { unreadCount, recent };
      const affected = recent.filter(e => ids.includes(e.id) && e.is_read !== read);
      setUnreadCount(n => Math.max(0, read ? n - affected.length : n + affected.length));
      setRecent(rs => rs.map(e => (ids.includes(e.id) ? { ...e, is_read: read } : e)));
      try {
        await call();
        await poll(true);          // reconcile against the server
      } catch (err) {
        setUnreadCount(snapshot.unreadCount);
        setRecent(snapshot.recent);
        throw err;
      }
    },
    [unreadCount, recent, poll],
  );

  const markRead = useCallback(
    (ids: string[]) => applyOptimistic(ids, true, () => api.alerts.markRead(ids)),
    [applyOptimistic],
  );

  const markUnread = useCallback(
    (ids: string[]) => applyOptimistic(ids, false, () => api.alerts.markUnread(ids)),
    [applyOptimistic],
  );

  const markAllRead = useCallback(async () => {
    const snapshot = { unreadCount, recent };
    setUnreadCount(0);
    setRecent(rs => rs.map(e => ({ ...e, is_read: true })));
    try {
      await api.alerts.markAllRead();
      await poll(true);
    } catch (err) {
      setUnreadCount(snapshot.unreadCount);
      setRecent(snapshot.recent);
      throw err;
    }
  }, [unreadCount, recent, poll]);

  const value = useMemo<AlertsContextValue>(() => ({
    enabled, unreadCount, capped, recent, loading, error, revision,
    refresh: () => poll(true), markRead, markUnread, markAllRead,
  }), [enabled, unreadCount, capped, recent, loading, error, revision,
       poll, markRead, markUnread, markAllRead]);

  return <AlertsContext.Provider value={value}>{children}</AlertsContext.Provider>;
}

/**
 * Returns an inert value outside a provider rather than throwing, so the bell
 * can be dropped into the AppBar without the AppBar caring whether alerting is
 * mounted for this session.
 */
export function useAlerts(): AlertsContextValue {
  const ctx = useContext(AlertsContext);
  if (ctx) return ctx;
  return {
    enabled: false, unreadCount: 0, capped: false, recent: [],
    loading: false, error: null, revision: 0,
    refresh: async () => {}, markRead: async () => {},
    markUnread: async () => {}, markAllRead: async () => {},
  };
}
