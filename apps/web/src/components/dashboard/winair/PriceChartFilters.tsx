import { Box, Slider, Typography, Tooltip } from '@mui/material';
import { alpha } from '@mui/material/styles';
import {
  formatDuration, DEP_TIME_MIN, DEP_TIME_MAX, DURATION_MIN, DURATION_MAX,
} from './priceChartTheme';
import { useBrandedChrome } from '../tenantChrome';

export type Range = [number, number];

export const FULL_DEP_RANGE: Range = [DEP_TIME_MIN, DEP_TIME_MAX];
export const FULL_DURATION_RANGE: Range = [DURATION_MIN, DURATION_MAX];

/** Is this range narrower than the whole axis, i.e. actually filtering? */
export function isNarrowed(value: Range, full: Range): boolean {
  return value[0] > full[0] || value[1] < full[1];
}

interface TimeRangeFilterProps {
  label: string;
  value: Range;
  min: number;
  max: number;
  onChange: (next: Range) => void;
  disabled?: boolean;
  help?: string;
}

/**
 * One labelled range slider with its two end readouts.
 *
 * Sized and labelled to sit as a single cell in WinairTopFilterBar's row,
 * beside the dashboard's own dropdowns, so the whole row reads as one set of
 * filters rather than two systems bolted together.
 *
 * Unlike those dropdowns this acts immediately: it filters points already in
 * the browser, so there is nothing for an Apply to batch.
 */
export default function TimeRangeFilter({
  label, value, min, max, onChange, disabled, help,
}: TimeRangeFilterProps) {
  const {
    FILTER_ACCENT, FILTER_FIELD_BG, FILTER_FIELD_LINE, FILTER_INK, FILTER_LABEL_INK,
    FILTER_MUTED_INK, FILTER_SLIDER_RAIL,
  } = useBrandedChrome();

  const active = value[0] > min || value[1] < max;

  const body = (
    // One cell of the bar's extra-controls group (WinairTopFilterBar
    // EXTRA_GROUP_SX, which assumes two of these). Wider basis than a dropdown
    // because the readout shares the field and the slider still needs room
    // to drag.
    <Box sx={{ flex: '1 1 160px', minWidth: 0, maxWidth: 340 }}>
      <Typography
        component="span"
        sx={{
          // Same label as FilterSelect's, to the pixel — any difference in
          // spacing drops these two labels below the dropdowns' in the row.
          display: 'block',
          fontSize: 11,
          fontWeight: 500,
          color: active ? FILTER_INK : FILTER_LABEL_INK,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          mb: '5px',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {label}
      </Typography>

      <Box
        sx={{
          border: '1px solid',
          borderColor: active ? FILTER_ACCENT : FILTER_FIELD_LINE,
          bgcolor: FILTER_FIELD_BG,
          borderRadius: '8px',
          px: 1,
          pt: 0.25,
          pb: 0.5,
          height: 34,
          display: 'flex',
          alignItems: 'center',
          gap: 1,
        }}
      >
        <Slider
          size="small"
          value={value}
          min={min}
          max={max}
          // 15 minutes: finer than any published schedule needs, and coarse
          // enough that a drag lands on a round time.
          step={15}
          disabled={disabled}
          onChange={(_, next) => onChange(next as Range)}
          valueLabelDisplay="auto"
          valueLabelFormat={(v: number) => formatDuration(v)}
          aria-label={label}
          getAriaValueText={(v: number) => formatDuration(v)}
          sx={{
            color: FILTER_ACCENT,
            py: 0,
            '& .MuiSlider-rail': { backgroundColor: FILTER_SLIDER_RAIL, opacity: 1 },
            '& .MuiSlider-track': { border: 'none' },
            '& .MuiSlider-thumb': {
              width: 11,
              height: 11,
              // The halo is the accent at the alpha the WinAir teal shipped with,
              // derived rather than literal so each tenant's sliders glow their
              // own chosen-state colour (WinAir renders byte-identically).
              '&:hover, &.Mui-focusVisible': { boxShadow: `0 0 0 6px ${alpha(FILTER_ACCENT, 0.16)}` },
            },
            '& .MuiSlider-valueLabel': { fontSize: 10, py: 0.25, px: 0.5 },
          }}
        />
        {/* End readouts. Display, not input: the slider is the control, and a
            half-typed "1:" in a text box would be a filter nobody asked for. */}
        <Typography
          component="span"
          sx={{
            fontSize: 10.5,
            color: active ? FILTER_INK : FILTER_MUTED_INK,
            fontVariantNumeric: 'tabular-nums',
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
        >
          {formatDuration(value[0])}–{formatDuration(value[1])}
        </Typography>
      </Box>
    </Box>
  );

  return help ? <Tooltip title={help}>{body}</Tooltip> : body;
}
