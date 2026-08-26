# Liat Air (5L) colour palette

The single source of truth for Liat Air colour — app chrome, native charts, and
Superset charts alike. Anchored on the Liat Air logo's **red** `#D02127`, with
the logo's remaining colours (gold, swoosh azure, wordmark blue) carrying the
other roles. This supersedes the blue-anchored first revision (2026-08-25,
same day): the client directed that red — the logo's A-mark — is 5L's identity
in every chart, and that the rest of the palette comes from the logo.
Revised again 2026-08-26 ("Option B", chrome only — no chart hex changed): the
client directed that the chrome mix red and blue the way the logo writes them,
so the chosen/scoped state moved from the gold step to the wordmark blue
`#275AA1` and the gold left the chrome entirely. Red now appears in the chrome
only for brand marks and committing actions (Apply, the zoom sliders, sidebar
and app-bar chrome).

Every categorical value below was checked with the data-viz validator
(`scripts/validate_palette.js` — OKLab ΔE ×100, Machado–Oliveira–Fernandes CVD
simulation at severity 1.0) against the surface it actually renders on: **white
`#FFFFFF`** for Superset charts, which draw on a white canvas — not the
`#fcfcfb` default. Measured results are quoted per section. Do not add or
change a hex without re-running the validator.

This document is the Liat counterpart of `docs/winair-palette.md` (whose brand
is also red — its rules port here almost verbatim) and
`docs/dreamair-palette.md`, and follows their section order deliberately.

**Where every value comes from.** The official vector logo is
`Logos/LiatAir/liat-logo-original.svg`; its hexes map to the palette so:

| Logo element | Logo value | Palette use |
|---|---|---|
| A-mark red gradient | `#E32228 → #BC2026` | brand red `#D02127` (gradient midpoint) — 5L in every chart, brand ink in the chrome |
| Swoosh gradient | `#245293 → #0375B4` | `#0375B4` = Palette A slot 2 + the measured-rate hue; the blue family also seeds the chrome surface `#E6EDF4` and its inks |
| Wordmark blue | `#275AA1` | Palette A slot 4 + the chrome's chosen/scoped accent (selected tab pill, date chips, filter accents) with its pressed step `#1B3F72` |
| Gold fold | `#E1BD23 → #F5D332` | chart gold `#C08A00` (text-safe step — the bright `#F5D332` is ~1.6:1 on white, unusable as a series). Charts only since 2026-08-26 — gold no longer appears in the chrome |

The header PNG is recomposed from the square SVG (mark left, wordmark right)
by `Logos/LiatAir/compose_logo.py` — the stacked layout is illegible at the
48px header height.

---

## 0. How Liat differs from its siblings

- **Red is the brand — the WinAir rules apply.** Status "critical" is the deep
  `#9A2A22`, never the brand red: brand must not read as error, error must not
  read as brand. The sold-out marker stays amber for the same reason WinAir's
  does — a red marker would read as a 5L datapoint. Palette C's "Reduce" DOES
  reuse the brand red, with WinAir's scope note: on that chart red means
  Reduce, not 5L, and the scopes never meet (the reco chart has no carrier
  series). One palette per chart.
- **Gold is two scoped steps, charts only.** Chart gold `#C08A00` (Palette A
  slot 3 / Palette C Monitor / composition Tax) and marker amber `#F39C12`
  (sold out). They never share a scope; do not move them closer together. The
  chrome accent `#8A5F00` was retired 2026-08-26 when the chosen state moved
  to the wordmark blue — do not reintroduce a third gold.
- **Blue is the chosen state in the chrome — and shares its hex with a
  carrier.** The chrome's `SCOPE_ACCENT`/`FILTER_ACCENT` `#275AA1` is the
  same hex as Palette A slot 4 (the WM line). Safe for the exact scope reason
  the brand red is: chrome is never a chart series, the two never meet inside
  one plot, and Apply already shares red with the 5L line under it. One
  palette per chart.
- **Two blue slots, never adjacent.** Palette A carries both logo blues —
  azure `#0375B4` (slot 2) and wordmark `#275AA1` (slot 4) — separated by the
  gold slot. The adjacency-based validation makes the slot order part of the
  result: **do not reorder.**

---

## 1. Brand core

Defined in `apps/web/src/components/dashboard/liatTheme.ts` — the third
sibling of `bannerTheme.ts` (WinAir) and `dreamairTheme.ts`.

