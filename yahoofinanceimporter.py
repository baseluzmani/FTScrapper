# yahoofinanceimporter.py
# Imports benchmark and index data from Yahoo Finance into the database.
# Checks latest date per ticker and only adds new rows — safe to run repeatedly.
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

# ── TICKER LIST ────────────────────────────────────────────────
# Add or remove tickers here. Format: (ticker, display_name)
# To add a new one, just append a new line in the same format.

TICKERS = [
    # ── Indices
    ("^GSPC", "S&P 500", "Index"),
    ("^FTSE", "FTSE 100", "Index"),
    ("^FTMC", "FTSE 250", "Index"),
    ("XU030.IS", "BIST 30", "Index"),
    ("^N225", "Nikkei 225", "Index"),
    ("^STOXX50E", "Euro Stoxx 50", "Index"),
    ("^IXIC", "NASDAQ Composite", "Index"),
    # ── Global Equity ETFs
    ("URTH", "MSCI World", "ETF"),
    ("EEM", "MSCI Emerging Markets", "ETF"),
    ("VWRL.L", "FTSE All World", "ETF"),
    ("CSP1.L", "iShares Core S&P 500 ETF", "ETF"),
    ("XDJP.L", "Xtr Nikkei 225 UCITS ETF", "ETF"),
    ("HMCH.L", "HSBC MSCI China UCITS ETF", "ETF"),
    ("HCAN.L", "HSBC MSCI Canada UCITS ETF", "ETF"),
    ("DFEU.L", "iShares Europe Def UETF", "ETF"),
    ("XAIX.L", "X AI and Big Data UCITS ETF", "ETF"),
    ("AINF.L", "iShares AI Infrastructure ETF", "ETF"),
    ("UIFS.L", "iShares S&P 500 Financials ETF", "ETF"),
    ("FCBR.L", "FT Nasdaq Cs UCITS ETF", "ETF"),
    ("QANT.L", "iShares Quantum Computing ETF", "ETF"),
    ("QWTM.L", "WisdomTree Quantum Computing ETF", "ETF"),
    ("NATP.L", "Future of Defence UCITS ETF", "ETF"),
    ("SPGP.L", "iShares Gold Producers ETF", "ETF"),
    ("CSCA.L", "iShares MSCI Canada UCITS ETF", "ETF"),
    ("PLAY.L", "iShares Digital Entertainment ETF", "ETF"),
    # ── Commodities — Futures
    ("GC=F", "Gold Futures", "Commodity"),
    ("SI=F", "Silver Futures", "Commodity"),
    ("HG=F", "Copper Futures", "Commodity"),
    ("ZW=F", "Wheat Futures", "Commodity"),
    ("CL=F", "Crude Oil Futures", "Commodity"),
    ("NG=F", "Natural Gas Futures", "Commodity"),
    ("CC=F", "Cocoa Futures", "Commodity"),
    # ── Commodity ETCs (London listed, GBP)
    ("SGLN.L", "iShares Physical Gold ETC", "Commodity"),
    ("SSLN.L", "iShares Physical Silver ETC", "Commodity"),
    ("PHPP.L", "WT Physical Precious Metals ETC", "Commodity"),
    ("COPB.L", "WisdomTree Copper ETC", "Commodity"),
    ("WEAP.L", "WisdomTree Wheat ETC", "Commodity"),
    ("MINE.L", "iShares Copper Miners ETF", "Commodity"),
    ("NRGT.L", "WisdomTree Energy Transition ETC", "Commodity"),
    ("BRNB.L", "iShares Brent Oil ETC", "Commodity"),
    ("NGSP.L", "WisdomTree Natural Gas ETC", "Commodity"),
    ("COCO", "WisdomTree Cocoa", "Commodity"),
    # ── Currencies & FX
    ("GBPUSD=X", "GBP/USD", "Index"),
    ("CNY=X", "USD/CNY", "Index"),
    # ── Crypto
    ("BTC-GBP", "Bitcoin GBP", "Commodity"),
    ("ETH-GBP", "Ethereum GBP", "Commodity"),
    # ── Individual Stocks
    ("GOOG", "Alphabet (Google)", "Stock"),
    ("AMZN", "Amazon", "Stock"),
    ("NVDA", "NVIDIA", "Stock"),
    ("ASML", "ASML Holding", "Stock"),
    ("QCOM", "Qualcomm", "Stock"),
    ("MU", "Micron Technology", "Stock"),
    ("JPM", "JPMorgan Chase", "Stock"),
    ("NVO", "Novo Nordisk", "Stock"),
    ("LLY", "Eli Lilly", "Stock"),
    ("GSK.L", "GSK plc", "Stock"),
    ("HSBA.L", "HSBC Holdings", "Stock"),
    ("DATA.L", "GlobalData plc", "Stock"),
    ("BRBY.L", "Burberry Group", "Stock"),
    ("QQ.L", "QinetiQ Group", "Stock"),
    ("HFG.L", "Hilton Food Group", "Stock"),
    ("CCH.L", "Coca-Cola HBC", "Stock"),
    ("BA.L", "BAE Systems", "Stock"),
]

