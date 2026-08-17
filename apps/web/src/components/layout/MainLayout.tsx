import { useState } from 'react';
import { Box, useMediaQuery, useTheme } from '@mui/material';
import { Outlet } from 'react-router-dom';
import AppBar from './AppBar';
import Sidebar from './Sidebar';
import Footer from './Footer';

// Persisted like the theme choice so a refresh keeps the sidebar the way the
// user left it. localStorage can be unavailable (private mode), so reads and
// writes both fail soft.
const SIDEBAR_OPEN_KEY = 'rts-sidebar-open';

export default function MainLayout() {
  const theme = useTheme();
  // Same breakpoint the Sidebar uses to pick its Drawer variant.
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  // Two states on purpose. Desktop open/collapsed is a durable preference;
  // the mobile drawer is a modal overlay, so it must always START closed (a
  // phone must never boot with the nav covering the page) and its opens and
  // closes are ephemeral — a phone session must not rewrite the desktop
  // default. Crossing the breakpoint mid-session switches which state rules,
  // so narrowing a window can't throw the overlay over the app either.
  const [desktopOpen, setDesktopOpen] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_OPEN_KEY) !== 'false';
    } catch {
      return true;
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);

  const sidebarOpen = isMobile ? mobileOpen : desktopOpen;
  const setSidebarOpen = (next: boolean) => {
    if (isMobile) {
      setMobileOpen(next);
      return;
    }
    setDesktopOpen(next);
    try {
      localStorage.setItem(SIDEBAR_OPEN_KEY, String(next));
    } catch {
      // ignore — the choice just won't survive the reload
    }
  };

  return (
    <Box sx={{ display: 'flex', height: '100vh', width: '100%', overflow: 'hidden' }}>
      <AppBar onToggleSidebar={() => setSidebarOpen(!sidebarOpen)} />
      <Sidebar
        open={sidebarOpen}
        onOpen={() => setSidebarOpen(true)}
        onClose={() => setSidebarOpen(false)}
      />
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
