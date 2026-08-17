/**
 * Fetches the top-level tab strip of a Superset dashboard.
 *
 * Drives the sidebar's per-tab navigation for tabbed dashboards (WinAir), the
 * counterpart to useDashboardCharts for the untabbed ones. Calls the backend
 * proxy at
 *   GET /api/v1/superset/dashboards/{id}/tabs
 * which reads the dashboard's own position_json server-side, so the list stays
 * 1:1 with the dashboard when a tab is renamed or reordered.
 *
 * Caches in-memory per dashboardId, so the sidebar costs one request per
 * session even though it is mounted on every page.
 */
import { useEffect, useMemo, useState, useCallback } from 'react';
import { api } from '../api';
import type { DashboardTab, DashboardTabsResponse } from '../api/client';

const _cache = new Map<string, DashboardTabsResponse>();

export interface UseDashboardTabsResult {
  tabs: DashboardTab[];
  /**
   * Whether `tabs` is genuinely the dashboard's navigation rather than one
   * section's sub-tabs the extractor could not tell apart. Only a caller that
   * REPLACES Superset's own tab row needs to care; offering the tabs as extra
   * links is safe either way. See tabs_are_navigation on the API.
   */
  tabsAreNavigation: boolean;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useDashboardTabs(dashboardId: string | undefined): UseDashboardTabsResult {
  const [data, setData] = useState<DashboardTabsResponse | null>(
    dashboardId ? _cache.get(dashboardId) ?? null : null,
  );
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTabs = useCallback(async () => {
    if (!dashboardId) return;
    const cached = _cache.get(dashboardId);
    if (cached) {
      setData(cached);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const resp = await api.superset.getDashboardTabs(dashboardId);
      _cache.set(dashboardId, resp);
      setData(resp);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load tab list';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [dashboardId]);

  useEffect(() => {
    fetchTabs();
  }, [fetchTabs]);

  const refetch = useCallback(() => {
    if (dashboardId) _cache.delete(dashboardId);
    fetchTabs();
  }, [dashboardId, fetchTabs]);

  return useMemo(() => ({
    tabs: data?.tabs ?? [],
    // Default false: an older API that omits the field must not be read as a
    // promise that these tabs are the navigation.
    tabsAreNavigation: data?.tabs_are_navigation === true,
    loading,
    error,
    refetch,
  }), [data, loading, error, refetch]);
}
