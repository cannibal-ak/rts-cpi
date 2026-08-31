# DreamAir (DA) colour palette

The single source of truth for DreamAir colour — app chrome, native charts, and
Superset charts alike. Anchored on the DreamAir logo azure `#1268E3`.

Every categorical value below was checked with the data-viz validator
(`scripts/validate_palette.js` — OKLab ΔE ×100, Machado–Oliveira–Fernandes CVD
simulation at severity 1.0) against the surface it actually renders on: **white
`#FFFFFF`** for Superset charts, which draw on a white canvas — not the
`#fcfcfb` default. Measured results are quoted per section. Do not add or change
a hex without re-running the validator.

This document is the DreamAir counterpart of `docs/winair-palette.md` and follows
its section order deliberately, so the two can be diffed.

**Where the anchor came from.** `DreamAir.svg` is a base64 PNG inside an SVG
wrapper, so the brand hue was sampled from pixels rather than read from fill
attributes: of the saturated, non-background pixels, 29.1% fall in the 210–220°
azure band and 22.1% in 200–210°, with a secondary orchid mass at 270–305°.
`#1268E3` is the centre of the dominant band; `#9B4FD8` represents the orchid.

---

## 0. How DreamAir differs from WinAir

Worth stating up front, because it changes two rules the WinAir doc had to work
around:

- **Red is free.** WinAir's brand *is* red, so its doc has to keep red away from
  error and status meanings. DreamAir's brand is azure, so red carries its
  conventional meaning here: `#C0392B` is critical, and "Reduce" in Palette C.
- **Cyan is not free.** The mirror of the same fact. Cyan sits next to azure, so
  the rate-family measure hue that WinAir renders in cyan (`#0891B2`) is a
  teal-green here (`#10996B`). Cyan against the azure brand fails the
  normal-vision floor in dark mode (ΔE 11.6, floor 15).

---

## 1. Brand core

To be defined in `apps/web/src/components/dashboard/dreamairTheme.ts` — a
sibling of `bannerTheme.ts`, not an edit to it. WinAir imports `bannerTheme.ts`
directly, and the tenants must be able to move independently.

| Role | Hex | Notes |
|---|---|---|
| Brand azure | `#1268E3` | sampled from the DreamAir logo; the anchor for everything below. White text 5.10:1 |
| Brand azure, pressed | `#0D4FB5` | one step darker — pressed/active chrome. White text 7.49:1 |
| Brand ink, dark mode | `lighten(#1268E3, 0.3)` ≈ `#5A92EB` | matches the WinAir treatment; flat azure is thin on dark paper |
| Deep ink | `#0B2E6B` | headings and the darkest brand step |

Azure is an **accent**, not a surface. The dashboard chrome (tab row, filter
card) sits on the light lilac grey below; azure appears on it only for the
committing action and brand marks.

| Role | Hex | Contrast on chrome |
|---|---|---|
| Chrome surface | `#E7E3F3` | — |
| Chrome accent (selection, active borders, chips) | `#7A45B8` | 4.95:1 |
| Chrome ink | `#221B3D` | 12.91:1 |
| Chrome label ink | `#463A6B` | 8.03:1 |
| Chrome muted ink | `#6A5F8C` | 4.60:1 |
| Chrome error ink / tint | `#9A2A22` / `rgba(154,42,34,0.09)` | 6.11:1 |

Every one of these meets or beats its WinAir counterpart (ink 10.17, label 5.89,
muted 3.86, accent 4.53).

`#7A45B8` is a **UI** accent only. As with WinAir's teal it never becomes a
series colour — the orchid that *does* appear in charts is the brighter
`#9B4FD8` in Palette A slot 7.

The alpha-derived tokens keep WinAir's alpha values exactly, re-based on the
DreamAir ink `rgb(34,27,61)` and accent `rgb(122,69,184)`:

