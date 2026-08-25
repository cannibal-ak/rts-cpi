# Liat Air (5L) colour palette

The single source of truth for Liat Air colour — app chrome, native charts, and
Superset charts alike. Anchored on the Liat Air logo's ocean blue `#1B5FA8`
(the swoosh), with the logo's gold as the chrome accent.

Every categorical value below was checked with the data-viz validator
(`scripts/validate_palette.js` — OKLab ΔE ×100, Machado–Oliveira–Fernandes CVD
simulation at severity 1.0) against the surface it actually renders on: **white
`#FFFFFF`** for Superset charts, which draw on a white canvas — not the
`#fcfcfb` default. Measured results are quoted per section. Do not add or change
a hex without re-running the validator.

This document is the Liat counterpart of `docs/dreamair-palette.md` and
`docs/winair-palette.md` and follows their section order deliberately, so the
three can be diffed.

**Where the anchor came from.** The supplied logo is a red/gold "A" mark over a
blue swoosh with white lettering on a sky background. The swoosh blue is the
brand anchor (`#1B5FA8`, deepened slightly from the gradient's midpoint so white
text clears 4.5:1 with room). The gold (`#F5C518` family in the mark) becomes
the chrome accent in a text-safe deep step, `#8A5F00`. The red of the "A" mark
is brand **art**, not a UI colour — see §0.

---

## 0. How Liat differs from its siblings

- **Red is free — but watch the logo.** Like DreamAir, the brand is blue, so
  red carries its conventional meaning: `#C0392B` is critical and "Reduce".
  Unlike DreamAir, the logo itself contains a red mark; that red stays inside
  the logo image and is never picked up as a UI or series colour, so the
  convention holds.
- **Gold is the accent, so gold is watched in charts.** The chrome accent
  family (`#8A5F00`) and the Palette A gold slot (`#C08A00`) and the sold-out
  amber (`#F39C12`) are three distinct steps of one hue family with three
  distinct scopes — chrome, carrier, marker. They never appear in the same
  scope, which is what keeps the reuse legal. Do not move any of them closer
  together.
- **Cyan is not free**, same as DreamAir: it sits next to the blue anchor, so
  the measured-rate hue is the teal-green `#10996B`, not WinAir's cyan.

---

## 1. Brand core

Defined in `apps/web/src/components/dashboard/liatTheme.ts` — the third sibling
of `bannerTheme.ts` (WinAir) and `dreamairTheme.ts`, not an edit to either.

| Role | Hex | Notes |
|---|---|---|
| Brand ocean blue | `#1B5FA8` | from the logo swoosh; the anchor for everything below. White text 6.46:1 |
| Brand blue, pressed | `#134878` | one step darker — pressed/active chrome. White text 9.43:1 |
| Brand ink, dark mode | `lighten(#1B5FA8, 0.3)` ≈ `#5F8FC2` | matches the sibling treatment; flat ocean is thin on dark paper |
| Deep ink | `#0C2A52` | headings and the darkest brand step |

Ocean blue is an **accent**, not a surface. The dashboard chrome (tab row,
filter card) sits on the cool blue-grey below; blue appears on it only for the
committing action and brand marks.

| Role | Hex | Contrast on chrome |
|---|---|---|
| Chrome surface | `#E6EDF4` | — |
| Chrome accent (selection, active borders, chips) | `#8A5F00` | 4.78:1 |
| Chrome ink | `#12263F` | 12.94:1 |
| Chrome label ink | `#2F4A6B` | 7.69:1 |
| Chrome muted ink | `#54677E` | 4.92:1 |
| Chrome error ink / tint | `#9A2A22` / `rgba(154,42,34,0.09)` | 6.52:1 |

Every one of these clears the WinAir floor (ink 10.17, label 5.89, muted 3.86,
accent 4.53, error 6.11).

`#8A5F00` is a **UI** accent only. As with WinAir's teal and DreamAir's orchid
it never becomes a series colour — the gold that *does* appear in charts is the
brighter `#C08A00` in Palette A slot 4.

