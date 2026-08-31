/**
 * Turning an alert's structured payload into the line under the headline.
 *
 * The message the backend writes is already a complete sentence; this adds the
 * supporting detail a revenue manager scans for — which departure window, what
 * the numbers were, how many competitors were actually in the comparison.
 */
import type { AlertEvent, AlertPayload } from '../types';

/** "2h ago", "3d ago". Absolute date once it stops being useful as elapsed. */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const mins = Math.floor((Date.now() - then) / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

/** Departure window as prose: "0-7 days out". */
export function windowLabel(window?: string): string {
  if (!window) return '';
  const [from, to] = window.split('-');
  return `${Number(from)}-${Number(to)} days out`;
}

export function money(value?: number | null, currency?: string | null): string {
  if (value === undefined || value === null) return '';
  const n = value.toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  return currency ? `${currency} ${n}` : n;
}

/** "nonstop", "1 stop", "2 stops". */
export function stopsLabel(n?: number | null): string {
  if (n === undefined || n === null) return '';
  return n === 0 ? 'nonstop' : `${n} stop${n === 1 ? '' : 's'}`;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/**
 * Split an ISO date BY STRING, never with `new Date`.
 *
 * 'YYYY-MM-DD' parses as UTC midnight, so `toLocaleDateString` renders the
 * PREVIOUS day for every viewer west of Greenwich — which is every user of
 * these rules. These are departure dates: naming the wrong flight day is not a
 * cosmetic bug. The rest of this module avoids Date for the same reason.
 */
function parts(iso: string): [number, number, number] | null {
  const p = iso.split('-').map(Number);
  return p.length === 3 && !p.some(Number.isNaN)
    ? [p[0], p[1], p[2]] as [number, number, number]
    : null;
}

/**
 * "27-28, 30-31 Aug +2 more days" — consecutive departure days folded.
 *
 * A gap is almost never scattered days; it is "we do not fly Tuesdays and
 * Thursdays". Folding makes that pattern visible where a flat list buries it,
 * and keeps the caption bounded however long the list is.
 */
export function gapDatesLabel(dates?: string[], maxGroups = 3): string {
  if (!dates?.length) return '';
  const parsed = dates.map(parts).filter(Boolean) as [number, number, number][];
  if (!parsed.length) return '';
  parsed.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);

  const dayNum = ([y, m, d]: number[]) => Date.UTC(y, m - 1, d) / 86_400_000;
  const runs: [number, number, number][][] = [[parsed[0]]];
  for (let i = 1; i < parsed.length; i++) {
    const run = runs[runs.length - 1];
    if (dayNum(parsed[i]) === dayNum(run[run.length - 1]) + 1) run.push(parsed[i]);
    else runs.push([parsed[i]]);
  }

  const shown = runs.slice(0, maxGroups);
  const hidden = runs.slice(maxGroups).reduce((n, r) => n + r.length, 0);
  const label = shown.map(run => {
    const a = run[0];
    const b = run[run.length - 1];
    if (a[1] === b[1]) {
      return run.length === 1
        ? `${a[2]} ${MONTHS[a[1] - 1]}`
        : `${a[2]}-${b[2]} ${MONTHS[a[1] - 1]}`;
    }
    return `${a[2]} ${MONTHS[a[1] - 1]} - ${b[2]} ${MONTHS[b[1] - 1]}`;
  }).join(', ');

  return hidden > 0 ? `${label} +${hidden} more day${hidden === 1 ? '' : 's'}` : label;
}

/** Every gap date spelled out, for the row's hover title. */
export function gapDatesFull(dates?: string[]): string {
  if (!dates?.length) return '';
  return dates.map(iso => {
    const p = parts(iso);
    return p ? `${p[2]} ${MONTHS[p[1] - 1]}` : iso;
  }).join(', ');
}

/**
 * The detail line. Returns the pieces so the row can style them; joining with
 * " · " is the caller's business.
 */
export function detailParts(event: AlertEvent): string[] {
  const p: AlertPayload = event.payload ?? {};
  const parts: string[] = [];

  if (p.route) parts.push(p.route);
  if (p.competitor) parts.push(p.competitor);
  if (p.window) parts.push(windowLabel(p.window));

  if (p.prev_value !== undefined && p.current_value !== undefined) {
    parts.push(`${money(p.prev_value, p.currency)} → ${money(p.current_value, p.currency)}`);
  }
  if (p.delta_pct !== undefined) {
    const sign = p.delta_pct > 0 ? '+' : '';
    parts.push(`${sign}${p.delta_pct.toFixed(1)}%`);
  }

  if (p.da_rank !== undefined) {
    // competitor_count is the number of RIVALS, so the field is that plus us.
    // Six of DreamAir's twelve routes carry exactly one competitor, and saying
    // "rank 2 of 2" is honest where "rank 2" alone implies a real field.
    const field = (p.competitor_count ?? 0) + 1;
    parts.push(`rank ${p.da_rank} of ${field}`);
  }
  if (p.best_competitor && p.best_competitor_fare !== undefined) {
    parts.push(`best ${p.best_competitor} ${money(p.best_competitor_fare, p.currency)}`);
  }

  // stops_disadvantage. Ours first, theirs second — the same order the position
  // rule's "rank 2 of 3" reads in.
  if (p.own_stops !== undefined && p.best_comp_stops !== undefined) {
    parts.push(`ours ${stopsLabel(p.own_stops)}, best ${stopsLabel(p.best_comp_stops)}`);
  }
  if (p.days_behind !== undefined && p.days_comparable !== undefined) {
    parts.push(`on ${p.days_behind} of ${p.days_comparable} days`);
  }

  // service_gap. The denominator is not optional: 3 of 8 is a schedule hole,
  // 3 of 3 is barely any data. The date list is FOLDED, never listed — the
  // compact popover row is nowrap, so raw dates push the route off the end.
  if (p.gap_days !== undefined && p.days_observed !== undefined) {
    parts.push(`${p.gap_days} of ${p.days_observed} departure days`);
    const dates = gapDatesLabel(p.gap_dates);
    if (dates) parts.push(dates);
  }
  if (p.competitors_on_sale) {
    parts.push(`${p.competitors_on_sale} competitor${p.competitors_on_sale === 1 ? '' : 's'} selling`);
  }

  return parts;
}

/**
 * How the event was produced, when that is worth saying.
 *
 * Backfilled events are real facts computed retroactively from real captures,
 * and the UI says so rather than passing them off as observed live.
 */
export function provenanceLabel(event: AlertEvent): string | null {
  if (event.evaluation_mode === 'backfill') return 'from history';
  if (event.evaluation_mode === 'manual') return 'manual run';
  return null;
}

/** "compared 2026-08-10 → 2026-08-12" — what the evaluator actually used. */
export function comparisonLabel(event: AlertEvent): string | null {
  if (!event.observed_at) return null;
  if (!event.prev_observed_at) return `captured ${event.observed_at}`;
  return `${event.prev_observed_at} → ${event.observed_at}`;
}
