/**
 * Create a user-owned alert rule — an instance of one of the built-in rule
 * types, with its own name, thresholds and scope.
 *
 * A modal with an explicit Create button, unlike the autosaving cards below
 * it: nothing exists on the server until Create succeeds, so there is nothing
 * for autosave to patch. The tunable controls themselves are the same
 * TunableField renderer the cards use, seeded from the chosen family's
 * current settings, and the optional preview reuses the family's preview
 * endpoint with the full draft condition — an honest "what would this fire
 * on the newest capture" before anything is saved.
 */
import { useEffect, useState } from 'react';
import {
  Alert, Button, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogTitle, Divider, FormControlLabel, MenuItem, Stack, Switch, TextField,
  Typography,
} from '@mui/material';
import VisibilityOutlined from '@mui/icons-material/VisibilityOutlined';

import { api } from '../../api';
import TunableField, { parseNumberInput } from './TunableField';
import type { AlertPreset, AlertPreview, AlertTunable } from '../../types';

interface Props {
  open: boolean;
  /** The built-in rules (is_preset), as loaded by the settings page — their
   *  tunables already carry the tenant's route/window option lists. */
  families: AlertPreset[];
  onClose: () => void;
  onCreated: (created: AlertPreset) => void;
}

export default function CreateAlertRuleDialog({ open, families, onClose, onCreated }: Props) {
  const [familyKey, setFamilyKey] = useState<string>('');
  const [name, setName] = useState('');
  const [condition, setCondition] = useState<Record<string, unknown>>({});
  const [fieldError, setFieldError] = useState<Record<string, string>>({});
  const [isActive, setIsActive] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<AlertPreview | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Active built-ins first; a deleted built-in stays usable as a template
  // (the admin removed the built-in, not the rule TYPE — they may well want
  // their own variant of it) but is labelled and never the default seed.
  const ordered = [
    ...families.filter(f => !f.deleted_at),
    ...families.filter(f => f.deleted_at),
  ];
  const family = ordered.find(f => f.rule_key === familyKey) ?? null;

  const seedFrom = (f: AlertPreset) => {
    setFamilyKey(f.rule_key);
    setName(`${f.name} (copy)`);
    setCondition({ ...f.condition });
    setFieldError({});
    setPreview(null);
    setError(null);
  };

  useEffect(() => {
    if (open && ordered.length > 0) {
      seedFrom(ordered[0]);
      setIsActive(false);
      setSubmitting(false);
    }
    // Reseeding is keyed on open only: reopening starts a fresh draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const setField = (t: AlertTunable, raw: unknown) => {
    if (t.type === 'number') {
      const { value, error: err } = parseNumberInput(t, raw);
      setCondition(c => ({ ...c, [t.key]: value }));
      setFieldError(e => {
        if (err) return { ...e, [t.key]: err };
        const { [t.key]: _drop, ...rest } = e;
        return rest;
      });
      return;
    }
    setCondition(c => ({ ...c, [t.key]: raw }));
  };

  const hasFieldErrors = Object.keys(fieldError).length > 0;
  const canSubmit = Boolean(family) && name.trim().length > 0 && !hasFieldErrors && !submitting;

  const runPreview = async () => {
    if (!family) return;
    setPreviewing(true);
    setError(null);
    try {
      // The draft carries every key of the family's condition, so this is a
      // full override of the stored settings — the preview really is the
      // draft, not a mix.
      setPreview(await api.alerts.previewPreset(family.rule_key, { condition }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not preview');
    } finally {
      setPreviewing(false);
    }
  };

  const submit = async () => {
    if (!family) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await api.alerts.createRule({
        preset_key: family.rule_key,
        name: name.trim(),
        condition,
        is_active: isActive,
      });
      onCreated(created);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the rule');
      setSubmitting(false);
    }
  };

  const scalar = family?.tunables.filter(t => t.type === 'number' || t.type === 'enum' || t.type === 'bool') ?? [];
  const multi = family?.tunables.filter(t => t.type === 'multiselect' && (t.options?.length ?? 0) > 0) ?? [];

  return (
    <Dialog open={open} onClose={submitting ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogTitle>Add alert rule</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <TextField
            select size="small" label="Rule type" value={familyKey}
            onChange={e => {
              const f = ordered.find(x => x.rule_key === e.target.value);
              if (f) seedFrom(f);
            }}
            sx={{ maxWidth: 420 }}
          >
            {ordered.map(f => (
              <MenuItem key={f.rule_key} value={f.rule_key}>
                {f.deleted_at ? `${f.name} (built-in deleted)` : f.name}
              </MenuItem>
            ))}
          </TextField>
          {family?.description && (
            <Typography variant="body2" color="text.secondary">
              {family.description}
            </Typography>
          )}

          <TextField
            size="small" label="Name" value={name}
            onChange={e => setName(e.target.value)}
            inputProps={{ maxLength: 128 }}
            helperText="Shown in the alert feed and on this settings page."
            sx={{ maxWidth: 420 }}
          />

          <Divider />

          {scalar.length > 0 && (
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
              {scalar.map(t => (
                <TunableField
                  key={t.key} tunable={t} value={condition[t.key]}
                  disabled={false} error={fieldError[t.key]} onChange={setField}
                />
              ))}
            </Stack>
          )}
          {multi.length > 0 && (
            <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
              {multi.map(t => (
                <TunableField
                  key={t.key} tunable={t} value={condition[t.key]}
                  disabled={false} onChange={setField}
                />
              ))}
            </Stack>
          )}

          <FormControlLabel
            control={
              <Switch
                size="small" checked={isActive}
                onChange={e => setIsActive(e.target.checked)}
              />
            }
            label={<Typography variant="body2">Enable immediately</Typography>}
          />

          {preview && (
            <Alert severity={preview.would_fire > 0 ? 'warning' : 'info'} onClose={() => setPreview(null)}>
              <Typography variant="body2">
                Would raise {preview.would_fire} alert{preview.would_fire === 1 ? '' : 's'}
                {preview.cap_date && preview.prev_cap_date
                  ? ` comparing ${preview.prev_cap_date} with ${preview.cap_date}`
                  : ''}
                .
              </Typography>
              {preview.sample.slice(0, 3).map((s, i) => (
                <Typography key={i} variant="caption" component="div" color="text.secondary">
                  • {s.message}
                </Typography>
              ))}
            </Alert>
          )}
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button
          size="small" disabled={!family || hasFieldErrors || previewing}
          startIcon={previewing ? <CircularProgress size={14} /> : <VisibilityOutlined />}
          onClick={() => void runPreview()}
          sx={{ mr: 'auto' }}
        >
          Preview matches
        </Button>
        <Button onClick={onClose} disabled={submitting}>Cancel</Button>
        <Button variant="contained" disabled={!canSubmit} onClick={() => void submit()}>
          {submitting ? 'Creating…' : 'Create rule'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
