import React, { useState, useEffect } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Chip, IconButton, Drawer, Divider, Stack, LinearProgress, Button,
  FormControl, InputLabel, Select, MenuItem, CircularProgress, Tooltip, Alert,
  Snackbar,
} from '@mui/material';
import { CloudUpload, Visibility, Close, Refresh, Warning, PlayArrow } from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import StatusChip from '../../components/common/StatusChip';
import StatusTimeline from '../../components/common/StatusTimeline';
import KpiTiles from '../../components/common/KpiTiles';
import { api } from '../../api';
import { useSession } from '../../context/SessionContext';
import type { IngestionJob, ImportBatch, Paginated } from '../../types';

const TENANT_COLORS: Record<string, 'primary' | 'secondary' | 'info' | 'default'> = {
  JY: 'primary',
  PW: 'secondary',
  FJL: 'info',
};

function CompletenessWidget({ batches }: { batches: ImportBatch[] }) {
  const compatBatches = batches.filter(b => b.completeness_score !== null);
  if (compatBatches.length === 0) return null;

  const avgScore = compatBatches.reduce((s, b) => s + (b.completeness_score || 0), 0) / compatBatches.length;
  const allWarnings = compatBatches.flatMap(b => b.validation_results?.warnings || []);
  const uniqueWarnings = [...new Map(allWarnings.map(w => [w.code, w])).values()];

  const color = avgScore >= 95 ? 'success' : avgScore >= 75 ? 'warning' : 'error';

  return (
    <Paper variant="outlined" sx={{ p: 2, mt: 2, borderColor: `${color}.main`, borderWidth: 2 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>
        COMPAT Mode — Completeness
      </Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
        <Box sx={{ position: 'relative', display: 'inline-flex' }}>
          <CircularProgress
            variant="determinate"
            value={avgScore}
            size={64}
            thickness={6}
            color={color}
          />
          <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Typography variant="body2" fontWeight={700}>{avgScore.toFixed(0)}%</Typography>
          </Box>
        </Box>
        <Box>
          <Typography variant="body2">
            {compatBatches[0]?.validation_results?.present_fields || '?'} of {compatBatches[0]?.validation_results?.total_fields || '?'} fields present
          </Typography>
          {compatBatches[0]?.validation_results?.optional_missing && (
            <Typography variant="caption" color="text.secondary">
              Missing: {compatBatches[0].validation_results.optional_missing.join(', ')}
            </Typography>
          )}
        </Box>
      </Box>

      {uniqueWarnings.length > 0 && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>Warnings:</Typography>
          {uniqueWarnings.map(w => (
            <Alert key={w.code} severity="warning" variant="outlined" sx={{ py: 0, px: 1, mb: 0.5, fontSize: '0.75rem' }} icon={<Warning sx={{ fontSize: 16 }} />}>
              <strong>{w.code}</strong>: {w.message}
            </Alert>
          ))}
        </Box>
      )}
    </Paper>
  );
}

export default function IngestionJobsPage() {
  const { session } = useSession();
  const isAdmin = session.user.roles.includes('TENANT_ADMIN');

  const [jobs, setJobs] = useState<Paginated<IngestionJob> | null>(null);
  const [loading, setLoading] = useState(true);
  const [domainFilter, setDomainFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [tenantFilter, setTenantFilter] = useState('');
  const [selectedJob, setSelectedJob] = useState<IngestionJob | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [batches, setBatches] = useState<ImportBatch[]>([]);

  // Trigger ingestion state
  const [ingesting, setIngesting] = useState(false);
  const [snackbar, setSnackbar] = useState<{ open: boolean; message: string; severity: 'success' | 'error' | 'info' }>({ open: false, message: '', severity: 'info' });

  const fetchJobs = async () => {
    setLoading(true);
    const q: Record<string, string> = {};
    if (domainFilter) q.domain = domainFilter;
    if (statusFilter) q.status = statusFilter;
    if (tenantFilter) q.tenant = tenantFilter;
    const result = await api.ingestion.listJobs(q);
    setJobs(result);
    setLoading(false);
  };

  useEffect(() => { fetchJobs(); }, [domainFilter, statusFilter, tenantFilter]);

  const openDetail = async (job: IngestionJob) => {
    const detail = await api.ingestion.getJob(job.id);
    setSelectedJob(detail);
    // Load batch completeness data
    try {
      const b = await api.ingestion.listJobBatches(job.id);
      setBatches(b);
    } catch { setBatches([]); }
    setDrawerOpen(true);
  };

  const handleTriggerIngest = async (tenant?: string) => {
    setIngesting(true);
    try {
      const result = await api.ingestion.triggerIngest(tenant);
      const responseType = (result as any).type || 'success';
      if (responseType === 'already_ingested') {
        setSnackbar({ open: true, message: result.message || 'Data already ingested. No new data to process.', severity: 'info' });
      } else {
        setSnackbar({ open: true, message: result.message || 'Ingestion completed successfully', severity: 'success' });
        // Refresh the jobs list after a short delay (only on actual ingestion)
        setTimeout(() => fetchJobs(), 1500);
      }
    } catch (err: any) {
      // Parse validation errors from API 400 responses
      let errorMsg = err.message || 'Ingestion failed';
      try {
        if (errorMsg.startsWith('API 4')) {
          // The httpClient wraps errors as "API 400: {...}"
          const jsonPart = errorMsg.substring(errorMsg.indexOf('{'));
          const parsed = JSON.parse(jsonPart);
          errorMsg = parsed.message || parsed.detail?.message || errorMsg;
        }
      } catch { /* keep original message */ }
      setSnackbar({ open: true, message: errorMsg, severity: 'error' });
    } finally {
      setIngesting(false);
    }
  };

  const allJobs = jobs?.items || [];
  const committed = allJobs.filter(j => j.status === 'committed').length;
  const failed = allJobs.filter(j => j.status === 'failed').length;
  const totalRecords = allJobs.reduce((s, j) => s + j.records_total, 0);

  // Tenant breakdown for KPI
  const tenantCounts: Record<string, number> = {};
  allJobs.forEach(j => {
    const tc = j.tenant_code || 'Unknown';
    tenantCounts[tc] = (tenantCounts[tc] || 0) + 1;
  });
  const tenantSummary = Object.entries(tenantCounts).map(([k, v]) => `${k}: ${v}`).join(' | ');

  return (
    <Box>
      <PageHeader
        title="Ingestion Jobs Monitor"
        subtitle="Track data import pipeline across all tenants — jobs, validation, and commit status"
        breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Ingestion Jobs' }]}
        actions={
          <Stack direction="row" spacing={1}>
            {isAdmin && (
              <Button
                size="small"
                variant="contained"
                color="primary"
                startIcon={ingesting ? <CircularProgress size={16} color="inherit" /> : <PlayArrow />}
                onClick={() => handleTriggerIngest(tenantFilter || undefined)}
                disabled={ingesting}
              >
                {ingesting ? 'Ingesting...' : tenantFilter ? `Ingest ${tenantFilter}` : 'Ingest All'}
              </Button>
            )}
            <Button size="small" variant="outlined" startIcon={<Refresh />} onClick={fetchJobs}>Refresh</Button>
          </Stack>
        }
      />

      <KpiTiles tiles={[
        { label: 'Total Jobs', value: allJobs.length, sub: tenantSummary || undefined },
        { label: 'Committed', value: committed, trend: 'up', color: 'success.main' },
        { label: 'Failed', value: failed, trend: failed > 0 ? 'down' : 'flat', color: failed > 0 ? 'error.main' : undefined },
        { label: 'Total Records', value: totalRecords.toLocaleString() },
      ]} />

      {/* Filters */}
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
              <MenuItem value="airline">Airline</MenuItem>
              <MenuItem value="cfl">CFL</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 140 }}>
            <InputLabel>Status</InputLabel>
            <Select value={statusFilter} label="Status" onChange={e => setStatusFilter(e.target.value)}>
              <MenuItem value="">All</MenuItem>
              <MenuItem value="queued">Queued</MenuItem>
              <MenuItem value="validating">Validating</MenuItem>
              <MenuItem value="committed">Committed</MenuItem>
              <MenuItem value="failed">Failed</MenuItem>
            </Select>
          </FormControl>
        </Stack>
      </Paper>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>
      ) : allJobs.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: 'center' }}>
          <CloudUpload sx={{ fontSize: 48, color: 'text.secondary', mb: 1 }} />
          <Typography variant="h6" color="text.secondary">No ingestion jobs found</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {tenantFilter ? `No jobs for tenant ${tenantFilter}` : 'No jobs match the current filters'}
          </Typography>
          {isAdmin && (
            <Button
              variant="contained"
              startIcon={<PlayArrow />}
              onClick={() => handleTriggerIngest(tenantFilter || undefined)}
              disabled={ingesting}
            >
              Trigger Ingestion
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
                <TableCell>Source</TableCell>
                <TableCell>Domain</TableCell>
                <TableCell>Mode</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Total</TableCell>
                <TableCell align="right">Valid</TableCell>
                <TableCell align="right">Rejected</TableCell>
                <TableCell>Started</TableCell>
                <TableCell>Completed</TableCell>
                <TableCell align="center">Details</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {allJobs.map(job => (
                <TableRow key={job.id} hover sx={{ cursor: 'pointer' }} onClick={() => openDetail(job)}>
                  <TableCell><Typography variant="caption" fontFamily="monospace">{job.id.slice(0, 8)}...</Typography></TableCell>
                  <TableCell>
                    <Chip
                      label={job.tenant_code || '—'}
                      size="small"
                      color={TENANT_COLORS[job.tenant_code || ''] || 'default'}
                      variant="outlined"
                    />
                  </TableCell>
                  <TableCell><Typography variant="body2" fontWeight={600}>{job.source_name || '—'}</Typography></TableCell>
                  <TableCell><Chip label={job.domain.toUpperCase()} size="small" variant="outlined" /></TableCell>
                  <TableCell>
                    <Chip
                      label={job.validation_mode}
                      size="small"
                      variant="outlined"
                      color={job.validation_mode === 'STRICT' ? 'error' : 'warning'}
                    />
                  </TableCell>
                  <TableCell>
                    <StatusChip status={job.status} />
                    {job.status === 'validating' && <LinearProgress sx={{ mt: 0.5, borderRadius: 1 }} />}
                  </TableCell>
                  <TableCell align="right">{job.records_total.toLocaleString()}</TableCell>
                  <TableCell align="right"><Typography variant="body2" color="success.main">{job.records_valid.toLocaleString()}</Typography></TableCell>
                  <TableCell align="right"><Typography variant="body2" color={job.records_rejected > 0 ? 'error.main' : 'text.primary'}>{job.records_rejected.toLocaleString()}</Typography></TableCell>
                  <TableCell><Typography variant="caption">{new Date(job.started_at).toLocaleString()}</Typography></TableCell>
                  <TableCell><Typography variant="caption">{job.completed_at ? new Date(job.completed_at).toLocaleString() : '—'}</Typography></TableCell>
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
      <Drawer anchor="right" open={drawerOpen} onClose={() => setDrawerOpen(false)} PaperProps={{ sx: { width: 440, p: 3 } }}>
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
                <Typography variant="caption" color="text.secondary">Source</Typography>
                <Typography variant="body2" fontWeight={600}>{selectedJob.source_name || 'Unknown'}</Typography>
              </Box>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Chip
                  label={selectedJob.tenant_code || '—'}
                  size="small"
                  color={TENANT_COLORS[selectedJob.tenant_code || ''] || 'default'}
                />
                <Chip label={selectedJob.domain.toUpperCase()} size="small" variant="outlined" />
                <StatusChip status={selectedJob.status} />
                <Chip
                  label={selectedJob.validation_mode}
                  size="small"
                  variant="outlined"
                  color={selectedJob.validation_mode === 'STRICT' ? 'error' : 'warning'}
                />
              </Box>

              <Divider />

              <Box>
                <Typography variant="caption" color="text.secondary">Records</Typography>
                <Stack direction="row" spacing={2} sx={{ mt: 0.5 }}>
                  <Box><Typography variant="h6">{selectedJob.records_total.toLocaleString()}</Typography><Typography variant="caption">Total</Typography></Box>
                  <Box><Typography variant="h6" color="success.main">{selectedJob.records_valid.toLocaleString()}</Typography><Typography variant="caption">Valid</Typography></Box>
                  <Box><Typography variant="h6" color="error.main">{selectedJob.records_rejected.toLocaleString()}</Typography><Typography variant="caption">Rejected</Typography></Box>
                </Stack>
                {selectedJob.records_total > 0 && (
                  <LinearProgress
                    variant="determinate"
                    value={(selectedJob.records_valid / selectedJob.records_total) * 100}
                    color={selectedJob.records_rejected > selectedJob.records_total * 0.1 ? 'error' : 'success'}
                    sx={{ mt: 1, height: 8, borderRadius: 4 }}
                  />
                )}
              </Box>

              {/* Completeness widget for COMPAT mode jobs */}
              {selectedJob.validation_mode === 'COMPAT' && batches.length > 0 && (
                <CompletenessWidget batches={batches} />
              )}

              <Divider />

              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>Status Timeline</Typography>
                <StatusTimeline timeline={selectedJob.timeline} />
              </Box>
            </Stack>
          </Box>
        )}
      </Drawer>

      {/* Snackbar for ingestion feedback */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={8000}
        onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
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
