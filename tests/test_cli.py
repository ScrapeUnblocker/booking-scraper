from __future__ import annotations

import csv
import json

import pytest
from conftest import FakeClient, url_params

from booking_scraper.cli import build_parser, main
from booking_scraper.scraper import BookingScraper


def fake_scraper(html):
    client = FakeClient(lambda url, n: html)
    return BookingScraper(client=client, transient_errors=(), sleep=lambda _s: None), client


def test_parser_search_options():
    args = build_parser().parse_args(
        [
            "search",
            "Lisbon",
            "--checkin",
            "2099-03-01",
            "--nights",
            "3",
            "--children-ages",
            "4,8",
            "--stars",
            "4,5",
            "--min-review",
            "8",
            "--type",
            "hotels,apartments",
            "--sort",
            "price",
            "--filter",
            "hotelfacility=107",
            "--limit",
            "60",
            "--split-by-stars",
            "--no-sponsored",
            "-o",
            "out.csv",
        ]
    )
    assert args.command == "search" and args.destination == "Lisbon"
    assert args.children_ages == [4, 8] and args.stars == [4, 5]
    assert args.property_types == ["hotels", "apartments"]
    assert args.filters == ["hotelfacility=107"]
    assert args.limit == 60 and args.split_by_stars and args.no_sponsored
    assert args.country == "US" and args.currency == "USD"


@pytest.mark.parametrize(
    "argv",
    [
        ["search", "Paris", "--limit", "0"],
        ["search", "Paris", "--sort", "cheapest"],
        ["search", "Paris", "--min-review", "5"],
        ["search", "Paris", "--stars", "four"],
        ["filters", "Paris", "--format", "csv"],
        [],
    ],
)
def test_parser_rejects(argv):
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)


def test_main_requires_destination(search_html):
    scraper, _ = fake_scraper(search_html)
    with pytest.raises(SystemExit):
        main(["search", "--checkin", "2099-01-01"], scraper=scraper)


def test_main_search_json_to_stdout(search_html, capsysbinary):
    scraper, client = fake_scraper(search_html)
    code = main(
        ["search", "Paris", "--checkin", "2099-01-10", "--nights", "2", "--stars", "4", "-q"],
        scraper=scraper,
    )
    assert code == 0
    data = json.loads(capsysbinary.readouterr().out.decode("utf-8"))
    assert len(data) == 4 and data[0]["property_id"] == 13286294
    params = url_params(client.calls[0][0])
    assert params["nflt"] == ["class=4"] and params["checkout"] == ["2099-01-12"]


def test_main_search_writes_csv(search_html, tmp_path):
    scraper, _ = fake_scraper(search_html)
    out = tmp_path / "paris.csv"
    code = main(
        ["search", "Paris", "--checkin", "2099-01-10", "--no-sponsored", "-o", str(out), "-q"],
        scraper=scraper,
    )
    assert code == 0
    rows = list(csv.DictReader(out.read_text(encoding="utf-8-sig").splitlines()))
    assert len(rows) == 3  # the sponsored placement was dropped
    assert rows[1]["highlights"] == "Garden; 24-hour front desk"
    assert rows[1]["free_cancellation"] == "true"


def test_main_filters_table(search_html, capsysbinary):
    scraper, _ = fake_scraper(search_html)
    assert main(["filters", "Paris", "--checkin", "2099-01-10", "-q"], scraper=scraper) == 0
    out = capsysbinary.readouterr().out.decode("utf-8")
    assert "Paris - 5501 properties" in out
    assert "hotelfacility=107" in out and "Free Wifi (5182)" in out


def test_main_filters_json(search_html, capsysbinary):
    scraper, _ = fake_scraper(search_html)
    main(["filters", "Paris", "--checkin", "2099-01-10", "--format", "json", "-q"], scraper=scraper)
    groups = json.loads(capsysbinary.readouterr().out.decode("utf-8"))
    assert {g["field"] for g in groups} >= {"ht_id", "class", "review_score"}


def test_main_destination_not_found(not_found_html, capsys):
    scraper, _ = fake_scraper(not_found_html)
    assert main(["search", "Qwxzz", "--checkin", "2099-01-10", "-q"], scraper=scraper) == 2
    assert "could not find" in capsys.readouterr().err


def test_main_url_and_destination_conflict(search_html):
    scraper, _ = fake_scraper(search_html)
    with pytest.raises(SystemExit):
        main(
            ["search", "Paris", "--url", "https://www.booking.com/searchresults.html?ss=Rome"],
            scraper=scraper,
        )