The alpha-derived tokens keep the sibling alpha values exactly, re-based on the
Liat ink `rgb(18,38,63)` and accent `rgb(138,95,0)`:

| Token | Value |
|---|---|
| border | `rgba(18,38,63,0.13)` |
| field line | `rgba(18,38,63,0.45)` |
| disabled bg / ink | `rgba(18,38,63,0.10)` / `rgba(18,38,63,0.38)` |
| hover bg | `rgba(18,38,63,0.07)` |
| skeleton / skeleton text | `rgba(18,38,63,0.11)` / `rgba(18,38,63,0.08)` |
| slider rail | `rgba(18,38,63,0.28)` |
| chip bg | `rgba(138,95,0,0.14)` |

---

## 2. Palette A — carrier identity

Used **only where a series is an airline**: the Superset price-comparison charts
on the Liat dashboard and the native Latest Prices panel. 5L is always the
brand ocean blue; competitors are spaced around it.

**Slot order is fixed and must not be reordered** — the validator's checks are
on *adjacent* pairs, so the order is part of the result.

Slots 2–8 keep the DreamAir competitor solution. That solution was searched
properly (a locked-anchor greedy plus local search over a forty-colour pool —
see the DreamAir doc) and its anchor family is the same blue region, so
re-deriving it would reproduce it. Swapping the anchor from azure `#1268E3` to
ocean `#1B5FA8` changes only the slot 1↔2 adjacency, and the full set was
re-validated after the swap.

| # | Carrier | Hex | On white | | # | Carrier | Hex | On white |
|---|---|---|---|---|---|---|---|---|
| 1 | **5L** (Liat Air) | `#1B5FA8` | 6.46:1 | | 5 | *(slot 5)* | `#0E9DA8` | 3.28:1 |
| 2 | *(slot 2)* | `#E8632A` | 3.36:1 | | 6 | *(slot 6)* | `#A05A2C` | 5.26:1 |
| 3 | *(slot 3)* | `#D6208F` | 4.71:1 | | 7 | *(slot 7)* | `#9B4FD8` | 4.66:1 |
| 4 | *(slot 4)* | `#C08A00` | 3.05:1 | | 8 | *(slot 8)* | `#2E7D32` | 5.13:1 |

**Slots 2–8 are UNASSIGNED as of 2026-08-25** — the Liat data has not been
ingested yet. When it lands, assign competitors in **descending row volume**
(`SELECT comp_al, count(*) FROM vw_airline_cpi_5l_snapshot GROUP BY 1
ORDER BY 2 DESC`) by running `scripts/superset/liat_dash8_carrier_keys.py`,
which derives the assignment from the live view, refuses to run against an
empty one, and merges the keys additively (key-level backup + --revert).
Record the counts and the assignment in this table afterwards.
`scripts/superset_provision_liat.py` deliberately writes no competitor keys —
structure is provisioned before data exists, colour slots after. The busiest
carrier gets slot 2, so the assignment is reproducible from the data rather
than from arrival order.

Note that `5L` also appears as a **competitor** inside JY's and WM's data (Liat
is a genuine interCaribbean competitor). Those tenants' palettes are their own;
nothing here applies outside the Liat dashboard, and the one-tenant-one-doc rule
means no cross-tenant key is ever written.

Fallbacks for unnamed carriers, in consumption order: `#64748B`, `#0F766E`,
`#B45309`, `#7C3AED`. **No blue-family fallback** — nothing may impersonate the
host carrier. Overflow beyond eight named carriers takes fallbacks in list
order, never a ninth hue (see the DreamAir doc's all-pairs ceiling analysis,
which applies unchanged: the search could not lift a nine-hue set past
normal-vision ΔE 12.3).

Validated on white, in the slot order above:

```
[PASS] Lightness band       all 8 inside L 0.43–0.77
[PASS] Chroma floor         all 8 >= 0.1
[PASS] CVD separation       worst adjacent #A05A2C↔#0E9DA8 ΔE 16.3 (deutan) · tritan 8.2
[PASS] Normal-vision floor  worst adjacent #D6208F↔#E8632A ΔE 19.5 (normal)
[PASS] Contrast vs surface  all 8 >= 3:1
→ ALL CHECKS PASS
```

