/**
 * One preset: a switch, and the handful of numbers it lets you tune.
 *
 * Auto-saves per card, debounced. With several independent toggles on one
 * screen a single page-level Save button invites "did that take?" ambiguity,
 * so each card owns its own idle → saving → saved caption instead.
 *
 * Every control is built from the server's `tunables` — ranges, units and
 * option lists all come down with the rule, so the client never hard-codes
 * what a threshold is allowed to be.
 */
import { useEffect, useRef, useState } from 'react';
import {
  Autocomplete, Box, Card, CardContent, Chip, FormControlLabel, InputAdornment,
  MenuItem, Stack, Switch, TextField, Typography, useTheme,
} from '@mui/material';
import CheckCircleOutline from '@mui/icons-material/CheckCircleOutline';

import { useTenantChrome } from '../../components/dashboard/tenantChrome';
import { accentColor } from '../../alerts/alertTheme';
import type { AlertPreset, AlertTunable } from '../../types';

const SAVE_DEBOUNCE_MS = 600;

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

interface Props {
  preset: AlertPreset;
  onSave: (ruleKey: string, patch: { is_active?: boolean; condition?: Record<string, unknown> })
    => Promise<AlertPreset>;
  onError: (message: string) => void;
}

function unitAdornment(unit: string | null): string | null {
  if (!unit) return null;
  if (unit === 'percent') return '%';
  if (unit === 'currency') return 'USD';
  // Anything else prints as itself — 'places', 'stops', 'days'. Returning null
  // for an unrecognised unit left a bare "3" with nothing beside it, which is a
  // question rather than a setting, and made every new unit a frontend change.
  return unit;
}

