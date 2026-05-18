/**
 * Left-side panel listing all analytical charts in the current dashboard.
 * Clicking a row selects that chart and (via parent) switches to chart view.
 *
 * Layout: fixed-width sidebar on >= md viewports; collapses to a horizontal
 * scrollable chip rail on narrow viewports via the `horizontal` prop.
 */
import React from 'react';
import {
  Box, Typography, CircularProgress, Button, Chip, Stack,
} from '@mui/material';
import {
  TrendingUp, BarChart as BarChartIcon, PieChart as PieChartIcon,
  TableChart, GridOn, ShowChart, ScatterPlot,
} from '@mui/icons-material';
import type { Theme } from '@mui/material/styles';
import type { DashboardChart } from '../../api/client';

interface Props {
  charts: DashboardChart[];
  selectedSliceId: number | null;
  onSelectChart: (sliceId: number) => void;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  horizontal?: boolean;
}

function iconForViz(vizType: string | null) {
  const v = vizType ?? '';
  if (v.includes('line') || v === 'line') return TrendingUp;
  if (v.includes('bar')) return BarChartIcon;
  if (v.includes('pie')) return PieChartIcon;
  if (v === 'table' || v.startsWith('pivot_table')) return TableChart;
  if (v === 'heatmap') return GridOn;
  if (v === 'bubble' || v.includes('scatter')) return ScatterPlot;
  if (v === 'mixed_timeseries') return ShowChart;
  return ShowChart;
}

// Selected-state palette — blue ramp, dark-mode safe.
// Light: solid hex from the spec.  Dark: low-alpha overlays so text stays readable.
const selectedSx = (theme: Theme) => {
  const dark = theme.palette.mode === 'dark';
  return {
    bg:       dark ? 'rgba(55,138,221,0.15)' : '#E6F1FB',
    border:   dark ? 'rgba(55,138,221,0.35)' : '#85B7EB',
    text:     dark ? '#85B7EB'               : '#0C447C',
    iconBg:   dark ? 'rgba(55,138,221,0.25)' : '#B5D4F4',
    iconText: dark ? '#85B7EB'               : '#0C447C',
    index:    dark ? '#85B7EB'               : '#185FA5',
  };
};

