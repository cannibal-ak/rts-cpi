import React from 'react';
import { Box, Typography, Chip, Tooltip, Paper, Stack } from '@mui/material';
import { AccessTime, CheckCircle, Warning, HelpOutline } from '@mui/icons-material';
import { DataFreshness } from '../../types';

interface DataFreshnessIndicatorProps {
  data: DataFreshness;
  compact?: boolean;
}

const statusConfig = {
  fresh: { color: 'success' as const, icon: <CheckCircle fontSize="small" />, label: 'Fresh' },
  stale: { color: 'warning' as const, icon: <Warning fontSize="small" />, label: 'Stale' },
  nodata: { color: 'default' as const, icon: <HelpOutline fontSize="small" />, label: 'No Data' },
  unknown: { color: 'default' as const, icon: <HelpOutline fontSize="small" />, label: 'Unknown' },
};

function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return 'N/A';
  const date = new Date(iso);
  if (isNaN(date.getTime())) return 'N/A';
  const diff = Date.now() - date.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ${mins % 60}m ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function DataFreshnessIndicator({ data, compact }: DataFreshnessIndicatorProps) {
  const cfg = statusConfig[data.status as keyof typeof statusConfig] || statusConfig.unknown;

  if (compact) {
    return (
      <Tooltip title={`${data.domain}: Last import ${formatRelativeTime(data.last_import_at)} — ${data.record_count.toLocaleString()} records`}>
        <Chip icon={cfg.icon} label={`${data.domain}: ${cfg.label}`} color={cfg.color} size="small" variant="outlined" />
      </Tooltip>
    );
  }

  return (
    <Paper variant="outlined" sx={{ p: 2, minWidth: 220 }}>
      <Stack spacing={1}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography variant="subtitle2">{data.domain}</Typography>
          <Chip icon={cfg.icon} label={cfg.label} color={cfg.color} size="small" />
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, color: 'text.secondary' }}>
          <AccessTime fontSize="small" />
          <Typography variant="caption">Last capture: {formatRelativeTime(data.last_capture_at)}</Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, color: 'text.secondary' }}>
          <AccessTime fontSize="small" />
          <Typography variant="caption">Last import: {formatRelativeTime(data.last_import_at)}</Typography>
        </Box>
        <Typography variant="caption" color="text.secondary">
          {data.record_count.toLocaleString()} records
        </Typography>
      </Stack>
    </Paper>
  );
}
