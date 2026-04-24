# migrate_transactions.py
# Imports transaction history from data/transactions.xlsx.
# Handles two types of closes:
#   1. Explicit SELL rows in the data
#   2. BUY rows with a Close Date + Close Price = auto-generated SELL
# Run: python3 migrate_transactions.py

import sqlite3
import pandas as pd
import os
from datetime import datetime

TICKER_MAP = {
    'AMZN':   'YF:AMZN',
    'DATA.L': 'YF:DATA.L',
    'NVO':    'YF:NVO',
    'LLY':    'YF:LLY',
    'GSK.L':  'YF:GSK.L',
    'BRBY.L': 'YF:BRBY.L',
    'QQ.L':   'YF:QQ.L',
    'MU':     'YF:MU',
    'HFG.L':  'YF:HFG.L',
    'CCH.L':  'YF:CCH.L',
    'BAES.L': 'YF:BA.L',
    'COPB.L': 'YF:COPB.L',
    'PHPP.L': 'YF:PHPP.L',
    'SGLN.L': 'YF:IGLN.L',
    'SSLN.L': 'YF:ISLN.L',
    'CMOP.L': None,
    'AINF.L': 'YF:AINF.L',
    'XDJP.L': 'YF:XDJP.L',
    'CSP1.L': 'YF:CSP1.L',
    'HSBA.L': 'YF:HSBA.L',
    'BTC-GBP':'YF:BTC-GBP',
    'ETH-GBP':'YF:ETH-GBP',
    'CSCA.L': 'YF:CSCA.L',
    'ASML':   'YF:ASML',
    'NRGT.L': 'YF:NRGT.L',
    'XAUGBP': 'CALC:XAUGBP',
    'WEAP.L': 'YF:WEAP.L',
    'GBP':    'CASH:GBP',
    'UIFS.L': 'YF:UIFS.L',
    'QCOM':   'YF:QCOM',
    'HMCH.L': 'YF:HMCH.L',
    'HCAN.L': 'YF:HCAN.L',
    'JPM':    'YF:JPM',
    'NGSP.L': 'YF:NGSP.L',
    'BRNB.L': None,
    'PLAY.L': 'YF:PLAY.L',
    'MINE.L': 'YF:MINE.L',
    'NVDA':   'YF:NVDA',
    'DFEU.L': 'YF:DFEU.L',
    'COCO':   'YF:COCO',
    'NATP.L': 'YF:NATP.L',
    'QWTM.L': 'YF:QWTM.L',
    'QANT.L': 'YF:QANT.L',
    'FCBR.L': 'YF:FCBR.L',
    'NCLP.L': None,
    'AIGA.L': 'YF:AIGA.L',
    'SPGP.L': 'YF:SPGP.L',
}


def create_transactions_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fund_id     TEXT NOT NULL,
            account     TEXT,
            trade_date  TEXT NOT NULL,
            type        TEXT NOT NULL,
            quantity    REAL NOT NULL,
            price       REAL NOT NULL,
            currency    TEXT,
            fx_rate     REAL DEFAULT 1.0
        )
    """)
    conn.commit()


def parse_date(val):
    if val is None:
        return None
    try:
        ts = pd.Timestamp(val)
        if pd.isna(ts):
            return None
        return ts.strftime('%Y-%m-%d')
    except Exception:
        return None


def main():
    xlsx_path = 'data/transactions.xlsx'
    if not os.path.exists(xlsx_path):
        xlsx_path = '/mnt/user-data/uploads/transactions.xlsx'

    print(f"Reading: {xlsx_path}")
    df = pd.read_excel(xlsx_path)
    print(f"Total rows: {len(df)}")

    conn = sqlite3.connect('data/funds.db')
    create_transactions_table(conn)
    conn.execute("DELETE FROM transactions")
    conn.commit()

    imported = 0
    skipped  = 0
    skipped_tickers = set()

    for _, row in df.iterrows():
        symbol  = str(row.get('Symbol', '')).strip()
        fund_id = TICKER_MAP.get(symbol)

        if fund_id is None:
            skipped += 1
            if symbol not in ('nan', ''):
                skipped_tickers.add(symbol)
            continue

        trade_type = str(row.get('Type', '')).strip().upper()
        if trade_type not in ('BUY', 'SELL'):
            skipped += 1
            continue

        # Only process BUY rows — closes are captured via Close Date on BUY rows.
        # Explicit SELL rows in the spreadsheet overlap with Close Date SELLs
        # and would double-count. Skip them.
        if trade_type == 'SELL':
            skipped += 1
            continue

        trade_date = parse_date(row.get('Open Date'))
        if not trade_date:
            skipped += 1
            continue

        quantity = float(row.get('Amount', 0) or 0)
        price    = float(row.get('Open Price', 0) or 0)
        currency = str(row.get('Currency', 'GBP')).strip()
        fx_rate  = float(row.get('Currency Rate TD', 1) or 1)
        account  = str(row.get('Account', '')).strip()

        if currency == 'GBPC':
            currency = 'GBP'
            fx_rate  = 1.0

        # Some instruments have quantity scaled differently in the Excel
        # BTC and ETH quantities are 100x actual — divide to get real units
        QUANTITY_DIVISOR = {
            'YF:BTC-GBP': 100,
            'YF:ETH-GBP': 100,
        }
        qty_divisor = QUANTITY_DIVISOR.get(fund_id, 1)
        actual_qty  = abs(quantity) / qty_divisor

        # Insert BUY
        conn.execute("""
            INSERT INTO transactions (fund_id, account, trade_date, type, quantity, price, currency, fx_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (fund_id, account, trade_date, trade_type, actual_qty, price, currency, fx_rate))
        imported += 1

        # If BUY has Close Date + Close Price — generate matching SELL
        close_date  = parse_date(row.get('Close Date'))
        close_price = row.get('Close Price')

        if close_date and close_price and not pd.isna(close_price):
            close_price = float(close_price)
            fx_latest   = float(row.get('Currency Rate Latest', fx_rate) or fx_rate)

            conn.execute("""
                INSERT INTO transactions (fund_id, account, trade_date, type, quantity, price, currency, fx_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (fund_id, account, close_date, 'SELL', actual_qty, close_price, currency, fx_latest))
            imported += 1

    conn.commit()
    conn.close()

    print(f"\nImported: {imported} rows (BUYs + auto-generated SELLs)")
    print(f"Skipped:  {skipped}")
    if skipped_tickers:
        print(f"Skipped tickers: {sorted(skipped_tickers)}")
    print("\nDone.")


if __name__ == '__main__':
    main()