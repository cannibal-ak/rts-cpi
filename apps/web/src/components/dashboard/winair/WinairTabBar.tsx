import { Box, Tabs, Tab, Alert, Skeleton, CircularProgress } from '@mui/material';
import { ScatterPlot } from '@mui/icons-material';
import type { DashboardTab } from '../../../api/client';
import { useBrandedChrome } from '../tenantChrome';

/**
 * Reserved key for the CPI-rendered Latest Prices pane.
 *
 * Deliberately not a Superset layout id (those are all "TAB-*"), so it can
 * never be mistaken for one and sent to the permalink endpoint.
 */
export const PRICES_TAB = 'prices';

/**
 * Fallback entry shown when the section list is unavailable — embeds the
 * dashboard with no permalink, so Superset opens its own default section.
 * Also not a Superset layout id, for the same reason as PRICES_TAB.
 */
export const DASHBOARD_TAB = 'dashboard';

interface WinairTabBarProps {
  /** The dashboard's own sections. Empty while loading, or on failure. */
  tabs: DashboardTab[];
  value: string;
  onChange: (next: string) => void;
  loading: boolean;
  /** A Superset section is being minted/embedded — shown on the target tab. */
  switching: boolean;
  error: string | null;
}

/**
 * WinAir's one row of navigation: Latest Prices, then the dashboard's sections.
 *
 * Superset's own tab row is hidden inside the iframe (WM-EMBED-HIDE-TOPTABS
 * css block on dashboard 6 — Superset 3.1.0 ignores the uiConfig hideNav bit
 * the embed also sends), so this bar is the ONLY way to reach four fifths of
 * the dashboard. That is why it degrades loudly rather than quietly: a failed
 * tab fetch still leaves Latest Prices and a plain "Dashboard" entry
 * reachable. Once a Superset upgrade honours hideNav (sent only while a
 * section is pinned), the css block can go and that fallback view will get
 * Superset's own row back as its navigation.
 *
 * Presentational only — it does no fetching and knows nothing about the URL.
 */
export default function WinairTabBar({
  tabs, value, onChange, loading, switching, error,
}: WinairTabBarProps) {
  const {
    BANNER_BG, BANNER_HEADER_BG, FILTER_BG, FILTER_BORDER, FILTER_ERROR_BG, FILTER_ERROR_INK,
    FILTER_FIELD_BG, FILTER_FIELD_LINE, FILTER_LABEL_INK, FILTER_SKELETON,
  } = useBrandedChrome();

  // With no usable section list, still offer a way into the embed. Superset
  // opens its own default section when no permalink pins one.
  const fallbackEntry: DashboardTab[] =
    !loading && tabs.length === 0 ? [{ id: DASHBOARD_TAB, label: 'Dashboard' }] : [];
  const entries = [...tabs, ...fallbackEntry];

  return (
    <Box
      sx={{
        // Same surface, radius and elevation as WinairTopFilterBar's card, so
        // the two read as siblings; the margin is the gap between them.
        bgcolor: FILTER_BG,
        border: '1px solid',
        borderColor: FILTER_BORDER,
        borderRadius: 1.5,
        boxShadow: 1,
        mb: 0.75,
        px: 1,
      }}
    >
      {loading ? (
        // Six entries: Latest Prices plus WinAir's five sections. A fixed
        // count keeps the bar from resizing when the real labels land.
        <Box sx={{ display: 'flex', gap: 1, py: 0.875, px: 1 }}>
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} variant="rounded" width={i === 0 ? 110 : 130} height={30}
                      sx={{ bgcolor: FILTER_SKELETON, borderRadius: 999 }} />
          ))}
        </Box>
      ) : (
        <Tabs
          value={value}
          onChange={(_, next) => onChange(next)}
          variant="scrollable"
          scrollButtons="auto"
          allowScrollButtonsMobile
          aria-label="Dashboard sections"
          sx={{
            minHeight: 44,
            py: 0.75,
            '& .MuiTabs-indicator': { display: 'none' },
            '& .MuiTabs-scrollButtons.Mui-disabled': { opacity: 0.25 },
            '& .MuiTabs-scrollButtons': { color: FILTER_LABEL_INK },
            // Idle pills reuse the filter fields' tokens, so an untouched tab
            // and an untouched field look the same. The current tab fills with
            // brand red, NOT the filters' teal: the two say different things —
            // red is where you are in the dashboard, teal is what you have
            // filtered — and one accent for both would blur that.
            //
            // Both pill states carry their own text colour rather than
            // inheriting, so each is legible on its own fill: white on the red
            // measures 5.5:1, slate on the white 7.6:1.
            '& .MuiTab-root': {
              minHeight: 32,
              minWidth: 'auto',
              my: 'auto',
              mr: 1,
              py: 0.5,
              px: 1.75,
              borderRadius: 999,
              bgcolor: FILTER_FIELD_BG,
              border: `1px solid ${FILTER_FIELD_LINE}`,
              fontSize: 12.5,
              fontWeight: 500,
              textTransform: 'none',
              color: FILTER_LABEL_INK,
              gap: 0.75,
              '&:hover': { borderColor: BANNER_BG, color: BANNER_HEADER_BG },
              '&.Mui-selected': {
                color: '#ffffff',
                fontWeight: 600,
                bgcolor: BANNER_BG,
                borderColor: BANNER_BG,
                '&:hover': { bgcolor: BANNER_HEADER_BG, borderColor: BANNER_HEADER_BG, color: '#ffffff' },
              },
            },
          }}
        >
          <Tab
            value={PRICES_TAB}
            label="Latest Prices"
            icon={<ScatterPlot sx={{ fontSize: 15 }} />}
            iconPosition="start"
          />
          {entries.map(tab => (
            <Tab
              key={tab.id}
              value={tab.id}
              label={tab.label}
              // Progress sits on the tab being switched TO, so the wait is
              // attached to the thing the user just asked for.
              icon={
                // The tab being switched to is the selected one, so the
                // spinner sits on the filled pill and has to be white.
                switching && value === tab.id
                  ? <CircularProgress size={12} sx={{ color: '#ffffff' }} />
                  : undefined
              }
              iconPosition="start"
            />
          ))}
        </Tabs>
      )}

      {error && (
        <Alert
          severity="warning"
          sx={{
            py: 0,
            mb: 0.75,
            fontSize: 11.5,
            bgcolor: FILTER_ERROR_BG,
            color: FILTER_ERROR_INK,
            '& .MuiAlert-icon': { color: FILTER_ERROR_INK, py: 0.5 },
          }}
        >
          {error}
        </Alert>
      )}
    </Box>
  );
}
