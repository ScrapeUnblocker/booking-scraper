from __future__ import annotations

import pytest
from conftest import FakeClient, make_page, make_result, url_params

from booking_scraper.parsing import DestinationNotFoundError
from booking_scraper.scraper import BookingScraper, make_query
from booking_scraper.urls import SearchQuery


class Transient(Exception):
    pass


def make_scraper(responder, **kwargs):
    client = FakeClient(responder)
    kwargs.setdefault("transient_errors", (Transient,))
    scraper = BookingScraper(client=client, sleep=lambda _s: None, **kwargs)
    return scraper, client


def by_sort(pages: dict[str, list[int]], total: int = 500):
    """Responder serving a page of property ids per sort order."""

    def responder(url, _n):
        sort = url_params(url).get("order", ["popularity"])[0]
        return make_page([make_result(i) for i in pages.get(sort, [])], total=total, sort=sort)

    return responder


@pytest.fixture
def query(stay):
    return SearchQuery("Testville", *stay)


def test_fetch_page_uses_proxy_country(search_html, query):
    scraper, client = make_scraper(lambda url, n: search_html, proxy_country="GB")
    page = scraper.fetch_page(query)
    assert len(page.properties) == 4
    assert client.calls[0] == (query.to_url(), "GB")


def test_retries_transient_errors_with_backoff(search_html, query):
    delays = []
    responses = [Transient("timeout"), "<html>interstitial</html>", search_html]
    scraper, client = make_scraper(
        lambda url, n: responses[n - 1],
        on_retry=lambda attempt, delay, exc: delays.append((attempt, delay, type(exc).__name__)),
        backoff=2,
    )
    page = scraper.fetch_page(query)
    assert len(page.properties) == 4
    assert delays == [(1, 2.0, "Transient"), (2, 4.0, "BookingParseError")]
    assert len(client.calls) == 3


def test_gives_up_after_retries(query):
    scraper, client = make_scraper(lambda url, n: Transient("down"), retries=2)
    with pytest.raises(Transient):
        scraper.fetch_page(query)
    assert len(client.calls) == 3


def test_non_transient_error_is_not_retried(query):
    scraper, client = make_scraper(lambda url, n: RuntimeError("bad key"))
    with pytest.raises(RuntimeError):
        scraper.fetch_page(query)
    assert len(client.calls) == 1


def test_destination_not_found_is_not_retried(not_found_html, query):
    scraper, client = make_scraper(lambda url, n: not_found_html)
    with pytest.raises(DestinationNotFoundError):
        scraper.fetch_page(query)
    assert len(client.calls) == 1


def test_single_request_when_limit_reached(query):
    scraper, client = make_scraper(by_sort({"popularity": list(range(1, 26))}))
    props = scraper.search_query(query, limit=10)
    assert [p.property_id for p in props] == list(range(1, 11))
    assert len(client.calls) == 1


def test_sweep_dedupes_across_sort_orders(query):
    pages = {"popularity": [1, 2, 3], "price": [3, 4, 5], "bayesian_review_score": [5, 6, 1]}
    scraper, client = make_scraper(by_sort(pages))
    props = scraper.search_query(query, limit=6)
    assert [p.property_id for p in props] == [1, 2, 3, 4, 5, 6]
    sorts = [url_params(u).get("order", [None])[0] for u, _ in client.calls]
    assert sorts == ["popularity", "price", "bayesian_review_score"]


def test_no_sweep_makes_one_request(query):
    scraper, client = make_scraper(by_sort({"popularity": [1, 2], "price": [3, 4]}))
    props = scraper.search_query(query, limit=10, sweep=False)
    assert [p.property_id for p in props] == [1, 2]
    assert len(client.calls) == 1


def test_query_sort_goes_first(stay):
    query = SearchQuery("Testville", *stay, sort="price")
    scraper, client = make_scraper(by_sort({"price": [1], "popularity": [2]}))
    scraper.search_query(query, limit=2, sorts=["popularity", "price"])
    sorts = [url_params(u)["order"][0] for u, _ in client.calls]
    assert sorts == ["price", "popularity"]


def test_stops_when_everything_fits_on_one_page(query):
    scraper, client = make_scraper(by_sort({"popularity": [1, 2, 3]}, total=3))
    props = scraper.search_query(query, limit=50)
    assert len(props) == 3
    assert len(client.calls) == 1


