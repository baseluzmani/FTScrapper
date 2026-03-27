# import_manual.py
# Imports a manually copied fund data file into the database.
# Format expected:
#   Line 1: Fund name
#   Line 2: Fund ID (e.g. LU2092165666:GBP)
#   Line 3: Header row (Date, Open, High, Low, Close, Volume) — skipped
#   Line 4+: Data rows tab-separated
#
# Usage:
#   python3 import_manual.py                        # reads data/import/fund.txt
#   python3 import_manual.py data/import/other.txt  # reads a specific file

import sys
from datetime import datetime
import database


def parse_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]

    # Remove any blank lines
    lines = [l for l in lines if l]

    # First line: fund name
    fund_name = lines[0]

    # Second line: fund ID
    fund_id = lines[1]

    # Third line: header — skip it
    # Lines 4+: data
    rows = []
    skipped = 0

    for line in lines[3:]:
        parts = line.split("\t")

        if len(parts) != 6:
            print(f"  WARNING: Skipping malformed line: {line}")
            skipped += 1
            continue

        date_str, open_val, high_val, low_val, close_val, vol_val = parts

        # Parse date from "Thursday, March 12, 2026" → "2026-03-12"
        try:
            date = datetime.strptime(date_str.strip(), "%A, %B %d, %Y")
            date_formatted = date.strftime("%Y-%m-%d")
        except ValueError:
            print(f"  WARNING: Could not parse date '{date_str}', skipping.")
            skipped += 1
            continue

        rows.append(
            {
                "date": date_formatted,
                "open": float(open_val.replace(",", "") or 0),
                "high": float(high_val.replace(",", "") or 0),
                "low": float(low_val.replace(",", "") or 0),
                "close": float(close_val.replace(",", "") or 0),
                "volume": int(float(vol_val.replace(",", "") or 0)),
            }
        )

    return fund_name, fund_id, rows, skipped


def main():
    if len(sys.argv) < 2:
        filepath = "data/import/fund.txt"
        print(f"No file specified, using default: {filepath}")
    else:
        filepath = sys.argv[1]

    print(f"Reading: {filepath}")

    fund_name, fund_id, rows, skipped = parse_file(filepath)

    print(f"  Fund name: {fund_name}")
    print(f"  Fund ID:   {fund_id}")
    print(f"  Rows found: {len(rows)}  |  Skipped: {skipped}")

    if not rows:
        print("  No valid rows found. Exiting.")
        sys.exit(1)

    # Show date range being imported
    dates = [r["date"] for r in rows]
    print(f"  Date range: {min(dates)} → {max(dates)}")

    conn = database.get_connection()
    database.create_table(conn)

    # Check if this fund already exists in the database
    if database.fund_exists(conn, fund_id):
        conn.close()
        print(
            f"\n  SKIPPED: Fund '{fund_name}' ({fund_id}) already exists in the database."
        )
        print(f"  To update with new data, use runner.py instead.")
        sys.exit(0)

    saved = database.save_prices(conn, fund_id, fund_name, new_rows, asset_type="Fund")
    conn.close()

    print(f"  Saved {saved} new rows to database.")
    print(f"\nDone. Remember to add this fund to config.py for future scraping:")
    print(f'  {{"name": "{fund_name}", "id": "{fund_id}"}}')


if __name__ == "__main__":
    main()
