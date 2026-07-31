import React, { useState, useEffect } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Chip, IconButton, Drawer, Divider, Stack, Button,
  FormControl, InputLabel, Select, MenuItem, CircularProgress, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions,
  Snackbar, Alert,
} from '@mui/material';
import {
  CloudUpload, Visibility, Close, Refresh,
  PlayArrow, CheckCircle, DeleteOutline, DeleteForever,
} from '@mui/icons-material';
import { Link as RouterLink } from 'react-router-dom';
import PageHeader from '../../components/common/PageHeader';
import StatusChip from '../../components/common/StatusChip';
import KpiTiles from '../../components/common/KpiTiles';
import { api } from '../../api';
import type { ApiErrorShape } from '../../api/httpClient';
import { useSession } from '../../context/SessionContext';
import { isSuperAdmin } from '../../utils/access';
import type { IngestionJob, IngestionStatus, Paginated } from '../../types';

const TENANT_COLORS: Record<string, 'primary' | 'secondary' | 'info' | 'default'> = {
  JY: 'primary',
  PW: 'secondary',
  FJL: 'info',
};

const STATUS_OPTIONS: IngestionStatus[] = [
  'STAGED', 'VALIDATING', 'VALIDATED', 'COMMITTING', 'COMMITTED',
  'REJECTED', 'REPLACED', 'FAILED', 'DELETED',
];

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

interface ConflictPrompt {
  jobId: string;
  jobLabel: string;
  existingJobId: string;
  message: string;
}

interface CancelPrompt {
  jobId: string;
  jobLabel: string;
}

interface DeletePrompt {
  jobId: string;
  jobLabel: string;
  rowCount: number | null;
}

interface SnackbarState {
  open: boolean;
  message: string;
  severity: 'success' | 'error' | 'info' | 'warning';
}

