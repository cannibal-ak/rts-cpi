/**
 * Admin Login Activity — when each user signed in and out on a given day.
 * One row per user per IST day, kept for 30 days (no long-term history).
 * RTS platform admin only.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Box, Paper, Typography, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Chip, IconButton, Stack, CircularProgress, Tooltip, TextField, FormControlLabel, Switch, Alert,
} from '@mui/material';
import { Refresh } from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import { api } from '../../api';
import type { ApiErrorShape } from '../../api/httpClient';
import { formatTenantCell, displayRole, roleChipColor } from '../../utils/adminUserLabels';
import type { LoginActivityItem, LoginActivityResponse, LoginSessionStatus } from '../../types';

// Today's list refreshes on its own so Online / Session ended stay current.
const AUTO_REFRESH_MS = 60_000;

// Days are bucketed in IST by the backend; en-CA formats as YYYY-MM-DD.
const istDayFormat = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' });

function istDay(d: Date): string {
  return istDayFormat.format(d);
}

// Time only when the stamp falls on the selected day; date + time when a
// session ran past midnight.
function formatStamp(iso: string | null, day: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return istDay(d) === day ? d.toLocaleTimeString() : d.toLocaleString();
}

const STATUS_CHIP: Record<LoginSessionStatus, {
  label: string; color: 'success' | 'warning' | 'default'; variant: 'filled' | 'outlined'; hint: string;
}> = {
  online:        { label: 'Online',        color: 'success', variant: 'filled',   hint: 'Signed in, browser tab still open' },
  logged_out:    { label: 'Logged out',    color: 'default', variant: 'filled',   hint: 'Clicked Logout after their last sign-in' },
  session_ended: { label: 'Session ended', color: 'warning', variant: 'outlined', hint: 'Closed the tab without logging out — see "last seen"' },
  not_signed_in: { label: 'Not signed in', color: 'default', variant: 'outlined', hint: 'No sign-in on this day' },
};

function statusChip(status: LoginSessionStatus) {
  const c = STATUS_CHIP[status];
  return (
    <Tooltip title={c.hint}>
      <Chip size="small" label={c.label} color={c.color} variant={c.variant} />
    </Tooltip>
  );
}

function logoutCell(item: LoginActivityItem, day: string) {
  if (item.status === 'not_signed_in') return '—';
  if (item.status === 'logged_out') return formatStamp(item.last_logout_at, day);
  return (
    <Box component="span" sx={{ color: 'text.disabled' }}>
      — (last seen {formatStamp(item.last_seen_at, day)})
    </Box>
  );
}

export default function LoginActivityPage() {
  const [day, setDay] = useState<string>(() => istDay(new Date()));
  const [data, setData] = useState<LoginActivityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showNotSignedIn, setShowNotSignedIn] = useState(false);

  const fetchActivity = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.admin.loginActivity.list(day);
      setData(res);
      setError('');
    } catch (err) {
      const e = err as Error & ApiErrorShape;
      setError(`Failed to load login activity: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [day]);

  useEffect(() => { void fetchActivity(); }, [fetchActivity]);

  // Auto-refresh only while today is selected — past days don't change.
  const isToday = day === istDay(new Date());
  const fetchRef = useRef(fetchActivity);
  fetchRef.current = fetchActivity;
  useEffect(() => {
    if (!isToday) return;
    const t = setInterval(() => { void fetchRef.current(); }, AUTO_REFRESH_MS);
    return () => clearInterval(t);
  }, [isToday]);

  const items = (data?.items ?? []).filter(i => showNotSignedIn || i.status !== 'not_signed_in');
  const today = istDay(new Date());
  const retention = data?.retention_days ?? 30;

  return (
    <Box>
      <PageHeader
        title="Login Activity"
        subtitle={`Daily sign-in and sign-out times for every user (kept for ${retention} days)`}
      />

      <Paper sx={{ p: 2.5, mb: 3, border: 1, borderColor: 'divider' }}>
        <Box sx={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexWrap: 'wrap', gap: 1.5, mb: 1.5,
        }}>
          <Stack direction="row" spacing={1.5} alignItems="baseline">
            <Typography variant="h6">User Sessions</Typography>
            {data && (
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {data.signed_in_count} of {data.total_users} users signed in
              </Typography>
            )}
          </Stack>
          <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
            <TextField
              type="date"
              size="small"
              label="Day"
              value={day}
              onChange={e => { if (e.target.value) setDay(e.target.value); }}
              inputProps={{ min: data?.oldest_date, max: today }}
              InputLabelProps={{ shrink: true }}
              sx={{ width: 170 }}
            />
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={showNotSignedIn}
                  onChange={e => setShowNotSignedIn(e.target.checked)}
                />
              }
              label={<Typography variant="body2">Show users who didn't sign in</Typography>}
            />
            <Tooltip title="Refresh">
              <span>
                <IconButton onClick={() => { void fetchActivity(); }} disabled={loading} size="small">
                  <Refresh fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          </Stack>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 1.5 }} onClose={() => setError('')}>
            {error}
          </Alert>
        )}

        {loading && !data ? (
          <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}>
            <CircularProgress size={24} />
          </Box>
        ) : (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Email</TableCell>
                  <TableCell>Tenant</TableCell>
                  <TableCell>Role</TableCell>
                  <TableCell>First Login</TableCell>
                  <TableCell>Last Login</TableCell>
                  <TableCell align="right">Logins</TableCell>
                  <TableCell>Logout</TableCell>
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {items.map(item => (
                  <TableRow key={item.user_id} hover>
                    <TableCell>{item.email}</TableCell>
                    <TableCell>{formatTenantCell(item)}</TableCell>
                    <TableCell>
                      <Chip size="small" label={displayRole(item)} variant="outlined" color={roleChipColor(item)} />
                    </TableCell>
                    <TableCell sx={{ color: 'text.secondary', fontSize: 13 }}>
                      {formatStamp(item.first_login_at, day)}
                    </TableCell>
                    <TableCell sx={{ color: 'text.secondary', fontSize: 13 }}>
                      {formatStamp(item.last_login_at, day)}
                    </TableCell>
                    <TableCell align="right" sx={{ color: 'text.secondary', fontSize: 13 }}>
                      {item.login_count || '—'}
                    </TableCell>
                    <TableCell sx={{ color: 'text.secondary', fontSize: 13 }}>
                      {logoutCell(item, day)}
                    </TableCell>
                    <TableCell>{statusChip(item.status)}</TableCell>
                  </TableRow>
                ))}
                {items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={8} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                      {data ? 'Nobody signed in on this day.' : 'No data.'}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        <Typography variant="caption" component="p" sx={{ color: 'text.secondary', mt: 1.5 }}>
          Days run midnight to midnight IST; times are shown in your local time. Most people close the
          tab instead of clicking Logout — for them, "last seen" is the last time their open tab checked in
          (every 5 minutes).
        </Typography>
      </Paper>
    </Box>
  );
}
