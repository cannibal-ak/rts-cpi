import { useEffect, useState } from 'react';
import {
  Box, Typography, IconButton, Collapse, Tooltip, CircularProgress,
} from '@mui/material';
import { Close, ExpandLess, ExpandMore, ShowChart, FlightTakeoff } from '@mui/icons-material';
import { api } from '../../../api';
import type { PricePoint, PriceHistoryPoint } from '../../../api/client';
import { formatClock, formatDeparture, formatDuration, formatSeen } from './priceChartTheme';
import { brandInk } from '../bannerTheme';

interface PriceDetailCardProps {
  point: PricePoint;
  /** Series colour, so a card is visually tied to the dot it came from. */
  color: string;
  currency: string | null;
  /** Name the market when more than one route is plotted. */
  showMarket?: boolean;
  onClose: () => void;
}

/** One label/value line. Values that are absent render an em-dash, never a zero. */
function DetailRow({ label, value, tint }: { label: string; value: string; tint?: boolean }) {
  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        gap: 1,
        px: 1,
        py: 0.4,
        // Alternating tint, as in the reference card — it keeps a long
        // label/value list scannable without drawing rules between rows.
        bgcolor: tint ? 'action.hover' : 'transparent',
      }}
    >
      <Typography sx={{ fontSize: 11.5, color: 'text.secondary', whiteSpace: 'nowrap' }}>
        {label}
      </Typography>
      <Typography
        sx={{
          fontSize: 11.5,
          fontWeight: 500,
          color: 'text.primary',
          textAlign: 'right',
          fontVariantNumeric: 'tabular-nums',
          wordBreak: 'break-word',
        }}
      >
        {value || '—'}
      </Typography>
    </Box>
  );
}

