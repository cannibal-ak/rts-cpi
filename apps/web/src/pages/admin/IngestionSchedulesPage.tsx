/**
 * Ingestion Schedules admin page (Phase 4.3).
 *
 * Lists / creates / edits / deletes / enables / disables / triggers
 * cron-driven SFTP-pull schedules. Skywave platform admins only —
 * gated at the route level via ProtectedRoute and again inside the
 * component via ``isSuperAdmin(session)`` for the direct-URL
 * fall-through.
 *
 * The status column surfaces redbeat drift (``is_enabled === true``
 * but ``redbeat_registered === false``) as an amber warning icon —
 * this can happen briefly after a 502 RedbeatSyncError or while a
 * lifespan reconcile catches up.
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, TablePagination, Chip, IconButton, Button, Stack,
  FormControl, InputLabel, Select, MenuItem, CircularProgress, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions,
  TextField, Switch, FormControlLabel, Snackbar, Alert,
  Radio, RadioGroup, FormLabel,
} from '@mui/material';
import {
  Add, Edit, PlayArrow, Pause, Send, DeleteOutline, Refresh,
  CheckCircle, Warning,
} from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import { api } from '../../api';
import type { ApiErrorShape } from '../../api/httpClient';
import { useSession } from '../../context/SessionContext';
import { isSuperAdmin } from '../../utils/access';
import { validateCron } from '../../utils/cron';
import { KNOWN_REGEXES } from '../../mock/sftpAdminMock';
import type {
  SftpConnection,
  IngestionSchedule,
  IngestionScheduleCreate,
  IngestionScheduleUpdate,
  IngestionDomain,
  PageInfo,
  RunNowScope,
} from '../../types';


interface ToastState {
  open: boolean;
  message: string;
  severity: 'success' | 'error' | 'info' | 'warning';
}


const DEFAULT_PAGE_SIZE = 20;

const DOMAIN_COLORS: Record<IngestionDomain, 'primary' | 'secondary' | 'default'> = {
  AIRLINE: 'primary',
  VELOCITY: 'secondary',
  CFL: 'default',
};

const REGEX_OPTIONS: Array<{ value: string; label: string; domain: IngestionDomain }> = [
  { value: KNOWN_REGEXES.jy_airline, label: 'JY AIRLINE — JY_DDMMYY.xlsx', domain: 'AIRLINE' },
  { value: KNOWN_REGEXES.jy_velocity, label: 'JY VELOCITY — JYVelocityData_DD.MM.YYYY.csv', domain: 'VELOCITY' },
  { value: KNOWN_REGEXES.pw_airline, label: 'PW AIRLINE — PW_DDMMYY.csv', domain: 'AIRLINE' },
  { value: KNOWN_REGEXES.pw_velocity, label: 'PW VELOCITY — PWVelocityData_DD.MM.YYYY.csv', domain: 'VELOCITY' },
  { value: KNOWN_REGEXES.fjl_cfl, label: 'FJL CFL — FJL_DDMMYY.csv', domain: 'CFL' },
];


// ─── Create / Edit dialog ───────────────────────────────────

interface FormState {
  tenant_code: string;
  sftp_connection_id: string;
  cron_expression: string;
  timezone: string;
  domain: IngestionDomain;
  filename_regex: string;
  replace_existing: boolean;
  is_enabled: boolean;
}

const emptyForm = (): FormState => ({
  tenant_code: '',
  sftp_connection_id: '',
  cron_expression: '0 3 * * *',
  timezone: 'UTC',
  domain: 'AIRLINE',
  filename_regex: '',
  replace_existing: false,
  is_enabled: true,
});

const formFromSchedule = (s: IngestionSchedule): FormState => ({
  tenant_code: s.tenant_code,
  sftp_connection_id: s.sftp_connection_id,
  cron_expression: s.cron_expression,
  timezone: s.timezone,
  domain: s.domain,
  filename_regex: s.filename_regex,
  replace_existing: s.replace_existing,
  is_enabled: s.is_enabled,
});


interface ScheduleDialogProps {
  open: boolean;
  mode: 'create' | 'edit';
  initial: IngestionSchedule | null;
  connections: SftpConnection[];
  onClose: () => void;
  onSaved: () => void;
  showToast: (message: string, severity: ToastState['severity']) => void;
}

function ScheduleDialog({
  open, mode, initial, connections, onClose, onSaved, showToast,
}: ScheduleDialogProps) {
  const [form, setForm] = useState<FormState>(emptyForm());
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setForm(mode === 'edit' && initial ? formFromSchedule(initial) : emptyForm());
  }, [open, mode, initial]);

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm(prev => ({ ...prev, [key]: value }));
  };

  const cronCheck = validateCron(form.cron_expression);
  const inEdit = mode === 'edit';

  const submit = async () => {
    if (!cronCheck.valid) {
      showToast(`Invalid cron: ${cronCheck.error}`, 'error');
      return;
    }
    setSubmitting(true);
    try {
      if (mode === 'create') {
        const body: IngestionScheduleCreate = {
          tenant_code: form.tenant_code.trim(),
          sftp_connection_id: form.sftp_connection_id,
          cron_expression: form.cron_expression.trim(),
          timezone: form.timezone.trim() || 'UTC',
          is_enabled: form.is_enabled,
          domain: form.domain,
          filename_regex: form.filename_regex,
          replace_existing: form.replace_existing,
        };
        await api.admin.ingestionSchedules.create(body);
        showToast('Schedule created', 'success');
      } else {
        if (!initial) throw new Error('edit mode without initial');
        const body: IngestionScheduleUpdate = {
          sftp_connection_id: form.sftp_connection_id !== initial.sftp_connection_id
            ? form.sftp_connection_id : undefined,
          cron_expression: form.cron_expression.trim() !== initial.cron_expression
            ? form.cron_expression.trim() : undefined,
          timezone: form.timezone.trim() !== initial.timezone
            ? form.timezone.trim() : undefined,
          is_enabled: form.is_enabled !== initial.is_enabled
            ? form.is_enabled : undefined,
          domain: form.domain !== initial.domain ? form.domain : undefined,
          filename_regex: form.filename_regex !== initial.filename_regex
            ? form.filename_regex : undefined,
          replace_existing: form.replace_existing !== initial.replace_existing
            ? form.replace_existing : undefined,
        };
        await api.admin.ingestionSchedules.update(initial.id, body);
        showToast('Schedule updated', 'success');
      }
      onSaved();
      onClose();
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Save failed', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{inEdit ? 'Edit Schedule' : 'New Schedule'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Tenant Code"
            value={form.tenant_code}
            onChange={e => setField('tenant_code', e.target.value)}
            disabled={inEdit}
            helperText={inEdit
              ? 'Tenant cannot be changed; delete and recreate to move.'
              : 'e.g. jy, pw, fjl'}
            required
            fullWidth
            size="small"
          />
          <FormControl size="small" required fullWidth>
            <InputLabel>SFTP Connection</InputLabel>
            <Select
              value={form.sftp_connection_id}
              label="SFTP Connection"
              onChange={e => setField('sftp_connection_id', e.target.value)}
            >
              {connections.length === 0 && (
                <MenuItem value="" disabled>
                  No connections available — create one first
                </MenuItem>
              )}
              {connections.map(conn => (
                <MenuItem key={conn.id} value={conn.id}>
                  {conn.name} ({conn.tenant_code})
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Box>
            <TextField
              label="Cron Expression"
              value={form.cron_expression}
              onChange={e => setField('cron_expression', e.target.value)}
              required
              fullWidth
              size="small"
              error={!cronCheck.valid && form.cron_expression.trim() !== ''}
              helperText={
                !cronCheck.valid && form.cron_expression.trim() !== ''
                  ? cronCheck.error
                  : cronCheck.description ?? 'Custom schedule'
              }
              InputProps={{ sx: { fontFamily: 'monospace' } }}
            />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
              Examples: <code>0 3 * * *</code> (daily at 03:00) ·{' '}
              <code>30 4 * * 1</code> (Mondays at 04:30) ·{' '}
              <code>*/15 * * * *</code> (every 15 min)
            </Typography>
          </Box>
          <TextField
            label="Timezone"
            value={form.timezone}
            onChange={e => setField('timezone', e.target.value)}
            required
            fullWidth
            size="small"
            helperText="IANA timezone, e.g. UTC, Asia/Kolkata, America/New_York"
          />
          <FormControl size="small" required fullWidth>
            <InputLabel>Domain</InputLabel>
            <Select
              value={form.domain}
              label="Domain"
              onChange={e => setField('domain', e.target.value as IngestionDomain)}
            >
              <MenuItem value="AIRLINE">AIRLINE</MenuItem>
              <MenuItem value="VELOCITY">VELOCITY</MenuItem>
              <MenuItem value="CFL">CFL</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" required fullWidth>
            <InputLabel>Filename Pattern</InputLabel>
            <Select
              value={form.filename_regex}
              label="Filename Pattern"
              onChange={e => setField('filename_regex', e.target.value)}
            >
              {REGEX_OPTIONS.filter(o => o.domain === form.domain).map(opt => (
                <MenuItem key={opt.value} value={opt.value}>
                  {opt.label}
                </MenuItem>
              ))}
            </Select>
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
              (domain, regex) pair must match the server's YAML source.
              Filtered options shown for the chosen domain.
            </Typography>
          </FormControl>
          <FormControlLabel
            control={
              <Switch
                checked={form.replace_existing}
                onChange={e => setField('replace_existing', e.target.checked)}
              />
            }
            label="Replace existing"
          />
          <Typography variant="caption" color="text.secondary" sx={{ mt: -1 }}>
            Re-process files even if already ingested. Use only when upstream re-issues files.
          </Typography>
          <FormControlLabel
            control={
              <Switch
                checked={form.is_enabled}
                onChange={e => setField('is_enabled', e.target.checked)}
              />
            }
            label="Enabled"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={submitting}>Cancel</Button>
        <Button
          variant="contained"
          onClick={submit}
          disabled={submitting || !cronCheck.valid}
          startIcon={submitting ? <CircularProgress size={16} /> : undefined}
        >
          {inEdit ? 'Save Changes' : 'Create'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}


