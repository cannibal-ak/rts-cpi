import React from 'react';
import { Box, Typography, Button } from '@mui/material';
import { ErrorOutline } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

export default function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '60vh',
        textAlign: 'center',
        p: 4,
      }}
    >
      <ErrorOutline sx={{ fontSize: 80, color: 'error.main', mb: 2 }} />
      <Typography variant="h4" gutterBottom>404 — Page Not Found</Typography>
      <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 480, mb: 3 }}>
        The page you are looking for does not exist or has been moved.
      </Typography>
      <Button variant="contained" onClick={() => navigate('/')}>Return to Dashboard</Button>
    </Box>
  );
}
