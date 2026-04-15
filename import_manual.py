# import_manual.py
# Batch imports fund price data from .txt files in data/import/
#
# File format (each .txt file):
#   Line 1: Fund Name
#   Line 2: Fund ID (e.g. GB00BJH4XW03:GBP)
#   Line 3: Header row (Date  Open  High  Low  Close  Volume)
#   Line 4+: Tab-separated data rows copied from FT
#
# Usage:
#   python3 import_manual.py              # imports all .txt files in data/import/
#   python3 import_manual.py myfile.txt   # imports a single specific file

import sys
import glob
import os
from datetime import datetime
import database


def parse_date(value):
    """Parse a date from FT format or YYYY-MM-DD."""
    if not value:
        return None
    value = value.strip()
    # FT full format: "Friday, March 13, 2026"
    try:
        return datetime.strptime(value, "%A, %B %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        pass
    # FT short format: "Fri, Mar 13, 2026"
    try:
        return datetime.strptime(value, "%a, %b %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        pass
    # Already YYYY-MM-DD
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except ValueError:
        pass
    # DD/MM/YYYY
    try:
        return datetime.strptime(value, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        pass
    return None


def parse_file(filepath):
    """
    Read a .txt file and return (fund_name, fund_id, rows, skipped_count).
    """
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if len(lines) < 3:
        raise ValueError(f"File too short — needs at least 3 lines (name, id, header)")

    fund_name = lines[0].strip()
    fund_id = lines[1].strip()

    if not fund_name:
        raise ValueError("Line 1 (fund name) is empty")
    if not fund_id:
        raise ValueError("Line 2 (fund ID) is empty")

    rows = []
    skipped = 0

    for line in lines[2:]:
        line = line.strip()
        if not line:
            continue

        # Split on tab
        parts = line.split("\t")
        if len(parts) < 5:
            skipped += 1
            continue

        # Skip header row if it appears in data
        if parts[0].strip().lower() in ("date", "datum"):
            continue

        date_formatted = parse_date(parts[0])
        if not date_formatted:
            skipped += 1
            continue

        try:
            rows.append(
                {
                    "date": date_formatted,
                    "open": float(parts[1].replace(",", "").strip() or 0),
                    "high": float(parts[2].replace(",", "").strip() or 0),
                    "low": float(parts[3].replace(",", "").strip() or 0),
                    "close": float(parts[4].replace(",", "").strip() or 0),
                    "volume": (
                        int(float(parts[5].replace(",", "").strip() or 0))
                        if len(parts) > 5
                        else 0
                    ),
                }
            )
        except (ValueError, IndexError):
            skipped += 1
            continue

    return fund_name, fund_id, rows, skipped


def main():
    if len(sys.argv) > 1:
        files = [sys.argv[1]]
    else:
        files = sorted(glob.glob("data/import/*.txt"))
        if not files:
            print("No .txt files found in data/import/")
            sys.exit(1)
        print(f"Found {len(files)} file(s) in data/import/\n")

    conn = database.get_connection()
    database.create_table(conn)

    total_saved = 0

    for filepath in files:
        print(f"── Reading: {filepath}")
        try:
            fund_name, fund_id, rows, skipped = parse_file(filepath)
            print(f"  Fund name:  {fund_name}")
            print(f"  Fund ID:    {fund_id}")
            print(f"  Rows found: {len(rows)}  |  Skipped: {skipped}")

            if not rows:
                print(f"  WARNING: No valid rows — skipping.\n")
                continue

            dates = [r["date"] for r in rows]
            print(f"  Date range: {min(dates)} → {max(dates)}")

            if database.fund_exists(conn, fund_id):
                print(
                    f"  SKIPPED: Fund already has data. Delete first if you want to reimport.\n"
                )
                continue

            saved = database.save_prices(
                conn, fund_id, fund_name, rows, asset_type="Fund"
            )
            total_saved += saved
            print(f"  Saved {saved} new rows.\n")

        except Exception as e:
            print(f"  ERROR: {e}\n")

    conn.close()
    print(f"Done. {total_saved} total rows imported.")


if __name__ == "__main__":
    main()