// ─── Page component ─────────────────────────────────────────

export default function IngestionSchedulesPage() {
  const { session } = useSession();

  const [schedules, setSchedules] = useState<IngestionSchedule[]>([]);
  const [pageInfo, setPageInfo] = useState<PageInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [connections, setConnections] = useState<SftpConnection[]>([]);

  const [tenantFilter, setTenantFilter] = useState<string>('');
  const [enabledFilter, setEnabledFilter] = useState<string>('');
  const [connectionFilter, setConnectionFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<IngestionSchedule | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<IngestionSchedule | null>(null);
  // Run-Now confirmation dialog state. `mode` mirrors the scope grammar
  // 1-for-1: 'today' / 'all' / 'date' (which combines with `dateValue`
  // YYYY-MM-DD into `date:DDMMYY` on submit).
  const [runNowTarget, setRunNowTarget] = useState<IngestionSchedule | null>(null);
  const [runNowMode, setRunNowMode] = useState<'today' | 'all' | 'date'>('today');
  const [runNowDate, setRunNowDate] = useState<string>(''); // YYYY-MM-DD
  const [pendingActions, setPendingActions] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<ToastState>({
    open: false, message: '', severity: 'info',
  });

  const showToast = useCallback((message: string, severity: ToastState['severity']) => {
    setToast({ open: true, message, severity });
  }, []);

  const fetchSchedules = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.admin.ingestionSchedules.list({
        page,
        page_size: pageSize,
        tenant_code: tenantFilter || undefined,
        is_enabled: enabledFilter === '' ? undefined : enabledFilter === 'true',
        sftp_connection_id: connectionFilter || undefined,
      });
      setSchedules(result.items);
      setPageInfo(result.page_info);
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Failed to load schedules', 'error');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, tenantFilter, enabledFilter, connectionFilter, showToast]);

  // Connections loaded once on mount (drives create-dialog dropdown
  // and the table's Connection column).
  useEffect(() => {
    (async () => {
      try {
        const result = await api.admin.sftpConnections.list({ page: 1, page_size: 100 });
        setConnections(result.items);
      } catch (err) {
        const e = err as Error & ApiErrorShape;
        showToast(`Failed to load SFTP connections: ${e.message}`, 'error');
      }
    })();
  }, [showToast]);

  useEffect(() => { fetchSchedules(); }, [fetchSchedules]);

  if (!isSuperAdmin(session)) {
    return (
      <Box>
        <PageHeader
          title="Ingestion Schedules"
          breadcrumbs={[{ label: 'Admin' }, { label: 'Ingestion Schedules' }]}
        />
        <Alert severity="warning" sx={{ mt: 2 }}>
          Skywave platform admin access required.
        </Alert>
      </Box>
    );
  }

  const markPending = (key: string, on: boolean) => {
    setPendingActions(prev => {
      const next = new Set(prev);
      if (on) next.add(key); else next.delete(key);
      return next;
    });
  };

  const handleEnable = async (sched: IngestionSchedule) => {
    const key = `enable:${sched.id}`;
    markPending(key, true);
    try {
      await api.admin.ingestionSchedules.enable(sched.id);
      showToast('Schedule enabled', 'success');
      await fetchSchedules();
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Enable failed', 'error');
    } finally {
      markPending(key, false);
    }
  };

  const handleDisable = async (sched: IngestionSchedule) => {
    const key = `disable:${sched.id}`;
    markPending(key, true);
    try {
      await api.admin.ingestionSchedules.disable(sched.id);
      showToast('Schedule disabled', 'success');
      await fetchSchedules();
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Disable failed', 'error');
    } finally {
      markPending(key, false);
    }
  };

  const openRunNow = (sched: IngestionSchedule) => {
    setRunNowTarget(sched);
    setRunNowMode('today');
    // Default the date field to today (local browser date) so a
    // user clicking "Specific date" doesn't see an empty picker.
    setRunNowDate(new Date().toISOString().slice(0, 10));
  };

  const closeRunNow = () => {
    setRunNowTarget(null);
  };

  // Convert a YYYY-MM-DD value from <input type="date"> into the
  // DDMMYY token the backend's scope grammar expects.
  const toDDMMYY = (yyyymmdd: string): string | null => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(yyyymmdd);
    if (!m) return null;
    return `${m[3]}${m[2]}${m[1].slice(2)}`;
  };

  const runNowScopeReady: { ok: true; scope: RunNowScope } | { ok: false; reason: string } = (() => {
    if (runNowMode === 'today') return { ok: true, scope: 'today' as const };
    if (runNowMode === 'all') return { ok: true, scope: 'all' as const };
    const ddmmyy = toDDMMYY(runNowDate);
    if (!ddmmyy) return { ok: false, reason: 'Pick a date.' };
    return { ok: true, scope: `date:${ddmmyy}` as RunNowScope };
  })();

  const handleConfirmRunNow = async () => {
    if (!runNowTarget) return;
    if (!runNowScopeReady.ok) return;
    const sched = runNowTarget;
    const scope = runNowScopeReady.scope;
    const key = `runNow:${sched.id}`;
    markPending(key, true);
    try {
      const result = await api.admin.ingestionSchedules.runNow(sched.id, { scope });
      const scopeLabel = scope === 'today'
        ? "today's file"
        : scope === 'all'
          ? 'all files'
          : `date ${scope.slice(5)}`;
      showToast(
        `Run dispatched (${scopeLabel}). Task ID: ${result.task_id.slice(0, 8)}…  ` +
        `Visible in Ingestion Runs in a few seconds.`,
        'info',
      );
      closeRunNow();
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Run-now failed', 'error');
    } finally {
      markPending(key, false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    const key = `delete:${deleteTarget.id}`;
    markPending(key, true);
    try {
      await api.admin.ingestionSchedules.delete(deleteTarget.id);
      showToast('Schedule deleted', 'success');
      setDeleteTarget(null);
      await fetchSchedules();
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Delete failed', 'error');
    } finally {
      markPending(key, false);
    }
  };

  const connectionName = (id: string): string | null => {
    const conn = connections.find(c => c.id === id);
    return conn?.name ?? null;
  };

  return (
    <Box>
      <PageHeader
        title="Ingestion Schedules"
        subtitle="Cron-driven SFTP pulls per tenant + domain"
        breadcrumbs={[{ label: 'Admin' }, { label: 'Ingestion Schedules' }]}
        actions={
          <Stack direction="row" spacing={1}>
            <Button
              size="small"
              variant="contained"
              color="primary"
              startIcon={<Add />}
              onClick={() => setCreateOpen(true)}
            >
              New Schedule
            </Button>
            <Button
              size="small"
              variant="outlined"
              startIcon={<Refresh />}
              onClick={fetchSchedules}
            >
              Refresh
            </Button>
          </Stack>
        }
      />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel>Tenant</InputLabel>
            <Select
              value={tenantFilter}
              label="Tenant"
              onChange={e => { setTenantFilter(e.target.value); setPage(1); }}
            >
              <MenuItem value="">All Tenants</MenuItem>
              <MenuItem value="jy">JY (Airline)</MenuItem>
              <MenuItem value="pw">PW (Airline)</MenuItem>
              <MenuItem value="fjl">FJL (Cruise/Ferry)</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel>Status</InputLabel>
            <Select
              value={enabledFilter}
              label="Status"
              onChange={e => { setEnabledFilter(e.target.value); setPage(1); }}
            >
              <MenuItem value="">All</MenuItem>
              <MenuItem value="true">Enabled only</MenuItem>
              <MenuItem value="false">Disabled only</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 220 }}>
            <InputLabel>Connection</InputLabel>
            <Select
              value={connectionFilter}
              label="Connection"
              onChange={e => { setConnectionFilter(e.target.value); setPage(1); }}
            >
              <MenuItem value="">All connections</MenuItem>
              {connections.map(conn => (
                <MenuItem key={conn.id} value={conn.id}>
                  {conn.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>
      </Paper>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      ) : schedules.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="h6" color="text.secondary">No schedules</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Create one to start pulling files on a cron.
          </Typography>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setCreateOpen(true)}
            disabled={connections.length === 0}
          >
            New Schedule
          </Button>
          {connections.length === 0 && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              Create an SFTP connection first.
            </Typography>
          )}
        </Paper>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="Ingestion schedules">
            <TableHead>
              <TableRow>
                <TableCell>Tenant</TableCell>
                <TableCell>Connection</TableCell>
                <TableCell>Domain</TableCell>
                <TableCell>Cron</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Last Run</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {schedules.map(sched => {
                const cronInfo = validateCron(sched.cron_expression);
                const connName = connectionName(sched.sftp_connection_id);
                const drift = sched.is_enabled && !sched.redbeat_registered;
                const enableKey = `enable:${sched.id}`;
                const disableKey = `disable:${sched.id}`;
                const runKey = `runNow:${sched.id}`;
                const deleteKey = `delete:${sched.id}`;
                return (
                  <TableRow key={sched.id} hover>
                    <TableCell>
                      <Chip label={sched.tenant_code} size="small" />
                    </TableCell>
                    <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
                      {connName ?? <em>(unknown)</em>}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={sched.domain}
                        size="small"
                        color={DOMAIN_COLORS[sched.domain]}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>
                      <Tooltip title={cronInfo.description ?? 'Custom schedule'}>
                        <Typography
                          variant="body2"
                          sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
                        >
                          {sched.cron_expression}
                        </Typography>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        <Chip
                          label={sched.is_enabled ? 'Enabled' : 'Disabled'}
                          size="small"
                          color={sched.is_enabled ? 'success' : 'default'}
                        />
                        {sched.is_enabled && (
                          drift ? (
                            <Tooltip title="Drift: enabled but not registered with the scheduler. Wait for the next reconcile or restart api.">
                              <Warning fontSize="small" color="warning" />
                            </Tooltip>
                          ) : (
                            <Tooltip title="Registered with scheduler">
                              <CheckCircle fontSize="small" color="success" />
                            </Tooltip>
                          )
                        )}
                      </Stack>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption">
                        {sched.last_run_at
                          ? new Date(sched.last_run_at).toLocaleString()
                          : 'Never'}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                        <Tooltip title="Edit">
                          <span>
                            <IconButton size="small" onClick={() => setEditTarget(sched)}>
                              <Edit fontSize="small" />
                            </IconButton>
                          </span>
                        </Tooltip>
                        {sched.is_enabled ? (
                          <Tooltip title="Disable">
                            <span>
                              <IconButton
                                size="small"
                                onClick={() => handleDisable(sched)}
                                disabled={pendingActions.has(disableKey)}
                              >
                                {pendingActions.has(disableKey)
                                  ? <CircularProgress size={16} />
                                  : <Pause fontSize="small" />}
                              </IconButton>
                            </span>
                          </Tooltip>
                        ) : (
                          <Tooltip title="Enable">
                            <span>
                              <IconButton
                                size="small"
                                onClick={() => handleEnable(sched)}
                                disabled={pendingActions.has(enableKey)}
                              >
                                {pendingActions.has(enableKey)
                                  ? <CircularProgress size={16} />
                                  : <PlayArrow fontSize="small" />}
                              </IconButton>
                            </span>
                          </Tooltip>
                        )}
                        <Tooltip
                          title={sched.is_enabled ? 'Run now…' : 'Enable schedule first'}
                        >
                          <span>
                            <IconButton
                              size="small"
                              onClick={() => openRunNow(sched)}
                              disabled={!sched.is_enabled || pendingActions.has(runKey)}
                            >
                              {pendingActions.has(runKey)
                                ? <CircularProgress size={16} />
                                : <Send fontSize="small" />}
                            </IconButton>
                          </span>
                        </Tooltip>
                        <Tooltip title="Delete">
                          <span>
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => setDeleteTarget(sched)}
                              disabled={pendingActions.has(deleteKey)}
                            >
                              {pendingActions.has(deleteKey)
                                ? <CircularProgress size={16} />
                                : <DeleteOutline fontSize="small" />}
                            </IconButton>
                          </span>
                        </Tooltip>
                      </Stack>
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

      <ScheduleDialog
        open={createOpen}
        mode="create"
        initial={null}
        connections={connections}
        onClose={() => setCreateOpen(false)}
        onSaved={fetchSchedules}
        showToast={showToast}
      />
      <ScheduleDialog
        open={editTarget !== null}
        mode="edit"
        initial={editTarget}
        connections={connections}
        onClose={() => setEditTarget(null)}
        onSaved={fetchSchedules}
        showToast={showToast}
      />

      <Dialog
        open={runNowTarget !== null}
        onClose={closeRunNow}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Run schedule now</DialogTitle>
        <DialogContent>
          {runNowTarget && (
            <Stack spacing={2} sx={{ mt: 0.5 }}>
              <Typography variant="body2" color="text.secondary">
                {runNowTarget.tenant_code} · {runNowTarget.domain} ·{' '}
                <Box component="span" sx={{ fontFamily: 'monospace' }}>
                  {runNowTarget.filename_regex}
                </Box>
              </Typography>
              <FormControl>
                <FormLabel>Which files should this run pull?</FormLabel>
                <RadioGroup
                  value={runNowMode}
                  onChange={e => setRunNowMode(e.target.value as 'today' | 'all' | 'date')}
                >
                  <FormControlLabel
                    value="today"
                    control={<Radio size="small" />}
                    label="Today's file only (default)"
                  />
                  <FormControlLabel
                    value="date"
                    control={<Radio size="small" />}
                    label="Specific date"
                  />
                  <FormControlLabel
                    value="all"
                    control={<Radio size="small" />}
                    label="All files (backfill)"
                  />
                </RadioGroup>
              </FormControl>
              {runNowMode === 'date' && (
                <TextField
                  size="small"
                  type="date"
                  label="Target date"
                  InputLabelProps={{ shrink: true }}
                  value={runNowDate}
                  onChange={e => setRunNowDate(e.target.value)}
                  helperText={
                    runNowDate
                      ? `Sent as scope=date:${toDDMMYY(runNowDate) ?? '??????'}`
                      : 'Pick a date to filter on.'
                  }
                />
              )}
              {runNowMode === 'all' && (
                <Alert severity="warning" variant="outlined">
                  Backfill mode scans every file in the SFTP folder that
                  matches the regex. Existing files are skipped by SHA-256
                  dedup, but the scan itself can be slow on large folders.
                </Alert>
              )}
              <Typography variant="caption" color="text.secondary">
                Resolved scope:{' '}
                <Box component="span" sx={{ fontFamily: 'monospace' }}>
                  {runNowScopeReady.ok ? runNowScopeReady.scope : '—'}
                </Box>
              </Typography>
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={closeRunNow}
            disabled={
              runNowTarget !== null &&
              pendingActions.has(`runNow:${runNowTarget.id}`)
            }
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleConfirmRunNow}
            disabled={
              !runNowScopeReady.ok ||
              (runNowTarget !== null &&
                pendingActions.has(`runNow:${runNowTarget.id}`))
            }
            startIcon={
              runNowTarget !== null &&
              pendingActions.has(`runNow:${runNowTarget.id}`)
                ? <CircularProgress size={16} />
                : <Send fontSize="small" />
            }
          >
            Run
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={deleteTarget !== null} onClose={() => setDeleteTarget(null)}>
        <DialogTitle>Delete schedule?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This will permanently delete the schedule and unregister it from
            the scheduler. Past ingestion runs will be retained but their
            schedule reference will be cleared.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
          <Button
            color="error"
            variant="contained"
            onClick={handleConfirmDelete}
            disabled={
              deleteTarget !== null &&
              pendingActions.has(`delete:${deleteTarget.id}`)
            }
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>

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
