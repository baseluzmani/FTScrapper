# fix_gold_silver_txns.py
# IGLN.L and ISLN.L transaction prices were stored in GBP pence
# but Yahoo Finance prices are in USD.
# This script converts them to USD using GBPUSD rate at each trade date.
# Run: python3 fix_gold_silver_txns.py

import sqlite3

DB_PATH = 'data/funds.db'


def get_gbpusd_at(conn, date):
    """Get GBPUSD rate on or before a given date."""
    row = conn.execute("""
        SELECT close FROM prices
        WHERE fund_id = 'YF:GBPUSD=X'
        AND date <= ?
        ORDER BY date DESC LIMIT 1
    """, (date,)).fetchone()
    return row[0] if row else 1.30  # fallback if no data


def main():
    conn = sqlite3.connect(DB_PATH)

    for fund_id in ['YF:IGLN.L', 'YF:ISLN.L']:
        txns = conn.execute("""
            SELECT id, trade_date, type, quantity, price, currency, fx_rate
            FROM transactions WHERE fund_id = ?
            ORDER BY trade_date
        """, (fund_id,)).fetchall()

        print(f"\n{fund_id}: {len(txns)} transactions")

        for txn_id, date, ttype, qty, price, currency, fx_rate in txns:
            # Skip if already converted (currency already USD)
            if currency == 'USD':
                print(f"  {date} {ttype} {qty} @ {price:.4f} USD — already converted")
                continue

            # Price is in GBP pence — convert: pence -> pounds -> USD
            gbpusd = get_gbpusd_at(conn, date)
            price_gbp = price / 100          # pence to pounds
            price_usd = price_gbp * gbpusd   # pounds to USD

            conn.execute("""
                UPDATE transactions
                SET price = ?, currency = 'USD', fx_rate = ?
                WHERE id = ?
            """, (price_usd, gbpusd, txn_id))

            print(f"  {date} {ttype} {qty} @ {price:.0f}p -> £{price_gbp:.2f} -> ${price_usd:.2f} (GBPUSD={gbpusd:.4f})")

    conn.commit()
    conn.close()
    print("\nDone.")


if __name__ == '__main__':
    main()