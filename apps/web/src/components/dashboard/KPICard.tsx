import React from 'react';
import { ButtonBase, Box, Typography } from '@mui/material';

export interface KPICardProps {
  label: string;
  value: string | number;
  subheader: string;
  isActive: boolean;
  onClick: () => void;
}

/**
 * A single clickable KPI tile. Light-blue card; active state gets an info
 * border + slightly darker fill + elevation. Built on ButtonBase so it is
 * keyboard-operable (Enter/Space) and focus-visible out of the box.
 */
export default function KPICard({ label, value, subheader, isActive, onClick }: KPICardProps) {
  return (
    <ButtonBase
      onClick={onClick}
      focusRipple
      aria-pressed={isActive}
      sx={{
        display: 'block',
        textAlign: 'left',
        width: '100%',
        height: '100%',
        borderRadius: '8px',
        p: '12px 16px',
        bgcolor: isActive ? '#cfe0fb' : '#dbeafe',
        border: '1.5px solid',
        borderColor: isActive ? 'info.main' : 'transparent',
        boxShadow: isActive ? 2 : 0,
        transition: 'background-color .15s ease, border-color .15s ease, box-shadow .15s ease',
        '&:hover': {
          bgcolor: isActive ? '#cfe0fb' : '#d2e3fb',
          borderColor: isActive ? 'info.main' : 'info.light',
        },
      }}
    >
      <Box sx={{ width: '100%' }}>
        <Typography sx={{ fontSize: 13, fontWeight: 600, color: '#4a6a8a', lineHeight: 1.3 }}>
          {label}
        </Typography>
        <Typography sx={{ fontSize: 30, fontWeight: 700, color: '#1A2027', lineHeight: 1.2, mt: '2px' }}>
          {value}
        </Typography>
        <Typography sx={{ fontSize: 11, color: '#7a9abb', lineHeight: 1.3, mt: '2px' }}>
          {subheader}
        </Typography>
      </Box>
    </ButtonBase>
  );
}
