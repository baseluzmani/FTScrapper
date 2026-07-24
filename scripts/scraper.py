# scraper.py
# This file has one job: given a fund ID and a date range,
# fetch the FT page and return the data as a list of dictionaries.
# It knows nothing about the database — that's database.py's job.

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import time
from requests.exceptions import RequestException


def build_url(fund_id, start_date, end_date):
    start_str = start_date.strftime("%d/%m/%Y")
    end_str = end_date.strftime("%d/%m/%Y")
    return (
        f"https://markets.ft.com/data/funds/tearsheet/historical"
        f"?s={fund_id}&startDate={start_str}&endDate={end_str}"
    )


def build_holdings_url(fund_id):
    # If holdings_id is a full URL, use it directly
    if fund_id.startswith("http"):
        return fund_id
    return f"https://markets.ft.com/data/funds/tearsheet/holdings?s={fund_id}"


def fetch_page(url, tries=3):
    """GET the FT page with retry + backoff on connection/timeout errors."""
    last_err = None
    for attempt in range(tries):
        try:
            response = requests.get(
                url,
                headers=config.HEADERS,
                timeout=(8, 30),
            )
            response.raise_for_status()
            return response.text
        except RequestException as e:
            last_err = e
            print(f"  attempt {attempt + 1}/{tries} failed: {type(e).__name__}")
            time.sleep(2 ** attempt)
    raise last_err


def fetch_fund_name(html, fallback_name):
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    if h1:
        name = h1.get_text(strip=True)
        if name:
            return name
    print(f"  Could not extract fund name from page, using: {fallback_name}")
    return fallback_name


def parse_table(html):
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", {"class": "mod-tearsheet-historical-prices__results"})
    if not table:
        print("  WARNING: Could not find the data table on the page.")
        return []

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) != 6:
            continue
        date_str = (
            cells[0]
            .find("span", {"class": "mod-ui-hide-small-below"})
            .get_text(strip=True)
        )
        open_val  = cells[1].get_text(strip=True)
        high_val  = cells[2].get_text(strip=True)
        low_val   = cells[3].get_text(strip=True)
        close_val = cells[4].get_text(strip=True)
        vol_val   = (
            cells[5]
            .find("span", {"class": "mod-ui-hide-small-below"})
            .get_text(strip=True)
        )
        try:
            date = datetime.strptime(date_str, "%A, %B %d, %Y")
            date_formatted = date.strftime("%Y-%m-%d")
        except ValueError:
            print(f"  WARNING: Could not parse date '{date_str}', skipping row.")
            continue
        rows.append({
            "date":   date_formatted,
            "open":   float(open_val.replace(",",  "") or 0),
            "high":   float(high_val.replace(",",  "") or 0),
            "low":    float(low_val.replace(",",   "") or 0),
            "close":  float(close_val.replace(",", "") or 0),
            "volume": int(vol_val.replace(",",     "") or 0),
        })
    return rows


