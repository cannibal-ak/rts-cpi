import { Box, Button, Typography, Skeleton, Tooltip } from '@mui/material';
import { FilterAltOff, Check } from '@mui/icons-material';
import DateFilterToggle from '../DateFilterToggle';
import FilterSelect from './FilterSelect';
import type {
  DashboardDateFilter,
  DashboardFilter,
  DashboardFilterSelections,
} from '../../../api/client';

/** WinAir brand teal. A fixed dark surface, so it reads the same in both themes. */
const BANNER_BG = '#005973';

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

  availableDates: string[];
  dateFilter: DashboardDateFilter;
  onDateFilterChange: (next: DashboardDateFilter) => void;
  datesLoading?: boolean;
}

/**
 * WinAir's global filter bar — the dashboard's native filters lifted out of
 * Superset's left-hand panel and rendered above the iframe.
 *
 * Controls are built from the dashboard's own filter definitions, so adding or
 * retargeting a filter in Superset shows up here with no code change.
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
  availableDates,
  dateFilter,
  onDateFilterChange,
  datesLoading = false,
}: WinairTopFilterBarProps) {
  const hasAnySelection = Object.values(pending).some(v => v && v.length > 0);

  return (
    <Box sx={{ width: '100%', mb: 0.75, borderRadius: 1.5, overflow: 'hidden', boxShadow: 1 }}>
      <Box
        sx={{
          bgcolor: BANNER_BG,
          color: '#ffffff',
          px: 1.5,
          py: 1,
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 1,
        }}
      >
        {/* Cap date first — it scopes every chart server-side via the guest
            token's RLS clause, unlike the native filters beside it. */}
        <Box sx={{ bgcolor: 'rgba(255,255,255,0.14)', borderRadius: 1, px: 0.75, py: 0.25 }}>
          <DateFilterToggle
            availableDates={availableDates}
            value={dateFilter}
            onChange={onDateFilterChange}
            disabled={datesLoading || availableDates.length === 0}
          />
        </Box>

        {filtersLoading && (
          <>
            {[0, 1, 2, 3].map(i => (
              <Skeleton
                key={i}
                variant="rounded"
                width={170}
                height={34}
                sx={{ bgcolor: 'rgba(255,255,255,0.18)' }}
              />
            ))}
          </>
        )}

        {!filtersLoading && filtersError && (
          <Typography sx={{ fontSize: 12.5, color: '#ffd9d9' }}>
            Filters unavailable — {filtersError}
          </Typography>
        )}

        {!filtersLoading && !filtersError && filters.map(f => (
          <FilterSelect
            key={f.id}
            label={f.label}
            description={f.description}
            options={f.values}
            value={pending[f.id] ?? []}
            multiple={f.multi_select}
            onDark
            onChange={next => onPendingChange({ ...pending, [f.id]: next })}
          />
        ))}

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
                  color: '#ffffff',
                  fontSize: 12,
                  textTransform: 'none',
                  '&.Mui-disabled': { color: 'rgba(255,255,255,0.4)' },
                }}
              >
                Clear
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
                  bgcolor: '#ffffff',
                  color: BANNER_BG,
                  fontSize: 12,
                  fontWeight: 700,
                  textTransform: 'none',
                  boxShadow: 'none',
                  '&:hover': { bgcolor: '#e6f2f6', boxShadow: 'none' },
                  '&.Mui-disabled': { bgcolor: 'rgba(255,255,255,0.25)', color: 'rgba(255,255,255,0.6)' },
                }}
              >
                {applying ? 'Applying…' : 'Apply'}
              </Button>
            </span>
          </Tooltip>
        </Box>
      </Box>
    </Box>
  );
}
