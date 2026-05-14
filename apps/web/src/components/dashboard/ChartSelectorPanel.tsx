/**
 * Left-side panel listing all analytical charts in the current dashboard.
 * Clicking a row selects that chart and (via parent) switches to chart view.
 *
 * Layout: fixed-width sidebar on >= md viewports; the parent collapses it to a
 * horizontal chip rail on narrow viewports via the `horizontal` prop.
 */
import React from 'react';
import {
  Box, List, ListItemButton, ListItemIcon, ListItemText, Typography,
  CircularProgress, Button, Chip, Stack,
} from '@mui/material';
import {
  TrendingUp, BarChart as BarChartIcon, PieChart as PieChartIcon,
  TableChart, GridOn, ShowChart, ScatterPlot,
} from '@mui/icons-material';
import type { DashboardChart } from '../../api/client';

interface Props {
  charts: DashboardChart[];
  selectedSliceId: number | null;
  onSelectChart: (sliceId: number) => void;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  horizontal?: boolean;   // narrow viewport: render as horizontal chip rail
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

export default function ChartSelectorPanel({
  charts, selectedSliceId, onSelectChart, loading, error, onRetry, horizontal = false,
}: Props) {
  // ── Error state ──
  if (error) {
    return (
      <Box sx={{
        ...(horizontal ? { width: '100%', py: 1 } : { width: 220, borderRight: '1px solid', borderColor: 'divider', p: 2 }),
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
          : { width: 220, borderRight: '1px solid', borderColor: 'divider', p: 2, display: 'flex', justifyContent: 'center' }),
      }}>
        <CircularProgress size={20} />
      </Box>
    );
  }

  // ── Horizontal (mobile) chip rail ──
  if (horizontal) {
    return (
      <Box sx={{
        width: '100%',
        overflowX: 'auto',
        py: 1,
        px: 1,
        borderBottom: '1px solid',
        borderColor: 'divider',
        // Hide horizontal scrollbar for a clean look while keeping wheel/touch scroll.
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
                sx={{ maxWidth: 220 }}
              />
            );
          })}
        </Stack>
      </Box>
    );
  }

  // ── Vertical sidebar ──
  return (
    <Box sx={{
      width: 220,
      flexShrink: 0,
      borderRight: '1px solid',
      borderColor: 'divider',
      bgcolor: 'background.paper',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
    }}>
      <Typography
        variant="caption"
        sx={{
          px: 2,
          pt: 2,
          pb: 1,
          letterSpacing: 1.2,
          fontWeight: 700,
          color: 'text.secondary',
          textTransform: 'uppercase',
          fontSize: '0.7rem',
        }}
      >
        Charts
      </Typography>

      <List dense sx={{ flex: 1, overflowY: 'auto', py: 0 }}>
        {charts.map(c => {
          const Icon = iconForViz(c.viz_type);
          const selected = c.slice_id === selectedSliceId;
          return (
            <ListItemButton
              key={c.slice_id}
              selected={selected}
              onClick={() => onSelectChart(c.slice_id)}
              sx={{
                pl: 2, pr: 1, py: 0.75,
                '&.Mui-selected': {
                  bgcolor: 'primary.main',
                  color: 'primary.contrastText',
                  '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
                  '&:hover': { bgcolor: 'primary.dark' },
                },
              }}
            >
              <ListItemIcon sx={{ minWidth: 28, color: selected ? 'inherit' : 'text.secondary' }}>
                <Icon sx={{ fontSize: 18 }} />
              </ListItemIcon>
              <ListItemText
                primary={c.slice_name}
                primaryTypographyProps={{
                  noWrap: true,
                  variant: 'body2',
                  sx: { fontSize: '0.82rem', fontWeight: selected ? 600 : 400 },
                }}
              />
            </ListItemButton>
          );
        })}
        {charts.length === 0 && !loading && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ px: 2, py: 2, display: 'block', fontStyle: 'italic' }}
          >
            No charts available
          </Typography>
        )}
      </List>
    </Box>
  );
}