export default function IngestionJobsPage() {
  const { session } = useSession();
  const adminOnly = isSuperAdmin(session);

  const [jobs, setJobs] = useState<Paginated<IngestionJob> | null>(null);
  const [loading, setLoading] = useState(true);
  const [domainFilter, setDomainFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [tenantFilter, setTenantFilter] = useState('');
  const [selectedJob, setSelectedJob] = useState<IngestionJob | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [pendingActions, setPendingActions] = useState<Set<string>>(new Set());
  const [conflict, setConflict] = useState<ConflictPrompt | null>(null);
  const [cancelPrompt, setCancelPrompt] = useState<CancelPrompt | null>(null);
  const [deletePrompt, setDeletePrompt] = useState<DeletePrompt | null>(null);
  const [snackbar, setSnackbar] = useState<SnackbarState>({ open: false, message: '', severity: 'info' });

  const showToast = (message: string, severity: SnackbarState['severity'] = 'info') => {
    setSnackbar({ open: true, message, severity });
  };

  const fetchJobs = async () => {
    setLoading(true);
    const q: Record<string, string> = {};
    if (domainFilter) q.domain = domainFilter;
    if (statusFilter) q.status = statusFilter;
    if (tenantFilter) q.tenant_code = tenantFilter;
    const result = await api.ingestion.listJobs(q);
    setJobs(result);
    setLoading(false);
  };

  useEffect(() => { fetchJobs(); }, [domainFilter, statusFilter, tenantFilter]);

  const refreshSelected = async (id: string) => {
    try {
      const detail = await api.ingestion.getJob(id);
      if (detail) setSelectedJob(detail);
    } catch { /* drawer remains stale until next reload */ }
  };

  const openDetail = async (job: IngestionJob) => {
    const detail = await api.ingestion.getJob(job.id);
    setSelectedJob(detail);
    setDrawerOpen(true);
  };

  const markPending = (id: string, on: boolean) => {
    setPendingActions(prev => {
      const next = new Set(prev);
      if (on) next.add(id); else next.delete(id);
      return next;
    });
  };

  const jobLabel = (j: IngestionJob): string =>
    `${j.tenant_code} ${j.domain} ${j.file_date} (${j.filename})`;

  const handleValidate = async (job: IngestionJob) => {
    markPending(job.id, true);
    try {
      const r = await api.ingestion.validate(job.id);
      showToast(
        `Validated ${jobLabel(job)} — ${r.row_count_valid}/${r.row_count_total} valid` +
          (r.row_count_rejected ? `, ${r.row_count_rejected} rejected` : ''),
        r.row_count_rejected > 0 ? 'warning' : 'success'
      );
      await fetchJobs();
      await refreshSelected(job.id);
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Validation failed', 'error');
    } finally {
      markPending(job.id, false);
    }
  };

  const performCommit = async (job: IngestionJob, replaceExisting: boolean) => {
    markPending(job.id, true);
    try {
      const r = await api.ingestion.commit(job.id, replaceExisting);
      showToast(
        `Committed ${jobLabel(job)} — ${r.rows_inserted.toLocaleString()} rows` +
          (r.replaced_job_id ? ` (replaced ${r.replaced_job_id.slice(0, 8)}…)` : ''),
        'success'
      );
      setConflict(null);
      await fetchJobs();
      await refreshSelected(job.id);
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      if (e.status === 409 && e.errorCode === 'ingestion_conflict') {
        const existingId = (e.details?.existing_job_id as string | undefined) || '';
        setConflict({
          jobId: job.id,
          jobLabel: jobLabel(job),
          existingJobId: existingId,
          message: e.message,
        });
      } else {
        showToast(e.message || 'Commit failed', 'error');
      }
    } finally {
      markPending(job.id, false);
    }
  };

  const handleCommit = (job: IngestionJob) => performCommit(job, false);
  const handleReplaceConfirm = async () => {
    if (!conflict) return;
    const job = (jobs?.items || []).find(j => j.id === conflict.jobId);
    if (!job) {
      setConflict(null);
      return;
    }
    await performCommit(job, true);
  };

  const handleCancel = async (jobId: string) => {
    markPending(jobId, true);
    try {
      await api.ingestion.cancel(jobId);
      showToast('Job cancelled', 'success');
      await fetchJobs();
      if (selectedJob?.id === jobId) await refreshSelected(jobId);
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Cancel failed', 'error');
    } finally {
      markPending(jobId, false);
      setCancelPrompt(null);
    }
  };

  const handleDeleteData = async (jobId: string) => {
    markPending(jobId, true);
    try {
      const r = await api.ingestion.deleteData(jobId);
      showToast(
        `Deleted ${r.rows_deleted.toLocaleString()} rows from the database`,
        'success'
      );
      await fetchJobs();
      if (selectedJob?.id === jobId) await refreshSelected(jobId);
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      showToast(e.message || 'Delete failed', 'error');
    } finally {
      markPending(jobId, false);
      setDeletePrompt(null);
    }
  };

  const allJobs = jobs?.items || [];
  const staged = allJobs.filter(j => j.status === 'STAGED').length;
  const validated = allJobs.filter(j => j.status === 'VALIDATED').length;
  const committed = allJobs.filter(j => j.status === 'COMMITTED').length;
  const failedOrRejected = allJobs.filter(j => j.status === 'FAILED' || j.status === 'REJECTED').length;

  // Renders the per-row inline action buttons. Buttons match the job's
  // current lifecycle position; transitional states (VALIDATING / COMMITTING)
  // surface a spinner instead.
  const renderRowActions = (job: IngestionJob, onCloseDrawer?: () => void) => {
    if (!adminOnly) return null;
    const busy = pendingActions.has(job.id);
    const transitional = job.status === 'VALIDATING' || job.status === 'COMMITTING';
    if (busy || transitional) {
      return <CircularProgress size={18} />;
    }

    const buttons: React.ReactNode[] = [];
    if (job.status === 'STAGED') {
      buttons.push(
        <Tooltip key="validate" title="Run validation on this staged file">
          <Button
            size="small"
            variant="contained"
            color="primary"
            startIcon={<PlayArrow />}
            onClick={(e) => { e.stopPropagation(); handleValidate(job); }}
          >
            Validate
          </Button>
        </Tooltip>
      );
    }
    if (job.status === 'VALIDATED') {
      buttons.push(
        <Tooltip key="commit" title="Commit valid rows to fact tables">
          <Button
            size="small"
            variant="contained"
            color="success"
            startIcon={<CheckCircle />}
            onClick={(e) => { e.stopPropagation(); handleCommit(job); }}
          >
            Commit
          </Button>
        </Tooltip>
      );
    }
    if (job.status === 'STAGED' || job.status === 'VALIDATED') {
      buttons.push(
        <Tooltip key="cancel" title="Cancel this job; deletes the staged file">
          <Button
            size="small"
            variant="outlined"
            color="error"
            startIcon={<DeleteOutline />}
            onClick={(e) => {
              e.stopPropagation();
              setCancelPrompt({ jobId: job.id, jobLabel: jobLabel(job) });
              if (onCloseDrawer) onCloseDrawer();
            }}
          >
            Cancel
          </Button>
        </Tooltip>
      );
    }
    if (job.status === 'COMMITTED' && job.deletable) {
      buttons.push(
        <Tooltip key="delete" title="Delete this file's committed rows from the database">
          <Button
            size="small"
            variant="outlined"
            color="error"
            startIcon={<DeleteForever />}
            onClick={(e) => {
              e.stopPropagation();
              setDeletePrompt({
                jobId: job.id,
                jobLabel: jobLabel(job),
                rowCount: job.row_count_valid ?? job.row_count_total,
              });
              if (onCloseDrawer) onCloseDrawer();
            }}
          >
            Delete
          </Button>
        </Tooltip>
      );
    }
    if (buttons.length === 0) {
      return <Typography variant="caption" color="text.disabled">—</Typography>;
    }
    return (
      <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', gap: 0.5 }}>
        {buttons}
      </Stack>
    );
  };

  return (
    <Box>
      <PageHeader
        title="Ingestion Jobs"
        subtitle="Track staged uploads through validate → commit"
        breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Ingestion Jobs' }]}
        actions={
          <Stack direction="row" spacing={1}>
            {adminOnly && (
              <Button
                size="small"
                variant="contained"
                color="primary"
                startIcon={<CloudUpload />}
                component={RouterLink}
                to="/ingestion/upload"
              >
                Upload Files
              </Button>
            )}
            <Button size="small" variant="outlined" startIcon={<Refresh />} onClick={fetchJobs}>Refresh</Button>
          </Stack>
        }
      />

      <KpiTiles tiles={[
        { label: 'Staged', value: staged, sub: 'awaiting validation' },
        { label: 'Validated', value: validated, sub: 'ready to commit' },
        { label: 'Committed', value: committed, color: 'success.main' },
        { label: 'Failed / Rejected', value: failedOrRejected, color: failedOrRejected > 0 ? 'error.main' : undefined },
      ]} />

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={2}>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Tenant</InputLabel>
            <Select value={tenantFilter} label="Tenant" onChange={e => setTenantFilter(e.target.value)}>
              <MenuItem value="">All Tenants</MenuItem>
              <MenuItem value="JY">JY (Airline)</MenuItem>
              <MenuItem value="PW">PW (Airline)</MenuItem>
              <MenuItem value="FJL">FJL (Cruise/Ferry)</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Domain</InputLabel>
            <Select value={domainFilter} label="Domain" onChange={e => setDomainFilter(e.target.value)}>
              <MenuItem value="">All</MenuItem>
              <MenuItem value="AIRLINE">Airline</MenuItem>
              <MenuItem value="VELOCITY">Velocity</MenuItem>
              <MenuItem value="CFL">CFL</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel>Status</InputLabel>
            <Select value={statusFilter} label="Status" onChange={e => setStatusFilter(e.target.value)}>
              <MenuItem value="">All</MenuItem>
              {STATUS_OPTIONS.map(s => (
                <MenuItem key={s} value={s}>{s}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Stack>
      </Paper>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>
      ) : allJobs.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
          <CloudUpload sx={{ fontSize: 48, color: 'text.secondary', mb: 1 }} />
          <Typography variant="h6" color="text.secondary">No ingestion jobs yet</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Upload a file to stage your first ingestion job.
          </Typography>
          {adminOnly && (
            <Button
              variant="contained"
              startIcon={<CloudUpload />}
              component={RouterLink}
              to="/ingestion/upload"
            >
              Upload Files
            </Button>
          )}
        </Paper>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="Ingestion jobs">
            <TableHead>
              <TableRow>
                <TableCell>Job ID</TableCell>
                <TableCell>Tenant</TableCell>
                <TableCell>Filename</TableCell>
                <TableCell>Domain</TableCell>
                <TableCell>File Date</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Total</TableCell>
                <TableCell align="right">Valid</TableCell>
                <TableCell align="right">Rejected</TableCell>
                <TableCell>Uploaded</TableCell>
                <TableCell>Actions</TableCell>
                <TableCell align="center">Details</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {allJobs.map(job => (
                <TableRow key={job.id} hover sx={{ cursor: 'pointer' }} onClick={() => openDetail(job)}>
                  <TableCell><Typography variant="caption" fontFamily="monospace">{job.id.slice(0, 8)}…</Typography></TableCell>
                  <TableCell>
                    <Chip
                      label={job.tenant_code || '—'}
                      size="small"
                      color={TENANT_COLORS[job.tenant_code] || 'default'}
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell>
                    <Tooltip title={job.filename}>
                      <Typography variant="body2" fontWeight={600} sx={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {job.filename}
                      </Typography>
                    </Tooltip>
                  </TableCell>
                  <TableCell><Chip label={job.domain} size="small" variant="outlined" /></TableCell>
                  <TableCell><Typography variant="caption">{job.file_date}</Typography></TableCell>
                  <TableCell><StatusChip status={job.status} /></TableCell>
                  <TableCell align="right">{job.row_count_total?.toLocaleString() ?? '—'}</TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" color="success.main">{job.row_count_valid?.toLocaleString() ?? '—'}</Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" color={(job.row_count_rejected ?? 0) > 0 ? 'error.main' : 'text.primary'}>
                      {job.row_count_rejected?.toLocaleString() ?? '—'}
                    </Typography>
                  </TableCell>
                  <TableCell><Typography variant="caption">{new Date(job.uploaded_at).toLocaleString()}</Typography></TableCell>
                  <TableCell sx={{ minWidth: 220 }}>{renderRowActions(job)}</TableCell>
                  <TableCell align="center">
                    <Tooltip title="View details">
                      <IconButton size="small" onClick={(e) => { e.stopPropagation(); openDetail(job); }} aria-label="View job details">
                        <Visibility fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Detail drawer */}
      <Drawer anchor="right" open={drawerOpen} onClose={() => setDrawerOpen(false)} PaperProps={{ sx: { width: 460, p: 3 } }}>
        {selectedJob && (
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">Job Details</Typography>
              <IconButton onClick={() => setDrawerOpen(false)} aria-label="Close"><Close /></IconButton>
            </Box>
            <Divider sx={{ mb: 2 }} />

            <Stack spacing={2}>
              <Box>
                <Typography variant="caption" color="text.secondary">Job ID</Typography>
                <Typography variant="body2" fontFamily="monospace">{selectedJob.id}</Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">Filename</Typography>
                <Typography variant="body2" fontWeight={600}>{selectedJob.filename}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {formatBytes(selectedJob.file_size_bytes)} · file_date {selectedJob.file_date}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Chip
                  label={selectedJob.tenant_code}
                  size="small"
                  color={TENANT_COLORS[selectedJob.tenant_code] || 'default'}
                />
                <Chip label={selectedJob.domain} size="small" variant="outlined" />
                <StatusChip status={selectedJob.status} />
                <Chip
                  label={selectedJob.mode}
                  size="small"
                  variant="outlined"
                  color={selectedJob.mode === 'STRICT' ? 'error' : 'warning'}
                />
              </Box>

              {/* Drawer-level action buttons */}
              {adminOnly && (selectedJob.status === 'STAGED' || selectedJob.status === 'VALIDATED' ||
                             selectedJob.status === 'VALIDATING' || selectedJob.status === 'COMMITTING') && (
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>Actions</Typography>
                  {renderRowActions(selectedJob, () => setDrawerOpen(false))}
                </Box>
              )}

              <Divider />

              <Box>
                <Typography variant="caption" color="text.secondary">SHA-256</Typography>
                <Typography variant="body2" fontFamily="monospace" sx={{ wordBreak: 'break-all', fontSize: '0.7rem' }}>
                  {selectedJob.file_hash}
                </Typography>
              </Box>

              <Divider />

              <Box>
                <Typography variant="caption" color="text.secondary">Records</Typography>
                <Stack direction="row" spacing={2} sx={{ mt: 0.5 }}>
                  <Box>
                    <Typography variant="h6">{selectedJob.row_count_total?.toLocaleString() ?? '—'}</Typography>
                    <Typography variant="caption">Total</Typography>
                  </Box>
                  <Box>
                    <Typography variant="h6" color="success.main">{selectedJob.row_count_valid?.toLocaleString() ?? '—'}</Typography>
                    <Typography variant="caption">Valid</Typography>
                  </Box>
                  <Box>
                    <Typography variant="h6" color="error.main">{selectedJob.row_count_rejected?.toLocaleString() ?? '—'}</Typography>
                    <Typography variant="caption">Rejected</Typography>
                  </Box>
                </Stack>
              </Box>

              <Divider />

              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>Timeline</Typography>
                <Stack spacing={0.5}>
                  <Typography variant="caption">Uploaded · {new Date(selectedJob.uploaded_at).toLocaleString()}</Typography>
                  {selectedJob.validated_at && (
                    <Typography variant="caption">Validated · {new Date(selectedJob.validated_at).toLocaleString()}</Typography>
                  )}
                  {selectedJob.committed_at && (
                    <Typography variant="caption">Committed · {new Date(selectedJob.committed_at).toLocaleString()}</Typography>
                  )}
                  {selectedJob.replaced_by_job_id && (
                    <Typography variant="caption" color="warning.main">
                      Replaced by job {selectedJob.replaced_by_job_id.slice(0, 8)}…
                    </Typography>
                  )}
                </Stack>
              </Box>

              {selectedJob.error_message && (
                <Box>
                  <Typography variant="caption" color="error.main">Error</Typography>
                  <Typography variant="body2" color="error.main">{selectedJob.error_message}</Typography>
                </Box>
              )}
            </Stack>
          </Box>
        )}
      </Drawer>

      {/* Conflict dialog — shown when commit returns 409 ingestion_conflict */}
      <Dialog open={conflict !== null} onClose={() => setConflict(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Replace existing committed job?</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            {conflict?.message || 'A committed job already exists for the same tenant, domain, and file date.'}
          </DialogContentText>
          {conflict?.existingJobId && (
            <DialogContentText variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
              Existing job: {conflict.existingJobId}
            </DialogContentText>
          )}
          <Alert severity="warning" sx={{ mt: 2 }}>
            Replacing will mark the existing job as <strong>REPLACED</strong> and delete its fact rows
            for that ({conflict?.jobLabel.split(' ').slice(0, 3).join(', ') || 'tenant, domain, date'}) before
            inserting the new ones. This is irreversible without restoring from a backup.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConflict(null)}>Cancel</Button>
          <Button
            onClick={handleReplaceConfirm}
            color="warning"
            variant="contained"
            disabled={!conflict || pendingActions.has(conflict.jobId)}
            startIcon={conflict && pendingActions.has(conflict.jobId) ? <CircularProgress size={14} color="inherit" /> : undefined}
          >
            Replace & Commit
          </Button>
        </DialogActions>
      </Dialog>

      {/* Cancel-confirmation dialog */}
      <Dialog open={cancelPrompt !== null} onClose={() => setCancelPrompt(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Cancel staged job?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Cancelling will delete the staged file from disk and mark the job as REJECTED.
            This is only possible while the job is STAGED or VALIDATED.
          </DialogContentText>
          {cancelPrompt && (
            <DialogContentText variant="body2" sx={{ mt: 1, fontFamily: 'monospace', fontSize: '0.85rem' }}>
              {cancelPrompt.jobLabel}
            </DialogContentText>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCancelPrompt(null)}>Keep</Button>
          <Button
            onClick={() => cancelPrompt && handleCancel(cancelPrompt.jobId)}
            color="error"
            variant="contained"
            disabled={!cancelPrompt || pendingActions.has(cancelPrompt.jobId)}
          >
            Cancel job
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete-committed-data confirmation dialog */}
      <Dialog open={deletePrompt !== null} onClose={() => setDeletePrompt(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Delete committed data?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This permanently deletes
            {deletePrompt?.rowCount != null
              ? ` the ${deletePrompt.rowCount.toLocaleString()} rows`
              : ' the rows'}{' '}
            this file loaded into the database. The job will be marked <strong>DELETED</strong>
            {' '}and kept as a history record.
          </DialogContentText>
          {deletePrompt && (
            <DialogContentText variant="body2" sx={{ mt: 1, fontFamily: 'monospace', fontSize: '0.85rem' }}>
              {deletePrompt.jobLabel}
            </DialogContentText>
          )}
          <Alert severity="warning" sx={{ mt: 2 }}>
            This cannot be undone. To restore the data you would need to re-upload and re-commit the file.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeletePrompt(null)}>Keep</Button>
          <Button
            onClick={() => deletePrompt && handleDeleteData(deletePrompt.jobId)}
            color="error"
            variant="contained"
            startIcon={deletePrompt && pendingActions.has(deletePrompt.jobId) ? <CircularProgress size={14} color="inherit" /> : <DeleteForever />}
            disabled={!deletePrompt || pendingActions.has(deletePrompt.jobId)}
          >
            Delete data
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar(s => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={() => setSnackbar(s => ({ ...s, open: false }))}
          severity={snackbar.severity}
          variant="filled"
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}
