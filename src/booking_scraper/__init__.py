"""Scrape Booking.com hotel and accommodation search results into clean JSON.

Powered by the ScrapeUnblocker ``getPageSource`` API
(https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos).

Quick start::

    from booking_scraper import BookingScraper

    scraper = BookingScraper()  # reads SCRAPEUNBLOCKER_KEY from the environment
    hotels = scraper.search("Paris", checkin="2026-11-10", nights=2, stars=[4, 5])
    for hotel in hotels:
        print(hotel.name, hotel.review_score, hotel.price, hotel.currency)
"""

from __future__ import annotations

from .models import FilterGroup, FilterOption, Property, SearchPage
from .parsing import (
    BookingError,
    BookingParseError,
    DestinationNotFoundError,
    parse_search_page,
)
from .scraper import BookingScraper, make_query
from .urls import PROPERTY_TYPES, SORTS, SearchQuery, build_filters

__version__ = "0.1.0"

__all__ = [
    "PROPERTY_TYPES",
    "SORTS",
    "BookingError",
    "BookingParseError",
    "BookingScraper",
    "DestinationNotFoundError",
    "FilterGroup",
    "FilterOption",
    "Property",
    "SearchPage",
    "SearchQuery",
    "__version__",
    "build_filters",
    "make_query",
    "parse_search_page",
]