| Role | Hex | Notes |
|---|---|---|
| Brand red | `#D02127` | the A-mark gradient midpoint; the anchor for everything below. White text 5.35:1 |
| Brand red, pressed | `#9C1B20` | the gradient's dark end, one step on. White text 8.10:1 |
| Brand ink, dark mode | `lighten(#D02127, 0.3)` ≈ `#DE6367` | flat red is thin on dark paper — the same treatment as WinAir |

Red is an **accent**, not a surface. The dashboard chrome (tab row, filter
card) sits on the light blue-grey below — the logo's blue family — and red
appears on it only for the committing action (Apply) and brand marks. The
chosen/scoped state is the **wordmark blue**, NOT red: on a red-branded page
a red selection would read as brand, not choice. Since 2026-08-26 that blue
covers both the filter card's chosen state (`FILTER_ACCENT`) and the
"where you are" chrome (`SCOPE_ACCENT`: the selected section pill, the
Latest data / Cap date chips, and — same day, per user direction — the
sidebar menu's on-path labels and selected rows, via the mode-aware
`scopeInk` = `lighten(#275AA1, 0.3)` ≈ `#688CBD` on dark paper). The
red-branded siblings paint all of it in their brand via aliased tokens.
The sidebar's solid rail tile stays `BANNER_BG` red by explicit user
choice — it is a brand mark, like the app-bar avatar; the logout button
was never tenant chrome (theme error red) and spinners stay `brandInk`.

| Role | Hex | Contrast on chrome |
|---|---|---|
| Chrome surface | `#E6EDF4` | — |
| Chrome accent (chosen state, active borders, chips, sliders) | `#275AA1` | 5.81:1 (6.86:1 on the white fields) |
| Scope accent (selected tab pill, date chips, sidebar selected rows) | `#275AA1` | white text on it 6.86:1; sidebar row text on its 10% tint 5.91:1, on the 12% hover tint 5.73:1 — both above the red family these alphas were tuned for (4.41:1) |
| Scope accent, pressed | `#1B3F72` | white text on it 10.50:1; as hover text on a white pill 10.50:1 |
| Chrome ink | `#12263F` | 12.94:1 |
| Chrome label ink | `#2F4A6B` | 7.69:1 |
| Chrome muted ink | `#54677E` | 4.92:1 |
| Chrome error ink / tint | `#9A2A22` / `rgba(154,42,34,0.09)` | 6.52:1 |
| Brand red on the chrome surface | `#D02127` | 4.53:1 |

Every card token clears the WinAir floor (ink 10.17, label 5.89, muted 3.86,
accent 4.53, error 6.11) — the blue accent (5.81) beats the retired gold
(4.78), and the blue pill's white text (6.86) beats the red pill it replaced
(5.35). The pressed step is a darkened wordmark blue, not the swoosh
gradient's dark end `#245293`, which is too close to `#275AA1` to read as a
state change.

The alpha-derived tokens keep the sibling alpha values exactly, re-based on
the Liat ink `rgb(18,38,63)` and accent `rgb(39,90,161)`:

| Token | Value |
|---|---|
| border | `rgba(18,38,63,0.13)` |
| field line | `rgba(18,38,63,0.45)` |
| disabled bg / ink | `rgba(18,38,63,0.10)` / `rgba(18,38,63,0.38)` |
| hover bg | `rgba(18,38,63,0.07)` |
| skeleton / skeleton text | `rgba(18,38,63,0.11)` / `rgba(18,38,63,0.08)` |
| slider rail | `rgba(18,38,63,0.28)` |
| chip bg | `rgba(39,90,161,0.14)` — accent text on the blended chip 5.56:1 |

---

## 2. Palette A — carrier identity

Used **only where a series is an airline**: the Superset price-comparison
charts on the Liat dashboard and the native Latest Prices panel. 5L is always
the brand red; competitors are spaced around it, with the logo's own colours
in the first three competitor slots — so the busiest carriers wear logo
colours.

**Slot order is fixed and must not be reordered** — the validator's checks are
on *adjacent* pairs, so the order is part of the result (and it is what keeps
the two blue slots apart).

