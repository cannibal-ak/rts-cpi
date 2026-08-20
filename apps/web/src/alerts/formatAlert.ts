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

/** Departure window as prose: "0–7 days out". */
export function windowLabel(window?: string): string {
  if (!window) return '';
  const [from, to] = window.split('-');
  return `${Number(from)}–${Number(to)} days out`;
}

export function money(value?: number | null, currency?: string | null): string {
  if (value === undefined || value === null) return '';
  const n = value.toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
  return currency ? `${currency} ${n}` : n;
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
