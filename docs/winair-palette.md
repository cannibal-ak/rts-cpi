# WinAir (WM) colour palette

The single source of truth for WinAir colour — app chrome, native charts, and
Superset charts alike. Anchored on the WinAir logo red `#CD1F25`.

Every categorical value below was checked with the data-viz validator (OKLab ΔE
×100, Machado–Oliveira–Fernandes CVD simulation at severity 1.0) against the
surface it actually renders on: **white `#FFFFFF`** for Superset charts, which
draw on a white canvas — not the `#fcfcfb` default. Measured results are quoted
per section. Do not add or change a hex without re-running the validator.

---

## 1. Brand core (already in code — unchanged)

Defined in `apps/web/src/components/dashboard/bannerTheme.ts`.

| Role | Hex | Notes |
|---|---|---|
| Brand red | `#CD1F25` | sampled from the WinAir logo; the anchor for everything below |
| Brand red, pressed | `#A5181D` | one step darker — pressed/active chrome |
| Brand ink, dark mode | `lighten(#CD1F25, 0.3)` ≈ `#DC6266` | flat red only reaches ~2.9:1 on dark paper |

Red is an **accent**, not a surface. The dashboard chrome (tab row, filter card)
sits on the light teal grey below; red appears on it only for the committing
action and brand marks.

| Role | Hex |
|---|---|
| Chrome surface | `#D9E5E6` |
| Chrome accent (selection, active borders, chips) | `#2F6E73` |
| Chrome ink / label ink / muted ink | `#1E3438` / `#40585C` / `#5C7478` |
| Chrome error ink / tint | `#9A2A22` / `rgba(154,42,34,0.09)` |

`#2F6E73` is a **UI** accent only. Its chroma is below the chart floor (it would
read as grey in a plot), so it never becomes a series colour.

---

## 2. Palette A — carrier identity (already in code — unchanged)

Used **only where a series is an airline**: the Superset price-comparison charts
on dashboard 6 and the native Latest Prices panel. WM is always the brand red;
competitors are spaced around it.

| Code | Hex | | Code | Hex |
|---|---|---|---|---|
| **WM** | `#CD1F25` | | Exp / Expedia | `#A05A2C` |
| 5L | `#1BAF7A` | | JY | `#2A78D6` |
| 7Z | `#8B5CF6` | | S6 | `#D6208F` |
| BW | `#C08A00` | | DM | `#0891B2` |

Fallbacks for unnamed carriers: `#64748B`, `#0070C0`, `#0F766E`, `#B45309`,
`#7C3AED`. No red-family fallback — nothing may impersonate the host carrier.

Validated on white, in the order above: CVD ΔE 12.9 (worst adjacent, deutan),
normal-vision ΔE 23.0, all inside the lightness band and above the chroma floor.
`#1BAF7A` sits at 2.82:1 contrast — it carries direct labels/tooltips as relief.

This set is mirrored in three places that must stay identical:
`apps/web/src/components/dashboard/winair/priceChartTheme.ts`,
`scripts/superset_provision_winair.py`, `scripts/superset/wm_recolor_dash6.py`.

---

## 3. Palette B — measure series (NEW — this is the gap)

Used where a series is a **metric, not an airline**: the velocity chart
(Booking / Capacity / Seat Factor), and any future KPI or trend chart. These
charts currently fall through to Superset's default scheme, which is why they
render green — a colour with no relationship to the WinAir brand.

The structure is two hue *families*, not four unrelated hues, because the four
velocity series are really two measure pairs:

### B1 — Seats family (red, ordinal pair)

Capacity is the envelope; Current Booking is the part of it that has sold. That
is an ordered relationship, so it takes one hue in two steps, not two hues.

| Role | Light | Dark |
|---|---|---|
| Envelope (Capacity, target, prior period) | `#DE8078` | `#A0393E` |
| Filled / actual (Current Booking, revenue) | `#CD1F25` | `#DC6266` |

Validated as an ordinal ramp: monotone lightness, ΔL gap clear of the 0.06
floor, light end 2.81:1 on white / 2.61:1 on dark — all PASS in both modes.

Full red ramp, if more than two steps are ever needed (validated 5-step,
all PASS on white): `#E8938C` · `#D9524B` · `#CD1F25` · `#A5181D` · `#7C1216`.
This is also the **sequential** hue for WinAir magnitude encodings (heatmaps).

### B2 — Rate family (the % measures)

| Role | Light | Dark |
|---|---|---|
| Actual Seat Factor (measured) | `#0891B2` | `#22A5C4` |
| Forecasted Seat Factor (modelled) | `#8B5CF6` | `#8E77E0` |

