/**
 * Ingestion Runs admin page (Phase 4.4) — read-only history
 * with right-side detail drawer and 5s auto-refresh while any
 * visible run is RUNNING (so a Run-Now triggered on the
 * Schedules page surfaces here without manual reload).
 *
 * RTS platform admins only. Route-level guard via
 * ProtectedRoute + soft in-component gate for the direct-URL
 * fall-through.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, TablePagination, Chip, IconButton, Button, Stack,
  FormControl, InputLabel, Select, MenuItem, CircularProgress, Tooltip,
  Drawer, Divider, Snackbar, Alert, TextField, Grid,
  Accordion, AccordionSummary, AccordionDetails,
  Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions,
} from '@mui/material';
import {
  Refresh, Close, ContentCopy, ExpandMore, Stop,
  DeleteOutline, CloudSync,
} from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import { api } from '../../api';
import type { ApiErrorShape } from '../../api/httpClient';
import { useSession } from '../../context/SessionContext';
import { isSuperAdmin } from '../../utils/access';
import type {
  IngestionRun,
  IngestionRunDetail,
  IngestedFile,
  IngestionSchedule,
  PageInfo,
} from '../../types';


interface ToastState {
  open: boolean;
  message: string;
  severity: 'success' | 'error' | 'info' | 'warning';
}


const DEFAULT_PAGE_SIZE = 20;
const AUTO_REFRESH_MS = 5000;


// ── Helpers (inline; no shared util exists for these yet) ──

function formatDuration(startedAt: string, finishedAt: string | null): string {
  if (!finishedAt) return '—';
  const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
  if (ms < 0) return '—';
  if (ms < 1000) return '<1s';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}


function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}


type StatusColor = 'success' | 'warning' | 'error' | 'info' | 'default';

function statusColor(status: string): StatusColor {
  switch (status) {
    case 'SUCCESS': return 'success';
    case 'PARTIAL': return 'warning';
    case 'FAILED': return 'error';
    case 'RUNNING': return 'info';
    case 'CANCELLING': return 'warning';
    case 'CANCELLED': return 'default';
    case 'DELETED': return 'default';
    default: return 'default';
  }
}


function outcomeColor(outcome: string): StatusColor {
  switch (outcome) {
    case 'COMMITTED': return 'success';
    case 'DUPLICATE': return 'default';
    case 'DELETED': return 'default';
    case 'FAILED': return 'error';
    default: return 'warning';
  }
}


// The worker prepends a {event: 'DATE_FILTER', ...} entry as
// detail_log[0]. Returns null when detail_log is missing, empty,
// or doesn't carry that event (legacy runs predating the scope feature).
interface DateFilterEvent {
  scope: string;
  target_date: string | null;
  timezone?: string;
  listed_total?: number;
  matched?: number;
  skipped_examples?: string[];
}

function extractDateFilterEvent(detailLog: unknown): DateFilterEvent | null {
  if (!Array.isArray(detailLog) || detailLog.length === 0) return null;
  const head = detailLog[0];
  if (!head || typeof head !== 'object') return null;
  const evt = head as Record<string, unknown>;
  if (evt.event !== 'DATE_FILTER') return null;
  if (typeof evt.scope !== 'string') return null;
  return {
    scope: evt.scope,
    target_date: typeof evt.target_date === 'string' ? evt.target_date : null,
    timezone: typeof evt.timezone === 'string' ? evt.timezone : undefined,
    listed_total: typeof evt.listed_total === 'number' ? evt.listed_total : undefined,
    matched: typeof evt.matched === 'number' ? evt.matched : undefined,
    skipped_examples: Array.isArray(evt.skipped_examples)
      ? evt.skipped_examples.filter((s): s is string => typeof s === 'string')
      : undefined,
  };
}

function scopeLabel(evt: DateFilterEvent): string {
  if (evt.scope === 'today') return `Today (${evt.target_date ?? '?'} ${evt.timezone ?? 'IST'})`;
  if (evt.scope === 'all') return 'All files (backfill)';
  if (evt.scope.startsWith('date:')) {
    return `Specific date — ${evt.target_date ?? evt.scope.slice(5)}`;
  }
  return evt.scope;
}


// ── Detail drawer ──────────────────────────────────────────

interface DetailDrawerProps {
  open: boolean;
  run: IngestionRunDetail | null;
  loading: boolean;
  scheduleLookup: (id: string | null) => string | null;
  onClose: () => void;
  showToast: (message: string, severity: ToastState['severity']) => void;
  onCancelRequest: (runId: string) => Promise<void>;
  onDeleteFile: (runId: string, fileId: string) => Promise<void>;
  onReingestFile: (runId: string, fileId: string) => Promise<void>;
}

function DetailDrawer({
  open, run, loading, scheduleLookup, onClose, showToast, onCancelRequest,
  onDeleteFile, onReingestFile,
}: DetailDrawerProps) {
  const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  // Per-file delete / re-ingest confirmation + in-flight tracking.
  const [fileAction, setFileAction] = useState<
    { type: 'delete' | 'reingest'; file: IngestedFile } | null
  >(null);
  const [fileActionBusy, setFileActionBusy] = useState(false);

  const handleConfirmFileAction = async () => {
    if (!run || !fileAction) return;
    setFileActionBusy(true);
    try {
      if (fileAction.type === 'delete') {
        await onDeleteFile(run.id, fileAction.file.id);
      } else {
        await onReingestFile(run.id, fileAction.file.id);
      }
      setFileAction(null);
    } catch {
      // Toast already surfaced by the parent handler; keep dialog open.
    } finally {
      setFileActionBusy(false);
    }
  };

  const copyId = (id: string) => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(id).then(
        () => showToast('Run ID copied', 'info'),
        () => showToast('Copy failed — clipboard unavailable', 'error'),
      );
    }
  };

  const scheduleLabel = (() => {
    if (!run) return null;
    if (run.schedule_id === null) return <em>(orphan)</em>;
    const found = scheduleLookup(run.schedule_id);
    if (found) return found;
    return <em>(deleted)</em>;
  })();

  const handleConfirmCancel = async () => {
    if (!run) return;
    setCancelling(true);
    try {
      await onCancelRequest(run.id);
      setCancelDialogOpen(false);
    } finally {
      setCancelling(false);
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: 640, p: 3 } }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Typography variant="h6">Run Details</Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          {run && run.status === 'RUNNING' && (
            <Button
              variant="contained"
              color="error"
              size="small"
              startIcon={<Stop />}
              onClick={() => setCancelDialogOpen(true)}
              disabled={cancelling}
            >
              Stop
            </Button>
          )}
          <IconButton onClick={onClose} aria-label="Close"><Close /></IconButton>
        </Stack>
      </Stack>

      <Dialog
        open={cancelDialogOpen}
        onClose={() => !cancelling && setCancelDialogOpen(false)}
        aria-labelledby="cancel-run-dialog-title"
      >
        <DialogTitle id="cancel-run-dialog-title">Cancel this ingestion run?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            The worker will stop processing further files at its next
            checkpoint. <strong>Files already committed in this run will be kept</strong> —
            cancellation does not roll back successful work.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCancelDialogOpen(false)} disabled={cancelling}>
            Keep running
          </Button>
          <Button
            onClick={handleConfirmCancel}
            color="error"
            variant="contained"
            startIcon={cancelling ? <CircularProgress size={16} color="inherit" /> : <Stop />}
            disabled={cancelling}
          >
            {cancelling ? 'Cancelling…' : 'Cancel run'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Per-file delete / re-ingest confirmation */}
      <Dialog
        open={fileAction !== null}
        onClose={() => !fileActionBusy && setFileAction(null)}
        aria-labelledby="file-action-dialog-title"
      >
        <DialogTitle id="file-action-dialog-title">
          {fileAction?.type === 'delete'
            ? 'Delete this day’s data?'
            : 'Re-ingest this file from SFTP?'}
        </DialogTitle>
        <DialogContent>
          <DialogContentText component="div">
            {fileAction?.type === 'delete' ? (
              <>
                This permanently removes the database rows loaded from{' '}
                <strong>{fileAction?.file.remote_filename}</strong>. The SFTP
                duplicate marker is cleared too, so the same or an updated file
                can be pulled again later. <strong>This cannot be undone.</strong>
              </>
            ) : (
              <>
                This re-downloads{' '}
                <strong>{fileAction?.file.remote_filename}</strong> from the SFTP
                folder and <strong>replaces</strong> this day’s data with the
                file’s current contents. A new run will appear in the list. If
                the file on SFTP is unchanged, nothing is re-loaded.
              </>
            )}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFileAction(null)} disabled={fileActionBusy}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirmFileAction}
            color={fileAction?.type === 'delete' ? 'error' : 'primary'}
            variant="contained"
            startIcon={
              fileActionBusy
                ? <CircularProgress size={16} color="inherit" />
                : fileAction?.type === 'delete' ? <DeleteOutline /> : <CloudSync />
            }
            disabled={fileActionBusy}
          >
            {fileActionBusy
              ? 'Working…'
              : fileAction?.type === 'delete' ? 'Delete data' : 'Re-ingest'}
          </Button>
        </DialogActions>
      </Dialog>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      ) : !run ? (
        <Alert severity="error">Failed to load run details.</Alert>
      ) : (
        <Stack spacing={2}>
          {/* Header section — key facts */}
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Chip label={run.status} size="small" color={statusColor(run.status)} />
            {run.tenant_code && <Chip label={run.tenant_code} size="small" />}
          </Stack>

          <Box>
            <Typography variant="caption" color="text.secondary">Run ID</Typography>
            <Stack direction="row" alignItems="center" spacing={0.5}>
              <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                {run.id}
              </Typography>
              <Tooltip title="Copy ID">
                <IconButton size="small" onClick={() => copyId(run.id)}>
                  <ContentCopy fontSize="inherit" />
                </IconButton>
              </Tooltip>
            </Stack>
          </Box>

          <Box>
            <Typography variant="caption" color="text.secondary">Schedule</Typography>
            <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
              {scheduleLabel}
            </Typography>
          </Box>

          <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
            <Box>
              <Typography variant="caption" color="text.secondary">Started</Typography>
              <Typography variant="body2">
                {new Date(run.started_at).toLocaleString()}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">Finished</Typography>
              <Typography variant="body2">
                {run.finished_at ? new Date(run.finished_at).toLocaleString() : '—'}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">Duration</Typography>
              <Typography variant="body2">
                {run.status === 'RUNNING' && !run.finished_at
                  ? 'running…'
                  : formatDuration(run.started_at, run.finished_at)}
              </Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">Triggered by</Typography>
              <Typography variant="body2">{run.triggered_by ?? 'scheduled'}</Typography>
            </Box>
          </Stack>

          {(() => {
            const evt = extractDateFilterEvent(run.detail_log);
            if (!evt) return null;
            return (
              <Box>
                <Typography variant="caption" color="text.secondary">Scope</Typography>
                <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                  <Chip
                    label={scopeLabel(evt)}
                    size="small"
                    color={evt.scope === 'all' ? 'warning' : 'primary'}
                    variant="outlined"
                  />
                  {typeof evt.listed_total === 'number' && typeof evt.matched === 'number' && (
                    <Typography variant="caption" color="text.secondary">
                      {evt.matched}/{evt.listed_total} files matched the date filter
                      {evt.listed_total > evt.matched ? ` (${evt.listed_total - evt.matched} skipped)` : ''}
                    </Typography>
                  )}
                </Stack>
              </Box>
            );
          })()}

          <Divider />

          {/* Counter tiles */}
          <Grid container spacing={2}>
            {[
              { label: 'Files seen', value: run.files_seen },
              { label: 'Files pulled', value: run.files_pulled },
              { label: 'Jobs created', value: run.jobs_created },
              { label: 'Jobs committed', value: run.jobs_committed },
            ].map(stat => (
              <Grid item xs={6} sm={3} key={stat.label}>
                <Paper variant="outlined" sx={{ p: 1.5, textAlign: 'center' }}>
                  <Typography variant="overline" color="text.secondary">
                    {stat.label}
                  </Typography>
                  <Typography variant="h5">{stat.value}</Typography>
                </Paper>
              </Grid>
            ))}
          </Grid>

          {run.error_summary && (
            <Alert severity="error" sx={{ my: 1 }}>
              <strong>Error:</strong> {run.error_summary}
            </Alert>
          )}

          <Divider />

          {/* Files table */}
          <Box>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>
              Files ({run.ingested_files.length})
            </Typography>
            {run.ingested_files.length === 0 ? (
              <Alert severity="info">No files ingested in this run.</Alert>
            ) : (
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Filename</TableCell>
                      <TableCell>SHA-256</TableCell>
                      <TableCell>Size</TableCell>
                      <TableCell>Outcome</TableCell>
                      <TableCell>Error</TableCell>
                      <TableCell align="right">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {run.ingested_files.map((f: IngestedFile) => (
                      <TableRow key={f.id}>
                        <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                          {f.remote_filename}
                        </TableCell>
                        <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                          <Tooltip title={f.sha256}>
                            <span>{f.sha256.slice(0, 8)}…</span>
                          </Tooltip>
                        </TableCell>
                        <TableCell>{formatBytes(f.remote_size_bytes)}</TableCell>
                        <TableCell>
                          <Chip label={f.outcome} size="small" color={outcomeColor(f.outcome)} />
                        </TableCell>
                        <TableCell>
                          {f.error_message ? (
                            <Tooltip title={f.error_message}>
                              <Typography
                                variant="caption"
                                sx={{
                                  display: 'inline-block',
                                  maxWidth: 200,
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                  verticalAlign: 'bottom',
                                }}
                              >
                                {f.error_message.length > 60
                                  ? `${f.error_message.slice(0, 60)}…`
                                  : f.error_message}
                              </Typography>
                            </Tooltip>
                          ) : (
                            '—'
                          )}
                        </TableCell>
                        <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                          <Tooltip
                            title={
                              f.schedule_id
                                ? 'Re-pull this file from SFTP and replace this day’s data'
                                : 'Source schedule was deleted — cannot re-pull'
                            }
                          >
                            <span>
                              <IconButton
                                size="small"
                                color="primary"
                                disabled={f.schedule_id === null || fileActionBusy}
                                onClick={() => setFileAction({ type: 'reingest', file: f })}
                                aria-label="Re-ingest from SFTP"
                              >
                                <CloudSync fontSize="inherit" />
                              </IconButton>
                            </span>
                          </Tooltip>
                          <Tooltip
                            title={
                              f.ingestion_job_id && f.outcome === 'COMMITTED'
                                ? 'Delete this day’s data from the database'
                                : 'Only committed files have data to delete'
                            }
                          >
                            <span>
                              <IconButton
                                size="small"
                                color="error"
                                disabled={
                                  f.ingestion_job_id === null ||
                                  f.outcome !== 'COMMITTED' ||
                                  fileActionBusy
                                }
                                onClick={() => setFileAction({ type: 'delete', file: f })}
                                aria-label="Delete this day's data"
                              >
                                <DeleteOutline fontSize="inherit" />
                              </IconButton>
                            </span>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Box>

          {/* Detail log */}
          {run.detail_log != null && (
            <Accordion>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography variant="subtitle2">Raw detail log (debug)</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Box
                  component="pre"
                  sx={{
                    fontSize: '0.75rem',
                    fontFamily: 'monospace',
                    whiteSpace: 'pre-wrap',
                    maxHeight: 300,
                    overflow: 'auto',
                    bgcolor: 'background.default',
                    p: 1,
                    m: 0,
                  }}
                >
                  {JSON.stringify(run.detail_log, null, 2)}
                </Box>
              </AccordionDetails>
            </Accordion>
          )}
        </Stack>
      )}
    </Drawer>
  );
}


// ── Page component ─────────────────────────────────────────

export default function IngestionRunsPage() {
  const { session } = useSession();

  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [pageInfo, setPageInfo] = useState<PageInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [schedules, setSchedules] = useState<IngestionSchedule[]>([]);

  const [tenantFilter, setTenantFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [scheduleFilter, setScheduleFilter] = useState<string>('');
  const [startedAfter, setStartedAfter] = useState<string>('');
  const [startedBefore, setStartedBefore] = useState<string>('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedRun, setSelectedRun] = useState<IngestionRunDetail | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);

  const [toast, setToast] = useState<ToastState>({
    open: false, message: '', severity: 'info',
  });

  const showToast = useCallback((message: string, severity: ToastState['severity']) => {
    setToast({ open: true, message, severity });
  }, []);

  // ─── Fetch pipeline ──

  const fetchRuns = useCallback(async () => {
    try {
      // datetime-local emits "YYYY-MM-DDTHH:MM"; the API accepts ISO,
      // so append ":00Z" to coerce. Empty strings stay undefined.
      const after = startedAfter ? `${startedAfter}:00Z` : undefined;
      const before = startedBefore ? `${startedBefore}:00Z` : undefined;
      const result = await api.admin.ingestionRuns.list({
        page,
        page_size: pageSize,
        tenant_code: tenantFilter || undefined,
        status: statusFilter || undefined,
        schedule_id: scheduleFilter || undefined,
        started_after: after,
        started_before: before,
      });
      setRuns(result.items);
      setPageInfo(result.page_info);
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Failed to load runs', 'error');
    }
  }, [
    page, pageSize, tenantFilter, statusFilter, scheduleFilter,
    startedAfter, startedBefore, showToast,
  ]);

  // Schedules loaded once on mount (drives schedule filter dropdown +
  // schedule-name lookup in the table).
  useEffect(() => {
    (async () => {
      try {
        const result = await api.admin.ingestionSchedules.list({ page: 1, page_size: 100 });
        setSchedules(result.items);
      } catch (err) {
        const e = err as Error & ApiErrorShape;
        showToast(`Failed to load schedules: ${e.message}`, 'error');
      }
    })();
  }, [showToast]);

  useEffect(() => {
    setLoading(true);
    fetchRuns().finally(() => setLoading(false));
  }, [fetchRuns]);

  // ─── Auto-refresh while any visible row is RUNNING ──

  const autoRefreshActive = runs.some(r => r.status === 'RUNNING');
  const fetchRunsRef = useRef(fetchRuns);
  fetchRunsRef.current = fetchRuns;

  useEffect(() => {
    if (!autoRefreshActive) return;
    const t = setInterval(() => { void fetchRunsRef.current(); }, AUTO_REFRESH_MS);
    return () => clearInterval(t);
  }, [autoRefreshActive]);

  // ─── Soft admin gate ──

  if (!isSuperAdmin(session)) {
    return (
      <Box>
        <PageHeader
          title="Ingestion Runs"
          breadcrumbs={[{ label: 'Admin' }, { label: 'Ingestion Runs' }]}
        />
        <Alert severity="warning" sx={{ mt: 2 }}>
          RTS platform admin access required.
        </Alert>
      </Box>
    );
  }

  // ─── Helpers ──

  const scheduleNameForId = (id: string | null): string | null => {
    if (!id) return null;
    const found = schedules.find(s => s.id === id);
    return found ? `${found.tenant_code} ${found.domain} · ${found.cron_expression}` : null;
  };

  const openDetail = async (run: IngestionRun) => {
    setSelectedRun(null);
    setDrawerLoading(true);
    setDrawerOpen(true);
    try {
      const detail = await api.admin.ingestionRuns.get(run.id);
      setSelectedRun(detail);
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Failed to load run details', 'error');
      setDrawerOpen(false);
    } finally {
      setDrawerLoading(false);
    }
  };

  const clearFilters = () => {
    setTenantFilter('');
    setStatusFilter('');
    setScheduleFilter('');
    setStartedAfter('');
    setStartedBefore('');
    setPage(1);
  };

  const handleCancelRun = async (runId: string) => {
    try {
      await api.admin.ingestionRuns.cancel(runId);
      showToast('Cancellation signalled — worker will stop at next checkpoint', 'info');
      // Refresh both the open drawer detail and the list so the
      // CANCELLING badge appears immediately. The 5s auto-refresh
      // then catches the terminal CANCELLED transition.
      try {
        const detail = await api.admin.ingestionRuns.get(runId);
        setSelectedRun(detail);
      } catch {
        // Drawer refresh is best-effort; the list auto-refresh
        // will surface the new state regardless.
      }
      await fetchRuns();
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Failed to cancel run', 'error');
      throw err;
    }
  };

  const handleDeleteFile = async (runId: string, fileId: string) => {
    try {
      const res = await api.admin.ingestionRuns.deleteFileData(fileId);
      showToast(
        `Deleted ${res.rows_deleted} row(s); this day can be re-pulled from SFTP`,
        'success',
      );
      // Refresh the open drawer (the file's row is gone) and the list.
      try {
        const detail = await api.admin.ingestionRuns.get(runId);
        setSelectedRun(detail);
      } catch {
        // Best-effort; list auto-refresh will reconcile.
      }
      await fetchRuns();
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Failed to delete data', 'error');
      throw err;
    }
  };

  const handleReingestFile = async (_runId: string, fileId: string) => {
    try {
      await api.admin.ingestionRuns.reingestFile(fileId);
      showToast('Re-ingest queued — a new run will appear shortly', 'info');
      // The new REINGEST run is RUNNING; fetching now surfaces it and
      // arms the 5s auto-refresh to track it to completion.
      await fetchRuns();
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Failed to queue re-ingest', 'error');
      throw err;
    }
  };

  return (
    <Box>
      <PageHeader
        title="Ingestion Runs"
        subtitle="History of scheduled and manual SFTP-driven ingestion runs"
        breadcrumbs={[{ label: 'Admin' }, { label: 'Ingestion Runs' }]}
        actions={
          <Stack direction="row" spacing={1} alignItems="center">
            {autoRefreshActive && (
              <Chip
                size="small"
                variant="outlined"
                icon={<CircularProgress size={12} thickness={5} />}
                label="Auto-refreshing"
              />
            )}
            <Button
              size="small"
              variant="outlined"
              startIcon={<Refresh />}
              onClick={() => { setLoading(true); fetchRuns().finally(() => setLoading(false)); }}
            >
              Refresh
            </Button>
          </Stack>
        }
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap alignItems="center">
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Tenant</InputLabel>
            <Select
              value={tenantFilter}
              label="Tenant"
              onChange={e => { setTenantFilter(e.target.value); setPage(1); }}
            >
              <MenuItem value="">All Tenants</MenuItem>
              <MenuItem value="jy">JY</MenuItem>
              <MenuItem value="pw">PW</MenuItem>
              <MenuItem value="fjl">FJL</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Status</InputLabel>
            <Select
              value={statusFilter}
              label="Status"
              onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
            >
              <MenuItem value="">All</MenuItem>
              <MenuItem value="RUNNING">RUNNING</MenuItem>
              <MenuItem value="SUCCESS">SUCCESS</MenuItem>
              <MenuItem value="PARTIAL">PARTIAL</MenuItem>
              <MenuItem value="FAILED">FAILED</MenuItem>
              <MenuItem value="CANCELLING">CANCELLING</MenuItem>
              <MenuItem value="CANCELLED">CANCELLED</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 240 }}>
            <InputLabel>Schedule</InputLabel>
            <Select
              value={scheduleFilter}
              label="Schedule"
              onChange={e => { setScheduleFilter(e.target.value); setPage(1); }}
            >
              <MenuItem value="">All schedules</MenuItem>
              {schedules.map(s => (
                <MenuItem key={s.id} value={s.id}>
                  {s.tenant_code} {s.domain} · {s.cron_expression}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            label="Started after"
            type="datetime-local"
            value={startedAfter}
            onChange={e => { setStartedAfter(e.target.value); setPage(1); }}
            size="small"
            InputLabelProps={{ shrink: true }}
            sx={{ minWidth: 200 }}
          />
          <TextField
            label="Started before"
            type="datetime-local"
            value={startedBefore}
            onChange={e => { setStartedBefore(e.target.value); setPage(1); }}
            size="small"
            InputLabelProps={{ shrink: true }}
            sx={{ minWidth: 200 }}
          />
          <Box sx={{ flexGrow: 1 }} />
          <Button size="small" onClick={clearFilters}>Clear filters</Button>
        </Stack>
      </Paper>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      ) : runs.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="h6" color="text.secondary">No runs yet</Typography>
          <Typography variant="body2" color="text.secondary">
            Runs appear here when a schedule fires or when an admin clicks Run Now.
          </Typography>
        </Paper>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="Ingestion runs">
            <TableHead>
              <TableRow>
                <TableCell>Status</TableCell>
                <TableCell>Tenant</TableCell>
                <TableCell>Schedule</TableCell>
                <TableCell>Started</TableCell>
                <TableCell>Duration</TableCell>
                <TableCell>Seen / Pulled</TableCell>
                <TableCell>Committed</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {runs.map(run => {
                const schedLabel = scheduleNameForId(run.schedule_id);
                const committedMismatch = run.jobs_committed !== run.files_pulled;
                return (
                  <TableRow
                    key={run.id}
                    hover
                    onClick={() => openDetail(run)}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell>
                      <Chip
                        label={run.status}
                        size="small"
                        color={statusColor(run.status)}
                        icon={
                          run.status === 'RUNNING'
                            ? <CircularProgress size={14} thickness={5} sx={{ ml: 0.5 }} />
                            : undefined
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Chip label={run.tenant_code ?? '?'} size="small" />
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                      {schedLabel ?? (run.schedule_id === null
                        ? <em>(orphan)</em>
                        : <em>(deleted)</em>)}
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption">
                        {new Date(run.started_at).toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {run.status === 'RUNNING' && !run.finished_at
                        ? 'running…'
                        : formatDuration(run.started_at, run.finished_at)}
                    </TableCell>
                    <TableCell>
                      {run.files_seen} / {run.files_pulled}
                    </TableCell>
                    <TableCell sx={{
                      bgcolor: committedMismatch ? 'warning.lighter' : undefined,
                      color: committedMismatch ? 'warning.dark' : undefined,
                    }}>
                      {run.jobs_committed}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          {pageInfo && (
            <TablePagination
              component="div"
              count={pageInfo.total}
              page={page - 1}
              onPageChange={(_, newPage) => setPage(newPage + 1)}
              rowsPerPage={pageSize}
              onRowsPerPageChange={e => {
                setPageSize(parseInt(e.target.value, 10));
                setPage(1);
              }}
              rowsPerPageOptions={[10, 20, 50, 100]}
            />
          )}
        </TableContainer>
      )}

      <DetailDrawer
        open={drawerOpen}
        run={selectedRun}
        loading={drawerLoading}
        scheduleLookup={scheduleNameForId}
        onClose={() => setDrawerOpen(false)}
        showToast={showToast}
        onCancelRequest={handleCancelRun}
        onDeleteFile={handleDeleteFile}
        onReingestFile={handleReingestFile}
      />

      <Snackbar
        open={toast.open}
        autoHideDuration={6000}
        onClose={() => setToast(prev => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          severity={toast.severity}
          onClose={() => setToast(prev => ({ ...prev, open: false }))}
          sx={{ width: '100%' }}
        >
          {toast.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