The adjacent-pairs standard (not all-pairs) is deliberate and inherited: these
are line and bar forms where series are also separated by position, legend and
tooltips. Under `--pairs all` the set fails at the same gold↔orange pair every
eight-plus-hue palette fails at; do not "fix" it, and do not rely on colour
alone in any chart form that needs any-pair discrimination.

---

## 3. Palette B — measure series

Used where a series is a **metric, not an airline**: the velocity chart
(Booking / Capacity / Seat Factor). Same two-family structure as the siblings.

### B1 — Seats family (ocean, ordinal pair)

Capacity is the envelope; Current Booking is the part of it that has sold. One
hue in two steps, not two hues.

| Role | Light | Dark |
|---|---|---|
| Envelope (Capacity, target, prior period) | `#79AEE8` | `#9CC3F5` |
| Filled / actual (Current Booking, revenue) | `#134878` | `#4E90DC` |

Validated as an ordinal ramp — **ALL PASS in both modes**: monotone lightness,
ΔL gaps clear of the 0.06 floor, single hue (spread 1°), light end 2.32:1 on
white and 5.14:1 on dark. The light filled step is the pressed brand blue, as
on DreamAir.

Full ocean ramp, if more than two steps are ever needed (validated 5-step, all
PASS on white — the light end is the B1 envelope colour, so the ramp and the
pair agree):

`#79AEE8` · `#4A86C8` · `#1B5FA8` · `#134878` · `#0C3255`

This is also the **sequential** hue for Liat magnitude encodings (heatmaps).

### B2 — Rate family (the % measures)

| Role | Light | Dark |
|---|---|---|
| Actual Seat Factor (measured) | `#10996B` | `#1FA97C` |
| Forecasted Seat Factor (modelled) | `#9B4FD8` | `#A96FE0` |

Carried from DreamAir unchanged, on the same reasoning: cyan fails next to a
blue brand; violet reads as *computed*, which is what a forecast is; and gold
cannot take the forecast because gold is a carrier slot **and** the chrome
accent here, and amber already means "sold out" on the availability markers —
a fourth meaning would make the hue unreadable.

Validated in the render order (seats anchor, actual, forecast): light triple
`#1B5FA8` / `#10996B` / `#9B4FD8` — **all-pairs PASS on white** (worst pair
CVD ΔE 8.0, normal 19.1, every slot ≥ 3:1). Dark triple `#4E90DC` / `#1FA97C` /
`#A96FE0` passes the adjacent standard on `#1A1A19` (worst adjacent CVD ΔE
16.0, normal 18.4) — the same standard the DreamAir dark triple meets, with the
same blue↔violet all-pairs caveat, mitigated the same way (bars vs lines are
different marks, and the forecast is dashed wherever the chart form allows).

The Superset `mixed_timeseries` limitation is inherited: both rate metrics
share one `seriesTypeB`, so no per-metric dash is possible there — colour
carries the distinction, which is legal at these ΔEs. Where a chart form does
support `lineStyle` per series (the native ECharts panels), dash the forecast.

### Hue reuse across palettes A and B

`#9B4FD8` appears in both palettes (a carrier slot in A, the forecast in B).
Safe for the same scope reason as on DreamAir: Palette B charts have no carrier
dimension (velocity is 5L-only data) and Palette A charts plot no metrics as
series. **One palette per chart** — never mix A and B slots inside one chart.

---

## 4. Status colours (reserved — never a series)

The brand does not collide with "red = critical", so status uses the
conventional hues directly — same values as DreamAir. Always icon + label,
never colour alone.

| Role | Hex | On white |
|---|---|---|
| good | `#0CA30C` | 3.35:1 |
| warning | `#FAB219` | 1.83:1 — icon + label is the mitigation; NEVER text or a fill behind text |
| serious | `#EC835A` | 2.64:1 — icon + label is the mitigation |
| critical | `#C0392B` | 5.44:1 |

