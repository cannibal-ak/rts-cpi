import React from 'react';
import { Box, Typography, Chip } from '@mui/material';
import { CheckCircle, RadioButtonUnchecked, Error, HourglassEmpty, Sync } from '@mui/icons-material';
import type { JobTimelineEntry, JobStatus } from '../../types';

const statusIcon: Record<JobStatus, React.ReactNode> = {
  queued: <HourglassEmpty fontSize="small" color="disabled" />,
  validating: <Sync fontSize="small" color="info" />,
  committed: <CheckCircle fontSize="small" color="success" />,
  failed: <Error fontSize="small" color="error" />,
};

const statusColor: Record<JobStatus, string> = {
  queued: 'text.disabled',
  validating: 'info.main',
  committed: 'success.main',
  failed: 'error.main',
};

interface StatusTimelineProps {
  timeline: JobTimelineEntry[];
}

export default function StatusTimeline({ timeline }: StatusTimelineProps) {
  return (
    <Box sx={{ pl: 1 }}>
      {timeline.map((entry, i) => (
        <Box key={i} sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5, mb: i < timeline.length - 1 ? 0 : 0, position: 'relative' }}>
          {/* Vertical connector */}
          {i < timeline.length - 1 && (
            <Box sx={{ position: 'absolute', left: 9, top: 22, width: 2, height: 'calc(100% - 4px)', bgcolor: 'divider' }} />
          )}
          <Box sx={{ mt: 0.25, zIndex: 1 }}>{statusIcon[entry.status]}</Box>
          <Box sx={{ pb: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="body2" fontWeight={600} sx={{ color: statusColor[entry.status], textTransform: 'capitalize' }}>
                {entry.status}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {new Date(entry.timestamp).toLocaleString()}
              </Typography>
            </Box>
            {entry.message && (
              <Typography variant="caption" color="text.secondary">{entry.message}</Typography>
            )}
          </Box>
        </Box>
      ))}
    </Box>
  );
}
