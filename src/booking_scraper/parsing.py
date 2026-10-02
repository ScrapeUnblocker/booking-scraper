"""Turn a Booking.com results page into :class:`~booking_scraper.models.SearchPage` objects.

Booking.com server-renders its search results page and embeds the data behind
it - every property card, the result count, the available filters and sort
orders - as a JSON store inside a ``<script>`` tag. Reading that store gives
far cleaner data than scraping the visible cards: exact prices with currency,
coordinates, review scores and counts, star ratings and unit details.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .models import FilterGroup, FilterOption, Property, SearchPage
from .urls import SearchQuery, booking_url, property_url

PHOTO_HOST = "https://cf.bstatic.com"

# Booking.com accommodation type ids (``ht_id``) -> singular label.
ACCOMMODATION_TYPES: dict[int, str] = {
    201: "Apartment",
    203: "Hostel",
    204: "Hotel",
    206: "Resort",
    208: "Bed and Breakfast",
    213: "Villa",
    214: "Campground",
    216: "Guesthouse",
    219: "Condo Hotel",
    220: "Vacation Home",
    222: "Homestay",
    226: "Love Hotel",
}

_STORE_RE = re.compile(
    r"<script\b[^>]*\bdata-capla-store-data=[\"']apollo[\"'][^>]*>(.*?)</script>",
    re.S | re.I,
)
# An unknown destination redirects to the home page with this marker in its URLs.
_NOT_FOUND_MARKER = "errorc_searchstring_not_found"
# Filter groups left out of listings: a duplicate of "popular", and "recently used"
# suggestions that depend on browsing history rather than on the search.
_SKIPPED_FILTER_GROUPS = {"popular_sticky", "used_filters"}
# Booking.com's generic caption, shown instead of a score word for some properties.
_GENERIC_REVIEW_CAPTION = "review score"


class BookingError(Exception):
    """Base class for Booking.com scraping errors."""


class BookingParseError(BookingError):
    """The page did not contain search results (e.g. an interstitial). Retryable."""


class DestinationNotFoundError(BookingError):
    """Booking.com could not match the destination text to a place."""


def _get(obj: Any, *path: Any, default: Any = None) -> Any:
    for key in path:
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and isinstance(key, int):
            obj = obj[key] if -len(obj) <= key < len(obj) else None
        else:
            return default
        if obj is None:
            return default
    return obj


def _money(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 2) if value > 0 else None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if value > 0 else None


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def extract_stores(html: str) -> list[dict[str, Any]]:
    """Every JSON data store embedded in the page (usually exactly one)."""
    stores = []
    for match in _STORE_RE.finditer(html or ""):
        try:
            data = json.loads(match.group(1))
        except ValueError:
            continue
        if isinstance(data, dict):
            stores.append(data)
    return stores


def find_search(html: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return ``(search_input, search_result)`` from the page's data store.

    Raises:
        DestinationNotFoundError: Booking.com did not recognise the destination.
        BookingParseError: No search results data on the page.
    """
    for store in extract_stores(html):
        queries = _get(store, "ROOT_QUERY", "searchQueries")
        if not isinstance(queries, dict):
            continue
        for key, value in queries.items():
            if key.startswith("search(") and isinstance(value, dict) and "results" in value:
                try:
                    args = json.loads(key[len("search(") : -1])
                except ValueError:
                    args = {}
                return (_get(args, "input") or {}), value
    if _NOT_FOUND_MARKER in (html or ""):
        raise DestinationNotFoundError("Booking.com could not find that destination")
    raise BookingParseError("no Booking.com search results data found on the page")


def _filter_groups(raw_filters: Any) -> list[FilterGroup]:
    groups = []
    for raw in raw_filters or []:
        field = _get(raw, "field")
        if not field or field in _SKIPPED_FILTER_GROUPS:
            continue
        options = []
        for opt in _get(raw, "options") or []:
            label = _text(_get(opt, "value", "text"))
            url_id = _text(_get(opt, "urlId"))
            if not (label and url_id):
                continue
            options.append(
                FilterOption(
                    filter=url_id,
                    label=label,
                    count=_get(opt, "count"),
                    selected=bool(_get(opt, "selected")),
                )
            )
        if options:
            groups.append(
                FilterGroup(
                    field=field, title=_text(_get(raw, "title", "text")) or field, options=options
                )
            )
    return groups


