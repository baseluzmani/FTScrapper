# scraper.py
# This file has one job: given a fund ID and a date range,
# fetch the FT page and return the data as a list of dictionaries.
# It knows nothing about the database — that's database.py's job.

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import config


def build_url(fund_id, start_date, end_date):
    # Convert date objects to the format FT expects: DD/MM/YYYY
    start_str = start_date.strftime("%d/%m/%Y")
    end_str = end_date.strftime("%d/%m/%Y")

    return (
        f"https://markets.ft.com/data/funds/tearsheet/historical"
        f"?s={fund_id}&startDate={start_str}&endDate={end_str}"
    )


def fetch_page(url):
    # Make an HTTP GET request to the URL
    # We pass headers so the server thinks we're a real browser
    response = requests.get(url, headers=config.HEADERS, timeout=30)

    # .raise_for_status() throws an error if the server
    # returned a failure code (404, 500, etc.)
    response.raise_for_status()

    return response.text  # Returns the raw HTML as a string


def fetch_fund_name(html, fallback_name):
    # Try to extract the fund name from the page <h1> tag
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    if h1:
        name = h1.get_text(strip=True)
        if name:
            return name
    # Fall back to the name from config if not found
    print(f"  Could not extract fund name from page, using: {fallback_name}")
    return fallback_name


def parse_table(html):
    # BeautifulSoup parses the raw HTML into a structured object
    # 'lxml' is the parser engine — fast and reliable
    soup = BeautifulSoup(html, "lxml")

    # Find the historical prices table on the page
    table = soup.find("table", {"class": "mod-tearsheet-historical-prices__results"})

    if not table:
        print("  WARNING: Could not find the data table on the page.")
        return []

    rows = []

    # Find all rows in the table body (skips the header row)
    for tr in table.find("tbody").find_all("tr"):
        cells = tr.find_all("td")

        # Skip any rows that don't have exactly 6 columns
        if len(cells) != 6:
            continue

        # Extract text from each cell and clean whitespace
        # Two spans exist — desktop (full) and mobile (short). We want the first.
        date_str = (
            cells[0]
            .find("span", {"class": "mod-ui-hide-small-below"})
            .get_text(strip=True)
        )
        open_val = cells[1].get_text(strip=True)  # e.g. "6.00"
        high_val = cells[2].get_text(strip=True)
        low_val = cells[3].get_text(strip=True)
        close_val = cells[4].get_text(strip=True)
        vol_val = (
            cells[5]
            .find("span", {"class": "mod-ui-hide-small-below"})
            .get_text(strip=True)
        )

        # Convert the date string to a standard format: YYYY-MM-DD
        # This format sorts correctly alphabetically and is the SQL standard
        try:
            date = datetime.strptime(date_str, "%A, %B %d, %Y")
            date_formatted = date.strftime("%Y-%m-%d")
        except ValueError:
            print(f"  WARNING: Could not parse date '{date_str}', skipping row.")
            continue

        # Convert price strings to floats, volumes to integers
        # The 'or 0' handles empty strings gracefully
        rows.append(
            {
                "date": date_formatted,
                "open": float(open_val.replace(",", "") or 0),
                "high": float(high_val.replace(",", "") or 0),
                "low": float(low_val.replace(",", "") or 0),
                "close": float(close_val.replace(",", "") or 0),
                "volume": int(vol_val.replace(",", "") or 0),
            }
        )

    return rows


def scrape_fund(fund_id, fallback_name, latest_date=None):
    today = datetime.today()
    all_rows = []

    if latest_date is None:
        print(f"  No historical data found.")
        print(f"  For historical data, use import_manual.py.")
        print(f"  Fetching latest data only...")

        end_date = today
        start_date = today - timedelta(days=30)
        url = build_url(fund_id, start_date, end_date)
        print(f"  Fetching: {start_date.date()} → {end_date.date()}")
        html = fetch_page(url)
        fund_name = fetch_fund_name(html, fallback_name)
        all_rows = parse_table(html)

    else:
        start_date = datetime.strptime(latest_date, "%Y-%m-%d") + timedelta(days=1)
        print(f"  Incremental run: fetching from {start_date.date()} to today")

        if start_date.date() > today.date():
            print("  Already up to date.")
            return [], fallback_name

        url = build_url(fund_id, start_date, today)
        print(f"  Fetching: {url}")
        html = fetch_page(url)
        fund_name = fetch_fund_name(html, fallback_name)
        all_rows = parse_table(html)

    # Deduplicate
    seen = set()
    unique_rows = []
    for row in all_rows:
        if row["date"] not in seen:
            seen.add(row["date"])
            unique_rows.append(row)

    print(f"  Total unique rows found: {len(unique_rows)}")
    return unique_rows, fund_name
