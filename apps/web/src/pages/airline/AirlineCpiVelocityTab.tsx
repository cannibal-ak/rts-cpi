import { useState, useEffect, useCallback, useMemo, useRef, type ReactNode, type MutableRefObject } from 'react';
import {
  Box, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  CircularProgress, Button, Autocomplete, TextField,
  FormControl, Select, MenuItem, Divider, IconButton,
} from '@mui/material';
import {
  Flight, RestartAlt, CalendarToday,
  ChevronLeft, ChevronRight, FirstPage, LastPage,
} from '@mui/icons-material';
import EmptyState from '../../components/common/EmptyState';
import { api } from '../../api';
import { fetchAllPagesCached } from '../../api/datasetCache';
import { isAbortError } from '../../api/httpClient';
import type { VelocitySnapshot, FilterMetadata } from '../../types';
import { getTenantChrome } from '../../components/dashboard/tenantChrome';

interface AirlineCpiVelocityTabProps {
  /** Tenant code selects which airline's velocity snapshot to query. */
  tenantCode: 'JY' | 'PW' | 'ALT' | 'WM' | 'DA' | '5L';
  filters: Record<string, string>;
  onFiltersChange: (f: Record<string, string>) => void;
  /** Parent populates this ref so the page toolbar's Export button can fire CSV. */
  exportRef?: MutableRefObject<() => void>;
}

