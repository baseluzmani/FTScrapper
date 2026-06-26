# yahoofinanceimporter.py
# Imports benchmark and index data from Yahoo Finance into the database.
# Checks latest date per ticker and only adds new rows — safe to run repeatedly.
# Always reimports last REIMPORT_DAYS to catch any Yahoo data corrections.
#
# Why this version batches:
#   The old version called yf.download() once PER ticker — 108 separate
#   requests every run. Combined with live_prices.py running just after,
#   that was ~200+ Yahoo hits back-to-back, which trips rate-limiting (429).
#   Here, tickers are grouped by their required start date (almost all share
#   the same one in steady state) and fetched in batched calls — typically
#   ~2 requests per run instead of 108.
#
# To add a new ticker: add it to config.YAHOO_TICKERS.
#
# Usage:
#   python3 yahoofinanceimporter.py          # imports all tickers
#   python3 yahoofinanceimporter.py ^GSPC    # imports a single ticker

import sys
import os
import time
import random
from datetime import datetime, timedelta
from collections import defaultdict

import logging

import pandas as pd
import yfinance as yf

import database

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Silence yfinance's own chatter (e.g. its misleading "possibly delisted"
# message, which usually really means "Yahoo returned nothing / rate-limited").
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

TICKERS = config.YAHOO_TICKERS

# ── SETTINGS ───────────────────────────────────────────────────

FIRST_RUN_DAYS = 730   # Days of history to fetch on first import
REIMPORT_DAYS = 3      # Always reimport this many recent days for corrections
FUND_ID_PREFIX = "YF"  # Prefix to avoid clashes with FT funds


# ── HELPERS ────────────────────────────────────────────────────


def make_fund_id(ticker):
    return f"{FUND_ID_PREFIX}:{ticker}"


def download_with_backoff(tickers, start_date, end_date, tries=4):
    """Batched download with exponential backoff.

    Prints a clear signal about throttling: a clean first-try success is silent,
    a success that needed retries is flagged (Yahoo is still throttling), and a
    full failure is stated plainly instead of yfinance's "possibly delisted".
    """
    for attempt in range(tries):
        try:
            data = yf.download(
                tickers,
                start=start_date,
                end=end_date,
                group_by="ticker",
                threads=False,        # serial — parallel threads worsen rate limits
                progress=False,
                auto_adjust=True,
            )
            if data is not None and not data.empty:
                if attempt > 0:
                    print(f"    ⚠ succeeded only on attempt {attempt + 1}/{tries} "
                          f"— Yahoo still throttling, not yet fully clear")
                return data
            print(f"    attempt {attempt + 1}/{tries}: no data returned "
                  f"(empty — almost always rate-limiting, NOT delisting)")
        except Exception as e:
            print(f"    attempt {attempt + 1}/{tries} error: {e}")
        time.sleep((2 ** attempt) + random.uniform(0, 1))  # 1s,2s,4s,8s + jitter
    print(f"    ✗ gave up after {tries} attempts — Yahoo not responding (throttled)")
    return None


def rows_from_frame(data, ticker):
    """Extract clean OHLCV row dicts for one ticker from a (possibly multi-ticker) frame."""
    rows = []
    multi = isinstance(data.columns, pd.MultiIndex)
    try:
        sub = data[ticker] if multi else data
    except KeyError:
        return rows

    sub = sub.dropna(subset=["Close"])
    for date, row in sub.iterrows():
        close = row["Close"]
        if pd.isna(close):
            continue

        def col_or_close(name):
            v = row[name]
            return float(v) if not pd.isna(v) else float(close)

        vol = row["Volume"]
        rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": col_or_close("Open"),
            "high": col_or_close("High"),
            "low": col_or_close("Low"),
            "close": float(close),
            "volume": int(vol) if not pd.isna(vol) else 0,
        })
    return rows