| # | Carrier | Hex | On white | | # | Carrier | Hex | On white |
|---|---|---|---|---|---|---|---|---|
| 1 | **5L** (Liat Air) | `#D02127` | 5.35:1 | | 5 | S6 | `#2E7D32` | 5.13:1 |
| 2 | BW | `#0375B4` | 4.29:1 | | 6 | PY | `#D6208F` | 4.71:1 |
| 3 | JY | `#C08A00` | 3.05:1 | | 7 | *(unused)* | `#A05A2C` | 5.26:1 |
| 4 | WM | `#275AA1` | 6.86:1 | | 8 | *(unused)* | `#9B4FD8` | 4.66:1 |

**Slots were assigned 2026-08-25** by
`scripts/superset/liat_dash8_carrier_keys.py` from the first committed
ingest (27,179 rows, cap_dates 2026-08-09..24), in descending row volume —
so the assignment is reproducible from the data, and the three busiest
carriers wear the logo's own colours:

| Carrier | Rows | Slot |
|---|---|---|
| BW | 12,313 | 2 (logo azure) |
| JY | 8,202 | 3 (logo gold) |
| WM | 4,421 | 4 (logo wordmark blue) |
| S6 | 2,045 | 5 |
| PY | 198 | 6 |

The same assignment is mirrored in `LIAT_CARRIERS.known` in
`apps/web/src/components/dashboard/tenantCarrierColors.ts` — the native
panel and the embedded dashboard must colour each carrier identically. A NEW
carrier appearing in a later upload takes the next free slot (7, then 8,
then the neutral fallbacks): re-run the script — existing keys are never
overwritten, so the established assignment cannot shift under it. Note BW,
JY, WM and S6 here are Liat's competitors, not the tenants of the same
codes — each tenant's palette is its own scope.

