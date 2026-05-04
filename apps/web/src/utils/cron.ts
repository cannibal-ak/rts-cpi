/**
 * Numeric-only cron-expression validator (v1).
 *
 * Backs the IngestionSchedulesPage's create/edit form. Catches the
 * common typos client-side so users don't round-trip a 422 for
 * "70 0 * * *". The server (celery.schedules.crontab) is the
 * authoritative validator — anything more exotic (named months,
 * named days, ``L``/``W``/``#`` extensions) we let the server
 * reject via 422.
 *
 * Grammar accepted per field:
 *   *
 *   integer in range
 *   range:  a-b   (a < b, both in range)
 *   list:   a,b,c (each item itself a *, integer, range, or step)
 *   step:   * /n   or   a-b/n   (n > 0)
 *
 * Field ranges:
 *   minute        0-59
 *   hour          0-23
 *   day-of-month  1-31
 *   month         1-12
 *   day-of-week   0-6   (0 = Sunday)
 *
 * Examples:
 *   "0 3 * * *"      → valid, description "Daily at 03:00"
 *   "*\/15 * * * *"  → valid, no description
 *   "30 4 * * 1"     → valid, no description (day-of-week not all-stars)
 *   "70 0 * * *"     → invalid (minute 70 > 59)
 *   "0 3 * *"        → invalid (4 fields)
 *   "a b c d e"      → invalid (non-numeric tokens)
 *
 * Phase 5 may swap this for cron-parser if a friendlier
 * description-of-arbitrary-cron is needed; for v1 the description
 * surface is intentionally minimal.
 */

export interface CronValidationResult {
  valid: boolean;
  error?: string;
  description?: string;
}


interface FieldSpec {
  name: string;
  min: number;
  max: number;
}

const FIELDS: FieldSpec[] = [
  { name: 'minute', min: 0, max: 59 },
  { name: 'hour', min: 0, max: 23 },
  { name: 'day-of-month', min: 1, max: 31 },
  { name: 'month', min: 1, max: 12 },
  { name: 'day-of-week', min: 0, max: 6 },
];


function parseInteger(token: string): number | null {
  if (!/^\d+$/.test(token)) return null;
  const n = Number(token);
  return Number.isFinite(n) ? n : null;
}


function validateAtom(atom: string, spec: FieldSpec): string | null {
  // Returns null on success, or an error string.
  if (atom === '*') return null;

  // Step:  * /n  or  a-b/n
  const stepIdx = atom.indexOf('/');
  if (stepIdx !== -1) {
    const head = atom.slice(0, stepIdx);
    const stepStr = atom.slice(stepIdx + 1);
    const stepNum = parseInteger(stepStr);
    if (stepNum === null || stepNum <= 0) {
      return `step ('${atom}') must be a positive integer after '/'`;
    }
    if (head === '*') return null;
    return validateAtom(head, spec); // head must be a range or single value
  }

  // Range:  a-b
  if (atom.includes('-')) {
    const [aStr, bStr, ...rest] = atom.split('-');
    if (rest.length > 0 || aStr === undefined || bStr === undefined) {
      return `malformed range '${atom}'`;
    }
    const a = parseInteger(aStr);
    const b = parseInteger(bStr);
    if (a === null || b === null) return `range '${atom}' has non-numeric bounds`;
    if (a < spec.min || a > spec.max || b < spec.min || b > spec.max) {
      return `range '${atom}' out of bounds for ${spec.name} (${spec.min}-${spec.max})`;
    }
    if (a > b) return `range '${atom}' has start > end`;
    return null;
  }

  // Plain integer
  const n = parseInteger(atom);
  if (n === null) return `'${atom}' is not a valid value for ${spec.name}`;
  if (n < spec.min || n > spec.max) {
    return `'${atom}' out of bounds for ${spec.name} (${spec.min}-${spec.max})`;
  }
  return null;
}


function validateField(value: string, spec: FieldSpec): string | null {
  // List:  a,b,c — each item validated as an atom
  const items = value.split(',');
  for (const item of items) {
    if (item === '') return `empty value in ${spec.name}`;
    const err = validateAtom(item, spec);
    if (err) return err;
  }
  return null;
}


const WEEKDAYS = [
  'Sunday', 'Monday', 'Tuesday', 'Wednesday',
  'Thursday', 'Friday', 'Saturday',
];


function describeCommon(fields: string[]): string | undefined {
  // Friendly description for the most common cron shapes. Everything
  // else stays undefined; the page falls back to "Custom schedule".
  const [minute, hour, dom, month, dow] = fields;

  // Every-N-minutes: minute=*/n, all other fields = '*'.
  if (
    hour === '*' && dom === '*' && month === '*' && dow === '*' &&
    /^\*\/\d+$/.test(minute)
  ) {
    const n = parseInteger(minute.slice(2));
    if (n !== null && n > 0) {
      return n === 1 ? 'Every minute' : `Every ${n} minutes`;
    }
  }

  // Daily / Weekly: minute and hour pinned to single integers,
  // dom = '*', month = '*'.
  const m = parseInteger(minute);
  const h = parseInteger(hour);
  if (m === null || h === null) return undefined;
  if (dom !== '*' || month !== '*') return undefined;
  const hh = String(h).padStart(2, '0');
  const mm = String(m).padStart(2, '0');

  if (dow === '*') return `Daily at ${hh}:${mm}`;

  const d = parseInteger(dow);
  if (d !== null && d >= 0 && d <= 6) {
    return `Weekly on ${WEEKDAYS[d]} at ${hh}:${mm}`;
  }
  return undefined;
}


export function validateCron(expression: string): CronValidationResult {
  const trimmed = expression.trim();
  if (trimmed === '') {
    return { valid: false, error: 'Cron expression is required' };
  }
  const fields = trimmed.split(/\s+/);
  if (fields.length !== 5) {
    return {
      valid: false,
      error: 'Cron must have 5 fields: minute hour day-of-month month day-of-week',
    };
  }
  for (let i = 0; i < FIELDS.length; i++) {
    const err = validateField(fields[i], FIELDS[i]);
    if (err) {
      return { valid: false, error: `${FIELDS[i].name}: ${err}` };
    }
  }
  const description = describeCommon(fields);
  return description ? { valid: true, description } : { valid: true };
}
