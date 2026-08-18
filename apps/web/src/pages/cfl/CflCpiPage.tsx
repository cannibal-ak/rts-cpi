import { useState, useEffect, useCallback, useMemo, useRef, type ReactNode } from 'react';
import {
  Box, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  CircularProgress, Button, Collapse, Chip, IconButton, Autocomplete, TextField,
  FormControl, Select, MenuItem, Stack, Divider, Tooltip, Breadcrumbs, Link,
  Tabs, Tab,
} from '@mui/material';
import {
  DirectionsBoat, KeyboardArrowDown, KeyboardArrowUp, RestartAlt, CalendarToday,
  ChevronLeft, ChevronRight, FirstPage, LastPage, NavigateNext, FileDownload,
} from '@mui/icons-material';
import EmptyState from '../../components/common/EmptyState';
import { api } from '../../api';
import { fetchAllPagesCached } from '../../api/datasetCache';
import { isAbortError } from '../../api/httpClient';
import type { CflSnapshot, FilterMetadata, DataFreshness } from '../../types';

interface CflCpiPageProps {
  tenantCode: 'FJL';
}

// ── Formatters ──────────────────────────────────────────────────────────
const DASH = '—';
const isEmpty = (v: unknown) => v == null || v === '';
const fmtText = (v: unknown): string => isEmpty(v) ? DASH : String(v);
const fmtCurrency = (v: unknown): string => {
  if (isEmpty(v)) return DASH;
  const n = Number(v);
  return Number.isNaN(n) ? String(v) : n.toFixed(2);
};
const fmtDate = (v: unknown): string => {
  if (isEmpty(v)) return DASH;
  const s = String(v);
  return s.length >= 10 ? s.substring(0, 10) : s;
};
const fmtTime = (v: unknown): string => {
  if (isEmpty(v)) return DASH;
  const s = String(v);
  return s.length >= 5 ? s.substring(0, 5) : s;
};

// ── Operator URL cleanup ────────────────────────────────────────────────
// "https://www.colorline.no/"     → "colorline.no"
// "https://www.fjordline.com/nb"  → "fjordline.com/nb"
function cleanOperator(url: string | null | undefined): string {
  if (!url) return '';
  return url.replace(/^https?:\/\/(www\.)?/, '').replace(/\/+$/, '');
}

// ── Trip-type normalisation ─────────────────────────────────────────────
// DB values: 'One-way' | 'CRUISE' | 'Cruise'  → 'OW' | 'Cr'
function tripBucket(t: string | null | undefined): 'OW' | 'Cr' | '' {
  if (!t) return '';
  if (t === 'One-way') return 'OW';
  if (t === 'CRUISE' || t === 'Cruise') return 'Cr';
  return '';
}

// ── Summary columns (compact labels + fixed widths) ─────────────────────
interface SummaryColumn {
  label: string;
  align?: 'left' | 'right';
  width: number;
  render: (row: CflSnapshot) => ReactNode;
}

const SUMMARY_COLUMNS: SummaryColumn[] = [
  { label: 'Org',       align: 'left',  width: 100, render: r => fmtText(r.org) },
  { label: 'Dst',       align: 'left',  width: 100, render: r => fmtText(r.dest) },
  { label: 'Trip',      align: 'left',  width: 44,  render: r => {
      const b = tripBucket(r.trip_type);
      return b
        ? <Chip label={b} size="small" variant="outlined"
                sx={{ height: 16, fontSize: 10, '& .MuiChip-label': { px: 0.5 } }} />
        : DASH;
  }},
  { label: 'Operator',  align: 'left',  width: 130, render: r => {
      const clean = cleanOperator(r.source);
      return (
        <Tooltip title={r.source || ''}>
          <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', display: 'block' }}>
            {clean || DASH}
          </Box>
        </Tooltip>
      );
  }},
  { label: 'Product',   align: 'left',  width: 64,  render: r => r.prod_family
      ? <Chip label={r.prod_family} size="small"
              sx={{ height: 16, fontSize: 10, '& .MuiChip-label': { px: 0.5 } }} />
      : DASH },
  { label: 'Equipment', align: 'left',  width: 130, render: r => (
      <Tooltip title={r.out_equip_name || ''}>
        <Box component="span" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', display: 'block' }}>
          {fmtText(r.out_equip_name)}
        </Box>
      </Tooltip>
  )},
  { label: 'Cab',       align: 'left',  width: 64,  render: r => fmtText(r.out_cab_type) },
  { label: 'Dep',       align: 'left',  width: 84,  render: r => fmtDate(r.out_dep_date) },
  { label: 'Time',      align: 'left',  width: 50,  render: r => fmtTime(r.out_dep_time) },
  { label: 'Pax fare',  align: 'right', width: 72,  render: r => (
      <Box component="span" sx={{ fontFamily: 'monospace', fontSize: 11 }}>{fmtCurrency(r.out_per_pax_fare)}</Box>
  )},
  { label: 'Veh fare',  align: 'right', width: 72,  render: r => (
      <Box component="span" sx={{ fontFamily: 'monospace', fontSize: 11 }}>{fmtCurrency(r.out_veh_fare)}</Box>
  )},
  { label: 'Total',     align: 'right', width: 76,  render: r => (
      <Box component="span" sx={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 600 }}>{fmtCurrency(r.total_fare)}</Box>
  )},
  { label: 'Cur',       align: 'left',  width: 44,  render: r => fmtText(r.curr_code) },
  { label: 'Avail',     align: 'left',  width: 52,  render: r => {
      if (!r.out_avail) return DASH;
      const color = r.out_avail === 'O' ? 'success' : r.out_avail === 'C' ? 'error' : 'default';
      return <Chip label={r.out_avail} size="small" color={color} variant="outlined"
                   sx={{ height: 16, fontSize: 10, '& .MuiChip-label': { px: 0.5 } }} />;
  }},
];

