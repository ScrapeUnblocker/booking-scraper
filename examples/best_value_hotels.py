"""Find well-reviewed 4-5 star hotels under a nightly budget, cheapest first.

export SCRAPEUNBLOCKER_KEY=your_key_here
python examples/best_value_hotels.py "Lisbon" 200
"""

from __future__ import annotations

import sys

from booking_scraper import BookingScraper


def main() -> None:
    destination = sys.argv[1] if len(sys.argv) > 1 else "Lisbon"
    budget = int(sys.argv[2]) if len(sys.argv) > 2 else 200

    scraper = BookingScraper()
    hotels = scraper.search(
        destination,
        nights=2,
        stars=[4, 5],
        min_review=8,
        property_types=["hotels"],
        max_price=budget,  # per night, in the search currency
        currency="USD",
        sort="price",
        include_sponsored=False,
        limit=15,
        sweep=False,  # one request, keeps Booking.com's price order
    )

    print(f"{'hotel':<45} {'stars':>5} {'score':>5} {'per night':>10} {'free cancel':>11}")
    for h in hotels:
        print(
            f"{h.name[:45]:<45} {h.star_rating or '-':>5} {h.review_score or '-':>5} "
            f"{h.price_per_night or 0:>10.2f} {'yes' if h.free_cancellation else 'no':>11}"
        )


if __name__ == "__main__":
    main()
