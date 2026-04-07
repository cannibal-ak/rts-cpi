import React from 'react';
import { Box, Button, Tooltip } from '@mui/material';
import { FileDownload } from '@mui/icons-material';
import { useSession } from '../../context/SessionContext';

interface ActionBarProps {
  onExport?: () => void;
  children?: React.ReactNode;
}

export default function ActionBar({ onExport, children }: ActionBarProps) {
  const { hasCapability } = useSession();

  const canExport = hasCapability(['exports']);

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: 1,
        py: 1,
        px: 2,
        borderBottom: 1,
        borderColor: 'divider',
        bgcolor: 'background.paper',
        flexWrap: 'wrap',
      }}
    >
      {children}
      <Box sx={{ flexGrow: 1 }} />
      {canExport && (
        <Tooltip title="Export data">
          <Button size="small" startIcon={<FileDownload />} onClick={onExport}>Export</Button>
        </Tooltip>
      )}
    </Box>
  );
}
