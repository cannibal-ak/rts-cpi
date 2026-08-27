# Precision Air (PW) chrome palette

The derivation record for `apps/web/src/components/dashboard/pwTheme.ts` — the
fifth chrome sibling after WinAir (`bannerTheme.ts`, docs/winair-palette.md),
DreamAir (`dreamairTheme.ts`, docs/dreamair-palette.md), Liat
(`liatTheme.ts`, docs/liat-palette.md) and interCaribbean (`jyTheme.ts`,
docs/jy-palette.md). Do not change a hex in the theme file without
re-measuring and updating this document.

Scope note: this document covers the **app chrome only** (filter bar, tab row,
sidebar/scope accents). PW's chart colours were deliberately left as they are —
the `precisionAir` scheme in `infra/superset_config.py` and dashboard 3's
`label_colors` are untouched except the additive `Exp` key (see §3).

## 0. Sources

- Dashboard 3's own CSS sheet (the `--pw-*` custom-property system): header
  gradient `#2B5329 → #3D7A39`, gold hover `#C9A824`.
- Superset `precisionAir` scheme (`infra/superset_config.py`, ~line 331):
  `#3C5414` forest green in the first slot (the PW series colour), gold
  `#FBC31C`, 9 slots total.
- AppBar logo `apps/web/src/assets/logos/precisionair-logo.png`: forest-green
  wordmark with gold accents.
- Caution: raw brand gold `#FBC31C` measures **1.62:1 on white** — unusable as
  ink anywhere; it can only ever appear darkened.

## 1. The chosen mapping (green + gold accent)

Semantic rules inherited from WinAir: **brand** = "where you are + the one
committing action" (BANNER_BG: Apply, sidebar active items, spinners);
**accent** = "what you chose" (FILTER_ACCENT: active field borders, chips,
"+N" pill, sliders); the two must never be confusable with each other or with
an error.

| Token | Hex | Derivation |
|---|---|---|
| BANNER_BG (brand) | `#2B5329` | dash-3 CSS header gradient start |
| BANNER_HEADER_BG (pressed) | `#1E3D1D` | brand darkened one step |
| FILTER_BG (card surface) | `#E4F0E2` | pale tint of the header green |
| FILTER_INK | `#17301A` | green-family ink |
| FILTER_LABEL_INK | `#2F4A2E` | |
| FILTER_MUTED_INK | `#4E6650` | |
| FILTER_ACCENT (chosen) | `#7A6000` | brand gold `#FBC31C` darkened until it reads (the naive one-step `#8A6D00` still fails at 4.18:1) |
| FILTER_CHIP_BG | `rgba(122,96,0,0.14)` | accent wash |
| FILTER_FIELD_LINE | `rgba(23,48,26,0.45)` | ink alpha for resting field borders |
| FILTER_ERROR_INK | `#9A2A22` | shared across all chrome tenants |

Contrast, measured (WinAir floor in parentheses):

| Pair | Ratio |
|---|---|
| white on BANNER_BG | 8.85:1 |
| white on BANNER_HEADER_BG | 12.07:1 |
| BANNER_BG on FILTER_BG (brandInk-on-card) | 7.53:1 |
| FILTER_INK on FILTER_BG | 12.12:1 (10.17) |
| FILTER_LABEL_INK on FILTER_BG | 8.35:1 (5.89) |
| FILTER_MUTED_INK on FILTER_BG | 5.35:1 (3.86) |
| FILTER_ACCENT on FILTER_BG | 5.10:1 (4.53) |
| FILTER_ERROR_INK on FILTER_BG | 6.55:1 (6.11) |

Trade-off note: unlike JY (two blues separated only by lightness), PW's brand
and accent separate by **hue** — dark green fill vs gold borders/chips — which
is exactly the axis WinAir's teal-vs-red walks. The cost is that the gold had
to be pulled a long way down from the logo's `#FBC31C` to read as ink.

## 2. Option B (documented fallback — all-green monochrome)

If review finds the darkened gold too far from the brand gold to register:
keep everything above but `FILTER_ACCENT = '#2F6B2F'` (5.47:1 on FILTER_BG,
6.43:1 on white) and the matching green chip wash. Caveat: brand and accent
then collapse into one green family, giving up the chosen-state vs brand
separation that the gold buys. Documented only — not applied.

## 3. Native price-chart carrier colours

`tenantCarrierColors.ts` `PW_CARRIERS` is a straight mirror of dashboard 3's
live `label_colors`: PW `#3C5414` (host), TC `#5C8226`, KQ `#4A6B1C`,
UI `#80A83A`, YS `#A8C44E`, CQ `#C49714`, Aur `#FBC31C`, Coa `#6E9930`,
Fli `#E0AD18` (Aur/Coa/Fli are legacy carriers appearing in historical
captures only), plus Exp `#64748B` added by
`scripts/superset/pw_dash3_exp_keys.py` — the DA-precedent gap fix: `Exp` has
32,557 historical rows and was missing from `label_colors` entirely. The table
and the dashboard's `label_colors` are the same assignment in two mirrors;
change them together or not at all.

## 4. Known notes / out-of-scope

Recorded here so nobody mistakes them for regressions of the chrome work:

- The Trip_Type filter on the bar is a **deliberate no-op**: its
  `chartsInScope` is empty (value-source only) and PW data is 100% one-way, so
  the dropdown holds a single value. Recorded so it is not filed as a bug.
- Dashboard chart restyling is out of scope for this work.
- Superset-side `label_colors` were left untouched except the additive `Exp`
  key described in §3.
