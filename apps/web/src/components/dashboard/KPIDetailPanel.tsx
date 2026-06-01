import React, { useEffect, useState } from 'react';
import {
  Box, Collapse, Paper, Typography, IconButton, CircularProgress,
  Table, TableHead, TableBody, TableRow, TableCell,
} from '@mui/material';
import { Close } from '@mui/icons-material';
import { api } from '../../api';
import type { KpiKey, KpiDetailResponse } from '../../api/client';

// Cells may be null when the backing AVG/MIN (wrapped in NULLIF) had no
// non-zero rows for that group; `fmt` renders null as a blank cell.
type Row = Record<string, string | number | null>;

interface ColumnDef {
  header: string;
  field: string;
  align?: 'left' | 'right' | 'center';
  render?: (row: Row) => React.ReactNode;
}

const TITLES: Partial<Record<KpiKey, string>> = {
  // JY
  jy_avg_fare: 'JY Avg Fare — fare by route',
  // PW (competitors_analyzed / routes_covered are shared with JY)
  competitors_analyzed: 'Competitors Analyzed — competitor breakdown',
  routes_covered: 'Routes Covered — route breakdown',
  pw_avg_fare: 'PW Avg Fare — fare by route',
  // Shared across JY/PW
  competitors_avg_fare: 'Competitors Avg Fare — fare by competitor',
  dep_dates_monitored: 'Dep Dates Monitored — coverage by date',
};

// Match KPIRow's summary-tile null guard: render null/undefined as the same
// em dash ('—' U+2014). Legitimately empty strings still render blank
// (String('') === '') — only null/undefined gets the dash.
const fmt = (v: string | number | null): string => {
  if (v === null || v === undefined) return '—';
  return typeof v === 'number' ? v.toLocaleString() : String(v);
};

// jy_avg_fare returns one row per route×competitor; collapse to one row per
// route with the mean JY fare. Routes keep their first-occurrence order from
// the source rows; null/blank/'—' fares are excluded from the mean.
const groupRouteAvgFare = (rows: Row[]): Row[] => {
  const order: string[] = [];
  const buckets = new Map<string, number[]>();
  for (const r of rows) {
    const route = String(r.route ?? '');
    if (!route) continue;
    if (!buckets.has(route)) { buckets.set(route, []); order.push(route); }
    const raw = r.jy_fare;
    if (raw === null || raw === undefined || raw === '' || raw === '—') continue;
    const n = Number(raw);
    if (Number.isFinite(n)) buckets.get(route)!.push(n);
  }
  return order.map((route, i) => {
    const vals = buckets.get(route)!;
    const avg = vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : null;
    return { rank: i + 1, route, avg_fare: avg };
  });
};

// PW fare_gap = Comp avg − PW avg. Positive ⇒ PW cheaper than the competitor
// (good ⇒ green); negative ⇒ competitor undercuts PW (⇒ red).
const fareGapCell = (row: Row): React.ReactNode => {
  const g = Number(row.fare_gap);
  const color = g > 0 ? 'success.main' : g < 0 ? 'error.main' : 'text.secondary';
  return (
    <Typography component="span" sx={{ fontSize: 13, fontWeight: 600, color }}>
      {g > 0 ? `+${g.toLocaleString()}` : g.toLocaleString()}
    </Typography>
  );
};

const COLUMN_CONFIG: Partial<Record<KpiKey, ColumnDef[]>> = {
  jy_avg_fare: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Route', field: 'route', align: 'center' },
    { header: 'JY Avg Fare', field: 'avg_fare', align: 'right' },
  ],
  // ── PW (competitors_analyzed / routes_covered are shared with JY) ──
  competitors_analyzed: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Competitor', field: 'comp_al' },
    { header: 'Routes', field: 'routes', align: 'right' },
  ],
  routes_covered: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Route', field: 'route' },
    { header: 'Competitors', field: 'competitors', align: 'right' },
  ],
  pw_avg_fare: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Route', field: 'route' },
    { header: 'Avg fare', field: 'avg_fare', align: 'right' },
    { header: 'Min', field: 'min_fare', align: 'right' },
    { header: 'Max', field: 'max_fare', align: 'right' },
  ],
  competitors_avg_fare: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Competitor', field: 'comp_al' },
    { header: 'Avg fare', field: 'avg_fare', align: 'right' },
    { header: 'Min', field: 'min_fare', align: 'right' },
    { header: 'Max', field: 'max_fare', align: 'right' },
    { header: 'Routes', field: 'routes', align: 'right' },
  ],
  dep_dates_monitored: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Dep date', field: 'ref_dep_date' },
  ],
};

const FJL_TITLES: Partial<Record<KpiKey, string>> = {
  competitors_tracked: 'Competitors Tracked — competitor breakdown',
  routes_covered: 'Routes Covered — route breakdown',
  fjl_avg_fare: 'FJL Avg Fare — fare breakdown by route',
  competitors_avg_fare: 'Competitors Avg Fare — fare by competitor',
  dep_dates_monitored: 'Departure Dates Monitored — coverage by date',
};

