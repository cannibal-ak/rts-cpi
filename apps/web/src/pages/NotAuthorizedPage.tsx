import React from 'react';
import { Box, Typography, Button } from '@mui/material';
import { Lock } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';

export default function NotAuthorizedPage() {
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
      <Lock sx={{ fontSize: 80, color: 'text.disabled', mb: 2 }} />
      <Typography variant="h4" gutterBottom>Not Authorized</Typography>
      <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 480, mb: 3 }}>
        You do not have the required permissions to access this page. Please contact your tenant administrator if you believe this is an error.
      </Typography>
      <Button variant="contained" onClick={() => navigate('/')}>Return to Home</Button>
    </Box>
  );
}