| Token | Value |
|---|---|
| border | `rgba(34,27,61,0.13)` |
| field line | `rgba(34,27,61,0.45)` |
| disabled bg / ink | `rgba(34,27,61,0.10)` / `rgba(34,27,61,0.38)` |
| hover bg | `rgba(34,27,61,0.07)` |
| skeleton / skeleton text | `rgba(34,27,61,0.11)` / `rgba(34,27,61,0.08)` |
| slider rail | `rgba(34,27,61,0.28)` |
| chip bg | `rgba(122,69,184,0.14)` |

---

## 2. Palette A — carrier identity

Used **only where a series is an airline**: the Superset price-comparison charts
on the DreamAir dashboard and the native Latest Prices panel. DA is always the
brand azure; competitors are spaced around it.

**Slot order is fixed and must not be reordered** — the validator's checks are on
*adjacent* pairs, so the order is part of the result.

Slots 2–8 are assigned to competitors in descending row volume, so the busiest
carrier gets the most separable hue and the assignment is reproducible from the
data rather than from arrival order.

| # | Carrier | Hex | On white | | # | Carrier | Hex | On white |
|---|---|---|---|---|---|---|---|---|
| 1 | **DA** (DreamAir) | `#1268E3` | 5.10:1 | | 5 | Aur | `#0E9DA8` | 3.28:1 |
| 2 | TC | `#E8632A` | 3.36:1 | | 6 | YS | `#A05A2C` | 5.26:1 |
| 3 | KQ | `#D6208F` | 4.71:1 | | 7 | Coa | `#9B4FD8` | 4.66:1 |
| 4 | Fli | `#C08A00` | 3.05:1 | | 8 | UI | `#2E7D32` | 5.13:1 |

The competitors actually present in the DreamAir data. The first figures are
the Jan–Jun 2026 window the slots were assigned from; the second are the whole
PW archive, which DreamAir was widened to on 2026-08-19 (b1cd1e0):

| Carrier | Jan–Jun 2026 | Full archive | Slot |
|---|---|---|---|
| TC | 1.36M | 2.30M | 2 |
| KQ | 790k | 1.21M | 3 |
| Fli | 190k | 303k | 4 |
| Aur | 86k | 163k | 5 |
| YS | 73k | 97.7k | 6 |
| Coa | 44k | 97.5k | 7 |
| UI | 32k | 47.0k | 8 |
| **Exp** | — | **32.6k** | neutral fallback #2 |
| CQ | 24k | 30.7k | neutral fallback #1 |

That is **nine** competitors for **seven** identity slots.

**CQ takes the neutral fallback rather than a ninth hue.** This is deliberate,
not an oversight: no ninth hue exists that keeps the set separable (see the note
below), and the documented remedy for an overflowing categorical scale is to
fold the smallest series into "Other", never to generate another colour.

Fallbacks for unnamed carriers, CQ first: `#64748B`, `#0F766E`, `#B45309`,
`#7C3AED`. **No azure-family fallback** — nothing may impersonate the host
carrier. (This is the same rule as WinAir's "no red-family fallback", moved to
the new brand hue.)

### Exp — the tenth carrier the widening brought in (fixed 2026-08-19, dev)

`CARRIER_COLORS` was written against the Jan–Jun 2026 window, which has no Exp
rows at all. The 2026-08-19 widening to PW's whole archive added 32,557 Exp rows
at cap_date 2025-09-03..2025-09-15, and nothing regenerated `label_colors` — so
dashboard 7 kept the 94 keys the nine-carrier run produced and Exp had none of
them. WinAir hit the same gap the same day for the same carrier, from a
different cause (its `CARRIERS` loops were one short); see
`docs/winair-palette.md`.

**Exp takes neutral fallback #2, `#0F766E`** — not a ninth hue, and not a new
value: it was already slot 10 of `DA_DOMAIN` in the provisioning script.
CQ keeps `#64748B` even though the widened archive now puts Exp marginally ahead
of it on volume (32.6k vs 30.7k): re-basing CQ would be a *modification* under
the additive-only rule, and this document pins CQ to the first fallback by name.
So the fallback list is consumed in list order, not re-derived from volume.

