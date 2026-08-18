from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class PlannerModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class EventInfo(PlannerModel):
    event_id: str = Field(min_length=1)
    name: str
    day: int | None = None
    event_date: str | None = None
    map_source_id: str | None = None


class PurchaseItem(PlannerModel):
    item_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    variant: str | None = None
    price: StrictInt | None = Field(default=None, ge=0)
    currency: str = "JPY"
    purchase_state: Literal["buy", "candidate", "skip"]
    availability: Literal["unknown", "available", "sold_out"] = "unknown"
    age_rating: str = "unknown"
    bundle_components: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)


class CircleVisit(PlannerModel):
    visit_id: str = Field(min_length=1)
    circle_name: str = Field(min_length=1)
    creator_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    x_user_id: str | None = None
    x_handle: str | None = None
    x_url: str | None = None
    x_display_name: str | None = None
    event_day: int | None = Field(default=None, ge=1, le=2)
    space_code: str | None = None
    hall: str | None = None
    placement_type: Literal["shutter_front", "wall", "island_end", "island", "unknown"]
    priority: Literal["A", "B", "C", "unassigned"]
    genre_short: str = ""
    visit_status: Literal["unvisited", "purchased", "sold_out", "skipped"]
    notes: str = ""
    items: list[PurchaseItem] = Field(default_factory=list)
    field_meta: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    circle_name_confirmed: bool = False


class Budget(PlannerModel):
    planned_total: StrictInt = Field(ge=0)
    max_total: StrictInt = Field(ge=0)
    unknown_price_buy_count: StrictInt = Field(ge=0)
    unknown_price_candidate_count: StrictInt = Field(ge=0)
    unknown_price_items: list[dict[str, str]] = Field(default_factory=list)


class EventPlan(PlannerModel):
    schema_version: str
    event: EventInfo
    circles: list[CircleVisit]
    budget: Budget
    generated_at: str | None = None
