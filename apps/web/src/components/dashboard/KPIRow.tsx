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
    order: ['airlines_analyzed', 'markets_covered', 'jy_avg_fare', 'competitors_avg_fare', 'dep_dates_monitored'],
    columns: 5,
  },
  PW: {
    order: ['competitors_analyzed', 'routes_covered', 'pw_avg_fare', 'competitors_avg_fare', 'dep_dates_monitored'],
    columns: 5,
  },
  FJL: {
    order: ['competitors_tracked', 'routes_covered', 'fjl_avg_fare', 'competitors_avg_fare', 'dep_dates_monitored'],
    columns: 5,
  },
};

// KPIs whose summary value is a fare ⇒ render with a currency prefix in the tile.
const CURRENCY_KEYS = new Set<KpiKey>(['jy_avg_fare', 'pw_avg_fare', 'competitors_avg_fare', 'fjl_avg_fare']);

// FJL fare prefix: localised symbol, not the ISO code. The currency picker
// shows the code (NOK/EUR/DKK), so the tiles can be unambiguous with the
// symbol alone. EUR is set tight against the number (€152.71); the Nordic
// "kr" convention is symbol-then-space-then-number (kr 1,054.41) — so we
// bake the trailing space into the map value.
const CURRENCY_SYMBOL: Record<string, string> = {
  EUR: '€',
  NOK: 'kr ',
  DKK: 'kr ',
};

export interface KPIRowProps {
  airlineCode: string;
  capDate: string;   // YYYY-MM-DD; empty while the date filter is resolving
  currency?: string; // FJL only — passes through to the API and prefixes fare tile values
}

/**
 * Orchestrates the KPI tile row + expandable detail panel.
 *  - Fetches the airline's KPI summary values on mount and whenever capDate changes.
 *  - Toggle logic: click opens; click the active one closes; click another switches.
 *  - When capDate changes with a panel open, the panel refetches itself
 *    (its effect depends on capDate) so the open detail stays in sync.
 */
export default function KPIRow({ airlineCode, capDate, currency }: KPIRowProps) {
  const [activeKPI, setActiveKPI] = useState<KpiKey | null>(null);
  const [summary, setSummary] = useState<KpiSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!capDate) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.kpi.getSummary(airlineCode, capDate, currency)
      .then((res) => { if (!cancelled) setSummary(res); })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load KPIs');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [airlineCode, capDate, currency]);

  const handleClick = (key: KpiKey) => {
    setActiveKPI((prev) => (prev === key ? null : key));
  };

  // Prefix fare tiles with the active currency symbol if the API returned one
  // (FJL → "€152.71" / "kr 1,054.41"), else fall back to "$" for JY/PW.
  const fareUnit = summary?.currency
    ? (CURRENCY_SYMBOL[summary.currency] ?? `${summary.currency} `)
    : '$';
  const formatValue = (key: KpiKey, value: number | null): string => {
    // NULLIF-wrapped fare AVG returns null when the period has no non-zero
    // fares — show an em dash rather than "$0.00" or crashing on toLocaleString.
    if (value === null) return '—';
    if (CURRENCY_KEYS.has(key)) {
      return `${fareUnit}${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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
        currency={currency}
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
