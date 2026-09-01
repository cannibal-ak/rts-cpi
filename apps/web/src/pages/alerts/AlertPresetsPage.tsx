/**
 * Alert settings — the tenant's own admin picks which changes raise an alert
 * and how big a change has to be.
 *
 * This is the first route in the app owned by a TENANT_ADMIN rather than the
 * RTS platform admin; every existing /admin/* page is requireSuperAdmin. The
 * backend enforces the same thing on PATCH, so the guard here is a courtesy,
 * not the control.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Button, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogContentText, DialogTitle, Snackbar, Stack, Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import PlayArrowOutlined from '@mui/icons-material/PlayArrowOutlined';

import { api } from '../../api';
import PageHeader from '../../components/common/PageHeader';
import { useAlerts } from '../../context/AlertsContext';
import type { AlertPreset, AlertRunSummary } from '../../types';
import AlertPresetCard from './AlertPresetCard';
import AlertsTabs from './AlertsTabs';
import CreateAlertRuleDialog from './CreateAlertRuleDialog';

export default function AlertPresetsPage() {
  const { refresh } = useAlerts();
  const [presets, setPresets] = useState<AlertPreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<AlertRunSummary | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AlertPreset | null>(null);
  const [deleting, setDeleting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setPresets(await api.alerts.listPresets());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load alert settings');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const save = useCallback(
    async (
      ruleKey: string,
      patch: { is_active?: boolean; condition?: Record<string, unknown>; name?: string },
    ) => {
      const saved = await api.alerts.updatePreset(ruleKey, patch);
      setPresets(ps => ps.map(p => (p.rule_key === ruleKey ? saved : p)));
      return saved;
    },
    [],
  );

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.alerts.deleteRule(deleteTarget.rule_key);
      setPresets(ps => ps.filter(p => p.rule_key !== deleteTarget.rule_key));
      setDeleteTarget(null);
      // The rule's events went with it, so the badge and feed need a refetch.
      await refresh();
    } catch (err) {
      setToast(err instanceof Error ? err.message : 'Could not delete the rule');
    } finally {
      setDeleting(false);
    }
  };

  const runNow = async () => {
    setRunning(true);
    try {
      const summary = await api.alerts.run();
      setLastRun(summary);
      await refresh();
    } catch (err) {
      setToast(err instanceof Error ? err.message : 'Could not run the evaluation');
    } finally {
      setRunning(false);
    }
  };

  return (
    <Box>
      <PageHeader
        title="Alert settings"
        subtitle="Choose which changes raise an alert, and how big a change has to be."
        actions={
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined" size="small" disabled={loading}
              startIcon={<AddOutlined />}
              onClick={() => setCreateOpen(true)}
            >
              Add rule
            </Button>
            <Button
              variant="outlined" size="small" disabled={running}
              startIcon={running ? <CircularProgress size={14} /> : <PlayArrowOutlined />}
              onClick={() => void runNow()}
            >
              Run evaluation now
            </Button>
          </Stack>
        }
      />
      <AlertsTabs />

      {lastRun && (
        // Report the run even when it created nothing. "Evaluated 95 groups
        // against 2026-08-12 vs 2026-08-10, 8 matched, 8 already recorded" is a
        // far better answer than a silent no-op, and it puts the age of the
        // data in front of whoever is asking whether the feed is live.
        <Alert
          severity={lastRun.events_created > 0 ? 'success' : 'info'}
          sx={{ mb: 2 }}
          onClose={() => setLastRun(null)}
        >
          <Typography variant="body2">
            Evaluated {lastRun.groups_evaluated} route groups
            {lastRun.prev_cap_date && lastRun.cap_date
              ? ` comparing ${lastRun.prev_cap_date} with ${lastRun.cap_date}`
              : ''}
            . {lastRun.events_created} new alert{lastRun.events_created === 1 ? '' : 's'}
            {lastRun.events_suppressed_dedupe > 0
              ? `, ${lastRun.events_suppressed_dedupe} already recorded`
              : ''}
            .
          </Typography>
          {lastRun.cap_date_age_days !== null && lastRun.cap_date_age_days > 3 && (
            <Typography variant="caption" color="text.secondary">
              The newest capture is {lastRun.cap_date_age_days} days old.
            </Typography>
          )}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress size={28} />
        </Box>
      ) : error ? (
        <Alert
          severity="error"
          action={<Button size="small" onClick={() => void load()}>Retry</Button>}
        >
          {error}
        </Alert>
      ) : (
        <Stack spacing={2}>
          {presets.map(p => (
            <AlertPresetCard
              key={p.rule_key} preset={p} onSave={save} onError={setToast}
              onDelete={setDeleteTarget}
            />
          ))}
        </Stack>
      )}

      <CreateAlertRuleDialog
        open={createOpen}
        families={presets.filter(p => p.is_preset)}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          // Reload rather than splice: the server owns the ordering (built-ins
          // first, then instances grouped by family).
          void load();
          setToast('Rule created');
        }}
      />

      <Dialog open={deleteTarget !== null} onClose={deleting ? undefined : () => setDeleteTarget(null)}>
        <DialogTitle>Delete rule?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            This permanently deletes “{deleteTarget?.name}” and every alert it
            has ever raised. Built-in rules are unaffected.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)} disabled={deleting}>Cancel</Button>
          <Button
            color="error" variant="contained" disabled={deleting}
            onClick={() => void confirmDelete()}
          >
            {deleting ? 'Deleting…' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={Boolean(toast)} autoHideDuration={5000}
        onClose={() => setToast(null)} message={toast ?? ''}
      />
    </Box>
  );
}