const CHEVRON_COL_WIDTH = 28;

// ── Detail-panel groups ─────────────────────────────────────────────────
type DetailFieldType = 'text' | 'currency' | 'date' | 'time';
interface DetailField {
  key: keyof CflSnapshot;
  label: string;
  type?: DetailFieldType;
}
interface DetailGroup {
  title: string;
  faded?: boolean;
  fields: DetailField[];
}

const DETAIL_GROUPS: DetailGroup[] = [
  {
    title: 'Outbound schedule',
    fields: [
      { key: 'out_dep_date', label: 'Dep Date', type: 'date' },
      { key: 'out_dep_time', label: 'Dep Time', type: 'time' },
      { key: 'out_arr_date', label: 'Arr Date', type: 'date' },
      { key: 'out_arr_time', label: 'Arr Time', type: 'time' },
      { key: 'duration',     label: 'Duration (min)' },
    ],
  },
  {
    title: 'Outbound product',
    fields: [
      { key: 'out_equip_name', label: 'Equipment' },
      { key: 'prod_family',    label: 'Product Family' },
      { key: 'out_cab_type',   label: 'Cabin Type' },
      { key: 'out_cabin_desc', label: 'Cabin Desc' },
      { key: 'out_seat_type',  label: 'Seat Type' },
      { key: 'veh_size',       label: 'Vehicle Size' },
    ],
  },
  {
    title: 'Outbound fares',
    fields: [
      { key: 'total_fare',       label: 'Total Fare',   type: 'currency' },
      { key: 'out_per_pax_fare', label: 'Pax Fare',     type: 'currency' },
      { key: 'out_veh_fare',     label: 'Vehicle Fare', type: 'currency' },
      { key: 'out_cab_fare',     label: 'Cabin Fare',   type: 'currency' },
      { key: 'out_seat_fare',    label: 'Seat Fare',    type: 'currency' },
      { key: 'out_taxes',        label: 'Taxes',        type: 'currency' },
      { key: 'curr_code',        label: 'Currency' },
      { key: 'out_num_pax',      label: 'Num Pax' },
      { key: 'out_num_cabs',     label: 'Num Cabins' },
      { key: 'out_num_seats',    label: 'Num Seats' },
    ],
  },
  {
    title: 'Return schedule',
    faded: true,
    fields: [
      { key: 'ret_dep_date', label: 'Dep Date', type: 'date' },
      { key: 'ret_dep_time', label: 'Dep Time', type: 'time' },
      { key: 'ret_arr_date', label: 'Arr Date', type: 'date' },
      { key: 'ret_arr_time', label: 'Arr Time', type: 'time' },
    ],
  },
  {
    title: 'Return product',
    faded: true,
    fields: [
      { key: 'ret_equip_name', label: 'Equipment' },
      { key: 'ret_cab_type',   label: 'Cabin Type' },
      { key: 'ret_cab_desc',   label: 'Cabin Desc' },
      { key: 'ret_seat_type',  label: 'Seat Type' },
      { key: 'ret_avail',      label: 'Availability' },
    ],
  },
  {
    title: 'Return fares',
    faded: true,
    fields: [
      { key: 'ret_per_pax_fare', label: 'Pax Fare',     type: 'currency' },
      { key: 'ret_veh_fare',     label: 'Vehicle Fare', type: 'currency' },
      { key: 'ret_cab_fare',     label: 'Cabin Fare',   type: 'currency' },
      { key: 'ret_seat_fare',    label: 'Seat Fare',    type: 'currency' },
      { key: 'ret_taxes',        label: 'Taxes',        type: 'currency' },
      { key: 'ret_num_pax',      label: 'Num Pax' },
      { key: 'ret_num_cabs',     label: 'Num Cabins' },
      { key: 'ret_num_seats',    label: 'Num Seats' },
    ],
  },
  {
    title: 'Combined totals',
    faded: true,
    fields: [
      { key: 'tot_per_pax_fare', label: 'Pax Fare',     type: 'currency' },
      { key: 'tot_veh_fare',     label: 'Vehicle Fare', type: 'currency' },
      { key: 'tot_cab_fare',     label: 'Cabin Fare',   type: 'currency' },
      { key: 'tot_seat_fare',    label: 'Seat Fare',    type: 'currency' },
      { key: 'tot_taxes',        label: 'Taxes',        type: 'currency' },
      { key: 'tot_num_pax',      label: 'Num Pax' },
      { key: 'tot_num_cabs',     label: 'Num Cabins' },
      { key: 'tot_num_seats',    label: 'Num Seats' },
    ],
  },
  {
    title: 'Capture metadata',
    faded: true,
    fields: [
      { key: 'cap_date', label: 'Capture Date', type: 'date' },
      { key: 'cap_time', label: 'Capture Time', type: 'time' },
    ],
  },
];

