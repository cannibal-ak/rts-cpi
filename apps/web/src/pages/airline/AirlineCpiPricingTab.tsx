import { useState, useEffect, useCallback, useMemo, type ReactNode } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Chip, CircularProgress, TablePagination, Tooltip,
  Button, Menu, MenuList, MenuItem, ListSubheader, Checkbox, ListItemText, Divider,
} from '@mui/material';
import { Flight, ViewColumn } from '@mui/icons-material';
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

// ── Column-definition framework ──────────────────────────────────────────
//
// Phase 2F lands the 47 new dictionary columns from migration 022 in the
// frontend. The full set is 77 dict-aligned columns (id + 76 data fields).
// 16 are visible by default; the remaining 61 are reachable via a column-
// picker menu and grouped by cluster.
//
// Default-visible 16:
//   route, trip_type, ref_cab_code, ref_al, ref_tot_fare,
//   comp_al, comp_tot_fare, delta, pos, cap_date, ref_dep_date,
//   ref_equip_code, comp_equip_code, ref_ff_code, comp_ff_code, ref_stops

type ColumnCluster =
  | 'core'
  | 'ref_outbound'
  | 'ref_return'
  | 'comp_outbound'
  | 'comp_return'
  | 'point_of'
  | 'provenance';

const CLUSTER_LABELS: Record<ColumnCluster, string> = {
  core: 'Core',
  ref_outbound: 'Reference flight — outbound',
  ref_return: 'Reference flight — return',
  comp_outbound: 'Competitor — outbound',
  comp_return: 'Competitor — return',
  point_of: 'Point-of-*',
  provenance: 'Provenance',
};

interface ColumnDef {
  key: string;
  label: string;
  cluster: ColumnCluster;
  defaultVisible: boolean;
  align?: 'left' | 'right';
  /** Custom renderer (defaults to plain text of row[key]). */
  render?: (row: AirlineSnapshot) => ReactNode;
}

/** Format a date-ish value for display. */
const fmtDate = (v: unknown): ReactNode =>
  v == null || v === '' ? '—' : String(v);

/** Format a plain text/number cell with a "—" fallback for null/empty. */
const fmtText = (v: unknown): ReactNode =>
  v == null || v === '' ? <Typography variant="body2" color="text.disabled">—</Typography>
                        : <Typography variant="body2">{String(v)}</Typography>;

const fmtCaption = (v: unknown): ReactNode =>
  v == null || v === '' ? '—' : <Typography variant="caption">{String(v)}</Typography>;

const fmtInteger = (v: unknown): ReactNode =>
  v == null || v === '' ? <Typography variant="body2" color="text.disabled">—</Typography>
                        : <Typography variant="body2">{String(v)}</Typography>;

const fmtFareRef = (row: AirlineSnapshot, key: keyof AirlineSnapshot): ReactNode =>
  <Typography variant="body2" fontFamily="monospace">
    {formatCurrency(row[key] as number | null | undefined, row.ref_curr)}
  </Typography>;

const fmtFareComp = (row: AirlineSnapshot, key: keyof AirlineSnapshot): ReactNode =>
  <Typography variant="body2" fontFamily="monospace">
    {formatCurrency(row[key] as number | null | undefined, row.comp_curr)}
  </Typography>;

