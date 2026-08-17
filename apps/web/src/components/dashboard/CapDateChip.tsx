import { useEffect, useRef, useState } from 'react';
import { Box, Chip, Popover, Tooltip, Typography } from '@mui/material';
import type { PopoverActions } from '@mui/material/Popover';
import { EventAvailable, ExpandMore } from '@mui/icons-material';
import DateFilterToggle from './DateFilterToggle';
import type { DashboardDateFilter } from '../../api/client';

const POPOVER_ID = 'cpi-cap-date-popover';

/** "29 Jul 2026". Parsed at local midnight so a DATE never slips a day via UTC. */
function fmtDay(iso?: string | null): string | null {
  if (!iso) return null;
  return new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
  });
}

/**
 * Chip text for the current selection.
 *
 * Range mode collapses the parts both ends share, so the common case reads
 * "23 – 29 Jul 2026" rather than "23 Jul 2026 – 29 Jul 2026" — the header row
 * has no width to spare on a repeated month.
 */
export function capDateLabel(value: DashboardDateFilter): string {
  if (value.mode === 'single') return fmtDay(value.capDateEq) ?? '—';
  const { capDateFrom: from, capDateTo: to } = value;
  if (!from || !to) return '—';
  const a = new Date(`${from}T00:00:00`);
  const b = new Date(`${to}T00:00:00`);
  const sameYear = a.getFullYear() === b.getFullYear();
  const sameMonth = sameYear && a.getMonth() === b.getMonth();
  const left = sameMonth
    ? a.toLocaleDateString('en-GB', { day: '2-digit' })
    : sameYear
      ? a.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })
      : fmtDay(from)!;
  return `${left} – ${fmtDay(to)}`;
}

export interface CapDateChipProps {
  availableDates: string[];
  value: DashboardDateFilter;
  onChange: (next: DashboardDateFilter) => void;
  /** /available-dates still in flight. */
  loading?: boolean;
  /**
   * False while the surrounding view does not honour cap_date (Chart view
   * today). The control stays live — the selection is kept and does scope the
   * dashboard pane behind it — but the tooltip says so rather than letting the
   * chip imply the chart in front of you is scoped.
   */
  appliesToView?: boolean;
  /** Drop the "Cap date:" prefix when the header row is tight. */
  compact?: boolean;
}

/**
 * The dashboard's capture-date scope, as a header chip that opens the shared
 * DateFilterToggle in a popover.
 *
 * A popover rather than an inline control because range mode needs ~750px and
 * the header has ~280px free with the sidebar open. The chip still reports the
 * current value, so the header reads the scope at a glance without spending the
 * width to edit it.
 *
 * Sits beside the "Latest data" chip, which reports data freshness and is NOT
 * this. The two routinely show the same date — cap date defaults to the newest
 * available — so they are deliberately different shapes: that one is an inert
 * outlined readout, this one is filled, clickable and carries a chevron.
 */
export default function CapDateChip({
  availableDates, value, onChange,
  loading = false, appliesToView = true, compact = false,
}: CapDateChipProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);

  // Range mode is roughly twice the width of single mode, and the Paper is
  // content-sized. Popover measures on open, not on content resize, so ask it
  // to re-measure when the mode changes under it.
  const popoverActions = useRef<PopoverActions | null>(null);
  useEffect(() => {
    if (open) popoverActions.current?.updatePosition();
  }, [open, value.mode]);

  const unavailable = !loading && availableDates.length === 0;
  const disabled = loading || unavailable;

  const text = loading ? '—' : unavailable ? 'unavailable' : capDateLabel(value);
  const label = compact ? text : `Cap date: ${text}`;

  const tip = loading
    ? 'Loading capture dates…'
    : unavailable
      ? 'No capture dates found for this dashboard.'
      : appliesToView
        ? 'Capture date every chart is scoped to. Click to change.'
        : 'Capture date the dashboard view is scoped to. Chart view is not scoped by it yet.';

  return (
    <>
      <Tooltip title={tip}>
        {/* span: a disabled Chip has pointer-events:none, so Tooltip needs a
            host that still emits enter/leave. It also owns the row spacing —
            the header row has no `gap` of its own. */}
        <Box component="span" sx={{ ml: 1, display: 'inline-flex' }}>
          <Chip
            size="small"
            color="primary"
            icon={<EventAvailable sx={{ fontSize: 16 }} />}
            label={
              <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.25 }}>
                {label}
                {!disabled && (
                  <ExpandMore
                    sx={{
                      fontSize: 16,
                      transition: 'transform 150ms ease',
                      transform: open ? 'rotate(180deg)' : 'none',
                    }}
                  />
                )}
              </Box>
            }
            disabled={disabled}
            clickable={!disabled}
            // currentTarget, not target: the click usually lands on the label
            // span or the chevron, and target would anchor to that child.
            onClick={disabled ? undefined : (e) => setAnchorEl(e.currentTarget)}
            aria-haspopup={disabled ? undefined : 'dialog'}
            aria-expanded={disabled ? undefined : open}
            aria-controls={open ? POPOVER_ID : undefined}
            sx={{ fontWeight: 500, '& .MuiChip-label': { pr: 0.75 } }}
          />
        </Box>
      </Tooltip>

      <Popover
        id={POPOVER_ID}
        action={popoverActions}
        open={open}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
        transformOrigin={{ vertical: 'top', horizontal: 'left' }}
        slotProps={{
          paper: {
            role: 'dialog',
            'aria-label': 'Cap date',
            sx: {
              mt: 1,
              p: 1.5,
              maxWidth: 'calc(100vw - 32px)',
              borderRadius: '12px',
              border: 1,
              borderColor: 'divider',
              bgcolor: 'background.paper',
            },
          },
        }}
      >
        <Typography
          sx={{
            fontSize: 11, fontWeight: 500, letterSpacing: '0.05em',
            textTransform: 'uppercase', color: 'text.secondary', mb: 1,
          }}
        >
          Capture date
        </Typography>
        <DateFilterToggle
          availableDates={availableDates}
          value={value}
          onChange={onChange}
          disabled={disabled}
          bare
        />
      </Popover>
    </>
  );
}
