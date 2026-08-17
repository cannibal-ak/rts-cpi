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
  Email,
  Storage, Schedule, PlayCircleFilled, VpnKey, AssignmentTurnedIn,
  PriceChange, Speed,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useSession } from '../../context/SessionContext';
import { navigationItems } from '../../mock/navigation';
import { NavItem } from '../../types';
import { isSuperAdmin } from '../../utils/access';
import SidebarDashboardCharts from './SidebarDashboardCharts';
import { subItemSx, subItemTextProps } from './sidebarSubItem';

const DRAWER_WIDTH = 260;
const MINI_DRAWER_WIDTH = 68;

const iconMap: Record<string, React.ReactElement> = {
  Home: <Home />, Flight: <Flight />, DirectionsBoat: <DirectionsBoat />,
  Dashboard: <Dashboard />,
  CloudUpload: <CloudUpload />,
  Security: <Security />, Settings: <Settings />, Description: <Description />,
  Email: <Email />,
  Storage: <Storage />,
  Schedule: <Schedule />,
  PlayCircleFilled: <PlayCircleFilled />,
  VpnKey: <VpnKey />,
  AssignmentTurnedIn: <AssignmentTurnedIn />,
  PriceChange: <PriceChange />,
  Speed: <Speed />,
};

// A child path carries its own query string (e.g. '/cpi/airline/wm?tab=velocity'),
// so matching on pathname alone would light up every sibling. Compare the path
// and every param the child names; params it does not name are ignored.
function isChildActive(pathname: string, search: string, childPath: string): boolean {
  const [childPathname, childQuery = ''] = childPath.split('?');
  if (pathname !== childPathname) return false;
  if (!childQuery) return true;
  const current = new URLSearchParams(search);
  const wanted = new URLSearchParams(childQuery);
  for (const [key, value] of wanted.entries()) {
    // A tab param the URL has not set yet still means the first tab, which is
    // what a bare /cpi/airline/wm renders.
    const actual = current.get(key) ?? (key === 'tab' ? 'pricing' : null);
    if (actual !== value) return false;
  }
  return true;
}

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
    if (item.hideForSuperAdmin && isSuperAdmin(session)) return false;
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
                    // Dashboards owns an async sub-list (the chart names) rather
                    // than static children, and its own route is /dashboards/:id,
                    // so both checks below need a prefix match for it.
                    const isDashboardsRow = item.path === '/dashboards';
                    const onPath = isDashboardsRow
                      ? location.pathname.startsWith('/dashboards')
                      : location.pathname === item.path;
                    // Rows that own sub-items are section headers: highlighting
                    // them solid as well as the active child would show two
                    // filled rows at once, so they get a lighter accent instead.
                    const hasSubItems = open && (!!item.children?.length || isDashboardsRow);
                    const isSelected = onPath && !hasSubItems;
                    const subItems = open ? item.children ?? [] : [];
                    return (
                      <React.Fragment key={item.path}>
                      <Tooltip title={item.label} placement="right" arrow disableHoverListener={open}>
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
                            ...(hasSubItems && onPath && {
                              color: 'primary.main',
                              '& .MuiListItemIcon-root': { color: 'primary.main' },
                            }),
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
                              fontWeight: isSelected || (hasSubItems && onPath) ? 700 : 500,
                            }}
                          />
                        </ListItemButton>
                      </Tooltip>

                      {/* Static sub-items (WinAir's Pricing / Velocity tabs) */}
                      {subItems.map(child => {
                        const childSelected = isChildActive(
                          location.pathname, location.search, child.path,
                        );
                        return (
                          <ListItemButton
                            key={child.path}
                            selected={childSelected}
                            onClick={() => handleNav(child.path)}
                            sx={subItemSx}
                          >
                            <ListItemIcon sx={{ minWidth: 0, mr: 1.5, justifyContent: 'center' }}>
                              {React.cloneElement(
                                iconMap[child.icon] || <Home />,
                                { sx: { fontSize: 17 } },
                              )}
                            </ListItemIcon>
                            <ListItemText
                              primary={child.label}
                              primaryTypographyProps={subItemTextProps(childSelected)}
                            />
                          </ListItemButton>
                        );
                      })}

                      {/* Chart names for this tenant's Superset dashboard */}
                      {open && item.path === '/dashboards' && (
                        <SidebarDashboardCharts onNavigate={handleNav} />
                      )}
                      </React.Fragment>
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
