import React from 'react';
import {
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Box,
  Typography,
  Tooltip,
  useTheme,
  useMediaQuery,
} from '@mui/material';
import {
  Home, Flight, DirectionsBoat, Dashboard,
  CloudUpload,
  Security, Settings, Description, ViewModule,
  Storage,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useSession } from '../../context/SessionContext';
import { navigationItems } from '../../mock/navigation';
import { NavItem } from '../../types';
import { isSuperAdmin } from '../../utils/access';

const DRAWER_WIDTH = 260;
const MINI_DRAWER_WIDTH = 68;

const iconMap: Record<string, React.ReactElement> = {
  Home: <Home />, Flight: <Flight />, DirectionsBoat: <DirectionsBoat />,
  Dashboard: <Dashboard />,
  CloudUpload: <CloudUpload />,
  Security: <Security />, Settings: <Settings />, Description: <Description />,
  Storage: <Storage />,
};

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export default function Sidebar({ open, onClose }: SidebarProps) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const navigate = useNavigate();
  const location = useLocation();
  const { hasAccess, session } = useSession();

  const filteredItems = navigationItems.filter(item => {
    if (item.requireSuperAdmin && !isSuperAdmin(session)) return false;
    return hasAccess({
      roles: item.requiredRoles,
      modules: item.requiredModules,
      capabilities: item.requiredCapabilities,
    });
  });

  const categories = Array.from(new Set(filteredItems.map(i => i.category || 'Other')));

  const handleNav = (path: string) => {
    navigate(path);
    onClose(); // Automatically collapse/minimize after navigation
  };

  const drawerWidth = isMobile ? (open ? DRAWER_WIDTH : 0) : (open ? DRAWER_WIDTH : MINI_DRAWER_WIDTH);

  return (
    <Drawer
      variant={isMobile ? 'temporary' : 'permanent'}
      open={isMobile ? open : true}
      onClose={onClose}
      ModalProps={{ keepMounted: true }}
      sx={{
        width: drawerWidth,
        flexShrink: 0,
        whiteSpace: 'nowrap',
        boxSizing: 'border-box',
        transition: theme.transitions.create('width', {
          easing: theme.transitions.easing.sharp,
          duration: theme.transitions.duration.enteringScreen,
        }),
        '& .MuiDrawer-paper': {
          width: drawerWidth,
          boxSizing: 'border-box',
          top: isMobile ? 0 : 64,
          height: isMobile ? '100%' : 'calc(100% - 64px)',
          borderRight: 1,
          borderColor: 'divider',
          overflowX: 'hidden',
          transition: theme.transitions.create('width', {
            easing: theme.transitions.easing.sharp,
            duration: theme.transitions.duration.enteringScreen,
          }),
        },
      }}
    >
      <Box sx={{ overflow: 'auto', py: 1 }}>
        {categories.map(cat => {
          const catItems = filteredItems.filter(i => (i.category || 'Other') === cat);
          if (catItems.length === 0) return null;

          // If sidebar is collapsed AND it's the 'Modules' category, consolidate into 1 icon
          const isModules = cat === 'Modules';
          const showConsolidated = !open && isModules;

          return (
            <Box key={cat} sx={{ mb: open ? 1 : 2 }}>
              {open && (
                <Typography
                  variant="overline"
                  sx={{ px: 2, py: 0.5, display: 'block', color: 'text.secondary', fontSize: 11, fontWeight: 700 }}
                >
                  {cat}
                </Typography>
              )}
              <List dense disablePadding>
                {showConsolidated ? (
                  (() => {
                    const isAnySelected = catItems.some(i => location.pathname === i.path);
                    const firstItem = catItems[0];
                    return (
                      <Tooltip title="Modules" placement="right" arrow>
                        <ListItemButton
                          selected={isAnySelected}
                          onClick={() => handleNav(firstItem.path)}
                          sx={{
                            mx: 1.5,
                            borderRadius: 1,
                            mb: 0.5,
                            justifyContent: 'center',
                            px: 1,
                            minHeight: 44,
                            '&.Mui-selected': {
                              bgcolor: 'primary.main',
                              color: 'primary.contrastText',
                              '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
                              '&:hover': { bgcolor: 'primary.dark' },
                            },
                          }}
                        >
                          <ListItemIcon sx={{ minWidth: 0, justifyContent: 'center' }}>
                            <ViewModule />
                          </ListItemIcon>
                        </ListItemButton>
                      </Tooltip>
                    );
                  })()
                ) : (
                  catItems.map(item => {
                    const isSelected = location.pathname === item.path;
                    return (
                      <Tooltip key={item.path} title={item.label} placement="right" arrow disableHoverListener={open}>
                        <ListItemButton
                          selected={isSelected}
                          onClick={() => handleNav(item.path)}
                          sx={{
                            mx: open ? 1 : 1.5,
                            borderRadius: 1,
                            mb: 0.5,
                            justifyContent: open ? 'initial' : 'center',
                            px: open ? 2 : 1,
                            minHeight: 44,
                            '&.Mui-selected': {
                              bgcolor: 'primary.main',
                              color: 'primary.contrastText',
                              '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
                              '&:hover': { bgcolor: 'primary.dark' },
                            },
                          }}
                        >
                          <ListItemIcon
                            sx={{
                              minWidth: 0,
                              mr: open ? 2 : 'auto',
                              justifyContent: 'center',
                            }}
                          >
                            {iconMap[item.icon] || <Home />}
                          </ListItemIcon>
                          <ListItemText
                            primary={item.label}
                            sx={{
                              opacity: open ? 1 : 0,
                              display: open ? 'block' : 'none',
                            }}
                            primaryTypographyProps={{
                              fontSize: 13,
                              fontWeight: isSelected ? 700 : 500,
                            }}
                          />
                        </ListItemButton>
                      </Tooltip>
                    );
                  })
                )}
              </List>
            </Box>
          );
        })}
      </Box>
    </Drawer>
  );
}
