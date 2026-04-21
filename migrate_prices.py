# migrate_prices.py
# Creates the new 'prices' table and migrates all data from 'fund_prices'.
# fund_prices is kept as backup — do not delete until everything is confirmed working.
# Run: python3 migrate_prices.py

import sqlite3
import os


def get_connection():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/funds.db")
    conn.row_factory = sqlite3.Row
    return conn


def main():
    conn = get_connection()

    print("Step 1: Creating prices table...")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fund_id     TEXT NOT NULL,
            date        TEXT NOT NULL,
            open        REAL,
            high        REAL,
            low         REAL,
            close       REAL,
            volume      INTEGER,
            UNIQUE(fund_id, date)
        )
    """)
    conn.commit()
    print("  Done.")

    print("Step 2: Migrating data from fund_prices to prices...")
    conn.execute("""
        INSERT OR IGNORE INTO prices (fund_id, date, open, high, low, close, volume)
        SELECT fund_id, date, open, high, low, close, volume
        FROM fund_prices
    """)
    conn.commit()

    old_count = conn.execute("SELECT COUNT(*) FROM fund_prices").fetchone()[0]
    new_count = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    print(f"  fund_prices rows: {old_count:,}")
    print(f"  prices rows:      {new_count:,}")

    print("Step 3: Verifying instruments table has all fund_ids from prices...")
    missing = conn.execute("""
        SELECT DISTINCT p.fund_id
        FROM prices p
        LEFT JOIN instruments i ON p.fund_id = i.fund_id
        WHERE i.fund_id IS NULL
    """).fetchall()

    if missing:
        print(f"  WARNING: {len(missing)} fund_ids in prices not in instruments:")
        for r in missing:
            print(f"    {r[0]}")
    else:
        print("  All fund_ids accounted for in instruments.")

    conn.close()
    print("\nMigration complete.")
    print("fund_prices kept as backup — verify dashboard works before deleting.")


if __name__ == "__main__":
    main()