import React, { useEffect, useState } from 'react';
import {
  Drawer,
  Divider,
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
import { alpha } from '@mui/material/styles';
import {
  Home, Flight, DirectionsBoat, Dashboard,
  CloudUpload,
  Security, Settings,
  Email,
  Storage, Schedule, PlayCircleFilled, VpnKey, AssignmentTurnedIn,
  PriceChange, Speed,
  LogoutOutlined,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useSession } from '../../context/SessionContext';
import { useAuth } from '../../context/AuthContext';
import { navigationItems } from '../../mock/navigation';
import { NavItem } from '../../types';
import { isSuperAdmin } from '../../utils/access';
import SidebarDashboardCharts from './SidebarDashboardCharts';
import { selectedRowSx, subItemSx, subItemTextProps } from './sidebarSubItem';
import { BANNER_BG, BANNER_HEADER_BG, brandInk } from '../dashboard/bannerTheme';

const DRAWER_WIDTH = 260;
const RAIL_WIDTH = 68;

const iconMap: Record<string, React.ReactElement> = {
  Home: <Home />, Flight: <Flight />, DirectionsBoat: <DirectionsBoat />,
  Dashboard: <Dashboard />,
  CloudUpload: <CloudUpload />,
  Security: <Security />, Settings: <Settings />,
  Email: <Email />,
  Storage: <Storage />,
  Schedule: <Schedule />,
  PlayCircleFilled: <PlayCircleFilled />,
  VpnKey: <VpnKey />,
  AssignmentTurnedIn: <AssignmentTurnedIn />,
  PriceChange: <PriceChange />,
  Speed: <Speed />,
};

// Rail sections built from a whole admin category (rather than a single nav
// item) wear the category's own icon, not the icon of whichever item happens
// to come first.
const categoryIconKey: Record<string, string> = {
  Overview: 'Home',
  Admin: 'Security',
  Settings: 'Settings',
  'Data Ops': 'CloudUpload',
};

// Tenant-facing categories put each item on the rail by itself: a tenant's
// module and its Dashboards are the two destinations they switch between, and
// each deserves its own recognizable icon. Admin categories collapse to one
// rail icon per category, or the rail would hold eight near-identical entries.
const PER_ITEM_CATEGORIES = new Set(['Modules', 'Analytics']);

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

/**
 * One entry on the icon rail. Clicking it reveals the section's items in the
 * panel (opening the panel if it was collapsed); it does not navigate.
 * Navigation only happens from the panel's rows.
 */
interface RailSection {
  key: string;
  title: string;
  iconKey: string;
  items: NavItem[];
}

interface SidebarProps {
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
}

export default function Sidebar({ open, onOpen, onClose }: SidebarProps) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const navigate = useNavigate();
  const location = useLocation();
  const { hasAccess, session } = useSession();
  const { logout } = useAuth();

  // WinAir's chrome follows its brand red instead of the app navy. Undefined
  // for every other tenant, and every use below falls back to theme primary.
  const isWmTenant =
    session.enabled_modules.length === 1 && session.enabled_modules[0] === 'airline_wm';
  const accent = isWmTenant ? BANNER_BG : undefined;

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

  const sections: RailSection[] = [];
  for (const cat of categories) {
    const catItems = filteredItems.filter(i => (i.category || 'Other') === cat);
    if (catItems.length === 0) continue;
    if (PER_ITEM_CATEGORIES.has(cat)) {
      for (const item of catItems) {
        sections.push({ key: item.path, title: item.label, iconKey: item.icon, items: [item] });
      }
    } else {
      sections.push({
        key: cat,
        title: cat,
        iconKey: categoryIconKey[cat] ?? catItems[0].icon,
        items: catItems,
      });
    }
  }

  const isItemOnPath = (item: NavItem): boolean => {
    // Dashboards' own route is /dashboards/:id, hence the prefix match.
    if (item.path === '/dashboards') return location.pathname.startsWith('/dashboards');
    if (location.pathname === item.path) return true;
    return (item.children ?? []).some(c =>
      isChildActive(location.pathname, location.search, c.path),
    );
  };

  const matchedSection = sections.find(s => s.items.some(isItemOnPath)) ?? null;

  // Which section the panel is browsing. Null means "follow the route"; rail
  // clicks set it (they preview a section without navigating) and navigation
  // clears it so the panel snaps back to tracking where the user actually is.
  const [viewedKey, setViewedKey] = useState<string | null>(null);
  useEffect(() => {
    setViewedKey(null);
  }, [location.pathname, location.search]);

  const browsedSection = sections.find(s => s.key === viewedKey) ?? null;

  // The panel still needs something to show on routes outside the nav
  // (profile, security), so it falls back to the first section rather than
  // rendering empty.
  const panelSection = browsedSection ?? matchedSection ?? sections[0] ?? null;

  // While browsing sections the rail follows the panel; collapsed, it marks
  // where the current route lives. The panel's sections[0] display fallback
  // deliberately does NOT feed the highlight — on routes outside the nav the
  // rail must not claim the first section is where you are.
  const railActiveKey = (open ? browsedSection ?? matchedSection : matchedSection)?.key;

  const showSection = (s: RailSection) => {
    setViewedKey(s.key);
    if (!open) onOpen();
  };

  const handleNav = (path: string) => {
    navigate(path);
    // Only the mobile overlay closes itself after navigating; the desktop
    // sidebar stays exactly as the user left it.
    if (isMobile) onClose();
  };

  const drawerWidth = isMobile ? (open ? DRAWER_WIDTH : 0) : (open ? DRAWER_WIDTH : RAIL_WIDTH);

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
      <Box sx={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
        {/* Icon rail: always visible on desktop, one distinct icon per section. */}
        <Box
          sx={{
            width: RAIL_WIDTH,
            flexShrink: 0,
            borderRight: 1,
            borderColor: 'divider',
            overflowX: 'hidden',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
          }}
        >
          <Box
            sx={{
              width: '100%',
              flexGrow: 1,
              overflowY: 'auto',
              overflowX: 'hidden',
              py: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 0.5,
            }}
          >
            {sections.map(s => (
              <Tooltip key={s.key} title={s.title} placement="right" arrow>
                <ListItemButton
                  selected={railActiveKey === s.key}
                  onClick={() => showSection(s)}
                  sx={{
                    width: 44,
                    minHeight: 44,
                    maxHeight: 44,
                    flexGrow: 0,
                    borderRadius: '10px',
                    justifyContent: 'center',
                    px: 0,
                    '&.Mui-selected': {
                      bgcolor: accent ?? 'primary.main',
                      color: 'primary.contrastText',
                      '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
                      '&:hover': { bgcolor: accent ? BANNER_HEADER_BG : 'primary.dark' },
                    },
                  }}
                >
                  <ListItemIcon sx={{ minWidth: 0, justifyContent: 'center' }}>
                    {iconMap[s.iconKey] || <Home />}
                  </ListItemIcon>
                </ListItemButton>
              </Tooltip>
            ))}
          </Box>

          {/* Sign out sits below the scrolling sections so it stays reachable
              in both the rail and expanded states. Same fire-and-forget flow
              as the AppBar popover's Sign out. */}
          <Divider sx={{ width: 28, my: 0.5 }} />
          <Tooltip title="Sign out" placement="right" arrow>
            <ListItemButton
              onClick={() => {
                logout();
                navigate('/login');
              }}
              sx={{
                width: 44,
                minHeight: 44,
                maxHeight: 44,
                flexGrow: 0,
                borderRadius: '10px',
                justifyContent: 'center',
                px: 0,
                mb: 1,
                '&:hover': {
                  bgcolor: (t) => alpha(t.palette.error.main, 0.08),
                },
              }}
            >
              <ListItemIcon sx={{ minWidth: 0, justifyContent: 'center', color: 'error.main' }}>
                <LogoutOutlined />
              </ListItemIcon>
            </ListItemButton>
          </Tooltip>
        </Box>

        {/* Panel: the active section's contents. Collapsing hides only this. */}
        {open && panelSection && (
          <Box sx={{ flexGrow: 1, minWidth: 0, overflowY: 'auto', overflowX: 'hidden', py: 1 }}>
            <Typography
              variant="overline"
              noWrap
              sx={{
                px: 2,
                py: 0.5,
                display: 'block',
                color: 'text.secondary',
                fontSize: 11,
                fontWeight: 700,
              }}
            >
              {panelSection.title}
            </Typography>
            <List dense disablePadding>
              {panelSection.items.map(item => {
                // Dashboards owns an async sub-list (the chart names) rather
                // than static children, and its own route is /dashboards/:id,
                // so both checks below need a prefix match for it.
                const isDashboardsRow = item.path === '/dashboards';
                const onPath = isDashboardsRow
                  ? location.pathname.startsWith('/dashboards')
                  : location.pathname === item.path;
                // Rows that own sub-items are section headers: highlighting
                // them as well as the active child would show two accented
                // rows at once, so they get a lighter text accent instead.
                const hasSubItems = !!item.children?.length || isDashboardsRow;
                const isSelected = onPath && !hasSubItems;
                return (
                  <React.Fragment key={item.path}>
                    <ListItemButton
                      selected={isSelected}
                      onClick={() => handleNav(item.path)}
                      sx={{
                        mx: 1,
                        borderRadius: 1,
                        mb: 0.5,
                        px: 1.5,
                        minHeight: 40,
                        ...(hasSubItems && onPath && {
                          // brandInk lightens the red in dark mode (flat red
                          // reads ~2.9:1 on dark paper); navy path unchanged.
                          color: accent ? brandInk : 'primary.main',
                          '& .MuiListItemIcon-root': {
                            color: accent ? brandInk : 'primary.main',
                          },
                        }),
                        ...selectedRowSx(accent),
                      }}
                    >
                      <ListItemIcon sx={{ minWidth: 0, mr: 1.5, justifyContent: 'center' }}>
                        {React.cloneElement(
                          iconMap[item.icon] || <Home />,
                          { sx: { fontSize: 20 } },
                        )}
                      </ListItemIcon>
                      <ListItemText
                        primary={item.label}
                        primaryTypographyProps={{
                          fontSize: 13,
                          fontWeight: isSelected || (hasSubItems && onPath) ? 700 : 500,
                        }}
                      />
                    </ListItemButton>

                    {/* Static sub-items (WinAir's Pricing / Velocity tabs) */}
                    {(item.children ?? []).map(child => {
                      const childSelected = isChildActive(
                        location.pathname, location.search, child.path,
                      );
                      return (
                        <ListItemButton
                          key={child.path}
                          selected={childSelected}
                          onClick={() => handleNav(child.path)}
                          sx={subItemSx(accent)}
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
                    {isDashboardsRow && <SidebarDashboardCharts onNavigate={handleNav} />}
                  </React.Fragment>
                );
              })}
            </List>
          </Box>
        )}
      </Box>
    </Drawer>
  );
}
