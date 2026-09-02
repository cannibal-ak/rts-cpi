/**
 * One rule: a switch, and the handful of numbers it lets you tune.
 *
 * Auto-saves per card, debounced. With several independent toggles on one
 * screen a single page-level Save button invites "did that take?" ambiguity,
 * so each card owns its own idle → saving → saved caption instead.
 *
 * Every control is built from the server's `tunables` — ranges, units and
 * option lists all come down with the rule, so the client never hard-codes
 * what a threshold is allowed to be. Every rule gets a Delete action — for a
 * built-in it tombstones the rule (restorable from the strip the settings
 * page renders), for a user-created instance (is_preset=false) it is
 * permanent. Instances additionally get inline rename; built-in names come
 * from the catalogue and stay fixed.
 */
import { useEffect, useRef, useState } from 'react';
import {
  Box, Card, CardContent, Chip, IconButton, Stack, Switch, TextField,
  Tooltip, Typography, useTheme,
} from '@mui/material';
import CheckCircleOutline from '@mui/icons-material/CheckCircleOutline';
import DeleteOutline from '@mui/icons-material/DeleteOutline';
import EditOutlined from '@mui/icons-material/EditOutlined';

import { useTenantChrome } from '../../components/dashboard/tenantChrome';
import { accentColor } from '../../alerts/alertTheme';
import TunableField, { parseNumberInput } from './TunableField';
import type { AlertPreset, AlertTunable } from '../../types';

const SAVE_DEBOUNCE_MS = 600;

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

interface Props {
  preset: AlertPreset;
  onSave: (
    ruleKey: string,
    patch: { is_active?: boolean; condition?: Record<string, unknown>; name?: string },
  ) => Promise<AlertPreset>;
  onError: (message: string) => void;
  /** Every rule renders Delete when provided; the page's confirm dialog
   *  explains the built-in vs custom difference. */
  onDelete?: (preset: AlertPreset) => void;
}

export default function AlertPresetCard({ preset, onSave, onError, onDelete }: Props) {
  const theme = useTheme();
  const chrome = useTenantChrome();
  const accent = accentColor(chrome, theme);

  const [active, setActive] = useState(preset.is_active);
  const [name, setName] = useState(preset.name);
  const [condition, setCondition] = useState<Record<string, unknown>>(preset.condition);
  const [state, setState] = useState<SaveState>('idle');
  const [fieldError, setFieldError] = useState<Record<string, string>>({});
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState(preset.name);

  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Last values the server confirmed, so a failed save can revert precisely.
  const committed = useRef({
    active: preset.is_active, condition: preset.condition, name: preset.name,
  });

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const push = (patch: { is_active?: boolean; condition?: Record<string, unknown>; name?: string }) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setState('saving');
      try {
        const saved = await onSave(preset.rule_key, patch);
        committed.current = {
          active: saved.is_active, condition: saved.condition, name: saved.name,
        };
        setActive(saved.is_active);
        setCondition(saved.condition);
        setName(saved.name);
        setState('saved');
        setTimeout(() => setState('idle'), 2000);
      } catch (err) {
        setActive(committed.current.active);
        setCondition(committed.current.condition);
        setName(committed.current.name);
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

  const commitName = () => {
    setEditingName(false);
    const next = nameDraft.trim();
    if (!next || next === name) {
      setNameDraft(name);
      return;
    }
    setName(next);
    push({ name: next });
  };

  const setField = (t: AlertTunable, raw: unknown) => {
    // Validate against the server-supplied range and block the save rather
    // than reverting mid-keystroke, which would fight the user's typing.
    if (t.type === 'number') {
      const { value, error, commit } = parseNumberInput(t, raw);
      setCondition(c => ({ ...c, [t.key]: value }));
      if (!commit) {
        setFieldError(e => ({ ...e, [t.key]: error ?? 'Invalid value' }));
        return;
      }
      setFieldError(e => { const { [t.key]: _drop, ...rest } = e; return rest; });
      push({ condition: { [t.key]: value } });
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
  const isInstance = !preset.is_preset;

  return (
    <Card variant="outlined">
      <CardContent sx={{ pb: 2, '&:last-child': { pb: 2 } }}>
        <Stack direction="row" alignItems="flex-start" spacing={2}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            {editingName ? (
              <TextField
                size="small" autoFocus fullWidth value={nameDraft}
                onChange={e => setNameDraft(e.target.value)}
                onBlur={commitName}
                onKeyDown={e => {
                  if (e.key === 'Enter') commitName();
                  if (e.key === 'Escape') { setEditingName(false); setNameDraft(name); }
                }}
                inputProps={{ maxLength: 128 }}
                sx={{ maxWidth: 420 }}
              />
            ) : (
              <Stack direction="row" alignItems="center" spacing={0.75} sx={{ minWidth: 0 }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }} noWrap>
                  {name}
                </Typography>
                {isInstance && (
                  <>
                    <Chip size="small" variant="outlined" label="Custom" />
                    <Tooltip title="Rename rule">
                      <IconButton
                        size="small"
                        onClick={() => { setNameDraft(name); setEditingName(true); }}
                      >
                        <EditOutlined sx={{ fontSize: 16 }} />
                      </IconButton>
                    </Tooltip>
                  </>
                )}
              </Stack>
            )}
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
            <Stack direction="row" alignItems="center" spacing={0.5}>
              {onDelete && (
                <Tooltip title="Delete rule">
                  <IconButton size="small" onClick={() => onDelete(preset)}>
                    <DeleteOutline sx={{ fontSize: 18 }} />
                  </IconButton>
                </Tooltip>
              )}
              <Switch
                checked={active}
                onChange={e => toggle(e.target.checked)}
                sx={{
                  '& .Mui-checked': { color: accent },
                  '& .Mui-checked + .MuiSwitch-track': { backgroundColor: `${accent} !important` },
                }}
              />
            </Stack>
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
            {scalar.map(t => (
              <TunableField
                key={t.key}
                tunable={t}
                value={condition[t.key]}
                // A field the server demands BEFORE activation has to stay
                // editable while the rule is off, or the requirement can never
                // be met. The multiselects already had this escape hatch; the
                // scalars did not, which deadlocked comp_price_threshold
                // completely: it ships off, requires `value` (a number), and
                // that number is disabled until it is on. Flipping the switch
                // 422s and the card reverts. It is is_active=false for every
                // tenant.
                disabled={!active && !preset.missing_requirements.includes(t.key)}
                error={fieldError[t.key]}
                onChange={setField}
              />
            ))}
          </Stack>
        )}
        {/* Scope pickers on their own line. They are flexGrow:1, so mixed in
            with the fixed-width thresholds they stretch to fill whatever gap
            the numbers happen to leave, and every card wraps differently. */}
        {multi.length > 0 && (
          <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mt: 1 }}>
            {multi.map(t => (
              <TunableField
                key={t.key}
                tunable={t}
                value={condition[t.key]}
                // Same before-activation escape hatch as the scalars.
                disabled={!active && !preset.missing_requirements.includes(t.key)}
                onChange={setField}
              />
            ))}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}
