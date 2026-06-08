"""
Build composite and calculated price series and save them to the database.
Run this once to backfill history, then after each scraper run to keep updated.

Usage:
    python3 build_composite_prices.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pandas as pd
from datetime import datetime
import config

DB_PATH = config.DB_PATH


def load_all_prices(conn):
    """Load all raw prices from the database."""
    df = pd.read_sql_query("""
        SELECT p.fund_id, p.date, p.open, p.high, p.low, p.close, p.volume
        FROM prices p
        ORDER BY p.fund_id, p.date
    """, conn)
    df['date'] = pd.to_datetime(df['date'])
    return df


def build_composite_data(df):
    """Build synthetic price series for composite funds — same logic as dashboard."""
    composites = getattr(config, 'COMPOSITE_FUNDS', [])
    if not composites:
        return pd.DataFrame()

    rows = []
    for comp in composites:
        fund_id = comp['fund_id']
        fund_name = comp['display_name']
        asset_type = comp.get('asset_type', 'Fund')
        components = comp['components']

        series = {}
        for c in components:
            cid = c['fund_id']
            cdf = df[df['fund_id'] == cid][['date', 'close']].sort_values('date')
            if not cdf.empty:
                series[cid] = cdf.set_index('date')['close']

        if not series:
            continue

        common_dates = None
        for s in series.values():
            dates = set(s.index)
            common_dates = dates if common_dates is None else common_dates & dates

        if not common_dates or len(common_dates) < 2:
            continue

        common_dates = sorted(common_dates)
        base_date = common_dates[0]
        composite_series = pd.Series(0.0, index=common_dates)

        for c in components:
            cid = c['fund_id']
            weight = c['weight']
            if cid not in series:
                continue
            s = series[cid].loc[common_dates]
            base_val = s.loc[base_date]
            if base_val == 0:
                continue
            composite_series += (s / base_val) * 100 * weight

        for date, price in composite_series.items():
            rows.append({
                'fund_id': fund_id,
                'date': date.strftime('%Y-%m-%d'),
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': 0,
            })

    return pd.DataFrame(rows)


def ensure_instruments(conn, df):
    """Ensure composite and calculated instruments exist in the instruments table."""
    needed = []
    
    # Add composites
    for comp in getattr(config, 'COMPOSITE_FUNDS', []):
        needed.append((comp['fund_id'], comp['display_name'], comp.get('asset_type', 'Fund'), 'GBP', 'pound', 'Pension'))
    
    for fund_id, name, asset_type, currency, price_unit, category in needed:
        conn.execute("""
            INSERT OR IGNORE INTO instruments (fund_id, name, asset_type, currency, price_unit, category)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (fund_id, name, asset_type, currency, price_unit, category))
    conn.commit()

def save_prices(conn, df):
    """Save price rows to database, skipping existing dates."""
    if df.empty:
        return 0
    
    # Count before
    before = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    
    for _, row in df.iterrows():
        try:
            conn.execute("""
                INSERT OR IGNORE INTO prices (fund_id, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (row['fund_id'], row['date'], row['open'], row['high'], row['low'], row['close'], row['volume']))
        except Exception as e:
            print(f"  Error saving {row['fund_id']} {row['date']}: {e}")
    
    conn.commit()
    
    # Count after
    after = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    return after - before

def main():
    conn = sqlite3.connect(DB_PATH)
    
    print("Loading raw prices...")
    df = load_all_prices(conn)
    print(f"  {len(df)} rows loaded")
    
    print("\nEnsuring instruments exist...")
    ensure_instruments(conn, df)
    
    print("\nBuilding composite prices...")
    df_comp = build_composite_data(df)
    print(f"  {len(df_comp)} rows built for {df_comp['fund_id'].nunique() if not df_comp.empty else 0} funds")
    if not df_comp.empty:
        for fid in df_comp['fund_id'].unique():
            subset = df_comp[df_comp['fund_id'] == fid]
            print(f"    {fid}: {len(subset)} rows, {subset['date'].min()} → {subset['date'].max()}")
    
    conn.close()
    print(f"\nDone.")


if __name__ == "__main__":
    main()