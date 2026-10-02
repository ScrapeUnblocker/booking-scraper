"""Command line interface: ``booking-scraper search`` and ``booking-scraper filters``."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from . import __version__
from .export import FORMATS, format_for, render, write
from .parsing import BookingError, DestinationNotFoundError
from .scraper import DEFAULT_PROXY_COUNTRY, BookingScraper, make_query
from .urls import PROPERTY_TYPES, REVIEW_SCORES, SORTS, SearchQuery

EPILOG = """examples:
  booking-scraper search "Paris" --checkin 2026-11-10 --nights 2
  booking-scraper search "Lisbon" --stars 4,5 --min-review 8 --sort price -o lisbon.csv
  booking-scraper search "New York" --limit 100 --max-price 250 --free-cancellation
  booking-scraper search --url "https://www.booking.com/searchresults.html?ss=Rome&..."
  booking-scraper filters "Barcelona"
"""


def _int_list(value: str) -> list[int]:
    try:
        return [int(v) for v in value.split(",") if v.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected comma-separated numbers, got {value!r}"
        ) from None


def _str_list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _query_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "destination", nargs="?", help='where to stay, e.g. "Paris" or "Lake Tahoe"'
    )
    parser.add_argument("--url", help="a Booking.com search results URL to scrape instead")
    parser.add_argument("--checkin", help="check-in date YYYY-MM-DD (default: 30 days from today)")
    parser.add_argument("--checkout", help="check-out date YYYY-MM-DD (default: checkin + nights)")
    parser.add_argument("--nights", type=_positive, default=1, help="length of stay (default 1)")
    parser.add_argument("--adults", type=_positive, default=2, help="number of adults (default 2)")
    parser.add_argument("--rooms", type=_positive, default=1, help="number of rooms (default 1)")
    parser.add_argument(
        "--children-ages",
        type=_int_list,
        default=[],
        metavar="AGES",
        help="ages of the children, comma-separated, e.g. 5,9",
    )
    parser.add_argument("--currency", default="USD", help="price currency (default USD)")
    parser.add_argument("--lang", default="en-us", help="site language (default en-us)")
    parser.add_argument("--dest-id", help="exact Booking.com destination id (from a search URL)")
    parser.add_argument("--dest-type", help="destination type for --dest-id, e.g. city or region")
    parser.add_argument(
        "--country",
        default=DEFAULT_PROXY_COUNTRY,
        help=f"country to route requests through (default {DEFAULT_PROXY_COUNTRY})",
    )
    parser.add_argument("--retries", type=int, default=3, help="retries per request (default 3)")
    parser.add_argument("-q", "--quiet", action="store_true", help="no progress output on stderr")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="booking-scraper",
        description="Scrape Booking.com search results into JSON/CSV via ScrapeUnblocker.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="scrape properties for a destination and dates")
    _query_args(search)
    search.add_argument("--sort", choices=sorted(SORTS), help="sort order (default: top picks)")
    search.add_argument("--stars", type=_int_list, default=[], help="star ratings, e.g. 4,5")
    search.add_argument(
        "--min-review", type=int, choices=sorted(REVIEW_SCORES), help="minimum review score"
    )
    search.add_argument(
        "--type",
        dest="property_types",
        type=_str_list,
        default=[],
        metavar="TYPES",
        help="property types, comma-separated: " + ", ".join(PROPERTY_TYPES),
    )
    search.add_argument("--min-price", type=int, help="minimum price per night (in --currency)")
    search.add_argument("--max-price", type=int, help="maximum price per night (in --currency)")
    search.add_argument("--free-cancellation", action="store_true")
    search.add_argument("--no-prepayment", action="store_true")
    search.add_argument("--breakfast", action="store_true", help="breakfast included")
    search.add_argument(
        "--filter",
        dest="filters",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="raw Booking.com filter (see the 'filters' command); repeatable",
    )
    search.add_argument(
        "--limit", type=_positive, default=25, help="max properties to return (default 25)"
    )
    search.add_argument(
        "--no-sweep",
        action="store_true",
        help="make a single request instead of sweeping sort orders to reach --limit",
    )
    search.add_argument(
        "--split-by-stars",
        action="store_true",
        help="also sweep one star class at a time (more properties, more requests)",
    )
    search.add_argument("--max-requests", type=_positive, help="hard cap on requests")
    search.add_argument("--no-sponsored", action="store_true", help="drop sponsored placements")
    search.add_argument("-o", "--output", help="write to a file (.json, .jsonl or .csv)")
    search.add_argument(
        "--format", choices=FORMATS, help="output format (default: from -o, else json)"
    )

    filters = sub.add_parser("filters", help="list the filters Booking.com offers for a search")
    _query_args(filters)
    filters.add_argument(
        "--format", choices=("table", "json"), default="table", help="output format (default table)"
    )
    return parser


def _query_from_args(args: argparse.Namespace, *, with_filters: bool) -> SearchQuery:
    if args.url:
        if args.destination:
            raise ValueError("pass either a destination or --url, not both")
        return SearchQuery.from_url(args.url)
    if not (args.destination or args.dest_id):
        raise ValueError("give a destination (or --url / --dest-id)")
    options: dict[str, Any] = {}
    if with_filters:
        options = dict(
            sort=args.sort,
            stars=args.stars,
            min_review=args.min_review,
            property_types=args.property_types,
            free_cancellation=args.free_cancellation,
            no_prepayment=args.no_prepayment,
            breakfast=args.breakfast,
            min_price=args.min_price,
            max_price=args.max_price,
            filters=args.filters,
        )
    return make_query(
        args.destination,
        checkin=args.checkin,
        checkout=args.checkout,
        nights=args.nights,
        adults=args.adults,
        rooms=args.rooms,
        children_ages=args.children_ages,
        currency=args.currency,
        language=args.lang,
        dest_id=args.dest_id,
        dest_type=args.dest_type,
        **options,
    )


def _stdout(text: str) -> None:
    # Write UTF-8 bytes so hotel names print on any console code page.
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
        buffer.flush()
    else:  # pragma: no cover - e.g. captured streams
        sys.stdout.write(text)


def _log(args: argparse.Namespace, message: str) -> None:
    if not args.quiet:
        print(message, file=sys.stderr)


def main(argv: Sequence[str] | None = None, *, scraper: BookingScraper | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        query = _query_from_args(args, with_filters=args.command == "search")
    except ValueError as exc:
        parser.error(str(exc))

    def on_retry(attempt: int, delay: float, exc: BaseException) -> None:
        _log(args, f"  retry {attempt} in {delay:.0f}s ({type(exc).__name__})")

    if scraper is None:
        scraper = BookingScraper(
            proxy_country=args.country, retries=args.retries, on_retry=on_retry
        )

    try:
        if args.command == "filters":
            page = scraper.fetch_page(query)
            if args.format == "json":
                _stdout(
                    json.dumps([g.to_dict() for g in page.filters], indent=2, ensure_ascii=False)
                    + "\n"
                )
            else:
                lines = [f"{page.destination} - {page.total_results} properties"]
                for group in page.filters:
                    lines.append(f"\n{group.title}")
                    for opt in group.options:
                        count = f" ({opt.count})" if opt.count is not None else ""
                        lines.append(f"  {opt.filter:<34} {opt.label}{count}")
                _stdout("\n".join(lines) + "\n")
            return 0

        def on_page(page: Any) -> None:
            _log(
                args,
                f"  {page.destination}: {len(page.properties)} properties "
                f"(sort={page.sort}, filters={';'.join(page.applied_filters) or '-'}, "
                f"{page.total_results} total)",
            )

        _log(
            args,
            f"Searching Booking.com: {query.destination or query.dest_id} "
            f"{query.checkin} -> {query.checkout}",
        )
        properties = scraper.search_query(
            query,
            limit=args.limit,
            sweep=not args.no_sweep,
            split_by_stars=args.split_by_stars,
            include_sponsored=not args.no_sponsored,
            max_requests=args.max_requests,
            on_page=on_page,
        )
    except DestinationNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (BookingError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.output:
        path = write(properties, args.output, args.format)
        _log(args, f"Wrote {len(properties)} properties to {path}")
    else:
        _stdout(render(properties, format_for(None, args.format)))
        _log(args, f"{len(properties)} properties")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
