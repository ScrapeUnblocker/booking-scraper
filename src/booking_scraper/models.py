"""Data classes returned by the scraper."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Property:
    """One property (hotel, apartment, hostel, ...) from a Booking.com search."""

    property_id: int
    name: str
    url: str | None = None
    booking_url: str | None = None
    position: int | None = None
    accommodation_type: str | None = None
    accommodation_type_id: int | None = None
    room_name: str | None = None
    unit_type: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    beds: int | None = None
    area: str | None = None
    area_unit: str | None = None
    star_rating: float | None = None
    star_rating_type: str | None = None
    review_score: float | None = None
    review_word: str | None = None
    review_count: int | None = None
    location_score: float | None = None
    external_review_score: float | None = None
    external_review_count: int | None = None
    address: str | None = None
    district: str | None = None
    city: str | None = None
    country_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance_from_center: str | None = None
    public_transport: str | None = None
    price: float | None = None
    price_per_night: float | None = None
    currency: str | None = None
    price_before_discount: float | None = None
    discount: float | None = None
    taxes_and_fees: float | None = None
    property_currency_price: float | None = None
    property_currency: str | None = None
    deals: list[str] = field(default_factory=list)
    sold_out: bool = False
    free_cancellation: bool = False
    free_cancellation_until: str | None = None
    no_prepayment: bool = False
    meal_plan: str | None = None
    availability_message: str | None = None
    highlights: list[str] = field(default_factory=list)
    preferred_partner: bool = False
    sustainability_certified: bool = False
    sponsored: bool = False
    host_type: str | None = None
    photo_url: str | None = None
    checkin: str | None = None
    checkout: str | None = None
    destination: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FilterOption:
    """One option in a Booking.com filter group, usable as ``--filter <filter>``."""

    filter: str
    label: str
    count: int | None = None
    selected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FilterGroup:
    """A filter group on the results page (property type, amenities, ...)."""

    field: str
    title: str
    options: list[FilterOption] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "title": self.title,
            "options": [o.to_dict() for o in self.options],
        }


@dataclass
class SearchPage:
    """One fetched results page: the properties plus the search's own metadata."""

    url: str
    properties: list[Property] = field(default_factory=list)
    destination: str | None = None
    dest_id: int | None = None
    dest_type: str | None = None
    country_code: str | None = None
    total_results: int | None = None
    checkin: str | None = None
    checkout: str | None = None
    nights: int | None = None
    adults: int | None = None
    rooms: int | None = None
    children_ages: list[int] = field(default_factory=list)
    sort: str | None = None
    applied_filters: list[str] = field(default_factory=list)
    sorts: dict[str, str] = field(default_factory=dict)
    filters: list[FilterGroup] = field(default_factory=list)
    breadcrumbs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["properties"] = [p.to_dict() for p in self.properties]
        data["filters"] = [g.to_dict() for g in self.filters]
        return data
