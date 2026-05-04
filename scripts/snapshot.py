# snapshot.py
# Saves current portfolio values to database tables
# Run automatically via cron at 10pm daily, or manually anytime.
# Usage: python3 snapshot.py

import sqlite3
import os
from datetime import datetime
from datetime import timedelta

DB_PATH = 'data/funds.db'


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_gbpusd(conn):
    row = conn.execute("""
        SELECT close FROM prices
        WHERE fund_id = 'YF:GBPUSD=X'
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    return row[0] if row else 1.26


def get_gbptry(conn):
    row = conn.execute("""
        SELECT close FROM prices
        WHERE fund_id = 'YF:GBPTRY=X'
        ORDER BY date DESC LIMIT 1
    """).fetchone()
    return row[0] if row else 43.0


def get_latest_price(conn, fund_id):
    row = conn.execute("""
        SELECT close FROM prices
        WHERE fund_id = ?
        ORDER BY date DESC LIMIT 1
    """, (fund_id,)).fetchone()
    return row[0] if row else None


def get_instrument(conn, fund_id):
    row = conn.execute(
        "SELECT currency, price_unit FROM instruments WHERE fund_id = ?",
        (fund_id,)
    ).fetchone()
    return (row[0], row[1]) if row else ('GBP', 'pound')


def to_gbp(price, price_unit, currency, gbpusd, gbptry):
    if price is None:
        return None
    p = float(price)
    if price_unit == 'pence':
        p = p / 100
    if price_unit == 'point':
        if currency == 'TRY':
            return p / gbptry
        return None
    if price_unit == 'ratio':
        return None
    if currency == 'USD':
        return p / gbpusd
    if currency == 'TRY':
        return p / gbptry
    return p


def get_composite_price_gbp(conn, fund_id, gbpusd, gbptry):
    import config
    comp_def = next((c for c in getattr(config, 'COMPOSITE_FUNDS', []) if c['fund_id'] == fund_id), None)
    if not comp_def:
        return None
    weighted = 0.0
    for c in comp_def['components']:
        cp = get_latest_price(conn, c['fund_id'])
        curr, punit = get_instrument(conn, c['fund_id'])
        cgbp = to_gbp(cp, punit, curr, gbpusd, gbptry)
        if cgbp:
            weighted += cgbp * c['weight']
    return weighted if weighted > 0 else None


def main():
    conn      = get_connection()
    gbpusd    = get_gbpusd(conn)
    gbptry    = get_gbptry(conn)
    snap_date = datetime.today().strftime('%Y-%m-%d')
    now       = datetime.today().strftime('%Y-%m-%d %H:%M:%S')
    total      = 0.0
    categories = {}

    # Load holdings from portfolio_holdings table
    holdings = conn.execute(
        "SELECT fund_id, units FROM portfolio_holdings"
    ).fetchall()

    # Insert or replace snapshot header
    conn.execute(
        "INSERT OR REPLACE INTO portfolio_snapshots (snap_date, gbpusd, gbptry, created_at) VALUES (?, ?, ?, ?)",
        (snap_date, gbpusd, gbptry, now)
    )
    conn.commit()

    snap_id = conn.execute(
        "SELECT id FROM portfolio_snapshots WHERE snap_date = ?", (snap_date,)
    ).fetchone()[0]

    # Clear existing detail rows for today
    conn.execute("DELETE FROM snapshot_holdings   WHERE snapshot_id = ?", (snap_id,))
    conn.execute("DELETE FROM snapshot_categories WHERE snapshot_id = ?", (snap_id,))
    conn.execute("DELETE FROM snapshot_cash       WHERE snapshot_id = ?", (snap_id,))
    conn.commit()

    # Process each holding
    for fid, units in holdings:
        units = float(units)
        row = conn.execute("SELECT category FROM instruments WHERE fund_id=?", (fid,)).fetchone()
        category = row[0] if row and row[0] else 'Other'

        if fid == 'CALC:XAUGBP':
            row_gc = conn.execute(
                "SELECT close FROM prices WHERE fund_id='YF:GC=F' ORDER BY date DESC LIMIT 1"
            ).fetchone()
            price_gbp = row_gc[0] / gbpusd if row_gc else None
            value = price_gbp * units if price_gbp else None
        elif fid.startswith('ASSET:'):
            curr, punit = get_instrument(conn, fid)
            gbp   = to_gbp(1.0, punit, curr, gbpusd, gbptry)
            value = (gbp or 1.0) * units
        elif fid.startswith('COMPOSITE:'):
            price_gbp = get_composite_price_gbp(conn, fid, gbpusd, gbptry)
            value = price_gbp * units if price_gbp else None
        else:
            curr, punit = get_instrument(conn, fid)
            price       = get_latest_price(conn, fid)
            price_gbp   = to_gbp(price, punit, curr, gbpusd, gbptry)
            value       = price_gbp * units if price_gbp else None

        if value is not None:
            conn.execute(
                "INSERT INTO snapshot_holdings (snapshot_id, fund_id, units, value_gbp) VALUES (?, ?, ?, ?)",
                (snap_id, fid, units, round(value, 2))
            )
            categories[category] = round(categories.get(category, 0) + value, 2)
            total += value

    # Process cash accounts
    cash_accounts = conn.execute(
        "SELECT name, currency, amount FROM cash_accounts ORDER BY id"
    ).fetchall()

    cash_total = 0.0
    for name, currency, amount in cash_accounts:
        amount = float(amount)
        if currency == 'GBP':
            value_gbp = amount
        elif currency == 'USD':
            value_gbp = amount / gbpusd
        elif currency == 'TRY':
            value_gbp = amount / gbptry
        else:
            value_gbp = amount
        cash_total += value_gbp
        conn.execute(
            "INSERT INTO snapshot_cash (snapshot_id, name, currency, amount, value_gbp) VALUES (?, ?, ?, ?, ?)",
            (snap_id, name, currency, amount, round(value_gbp, 2))
        )

    if cash_total > 0:
        conn.execute(
            "INSERT INTO snapshot_holdings (snapshot_id, fund_id, units, value_gbp) VALUES (?, 'CASH:TOTAL', NULL, ?)",
            (snap_id, round(cash_total, 2))
        )
        categories['Cash'] = round(categories.get('Cash', 0) + cash_total, 2)
        total += cash_total

    # Save categories
    for category, value_gbp in categories.items():
        conn.execute(
            "INSERT INTO snapshot_categories (snapshot_id, category, value_gbp) VALUES (?, ?, ?)",
            (snap_id, category, value_gbp)
        )

    # Update total in header
    conn.execute(
        "UPDATE portfolio_snapshots SET total_gbp = ? WHERE id = ?",
        (round(total, 2), snap_id)
    )
    conn.commit()
    conn.close()

    # Save month-end total to networth_history
    from datetime import date
    import calendar
    today = date.today()
    # First working day of month = first day that is Mon-Fri
    first = date(today.year, today.month, 1)
    offset = 0
    while (first + timedelta(days=offset)).weekday() >= 5:
        offset += 1
    first_working_day = first + timedelta(days=offset)
    if today == first_working_day:
        conn2 = sqlite3.connect(DB_PATH)
        conn2.execute(
            "INSERT OR REPLACE INTO networth_history (date, total_gbp, source) VALUES (?, ?, 'snapshot')",
            (today.strftime('%Y-%m-%d'), round(total, 2))
        )
        conn2.commit()
        conn2.close()
        print(f"Month-end saved to networth_history: £{total:,.0f}")


    print(f"Snapshot saved: {snap_date} (id={snap_id})")
    print(f"Total portfolio value: £{total:,.2f}")
    print(f"Holdings captured: {len(holdings)}")
    print(f"Cash accounts: {len(cash_accounts)} | Cash total: £{cash_total:,.2f}")


if __name__ == '__main__':
    main()