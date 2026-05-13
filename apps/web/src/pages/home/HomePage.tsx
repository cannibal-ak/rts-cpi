/**
 * Admin Home — System Overview.
 *
 * Three rows: Platform Health Strip, Enhanced Tenant Cards, Quick Actions.
 * Health + tenant data refresh together every 60s.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  Paper,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Cancel as CancelIcon,
  FiberManualRecord as DotIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../components/common/PageHeader';
import { api } from '../../api';
import type {
  PlatformHealthResponse,
  ServiceHealthItem,
  ServiceHealthStatus,
  TenantDataSummary,
  TenantFreshnessStatus,
  TenantSummaryResponse,
} from '../../types';

const REFRESH_INTERVAL_MS = 60_000;

// ── Time formatters ──────────────────────────────────────
function formatRelative(iso: string | null | undefined): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const diffMs = Date.now() - then;
  if (diffMs < 0) {
    const future = -diffMs;
    if (future < 60_000) return 'in <1 min';
    if (future < 3_600_000) return `in ${Math.round(future / 60_000)} min`;
    if (future < 86_400_000) return `in ${Math.round(future / 3_600_000)} h`;
    return `in ${Math.round(future / 86_400_000)} d`;
  }
  if (diffMs < 60_000) return 'just now';
  if (diffMs < 3_600_000) return `${Math.round(diffMs / 60_000)} min ago`;
  if (diffMs < 86_400_000) return `${Math.round(diffMs / 3_600_000)} h ago`;
  return `${Math.round(diffMs / 86_400_000)} d ago`;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

// ── Color helpers ────────────────────────────────────────
function healthDotColor(status: ServiceHealthStatus): 'success' | 'error' | 'disabled' {
  if (status === 'healthy') return 'success';
  if (status === 'unhealthy') return 'error';
  return 'disabled';
}

function freshnessChipProps(status: TenantFreshnessStatus): {
  label: string;
  color: 'success' | 'warning' | 'error' | 'default';
} {
  switch (status) {
    case 'fresh': return { label: 'Fresh', color: 'success' };
    case 'stale': return { label: 'Stale', color: 'warning' };
    case 'critical': return { label: 'Critical', color: 'error' };
    case 'no_data':
    default: return { label: 'No Data', color: 'default' };
  }
}

// ── Sub-components ───────────────────────────────────────
function HealthStrip({
  health,
  loading,
  lastCheckedAt,
}: {
  health: PlatformHealthResponse | null;
  loading: boolean;
  lastCheckedAt: number | null;
}) {
  const services: ServiceHealthItem[] = health?.services ?? [];
  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5 }}>
        <Typography variant="subtitle2" color="text.secondary">Platform Health</Typography>
        <Typography variant="caption" color="text.secondary">
          {loading && !health
            ? 'Checking…'
            : lastCheckedAt
              ? `Last checked: ${formatRelative(new Date(lastCheckedAt).toISOString())}`
              : ''}
        </Typography>
      </Box>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
        {loading && !health ? (
          <CircularProgress size={20} />
        ) : services.length === 0 ? (
          <Typography variant="body2" color="text.secondary">Health data unavailable.</Typography>
        ) : (
          services.map((s) => (
            <Tooltip
              key={s.name}
              title={s.details ? `${s.status} — ${s.details}` : s.status}
              arrow
            >
              <Chip
                size="small"
                variant="outlined"
                icon={<DotIcon sx={{ fontSize: 12 }} color={healthDotColor(s.status)} />}
                label={
                  <Box component="span" sx={{ display: 'inline-flex', alignItems: 'baseline', gap: 0.5 }}>
                    <Box component="span">{s.name}</Box>
                    {s.response_time_ms != null && s.response_time_ms > 0 && (
                      <Box component="span" sx={{ color: 'text.secondary', fontSize: 11 }}>
                        {s.response_time_ms}ms
                      </Box>
                    )}
                  </Box>
                }
                sx={{ borderColor: 'divider' }}
              />
            </Tooltip>
          ))
        )}
      </Box>
    </Paper>
  );
}

function TenantCard({
  tenant,
  onViewRun,
}: {
  tenant: TenantDataSummary;
  onViewRun: (runId: string) => void;
}) {
  const fresh = freshnessChipProps(tenant.freshness_status);
  const sftpStatusColor = tenant.sftp_connected ? 'success' : 'error';
  const hasNoData = tenant.freshness_status === 'no_data' && tenant.total_records === 0;
  const lastRunOK = tenant.last_run_status === 'SUCCESS';

  return (
    <Paper variant="outlined" sx={{ p: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <Typography variant="subtitle1" fontWeight={600} sx={{ flexGrow: 1 }}>
          {tenant.tenant_name}
        </Typography>
        <Chip
          size="small"
          label={tenant.tenant_type === 'airline' ? 'Airline' : 'Cruise'}
          variant="outlined"
        />
        <Chip size="small" label={fresh.label} color={fresh.color} />
      </Box>
      <Divider sx={{ mb: 1.5 }} />

      {hasNoData ? (
        <Box sx={{ py: 4, textAlign: 'center', color: 'text.disabled' }}>
          <Typography variant="body2">No data ingested yet</Typography>
        </Box>
      ) : (
        <>
          {/* SFTP */}
          <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}>
            SFTP Connection
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5, mb: 1.5 }}>
            <DotIcon sx={{ fontSize: 12 }} color={sftpStatusColor} />
            <Typography variant="body2">
              {tenant.sftp_connected ? 'Connected' : 'Not configured'}
            </Typography>
            {tenant.sftp_last_pull && (
              <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                Last pull: {formatRelative(tenant.sftp_last_pull)}
              </Typography>
            )}
          </Box>
          <Divider sx={{ mb: 1.5 }} />

          {/* Freshness */}
          <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Data Freshness
          </Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25, mt: 0.5, mb: 1.5 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="body2" color="text.secondary">Latest date</Typography>
              <Typography variant="body2">{formatDate(tenant.latest_data_date)}</Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="body2" color="text.secondary">Captured</Typography>
              <Typography variant="body2">{formatRelative(tenant.last_capture_at)}</Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="body2" color="text.secondary">Records</Typography>
              <Typography variant="body2">{tenant.total_records.toLocaleString()}</Typography>
            </Box>
          </Box>
          <Divider sx={{ mb: 1.5 }} />

          {/* Schedule */}
          <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Schedule
          </Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.25, mt: 0.5, mb: 1.5 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="body2" color="text.secondary">Next run</Typography>
              <Typography variant="body2">{formatDateTime(tenant.next_scheduled_run)}</Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="body2" color="text.secondary">Status</Typography>
              <Typography
                variant="body2"
                color={tenant.schedule_enabled ? 'success.main' : 'text.disabled'}
              >
                {tenant.schedule_enabled ? 'Enabled' : 'Disabled'}
              </Typography>
            </Box>
          </Box>
          <Divider sx={{ mb: 1.5 }} />

          {/* Last ingestion */}
          <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Last Ingestion
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
            {tenant.last_run_status ? (
              <>
                {lastRunOK ? (
                  <CheckCircleIcon fontSize="small" color="success" />
                ) : (
                  <CancelIcon fontSize="small" color="error" />
                )}
                <Typography variant="body2">
                  {tenant.last_run_status}
                  {tenant.last_run_at && ` — ${formatRelative(tenant.last_run_at)}`}
                </Typography>
                {tenant.last_run_id && (
                  <Button
                    size="small"
                    onClick={() => onViewRun(tenant.last_run_id as string)}
                    sx={{ ml: 'auto', textTransform: 'none' }}
                  >
                    View
                  </Button>
                )}
              </>
            ) : (
              <Typography variant="body2" color="text.disabled">No runs yet</Typography>
            )}
          </Box>
        </>
      )}
    </Paper>
  );
}

