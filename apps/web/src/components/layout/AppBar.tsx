import React from 'react';
import {
  AppBar as MuiAppBar,
  Toolbar,
  Typography,
  IconButton,
  Box,
  Chip,
  Avatar,
  Menu,
  MenuItem,
  Divider,
  Tooltip,
} from '@mui/material';
import {
  Menu as MenuIcon,
  LightMode,
  DarkMode,
  Person,
  Logout as LogoutIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../../context/SessionContext';
import { useThemeMode } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import interCaribbeanLogo from '../../assets/logos/jy-logo-banner.png';
import precisionAirLogo from '../../assets/logos/precisionair-logo.png';
import fjordlineLogo from '../../assets/logos/fjordline-logo.png';

interface AppBarProps {
  onToggleSidebar: () => void;
}

/**
 * Display names shown in the AppBar tenant chip. Keyed by tenantCode
 * derived from session.enabled_modules. Anything not in this map falls
 * back to session.tenant_name (which is what Skywave admin and any
 * unmapped tenant continue to see).
 */
const TENANT_DISPLAY_NAMES: Record<string, string> = {
  JY: 'interCaribbean Airways',
  PW: 'Precision Air',
  FJL: 'Fjord Line',
};

export default function AppBar({ onToggleSidebar }: AppBarProps) {
  const { session } = useSession();
  const { mode, toggleTheme } = useThemeMode();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);

  // Derive a tenant code from enabled_modules. A single-module session
  // identifies a tenant; multi-module is the Skywave admin.
  const tenantCode: 'JY' | 'PW' | 'FJL' | null =
    session.enabled_modules.length === 1
      ? (session.enabled_modules[0] === 'airline_jy' ? 'JY'
        : session.enabled_modules[0] === 'airline_pw' ? 'PW'
        : session.enabled_modules[0] === 'cfl_fjl' ? 'FJL'
        : null)
      : null;
  const isJyTenant = tenantCode === 'JY';
  const isPwTenant = tenantCode === 'PW';
  const isFjlTenant = tenantCode === 'FJL';

  const handleLogout = () => {
    setAnchorEl(null);
    logout();
    navigate('/login');
  };



  return (
    <MuiAppBar
      position="fixed"
      elevation={0}
      sx={{
        zIndex: (theme) => theme.zIndex.drawer + 1,
        borderBottom: 1,
        borderColor: 'divider',
        bgcolor: 'background.paper',
        color: 'text.primary',
      }}
    >
      <Toolbar sx={{ gap: 1 }}>
        <IconButton
          edge="start"
          aria-label="Toggle sidebar navigation"
          onClick={onToggleSidebar}
          sx={{ mr: 1 }}
        >
          <MenuIcon />
        </IconButton>

        {isFjlTenant ? (
          <Box
            component="img"
            src={fjordlineLogo}
            alt="Fjord Line"
            sx={{ height: 48, mr: 1.5 }}
          />
        ) : isPwTenant ? (
          <Box
            component="img"
            src={precisionAirLogo}
            alt="Precision Air"
            sx={{ height: 48, mr: 1.5 }}
          />
        ) : isJyTenant ? (
          <Box
            component="img"
            src={interCaribbeanLogo}
            alt="interCaribbean Airways"
            sx={{
              height: 48,
              mr: 1.5,
            }}
          />
        ) : (
          /* RTS Logo — tries PNG first, falls back to SVG. Dark-mode
             flips the navy artwork to white via CSS filter; PNG has a
             real alpha channel so the background stays transparent. */
          <Box
            component="img"
            src="/assets/RTS_Logo.png"
            alt="RTS Logo"
            onError={(e: React.SyntheticEvent<HTMLImageElement>) => {
              const img = e.currentTarget;
              if (img.src.endsWith('.png')) {
                img.src = '/assets/RTS_Logo.svg';
              } else {
                img.style.display = 'none';
              }
            }}
            sx={{
              height: 48,
              mr: 1.5,
              filter: mode === 'dark' ? 'brightness(0) invert(1)' : 'none',
              transition: 'filter 200ms ease',
            }}
          />
        )}
        <Box sx={{ flexGrow: 1 }} />

        <Chip
          size="small"
          label={tenantCode ? (TENANT_DISPLAY_NAMES[tenantCode] ?? session.tenant_name) : session.tenant_name}
          variant="outlined"
          sx={{ display: { xs: 'none', md: 'flex' } }}
        />

        <Tooltip title={`Switch to ${mode === 'light' ? 'dark' : 'light'} mode`}>
          <IconButton onClick={toggleTheme} aria-label="Toggle theme">
            {mode === 'light' ? <DarkMode /> : <LightMode />}
          </IconButton>
        </Tooltip>

        <Tooltip title="User menu & role switcher">
          <IconButton onClick={(e) => setAnchorEl(e.currentTarget)} aria-label="User menu">
            <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main', fontSize: 14 }}>
              {session.user.name.split(' ').map(n => n[0]).join('')}
            </Avatar>
          </IconButton>
        </Tooltip>

        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={() => setAnchorEl(null)}
          transformOrigin={{ horizontal: 'right', vertical: 'top' }}
          anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
        >
          <MenuItem disabled>
            <Box>
              <Typography variant="subtitle2">{session.user.name}</Typography>
              <Typography variant="caption" color="text.secondary">{session.user.email}</Typography>
            </Box>
          </MenuItem>
          <MenuItem disabled sx={{ pb: 1, pt: 0 }}>
            <Box sx={{ display: 'flex', gap: 0.5 }}>
              <Chip 
                label="admin" 
                size="small" 
                color="primary" 
                sx={{ 
                  textTransform: 'lowercase', 
                  fontWeight: 600, 
                  height: 20, 
                  fontSize: '0.75rem',
                  px: 0.5
                }} 
              />
            </Box>
          </MenuItem>
          <Divider />
          <MenuItem onClick={handleLogout} sx={{ color: 'error.main' }}>
            <LogoutIcon fontSize="small" sx={{ mr: 1 }} />
            Logout
          </MenuItem>
        </Menu>
      </Toolbar>
    </MuiAppBar>
  );
}
