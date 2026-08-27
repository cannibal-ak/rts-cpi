# interCaribbean (JY) chrome palette

The derivation record for `apps/web/src/components/dashboard/jyTheme.ts` — the
fourth chrome sibling after WinAir (`bannerTheme.ts`, docs/winair-palette.md),
DreamAir (`dreamairTheme.ts`, docs/dreamair-palette.md) and Liat
(`liatTheme.ts`, docs/liat-palette.md). Do not change a hex in the theme file
without re-measuring and updating this document.

Scope note: this document covers the **app chrome only** (filter bar, tab row,
sidebar/scope accents). JY's chart colours were deliberately left exactly as
they are — the `ic_branded` scheme in `infra/superset_config.py` and dashboard
1's `label_colors` are untouched (user decision, 2026-08-27).

## 0. Sources

- Logo `apps/web/src/assets/logos/jy-logo-banner.png`: dark-blue + mid-blue
  wordmark, tagline, and a magenta/green/cyan ribbon swoosh.
- Superset `ic_branded` scheme (`infra/superset_config.py`): `#049CFC` ocean
  (the JY series colour), `#E4049C` magenta, `#8CD404` green, `#04049C` deep
  blue, then amber/cyan/purple/slate competitor slots.
- Dashboard 1's own CSS sheet (the `--jy-*` custom-property system): header
  gradient `#1e4a7a → #2563ab`, tab ink gradient `#049CFC → #E4049C`.
- RTS platform navy `#1a5276` (`assets/RTS_Logo.svg`, MUI `primary.main`).

## 1. The chosen mapping (Option A — navy + cerulean)

Semantic rules inherited from WinAir: **brand** = "where you are + the one
committing action" (BANNER_BG: Apply, sidebar active items, spinners);
**accent** = "what you chose" (FILTER_ACCENT: active field borders, chips,
"+N" pill, sliders); the two must never be confusable with each other or with
an error.

| Token | Hex | Derivation |
|---|---|---|
| BANNER_BG (brand) | `#1E4A7A` | dash-1 CSS header gradient start; neighbour of RTS navy |
| BANNER_HEADER_BG (pressed) | `#163A61` | brand darkened one step |
| SCOPE_ACCENT / scopeInk | = brand | WM/DA pattern (only Liat splits scope from brand) |
| FILTER_BG (card surface) | `#DCEDF9` | sky tint of ocean `#049CFC` |
| FILTER_INK | `#0F2A40` | navy-family ink; alphas for borders/washes use rgb(15,42,64) |
| FILTER_LABEL_INK | `#2C4A66` | |
| FILTER_MUTED_INK | `#4E6980` | |
| FILTER_ACCENT (chosen) | `#0369A1` | ocean `#049CFC` darkened until it reads (raw ocean is 2.45:1 on the card) |
| FILTER_ERROR_INK | `#9A2A22` | shared across all four tenants |

Contrast, measured (WinAir floor in parentheses):

| Pair | Ratio |
|---|---|
| white on BANNER_BG | 9.07:1 |
| white on BANNER_HEADER_BG | 11.59:1 |
| BANNER_BG on FILTER_BG | 7.57:1 |
| FILTER_INK on FILTER_BG | 12.29:1 (10.17) |
| FILTER_LABEL_INK on FILTER_BG | 7.69:1 (5.89) |
| FILTER_MUTED_INK on FILTER_BG | 4.79:1 (3.86) |
| FILTER_ACCENT on FILTER_BG | 4.95:1 (4.53) |
| FILTER_ACCENT on white fields | 5.93:1 |
| white on FILTER_ACCENT | 5.93:1 |
| FILTER_ERROR_INK on FILTER_BG | 6.42:1 (6.11) |

Known trade-off: brand and accent are both blues, separated by lightness and
saturation (dark muted navy fill vs bright cerulean borders/chips) rather
than by hue the way WinAir's teal-vs-red separates. Accepted because the
whole JY page is already a blue system (embedded header, RTS navy, the JY
ocean-blue chart series), per the Liat precedent of the chrome speaking the
logo's own colours.

## 2. Option B (documented fallback — magenta accent)

If review finds the two blues read as one: keep everything above but
`FILTER_ACCENT = '#A8037B'` (logo magenta `#E4049C` darkened; 5.91:1 on
FILTER_BG, 7.09:1 on white) and `FILTER_CHIP_BG = 'rgba(168,3,123,0.14)'`.
Caveat: `#E4049C` is carrier **BW**'s series colour on JY charts — same
"chrome never meets a chart series in one plot" argument Liat used for its
blue, but it wants the same comment in the theme file.

## 3. Native price-chart carrier colours

`tenantCarrierColors.ts` `JY_CARRIERS` is a straight mirror of dashboard 1's
live `label_colors` (dev superset.db, 2026-08-27): JY `#049CFC`, BW `#E4049C`,
WM `#8CD404`, 9Q `#04049C`, 5L `#F59E0B`, PY `#06B6D4`, DO `#8B5CF6`,
S6 `#64748B`; fallbacks `#A05A2C`, `#0F766E` (no blue, nothing near an
existing slot). The table and the dashboard's `label_colors` are the same
assignment in two mirrors; change them together or not at all.

## 4. Known, out-of-scope chart gaps (pre-existing)

Recorded here so nobody mistakes them for regressions of the chrome work:

- Dashboard 1's `label_colors` has only the 8 bare carrier keys — none of the
  `"Min Fare, <carrier>"` / `"Max Fare, <carrier>"` composites WinAir binds
  (81 keys on dash 6). JY's own Min/Max series therefore render on scheme
  rotation (green/amber), not JY blue. See docs/winair-palette.md §6 traps.
- Slices 49 and 53 are legacy `dist_bar`, which cannot carry per-carrier
  colour at all; WinAir fixed the same thing by clone-and-swap (97→111,
  101→112).

Both are chart-side changes the user explicitly kept out of the 2026-08-27
chrome work ("charts stay as they are").
