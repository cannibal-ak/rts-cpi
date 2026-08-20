/**
 * The alerts feed.
 *
 * Owns its own paginated, filtered state rather than reading the context's
 * `recent` — the two are answering different questions, so trying to share one
 * array would mean merging a filtered page against an unfiltered five. It
 * refetches when the context's `revision` bumps, which happens only when a poll
 * actually saw something change, so one HTTP request refreshes both surfaces
 * and this page runs no timer of its own.
 *
 * A List rather than a DataGrid: alert messages are prose of variable length
 * and a grid row's fixed height truncates them.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Alert, Box, Button, Chip, CircularProgress, FormControlLabel, MenuItem,
  Paper, Snackbar, Stack, Switch, TablePagination, TextField, Typography,
} from '@mui/material';
import NotificationsOffOutlined from '@mui/icons-material/NotificationsOffOutlined';
import SearchOffOutlined from '@mui/icons-material/SearchOffOutlined';

import { api } from '../../api';
import EmptyState from '../../components/common/EmptyState';
import PageHeader from '../../components/common/PageHeader';
import AlertEventRow from '../../components/alerts/AlertEventRow';
import { useAlerts } from '../../context/AlertsContext';
import { useSession } from '../../context/SessionContext';
import { canEditAlertRules } from '../../alerts/alertsAccess';
import { useTenantChrome } from '../../components/dashboard/tenantChrome';
import type { AlertEvent, AlertSeverity } from '../../types';
import AlertsTabs from './AlertsTabs';

const PAGE_SIZE = 25;

const RULE_LABELS: Record<string, string> = {
  undercut_position: 'Position changes',
  comp_price_move: 'Price moves',
  comp_price_threshold: 'Price lines',
};

export default function AlertsPage() {
  const [params, setParams] = useSearchParams();
  const focusId = params.get('focus');
  const { session } = useSession();
  const chrome = useTenantChrome();
  const canEdit = canEditAlertRules(session);
  const { revision, markRead, markAllRead, unreadCount } = useAlerts();

  const [events, setEvents] = useState<AlertEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [toast, setToast] = useState<string | null>(null);

  const [unreadOnly, setUnreadOnly] = useState(false);
  const [severity, setSeverity] = useState<AlertSeverity | ''>('');
  const [ruleKey, setRuleKey] = useState('');
  const [route, setRoute] = useState('');
  const [routeInput, setRouteInput] = useState('');

  const focusRef = useRef<HTMLDivElement | null>(null);

  // Free-text needs a debounce; the selects fire immediately.
  useEffect(() => {
    const t = setTimeout(() => setRoute(routeInput.trim().toUpperCase()), 300);
    return () => clearTimeout(t);
  }, [routeInput]);

  const filtersActive = Boolean(unreadOnly || severity || ruleKey || route);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.alerts.listEvents({
        page: page + 1,
        page_size: PAGE_SIZE,
        unread_only: unreadOnly || undefined,
        severity: severity || undefined,
        rule_key: ruleKey || undefined,
        route: route || undefined,
      });
      setEvents(res.items);
      setTotal(res.page_info.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load alerts');
    } finally {
      setLoading(false);
    }
  }, [page, unreadOnly, severity, ruleKey, route]);

  useEffect(() => { void load(); }, [load]);
  // A poll saw something change — pick it up without running our own timer.
  useEffect(() => { if (revision > 0) void load(); }, [revision, load]);

  useEffect(() => {
    if (focusId && focusRef.current) {
      focusRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [focusId, events]);

  const resetFilters = () => {
    setUnreadOnly(false); setSeverity(''); setRuleKey('');
    setRouteInput(''); setRoute(''); setPage(0);
  };

  const onSelect = (id: string, checked: boolean) =>
    setSelected(s => (checked ? [...s, id] : s.filter(x => x !== id)));

  const markSelectedRead = async () => {
    try {
      await markRead(selected);
      setEvents(es => es.map(e => (selected.includes(e.id) ? { ...e, is_read: true } : e)));
      setToast(`${selected.length} alert${selected.length === 1 ? '' : 's'} marked read`);
      setSelected([]);
    } catch {
      setToast('Could not mark those read');
    }
  };

  const body = useMemo(() => {
    if (loading && events.length === 0) {
      return (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress size={28} />
        </Box>
      );
    }
    if (error) {
      return (
        <Alert
          severity="error" sx={{ m: 2 }}
          action={<Button size="small" onClick={() => void load()}>Retry</Button>}
        >
          {error}
        </Alert>
      );
    }
    if (events.length === 0) {
      return filtersActive ? (
        <EmptyState
          icon={<SearchOffOutlined sx={{ fontSize: 40 }} />}
          title="No alerts match these filters"
          actionLabel="Clear filters"
          onAction={resetFilters}
          accent={chrome?.BANNER_BG}
        />
      ) : (
        <EmptyState
          icon={<NotificationsOffOutlined sx={{ fontSize: 40 }} />}
          title="No alerts yet"
          description="Alerts appear here when a competitor's fare moves past a threshold you've set, or when we lose the cheapest position on a route."
          actionLabel={canEdit ? 'Configure alerts' : undefined}
          onAction={canEdit ? () => { window.location.href = '/alerts/settings'; } : undefined}
          accent={chrome?.BANNER_BG}
        />
      );
    }
    return events.map(ev => (
      <Box key={ev.id} ref={ev.id === focusId ? focusRef : undefined}>
        <AlertEventRow
          event={ev} variant="full"
          selected={selected.includes(ev.id)}
          onSelect={onSelect}
          highlighted={ev.id === focusId}
        />
      </Box>
    ));
  }, [loading, error, events, filtersActive, selected, focusId, chrome, canEdit, load]);

  return (
    <Box>
      <PageHeader
        title="Alerts"
        subtitle="Competitor price moves and changes to our position"
        actions={
          <Button
            variant="outlined" size="small" disabled={unreadCount === 0}
            onClick={() => { void markAllRead().then(() => load()); }}
          >
            Mark all read
          </Button>
        }
      />
      <AlertsTabs />

      <Paper variant="outlined" sx={{ mb: 2, p: 1.5 }}>
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap>
          <TextField
            select size="small" label="Type" value={ruleKey}
            onChange={e => { setRuleKey(e.target.value); setPage(0); }}
            sx={{ minWidth: 170 }}
          >
            <MenuItem value="">All types</MenuItem>
            {Object.entries(RULE_LABELS).map(([k, v]) => (
              <MenuItem key={k} value={k}>{v}</MenuItem>
            ))}
          </TextField>

          <TextField
            select size="small" label="Severity" value={severity}
            onChange={e => { setSeverity(e.target.value as AlertSeverity | ''); setPage(0); }}
            sx={{ minWidth: 140 }}
          >
            <MenuItem value="">Any</MenuItem>
            <MenuItem value="critical">Urgent</MenuItem>
            <MenuItem value="warning">Watch</MenuItem>
            <MenuItem value="info">Info</MenuItem>
          </TextField>

          <TextField
            size="small" label="Route" placeholder="ZNZ-NBO" value={routeInput}
            onChange={e => { setRouteInput(e.target.value); setPage(0); }}
            sx={{ minWidth: 150 }}
          />

          <FormControlLabel
            control={
              <Switch
                size="small" checked={unreadOnly}
                onChange={e => { setUnreadOnly(e.target.checked); setPage(0); }}
              />
            }
            label={<Typography variant="body2">Unread only</Typography>}
          />

          {filtersActive && (
            <Button size="small" onClick={resetFilters} sx={{ textTransform: 'none' }}>
              Clear
            </Button>
          )}
        </Stack>
      </Paper>

      {selected.length > 0 && (
        <Paper
          variant="outlined"
          sx={{
            mb: 1, px: 2, py: 1, display: 'flex', alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Chip size="small" label={`${selected.length} selected`} />
          <Stack direction="row" spacing={1}>
            <Button size="small" onClick={() => setSelected([])}>Clear</Button>
            <Button size="small" variant="contained" onClick={() => void markSelectedRead()}>
              Mark read
            </Button>
          </Stack>
        </Paper>
      )}

      <Paper variant="outlined">
        {body}
        {events.length > 0 && (
          <TablePagination
            component="div"
            count={total}
            page={page}
            rowsPerPage={PAGE_SIZE}
            rowsPerPageOptions={[PAGE_SIZE]}
            onPageChange={(_, p) => setPage(p)}
          />
        )}
      </Paper>

      <Snackbar
        open={Boolean(toast)} autoHideDuration={3000}
        onClose={() => setToast(null)} message={toast ?? ''}
      />
    </Box>
  );
}