function renderDetailValue(row: CflSnapshot, field: DetailField): string {
  const v = row[field.key];
  switch (field.type) {
    case 'currency': return fmtCurrency(v);
    case 'date':     return fmtDate(v);
    case 'time':     return fmtTime(v);
    default:         return fmtText(v);
  }
}

// ── Export columns (data-dictionary headers) ────────────────────────────
const EXPORT_COLUMNS: Array<{ header: string; key: keyof CflSnapshot }> = [
  { header: 'CapDate',        key: 'cap_date' },
  { header: 'CapTime',        key: 'cap_time' },
  { header: 'TripType',       key: 'trip_type' },
  { header: 'Source',         key: 'source' },
  { header: 'Org',            key: 'org' },
  { header: 'Dest',           key: 'dest' },
  { header: 'OutDepDate',     key: 'out_dep_date' },
  { header: 'OutDepTime',     key: 'out_dep_time' },
  { header: 'OutArrDate',     key: 'out_arr_date' },
  { header: 'OutArrTime',     key: 'out_arr_time' },
  { header: 'ProdFamily',     key: 'prod_family' },
  { header: 'OutEquipName',   key: 'out_equip_name' },
  { header: 'OutCabType',     key: 'out_cab_type' },
  { header: 'OutCabinDesc',   key: 'out_cabin_desc' },
  { header: 'OutSeatType',    key: 'out_seat_type' },
  { header: 'OutNumCabs',     key: 'out_num_cabs' },
  { header: 'OutSeatFare',    key: 'out_seat_fare' },
  { header: 'OutNumSeats',    key: 'out_num_seats' },
  { header: 'TotalFare',      key: 'total_fare' },
  { header: 'OutPerPaxFare',  key: 'out_per_pax_fare' },
  { header: 'OutVehFare',     key: 'out_veh_fare' },
  { header: 'OutCabFare',     key: 'out_cab_fare' },
  { header: 'OutTaxes',       key: 'out_taxes' },
  { header: 'OutNumPax',      key: 'out_num_pax' },
  { header: 'VehSize',        key: 'veh_size' },
  { header: 'CurrCode',       key: 'curr_code' },
  { header: 'OutAvail',       key: 'out_avail' },
  { header: 'RetDepDate',     key: 'ret_dep_date' },
  { header: 'RetDepTime',     key: 'ret_dep_time' },
  { header: 'RetArrDate',     key: 'ret_arr_date' },
  { header: 'RetArrTime',     key: 'ret_arr_time' },
  { header: 'RetEquipName',   key: 'ret_equip_name' },
  { header: 'RetCabType',     key: 'ret_cab_type' },
  { header: 'RetCabDesc',     key: 'ret_cab_desc' },
  { header: 'RetSeatType',    key: 'ret_seat_type' },
  { header: 'RetAvail',       key: 'ret_avail' },
  { header: 'RetPerPaxFare',  key: 'ret_per_pax_fare' },
  { header: 'RetNumPax',      key: 'ret_num_pax' },
  { header: 'RetVehFare',     key: 'ret_veh_fare' },
  { header: 'RetCabFare',     key: 'ret_cab_fare' },
  { header: 'RetNumCabs',     key: 'ret_num_cabs' },
  { header: 'RetSeatFare',    key: 'ret_seat_fare' },
  { header: 'RetNumSeats',    key: 'ret_num_seats' },
  { header: 'RetTaxes',       key: 'ret_taxes' },
  { header: 'TotPerPaxFare',  key: 'tot_per_pax_fare' },
  { header: 'TotNumPax',      key: 'tot_num_pax' },
  { header: 'TotVehFare',     key: 'tot_veh_fare' },
  { header: 'TotCabFare',     key: 'tot_cab_fare' },
  { header: 'TotNumCabs',     key: 'tot_num_cabs' },
  { header: 'TotSeatFare',    key: 'tot_seat_fare' },
  { header: 'TotNumSeats',    key: 'tot_num_seats' },
  { header: 'TotTaxes',       key: 'tot_taxes' },
  { header: 'Duration',       key: 'duration' },
];

// ── Page walker (load all rows for selected file_date) ──────────────────
// Shared with the pricing and velocity grids — see api/fetchAllPages.ts.
// Wrapped in the session cache (api/datasetCache.ts): repeat views are served
// from memory after a 50-row freshness probe instead of re-walking every page.
function fetchAllRows(
  baseQuery: Record<string, string>,
  tenantCode: 'FJL',
  onProgress?: (loaded: number, total: number) => void,
  signal?: AbortSignal,
): Promise<CflSnapshot[]> {
  return fetchAllPagesCached<CflSnapshot>({
    key: { endpoint: '/api/v1/cfl/snapshots', tenant: tenantCode, query: baseQuery },
    fetchPage: (page, pageSize, sig, withTotal) => api.cfl.listSnapshots(
      {
        ...baseQuery, tenant: tenantCode, page, page_size: pageSize,
        with_total: withTotal === false ? 'false' : 'true',
      },
      { signal: sig },
    ),
    onProgress,
    signal,
  });
}