const COLUMNS: ColumnDef[] = [
  // ── core (default visible) ──
  { key: 'route', label: 'Route', cluster: 'core', defaultVisible: true,
    render: (r) => <Typography variant="body2" fontWeight={600}>{r.ref_org}–{r.ref_dst}</Typography> },
  { key: 'trip_type', label: 'Trip', cluster: 'core', defaultVisible: true,
    render: (r) => <Chip label={r.trip_type} size="small" variant="outlined" /> },
  { key: 'ref_al', label: 'Ref Airline', cluster: 'core', defaultVisible: true,
    render: (r) => <Tooltip title={r.ref_flt_num}><Chip label={r.ref_al} size="small" /></Tooltip> },
  { key: 'ref_cab_code', label: 'Cabin', cluster: 'core', defaultVisible: true,
    render: (r) => <Chip label={r.ref_cab_code} size="small" variant="outlined" /> },
  { key: 'ref_tot_fare', label: 'Ref Fare', cluster: 'core', defaultVisible: true, align: 'right',
    render: (r) => fmtFareRef(r, 'ref_tot_fare') },
  { key: 'comp_al', label: 'Comp Airline', cluster: 'core', defaultVisible: true,
    render: (r) => <Tooltip title={r.comp_flt_num}><Chip label={r.comp_al} size="small" color="secondary" /></Tooltip> },
  { key: 'comp_tot_fare', label: 'Comp Fare', cluster: 'core', defaultVisible: true, align: 'right',
    render: (r) => fmtFareComp(r, 'comp_tot_fare') },
  { key: 'delta', label: 'Delta', cluster: 'core', defaultVisible: true, align: 'right',
    render: (r) => {
      const delta = r.ref_tot_fare > 0
        ? ((r.comp_tot_fare - r.ref_tot_fare) / r.ref_tot_fare * 100)
        : null;
      if (delta === null) {
        return <Typography variant="body2" color="text.disabled">—</Typography>;
      }
      return (
        <Typography
          variant="body2"
          fontWeight={600}
          sx={{ color: delta < 0 ? 'success.main' : delta > 0 ? 'error.main' : 'text.primary' }}
        >
          {delta > 0 ? '+' : ''}{delta.toFixed(1)}%
        </Typography>
      );
    } },
  { key: 'pos', label: 'POS', cluster: 'core', defaultVisible: true,
    render: (r) => fmtCaption(r.pos) },
  { key: 'cap_date', label: 'Cap Date', cluster: 'core', defaultVisible: true,
    render: (r) => fmtCaption(r.cap_date) },
  { key: 'ref_dep_date', label: 'Dep Date', cluster: 'core', defaultVisible: true,
    render: (r) => fmtCaption(r.ref_dep_date) },

  // ── reference flight outbound additions (default visible 5; rest in picker) ──
  { key: 'ref_equip_code', label: 'Ref Equipment', cluster: 'ref_outbound', defaultVisible: true,
    render: (r) => fmtText(r.ref_equip_code) },
  { key: 'ref_ff_code', label: 'Ref FF Code', cluster: 'ref_outbound', defaultVisible: true,
    render: (r) => fmtText(r.ref_ff_code) },
  { key: 'ref_stops', label: 'Ref Stops', cluster: 'ref_outbound', defaultVisible: true, align: 'right',
    render: (r) => fmtInteger(r.ref_stops) },
  { key: 'ref_dep_time', label: 'Ref Dep Time', cluster: 'ref_outbound', defaultVisible: false,
    render: (r) => fmtText(r.ref_dep_time) },
  { key: 'ref_arr_time', label: 'Ref Arr Time', cluster: 'ref_outbound', defaultVisible: false,
    render: (r) => fmtText(r.ref_arr_time) },
  { key: 'ref_via', label: 'Ref Via', cluster: 'ref_outbound', defaultVisible: false,
    render: (r) => fmtText(r.ref_via) },
  { key: 'ref_cab_name', label: 'Ref Cabin Name', cluster: 'ref_outbound', defaultVisible: false,
    render: (r) => fmtText(r.ref_cab_name) },
  { key: 'ref_bkg_class', label: 'Ref Bkg Class', cluster: 'ref_outbound', defaultVisible: false,
    render: (r) => fmtText(r.ref_bkg_class) },
  { key: 'ref_yr', label: 'Ref YR', cluster: 'ref_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtFareRef(r, 'ref_yr') },
  { key: 'ref_anc_price', label: 'Ref Anc Price', cluster: 'ref_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtFareRef(r, 'ref_anc_price') },
  { key: 'ref_anc_type', label: 'Ref Anc Type', cluster: 'ref_outbound', defaultVisible: false,
    render: (r) => fmtText(r.ref_anc_type) },

  // ── reference flight return-leg (all in picker) ──
  { key: 'ref_ret_flt_num', label: 'Ref Ret Flt#', cluster: 'ref_return', defaultVisible: false,
    render: (r) => fmtText(r.ref_ret_flt_num) },
  { key: 'ref_ret_dep_date', label: 'Ref Ret Dep Date', cluster: 'ref_return', defaultVisible: false,
    render: (r) => fmtDate(r.ref_ret_dep_date) },
  { key: 'ref_ret_dep_time', label: 'Ref Ret Dep Time', cluster: 'ref_return', defaultVisible: false,
    render: (r) => fmtText(r.ref_ret_dep_time) },
  { key: 'ref_ret_arr_time', label: 'Ref Ret Arr Time', cluster: 'ref_return', defaultVisible: false,
    render: (r) => fmtText(r.ref_ret_arr_time) },
  { key: 'ref_ret_stops', label: 'Ref Ret Stops', cluster: 'ref_return', defaultVisible: false, align: 'right',
    render: (r) => fmtInteger(r.ref_ret_stops) },
  { key: 'ref_ret_via', label: 'Ref Ret Via', cluster: 'ref_return', defaultVisible: false,
    render: (r) => fmtText(r.ref_ret_via) },
  { key: 'ref_ret_cab_name', label: 'Ref Ret Cabin Name', cluster: 'ref_return', defaultVisible: false,
    render: (r) => fmtText(r.ref_ret_cab_name) },
  { key: 'ref_ret_cab_code', label: 'Ref Ret Cabin Code', cluster: 'ref_return', defaultVisible: false,
    render: (r) => fmtText(r.ref_ret_cab_code) },
  { key: 'ref_ret_bkg_class', label: 'Ref Ret Bkg Class', cluster: 'ref_return', defaultVisible: false,
    render: (r) => fmtText(r.ref_ret_bkg_class) },
  { key: 'ref_ret_seats', label: 'Ref Ret Seats', cluster: 'ref_return', defaultVisible: false, align: 'right',
    render: (r) => fmtInteger(r.ref_ret_seats) },
  { key: 'ref_ret_equip_code', label: 'Ref Ret Equipment', cluster: 'ref_return', defaultVisible: false,
    render: (r) => fmtText(r.ref_ret_equip_code) },

  // ── competitor outbound additions (default visible 2; rest in picker) ──
  { key: 'comp_equip_code', label: 'Comp Equipment', cluster: 'comp_outbound', defaultVisible: true,
    render: (r) => fmtText(r.comp_equip_code) },
  { key: 'comp_ff_code', label: 'Comp FF Code', cluster: 'comp_outbound', defaultVisible: true,
    render: (r) => fmtText(r.comp_ff_code) },
  { key: 'comp_dep_time', label: 'Comp Dep Time', cluster: 'comp_outbound', defaultVisible: false,
    render: (r) => fmtText(r.comp_dep_time) },
  { key: 'comp_arr_time', label: 'Comp Arr Time', cluster: 'comp_outbound', defaultVisible: false,
    render: (r) => fmtText(r.comp_arr_time) },
  { key: 'comp_stops', label: 'Comp Stops', cluster: 'comp_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtInteger(r.comp_stops) },
  { key: 'comp_via', label: 'Comp Via', cluster: 'comp_outbound', defaultVisible: false,
    render: (r) => fmtText(r.comp_via) },
  { key: 'comp_cab_name', label: 'Comp Cabin Name', cluster: 'comp_outbound', defaultVisible: false,
    render: (r) => fmtText(r.comp_cab_name) },
  { key: 'comp_bkg_class', label: 'Comp Bkg Class', cluster: 'comp_outbound', defaultVisible: false,
    render: (r) => fmtText(r.comp_bkg_class) },
  { key: 'comp_yr', label: 'Comp YR', cluster: 'comp_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtFareComp(r, 'comp_yr') },
  { key: 'comp_anc_price', label: 'Comp Anc Price', cluster: 'comp_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtFareComp(r, 'comp_anc_price') },
  { key: 'comp_anc_type', label: 'Comp Anc Type', cluster: 'comp_outbound', defaultVisible: false,
    render: (r) => fmtText(r.comp_anc_type) },

  // ── competitor return-leg (all in picker) ──
  { key: 'comp_ret_flt_num', label: 'Comp Ret Flt#', cluster: 'comp_return', defaultVisible: false,
    render: (r) => fmtText(r.comp_ret_flt_num) },
  { key: 'comp_ret_dep_date', label: 'Comp Ret Dep Date', cluster: 'comp_return', defaultVisible: false,
    render: (r) => fmtDate(r.comp_ret_dep_date) },
  { key: 'comp_ret_dep_time', label: 'Comp Ret Dep Time', cluster: 'comp_return', defaultVisible: false,
    render: (r) => fmtText(r.comp_ret_dep_time) },
  { key: 'comp_ret_arr_time', label: 'Comp Ret Arr Time', cluster: 'comp_return', defaultVisible: false,
    render: (r) => fmtText(r.comp_ret_arr_time) },
  { key: 'comp_ret_stops', label: 'Comp Ret Stops', cluster: 'comp_return', defaultVisible: false, align: 'right',
    render: (r) => fmtInteger(r.comp_ret_stops) },
  { key: 'comp_ret_via', label: 'Comp Ret Via', cluster: 'comp_return', defaultVisible: false,
    render: (r) => fmtText(r.comp_ret_via) },
  { key: 'comp_ret_cab_name', label: 'Comp Ret Cabin Name', cluster: 'comp_return', defaultVisible: false,
    render: (r) => fmtText(r.comp_ret_cab_name) },
  { key: 'comp_ret_cab_code', label: 'Comp Ret Cabin Code', cluster: 'comp_return', defaultVisible: false,
    render: (r) => fmtText(r.comp_ret_cab_code) },
  { key: 'comp_ret_bkg_class', label: 'Comp Ret Bkg Class', cluster: 'comp_return', defaultVisible: false,
    render: (r) => fmtText(r.comp_ret_bkg_class) },
  { key: 'comp_ret_seats', label: 'Comp Ret Seats', cluster: 'comp_return', defaultVisible: false, align: 'right',
    render: (r) => fmtInteger(r.comp_ret_seats) },
  { key: 'comp_ret_equip_code', label: 'Comp Ret Equipment', cluster: 'comp_return', defaultVisible: false,
    render: (r) => fmtText(r.comp_ret_equip_code) },

  // ── point-of-* (POS is core; poa/pod/poc in picker) ──
  { key: 'poa', label: 'POA', cluster: 'point_of', defaultVisible: false,
    render: (r) => fmtText(r.poa) },
  { key: 'pod', label: 'POD', cluster: 'point_of', defaultVisible: false,
    render: (r) => fmtText(r.pod) },
  { key: 'poc', label: 'POC', cluster: 'point_of', defaultVisible: false,
    render: (r) => fmtText(r.poc) },

  // ── provenance ──
  { key: 'path', label: 'Path', cluster: 'provenance', defaultVisible: false,
    render: (r) => fmtText(r.path) },

  // ── pre-existing dict columns not in default-16 (picker) ──
  { key: 'id', label: 'ID', cluster: 'core', defaultVisible: false,
    render: (r) => fmtCaption(r.id) },
  { key: 'cap_time', label: 'Cap Time', cluster: 'core', defaultVisible: false,
    render: (r) => fmtCaption(r.cap_time) },
  { key: 'ref_flt_num', label: 'Ref Flt#', cluster: 'ref_outbound', defaultVisible: false,
    render: (r) => fmtText(r.ref_flt_num) },
  { key: 'ref_base_fare', label: 'Ref Base Fare', cluster: 'ref_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtFareRef(r, 'ref_base_fare') },
  { key: 'ref_tax', label: 'Ref Tax', cluster: 'ref_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtFareRef(r, 'ref_tax') },
  { key: 'ref_yq', label: 'Ref YQ', cluster: 'ref_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtFareRef(r, 'ref_yq') },
  { key: 'ref_seats', label: 'Ref Seats', cluster: 'ref_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtInteger(r.ref_seats) },
  { key: 'ref_curr', label: 'Ref Currency', cluster: 'ref_outbound', defaultVisible: false,
    render: (r) => fmtText(r.ref_curr) },
  { key: 'comp_flt_num', label: 'Comp Flt#', cluster: 'comp_outbound', defaultVisible: false,
    render: (r) => fmtText(r.comp_flt_num) },
  { key: 'comp_org', label: 'Comp Org', cluster: 'comp_outbound', defaultVisible: false,
    render: (r) => fmtText(r.comp_org) },
  { key: 'comp_dst', label: 'Comp Dst', cluster: 'comp_outbound', defaultVisible: false,
    render: (r) => fmtText(r.comp_dst) },
  { key: 'comp_dep_date', label: 'Comp Dep Date', cluster: 'comp_outbound', defaultVisible: false,
    render: (r) => fmtCaption(r.comp_dep_date) },
  { key: 'comp_cab_code', label: 'Comp Cabin Code', cluster: 'comp_outbound', defaultVisible: false,
    render: (r) => fmtText(r.comp_cab_code) },
  { key: 'comp_base_fare', label: 'Comp Base Fare', cluster: 'comp_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtFareComp(r, 'comp_base_fare') },
  { key: 'comp_tax', label: 'Comp Tax', cluster: 'comp_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtFareComp(r, 'comp_tax') },
  { key: 'comp_yq', label: 'Comp YQ', cluster: 'comp_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtFareComp(r, 'comp_yq') },
  { key: 'comp_seats', label: 'Comp Seats', cluster: 'comp_outbound', defaultVisible: false, align: 'right',
    render: (r) => fmtInteger(r.comp_seats) },
  { key: 'comp_curr', label: 'Comp Currency', cluster: 'comp_outbound', defaultVisible: false,
    render: (r) => fmtText(r.comp_curr) },
];

const DEFAULT_VISIBLE = new Set(COLUMNS.filter(c => c.defaultVisible).map(c => c.key));

export default function AirlineCpiPricingTab({ tenantCode, filters, onFiltersChange }: AirlineCpiPricingTabProps) {
  const [filterOpen, setFilterOpen] = useState(true);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Paginated<AirlineSnapshot> | null>(null);
  const [meta, setMeta] = useState<FilterMetadata[]>([]);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(20);

  // Column-picker state
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(new Set(DEFAULT_VISIBLE));
  const [colMenuAnchor, setColMenuAnchor] = useState<HTMLElement | null>(null);

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

  const displayedFields = allFields
    .filter(f => f.key === 'file_date')
    .map(f => ({ ...f, required: true }));

  const toggleColumn = (key: string) => {
    setVisibleColumns(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const resetColumns = () => setVisibleColumns(new Set(DEFAULT_VISIBLE));

  // Visible columns in their declared order
  const renderedColumns = useMemo(
    () => COLUMNS.filter(c => visibleColumns.has(c.key)),
    [visibleColumns],
  );

  // Picker entries grouped by cluster (in cluster declaration order)
  const pickerByCluster = useMemo(() => {
    const groups: Record<ColumnCluster, ColumnDef[]> = {
      core: [], ref_outbound: [], ref_return: [], comp_outbound: [],
      comp_return: [], point_of: [], provenance: [],
    };
    for (const col of COLUMNS) groups[col.cluster].push(col);
    return groups;
  }, []);

  const orderedClusters: ColumnCluster[] = [
    'core', 'ref_outbound', 'ref_return', 'comp_outbound', 'comp_return', 'point_of', 'provenance',
  ];

  return (
    <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <ActionBar onExport={() => api.airline.exportSnapshots({ ...filters, tenant: tenantCode })}>
        <Button
          size="small"
          startIcon={<ViewColumn />}
          onClick={(e) => setColMenuAnchor(e.currentTarget)}
          aria-haspopup="true"
          aria-expanded={Boolean(colMenuAnchor)}
        >
          Columns ({renderedColumns.length})
        </Button>
        <Menu
          anchorEl={colMenuAnchor}
          open={Boolean(colMenuAnchor)}
          onClose={() => setColMenuAnchor(null)}
          slotProps={{ paper: { sx: { maxHeight: 480, minWidth: 280 } } }}
        >
          <MenuItem dense onClick={resetColumns}>
            <ListItemText primary="Reset to defaults (16)" />
          </MenuItem>
          <Divider />
          {orderedClusters.map(cluster => (
            <MenuList key={cluster} dense subheader={
              <ListSubheader sx={{ lineHeight: '32px' }}>{CLUSTER_LABELS[cluster]}</ListSubheader>
            }>
              {pickerByCluster[cluster].map(col => (
                <MenuItem key={col.key} dense onClick={() => toggleColumn(col.key)}>
                  <Checkbox edge="start" size="small" checked={visibleColumns.has(col.key)} tabIndex={-1} disableRipple />
                  <ListItemText primary={col.label} />
                </MenuItem>
              ))}
            </MenuList>
          ))}
        </Menu>
      </ActionBar>

      <Box sx={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <FilterPanel
          title={`${tenantCode} Pricing Filters`}
          fields={displayedFields}
          open={filterOpen}
          onToggle={() => setFilterOpen(!filterOpen)}
          values={filters}
          onValuesChange={onFiltersChange}
          onApply={handleApply}
          onReset={handleReset}
        />

        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, minHeight: 0, p: 2 }}>
          {loading ? (
            <Box sx={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}><CircularProgress /></Box>
          ) : !data || data.items.length === 0 ? (
            <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <EmptyState icon={<Flight sx={{ fontSize: 64 }} />} title={`No ${tenantCode} Data`} description={`Apply filters to search ${tenantCode} airline CPI snapshots.`} actionLabel="Load All" onAction={() => fetchData({}, 0)} />
            </Box>
          ) : (
            <>
              <TableContainer component={Paper} variant="outlined" sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
                <Table size="small" stickyHeader aria-label={`${tenantCode} Airline CPI snapshots`}>
                  <TableHead>
                    <TableRow>
                      {renderedColumns.map(col => (
                        <TableCell key={col.key} align={col.align ?? 'left'}>{col.label}</TableCell>
                      ))}
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {data.items.map(row => (
                      <TableRow key={row.id} hover>
                        {renderedColumns.map(col => (
                          <TableCell key={col.key} align={col.align ?? 'left'}>
                            {col.render ? col.render(row) : null}
                          </TableCell>
                        ))}
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