def parse_property(
    raw: dict[str, Any],
    *,
    position: int | None = None,
    query: SearchQuery | None = None,
    checkin: str | None = None,
    checkout: str | None = None,
    nights: int | None = None,
    destination: str | None = None,
) -> Property | None:
    """Convert one raw search result into a :class:`Property` (``None`` if unusable)."""
    basic = _get(raw, "basicPropertyData") or {}
    prop_id = _get(basic, "id")
    name = _text(_get(raw, "displayName", "text"))
    if not isinstance(prop_id, int) or not name:
        return None

    loc = _get(basic, "location") or {}
    reviews = _get(basic, "reviews") or {}
    external = _get(basic, "externalReviews") or {}
    stars = _get(basic, "starRating") or {}
    units = _get(raw, "matchingUnitConfigurations") or {}
    common = _get(units, "commonConfiguration") or {}
    first_unit = _get(units, "unitConfigurations", 0) or {}
    block = _get(raw, "blocks", 0) or {}
    prices = _get(raw, "priceDisplayInfoIrene") or {}
    policies = _get(raw, "policies") or {}
    persuasion = _get(raw, "persuasion") or {}

    type_id = _get(basic, "accommodationTypeId")
    url = property_url(_get(loc, "countryCode"), _get(basic, "pageName"))

    review_score = _get(reviews, "totalScore") if _get(reviews, "showScore") else None
    review_word = _text(_get(reviews, "totalScoreTextTag", "translation"))
    if review_word and review_word.lower() == _GENERIC_REVIEW_CAPTION:
        review_word = None
    location_score = None
    if _get(reviews, "secondaryTextTag", "tag") == "hotel_location":
        location_score = _get(reviews, "secondaryScore") or None
    ext_score = _get(external, "totalScore") if _get(external, "showScore") else None

    star_value = _get(stars, "value") or None
    star_symbol = _text(_get(stars, "symbol"))
    star_type = (
        star_symbol.lower() if star_symbol and star_symbol != "NONE" and star_value else None
    )

    total = _get(prices, "displayPrice", "amountPerStay") or {}
    price = _money(_get(total, "amountUnformatted"))
    currency = _text(_get(total, "currency"))
    if price is None:  # fall back to the cheapest matching room block
        price = _money(_get(block, "finalPrice", "amount"))
        currency = _text(_get(block, "finalPrice", "currency"))
    per_night = _money(_get(prices, "averagePricePerNight", "amountUnformatted"))
    if per_night is None and price is not None and nights:
        per_night = round(price / nights, 2)
    before = _money(_get(prices, "priceBeforeDiscount", "amountPerStay", "amountUnformatted"))
    if before is not None and (price is None or before <= price):
        before = None
    hotel_curr = _get(prices, "displayPrice", "amountPerStayHotelCurr") or {}
    sold_out = bool(_get(raw, "soldOutInfo", "isSoldOut"))

    deals = [_text(_get(b, "name", "translation")) for b in (_get(prices, "badges") or [])]
    highlights = [_text(_get(b, "translatedName")) for b in (_get(raw, "propertyUspBadges") or [])]
    unit_type = _text(_get(common, "unitTypeNames", 0, "translation")) or _text(
        _get(first_unit, "unitTypeNames", 0, "translation")
    )
    area = _get(common, "localizedArea") or _get(first_unit, "localizedArea") or {}
    photo = _get(basic, "photos", "main", "highResJpegUrl", "relativeUrl") or _get(
        basic, "photos", "main", "highResUrl", "relativeUrl"
    )
    meal_plan = _text(_get(raw, "mealPlanIncluded", "text")) or _text(
        _get(block, "mealPlanIncluded", "text")
    )
    host = _text(_get(raw, "hostTraderLabel"))

    return Property(
        property_id=prop_id,
        name=name,
        url=url,
        booking_url=booking_url(url, query),
        position=position,
        accommodation_type=ACCOMMODATION_TYPES.get(type_id) if isinstance(type_id, int) else None,
        accommodation_type_id=type_id if isinstance(type_id, int) else None,
        room_name=_text(_get(first_unit, "name")),
        unit_type=unit_type,
        bedrooms=_positive_int(_get(common, "nbBedrooms")),
        bathrooms=_positive_int(_get(common, "nbBathrooms")),
        beds=_positive_int(_get(common, "nbAllBeds")),
        area=_text(_get(area, "localizedArea")),
        area_unit=_text(_get(area, "unit")),
        star_rating=star_value,
        star_rating_type=star_type,
        review_score=review_score or None,
        review_word=review_word if review_score else None,
        review_count=_positive_int(_get(reviews, "reviewsCount")),
        location_score=location_score,
        external_review_score=round(ext_score, 1) if ext_score else None,
        external_review_count=_positive_int(_get(external, "reviewsCount")) if ext_score else None,
        address=_text(_get(loc, "address")),
        district=_text(_get(raw, "location", "displayLocation")),
        city=_text(_get(loc, "city")),
        country_code=_text(_get(loc, "countryCode")),
        latitude=_get(loc, "latitude"),
        longitude=_get(loc, "longitude"),
        distance_from_center=_text(_get(raw, "location", "mainDistance")),
        public_transport=_text(_get(raw, "location", "publicTransportDistanceDescription")),
        price=None if sold_out else price,
        price_per_night=None if sold_out else per_night,
        currency=None if sold_out else currency,
        price_before_discount=None if sold_out else before,
        discount=round(before - price, 2) if (before and price and not sold_out) else None,
        taxes_and_fees=_money(
            _get(
                prices,
                "excludedCharges",
                "excludeChargesAggregated",
                "amountPerStay",
                "amountUnformatted",
            )
        ),
        property_currency_price=_money(_get(hotel_curr, "amountUnformatted")),
        property_currency=_text(_get(hotel_curr, "currency")),
        deals=[d for d in deals if d],
        sold_out=sold_out,
        free_cancellation=bool(_get(policies, "showFreeCancellation")),
        free_cancellation_until=_text(_get(block, "freeCancellationUntil")),
        no_prepayment=bool(_get(policies, "showNoPrepayment")),
        meal_plan=meal_plan,
        availability_message=_text(_get(block, "onlyXLeftMessage", "translation")),
        highlights=[h for h in highlights if h],
        preferred_partner=bool(_get(persuasion, "preferred") or _get(persuasion, "preferredPlus")),
        sustainability_certified=bool(_get(raw, "propertySustainability", "isSustainable")),
        sponsored=bool(
            _get(raw, "sponsoredListingData")
            or _get(persuasion, "showNativeAdLabel")
            or _get(raw, "showAdLabel")
        ),
        host_type=host.lower() if host else None,
        photo_url=f"{PHOTO_HOST}{photo}" if photo else None,
        checkin=checkin,
        checkout=checkout,
        destination=destination,
    )