def plan_ticker(conn, ticker, name, asset_type):
    """
    Work out the start date for this ticker and delete recent rows for reimport.
    Pure local DB work — no Yahoo calls here.
    """
    fund_id = make_fund_id(ticker)
    fund_name = f"{name} ({ticker})"
    latest_date = database.get_latest_date(conn, fund_id)
    reimport_from = (datetime.today() - timedelta(days=REIMPORT_DAYS)).strftime("%Y-%m-%d")

    if latest_date:
        deleted = conn.execute(
            "DELETE FROM prices WHERE fund_id=? AND date >= ?",
            (fund_id, reimport_from),
        )
        conn.commit()
        if deleted.rowcount > 0:
            print(f"  {fund_name:<45} | cleared {deleted.rowcount} recent rows for reimport")
        day_after_latest = (
            datetime.strptime(latest_date, "%Y-%m-%d") + timedelta(days=1)
        ).strftime("%Y-%m-%d")
        start_date = min(day_after_latest, reimport_from)
    else:
        start_date = (datetime.today() - timedelta(days=FIRST_RUN_DAYS)).strftime("%Y-%m-%d")
        print(f"  {fund_name:<45} | first import | {FIRST_RUN_DAYS} days")

    return {
        "ticker": ticker,
        "name": name,
        "fund_id": fund_id,
        "fund_name": fund_name,
        "asset_type": asset_type,
        "start_date": start_date,
    }


# ── MAIN ───────────────────────────────────────────────────────


def main():
    if len(sys.argv) > 1:
        ticker_arg = sys.argv[1].upper()
        match = next((t for t in TICKERS if t[0].upper() == ticker_arg), None)
        if match:
            tickers_to_run = [match]
        else:
            print(f"  Ticker {ticker_arg} not in list, importing with ticker as name.")
            tickers_to_run = [(sys.argv[1], sys.argv[1], None)]
    else:
        tickers_to_run = TICKERS

    print("Yahoo Finance Importer")
    print(f"Processing {len(tickers_to_run)} ticker(s)...\n")

    conn = database.get_connection()
    database.create_table(conn)

    # 1) Plan every ticker (computes start dates, clears recent rows) — no Yahoo calls
    plans = []
    for item in tickers_to_run:
        ticker = item[0]
        name = item[1]
        asset_type = item[2] if len(item) > 2 else None
        plans.append(plan_ticker(conn, ticker, name, asset_type))

    end_date = datetime.today().strftime("%Y-%m-%d")

    # 2) Group by start date; split indices (^) from the rest within each group
    by_start = defaultdict(list)
    for p in plans:
        by_start[p["start_date"]].append(p["ticker"])

    print("\nFetching in batched calls...")
    frames = []  # list of (set_of_symbols, dataframe)
    for start_date, syms in by_start.items():
        idx = [s for s in syms if s.startswith("^")]
        oth = [s for s in syms if not s.startswith("^")]
        for sub in (idx, oth):
            if not sub:
                continue
            print(f"  {len(sub)} ticker(s) from {start_date} to {end_date}")
            d = download_with_backoff(sub, start_date, end_date)
            if d is not None:
                frames.append((set(sub), d))
            time.sleep(2)  # gap between batched calls

    # 3) Save per ticker from whichever frame holds it
    total_saved = 0
    for p in plans:
        rows = []
        for syms_set, d in frames:
            if p["ticker"] in syms_set:
                rows = rows_from_frame(d, p["ticker"])
                break

        if not rows:
            print(f"  ✗ {p['fund_name']:<45} no data")
            continue

        saved = database.save_prices(
            conn, p["fund_id"], p["fund_name"], rows, asset_type=p["asset_type"]
        )
        total_saved += saved
        dates = [r["date"] for r in rows]
        print(f"  ✓ {p['fund_name']:<45} {len(rows)} rows | {saved} new | {min(dates)} → {max(dates)}")

    # 4) Rebuild composites from fresh data
    print("\nBuilding composite prices...")
    try:
        import build_composite_prices
        build_composite_prices.main()
    except Exception as e:
        print(f"  ERROR building composites: {e}")

    conn.close()
    print(f"\nDone. {total_saved} total new rows saved.")


if __name__ == "__main__":
    main()