export default function AlertPresetCard({ preset, onSave, onError }: Props) {
  const theme = useTheme();
  const chrome = useTenantChrome();
  const accent = accentColor(chrome, theme);

  const [active, setActive] = useState(preset.is_active);
  const [condition, setCondition] = useState<Record<string, unknown>>(preset.condition);
  const [state, setState] = useState<SaveState>('idle');
  const [fieldError, setFieldError] = useState<Record<string, string>>({});

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Last values the server confirmed, so a failed save can revert precisely.
  const committed = useRef({ active: preset.is_active, condition: preset.condition });

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const push = (patch: { is_active?: boolean; condition?: Record<string, unknown> }) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setState('saving');
      try {
        const saved = await onSave(preset.rule_key, patch);
        committed.current = { active: saved.is_active, condition: saved.condition };
        setActive(saved.is_active);
        setCondition(saved.condition);
        setState('saved');
        setTimeout(() => setState('idle'), 2000);
      } catch (err) {
        setActive(committed.current.active);
        setCondition(committed.current.condition);
        setState('error');
        onError(err instanceof Error ? err.message : 'Could not save');
        setTimeout(() => setState('idle'), 2000);
      }
    }, SAVE_DEBOUNCE_MS);
  };

  const toggle = (next: boolean) => {
    setActive(next);
    push({ is_active: next });
  };

  const setField = (t: AlertTunable, raw: unknown) => {
    // Validate against the server-supplied range and block the save rather
    // than reverting mid-keystroke, which would fight the user's typing.
    if (t.type === 'number') {
      const n = Number(raw);
      if (raw === '' || Number.isNaN(n)) {
        setFieldError(e => ({ ...e, [t.key]: 'Enter a number' }));
        setCondition(c => ({ ...c, [t.key]: raw }));
        return;
      }
      if ((t.min !== null && n < t.min) || (t.max !== null && n > t.max)) {
        setFieldError(e => ({
          ...e, [t.key]: `Must be between ${t.min ?? '−∞'} and ${t.max ?? '∞'}`,
        }));
        setCondition(c => ({ ...c, [t.key]: n }));
        return;
      }
      setFieldError(e => { const { [t.key]: _drop, ...rest } = e; return rest; });
      setCondition(c => ({ ...c, [t.key]: n }));
      push({ condition: { [t.key]: n } });
      return;
    }
    setCondition(c => ({ ...c, [t.key]: raw }));
    push({ condition: { [t.key]: raw } });
  };

  // Scalar controls always render. A multi-select renders once the server
  // sends its option list — the rules responses now carry the tenant's routes
  // — and stays hidden without one (the competitor picker still has no list),
  // because an empty picker would look broken rather than honest.
  const scalar = preset.tunables.filter(t => t.type === 'number' || t.type === 'enum' || t.type === 'bool');
  const multi = preset.tunables.filter(t => t.type === 'multiselect' && (t.options?.length ?? 0) > 0);

  const blocked = preset.missing_requirements.length > 0 && !active;

  return (
    <Card variant="outlined">
      <CardContent sx={{ pb: 2, '&:last-child': { pb: 2 } }}>
        <Stack direction="row" alignItems="flex-start" spacing={2}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              {preset.name}
            </Typography>
            {preset.description && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
                {preset.description}
              </Typography>
            )}
            {blocked && (
              <Chip
                size="small" variant="outlined" sx={{ mt: 1 }}
                label={`Needs ${preset.missing_requirements.join(' and ')} before it can be switched on`}
              />
            )}
          </Box>

          <Stack alignItems="flex-end" spacing={0.5}>
            <Switch
              checked={active}
              onChange={e => toggle(e.target.checked)}
              sx={{
                '& .Mui-checked': { color: accent },
                '& .Mui-checked + .MuiSwitch-track': { backgroundColor: `${accent} !important` },
              }}
            />
            <Box sx={{ height: 18 }}>
              {state === 'saving' && (
                <Typography variant="caption" color="text.secondary">Saving…</Typography>
              )}
              {state === 'saved' && (
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <CheckCircleOutline sx={{ fontSize: 13, color: 'success.main' }} />
                  <Typography variant="caption" color="success.main">Saved</Typography>
                </Stack>
              )}
              {state === 'error' && (
                <Typography variant="caption" color="error.main">Not saved</Typography>
              )}
            </Box>
          </Stack>
        </Stack>

        {scalar.length > 0 && (
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mt: 2 }}>
            {scalar.map(t => {
              const value = condition[t.key];
              // A field the server demands BEFORE activation has to stay
              // editable while the rule is off, or the requirement can never be
              // met. The multiselects already had this escape hatch; the
              // scalars did not, which deadlocked comp_price_threshold
              // completely: it ships off, requires `value` (a number), and that
              // number is disabled until it is on. Flipping the switch 422s and
              // the card reverts. It is is_active=false for every tenant.
              const required = preset.missing_requirements.includes(t.key);
              if (t.type === 'bool') {
                return (
                  <FormControlLabel
                    key={t.key}
                    control={
                      <Switch
                        size="small" disabled={!active && !required}
                        checked={Boolean(value)}
                        onChange={e => setField(t, e.target.checked)}
                      />
                    }
                    label={<Typography variant="body2">{t.label}</Typography>}
                  />
                );
              }
              if (t.type === 'enum') {
                return (
                  <TextField
                    key={t.key} select size="small" label={t.label}
                    disabled={!active && !required}
                    value={(value as string) ?? ''}
                    onChange={e => setField(t, e.target.value)}
                    sx={{ minWidth: 140 }}
                  >
                    {(t.options ?? []).map(o => (
                      <MenuItem key={o} value={o}>{o}</MenuItem>
                    ))}
                  </TextField>
                );
              }
              const adornment = unitAdornment(t.unit);
              return (
                <TextField
                  key={t.key} size="small" type="number" label={t.label}
                  // Greyed rather than hidden when off: the numbers are still
                  // worth seeing, they just are not doing anything.
                  disabled={!active && !required}
                  value={value ?? ''}
                  onChange={e => setField(t, e.target.value)}
                  error={Boolean(fieldError[t.key])}
                  helperText={fieldError[t.key] ?? t.help ?? ' '}
                  inputProps={{ min: t.min ?? undefined, max: t.max ?? undefined, step: t.step ?? undefined }}
                  InputProps={adornment ? {
                    endAdornment: <InputAdornment position="end">{adornment}</InputAdornment>,
                  } : undefined}
                  sx={{ minWidth: 190 }}
                />
              );
            })}
          </Stack>
        )}
        {/* Scope pickers on their own line. They are flexGrow:1, so mixed in
            with the fixed-width thresholds they stretch to fill whatever gap
            the numbers happen to leave, and every card wraps differently. */}
        {multi.length > 0 && (
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
            {multi.map(t => (
              <Autocomplete
                key={t.key}
                multiple
                size="small"
                options={t.options ?? []}
                // A field the server requires BEFORE activation must stay
                // editable while the rule is off, or the requirement could
                // never be satisfied; optional multi-selects grey out with
                // the scalars.
                disabled={!active && !preset.missing_requirements.includes(t.key)}
                value={Array.isArray(condition[t.key]) ? (condition[t.key] as string[]) : []}
                onChange={(_, next) => setField(t, next)}
                renderInput={p => (
                  <TextField {...p} label={t.label} helperText={t.help ?? ' '} />
                )}
                sx={{ minWidth: 280, flexGrow: 1 }}
              />
            ))}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}
