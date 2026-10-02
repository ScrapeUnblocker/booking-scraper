"""Collect a large set of properties for a city and export them to CSV.

Booking.com shows up to 25 properties per request, so this sweeps several sort
orders and star classes and de-duplicates by property id.

    export SCRAPEUNBLOCKER_KEY=your_key_here
    python examples/city_to_csv.py "Rome" 150
"""

from __future__ import annotations

import sys

from booking_scraper import BookingScraper
from booking_scraper.export import write


def main() -> None:
    destination = sys.argv[1] if len(sys.argv) > 1 else "Rome"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 150

    scraper = BookingScraper(
        on_retry=lambda attempt, delay, exc: print(f"  retry {attempt} in {delay:.0f}s")
    )
    properties = scraper.search(
        destination,
        nights=1,
        limit=limit,
        split_by_stars=True,
        max_requests=20,  # cost cap
        on_page=lambda page: print(
            f"  {page.sort} {';'.join(page.applied_filters) or '(all)'}: "
            f"{len(page.properties)} properties of {page.total_results}"
        ),
    )
    path = write(properties, f"{destination.lower().replace(' ', '_')}_booking.csv")
    print(f"Wrote {len(properties)} unique properties to {path}")


if __name__ == "__main__":
    main()
