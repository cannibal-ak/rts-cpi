import { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Typography, CircularProgress, Alert, Chip, Tooltip, useTheme, alpha } from '@mui/material';
import { TravelExplore, EventAvailable, EventBusy } from '@mui/icons-material';
import * as echarts from 'echarts/core';
import { LineChart, ScatterChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent, DataZoomComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { ComposeOption } from 'echarts/core';
import type { LineSeriesOption, ScatterSeriesOption } from 'echarts/charts';
import type {
  GridComponentOption, TooltipComponentOption, LegendComponentOption, DataZoomComponentOption,
} from 'echarts/components';

import EmptyState from '../../common/EmptyState';
import PriceDetailCard from './PriceDetailCard';
import {
  buildAirlineColorMap, formatClock, clockToMinutes,
  ROUTE_STYLES, ROUTE_STYLE_COUNT, DAYS_LEFT_MAX,
  SOLD_OUT_Y, NOT_ON_SALE_Y, AVAILABILITY_LABELS,
} from './priceChartTheme';
import { useCarrierColorTable } from '../tenantCarrierColors';
import { FULL_DEP_RANGE, FULL_DURATION_RANGE, isNarrowed, type Range } from './PriceChartFilters';
import { useBrandedChrome } from '../tenantChrome';
import { api } from '../../../api';
import type { PricePoint, NoFareDay } from '../../../api/client';

// Only the pieces this chart draws are registered — the full ECharts bundle
// is roughly twice the size and everything else in it is unused here.
echarts.use([
  LineChart, ScatterChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent, CanvasRenderer,
]);

type ChartOption = ComposeOption<
  | LineSeriesOption
  | ScatterSeriesOption
  | GridComponentOption
  | TooltipComponentOption
  | LegendComponentOption
  | DataZoomComponentOption
>;

interface LatestPricesPanelProps {
  /** Selected markets as "ORG-DST". Empty until the user applies a route. */
  routes: string[];
  /**
   * Capture date from the page header; null lets the API pin the newest.
   * In range mode the page resolves this to the newest capture INSIDE the
   * window — never the raw range end, which may be a day with no capture.
   */
  capDate: string | null;
  /**
   * The header's range holds no capture day at all. A real "nothing to
   * show": the panel skips fetching and says so, rather than plotting a
   * day the user did not pick.
   */
  noCaptureInRange?: boolean;
  /**
   * Name the capture day the dots come from in the context strip. Turned on
   * in range mode, where the header chip states a window rather than the
   * one day actually plotted.
   */
  showCapDate?: boolean;
  /** Remaining filter-bar selections, all multi-value. */
  stops: number[];
  fltNums: string[];
  daysLeft: number[];
  tripTypes: string[];
  /**
   * Departure-time and duration windows, in minutes. Owned by the page
   * because their controls live in the filter bar above this pane.
   */
  depTime: Range;
  duration: Range;
  /** Every route the dashboard offers. The first is the landing default. */
  routeOptions: Array<{ market: string; label: string }>;
  /**
   * Whether this pane is the selected tab. The pane stays mounted when hidden
   * so its chart and data survive a trip to a Superset section, and a canvas
   * sized while display:none comes back 0x0 — so becoming active has to force
   * a re-measure.
   */
  active: boolean;
}

/**
 * One availability-marker datum: every airline and route sharing a no-fare
 * date and class. Grouped so a busy day draws one marker carrying a list,
 * not a stack of overlapping dots.
 */
interface NoFareGroup {
  date: string;
  status: NoFareDay['status'];
  entries: NoFareDay[];
}

/** Identity of a plotted fare, for de-duplicating pinned cards. */
function pointKey(p: PricePoint): string {
  // market is part of the identity: the same airline, flight, date and fare
  // can legitimately appear under two selected markets, and without it the
  // second one silently fails to pin.
  return [p.market, p.airline, p.flt_num ?? '', p.dep_date, p.dep_time ?? '', p.tot_fare, p.cab_code ?? ''].join('|');
}

/**
 * Every fare observed on the selected routes, one dot each — no averaging.
 *
 * The Superset sections beside this one aggregate; this deliberately does not,
 * because the question it answers is "what exactly is each airline charging on
 * each departure", which an average destroys. Clicking a dot pins a card with
 * the full flight detail behind that price, and several stay open at once.
 */
export default function LatestPricesPanel({
  routes, capDate, noCaptureInRange = false, showCapDate = false,
  stops, fltNums, daysLeft, tripTypes, depTime, duration, routeOptions, active,
}: LatestPricesPanelProps) {
  const { brandInk, BANNER_BG } = useBrandedChrome();

  const theme = useTheme();
  const hostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  const [fetched, setFetched] = useState<PricePoint[]>([]);
  const [currency, setCurrency] = useState<string | null>(null);
  // The capture date is surfaced in the context strip only when showCapDate
  // asks for it (range mode). In single mode the page header's Cap date chip
  // already states it, and repeating it was one of the lines cluttering the
  // route strip.
  const [truncatedRoutes, setTruncatedRoutes] = useState<string[]>([]);
  const [noFareDays, setNoFareDays] = useState<NoFareDay[]>([]);
  // The server's own suppression flag: set when a stops/flt_num param made it
  // withhold no_fare_days. The client-side equivalent is derived below.
  const [availabilitySuppressed, setAvailabilitySuppressed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pinned, setPinned] = useState<PricePoint[]>([]);
  const [ready, setReady] = useState(false);

  // The chart cannot say anything useful about all 55 routes at once, and
  // opening blank makes the tab look broken — so with no route filter applied
  // it falls back to the first the dashboard offers.
  //
  // Panel-local on purpose. Seeding the shared filter instead would also scope
  // the Superset sections behind this tab, quietly changing what the rest of
  // the dashboard shows on arrival. The caption below says which route is
  // standing in, so the chart never claims to be something it is not.
  const defaultRoute = routes.length === 0 ? routeOptions[0] ?? null : null;
  const effectiveRoutes = defaultRoute ? [defaultRoute.market] : routes;

  // Arrays break effect identity, so the fetch keys on the joined string.
  const routesKey = effectiveRoutes.join(',');
  // Single-valued selections are pushed to the server to shrink the payload;
  // multi-valued ones are refined client-side below. Filtering client-side in
  // BOTH cases is what makes "multi-select silently became first-value-only"
  // structurally impossible rather than a thing to remember.
  const singleStop = stops.length === 1 ? stops[0] : undefined;
  const singleFltNum = fltNums.length === 1 ? fltNums[0] : undefined;
  const singleTripType = tripTypes.length === 1 ? tripTypes[0] : undefined;

  // ── Data ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!routesKey || noCaptureInRange) {
      setFetched([]);
      setPinned([]);
      setTruncatedRoutes([]);
      setNoFareDays([]);
      setAvailabilitySuppressed(false);
      // A leftover error from the previous query would sit above the
      // no-capture empty state and blame the wrong thing — and a fetch this
      // bail-out just aborted skips its own finally, which would leave the
      // spinner up for good.
      setError(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api.airline
      .listPricePoints(
        {
          routes: routesKey,
          include_availability: 1,
          ...(capDate ? { cap_date: capDate } : {}),
          ...(singleStop !== undefined ? { stops: singleStop } : {}),
          ...(singleFltNum ? { flt_num: singleFltNum } : {}),
          ...(singleTripType ? { trip_type: singleTripType } : {}),
        },
        { signal: controller.signal },
      )
      .then(res => {
        setFetched(res.points);
        setCurrency(res.currency);
        setTruncatedRoutes(res.truncated_routes ?? []);
        setNoFareDays(res.no_fare_days ?? []);
        setAvailabilitySuppressed(res.availability_suppressed ?? false);
        // A card describes a fare from the previous query; keeping it open
        // across a route or date change would annotate a point that is no
        // longer on the chart.
        setPinned([]);
      })
      .catch(err => {
        if (controller.signal.aborted) return;
        console.error('[LatestPrices] price-points failed:', err);
        setError(err?.message ?? 'could not load prices');
        setFetched([]);
        setNoFareDays([]);
        setAvailabilitySuppressed(false);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [routesKey, capDate, singleStop, singleFltNum, singleTripType, noCaptureInRange]);

  // ── Client-side refinement ──────────────────────────────────────────
  const depNarrowed = isNarrowed(depTime, FULL_DEP_RANGE);
  const durNarrowed = isNarrowed(duration, FULL_DURATION_RANGE);

  const points = useMemo(() => {
    const stopSet = stops.length ? new Set(stops) : null;
    const fltSet = fltNums.length ? new Set(fltNums) : null;
    const dbdSet = daysLeft.length ? new Set(daysLeft) : null;
    const tripSet = tripTypes.length ? new Set(tripTypes) : null;
    if (!stopSet && !fltSet && !dbdSet && !tripSet && !depNarrowed && !durNarrowed) return fetched;
    return fetched.filter(p => {
      if (stopSet && (p.stops === null || !stopSet.has(p.stops))) return false;
      if (fltSet && (!p.flt_num || !fltSet.has(p.flt_num))) return false;
      if (dbdSet && (p.dbd === null || !dbdSet.has(p.dbd))) return false;
      if (tripSet && (!p.trip_type || !tripSet.has(p.trip_type))) return false;
      if (depNarrowed) {
        // A fare with no departure time cannot be shown to satisfy a
        // narrowed window, so it drops out — and gets counted below rather
        // than disappearing quietly.
        const m = clockToMinutes(p.dep_time);
        if (m === null || m < depTime[0] || m > depTime[1]) return false;
      }
      if (durNarrowed) {
        if (p.duration_min === null) return false;
        if (p.duration_min < duration[0] || p.duration_min > duration[1]) return false;
      }
      return true;
    });
  }, [fetched, stops, fltNums, daysLeft, tripTypes, depTime, duration, depNarrowed, durNarrowed]);

  // Fares excluded purely because they carry no time to compare against —
  // a different thing from "outside the window you chose".
  const droppedUnknownTime = useMemo(() => {
    if (!depNarrowed && !durNarrowed) return 0;
    return fetched.filter(p =>
      (depNarrowed && clockToMinutes(p.dep_time) === null)
      || (durNarrowed && p.duration_min === null),
    ).length;
  }, [fetched, depNarrowed, durNarrowed]);

  // How many fares the Days Left filter cannot reach, stated rather than
  // silently dropped. See DAYS_LEFT_MAX for why the ceiling exists.
  const beyondDaysLeftRange = useMemo(() => {
    if (!daysLeft.length) return 0;
    return fetched.filter(p => p.dbd !== null && p.dbd > DAYS_LEFT_MAX).length;
  }, [fetched, daysLeft]);

  // A no-fare day carries no stops and no flight number, so it cannot honestly
  // satisfy either filter — any stops/flight selection hides the markers,
  // whether the server applied it (single value) or the client does (multi).
  const markersSuppressed = availabilitySuppressed || stops.length > 0 || fltNums.length > 0;

  const visibleNoFareDays = useMemo(() => {
    if (markersSuppressed || noFareDays.length === 0) return [];
    // Route and Days Left refine the markers the same way they refine the
    // points. The time filters do not: a marker is a whole-day statement with
    // no departure time to compare against, and the tooltip says so.
    const marketSet = new Set(routesKey.split(','));
    const dbdSet = daysLeft.length ? new Set(daysLeft) : null;
    return noFareDays.filter(d => marketSet.has(d.market) && (!dbdSet || dbdSet.has(d.dbd)));
  }, [noFareDays, markersSuppressed, routesKey, daysLeft]);

  // Pinned cards whose point is no longer drawn would annotate empty space.
  const visiblePinned = useMemo(() => {
    const live = new Set(points.map(pointKey));
    return pinned.filter(p => live.has(pointKey(p)));
  }, [pinned, points]);
  const hiddenPinnedCount = pinned.length - visiblePinned.length;

  // ── Series ──────────────────────────────────────────────────────────
  // The host carrier leads the legend; competitors follow alphabetically, so
  // the reading order is stable as routes change and colours stay put.
  const airlines = useMemo(() => {
    const reference = [...new Set(points.filter(p => p.role === 'reference').map(p => p.airline))];
    const competitors = [...new Set(points.filter(p => p.role === 'competitor').map(p => p.airline))].sort();
    return [...reference, ...competitors];
  }, [points]);

  const carrierTable = useCarrierColorTable();
  const colorMap = useMemo(() => buildAirlineColorMap(airlines, carrierTable), [airlines, carrierTable]);
  // Style index follows the ORDER THE USER SELECTED, so a route keeps its dash
  // pattern as other routes are added or removed around it.
  const markets = useMemo(
    () => effectiveRoutes.filter(m => points.some(p => p.market === m)),
    [effectiveRoutes, points], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const multiRoute = markets.length > 1;

  const option = useMemo<ChartOption>(() => {
    const ink = theme.palette.text.primary;
    const muted = theme.palette.text.secondary;
    const line = theme.palette.divider;

    // Brand ink, lightened in dark mode like the sidebar ink. Worn by the
    // zoom sliders (otherwise stock ECharts blue) and by the host carrier's
    // legend text below.
    const accent = brandInk(theme);
    const zoomSliderStyle = {
      fillerColor: alpha(BANNER_BG, 0.12),
      handleStyle: { color: accent, borderColor: accent },
      moveHandleStyle: { color: accent },
      emphasis: {
        handleStyle: { color: accent, borderColor: accent },
        moveHandleStyle: { color: accent },
      },
      selectedDataBackground: {
        lineStyle: { color: accent },
        areaStyle: { color: alpha(BANNER_BG, 0.2) },
      },
    };

    const series: Array<LineSeriesOption | ScatterSeriesOption> = [];
    for (const code of airlines) {
      for (const market of markets) {
        const data = points
          .filter(p => p.airline === code && p.market === market)
          .map(p => ({
            value: [`${p.dep_date}T00:00:00Z`, p.tot_fare] as [string, number],
            point: p,
          }));
        if (!data.length) continue;
        const style = ROUTE_STYLES[markets.indexOf(market) % ROUTE_STYLE_COUNT];
        series.push({
          // Airline alone when there is one route, so a single-route chart is
          // exactly as legible as it was before multi-route existed.
          name: multiRoute ? `${code} · ${market}` : code,
          type: 'line',
          // Several fares can share a departure date — that is real (different
          // flights, cabins and booking classes) and the line steps through
          // them rather than pretending there is one price per day.
          data,
          symbol: multiRoute ? style.symbol : 'circle',
          symbolSize: 6,
          showSymbol: true,
          lineStyle: { width: 1.5, color: colorMap[code], ...(multiRoute ? { type: style.dash } : {}) },
          itemStyle: { color: colorMap[code] },
          emphasis: { focus: 'series', scale: 1.6 },
          // The host carrier sits above its competitors where lines cross.
          z: points.some(p => p.airline === code && p.role === 'reference') ? 5 : 3,
        });
      }
    }

    // Availability markers ride the hidden second y-axis so the fare axis's
    // zoom and scale never move them. One datum per (date, class); the
    // airline/route list travels with it for the tooltip.
    const groups = new Map<string, NoFareGroup>();
    for (const d of visibleNoFareDays) {
      const key = `${d.status}|${d.dep_date}`;
      const g = groups.get(key);
      if (g) g.entries.push(d);
      else groups.set(key, { date: d.dep_date, status: d.status, entries: [d] });
    }
    const markerData = (status: NoFareDay['status']) =>
      [...groups.values()]
        .filter(g => g.status === status)
        .map(g => ({
          value: [`${g.date}T00:00:00Z`, status === 'sold_out' ? SOLD_OUT_Y : NOT_ON_SALE_Y] as [string, number],
          noFare: g,
        }));
    const soldOutData = markerData('sold_out');
    const notOnSaleData = markerData('not_on_sale');
    if (soldOutData.length) {
      series.push({
        name: AVAILABILITY_LABELS.sold_out,
        type: 'scatter',
        yAxisIndex: 1,
        data: soldOutData,
        symbol: 'triangle',
        symbolSize: 8,
        itemStyle: { color: theme.palette.warning.main },
        emphasis: { scale: 1.6 },
        // Above the fare lines — a marker hidden behind a line defeats itself.
        z: 6,
      });
    }
    if (notOnSaleData.length) {
      series.push({
        name: AVAILABILITY_LABELS.not_on_sale,
        type: 'scatter',
        yAxisIndex: 1,
        data: notOnSaleData,
        // Hollow, so "never went on sale" reads as an absence next to the
        // filled sold-out triangle.
        symbol: 'circle',
        symbolSize: 7,
        itemStyle: { color: 'transparent', borderColor: theme.palette.text.disabled, borderWidth: 1.5 },
        emphasis: { scale: 1.6 },
        z: 6,
      });
    }

    // Explicit legend entries so the host carrier's TEXT wears the brand red
    // too, not just its swatch. Every series name must be listed — an entry
    // missing from legend.data simply vanishes from the legend.
    const referenceCodes = new Set(
      airlines.filter(code => points.some(p => p.airline === code && p.role === 'reference')),
    );
    const legendData = series.map(s => {
      const name = String(s.name);
      const code = name.includes(' · ') ? name.slice(0, name.indexOf(' · ')) : name;
      return referenceCodes.has(code)
        ? { name, textStyle: { color: accent, fontWeight: 'bold' as const } }
        : name;
    });

    return {
      animation: false,
      backgroundColor: 'transparent',
      legend: {
        top: 4,
        type: 'scroll',
        data: legendData,
        textStyle: { color: ink, fontSize: 11 },
        inactiveColor: muted,
      },
      grid: { left: 56, right: 16, top: 34, bottom: 52, containLabel: true },
      tooltip: {
        trigger: 'item',
        confine: true,
        backgroundColor: theme.palette.background.paper,
        borderColor: line,
        textStyle: { color: ink, fontSize: 11 },
        // Hover stays a one-line read; the full detail is what clicking is for.
        formatter: (params: any) => {
          const nf: NoFareGroup | undefined = params.data?.noFare;
          if (nf) {
            const listed = nf.entries.slice(0, 8)
              .map(e => `${e.airline} (${e.market.replace('-', ' → ')})`);
            const rest = nf.entries.length - listed.length;
            return [
              `<b>${AVAILABILITY_LABELS[nf.status]}</b> — ${nf.date}`,
              nf.status === 'sold_out'
                ? 'Nothing left to buy this day on:'
                : 'Not yet open for booking this day on:',
              ...listed,
              ...(rest > 0 ? [`…and ${rest} more`] : []),
              '<i style="opacity:.7">whole-day status — time filters do not apply to it</i>',
            ].join('<br/>');
          }
          const p: PricePoint = params.data?.point;
          if (!p) return '';
          const clock = formatClock(p.dep_time);
          return [
            // The code wears its series colour, so WM reads brand red and
            // every carrier's tooltip echoes its line.
            `<b><span style="color:${colorMap[p.airline]}">${p.airline}</span></b> ${p.flt_num ?? ''}${multiRoute ? ` · ${p.market}` : ''}`,
            `${p.dep_date}${clock ? ` ${clock}` : ''}`,
            `<b>${p.tot_fare.toFixed(2)}</b> ${p.curr ?? ''}`,
            '<i style="opacity:.7">click to pin details</i>',
          ].join('<br/>');
        },
      },
      xAxis: {
        type: 'time',
        name: 'Departure date',
        nameLocation: 'middle',
        nameGap: 28,
        nameTextStyle: { color: muted, fontSize: 11 },
        axisLabel: { color: muted, fontSize: 10, hideOverlap: true },
        axisLine: { lineStyle: { color: line } },
        splitLine: { show: true, lineStyle: { color: line, opacity: 0.4 } },
      },
      yAxis: [
        {
          type: 'value',
          name: currency ? `Fare (${currency})` : 'Fare',
          nameLocation: 'middle',
          nameGap: 42,
          nameTextStyle: { color: muted, fontSize: 11 },
          axisLabel: { color: muted, fontSize: 10 },
          axisLine: { lineStyle: { color: line } },
          splitLine: { lineStyle: { color: line, opacity: 0.4 } },
          scale: true,
        },
        // Hidden 0–1 strip the availability markers plot on. The y dataZoom
        // below pins yAxisIndex 0, so zooming the fares leaves this axis —
        // and the markers — where they are.
        { type: 'value', show: false, min: 0, max: 1 },
      ],
      dataZoom: [
        // Drag inside the plot and a handle per axis. Wheel zoom is off on
        // purpose: this pane fills the page and hijacking the wheel would take
        // scrolling away from anyone using one.
        { type: 'inside', xAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: false, moveOnMouseWheel: false },
        { type: 'inside', yAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: false, moveOnMouseWheel: false },
        { type: 'slider', xAxisIndex: 0, bottom: 6, height: 16, filterMode: 'none', ...zoomSliderStyle },
        { type: 'slider', yAxisIndex: 0, left: 4, width: 14, filterMode: 'none', ...zoomSliderStyle },
      ],
      series,
    };
  }, [airlines, markets, multiRoute, colorMap, points, visibleNoFareDays, currency, theme]);

  // ── Chart lifecycle ─────────────────────────────────────────────────
  // Initialised on first activation, because ECharts binding to a display:none
  // host measures 0x0, caches it and warns. Disposal is a SEPARATE effect
  // keyed on mount: tying it to `active` tore the instance down every time the
  // user visited a Superset section, losing all zoom and legend state while
  // the pinned cards — plain React state — survived. Cards floating over a
  // chart snapped back to full range is worse than losing both.
  const observerRef = useRef<ResizeObserver | null>(null);

  useEffect(() => {
    if (!active || chartRef.current || !hostRef.current) return;
    const chart = echarts.init(hostRef.current, undefined, { renderer: 'canvas' });
    chartRef.current = chart;

    chart.on('click', (params: any) => {
      // Marker datums carry .noFare, not .point — a no-fare day has no fare detail to pin.
      const p: PricePoint | undefined = params.data?.point;
      if (!p) return;
      // Functional update, so the handler never closes over a stale list and
      // can be bound once for the life of the instance.
      setPinned(prev =>
        prev.some(existing => pointKey(existing) === pointKey(p)) ? prev : [...prev, p],
      );
    });

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(hostRef.current);
    observerRef.current = observer;

    setReady(true);
  }, [active]);

  useEffect(() => () => {
    observerRef.current?.disconnect();
    chartRef.current?.dispose();
    chartRef.current = null;
  }, []);

  useEffect(() => {
    if (!ready) return;
    // notMerge, so a selection with fewer series than the last does not keep
    // the previous one's lines hanging around.
    chartRef.current?.setOption(option as echarts.EChartsCoreOption, true);
  }, [option, ready]);

  // Returning from a Superset section, the host was last laid out at
  // display:none; ECharts holds that stale size until told to measure again.
  useEffect(() => {
    if (active && ready) chartRef.current?.resize();
  }, [active, ready, points]);

  // ── Render ──────────────────────────────────────────────────────────
  const hasRoutes = effectiveRoutes.length > 0;
  const showChart = hasRoutes && !loading && !error && points.length > 0;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flexGrow: 1, minHeight: 0 }}>
      {/* Context strip — what the chart is currently showing. */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 0.5, pt: 0.5 }}>
        <Typography sx={{ fontSize: 12.5, fontWeight: 600 }}>Latest Prices</Typography>
        {/* Routes, plus the capture day when the header names a range. In
            single mode the header chip already states the day exactly; the
            airline count is readable from the legend, and the explanation of
            the default belonged in a tooltip rather than across the chart. */}
        {markets.map(m => (
          <Tooltip
            key={m}
            title={defaultRoute
              ? 'No route selected — showing the first one. Pick Route (O&D) above to change or add routes.'
              : ''}
          >
            <Chip
              size="small"
              label={m.replace('-', ' → ')}
              // Outlined for a route the user did not choose, so a default
              // never reads as a selection.
              variant={defaultRoute ? 'outlined' : 'filled'}
              sx={{ height: 20, fontSize: 11 }}
            />
          </Tooltip>
        ))}
        {showCapDate && capDate && (
          <Tooltip title="The capture day the plotted fares come from — the newest one inside the selected date range. This chart shows one capture at a time.">
            <Chip
              size="small"
              variant="outlined"
              icon={<EventAvailable sx={{ fontSize: 14 }} />}
              label={`capture ${capDate}`}
              sx={{ height: 20, fontSize: 11 }}
            />
          </Tooltip>
        )}
        <Box sx={{ flexGrow: 1 }} />
        {visiblePinned.length > 0 && (
          <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>
            {visiblePinned.length} card{visiblePinned.length > 1 ? 's' : ''} pinned
          </Typography>
        )}
      </Box>

      {droppedUnknownTime > 0 && (
        <Alert severity="info" sx={{ mb: 0.5, py: 0, fontSize: 11.5 }}>
          {droppedUnknownTime} fare{droppedUnknownTime > 1 ? 's carry' : ' carries'} no departure
          time, so {droppedUnknownTime > 1 ? 'they cannot' : 'it cannot'} be matched against the
          time filters and {droppedUnknownTime > 1 ? 'are' : 'is'} not shown.
        </Alert>
      )}
      {truncatedRoutes.length > 0 && (
        <Alert severity="warning" sx={{ mb: 0.5, py: 0, fontSize: 11.5 }}>
          More fares than the chart will draw on {truncatedRoutes.join(', ')} — some points are not shown.
        </Alert>
      )}
      {beyondDaysLeftRange > 0 && (
        <Alert severity="info" sx={{ mb: 0.5, py: 0, fontSize: 11.5 }}>
          Days Left only covers 0–{DAYS_LEFT_MAX} days; {beyondDaysLeftRange} fares departing further
          out cannot be matched by it and are not shown.
        </Alert>
      )}
      {markersSuppressed && (noFareDays.length > 0 || availabilitySuppressed) && (
        <Alert severity="info" sx={{ mb: 0.5, py: 0, fontSize: 11.5 }}>
          Sold-out / not-on-sale markers are hidden while a Stops or Flight Number filter is
          active — a day with no fare has no stops or flight number to match against them.
        </Alert>
      )}
      {markets.length > ROUTE_STYLE_COUNT && (
        <Alert severity="info" sx={{ mb: 0.5, py: 0, fontSize: 11.5 }}>
          Line styles repeat after {ROUTE_STYLE_COUNT} routes — colour still identifies the airline.
        </Alert>
      )}
      {hiddenPinnedCount > 0 && (
        <Alert severity="info" sx={{ mb: 0.5, py: 0, fontSize: 11.5 }}>
          {hiddenPinnedCount} pinned card{hiddenPinnedCount > 1 ? 's are' : ' is'} hidden — those
          fares are filtered out of the current view.
        </Alert>
      )}
      {error && (
        <Alert severity="error" sx={{ mb: 0.5, py: 0, fontSize: 11.5 }}>{error}</Alert>
      )}

      <Box sx={{ position: 'relative', flexGrow: 1, minHeight: 0 }}>
        {/* The canvas host is always mounted: ECharts binds to this element
            once, and swapping it out for an empty state would dispose the
            instance on every route change. */}
        <Box ref={hostRef} sx={{ position: 'absolute', inset: 0, visibility: showChart ? 'visible' : 'hidden' }} />

        {/* Only reachable when the dashboard offers no routes at all — with
            any route list the panel falls back to the first one instead. */}
        {!hasRoutes && !loading && !noCaptureInRange && (
          <Box sx={{ position: 'absolute', inset: 0, overflowY: 'auto' }}>
            <EmptyState
              icon={<TravelExplore sx={{ fontSize: 56 }} />}
              title="No routes available"
              description="This dashboard is not offering any Route (O&D) values, so there is nothing to plot. That usually means the capture date holds no data for this airline."
            />
          </Box>
        )}
        {hasRoutes && loading && (
          <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <CircularProgress size={28} sx={{ color: brandInk }} />
          </Box>
        )}
        {noCaptureInRange && !loading && (
          <Box sx={{ position: 'absolute', inset: 0, overflowY: 'auto' }}>
            <EmptyState
              icon={<EventBusy sx={{ fontSize: 56 }} />}
              title="No captures in the selected date range"
              description="Data was not captured on any day inside the selected range, so there are no latest prices to plot. Widen or move the range — single-day mode in the Cap date picker lists the days that hold data."
            />
          </Box>
        )}
        {hasRoutes && !loading && !error && !noCaptureInRange && points.length === 0 && (
          <Box sx={{ position: 'absolute', inset: 0, overflowY: 'auto' }}>
            <EmptyState
              title="No fares match the current filters"
              description="Nothing was observed for these routes on the selected capture date, or the other filters have excluded everything. Try widening them."
            />
          </Box>
        )}

        {/* Pinned cards float over the plot and scroll horizontally once more
            are open than fit. pointerEvents is released on the rail itself so
            the chart underneath stays usable in the gaps between cards. */}
        {visiblePinned.length > 0 && (
          <Box
            sx={{
              position: 'absolute',
              top: 28,
              right: 8,
              left: 72,
              display: 'flex',
              justifyContent: 'flex-end',
              gap: 1,
              overflowX: 'auto',
              pb: 1,
              pointerEvents: 'none',
              '& > *': { pointerEvents: 'auto' },
            }}
          >
            {visiblePinned.map(p => (
              <PriceDetailCard
                key={pointKey(p)}
                point={p}
                color={colorMap[p.airline] ?? brandInk(theme)}
                currency={currency}
                showMarket={multiRoute}
                onClose={() => setPinned(prev => prev.filter(x => pointKey(x) !== pointKey(p)))}
              />
            ))}
          </Box>
        )}
      </Box>
    </Box>
  );
}
