import type React from 'react';
import { Box, Button, Typography, Skeleton, Tooltip, Chip, CircularProgress } from '@mui/material';
import { FilterAltOff, Check, Tune } from '@mui/icons-material';
import FilterSelect from './FilterSelect';
import { useBrandedChrome } from '../tenantChrome';
import type {
  DashboardFilter,
  DashboardFilterSelections,
} from '../../../api/client';

export interface WinairTopFilterBarProps {
  /** The dashboard's own native filters, from GET .../filter-config. */
  filters: DashboardFilter[];
  filtersLoading: boolean;
  filtersError: string | null;

  /** Edited-but-not-yet-applied selections, keyed by native filter id. */
  pending: DashboardFilterSelections;
  onPendingChange: (next: DashboardFilterSelections) => void;

  /** True when `pending` differs from what the dashboard is currently showing. */
  dirty: boolean;
  applying: boolean;
  onApply: () => void;
  onReset: () => void;

  /**
   * Name of the single chart these filters apply to, when the bar is scoped to
   * one (Chart view). Undefined means the whole dashboard.
   */
  scopeLabel?: string;

  /**
   * Extra controls rendered into the same row after the dashboard's own
   * filters, as one group that wraps as a unit — used for the Latest Prices
   * tab's two time ranges, which have no Superset counterpart. Pass them only
   * on the pane they act on, so a control is never on screen where it would
   * do nothing.
   */
  extraControls?: React.ReactNode;
}

/** A dropdown's cell. TimeRangeFilter sizes its own to match (wider basis —
 *  its readout shares the field with the slider). */
const FIELD_CELL_SX = { flex: '1 1 136px', minWidth: 0, maxWidth: 260 } as const;

/**
 * extraControls travel as ONE item, so a wrap moves them together — on the
 * Latest Prices tab the two time ranges land side by side on the second row
 * rather than leaving Duration alone and stretched under Departure Time.
 * Basis and cap are two TimeRangeFilter cells plus the gap between them.
 */
const EXTRA_GROUP_SX = {
  flex: '2.4 1 330px', minWidth: 0, maxWidth: 690,
  display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', gap: '10px',
} as const;

/**
 * WinAir's global filter bar — the dashboard's native filters lifted out of
 * Superset's left-hand panel and rendered above the iframe.
 *
 * Controls are built from the dashboard's own filter definitions, so adding or
 * retargeting a filter in Superset shows up here with no code change.
 *
 * One row: the native filters, then Clear all / Apply in a column labelled like
 * the fields, so the buttons sit level with the controls. It used to be an
 * actions row over a 170px auto-fill grid — a whole row spent on two buttons,
 * and at common desktop widths the last control wrapped onto a row of its own.
 * The page never scrolls, so those ~150px came straight out of the chart.
 *
 * The fields wrap as a flex row with a FIXED basis per cell. An earlier flex
 * row sized each control to its own label, which is why nothing lined up; a
 * shared basis keeps a single row aligned, and the max width stops a dashboard
 * with only two or three filters stretching each across the screen. The
 * actions stay out of the field row so a wrap can never strand them mid-row.
 *
 * The cap date is NOT here — it lives in the page header (CapDateChip), where
 * it is reachable from Chart view too. It used to lead this bar on its own
 * darker strip, because it scopes charts server-side via the guest token's RLS
 * clause while the filters below do not; with it gone, everything left acts on
 * the chart below and a second background would assert a split that no longer
 * exists.
 *
 * Changes are staged and applied on the Apply button rather than live. That is
 * forced by Superset, not a preference: an embedded dashboard reads filter
 * state from its URL exactly once, when it mounts, so applying a selection
 * means rebuilding the iframe and re-running every chart. Batching keeps that
 * to one reload per intent instead of one per dropdown.
 */