The chrome error ink stays `#9A2A22` (6.52:1 on the chrome surface). Error tint
and status critical are allowed to differ: one is a surface treatment inside
the filter card, the other is a data state.

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

Ink follows the chrome tokens in `liatTheme.ts` so the embed and the app around
it agree. **Text never wears a series colour** — a coloured mark beside the
label carries identity.

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
series-column label** (duplicate labels 400 on `/api/v1/chart/data` but pass an
engine dry run), and **verify through `POST /api/v1/chart/data` with a guest
token** — with `dashboardId` in `form_data` — never via `QueryContext`.

**Verify with an UNSCOPED guest token.** A cap_date-scoped PASS is necessary,
not sufficient: DreamAir's Exp gap hid behind a scoped token for a day because
the missing carrier's rows sat outside the tested date (see the DreamAir doc §2).

**Write to all three places**: the **dashboard's** `json_metadata.label_colors`
is what binds inside a dashboard; the slice's `params.label_colors` and
`query_context.form_data.label_colors` keep Explore consistent. Additive only —
merge keys, never replace the dict.

**Never edit `rts_cpi_palette`** — it is cross-tenant. A Liat change there
would repaint JY, PW, FJL, WM and DA.

### Availability-marker colours (cross-surface rule)

Semantic, not brand — carried over unchanged:

| Marker | Hex | Why not brand |
|---|---|---|
| Sold out | `#F39C12` | an event, and amber is the conventional read |
| Not on sale | `#9E9E9E` | absence, not an event — stays grey on both surfaces |

The amber-vs-gold tension with Palette A's `#C08A00` and the chrome `#8A5F00`
is accepted deliberately, as on both siblings — three steps, three scopes (§0).
Whether the sold-out marker is reachable depends on the Liat data carrying
`ref_seats = 0` rows; check after the first ingest, and note the answer here as
the DreamAir doc does. The sold-out *series* is built by the mixed_timeseries
query even with no data in it, so it needs its `label_colors` keys regardless.

### Palette C — recommendation semantics

Same values as DreamAir — red is not the brand, so the traffic light is
conventional:

| Category | Hex | Meaning |
|---|---|---|
| Reduce | `#C0392B` | act — price is too high |
| Monitor | `#C08A00` | watch |
| No Change | `#64748B` | neutral — **deliberately grey** |
| Consider Increase | `#1BAF7A` | opportunity |

Validated in display order on white: worst adjacent CVD ΔE 12.7, normal-vision
ΔE 18.7. Two expected flags, the same ones both siblings carry:

- **chroma floor FAIL on `#64748B`** — expected and intended. "Nothing to do"
  should not carry a hue. Do not "fix" this by saturating the grey.
- **contrast WARN on `#1BAF7A` (2.82:1)** — relieved by per-bar value labels,
  which the chart already draws.

---

## 7. Checklist when changing a hex

1. Re-run the validator in the **slot order used in code**, once per mode.
   The dev host has no `node` on the PATH — run it inside the web container,
   and keep the filename (the CLI guard checks
   `process.argv[1].endsWith("validate_palette.js")`):

   ```bash
   docker exec cpi-web-1 mkdir -p /tmp/pal
   docker cp ~/CPI/scripts/validate_palette.js cpi-web-1:/tmp/pal/validate_palette.js
   docker exec cpi-web-1 sh -lc 'cd /tmp/pal && node validate_palette.js "#1B5FA8,…" --mode light --surface "#FFFFFF"'
   ```

   Then again with `--mode dark --surface "#1A1A19"`. Add `--ordinal` for a ramp.
2. Update all the mirrors: `liatTheme.ts` (chrome), and
   `scripts/superset_provision_liat.py` (chart hues). If a native per-carrier
   chart is built later, it must mirror the carrier map too — and this list
   must be updated to say so.
3. Re-apply and verify through `POST /api/v1/chart/data` with an **unscoped**
   guest token — not an engine dry run.
4. Update the measured numbers quoted in this document.
