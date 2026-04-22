# live_prices.py
# Fetches the latest available price for all Yahoo Finance tickers
# using yfinance Ticker.info — gives delayed live price (15-20 min delay).
# Upserts today's row into the prices table.
# Safe to run multiple times — overwrites today's price each time.
#
# Usage:
#   python3 live_prices.py              # updates all tickers
#   python3 live_prices.py NATP.L       # updates a single ticker

import sys
import yfinance as yf
from datetime import datetime
import database
import config

TODAY = datetime.today().strftime('%Y-%m-%d')


def fetch_live_price(ticker):
    """Fetch latest available price via Ticker.info."""
    try:
        info = yf.Ticker(ticker).info
        price = info.get('regularMarketPrice')
        if price is None:
            print(f"  WARNING: No regularMarketPrice for {ticker}")
            return None
        return float(price)
    except Exception as e:
        print(f"  ERROR fetching {ticker}: {e}")
        return None


def upsert_today(conn, fund_id, fund_name, price):
    """Insert or replace today's price row."""
    # Delete existing today row if any
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
    print(f"Fetching {len(tickers_to_run)} ticker(s)...\n")

    conn = database.get_connection()
    database.create_table(conn)

    # Tickers where regularMarketPrice needs dividing by 100
    DIVIDE_BY_100 = {'WEAP.L'}

    updated = 0
    failed  = 0

    for item in tickers_to_run:
        ticker    = item[0]
        name      = item[1]
        fund_id   = f"YF:{ticker}"
        fund_name = f"{name} ({ticker})"

        price = fetch_live_price(ticker)
        if price is not None:
            if ticker in DIVIDE_BY_100:
                price = price / 100
            upsert_today(conn, fund_id, fund_name, price)
            print(f"  ✓ {name:<45} {price:.4f}")
            updated += 1
        else:
            print(f"  ✗ {name:<45} failed")
            failed += 1

    conn.close()
    print(f"\nDone. Updated: {updated} | Failed: {failed}")


if __name__ == '__main__':
    main()