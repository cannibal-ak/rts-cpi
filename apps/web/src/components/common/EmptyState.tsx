import React from 'react';
import { Box, Typography, Button } from '@mui/material';
import { darken } from '@mui/material/styles';
import { Inbox } from '@mui/icons-material';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  /**
   * Tenant-brand fill for the action button (a literal color — it feeds
   * darken()). Omitted, the button stays theme primary.
   */
  accent?: string;
}

export default function EmptyState({ icon, title, description, actionLabel, onAction, accent }: EmptyStateProps) {
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
        <Button
          variant="contained"
          onClick={onAction}
          sx={accent ? { bgcolor: accent, '&:hover': { bgcolor: darken(accent, 0.15) } } : undefined}
        >
          {actionLabel}
        </Button>
      )}
    </Box>
  );
}
