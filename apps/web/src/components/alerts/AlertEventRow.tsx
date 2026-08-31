/**
 * One alert. Shared by the popover preview and the alerts page so the two
 * cannot drift — `variant` is the only difference between them.
 *
 * compact: headline + one detail line. No chips, no checkbox.
 * full:    adds the severity chip, provenance, the comparison dates, and an
 *          optional selection checkbox.
 */
import {
  Box, Checkbox, Stack, Typography, useTheme,
} from '@mui/material';

import { useTenantChrome } from '../dashboard/tenantChrome';
import { accentColor, severityStyle } from '../../alerts/alertTheme';
import {
  comparisonLabel, detailParts, provenanceLabel, timeAgo,
  gapDatesFull,
} from '../../alerts/formatAlert';
import type { AlertEvent } from '../../types';
import SeverityChip from './SeverityChip';

interface Props {
  event: AlertEvent;
  variant?: 'compact' | 'full';
  selected?: boolean;
  onSelect?: (id: string, checked: boolean) => void;
  onClick?: (event: AlertEvent) => void;
  /** Briefly highlighted when arrived at via ?focus=<id>. */
  highlighted?: boolean;
}

export default function AlertEventRow({
  event, variant = 'full', selected = false, onSelect, onClick, highlighted,
}: Props) {
  const theme = useTheme();
  const chrome = useTenantChrome();
  const accent = accentColor(chrome, theme);
  const style = severityStyle(event.severity, chrome, theme);
  const compact = variant === 'compact';
  const unread = !event.is_read;

  const details = detailParts(event);
  const provenance = provenanceLabel(event);
  const comparison = comparisonLabel(event);

  return (
    <Box
      onClick={onClick ? () => onClick(event) : undefined}
      sx={{
        display: 'flex', alignItems: 'flex-start', gap: 1.25,
        px: compact ? 1.5 : 2, py: compact ? 1.25 : 1.5,
        cursor: onClick ? 'pointer' : 'default',
        // The severity rule. Amber is safe here because it is not behind text.
        borderLeft: '4px solid',
        borderLeftColor: unread ? style.color : 'transparent',
        // Mode-aware surfaces only — the dashboard's FILTER_BG token is a
        // light-mode chrome colour and glares on dark paper.
        bgcolor: highlighted ? 'action.selected' : 'transparent',
        transition: 'background-color 240ms ease',
        '&:hover': onClick ? { bgcolor: 'action.hover' } : undefined,
        borderBottom: compact ? 'none' : '1px solid',
        borderBottomColor: 'divider',
      }}
    >
      {onSelect && !compact && (
        <Checkbox
          size="small" checked={selected}
          onClick={e => e.stopPropagation()}
          onChange={e => onSelect(event.id, e.target.checked)}
          sx={{ mt: -0.5, ml: -0.5 }}
        />
      )}

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Stack direction="row" spacing={1} alignItems="baseline">
          <Typography
            variant="body2"
            sx={{
              flex: 1, minWidth: 0, fontWeight: unread ? 600 : 400,
              color: 'text.primary',
            }}
          >
            {event.message}
          </Typography>
          {unread && (
            <Box sx={{
              width: 7, height: 7, borderRadius: '50%', bgcolor: accent,
              flexShrink: 0, mt: 0.5,
            }} />
          )}
          <Typography variant="caption" sx={{ color: 'text.secondary', flexShrink: 0 }}>
            {timeAgo(event.triggered_at)}
          </Typography>
        </Stack>

        {details.length > 0 && (
          <Typography
            variant="caption"
            // The detail line folds a gap's dates into ranges to stay inside
            // one nowrap caption; the full list lives here rather than in a
            // Tooltip, which would need a popper inside an already-dense row.
            title={gapDatesFull(event.payload?.gap_dates as string[] | undefined) || undefined}
            sx={{
              display: 'block', mt: 0.25, color: 'text.secondary',
              fontVariantNumeric: 'tabular-nums',
              overflow: 'hidden', textOverflow: 'ellipsis',
              whiteSpace: compact ? 'nowrap' : 'normal',
            }}
          >
            {details.join(' · ')}
          </Typography>
        )}

        {!compact && (
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.75 }}>
            <SeverityChip severity={event.severity} />
            {comparison && (
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                {comparison}
              </Typography>
            )}
            {provenance && (
              // Backfilled rows say so. They are real facts computed
              // retroactively, and the UI should not imply they were observed
              // as they happened.
              <Typography variant="caption" sx={{ color: 'text.disabled', fontStyle: 'italic' }}>
                {provenance}
              </Typography>
            )}
          </Stack>
        )}
      </Box>
    </Box>
  );
}
