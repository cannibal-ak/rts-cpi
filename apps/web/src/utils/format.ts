/**
 * Currency formatter for the CPI application.
 *
 * Reads the currency code from the row's ref_curr / comp_curr / curr_code
 * and renders the appropriate symbol (GBP →£, KES →KSh, USD →$, EUR →€,
 * DKK →kr, etc.). Defaults to GBP if the currency code is missing.
 *
 * Phase 2F change: previously hardcoded 'USD'/'$'; now per-row currency.
 */

const formatterCache = new Map<string, Intl.NumberFormat>();

function getFormatter(currency: string): Intl.NumberFormat {
  let f = formatterCache.get(currency);
  if (!f) {
    try {
      f = new Intl.NumberFormat('en-GB', {
        style: 'currency',
        currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    } catch {
      // Unknown ISO 4217 code — fall back to GBP formatter
      f = new Intl.NumberFormat('en-GB', {
        style: 'currency',
        currency: 'GBP',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    }
    formatterCache.set(currency, f);
  }
  return f;
}

/**
 * Formats a numeric value using the row's currency code.
 *
 * @param value         The numeric amount (null/undefined for missing data)
 * @param currencyCode  ISO 4217 code (defaults to GBP if missing/empty)
 * @returns Formatted string e.g. "£1,234.56"; "—" for missing values
 */
export function formatCurrency(
  value: number | null | undefined,
  currencyCode?: string | null,
): string {
  if (value === undefined || value === null || isNaN(value)) {
    return '—';
  }
  const code = (currencyCode && currencyCode.trim()) || 'GBP';
  return getFormatter(code.toUpperCase()).format(value);
}

/**
 * Formats a numeric value using the row's currency code, no decimals.
 * Useful for mini-charts or dense tables.
 */
export function formatCurrencyCompact(
  value: number | null | undefined,
  currencyCode?: string | null,
): string {
  if (value === undefined || value === null || isNaN(value)) {
    return '—';
  }
  const code = (currencyCode && currencyCode.trim()) || 'GBP';
  try {
    return new Intl.NumberFormat('en-GB', {
      style: 'currency',
      currency: code.toUpperCase(),
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return value.toFixed(0);
  }
}