const FJL_COLUMN_CONFIG: Partial<Record<KpiKey, ColumnDef[]>> = {
  competitors_tracked: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Competitor', field: 'source' },
    { header: 'Routes', field: 'routes', align: 'right' },
  ],
  routes_covered: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Route', field: 'route' },
    { header: 'Competitors', field: 'competitors', align: 'right' },
  ],
  fjl_avg_fare: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Route', field: 'route' },
    { header: 'Competitor', field: 'source' },
    { header: 'Total Fare', field: 'total_fare', align: 'right' },
    { header: 'Pax Fare', field: 'pax_fare', align: 'right' },
    { header: 'Vehicle Fare', field: 'veh_fare', align: 'right' },
    { header: 'Cabin Fare', field: 'cab_fare', align: 'right' },
  ],
  competitors_avg_fare: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Competitor', field: 'source' },
    { header: 'Avg Total', field: 'avg_total', align: 'right' },
    { header: 'Avg Pax', field: 'avg_pax', align: 'right' },
    { header: 'Avg Vehicle', field: 'avg_vehicle', align: 'right' },
    { header: 'Avg Cabin', field: 'avg_cabin', align: 'right' },
  ],
  dep_dates_monitored: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Departure Date', field: 'out_dep_date' },
    { header: 'Competitors', field: 'competitors', align: 'right' },
    { header: 'Routes', field: 'routes', align: 'right' },
  ],
};

// JY's competitors_avg_fare detail is per-route (backend _detail_jy_comp_fare_by_route);
// PW's competitors_avg_fare stays per-competitor via COLUMN_CONFIG above.
const JY_COMPETITORS_AVG_FARE_COLS: ColumnDef[] = [
  { header: '#', field: 'rank', align: 'right' },
  { header: 'Route', field: 'route', align: 'center' },
  { header: 'Competitors Avg Fare', field: 'avg_comp_fare', align: 'right' },
];

export interface KPIDetailPanelProps {
  kpiKey: KpiKey | null;        // null ⇒ panel collapsed/hidden
  airlineCode: string;
  capDate: string;
  currency?: string;            // FJL only — passed through to the API + shown in header
  onClose: () => void;
}

/**
 * Expandable detail table for the active KPI. Fetches whenever the active
 * key OR the cap date changes (so the Cap Date picker refreshes an open
 * panel). Animates open/close via MUI Collapse.
 */
export default function KPIDetailPanel({ kpiKey, airlineCode, capDate, currency, onClose }: KPIDetailPanelProps) {
  const [data, setData] = useState<KpiDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!kpiKey || !capDate) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.kpi.getDetail(airlineCode, kpiKey, capDate, currency)
      .then((res) => { if (!cancelled) setData(res); })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load detail');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [kpiKey, airlineCode, capDate, currency]);

  const isFjl = airlineCode.toUpperCase() === 'FJL';
  const titles = isFjl ? FJL_TITLES : TITLES;
  const columnCfg = isFjl ? FJL_COLUMN_CONFIG : COLUMN_CONFIG;
  const isJy = airlineCode.toUpperCase() === 'JY';
  const cols = kpiKey
    ? (isJy && kpiKey === 'competitors_avg_fare'
        ? JY_COMPETITORS_AVG_FARE_COLS
        : (columnCfg[kpiKey] ?? []))
    : [];
  const rawRows = data && data.kpi_key === kpiKey ? data.rows : [];
  const rows = !isFjl && kpiKey === 'jy_avg_fare' ? groupRouteAvgFare(rawRows) : rawRows;

  return (
    <Collapse in={kpiKey !== null} timeout="auto" unmountOnExit>
      <Paper variant="outlined" sx={{ mt: '10px', borderRadius: '8px', overflow: 'hidden' }}>
        <Box sx={{
          display: 'flex', alignItems: 'center', px: 1.5, py: 1,
          borderBottom: '1px solid', borderColor: 'divider', bgcolor: '#f1f6fe',
        }}>
          <Typography sx={{ fontSize: 13, fontWeight: 600, color: '#4a6a8a' }}>
            {kpiKey ? (titles[kpiKey] ?? '') : ''}
          </Typography>
          <Box sx={{ flexGrow: 1 }} />
          {data?.currency && (
            <Typography
              sx={{
                fontSize: 11,
                fontWeight: 600,
                color: '#4a6a8a',
                bgcolor: '#e3edf7',
                px: 0.75,
                py: 0.25,
                borderRadius: '4px',
                mr: 1,
              }}
            >
              {data.currency}
            </Typography>
          )}
          <Typography sx={{ fontSize: 11, color: 'text.secondary', mr: 1 }}>{capDate}</Typography>
          <IconButton size="small" onClick={onClose} aria-label="Close detail panel">
            <Close fontSize="small" />
          </IconButton>
        </Box>

        {loading && (
          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
            <CircularProgress size={24} />
          </Box>
        )}

        {!loading && error && (
          <Box sx={{ p: 2 }}>
            <Typography color="error" sx={{ fontSize: 13 }}>{error}</Typography>
          </Box>
        )}

        {!loading && !error && (
          <Box sx={{ overflow: 'auto', maxHeight: 320 }}>
            {/* tableLayout:fixed + equal per-cell widths distributes columns
                evenly across the panel's full width, and `align="center"`
                here overrides any per-column align in COLUMN_CONFIG so every
                tenant's detail tables render with the same balanced look. */}
            <Table size="small" stickyHeader sx={{ tableLayout: 'fixed' }}>
              <TableHead>
                <TableRow>
                  {cols.map((c) => (
                    <TableCell
                      key={c.header}
                      align="center"
                      sx={{
                        fontSize: 12,
                        fontWeight: 700,
                        color: '#4a6a8a',
                        bgcolor: '#f8fbff',
                        width: `${100 / cols.length}%`,
                      }}
                    >
                      {c.header}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={cols.length} sx={{ fontSize: 13, color: 'text.secondary', textAlign: 'center', py: 3 }}>
                      No data for {capDate}.
                    </TableCell>
                  </TableRow>
                )}
                {rows.map((row, i) => (
                  <TableRow key={i} hover>
                    {cols.map((c) => (
                      <TableCell key={c.header} align="center" sx={{ fontSize: 13 }}>
                        {c.render ? c.render(row) : fmt(row[c.field])}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
      </Paper>
    </Collapse>
  );
}
