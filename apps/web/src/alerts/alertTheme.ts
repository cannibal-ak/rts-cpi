/**
 * Severity presentation. Every colour here is already documented and
 * contrast-validated — no new hexes.
 *
 * On a branded tenant the values come from docs/dreamair-palette.md §4 (status)
 * and §2 (Palette C neutral); everywhere else they fall through to the MUI
 * semantic tokens, so the same component is DreamAir-branded on DreamAir and
 * app-navy on JY/PW/SKY/FJL with no per-tenant branch in any alerts file.
 *
 * TWO RULES THAT ARE NOT PREFERENCES:
 *
 * 1. Amber (#FAB219) is 1.83:1 on white. It may NEVER be text, and never a fill
 *    behind text. It is allowed as an icon colour, a left rule, and a chip
 *    OUTLINE — the label itself stays text.primary. `textSafe` encodes this so
 *    a caller cannot get it wrong by accident.
 * 2. Severity is never the only channel. Every chip and row carries an icon and
 *    a word as well as a colour. That is what makes the amber acceptable and
 *    what makes the whole thing legible to colour-blind users.
 *
 * `info` is the documented neutral #64748B rather than the brand azure, on
 * purpose: azure is DreamAir's brand mark, and using it for a severity would
 * make the brand colour mean "low priority" while colliding with the accent
 * used for unread dots and the active tab.
 */
import type { Theme } from '@mui/material';
import type { AlertSeverity } from '../types';
import type { TenantChrome } from '../components/dashboard/tenantChrome';

export interface SeverityStyle {
  /** Icon / rule / chip-outline colour. */
  color: string;
  /** Safe to use as text or as a fill behind white text. */
  textSafe: boolean;
  label: string;
  iconKey: 'info' | 'warning' | 'critical';
}

const BRANDED: Record<AlertSeverity, SeverityStyle> = {
  // Palette C neutral. 4.76:1 on white. Deliberately hue-free — "noted,
  // nothing to do" should not carry a colour that implies urgency.
  info: { color: '#64748B', textSafe: true, label: 'Info', iconKey: 'info' },
  // 1.83:1. Icon, rule and outline only. See rule 1 above.
  warning: { color: '#FAB219', textSafe: false, label: 'Watch', iconKey: 'warning' },
  // 5.44:1, and fill-safe with white text.
  critical: { color: '#C0392B', textSafe: true, label: 'Urgent', iconKey: 'critical' },
};

export function severityStyle(
  severity: AlertSeverity,
  chrome: TenantChrome | null,
  theme: Theme,
): SeverityStyle {
  if (chrome) return BRANDED[severity] ?? BRANDED.info;
  const fallback: Record<AlertSeverity, SeverityStyle> = {
    info: { color: theme.palette.text.secondary, textSafe: true, label: 'Info', iconKey: 'info' },
    warning: { color: theme.palette.warning.main, textSafe: false, label: 'Watch', iconKey: 'warning' },
    critical: { color: theme.palette.error.main, textSafe: true, label: 'Urgent', iconKey: 'critical' },
  };
  return fallback[severity] ?? fallback.info;
}

/**
 * The accent for unread dots, the active tab and preset switches.
 *
 * Brand-coloured TEXT and icons go through `chrome.brandInk(theme)`, which
 * lightens azure on dark paper; flat #1268E3 on #1A1A19 is too thin to read.
 *
 * Orchid (FILTER_ACCENT) is validated against the light FILTER_BG surface only
 * and has never been measured on dark paper, so it is not used here — brandInk
 * covers both modes and needs no new validator run.
 */
export function accentColor(chrome: TenantChrome | null, theme: Theme): string {
  return chrome ? chrome.brandInk(theme) : theme.palette.primary.main;
}

/**
 * Unread-badge fill. Red is free on DreamAir — the brand is azure, so a red
 * count carries no brand ambiguity. On an unbranded tenant this is the theme's
 * error colour, which is the same convention.
 *
 * NOTE for whoever switches WinAir on: WinAir's brand IS red, so its badge must
 * take theme.palette.error.main rather than a branded value, or the badge and
 * the brand become indistinguishable. Special-case it here when that happens.
 */
export function badgeColor(chrome: TenantChrome | null, theme: Theme): string {
  return chrome ? '#C0392B' : theme.palette.error.main;
}
