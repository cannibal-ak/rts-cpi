import type React from 'react';
import { Box, Button, Typography, Skeleton, Tooltip, Chip } from '@mui/material';
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
   * Extra controls rendered into the same grid after the dashboard's own
   * filters — used for the Latest Prices tab's time ranges, which have no
   * Superset counterpart. Pass them only on the pane they act on, so a
   * control is never on screen where it would do nothing.
   */
  extraControls?: React.ReactNode;
}

/**
 * WinAir's global filter bar — the dashboard's native filters lifted out of
 * Superset's left-hand panel and rendered above the iframe.
 *
 * Controls are built from the dashboard's own filter definitions, so adding or
 * retargeting a filter in Superset shows up here with no code change.
 *
 * An actions row over a grid of the native filters. The grid is deliberate — a
 * wrapped flex row sized each control to its own label, so nothing lined up
 * either horizontally or vertically once the row wrapped, and the action
 * buttons ended up wherever the wrap dropped them. Fixed columns keep both
 * stable at any width. The actions stay out of the grid on purpose: auto-fill
 * would size Apply to a single 170px track.
 *
 * The cap date is NOT here — it lives in the page header (CapDateChip), where
 * it is reachable from Chart view too. It used to lead this bar on its own
 * darker strip, because it scopes charts server-side via the guest token's RLS
 * clause while the filters below do not; with it gone, everything left acts on
 * the grid below and a second background would assert a split that no longer
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
    FILTER_MUTED_INK, FILTER_SKELETON, FILTER_SKELETON_TEXT,
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
        px: 1.75, pt: 1, pb: 1.5,
      }}
    >
      {/* ── Actions row ─────────────────────────────────────────────────── */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 1.25,
          rowGap: 1,
          mb: 1.25,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, minWidth: 0 }}>
          <Tune sx={{ fontSize: 17, color: FILTER_MUTED_INK }} />
          <Typography sx={{ fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap' }}>
            Filters
          </Typography>
          {/* Say out loud what these controls act on. Without it the bar looks
              identical in both views while doing something different in each. */}
          {scopeLabel && (
            <Typography
              noWrap
              sx={{ fontSize: 12, color: FILTER_LABEL_INK, minWidth: 0 }}
              title={scopeLabel}
            >
              — {scopeLabel} only
            </Typography>
          )}
        </Box>

        {/* aria-live on the host, not the Chip — the Chip unmounts at zero,
            and a removed node announces nothing. */}
        <Box aria-live="polite" sx={{ display: 'flex', alignItems: 'center' }}>
          {hasAnySelection && (
            <Chip
              label={`${activeCount} active`}
              size="small"
              sx={{
                height: 20,
                fontSize: 11,
                fontWeight: 500,
                bgcolor: FILTER_ACCENT,
                color: '#ffffff',
              }}
            />
          )}
        </Box>

        <Box sx={{ flexGrow: 1 }} />

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <Tooltip title={hasAnySelection ? 'Clear all filters' : 'No filters applied'}>
            {/* span: a disabled button emits no events, so Tooltip needs a host */}
            <span>
              <Button
                size="small"
                onClick={onReset}
                disabled={applying || !hasAnySelection}
                startIcon={<FilterAltOff fontSize="small" />}
                sx={{
                  color: FILTER_LABEL_INK,
                  fontSize: 12,
                  textTransform: 'none',
                  borderRadius: '8px',
                  px: 1.25,
                  '&:hover': { bgcolor: FILTER_HOVER_BG },
                  '&.Mui-disabled': { color: FILTER_DISABLED_INK },
                }}
              >
                Clear all
              </Button>
            </span>
          </Tooltip>

          <Tooltip title={dirty ? 'Apply filters to the dashboard' : 'No pending changes'}>
            <span>
              <Button
                size="small"
                variant="contained"
                onClick={onApply}
                disabled={!dirty || applying}
                startIcon={<Check fontSize="small" />}
                sx={{
                  // The one red thing left in the card, and the only control
                  // that commits anything.
                  bgcolor: BANNER_BG,
                  color: '#ffffff',
                  fontSize: 12,
                  fontWeight: 700,
                  textTransform: 'none',
                  borderRadius: '8px',
                  px: 1.75,
                  boxShadow: 'none',
                  '&:hover': { bgcolor: BANNER_HEADER_BG, boxShadow: 'none' },
                  '&.Mui-disabled': { bgcolor: FILTER_DISABLED_BG, color: FILTER_DISABLED_INK },
                }}
              >
                {applying ? 'Applying…' : 'Apply'}
              </Button>
            </span>
          </Tooltip>
        </Box>
      </Box>

      {/* ── Filter grid ──────────────────────────────────────────────────
          One column count for the whole grid, so every field shares a width
          and lines up on both axes however many filters the dashboard
          defines. auto-fill rather than auto-fit: auto-fit collapses the
          empty tracks, which would stretch a two-filter dashboard's controls
          across half the screen each. */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))',
          gap: '12px 14px',
          alignItems: 'end',
        }}
      >
        {/* Four, matching WM's filter count after suppression — a skeleton
            count that overshoots reflows the grid on every load. */}
        {filtersLoading && [0, 1, 2, 3].map(i => (
          <Box key={i}>
            <Skeleton
              variant="text"
              width="55%"
              sx={{ fontSize: 11, bgcolor: FILTER_SKELETON_TEXT }}
            />
            <Skeleton
              variant="rounded"
              height={34}
              sx={{ bgcolor: FILTER_SKELETON }}
            />
          </Box>
        ))}

        {!filtersLoading && filtersError && (
          <Typography sx={{ gridColumn: '1 / -1', fontSize: 12.5, color: FILTER_ERROR_INK }}>
            Filters unavailable — {filtersError}
          </Typography>
        )}

        {!filtersLoading && !filtersError && filters.length === 0 && (
          <Typography sx={{ gridColumn: '1 / -1', fontSize: 12.5, color: FILTER_LABEL_INK }}>
            This dashboard has no filters.
          </Typography>
        )}

        {!filtersLoading && !filtersError && filters.map(f => (
          <FilterSelect
            key={f.id}
            id={f.id}
            label={f.label}
            description={f.description}
            options={f.values}
            value={pending[f.id] ?? []}
            multiple={f.multi_select}
            onBanner
            onChange={next => onPendingChange({ ...pending, [f.id]: next })}
          />
        ))}

        {/* Extra controls that belong to whatever pane is showing, sharing the
            grid so they line up with the dashboard's own filters. Unlike those,
            these act immediately — they are client-side and need no re-embed,
            so making the user press Apply would be a wait invented for the sake
            of symmetry. The caller only passes them where they apply. */}
        {extraControls}
      </Box>
    </Box>
  );
}
