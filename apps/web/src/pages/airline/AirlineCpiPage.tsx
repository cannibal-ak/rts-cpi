import { useState, useEffect, useCallback } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Chip, CircularProgress, TablePagination, Tooltip,
} from '@mui/material';
import { Flight } from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import DataFreshnessIndicator from '../../components/common/DataFreshnessIndicator';
import FilterPanel from '../../components/filters/FilterPanel';
import ActionBar from '../../components/filters/ActionBar';
import KpiTiles from '../../components/common/KpiTiles';
import type { KpiTile } from '../../components/common/KpiTiles';
import EmptyState from '../../components/common/EmptyState';
import { api } from '../../api';
import { formatCurrency } from '../../utils/format';
import type { AirlineSnapshot, FilterMetadata, Paginated } from '../../types';
import { DataFreshness } from '../../types';

interface AirlineCpiPageProps {
  /** Tenant code determines which snapshot view to query (JY or PW). */
  tenantCode: 'JY' | 'PW';
}

const TENANT_LABELS: Record<string, string> = {
  JY: 'Airline CPI \u2013 JY',
  PW: 'Airline CPI \u2013 PW',
};

export default function AirlineCpiPage({ tenantCode }: AirlineCpiPageProps) {
  const [filterOpen, setFilterOpen] = useState(true);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Paginated<AirlineSnapshot> | null>(null);
  const [meta, setMeta] = useState<FilterMetadata[]>([]);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(20);

  const [freshness, setFreshness] = useState<DataFreshness | null>(null);

  const pageTitle = TENANT_LABELS[tenantCode] || `Airline CPI \u2013 ${tenantCode}`;

  // Reset state when switching tenant
  useEffect(() => {
    setFilters({});
    setData(null);
    setMeta([]);
    setPage(0);
  }, [tenantCode]);

  // Load filter metadata for this tenant
  useEffect(() => {
    api.airline.getFilterMetadata(tenantCode).then(setMeta);
    api.stats.getFreshnessMetrics().then(data => {
      const air = data.find(d => d.domain === 'Airline CPI');
      if (air) setFreshness(air);
    });
  }, [tenantCode]);

  // Auto-load on mount / tenant switch
  useEffect(() => { fetchData(); }, [tenantCode]);

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
      const airlineMeta = meta.find(m => m.field === 'airline');
      if (airlineMeta && airlineMeta.values.length === 1) {
        defaultFilters.airline = airlineMeta.values[0];
      }
      if (Object.keys(defaultFilters).length > 0) {
        setFilters(defaultFilters);
        fetchData(defaultFilters, 0);
      }
    }
  }, [meta, fetchData, filters]);

  const handlePageChange = (_: unknown, p: number) => {
    setPage(p);
    fetchData(filters, p);
  };

  // Compute KPIs
  const kpis: KpiTile[] = data && data.items.length > 0 ? (() => {
    const items = data.items;
    const refFares = items.map(i => i.ref_tot_fare);
    const compFares = items.map(i => i.comp_tot_fare);
    const avgRef = refFares.reduce((a, b) => a + b, 0) / refFares.length;
    const avgComp = compFares.reduce((a, b) => a + b, 0) / compFares.length;
    const diff = ((avgComp - avgRef) / avgRef) * 100;
    return [
      { label: 'Results', value: data.page_info.total, sub: `Page ${data.page_info.page} of ${Math.ceil(data.page_info.total / rowsPerPage)}` },
      { label: 'Avg Ref Fare', value: formatCurrency(avgRef), sub: `Min ${formatCurrency(Math.min(...refFares))} / Max ${formatCurrency(Math.max(...refFares))}` },
      { label: 'Avg Comp Fare', value: formatCurrency(avgComp), sub: `Min ${formatCurrency(Math.min(...compFares))} / Max ${formatCurrency(Math.max(...compFares))}`, color: avgComp < avgRef ? 'success.main' : avgComp > avgRef ? 'error.main' : undefined },
      { label: 'Comp vs Ref', value: `${diff > 0 ? '+' : ''}${diff.toFixed(1)}%`, trend: diff > 1 ? 'up' : diff < -1 ? 'down' : 'flat', sub: avgComp < avgRef ? 'Competitor undercuts' : 'Competitor premium' },
    ];
  })() : [];

  // Build filter fields from metadata
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
    <Box>
      <PageHeader
        title={pageTitle}
        subtitle={`Competitive pricing intelligence for ${tenantCode} airline routes`}
        breadcrumbs={[{ label: 'Home', href: '/' }, { label: pageTitle }]}
        actions={freshness && <DataFreshnessIndicator data={freshness} compact />}
      />

      <ActionBar onExport={() => api.airline.exportSnapshots({ ...filters, tenant: tenantCode })} />

      <Box sx={{ display: 'flex', height: 'calc(100vh - 220px)' }}>
        <FilterPanel
          title={`${tenantCode} Filters`}
          fields={allFields}
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
            <EmptyState icon={<Flight sx={{ fontSize: 64 }} />} title={`No ${tenantCode} Data`} description={`Apply filters to search ${tenantCode} airline CPI snapshots.`} actionLabel="Load All" onAction={() => fetchData({}, 0)} />
          ) : (
            <>
              <KpiTiles tiles={kpis} />
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
    </Box>
  );
}
