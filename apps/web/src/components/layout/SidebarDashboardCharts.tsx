/**
 * The contents of the tenant's Superset dashboard, listed as sub-items under
 * the sidebar's "Dashboards" row.
 *
 * What gets listed depends on how the dashboard is built:
 *
 *  - Tabbed dashboards (WinAir) list their top-level TABS. Clicking one lands
 *    on /dashboards/:id?tab=<TAB-id>, and the viewer reopens the dashboard with
 *    that tab active. These have no Chart view.
 *  - Everything else lists its analytics CHARTS. Clicking one lands on
 *    /dashboards/:id?chart=<slice_id>, which opens Chart view on that chart.
 *
 * Its own component rather than inline JSX because it calls hooks and the
 * Dashboards row is rendered inside a .map().
 */
import {
  List, ListItemButton, ListItemIcon, ListItemText, Box, CircularProgress,
} from '@mui/material';
import {
  TrendingUp, BarChart as BarChartIcon, PieChart as PieChartIcon,
  TableChart, GridOn, ShowChart, ScatterPlot, Tab as TabIcon,
} from '@mui/icons-material';
import { useLocation } from 'react-router-dom';
import { useSession } from '../../context/SessionContext';
import { useDashboardCharts } from '../../hooks/useDashboardCharts';
import { useDashboardTabs } from '../../hooks/useDashboardTabs';
import { getPrimaryDashboardId, hasChartView } from '../../pages/superset/dashboardAccess';
import { subItemSx, subItemTextProps } from './sidebarSubItem';

interface Props {
  /** Same navigate-then-collapse handler the top-level rows use. */
  onNavigate: (path: string) => void;
}

// Same mapping as ChartSelectorPanel so a chart wears the same icon in the
// sidebar as it does in the in-page selector.
function iconForViz(vizType: string | null) {
  const v = vizType ?? '';
  if (v.includes('line') || v === 'line') return TrendingUp;
  if (v.includes('bar')) return BarChartIcon;
  if (v.includes('pie')) return PieChartIcon;
  if (v === 'table' || v.startsWith('pivot_table')) return TableChart;
  if (v === 'heatmap') return GridOn;
  if (v === 'bubble' || v.includes('scatter')) return ScatterPlot;
  return ShowChart;
}

export default function SidebarDashboardCharts({ onNavigate }: Props) {
  const location = useLocation();
  const { session } = useSession();

  // Every tenant has exactly one enabled module, hence one dashboard. Returns
  // null for anyone with none or several, and then we render nothing rather
  // than guess which dashboard's contents to list.
  const dashboardId = getPrimaryDashboardId(session);
  const listCharts = hasChartView(dashboardId);

  // Both hooks run every render (hook rules); passing undefined is what skips
  // the fetch, so only the relevant one ever hits the network. Each is cached
  // per dashboard id, so this costs one request per session even though the
  // sidebar is mounted on every page.
  const charts = useDashboardCharts(listCharts ? dashboardId ?? undefined : undefined);
  const tabsResult = useDashboardTabs(!listCharts ? dashboardId ?? undefined : undefined);

  if (!dashboardId) return null;

  // Fail quiet. This list is a convenience; a Superset hiccup must not take the
  // navigation down with it.
  const error = listCharts ? charts.error : tabsResult.error;
  if (error) return null;

  const loading = listCharts ? charts.loading : tabsResult.loading;
  const onThisDashboard = location.pathname === `/dashboards/${dashboardId}`;
  const params = new URLSearchParams(location.search);

  // One shape for both kinds of row, so they render through the same code.
  const rows = listCharts
    ? charts.analyticsCharts.map(c => ({
        key: String(c.slice_id),
        label: c.slice_name,
        Icon: iconForViz(c.viz_type),
        to: `/dashboards/${dashboardId}?chart=${c.slice_id}`,
        selected: onThisDashboard && params.get('chart') === String(c.slice_id),
      }))
    : [
        // Where the page renders its own tab bar, no ?tab= means Latest
        // Prices — a CPI-rendered pane, not a Superset tab — so the sidebar
        // has to offer it or that pane is unreachable from here. Gated on the
        // same signal the page uses, so dashboards that keep Superset's own
        // tab row are unaffected.
        ...(tabsResult.tabsAreNavigation
          ? [{
              key: 'prices',
              label: 'Latest Prices',
              Icon: ScatterPlot,
              to: `/dashboards/${dashboardId}`,
              selected: onThisDashboard && !params.get('tab'),
            }]
          : []),
        ...tabsResult.tabs.map((t, idx) => ({
          key: t.id,
          label: t.label,
          Icon: TabIcon,
          to: `/dashboards/${dashboardId}?tab=${encodeURIComponent(t.id)}`,
          // Where Latest Prices owns the no-param state, the first Superset
          // tab is NOT what is on screen without a ?tab=; elsewhere it still
          // is, so highlight it rather than nothing.
          selected: onThisDashboard && (
            tabsResult.tabsAreNavigation
              ? params.get('tab') === t.id
              : (params.get('tab') ?? (idx === 0 ? t.id : null)) === t.id
          ),
        })),
      ];

  if (loading && rows.length === 0) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 1 }}>
        <CircularProgress size={16} />
      </Box>
    );
  }

  if (rows.length === 0) return null;

  return (
    <List dense disablePadding>
      {rows.map(row => (
        <ListItemButton
          key={row.key}
          selected={row.selected}
          onClick={() => onNavigate(row.to)}
          sx={subItemSx}
        >
          <ListItemIcon sx={{ minWidth: 0, mr: 1.5, justifyContent: 'center' }}>
            <row.Icon sx={{ fontSize: 17 }} />
          </ListItemIcon>
          <ListItemText
            primary={row.label}
            primaryTypographyProps={subItemTextProps(row.selected)}
          />
        </ListItemButton>
      ))}
    </List>
  );
}
