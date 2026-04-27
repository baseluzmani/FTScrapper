# snapshot.py
# Saves current portfolio values to data/snapshots/YYYY-MM-DD.json
# Run automatically via cron at 10pm daily, or manually anytime.
# Usage: python3 snapshot.py

import sqlite3
import json
import os
from datetime import datetime

DB_PATH        = 'data/funds.db'
PORTFOLIO_PATH = 'data/portfolio.json'
SNAPSHOTS_DIR  = 'data/snapshots'


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
    """Calculate composite fund price in GBP."""
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


def calc_cash_total(cash_accounts, gbpusd, gbptry):
    """Convert all cash accounts to GBP and return total."""
    total = 0.0
    for acc in cash_accounts:
        amount = float(acc.get('amount', 0))
        curr   = acc.get('currency', 'GBP')
        if curr == 'GBP':
            total += amount
        elif curr == 'USD':
            total += amount / gbpusd
        elif curr == 'TRY':
            total += amount / gbptry
    return total


def main():
    if not os.path.exists(PORTFOLIO_PATH):
        print("No portfolio.json found.")
        return

    with open(PORTFOLIO_PATH) as f:
        data = json.load(f)

    # Support both old flat list and new {holdings} structure
    if isinstance(data, list):
        holdings = data
    else:
        holdings = data.get('holdings', [])

    # Load cash accounts from SQLite
    try:
        cash_conn = sqlite3.connect(DB_PATH)
        rows = cash_conn.execute(
            "SELECT name, currency, amount FROM cash_accounts ORDER BY id"
        ).fetchall()
        cash_conn.close()
        cash_accounts = [{'name': r[0], 'currency': r[1], 'amount': r[2]} for r in rows]
    except Exception:
        cash_accounts = []

    conn   = get_connection()
    gbpusd = get_gbpusd(conn)
    gbptry = get_gbptry(conn)

    snapshot = {
        'date':          datetime.today().strftime('%Y-%m-%d'),
        'gbpusd':        gbpusd,
        'gbptry':        gbptry,
        'holdings':      {},
        'categories':    {},
        'cash_total':    0.0,
        'cash_accounts': cash_accounts,  # full breakdown saved for reference
    }

    total = 0.0

    # Process holdings — skip legacy CASH: entries (now handled separately)
    for item in holdings:
        fid   = item['fund_id']
        units = float(item.get('units', 0))

        if fid.startswith('CASH:'):
            continue

        row = conn.execute(
            "SELECT category FROM instruments WHERE fund_id=?", (fid,)
        ).fetchone()
        category = row[0] if row and row[0] else 'Other'

        if fid == 'CALC:XAUGBP':
            row_gc = conn.execute(
                "SELECT close FROM prices WHERE fund_id='YF:GC=F' ORDER BY date DESC LIMIT 1"
            ).fetchone()
            price_gbp = row_gc[0] / gbpusd if row_gc else None
            value = price_gbp * units if price_gbp else None

        elif fid.startswith('ASSET:'):
            curr, punit = get_instrument(conn, fid)
            gbp = to_gbp(1.0, punit, curr, gbpusd, gbptry)
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
            snapshot['holdings'][fid] = round(value, 2)
            snapshot['categories'][category] = round(
                snapshot['categories'].get(category, 0) + value, 2
            )
            total += value

    # Process cash accounts — save total and full breakdown
    if cash_accounts:
        cash_total = calc_cash_total(cash_accounts, gbpusd, gbptry)
        snapshot['cash_total']             = round(cash_total, 2)
        snapshot['holdings']['CASH:TOTAL'] = round(cash_total, 2)
        snapshot['categories']['Cash']     = round(
            snapshot['categories'].get('Cash', 0) + cash_total, 2
        )
        total += cash_total

    snapshot['total'] = round(total, 2)
    conn.close()

    # Save snapshot
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    date_str = snapshot['date']
    out_path = os.path.join(SNAPSHOTS_DIR, f"{date_str}.json")
    with open(out_path, 'w') as f:
        json.dump(snapshot, f, indent=2)

    print(f"Snapshot saved: {out_path}")
    print(f"Total portfolio value: £{total:,.2f}")
    print(f"Holdings captured: {len(snapshot['holdings'])}")
    print(f"Cash total: £{snapshot['cash_total']:,.2f}")
    print(f"Cash accounts captured: {len(cash_accounts)}")


if __name__ == '__main__':
    main()