# database.py
# This file handles everything related to the database.
# No other file talks to the database directly — only this one.
# That means if we ever switch from SQLite to PostgreSQL,
# we only change this file.

import sqlite3
import os
from datetime import datetime


def get_connection():
    # Create the data/ folder if it doesn't exist yet
    os.makedirs("data", exist_ok=True)

    # Connect to the database file (creates it if it doesn't exist)
    conn = sqlite3.connect("data/funds.db")

    # This makes rows behave like dictionaries
    # so we can access columns by name: row['date'] instead of row[0]
    conn.row_factory = sqlite3.Row

    return conn


def create_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fund_prices (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fund_id     TEXT NOT NULL,
            fund_name   TEXT,
            date        TEXT NOT NULL,
            open        REAL,
            high        REAL,
            low         REAL,
            close       REAL,
            volume      INTEGER,
            UNIQUE(fund_id, date)
        )
    """
    )
    conn.commit()


def update_fund_name(conn, fund_id, fund_name):
    # Update the name on all rows for this fund
    conn.execute(
        """
        UPDATE fund_prices SET fund_name = ? WHERE fund_id = ?
    """,
        (fund_name, fund_id),
    )
    conn.commit()


def get_latest_date(conn, fund_id):
    # Ask the database: what is the most recent date we have for this fund?
    # Returns a date string like '2026-03-13', or None if no data exists yet
    cursor = conn.execute(
        """
        SELECT MAX(date) as latest
        FROM fund_prices
        WHERE fund_id = ?
    """,
        (fund_id,),
    )

    row = cursor.fetchone()
    return row["latest"] if row["latest"] else None


def fund_exists(conn, fund_id):
    # Returns True if there is any data for this fund in the database
    cursor = conn.execute(
        """
        SELECT COUNT(*) as count
        FROM fund_prices
        WHERE fund_id = ?
    """,
        (fund_id,),
    )
    row = cursor.fetchone()
    return row["count"] > 0


def save_prices(conn, fund_id, fund_name, rows, asset_type=None):
    saved_count = 0
    for row in rows:
        result = conn.execute(
            """
            INSERT OR IGNORE INTO fund_prices
                (fund_id, fund_name, date, open, high, low, close, volume, asset_type)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                fund_id,
                fund_name,
                row["date"],
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                row["volume"],
                asset_type,
            ),
        )
        saved_count += result.rowcount
    conn.commit()
    return saved_count


def update_asset_type(conn, fund_id, asset_type):
    conn.execute(
        """
        UPDATE fund_prices SET asset_type = ? WHERE fund_id = ?
    """,
        (asset_type, fund_id),
    )
    conn.commit()
