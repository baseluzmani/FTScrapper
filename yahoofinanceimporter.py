# yahoofinanceimporter.py
# Imports benchmark and index data from Yahoo Finance into the database.
# Checks latest date per ticker and only adds new rows — safe to run repeatedly.
# Always reimports last 3 days to catch any Yahoo data corrections.
#
# To add a new ticker: just add it to the TICKERS list below.
#
# Usage:
#   python3 yahoofinanceimporter.py          # imports all tickers in the list
#   python3 yahoofinanceimporter.py ^GSPC    # imports a single specific ticker

import sys
import yfinance as yf
from datetime import datetime, timedelta
import database
import config

TICKERS = config.YAHOO_TICKERS

# ── SETTINGS ───────────────────────────────────────────────────

FIRST_RUN_DAYS = 730  # How many days of history to fetch on first import
REIMPORT_DAYS = 3  # Always reimport this many recent days to catch Yahoo corrections
FUND_ID_PREFIX = "YF"  # Prefix added to fund_id to avoid clashes with FT funds


# ── CORE FUNCTIONS ─────────────────────────────────────────────


def make_fund_id(ticker):
    """Convert a Yahoo ticker to a database fund_id."""
    return f"{FUND_ID_PREFIX}:{ticker}"


def fetch_yahoo(ticker, start_date, end_date):
    """
    Fetch historical data from Yahoo Finance for a given ticker.
    Returns a list of row dicts ready to insert into the database.
    """
    print(f"  Fetching {ticker} from {start_date} to {end_date}...")

    try:
        data = yf.download(
            ticker,
            start=start_date,
            end=end_date,
            progress=False,
            auto_adjust=True,
        )
    except Exception as e:
        print(f"  ERROR fetching {ticker}: {e}")
        return []

    if data.empty:
        print(f"  WARNING: No data returned for {ticker}")
        return []

    rows = []
    for date, row in data.iterrows():
        try:
            rows.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "open": float(
                        row["Open"].item()
                        if hasattr(row["Open"], "item")
                        else row["Open"]
                    ),
                    "high": float(
                        row["High"].item()
                        if hasattr(row["High"], "item")
                        else row["High"]
                    ),
                    "low": float(
                        row["Low"].item() if hasattr(row["Low"], "item") else row["Low"]
                    ),
                    "close": float(
                        row["Close"].item()
                        if hasattr(row["Close"], "item")
                        else row["Close"]
                    ),
                    "volume": int(
                        row["Volume"].item()
                        if hasattr(row["Volume"], "item")
                        else row["Volume"]
                    ),
                }
            )
        except Exception as e:
            print(f"  WARNING: Could not parse row for {date}: {e}")
            continue

    return rows


def process_ticker(conn, ticker, name, asset_type=None):
    """
    Check latest date in DB for this ticker, fetch only what's missing,
    and save to database. Always reimports the last REIMPORT_DAYS days
    to catch any corrections Yahoo may have made.
    """
    fund_id = make_fund_id(ticker)
    fund_name = f"{name} ({ticker})"

    # Check what we already have
    latest_date = database.get_latest_date(conn, fund_id)

    # Date that is REIMPORT_DAYS before today
    reimport_from = (datetime.today() - timedelta(days=REIMPORT_DAYS)).strftime(
        "%Y-%m-%d"
    )

    if latest_date:
        # Delete the last REIMPORT_DAYS to allow fresh reimport
        deleted = conn.execute(
            "DELETE FROM prices WHERE fund_id=? AND date >= ?",
            (fund_id, reimport_from),
        )
        conn.commit()
        if deleted.rowcount > 0:
            print(
                f"  Deleted {deleted.rowcount} recent rows from {reimport_from} for fresh reimport"
            )

        # Start from whichever is earlier:
        # — day after latest saved date (to catch any gap)
        # — or REIMPORT_DAYS ago (to refresh recent data)
        day_after_latest = (
            datetime.strptime(latest_date, "%Y-%m-%d") + timedelta(days=1)
        ).strftime("%Y-%m-%d")
        start_date = min(day_after_latest, reimport_from)

        print(
            f"  {fund_name:<45} | latest in DB: {latest_date} | fetching from {start_date}"
        )
    else:
        # First run — fetch full history
        start_date = (datetime.today() - timedelta(days=FIRST_RUN_DAYS)).strftime(
            "%Y-%m-%d"
        )
        print(
            f"  {fund_name:<45} | first import | fetching {FIRST_RUN_DAYS} days from {start_date}"
        )

    end_date = datetime.today().strftime("%Y-%m-%d")

    rows = fetch_yahoo(ticker, start_date, end_date)

    if not rows:
        return 0

    saved = database.save_prices(conn, fund_id, fund_name, rows, asset_type=asset_type)
    dates = [r["date"] for r in rows]
    print(
        f"  {len(rows)} rows fetched | {saved} new rows saved | {min(dates)} → {max(dates)}"
    )
    return saved


# ── MAIN ───────────────────────────────────────────────────────


def main():
    if len(sys.argv) > 1:
        ticker_arg = sys.argv[1].upper()
        match = next((t for t in TICKERS if t[0].upper() == ticker_arg), None)
        if match:
            tickers_to_run = [match]
        else:
            print(
                f"  Ticker {ticker_arg} not in TICKERS list, importing with ticker as name."
            )
            tickers_to_run = [(sys.argv[1], sys.argv[1], None)]
    else:
        tickers_to_run = TICKERS

    print(f"Yahoo Finance Importer")
    print(f"Processing {len(tickers_to_run)} ticker(s)...\n")

    conn = database.get_connection()
    database.create_table(conn)

    total_saved = 0

    for item in tickers_to_run:
        ticker = item[0]
        name = item[1]
        asset_type = item[2] if len(item) > 2 else None
        print(f"── {name} ({ticker})")
        try:
            saved = process_ticker(conn, ticker, name, asset_type=asset_type)
            total_saved += saved
        except Exception as e:
            print(f"  ERROR: {e}")
        print()

    conn.close()
    print(f"Done. {total_saved} total new rows saved.")
    print(f"\nTo add a new ticker permanently, add a line to TICKERS:")
    print(f'  ("TICKER", "Display Name", "Asset Type"),')


if __name__ == "__main__":
    main()