Validated as categorical against the seats anchor — `#CD1F25`, `#0891B2`,
`#8B5CF6`: **all six checks PASS on white** (worst adjacent CVD ΔE 12.6,
normal-vision ΔE 21.1, every slot ≥ 3:1). Dark mode passes with one WARN
(violet↔cyan CVD ΔE 7.5, inside the 6–8 floor band), which is legal because the
two lines already carry secondary encoding — see below. Dark mode does not apply
to the Superset embed, which renders light-only.

**Why violet and not gold for the forecast.** Gold `#C08A00` also validates, but
gold is already BW's carrier colour and amber already means "sold out" on the
availability markers; a third meaning would make gold ambiguous. Violet reads as
*computed* rather than *warning*, which is what a forecast is.

**Secondary encoding — wanted, but not available in Superset.** Forecast and
Actual are the same measure, so ideally the forecast line would be dashed and
the actual solid. Superset's `mixed_timeseries` has no per-metric line style:
both rate metrics live in the same query group (`metrics_b`) and share one
`seriesTypeB`, so there is no form_data key that dashes one and not the other.

Colour alone therefore carries the distinction on that chart. That is legal
here — the pair measures CVD ΔE 12.6, above the ≥8 target, not in the 6–8 band
that would *require* a second channel. Where a chart form does support it
(the native ECharts panels, which set `lineStyle` per series), still dash the
forecast.

### Hue reuse across palettes A and B

`#0891B2` and `#8B5CF6` appear in both palettes. This is safe because the scopes
never meet: Palette B charts have no carrier dimension at all (velocity is
WM-only data), and Palette A charts plot no metrics as series. The rule is
**one palette per chart** — never mix A and B slots inside a single chart.

---

## 4. Status colours (reserved — never a series)

A red brand collides with the usual "red = critical" convention, so status is
deliberately pulled off the brand hue and always ships with an icon and a label.
Never use a status colour for "series 4", and never use a series colour for state.

| Role | Hex | On white |
|---|---|---|
| good | `#0CA30C` | 3.35:1 |
| warning | `#FAB219` | 1.83:1 — icon + label is the mitigation |
| serious | `#EC835A` | 2.64:1 — icon + label is the mitigation |
| critical | `#9A2A22` | 7.70:1 — the deep red already used for `FILTER_ERROR_INK`, *not* the brand red |

Critical reuses `#9A2A22` rather than `#CD1F25` on purpose: brand red must never
read as an error, and an error must never read as brand.

---

## 5. Chart chrome

| Role | Light | Dark |
|---|---|---|
| Chart surface | `#FFFFFF` (Superset canvas) | `#1A1A19` |
| Primary ink | `#1E3438` | `#FFFFFF` |
| Secondary ink | `#40585C` | `#C3C2B7` |
| Muted (axis, tick labels) | `#5C7478` | `#898781` |
| Gridline (hairline) | `#E1E5E6` | `#2C2C2A` |
| Baseline / axis | `#C3C9CA` | `#383835` |

Ink follows the chrome tokens already in `bannerTheme.ts` so the embed and the
app around it agree. **Text never wears a series colour** — a coloured mark
beside the label carries identity.

---

## 6. Applying this in Superset — read this first

Colour is bound by `label_colors`, a dict keyed on the **series name Superset
actually builds**. A key that does not match that name character-for-character
is *silently ignored* — no error, no warning, the chart just falls through to
`rts_cpi_palette[0]` (forest green `#2B6B2B`). Almost every off-brand chart on
dashboard 6 was a key that looked right and never matched.

The series name is rarely what the chart's legend shows. Four traps, all
verified in the running Superset 3.1.0 source:

| Chart shape | Series name is actually… | Trap |
|---|---|---|
| `dist_bar` with empty "Breakdowns" (`columns: []`) | the **metric label** — one series per metric | groupby values are x-axis *categories*, never series. Carrier keys on such a chart are all dead. |
| `mixed_timeseries`, query B (`metrics_b`) | the label **plus a literal ` (1)` suffix** | the legend shows the unsuffixed name; only the colour lookup is suffixed. `MixedTimeseries/transformProps.ts:408`. Query A has no suffix. |
| one metric + a groupby, `truncate_metric` off | `"<metric>, <carrier>"` | the bare carrier code never matches. |
| one metric + a groupby, `truncate_metric` on | the bare carrier code | the composite never matches. The opposite trap. |

Two more traps, learned building the per-carrier Competitor Breakdown (111):

