import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box, Paper, IconButton, Typography, Fade, Chip, Tooltip,
  ToggleButton, ToggleButtonGroup, useMediaQuery,
  FormControl, Select, MenuItem,
} from '@mui/material';
import {
  ArrowBack, Flight, DirectionsBoat, CalendarMonth, Refresh,
  Dashboard as DashboardIcon, BarChart as BarChartIcon,
} from '@mui/icons-material';
import { keyframes } from '@mui/system';
import type { Theme } from '@mui/material/styles';
import { api } from '../../api';
import type {
  DashboardDateFilter, DashboardFilter, DashboardFilterSelections, DashboardTab,
} from '../../api/client';
import { filterAppliesTo } from '../../api/client';
import { useSession } from '../../context/SessionContext';
import { canAccessDashboard, hasChartView } from './dashboardAccess';
import { useDashboardCharts } from '../../hooks/useDashboardCharts';
import ChartSelectorPanel from '../../components/dashboard/ChartSelectorPanel';
import DateFilterToggle from '../../components/dashboard/DateFilterToggle';
import SingleChartViewer from '../../components/dashboard/SingleChartViewer';
import KPIRow from '../../components/dashboard/KPIRow';
import CapDateChip from '../../components/dashboard/CapDateChip';
import { getTenantChrome } from '../../components/dashboard/tenantChrome';
import WinairTopFilterBar from '../../components/dashboard/winair/WinairTopFilterBar';
import LatestPricesPanel from '../../components/dashboard/winair/LatestPricesPanel';
import WinairTabBar, { PRICES_TAB, DASHBOARD_TAB } from '../../components/dashboard/winair/WinairTabBar';
import TimeRangeFilter, {
  FULL_DEP_RANGE, FULL_DURATION_RANGE, type Range,
} from '../../components/dashboard/winair/PriceChartFilters';
import {
  DEP_TIME_MIN, DEP_TIME_MAX, DURATION_MIN, DURATION_MAX,
} from '../../components/dashboard/winair/priceChartTheme';

/**
 * Superset base URL — used by the Embedded SDK to construct the iframe src.
 * The SDK creates:  {SUPERSET_URL}/embedded/{embedded_uuid}?uiConfig=...&show_filters=1&expand_filters=1
 * That endpoint renders the dashboard canvas only (no Superset nav/menu).
 */
const SUPERSET_URL = (import.meta.env.VITE_SUPERSET_URL as string) || `https://${window.location.hostname}:8488`;

// Dashboard metadata (must match backend DASHBOARDS registry)
const DASHBOARD_META: Record<string, { title: string; tenant: string; isAirline: boolean; freshnessDomain: string }> = {
  '1': { title: 'JY Dashboard', tenant: 'JY', isAirline: true, freshnessDomain: 'Airline CPI \u2013 JY' },
  '2': { title: 'PW Dashboard', tenant: 'PW', isAirline: true, freshnessDomain: 'Airline CPI \u2013 PW' },
  '3': { title: 'FJL Dashboard', tenant: 'FJL', isAirline: false, freshnessDomain: 'Cruise/Ferry CPI \u2013 FJL' },
  '4': { title: 'Sky Dashboard', tenant: 'ALT', isAirline: true, freshnessDomain: 'Airline CPI \u2013 SKY' },
  // WinAir's header renders no title at all (see the header bar below), so this
  // string is unread for '5' \u2014 the row is here for tenant and freshnessDomain.
  '5': { title: 'WinAir Dashboard', tenant: 'WM', isAirline: true, freshnessDomain: 'Airline CPI \u2013 WM' },
  // DreamAir is a WinAir twin: same header treatment, so this title is unread too.
  '6': { title: 'DreamAir Dashboard', tenant: 'DA', isAirline: true, freshnessDomain: 'Airline CPI \u2013 DreamAir' },
  // Liat Air is another WinAir twin: same header treatment, so this title is unread too.
  '7': { title: 'Liat Air Dashboard', tenant: '5L', isAirline: true, freshnessDomain: 'Airline CPI \u2013 Liat Air' },
};

// Dashboards allow-listed for the Chart-view filter overlay (see chartFiltersEnabled).
const CHART_FILTER_DASHBOARDS = ['5'];

// Superset Embedded SDK type (UMD bundle loaded via CDN in index.html)
declare global {
  interface Window {
    supersetEmbeddedSdk: {
      embedDashboard: (config: {
        id: string;
        supersetDomain: string;
        mountPoint: HTMLElement;
        fetchGuestToken: () => Promise<string>;
        dashboardUiConfig?: {
          hideTitle?: boolean;
          hideChartControls?: boolean;
          hideTab?: boolean;
          filters?: { visible?: boolean; expanded?: boolean };
          /**
           * Appended verbatim to the iframe's query string. This is the only
           * channel for pushing filter state into an embedded dashboard — the
           * SDK exposes readers (getDataMask) but no setter — which is why
           * changing filters requires a re-embed.
           */
          urlParams?: Record<string, string>;
        };
      }) => Promise<{ unmount: () => void }>;
    };
  }
}

const pulse = keyframes`
  0% { transform: scale(1); opacity: 0.8; }
  50% { transform: scale(1.2); opacity: 1; }
  100% { transform: scale(1); opacity: 0.8; }
`;

// FJL fares are rendered symbol-less in the embedded Superset charts (the wrong
// '$' was stripped, and a static D3 symbol can't track the live currency); this
// map backs the "Values in <CUR>" indicator. Mirrors KPIRow's CURRENCY_SYMBOL —
// kept local rather than exporting that const across modules.
const FJL_CURRENCY_SYMBOL: Record<'NOK' | 'EUR' | 'DKK', string> = {
  NOK: 'kr', EUR: '€', DKK: 'kr',
};