# ── SETTINGS ───────────────────────────────────────────────────

FIRST_RUN_DAYS = 730  # How many days of history to fetch on first import
FUND_ID_PREFIX = "YF"  # Prefix added to fund_id to avoid clashes with FT funds
# e.g. ticker ^GSPC becomes fund_id "YF:^GSPC"


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
    and save to database.
    """
    fund_id = make_fund_id(ticker)
    fund_name = f"{name} ({ticker})"

    # Check what we already have
    latest_date = database.get_latest_date(conn, fund_id)

    if latest_date:
        # Delete last 3 days and reimport to catch any Yahoo corrections
        delete_from = (datetime.today() - timedelta(days=3)).strftime("%Y-%m-%d")
        deleted = conn.execute(
            "DELETE FROM fund_prices WHERE fund_id=? AND date >= ?",
            (fund_id, delete_from),
        )
        conn.commit()
        if deleted.rowcount > 0:
            print(
                f"  Deleted {deleted.rowcount} recent rows from {delete_from} for fresh reimport"
            )

        start_date = delete_from
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

    # Check if already up to date
    if latest_date and latest_date >= (datetime.today() - timedelta(days=1)).strftime(
        "%Y-%m-%d"
    ):
        print(f"  Already up to date.")
        return 0

    rows = fetch_yahoo(ticker, start_date, end_date)

    if not rows:
        return 0

    saved = database.save_prices(conn, fund_id, fund_name, rows, asset_type=asset_type)
    dates = [r["date"] for r in rows]
    print(
        f"  {len(rows)} rows fetched | {saved} new rows saved | {min(dates)} → {max(dates)}"
    )
    return saved


# def clean_bad_rows(conn, threshold=4.0):
#    """
#    Find and delete rows where price jumped more than threshold*100%
#    compared to the previous day. These are typically caused by
#    currency redenominations or data errors in Yahoo Finance.
#    Prints a summary of deleted rows.
#    """
#    print("\n── Checking for bad price data...")
#
#    bad_rows = conn.execute(
#        """
#        SELECT
#            a.fund_id,
#            a.fund_name,
#            a.date,
#            b.close as prev_close,
#            a.close as curr_close,
#            ROUND((a.close / b.close - 1) * 100, 1) as pct_change
#        FROM fund_prices a
#        JOIN fund_prices b
#            ON a.fund_id = b.fund_id
#            AND b.date = (
#                SELECT MAX(date) FROM fund_prices
#                WHERE fund_id = a.fund_id AND date < a.date
#            )
#        WHERE ABS(a.close / b.close - 1) > ?
#        ORDER BY ABS(a.close / b.close - 1) DESC
#    """,
#        (threshold,),
#    ).fetchall()
#
#    if not bad_rows:
#        print("  No bad rows found.")
#        return#
#
#    print(f"  Found {len(bad_rows)} suspicious rows — deleting:\n")
#    deleted = 0
#    for r in bad_rows:
#        print(
#            f"  DELETE {r[0]:<25} {r[2]}  "
#            f"prev:{r[3]:.2f}  curr:{r[4]:.2f}  chg:{r[5]}%"
#        )
#        conn.execute("DELETE FROM fund_prices WHERE fund_id=? AND date=?", (r[0], r[2]))
#        deleted += 1
#
#    conn.commit()
#    print(f"\n  Deleted {deleted} bad rows.")


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
            tickers_to_run = [(sys.argv[1], sys.argv[1])]
    else:
        tickers_to_run = TICKERS

    print(f"Yahoo Finance Importer")
    print(f"Processing {len(tickers_to_run)} ticker(s)...\n")

    conn = database.get_connection()
    database.create_table(conn)

    total_saved = 0

    for item in tickers_to_run:
        ticker, name = item[0], item[1]
        asset_type = item[2] if len(item) > 2 else None
        print(f"── {name} ({ticker})")
        try:
            saved = process_ticker(conn, ticker, name, asset_type=asset_type)
            total_saved += saved
        except Exception as e:
            print(f"  ERROR: {e}")
        print()

    # clean_bad_rows(conn)
    conn.close()
    print(f"\nDone. {total_saved} total new rows saved.")
    print(f"\nTo add a new ticker permanently, add a line to TICKERS:")
    print(f'  ("TICKER", "Display Name"),')


if __name__ == "__main__":
    main()
