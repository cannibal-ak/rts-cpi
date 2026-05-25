import React, { useEffect, useState } from 'react';
import {
  Box, Collapse, Paper, Typography, IconButton, CircularProgress, Chip,
  Table, TableHead, TableBody, TableRow, TableCell,
} from '@mui/material';
import { Close } from '@mui/icons-material';
import { api } from '../../api';
import type { KpiKey, KpiDetailResponse } from '../../api/client';

type Row = Record<string, string | number>;

interface ColumnDef {
  header: string;
  field: string;
  align?: 'left' | 'right' | 'center';
  render?: (row: Row) => React.ReactNode;
}

const TITLES: Record<KpiKey, string> = {
  // JY
  airlines_analyzed: 'Airlines Analyzed — competitor breakdown',
  markets_covered: 'Markets Covered — route breakdown',
  cheaper_routes_pct: 'Cheaper on Routes — fare comparison',
  undercut_count: 'Undercut Count — where competitors beat JY',
  // PW
  competitors_analyzed: 'Competitors Analyzed — competitor breakdown',
  routes_covered: 'Routes Covered — route breakdown',
  pw_avg_fare: 'PW Avg Fare — fare by route',
  competitors_avg_fare: 'Competitors Avg Fare — fare by competitor',
  dep_dates_monitored: 'Dep Dates Monitored — coverage by date',
};

const fmt = (v: string | number): string =>
  typeof v === 'number' ? v.toLocaleString() : String(v ?? '');

// Δ = JY avg − Comp avg. Negative ⇒ JY cheaper (good ⇒ green); positive ⇒ red.
const deltaCell = (row: Row): React.ReactNode => {
  const d = Number(row.delta);
  const color = d < 0 ? 'success.main' : d > 0 ? 'error.main' : 'text.secondary';
  return (
    <Typography component="span" sx={{ fontSize: 13, fontWeight: 600, color }}>
      {d > 0 ? `+${d.toLocaleString()}` : d.toLocaleString()}
    </Typography>
  );
};

// Gap is always negative for undercuts (comp beat JY) ⇒ red.
const gapCell = (row: Row): React.ReactNode => (
  <Typography component="span" sx={{ fontSize: 13, fontWeight: 600, color: 'error.main' }}>
    {Number(row.gap).toLocaleString()}
  </Typography>
);

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

const winnerBadge = (row: Row): React.ReactNode => {
  const jy = row.winner === 'JY';
  return (
    <Chip
      label={String(row.winner)}
      size="small"
      color={jy ? 'success' : 'error'}
      sx={{ height: 20, fontSize: 11, fontWeight: 700 }}
    />
  );
};

const COLUMN_CONFIG: Record<KpiKey, ColumnDef[]> = {
  airlines_analyzed: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Competitor', field: 'comp_al' },
    { header: 'Routes present', field: 'routes', align: 'right' },
    { header: 'Avg fare', field: 'avg_fare', align: 'right' },
  ],
  markets_covered: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Route', field: 'route' },
    { header: 'Competitors', field: 'competitors', align: 'right' },
    { header: 'JY avg fare', field: 'jy_avg', align: 'right' },
  ],
  cheaper_routes_pct: [
    { header: 'Route', field: 'route' },
    { header: 'JY avg', field: 'jy_avg', align: 'right' },
    { header: 'Comp avg', field: 'comp_avg', align: 'right' },
    { header: 'Δ', field: 'delta', align: 'right', render: deltaCell },
    { header: 'Winner', field: 'winner', align: 'center', render: winnerBadge },
  ],
  undercut_count: [
    { header: 'Route', field: 'route' },
    { header: 'Competitor', field: 'comp_al' },
    { header: 'JY avg', field: 'jy_avg', align: 'right' },
    { header: 'Comp avg', field: 'comp_avg', align: 'right' },
    { header: 'Gap', field: 'gap', align: 'right', render: gapCell },
  ],
  // ── PW ──
  competitors_analyzed: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Competitor', field: 'comp_al' },
    { header: 'Routes', field: 'routes', align: 'right' },
    { header: 'Avg fare', field: 'avg_fare', align: 'right' },
    { header: 'Fare gap', field: 'fare_gap', align: 'right', render: fareGapCell },
  ],
  routes_covered: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Route', field: 'route' },
    { header: 'Competitors', field: 'competitors', align: 'right' },
    { header: 'PW avg', field: 'pw_avg', align: 'right' },
    { header: 'Comp avg', field: 'comp_avg', align: 'right' },
    { header: 'Gap', field: 'fare_gap', align: 'right', render: fareGapCell },
  ],
  pw_avg_fare: [
    { header: '#', field: 'rank', align: 'right' },
    { header: 'Route', field: 'route' },
    { header: 'Avg fare', field: 'avg_fare', align: 'right' },
    { header: 'Min', field: 'min_fare', align: 'right' },
    { header: 'Max', field: 'max_fare', align: 'right' },
    { header: 'Records', field: 'records', align: 'right' },
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
    { header: 'Records', field: 'records', align: 'right' },
    { header: 'Competitors', field: 'competitors', align: 'right' },
    { header: 'Routes', field: 'routes', align: 'right' },
  ],
};

export interface KPIDetailPanelProps {
  kpiKey: KpiKey | null;        // null ⇒ panel collapsed/hidden
  airlineCode: string;
  capDate: string;
  onClose: () => void;
}

/**
 * Expandable detail table for the active KPI. Fetches whenever the active
 * key OR the cap date changes (so the Cap Date picker refreshes an open
 * panel). Animates open/close via MUI Collapse.
 */
export default function KPIDetailPanel({ kpiKey, airlineCode, capDate, onClose }: KPIDetailPanelProps) {
  const [data, setData] = useState<KpiDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!kpiKey || !capDate) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.kpi.getDetail(airlineCode, kpiKey, capDate)
      .then((res) => { if (!cancelled) setData(res); })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load detail');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [kpiKey, airlineCode, capDate]);

  const cols = kpiKey ? COLUMN_CONFIG[kpiKey] : [];
  const rows = data && data.kpi_key === kpiKey ? data.rows : [];

  return (
    <Collapse in={kpiKey !== null} timeout="auto" unmountOnExit>
      <Paper variant="outlined" sx={{ mt: '10px', borderRadius: '8px', overflow: 'hidden' }}>
        <Box sx={{
          display: 'flex', alignItems: 'center', px: 1.5, py: 1,
          borderBottom: '1px solid', borderColor: 'divider', bgcolor: '#f1f6fe',
        }}>
          <Typography sx={{ fontSize: 13, fontWeight: 600, color: '#4a6a8a' }}>
            {kpiKey ? TITLES[kpiKey] : ''}
          </Typography>
          <Box sx={{ flexGrow: 1 }} />
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
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  {cols.map((c) => (
                    <TableCell
                      key={c.header}
                      align={c.align ?? 'left'}
                      sx={{ fontSize: 12, fontWeight: 700, color: '#4a6a8a', bgcolor: '#f8fbff', whiteSpace: 'nowrap' }}
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
                      <TableCell key={c.header} align={c.align ?? 'left'} sx={{ fontSize: 13, whiteSpace: 'nowrap' }}>
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