**Why `#0F766E` is acceptable, measured.** On the full ten-slot set the
validator's worst all-pairs normal-vision pair becomes `#0F766E` ↔ UI `#2E7D32`
at ΔE 9.2, under the 15 floor — but **that pair cannot render.** On the
cap_dates where Exp has rows, only TC, KQ, Aur, Fli and Coa appear; UI, CQ and
YS all start 2026-05-09 and never co-occur with Exp. The worst pair Exp can
actually be seen beside is Aur:

```
#0F766E vs #0E9DA8 (Aur)     normal ΔE 12.9   CVD ΔE 12.6 (deutan)
#C08A00 vs #E8632A (Fli/TC)  normal ΔE 11.4   CVD ΔE  1.1 (deutan)   <- already shipped
```

Exp's worst *realisable* neighbour beats the palette's own existing worst
realisable pair on both axes, so this adds no separation problem that the
palette had not already accepted. `#0F766E`'s chroma (0.086) sits under the 0.10
floor; that is the point of a neutral overflow slot, exactly as with CQ's
`#64748B` (0.041) — do not saturate it. The other two fallbacks were measured
and rejected: `#B45309` vs YS `#A05A2C` is normal ΔE 3.9 / CVD 2.2, and
`#7C3AED` vs Coa `#9B4FD8` is normal ΔE 8.0 / CVD 4.1.