def parse_holdings(html, fund_id):
    """
    Parse the FT fund holdings page.

    Returns a tuple: (holdings, followed_id)
      holdings    — list of dicts with keys: rank, name, ticker, weight_pct
      followed_id — if the fund is a feeder (single holding ~100%), this is
                    the underlying fund's FT ID so the caller can follow it.
                    None if the holdings are direct equity positions.
    """
    soup = BeautifulSoup(html, "lxml")
    holdings = []

    # Find the holdings table — it has headers: Company, 1 year change, Portfolio weight, Long allocation
    table = None
    for t in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in t.find_all("th")]
        if "Company" in headers and "Portfolio weight" in headers:
            table = t
            break

    if not table:
        print("  WARNING: Could not find holdings table on page.")
        return [], None

    rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")

    for i, tr in enumerate(rows):
        # Skip header rows (contain th not td)
        if tr.find("th"):
            continue
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue

        # Company name — first cell, may contain a link and a sub-ticker line
        name_cell = cells[0]
        # Get the main name (first text node or first element text)
        name_link = name_cell.find("a")
        name = name_link.get_text(strip=True) if name_link else name_cell.get_text(separator=" ", strip=True).split("\n")[0].strip()

        # Sub-ticker shown below the name (e.g. "2330:TAI")
        ticker = ""
        spans = name_cell.find_all("span")
        for span in spans:
            t = span.get_text(strip=True)
            if t and t != name:
                ticker = t
                break

        # Underlying fund FT ID (for feeder funds — the link href contains ?s=)
        underlying_id = None
        if name_link and name_link.get("href"):
            href = name_link["href"]
            if "tearsheet" in href and "?s=" in href:
                underlying_id = href.split("?s=")[-1]

        # Portfolio weight is the 3rd column (index 2): Company | 1yr change | Portfolio weight | Long alloc
        weight_pct = None
        if len(cells) >= 3:
            text = cells[2].get_text(strip=True).replace("%", "").replace(",", "").strip()
            try:
                val = float(text)
                if 0 < val <= 100:
                    weight_pct = val
            except ValueError:
                pass
        # Fallback: scan all cells for a plausible weight
        if weight_pct is None:
            for cell in cells[1:]:
                text = cell.get_text(strip=True).replace("%", "").replace(",", "").strip()
                try:
                    val = float(text)
                    if 0 < val <= 100:
                        weight_pct = val
                        break
                except ValueError:
                    continue

        if not name:
            continue

        holdings.append({
            "rank":       i + 1,
            "name":       name,
            "ticker":     ticker,
            "weight_pct": weight_pct,
            "underlying_id": underlying_id,
        })

    # Detect feeder fund pattern: single holding with weight ~99-100%
    if len(holdings) == 1 and holdings[0]["weight_pct"] and holdings[0]["weight_pct"] >= 95:
        followed_id = holdings[0].get("underlying_id")
        print(f"  Feeder fund detected — underlying: {holdings[0]['name']} ({followed_id})")
        return holdings, followed_id

    return holdings, None


def scrape_holdings(fund_id, holdings_id, fund_name, max_follow=1):
    """
    Scrape top 10 holdings for a fund from the FT holdings page.
    If holdings_id differs from fund_id, uses holdings_id directly.
    If a feeder fund is detected (single ~100% holding), follows through
    to the underlying fund automatically (up to max_follow times).

    Returns list of holding dicts with: rank, name, ticker, weight_pct,
            plus scraped_date (today's date as YYYY-MM-DD).
    """
    today = datetime.today().strftime("%Y-%m-%d")
    target_id = holdings_id

    for depth in range(max_follow + 1):
        url = build_holdings_url(target_id)
        print(f"  Fetching holdings: {url}")
        try:
            html = fetch_page(url)
        except Exception as e:
            print(f"  ERROR fetching holdings for {fund_name}: {e}")
            return []

        holdings, followed_id = parse_holdings(html, target_id)

        if followed_id and depth < max_follow:
            print(f"  Following through to underlying fund: {followed_id}")
            target_id = followed_id
            time.sleep(1)
            continue

        # Tag each holding with the scrape date
        for h in holdings:
            h["scraped_date"] = today
            h.pop("underlying_id", None)  # Don't store internal field

        print(f"  Found {len(holdings)} holdings for {fund_name}")
        return holdings

    return []


def scrape_fund(fund_id, fallback_name, latest_date=None):
    today = datetime.today()
    all_rows = []

    if latest_date is None:
        print(f"  No historical data found.")
        print(f"  For historical data, use import_manual.py.")
        print(f"  Fetching latest data only...")
        end_date   = today
        start_date = today - timedelta(days=30)
        url        = build_url(fund_id, start_date, end_date)
        print(f"  Fetching: {start_date.date()} → {end_date.date()}")
        html       = fetch_page(url)
        fund_name  = fetch_fund_name(html, fallback_name)
        all_rows   = parse_table(html)
    else:
        start_date = datetime.strptime(latest_date, "%Y-%m-%d") + timedelta(days=1)
        print(f"  Incremental run: fetching from {start_date.date()} to today")
        if start_date.date() > today.date():
            print("  Already up to date.")
            return [], fallback_name
        url       = build_url(fund_id, start_date, today)
        print(f"  Fetching: {url}")
        html      = fetch_page(url)
        fund_name = fetch_fund_name(html, fallback_name)
        all_rows  = parse_table(html)

    # Deduplicate
    seen, unique_rows = set(), []
    for row in all_rows:
        if row["date"] not in seen:
            seen.add(row["date"])
            unique_rows.append(row)

    print(f"  Total unique rows found: {len(unique_rows)}")
    return unique_rows, fund_name