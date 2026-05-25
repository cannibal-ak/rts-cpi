import React, { useEffect, useState } from 'react';
import { Box, Typography, Skeleton } from '@mui/material';
import { api } from '../../api';
import type { KpiKey, KpiSummaryResponse } from '../../api/client';
import KPICard from './KPICard';
import KPIDetailPanel from './KPIDetailPanel';

// Per-airline KPI ordering + grid column count. The backend returns only
// the keys listed here for the matching airline_code.
const KPI_LAYOUT: Record<string, { order: KpiKey[]; columns: number }> = {
  JY: {
    order: ['airlines_analyzed', 'markets_covered', 'cheaper_routes_pct', 'undercut_count'],
    columns: 4,
  },
  PW: {
    order: ['competitors_analyzed', 'routes_covered', 'pw_avg_fare', 'competitors_avg_fare', 'dep_dates_monitored'],
    columns: 5,
  },
};

// KPIs whose summary value is a fare ⇒ render as $x.xx in the tile.
const CURRENCY_KEYS = new Set<KpiKey>(['pw_avg_fare', 'competitors_avg_fare']);
// KPIs rendered as a percentage.
const PERCENT_KEYS = new Set<KpiKey>(['cheaper_routes_pct']);

export interface KPIRowProps {
  airlineCode: string;
  capDate: string;   // YYYY-MM-DD; empty while the date filter is resolving
}

/**
 * Orchestrates the KPI tile row + expandable detail panel.
 *  - Fetches the 4 summary values on mount and whenever capDate changes.
 *  - Toggle logic: click opens; click the active one closes; click another switches.
 *  - When capDate changes with a panel open, the panel refetches itself
 *    (its effect depends on capDate) so the open detail stays in sync.
 */
export default function KPIRow({ airlineCode, capDate }: KPIRowProps) {
  const [activeKPI, setActiveKPI] = useState<KpiKey | null>(null);
  const [summary, setSummary] = useState<KpiSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!capDate) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.kpi.getSummary(airlineCode, capDate)
      .then((res) => { if (!cancelled) setSummary(res); })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load KPIs');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [airlineCode, capDate]);

  const handleClick = (key: KpiKey) => {
    setActiveKPI((prev) => (prev === key ? null : key));
  };

  const formatValue = (key: KpiKey, value: number): string => {
    if (PERCENT_KEYS.has(key)) return `${value}%`;
    if (CURRENCY_KEYS.has(key)) {
      return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
    return value.toLocaleString();
  };

  if (!capDate) return null;

  const layout = KPI_LAYOUT[airlineCode.toUpperCase()] ?? KPI_LAYOUT.JY;

  return (
    <Box sx={{ px: '12px', py: '8px' }}>
      <Box sx={{
        display: 'grid',
        gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: `repeat(${layout.columns}, 1fr)` },
        gap: '12px',
      }}>
        {layout.order.map((key) => {
          const item = summary?.kpis[key];
          if (loading || !item) {
            return <Skeleton key={key} variant="rounded" height={92} sx={{ borderRadius: '8px' }} />;
          }
          return (
            <KPICard
              key={key}
              label={item.label}
              value={formatValue(key, item.value)}
              subheader={item.subheader}
              isActive={activeKPI === key}
              onClick={() => handleClick(key)}
            />
          );
        })}
      </Box>

      {error && (
        <Typography color="error" sx={{ fontSize: 12, mt: 1 }}>{error}</Typography>
      )}

      <KPIDetailPanel
        kpiKey={activeKPI}
        airlineCode={airlineCode}
        capDate={capDate}
        onClose={() => setActiveKPI(null)}
      />

      {!activeKPI && !error && (
        <Typography sx={{ fontSize: 11, color: 'text.secondary', mt: 1, textAlign: 'center' }}>
          Click any KPI to see its detail breakdown
        </Typography>
      )}
    </Box>
  );
}
