/**
 * Series colours for the WinAir Latest Prices chart.
 *
 * These are the same hexes the WinAir Superset charts use (see
 * scripts/superset_provision_winair.py), so the native chart and the
 * embedded dashboard above it agree on what colour each airline is. An
 * airline that changed colour between the two panes would read as two
 * different carriers.
 *
 * WM is deliberately first and the most saturated: on this dashboard it is
 * always the host carrier, and the whole point of the chart is comparing
 * everyone else against it.
 */

/** Airlines with a colour fixed by the Superset provisioning script. */
const KNOWN_AIRLINE_COLORS: Record<string, string> = {
  WM: '#C5981B',
  '5L': '#2B6B2B',
  BW: '#D4652F',
  Exp: '#8B5CF6',
  Expedia: '#8B5CF6',
  JY: '#1A6B8A',
  S6: '#E4049C',
};

/**
 * Fallbacks for carriers the provisioning script never named — 7Z and DM
 * both appear in WinAir's live data. Assigned by first appearance rather
 * than hashing the code, so a route's legend reads in a stable order and
 * two carriers can never collide on the same colour within one chart.
 */
const FALLBACK_COLORS = [
  '#64748B',
  '#0070C0',
  '#B45309',
  '#0F766E',
  '#7C3AED',
  '#BE123C',
];

/**
 * Build a code → colour map for exactly the airlines present.
 *
 * `airlines` should already be in the order you want the legend to read;
 * fallbacks are handed out in that order.
 */
export function buildAirlineColorMap(airlines: string[]): Record<string, string> {
  const map: Record<string, string> = {};
  let nextFallback = 0;
  for (const code of airlines) {
    const known = KNOWN_AIRLINE_COLORS[code];
    if (known) {
      map[code] = known;
    } else {
      map[code] = FALLBACK_COLORS[nextFallback % FALLBACK_COLORS.length];
      nextFallback += 1;
    }
  }
  return map;
}

/**
 * Line style + marker per ROUTE, when more than one is plotted.
 *
 * Colour already means airline and must keep meaning only that — the chart
 * sits beside Superset charts that colour the same carriers the same way. So
 * route needs a second, orthogonal channel: dash pattern for the line, shape
 * for the marker. Both are readable in monochrome and to colour-blind
 * viewers, which colour alone is not.
 *
 * Five entries. Beyond that the styles repeat and the chart says so rather
 * than silently drawing two routes identically.
 */
export const ROUTE_STYLES: Array<{ dash: 'solid' | 'dashed' | 'dotted' | number[]; symbol: string }> = [
  { dash: 'solid', symbol: 'circle' },
  { dash: 'dashed', symbol: 'triangle' },
  { dash: 'dotted', symbol: 'diamond' },
  { dash: [7, 3, 2, 3], symbol: 'roundRect' },
  { dash: [11, 4], symbol: 'arrow' },
];

/** How many distinct route styles exist before they start repeating. */
export const ROUTE_STYLE_COUNT = ROUTE_STYLES.length;

/**
 * Upper bound of the dashboard's "Days Left" filter.
 *
 * That filter targets `days_left` on the velocity dataset, which only ever
 * reaches 45. The pricing side measures days-before-departure independently
 * (`dep_date - cap_date`) and reaches 85, with about a third of WinAir's rows
 * beyond 45. The two are different columns from different datasets that merely
 * share a unit — so applying the filter here has a ceiling the user has to be
 * told about, rather than silently dropping a third of the fares.
 */
export const DAYS_LEFT_MAX = 45;

/** Two-letter day label used in the card's "Departing" line, e.g. "Th". */
const DAY_LABELS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];

/**
 * "30-07-2026 (Th) 07:50" — the departure line on a price card.
 *
 * `time` is a feed clock string and may be absent or in either of the two
 * shapes the feeds use, so it is normalised rather than trusted. The date
 * is parsed as UTC: dep_date is a calendar date with no zone, and letting
 * the browser's local offset shift it would move a late-evening departure
 * onto the wrong day.
 */
export function formatDeparture(depDate: string, time: string | null): string {
  const parsed = new Date(`${depDate}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return depDate;
  const dd = String(parsed.getUTCDate()).padStart(2, '0');
  const mm = String(parsed.getUTCMonth() + 1).padStart(2, '0');
  const yyyy = parsed.getUTCFullYear();
  const day = DAY_LABELS[parsed.getUTCDay()];
  const clock = formatClock(time);
  return `${dd}-${mm}-${yyyy} (${day})${clock ? ` ${clock}` : ''}`;
}

/**
 * Normalise a feed clock string to "HH:MM".
 *
 * WinAir sends "HH:MM", JY and PW send "HHMM". Anything that is not four
 * digits after stripping the colon is returned as-is rather than reshaped
 * into something that looks authoritative but isn't.
 */
export function formatClock(value: string | null): string {
  if (!value) return '';
  const raw = value.trim().replace(':', '');
  if (raw.length !== 4 || !/^\d{4}$/.test(raw)) return value.trim();
  return `${raw.slice(0, 2)}:${raw.slice(2)}`;
}

/** "00:45" from 45 minutes. */
export function formatDuration(minutes: number | null): string {
  if (minutes === null || minutes < 0) return '';
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`;
}

/** Minutes past midnight from a feed clock string, or null. Mirrors the API's parser. */
export function clockToMinutes(value: string | null): number | null {
  if (!value) return null;
  const raw = value.trim().replace(':', '');
  if (raw.length !== 4 || !/^\d{4}$/.test(raw)) return null;
  const hours = Number(raw.slice(0, 2));
  const mins = Number(raw.slice(2));
  if (hours > 23 || mins > 59) return null;
  return hours * 60 + mins;
}

/** Departure-time slider bounds, in minutes past midnight. A full day. */
export const DEP_TIME_MIN = 0;
export const DEP_TIME_MAX = 1439;

/**
 * Duration slider bounds, in minutes.
 *
 * Capped at 24h because that is genuinely the ceiling of what the data can
 * express, not a UI choice: arrival is stored as a clock time with no date, so
 * a journey crossing midnight is read as wrapping into the same day. Measured
 * on WinAir's live data, the longest derivable duration is exactly 23:59 —
 * the wrap ceiling. Offering a 36-hour range would imply we can tell a 30-hour
 * itinerary from a 6-hour one; we cannot.
 */
export const DURATION_MIN = 0;
export const DURATION_MAX = 1440;

/** "6 days ago" / "today" / "yesterday", from a capture date. */
export function formatSeen(capDate: string): string {
  const captured = new Date(`${capDate}T00:00:00Z`);
  if (Number.isNaN(captured.getTime())) return capDate;
  const today = new Date();
  const todayUtc = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const days = Math.round((todayUtc - captured.getTime()) / 86_400_000);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  return `${days} days ago`;
}
