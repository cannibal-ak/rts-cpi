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

interface AppBarProps {
  onToggleSidebar: () => void;
}

export default function AppBar({ onToggleSidebar }: AppBarProps) {
  const { session } = useSession();
  const { mode, toggleTheme } = useThemeMode();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);

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

        {/* RTS Logo — tries PNG first, falls back to SVG */}
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
          sx={{ height: 40, mr: 1.5 }}
        />
        <Typography variant="body2" noWrap sx={{ color: 'text.secondary', ml: 0.5, display: { xs: 'none', sm: 'block' }, fontWeight: 500 }}>
          Competitor Pricing Intelligence
        </Typography>

        <Box sx={{ flexGrow: 1 }} />

        <Chip
          size="small"
          label={session.tenant_name}
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