- **x-axis label must differ from every series-column label.** A chart with
  `x_axis = airline` *and* `groupby = [airline]` sends duplicate `airline`
  labels, and `/api/v1/chart/data` rejects it with a 400 ("Duplicate
  column/metric labels"). Make the x-axis an adhoc column with a distinct
  label (`airline` AS `Airline`).
- **An engine-level dry run is not proof.** `QueryContext.get_payload()`
  skips the duplicate-label validator that the REST endpoint runs — a chart
  can pass in-container testing and 400 on the dashboard. Verify through
  `POST /api/v1/chart/data` with a guest token, with `dashboardId` set in
  `form_data` (the guest access branch requires it).

**Write to all three places**, and know which one does the work: the
**dashboard's** `json_metadata.label_colors` is what binds when a chart renders
inside a dashboard (`Chart.jsx` overwrites each slice's copy with it); the
slice's `params.label_colors` and `query_context.form_data.label_colors` keep
Explore consistent. Additive only — merge keys, never replace the dict.

**Standalone Chart-view cannot be fixed this way.** Explore's request builder
drops `label_colors`, so a chart opened by bare URL falls through to the scheme
regardless. Only registering a WinAir-first colour scheme helps there, and it
buys "brand-ish instead of green", not correct per-series colour.

### Availability-marker colours (cross-surface rule)

The native Latest Prices panel and Superset must mark availability the same
way. The native panel uses `theme.palette.warning.main` for sold-out and
`text.disabled` for not-on-sale (`LatestPricesPanel.tsx`), which resolve to:

| Marker | Hex | Why not red |
|---|---|---|
| Sold out | `#F39C12` | the old `#D32F2F` sits ΔE ≈ 4 from WM red — markers would read as WM datapoints |
| Not on sale | `#9E9E9E` | absence, not an event — stays grey on both surfaces |

Amber-vs-gold tension with BW `#C08A00` is accepted deliberately, same as the
native chart (its comment: BW is gold *because* the markers wear amber).

### Bound on dashboard 6 (dev, 2026-08-18)

| Slice | Series | Colour |
|---|---|---|
| 103 Booking/SF/Capacity | `Capacity` / `Current Booking` | `#DE8078` / `#CD1F25` |
| 103 | `Actual Seat Factor (1)` / `Forecasted SF (1)` | `#0891B2` / `#8B5CF6` |
| **111** Competitor Breakdown (replaced 97) | bare carrier codes | Palette A |
| 107 Fare Composition | `Base` / `Tax` / `YQ` | `#CD1F25` / `#DE8078` / `#0891B2` |
| 105 Lowest Available Avg_Fare | `Lowest Available Fare, <carrier>` | Palette A |
| 109 markers | `Sold out, <AL> (1)` / `Not on sale, <AL> (1)` | `#F39C12` / `#9E9E9E` |

**Slice 111 replaced slice 97** (2026-08-18): the old chart was a legacy
`dist_bar`, where per-carrier bars are structurally impossible (its one series
is the metric). 111 is `echarts_timeseries_bar` with `x_axis=airline` +
`groupby=[airline]` + `truncate_metric` + `stack` — series become the bare
carrier codes, Palette A binds, one identity-coloured bar per airline,
value-sorted via `x_axis_sort_series` (`x_axis_sort` is dead when groupby is
present). 97 is parked, intact, as rollback. A swap like this must repoint
every place the dashboard references the chart **by id**: `dashboard_slices`,
the `position_json` node, each native filter's `chartsInScope` / `scope.excluded`,
and `global_chart_configuration.chartsInScope` — a missed one makes filters
silently skip the chart. No app-code change: the tab row and chart lists are
discovered live from `position_json`.

Scripts, in order applied: `scripts/superset/wm_recolor_velocity.py`,
`wm_dash6_palette_keys.py`, `wm_carrier_consistency.py` (the 97→111 swap +
marker recolour). Each carries an in-DB backup table and a `--revert`; the
later two revert **key by key** rather than restoring whole payloads, because
other sessions edit this dashboard concurrently and a payload restore would
discard their work.

### Palette C — recommendation semantics (slice 112)

**Slice 112 replaced slice 101** (2026-08-18, same clone-and-swap as 111):
recommendation became the series, which finally made the intended traffic-light
renderable, re-based onto sanctioned hexes:

| Category | Hex | Meaning |
|---|---|---|
| Reduce | `#CD1F25` | act — price is too high |
| Monitor | `#C08A00` | watch |
| No Change | `#64748B` | neutral — **deliberately grey**; the validator's chroma-floor flag is expected (a "nothing to do" category should not carry a hue) |
| Consider Increase | `#1BAF7A` | opportunity |

Validated in display order on white: worst adjacent CVD ΔE 12.1,
normal-vision 20.9; `#1BAF7A`'s 2.82:1 contrast relieved by per-bar value
labels. Scope note: on this chart red means *Reduce*, not WM — a third palette
with its own scope, same one-palette-per-chart rule. 101 parked intact.

**Separate issue, flagged not fixed:** that chart is dual-axis (seats on the
left, seat factor % on the right). Two y-scales let the reader infer
relationships the data does not support — the bars and the lines can be made to
cross anywhere by rescaling. Colour will not fix that; splitting it into two
stacked charts sharing one x-axis would. Raised for a later decision.
