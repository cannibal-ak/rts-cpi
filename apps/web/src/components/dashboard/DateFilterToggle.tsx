import React, { useMemo } from 'react';
import {
  Box, ToggleButton, ToggleButtonGroup,
  Select, MenuItem,
  TextField, Stack, Tooltip, Typography,
} from '@mui/material';
import { CalendarToday, DateRange } from '@mui/icons-material';
import type { DashboardDateFilter } from '../../api/client';

// ── Presets ─────────────────────────────────────────────────
//   "anchor" is the most recent available date — when no data
//   exists yet we fall back to today's date.
type PresetKey = 'custom' | '7' | '14' | '30' | '90';
const PRESETS: { key: PresetKey; label: string; days: number | null }[] = [
  { key: 'custom', label: 'Custom range',  days: null },
  { key: '7',      label: 'Last 7 days',   days: 7   },
  { key: '14',     label: 'Last 14 days',  days: 14  },
  { key: '30',     label: 'Last 30 days',  days: 30  },
  { key: '90',     label: 'Last quarter',  days: 90  },
];

function fmt(d: Date): string {
  // YYYY-MM-DD in local time (matches backend's DATE column semantics).
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function rangeFromPreset(preset: PresetKey, anchor: string): { from: string; to: string } {
  const to = anchor;
  const days = PRESETS.find(p => p.key === preset)?.days ?? 7;
  const toDate = new Date(`${anchor}T00:00:00`);
  const fromDate = new Date(toDate);
  fromDate.setDate(toDate.getDate() - days + 1);
  return { from: fmt(fromDate), to };
}

// ── Component ──────────────────────────────────────────────

export interface DateFilterToggleProps {
  availableDates: string[];           // newest first; may be empty while loading
  value: DashboardDateFilter;
  onChange: (next: DashboardDateFilter) => void;
  disabled?: boolean;
  /**
   * Drop the wrapper's own padding and top rule.
   *
   * The default wrapper is sized to sit directly under a page header, where
   * that rule separates it from the content above. Inside a popover the
   * surrounding Paper already owns both, and the rule just draws a stray line
   * across the top of the panel.
   */
  bare?: boolean;
  /**
   * Tenant-brand focus color (a literal color, not a theme path). The default
   * focus ring is theme-primary navy, which clashes inside brand-accented
   * hosts like WinAir's red cap-date popover. Omitted, nothing changes.
   */
  accent?: string;
}

export default function DateFilterToggle({
  availableDates, value, onChange, disabled, bare = false, accent,
}: DateFilterToggleProps) {
  const anchor = availableDates[0] ?? fmt(new Date());

  // Infer the preset that matches the current range (so user toggling
  // between modes doesn't surprise them with a stale "Custom" label).
  const currentPreset: PresetKey = useMemo(() => {
    if (value.mode !== 'range' || !value.capDateFrom || !value.capDateTo) return 'custom';
    for (const p of PRESETS) {
      if (p.days == null) continue;
      const candidate = rangeFromPreset(p.key, value.capDateTo);
      if (candidate.from === value.capDateFrom) return p.key;
    }
    return 'custom';
  }, [value]);

  const handleMode = (_e: unknown, next: 'single' | 'range' | null) => {
    if (!next || next === value.mode) return;
    if (next === 'single') {
      onChange({ mode: 'single', capDateEq: anchor });
    } else {
      const { from, to } = rangeFromPreset('7', anchor);
      onChange({ mode: 'range', capDateFrom: from, capDateTo: to });
    }
  };

  const handleDayPick = (date: string) => {
    onChange({ mode: 'single', capDateEq: date });
  };

  const handlePreset = (preset: PresetKey) => {
    if (preset === 'custom') {
      onChange({
        mode: 'range',
        capDateFrom: value.capDateFrom ?? rangeFromPreset('7', anchor).from,
        capDateTo:   value.capDateTo   ?? anchor,
      });
      return;
    }
    const { from, to } = rangeFromPreset(preset, anchor);
    onChange({ mode: 'range', capDateFrom: from, capDateTo: to });
  };

  // ── Shared sx for compact inputs (Select / TextField) — keeps the bar ~32px tall.
  const compactInputSx = {
    '& .MuiOutlinedInput-root': { height: 28, fontSize: 12 },
    '& .MuiOutlinedInput-input': { py: 0, fontSize: 12 },
    '& input[type="date"]': { py: 0, fontSize: 12, height: 28, boxSizing: 'border-box' as const },
    // Both selector forms on purpose: on a bare <Select> the sx host IS the
    // OutlinedInput root, so the descendant form alone silently misses it.
    ...(accent && {
      '&.MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline, & .MuiOutlinedInput-root.Mui-focused .MuiOutlinedInput-notchedOutline':
        { borderColor: accent },
    }),
  };
  const inlineLabelSx = { fontSize: 12, color: 'text.secondary', whiteSpace: 'nowrap' as const };

  const toggleGroupSx = {
    '& .MuiToggleButton-root': {
      py: '4px', px: '12px',
      fontSize: 12,
      lineHeight: 1.2,
      textTransform: 'none',
    },
  };

  return (
    <Box
      sx={bare ? undefined : {
        px: '12px', py: '4px',
        borderTop: '0.5px solid',
        borderColor: 'divider',
      }}
    >
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={1.5}
        alignItems={{ xs: 'stretch', md: 'center' }}
      >
        <ToggleButtonGroup
          exclusive
          size="small"
          value={value.mode}
          onChange={handleMode}
          disabled={disabled}
          aria-label="Date filter mode"
          sx={toggleGroupSx}
        >
          <ToggleButton value="single" aria-label="Single day">
            <CalendarToday sx={{ fontSize: 14, mr: 0.5 }} />
            Single day
          </ToggleButton>
          <ToggleButton value="range" aria-label="Date range">
            <DateRange sx={{ fontSize: 14, mr: 0.5 }} />
            Date range
          </ToggleButton>
        </ToggleButtonGroup>

        {value.mode === 'single' && (
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography component="label" htmlFor="cpi-cap-date-select" sx={inlineLabelSx}>
              Cap Date:
            </Typography>
            <Select
              id="cpi-cap-date-select"
              size="small"
              disabled={disabled}
              value={value.capDateEq && availableDates.includes(value.capDateEq) ? value.capDateEq : ''}
              onChange={(e) => handleDayPick(String(e.target.value))}
              sx={{ minWidth: 150, ...compactInputSx }}
            >
              {availableDates.length === 0 && (
                <MenuItem value="" disabled>No dates available</MenuItem>
              )}
              {availableDates.map(d => (
                <MenuItem key={d} value={d}>{d}</MenuItem>
              ))}
            </Select>
          </Stack>
        )}

        {value.mode === 'range' && (
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems="center" flexGrow={1}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Typography component="label" htmlFor="cpi-range-preset" sx={inlineLabelSx}>
                Preset:
              </Typography>
              <Select
                id="cpi-range-preset"
                size="small"
                disabled={disabled}
                value={currentPreset}
                onChange={(e) => handlePreset(e.target.value as PresetKey)}
                sx={{ minWidth: 130, ...compactInputSx }}
              >
                {PRESETS.map(p => (
                  <MenuItem key={p.key} value={p.key}>{p.label}</MenuItem>
                ))}
              </Select>
            </Stack>

            <Stack direction="row" spacing={1} alignItems="center">
              <Typography component="label" htmlFor="cpi-range-from" sx={inlineLabelSx}>
                From:
              </Typography>
              <Tooltip title="From (inclusive)">
                <TextField
                  id="cpi-range-from"
                  size="small"
                  type="date"
                  disabled={disabled}
                  value={value.capDateFrom ?? ''}
                  onChange={(e) => onChange({
                    ...value,
                    mode: 'range',
                    capDateFrom: e.target.value,
                    capDateTo:   value.capDateTo ?? anchor,
                  })}
                  sx={{ minWidth: 140, ...compactInputSx }}
                />
              </Tooltip>
            </Stack>

            <Stack direction="row" spacing={1} alignItems="center">
              <Typography component="label" htmlFor="cpi-range-to" sx={inlineLabelSx}>
                To:
              </Typography>
              <Tooltip title="To (inclusive)">
                <TextField
                  id="cpi-range-to"
                  size="small"
                  type="date"
                  disabled={disabled}
                  value={value.capDateTo ?? ''}
                  onChange={(e) => onChange({
                    ...value,
                    mode: 'range',
                    capDateFrom: value.capDateFrom ?? rangeFromPreset('7', anchor).from,
                    capDateTo:   e.target.value,
                  })}
                  sx={{ minWidth: 140, ...compactInputSx }}
                />
              </Tooltip>
            </Stack>
          </Stack>
        )}

      </Stack>
    </Box>
  );
}