def parse_search_page(html: str, *, url: str, query: SearchQuery | None = None) -> SearchPage:
    """Parse a Booking.com ``searchresults.html`` page.

    Raises:
        DestinationNotFoundError: the destination text matched no place.
        BookingParseError: the page held no search results data.
    """
    _args, search = find_search(html)
    meta = _get(search, "searchMeta") or {}
    dates = _get(meta, "dates") or {}
    checkin = _text(_get(dates, "checkin")) or (query.checkin.isoformat() if query else None)
    checkout = _text(_get(dates, "checkout")) or (query.checkout.isoformat() if query else None)
    nights = _get(dates, "lengthOfStayInDays") or (query.nights if query else None)
    destination = _text(_get(search, "destinationLocation", "name", "text"))
    if destination is None and query is not None:
        destination = query.destination

    properties = []
    for raw in _get(search, "results") or []:
        prop = parse_property(
            raw,
            position=len(properties) + 1,
            query=query,
            checkin=checkin,
            checkout=checkout,
            nights=nights,
            destination=destination,
        )
        if prop is not None:
            properties.append(prop)

    sorts: dict[str, str] = {}
    selected_sort = None
    for sorter in _get(search, "sorters") or []:
        name = _text(_get(sorter, "option", "name"))
        if not name:
            continue
        sorts[name] = _text(_get(sorter, "option", "captionTranslationTag", "translation")) or name
        if _get(sorter, "option", "selected"):
            selected_sort = name

    dest_type = _text(_get(meta, "destType"))
    return SearchPage(
        url=url,
        properties=properties,
        destination=destination,
        dest_id=_get(meta, "destId"),
        dest_type=dest_type.lower() if dest_type else None,
        country_code=_text(_get(search, "destinationLocation", "countryCode")),
        total_results=_get(search, "pagination", "nbResultsTotal"),
        checkin=checkin,
        checkout=checkout,
        nights=nights,
        adults=_get(meta, "nbAdults"),
        rooms=_get(meta, "nbRooms"),
        children_ages=list(_get(meta, "childrenAges") or []),
        sort=selected_sort,
        applied_filters=[
            f
            for f in (_text(_get(o, "urlId")) for o in _get(search, "appliedFilterOptions") or [])
            if f
        ],
        sorts=sorts,
        filters=_filter_groups(_get(search, "filters")),
        breadcrumbs=[
            n for n in (_text(_get(b, "name")) for b in _get(search, "breadcrumbs") or []) if n
        ],
    )