export default function WinairTopFilterBar({
  filters,
  filtersLoading,
  filtersError,
  pending,
  onPendingChange,
  dirty,
  applying,
  onApply,
  onReset,
  scopeLabel,
  extraControls,
}: WinairTopFilterBarProps) {
  const {
    BANNER_BG, BANNER_HEADER_BG, FILTER_ACCENT, FILTER_BG, FILTER_BORDER, FILTER_DISABLED_BG,
    FILTER_DISABLED_INK, FILTER_ERROR_INK, FILTER_HOVER_BG, FILTER_INK, FILTER_LABEL_INK,
    FILTER_MUTED_INK, FILTER_SKELETON, FILTER_SKELETON_COUNT, FILTER_SKELETON_TEXT,
  } = useBrandedChrome();

  // Count only what is on screen: a stale selection for a filter this dashboard
  // no longer surfaces would otherwise be counted with no control to clear it.
  const activeCount = filters.filter(f => (pending[f.id] ?? []).length > 0).length;
  // Clear stays keyed off the FULL pending set — a selection the bar is not
  // showing is still the user's, and they must always be able to drop it.
  const hasAnySelection = Object.values(pending).some(v => v && v.length > 0);

  return (
    <Box
      sx={{
        width: '100%', mb: 0.75, borderRadius: 1.5, overflow: 'hidden', boxShadow: 1,
        bgcolor: FILTER_BG,
        border: '1px solid', borderColor: FILTER_BORDER,
        color: FILTER_INK,
        px: 1.5, py: 1,
        display: 'flex',
        flexDirection: { xs: 'column', md: 'row' },
        // flex-start, not end: if the fields ever wrap, the actions line up
        // with the first row rather than drifting down to the last.
        alignItems: { xs: 'stretch', md: 'flex-start' },
        gap: { xs: 1, md: 1.5 },
      }}
    >
      {/* ── Filter fields ────────────────────────────────────────────────── */}
      <Box
        sx={{
          flex: 1,
          minWidth: 0,
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'flex-end',
          gap: '10px',
        }}
      >
        {/* The tenant's own visible-filter count (theme token) — a skeleton
            count that misses reflows the row on every load. */}
        {filtersLoading && Array.from({ length: FILTER_SKELETON_COUNT }, (_, i) => i).map(i => (
          <Box key={i} sx={FIELD_CELL_SX}>
            {/* mb matches the real label's, so the placeholder field sits
                level with the buttons and nothing shifts when filters land. */}
            <Skeleton
              variant="text"
              width="55%"
              sx={{ fontSize: 11, mb: '5px', bgcolor: FILTER_SKELETON_TEXT }}
            />
            <Skeleton
              variant="rounded"
              height={34}
              sx={{ bgcolor: FILTER_SKELETON }}
            />
          </Box>
        ))}

        {!filtersLoading && filtersError && (
          <Typography sx={{ flexBasis: '100%', fontSize: 12.5, color: FILTER_ERROR_INK }}>
            Filters unavailable — {filtersError}
          </Typography>
        )}

        {!filtersLoading && !filtersError && filters.length === 0 && (
          <Typography sx={{ flexBasis: '100%', fontSize: 12.5, color: FILTER_LABEL_INK }}>
            This dashboard has no filters.
          </Typography>
        )}

        {!filtersLoading && !filtersError && filters.map(f => (
          <Box key={f.id} sx={FIELD_CELL_SX}>
            <FilterSelect
              id={f.id}
              label={f.label}
              description={f.description}
              options={f.values}
              value={pending[f.id] ?? []}
              multiple={f.multi_select}
              onBanner
              onChange={next => onPendingChange({ ...pending, [f.id]: next })}
            />
          </Box>
        ))}

        {/* Extra controls that belong to whatever pane is showing, sharing the
            row so they line up with the dashboard's own filters. Unlike those,
            these act immediately — they are client-side and need no re-embed,
            so making the user press Apply would be a wait invented for the sake
            of symmetry. The caller only passes them where they apply. */}
        {extraControls && <Box sx={EXTRA_GROUP_SX}>{extraControls}</Box>}
      </Box>

      {/* ── Actions ──────────────────────────────────────────────────────
          Laid out like one more field — a label line over a 34px row — so
          Clear all / Apply sit level with the controls. On a phone it falls
          back to a header row above the fields. */}
      <Box
        sx={{
          flexShrink: 0,
          order: { xs: -1, md: 0 },
          display: 'flex',
          flexDirection: { xs: 'row', md: 'column' },
          // On a narrow phone the buttons drop to their own line; without the
          // wrap the label line shrinks under its own text and the "N active"
          // chip slides beneath Clear all.
          flexWrap: { xs: 'wrap', md: 'nowrap' },
          alignItems: { xs: 'center', md: 'flex-start' },
          justifyContent: 'space-between',
          gap: { xs: 1, md: '5px' },
          minWidth: 0,
        }}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.75,
            minWidth: 0,
            maxWidth: { xs: '100%', md: 260 },
          }}
        >
          <Tune sx={{ fontSize: 14, color: FILTER_MUTED_INK }} />
          <Typography
            component="span"
            sx={{
              fontSize: 11,
              fontWeight: 500,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              color: FILTER_LABEL_INK,
              whiteSpace: 'nowrap',
            }}
          >
            Filters
          </Typography>
          {/* Say out loud what these controls act on. Without it the bar looks
              identical in both views while doing something different in each. */}
          {scopeLabel && (
            <Typography
              noWrap
              sx={{ fontSize: 11, color: FILTER_LABEL_INK, minWidth: 0 }}
              title={scopeLabel}
            >
              — {scopeLabel} only
            </Typography>
          )}
          {/* aria-live on the host, not the Chip — the Chip unmounts at zero,
              and a removed node announces nothing. */}
          <Box aria-live="polite" sx={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
            {hasAnySelection && (
              <Chip
                label={`${activeCount} active`}
                size="small"
                sx={{
                  height: 16,
                  fontSize: 10.5,
                  fontWeight: 500,
                  bgcolor: FILTER_ACCENT,
                  color: '#ffffff',
                  '& .MuiChip-label': { px: 0.75 },
                }}
              />
            )}
          </Box>
        </Box>

        {/* ml auto keeps the buttons right-aligned when they wrap on a phone. */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, ml: { xs: 'auto', md: 0 } }}>
          <Tooltip title={hasAnySelection ? 'Clear all filters' : 'No filters applied'}>
            {/* span: a disabled button emits no events, so Tooltip needs a host */}
            <span>
              {/* Icon-only beside the fields (md+), where every pixel of this
                  column comes out of the field row — the text alone cost the
                  last filter its place on a 1920@125% laptop with the sidebar
                  open. The phone header row has room, so it keeps the words. */}
              <Button
                size="small"
                onClick={onReset}
                disabled={applying || !hasAnySelection}
                startIcon={<FilterAltOff fontSize="small" />}
                aria-label="Clear all filters"
                sx={{
                  // Field height, so the buttons sit level with the controls.
                  height: 34,
                  minWidth: { xs: 64, md: 34 },
                  color: FILTER_LABEL_INK,
                  fontSize: 12,
                  textTransform: 'none',
                  borderRadius: '8px',
                  px: { xs: 1.25, md: 0 },
                  whiteSpace: 'nowrap',
                  '& .MuiButton-startIcon': { mx: { md: 0 } },
                  '&:hover': { bgcolor: FILTER_HOVER_BG },
                  '&.Mui-disabled': { color: FILTER_DISABLED_INK },
                }}
              >
                <Box component="span" sx={{ display: { xs: 'inline', md: 'none' } }}>
                  Clear all
                </Box>
              </Button>
            </span>
          </Tooltip>

          <Tooltip
            title={applying ? 'Applying filters…' : dirty ? 'Apply filters to the dashboard' : 'No pending changes'}
          >
            <span>
              <Button
                size="small"
                variant="contained"
                onClick={onApply}
                disabled={!dirty || applying}
                // The visible label stays "Apply" for width's sake, so the busy
                // state has to be named for screen readers here — otherwise it
                // reads exactly like "nothing to apply".
                aria-label={applying ? 'Applying filters' : undefined}
                aria-busy={applying || undefined}
                // A spinner in place of the tick, not an "Applying…" label: the
                // button's width comes straight out of the field row, and a
                // wider label re-wrapped the filters for the length of the
                // request, bouncing the chart below.
                startIcon={applying
                  ? (
                    // The tick's own box (MUI sizes a small button's start
                    // icon to 18px), so not even the fields beside it shift by
                    // the few pixels a bare spinner differs.
                    <Box component="span" aria-hidden sx={{ width: 18, height: 18, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                      <CircularProgress size={14} color="inherit" />
                    </Box>
                  )
                  : <Check fontSize="small" />}
                sx={{
                  height: 34,
                  // The one red thing left in the card, and the only control
                  // that commits anything.
                  bgcolor: BANNER_BG,
                  color: '#ffffff',
                  fontSize: 12,
                  fontWeight: 700,
                  textTransform: 'none',
                  borderRadius: '8px',
                  px: 1.75,
                  whiteSpace: 'nowrap',
                  boxShadow: 'none',
                  '&:hover': { bgcolor: BANNER_HEADER_BG, boxShadow: 'none' },
                  '&.Mui-disabled': { bgcolor: FILTER_DISABLED_BG, color: FILTER_DISABLED_INK },
                }}
              >
                Apply
              </Button>
            </span>
          </Tooltip>
        </Box>
      </Box>
    </Box>
  );
}