**Why the dashboard looked fine.** The date picker reads `vw_da_dashboard_dates`,
whose INTERSECT of the fares and velocity feeds starts 2025-12-12 — after Exp's
last date. With a cap_date-scoped guest token all 12 slices pass. Only a request
with **no** cap_date clause reaches Exp, and it built six unbindable series:
`Exp` (slices 121/122/123), `Max Fare, Exp` + `Min Fare, Exp` (113),
`Lowest Available Fare, Exp` (118), `Sold out, Exp (1)` + `Not on sale, Exp (1)`
(121). So **verify with an unscoped token** — a scoped PASS is necessary, not
sufficient. This is the same lesson WinAir's doc records from the other
direction (dev passed, prod's wider data did not).

Applied additively by `scripts/superset/da_dash7_exp_keys.py` (key-level backup
and `--revert`, single transaction), which writes the nine spellings
`build_label_colors()` emits per carrier — the six above plus `Avg Fare, Exp`,
`Sold out, Exp` and `Not on sale, Exp`, which nothing builds today but which
keep Exp from being the one carrier with a partial key set. Dashboard 7 went
94 → 103 keys, and the patched provisioning script regenerates that dict
byte-for-byte.

Validated on white, in the order above:

```
[PASS] Lightness band       all 8 inside L 0.43–0.77
[PASS] Chroma floor         all 8 >= 0.1
[PASS] CVD separation       worst adjacent #A05A2C↔#0E9DA8 ΔE 16.3 (deutan) · tritan 8.2
[PASS] Normal-vision floor  worst adjacent #D6208F↔#E8632A ΔE 19.5 (normal)
[PASS] Contrast vs surface  all 8 >= 3:1
→ ALL CHECKS PASS
```

This clears WinAir's Palette A on CVD separation (16.3 vs 12.9) and, unlike it,
has no sub-3:1 slot — so no slot depends on direct labels for relief.

**The all-pairs limit — read before adding a hue.** The run above tests
*adjacent* pairs, which is the right test for these line and bar forms, where
series are also separated by position, a legend, and tooltips. Under
`--pairs all` this set fails, worst pair gold `#C08A00` ↔ TC orange `#E8632A`
at normal-vision ΔE 11.4 and deutan ΔE 1.1.

That is not a defect introduced here; it is the ceiling for eight-plus
categorical hues, and WinAir's shipped palette fails the same way. It was
searched properly: a locked-anchor greedy plus local search over a
forty-colour pool could not lift the all-pairs normal-vision floor past 12.3
at nine slots, and every nine-slot candidate that scored well on adjacency did
so by adding a second violet or a near-azure indigo — `#5E35B1` alongside
`#9B4FD8` measures ΔE 14.0 head to head, under the 15 floor, so the legend
would have two violets a reader cannot separate.

Two consequences:

1. **Do not add a ninth carrier hue.** Fold the smallest carrier into "Other".
2. Where a chart genuinely needs any-pair discrimination (a scatter, a map),
   facet it or cut series instead of relying on colour.

The green slot is `#2E7D32` rather than the `#159467` this palette started
with: `#159467` is a blue-green and sat ΔE 9.4 from the `#0E9DA8` teal, the
worst pair in the set. A true forest green moves that to 11.4 while keeping
every adjacent check and the ≥3:1 floor intact.

This set currently lives in **one** place, plus the patch script that extends
it: `scripts/superset_provision_dreamair.py` (`CARRIER_COLORS`) and
`scripts/superset/da_dash7_exp_keys.py` (Exp only). Earlier revisions of this
document named `apps/web/src/components/dashboard/dreamair/priceChartTheme.ts`
and `scripts/superset/da_recolor_dash7.py` as mirrors; **neither file was ever
created** (checked 2026-08-19). `dreamairTheme.ts` exists but carries only the
brand and chrome tokens from section 1, no carrier hexes. If a native
per-carrier chart is built later, it must mirror `CARRIER_COLORS` including
Exp — and this list must be updated to say so.

---

## 3. Palette B — measure series

Used where a series is a **metric, not an airline**: the velocity chart
(Booking / Capacity / Seat Factor), and any future KPI or trend chart. Same
two-family structure as WinAir, because the four velocity series are really two
measure pairs.

### B1 — Seats family (azure, ordinal pair)

Capacity is the envelope; Current Booking is the part of it that has sold. That
is an ordered relationship, so it takes one hue in two steps, not two hues.

| Role | Light | Dark |
|---|---|---|
| Envelope (Capacity, target, prior period) | `#7FB0F0` | `#9CC3F5` |
| Filled / actual (Current Booking, revenue) | `#0D4FB5` | `#4A8DEC` |

Validated as an ordinal ramp — **ALL PASS in both modes**: monotone lightness,
ΔL gaps clear of the 0.06 floor, single hue (spread 5° light / 3° dark), light
end 2.24:1 on white and 5.24:1 on dark.

Full azure ramp, if more than two steps are ever needed (validated 5-step, all
PASS on white — note the light end is the B1 envelope colour, so the ramp and
the pair agree):

`#7FB0F0` · `#4A8DEC` · `#1268E3` · `#0D4FB5` · `#0A3C8A`

This is also the **sequential** hue for DreamAir magnitude encodings (heatmaps).

### B2 — Rate family (the % measures)

| Role | Light | Dark |
|---|---|---|
| Actual Seat Factor (measured) | `#10996B` | `#1FA97C` |
| Forecasted Seat Factor (modelled) | `#9B4FD8` | `#A96FE0` |

Validated as categorical against the seats anchor — `#1268E3`, `#10996B`,
`#9B4FD8`: **all six checks PASS on white** (worst adjacent CVD ΔE 12.8,
normal-vision ΔE 25.8, every slot ≥ 3:1). The dark triple `#4A8DEC`, `#1FA97C`,
`#A96FE0` also passes **all six** (CVD ΔE 16.0, normal 21.0) — better than
WinAir's dark set, which carries a WARN.

**Why teal-green and not cyan for the measured rate.** WinAir uses cyan
`#0891B2` here. Against an azure brand that fails: `#0891B2` vs `#4A8DEC` scores
normal-vision ΔE 11.6 in dark mode, under the 15 floor — a full-colour reader
cannot reliably separate them. Teal-green `#10996B` is the nearest hue that
clears the floor in both modes while staying clear of the status green `#0CA30C`.

**Why violet for the forecast.** Same reasoning WinAir gives, and it lands better
here: gold is a carrier slot and amber already means "sold out" on the
availability markers, so a third meaning would make gold ambiguous. Violet reads
as *computed* rather than *warning*, which is what a forecast is — and orchid is
DreamAir's own secondary brand hue, so the modelled series is on-brand.

**Secondary encoding — wanted, but not available in Superset.** Forecast and
Actual are the same measure, so ideally the forecast line would be dashed and the
actual solid. Superset's `mixed_timeseries` has no per-metric line style: both
rate metrics live in the same query group (`metrics_b`) and share one
`seriesTypeB`, so no form_data key dashes one and not the other. Colour alone
carries the distinction there, which is legal at ΔE 12.8 — above the ≥8 target,
not in the 6–8 band that would *require* a second channel. Where a chart form
does support it (the native ECharts panels, which set `lineStyle` per series),
still dash the forecast.

### Hue reuse across palettes A and B

`#9B4FD8` appears in both palettes (UI's carrier colour in A, the forecast in B),
and B's `#10996B` sits between A's teal `#0E9DA8` and green `#2E7D32`. This is
safe because the scopes never meet: Palette B charts have no carrier dimension at
all (velocity is DA-only data), and Palette A charts plot no metrics as series.
The rule is **one palette per chart** — never mix A and B slots inside a single
chart.

---

## 4. Status colours (reserved — never a series)

Unlike WinAir, DreamAir's brand does not collide with the "red = critical"
convention, so status can use the conventional hues directly. They still always
ship with an icon and a label — never colour alone. Never use a status colour for
"series 4", and never use a series colour for state.

| Role | Hex | On white |
|---|---|---|
| good | `#0CA30C` | 3.35:1 |
| warning | `#FAB219` | 1.83:1 — icon + label is the mitigation |
| serious | `#EC835A` | 2.64:1 — icon + label is the mitigation |
| critical | `#C0392B` | 5.44:1 — a true red, which is available here because the brand is azure |

The chrome error ink stays `#9A2A22` (6.11:1 on the chrome surface), matching
WinAir. Error tint and status critical are allowed to differ: one is a surface
treatment inside the filter card, the other is a data state.

---

## 5. Chart chrome

| Role | Light | Dark |
|---|---|---|
| Chart surface | `#FFFFFF` (Superset canvas) | `#1A1A19` |
| Primary ink | `#221B3D` (16.25:1) | `#FFFFFF` (17.42:1) |
| Secondary ink | `#463A6B` (10.11:1) | `#C7C3D6` (10.12:1) |
| Muted (axis, tick labels) | `#6A5F8C` (5.79:1) | `#918BA6` (5.35:1) |
| Gridline (hairline) | `#E6E3EE` | `#2C2A30` |
| Baseline / axis | `#C7C2D4` | `#3A3740` |

Ink follows the chrome tokens in `dreamairTheme.ts` so the embed and the app
around it agree. **Text never wears a series colour** — a coloured mark beside
the label carries identity.

---

## 6. Applying this in Superset — read this first

Everything in this section is inherited from the WinAir build and applies
unchanged; it is repeated here rather than cross-referenced because getting it
wrong is silent.

Colour is bound by `label_colors`, a dict keyed on the **series name Superset
actually builds**. A key that does not match that name character-for-character is
*silently ignored* — no error, no warning, the chart just falls through to
`rts_cpi_palette[0]` (forest green `#2B6B2B`).

The series name is rarely what the chart's legend shows. Four traps:

| Chart shape | Series name is actually… | Trap |
|---|---|---|
| `dist_bar` with empty "Breakdowns" (`columns: []`) | the **metric label** — one series per metric | groupby values are x-axis *categories*, never series. Carrier keys on such a chart are all dead. |
| `mixed_timeseries`, query B (`metrics_b`) | the label **plus a literal ` (1)` suffix** | the legend shows the unsuffixed name; only the colour lookup is suffixed. `MixedTimeseries/transformProps.ts:408`. Query A has no suffix. |
| one metric + a groupby, `truncate_metric` off | `"<metric>, <carrier>"` | the bare carrier code never matches. |
| one metric + a groupby, `truncate_metric` on | the bare carrier code | the composite never matches. The opposite trap. |

Two more, learned building WinAir's per-carrier Competitor Breakdown:

- **x-axis label must differ from every series-column label.** A chart with
  `x_axis = airline` *and* `groupby = [airline]` sends duplicate `airline`
  labels and `/api/v1/chart/data` rejects it with a 400 ("Duplicate
  column/metric labels"). Make the x-axis an adhoc column with a distinct label
  (`airline` AS `Airline`).
- **An engine-level dry run is not proof.** `QueryContext.get_payload()` skips
  the duplicate-label validator that the REST endpoint runs — a chart can pass
  in-container testing and 400 on the dashboard. Verify through
  `POST /api/v1/chart/data` with a guest token, with `dashboardId` set in
  `form_data` (the guest access branch requires it).

**Write to all three places**, and know which one does the work: the
**dashboard's** `json_metadata.label_colors` is what binds when a chart renders
inside a dashboard (`Chart.jsx` overwrites each slice's copy with it); the
slice's `params.label_colors` and `query_context.form_data.label_colors` keep
Explore consistent. Additive only — merge keys, never replace the dict.

**Standalone Chart-view cannot be fixed this way.** Explore's request builder
drops `label_colors`, so a chart opened by bare URL falls through to the scheme
regardless.

**Never edit `rts_cpi_palette`** — it is cross-tenant. A DreamAir change there
would repaint JY, PW, FJL and WM.

### Availability-marker colours (cross-surface rule)

The native Latest Prices panel and Superset must mark availability the same way.
These are **carried over from WinAir unchanged** — they are semantic, not brand:

| Marker | Hex | Why not brand |
|---|---|---|
| Sold out | `#F39C12` | an event, and amber is the conventional read |
| Not on sale | `#9E9E9E` | absence, not an event — stays grey on both surfaces |

Amber-vs-gold tension with the Palette A gold slot `#C08A00` is accepted
deliberately, exactly as on WinAir.

> **Data note.** The DreamAir dataset contains no `ref_seats = 0` rows, so the
> **sold-out** marker never fires — only "not on sale" appears. The amber is
> specified so the chart is correct if seat-zero data ever arrives, not because
> it is currently reachable. Re-checked after the 2026-08-19 widening to the
> full PW archive: still 0 of 4,285,228 rows, so this holds. Note the sold-out
> *series* is still built by the mixed_timeseries query even with no data in it,
> which is why it needs a `label_colors` key regardless.

### Palette C — recommendation semantics

The recommendation traffic-light. On DreamAir this is straightforward, because
red is not the brand:

| Category | Hex | Meaning |
|---|---|---|
| Reduce | `#C0392B` | act — price is too high |
| Monitor | `#C08A00` | watch |
| No Change | `#64748B` | neutral — **deliberately grey** |
| Consider Increase | `#1BAF7A` | opportunity |

Validated in display order on white: worst adjacent CVD ΔE 12.7, normal-vision
ΔE 18.7, all four inside the lightness band. Two expected flags, both the same
ones WinAir carries:

- **chroma floor FAIL on `#64748B`** — expected and intended. A "nothing to do"
  category should not carry a hue. Do not "fix" this by saturating the grey.
- **contrast WARN on `#1BAF7A` (2.82:1)** — relieved by per-bar value labels,
  which the chart already draws.

Unlike WinAir, `#C0392B` here means only "Reduce" and "critical" — the same
meaning in both scopes — so the one-palette-per-chart rule is easier to hold.

---

## 7. Checklist when changing a hex

1. Re-run the validator in the **slot order used in code**, once per mode.
   The dev host has no `node` on the PATH — run it inside the web container, and
   keep the filename, because the script's CLI guard checks
   `process.argv[1].endsWith("validate_palette.js")` and prints nothing if you
   rename it:

   ```bash
   docker exec cpi-web-1 mkdir -p /tmp/pal
   docker cp ~/CPI/scripts/validate_palette.js cpi-web-1:/tmp/pal/validate_palette.js
   docker exec cpi-web-1 sh -lc 'cd /tmp/pal && node validate_palette.js "#1268E3,…" --mode light --surface "#FFFFFF"'
   ```

   Then again with `--mode dark --surface "#1A1A19"`. Add `--ordinal` for a ramp.
2. Update all three mirrors (frontend theme, provisioning script, recolour script).
3. Re-apply the recolour script and verify through `POST /api/v1/chart/data`
   with a guest token — not an engine dry run.
4. Update the measured numbers quoted in this document.
