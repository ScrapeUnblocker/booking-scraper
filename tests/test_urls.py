from __future__ import annotations

import datetime as dt

import pytest
from conftest import url_params

from booking_scraper.urls import (
    SearchQuery,
    booking_url,
    build_filters,
    price_filter,
    property_url,
    stay_dates,
)

TODAY = dt.date(2026, 10, 1)


def test_stay_dates_defaults():
    assert stay_dates(today=TODAY) == (dt.date(2026, 10, 31), dt.date(2026, 11, 1))
    assert stay_dates("2026-11-10", nights=3, today=TODAY) == (
        dt.date(2026, 11, 10),
        dt.date(2026, 11, 13),
    )
    assert stay_dates("2026-11-10", "2026-11-12", nights=9, today=TODAY)[1] == dt.date(2026, 11, 12)


@pytest.mark.parametrize(
    "checkin, checkout, nights",
    [
        ("2026-09-01", None, 1),  # past
        ("2026-11-10", "2026-11-10", 1),  # zero nights
        ("2026-11-10", None, 0),
        ("2026-11-10", None, 91),  # longer than Booking.com allows
        ("10/11/2026", None, 1),  # wrong format
    ],
)
def test_stay_dates_rejects(checkin, checkout, nights):
    with pytest.raises(ValueError):
        stay_dates(checkin, checkout, nights=nights, today=TODAY)


def test_build_filters():
    filters = build_filters(
        stars=[4, 5],
        min_review=8,
        property_types=["hotels", "Apartments"],
        free_cancellation=True,
        breakfast=True,
        currency="eur",
        max_price=200,
        extra=["hotelfacility=107", "class=4"],
    )
    assert filters == [
        "class=4",
        "class=5",
        "review_score=80",
        "ht_id=204",
        "ht_id=201",
        "fc=2",
        "mealplan=1",
        "price=EUR-0-200-1",
        "hotelfacility=107",
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"stars": [6]},
        {"min_review": 5},
        {"property_types": ["castles"]},
        {"extra": ["wifi"]},
    ],
)
def test_build_filters_rejects(kwargs):
    with pytest.raises(ValueError):
        build_filters(**kwargs)


def test_price_filter():
    assert price_filter("usd", 100, 250) == "price=USD-100-250-1"
    assert price_filter("USD", min_price=80) == "price=USD-80-max-1"
    with pytest.raises(ValueError):
        price_filter("USD")
    with pytest.raises(ValueError):
        price_filter("USD", 300, 100)


def test_query_to_url(stay):
    query = SearchQuery(
        "Lisbon",
        *stay,
        adults=3,
        children_ages=(5, 9),
        currency="EUR",
        sort="price",
        filters=("class=4", "review_score=80"),
    )
    params = url_params(query.to_url())
    assert query.to_url().startswith("https://www.booking.com/searchresults.html?")
    assert params["ss"] == ["Lisbon"]
    assert params["checkin"] == ["2026-11-10"] and params["checkout"] == ["2026-11-12"]
    assert params["group_adults"] == ["3"] and params["group_children"] == ["2"]
    assert params["age"] == ["5", "9"]
    assert params["selected_currency"] == ["EUR"]
    assert params["order"] == ["price"]
    assert params["nflt"] == ["class=4;review_score=80"]
    assert params["rows"] == ["25"]
    assert "nflt=class%3D4%3Breview_score%3D80" in query.to_url()
    assert query.nights == 2


def test_query_with_options_does_not_mutate(stay):
    query = SearchQuery("Rome", *stay, filters=("fc=2",))
    other = query.with_options(sort="class", add_filters=["class=5", "fc=2"])
    assert other.sort == "class" and other.filters == ("fc=2", "class=5")
    assert query.sort is None and query.filters == ("fc=2",)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"destination": None},
        {"adults": 0},
        {"rooms": 3, "adults": 2},
        {"children_ages": (18,)},
        {"sort": "cheapest"},
    ],
)
def test_query_validation(stay, kwargs):
    base = {"destination": "Rome"}
    base.update(kwargs)
    with pytest.raises(ValueError):
        SearchQuery(checkin=stay[0], checkout=stay[1], **base)


def test_query_from_url_round_trip():
    url = (
        "https://www.booking.com/searchresults.en-gb.html?aid=123&label=abc&ss=Paris"
        "&dest_id=-1456928&dest_type=city&checkin=2026-11-10&checkout=2026-11-13"
        "&group_adults=2&no_rooms=1&group_children=1&age=7&selected_currency=GBP"
        "&order=price&nflt=class%3D4%3Bfc%3D2&offset=25&map=1"
    )
    query = SearchQuery.from_url(url, today=TODAY)
    assert query.destination == "Paris"
    assert (query.dest_id, query.dest_type) == ("-1456928", "city")
    assert (query.checkin, query.checkout) == (dt.date(2026, 11, 10), dt.date(2026, 11, 13))
    assert query.children_ages == (7,)
    assert query.currency == "GBP" and query.sort == "price"
    assert query.filters == ("class=4", "fc=2")
    assert query.extra == (("map", "1"),)  # tracking params dropped, unknown kept
    params = url_params(query.to_url())
    assert "aid" not in params and "label" not in params and "offset" not in params
    assert params["map"] == ["1"]


@pytest.mark.parametrize(
    "url",
    [
        "https://www.example.com/searchresults.html?ss=Paris",
        "https://www.booking.com/hotel/fr/muguet.html",
    ],
)
def test_query_from_url_rejects(url):
    with pytest.raises(ValueError):
        SearchQuery.from_url(url, today=TODAY)


def test_property_urls(stay):
    assert property_url("FR", "muguet") == "https://www.booking.com/hotel/fr/muguet.html"
    assert property_url(None, "muguet") is None
    url = booking_url("https://www.booking.com/hotel/fr/muguet.html", SearchQuery("Paris", *stay))
    assert url.endswith(
        "?checkin=2026-11-10&checkout=2026-11-12&group_adults=2&no_rooms=1"
        "&group_children=0&selected_currency=USD&lang=en-us"
    )
