"""The preset rule catalogue — the single source of truth for what a user may tune.

Users do not author rules here; they switch presets on and off and adjust a
handful of numbers. That constraint is what makes the evaluator safe: it only
ever runs conditions it defined itself, so there is no free-form JSON to
interpret and no way for a client to describe something the engine cannot
compute.

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

# The three departure-horizon buckets. DA's feed carries exactly 30 days of
# departures per capture, so these cover it without a remainder. They are a
# closed set: an unknown bucket string is a validation error, not a new bucket.
WINDOWS = ("00-07", "08-14", "15-30")
WindowLiteral = Literal["00-07", "08-14", "15-30"]


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
    windows: list[WindowLiteral] = Field(default_factory=lambda: list(WINDOWS), min_length=1)
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
    windows: list[WindowLiteral] = Field(default_factory=lambda: list(WINDOWS), min_length=1)
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


_WINDOW_TUNABLE = Tunable(
    key="windows", label="Departure windows", type="multiselect",
    options=list(WINDOWS),
    help="How far ahead of departure to watch, in days.",
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
            Tunable("routes", "on routes", "multiselect"),
            Tunable("competitors", "Competitors", "multiselect",
                    help="Leave empty to watch every competitor."),
            _WINDOW_TUNABLE,
        ],
        requires_before_active=("value", "routes"),
    ),
}

# Evaluation order. Position changes are the more actionable signal, so they are
# emitted first and read first when several land on the same capture.
PRESET_ORDER = ("undercut_position", "comp_price_move", "comp_price_threshold")


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