def test_max_requests_caps_the_sweep(query):
    pages = {
        s: [i * 10 + k for k in range(3)] for i, s in enumerate(["popularity", "price", "class"])
    }
    scraper, client = make_scraper(by_sort(pages))
    scraper.search_query(query, limit=100, max_requests=2)
    assert len(client.calls) == 2


def test_split_by_stars_adds_class_filters(query):
    def responder(url, n):
        params = url_params(url)
        nflt = params.get("nflt", [""])[0]
        star = int(nflt.split("=")[1]) if nflt.startswith("class=") else 0
        # each star class has exactly two properties -> one request per class
        ids = [star * 100 + 1, star * 100 + 2] if star else [1, 2]
        return make_page([make_result(i) for i in ids], total=2 if star else 900)

    scraper, client = make_scraper(responder)
    props = scraper.search_query(
        query, limit=100, split_by_stars=True, sorts=["popularity", "price"]
    )
    assert len(props) == 12  # unsplit page + 5 star classes x 2
    nflts = [url_params(u).get("nflt", [""])[0] for u, _ in client.calls]
    assert nflts == ["", "class=5", "class=4", "class=3", "class=2", "class=1"]


def test_split_by_stars_conflicts_with_star_filter(stay):
    query = SearchQuery("Testville", *stay, filters=("class=4",))
    scraper, _ = make_scraper(by_sort({}))
    with pytest.raises(ValueError):
        scraper.search_query(query, split_by_stars=True)


def test_sponsored_can_be_excluded(query):
    def responder(url, n):
        return make_page([make_result(1, sponsored=True), make_result(2)], total=2)

    scraper, _ = make_scraper(responder)
    assert [p.property_id for p in scraper.search_query(query)] == [1, 2]
    assert [p.property_id for p in scraper.search_query(query, include_sponsored=False)] == [2]


def test_shared_seen_set_dedupes_across_calls(query):
    scraper, _ = make_scraper(by_sort({"popularity": [1, 2, 3]}, total=3))
    seen: set[int] = set()
    first = scraper.search_query(query, seen=seen)
    second = scraper.search_query(query, seen=seen)
    assert len(first) == 3 and second == []


def test_on_page_callback(query):
    pages = []
    scraper, _ = make_scraper(by_sort({"popularity": [1]}, total=1))
    scraper.search_query(query, on_page=pages.append)
    assert len(pages) == 1 and pages[0].destination == "Testville"


def test_search_builds_query_from_options():
    scraper, client = make_scraper(by_sort({"popularity": [1]}, total=1))
    scraper.search(
        "Testville",
        checkin="2099-05-01",
        nights=3,
        stars=[5],
        min_review=9,
        currency="eur",
        max_price=300,
    )
    params = url_params(client.calls[0][0])
    assert params["checkout"] == ["2099-05-04"]
    assert params["selected_currency"] == ["EUR"]
    assert params["nflt"] == ["class=5;review_score=90;price=EUR-0-300-1"]


def test_search_accepts_a_url():
    scraper, client = make_scraper(by_sort({"popularity": [1]}, total=1))
    scraper.search(url="https://www.booking.com/searchresults.html?ss=Oslo&checkin=2099-01-02")
    params = url_params(client.calls[0][0])
    assert params["ss"] == ["Oslo"] and params["checkout"] == ["2099-01-03"]
    with pytest.raises(ValueError):
        scraper.search("Oslo", url="https://www.booking.com/searchresults.html?ss=Oslo")


def test_filters_returns_groups(search_html):
    scraper, _ = make_scraper(lambda url, n: search_html)
    groups = scraper.filters("Paris", checkin="2099-01-02")
    assert any(g.field == "hotelfacility" for g in groups)


def test_invalid_limits(query):
    scraper, _ = make_scraper(by_sort({}))
    with pytest.raises(ValueError):
        scraper.search_query(query, limit=0)
    with pytest.raises(ValueError):
        scraper.search_query(query, max_requests=0)


def test_make_query_validates():
    with pytest.raises(ValueError):
        make_query("Paris", checkin="2001-01-01")
    with pytest.raises(ValueError):
        make_query("Paris", checkin="2099-01-01", property_types=["igloo"])
