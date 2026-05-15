# yahoofinance_backfill.py
# Backfill Yahoo Finance data for a specific date range.
# Useful for filling gaps identified by the Data Quality dashboard.
#
# Usage:
#   python3 yahoofinance_backfill.py                          # interactive mode
#   python3 yahoofinance_backfill.py 2026-03-10 2026-03-20   # specific date range
#   python3 yahoofinance_backfill.py --ticker ^GSPC --from 2026-03-01 --to 2026-03-31
#   python3 yahoofinance_backfill.py --all --from 2021-01-01 --to 2024-03-13

# yahoofinance_backfill.py
# ... (docstring) ...

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import yfinance as yf
from datetime import datetime, timedelta
import database
import config

TICKERS = config.YAHOO_TICKERS
FUND_ID_PREFIX = "YF"


def make_fund_id(ticker):
    return f"{FUND_ID_PREFIX}:{ticker}"


def list_tickers():
    print("\nAvailable tickers:")
    print("-" * 60)
    for i, item in enumerate(TICKERS):
        ticker, name = item[0], item[1]
        asset_type = item[2] if len(item) > 2 else ""
        print(f"  {i+1:3d}. {ticker:<15s} {name:<35s} {asset_type}")
    print("-" * 60)


def find_ticker(query):
    query = query.upper().strip()
    for item in TICKERS:
        if item[0].upper() == query:
            return item
    matches = []
    for item in TICKERS:
        if query.lower() in item[1].lower() or query.lower() in item[0].lower():
            matches.append(item)
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        print(f"\nMultiple matches for '{query}':")
        for m in matches:
            print(f"  {m[0]:<15s} {m[1]}")
        return None
    else:
        print(f"\nNo ticker found matching '{query}'")
        return None


def parse_date(date_str):
    formats = ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d %b %Y', '%d %B %Y']
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    date_str_lower = date_str.lower().strip()
    if date_str_lower == 'today':
        return datetime.today()
    elif date_str_lower == 'yesterday':
        return datetime.today() - timedelta(days=1)
    elif date_str_lower.endswith('days ago'):
        try:
            days = int(date_str_lower.split()[0])
            return datetime.today() - timedelta(days=days)
        except:
            pass
    return None


