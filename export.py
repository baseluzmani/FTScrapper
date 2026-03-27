# export.py
# Exports all data from the database to a timestamped CSV file.
# Run with: python3 export.py
# Output goes to the exports/ folder.

import sqlite3
import csv
import os
from datetime import datetime


def export_to_csv():
    # Create exports folder if it doesn't exist
    os.makedirs("exports", exist_ok=True)

    # Build a filename with the current timestamp
    # e.g. exports/funds_2026-03-13_14-30-00.csv
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"exports/funds_{timestamp}.csv"

    conn = sqlite3.connect("data/funds.db")
    conn.row_factory = sqlite3.Row

    # Pull all data ordered by fund and date
    cursor = conn.execute(
        """
        SELECT
            fund_id,
            fund_name,
            date,
            open,
            high,
            low,
            close,
            volume
        FROM fund_prices
        ORDER BY fund_id, date
    """
    )

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No data found in database.")
        return

    # Write to CSV
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)

        # Header row
        writer.writerow(
            ["fund_id", "fund_name", "date", "open", "high", "low", "close", "volume"]
        )

        # Data rows
        for row in rows:
            writer.writerow(
                [
                    row["fund_id"],
                    row["fund_name"],
                    row["date"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                ]
            )

    print(f"Exported {len(rows)} rows to {filename}")


if __name__ == "__main__":
    export_to_csv()
