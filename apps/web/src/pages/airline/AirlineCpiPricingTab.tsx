import { useState, useEffect, useCallback, useMemo, useRef, type ReactNode, type MutableRefObject } from 'react';
import {
  Box, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  CircularProgress, Button, Collapse, Chip, IconButton, Autocomplete, TextField,
  FormControl, Select, MenuItem, Stack, Divider,
} from '@mui/material';
import {
  Flight, KeyboardArrowDown, KeyboardArrowUp, RestartAlt, CalendarToday,
  ChevronLeft, ChevronRight, FirstPage, LastPage,
} from '@mui/icons-material';
import EmptyState from '../../components/common/EmptyState';
import { api } from '../../api';
import { fetchAllPagesCached } from '../../api/datasetCache';
import { isAbortError } from '../../api/httpClient';
import type { AirlineSnapshot, FilterMetadata } from '../../types';
import { BANNER_BG, brandInk } from '../../components/dashboard/bannerTheme';

interface AirlineCpiPricingTabProps {
  tenantCode: 'JY' | 'PW' | 'ALT' | 'WM';
  filters: Record<string, string>;
  onFiltersChange: (f: Record<string, string>) => void;
  /** Parent populates this ref so the page toolbar's Export button can fire CSV. */
  exportRef?: MutableRefObject<() => void>;
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
const fmtSignedCurrency = (n: number): string => (n > 0 ? '+' : n < 0 ? '-' : '') + Math.abs(n).toFixed(2);
const fmtSignedPercent = (n: number): string => (n > 0 ? '+' : n < 0 ? '-' : '') + Math.abs(n).toFixed(2) + '%';
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

// ── Fare delta computation ──────────────────────────────────────────────
function getFareDelta(row: AirlineSnapshot): number | null {
  if (row.fare_delta != null) {
    const n = Number(row.fare_delta);
    if (!Number.isNaN(n)) return n;
  }
  if (row.ref_tot_fare != null && row.comp_tot_fare != null) {
    const a = Number(row.ref_tot_fare);
    const b = Number(row.comp_tot_fare);
    if (!Number.isNaN(a) && !Number.isNaN(b)) return a - b;
  }
  return null;
}

function getFareDeltaPct(row: AirlineSnapshot): number | null {
  if (row.fare_delta_pct != null) {
    const n = Number(row.fare_delta_pct);
    if (!Number.isNaN(n)) return n;
  }
  const d = getFareDelta(row);
  const c = row.comp_tot_fare == null ? null : Number(row.comp_tot_fare);
  if (d == null || c == null || c === 0 || Number.isNaN(c)) return null;
  return (d / c) * 100;
}

function deltaColor(d: number | null): 'success.main' | 'error.main' | 'text.primary' {
  if (d == null) return 'text.primary';
  if (d < 0) return 'success.main';
  if (d > 0) return 'error.main';
  return 'text.primary';
}

// ── Summary columns (compact labels + fixed widths) ─────────────────────
interface SummaryColumn {
  label: string;
  align?: 'left' | 'right';
  width: number;
  render: (row: AirlineSnapshot) => ReactNode;
  /** Plain-text value for the cell's native tooltip. Set it on any column
   *  whose content can outrun its fixed width — connection itineraries
   *  concatenate a flight number per leg, so they routinely do. */
  title?: (row: AirlineSnapshot) => string;
}

const SUMMARY_COLUMNS: SummaryColumn[] = [
  { label: 'Org',       align: 'left',  width: 44, render: r => fmtText(r.ref_org) },
  { label: 'Dst',       align: 'left',  width: 44, render: r => fmtText(r.ref_dst) },
  { label: 'Trip',      align: 'left',  width: 40, render: r => r.trip_type
      ? <Chip label={r.trip_type} size="small" variant="outlined"
              sx={{ height: 16, fontSize: 10, '& .MuiChip-label': { px: 0.5 } }} />
      : DASH },
  { label: 'AL',        align: 'left',  width: 36, render: r => fmtText(r.ref_al) },
  { label: 'Flt',       align: 'left',  width: 110, render: r => fmtText(r.ref_flt_num),
    title: r => fmtText(r.ref_flt_num) },
  { label: 'Dep',       align: 'left',  width: 84, render: r => fmtDate(r.ref_dep_date) },
  { label: 'Cab',       align: 'left',  width: 40, render: r => fmtText(r.ref_cab_code) },
  { label: 'Ref fare',  align: 'right', width: 76, render: r => (
      <Box component="span" sx={{ fontFamily: 'monospace', fontSize: 11 }}>{fmtCurrency(r.ref_tot_fare)}</Box>
  )},
  { label: 'Comp',      align: 'left',  width: 40, render: r => fmtText(r.comp_al) },
  { label: 'C.Flt',     align: 'left',  width: 110, render: r => fmtText(r.comp_flt_num),
    title: r => fmtText(r.comp_flt_num) },
  { label: 'C.Dep',     align: 'left',  width: 84, render: r => fmtDate(r.comp_dep_date) },
  { label: 'C.Cab',     align: 'left',  width: 40, render: r => fmtText(r.comp_cab_code) },
  { label: 'Comp fare', align: 'right', width: 76, render: r => (
      <Box component="span" sx={{ fontFamily: 'monospace', fontSize: 11 }}>{fmtCurrency(r.comp_tot_fare)}</Box>
  )},
  { label: 'Delta',     align: 'right', width: 72, render: r => {
      const d = getFareDelta(r);
      return <Box component="span" sx={{ color: deltaColor(d), fontFamily: 'monospace', fontSize: 11, fontWeight: 500 }}>
        {d == null ? DASH : fmtSignedCurrency(d)}
      </Box>;
  }},
  { label: 'Δ%',        align: 'right', width: 56, render: r => {
      const p = getFareDeltaPct(r);
      const d = getFareDelta(r);
      return <Box component="span" sx={{ color: deltaColor(d), fontFamily: 'monospace', fontSize: 11, fontWeight: 500 }}>
        {p == null ? DASH : fmtSignedPercent(p)}
      </Box>;
  }},
];

const CHEVRON_COL_WIDTH = 28;

// ── Detail-panel groups ─────────────────────────────────────────────────
type DetailFieldType = 'text' | 'currency' | 'date' | 'time';
interface DetailField {
  key: keyof AirlineSnapshot;
  label: string;
  type?: DetailFieldType;
}
interface DetailGroup {
  title: string;
  rtOnly?: boolean;
  faded?: boolean;
  fields: DetailField[];
}

const DETAIL_GROUPS: DetailGroup[] = [
  {
    title: 'Reference outbound',
    fields: [
      { key: 'ref_dep_time',   label: 'Dep Time',       type: 'time' },
      { key: 'ref_arr_time',   label: 'Arr Time',       type: 'time' },
      { key: 'ref_stops',      label: 'Stops' },
      { key: 'ref_via',        label: 'Via' },
      { key: 'ref_equip_code', label: 'Equipment Code' },
      { key: 'ref_equip_name', label: 'Aircraft' },
      { key: 'ref_cab_name',   label: 'Cabin Name' },
      { key: 'ref_bkg_class',  label: 'Booking Class' },
      { key: 'ref_seats',      label: 'Seats' },
    ],
  },
  {
    title: 'Reference return',
    rtOnly: true,
    fields: [
      { key: 'ref_ret_flt_num',    label: 'Return Flight #' },
      { key: 'ref_ret_dep_date',   label: 'Return Dep Date', type: 'date' },
      { key: 'ref_ret_dep_time',   label: 'Return Dep Time', type: 'time' },
      { key: 'ref_ret_arr_time',   label: 'Return Arr Time', type: 'time' },
      { key: 'ref_ret_stops',      label: 'Return Stops' },
      { key: 'ref_ret_via',        label: 'Return Via' },
      { key: 'ref_ret_equip_code', label: 'Return Equip Code' },
      { key: 'ref_ret_cab_name',   label: 'Return Cabin Name' },
      { key: 'ref_ret_cab_code',   label: 'Return Cabin Code' },
      { key: 'ref_ret_bkg_class',  label: 'Return Bkg Class' },
      { key: 'ref_ret_seats',      label: 'Return Seats' },
    ],
  },
  {
    title: 'Reference fare breakdown',
    fields: [
      { key: 'ref_base_fare', label: 'Base Fare',  type: 'currency' },
      { key: 'ref_tax',       label: 'Tax',        type: 'currency' },
      { key: 'ref_yq',        label: 'YQ',         type: 'currency' },
      { key: 'ref_yr',        label: 'YR',         type: 'currency' },
      { key: 'ref_anc_price', label: 'Anc Price',  type: 'currency' },
      { key: 'ref_anc_type',  label: 'Anc Type' },
      { key: 'ref_tot_fare',  label: 'Total Fare', type: 'currency' },
      { key: 'ref_curr',      label: 'Currency' },
    ],
  },
  {
    title: 'Competitor outbound',
    fields: [
      { key: 'comp_dep_time',   label: 'Dep Time',       type: 'time' },
      { key: 'comp_arr_time',   label: 'Arr Time',       type: 'time' },
      { key: 'comp_stops',      label: 'Stops' },
      { key: 'comp_via',        label: 'Via' },
      { key: 'comp_equip_code', label: 'Equipment Code' },
      { key: 'comp_cab_name',   label: 'Cabin Name' },
      { key: 'comp_bkg_class',  label: 'Booking Class' },
      { key: 'comp_seats',      label: 'Seats' },
    ],
  },
  {
    title: 'Competitor return',
    rtOnly: true,
    fields: [
      { key: 'comp_ret_flt_num',    label: 'Return Flight #' },
      { key: 'comp_ret_dep_date',   label: 'Return Dep Date', type: 'date' },
      { key: 'comp_ret_dep_time',   label: 'Return Dep Time', type: 'time' },
      { key: 'comp_ret_arr_time',   label: 'Return Arr Time', type: 'time' },
      { key: 'comp_ret_stops',      label: 'Return Stops' },
      { key: 'comp_ret_via',        label: 'Return Via' },
      { key: 'comp_ret_equip_code', label: 'Return Equip Code' },
      { key: 'comp_ret_cab_name',   label: 'Return Cabin Name' },
      { key: 'comp_ret_cab_code',   label: 'Return Cabin Code' },
      { key: 'comp_ret_bkg_class',  label: 'Return Bkg Class' },
      { key: 'comp_ret_seats',      label: 'Return Seats' },
    ],
  },
  {
    title: 'Competitor fare breakdown',
    fields: [
      { key: 'comp_base_fare', label: 'Base Fare',  type: 'currency' },
      { key: 'comp_tax',       label: 'Tax',        type: 'currency' },
      { key: 'comp_yq',        label: 'YQ',         type: 'currency' },
      { key: 'comp_yr',        label: 'YR',         type: 'currency' },
      { key: 'comp_anc_price', label: 'Anc Price',  type: 'currency' },
      { key: 'comp_anc_type',  label: 'Anc Type' },
      { key: 'comp_tot_fare',  label: 'Total Fare', type: 'currency' },
      { key: 'comp_curr',      label: 'Currency' },
    ],
  },
  {
    title: 'Additional info',
    fields: [
      { key: 'ref_ff_code',  label: 'Ref FF Code' },
      { key: 'comp_ff_code', label: 'Comp FF Code' },
      { key: 'ref_channel',  label: 'Ref Channel' },
      { key: 'comp_channel', label: 'Comp Channel' },
      { key: 'ref_pos',      label: 'Ref POS' },
      { key: 'comp_pos',     label: 'Comp POS' },
    ],
  },
  {
    title: 'Capture metadata',
    faded: true,
    fields: [
      { key: 'cap_date',      label: 'Capture Date', type: 'date' },
      { key: 'cap_time',      label: 'Capture Time', type: 'time' },
      { key: 'file_date',     label: 'File Date',    type: 'date' },
      { key: 'source_file',   label: 'Source File' },
      { key: 'report_date',   label: 'Report Date',  type: 'date' },
      { key: 'ingested_at',   label: 'Ingested At' },
      { key: 'loaded_at',     label: 'Loaded At' },
      { key: 'tenant_code',   label: 'Tenant' },
      { key: 'business_type', label: 'Business Type' },
    ],
  },
];

function renderDetailValue(row: AirlineSnapshot, field: DetailField): string {
  const v = row[field.key];
  switch (field.type) {
    case 'currency': return fmtCurrency(v);
    case 'date':     return fmtDate(v);
    case 'time':     return fmtTime(v);
    default:         return fmtText(v);
  }
}

// ── Export columns (76 data-dictionary headers) ─────────────────────────
const EXPORT_COLUMNS: Array<{ header: string; key: keyof AirlineSnapshot }> = [
  { header: 'CapDate',          key: 'cap_date' },
  { header: 'CapTime',          key: 'cap_time' },
  { header: 'RefAL',            key: 'ref_al' },
  { header: 'RefFltNum',        key: 'ref_flt_num' },
  { header: 'RefRetFltNum',     key: 'ref_ret_flt_num' },
  { header: 'RefOrg',           key: 'ref_org' },
  { header: 'RefDst',           key: 'ref_dst' },
  { header: 'RefDepDate',       key: 'ref_dep_date' },
  { header: 'RefRetDepDate',    key: 'ref_ret_dep_date' },
  { header: 'RefDepTime',       key: 'ref_dep_time' },
  { header: 'RefRetDepTime',    key: 'ref_ret_dep_time' },
  { header: 'RefArrTime',       key: 'ref_arr_time' },
  { header: 'RefRetArrTime',    key: 'ref_ret_arr_time' },
  { header: 'RefStops',         key: 'ref_stops' },
  { header: 'RefVia',           key: 'ref_via' },
  { header: 'RefRetVia',        key: 'ref_ret_via' },
  { header: 'RefRetStops',      key: 'ref_ret_stops' },
  { header: 'TripType',         key: 'trip_type' },
  { header: 'RefCurr',          key: 'ref_curr' },
  { header: 'RefBaseFare',      key: 'ref_base_fare' },
  { header: 'RefTax',           key: 'ref_tax' },
  { header: 'RefYQ',            key: 'ref_yq' },
  { header: 'RefYR',            key: 'ref_yr' },
  { header: 'RefFFCode',        key: 'ref_ff_code' },
  { header: 'RefAncPrice',      key: 'ref_anc_price' },
  { header: 'RefAncType',       key: 'ref_anc_type' },
  { header: 'RefTotFare',       key: 'ref_tot_fare' },
  { header: 'RefCabName',       key: 'ref_cab_name' },
  { header: 'RefRetCabName',    key: 'ref_ret_cab_name' },
  { header: 'RefCabCode',       key: 'ref_cab_code' },
  { header: 'RefRetCabCode',    key: 'ref_ret_cab_code' },
  { header: 'RefBkgClass',      key: 'ref_bkg_class' },
  { header: 'RefRetBkgClass',   key: 'ref_ret_bkg_class' },
  { header: 'RefSeats',         key: 'ref_seats' },
  { header: 'RefRetSeats',      key: 'ref_ret_seats' },
  { header: 'RefEquipCode',     key: 'ref_equip_code' },
  { header: 'RefRetEquipCode',  key: 'ref_ret_equip_code' },
  { header: 'RefAircraft',      key: 'ref_equip_name' },
  { header: 'RefPOS',           key: 'ref_pos' },
  { header: 'RefChannel',       key: 'ref_channel' },
  { header: 'CompAL',           key: 'comp_al' },
  { header: 'CompFltNum',       key: 'comp_flt_num' },
  { header: 'CompRetFltNum',    key: 'comp_ret_flt_num' },
  { header: 'CompOrg',          key: 'comp_org' },
  { header: 'CompDst',          key: 'comp_dst' },
  { header: 'CompDepDate',      key: 'comp_dep_date' },
  { header: 'CompRetDepDate',   key: 'comp_ret_dep_date' },
  { header: 'CompDepTime',      key: 'comp_dep_time' },
  { header: 'CompRetDepTime',   key: 'comp_ret_dep_time' },
  { header: 'CompArrTime',      key: 'comp_arr_time' },
  { header: 'CompRetArrTime',   key: 'comp_ret_arr_time' },
  { header: 'CompStops',        key: 'comp_stops' },
  { header: 'CompVia',          key: 'comp_via' },
  { header: 'CompRetVia',       key: 'comp_ret_via' },
  { header: 'CompRetStops',     key: 'comp_ret_stops' },
  { header: 'CompCurr',         key: 'comp_curr' },
  { header: 'CompBaseFare',     key: 'comp_base_fare' },
  { header: 'CompTax',          key: 'comp_tax' },
  { header: 'CompYQ',           key: 'comp_yq' },
  { header: 'CompYR',           key: 'comp_yr' },
  { header: 'CompAncPrice',     key: 'comp_anc_price' },
  { header: 'CompAncType',      key: 'comp_anc_type' },
  { header: 'CompTotFare',      key: 'comp_tot_fare' },
  { header: 'CompCabName',      key: 'comp_cab_name' },
  { header: 'CompRetCabName',   key: 'comp_ret_cab_name' },
  { header: 'CompCabCode',      key: 'comp_cab_code' },
  { header: 'CompRetCabCode',   key: 'comp_ret_cab_code' },
  { header: 'CompBkgClass',     key: 'comp_bkg_class' },
  { header: 'CompRetBkgClass',  key: 'comp_ret_bkg_class' },
  { header: 'CompSeats',        key: 'comp_seats' },
  { header: 'CompRetSeats',     key: 'comp_ret_seats' },
  { header: 'CompEquipCode',    key: 'comp_equip_code' },
  { header: 'CompRetEquipCode', key: 'comp_ret_equip_code' },
  { header: 'CompPOS',          key: 'comp_pos' },
  { header: 'CompChannel',      key: 'comp_channel' },
];

// ── Page walker (load all rows for selected file_date) ──────────────────
// Shared with the velocity and cruise grids — see api/fetchAllPages.ts.
// Wrapped in the session cache: a repeat view of the same (tenant, file_date,
// airline) is served from memory after a 50-row freshness probe instead of
// re-walking every page. See api/datasetCache.ts.
function fetchAllRows(
  baseQuery: Record<string, string>,
  tenantCode: 'JY' | 'PW' | 'ALT' | 'WM',
  onProgress?: (loaded: number, total: number) => void,
  signal?: AbortSignal,
): Promise<AirlineSnapshot[]> {
  return fetchAllPagesCached<AirlineSnapshot>({
    key: { endpoint: '/api/v1/airline/snapshots', tenant: tenantCode, query: baseQuery },
    fetchPage: (page, pageSize, sig, withTotal) => api.airline.listSnapshots(
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
export default function AirlineCpiPricingTab({ tenantCode, filters, onFiltersChange, exportRef }: AirlineCpiPricingTabProps) {
  // WinAir accents follow the brand red; other tenants keep theme primary.
  const isWm = tenantCode === 'WM';
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ loaded: number; total: number } | null>(null);
  const [allData, setAllData] = useState<AirlineSnapshot[]>([]);
  const [meta, setMeta] = useState<FilterMetadata[]>([]);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(30);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Client-side filters (operate on already-loaded `allData`)
  const [routes, setRoutes] = useState<string[]>([]);
  const [competitors, setCompetitors] = useState<string[]>([]);
  const [tripTypeFilter, setTripTypeFilter] = useState<'all' | 'OW' | 'RT'>('all');
  const [cabins, setCabins] = useState<string[]>([]);
  const [depFrom, setDepFrom] = useState<string>('');
  const [depTo, setDepTo] = useState<string>('');

  // ── Load filter metadata once per tenant ────────────────────────────
  useEffect(() => {
    api.airline.getFilterMetadata(tenantCode).then(setMeta);
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
      console.error('Failed to load airline pricing snapshots:', err);
      setAllData([]);
    } finally {
      if (!ctrl.signal.aborted) {
        setLoading(false);
        setProgress(null);
      }
    }
  }, [tenantCode]);

  // Cancel any in-flight load when the tab unmounts (switching Pricing/Velocity
  // unmounts this component, so without this an abandoned load keeps fetching).
  //
  // Safe under React StrictMode, which in dev mounts, cleans up, then mounts
  // again: at that synthetic cleanup `abortRef.current` is still null, because
  // a load can only start from the `[meta]` effect below and `meta` is filled
  // by an async request that cannot resolve inside the mount commit. If a
  // future change ever starts a load synchronously on mount, revisit this —
  // it would cancel that first load and never restart it.
  useEffect(() => () => abortRef.current?.abort(), []);

  // ── Default filter wiring (file_date = latest, airline if locked) ───
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
  }, [routes, competitors, tripTypeFilter, cabins, depFrom, depTo]);

  // ── Derived option lists from loaded data ───────────────────────────
  const routeOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) {
      if (r.ref_org && r.ref_dst) set.add(`${r.ref_org}–${r.ref_dst}`);
    }
    return Array.from(set).sort();
  }, [allData]);

  const competitorOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) if (r.comp_al) set.add(r.comp_al);
    return Array.from(set).sort();
  }, [allData]);

  const cabinOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) if (r.ref_cab_code) set.add(r.ref_cab_code);
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
      if (routes.length > 0 && !routes.includes(`${r.ref_org}–${r.ref_dst}`)) return false;
      if (competitors.length > 0 && !competitors.includes(r.comp_al)) return false;
      if (tripTypeFilter !== 'all' && r.trip_type !== tripTypeFilter) return false;
      if (cabins.length > 0 && !cabins.includes(r.ref_cab_code)) return false;
      if (depFrom && (!r.ref_dep_date || r.ref_dep_date < depFrom)) return false;
      if (depTo && (!r.ref_dep_date || r.ref_dep_date > depTo)) return false;
      return true;
    });
  }, [allData, routes, competitors, tripTypeFilter, cabins, depFrom, depTo]);

  const totalPages = Math.max(1, Math.ceil(filteredData.length / rowsPerPage));
  const safePage = Math.min(page, totalPages - 1);
  const pagedData = useMemo(() => {
    return filteredData.slice(safePage * rowsPerPage, (safePage + 1) * rowsPerPage);
  }, [filteredData, safePage, rowsPerPage]);

  const hasClientFilters =
    routes.length > 0 || competitors.length > 0 || tripTypeFilter !== 'all' ||
    cabins.length > 0 || depFrom !== '' || depTo !== '';

  // ── Handlers ────────────────────────────────────────────────────────
  const handleFileDateChange = (v: string) => {
    const next: Record<string, string> = { ...filters, file_date: v };
    onFiltersChange(next);
    setPage(0);
    fetchData(next);
  };

  const handleResetClientFilters = () => {
    setRoutes([]);
    setCompetitors([]);
    setTripTypeFilter('all');
    setCabins([]);
    setDepFrom('');
    setDepTo('');
  };

  const handleRowToggle = (id: string) => {
    setExpandedId(prev => (prev === id ? null : id));
  };

  // ── Export (CSV only) ───────────────────────────────────────────────
  const handleExportCsv = useCallback(() => {
    if (filteredData.length === 0) return;
    const headers = EXPORT_COLUMNS.map(c => c.header);
    const lines: string[] = [headers.join(',')];
    for (const row of filteredData) {
      lines.push(EXPORT_COLUMNS.map(c => csvEscape(row[c.key])).join(','));
    }
    const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const fileDate = filters.file_date || new Date().toISOString().slice(0, 10);
    downloadBlob(blob, `${tenantCode}_CPI_Pricing_${fileDate}.csv`);
  }, [filteredData, filters.file_date, tenantCode]);

  // Re-bind the export trigger every render so the page toolbar's button
  // closes over the latest filteredData.
  if (exportRef) exportRef.current = handleExportCsv;

  // ── Render ──────────────────────────────────────────────────────────
  return (
    <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      {/* ── Inline filter strip ─────────────────────────────────── */}
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
        <CompactMultiSelect label="Route"      value={routes}      onChange={setRoutes}      options={routeOptions} />
        <CompactMultiSelect label="Comp"       value={competitors} onChange={setCompetitors} options={competitorOptions} />
        <CompactSingleSelect label="Trip"
          value={tripTypeFilter}
          options={[
            { value: 'all', label: 'All' },
            { value: 'OW',  label: 'OW' },
            { value: 'RT',  label: 'RT' },
          ]}
          onChange={(v) => setTripTypeFilter(v as 'all' | 'OW' | 'RT')}
          minWidth={80}
        />
        <CompactMultiSelect label="Cab" value={cabins}  onChange={setCabins}  options={cabinOptions} />
        <CompactDateInput label="Dep from" value={depFrom} onChange={setDepFrom} />
        <CompactDateInput label="Dep to"   value={depTo}   onChange={setDepTo}   />

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
          sx={{ fontSize: 11, textTransform: 'none', minHeight: 26, py: 0.25, px: 0.75, ...(isWm && { color: brandInk }) }}
        >
          Reset
        </Button>
      </Box>

      {/* ── Table area ──────────────────────────────────────────── */}
      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {loading && allData.length === 0 ? (
          <Box sx={{ flex: 1, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <CircularProgress size={28} sx={isWm ? { color: brandInk } : undefined} />
          </Box>
        ) : allData.length === 0 ? (
          <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <EmptyState
              icon={<Flight sx={{ fontSize: 48 }} />}
              title={`No ${tenantCode} Data`}
              description={`Pick a file date to load ${tenantCode} airline CPI snapshots.`}
              actionLabel="Load All"
              onAction={() => fetchData(filters.file_date ? { file_date: filters.file_date } : {})}
              accent={isWm ? BANNER_BG : undefined}
            />
          </Box>
        ) : (
          <>
            <TableContainer sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
              <Table size="small" stickyHeader aria-label={`${tenantCode} Airline CPI snapshots`} sx={{ tableLayout: 'fixed' }}>
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
                    <PricingRow
                      key={row.id}
                      row={row}
                      expanded={expandedId === row.id}
                      onToggle={() => handleRowToggle(row.id)}
                      isWm={isWm}
                    />
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            {/* ── Compact pagination ───────────────────────────── */}
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

// ── PricingRow ──────────────────────────────────────────────────────────
interface PricingRowProps {
  row: AirlineSnapshot;
  expanded: boolean;
  onToggle: () => void;
  /** WinAir rows accent in brand red instead of theme primary. */
  isWm?: boolean;
}

function PricingRow({ row, expanded, onToggle, isWm = false }: PricingRowProps) {
  const isRT = row.trip_type === 'RT';
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
          '&:last-child > td': expanded ? {} : { borderBottom: '1px solid', borderColor: 'divider' },
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
          <TableCell key={col.label} align={col.align ?? 'left'} title={col.title?.(row)}>
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
              borderColor: isWm ? brandInk : 'primary.main',
              maxHeight: 150,
              overflowY: 'auto',
            }}>
              <Box sx={{
                display: 'grid',
                gap: 1,
                gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', md: 'repeat(3, 1fr)', lg: 'repeat(4, 1fr)' },
              }}>
                {DETAIL_GROUPS.map(group => {
                  if (group.rtOnly && !isRT) return null;
                  return (
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
                  );
                })}
              </Box>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </>
  );
}

// ── Compact filter primitives ───────────────────────────────────────────
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
