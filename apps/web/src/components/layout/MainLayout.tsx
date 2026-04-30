import React, { useState } from 'react';
import { Box } from '@mui/material';
import { Outlet } from 'react-router-dom';
import AppBar from './AppBar';
import Sidebar from './Sidebar';

export default function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <Box sx={{ display: 'flex', height: '100vh', width: '100%', overflow: 'hidden' }}>
      <AppBar onToggleSidebar={() => setSidebarOpen(prev => !prev)} />
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          mt: 8,
          height: 'calc(100vh - 64px)',
          overflow: 'auto',
          minWidth: 0, // Crucial for flex child to shrink properly if content is wide
          display: 'flex',
          flexDirection: 'column',
          // Animations are implicitly handled by Sidebar's width transition
        }}
      >
        <Outlet />
      </Box>
    </Box>
  );
}
