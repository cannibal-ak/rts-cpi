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
const DEFAULT_RETENTION_DAYS = 30;

// Days are bucketed in IST by the backend; en-CA formats as YYYY-MM-DD.
const istDayFormat = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' });

function istDay(d: Date): string {
  return istDayFormat.format(d);
}

// YYYY-MM-DD arithmetic in UTC, so no local-timezone shift creeps in.
function addDays(day: string, n: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

// The native date input follows the browser's UI language (often mm/dd/yyyy)
// while the admin tables print dd/mm/yyyy — spell the chosen day out.
const dayLabelFormat = new Intl.DateTimeFormat('en-GB', {
  weekday: 'short', day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
});

function dayLabel(day: string): string {
  return dayLabelFormat.format(new Date(`${day}T00:00:00Z`));
}

// Time only when the stamp falls on the selected day; day + month + time
// (never an all-numeric date) when a session ran past midnight.
function formatStamp(iso: string | null, day: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  if (istDay(d) === day) return d.toLocaleTimeString();
  return d.toLocaleString(undefined, {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit',
  });
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

function loginsCell(item: LoginActivityItem) {
  if (item.login_count > 0) return item.login_count;
  if (item.status === 'not_signed_in') return '—';
  return (
    <Tooltip title="Still signed in from an earlier day — no new login on this day">
      <span>0</span>
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
  // True while the admin is looking at "today": the view then rolls over to
  // the new day at IST midnight instead of freezing on yesterday.
  const [followToday, setFollowToday] = useState(true);
  const [data, setData] = useState<LoginActivityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showNotSignedIn, setShowNotSignedIn] = useState(false);

  // Only the newest request may update the page — an older, slower reply
  // must not overwrite the day the admin has since picked.
  const requestSeq = useRef(0);
  const fetchActivity = useCallback(async () => {
    const seq = ++requestSeq.current;
    setLoading(true);
    try {
      const res = await api.admin.loginActivity.list(day);
      if (seq !== requestSeq.current) return;
      setData(res);
      setError('');
    } catch (err) {
      if (seq !== requestSeq.current) return;
      const e = err as Error & ApiErrorShape;
      setError(`Failed to load login activity: ${e.message}`);
    } finally {
      if (seq === requestSeq.current) setLoading(false);
    }
  }, [day]);

  useEffect(() => { void fetchActivity(); }, [fetchActivity]);

  // Kept current by a light always-on ticker, so the picker's limits stay
  // right even while a past day is shown and nothing else re-renders.
  const [today, setToday] = useState(() => istDay(new Date()));
  useEffect(() => {
    const t = setInterval(() => setToday(istDay(new Date())), AUTO_REFRESH_MS);
    return () => clearInterval(t);
  }, []);
  const retention = data?.retention_days ?? DEFAULT_RETENTION_DAYS;
  // The later of the server's and our own window start — a stale server
  // value would allow a day that has since aged out.
  const windowStart = addDays(today, -(retention - 1));
  const oldest = data?.oldest_date && data.oldest_date > windowStart ? data.oldest_date : windowStart;

  // Auto-refresh while following today (past days don't change). Each tick
  // either rolls over to a new IST day or re-fetches the current one.
  const tickRef = useRef<() => void>(() => {});
  tickRef.current = () => {
    const now = istDay(new Date());
    if (now !== day) setDay(now);
    else void fetchActivity();
  };
  useEffect(() => {
    if (!followToday) return;
    const t = setInterval(() => tickRef.current(), AUTO_REFRESH_MS);
    return () => clearInterval(t);
  }, [followToday]);

  // The input edits a draft; only complete, in-window dates are committed.
  // Typing into the native input passes through partial values (e.g. year
  // 0002) that would each fetch — and rejecting them on a controlled input
  // would reset the field mid-typing.
  const [draft, setDraft] = useState(day);
  useEffect(() => { setDraft(day); }, [day]);
  const pickDay = (value: string) => {
    setDraft(value);
    const nowDay = istDay(new Date());
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value < oldest || value > nowDay) return;
    setDay(value);
    setFollowToday(value === nowDay);
  };

  // Rows are shown only for the day they belong to; while another day loads
  // the table shows the spinner instead of the previous day's data.
  const current = data && data.date === day ? data : null;
  const items = (current?.items ?? []).filter(i => showNotSignedIn || i.status !== 'not_signed_in');

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
            {current && (
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {current.signed_in_count} of {current.total_users} users active
              </Typography>
            )}
          </Stack>
          <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="body2" sx={{ fontWeight: 500 }}>
              {dayLabel(day)}
            </Typography>
            <TextField
              type="date"
              size="small"
              label="Day (IST)"
              value={draft}
              onChange={e => pickDay(e.target.value)}
              onBlur={() => setDraft(day)}
              inputProps={{ min: oldest, max: today }}
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

        {!current ? (
          <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}>
            {loading ? <CircularProgress size={24} /> : (
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>No data for this day.</Typography>
            )}
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
                      {loginsCell(item)}
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
                      Nobody was active on this day.
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
          (every 5 minutes). Someone still signed in from an earlier day appears with 0 logins and the
          original login time.
        </Typography>
      </Paper>
    </Box>
  );
}