Note that `5L` also appears as a **competitor** inside JY's and WM's data
(WinAir's palette gives it mint `#1BAF7A` there). Those tenants' palettes are
their own; the tenant-aware carrier table in `tenantCarrierColors.ts` is what
keeps the two meanings of "5L" from ever meeting on one screen.

Fallbacks for unnamed carriers, in consumption order: `#64748B`, `#0F766E`.
**No red-family fallback** — nothing may impersonate the host carrier.
Overflow past the two neutrals folds into "Other", never a new hue (the
nine-hue ceiling analysis in the DreamAir doc applies unchanged).

Validated on white, in the slot order above:

```
[PASS] Lightness band       all 8 inside L 0.43–0.77
[PASS] Chroma floor         all 8 >= 0.1
[PASS] CVD separation       worst adjacent #D6208F↔#2E7D32 ΔE 11.5 (deutan) · tritan 5.6
[PASS] Normal-vision floor  worst adjacent #A05A2C↔#D6208F ΔE 20.7 (normal)
[PASS] Contrast vs surface  all 8 >= 3:1
→ ALL CHECKS PASS
```

No slot carries a contrast WARN — unlike both siblings' shipped sets, no slot
depends on direct labels for relief. The adjacent-pairs standard (not
all-pairs) is deliberate and inherited: these are line and bar forms where
series are also separated by position, legend and tooltips.

---

## 3. Palette B — measure series

Used where a series is a **metric, not an airline**: the velocity chart
(Booking / Capacity / Seat Factor). Same two-family structure as the siblings;
with a red brand the whole section is structurally WinAir's, in Liat's hexes.

### B1 — Seats family (red, ordinal pair)

Capacity is the envelope; Current Booking is the part of it that has sold.
One hue in two steps, not two hues.

| Role | Light | Dark |
|---|---|---|
| Envelope (Capacity, target, prior period) | `#DE8078` | `#A0393E` |
| Filled / actual (Current Booking, revenue) | `#D02127` | `#DE6367` |

Validated as an ordinal ramp — **ALL PASS in both modes**: monotone lightness,
ΔL gaps clear of the 0.06 floor, single hue, light end 2.81:1 on white and
2.61:1 on dark (the sub-3:1 light ends are the documented WinAir trade — the
bars carry direct labels).

Full red ramp, if more than two steps are ever needed (validated 5-step, all
PASS on white): `#E8938C` · `#D9524B` · `#D02127` · `#9C1B20`-family `#A5181D`
· `#7C1216`. This is also the **sequential** hue for Liat magnitude encodings
(heatmaps).

### B2 — Rate family (the % measures)

| Role | Light | Dark |
|---|---|---|
| Actual Seat Factor (measured) | `#0375B4` | `#22A5C4` |
| Forecasted Seat Factor (modelled) | `#8B5CF6` | `#8E77E0` |

The measured rate is the **logo swoosh azure** — available here because the
brand is red (on the blue-branded siblings this hue was too close to their
anchors). The forecast is violet, the sibling-wide convention: violet reads as
*computed*, and gold cannot take it (both chart-gold steps already have scopes, §0).

Validated in the render order (seats anchor, actual, forecast): light triple
`#D02127` / `#0375B4` / `#8B5CF6` — **all-pairs PASS on white** (worst pair
CVD ΔE 10.1, normal 17.9, every slot ≥ 3:1). Dark triple `#DE6367` /
`#22A5C4` / `#8E77E0` passes all-pairs on `#1A1A19` with one WARN
(violet↔cyan CVD ΔE 7.5, inside the 6–8 band — legal because the lines carry
secondary encoding, and the same WARN WinAir's dark set carries). The dark
Actual leans cyan (`#22A5C4`, WinAir's value) rather than a straight lighten
of the azure: `lighten(#0375B4)` ≈ `#4F9ECA` measures normal-vision ΔE 13.2
against the violet — under the 15 floor — so it was rejected.

The Superset `mixed_timeseries` limitation is inherited: both rate metrics
share one `seriesTypeB`, so no per-metric dash is possible there — colour
carries the distinction, which is legal at these ΔEs. Where a chart form does
support `lineStyle` per series (the native ECharts panels), dash the forecast.

### Fare Composition (dist_bar metrics — all three logo families)

| Metric | Hex |
|---|---|
| Base | `#D02127` (brand red) |
| Tax | `#C08A00` (logo gold step) |
| YQ | `#0375B4` (logo azure) |

Validated all-pairs on white: worst pair `#C08A00`↔`#D02127` CVD ΔE 11.4,
normal 20.6, all ≥ 3:1 — ALL PASS.

### Hue reuse across palettes A and B

`#0375B4` appears in both palettes (a carrier slot in A, the measured rate in
B), as does the brand red (5L in A, Current Booking / Base in B). Safe for the
same scope reason as on the siblings: Palette B charts have no carrier
dimension (velocity is 5L-only data) and Palette A charts plot no metrics as
series. **One palette per chart.**

---

## 4. Status colours (reserved — never a series)

A red brand collides with "red = critical", so status is pulled off the brand
hue — WinAir §4 verbatim. Always icon + label, never colour alone.

| Role | Hex | On white |
|---|---|---|
| good | `#0CA30C` | 3.35:1 |
| warning | `#FAB219` | 1.83:1 — icon + label is the mitigation; NEVER text or a fill behind text |
| serious | `#EC835A` | 2.64:1 — icon + label is the mitigation |
| critical | `#9A2A22` | 7.70:1 — the deep red already used for `FILTER_ERROR_INK`, *not* the brand red |

Critical reuses `#9A2A22` rather than `#D02127` on purpose: brand red must
never read as an error, and an error must never read as brand.

---

## 5. Chart chrome

| Role | Light | Dark |
|---|---|---|
| Chart surface | `#FFFFFF` (Superset canvas) | `#1A1A19` |
| Primary ink | `#12263F` (15.4:1) | `#FFFFFF` (17.4:1) |
| Secondary ink | `#2F4A6B` (9.0:1) | `#C2CBD8` (10.6:1) |
| Muted (axis, tick labels) | `#54677E` (5.7:1) | `#8B99AB` (5.5:1) |
| Gridline (hairline) | `#E3E9F1` | `#2A2C30` |
| Baseline / axis | `#C4CFDC` | `#393D44` |

Ink follows the chrome tokens in `liatTheme.ts` so the embed and the app
around it agree. **Text never wears a series colour** — a coloured mark beside
the label carries identity.

---

## 6. Applying this in Superset — read this first

Everything in this section is inherited from the WinAir/DreamAir builds and
applies unchanged; repeated rather than cross-referenced because getting it
wrong is silent.

Colour is bound by `label_colors`, a dict keyed on the **series name Superset
actually builds**. A key that does not match that name character-for-character
is *silently ignored* — no error, no warning, the chart falls through to
`rts_cpi_palette[0]` (forest green `#2B6B2B`).

The series name is rarely what the legend shows. The four traps:

| Chart shape | Series name is actually… | Trap |
|---|---|---|
| `dist_bar` with empty "Breakdowns" (`columns: []`) | the **metric label** — one series per metric | groupby values are x-axis *categories*, never series. Carrier keys on such a chart are all dead. |
| `mixed_timeseries`, query B (`metrics_b`) | the label **plus a literal ` (1)` suffix** | the legend shows the unsuffixed name; only the colour lookup is suffixed. Query A has no suffix. |
| one metric + a groupby, `truncate_metric` off | `"<metric>, <carrier>"` | the bare carrier code never matches. |
| one metric + a groupby, `truncate_metric` on | the bare carrier code | the composite never matches. The opposite trap. |

Plus the two WinAir lessons: **x-axis label must differ from every
series-column label** (duplicate labels 400 on `/api/v1/chart/data` but pass
an engine dry run), and **verify through `POST /api/v1/chart/data` with a
guest token** — with `dashboardId` in `form_data` — never via `QueryContext`.

**Verify with an UNSCOPED guest token.** A cap_date-scoped PASS is necessary,
not sufficient (the DreamAir Exp lesson).

**Write to all three places**: the **dashboard's**
`json_metadata.label_colors` binds inside a dashboard; the slice's
`params.label_colors` and `query_context.form_data.label_colors` keep Explore
consistent. Additive only — merge keys, never replace the dict.

**Never edit `rts_cpi_palette`** — it is cross-tenant.

The 2026-08-25 re-anchor was applied to the live dashboard 8 by
`scripts/superset/liat_dash8_recolor.py` (key-level backup + `--revert`);
`superset_provision_liat.py` carries the red values for any future
re-provision.

### Availability-marker colours (cross-surface rule)

Semantic, not brand — and on a red brand the WinAir rationale applies
directly: a red marker would read as a 5L datapoint.

| Marker | Hex | Why not brand |
|---|---|---|
| Sold out | `#F39C12` | an event; amber is the conventional read, and it is the second scoped gold step (§0) |
| Not on sale | `#9E9E9E` | absence, not an event — stays grey on both surfaces |

Whether the sold-out marker is reachable depends on the Liat data carrying
`ref_seats = 0` rows; check after the first ingest and note the answer here.
The sold-out *series* is built by the mixed_timeseries query even with no
data in it, so it needs its `label_colors` keys regardless.

### Palette C — recommendation semantics

As on WinAir, Reduce reuses the brand red — on this chart red means *Reduce*,
not 5L, and the scopes never meet:

| Category | Hex | Meaning |
|---|---|---|
| Reduce | `#D02127` | act — price is too high |
| Monitor | `#C08A00` | watch |
| No Change | `#64748B` | neutral — **deliberately grey** |
| Consider Increase | `#1BAF7A` | opportunity |

Validated in display order on white: worst adjacent CVD ΔE 11.4, normal-vision
ΔE 18.9. Two expected flags, the same ones both siblings carry:

- **chroma floor FAIL on `#64748B`** — expected and intended. Do not "fix"
  this by saturating the grey.
- **contrast WARN on `#1BAF7A` (2.82:1)** — relieved by per-bar value labels.

---

## 7. Checklist when changing a hex

1. Re-run the validator in the **slot order used in code**, once per mode.
   The dev host has no `node` on the PATH — run it inside the web container,
   and keep the filename (the CLI guard checks
   `process.argv[1].endsWith("validate_palette.js")`):

   ```bash
   docker exec cpi-web-1 mkdir -p /tmp/pal
   docker cp ~/CPI/scripts/validate_palette.js cpi-web-1:/tmp/pal/validate_palette.js
   docker exec cpi-web-1 sh -lc 'cd /tmp/pal && node validate_palette.js "#D02127,…" --mode light --surface "#FFFFFF"'
   ```

   Then again with `--mode dark --surface "#1A1A19"`. Add `--ordinal` for a ramp.
2. Update ALL the mirrors: `liatTheme.ts` (chrome + brand),
   `tenantCarrierColors.ts` (native-panel carrier table),
   `scripts/superset_provision_liat.py` (chart hues),
   `scripts/superset/liat_dash8_carrier_keys.py` (slot hexes) — and re-apply
   to the live dashboard via `scripts/superset/liat_dash8_recolor.py`.
3. Re-apply and verify through `POST /api/v1/chart/data` with an **unscoped**
   guest token — not an engine dry run.
4. Update the measured numbers quoted in this document.
