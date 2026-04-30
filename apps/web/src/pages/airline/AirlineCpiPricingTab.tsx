import { useState, useEffect, useCallback } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Chip, CircularProgress, TablePagination, Tooltip,
} from '@mui/material';
import { Flight } from '@mui/icons-material';
import FilterPanel from '../../components/filters/FilterPanel';
import ActionBar from '../../components/filters/ActionBar';
import EmptyState from '../../components/common/EmptyState';
import { api } from '../../api';
import { formatCurrency } from '../../utils/format';
import type { AirlineSnapshot, FilterMetadata, Paginated } from '../../types';

interface AirlineCpiPricingTabProps {
  tenantCode: 'JY' | 'PW';
  filters: Record<string, string>;
  onFiltersChange: (f: Record<string, string>) => void;
}

export default function AirlineCpiPricingTab({ tenantCode, filters, onFiltersChange }: AirlineCpiPricingTabProps) {
  const [filterOpen, setFilterOpen] = useState(true);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Paginated<AirlineSnapshot> | null>(null);
  const [meta, setMeta] = useState<FilterMetadata[]>([]);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(20);

  // Load filter metadata on mount / tenant switch
  useEffect(() => {
    api.airline.getFilterMetadata(tenantCode).then(setMeta);
  }, [tenantCode]);

  const fetchData = useCallback(async (f?: Record<string, string>, p?: number) => {
    setLoading(true);
    try {
      const q = f || filters;
      const result = await api.airline.listSnapshots({
        ...q,
        tenant: tenantCode,
        page: (p ?? page) + 1,
        page_size: rowsPerPage,
      });
      setData(result);
    } finally {
      setLoading(false);
    }
  }, [filters, page, rowsPerPage, tenantCode]);

  // When metadata is loaded, auto-select latest file_date if filters are empty,
  // then fire the initial fetch.
  useEffect(() => {
    if (meta.length === 0) return;
    if (Object.keys(filters).length === 0) {
      const defaults: Record<string, string> = {};
      const fdMeta = meta.find(m => m.field === 'file_date');
      if (fdMeta && fdMeta.values.length > 0 && fdMeta.values[0] !== 'No file dates available') {
        defaults.file_date = fdMeta.values[0];
      }
      const alMeta = meta.find(m => m.field === 'airline');
      if (alMeta && alMeta.values.length === 1) {
        defaults.airline = alMeta.values[0];
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
    const defaultFilters: Record<string, string> = {};
    const fileDateMeta = meta.find(m => m.field === 'file_date');
    if (fileDateMeta && fileDateMeta.values.length > 0 && fileDateMeta.values[0] !== 'No file dates available') {
      defaultFilters.file_date = fileDateMeta.values[0];
    }
    const airlineMeta = meta.find(m => m.field === 'airline');
    if (airlineMeta && airlineMeta.values.length === 1) {
      defaultFilters.airline = airlineMeta.values[0];
    }
    onFiltersChange(defaultFilters);
    setPage(0);
    fetchData(defaultFilters, 0);
  };

  const handlePageChange = (_: unknown, p: number) => {
    setPage(p);
    fetchData(filters, p);
  };

  const allFields = meta.map(m => {
    const isRestricted = m.field === 'airline' && m.values.length === 1;
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

  return (
    <>
      <ActionBar onExport={() => api.airline.exportSnapshots({ ...filters, tenant: tenantCode })} />

      <Box sx={{ display: 'flex', height: 'calc(100vh - 280px)' }}>
        <FilterPanel
          title={`${tenantCode} Filters`}
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
            <EmptyState icon={<Flight sx={{ fontSize: 64 }} />} title={`No ${tenantCode} Data`} description={`Apply filters to search ${tenantCode} airline CPI snapshots.`} actionLabel="Load All" onAction={() => fetchData({}, 0)} />
          ) : (
            <>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small" stickyHeader aria-label={`${tenantCode} Airline CPI snapshots`}>
                  <TableHead>
                    <TableRow>
                      <TableCell>Route</TableCell>
                      <TableCell>Trip</TableCell>
                      <TableCell>Ref Airline</TableCell>
                      <TableCell>Cabin</TableCell>
                      <TableCell align="right">Ref Fare</TableCell>
                      <TableCell>Comp Airline</TableCell>
                      <TableCell align="right">Comp Fare</TableCell>
                      <TableCell align="right">Delta</TableCell>
                      <TableCell>POS</TableCell>
                      <TableCell>Cap Date</TableCell>
                      <TableCell>Dep Date</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {data.items.map(row => {
                      const delta = ((row.comp_tot_fare - row.ref_tot_fare) / row.ref_tot_fare * 100);
                      return (
                        <TableRow key={row.id} hover>
                          <TableCell>
                            <Typography variant="body2" fontWeight={600}>{row.ref_org}–{row.ref_dst}</Typography>
                          </TableCell>
                          <TableCell><Chip label={row.trip_type} size="small" variant="outlined" /></TableCell>
                          <TableCell>
                            <Tooltip title={row.ref_flt_num}><Chip label={row.ref_al} size="small" /></Tooltip>
                          </TableCell>
                          <TableCell><Chip label={row.ref_cab_code} size="small" variant="outlined" /></TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" fontFamily="monospace">{formatCurrency(row.ref_tot_fare)}</Typography>
                          </TableCell>
                          <TableCell>
                            <Tooltip title={row.comp_flt_num}><Chip label={row.comp_al} size="small" color="secondary" /></Tooltip>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" fontFamily="monospace">{formatCurrency(row.comp_tot_fare)}</Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2" fontWeight={600} sx={{ color: delta < 0 ? 'success.main' : delta > 0 ? 'error.main' : 'text.primary' }}>
                              {delta > 0 ? '+' : ''}{delta.toFixed(1)}%
                            </Typography>
                          </TableCell>
                          <TableCell><Typography variant="caption">{row.pos}</Typography></TableCell>
                          <TableCell><Typography variant="caption">{row.cap_date}</Typography></TableCell>
                          <TableCell><Typography variant="caption">{row.ref_dep_date}</Typography></TableCell>
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
