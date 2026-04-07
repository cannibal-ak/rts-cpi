import React from 'react';
import { Box, Paper, Typography, Stack } from '@mui/material';
import { TrendingUp, TrendingDown, TrendingFlat } from '@mui/icons-material';

export interface KpiTile {
  label: string;
  value: string | number;
  sub?: string;
  trend?: 'up' | 'down' | 'flat';
  color?: string;
}

interface KpiTilesProps {
  tiles: KpiTile[];
}

export default function KpiTiles({ tiles }: KpiTilesProps) {
  return (
    <Stack direction="row" spacing={2} sx={{ mb: 2, flexWrap: 'wrap', '& > *': { minWidth: 160, flex: 1 } }}>
      {tiles.map((t, i) => (
        <Paper key={i} variant="outlined" sx={{ p: 2 }}>
          <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', fontWeight: 700, letterSpacing: 0.5 }}>
            {t.label}
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, mt: 0.5 }}>
            <Typography variant="h5" fontWeight={700} sx={{ color: t.color }}>
              {typeof t.value === 'number' ? t.value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 }) : t.value}
            </Typography>
            {t.trend === 'up' && <TrendingUp fontSize="small" color="success" />}
            {t.trend === 'down' && <TrendingDown fontSize="small" color="error" />}
            {t.trend === 'flat' && <TrendingFlat fontSize="small" color="disabled" />}
          </Box>
          {t.sub && <Typography variant="caption" color="text.secondary">{t.sub}</Typography>}
        </Paper>
      ))}
    </Stack>
  );
}
