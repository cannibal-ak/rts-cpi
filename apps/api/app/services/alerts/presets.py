"""The preset rule catalogue — the single source of truth for what a user may tune.

Users do not author rule TYPES here; they switch presets on and off, adjust a
handful of numbers, and may create additional INSTANCES of these same families
(rows with is_preset=false and preset_key naming the family). That constraint
is what makes the evaluator safe: it only ever runs conditions it defined
itself, so there is no free-form JSON to interpret and no way for a client to
describe something the engine cannot compute.

Each preset declares its `tunables`. The API validates a PATCH by merging the
submitted keys over the stored condition and validating the MERGED WHOLE against
the pydantic model below with extra="forbid", so a non-tunable or misspelled key
is a 422 that names the field rather than a silently ignored write. The same
`tunables` list is returned to the frontend so it can render the controls
without hard-coding ranges.

Migration 040 carries a frozen copy of the defaults. Migrations must not import
app code — a later edit here would otherwise rewrite history — so the two are
kept in sync deliberately, with this module as the source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# The departure-horizon ladder, as (label, first day, last day) — BOTH ENDS
# INCLUSIVE, so '15-30' really does mean days 15 to 30.
#
# It runs to 90 days because feeds differ, and the old three-bucket set quietly
# threw away everything past day 30. Measured on the newest capture of each
# tenant: DA, PW and ALT carry exactly 30 departure days (0-29) and lose
# nothing; JY and 5L carry 46 (0-45); WM carries 86 (0-85). On WM that was
# 83,450 rows a capture — 20,131 of them priced on our own side — invisible to
# every rule. A tenant simply cannot see a bucket its feed never reaches, so
# which buckets exist is tenant DATA and the picker is filled per request
# (options_source below), exactly as routes and competitors are.
#
# Still a closed set: an unknown bucket string is a validation error. The first
# three labels and their bounds are unchanged, so every stored condition stays
# valid — the only shift is that day 30 now falls in '15-30' rather than being
# dropped by the horizon filter, which is what the label always claimed.
WINDOW_BOUNDS: tuple[tuple[str, int, int], ...] = (
    ("00-07", 0, 7),
    ("08-14", 8, 14),
    ("15-30", 15, 30),
    ("31-45", 31, 45),
    ("46-60", 46, 60),
    ("61-90", 61, 90),
)

WINDOWS = tuple(label for label, _, _ in WINDOW_BOUNDS)

# What a preset SHIPS watching, which is deliberately not the whole ladder.
# Widening the default would silently increase alert volume for JY, 5L and WM
# the moment this lands; the extra buckets are offered in the picker and ticked
# on purpose.
DEFAULT_WINDOWS = ("00-07", "08-14", "15-30")

# Literal cannot be computed from WINDOW_BOUNDS — keep the two in step.
WindowLiteral = Literal["00-07", "08-14", "15-30", "31-45", "46-60", "61-90"]

# How far any rule can look. Bounds the snapshot scan in queries.py.
MAX_WINDOW_DTD = WINDOW_BOUNDS[-1][2]


def windows_for_horizon(max_dtd: int | None) -> list[str]:
    """The buckets a feed reaching `max_dtd` days out can actually populate.

    A bucket qualifies as soon as the horizon reaches its FIRST day: WM's 85-day
    feed offers 61-90 even though it stops short of day 90, because the days it
    does have in that band are real. Falls back to the shipped default when the
    horizon is unknown, so the picker is never empty.
    """
    if max_dtd is None:
        return list(DEFAULT_WINDOWS)
    found = [label for label, lo, _ in WINDOW_BOUNDS if lo <= max_dtd]
    return found or list(DEFAULT_WINDOWS)

# The products a feed can carry. DA, PW, ALT and WM are 100% one-way; JY and 5L
# carry both. A closed set for the same reason WINDOWS is: an unknown value is a
# validation error, not a new product.
#
# This is a GRAIN, not merely a filter. Mixing the two collapses min(stops) onto
# the one-way value, because a one-way is never worse than the round trip it is
# half of: measured on JY, mixed OW+RT scores 38 comparable / 2 disadvantaged --
# numerically identical to one-way alone, with all 698,070 round-trip rows
# silently invisible.
TRIP_TYPES = ("OW", "RT")
TripTypeLiteral = Literal["OW", "RT"]


# ─────────────────────────────────────────────────────────────
# Condition models — one per preset, all extra="forbid"
# ─────────────────────────────────────────────────────────────

class _Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompPriceMoveCondition(_Condition):
    grain: Literal["route_competitor_window"] = "route_competitor_window"
    metric: Literal["min_available_fare"] = "min_available_fare"
    move_pct: float = Field(10.0, ge=1.0, le=50.0)
    direction: Literal["down", "up", "both"] = "both"
    # The noise floor. A 12% move on a $50 route is $6, which nobody reprices
    # against; without this the cheap ARK/DAR routes crowd out everything else.
    min_abs_move: float = Field(5.0, ge=0.0, le=500.0)
    windows: list[WindowLiteral] = Field(default_factory=lambda: list(DEFAULT_WINDOWS), min_length=1)
    competitors: list[str] | None = None
    routes: list[str] | None = None


class UndercutPositionCondition(_Condition):
    grain: Literal["route_window"] = "route_window"
    metric: Literal["min_available_fare"] = "min_available_fare"
    max_rank: int = Field(1, ge=1, le=5)
    # Defaults to 1.0%, not 0. The DA demo feed advances our own fare by exactly
    # +0.10 every capture, so a competitor sitting cents below us flips the rank
    # on synthetic noise. A floor keeps "undercut" meaning something commercial.
    min_gap_pct: float = Field(1.0, ge=0.0, le=20.0)
    notify_on_recovery: bool = True
    windows: list[WindowLiteral] = Field(default_factory=lambda: list(DEFAULT_WINDOWS), min_length=1)
    routes: list[str] | None = None


class CompPriceThresholdCondition(_Condition):
    grain: Literal["route_competitor_window"] = "route_competitor_window"
    metric: Literal["min_available_fare"] = "min_available_fare"
    operator: Literal["below", "above"] = "below"
    value: float | None = Field(None, ge=0.0)
    currency: str = "USD"
    windows: list[WindowLiteral] = Field(default_factory=lambda: ["00-07"], min_length=1)
    competitors: list[str] | None = None
    routes: list[str] | None = None


class StopsDisadvantageCondition(_Condition):
    grain: Literal["route_trip_window"] = "route_trip_window"
    metric: Literal["min_stops_on_sale"] = "min_stops_on_sale"
    # How many stops worse than the best competitor before it counts. Only gaps
    # of 1 have ever been observed in any tenant's feed, so this is headroom
    # rather than a filter.
    min_stop_gap: int = Field(1, ge=1, le=3)
    # A verdict resting on one departure day is noise, not a finding: both JY
    # cells that scored "disadvantaged" across three captures were backed by
    # exactly one comparable day out of the 8-10 the window observed.
    min_days: int = Field(3, ge=1, le=15)
    min_day_share: float = Field(50.0, ge=1.0, le=100.0)
    notify_on_recovery: bool = True
    windows: list[WindowLiteral] = Field(default_factory=lambda: list(DEFAULT_WINDOWS), min_length=1)
    trip_types: list[TripTypeLiteral] | None = None
    competitors: list[str] | None = None
    routes: list[str] | None = None


class ServiceGapCondition(_Condition):
    grain: Literal["route_trip_window"] = "route_trip_window"
    metric: Literal["days_not_on_sale"] = "days_not_on_sale"
    # Enter 'gap' at this many days. LEAVING requires zero: the band between is
    # a deliberate dead zone. Without it, a bare threshold flips 66 cells over
    # four JY captures -- 16.5 alerts every capture, forever.
    #
    # Defaults to 3, not 1, because the window itself rolls: the 00-07 bucket
    # covers a different set of departure days on every capture, so a route that
    # is off sale on one weekday drifts in and out of it. Measured over a
    # 40-pair JY backfill -- 2: 110 events (2.75/capture), 3: 70 (1.75),
    # 4: 44 (1.10). Three missing days out of eight is a real hole; two is
    # often just the window moving.
    min_gap_days: int = Field(3, ge=1, le=30)
    # The denominator guard, and the most important number in this rule. JY
    # samples departure offsets {0..7, 10, 15, 20, 25}, so its 08-14 window
    # observes 1.4 days on average and 15-30 observes 3.7. A cell that thin
    # cannot carry a day count: unguarded it flips like a coin, and with
    # min_gap_days > 1 it can never reach 'gap' at all and goes SILENTLY blind.
    # Guard the denominator; do not tune around it.
    min_days_observed: int = Field(4, ge=1, le=30)
    min_competitors: int = Field(1, ge=1, le=10)
    # Count days where we hold a flight but no sellable fare. The two cases are
    # separable in this feed and mean different things -- no flight is a network
    # decision, a flight with no fare is an inventory or fare-loading one -- so
    # they are always split out in the payload and the message.
    include_sold_out: bool = True
    notify_on_recovery: bool = True
    # 00-07 only by default: the one window every tenant's feed observes
    # completely (JY 7.8 of 8, against 1.4 of 7 and 3.7 of 15).
    windows: list[WindowLiteral] = Field(default_factory=lambda: ["00-07"], min_length=1)
    trip_types: list[TripTypeLiteral] | None = None
    competitors: list[str] | None = None
    routes: list[str] | None = None


# ─────────────────────────────────────────────────────────────
# Tunables — what the settings screen renders
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Tunable:
    key: str
    label: str
    type: Literal["number", "enum", "bool", "multiselect"]
    unit: str | None = None
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: list[str] | None = None
    help: str | None = None
    # Where the option list comes from when it is tenant DATA rather than preset
    # shape. Resolved per request by the router, and deliberately NOT serialised
    # by tunables_payload below -- the wire contract is unchanged, so the API
    # schema and the frontend need no edit. This replaces a hardcoded
    # `t["key"] == "routes"` that lived in three call sites and is the reason
    # the competitors picker has never once rendered.
    options_source: Literal["routes", "competitors"] | None = None


@dataclass(frozen=True)
class Preset:
    rule_key: str
    name: str
    description: str
    domain: str
    rule_type: str
    severity_default: str
    default_active: bool
    model: type[_Condition]
    tunables: list[Tunable] = field(default_factory=list)
    # Fields that must be set before the rule may be switched on. Enforced by
    # the API so a rule can never be active-but-uncomputable.
    requires_before_active: tuple[str, ...] = ()

    def defaults(self) -> dict[str, Any]:
        return self.model().model_dump()

    def validate_condition(self, merged: dict[str, Any]) -> dict[str, Any]:
        """Validate a fully-merged condition. Raises pydantic ValidationError."""
        return self.model(**merged).model_dump()


# options=None: which buckets a tenant can reach depends on how far ahead its
# feed quotes, so the router fills this per request like routes and competitors.
# Offering WM's 61-90 to DreamAir, whose feed stops at day 29, would be a
# setting that silently matches nothing.
_WINDOW_TUNABLE = Tunable(
    key="windows", label="Departure windows", type="multiselect",
    options=None, options_source="windows",
    help="How far ahead of departure to watch, in days.",
)

# Literal options, so this one renders without server injection. A no-op for the
# four tenants whose feed is entirely one-way; for JY and 5L it lets a user mute
# the product they do not sell.
_TRIP_TYPE_TUNABLE = Tunable(
    key="trip_types", label="Trip types", type="multiselect",
    options=list(TRIP_TYPES),
    help="Leave empty to watch every product the feed carries.",
)


PRESETS: dict[str, Preset] = {
    "comp_price_move": Preset(
        rule_key="comp_price_move",
        name="Competitor fare moved sharply",
        description=(
            "A competitor's cheapest available fare on a route and departure "
            "window moved by more than the threshold since the previous capture."
        ),
        domain="airline",
        rule_type="threshold",
        severity_default="warning",
        default_active=True,
        model=CompPriceMoveCondition,
        tunables=[
            Tunable("move_pct", "Move of at least", "number", unit="percent",
                    min=1, max=50, step=0.5,
                    help="Percentage change against the previous capture."),
            Tunable("min_abs_move", "and at least", "number", unit="currency",
                    min=0, max=500, step=1,
                    help="Ignores large percentages on cheap fares."),
            Tunable("direction", "Direction", "enum",
                    options=["down", "up", "both"]),
            Tunable("competitors", "Competitors", "multiselect",
                    options_source="competitors",
                    help="Leave empty to watch every competitor."),
            _WINDOW_TUNABLE,
        ],
    ),
    "undercut_position": Preset(
        rule_key="undercut_position",
        name="Lost the cheapest position",
        description=(
            "Our cheapest available fare on a route and departure window fell "
            "behind the competition, or recovered."
        ),
        domain="airline",
        rule_type="threshold",
        severity_default="warning",
        default_active=True,
        model=UndercutPositionCondition,
        tunables=[
            Tunable("max_rank", "Alert when our rank falls below", "number",
                    unit="places", min=1, max=5, step=1,
                    help="1 means alert as soon as we are no longer cheapest."),
            Tunable("min_gap_pct", "Ignore gaps smaller than", "number",
                    unit="percent", min=0, max=20, step=0.5,
                    help="Stops being undercut by pennies from raising an alert."),
            Tunable("notify_on_recovery", "Also tell me when we recover", "bool"),
            Tunable("routes", "Routes", "multiselect",
                    options_source="routes",
                    help="Leave empty to watch every route."),
            _WINDOW_TUNABLE,
        ],
    ),
    "comp_price_threshold": Preset(
        rule_key="comp_price_threshold",
        name="Competitor fare crossed a price line",
        description=(
            "A competitor's cheapest available fare crossed an absolute price "
            "you set."
        ),
        domain="airline",
        rule_type="threshold",
        severity_default="info",
        # Ships off. Fares span USD 50-353 across twelve routes, so one global
        # price line is meaningless until a user picks a route — and a preset
        # that fires on everything the moment it is switched on teaches people
        # to ignore the bell.
        default_active=False,
        model=CompPriceThresholdCondition,
        tunables=[
            Tunable("operator", "Alert when the fare goes", "enum",
                    options=["below", "above"]),
            Tunable("value", "this price", "number", unit="currency",
                    min=0, max=100000, step=1),
            Tunable("routes", "on routes", "multiselect",
                    options_source="routes"),
            Tunable("competitors", "Competitors", "multiselect",
                    options_source="competitors",
                    help="Leave empty to watch every competitor."),
            _WINDOW_TUNABLE,
        ],
        requires_before_active=("value", "routes"),
    ),
}

PRESETS["stops_disadvantage"] = Preset(
    rule_key="stops_disadvantage",
    name="A competitor flies it in fewer stops",
    description=(
        "The best itinerary we have on sale for a route and departure window "
        "makes more stops than the best a competitor is selling."
    ),
    domain="airline",
    rule_type="threshold",
    severity_default="warning",
    # Ships OFF, for the same reason service_gap does. The steady state is
    # genuinely quiet — this reports a network fact that changes a few times a
    # year, not a daily one — but the FIRST fire is not, because every existing
    # disadvantage announces itself at once. Measured against the newest capture
    # pair on 2026-08-28: JY 0, PW 6, DA 6, 5L 8, WM 29.
    #
    # Twenty-nine alerts arriving unannounced on a live tenant teaches people to
    # ignore the bell just as surely as a rule that matches everything. Size it
    # per tenant with POST /rules/stops_disadvantage/preview, then switch it on.
    default_active=False,
    model=StopsDisadvantageCondition,
    tunables=[
        Tunable("min_stop_gap", "Alert when they are ahead by at least", "number",
                unit="stops", min=1, max=3, step=1,
                help="1 means alert as soon as anyone offers a shorter itinerary."),
        Tunable("min_days", "over at least this many departure days", "number",
                unit="days", min=1, max=15, step=1,
                help="Only days where both sides publish a stop count."),
        Tunable("min_day_share", "on at least this share of them", "number",
                unit="percent", min=1, max=100, step=5),
        Tunable("notify_on_recovery", "Also tell me when we match them again", "bool"),
        Tunable("routes", "Routes", "multiselect", options_source="routes",
                help="Leave empty to watch every route."),
        Tunable("competitors", "Competitors", "multiselect",
                options_source="competitors",
                help="Leave empty to watch every competitor."),
        _TRIP_TYPE_TUNABLE,
        _WINDOW_TUNABLE,
    ],
)

PRESETS["service_gap"] = Preset(
    rule_key="service_gap",
    name="Nothing of ours on sale while they sell",
    description=(
        "On several departure days in a window we have no fare on sale -- no "
        "flight at all, or a flight with no fare -- while competitors do."
    ),
    domain="airline",
    rule_type="threshold",
    severity_default="warning",
    # Ships OFF, but NOT for comp_price_threshold's reason. This preset is fully
    # configured out of the box; what it cannot do is arrive quietly. First fire
    # with these defaults is 14 events on JY and 37 on WM, and 103 of WM's 165
    # cells once all three windows are ticked. A preset that lands 37 alerts the
    # moment it is switched on teaches people to ignore the bell just as surely
    # as one that matches everything.
    #
    # POST /rules/service_gap/preview reports the real count against the newest
    # capture pair, so the toggle is an informed decision rather than a
    # surprise. Do not flip this to True without re-running that preview per
    # tenant -- and note requires_before_active is deliberately EMPTY, because
    # the settings card disables every scalar while a rule is off, so a preset
    # that requires a number before activation can never be switched on at all.
    default_active=False,
    model=ServiceGapCondition,
    tunables=[
        Tunable("min_gap_days", "Alert when we are off sale for", "number",
                unit="days", min=1, max=30, step=1,
                help="Clears only when we are back on sale on every observed day."),
        Tunable("min_days_observed", "Ignore windows with fewer than", "number",
                unit="days", min=1, max=30, step=1,
                help="Some feeds sample only a few departure dates per window."),
        Tunable("min_competitors", "and at least this many competitors selling",
                "number", unit="airlines", min=1, max=10, step=1),
        Tunable("include_sold_out", "Count days we fly but have no fare", "bool"),
        Tunable("notify_on_recovery", "Also tell me when we are back on sale", "bool"),
        Tunable("routes", "Routes", "multiselect", options_source="routes",
                help="Leave empty to watch every route."),
        Tunable("competitors", "Competitors", "multiselect",
                options_source="competitors",
                help="Leave empty to count every competitor."),
        _TRIP_TYPE_TUNABLE,
        _WINDOW_TUNABLE,
    ],
)

# Evaluation order, and the iteration list for BOTH _ensure_presets and
# load_active_rules -- a preset missing from here is invisible to the entire
# engine. Ordered by how actionable the signal is: losing the cheapest position
# and having nothing on sale at all outrank a competitor's price twitch, and the
# stops rule reports a network fact that changes a few times a year.
PRESET_ORDER = (
    "undercut_position",
    "service_gap",
    "comp_price_move",
    "stops_disadvantage",
    "comp_price_threshold",
)


def get_preset(rule_key: str) -> Preset | None:
    return PRESETS.get(rule_key)


def tunables_payload(preset: Preset) -> list[dict[str, Any]]:
    """Serialise tunables for the API."""
    return [
        {
            "key": t.key, "label": t.label, "type": t.type, "unit": t.unit,
            "min": t.min, "max": t.max, "step": t.step,
            "options": t.options, "help": t.help,
        }
        for t in preset.tunables
    ]


def missing_requirements(preset: Preset, condition: dict[str, Any]) -> list[str]:
    """Fields that must be set before this preset may be activated."""
    return [
        key for key in preset.requires_before_active
        if condition.get(key) in (None, [], "")
    ]
