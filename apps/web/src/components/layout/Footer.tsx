import React from 'react';
import { Box, Typography, useTheme } from '@mui/material';

export default function Footer() {
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';
  const currentYear = new Date().getFullYear();

  return (
    <Box
      component="footer"
      sx={{
        flexShrink: 0,
        width: '100%',
        m: 0,
        py: 0.25,
        px: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 0,
        borderTop: 'none',
        bgcolor: 'transparent',
      }}
    >
      {/* Line 1: RTS logo mark + "Powered by RTS" (prominent) */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
        <Box
          component="img"
          src="/assets/RTS_Logo.png"
          alt="RTS"
          onError={(e: React.SyntheticEvent<HTMLImageElement>) => {
            const img = e.currentTarget;
            if (img.src.endsWith('.png')) {
              img.src = '/assets/RTS_Logo.svg';
            } else {
              img.style.display = 'none';
            }
          }}
          sx={{
            height: 14,
            width: 'auto',
            opacity: 0.6,
            filter: isDark ? 'brightness(0) invert(1)' : 'none',
          }}
        />
        <Typography
          sx={{
            fontSize: '10px',
            fontWeight: 600,
            lineHeight: 1.1,
            letterSpacing: '0.2px',
            color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)',
          }}
        >
          Powered by RTS
        </Typography>
      </Box>

      {/* Line 2: Copyright (muted) */}
      <Typography
        sx={{
          fontSize: '8px',
          fontWeight: 600,
          lineHeight: 1.1,
          textAlign: 'center',
          letterSpacing: '0.2px',
          color: isDark ? 'rgba(255,255,255,0.20)' : 'rgba(0,0,0,0.20)',
        }}
      >
        © {currentYear} Revenue Technology Services
      </Typography>
    </Box>
  );
}