def fetch_and_save(conn, ticker, name, asset_type, start_date, end_date):
    fund_id = make_fund_id(ticker)
    fund_name = f"{name} ({ticker})"
    
    print(f"\n  {fund_name}")
    print(f"  Period: {start_date.strftime('%d %b %Y')} → {end_date.strftime('%d %b %Y')}")
    
    try:
        data = yf.download(
            ticker,
            start=start_date.strftime('%Y-%m-%d'),
            end=(end_date + timedelta(days=1)).strftime('%Y-%m-%d'),
            progress=False,
            auto_adjust=True,
        )
    except Exception as e:
        print(f"  ERROR fetching: {e}")
        return 0
    
    if data.empty:
        print(f"  No data returned for this period.")
        return 0
    
    rows = []
    for date, row in data.iterrows():
        try:
            rows.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": float(row["Open"].item() if hasattr(row["Open"], "item") else row["Open"]),
                "high": float(row["High"].item() if hasattr(row["High"], "item") else row["High"]),
                "low": float(row["Low"].item() if hasattr(row["Low"], "item") else row["Low"]),
                "close": float(row["Close"].item() if hasattr(row["Close"], "item") else row["Close"]),
                "volume": int(row["Volume"].item() if hasattr(row["Volume"], "item") else row["Volume"]),
            })
        except Exception as e:
            print(f"  WARNING: Could not parse row for {date}: {e}")
            continue
    
    if not rows:
        print(f"  No valid rows to save.")
        return 0
    
    existing_dates = set()
    existing = conn.execute(
        "SELECT date FROM prices WHERE fund_id = ? AND date BETWEEN ? AND ?",
        (fund_id, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    ).fetchall()
    for row in existing:
        existing_dates.add(row[0])
    
    new_rows = [r for r in rows if r['date'] not in existing_dates]
    
    if new_rows:
        saved = database.save_prices(conn, fund_id, fund_name, new_rows, asset_type=asset_type)
        print(f"  {len(rows)} rows fetched | {saved} new rows saved | {len(rows) - len(new_rows)} already in DB")
        return saved
    else:
        print(f"  {len(rows)} rows fetched | 0 new (all already in database)")
        return 0


def interactive_mode():
    print("\n" + "=" * 60)
    print("  YAHOO FINANCE BACKFILL TOOL")
    print("=" * 60)
    print("\nThis tool fills gaps in your Yahoo Finance price data.")
    
    while True:
        print("\n" + "-" * 60)
        print("Options:")
        print("  1. Fill gaps for ALL tickers")
        print("  2. Fill gaps for a SPECIFIC ticker")
        print("  3. List all available tickers")
        print("  4. Fill gaps for tickers matching a keyword")
        print("  q. Quit")
        print("-" * 60)
        
        choice = input("\nChoose an option: ").strip()
        
        if choice.lower() == 'q':
            print("Goodbye!")
            break
        
        elif choice == '1':
            from_date = _input_date("Start date (YYYY-MM-DD or '30 days ago'): ")
            to_date = _input_date("End date (YYYY-MM-DD or 'today'): ")
            if not from_date or not to_date:
                continue
            
            conn = database.get_connection()
            database.create_table(conn)
            total = 0
            print(f"\nProcessing ALL {len(TICKERS)} tickers...")
            for item in TICKERS:
                total += fetch_and_save(conn, item[0], item[1],
                                        item[2] if len(item) > 2 else None,
                                        from_date, to_date)
            conn.close()
            print(f"\nDone. {total} total new rows saved.")
        
        elif choice == '2':
            list_tickers()
            ticker_input = input("\nEnter ticker symbol (e.g. ^GSPC, AMZN): ").strip()
            match = find_ticker(ticker_input)
            if not match:
                continue
            
            from_date = _input_date("Start date: ")
            to_date = _input_date("End date: ")
            if not from_date or not to_date:
                continue
            
            conn = database.get_connection()
            database.create_table(conn)
            total = fetch_and_save(conn, match[0], match[1],
                                   match[2] if len(match) > 2 else None,
                                   from_date, to_date)
            conn.close()
            print(f"\nDone. {total} new rows saved.")
        
        elif choice == '3':
            list_tickers()
        
        elif choice == '4':
            keyword = input("\nEnter keyword to search ticker names: ").strip()
            matches = [t for t in TICKERS if keyword.lower() in t[1].lower() or keyword.lower() in t[0].lower()]
            if not matches:
                print(f"No tickers match '{keyword}'")
                continue
            
            print(f"\nFound {len(matches)} matching tickers:")
            for m in matches:
                print(f"  {m[0]:<15s} {m[1]}")
            
            confirm = input("\nImport data for all these tickers? (y/n): ").strip().lower()
            if confirm != 'y':
                continue
            
            from_date = _input_date("Start date: ")
            to_date = _input_date("End date: ")
            if not from_date or not to_date:
                continue
            
            conn = database.get_connection()
            database.create_table(conn)
            total = 0
            for m in matches:
                total += fetch_and_save(conn, m[0], m[1],
                                        m[2] if len(m) > 2 else None,
                                        from_date, to_date)
            conn.close()
            print(f"\nDone. {total} total new rows saved.")
        
        else:
            print("Invalid option. Please try again.")


def _input_date(prompt):
    while True:
        date_str = input(prompt).strip()
        if date_str.lower() == 'q':
            return None
        parsed = parse_date(date_str)
        if parsed:
            return parsed
        print(f"  Could not parse '{date_str}'. Try YYYY-MM-DD, DD/MM/YYYY, or '30 days ago'.")


def parse_args():
    args = {'tickers': 'ALL', 'from_date': None, 'to_date': None, 'interactive': False}
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in ('--ticker', '-t'):
            i += 1
            args['tickers'] = sys.argv[i]
        elif arg in ('--from', '-f'):
            i += 1
            args['from_date'] = parse_date(sys.argv[i])
        elif arg in ('--to'):
            i += 1
            args['to_date'] = parse_date(sys.argv[i])
        elif arg == '--all':
            args['tickers'] = 'ALL'
        elif arg in ('--interactive', '-i'):
            args['interactive'] = True
        elif arg in ('--help', '-h'):
            print("""
Yahoo Finance Backfill Tool
============================
Usage:
  python3 yahoofinance_backfill.py                          Interactive mode
  python3 yahoofinance_backfill.py 2026-03-10 2026-03-20   All tickers, date range
  python3 yahoofinance_backfill.py --ticker ^GSPC --from 2026-03-01 --to 2026-03-15
  python3 yahoofinance_backfill.py --all -f 2021-01-01 -t 2024-03-13

Options:
  -t, --ticker TICKER    Specific ticker
  -f, --from DATE        Start date (YYYY-MM-DD)
  -t, --to DATE          End date
  --all                  All tickers (default)
  -i, --interactive      Interactive mode
  -h, --help             This help
""")
            sys.exit(0)
        else:
            if not args['from_date']:
                args['from_date'] = parse_date(arg)
            elif not args['to_date']:
                args['to_date'] = parse_date(arg)
        i += 1
    
    return args


def main():
    args = parse_args()
    
    if args['interactive'] or (args['from_date'] is None and args['to_date'] is None and args['tickers'] == 'ALL'):
        interactive_mode()
        return
    
    if not args['from_date']:
        print("ERROR: Start date required. Use -f or --from.")
        sys.exit(1)
    if not args['to_date']:
        args['to_date'] = datetime.today()
        print(f"End date not specified. Using today: {args['to_date'].strftime('%d %b %Y')}")
    
    if args['from_date'] > args['to_date']:
        print("ERROR: Start date must be before end date.")
        sys.exit(1)
    
    if args['tickers'] == 'ALL':
        tickers_to_run = TICKERS
    else:
        match = find_ticker(args['tickers'])
        if not match:
            sys.exit(1)
        tickers_to_run = [match]
    
    print(f"\nYahoo Finance Backfill")
    print(f"Period: {args['from_date'].strftime('%d %b %Y')} → {args['to_date'].strftime('%d %b %Y')}")
    print(f"Tickers: {len(tickers_to_run)}")
    
    conn = database.get_connection()
    database.create_table(conn)
    
    total_saved = 0
    for item in tickers_to_run:
        ticker, name = item[0], item[1]
        asset_type = item[2] if len(item) > 2 else None
        total_saved += fetch_and_save(conn, ticker, name, asset_type,
                                      args['from_date'], args['to_date'])
    
    conn.close()
    
    print(f"\n{'=' * 60}")
    print(f"Complete. {total_saved} total new rows saved across {len(tickers_to_run)} ticker(s).")
    print(f"  Run build_composite_prices.py to update composite data.")


if __name__ == "__main__":
    main()