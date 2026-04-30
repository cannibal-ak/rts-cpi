import { useState, useEffect, useCallback } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Chip, CircularProgress, TablePagination, Tooltip,
} from '@mui/material';
import { DirectionsBoat } from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
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

  useEffect(() => { fetchData(); }, [tenantCode]);

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

  // Auto-select latest date when metadata is loaded
  useEffect(() => {
    if (meta.length > 0 && Object.keys(filters).length === 0) {
      const defaultFilters: Record<string, string> = {};
      const fileDateMeta = meta.find(m => m.field === 'file_date');
      if (fileDateMeta && fileDateMeta.values.length > 0 && fileDateMeta.values[0] !== 'No file dates available') {
        defaultFilters.file_date = fileDateMeta.values[0];
      }
      const operatorMeta = meta.find(m => m.field === 'operator');
      if (operatorMeta && operatorMeta.values.length === 1) {
        defaultFilters.operator = operatorMeta.values[0];
      }
      if (Object.keys(defaultFilters).length > 0) {
        setFilters(defaultFilters);
        fetchData(defaultFilters, 0);
      }
    }
  }, [meta, fetchData, filters]);
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
    <Box>
      <PageHeader
        title={pageTitle}
        subtitle={`Competitive pricing across ${tenantCode} cruise and ferry routes`}
        breadcrumbs={[{ label: 'Home', href: '/' }, { label: pageTitle }]}
        actions={freshness && <DataFreshnessIndicator data={freshness} compact />}
      />

      <ActionBar onExport={() => api.cfl.exportSnapshots({ ...filters, tenant: tenantCode })} />

      <Box sx={{ display: 'flex', height: 'calc(100vh - 220px)' }}>
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

        <Box sx={{ flex: 1, overflow: 'auto', p: 2 }}>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}><CircularProgress /></Box>
          ) : !data || data.items.length === 0 ? (
            <EmptyState icon={<DirectionsBoat sx={{ fontSize: 64 }} />} title="No CFL Data" description="Apply filters to search cruise/ferry snapshots." actionLabel="Load All" onAction={() => fetchData({}, 0)} />
          ) : (
            <>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small" stickyHeader aria-label="CFL CPI snapshots">
                  <TableHead>
                    <TableRow>
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
              />
            </>
          )}
        </Box>
      </Box>
    </Box>
  );
}
