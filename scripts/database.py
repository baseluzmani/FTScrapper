# database.py
# Handles all database operations.
# Uses two tables:
#   instruments — static info per fund (name, type, currency, unit, category)
#   prices      — daily OHLCV price data, linked by fund_id

import sqlite3
import os


def get_connection():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/funds.db")
    conn.row_factory = sqlite3.Row
    return conn


def create_table(conn):
    """Create prices and instruments tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS instruments (
            fund_id     TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            asset_type  TEXT,
            currency    TEXT,
            price_unit  TEXT,
            category    TEXT
        )
    """)
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


def get_latest_date(conn, fund_id):
    """Return the most recent date for a fund, or None if no data exists."""
    row = conn.execute(
        "SELECT MAX(date) as latest FROM prices WHERE fund_id = ?",
        (fund_id,)
    ).fetchone()
    return row["latest"] if row["latest"] else None


def fund_exists(conn, fund_id):
    """Return True if any price data exists for this fund_id."""
    row = conn.execute(
        "SELECT COUNT(*) FROM prices WHERE fund_id = ?",
        (fund_id,)
    ).fetchone()
    return row[0] > 0


def save_prices(conn, fund_id, fund_name, rows, asset_type=None):
    """Insert new price rows — skips duplicates silently.
    Also upserts instrument record if not already present.
    """
    # Ensure instrument record exists
    existing = conn.execute(
        "SELECT fund_id FROM instruments WHERE fund_id = ?", (fund_id,)
    ).fetchone()
    if not existing:
        conn.execute("""
            INSERT OR IGNORE INTO instruments (fund_id, name, asset_type)
            VALUES (?, ?, ?)
        """, (fund_id, fund_name, asset_type))

    saved_count = 0
    for row in rows:
        result = conn.execute("""
            INSERT OR IGNORE INTO prices
                (fund_id, date, open, high, low, close, volume)
            VALUES
                (?, ?, ?, ?, ?, ?, ?)
        """, (
            fund_id,
            row["date"],
            row["open"],
            row["high"],
            row["low"],
            row["close"],
            row["volume"],
        ))
        saved_count += result.rowcount
    conn.commit()
    return saved_count


def update_fund_name(conn, fund_id, fund_name):
    """Update the display name in instruments table."""
    conn.execute(
        "UPDATE instruments SET name = ? WHERE fund_id = ?",
        (fund_name, fund_id),
    )
    conn.commit()


def update_asset_type(conn, fund_id, asset_type):
    """Update the asset type in instruments table."""
    conn.execute(
        "UPDATE instruments SET asset_type = ? WHERE fund_id = ?",
        (asset_type, fund_id),
    )
    conn.commit()