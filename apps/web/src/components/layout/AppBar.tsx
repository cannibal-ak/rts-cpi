import React from 'react';
import {
  AppBar as MuiAppBar,
  Toolbar,
  Typography,
  IconButton,
  Box,
  Avatar,
  Popover,
  Divider,
  Tooltip,
} from '@mui/material';
import {
  Menu as MenuIcon,
  LightMode,
  DarkMode,
  PersonOutlined,
  LogoutOutlined,
  BusinessOutlined,
  VerifiedUserOutlined,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useSession } from '../../context/SessionContext';
import { useThemeMode } from '../../context/ThemeContext';
import { useAuth } from '../../context/AuthContext';
import interCaribbeanLogo from '../../assets/logos/jy-logo-banner.png';
import winairLogo from '../../assets/logos/winair-logo.png';
import precisionAirLogo from '../../assets/logos/precisionair-logo.png';
import fjordlineLogo from '../../assets/logos/fjordline-logo.png';
import skyLogoLight from '../../assets/logos/sky-airways-logo.png';
import skyLogoDark from '../../assets/logos/sky-airways-logo-dark.png';
import { TENANT_CONFIG, TENANT_FALLBACK } from '../../utils/tenantConfig';

interface AppBarProps {
  onToggleSidebar: () => void;
}

