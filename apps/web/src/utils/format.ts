/**
 * Global currency formatter for the CPI application.
 * Standardizes all currency displays to USD ($).
 */

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * Formats a numeric value as a USD currency string.
 * @param value The numeric amount to format.
 * @returns A formatted string e.g. "$1,234.56"
 */
export function formatCurrency(value: number): string {
  if (value === undefined || value === null || isNaN(value)) {
    return '$0.00';
  }
  return currencyFormatter.format(value);
}

/**
 * Formats a numeric value as a compact USD string (no decimals if not needed, or truncated).
 * Useful for mini-charts or dense tables if needed.
 */
export function formatCurrencyCompact(value: number): string {
  if (value === undefined || value === null || isNaN(value)) {
    return '$0';
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}