export default function ChartSelectorPanel({
  charts, selectedSliceId, onSelectChart, loading, error, onRetry, horizontal = false,
}: Props) {
  // ── Error state ──
  if (error) {
    return (
      <Box sx={{
        ...(horizontal
          ? { width: '100%', py: 1, px: 2 }
          : { width: 240, borderRight: '1px solid', borderColor: 'divider', p: 1.5 }),
      }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
          Could not load chart list
        </Typography>
        <Button size="small" variant="outlined" onClick={onRetry}>Retry</Button>
      </Box>
    );
  }

  // ── Loading state ──
  if (loading && charts.length === 0) {
    return (
      <Box sx={{
        ...(horizontal
          ? { width: '100%', py: 1, display: 'flex', justifyContent: 'center' }
          : { width: 240, borderRight: '1px solid', borderColor: 'divider', p: 2, display: 'flex', justifyContent: 'center' }),
      }}>
        <CircularProgress size={20} />
      </Box>
    );
  }

  // ── Horizontal (narrow-viewport) chip rail ──
  if (horizontal) {
    return (
      <Box sx={{
        width: '100%',
        overflowX: 'auto',
        py: 1, px: 1,
        borderBottom: '1px solid',
        borderColor: 'divider',
        '&::-webkit-scrollbar': { height: 4 },
      }}>
        <Stack direction="row" spacing={1} sx={{ width: 'max-content' }}>
          {charts.map(c => {
            const Icon = iconForViz(c.viz_type);
            const selected = c.slice_id === selectedSliceId;
            return (
              <Chip
                key={c.slice_id}
                icon={<Icon sx={{ fontSize: 16 }} />}
                label={c.slice_name}
                size="small"
                color={selected ? 'primary' : 'default'}
                variant={selected ? 'filled' : 'outlined'}
                onClick={() => onSelectChart(c.slice_id)}
                sx={{ maxWidth: 240 }}
              />
            );
          })}
        </Stack>
      </Box>
    );
  }

  // ── Vertical sidebar ──
  return (
    <Box sx={(theme) => ({
      width: 240,
      flexShrink: 0,
      borderRight: '1px solid',
      borderColor: 'divider',
      bgcolor: 'background.paper',
      py: 1.5,
      px: 1,
      display: 'flex',
      flexDirection: 'column',
      gap: 0.5,
      // Independent vertical scroll so dashboards with many charts don't
      // push the sidebar past the viewport, and so the right-pane scroll
      // (chart iframe) doesn't drag the sidebar along with it.
      overflowY: 'auto',
      overflowX: 'hidden',
      // Slim, theme-aware scrollbar so it doesn't dominate the 240px column.
      '&::-webkit-scrollbar': { width: 6 },
      '&::-webkit-scrollbar-thumb': {
        backgroundColor: theme.palette.mode === 'dark'
          ? 'rgba(255,255,255,0.2)'
          : 'rgba(0,0,0,0.18)',
        borderRadius: 3,
      },
    })}>
      <Typography
        sx={{
          px: 1,
          pb: 0.75,
          fontSize: 11,
          letterSpacing: 0.5,
          fontWeight: 500,
          color: 'text.secondary',
          textTransform: 'uppercase',
        }}
      >
        Charts
      </Typography>

      {charts.map((c, idx) => {
        const Icon = iconForViz(c.viz_type);
        const selected = c.slice_id === selectedSliceId;
        return (
          <Box
            key={c.slice_id}
            role="button"
            tabIndex={0}
            onClick={() => onSelectChart(c.slice_id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelectChart(c.slice_id);
              }
            }}
            sx={(theme) => {
              const sel = selectedSx(theme);
              return {
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                px: 1.5,
                py: '9px',
                borderRadius: 1,             // 8px
                border: '1px solid',
                borderColor: selected ? sel.border : 'transparent',
                bgcolor: selected ? sel.bg : 'transparent',
                color: selected ? sel.text : 'text.primary',
                cursor: 'pointer',
                transition: 'background-color 0.15s, border-color 0.15s',
                outline: 'none',
                '&:hover': {
                  bgcolor: selected ? sel.bg : 'action.hover',
                },
                '&:focus-visible': {
                  borderColor: selected ? sel.border : theme.palette.primary.main,
                },
              };
            }}
          >
            {/* Icon box */}
            <Box
              sx={(theme) => {
                const sel = selectedSx(theme);
                return {
                  width: 28,
                  height: 28,
                  flexShrink: 0,
                  borderRadius: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  bgcolor: selected
                    ? sel.iconBg
                    : (theme.palette.mode === 'dark' ? 'action.hover' : theme.palette.grey[100]),
                  color: selected ? sel.iconText : 'text.secondary',
                  transition: 'background-color 0.15s, color 0.15s',
                };
              }}
            >
              <Icon sx={{ fontSize: 15 }} />
            </Box>

            {/* Chart name — up to 2 lines */}
            <Box
              sx={{
                flex: 1,
                minWidth: 0,
                fontSize: 13,
                lineHeight: 1.3,
                fontWeight: selected ? 500 : 400,
                overflow: 'hidden',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                wordBreak: 'break-word',
              }}
            >
              {c.slice_name}
            </Box>

            {/* Index number */}
            <Box
              sx={(theme) => {
                const sel = selectedSx(theme);
                return {
                  flexShrink: 0,
                  minWidth: 14,
                  textAlign: 'right',
                  fontSize: 11,
                  color: selected ? sel.index : 'text.disabled',
                  fontVariantNumeric: 'tabular-nums',
                };
              }}
            >
              {idx + 1}
            </Box>
          </Box>
        );
      })}

      {charts.length === 0 && !loading && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ px: 1.5, py: 2, fontStyle: 'italic' }}
        >
          No charts available
        </Typography>
      )}
    </Box>
  );
}
