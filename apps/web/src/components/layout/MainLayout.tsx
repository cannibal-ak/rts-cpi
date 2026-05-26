import React, { useState, useEffect } from 'react';
import { Box } from '@mui/material';
import { Outlet } from 'react-router-dom';
import AppBar from './AppBar';
import Sidebar from './Sidebar';
import Footer from './Footer';

export default function MainLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Auto-collapse the sidebar 2.5s after initial load: users see the
  // navigation briefly, then get maximum content area. Fires once on mount
  // (MainLayout stays mounted across route changes), so it does not re-fire
  // per navigation; the hamburger toggle still works normally afterward.
  useEffect(() => {
    const timer = setTimeout(() => setSidebarOpen(false), 2500);
    return () => clearTimeout(timer);
  }, []);

  return (
    <Box sx={{ display: 'flex', height: '100vh', width: '100%', overflow: 'hidden' }}>
      <AppBar onToggleSidebar={() => setSidebarOpen(prev => !prev)} />
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          pt: 1,
          px: 3,
          pb: 0,
          mt: 8,
          height: 'calc(100vh - 64px)',
          overflow: 'auto',
          minWidth: 0, // Crucial for flex child to shrink properly if content is wide
          display: 'flex',
          flexDirection: 'column',
          // Animations are implicitly handled by Sidebar's width transition
        }}
      >
        {/* Content fills the available height (definite, so pages using
            height:100% still resolve) and pushes the footer to the bottom
            when content is short; on long pages it grows and main scrolls. */}
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <Outlet />
        </Box>
        <Footer />
      </Box>
    </Box>
  );
}
