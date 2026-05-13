import { useState, useEffect, useCallback } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Chip, CircularProgress, TablePagination, Tooltip, Breadcrumbs, Link,
} from '@mui/material';
import { DirectionsBoat, NavigateNext } from '@mui/icons-material';
import DataFreshnessIndicator from '../../components/common/DataFreshnessIndicator';
import FilterPanel from '../../components/filters/FilterPanel';
import ActionBar from '../../components/filters/ActionBar';
import EmptyState from '../../components/common/EmptyState';
import { api } from '../../api';
import { formatCurrency } from '../../utils/format';
import type { CflSnapshot, FilterMetadata, Paginated } from '../../types';
import { DataFreshness } from '../../types';

interface CflCpiPageProps {
  tenantCode: 'FJL';
}

export default function CflCpiPage({ tenantCode }: CflCpiPageProps) {
  const [filterOpen, setFilterOpen] = useState(true);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Paginated<CflSnapshot> | null>(null);
  const [meta, setMeta] = useState<FilterMetadata[]>([]);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(20);

  const [freshness, setFreshness] = useState<DataFreshness | null>(null);

  const pageTitle = `Cruise/Ferry CPI \u2013 ${tenantCode}`;

  useEffect(() => {
    api.cfl.getFilterMetadata(tenantCode).then(setMeta);
    api.stats.getFreshnessMetrics().then(data => {
      const cfl = data.find(d => d.domain === 'Cruise/Ferry CPI');
      if (cfl) setFreshness(cfl);
    });
  }, [tenantCode]);

  const fetchData = useCallback(async (f?: Record<string, string>, p?: number) => {
    setLoading(true);
    try {
      const q = f || filters;
      const result = await api.cfl.listSnapshots({
        ...q,
        tenant: tenantCode,
        page: (p ?? page) + 1,
        page_size: rowsPerPage
      });
      setData(result);
    } finally { setLoading(false); }
  }, [filters, page, rowsPerPage, tenantCode]);


  const handleApply = () => {
    setPage(0);
    fetchData(filters, 0);
  };

  const handleReset = () => {
    const defaultFilters: Record<string, string> = {};
    const fileDateMeta = meta.find(m => m.field === 'file_date');
    if (fileDateMeta && fileDateMeta.values.length > 0 && fileDateMeta.values[0] !== 'No file dates available') {
      defaultFilters.file_date = fileDateMeta.values[0];
    }
    const operatorMeta = meta.find(m => m.field === 'operator');
    if (operatorMeta && operatorMeta.values.length === 1) {
      defaultFilters.operator = operatorMeta.values[0];
    }
    setFilters(defaultFilters);
    setPage(0);
    fetchData(defaultFilters, 0);
  };

  useEffect(() => {
    if (meta.length === 0) return;
    if (Object.keys(filters).length === 0) {
      const defaults: Record<string, string> = {};
      const fileDateMeta = meta.find(m => m.field === 'file_date');
      if (fileDateMeta && fileDateMeta.values.length > 0 && fileDateMeta.values[0] !== 'No file dates available') {
        defaults.file_date = fileDateMeta.values[0];
      }
      const operatorMeta = meta.find(m => m.field === 'operator');
      if (operatorMeta && operatorMeta.values.length === 1) {
        defaults.operator = operatorMeta.values[0];
      }
      if (Object.keys(defaults).length > 0) {
        setFilters(defaults);
        fetchData(defaults, 0);
        return;
      }
    }
    fetchData(filters, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta]);

  const handlePageChange = (_: unknown, p: number) => { setPage(p); fetchData(filters, p); };

  const allFields = meta.map(m => {
    const isRestricted = m.field === 'operator' && m.values.length === 1;
    const isNoDates = m.field === 'file_date' && m.values[0] === 'No file dates available';

    return {
      key: m.field,
      label: m.label,
      type: 'select' as const,
      options: m.values.map(v => ({ value: v, label: v })),
      disabled: isRestricted || isNoDates,
      placeholder: m.values.slice(0, 3).join(', ') + '...',
    };
  });

  const displayedFields = allFields
    .filter(f => f.key === 'file_date')
    .map(f => ({ ...f, required: true }));

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box
        sx={{
          mb: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1,
          minHeight: 28,
          flexWrap: 'wrap',
        }}
      >
        <Breadcrumbs separator={<NavigateNext fontSize="small" />}>
          <Link underline="hover" color="inherit" href="/" sx={{ fontSize: 13 }}>
            Home
          </Link>
          <Typography color="text.primary" sx={{ fontSize: 13 }}>
            {pageTitle}
          </Typography>
        </Breadcrumbs>
        {freshness && (
          <Box sx={{ display: 'inline-flex', alignItems: 'center' }}>
            <DataFreshnessIndicator data={freshness} compact />
          </Box>
        )}
      </Box>

      <ActionBar onExport={() => api.cfl.exportSnapshots({ ...filters, tenant: tenantCode })} />

      <Box sx={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <FilterPanel
          title={`${tenantCode} Filters`}
          fields={displayedFields}
          open={filterOpen}
          onToggle={() => setFilterOpen(!filterOpen)}
          values={filters}
          onValuesChange={setFilters}
          onApply={handleApply}
          onReset={handleReset}
        />

        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, p: 2 }}>
          {loading ? (
            <Box sx={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}><CircularProgress /></Box>
          ) : !data || data.items.length === 0 ? (
            <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <EmptyState icon={<DirectionsBoat sx={{ fontSize: 64 }} />} title="No CFL Data" description="No snapshots match the current filters." />
            </Box>
          ) : (
            <>
              <TableContainer component={Paper} variant="outlined" sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
                <Table size="small" stickyHeader aria-label="CFL CPI snapshots">
                  <TableHead>
                    <TableRow>
                      {/* ── Existing outbound summary ── */}
                      <TableCell>Route</TableCell>
                      <TableCell>Trip</TableCell>
                      <TableCell>Operator</TableCell>
                      <TableCell>Product</TableCell>
                      <TableCell>Equipment</TableCell>
                      <TableCell align="right">Total Fare</TableCell>
                      <TableCell align="right">Pax Fare</TableCell>
                      <TableCell align="right">Veh Fare</TableCell>
                      <TableCell align="right">Taxes</TableCell>
                      <TableCell>Vehicle</TableCell>
                      <TableCell>Avail</TableCell>
                      <TableCell>Dep Date</TableCell>
                      {/* ── Outbound Arrival (024) ── */}
                      <TableCell>Out Arr Date</TableCell>
                      <TableCell>Out Arr Time</TableCell>
                      {/* ── Outbound Descriptions & Seats (024) ── */}
                      <TableCell>Out Cabin Desc</TableCell>
                      <TableCell>Out Seat Type</TableCell>
                      <TableCell align="right">Out #Cabins</TableCell>
                      <TableCell align="right">Out Seat Charge</TableCell>
                      <TableCell align="right">Out #Seats</TableCell>
                      {/* ── Return Journey — Schedule & Product (024) ── */}
                      <TableCell>Return Dep Date</TableCell>
                      <TableCell>Return Dep Time</TableCell>
                      <TableCell>Return Arr Date</TableCell>
                      <TableCell>Return Arr Time</TableCell>
                      <TableCell>Ship Name (R)</TableCell>
                      <TableCell>Return Cabin Type</TableCell>
                      <TableCell>Return Cabin Desc</TableCell>
                      <TableCell>Return Seat Type</TableCell>
                      <TableCell>Return Availability</TableCell>
                      {/* ── Return Journey — Fares (024) ── */}
                      <TableCell align="right">Return Per Pax</TableCell>
                      <TableCell align="right">Return #Pax</TableCell>
                      <TableCell align="right">Return Vehicle</TableCell>
                      <TableCell align="right">Return Cabin</TableCell>
                      <TableCell align="right">Return #Cabins</TableCell>
                      <TableCell align="right">Return Seat</TableCell>
                      <TableCell align="right">Return #Seats</TableCell>
                      <TableCell align="right">Return Taxes</TableCell>
                      {/* ── Total/Combined Fares (024) ── */}
                      <TableCell align="right">Total Per Pax</TableCell>
                      <TableCell align="right">Total #Pax</TableCell>
                      <TableCell align="right">Total Vehicle</TableCell>
                      <TableCell align="right">Total Cabin</TableCell>
                      <TableCell align="right">Total #Cabins</TableCell>
                      <TableCell align="right">Total Seat</TableCell>
                      <TableCell align="right">Total #Seats</TableCell>
                      <TableCell align="right">Total Taxes</TableCell>
                      {/* ── Duration (024) ── */}
                      <TableCell align="right">Duration (Days)</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {data.items.map(row => (
                      <TableRow key={row.id} hover>
                        <TableCell><Typography variant="body2" fontWeight={600}>{row.org}–{row.dest}</Typography></TableCell>
                        <TableCell><Chip label={row.trip_type === 'ONE_WAY' ? 'OW' : 'RT'} size="small" variant="outlined" /></TableCell>
                        <TableCell><Typography variant="body2">{row.source}</Typography></TableCell>
                        <TableCell><Chip label={row.prod_family} size="small" /></TableCell>
                        <TableCell><Tooltip title={row.out_equip_name}><Typography variant="caption" noWrap sx={{ maxWidth: 100, display: 'block' }}>{row.out_equip_name}</Typography></Tooltip></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace" fontWeight={600}>{formatCurrency(row.total_fare)}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{formatCurrency(row.out_per_pax_fare)}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.out_veh_fare > 0 ? formatCurrency(row.out_veh_fare) : '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{formatCurrency(row.out_taxes)}</Typography></TableCell>
                        <TableCell><Chip label={row.veh_size} size="small" variant="outlined" /></TableCell>
                        <TableCell>
                          <Chip label={row.out_avail} size="small"
                            color={row.out_avail === 'Available' ? 'success' : row.out_avail === 'Limited' ? 'warning' : 'error'} variant="outlined" />
                        </TableCell>
                        <TableCell><Typography variant="caption">{row.out_dep_date}</Typography></TableCell>
                        {/* ── Outbound Arrival (024) ── */}
                        <TableCell><Typography variant="caption">{row.out_arr_date ?? '—'}</Typography></TableCell>
                        <TableCell><Typography variant="caption">{row.out_arr_time ?? '—'}</Typography></TableCell>
                        {/* ── Outbound Descriptions & Seats (024) ── */}
                        <TableCell><Tooltip title={row.out_cabin_desc ?? ''}><Typography variant="caption" noWrap sx={{ maxWidth: 140, display: 'block' }}>{row.out_cabin_desc ?? '—'}</Typography></Tooltip></TableCell>
                        <TableCell><Typography variant="caption">{row.out_seat_type ?? '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.out_num_cabs ?? '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.out_seat_fare != null ? formatCurrency(row.out_seat_fare) : '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.out_num_seats ?? '—'}</Typography></TableCell>
                        {/* ── Return Journey — Schedule & Product (024) ── */}
                        <TableCell><Typography variant="caption">{row.ret_dep_date ?? '—'}</Typography></TableCell>
                        <TableCell><Typography variant="caption">{row.ret_dep_time ?? '—'}</Typography></TableCell>
                        <TableCell><Typography variant="caption">{row.ret_arr_date ?? '—'}</Typography></TableCell>
                        <TableCell><Typography variant="caption">{row.ret_arr_time ?? '—'}</Typography></TableCell>
                        <TableCell><Tooltip title={row.ret_equip_name ?? ''}><Typography variant="caption" noWrap sx={{ maxWidth: 100, display: 'block' }}>{row.ret_equip_name ?? '—'}</Typography></Tooltip></TableCell>
                        <TableCell><Typography variant="caption">{row.ret_cab_type ?? '—'}</Typography></TableCell>
                        <TableCell><Tooltip title={row.ret_cab_desc ?? ''}><Typography variant="caption" noWrap sx={{ maxWidth: 140, display: 'block' }}>{row.ret_cab_desc ?? '—'}</Typography></Tooltip></TableCell>
                        <TableCell><Typography variant="caption">{row.ret_seat_type ?? '—'}</Typography></TableCell>
                        <TableCell>
                          {row.ret_avail
                            ? <Chip label={row.ret_avail} size="small" color={row.ret_avail === 'Available' ? 'success' : row.ret_avail === 'Limited' ? 'warning' : 'error'} variant="outlined" />
                            : <Typography variant="caption">—</Typography>}
                        </TableCell>
                        {/* ── Return Journey — Fares (024) ── */}
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.ret_per_pax_fare != null ? formatCurrency(row.ret_per_pax_fare) : '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.ret_num_pax ?? '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.ret_veh_fare != null ? formatCurrency(row.ret_veh_fare) : '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.ret_cab_fare != null ? formatCurrency(row.ret_cab_fare) : '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.ret_num_cabs ?? '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.ret_seat_fare != null ? formatCurrency(row.ret_seat_fare) : '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.ret_num_seats ?? '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.ret_taxes != null ? formatCurrency(row.ret_taxes) : '—'}</Typography></TableCell>
                        {/* ── Total/Combined Fares (024) ── */}
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.tot_per_pax_fare != null ? formatCurrency(row.tot_per_pax_fare) : '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.tot_num_pax ?? '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.tot_veh_fare != null ? formatCurrency(row.tot_veh_fare) : '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.tot_cab_fare != null ? formatCurrency(row.tot_cab_fare) : '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.tot_num_cabs ?? '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.tot_seat_fare != null ? formatCurrency(row.tot_seat_fare) : '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.tot_num_seats ?? '—'}</Typography></TableCell>
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.tot_taxes != null ? formatCurrency(row.tot_taxes) : '—'}</Typography></TableCell>
                        {/* ── Duration (024) ── */}
                        <TableCell align="right"><Typography variant="body2" fontFamily="monospace">{row.duration ?? '—'}</Typography></TableCell>
                      </TableRow>
                    ))}
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
                sx={{ flexShrink: 0 }}
              />
            </>
          )}
        </Box>
      </Box>
    </Box>
  );
}
