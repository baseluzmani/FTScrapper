# runner.py
# Entry point for the entire scraper.
# Run: python3 runner.py
# Optional flags:
#   --no-holdings   skip holdings scrape (faster, prices only)
#   --holdings-only skip price scrape, only update holdings

import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import database
import scraper


def process_fund(conn, fund, scrape_prices=True, scrape_holdings=True):
    fund_id      = fund["id"]
    holdings_id  = fund.get("holdings_id", fund_id)
    fund_name    = fund["name"]

    print(f"\n{'='*50}")
    print(f"Processing: {fund_name}")
    print(f"Fund ID:    {fund_id}")
    if holdings_id != fund_id:
        print(f"Holdings ID:{holdings_id}  (override)")
    print(f"{'='*50}")

    # ── Price scrape ──────────────────────────────────────
    if scrape_prices:
        latest_date = database.get_latest_date(conn, fund_id)
        if latest_date:
            print(f"  Latest date in database: {latest_date}")
        else:
            print(f"  No existing data found — first run.")

        rows, fetched_name = scraper.scrape_fund(fund_id, fund_name, latest_date)

        if rows:
            saved = database.save_prices(conn, fund_id, fetched_name, rows, asset_type="Fund")
            print(f"  Saved {saved} new price rows.")
        else:
            print(f"  No new price data.")

        database.update_fund_name(conn, fund_id, fetched_name)
        print(f"  Fund name: {fetched_name}")

    # ── Holdings scrape ───────────────────────────────────
    if scrape_holdings:
        holdings = scraper.scrape_holdings(fund_id, holdings_id, fund_name)
        if holdings:
            saved = database.save_holdings(conn, fund_id, fund_name, holdings)
            print(f"  Saved {saved} holding rows.")
        else:
            print(f"  No holdings data retrieved.")


def main():
    parser = argparse.ArgumentParser(description="FTScrapper runner")
    parser.add_argument("--no-holdings",    action="store_true", help="Skip holdings scrape")
    parser.add_argument("--holdings-only",  action="store_true", help="Skip price scrape")
    args = parser.parse_args()

    do_prices   = not args.holdings_only
    do_holdings = not args.no_holdings

    print("FT Fund Scraper starting...")
    conn = database.get_connection()
    database.create_table(conn)
    database.create_holdings_table(conn)

    for fund in config.FUNDS:
        try:
            process_fund(conn, fund,
                         scrape_prices=do_prices,
                         scrape_holdings=do_holdings)
        except Exception as e:
            print(f"  ERROR processing {fund['name']}: {e}")

    if do_prices:
        print("\nBuilding composite prices...")
        try:
            import build_composite_prices
            build_composite_prices.main()
        except Exception as e:
            print(f"  ERROR building composites: {e}")

    conn.close()
    print("\nAll done.")


if __name__ == "__main__":
    main()