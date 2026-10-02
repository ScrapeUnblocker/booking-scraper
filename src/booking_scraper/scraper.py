"""Scrape Booking.com search results through the ScrapeUnblocker ``getPageSource`` API.

ScrapeUnblocker loads the results page in a real browser and returns its HTML;
:mod:`booking_scraper.parsing` reads the data embedded in it.

Booking.com renders 15-25 properties per request and ignores paging offsets
on the server-rendered page, so the scraper collects more than one request's
worth by *sweeping*: it re-runs the same search under different sort orders
(and, optionally, one star-rating class at a time) and de-duplicates by
property id. Timeouts, transient API errors and pages without results data are
retried with doubling backoff.
"""

from __future__ import annotations

import datetime as _dt
import time
from collections.abc import Iterable, Sequence
from typing import Any, Callable

from .models import FilterGroup, Property, SearchPage
from .parsing import BookingParseError, parse_search_page
from .urls import SWEEP_SORTS, SearchQuery, build_filters, stay_dates

# A US route sees Booking.com the way a US visitor does; prices still follow ``currency``.
DEFAULT_PROXY_COUNTRY = "US"
STAR_CLASSES = (5, 4, 3, 2, 1)


def _transient_errors() -> tuple[type[BaseException], ...]:
    """Best-effort tuple of ScrapeUnblocker exceptions worth retrying.

    Imported lazily so the package is usable (and unit-testable) even when the
    ``scrapeunblocker`` SDK is not installed.
    """
    try:
        from scrapeunblocker import (  # type: ignore
            BlockedError,
            BrowserTimeoutError,
            RateLimitError,
            ScrapeTimeoutError,
            ServerError,
            UpstreamOutageError,
        )
        from scrapeunblocker import (
            ConnectionError as SUConnectionError,
        )
    except Exception:  # pragma: no cover - depends on SDK availability
        return ()
    return (
        UpstreamOutageError,
        RateLimitError,
        ScrapeTimeoutError,
        BrowserTimeoutError,
        BlockedError,
        ServerError,
        SUConnectionError,
    )


def make_query(
    destination: str | None = None,
    *,
    checkin: str | _dt.date | None = None,
    checkout: str | _dt.date | None = None,
    nights: int = 1,
    adults: int = 2,
    rooms: int = 1,
    children_ages: Sequence[int] = (),
    currency: str = "USD",
    language: str = "en-us",
    sort: str | None = None,
    stars: Iterable[int] = (),
    min_review: int | None = None,
    property_types: Iterable[str] = (),
    free_cancellation: bool = False,
    no_prepayment: bool = False,
    breakfast: bool = False,
    min_price: int | None = None,
    max_price: int | None = None,
    filters: Iterable[str] = (),
    dest_id: str | None = None,
    dest_type: str | None = None,
) -> SearchQuery:
    """Build a :class:`SearchQuery` from friendly options (see :class:`BookingScraper.search`)."""
    start, end = stay_dates(checkin, checkout, nights=nights)
    return SearchQuery(
        destination=destination,
        checkin=start,
        checkout=end,
        adults=adults,
        rooms=rooms,
        children_ages=tuple(int(a) for a in children_ages),
        currency=currency.upper(),
        language=language,
        sort=sort,
        filters=tuple(
            build_filters(
                stars=stars,
                min_review=min_review,
                property_types=property_types,
                free_cancellation=free_cancellation,
                no_prepayment=no_prepayment,
                breakfast=breakfast,
                currency=currency,
                min_price=min_price,
                max_price=max_price,
                extra=filters,
            )
        ),
        dest_id=str(dest_id) if dest_id is not None else None,
        dest_type=dest_type,
    )


