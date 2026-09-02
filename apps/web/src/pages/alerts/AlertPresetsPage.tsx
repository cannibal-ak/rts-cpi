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
import RestoreOutlined from '@mui/icons-material/RestoreOutlined';

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
  // Open flag separate from the target: the target must survive the dialog's
  // fade-out, or the conditional copy flashes to the wrong branch with an
  // empty rule name while the modal is still closing.
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AlertPreset | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [restoring, setRestoring] = useState<string | null>(null);

  // `quiet` refreshes the list without collapsing the page into the loading
  // spinner — used after create/delete, where the cards are already on screen
  // and a full-page flash (behind a still-open dialog) reads as a hang.
  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
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
      // Close first, reload quietly after: the delete succeeded, so the modal
      // must not sit on top of a page-level spinner (or, if the reload then
      // fails, on top of an error state that hides the success).
      setDeleteOpen(false);
      // A reload rather than a local splice: a deleted built-in comes back as
      // a tombstone the restore strip renders, which only the server knows.
      await load(true);
      // The rule's events went with it, so the badge and feed need a refetch.
      await refresh();
    } catch (err) {
      setToast(err instanceof Error ? err.message : 'Could not delete the rule');
    } finally {
      setDeleting(false);
    }
  };

  const restore = async (ruleKey: string) => {
    if (restoring) return;
    setRestoring(ruleKey);
    try {
      const restored = await api.alerts.restoreRule(ruleKey);
      setPresets(ps => ps.map(p => (p.rule_key === ruleKey ? restored : p)));
      setToast(`Restored “${restored.name}” — it is switched off until you enable it`);
    } catch (err) {
      setToast(err instanceof Error ? err.message : 'Could not restore the rule');
    } finally {
      setRestoring(null);
    }
  };

  const visible = presets.filter(p => !p.deleted_at);
  const deletedBuiltins = presets.filter(p => p.deleted_at && p.is_preset);

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
          {visible.map(p => (
            <AlertPresetCard
              key={p.rule_key} preset={p} onSave={save} onError={setToast}
              onDelete={target => { setDeleteTarget(target); setDeleteOpen(true); }}
            />
          ))}
          {deletedBuiltins.length > 0 && (
            <Box sx={{ pt: 1 }}>
              <Typography variant="caption" color="text.secondary">
                Deleted built-in rules — restore brings one back switched off,
                with the settings it had.
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
                {deletedBuiltins.map(p => (
                  <Button
                    key={p.rule_key} size="small" variant="outlined"
                    disabled={restoring !== null}
                    startIcon={restoring === p.rule_key
                      ? <CircularProgress size={14} />
                      : <RestoreOutlined />}
                    onClick={() => void restore(p.rule_key)}
                  >
                    {p.name}
                  </Button>
                ))}
              </Stack>
            </Box>
          )}
        </Stack>
      )}

      <CreateAlertRuleDialog
        open={createOpen}
        families={presets.filter(p => p.is_preset)}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          // Reload rather than splice: the server owns the ordering (built-ins
          // first, then instances grouped by family). Quiet — the cards are
          // already on screen.
          void load(true);
          setToast('Rule created');
        }}
      />

      <Dialog open={deleteOpen} onClose={deleting ? undefined : () => setDeleteOpen(false)}>
        <DialogTitle>Delete rule?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {deleteTarget?.is_preset
              ? <>This deletes “{deleteTarget?.name}” and every alert it has
                  ever raised. It is a built-in rule, so you can restore it
                  later from this page — it comes back switched off, keeping
                  its current settings, but its alert history will not.</>
              : <>This permanently deletes “{deleteTarget?.name}” and every
                  alert it has ever raised. Custom rules cannot be restored.</>}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteOpen(false)} disabled={deleting}>Cancel</Button>
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
