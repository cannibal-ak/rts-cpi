import React from 'react';
import { Box, Typography, Button } from '@mui/material';
import { Inbox } from '@mui/icons-material';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
}

export default function EmptyState({ icon, title, description, actionLabel, onAction }: EmptyStateProps) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        py: 8,
        px: 3,
        textAlign: 'center',
      }}
      role="status"
      aria-label={title}
    >
      <Box sx={{ color: 'text.disabled', mb: 2 }}>
        {icon || <Inbox sx={{ fontSize: 64 }} />}
      </Box>
      <Typography variant="h6" gutterBottom>{title}</Typography>
      {description && (
        <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 400, mb: 2 }}>
          {description}
        </Typography>
      )}
      {actionLabel && onAction && (
        <Button variant="contained" onClick={onAction}>{actionLabel}</Button>
      )}
    </Box>
  );
}