export default function DashboardViewerPage() {
  const { id } = useParams<{ id: string }>();
  const { session } = useSession();
  const navigate = useNavigate();
  const mountRef = useRef<HTMLDivElement>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dataDate, setDataDate] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // ── Date filter (drives RLS on chart queries via guest token) ──
  // Default to single-day mode; the actual day is filled in once
  // /available-dates resolves. We keep dateFilter in a ref so the
  // SDK's fetchGuestToken closure always reads the latest value
  // without having to re-bind the SDK callback on every change.
  const [availableDates, setAvailableDates] = useState<string[]>([]);
  const [datesLoading, setDatesLoading] = useState(true);
  const [dateFilter, setDateFilter] = useState<DashboardDateFilter>({ mode: 'single' });
  const dateFilterRef = useRef<DashboardDateFilter>(dateFilter);
  useEffect(() => { dateFilterRef.current = dateFilter; }, [dateFilter]);

  // FJL KPIs are computed within a single currency at a time (raw rows span
  // EUR/DKK/NOK across regional sites). NOK is the default since Fjord Line
  // is Norwegian. JY/PW have no currency dimension and ignore this state.
  const [fjlCurrency, setFjlCurrency] = useState<'NOK' | 'EUR' | 'DKK'>('NOK');
  // Kept in a ref so the SDK's fetchGuestToken closure always reads the latest
  // currency (same pattern as dateFilterRef above).
  const fjlCurrencyRef = useRef(fjlCurrency);
  useEffect(() => { fjlCurrencyRef.current = fjlCurrency; }, [fjlCurrency]);

  const meta = id ? DASHBOARD_META[id] : undefined;

  // ── WinAir global filter bar ──
  // WM shows the dashboard's own native filters ABOVE the iframe instead of in
  // Superset's left-hand panel. Selections travel as a rison dataMask on the
  // iframe URL, which Superset reads once at mount — so `appliedFilterParams`
  // is what the embed is currently built from, and `pendingFilters` is what the
  // user has staged. Apply promotes one to the other and re-embeds.
  // "Winair" here means "a tenant with its own out-of-iframe filter bar and tab
  // row", which is now WinAir and DreamAir. The name is kept so the ~25 call
  // sites below stay recognisable against git history; the chrome it paints
  // with comes from the tenant, not from a hardcoded WinAir constant.
  const chrome = getTenantChrome(meta?.tenant?.toLowerCase());
  const isWinair = chrome !== null;
  // The date chips wear SCOPE_ACCENT, not BANNER_BG: they state which capture
  // the page is scoped to, and Liat paints scope in its logo blue while the
  // other branded tenants alias it to their brand.
  const SCOPE_ACCENT = chrome?.SCOPE_ACCENT;
  const brandInk = chrome?.brandInk;
  // Dashboards whose Chart view mints a form_data_key overlay so the global
  // filter bar reaches the standalone explore iframe. App-route ids. WM only for
  // now — it is the only dashboard with an out-of-iframe bar. Extend one at a
  // time, each after checking Chart view against Dashboard view for a filtered
  // chart: the overlay merges with each slice's SAVED adhoc_filters.
  const chartFiltersEnabled = !!id && CHART_FILTER_DASHBOARDS.includes(id);
  const [filterConfig, setFilterConfig] = useState<DashboardFilter[]>([]);
  const [filtersLoading, setFiltersLoading] = useState(false);
  const [filtersError, setFiltersError] = useState<string | null>(null);
  const [pendingFilters, setPendingFilters] = useState<DashboardFilterSelections>({});
  const [appliedFilters, setAppliedFilters] = useState<DashboardFilterSelections>({});
  const [applyingFilters, setApplyingFilters] = useState(false);
  // Chart view keeps its OWN selections, per slice, rather than sharing the
  // dashboard's. Applying a filter while looking at one chart must affect that
  // chart and nothing else — the dashboard's own filter state is a separate
  // thing the user set separately, and a shared set would silently re-filter
  // every other chart the moment they switched to it.
  const [chartPending, setChartPending] = useState<Record<number, DashboardFilterSelections>>({});
  const [chartApplied, setChartApplied] = useState<Record<number, DashboardFilterSelections>>({});
  const [appliedFilterParams, setAppliedFilterParams] = useState('');
  const appliedFilterParamsRef = useRef(appliedFilterParams);
  useEffect(() => { appliedFilterParamsRef.current = appliedFilterParams; }, [appliedFilterParams]);

  const normalizeSelections = (s: DashboardFilterSelections) =>
    JSON.stringify(
      Object.entries(s)
        .filter(([, v]) => v && v.length > 0)
        .map(([k, v]) => [k, [...v].sort()] as [string, string[]])
        .sort((a, b) => a[0].localeCompare(b[0])),
    );

  useEffect(() => {
    if (!id || !isWinair) {
      setFilterConfig([]);
      return;
    }
    let cancelled = false;
    setFiltersLoading(true);
    setFiltersError(null);
    api.superset.getFilterConfig(id)
      .then(res => { if (!cancelled) setFilterConfig(res.filters ?? []); })
      .catch(err => {
        if (cancelled) return;
        console.error('[WinairFilters] filter-config failed:', err);
        setFiltersError(err?.message ?? 'could not load filters');
      })
      .finally(() => { if (!cancelled) setFiltersLoading(false); });
    return () => { cancelled = true; };
  }, [id, isWinair]);

  const applyWinairFilters = async (selections: DashboardFilterSelections) => {
    if (!id) return;
    setApplyingFilters(true);
    try {
      if (supersetTabRef.current) {
        // A tab is pinned, so filters have to travel in the SAME permalink -
        // a permalink_key next to a native_filters param would leave two
        // sources of truth for filter state racing each other on mount.
        const { key } = await api.superset.mintDashboardPermalink(id, {
          activeTab: supersetTabRef.current, selections,
        });
        permalinkKeyRef.current = key;
        // Cache under the same key the tab effect uses, so switching away and
        // back on this filter state is free.
        if (key) {
          permalinkCacheRef.current.set(
            `${supersetTabRef.current}|${normalizeSelections(selections)}`, key,
          );
        }
        setAppliedFilterParams('');
        appliedFilterParamsRef.current = '';
      } else {
        const { native_filters } = await api.superset.buildFilterParams(id, selections);
        permalinkKeyRef.current = null;
        setAppliedFilterParams(native_filters);
        appliedFilterParamsRef.current = native_filters;   // the embed reads this synchronously
      }
      setAppliedFilters(selections);
      // On Latest Prices the iframe is hidden: the panel refetches from
      // appliedFilters on its own, so re-embedding now would run every chart
      // in a pane nobody is looking at. Defer it to the next Superset tab.
      if (isWinair && activeTabRef.current === PRICES_TAB) embedStaleRef.current = true;
      else setRefreshKey(k => k + 1);
    } catch (err: any) {
      console.error('[WinairFilters] filter-params failed:', err);
      setFiltersError(err?.message ?? 'could not apply filters');
    } finally {
      setApplyingFilters(false);
    }
  };

  const handleWinairReset = () => {
    setPendingFilters({});
    void applyWinairFilters({});
  };

  // ── Slice & dice: chart selector + isolated chart view (additive) ──
  // viewMode toggles the right pane between the embedded dashboard SDK iframe
  // (existing) and a single-chart standalone iframe (new).  selectedSliceId
  // tracks which analytics chart the user picked.
  const [viewMode, setViewMode] = useState<'dashboard' | 'chart'>('dashboard');
  const [selectedSliceId, setSelectedSliceId] = useState<number | null>(null);

  // WinAir reads its charts inside the embedded dashboard only, so the whole
  // Chart view - toggle, selector panel and single-chart pane - is off there.
  // activeViewMode, not viewMode, is what the rest of the component reads, so
  // a stale 'chart' in state can never surface the pane on such a dashboard.
  const chartViewEnabled = hasChartView(id);
  const activeViewMode = chartViewEnabled ? viewMode : 'dashboard';

  // The selection is mirrored into ?chart=<slice_id> so the sidebar can link
  // straight to a chart and so a chart view is bookmarkable. The state above
  // stays authoritative for rendering — the param is a second way in, not a
  // replacement (chartPending/chartApplied are keyed off selectedSliceId).
  const [searchParams, setSearchParams] = useSearchParams();
  const chartParam = searchParams.get('chart');

  // ── Tab deep-linking (?tab=TAB-xxx, set by the sidebar and, for WinAir, by
  // the tab bar) ──
  // The Embedded SDK cannot select a tab after mount and Superset reads the
  // URL once, so the tab travels as a minted permalink_key instead. Both the
  // key and the tab live in refs because the embed effect reads them
  // synchronously while building dashboardUiConfig.
  const tabParam = searchParams.get('tab');
  // WinAir's bar always has a selection. No ?tab= means Latest Prices, which
  // is CPI-rendered and must never be sent to Superset as a tab id.
  const activeTab = isWinair ? (tabParam ?? PRICES_TAB) : null;
  // Only genuine Superset layout ids reach the permalink endpoint. Named
  // supersetTab, not tabParam, so the invariant is visible at every read site.
  const supersetTab =
    tabParam && tabParam !== PRICES_TAB && tabParam !== DASHBOARD_TAB ? tabParam : null;
  const supersetTabRef = useRef<string | null>(supersetTab);
  const permalinkKeyRef = useRef<string | null>(null);
  const appliedFiltersRef = useRef<DashboardFilterSelections>({});
  useEffect(() => { supersetTabRef.current = supersetTab; }, [supersetTab]);
  useEffect(() => { appliedFiltersRef.current = appliedFilters; }, [appliedFilters]);
  // Read by the two defer-or-re-embed sites below. They used to test
  // supersetTabRef, but that is null on BOTH panes without a pinned section —
  // Latest Prices (iframe hidden, deferring correct) and the Dashboard
  // fallback tab (iframe in plain view, deferring left its charts stale).
  const activeTabRef = useRef<string | null>(activeTab);
  useEffect(() => { activeTabRef.current = activeTab; }, [activeTab]);

  // ── WinAir section list ──
  // Fetched only where the bar replaces Superset's own tab row. Everyone else
  // keeps that row, so their sidebar-only use of /tabs is untouched.
  const [winairTabs, setWinairTabs] = useState<DashboardTab[]>([]);
  const [tabsLoading, setTabsLoading] = useState(false);
  const [tabError, setTabError] = useState<string | null>(null);
  const [switchingTab, setSwitchingTab] = useState(false);

  // Departure-time and duration windows for the Latest Prices chart. Owned
  // here because their controls render inside the filter bar, which lives on
  // this page rather than in the pane they filter. Deliberately NOT reset when
  // the route changes — "morning departures under two hours" is a question
  // asked of every route the user looks at, not of one.
  const [depTimeRange, setDepTimeRange] = useState<Range>(FULL_DEP_RANGE);
  const [durationRange, setDurationRange] = useState<Range>(FULL_DURATION_RANGE);

  useEffect(() => {
    if (!id || !isWinair) { setWinairTabs([]); return; }
    let cancelled = false;
    setTabsLoading(true);
    setTabError(null);
    api.superset.getDashboardTabs(id)
      .then(res => {
        if (cancelled) return;
        // Only a real navigation strip may stand in for Superset's tab row.
        // Without this the bar could steer by one section's sub-tabs and
        // address a fifth of the dashboard while looking complete.
        if (res.tabs_are_navigation && res.tabs.length > 0) {
          setWinairTabs(res.tabs);
        } else {
          setWinairTabs([]);
          setTabError('Dashboard sections are unavailable — showing the dashboard whole.');
        }
      })
      .catch(err => {
        if (cancelled) return;
        console.error('[WinairTabs] tab fetch failed:', err);
        setWinairTabs([]);
        setTabError('Could not load the dashboard sections — showing the dashboard whole.');
      })
      .finally(() => { if (!cancelled) setTabsLoading(false); });
    return () => { cancelled = true; };
  }, [id, isWinair]);

  // Minted permalinks, keyed on tab + the filter state baked into them.
  // Re-opening a section already visited costs no Superset round-trip, which
  // is most of the cost of a tab switch.
  const permalinkCacheRef = useRef<Map<string, string>>(new Map());
  // The embed is deferred while WinAir sits on Latest Prices, so anything
  // that would have forced a re-embed just marks it stale instead.
  const embedStaleRef = useRef(false);
  const embeddedOnceRef = useRef(false);

  // Mint a fresh permalink whenever the pinned tab changes, then re-embed.
  // Filter changes do NOT come through here - applyWinairFilters re-mints with
  // the tab included, so the two never fight over the embed.
  useEffect(() => {
    if (!id) return;
    if (!supersetTab) {
      // Left a pinned tab. For WinAir that means Latest Prices is showing and
      // the iframe is hidden, so re-embedding would be work nobody can see —
      // mark it stale and let the next Superset tab pay for it.
      if (permalinkKeyRef.current) {
        permalinkKeyRef.current = null;
        if (isWinair) embedStaleRef.current = true;
        else setRefreshKey(k => k + 1);
      }
      return;
    }
    const cacheKey = `${supersetTab}|${normalizeSelections(appliedFiltersRef.current)}`;
    const cached = permalinkCacheRef.current.get(cacheKey);
    if (cached) {
      permalinkKeyRef.current = cached;
      setRefreshKey(k => k + 1);
      return;
    }
    let cancelled = false;
    setSwitchingTab(true);
    api.superset.mintDashboardPermalink(id, {
      activeTab: supersetTab, selections: appliedFiltersRef.current,
    })
      .then(({ key }) => {
        if (cancelled) return;
        // A null key is a SUCCESS response meaning "nothing to pin". Treated
        // as a key it would leave the bar naming one section while the iframe
        // showed another, so it is a failure for our purposes.
        if (!key) throw new Error('no permalink returned');
        permalinkCacheRef.current.set(cacheKey, key);
        permalinkKeyRef.current = key;
        setTabError(null);
        setRefreshKey(k => k + 1);
      })
      .catch(err => {
        if (cancelled) return;
        // Must still embed: with Superset's own tab row hidden, leaving the
        // iframe untouched would strand the user on a stale section with a
        // spinner and no way out.
        console.error('[DashboardTabs] permalink mint failed:', err);
        permalinkKeyRef.current = null;
        if (isWinair) setTabError('Could not open that section — showing the dashboard default.');
        setRefreshKey(k => k + 1);
      })
      .finally(() => { if (!cancelled) setSwitchingTab(false); });
    return () => { cancelled = true; };
  }, [id, supersetTab, isWinair]); // eslint-disable-line react-hooks/exhaustive-deps

  // The Dashboard fallback tab shows the iframe WITHOUT pinning a section, so
  // the permalink effect above never re-embeds for it — arriving there still
  // has to pay for anything deferred while Latest Prices was up, or for the
  // very first embed, which the landing gate skipped. Ordered after that
  // effect on purpose: it clears permalinkKeyRef first, so the embed this
  // triggers opens Superset's own default section rather than a stale pin.
  useEffect(() => {
    if (!isWinair || activeTab !== DASHBOARD_TAB) return;
    if (embedStaleRef.current || !embeddedOnceRef.current) setRefreshKey(k => k + 1);
  }, [isWinair, activeTab]);

  /** Move the WinAir bar. `?tab=` is the single source of truth for the selection. */
  const selectTab = (next: string) => {
    const p = new URLSearchParams(searchParams);
    if (next === PRICES_TAB) p.delete('tab');
    else p.set('tab', next);
    // replace, not push — a tab is a view of one page, and a history entry per
    // click would make Back walk the tab strip instead of leaving the page.
    setSearchParams(p, { replace: true });
  };

  const writeChartParam = (sliceId: number | null) => {
    const next = new URLSearchParams(searchParams);
    if (sliceId === null) next.delete('chart');
    else next.set('chart', String(sliceId));
    setSearchParams(next, { replace: true });
  };

  // Passing undefined skips the fetch entirely - no point asking Superset for a
  // chart manifest the page will never show.
  const { analyticsCharts, loading: chartsLoading, error: chartsError, refetch: refetchCharts } =
    useDashboardCharts(chartViewEnabled ? id : undefined);

  // Narrow viewport → collapse selector into a horizontal chip rail
  const isNarrow = useMediaQuery((t: Theme) => t.breakpoints.down('md'));

  // Below lg the header runs out of room once the cap-date chip joins it and
  // the title starts wrapping to a second line, so the chip drops its
  // "Cap date:" prefix and shows just the date. Its tooltip and the popover's
  // own heading still name it. Deliberately a wider threshold than isNarrow —
  // with the sidebar open there is ~260px less room than this measures.
  const isHeaderTight = useMediaQuery((t: Theme) => t.breakpoints.down('lg'));

  // When the chart list resolves (initial load OR dashboard switch), default
  // to the first chart.  If the current selection still exists in the new
  // list (e.g. an unrelated re-render), keep it — avoids snapping back to
  // chart 1 every time the manifest re-resolves.
  useEffect(() => {
    // Deliberately do NOT null the selection on an empty list. The manifest is
    // memoised on [data, loading, error], so it re-identifies on every load
    // flip; nulling here and re-defaulting on the next tick is what snapped the
    // user back to the first chart mid-session. The render is already gated on
    // analyticsCharts.length, so holding a stale id is harmless.
    if (analyticsCharts.length === 0) return;
    // A ?chart= that names a real slice wins over the first-chart default —
    // otherwise a sidebar deep link would flash the right chart and then snap
    // back to chart 1 the moment the manifest resolved.
    const fromUrl = chartParam === null ? NaN : Number(chartParam);
    if (Number.isFinite(fromUrl) && analyticsCharts.some(c => c.slice_id === fromUrl)) {
      setSelectedSliceId(fromUrl);
      setViewMode('chart');
      return;
    }
    setSelectedSliceId(prev =>
      prev !== null && analyticsCharts.some(c => c.slice_id === prev)
        ? prev
        : analyticsCharts[0].slice_id
    );
  }, [analyticsCharts, chartParam]);

  // Returning to a different dashboard always starts in Dashboard mode —
  // unless the URL asked for a specific chart, which the effect above adopts.
  useEffect(() => {
    if (!searchParams.get('chart')) setViewMode('dashboard');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // ── Load available cap_date values for this dashboard ──
  // Resets to default single-day mode whenever the dashboard changes, then
  // anchors on the most recent date once /available-dates resolves.
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setDatesLoading(true);
    setAvailableDates([]);
    setDateFilter({ mode: 'single' });
    api.superset.getAvailableDates(id)
      .then(res => {
        if (cancelled) return;
        const dates = res.dates ?? [];
        setAvailableDates(dates);
        if (dates.length > 0) {
          setDateFilter({ mode: 'single', capDateEq: dates[0] });
        }
      })
      .catch(err => {
        if (!cancelled) console.error('[DateFilter] available-dates failed:', err);
      })
      .finally(() => { if (!cancelled) setDatesLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  const handleDateFilterChange = (next: DashboardDateFilter) => {
    setDateFilter(next);
    // On Latest Prices the iframe is hidden and the panel refetches on its own
    // capDate prop, so a re-embed here would re-run every chart out of sight.
    // fetchGuestToken reads dateFilterRef, so a deferred embed still picks up
    // the current date whenever it eventually runs.
    if (isWinair && activeTabRef.current === PRICES_TAB) embedStaleRef.current = true;
    else setRefreshKey(k => k + 1);   // bump → re-embed with new RLS-scoped guest token
  };

  // Effective selection — falls back to the first chart if state hasn't
  // settled yet.  Keeps the right pane non-blank in the brief window between
  // viewMode='chart' and the default-selection effect committing.
  const effectiveSliceId: number | null = selectedSliceId ?? analyticsCharts[0]?.slice_id ?? null;

  const selectedIndex = useMemo(
    () => analyticsCharts.findIndex(c => c.slice_id === effectiveSliceId),
    [analyticsCharts, effectiveSliceId],
  );

  // ── Filter bar bindings ──────────────────────────────────────────────────
  // The one bar serves both views, but they own different state: the dashboard
  // has a single global selection set, chart view has one set per chart.
  const inChartView = activeViewMode === 'chart' && effectiveSliceId !== null;

  // In chart view the bar offers only the filters that reach the SELECTED chart
  // — the dashboard's own scope, read from Superset, not a guess.
  const barFilters = useMemo(
    () => (inChartView
      ? filterConfig.filter(f => filterAppliesTo(f, effectiveSliceId))
      : filterConfig),
    [filterConfig, inChartView, effectiveSliceId],
  );

  const barPending = inChartView ? (chartPending[effectiveSliceId!] ?? {}) : pendingFilters;
  const barApplied = inChartView ? (chartApplied[effectiveSliceId!] ?? {}) : appliedFilters;
  const barDirty = normalizeSelections(barPending) !== normalizeSelections(barApplied);

  // ── Latest Prices scope, read off the SAME filter bar ──
  // The pane takes its route and refinements from what the user already
  // applied above, rather than growing a second set of controls that could
  // disagree with the dashboard beside it. Selections are keyed by native
  // filter id, so the column name (`field`) is what maps a filter to a
  // meaning — the ids are Superset's and carry none.
  const pricesScope = useMemo(() => {
    // EVERY selected value, not the first. All four WinAir filters are
    // multi-select, and taking only the first made the chart quietly disagree
    // with the Superset section beside it — which reads as a data problem
    // rather than a missing feature.
    const allValuesOf = (field: string): string[] => {
      const filter = filterConfig.find(f => f.field === field);
      return filter ? (appliedFilters[filter.id] ?? []) : [];
    };
    // Numeric filter values arrive as rendered, e.g. stops as "0.0"/"1.0"
    // because the dataset column is a float. Number() normalises that;
    // non-integers are dropped rather than sent on to be rejected.
    const toInts = (values: string[]): number[] =>
      values.map(Number).filter(n => Number.isInteger(n));

    const routeFilter = filterConfig.find(f => f.field === 'route');
    // "EIS → SXM" is the label wm_all_airlines_fares builds; the API takes
    // the two stations as ORG-DST. Keep both: the label is what the filter
    // bar expects back when the panel offers a shortcut.
    const toRoute = (label: string): { market: string; label: string } | null => {
      const parts = label.split('→').map(s => s.trim());
      return parts.length === 2 && parts[0] && parts[1]
        ? { market: `${parts[0]}-${parts[1]}`, label }
        : null;
    };
    const notNull = <T,>(v: T | null): v is T => v !== null;

    return {
      routes: allValuesOf('route').map(toRoute).filter(notNull).map(r => r.market),
      fltNums: allValuesOf('flt_num'),
      stops: toInts(allValuesOf('stops')),
      daysLeft: toInts(allValuesOf('days_left')),
      tripTypes: allValuesOf('trip_type'),
      // The panel falls back to the first of these when no route is applied,
      // so Latest Prices opens with a chart instead of an empty box.
      routeOptions: (routeFilter?.values ?? []).map(toRoute).filter(notNull),
    };
  }, [filterConfig, appliedFilters]);

  // ── Latest Prices capture date ──
  // The price-points endpoint pins ONE capture day (an equality — a range
  // predicate on the snapshot table is the known slow path), so range mode
  // resolves to the newest capture INSIDE the window, found against
  // /available-dates. Resolving here is what makes the panel react to a
  // custom range at all: it used to key its fetch on the raw range END, a
  // free calendar value — editing From changed nothing, and a To on a day
  // with no capture emptied the chart while the window held plenty of data.
  const pricesCapDate = useMemo(() => {
    if (dateFilter.mode === 'single') return dateFilter.capDateEq ?? null;
    const { capDateFrom: from, capDateTo: to } = dateFilter;
    // availableDates is newest-first, so the first hit is the newest capture
    // in the window. An end cleared mid-edit leaves that side open rather
    // than matching nothing.
    return availableDates.find(d => (!from || d >= from) && (!to || d <= to)) ?? null;
  }, [dateFilter, availableDates]);
  // A range that skips every capture day is a real "nothing to show" —
  // distinct from single mode's null, which means "let the API pin the
  // newest". The panel needs the difference to say so instead of quietly
  // plotting a day the user did not pick.
  const pricesNoCapture =
    dateFilter.mode === 'range' && availableDates.length > 0 && pricesCapDate === null;

  const handleBarPendingChange = (next: DashboardFilterSelections) => {
    if (inChartView) setChartPending(m => ({ ...m, [effectiveSliceId!]: next }));
    else setPendingFilters(next);
  };

  const handleBarApply = () => {
    if (!inChartView) { void applyWinairFilters(pendingFilters); return; }
    // Chart view commits locally and does NOT bump refreshKey: the dashboard
    // iframe is a different view with its own filters, and re-embedding it here
    // would re-run every chart on it for something not on screen — which is
    // also what threw the user back to the first chart.
    setChartApplied(m => ({ ...m, [effectiveSliceId!]: barPending }));
  };

  const handleBarReset = () => {
    // "Clear all" has to mean all of it. The time ranges render in the same
    // bar, so leaving them narrowed here would clear the visible dropdowns
    // while the chart stayed filtered by controls that just reset to look
    // untouched.
    setDepTimeRange(FULL_DEP_RANGE);
    setDurationRange(FULL_DURATION_RANGE);
    if (!inChartView) { handleWinairReset(); return; }
    setChartPending(m => ({ ...m, [effectiveSliceId!]: {} }));
    setChartApplied(m => ({ ...m, [effectiveSliceId!]: {} }));
  };

  const handleSelectChart = (sliceId: number) => {
    setSelectedSliceId(sliceId);
    setViewMode('chart');     // clicking a chart name auto-switches to chart view
    writeChartParam(sliceId); // keep the URL (and the sidebar highlight) in step
  };

  const handlePrev = () => {
    if (analyticsCharts.length === 0) return;
    const idx = selectedIndex < 0 ? 0 : selectedIndex;
    const next = (idx - 1 + analyticsCharts.length) % analyticsCharts.length;
    setSelectedSliceId(analyticsCharts[next].slice_id);
    writeChartParam(analyticsCharts[next].slice_id);
  };

  const handleNext = () => {
    if (analyticsCharts.length === 0) return;
    const idx = selectedIndex < 0 ? 0 : selectedIndex;
    const next = (idx + 1) % analyticsCharts.length;
    setSelectedSliceId(analyticsCharts[next].slice_id);
    writeChartParam(analyticsCharts[next].slice_id);
  };

  // Freshness belongs to the data, not to the embed. It used to be fetched
  // inside the embed effect, which re-ran it on every tab switch for a value
  // that cannot change in between — and left the header's date blank entirely
  // whenever the embed was deferred.
  useEffect(() => {
    if (!meta) return;
    let cancelled = false;
    api.stats.getFreshnessMetrics()
      .then(freshness => {
        if (cancelled) return;
        const match = freshness.find(f => f.domain === meta.freshnessDomain);
        if (match?.report_date) setDataDate(match.report_date);
      })
      .catch(() => { /* non-critical — the dashboard works without the date */ });
    return () => { cancelled = true; };
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!id || !mountRef.current || !meta) return;

    // WinAir lands on Latest Prices, which is CPI-rendered. Embedding the
    // dashboard behind it would spend a guest token and every chart query on
    // a pane nobody has asked for. Deferred until a section is selected —
    // after which the iframe stays mounted and this gate never fires again.
    // isLoading must still be cleared here: it initialises true and is only
    // ever cleared inside this effect, so returning early without it leaves
    // the Refresh button disabled for good.
    if (isWinair && activeTab === PRICES_TAB && !embeddedOnceRef.current) {
      setIsLoading(false);
      return;
    }

    let unmount: (() => void) | undefined;
    // `unmount` is only assigned after two awaits. If refreshKey bumps again
    // before then (Apply twice in quick succession), cleanup would run with it
    // still undefined and the in-flight embed would leak — its guest-token
    // refresh timer keeps polling forever. This flag lets the late assignment
    // tear itself down instead.
    let disposed = false;

    const embed = async () => {
      try {
        // ── 1. Frontend access guard ──
        if (!canAccessDashboard(session, id)) {
          setError('Access Denied: You do not have permission to view this dashboard.');
          setIsLoading(false);
          return;
        }

        // ── 2. Wait for SDK (UMD bundle from CDN) ──
        let attempts = 0;
        while (!window.supersetEmbeddedSdk && attempts < 20) {
          await new Promise(r => setTimeout(r, 300));
          attempts++;
        }
        if (!window.supersetEmbeddedSdk) {
          throw new Error('Superset Embedded SDK did not load. Check the <script> tag in index.html.');
        }

        // ── 3. Fetch embedded_uuid + initial guest token from backend ──
        //   Pass the current date filter so the very first token carries
        //   the cap_date RLS clause — otherwise the iframe briefly loads
        //   unfiltered data before the SDK re-fetches.
        setIsLoading(true);
        const metadata = await api.superset.getGuestToken(
          id, dateFilterRef.current,
          meta.tenant === 'FJL' ? fjlCurrencyRef.current : undefined,
        );

        // ── 4. Embed the dashboard ──
        //   SDK creates an iframe to: {SUPERSET_URL}/embedded/{embedded_uuid}
        //   which is Superset's canvas-only view (no global nav, no chrome).
        //   The guest token is sent to the iframe via postMessage.
        //
        // Extra query params for that iframe URL. The SDK spreads these LAST
        // over its own derived params, so uiConfig here replaces the value it
        // computes from the hide* flags below.
        const urlParams: Record<string, string> = {};
        // While a section is pinned, the teal bar is the sole navigation and
        // Superset's own top-level tab strip would repeat the same five names.
        // uiConfig 13 = hideTitle(1) + hideNav(4) + hideChartControls(8).
        // NOTE: Superset 3.1.0 never consumes hideNav (verified live) — the
        // strip is actually hidden by the WM-EMBED-HIDE-TOPTABS css block in
        // dashboard 6's metadata (scripts/superset/wm_hide_toptabs.py).
        // hideNav becomes functional after a Superset upgrade; keep sending it
        // so this conditional takes over and the css block can be retired.
        if (isWinair && supersetTabRef.current) urlParams.uiConfig = '13';
        // Seed the dashboard's state from outside the iframe. A permalink
        // wins when one is pinned: it already carries the filters as well
        // as the tab, so passing native_filters too would give Superset two
        // sources of truth for the same thing. Both omitted when empty, so
        // the dashboard falls back to its own defaults.
        if (permalinkKeyRef.current) {
          urlParams.permalink_key = permalinkKeyRef.current;
        } else if (isWinair && appliedFilterParamsRef.current) {
          urlParams.native_filters = appliedFilterParamsRef.current;
        }

        const result = await window.supersetEmbeddedSdk.embedDashboard({
          id: metadata.embedded_uuid,
          supersetDomain: SUPERSET_URL,
          mountPoint: mountRef.current!,
          fetchGuestToken: async () => {
            const { token } = await api.superset.getGuestToken(
              id, dateFilterRef.current,
              meta.tenant === 'FJL' ? fjlCurrencyRef.current : undefined,
            );
            return token;
          },
          dashboardUiConfig: {
            hideTitle: true,           // hide Superset's title bar (we show our own + data date)
            hideChartControls: true,   // hide chart-level three-dot menus
            hideTab: false,
            filters: {
              // WinAir drives the same native filters from the bar above, so
              // Superset's own panel would be a duplicate set of controls.
              // NOTE: Superset 3.1.0 ignores visible (show_filters is declared but
              // never consumed) — the panel is actually hidden by the
              // WM-EMBED-HIDE-FILTERBAR css block in dashboard 6's metadata.
              // visible becomes functional after a Superset upgrade; keep it.
              visible: !isWinair,
              expanded: !isWinair,   // others: filters visible (restyled as a horizontal bar via dashboard CSS)
            },
            ...(Object.keys(urlParams).length ? { urlParams } : {}),
          },
        });
        if (disposed) { result.unmount(); return; }
        unmount = result.unmount;
        // From here the iframe exists, so the lazy gate above must not fire
        // again — leaving Latest Prices and returning should not tear it down.
        embeddedOnceRef.current = true;
        embedStaleRef.current = false;

        // Give Superset a moment to render inside the iframe
        setTimeout(() => setIsLoading(false), 1500);
      } catch (err: any) {
        console.error('Dashboard embed failed:', err);
        const msg = err?.message || 'Failed to load dashboard';
        setError(msg.startsWith('API ') || msg.startsWith('Network Error')
          ? `Backend error: ${msg}`
          : msg);
        setIsLoading(false);
      }
    };

    embed();

    return () => { disposed = true; unmount?.(); };
  }, [id, refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const LoadingIcon = meta?.isAirline ? Flight : DirectionsBoat;
  const loadingLabel = meta?.isAirline ? 'Loading Airline Analytics...' : 'Preparing Maritime Insights...';

  // Format the data date for display
  const formattedDate = dataDate
    ? new Date(dataDate + 'T00:00:00').toLocaleDateString('en-GB', {
        day: '2-digit', month: 'short', year: 'numeric',
      })
    : null;

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header bar */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 0 }}>
        {/* WinAir shows neither title nor back arrow. Its identity is already
            in the app-bar logo directly above, and it navigates by the sidebar
            and its own tab bar — /dashboards would bounce a single-dashboard
            tenant straight back here anyway (see SupersetPage). That leaves the
            two date chips, which is all this row needs to say. */}
        {!isWinair && (
          <>
            <Tooltip title="Back to dashboards">
              <IconButton onClick={() => navigate('/dashboards')} sx={{ mr: 1 }}>
                <ArrowBack />
              </IconButton>
            </Tooltip>
            <Typography variant="h5" component="h1" fontWeight={600}>
              {meta?.title ?? 'Dashboard'}
            </Typography>
          </>
        )}
        {formattedDate && (
          <Chip
            icon={<CalendarMonth sx={{ fontSize: 16 }} />}
            label={`Latest data: ${formattedDate}`}
            size="small"
            variant="outlined"
            color="primary"
            sx={{
              // On WinAir this chip starts the row, so there is nothing to
              // separate it from and the leading gap would read as a stray indent.
              ml: isWinair ? 0 : 2,
              fontWeight: 500,
              // Branded tenants' chips follow their scope accent (brand red
              // on WinAir/DreamAir, wordmark blue on Liat), not app primary.
              ...(isWinair && {
                color: SCOPE_ACCENT,
                borderColor: SCOPE_ACCENT,
                '& .MuiChip-icon': { color: SCOPE_ACCENT },
              }),
            }}
          />
        )}

        {/* WinAir edits its cap date from here rather than from the filter bar
            below: range mode needs ~750px and the header has ~280px free with
            the sidebar open, so the chip reports the scope and a popover owns
            the editing. Deliberately NOT interchangeable with the chip above —
            that one reports data freshness (report_date from /stats/freshness),
            and the two routinely show the same date. */}
        {isWinair && (
          <CapDateChip
            availableDates={availableDates}
            value={dateFilter}
            onChange={handleDateFilterChange}
            loading={datesLoading}
            // For WinAir the cap date drives the Latest Prices panel as well as
            // the embed, so it always applies to whatever is on screen.
            appliesToView={isWinair || activeViewMode === 'dashboard'}
            compact={isHeaderTight}
            accent={SCOPE_ACCENT}
          />
        )}

        <Box sx={{ flexGrow: 1 }} />

        {/* View mode toggle — segmented control. Absent where Chart view is
            not offered, so the header reads as dashboard-only. WinAir has no
            Chart view and navigates by its own tab bar instead, so no toggle
            appears there at all. */}
        {chartViewEnabled && (
        <ToggleButtonGroup
          size="small"
          exclusive
          value={viewMode}
          onChange={(_, v) => {
            if (!v) return;
            // Defensive: if the user toggles into Chart view before the
            // default-selection effect has settled, pick the first chart now
            // so the right pane never renders blank.
            if (v === 'chart' && selectedSliceId === null && analyticsCharts.length > 0) {
              setSelectedSliceId(analyticsCharts[0].slice_id);
            }
            setViewMode(v);
            // Dashboard view isn't about one chart, so drop the param; entering
            // chart view stamps whichever chart is about to be shown.
            writeChartParam(v === 'chart' ? effectiveSliceId : null);
          }}
          sx={{
            mr: 1,
            p: '3px',
            gap: '2px',
            bgcolor: 'action.hover',
            borderRadius: 1,                  // 8px container
            border: 0,
            '& .MuiToggleButton-root': {
              px: 1.5,
              py: '5px',
              fontSize: 12,
              fontWeight: 500,
              textTransform: 'none',
              border: 0,
              borderRadius: '6px',
              color: 'text.secondary',
              gap: 0.75,
              '&:hover': { bgcolor: 'transparent' },
              '&.Mui-selected': {
                bgcolor: 'background.paper',
                color: 'text.primary',
                border: '0.5px solid',
                borderColor: 'divider',
                '&:hover': { bgcolor: 'background.paper' },
              },
              '&.Mui-disabled': { border: 0 },
            },
          }}
        >
          <ToggleButton value="dashboard" aria-label="Full dashboard view">
            <DashboardIcon sx={{ fontSize: 14 }} />
            Dashboard
          </ToggleButton>
          <ToggleButton value="chart" aria-label="Single chart view" disabled={analyticsCharts.length === 0}>
            <BarChartIcon sx={{ fontSize: 14 }} />
            Chart view
          </ToggleButton>
        </ToggleButtonGroup>
        )}

        <Tooltip title="Refresh dashboard">
          <IconButton
            size="small"
            onClick={() => setRefreshKey(k => k + 1)}
            disabled={isLoading}
            aria-label="Refresh dashboard"
            sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1 }}
          >
            <Refresh fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* WinAir: one row of navigation — Latest Prices, then the dashboard's
          own sections. Superset's tab row is hidden inside the iframe, so this
          bar is the only way to reach four fifths of the dashboard; it is
          rendered above the filter bar so the page reads top-down as
          what am I looking at → how is it filtered → the thing itself. */}
      {isWinair && (
        <WinairTabBar
          tabs={winairTabs}
          value={activeTab ?? PRICES_TAB}
          onChange={selectTab}
          loading={tabsLoading}
          switching={switchingTab}
          error={tabError}
        />
      )}

      {/* WinAir: the dashboard's native filters, lifted out of Superset's
          left-hand panel into a global bar. Rendered ABOVE both panes, not
          inside the dashboard pane, so Chart view gets it too — a second
          instance is not an option, because FilterSelect emits id={filter-*}
          with a matching htmlFor and two mounts would duplicate DOM ids.
          The cap date is not here — it lives in the page header (CapDateChip). */}
      {isWinair && (
        <WinairTopFilterBar
          filters={barFilters}
          filtersLoading={filtersLoading}
          filtersError={filtersError}
          pending={barPending}
          onPendingChange={handleBarPendingChange}
          dirty={barDirty}
          // Chart view's Apply is synchronous local state; the mint spinner in
          // the chart pane is what reports progress there.
          applying={inChartView ? false : applyingFilters}
          onApply={handleBarApply}
          onReset={handleBarReset}
          scopeLabel={inChartView
            ? analyticsCharts[Math.max(0, selectedIndex)]?.slice_name ?? 'this chart'
            : undefined}
          // Only on the Latest Prices tab. Duration is derived per fare by the
          // price-points endpoint and exists on no Superset dataset, so these
          // two can only ever act on that chart — showing them beside a
          // Superset section would be two controls that quietly do nothing.
          extraControls={activeTab === PRICES_TAB ? (
            <>
              <TimeRangeFilter
                label="Departure Time"
                value={depTimeRange}
                min={DEP_TIME_MIN}
                max={DEP_TIME_MAX}
                onChange={setDepTimeRange}
              />
              <TimeRangeFilter
                label="Duration"
                value={durationRange}
                min={DURATION_MIN}
                max={DURATION_MAX}
                onChange={setDurationRange}
                help="Journey time from departure to final arrival. Capped at 24h: arrival is stored without a date, so a journey crossing midnight cannot be told apart from a same-day one."
              />
            </>
          ) : undefined}
        />
      )}

      {/* ── Dashboard pane — kept mounted across mode toggles so the SDK
          iframe (and its guest-token / fetch lifecycle) survives a switch
          to Chart view and back without re-init.  In Chart view it is hidden
          via display:none, NOT unmounted. ──────────────────────────────── */}
      <Box sx={{
        // For WinAir the tab bar decides this: the embed is hidden whenever
        // Latest Prices is the selected tab.
        display: activeViewMode === 'dashboard' && !(isWinair && activeTab === PRICES_TAB)
          ? 'flex' : 'none',
        flexDirection: 'column',
        flexGrow: 1,
        minHeight: 0,
      }}>
        {/* Date filter bar — drives cap_date RLS on every chart in this dashboard.
            For FJL, a Currency dropdown sits to the right of the date toggle and
            is threaded into KPIRow so the tiles stay within a single currency. */}
        {!isWinair && (
        <Box sx={{ mb: 0.5, display: 'flex', alignItems: 'center', gap: 1 }}>
          <DateFilterToggle
            availableDates={availableDates}
            value={dateFilter}
            onChange={handleDateFilterChange}
            disabled={datesLoading || availableDates.length === 0}
          />
          <Box sx={{ flexGrow: 1 }} />
          {meta?.tenant === 'FJL' && (
            <>
              {/* Embedded charts now show fares without a symbol; this indicator
                  names the active currency. Plain label — re-renders on toggle,
                  no re-embed needed. */}
              <Typography
                sx={{ fontSize: 12, color: 'text.secondary', whiteSpace: 'nowrap' }}
                aria-live="polite"
              >
                Values in {fjlCurrency} ({FJL_CURRENCY_SYMBOL[fjlCurrency]})
              </Typography>
              <FormControl size="small" sx={{ ml: 1.5, minWidth: 88 }}>
              {/* No floating <InputLabel> here — at size="small" with the
                  outlined variant it tends to clip the notch and visually
                  push into the row above. renderValue keeps the control
                  self-describing ("Currency: NOK") without the label. */}
              <Select
                value={fjlCurrency}
                onChange={(e) => {
                  setFjlCurrency(e.target.value as 'NOK' | 'EUR' | 'DKK');
                  setRefreshKey(k => k + 1);   // re-embed with the new currency-scoped guest token
                }}
                renderValue={(v) => `Currency: ${v}`}
                inputProps={{ 'aria-label': 'Currency' }}
                sx={{
                  fontSize: 13,
                  height: 32,
                  '& .MuiSelect-select': { py: '6px', pl: 1.25, pr: '24px !important' },
                }}
              >
                <MenuItem value="NOK" sx={{ fontSize: 13 }}>NOK</MenuItem>
                <MenuItem value="EUR" sx={{ fontSize: 13 }}>EUR</MenuItem>
                <MenuItem value="DKK" sx={{ fontSize: 13 }}>DKK</MenuItem>
              </Select>
              </FormControl>
            </>
          )}
        </Box>
        )}

        {/* KPI row — CPI-rendered tiles + click-to-expand detail (SKY + FJL).
            These replace the Superset big-number tiles so the values and their
            drill-downs share a single source of truth and respond to the Cap
            Date picker above. The KPI set is per-airline (see KPIRow).
            cap_date: single-day uses the picked day; range uses the window's
            end (most recent) day, since the KPI queries are single-day.
            currency: only meaningful for FJL; ALT ignores it server-side.
            WM is deliberately excluded — WinAir's page leads with the global
            filter bar and the dashboard's own charts, with no KPI strip — and
            JY and PW joined it 2026-08-27 when they adopted the same chrome.
            The /kpi endpoints still serve WM, JY and PW, so this is a
            one-line reinstate. */}
        {(meta?.tenant === 'ALT' || meta?.tenant === 'FJL') && (
          <KPIRow
            airlineCode={meta.tenant}
            capDate={(dateFilter.mode === 'single' ? dateFilter.capDateEq : dateFilter.capDateTo) ?? ''}
            currency={meta.tenant === 'FJL' ? fjlCurrency : undefined}
          />
        )}

        {/* Dashboard container */}
        <Paper
          variant="outlined"
          sx={{
            flexGrow: 1,
            overflow: 'hidden',
            position: 'relative',
            bgcolor: 'background.paper',
            // Bleed past <main>'s p:3 horizontal padding so the embedded dashboard
            // gets the full available width — prevents right-edge clipping of the
            // last X-axis tick / legend items inside the iframe.
            mx: -3,
            borderRadius: 0,
            borderLeft: 'none',
            borderRight: 'none',
            // The SDK injects an <iframe> inside mountRef
            '& iframe': { width: '100%', height: '100%', border: 'none' },
          }}
        >
          {/* Loading overlay */}
          <Fade in={isLoading} unmountOnExit>
            <Box sx={{
              position: 'absolute', inset: 0, display: 'flex',
              flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              bgcolor: 'background.paper', zIndex: 10,
            }}>
              <LoadingIcon sx={{ fontSize: 56, color: isWinair ? brandInk : 'primary.main', mb: 2, animation: `${pulse} 2s infinite ease-in-out` }} />
              <Typography variant="h6" color="text.secondary">{loadingLabel}</Typography>
            </Box>
          </Fade>

          {/* Error state */}
          {error && (
            <Box sx={{ p: 4, textAlign: 'center' }}>
              <Typography color="error" variant="h6" gutterBottom>{error}</Typography>
              <Typography variant="body2" color="text.secondary">
                Check that Superset is running and the dashboard exists.
              </Typography>
            </Box>
          )}

          {/* SDK mount point — must stay in the DOM even while loading.
              Absolute-fill the (position:relative) Paper so the injected iframe
              exactly matches the flex-sized container. Avoids the brittle
              `calc(100vh - Npx)` that over-sized the iframe and let its bottom
              (the filter bar's APPLY FILTERS button) get clipped by the Paper's
              overflow:hidden. */}
          <Box
            key={refreshKey}
            ref={mountRef}
            sx={{
              position: 'absolute',
              inset: 0,
              visibility: isLoading ? 'hidden' : 'visible',
              '& > iframe': { width: '100%', height: '100% !important', border: 'none' },
            }}
          />
        </Paper>
      </Box>

      {/* ── Latest Prices pane (WinAir) — every observed fare, one dot each.
          Kept MOUNTED once first shown, unlike the Chart view pane above:
          it owns an ECharts instance and a fetched result set, and
          unmounting on every toggle would dispose the canvas and re-request
          the route. `active` tells it to re-measure, since a canvas laid out
          while display:none comes back zero-sized. ────────────────────── */}
      {isWinair && (
        <Box sx={{
          display: activeTab === PRICES_TAB ? 'flex' : 'none',
          flexDirection: 'column',
          flexGrow: 1,
          minHeight: 0,
          minWidth: 0,
        }}>
          <LatestPricesPanel
            routes={pricesScope.routes}
            capDate={pricesCapDate}
            noCaptureInRange={pricesNoCapture}
            // The header chip names a WINDOW in range mode; the chart plots
            // one capture day out of it, so the panel says which.
            showCapDate={dateFilter.mode === 'range'}
            stops={pricesScope.stops}
            fltNums={pricesScope.fltNums}
            daysLeft={pricesScope.daysLeft}
            tripTypes={pricesScope.tripTypes}
            depTime={depTimeRange}
            duration={durationRange}
            routeOptions={pricesScope.routeOptions}
            active={activeTab === PRICES_TAB}
          />
        </Box>
      )}

      {/* ── Chart view pane — selector sidebar + isolated chart iframe.
          Conditionally rendered so the sidebar (and the flex row) do not
          exist in the DOM during Dashboard mode — the dashboard view is
          visually identical to the pre-feature state. ─────────────────── */}
      {activeViewMode === 'chart' && (
        <Box sx={{
          flexGrow: 1,
          display: 'flex',
          flexDirection: isNarrow ? 'column' : 'row',
          minHeight: 0,
          minWidth: 0,
          // Match the dashboard Paper's edge-to-edge bleed past <main>'s p:3.
          mx: -3,
          // Clip any inner overflow so the page never shows a horizontal scrollbar.
          overflow: 'hidden',
          bgcolor: 'background.paper',
          borderTop: '1px solid',
          borderColor: 'divider',
        }}>
          <ChartSelectorPanel
            charts={analyticsCharts}
            selectedSliceId={effectiveSliceId}
            onSelectChart={handleSelectChart}
            loading={chartsLoading}
            error={chartsError}
            onRetry={refetchCharts}
            horizontal={isNarrow}
          />

          <Box sx={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minWidth: 0,
            minHeight: 0,
            // No vertical scroll on the chart pane — the iframe is sized to
            // fit the available height, and Superset re-renders the chart
            // smaller to keep everything visible in a single frame.
            overflow: 'hidden',
          }}>
            {effectiveSliceId !== null && analyticsCharts.length > 0 && (
              <SingleChartViewer
                sliceId={effectiveSliceId}
                sliceName={analyticsCharts[Math.max(0, selectedIndex)]?.slice_name ?? `Chart ${effectiveSliceId}`}
                supersetBaseUrl={SUPERSET_URL}
                currentIndex={Math.max(0, selectedIndex)}
                total={analyticsCharts.length}
                onPrev={handlePrev}
                onNext={handleNext}
                dashboardId={id!}
                overlayEnabled={chartFiltersEnabled}
                dateFilter={dateFilter}
                // This chart's OWN applied selections — not the dashboard's, and
                // not another chart's. Apply is the commit point, which is what
                // barDirty and the Apply button promise.
                selections={chartApplied[effectiveSliceId] ?? {}}
                refreshKey={refreshKey}
              />
            )}
          </Box>
        </Box>
      )}
    </Box>
  );
}