// ── Main page ─────────────────────────────────────────────
export default function HomePage() {
  const theme = useTheme();
  const navigate = useNavigate();
  const [health, setHealth] = useState<PlatformHealthResponse | null>(null);
  const [summary, setSummary] = useState<TenantSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastCheckedAt, setLastCheckedAt] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [h, s] = await Promise.all([
        api.admin.dashboard.getHealth(),
        api.admin.dashboard.getTenantSummary(),
      ]);
      setHealth(h);
      setSummary(s);
      setLastCheckedAt(Date.now());
    } catch (err) {
      console.error('Failed to load dashboard:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  const tenants = useMemo(() => summary?.tenants ?? [], [summary]);

  const handleViewRun = useCallback((runId: string) => {
    navigate(`/admin/ingestion-runs?run_id=${runId}`);
  }, [navigate]);

  return (
    <Box>
      <PageHeader
        title="System Overview"
        subtitle="Platform health and tenant data status"
        actions={
          <Button
            size="small"
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={refresh}
            disabled={loading && !health}
            sx={{ textTransform: 'none' }}
          >
            Refresh
          </Button>
        }
      />

      {/* Row 1 — Platform Health Strip */}
      <HealthStrip health={health} loading={loading} lastCheckedAt={lastCheckedAt} />

      {/* Row 2 — Enhanced Tenant Cards */}
      <Box>
        {loading && !summary ? (
          <Box sx={{ display: 'flex', alignItems: 'center', minHeight: 120, justifyContent: 'center' }}>
            <CircularProgress size={28} />
          </Box>
        ) : tenants.length === 0 ? (
          <Paper variant="outlined" sx={{ p: 3, textAlign: 'center', color: theme.palette.text.secondary }}>
            No tenants configured.
          </Paper>
        ) : (
          <Grid container spacing={2}>
            {tenants.map((t) => (
              <Grid item xs={12} md={6} lg={4} key={t.tenant_id}>
                <TenantCard tenant={t} onViewRun={handleViewRun} />
              </Grid>
            ))}
          </Grid>
        )}
      </Box>
    </Box>
  );
}