/** Money, to 2dp, grouped. The currency lives in the section header, not per row. */
function money(value: number): string {
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/**
 * Fare history as a bare inline SVG rather than a second charting instance.
 *
 * One ECharts instance per open card would be several instances competing
 * for canvases and resize observers to draw a dozen points. A polyline is
 * enough for a trend read; the numbers beneath it carry the precision.
 */
function Sparkline({ points, color }: { points: PriceHistoryPoint[]; color: string }) {
  if (points.length < 2) {
    return (
      <Typography sx={{ fontSize: 11, color: 'text.secondary', px: 1, py: 0.5 }}>
        {points.length === 1
          ? 'Only one capture holds this flight — no trend to draw yet.'
          : 'No earlier captures hold this flight.'}
      </Typography>
    );
  }

  const width = 232;
  const height = 40;
  const fares = points.map(p => p.tot_fare);
  const min = Math.min(...fares);
  const max = Math.max(...fares);
  // A flat series would divide by zero; pin it to the middle of the band.
  const span = max - min || 1;
  const coords = points.map((p, i) => {
    const x = (i / (points.length - 1)) * (width - 4) + 2;
    const y = height - 4 - ((p.tot_fare - min) / span) * (height - 8);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const first = points[0];
  const last = points[points.length - 1];
  const delta = last.tot_fare - first.tot_fare;

  return (
    <Box sx={{ px: 1, pt: 0.5, pb: 0.75 }}>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <polyline
          points={coords.join(' ')}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {coords.map((c, i) => {
          const [cx, cy] = c.split(',');
          return <circle key={i} cx={cx} cy={cy} r={2} fill={color} />;
        })}
      </svg>
      <Typography sx={{ fontSize: 10.5, color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}>
        {money(first.tot_fare)} → {money(last.tot_fare)}
        {delta !== 0 && (
          <Box
            component="span"
            sx={{ ml: 0.5, color: delta > 0 ? 'error.main' : 'success.main', fontWeight: 600 }}
          >
            ({delta > 0 ? '+' : ''}{money(delta)})
          </Box>
        )}
        <Box component="span" sx={{ ml: 0.5 }}>
          across {points.length} captures
        </Box>
      </Typography>
    </Box>
  );
}

/**
 * The full detail behind one plotted fare.
 *
 * Cards are pinned by clicking a point and stay open until dismissed, so
 * several can sit side by side for comparison — which is the reason this is
 * a card and not a tooltip. Everything shown comes from the point itself;
 * only the fare history is fetched, and only when asked for.
 */
export default function PriceDetailCard({
  point, color, currency, showMarket, onClose,
}: PriceDetailCardProps) {
  const [expanded, setExpanded] = useState(true);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<PriceHistoryPoint[] | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  useEffect(() => {
    if (!showHistory || history !== null || historyLoading) return;
    let cancelled = false;
    setHistoryLoading(true);
    setHistoryError(null);
    api.airline
      .getPriceHistory({
        origin: point.origin,
        destination: point.destination,
        airline: point.airline,
        dep_date: point.dep_date,
        ...(point.flt_num ? { flt_num: point.flt_num } : {}),
      })
      .then(res => { if (!cancelled) setHistory(res.points); })
      .catch(err => {
        if (cancelled) return;
        console.error('[LatestPrices] price history failed:', err);
        setHistoryError(err?.message ?? 'could not load history');
      })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [showHistory, history, historyLoading, point]);

  // Surcharges are folded into one line so Base + Tax + Surcharges always
  // reconciles to Total. Splitting YQ and YR out would be four rows that
  // only a revenue analyst reads, and they are zero on most fares.
  const surcharges = point.yq + point.yr;
  const stopsLabel =
    point.stops === null ? '' : point.stops === 0 ? 'Nonstop' : `${point.stops} stop${point.stops > 1 ? 's' : ''}`;

  // 9 is the ingest's stand-in for "the feed sent no seat count" — it is not
  // an availability of nine. Showing it would invent a number, so the row is
  // dropped instead. A genuine 9 is hidden too; that is the cost of the feed
  // not distinguishing the two.
  const seatsLabel = point.seats === null || point.seats === 9 ? '' : String(point.seats);

  return (
    <Box
      sx={{
        width: 264,
        flexShrink: 0,
        borderRadius: '12px',
        border: 1,
        borderColor: 'divider',
        bgcolor: 'background.paper',
        boxShadow: 4,
        overflow: 'hidden',
        // The series colour reads down the left edge, tying the card to its dot.
        borderLeft: '4px solid',
        borderLeftColor: color,
      }}
    >
      {/* Header — airline, and the two controls */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          px: 1,
          py: 0.5,
          bgcolor: 'action.hover',
        }}
      >
        <FlightTakeoff sx={{ fontSize: 15, color }} />
        {/* The host carrier's code wears its series colour (brand red);
            competitor codes stay theme ink. */}
        <Typography
          sx={{
            fontSize: 12.5,
            fontWeight: 700,
            flexGrow: 1,
            ...(point.role === 'reference' && { color }),
          }}
        >
          {point.airline}
          {point.role === 'reference' && (
            <Box component="span" sx={{ ml: 0.5, fontSize: 10, fontWeight: 500, color: 'text.secondary' }}>
              (you)
            </Box>
          )}
        </Typography>
        <Tooltip title={expanded ? 'Collapse' : 'Expand'}>
          <IconButton size="small" onClick={() => setExpanded(v => !v)} sx={{ p: 0.25 }}>
            {expanded ? <ExpandLess sx={{ fontSize: 16 }} /> : <ExpandMore sx={{ fontSize: 16 }} />}
          </IconButton>
        </Tooltip>
        <Tooltip title="Close">
          <IconButton size="small" onClick={onClose} sx={{ p: 0.25 }} aria-label={`Close ${point.airline} details`}>
            <Close sx={{ fontSize: 16 }} />
          </IconButton>
        </Tooltip>
      </Box>

      <Collapse in={expanded}>
        <Typography
          sx={{ fontSize: 11, fontWeight: 600, color: 'text.secondary', px: 1, pt: 0.75, pb: 0.25 }}
        >
          Outbound Sector
        </Typography>
        <Typography sx={{ fontSize: 13, fontWeight: 600, px: 1, pb: 0.5 }}>
          {point.origin} › {point.destination}
          {/* A competitor's own stations can differ from the market it was
              compared in, so name the market when several are plotted and
              this card could otherwise be attributed to the wrong line. */}
          {showMarket && point.market !== `${point.origin}-${point.destination}` && (
            <Box component="span" sx={{ ml: 0.75, fontSize: 10.5, fontWeight: 500, color: 'text.secondary' }}>
              in {point.market.replace('-', ' › ')}
            </Box>
          )}
        </Typography>

        <DetailRow label="Departing" value={formatDeparture(point.dep_date, point.dep_time)} tint />
        <DetailRow label="Arriving" value={formatClock(point.arr_time)} />
        <DetailRow label="Duration" value={formatDuration(point.duration_min)} tint />
        <DetailRow label="Flight Number" value={point.flt_num ?? ''} />
        <DetailRow label="Stops" value={point.via ? `${stopsLabel} via ${point.via}` : stopsLabel} tint />
        <DetailRow label="Cabin" value={point.cab_name || point.cab_code || ''} />
        {/* WinAir carries no fare-family code; its branded fare name arrives
            in the booking-class column instead. Preferring ff_code keeps
            this correct for tenants that do send one. */}
        <DetailRow label="Fare Family" value={point.ff_code || point.bkg_class || ''} tint />
        <DetailRow label="Aircraft" value={point.equip_code ?? ''} />
        {seatsLabel && <DetailRow label="Seats" value={seatsLabel} tint />}

        {/* Price block */}
        <Box sx={{ borderTop: 1, borderColor: 'divider', mt: 0.5, pt: 0.5 }}>
          <Typography sx={{ fontSize: 11, fontWeight: 600, color: 'text.secondary', px: 1, pb: 0.25 }}>
            Outbound Price {(point.curr || currency) && `(${point.curr || currency})`}
          </Typography>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', px: 1 }}>
            <Typography sx={{ fontSize: 11.5, color: 'text.secondary' }}>Total</Typography>
            <Typography sx={{ fontSize: 18, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
              {money(point.tot_fare)}
            </Typography>
          </Box>
          <DetailRow label="Base" value={money(point.base_fare)} />
          <DetailRow label="Tax" value={money(point.tax)} tint />
          {surcharges > 0 && <DetailRow label="Surcharges" value={money(surcharges)} />}
        </Box>

        {/* Footer — provenance and the history toggle */}
        <Box
          sx={{
            borderTop: 1,
            borderColor: 'divider',
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            px: 1,
            py: 0.4,
          }}
        >
          <Typography sx={{ fontSize: 10.5, color: 'text.secondary', flexGrow: 1 }}>
            Seen: {formatSeen(point.cap_date)}
            {point.dbd !== null && ` (${point.dbd} DBD)`}
          </Typography>
          <Tooltip title={showHistory ? 'Hide fare history' : 'Show fare history'}>
            <IconButton
              size="small"
              onClick={() => setShowHistory(v => !v)}
              sx={{ p: 0.25, color: showHistory ? color : 'text.secondary' }}
              aria-label="Toggle fare history"
            >
              <ShowChart sx={{ fontSize: 15 }} />
            </IconButton>
          </Tooltip>
        </Box>

        <Collapse in={showHistory}>
          {historyLoading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 1 }}>
              <CircularProgress size={16} sx={{ color: brandInk }} />
            </Box>
          )}
          {historyError && (
            <Typography sx={{ fontSize: 10.5, color: 'error.main', px: 1, py: 0.5 }}>
              {historyError}
            </Typography>
          )}
          {history && !historyLoading && <Sparkline points={history} color={color} />}
        </Collapse>
      </Collapse>
    </Box>
  );
}
