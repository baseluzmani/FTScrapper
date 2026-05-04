# runner.py
# This is the entry point for the entire scraper.
# It is the only file you run: python3 runner.py
# Its job is to coordinate the other modules in the right order.

import config
import database
import scraper


def process_fund(conn, fund):
    fund_id = fund["id"]
    fund_name = fund["name"]

    print(f"\n{'='*50}")
    print(f"Processing: {fund_name}")
    print(f"Fund ID:    {fund_id}")
    print(f"{'='*50}")

    latest_date = database.get_latest_date(conn, fund_id)

    if latest_date:
        print(f"  Latest date in database: {latest_date}")
    else:
        print(f"  No existing data found — this is a first run.")

    rows, fetched_name = scraper.scrape_fund(fund_id, fund_name, latest_date)

    if rows:
        saved = database.save_prices(
            conn, fund_id, fetched_name, rows, asset_type="Fund"
        )
        print(f"  Saved {saved} new rows to database.")
    else:
        print(f"  No new data to save.")

    # Always update the name on all rows in case it changed
    database.update_fund_name(conn, fund_id, fetched_name)
    print(f"  Fund name: {fetched_name}")


def main():
    print("FT Fund Scraper starting...")

    # Open one database connection for the entire run
    conn = database.get_connection()

    # Make sure the table exists (safe to call every time)
    database.create_table(conn)

    # Process every fund in config.py
    for fund in config.FUNDS:
        try:
            process_fund(conn, fund)
        except Exception as e:
            print(f"  ERROR processing {fund['name']}: {e}")

    # Rebuild composite and calculated prices from fresh data
    print("\nBuilding composite prices...")
    try:
        import build_composite_prices
        build_composite_prices.main()
    except Exception as e:
        print(f"  ERROR building composites: {e}")

    # Close the database connection when all funds are done
    conn.close()
    print("\nAll done.")


# This is a Python convention.
# It means: only run main() if this file is executed directly.
# If another file imports runner.py, main() won't run automatically.
if __name__ == "__main__":
    main()