class BookingScraper:
    """Scrape Booking.com hotel and accommodation search results.

    Args:
        api_key: ScrapeUnblocker key. If omitted, the SDK reads
            ``SCRAPEUNBLOCKER_KEY`` from the environment.
        client: A pre-built client (or any object exposing
            ``get_page_source(url, proxy_country=...)``). Mainly for testing.
        proxy_country: Country to route requests through (default ``"US"``).
        retries: Extra attempts per request on transient failures.
        backoff: Seconds before the first retry; doubles on every further retry.
        max_backoff: Upper bound for a single wait between retries.
        timeout: Per-request timeout passed to the SDK client.
        transient_errors: Exception classes treated as retryable. Defaults to
            the ScrapeUnblocker transient set.
        on_retry: Optional callback ``(attempt, delay_seconds, error)`` invoked
            before every retry (handy for progress output).
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: Any | None = None,
        proxy_country: str | None = DEFAULT_PROXY_COUNTRY,
        retries: int = 3,
        backoff: float = 5.0,
        max_backoff: float = 60.0,
        timeout: float = 180.0,
        transient_errors: Sequence[type[BaseException]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        on_retry: Callable[[int, float, BaseException], None] | None = None,
    ) -> None:
        if client is None:
            from scrapeunblocker import Client  # local import: optional dep

            client = Client(api_key=api_key, timeout=timeout)
        self._client = client
        self.proxy_country = proxy_country
        self.retries = max(0, int(retries))
        self.backoff = float(backoff)
        self.max_backoff = float(max_backoff)
        self.on_retry = on_retry
        transient = tuple(transient_errors) if transient_errors is not None else _transient_errors()
        self._transient = (*transient, BookingParseError)
        self._sleep = sleep
        self.requests_made = 0

    # ------------------------------------------------------------------ #
    # Fetching
    # ------------------------------------------------------------------ #

    def fetch_page(self, query: SearchQuery | str) -> SearchPage:
        """Fetch and parse one results page for a query (or a search URL).

        Raises:
            DestinationNotFoundError: Booking.com could not match the destination.
        """
        if isinstance(query, str):
            query = SearchQuery.from_url(query)
        url = query.to_url()
        attempt = 0
        while True:
            try:
                self.requests_made += 1
                html = self._client.get_page_source(url, proxy_country=self.proxy_country)
                return parse_search_page(
                    html if isinstance(html, str) else "", url=url, query=query
                )
            except Exception as exc:
                if not isinstance(exc, self._transient) or attempt >= self.retries:
                    raise
                attempt += 1
                delay = min(self.backoff * 2 ** (attempt - 1), self.max_backoff)
                if self.on_retry is not None:
                    self.on_retry(attempt, delay, exc)
                self._sleep(delay)

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def search_query(
        self,
        query: SearchQuery,
        *,
        limit: int = 25,
        sweep: bool = True,
        sorts: Sequence[str] | None = None,
        split_by_stars: bool = False,
        include_sponsored: bool = True,
        max_requests: int | None = None,
        seen: set[int] | None = None,
        on_page: Callable[[SearchPage], None] | None = None,
    ) -> list[Property]:
        """Collect up to ``limit`` properties for a prepared :class:`SearchQuery`.

        Args:
            query: The search to run.
            limit: Maximum number of properties to return.
            sweep: When the first request returns fewer than ``limit`` new
                properties, re-run the search under other sort orders until
                ``limit`` is reached (default ``True``).
            sorts: Sort orders to sweep through (default :data:`SWEEP_SORTS`).
                The query's own sort order always goes first.
            split_by_stars: Also run every sort order once per star-rating
                class (5 to 1 stars) - many more distinct properties for big
                cities, at the cost of more requests. Unrated properties are
                only reached by the unsplit first request.
            include_sponsored: Keep properties shown as sponsored placements.
            max_requests: Hard cap on the number of requests for this call.
            seen: Shared set of property ids; ids already in it are skipped.
                Pass the same set to several calls to de-duplicate across searches.
            on_page: Callback invoked with every fetched :class:`SearchPage`.
        """
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if max_requests is not None and max_requests < 1:
            raise ValueError("max_requests must be at least 1")
        if split_by_stars and any(f.startswith("class=") for f in query.filters):
            raise ValueError("split_by_stars cannot be combined with a star-rating filter")
        seen = seen if seen is not None else set()
        order = [query.sort or "popularity"]
        order += [s for s in (sorts if sorts is not None else SWEEP_SORTS) if s not in order]

        plan: list[tuple[str, tuple[str, ...]]] = [(order[0], ())]
        if split_by_stars:
            plan += [(s, (f"class={c}",)) for c in STAR_CLASSES for s in order]
        else:
            plan += [(s, ()) for s in order[1:]]

        out: list[Property] = []
        exhausted: set[tuple[str, ...]] = set()
        requests = 0
        for index, (sort, slice_filters) in enumerate(plan):
            if len(out) >= limit or (max_requests is not None and requests >= max_requests):
                break
            if index > 0 and sweep is False:
                break
            if slice_filters in exhausted:
                continue
            page = self.fetch_page(query.with_options(sort=sort, add_filters=slice_filters))
            requests += 1
            if on_page is not None:
                on_page(page)
            for prop in page.properties:
                if prop.property_id in seen or (prop.sponsored and not include_sponsored):
                    continue
                seen.add(prop.property_id)
                out.append(prop)
                if len(out) >= limit:
                    break
            # Every result of this slice fitted on one page: other sorts add nothing new.
            if page.total_results is not None and page.total_results <= len(page.properties):
                exhausted.add(slice_filters)
                if not slice_filters:
                    break
        return out

    def search(
        self,
        destination: str | None = None,
        *,
        url: str | None = None,
        limit: int = 25,
        sweep: bool = True,
        sorts: Sequence[str] | None = None,
        split_by_stars: bool = False,
        include_sponsored: bool = True,
        max_requests: int | None = None,
        seen: set[int] | None = None,
        on_page: Callable[[SearchPage], None] | None = None,
        **query_options: Any,
    ) -> list[Property]:
        """Search Booking.com and return up to ``limit`` properties.

        Give a free-text ``destination`` (``"Paris"``, ``"Lake Tahoe"``, ...) plus
        any query options, or a ``url`` copied from a Booking.com results page.

        Query options (all optional): ``checkin``/``checkout`` (``YYYY-MM-DD``;
        check-in defaults to 30 days out), ``nights`` (default 1), ``adults``,
        ``rooms``, ``children_ages``, ``currency``, ``language``, ``sort``,
        ``stars``, ``min_review`` (6-9), ``property_types``,
        ``free_cancellation``, ``no_prepayment``, ``breakfast``,
        ``min_price``/``max_price`` (per night, in ``currency``), ``filters``
        (raw ``key=value`` strings from :meth:`filters`), ``dest_id`` and
        ``dest_type``. See :meth:`search_query` for the collection options.
        """
        if url is not None:
            if destination is not None or query_options:
                raise ValueError("pass either url or destination/query options, not both")
            query = SearchQuery.from_url(url)
        else:
            query = make_query(destination, **query_options)
        return self.search_query(
            query,
            limit=limit,
            sweep=sweep,
            sorts=sorts,
            split_by_stars=split_by_stars,
            include_sponsored=include_sponsored,
            max_requests=max_requests,
            seen=seen,
            on_page=on_page,
        )

    def filters(
        self, destination: str | None = None, *, url: str | None = None, **query_options: Any
    ) -> list[FilterGroup]:
        """List the filters Booking.com offers for a search (one request).

        Every option's ``filter`` value (e.g. ``hotelfacility=107``) can be passed
        back through ``filters=[...]`` / ``--filter``.
        """
        if url is not None:
            query = SearchQuery.from_url(url)
        else:
            query = make_query(destination, **query_options)
        return self.fetch_page(query).filters
