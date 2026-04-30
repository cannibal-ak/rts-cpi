import { useState, useEffect, useCallback } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Chip, CircularProgress, TablePagination,
} from '@mui/material';
import { Flight, ArrowForward } from '@mui/icons-material';
import FilterPanel from '../../components/filters/FilterPanel';
import ActionBar from '../../components/filters/ActionBar';
import KpiTiles from '../../components/common/KpiTiles';
import type { KpiTile } from '../../components/common/KpiTiles';
import EmptyState from '../../components/common/EmptyState';
import { api } from '../../api';
import type { JyVelocitySnapshot, FilterMetadata, Paginated } from '../../types';

interface AirlineCpiVelocityTabProps {
  filters: Record<string, string>;
  onFiltersChange: (f: Record<string, string>) => void;
}

// Threshold colors for booking %, actual SF %, forecasted SF %.
// Uses theme palette tokens (not hex) so dark mode renders correctly.
function pctColor(pct: number | null | undefined): string {
  if (pct === null || pct === undefined) return 'text.primary';
  if (pct >= 70) return 'success.main';
  if (pct >= 40) return 'warning.main';
  return 'error.main';
}

export default function AirlineCpiVelocityTab({ filters, onFiltersChange }: AirlineCpiVelocityTabProps) {
  const [filterOpen, setFilterOpen] = useState(true);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Paginated<JyVelocitySnapshot> | null>(null);
  const [meta, setMeta] = useState<FilterMetadata[]>([]);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(20);

  // Velocity is JY-only. tenant param is fixed.
  const TENANT = 'JY' as const;

  useEffect(() => {
    api.airline.velocity.getFilterMetadata(TENANT).then(setMeta);
  }, []);

  const fetchData = useCallback(async (f?: Record<string, string>, p?: number) => {
    setLoading(true);
    try {
      const q = f || filters;
      const result = await api.airline.velocity.listSnapshots({
        ...q,
        tenant: TENANT,
        page: (p ?? page) + 1,
        page_size: rowsPerPage,
      });
      setData(result);
    } finally {
      setLoading(false);
    }
  }, [filters, page, rowsPerPage]);

  // On metadata load, auto-select latest file_date if filters are empty, then fetch.
  useEffect(() => {
    if (meta.length === 0) return;
    if (Object.keys(filters).length === 0) {
      const defaults: Record<string, string> = {};
      const fdMeta = meta.find(m => m.field === 'file_date');
      if (fdMeta && fdMeta.values.length > 0 && fdMeta.values[0] !== 'No file dates available') {
        defaults.file_date = fdMeta.values[0];
      }
      if (Object.keys(defaults).length > 0) {
        onFiltersChange(defaults);
        fetchData(defaults, 0);
        return;
      }
    }
    fetchData(filters, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta]);

  const handleApply = () => {
    setPage(0);
    fetchData(filters, 0);
  };

  const handleReset = () => {
    const defaults: Record<string, string> = {};
    const fdMeta = meta.find(m => m.field === 'file_date');
    if (fdMeta && fdMeta.values.length > 0 && fdMeta.values[0] !== 'No file dates available') {
      defaults.file_date = fdMeta.values[0];
    }
    onFiltersChange(defaults);
    setPage(0);
    fetchData(defaults, 0);
  };

  const handlePageChange = (_: unknown, p: number) => {
    setPage(p);
    fetchData(filters, p);
  };

  // KPIs (computed from current page rows; page_info.total is total flights)
  const kpis: KpiTile[] = data && data.items.length > 0 ? (() => {
    const items = data.items;
    const avgCap = items.reduce((s, r) => s + r.capacity, 0) / items.length;
    const avgBook = items.reduce((s, r) => s + Number(r.booking_pct || 0), 0) / items.length;
    const avgFcst = items.reduce((s, r) => s + r.forecasted_seat_factor, 0) / items.length;
    const trend: 'up' | 'down' | 'flat' = avgBook >= 75 ? 'up' : avgBook < 65 ? 'down' : 'flat';
    return [
      { label: 'Total Flights', value: data.page_info.total, sub: `Page ${data.page_info.page} of ${Math.ceil(data.page_info.total / rowsPerPage)}` },
      { label: 'Avg Capacity', value: Math.round(avgCap), sub: 'seats per flight' },
      { label: 'Avg Booking %', value: `${avgBook.toFixed(1)}%`, trend, sub: 'benchmark 70%', color: pctColor(avgBook) },
      { label: 'Avg Forecasted SF %', value: `${avgFcst.toFixed(1)}%`, sub: 'forecast load factor', color: pctColor(avgFcst) },
    ];
  })() : [];

  // Filter fields from metadata
  const allFields = meta.map(m => {
    const isNoDates = m.field === 'file_date' && m.values[0] === 'No file dates available';
    return {
      key: m.field,
      label: m.label,
      type: 'select' as const,
      options: m.values.map(v => ({ value: v, label: v })),
      disabled: isNoDates,
      placeholder: m.values.slice(0, 3).join(', ') + '...',
    };
  });

  return (
    <>
      <ActionBar onExport={() => api.airline.velocity.exportSnapshots({ ...filters, tenant: TENANT })} />

      <Box sx={{ display: 'flex', height: 'calc(100vh - 280px)' }}>
        <FilterPanel
          title="JY Velocity Filters"
          fields={allFields}
          open={filterOpen}
          onToggle={() => setFilterOpen(!filterOpen)}
          values={filters}
          onValuesChange={onFiltersChange}
          onApply={handleApply}
          onReset={handleReset}
        />

        <Box sx={{ flex: 1, overflow: 'auto', p: 2 }}>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}><CircularProgress /></Box>
          ) : !data || data.items.length === 0 ? (
            <EmptyState icon={<Flight sx={{ fontSize: 64 }} />} title="No JY Velocity Data" description="Apply filters to search JY velocity snapshots." actionLabel="Load All" onAction={() => fetchData({}, 0)} />
          ) : (
            <>
              <KpiTiles tiles={kpis} />
              <TableContainer component={Paper} variant="outlined">
                <Table size="small" stickyHeader aria-label="JY velocity snapshots">
                  <TableHead>
                    <TableRow>
                      <TableCell>Dep Date</TableCell>
                      <TableCell>Dep Time</TableCell>
                      <TableCell>Origin → Dest</TableCell>
                      <TableCell>City Pair</TableCell>
                      <TableCell>Eqp</TableCell>
                      <TableCell>Compartment</TableCell>
                      <TableCell align="right">Days Left</TableCell>
                      <TableCell align="right">Capacity</TableCell>
                      <TableCell align="right">Current Booking</TableCell>
                      <TableCell align="right">Seats Available</TableCell>
                      <TableCell align="right">Booking %</TableCell>
                      <TableCell align="right">Actual SF %</TableCell>
                      <TableCell align="right">Forecasted SF %</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {data.items.map(row => {
                      const bookingPct = Number(row.booking_pct);
                      const actual = Number(row.actual_seat_factor);
                      const forecast = Number(row.forecasted_seat_factor);
                      return (
                        <TableRow key={row.id} hover>
                          <TableCell><Typography variant="caption">{row.dep_date}</Typography></TableCell>
                          <TableCell><Typography variant="caption" fontFamily="monospace">{row.dep_time}</Typography></TableCell>
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                              <Chip label={row.origin} size="small" variant="outlined" />
                              <ArrowForward sx={{ fontSize: 14, color: 'text.secondary' }} />
                              <Chip label={row.destination} size="small" variant="outlined" />
                            </Box>
                          </TableCell>
                          <TableCell><Typography variant="caption" fontFamily="monospace">{row.city_pair}</Typography></TableCell>
                          <TableCell><Chip label={row.eqp} size="small" /></TableCell>
                          <TableCell><Chip label={row.compartment} size="small" variant="outlined" /></TableCell>
                          <TableCell align="right"><Typography variant="body2">{row.days_left}</Typography></TableCell>
                          <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.capacity}</Typography></TableCell>
                          <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.current_booking}</Typography></TableCell>
                          <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.seats_available}</Typography></TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" fontWeight={600} sx={{ color: pctColor(bookingPct) }}>
                              {bookingPct.toFixed(1)}%
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" fontWeight={600} sx={{ color: pctColor(actual) }}>
                              {actual.toFixed(0)}%
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" fontWeight={600} sx={{ color: pctColor(forecast) }}>
                              {forecast.toFixed(0)}%
                            </Typography>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
              <TablePagination
                component="div"
                count={data.page_info.total}
                page={page}
                onPageChange={handlePageChange}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={(e: React.ChangeEvent<HTMLInputElement>) => { setRowsPerPage(parseInt(e.target.value)); setPage(0); fetchData(filters, 0); }}
                rowsPerPageOptions={[10, 20, 50]}
              />
            </>
          )}
        </Box>
      </Box>
    </>
  );
}
