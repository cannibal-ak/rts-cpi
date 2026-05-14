/**
 * Fetches the chart manifest for a Superset dashboard (KPIs + analytics charts).
 *
 * Used by the dashboard slice-and-dice feature: the left-side chart selector
 * panel and the isolated single-chart view.  Calls the backend proxy at
 *   GET /api/v1/superset/dashboards/{id}/charts
 * which authenticates to Superset server-side and returns a stable, sorted
 * chart list.
 *
 * Caches in-memory per dashboardId so switching view modes / re-renders don't
 * re-fetch.  Cache survives navigation away and back within the same session.
 */
import { useEffect, useMemo, useState, useCallback } from 'react';
import { api } from '../api';
import type { DashboardChart, DashboardChartsResponse } from '../api/client';

const _cache = new Map<string, DashboardChartsResponse>();

export interface UseDashboardChartsResult {
  charts: DashboardChart[];
  kpiCharts: DashboardChart[];
  analyticsCharts: DashboardChart[];
  dashboardTitle: string | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useDashboardCharts(dashboardId: string | undefined): UseDashboardChartsResult {
  const [data, setData] = useState<DashboardChartsResponse | null>(
    dashboardId ? _cache.get(dashboardId) ?? null : null,
  );
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchManifest = useCallback(async () => {
    if (!dashboardId) return;
    // Serve from cache when available — avoids round-trip on tab toggles.
    const cached = _cache.get(dashboardId);
    if (cached) {
      setData(cached);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const resp = await api.superset.getDashboardCharts(dashboardId);
      _cache.set(dashboardId, resp);
      setData(resp);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load chart list';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [dashboardId]);

  useEffect(() => {
    fetchManifest();
  }, [fetchManifest]);

  const refetch = useCallback(() => {
    if (dashboardId) _cache.delete(dashboardId);
    fetchManifest();
  }, [dashboardId, fetchManifest]);

  return useMemo(() => {
    const charts = data?.charts ?? [];
    return {
      charts,
      kpiCharts: charts.filter(c => c.is_kpi),
      analyticsCharts: charts.filter(c => !c.is_kpi),
      dashboardTitle: data?.dashboard_title ?? null,
      loading,
      error,
      refetch,
    };
  }, [data, loading, error, refetch]);
}
