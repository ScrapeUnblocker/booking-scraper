"""Build and parse Booking.com search URLs.

A :class:`SearchQuery` holds everything that shapes a Booking.com search -
destination, stay dates, guests, currency, sort order and filters - and turns
it into a ``https://www.booking.com/searchresults.html?...`` URL. It can also be
built from a search URL copied out of your browser, so anything you can click
together on the site can be scraped.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from urllib.parse import parse_qsl, urlencode, urlsplit

BASE_URL = "https://www.booking.com"
SEARCH_PATH = "/searchresults.html"

# Booking.com renders 15-25 properties per request; asking for 25 gets the most.
ROWS_PER_REQUEST = 25
# Longest stay Booking.com accepts in one search.
MAX_NIGHTS = 90

# Sort orders offered on the results page (``order=<name>``).
SORTS: dict[str, str] = {
    "popularity": "Our top picks",
    "upsort_bh": "Homes & apartments first",
    "price": "Price (lowest first)",
    "price_from_high_to_low": "Price (highest first)",
    "review_score_and_price": "Best reviewed & lowest price",
    "bayesian_review_score": "Top reviewed",
    "class": "Property rating (high to low)",
    "class_asc": "Property rating (low to high)",
    "class_and_price": "Property rating and price",
    "distance_from_search": "Distance from downtown",
    "business_popularity": "Top picks for business travelers",
}

# Order in which a sweep walks the sort orders to widen coverage. Orders that
# rank the same pool very differently come first.
SWEEP_SORTS: tuple[str, ...] = (
    "popularity",
    "price",
    "bayesian_review_score",
    "price_from_high_to_low",
    "distance_from_search",
    "class",
    "class_asc",
    "review_score_and_price",
    "upsort_bh",
    "class_and_price",
    "business_popularity",
)

# Property types (``ht_id`` filter) -> Booking.com accommodation type id.
PROPERTY_TYPES: dict[str, int] = {
    "hotels": 204,
    "apartments": 201,
    "hostels": 203,
    "resorts": 206,
    "bed-and-breakfasts": 208,
    "villas": 213,
    "campgrounds": 214,
    "guesthouses": 216,
    "condo-hotels": 219,
    "vacation-homes": 220,
    "homestays": 222,
}

# Minimum review score -> ``review_score`` filter value.
REVIEW_SCORES: dict[int, int] = {6: 60, 7: 70, 8: 80, 9: 90}


def _parse_date(value: str | _dt.date, name: str) -> _dt.date:
    if isinstance(value, _dt.date):
        return value
    try:
        return _dt.date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"{name} must be a YYYY-MM-DD date, got {value!r}") from None


def stay_dates(
    checkin: str | _dt.date | None = None,
    checkout: str | _dt.date | None = None,
    *,
    nights: int = 1,
    today: _dt.date | None = None,
) -> tuple[_dt.date, _dt.date]:
    """Resolve check-in/check-out dates.

    ``checkin`` defaults to 30 days from today. ``checkout`` defaults to
    ``checkin + nights``. Raises :class:`ValueError` for past dates, a checkout
    on or before check-in, or stays longer than :data:`MAX_NIGHTS`.
    """
    today = today or _dt.date.today()
    start = _parse_date(checkin, "checkin") if checkin else today + _dt.timedelta(days=30)
    if checkout:
        end = _parse_date(checkout, "checkout")
    else:
        if nights < 1:
            raise ValueError("nights must be at least 1")
        end = start + _dt.timedelta(days=nights)
    if start < today:
        raise ValueError(f"checkin {start} is in the past")
    if end <= start:
        raise ValueError("checkout must be after checkin")
    if (end - start).days > MAX_NIGHTS:
        raise ValueError(f"Booking.com searches are limited to {MAX_NIGHTS} nights")
    return start, end


def price_filter(currency: str, min_price: int | None = None, max_price: int | None = None) -> str:
    """Return the ``price`` filter for a per-night budget, e.g. ``price=USD-100-200-1``."""
    if min_price is None and max_price is None:
        raise ValueError("give min_price, max_price or both")
    low = int(min_price or 0)
    high = "max" if max_price is None else int(max_price)
    if low < 0 or (high != "max" and high <= low):
        raise ValueError("max_price must be greater than min_price")
    return f"price={currency.upper()}-{low}-{high}-1"


def build_filters(
    *,
    stars: Iterable[int] = (),
    min_review: int | None = None,
    property_types: Iterable[str] = (),
    free_cancellation: bool = False,
    no_prepayment: bool = False,
    breakfast: bool = False,
    currency: str = "USD",
    min_price: int | None = None,
    max_price: int | None = None,
    extra: Iterable[str] = (),
) -> list[str]:
    """Translate friendly filter options into Booking.com ``nflt`` filter strings."""
    out: list[str] = []
    for star in stars:
        if int(star) not in range(1, 6):
            raise ValueError(f"stars must be between 1 and 5, got {star!r}")
        out.append(f"class={int(star)}")
    if min_review is not None:
        if int(min_review) not in REVIEW_SCORES:
            raise ValueError(f"min_review must be one of {sorted(REVIEW_SCORES)}")
        out.append(f"review_score={REVIEW_SCORES[int(min_review)]}")
    for name in property_types:
        key = name.strip().lower()
        if key not in PROPERTY_TYPES:
            raise ValueError(
                f"unknown property type {name!r}; choose from {sorted(PROPERTY_TYPES)}"
            )
        out.append(f"ht_id={PROPERTY_TYPES[key]}")
    if free_cancellation:
        out.append("fc=2")
    if no_prepayment:
        out.append("fc=5")
    if breakfast:
        out.append("mealplan=1")
    if min_price is not None or max_price is not None:
        out.append(price_filter(currency, min_price, max_price))
    for item in extra:
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"filters look like key=value (e.g. hotelfacility=107), got {item!r}")
        out.append(item)
    return _dedupe(out)


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


@dataclass(frozen=True)
class SearchQuery:
    """Everything that defines one Booking.com search.

    Args:
        destination: Free-text destination (city, region, landmark, ...).
            Booking.com resolves it the same way its search box does.
        checkin, checkout: Stay dates (``datetime.date``).
        adults, rooms: Party size.
        children_ages: Age of every child (0-17); one entry per child.
        currency: Display currency, e.g. ``"USD"`` or ``"EUR"``.
        language: Site language, e.g. ``"en-us"`` or ``"en-gb"``.
        sort: One of :data:`SORTS` (``None`` = Booking.com's default ranking).
        filters: ``nflt`` filter strings such as ``"class=4"``.
        dest_id, dest_type: Pin the destination to an exact Booking.com id
            (as seen in search URLs) instead of resolving free text.
        extra: Any other query parameters to pass through untouched.
    """

    destination: str | None
    checkin: _dt.date
    checkout: _dt.date
    adults: int = 2
    rooms: int = 1
    children_ages: tuple[int, ...] = ()
    currency: str = "USD"
    language: str = "en-us"
    sort: str | None = None
    filters: tuple[str, ...] = ()
    dest_id: str | None = None
    dest_type: str | None = None
    extra: tuple[tuple[str, str], ...] = field(default=())

    def __post_init__(self) -> None:
        if not (self.destination or self.dest_id):
            raise ValueError("give a destination or a dest_id")
        if self.adults < 1 or self.adults > 30:
            raise ValueError("adults must be between 1 and 30")
        if self.rooms < 1 or self.rooms > 30:
            raise ValueError("rooms must be between 1 and 30")
        if self.rooms > self.adults:
            raise ValueError("every room needs at least one adult")
        for age in self.children_ages:
            if not 0 <= int(age) <= 17:
                raise ValueError(f"children ages must be 0-17, got {age!r}")
        if self.sort is not None and self.sort not in SORTS:
            raise ValueError(f"unknown sort {self.sort!r}; choose from {sorted(SORTS)}")
        if self.checkout <= self.checkin:
            raise ValueError("checkout must be after checkin")

    @property
    def nights(self) -> int:
        return (self.checkout - self.checkin).days

    def with_options(
        self, *, sort: str | None = None, add_filters: Sequence[str] = ()
    ) -> SearchQuery:
        """Copy of this query with another sort order and/or extra filters."""
        return replace(
            self,
            sort=sort if sort is not None else self.sort,
            filters=tuple(_dedupe([*self.filters, *add_filters])),
        )

    def stay_params(self) -> list[tuple[str, str]]:
        """Dates, guests and currency - shared by search and property URLs."""
        params = [
            ("checkin", self.checkin.isoformat()),
            ("checkout", self.checkout.isoformat()),
            ("group_adults", str(self.adults)),
            ("no_rooms", str(self.rooms)),
            ("group_children", str(len(self.children_ages))),
        ]
        params += [("age", str(int(age))) for age in self.children_ages]
        params += [("selected_currency", self.currency.upper()), ("lang", self.language)]
        return params

    def to_url(self) -> str:
        """The ``searchresults.html`` URL for this query."""
        params: list[tuple[str, str]] = []
        if self.destination:
            params.append(("ss", self.destination))
        if self.dest_id:
            params.append(("dest_id", str(self.dest_id)))
            if self.dest_type:
                params.append(("dest_type", self.dest_type.lower()))
        params += self.stay_params()
        params.append(("rows", str(ROWS_PER_REQUEST)))
        if self.sort:
            params.append(("order", self.sort))
        if self.filters:
            params.append(("nflt", ";".join(self.filters)))
        params += list(self.extra)
        return f"{BASE_URL}{SEARCH_PATH}?{urlencode(params)}"

    @classmethod
    def from_url(cls, url: str, *, today: _dt.date | None = None) -> SearchQuery:
        """Build a query from a Booking.com search URL (e.g. copied from a browser).

        Missing dates default like :func:`stay_dates`. Tracking parameters
        (``aid``, ``label``, ``sid``, ...) are dropped; any other unknown
        parameter is kept and passed through.
        """
        parts = urlsplit(url)
        host = parts.netloc.lower()
        if not (host == "booking.com" or host.endswith(".booking.com")):
            raise ValueError(f"not a Booking.com URL: {url!r}")
        if "searchresults" not in parts.path:
            raise ValueError(f"not a Booking.com search results URL: {url!r}")
        qs = parse_qsl(parts.query, keep_blank_values=False)
        known = {
            "ss",
            "dest_id",
            "dest_type",
            "checkin",
            "checkout",
            "group_adults",
            "no_rooms",
            "group_children",
            "age",
            "selected_currency",
            "lang",
            "order",
            "nflt",
            "rows",
            "offset",
        }
        tracking = {"aid", "label", "sid", "srpvid", "sb", "src", "src_elem", "chal_t"}
        tracking |= {"force_referer", "ac_position", "ac_langcode", "ac_click_type"}
        values: dict[str, str] = {}
        ages: list[int] = []
        extra: list[tuple[str, str]] = []
        for key, value in qs:
            if key == "age":
                ages.append(int(value))
            elif key in known:
                values[key] = value
            elif key not in tracking:
                extra.append((key, value))
        checkin, checkout = stay_dates(values.get("checkin"), values.get("checkout"), today=today)
        filters = tuple(f for f in values.get("nflt", "").split(";") if f)
        return cls(
            destination=values.get("ss") or None,
            checkin=checkin,
            checkout=checkout,
            adults=int(values.get("group_adults", 2)),
            rooms=int(values.get("no_rooms", 1)),
            children_ages=tuple(ages),
            currency=values.get("selected_currency", "USD"),
            language=values.get("lang", "en-us"),
            sort=values.get("order") or None,
            filters=filters,
            dest_id=values.get("dest_id") or None,
            dest_type=values.get("dest_type") or None,
            extra=tuple(extra),
        )


def property_url(country_code: str | None, page_name: str | None) -> str | None:
    """Canonical property page URL, e.g. ``https://www.booking.com/hotel/fr/muguet.html``."""
    if not (country_code and page_name):
        return None
    return f"{BASE_URL}/hotel/{country_code.lower()}/{page_name}.html"


def booking_url(base: str | None, query: SearchQuery | None) -> str | None:
    """Property URL with the stay dates and guests filled in, ready to book."""
    if not base or query is None:
        return base
    return f"{base}?{urlencode(query.stay_params())}"
