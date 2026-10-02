"""Scrape one Booking.com search and save it as JSON.

export SCRAPEUNBLOCKER_KEY=your_key_here
python examples/search_to_json.py "Paris" 2026-11-10
"""

from __future__ import annotations

import json
import sys

from booking_scraper import BookingScraper


def main() -> None:
    destination = sys.argv[1] if len(sys.argv) > 1 else "Paris"
    checkin = sys.argv[2] if len(sys.argv) > 2 else None  # default: 30 days from today

    scraper = BookingScraper()  # reads SCRAPEUNBLOCKER_KEY
    properties = scraper.search(destination, checkin=checkin, nights=2, adults=2, limit=25)

    with open("booking_results.json", "w", encoding="utf-8") as fh:
        json.dump([p.to_dict() for p in properties], fh, indent=2, ensure_ascii=False)

    for p in properties[:10]:
        price = f"{p.price:,.2f} {p.currency}" if p.price else "sold out"
        print(f"{p.position:>2}. {p.name} - {p.review_score or '-'}/10 - {price}")
    print(f"Saved {len(properties)} properties to booking_results.json")


if __name__ == "__main__":
    main()
