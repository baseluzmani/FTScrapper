# live_prices.py
# Fetches the latest available price for all Yahoo Finance tickers
# using a SINGLE batched yf.download() call instead of per-ticker .info.
#
# Why the change:
#   - .info hits Yahoo's heaviest endpoint (full quoteSummary) per ticker.
#     108 tickers = 108 heavy calls = guaranteed rate-limit (HTTP 429).
#   - yf.download() pulls the whole list in essentially one round-trip,
#     reads as a normal request, and stays under Yahoo's radar.
#
# Price source: last available daily Close. During market hours this is the
# current delayed price; after close it's the official close.
#
# Usage:
#   python3 live_prices.py              # updates all tickers
#   python3 live_prices.py NATP.L       # updates a single ticker

import sys
import os
import time
import random
import logging
from datetime import datetime

import pandas as pd
import yfinance as yf

import database

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Quiet yfinance's misleading internal messages ("possibly delisted" usually
# just means Yahoo returned nothing because it's rate-limiting).
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

TODAY = datetime.today().strftime('%Y-%m-%d')

# Tickers where Yahoo quotes in pence (GBX) and need dividing by 100 -> GBP
DIVIDE_BY_100 = {'WEAP.L', 'NRGT.L'}


def download_with_backoff(tickers, tries=4):
    """One batched download for all tickers, with exponential backoff.

    Flags when a fetch only succeeded after retries (a sign Yahoo is still
    throttling) so diagnostic runs are easy to read.
    """
    for attempt in range(tries):
        try:
            data = yf.download(
                tickers,
                period="2d",
                interval="1d",
                group_by="ticker",
                threads=False,        # serial — parallel threads trip rate limits
                progress=False,
                auto_adjust=False,
            )
            if data is not None and not data.empty:
                if attempt > 0:
                    print(f"  ⚠ succeeded only on attempt {attempt + 1}/{tries} "
                          f"— Yahoo still throttling, not yet fully clear")
                return data
            print(f"  attempt {attempt + 1}/{tries}: no data "
                  f"(empty — usually rate-limiting, not delisting)")
        except Exception as e:
            print(f"  attempt {attempt + 1}/{tries} error: {e}")
        # 1s, 2s, 4s, 8s (+ jitter) — gives Yahoo room to cool off
        time.sleep((2 ** attempt) + random.uniform(0, 1))
    print(f"  ✗ gave up after {tries} attempts — Yahoo not responding (throttled)")
    return None


def extract_close(data, ticker):
    """Pull the latest non-null Close for a ticker, handling single vs multi-ticker frames."""
    try:
        if isinstance(data.columns, pd.MultiIndex):
            series = data[ticker]["Close"].dropna()
        else:
            # single-ticker download returns flat columns
            series = data["Close"].dropna()
        if len(series) == 0:
            return None
        return float(series.iloc[-1])
    except (KeyError, IndexError):
        return None


def upsert_today(conn, fund_id, fund_name, price):
    """Insert or replace today's price row."""
    conn.execute(
        "DELETE FROM prices WHERE fund_id=? AND date=?",
        (fund_id, TODAY)
    )
    conn.execute("""
        INSERT INTO prices (fund_id, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (fund_id, TODAY, price, price, price, price))
    conn.commit()


def main():
    if len(sys.argv) > 1:
        ticker_arg = sys.argv[1].upper()
        match = next((t for t in config.YAHOO_TICKERS if t[0].upper() == ticker_arg), None)
        tickers_to_run = [match] if match else [(sys.argv[1], sys.argv[1], None)]
    else:
        tickers_to_run = config.YAHOO_TICKERS

    print(f"Live Price Updater — {TODAY}")
    print(f"Fetching {len(tickers_to_run)} ticker(s) in one batched call...\n")

    symbols = [item[0] for item in tickers_to_run]

    # Indices (^) sometimes misbehave in a mixed batch. Split them out so
    # an index quirk can't wipe the whole frame — still only 2 requests.
    index_syms = [s for s in symbols if s.startswith('^')]
    other_syms = [s for s in symbols if not s.startswith('^')]

    data_frames = {}
    for group in (index_syms, other_syms):
        if not group:
            continue
        d = download_with_backoff(group)
        if d is not None:
            data_frames[id(group)] = d
        time.sleep(2)  # small gap between the two batched calls

    conn = database.get_connection()
    database.create_table(conn)

    updated = 0
    failed = 0

    for item in tickers_to_run:
        ticker = item[0]
        name = item[1]
        fund_id = f"YF:{ticker}"
        fund_name = f"{name} ({ticker})"

        # find which frame this ticker landed in
        price = None
        for d in data_frames.values():
            price = extract_close(d, ticker)
            if price is not None:
                break

        if price is not None:
            if ticker in DIVIDE_BY_100:
                price = price / 100
            upsert_today(conn, fund_id, fund_name, price)
            print(f"  ✓ {name:<45} {price:.4f}")
            updated += 1
        else:
            print(f"  ✗ {name:<45} no data")
            failed += 1

    conn.close()
    print(f"\nDone. Updated: {updated} | Failed: {failed}")


if __name__ == '__main__':
    main()