// ── Formatters ──────────────────────────────────────────────────────────
const DASH = '—';
const isEmpty = (v: unknown) => v == null || v === '';
const fmtText = (v: unknown): string => isEmpty(v) ? DASH : String(v);
const fmtInt = (v: unknown): string => {
  if (isEmpty(v)) return DASH;
  const n = Number(v);
  return Number.isNaN(n) ? String(v) : n.toLocaleString();
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

// Seat factor arrives from API as integer percentage (0–100); guard the
// 0–1 case defensively in case the schema ever ships floats.
function toPercent(v: unknown): number | null {
  if (isEmpty(v)) return null;
  const n = Number(v);
  if (Number.isNaN(n)) return null;
  return n > 0 && n <= 1 ? n * 100 : n;
}

const fmtPercent = (v: unknown): string => {
  const p = toPercent(v);
  return p == null ? DASH : `${p.toFixed(1)}%`;
};

function seatFactorColor(v: unknown): string {
  const p = toPercent(v);
  if (p == null) return 'text.primary';
  if (p >= 90) return 'success.main';
  if (p >= 70) return 'warning.main';
  return 'error.main';
}

// ── Summary columns (compact labels + fixed widths) ─────────────────────
interface SummaryColumn {
  label: string;
  align?: 'left' | 'right';
  width: number;
  render: (row: VelocitySnapshot) => ReactNode;
}

const SUMMARY_COLUMNS: SummaryColumn[] = [
  { label: 'Dep date',  align: 'left',  width: 80, render: r => fmtDate(r.dep_date) },
  { label: 'Time',      align: 'left',  width: 48, render: r => (
      <Box component="span" sx={{ fontFamily: 'monospace', fontSize: 11 }}>{fmtTime(r.dep_time)}</Box>
  )},
  { label: 'Code',      align: 'left',  width: 48, render: r => fmtText(r.dep_code) },
  { label: 'City pair', align: 'left',  width: 72, render: r => (
      <Box component="span" sx={{ fontFamily: 'monospace', fontSize: 11 }}>{fmtText(r.city_pair)}</Box>
  )},
  { label: 'Eqp',       align: 'left',  width: 44, render: r => fmtText(r.eqp) },
  { label: 'L/S type',  align: 'left',  width: 60, render: r => fmtText(r.legseg_type) },
  { label: 'L/S#',      align: 'right', width: 40, render: r => fmtInt(r.leg_seg_order) },
  { label: 'Days',      align: 'right', width: 44, render: r => fmtInt(r.days_left) },
  { label: 'Comp',      align: 'left',  width: 48, render: r => fmtText(r.compartment) },
  { label: 'Bkg',       align: 'right', width: 44, render: r => (
      <Box component="span" sx={{ fontFamily: 'monospace', fontSize: 11 }}>{fmtInt(r.current_booking)}</Box>
  )},
  { label: 'Cap',       align: 'right', width: 44, render: r => (
      <Box component="span" sx={{ fontFamily: 'monospace', fontSize: 11 }}>{fmtInt(r.capacity)}</Box>
  )},
  { label: 'Act SF',    align: 'right', width: 56, render: r => (
      <Box component="span" sx={{
        fontFamily: 'monospace', fontSize: 11, fontWeight: 500,
        color: seatFactorColor(r.actual_seat_factor),
      }}>{fmtPercent(r.actual_seat_factor)}</Box>
  )},
  { label: 'Fcst SF',   align: 'right', width: 56, render: r => (
      <Box component="span" sx={{
        fontFamily: 'monospace', fontSize: 11, fontWeight: 500,
        color: seatFactorColor(r.forecasted_seat_factor),
      }}>{fmtPercent(r.forecasted_seat_factor)}</Box>
  )},
];

// ── Export columns (13 data-dictionary headers) ─────────────────────────
const EXPORT_COLUMNS: Array<{ header: string; key: keyof VelocitySnapshot }> = [
  { header: 'DepDate',                key: 'dep_date' },
  { header: 'DepTime',                key: 'dep_time' },
  { header: 'DepCode',                key: 'dep_code' },
  { header: 'CityPair',               key: 'city_pair' },
  { header: 'Eqp',                    key: 'eqp' },
  { header: 'LegsegType',             key: 'legseg_type' },
  { header: 'LegSegOrder',            key: 'leg_seg_order' },
  { header: 'Days_Left',              key: 'days_left' },
  { header: 'Compartment',            key: 'compartment' },
  { header: 'Current_Booking',        key: 'current_booking' },
  { header: 'Capacity',               key: 'capacity' },
  { header: 'Actual_Seat_Factor',     key: 'actual_seat_factor' },
  { header: 'Forecasted_Seat_Factor', key: 'forecasted_seat_factor' },
];

// ── Page walker (load all rows for selected file_date) ──────────────────
// Shared with the pricing and cruise grids — see api/fetchAllPages.ts.
// Wrapped in the session cache (api/datasetCache.ts): repeat views are served
// from memory after a 50-row freshness probe instead of re-walking every page.
function fetchAllRows(
  baseQuery: Record<string, string>,
  tenantCode: 'JY' | 'PW' | 'ALT' | 'WM' | 'DA' | '5L',
  onProgress?: (loaded: number, total: number) => void,
  signal?: AbortSignal,
): Promise<VelocitySnapshot[]> {
  return fetchAllPagesCached<VelocitySnapshot>({
    key: { endpoint: '/api/v1/airline/velocity/snapshots', tenant: tenantCode, query: baseQuery },
    fetchPage: (page, pageSize, sig, withTotal) => api.airline.velocity.listSnapshots(
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
export default function AirlineCpiVelocityTab({ tenantCode, filters, onFiltersChange, exportRef }: AirlineCpiVelocityTabProps) {
  // WinAir accents follow the brand red; other tenants keep theme primary.
  const chrome = getTenantChrome(tenantCode.toLowerCase());
  const isWm = chrome !== null;
  const brandInk = chrome?.brandInk;
  const BANNER_BG = chrome?.BANNER_BG;
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ loaded: number; total: number } | null>(null);
  const [allData, setAllData] = useState<VelocitySnapshot[]>([]);
  const [meta, setMeta] = useState<FilterMetadata[]>([]);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(30);

  // Client-side filters (operate on already-loaded `allData`)
  const [cityPairs, setCityPairs] = useState<string[]>([]);
  const [compartments, setCompartments] = useState<string[]>([]);
  const [equipment, setEquipment] = useState<string[]>([]);
  const [depCodes, setDepCodes] = useState<string[]>([]);
  const [daysMin, setDaysMin] = useState<string>('');
  const [daysMax, setDaysMax] = useState<string>('');

  // ── Load filter metadata once per tenant ────────────────────────────
  useEffect(() => {
    api.airline.velocity.getFilterMetadata(tenantCode).then(setMeta).catch(() => setMeta([]));
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
      console.error('Failed to load velocity snapshots:', err);
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
  }, [cityPairs, compartments, equipment, depCodes, daysMin, daysMax]);

  // ── Derived option lists from loaded data ───────────────────────────
  const cityPairOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) if (r.city_pair) set.add(r.city_pair);
    return Array.from(set).sort();
  }, [allData]);

  const compartmentOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) if (r.compartment) set.add(r.compartment);
    return Array.from(set).sort();
  }, [allData]);

  const equipmentOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) if (r.eqp) set.add(r.eqp);
    return Array.from(set).sort();
  }, [allData]);

  const depCodeOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of allData) if (r.dep_code) set.add(r.dep_code);
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
    const dMin = daysMin === '' ? null : Number(daysMin);
    const dMax = daysMax === '' ? null : Number(daysMax);
    return allData.filter(r => {
      if (cityPairs.length > 0 && !cityPairs.includes(r.city_pair)) return false;
      if (compartments.length > 0 && !compartments.includes(r.compartment)) return false;
      if (equipment.length > 0 && !equipment.includes(r.eqp)) return false;
      if (depCodes.length > 0 && !depCodes.includes(r.dep_code)) return false;
      if (dMin != null && !Number.isNaN(dMin) && r.days_left < dMin) return false;
      if (dMax != null && !Number.isNaN(dMax) && r.days_left > dMax) return false;
      return true;
    });
  }, [allData, cityPairs, compartments, equipment, depCodes, daysMin, daysMax]);

  const totalPages = Math.max(1, Math.ceil(filteredData.length / rowsPerPage));
  const safePage = Math.min(page, totalPages - 1);
  const pagedData = useMemo(() => {
    return filteredData.slice(safePage * rowsPerPage, (safePage + 1) * rowsPerPage);
  }, [filteredData, safePage, rowsPerPage]);

  const hasClientFilters =
    cityPairs.length > 0 || compartments.length > 0 || equipment.length > 0 ||
    depCodes.length > 0 || daysMin !== '' || daysMax !== '';

  // ── Handlers ────────────────────────────────────────────────────────
  const handleFileDateChange = (v: string) => {
    const next: Record<string, string> = { ...filters, file_date: v };
    onFiltersChange(next);
    setPage(0);
    fetchData(next);
  };

  const handleResetClientFilters = () => {
    setCityPairs([]);
    setCompartments([]);
    setEquipment([]);
    setDepCodes([]);
    setDaysMin('');
    setDaysMax('');
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
    downloadBlob(blob, `${tenantCode}_CPI_Velocity_${fileDate}.csv`);
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
        <CompactMultiSelect label="City pair" value={cityPairs}    onChange={setCityPairs}    options={cityPairOptions} />
        <CompactMultiSelect label="Comp"      value={compartments} onChange={setCompartments} options={compartmentOptions} />
        <CompactMultiSelect label="Eqp"       value={equipment}    onChange={setEquipment}    options={equipmentOptions} />
        <CompactMultiSelect label="Code"      value={depCodes}     onChange={setDepCodes}     options={depCodeOptions} />
        <CompactNumberInput label="Days min"  value={daysMin}      onChange={setDaysMin} />
        <CompactNumberInput label="Days max"  value={daysMax}      onChange={setDaysMax} />

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
              title={`No ${tenantCode} Velocity Data`}
              description={`Pick a file date to load ${tenantCode} velocity snapshots.`}
              actionLabel="Load All"
              onAction={() => fetchData(filters.file_date ? { file_date: filters.file_date } : {})}
              accent={isWm ? BANNER_BG : undefined}
            />
          </Box>
        ) : (
          <>
            <TableContainer sx={{ flex: 1, overflow: 'auto', minHeight: 0 }}>
              <Table size="small" stickyHeader aria-label={`${tenantCode} velocity snapshots`} sx={{ tableLayout: 'fixed' }}>
                <colgroup>
                  {SUMMARY_COLUMNS.map(c => <col key={c.label} style={{ width: c.width }} />)}
                </colgroup>
                <TableHead>
                  <TableRow sx={{
                    '& > th': {
                      py: 0.5,
                      px: 0.75,
                      fontSize: 11,
                      fontWeight: 500,
                      lineHeight: 1.2,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      bgcolor: 'background.paper',
                      borderBottom: '1px solid',
                      borderColor: 'divider',
                    },
                  }}>
                    {SUMMARY_COLUMNS.map(col => (
                      <TableCell key={col.label} align={col.align ?? 'left'}>
                        {col.label}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {pagedData.map(row => (
                    <TableRow
                      key={row.id}
                      hover
                      sx={{
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
                      {SUMMARY_COLUMNS.map(col => (
                        <TableCell key={col.label} align={col.align ?? 'left'}>
                          {col.render(row)}
                        </TableCell>
                      ))}
                    </TableRow>
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

// ── Compact filter primitives (private — duplicated from Pricing tab so
// changes here can't regress that one) ──────────────────────────────────
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

interface CompactNumberInputProps {
  label: string;
  value: string;
  onChange: (v: string) => void;
}

function CompactNumberInput({ label, value, onChange }: CompactNumberInputProps) {
  return (
    <TextField
      size="small"
      label={label}
      type="number"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      InputLabelProps={{ shrink: true, sx: { fontSize: 11 } }}
      inputProps={{ inputMode: 'numeric' }}
      sx={{
        width: 86,
        '& .MuiInputBase-root': { fontSize: 11, height: 26 },
        '& .MuiInputBase-input': { py: 0.25, px: 1, fontSize: 11 },
        '& .MuiInputLabel-shrink': { transform: 'translate(8px, -7px) scale(0.85)' },
      }}
    />
  );
}