// ── CSV helpers ─────────────────────────────────────────────────────────
function csvEscape(v: unknown): string {
  if (v == null) return '';
  const s = String(v);
  if (s.includes(',') || s.includes('"') || s.includes('\n') || s.includes('\r')) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ────────────────────────────────────────────────────────────────────────
export default function CflCpiPage({ tenantCode }: CflCpiPageProps) {
  const pageTitle = `Cruise/Ferry CPI – ${tenantCode}`;

  const [filters, setFilters] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ loaded: number; total: number } | null>(null);
  const [allData, setAllData] = useState<CflSnapshot[]>([]);
  const [meta, setMeta] = useState<FilterMetadata[]>([]);
  const [freshness, setFreshness] = useState<DataFreshness | null>(null);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(30);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Client-side filters (operate on already-loaded `allData`)
  const [routes, setRoutes] = useState<string[]>([]);
  const [operators, setOperators] = useState<string[]>([]);
  const [tripFilter, setTripFilter] = useState<'all' | 'OW' | 'Cr'>('all');
  const [products, setProducts] = useState<string[]>([]);
  const [equipment, setEquipment] = useState<string[]>([]);
  const [cabins, setCabins] = useState<string[]>([]);
  const [currencies, setCurrencies] = useState<string[]>([]);
  const [availFilter, setAvailFilter] = useState<'all' | 'O' | 'C'>('all');
  const [depFrom, setDepFrom] = useState<string>('');
  const [depTo, setDepTo] = useState<string>('');

  // ── Load filter metadata + freshness once ───────────────────────────
  useEffect(() => {
    api.cfl.getFilterMetadata(tenantCode).then(setMeta);
    api.stats.getFreshnessMetrics().then(data => {
      const cfl = data.find(d => d.domain === 'Cruise/Ferry CPI' || d.domain === `Cruise/Ferry CPI – ${tenantCode}`);
      if (cfl) setFreshness(cfl);
    });
  }, [tenantCode]);

  // ── Data fetcher (walks all pages for the chosen file_date) ─────────
  // Holds the controller for the load currently in flight, so a new load — or
  // unmounting — cancels the old one instead of letting it run to completion
  // and overwrite fresher results.
  const abortRef = useRef<AbortController | null>(null);

  const fetchData = useCallback(async (q: Record<string, string>) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setProgress(null);
    setExpandedId(null);
    try {
      const rows = await fetchAllRows(q, tenantCode, (loaded, total) => {
        if (!ctrl.signal.aborted) setProgress({ loaded, total });
      }, ctrl.signal);
      if (ctrl.signal.aborted) return;
      setAllData(rows);
    } catch (err) {
      // A superseded or cancelled load is not a failure — leave the existing
      // rows alone and let the newer load own the state.
      if (ctrl.signal.aborted || isAbortError(err)) return;
      console.error('Failed to load CFL snapshots:', err);
      setAllData([]);
    } finally {
      if (!ctrl.signal.aborted) {
        setLoading(false);
        setProgress(null);
      }
    }
  }, [tenantCode]);

  // Cancel any in-flight load when the page unmounts, so navigating away
  // doesn't leave an abandoned load still fetching.
  //
  // Safe under React StrictMode, which in dev mounts, cleans up, then mounts
  // again: at that synthetic cleanup `abortRef.current` is still null, because
  // a load can only start from the `[meta]` effect below and `meta` is filled
  // by an async request that cannot resolve inside the mount commit. If a
  // future change ever starts a load synchronously on mount, revisit this —
  // it would cancel that first load and never restart it.
  useEffect(() => () => abortRef.current?.abort(), []);

  // ── Default filter wiring (file_date = latest) ──────────────────────
  useEffect(() => {
    if (meta.length === 0) return;
    if (Object.keys(filters).length === 0) {
      const defaults: Record<string, string> = {};
      const fdMeta = meta.find(m => m.field === 'file_date');
      if (fdMeta && fdMeta.values.length > 0 && fdMeta.values[0] !== 'No file dates available') {
        defaults.file_date = fdMeta.values[0];
      }
      if (Object.keys(defaults).length > 0) {
        setFilters(defaults);
        fetchData(defaults);
        return;
      }
    }
    fetchData(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta]);

  // ── Reset page on any client filter change ──────────────────────────
  useEffect(() => {
    setPage(0);
    setExpandedId(null);
  }, [routes, operators, tripFilter, products, equipment, cabins, currencies, availFilter, depFrom, depTo]);

  // ── Derived option lists from loaded data ───────────────────────────
  const routeOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) {
      if (r.org && r.dest) set.add(`${r.org}–${r.dest}`);
    }
    return Array.from(set).sort();
  }, [allData]);

  const operatorOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) {
      const c = cleanOperator(r.source);
      if (c) set.add(c);
    }
    return Array.from(set).sort();
  }, [allData]);

  const productOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) if (r.prod_family) set.add(r.prod_family);
    return Array.from(set).sort();
  }, [allData]);

  const equipmentOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) if (r.out_equip_name) set.add(r.out_equip_name);
    return Array.from(set).sort();
  }, [allData]);

  const cabinOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) {
      if (r.out_cab_type && r.out_cab_type !== 'none') set.add(r.out_cab_type);
    }
    return Array.from(set).sort();
  }, [allData]);

  const currencyOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) if (r.curr_code) set.add(r.curr_code);
    return Array.from(set).sort();
  }, [allData]);

  // ── File-date options (from metadata) ───────────────────────────────
  const fileDateOptions = useMemo(() => {
    const fdMeta = meta.find(m => m.field === 'file_date');
    if (!fdMeta || fdMeta.values[0] === 'No file dates available') return [];
    return fdMeta.values;
  }, [meta]);

  // ── Filtered view ───────────────────────────────────────────────────
  const filteredData = useMemo(() => {
    return allData.filter(r => {
      if (routes.length > 0 && !routes.includes(`${r.org}–${r.dest}`)) return false;
      if (operators.length > 0 && !operators.includes(cleanOperator(r.source))) return false;
      if (tripFilter !== 'all' && tripBucket(r.trip_type) !== tripFilter) return false;
      if (products.length > 0 && !products.includes(r.prod_family)) return false;
      if (equipment.length > 0 && !equipment.includes(r.out_equip_name)) return false;
      if (cabins.length > 0 && !cabins.includes(r.out_cab_type)) return false;
      if (currencies.length > 0 && !currencies.includes(r.curr_code)) return false;
      if (availFilter !== 'all' && r.out_avail !== availFilter) return false;
      if (depFrom && (!r.out_dep_date || r.out_dep_date < depFrom)) return false;
      if (depTo && (!r.out_dep_date || r.out_dep_date > depTo)) return false;
      return true;
    });
  }, [allData, routes, operators, tripFilter, products, equipment, cabins, currencies, availFilter, depFrom, depTo]);

  const totalPages = Math.max(1, Math.ceil(filteredData.length / rowsPerPage));
  const safePage = Math.min(page, totalPages - 1);
  const pagedData = useMemo(() => {
    return filteredData.slice(safePage * rowsPerPage, (safePage + 1) * rowsPerPage);
  }, [filteredData, safePage, rowsPerPage]);

  const hasClientFilters =
    routes.length > 0 || operators.length > 0 || tripFilter !== 'all' ||
    products.length > 0 || equipment.length > 0 || cabins.length > 0 ||
    currencies.length > 0 || availFilter !== 'all' || depFrom !== '' || depTo !== '';

  // ── Handlers ────────────────────────────────────────────────────────
  const handleFileDateChange = (v: string) => {
    const next: Record<string, string> = { ...filters, file_date: v };
    setFilters(next);
    setPage(0);
    fetchData(next);
  };

  const handleResetClientFilters = () => {
    setRoutes([]);
    setOperators([]);
    setTripFilter('all');
    setProducts([]);
    setEquipment([]);
    setCabins([]);
    setCurrencies([]);
    setAvailFilter('all');
    setDepFrom('');
    setDepTo('');
  };

  const handleRowToggle = (id: string) => {
    setExpandedId(prev => (prev === id ? null : id));
  };

  // ── Export (CSV) ────────────────────────────────────────────────────
  const handleExportCsv = useCallback(() => {
    if (filteredData.length === 0) return;
    const headers = EXPORT_COLUMNS.map(c => c.header);
    const lines: string[] = [headers.join(',')];
    for (const row of filteredData) {
      lines.push(EXPORT_COLUMNS.map(c => csvEscape(row[c.key])).join(','));
    }
    const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const fileDate = filters.file_date || new Date().toISOString().slice(0, 10);
    downloadBlob(blob, `FJL_CPI_Pricing_${fileDate}.csv`);
  }, [filteredData, filters.file_date]);

  // ── Render ──────────────────────────────────────────────────────────
  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* ── Header bar (breadcrumb + export + freshness) ─────────────── */}
      {/* ── Row 1 — Header bar (breadcrumb + freshness dot) ─────────── */}
      <Box sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 1,
        height: 32,
        minHeight: 32,
        px: 2,
        flexShrink: 0,
      }}>
        <Breadcrumbs separator={<NavigateNext sx={{ fontSize: 14 }} />}>
          <Link underline="hover" color="inherit" href="/" sx={{ fontSize: 12 }}>Home</Link>
          <Typography color="text.primary" sx={{ fontSize: 12, fontWeight: 500 }}>{pageTitle}</Typography>
        </Breadcrumbs>
        {freshness && <FreshnessBadge data={freshness} />}
      </Box>

      {/* ── Row 2 — Tab label + Export (single thin toolbar) ──────────
          FJL has no velocity data, so the "Pricing" tab is a single
          non-clickable label rendered with the same MUI Tabs styling
          as the JY/PW pages, for visual consistency. */}
      <Box sx={{
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'space-between',
        gap: 1,
        borderBottom: 1,
        borderColor: 'divider',
        minHeight: 32,
        height: 32,
        px: 2,
        flexShrink: 0,
      }}>
        <Tabs
          value={0}
          aria-label={`${tenantCode} data tabs`}
          sx={{
            minHeight: 32,
            '& .MuiTabs-flexContainer': { gap: 0 },
            '& .MuiTab-root': {
              minHeight: 32,
              py: 0.25,
              px: 1.5,
              fontSize: 12,
              fontWeight: 500,
              textTransform: 'none',
            },
            '& .MuiTabs-indicator': { height: 2 },
          }}
        >
          <Tab label="Pricing" />
        </Tabs>
        <Tooltip title={`Download filtered rows as CSV (${EXPORT_COLUMNS.length} dictionary-named columns)`}>
          <span>
            <Button
              size="small"
              startIcon={<FileDownload sx={{ fontSize: 14 }} />}
              onClick={handleExportCsv}
              disabled={filteredData.length === 0}
              sx={{
                fontSize: 11.5,
                textTransform: 'none',
                minHeight: 26,
                py: 0.25,
                px: 1,
                mb: 0.25,
              }}
            >
              Export
            </Button>
          </span>
        </Tooltip>
      </Box>

      {/* ── Inline filter strip ──────────────────────────────────────── */}
      <Box sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 0.75,
        flexWrap: 'wrap',
        rowGap: 0.75,
        px: 2,
        py: 0.5,
        borderBottom: 1,
        borderColor: 'divider',
        bgcolor: 'background.paper',
        flexShrink: 0,
      }}>
        {/* File Date — server-side */}
        <CompactSingleSelect
          icon={<CalendarToday sx={{ fontSize: 12, color: 'text.secondary' }} />}
          label="Date"
          value={filters.file_date || ''}
          options={fileDateOptions.map(d => ({ value: d, label: d }))}
          onChange={handleFileDateChange}
          minWidth={150}
          disabled={loading || fileDateOptions.length === 0}
        />
        <Divider orientation="vertical" flexItem sx={{ mx: 0.5, my: 0.5 }} />

        {/* Client-side filters */}
        <CompactMultiSelect label="Route"     value={routes}     onChange={setRoutes}     options={routeOptions} />
        <CompactMultiSelect label="Operator"  value={operators}  onChange={setOperators}  options={operatorOptions} />
        <CompactSingleSelect label="Trip"
          value={tripFilter}
          options={[
            { value: 'all', label: 'All' },
            { value: 'OW',  label: 'OW' },
            { value: 'Cr',  label: 'Cr' },
          ]}
          onChange={(v) => setTripFilter(v as 'all' | 'OW' | 'Cr')}
          minWidth={80}
        />
        <CompactMultiSelect label="Product"   value={products}   onChange={setProducts}   options={productOptions} />
        <CompactMultiSelect label="Equipment" value={equipment}  onChange={setEquipment}  options={equipmentOptions} />
        <CompactMultiSelect label="Cab"       value={cabins}     onChange={setCabins}     options={cabinOptions} />
        <CompactMultiSelect label="Cur"       value={currencies} onChange={setCurrencies} options={currencyOptions} />
        <CompactSingleSelect label="Avail"
          value={availFilter}
          options={[
            { value: 'all', label: 'All' },
            { value: 'O',   label: 'O' },
            { value: 'C',   label: 'C' },
          ]}
          onChange={(v) => setAvailFilter(v as 'all' | 'O' | 'C')}
          minWidth={80}
        />
        <CompactDateInput label="Dep from" value={depFrom} onChange={setDepFrom} />
        <CompactDateInput label="Dep to"   value={depTo}   onChange={setDepTo} />

        <Box sx={{ flexGrow: 1 }} />

        <Typography sx={{ fontSize: 11, color: 'text.secondary', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
          {loading && progress
            ? `Loading ${progress.loaded.toLocaleString()} / ${progress.total.toLocaleString()}`
            : hasClientFilters
              ? `${filteredData.length.toLocaleString()} of ${allData.length.toLocaleString()} rows`
              : `${allData.length.toLocaleString()} rows`}
        </Typography>
        <Button
          size="small"
          startIcon={<RestartAlt sx={{ fontSize: 13 }} />}
          onClick={handleResetClientFilters}
          disabled={!hasClientFilters}
          sx={{ fontSize: 11, textTransform: 'none', minHeight: 26, py: 0.25, px: 0.75 }}
        >
          Reset
        </Button>
      </Box>

      {/* ── Table area ───────────────────────────────────────────────── */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {loading && allData.length === 0 ? (
          <Box sx={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <CircularProgress size={28} />
          </Box>
        ) : allData.length === 0 ? (
          <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <EmptyState
              icon={<DirectionsBoat sx={{ fontSize: 48 }} />}
              title="No CFL Data"
              description="Pick a file date to load FJL cruise/ferry snapshots."
            />
          </Box>
        ) : (
          <>
            <TableContainer sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
              <Table size="small" stickyHeader aria-label="FJL Cruise/Ferry CPI snapshots" sx={{ tableLayout: 'fixed' }}>
                <colgroup>
                  <col style={{ width: CHEVRON_COL_WIDTH }} />
                  {SUMMARY_COLUMNS.map(c => <col key={c.label} style={{ width: c.width }} />)}
                </colgroup>
                <TableHead>
                  <TableRow sx={{
                    '& > th': {
                      py: 0.5,
                      px: 0.75,
                      fontSize: 11,
                      fontWeight: 600,
                      lineHeight: 1.2,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      bgcolor: 'background.paper',
                      borderBottom: '1px solid',
                      borderColor: 'divider',
                    },
                  }}>
                    <TableCell aria-label="Expand row" />
                    {SUMMARY_COLUMNS.map(col => (
                      <TableCell key={col.label} align={col.align ?? 'left'}>
                        {col.label}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {pagedData.map(row => (
                    <CflRow
                      key={row.id}
                      row={row}
                      expanded={expandedId === row.id}
                      onToggle={() => handleRowToggle(row.id)}
                    />
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            {/* ── Compact pagination ───────────────────────────────── */}
            <Box sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: 1,
              px: 2,
              py: 0.5,
              borderTop: 1,
              borderColor: 'divider',
              minHeight: 32,
              flexShrink: 0,
            }}>
              <Typography sx={{ fontSize: 11, color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}>
                Page {safePage + 1} of {totalPages.toLocaleString()}
              </Typography>
              <FormControl size="small">
                <Select
                  value={rowsPerPage}
                  onChange={(e) => { setRowsPerPage(Number(e.target.value)); setPage(0); }}
                  sx={{
                    fontSize: 11,
                    height: 24,
                    '& .MuiSelect-select': { py: 0, pl: 1, pr: '24px !important' },
                  }}
                >
                  {[20, 30, 50, 100].map(n => <MenuItem key={n} value={n} sx={{ fontSize: 11 }}>{n} / page</MenuItem>)}
                </Select>
              </FormControl>
              <IconButton size="small" disabled={safePage === 0} onClick={() => setPage(0)} aria-label="First page">
                <FirstPage sx={{ fontSize: 16 }} />
              </IconButton>
              <IconButton size="small" disabled={safePage === 0} onClick={() => setPage(p => Math.max(0, p - 1))} aria-label="Previous page">
                <ChevronLeft sx={{ fontSize: 16 }} />
              </IconButton>
              <IconButton size="small" disabled={safePage >= totalPages - 1} onClick={() => setPage(p => p + 1)} aria-label="Next page">
                <ChevronRight sx={{ fontSize: 16 }} />
              </IconButton>
              <IconButton size="small" disabled={safePage >= totalPages - 1} onClick={() => setPage(totalPages - 1)} aria-label="Last page">
                <LastPage sx={{ fontSize: 16 }} />
              </IconButton>
            </Box>
          </>
        )}
      </Box>
    </Box>
  );
}

// ── CflRow ──────────────────────────────────────────────────────────────
interface CflRowProps {
  row: CflSnapshot;
  expanded: boolean;
  onToggle: () => void;
}

function CflRow({ row, expanded, onToggle }: CflRowProps) {
  return (
    <>
      <TableRow
        hover
        onClick={onToggle}
        sx={{
          cursor: 'pointer',
          height: 28,
          '& > td': {
            py: 0,
            px: 0.75,
            fontSize: 11.5,
            lineHeight: 1.3,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            borderBottom: '1px solid',
            borderColor: 'divider',
          },
        }}
      >
        <TableCell sx={{ p: 0, textAlign: 'center' }}>
          <IconButton
            size="small"
            onClick={(e) => { e.stopPropagation(); onToggle(); }}
            aria-label={expanded ? 'Collapse row' : 'Expand row'}
            sx={{ p: 0.25 }}
          >
            {expanded ? <KeyboardArrowUp sx={{ fontSize: 14 }} /> : <KeyboardArrowDown sx={{ fontSize: 14 }} />}
          </IconButton>
        </TableCell>
        {SUMMARY_COLUMNS.map(col => (
          <TableCell key={col.label} align={col.align ?? 'left'}>
            {col.render(row)}
          </TableCell>
        ))}
      </TableRow>
      <TableRow>
        <TableCell sx={{ p: 0, border: 0 }} colSpan={SUMMARY_COLUMNS.length + 1}>
          <Collapse in={expanded} timeout={150} unmountOnExit>
            <Box sx={{
              bgcolor: 'action.hover',
              p: 1,
              borderLeft: 3,
              borderColor: 'primary.main',
              maxHeight: 150,
              overflowY: 'auto',
            }}>
              <Box sx={{
                display: 'grid',
                gap: 1,
                gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', md: 'repeat(3, 1fr)', lg: 'repeat(4, 1fr)' },
              }}>
                {DETAIL_GROUPS.map(group => (
                  <Box key={group.title}>
                    <Typography sx={{
                      display: 'block',
                      fontSize: 9.5,
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: 0.5,
                      color: group.faded ? 'text.disabled' : 'text.secondary',
                      mb: 0.25,
                      lineHeight: 1.4,
                    }}>
                      {group.title}
                    </Typography>
                    <Stack spacing={0}>
                      {group.fields.map(field => (
                        <Box
                          key={field.key as string}
                          sx={{ display: 'flex', justifyContent: 'space-between', gap: 0.5, py: '1px' }}
                        >
                          <Typography sx={{ fontSize: 10.5, color: 'text.secondary', lineHeight: 1.3 }}>
                            {field.label}
                          </Typography>
                          <Typography sx={{
                            fontSize: 10.5,
                            color: group.faded ? 'text.disabled' : 'text.primary',
                            fontFamily: field.type === 'currency' ? 'monospace' : undefined,
                            textAlign: 'right',
                            lineHeight: 1.3,
                            wordBreak: 'break-word',
                          }}>
                            {renderDetailValue(row, field)}
                          </Typography>
                        </Box>
                      ))}
                    </Stack>
                  </Box>
                ))}
              </Box>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

// ── Compact filter primitives (duplicated locally, not imported) ────────
interface CompactSingleSelectProps {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (v: string) => void;
  minWidth?: number;
  disabled?: boolean;
  icon?: ReactNode;
}

function CompactSingleSelect({ label, value, options, onChange, minWidth = 90, disabled, icon }: CompactSingleSelectProps) {
  return (
    <FormControl size="small" sx={{ minWidth }}>
      <Select
        value={value}
        onChange={(e) => onChange(e.target.value as string)}
        displayEmpty
        disabled={disabled}
        renderValue={(selected) => {
          const display = options.find(o => o.value === selected)?.label || (selected ? String(selected) : '');
          return (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, minWidth: 0 }}>
              {icon}
              <Typography component="span" sx={{ fontSize: 11, color: 'text.secondary', flexShrink: 0 }}>
                {label}:
              </Typography>
              <Typography component="span" sx={{
                fontSize: 11,
                color: 'text.primary',
                fontVariantNumeric: 'tabular-nums',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {display || '—'}
              </Typography>
            </Box>
          );
        }}
        sx={{
          height: 26,
          fontSize: 11,
          '& .MuiSelect-select': { py: 0, pl: 1, pr: '24px !important' },
        }}
      >
        {options.map(o => (
          <MenuItem key={o.value} value={o.value} sx={{ fontSize: 11.5 }}>{o.label}</MenuItem>
        ))}
      </Select>
    </FormControl>
  );
}

interface CompactMultiSelectProps {
  label: string;
  value: string[];
  options: string[];
  onChange: (v: string[]) => void;
  minWidth?: number;
}

function CompactMultiSelect({ label, value, options, onChange, minWidth = 110 }: CompactMultiSelectProps) {
  return (
    <Autocomplete
      multiple
      size="small"
      disableCloseOnSelect
      options={options}
      value={value}
      onChange={(_, v) => onChange(v)}
      renderTags={(values) => (
        <Typography component="span" sx={{
          fontSize: 11,
          color: 'text.primary',
          ml: 0.5,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          maxWidth: 90,
        }}>
          {values.length === 1 ? values[0] : `${values.length} sel.`}
        </Typography>
      )}
      sx={{
        minWidth,
        maxWidth: 200,
        '& .MuiOutlinedInput-root': {
          py: '0 !important',
          minHeight: 26,
          fontSize: 11,
          paddingRight: '32px !important',
        },
        '& .MuiAutocomplete-input': {
          py: '2px !important',
          fontSize: 11,
        },
        '& .MuiInputLabel-root': {
          fontSize: 11,
          transform: 'translate(8px, 6px) scale(1)',
          '&.MuiInputLabel-shrink': {
            transform: 'translate(8px, -7px) scale(0.85)',
          },
        },
      }}
      slotProps={{
        paper: { sx: { fontSize: 11.5 } },
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          placeholder={value.length === 0 ? 'Any' : ''}
        />
      )}
    />
  );
}

interface CompactDateInputProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
}

function CompactDateInput({ label, value, onChange }: CompactDateInputProps) {
  return (
    <TextField
      size="small"
      label={label}
      type="date"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      InputLabelProps={{ shrink: true, sx: { fontSize: 11 } }}
      sx={{
        width: 140,
        '& .MuiInputBase-root': { fontSize: 11, height: 26 },
        '& .MuiInputBase-input': { py: 0.25, px: 1, fontSize: 11 },
        '& .MuiInputLabel-shrink': { transform: 'translate(8px, -7px) scale(0.85)' },
      }}
    />
  );
}

// ── Freshness badge (duplicated locally) ────────────────────────────────
interface FreshnessBadgeProps { data: DataFreshness }

function FreshnessBadge({ data }: FreshnessBadgeProps) {
  const capIso = data.last_capture_at || data.report_date || null;
  if (!capIso) {
    return <DotLabel color="text.disabled" label="No data" tooltip="No file uploaded yet" />;
  }
  const capDate = new Date(capIso);
  if (isNaN(capDate.getTime())) {
    return <DotLabel color="text.disabled" label="No data" tooltip="Invalid capture timestamp" />;
  }
  const ageHours = (Date.now() - capDate.getTime()) / 3600_000;
  let dotColor: string = 'success.main';
  if (ageHours > 24 * 3) dotColor = 'error.main';
  else if (ageHours > 24) dotColor = 'warning.main';

  const dateLabel = capDate.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  const timeLabel = capDate.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  return <DotLabel color={dotColor} label={dateLabel} tooltip={`Last file uploaded: ${dateLabel} at ${timeLabel}`} />;
}

function DotLabel({ color, label, tooltip }: { color: string; label: string; tooltip: string }) {
  return (
    <Tooltip title={tooltip}>
      <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.75 }}>
        <Box component="span" sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: color, flexShrink: 0 }} />
        <Typography component="span" sx={{ fontSize: 11.5, color: 'text.primary', fontVariantNumeric: 'tabular-nums' }}>
          {label}
        </Typography>
      </Box>
    </Tooltip>
  );
}
