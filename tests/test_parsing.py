from __future__ import annotations

import json

import pytest
from conftest import make_page, make_result

from booking_scraper.parsing import (
    BookingParseError,
    DestinationNotFoundError,
    extract_stores,
    parse_property,
    parse_search_page,
)
from booking_scraper.urls import SearchQuery


@pytest.fixture
def page(search_html, stay):
    query = SearchQuery("Paris", *stay)
    return parse_search_page(
        search_html, url="https://www.booking.com/searchresults.html", query=query
    )


def test_page_metadata(page):
    assert page.destination == "Paris"
    assert page.dest_id == -1456928
    assert page.dest_type == "city"
    assert page.country_code == "fr"
    assert page.total_results == 5501
    assert (page.checkin, page.checkout, page.nights) == ("2026-11-10", "2026-11-12", 2)
    assert (page.adults, page.rooms, page.children_ages) == (2, 1, [])
    assert page.sort == "popularity"
    assert page.breadcrumbs == ["France", "Ile de France", "Paris"]
    assert page.sorts["bayesian_review_score"] == "Top reviewed"
    assert len(page.properties) == 4


def test_apartment_fields(page):
    apt = page.properties[0]
    assert apt.property_id == 13286294
    assert apt.position == 1
    assert apt.accommodation_type == "Apartment"
    assert (
        apt.url == "https://www.booking.com/hotel/fr/magnificent-apartment-2bd-6p-belleville.html"
    )
    assert apt.booking_url.startswith(apt.url + "?checkin=2026-11-10&checkout=2026-11-12")
    assert (apt.unit_type, apt.bedrooms, apt.bathrooms, apt.beds) == ("Entire apartment", 2, 1, 3)
    assert (apt.area, apt.area_unit) == ("1,399", "ft\u00b2")
    assert (apt.review_score, apt.review_word, apt.review_count) == (8.5, "Very Good", 17)
    assert (apt.external_review_score, apt.external_review_count) == (9.7, 7)
    assert apt.address is None
    assert apt.district == "20th arr., Paris"
    assert apt.latitude == pytest.approx(48.8652)


def test_prices_and_discount(page):
    apt = page.properties[0]
    assert (apt.price, apt.currency) == (531.41, "USD")
    assert apt.price_per_night == 183.38
    assert apt.price_before_discount == 814.24
    assert apt.discount == 282.83
    assert apt.taxes_and_fees == 11.72
    assert (apt.property_currency_price, apt.property_currency) == (471.73, "EUR")
    assert apt.deals == ["Limited-time Deal"]


def test_per_night_falls_back_to_total_over_nights(page):
    muguet = page.properties[2]
    assert muguet.price == 360.48
    assert muguet.price_per_night == 180.24


def test_hotel_flags(page):
    sponsored, muguet, belleclaire = page.properties[1], page.properties[2], page.properties[3]
    assert sponsored.sponsored is True
    assert sponsored.location_score == 9.4
    assert sponsored.room_name == "Alcove Room with One Queen Bed"
    assert sponsored.preferred_partner and sponsored.sustainability_certified
    assert muguet.free_cancellation is True
    assert muguet.free_cancellation_until == "2026-11-07T23:00:00Z"
    assert muguet.availability_message == "We have 4 left at this price"
    assert muguet.highlights == ["Garden", "24-hour front desk"]
    assert muguet.photo_url.startswith("https://cf.bstatic.com/xdata/images/hotel/")
    assert belleclaire.meal_plan == "Breakfast included"
    assert belleclaire.sponsored is False


def test_filter_groups(page):
    fields = [g.field for g in page.filters]
    assert "popular_sticky" not in fields  # duplicate group dropped
    assert "price" not in fields  # slider without options
    rating = next(g for g in page.filters if g.field == "class")
    assert rating.title == "Property rating"
    assert rating.options[3].filter == "class=4"
    assert rating.options[3].label == "4 stars"
    assert rating.options[3].count == 2802


def test_destination_not_found(not_found_html):
    with pytest.raises(DestinationNotFoundError):
        parse_search_page(not_found_html, url="u")


def test_page_without_data_is_parse_error():
    with pytest.raises(BookingParseError):
        parse_search_page("<html><body>Please wait...</body></html>", url="u")


def test_broken_store_is_skipped():
    html = '<script data-capla-store-data="apollo">{not json</script>'
    assert extract_stores(html) == []


def test_minimal_result_and_unusable_rows():
    prop = parse_property(make_result(7), position=1)
    assert prop.name == "Hotel 7"
    assert prop.url == "https://www.booking.com/hotel/fr/hotel-7.html"
    assert prop.booking_url == prop.url  # no query -> no stay parameters
    assert parse_property({"displayName": {"text": "No id"}}) is None
    assert parse_property({"basicPropertyData": {"id": 5}}) is None


def test_sold_out_has_no_price():
    raw = make_result(9)
    raw["soldOutInfo"] = {"isSoldOut": True}
    prop = parse_property(raw)
    assert prop.sold_out is True
    assert prop.price is None and prop.currency is None


def test_hidden_review_score():
    raw = make_result(3)
    raw["basicPropertyData"]["reviews"] = {"showScore": False, "totalScore": 6.0, "reviewsCount": 2}
    prop = parse_property(raw)
    assert prop.review_score is None
    assert prop.review_count == 2


def test_empty_results_page():
    page = parse_search_page(make_page([], total=0), url="u")
    assert page.properties == []
    assert page.total_results == 0


def test_history_based_filter_groups_are_skipped():
    def group(field, url_id):
        return {
            "field": field,
            "title": {"text": field},
            "options": [{"urlId": url_id, "value": {"text": url_id}, "count": 1}],
        }

    groups = [group("used_filters", "class=4"), group("class", "class=5")]
    html = make_page([make_result(1)]).replace(
        '"filters": []', json.dumps({"filters": groups})[1:-1]
    )
    page = parse_search_page(html, url="u")
    assert [g.field for g in page.filters] == ["class"]
