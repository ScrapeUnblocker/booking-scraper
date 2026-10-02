"""Shared fixtures: saved Booking.com pages and a fake ScrapeUnblocker client."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def make_result(prop_id: int, name: str | None = None, *, sponsored: bool = False) -> dict:
    """A minimal raw search result as Booking.com embeds it."""
    return {
        "basicPropertyData": {
            "id": prop_id,
            "accommodationTypeId": 204,
            "pageName": f"hotel-{prop_id}",
            "location": {"city": "Testville", "countryCode": "fr"},
            "reviews": {"showScore": True, "totalScore": 8.0, "reviewsCount": 10},
        },
        "displayName": {"text": name or f"Hotel {prop_id}"},
        "persuasion": {"showNativeAdLabel": sponsored},
        "priceDisplayInfoIrene": {
            "displayPrice": {
                "amountPerStay": {"amountUnformatted": 100.0 + prop_id, "currency": "USD"}
            }
        },
    }


def make_page(results: list[dict], *, total: int | None = None, sort: str = "popularity") -> str:
    """A minimal results page with an embedded data store."""
    search = {
        "results": results,
        "pagination": {"nbResultsTotal": len(results) if total is None else total},
        "destinationLocation": {"name": {"text": "Testville"}, "countryCode": "fr"},
        "searchMeta": {"destId": -1, "destType": "CITY", "nbAdults": 2, "nbRooms": 1},
        "sorters": [{"option": {"name": sort, "selected": True}}],
        "filters": [],
    }
    store = {"ROOT_QUERY": {"searchQueries": {'search({"input":{}})': search}}}
    return (
        '<html><body><script data-capla-store-data="apollo" type="application/json">'
        + json.dumps(store)
        + "</script></body></html>"
    )


class FakeClient:
    """Stands in for ``scrapeunblocker.Client``; serves pages by sort/filter."""

    def __init__(self, responder):
        self.responder = responder
        self.calls: list[tuple[str, str | None]] = []

    def get_page_source(self, url: str, proxy_country: str | None = None):
        self.calls.append((url, proxy_country))
        result = self.responder(url, len(self.calls))
        if isinstance(result, BaseException):
            raise result
        return result


def url_params(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


@pytest.fixture
def search_html() -> str:
    return load_fixture("search_paris.html")


@pytest.fixture
def not_found_html() -> str:
    return load_fixture("destination_not_found.html")


@pytest.fixture
def stay() -> tuple[dt.date, dt.date]:
    return dt.date(2026, 11, 10), dt.date(2026, 11, 12)
