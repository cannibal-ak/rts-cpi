import React from 'react';
import { Chip } from '@mui/material';

const statusColors: Record<string, 'success' | 'warning' | 'error' | 'info' | 'default'> = {
  // Legacy lowercase
  committed: 'success',
  active: 'success',
  fresh: 'success',
  sent: 'success',
  validating: 'info',
  queued: 'default',
  pending: 'default',
  inactive: 'default',
  failed: 'error',
  error: 'error',
  critical: 'error',
  stale: 'warning',
  warning: 'warning',
  info: 'info',
  private: 'default',
  team: 'info',
  public: 'success',
  // Phase A ingestion statuses (uppercase, server-authoritative)
  STAGED: 'default',
  VALIDATING: 'info',
  VALIDATED: 'info',
  COMMITTING: 'info',
  COMMITTED: 'success',
  REJECTED: 'warning',
  REPLACED: 'default',
  FAILED: 'error',
};

interface StatusChipProps {
  status: string;
  size?: 'small' | 'medium';
}

export default function StatusChip({ status, size = 'small' }: StatusChipProps) {
  return (
    <Chip
      label={status.charAt(0).toUpperCase() + status.slice(1).replace('_', ' ')}
      color={statusColors[status] || 'default'}
      size={size}
      variant="outlined"
    />
  );
}