export default function AppBar({ onToggleSidebar }: AppBarProps) {
  const { session } = useSession();
  const { mode, toggleTheme } = useThemeMode();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [anchorEl, setAnchorEl] = React.useState<null | HTMLElement>(null);

  // Derive tenant key from enabled_modules. A single-module session
  // identifies a tenant; multi-module or empty is the RTS platform admin.
  const tenantKey: keyof typeof TENANT_CONFIG =
    session.enabled_modules.length === 1
      ? (session.enabled_modules[0] === 'airline_jy' ? 'jy'
        : session.enabled_modules[0] === 'airline_pw' ? 'pw'
        : session.enabled_modules[0] === 'airline_alt' ? 'alt'
        : session.enabled_modules[0] === 'airline_wm' ? 'wm'
        : session.enabled_modules[0] === 'cfl_fjl' ? 'fjl'
        : 'rts')
      : 'rts';

  const isJyTenant = tenantKey === 'jy';
  const isWmTenant = tenantKey === 'wm';
  const isPwTenant = tenantKey === 'pw';
  const isFjlTenant = tenantKey === 'fjl';
  const isAltTenant = tenantKey === 'alt';
  const tenant = TENANT_CONFIG[tenantKey] ?? TENANT_FALLBACK;

  // Explicit chip-label overrides win; otherwise strip the TENANT_ prefix
  // and title-case (TENANT_ADMIN → "Admin", TENANT_USER → "Subtenant").
  const ROLE_CHIP_LABEL_OVERRIDES: Record<string, string> = { TENANT_USER: 'Subtenant' };
  const rawRole = session.user.roles[0] ?? 'user';
  const roleLabel = ROLE_CHIP_LABEL_OVERRIDES[rawRole] ?? rawRole
    .toLowerCase()
    .replace(/^tenant_/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());

  const handleLogout = () => {
    setAnchorEl(null);
    logout();
    navigate('/login');
  };

  const handleMyAccount = () => {
    setAnchorEl(null);
    navigate('/security');
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

        {isPwTenant ? (
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
            sx={{ height: 48, mr: 1.5 }}
          />
        ) : isFjlTenant ? (
          <Box
            component="img"
            src={fjordlineLogo}
            alt="Fjord Line"
            sx={{
              height: 48,
              width: 'auto',
              maxWidth: 200,
              objectFit: 'contain',
              mr: 1.5,
            }}
          />
        ) : isAltTenant ? (
          <Box
            component="img"
            src={mode === 'dark' ? skyLogoDark : skyLogoLight}
            alt="Sky Airways"
            sx={{
              height: 48,
              width: 'auto',
              maxWidth: 280,
              objectFit: 'contain',
              mr: 1.5,
            }}
          />
        ) : isWmTenant ? (
          <Box
            component="img"
            src={winairLogo}
            alt="WinAir"
            sx={{ height: 48, mr: 1.5 }}
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
              height: 60,
              maxWidth: 200,
              objectFit: 'contain',
              mr: 1.5,
              filter: mode === 'dark' ? 'brightness(0) invert(1)' : 'none',
              transition: 'filter 200ms ease',
            }}
          />
        )}

        <Box sx={{ flexGrow: 1 }} />

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Tooltip title={`Switch to ${mode === 'light' ? 'dark' : 'light'} mode`}>
            <IconButton onClick={toggleTheme} aria-label="Toggle theme">
              {mode === 'light' ? <DarkMode /> : <LightMode />}
            </IconButton>
          </Tooltip>

          <Tooltip title="Account">
            <IconButton
              onClick={(e) => setAnchorEl(e.currentTarget)}
              aria-label="User menu"
              sx={{ p: 0 }}
            >
              <Avatar
                sx={{
                  width: 36,
                  height: 36,
                  bgcolor: 'primary.light',
                  color: 'primary.dark',
                  fontSize: 14,
                  fontWeight: 500,
                  transition: 'opacity 150ms ease',
                  '&:hover': { opacity: 0.85 },
                }}
              >
                {tenant.initials}
              </Avatar>
            </IconButton>
          </Tooltip>
        </Box>

        <Popover
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={() => setAnchorEl(null)}
          anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
          transformOrigin={{ horizontal: 'right', vertical: 'top' }}
          slotProps={{
            paper: {
              sx: {
                mt: 1,
                width: 280,
                borderRadius: '12px',
                border: 1,
                borderColor: 'divider',
                boxShadow: (theme) => theme.shadows[4],
                overflow: 'hidden',
                bgcolor: 'background.paper',
              },
            },
          }}
        >
          {/* Identity */}
          <Box sx={{ p: 2, display: 'flex', gap: 1.5, alignItems: 'flex-start' }}>
            <Avatar
              sx={{
                width: 42,
                height: 42,
                bgcolor: 'primary.light',
                color: 'primary.dark',
                fontSize: 15,
                fontWeight: 500,
              }}
            >
              {tenant.initials}
            </Avatar>
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Typography
                sx={{ fontSize: 14, fontWeight: 500, color: 'text.primary', lineHeight: 1.3 }}
              >
                {tenant.displayName}
              </Typography>
              <Typography
                title={session.user.email}
                sx={{
                  fontSize: 12,
                  color: 'text.secondary',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  mt: 0.25,
                }}
              >
                {session.user.email}
              </Typography>
              <Box
                sx={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 0.5,
                  mt: 0.75,
                  px: 1,
                  py: '2px',
                  borderRadius: '6px',
                  bgcolor: 'success.light',
                  color: 'success.dark',
                  fontSize: 11,
                  fontWeight: 500,
                  lineHeight: 1.4,
                }}
              >
                <VerifiedUserOutlined sx={{ fontSize: 14 }} />
                {roleLabel}
              </Box>
            </Box>
          </Box>

          {/* Organisation card */}
          <Box sx={{ px: 2, pb: 1.5 }}>
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                bgcolor: 'action.hover',
                borderRadius: '8px',
                px: '10px',
                py: 1,
              }}
            >
              <BusinessOutlined sx={{ fontSize: 15, color: 'text.secondary' }} />
              <Box sx={{ minWidth: 0 }}>
                <Typography sx={{ fontSize: 11, color: 'text.disabled', lineHeight: 1.2 }}>
                  Organisation
                </Typography>
                <Typography
                  title={tenant.orgName}
                  sx={{
                    fontSize: 12,
                    fontWeight: 500,
                    color: 'text.primary',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {tenant.orgName}
                </Typography>
              </Box>
            </Box>
          </Box>

          <Divider />

          {/* Actions */}
          <Box sx={{ p: 1 }}>
            <Box
              onClick={handleMyAccount}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1.25,
                px: '10px',
                py: 1,
                borderRadius: '6px',
                cursor: 'pointer',
                color: 'text.secondary',
                transition: 'background-color 150ms ease',
                '&:hover': { bgcolor: 'action.hover' },
              }}
            >
              <PersonOutlined sx={{ fontSize: 16 }} />
              <Typography sx={{ fontSize: 13 }}>Security</Typography>
            </Box>

            <Box
              onClick={handleLogout}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1.25,
                px: '10px',
                py: 1,
                borderRadius: '6px',
                cursor: 'pointer',
                color: 'error.main',
                transition: 'background-color 150ms ease',
                '&:hover': { bgcolor: 'error.light' },
              }}
            >
              <LogoutOutlined sx={{ fontSize: 16 }} />
              <Typography sx={{ fontSize: 13 }}>Sign out</Typography>
            </Box>
          </Box>
        </Popover>
      </Toolbar>
    </MuiAppBar>
  );
}
