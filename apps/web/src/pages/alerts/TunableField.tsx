/**
 * The shared renderer for one server-declared tunable — number, enum, bool or
 * multiselect. Extracted from AlertPresetCard so the create-rule dialog and
 * the settings cards can never drift apart on how a control looks or
 * validates. Ranges, units and option lists all come from the server's
 * `tunables`, so the client never hard-codes what a threshold is allowed to be.
 */
import {
  Autocomplete, FormControlLabel, InputAdornment, MenuItem, Switch, TextField,
  Typography,
} from '@mui/material';

import type { AlertTunable } from '../../types';

export function unitAdornment(unit: string | null): string | null {
  if (!unit) return null;
  if (unit === 'percent') return '%';
  if (unit === 'currency') return 'USD';
  // Anything else prints as itself — 'places', 'stops', 'days'. Returning null
  // for an unrecognised unit left a bare "3" with nothing beside it, which is a
  // question rather than a setting, and made every new unit a frontend change.
  return unit;
}

/** Client-side check against the server-supplied range. `commit: false` means
 *  keep the keystroke on screen but do not save it — blocking beats reverting
 *  mid-keystroke, which would fight the user's typing. */
export function parseNumberInput(
  t: AlertTunable, raw: unknown,
): { value: unknown; error: string | null; commit: boolean } {
  const n = Number(raw);
  if (raw === '' || Number.isNaN(n)) {
    return { value: raw, error: 'Enter a number', commit: false };
  }
  if ((t.min !== null && n < t.min) || (t.max !== null && n > t.max)) {
    return {
      value: n,
      error: `Must be between ${t.min ?? '−∞'} and ${t.max ?? '∞'}`,
      commit: false,
    };
  }
  return { value: n, error: null, commit: true };
}

interface Props {
  tunable: AlertTunable;
  value: unknown;
  disabled: boolean;
  error?: string;
  onChange: (tunable: AlertTunable, raw: unknown) => void;
}

export default function TunableField({ tunable: t, value, disabled, error, onChange }: Props) {
  if (t.type === 'bool') {
    return (
      <FormControlLabel
        control={
          <Switch
            size="small" disabled={disabled} checked={Boolean(value)}
            onChange={e => onChange(t, e.target.checked)}
          />
        }
        label={<Typography variant="body2">{t.label}</Typography>}
      />
    );
  }
  if (t.type === 'enum') {
    return (
      <TextField
        select size="small" label={t.label} disabled={disabled}
        value={(value as string) ?? ''}
        onChange={e => onChange(t, e.target.value)}
        sx={{ minWidth: 140 }}
      >
        {(t.options ?? []).map(o => (
          <MenuItem key={o} value={o}>{o}</MenuItem>
        ))}
      </TextField>
    );
  }
  if (t.type === 'multiselect') {
    return (
      <Autocomplete
        multiple size="small" options={t.options ?? []} disabled={disabled}
        value={Array.isArray(value) ? (value as string[]) : []}
        onChange={(_, next) => onChange(t, next)}
        renderInput={p => (
          <TextField {...p} label={t.label} helperText={t.help ?? ' '} />
        )}
        sx={{ minWidth: 280, flexGrow: 1 }}
      />
    );
  }
  const adornment = unitAdornment(t.unit);
  return (
    <TextField
      size="small" type="number" label={t.label}
      // Greyed rather than hidden when off: the numbers are still worth
      // seeing, they just are not doing anything.
      disabled={disabled}
      value={value ?? ''}
      onChange={e => onChange(t, e.target.value)}
      error={Boolean(error)}
      helperText={error ?? t.help ?? ' '}
      inputProps={{ min: t.min ?? undefined, max: t.max ?? undefined, step: t.step ?? undefined }}
      InputProps={adornment ? {
        endAdornment: <InputAdornment position="end">{adornment}</InputAdornment>,
      } : undefined}
      sx={{ minWidth: 190 }}
    />
  );
}
