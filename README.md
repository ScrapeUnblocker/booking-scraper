# Booking.com Scraper

[![CI](https://github.com/ScrapeUnblocker/booking-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/ScrapeUnblocker/booking-scraper/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Powered by ScrapeUnblocker](https://img.shields.io/badge/powered%20by-ScrapeUnblocker-6f42c1.svg)](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)

**Scrape [Booking.com](https://www.booking.com) hotel and accommodation search results into clean JSON or CSV.**
Pick a destination and stay dates. For every property you get the price for your
stay (total and per night, with currency), the original price and discount, review score
and count, star rating, accommodation type, address, district, coordinates, distance
from the center, cancellation and prepayment policy, room or unit details, a photo and a
ready-to-book link.

Powered by [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos):
the `getPageSource` API loads the Booking.com results page in a real browser and returns
the HTML. This package reads the data Booking.com embeds in that page and turns it into
typed records. You don't need to run proxies, headless browsers or retry logic yourself.

## Features

- **Search like the website does.** Any destination Booking.com's search box understands
  (`Paris`, `New York`, `Lake Tahoe`, `Shibuya`), with check-in/check-out dates,
  adults, children's ages, rooms, currency and site language. You can also paste a
  results URL from your browser and it is scraped with all its filters.
- **Accurate prices.** The total for the stay and the nightly rate in your chosen
  currency, plus the price before discount, the discount amount, deal badges such as
  *Limited-time Deal*, taxes and fees not included in the price, and the price in the
  property's own currency.
- **Rich, typed records.** Booking.com property ID, name, accommodation type, matched room
  or unit, bedrooms/bathrooms/beds and floor area for entire homes, star rating, review
  score, review word and count, location score, address, district, city, country,
  latitude/longitude, distance from the center, nearest public transport, free
  cancellation (and deadline), no prepayment, meal plan, "only X left" message,
  highlights, Preferred Partner, sustainability certification, sponsored flag, host type
  and photo URL.
- **Every Booking.com filter.** Shortcuts for star rating, minimum review score, property
  type, nightly price range, free cancellation, no prepayment and breakfast. The
  `filters` command lists every other filter Booking.com offers for a destination, such as
  amenities, neighborhoods, brands, landmarks, bed type and accessibility, with counts.
  You can pass any of them with `--filter`.
- **Every sort order.** Top picks, lowest/highest price, top reviewed, best reviewed and
  lowest price, distance from downtown, property rating, and more.
- **More than one page of results.** Booking.com shows 15-25 properties per request and
  ignores paging offsets on the server-rendered page. So the scraper *sweeps*: it re-runs
  your search with other sort orders (and, with `--split-by-stars`, one star class at a
  time) and de-duplicates by property ID until it reaches `--limit`. You can cap the cost
  with `--max-requests`.
- **Resilient.** Timeouts, transient API errors and pages without results data are retried
  with doubling backoff. An unknown destination raises a clear error instead of silently
  returning Booking.com's home page.
- **JSON, JSON Lines or CSV.** CSV joins list fields with `"; "` and is written as UTF-8 with
  a BOM so Excel shows accented hotel names correctly.
- **CLI + Python library.** Type-hinted, and tested offline with a mocked client.

## Install

```bash
git clone https://github.com/ScrapeUnblocker/booking-scraper.git
cd booking-scraper
pip install .
```

Get an API key at [scrapeunblocker.com](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos)
and expose it as `SCRAPEUNBLOCKER_KEY` (the official SDK reads it from there):

```bash
export SCRAPEUNBLOCKER_KEY=your_key_here        # Windows PowerShell: $env:SCRAPEUNBLOCKER_KEY="your_key_here"
```

Or copy `.env.example` to `.env` and load it with your tool of choice. Never commit a real key.

## CLI usage

```bash
# 25 properties in Paris for 2 nights, 2 adults (JSON to stdout)
booking-scraper search "Paris" --checkin 2026-11-10 --nights 2

# 4-5 star hotels rated 8+ under $200/night, cheapest first, to CSV
booking-scraper search "Lisbon" --stars 4,5 --min-review 8 --type hotels \
    --max-price 200 --sort price -o lisbon.csv

# A family of four, two rooms, prices in euros
booking-scraper search "Barcelona" --adults 2 --children-ages 5,9 --rooms 2 --currency EUR

# Collect 150 properties: sweep sort orders and star classes, at most 20 requests
booking-scraper search "Rome" --limit 150 --split-by-stars --max-requests 20 -o rome.csv

# See every filter Booking.com offers for a destination...
booking-scraper filters "Amsterdam" --checkin 2026-11-20
# ...and use any of them (Free Wifi + pet friendly)
booking-scraper search "Amsterdam" --filter hotelfacility=107 --filter stay_type=1

# Scrape a results URL copied from your browser
booking-scraper search --url "https://www.booking.com/searchresults.html?ss=Tokyo&checkin=2026-12-01&checkout=2026-12-04&group_adults=2&nflt=class%3D4"
```

`python -m booking_scraper ...` works too. Progress goes to stderr, so stdout stays clean
for piping. Add `-q` to silence it.

| Option | Meaning |
| --- | --- |
| `destination` / `--url` | Free-text destination, or a Booking.com `searchresults` URL |
| `--checkin`, `--checkout`, `--nights` | Stay dates. Check-in defaults to 30 days from today, 1 night |
| `--adults`, `--children-ages`, `--rooms` | Party size, e.g. `--children-ages 5,9` |
| `--currency`, `--lang` | Price currency (default `USD`) and site language (default `en-us`) |
| `--dest-id`, `--dest-type` | Pin an exact Booking.com destination id (as seen in search URLs) |
| `--sort` | `popularity`, `price`, `price_from_high_to_low`, `bayesian_review_score`, `review_score_and_price`, `class`, `class_asc`, `class_and_price`, `distance_from_search`, `upsort_bh`, `business_popularity` |
| `--stars`, `--min-review`, `--type` | Star classes, minimum score (6/7/8/9), property types (`hotels`, `apartments`, `hostels`, `resorts`, `bed-and-breakfasts`, `villas`, `campgrounds`, `guesthouses`, `condo-hotels`, `vacation-homes`, `homestays`) |
| `--min-price`, `--max-price` | Nightly budget in `--currency` |
| `--free-cancellation`, `--no-prepayment`, `--breakfast` | Policy and meal filters |
| `--filter KEY=VALUE` | Any filter from the `filters` command (repeatable) |
| `--limit` | Max properties (default 25). Sweeps sort orders when one request isn't enough |
| `--no-sweep`, `--split-by-stars`, `--max-requests` | Control how far a sweep goes |
| `--no-sponsored` | Drop sponsored placements (kept and flagged by default) |
| `-o`, `--format` | Output file (`.json`, `.jsonl`, `.csv`) or explicit format |
| `--country`, `--retries` | Request routing country (default `US`) and retries per request |

## Library usage

```python
from booking_scraper import BookingScraper

scraper = BookingScraper()  # reads SCRAPEUNBLOCKER_KEY; or BookingScraper(api_key="...")

hotels = scraper.search(
    "Paris",
    checkin="2026-11-10",
    nights=2,
    adults=2,
    stars=[4, 5],
    min_review=8,
    free_cancellation=True,
    currency="EUR",
    limit=50,
)
for h in hotels:
    print(h.name, h.review_score, h.price, h.currency, h.booking_url)
```

Lower-level building blocks:

```python
from booking_scraper import BookingScraper, SearchQuery, make_query

scraper = BookingScraper(retries=5, on_retry=lambda n, delay, exc: print("retry", n))

# One request -> one SearchPage with the search's own metadata
page = scraper.fetch_page(make_query("Lisbon", checkin="2026-11-20", sort="price"))
print(page.destination, page.dest_id, page.total_results, page.applied_filters)
print(page.sorts)  # sort orders available for this search
for group in page.filters:  # every filter, with property counts
    print(group.title, [(o.filter, o.label, o.count) for o in group.options][:3])

# Build a query from a browser URL, then tweak it
query = SearchQuery.from_url(
    "https://www.booking.com/searchresults.html?ss=Rome&checkin=2026-12-01"
)
cheap = scraper.search_query(query.with_options(sort="price", add_filters=["fc=2"]), limit=10)

# De-duplicate across several searches by sharing a seen-set
seen: set[int] = set()
coast = []
for town in ["Positano", "Amalfi", "Ravello"]:
    coast += scraper.search(town, checkin="2027-06-10", nights=3, limit=25, seen=seen)
```

Save results with `booking_scraper.export.write(properties, "out.csv")` (or `.json` / `.jsonl`).

Errors: `DestinationNotFoundError` when Booking.com can't match the destination,
`BookingParseError` when a page held no results data after all retries, and the SDK's own
exceptions (bad key, out of credit, ...) are passed through unchanged.

## Example output

`booking-scraper search "Barcelona" --checkin 2026-11-20 --nights 2 --limit 40` (real output, first record):

```text
Searching Booking.com: Barcelona 2026-11-20 -> 2026-11-22
  Barcelona: 23 properties (sort=popularity, filters=-, 1258 total)
  Barcelona: 20 properties (sort=price, filters=-, 1257 total)
40 properties
```

```json
{
  "property_id": 93521,
  "name": "Eco Boutique Hostal Grau",
  "url": "https://www.booking.com/hotel/es/hosteria-grau.html",
  "booking_url": "https://www.booking.com/hotel/es/hosteria-grau.html?checkin=2026-11-20&checkout=2026-11-22&group_adults=2&no_rooms=1&group_children=0&selected_currency=USD&lang=en-us",
  "position": 1,
  "accommodation_type": "Hotel",
  "accommodation_type_id": 204,
  "room_name": "Double or Twin Room",
  "unit_type": null,
  "bedrooms": null,
  "bathrooms": null,
  "beds": 2,
  "area": null,
  "area_unit": null,
  "star_rating": 2,
  "star_rating_type": null,
  "review_score": 9,
  "review_word": "Wonderful",
  "review_count": 1108,
  "location_score": 9.7,
  "external_review_score": 9.7,
  "external_review_count": 14,
  "address": "Ramelleres 27",
  "district": "Ciutat Vella, Barcelona",
  "city": "Barcelona",
  "country_code": "es",
  "latitude": 41.384690149815135,
  "longitude": 2.1681831032037735,
  "distance_from_center": "0.2 miles from downtown",
  "public_transport": "Plaça de Catalunya (FGC) station is within 150 yards",
  "price": 324.29,
  "price_per_night": 162.15,
  "currency": "USD",
  "price_before_discount": null,
  "discount": null,
  "taxes_and_fees": 32.42,
  "property_currency_price": 287.87,
  "property_currency": "EUR",
  "deals": [],
  "sold_out": false,
  "free_cancellation": false,
  "free_cancellation_until": null,
  "no_prepayment": false,
  "meal_plan": null,
  "availability_message": null,
  "highlights": ["Shuttle service", "24-hour front desk"],
  "preferred_partner": true,
  "sustainability_certified": true,
  "sponsored": false,
  "host_type": "professional",
  "photo_url": "https://cf.bstatic.com/xdata/images/hotel/square600/147973986.jpg?k=ccede9a6cde3f1f7cfcd73f47b788f8111b5b6a12b763bda018bb6fcd05ad4e3&o=",
  "checkin": "2026-11-20",
  "checkout": "2026-11-22",
  "destination": "Barcelona"
}
```

Prices and availability are live, so you'll see different numbers.

### Field notes

- `price` is the total for the whole stay and party as Booking.com displays it. `taxes_and_fees`
  are the charges Booking.com lists as *not* included in that price (city tax, cleaning, ...).
- `price_per_night` is Booking.com's own average nightly rate as shown on the card. It isn't always
  `price / nights`, because Booking.com can leave some charges (such as one-off fees) out of
  it. When the page shows no nightly rate, it is `price / nights`.
- `discount` = `price_before_discount - price`, filled only when Booking.com shows a struck-through price.
- `review_score` is on Booking.com's 0-10 scale and is `null` when Booking.com hides it
  (too few reviews). `external_review_score` / `external_review_count` are the external-review
  figures Booking.com shows for some properties.
- `bedrooms`, `bathrooms`, `area` and `unit_type` are filled for entire homes and apartments.
  For hotels, `room_name` is the room Booking.com matched to your party.
- Distances and areas are the text Booking.com shows for the site language (`en-us`: miles
  and ft²).
- `sponsored` marks paid placements in the results. They are real, bookable properties
  matching your search, so they're kept by default. Use `--no-sponsored` to drop them.

## Project layout

```text
booking-scraper/
├── src/booking_scraper/
│   ├── __init__.py      # public API + __version__
│   ├── scraper.py       # BookingScraper: fetching, retries, sweeps, de-duplication
│   ├── parsing.py       # embedded results data -> Property / SearchPage / FilterGroup
│   ├── urls.py          # SearchQuery, filters, sort orders, URL building/parsing
│   ├── models.py        # dataclasses
│   ├── export.py        # JSON / JSON Lines / CSV writers
│   ├── cli.py           # `booking-scraper` command
│   └── __main__.py      # `python -m booking_scraper`
├── examples/
│   ├── search_to_json.py     # one search -> JSON file
│   ├── best_value_hotels.py  # 4-5 star, 8+ score, under a budget, cheapest first
│   └── city_to_csv.py        # sweep a whole city into CSV
├── tests/                    # offline tests with a fake client + saved page fixture
├── pyproject.toml
├── requirements.txt
├── Makefile
└── .github/workflows/ci.yml
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
make install      # pip install -e ".[dev]"
make lint         # ruff check
make format       # ruff format
make test         # pytest (offline, no API key needed)
pre-commit install
```

The tests replay a saved, trimmed Booking.com results page and synthetic pages through a
fake client. They spend no API credit and run in CI on Python 3.9 and 3.12.

## Responsible use

Scrape at a reasonable pace and respect Booking.com's terms of use. Prices and availability
change constantly, so treat scraped prices as a snapshot and confirm on Booking.com before
you rely on them. This project is not affiliated with or endorsed by Booking.com.

## Links

- [ScrapeUnblocker](https://scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos) - the web scraping API behind this project
- [ScrapeUnblocker documentation](https://docs.scrapeunblocker.com/?utm_source=github&utm_medium=integration&utm_campaign=example-repos) - `getPageSource`, SDKs, parsing options
- [Python SDK on PyPI](https://pypi.org/project/scrapeunblocker/) - `pip install scrapeunblocker`

## License

[MIT](LICENSE) - Copyright (c) 2026 ScrapeUnblocker
