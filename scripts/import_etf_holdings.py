"""
ETF Holdings Importer
---------------------
Two sources:
1. Historical Excel: data/Funds Database.xlsx
2. Ongoing CSVs/XLS: data/etf_holdings_import/*.csv or *.xls

File naming for ongoing imports: {PREFIX}_{anything}.csv
Date is always read from inside the file.
If (etf_fund_id, scraped_date) already exists in DB, file is skipped.
Processed files are moved to data/etf_holdings_import/archive/

Usage:
    python3 scripts/import_etf_holdings.py              # process ongoing CSVs only
    python3 scripts/import_etf_holdings.py --historical  # also import from Excel
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import csv
import re
import xml.etree.ElementTree as ET
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

DB_PATH    = 'data/funds.db'
IMPORT_DIR = Path('data/etf_holdings_import')
EXCEL_PATH = Path('data/Funds Database.xlsx')

# Mapping from file prefix / sheet ETF code to instruments.fund_id
FUND_ID_MAP = {
    'AINF': 'YF:AINF.L',
    'IUFS': 'YF:UIFS.L',
    'PLAY': 'YF:PLAY.L',
    'MINE': 'YF:MINE.L',
    'DFEU': 'YF:DFEU.L',
    'QANT': 'YF:QANT.L',
    'QWTM': 'YF:QWTM.L',
    'WQTM': 'YF:QWTM.L',
    'NATP': 'YF:NATP.L',
    'FCBR': 'YF:FCBR.L',
    'SEMI': 'YF:SEMI.L',
    'DFNG': 'YF:DFNG.L',
    'NUCG': 'YF:NUCG.L',
    'ISLN': 'YF:ISLN.L',
    'IGLN': 'YF:IGLN.L',
    'SPGP': 'YF:SPGP.L',
    'WEAP': 'YF:WEAP.L',
    'UC15': 'YF:UC15.L',
    'IITU': 'YF:IITU.L',
}

# Skip these asset classes
SKIP_ASSET_CLASSES = {'cash and/or derivatives', 'cash', 'futures', 'options', 'cash collateral and margins'}

# Sheets to skip in Excel (NAV/performance/price data)
SKIP_SHEETS = {'Sheet1', 'Sheet2', 'Sheet9', 'AINF', 'DFEU', 'MINE', 'SL Funds', 
               'HSBC Pension', 'Burcu Dashboard', 'Ahmet Dashboard'}


def create_tables(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS etf_holdings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            etf_fund_id     TEXT NOT NULL,
            scraped_date    TEXT NOT NULL,
            ticker          TEXT,
            name            TEXT NOT NULL,
            sector          TEXT,
            asset_class     TEXT,
            weight_pct      REAL,
            market_value    REAL,
            location        TEXT,
            currency        TEXT,
            UNIQUE(etf_fund_id, scraped_date, name)
        );
        CREATE TABLE IF NOT EXISTS etf_holding_ticker_map (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_ticker   TEXT NOT NULL,
            source_name     TEXT NOT NULL,
            yahoo_fund_id   TEXT,
            confidence      REAL,
            reviewed        INTEGER DEFAULT 0,
            notes           TEXT,
            UNIQUE(source_ticker, source_name)
        );
        CREATE INDEX IF NOT EXISTS idx_etf_holdings_fund_date
            ON etf_holdings(etf_fund_id, scraped_date);
        CREATE INDEX IF NOT EXISTS idx_etf_holdings_ticker
            ON etf_holdings(ticker);
    """)
    conn.commit()


def already_imported(conn, etf_fund_id, scraped_date):
    """Check if this ETF/date combination already exists."""
    count = conn.execute(
        "SELECT COUNT(*) FROM etf_holdings WHERE etf_fund_id=? AND scraped_date=?",
        (etf_fund_id, scraped_date)
    ).fetchone()[0]
    return count > 0


def insert_holdings(conn, etf_fund_id, scraped_date, holdings):
    """Insert holdings into DB. Returns count of inserted rows."""
    inserted = 0
    errors = 0
    for h in holdings:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO etf_holdings
                    (etf_fund_id, scraped_date, ticker, name, sector,
                     asset_class, weight_pct, market_value, location, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                etf_fund_id, scraped_date,
                h.get('ticker'), h['name'], h.get('sector'),
                h.get('asset_class'), h.get('weight_pct'), h.get('market_value'),
                h.get('location'), h.get('currency'),
            ))
            inserted += 1
        except Exception as e:
            errors += 1
            print(f"    Row error ({h.get('name', '?')}): {e}")
    conn.commit()
    return inserted, errors


def safe_float(val, multiply=1.0):
    """Parse float safely, return None on failure."""
    if val is None:
        return None
    try:
        s = str(val).replace(',', '').strip()
        if not s or s in ('-', 'N/A', 'nan'):
            return None
        return float(s) * multiply
    except:
        return None


# ── PARSERS ──────────────────────────────────────────────────────────────────

def parse_ishares_csv(filepath):
    """
    Parse iShares CSV format.
    Header rows at top contain date. Data starts after column header row.
    Columns: Ticker, Name, Sector, Asset Class, Market Value, Weight (%), Location, Market Currency
    """
    holdings = []
    scraped_date = None

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()

    # Find date in first 5 lines
    for line in lines[:5]:
        m = re.search(r'(\d{2}/\w+/\d{4})', line)
        if m:
            try:
                scraped_date = datetime.strptime(m.group(1), '%d/%b/%Y').strftime('%Y-%m-%d')
                break
            except:
                pass

    # Find header row
    header_idx = None
    for i, line in enumerate(lines):
        if 'Ticker' in line and 'Name' in line and 'Weight' in line:
            header_idx = i
            break

    if header_idx is None:
        return holdings, scraped_date

    reader = csv.DictReader(lines[header_idx:])
    for row in reader:
        ticker    = (row.get('Ticker') or row.get('Issuer Ticker') or '').strip().strip('"')
        name      = (row.get('Name') or '').strip().strip('"')
        sector    = (row.get('Sector') or '').strip().strip('"')
        asset_cls = (row.get('Asset Class') or '').strip().strip('"')
        weight    = safe_float(row.get('Weight (%)'))
        mktval    = safe_float(row.get('Market Value'))
        location  = (row.get('Location') or '').strip().strip('"')
        currency  = (row.get('Market Currency') or '').strip().strip('"')

        if not name or asset_cls.lower() in SKIP_ASSET_CLASSES:
            continue

        holdings.append({
            'ticker': ticker, 'name': name, 'sector': sector,
            'asset_class': asset_cls, 'weight_pct': weight,
            'market_value': mktval, 'location': location, 'currency': currency,
        })

    return holdings, scraped_date


def parse_ishares_xls(filepath):
    """Parse iShares XLS (XML Spreadsheet) format."""
    holdings = []
    scraped_date = None

    with open(filepath, 'rb') as f:
        content = f.read().decode('utf-8-sig')

    ns = {'ss': 'urn:schemas-microsoft-com:office:spreadsheet'}
    root = ET.fromstring(content)
    rows = root.findall('.//ss:Row', ns)

    def get_vals(row):
        cells = row.findall('ss:Cell', ns)
        return [c.find('ss:Data', ns).text or '' if c.find('ss:Data', ns) is not None else ''
                for c in cells]

    # Find date
    for row in rows[:8]:
        for v in get_vals(row):
            m = re.search(r'(\d{2}[/-]\w+[/-]\d{4}|\d{4}-\d{2}-\d{2})', str(v or ''))
            if m:
                for fmt in ['%d/%b/%Y', '%d-%b-%Y', '%Y-%m-%d']:
                    try:
                        scraped_date = datetime.strptime(m.group(1), fmt).strftime('%Y-%m-%d')
                        break
                    except:
                        pass
            if scraped_date:
                break
        if scraped_date:
            break

    # Find header row
    headers = []
    header_idx = None
    for i, row in enumerate(rows):
        vals = get_vals(row)
        if any(v in ('Name', 'Ticker', 'Issuer Ticker') for v in vals):
            headers = vals
            header_idx = i
            break

    if header_idx is None:
        return holdings, scraped_date

    def col(options):
        for n in options:
            if n in headers:
                return headers.index(n)
        return None

    idx = {
        'ticker':   col(['Ticker', 'Issuer Ticker']),
        'name':     col(['Name']),
        'sector':   col(['Sector']),
        'asset':    col(['Asset Class']),
        'weight':   col(['Weight (%)']),
        'mktval':   col(['Market Value']),
        'location': col(['Location']),
        'currency': col(['Market Currency']),
    }

    for row in rows[header_idx + 1:]:
        vals = get_vals(row)
        if not any(vals):
            continue

        def g(k):
            i = idx[k]
            return vals[i].strip() if i is not None and i < len(vals) else ''

        name      = g('name')
        asset_cls = g('asset')
        if not name or asset_cls.lower() in SKIP_ASSET_CLASSES:
            continue

        holdings.append({
            'ticker':      g('ticker'),
            'name':        name,
            'sector':      g('sector'),
            'asset_class': asset_cls,
            'weight_pct':  safe_float(g('weight')),
            'market_value':safe_float(g('mktval')),
            'location':    g('location'),
            'currency':    g('currency'),
        })

    return holdings, scraped_date


def parse_excel_funds_sheet(xl):
    """
    Parse 'Funds' sheet — iShares format with FUND column.
    Returns dict: {(etf_fund_id, date): [holdings]}
    """
    results = {}
    df = xl.parse('Funds', header=0)
    df.columns = [str(c).strip() for c in df.columns]

    # Rename columns to standard
    col_map = {
        df.columns[0]: 'FUND',
        df.columns[1]: 'Date',
        df.columns[2]: 'Ticker',
        df.columns[3]: 'Name',
        df.columns[5]: 'Sector',
        df.columns[6]: 'Asset Class',
        df.columns[7]: 'Market Value',
        df.columns[8]: 'Weight (%)',
        df.columns[11]: 'Location',
        df.columns[14]: 'Currency',
    }
    df = df.rename(columns=col_map)

    for _, row in df.iterrows():
        fund_code = str(row.get('FUND', '')).strip().upper()
        etf_fund_id = FUND_ID_MAP.get(fund_code)
        if not etf_fund_id:
            continue

        date_val = row.get('Date')
        try:
            scraped_date = pd.to_datetime(date_val).strftime('%Y-%m-%d')
        except:
            continue

        asset_cls = str(row.get('Asset Class', '')).strip()
        if asset_cls.lower() in SKIP_ASSET_CLASSES:
            continue

        name = str(row.get('Name', '')).strip()
        if not name or name == 'nan':
            continue

        key = (etf_fund_id, scraped_date)
        if key not in results:
            results[key] = []

        results[key].append({
            'ticker':      str(row.get('Ticker', '')).strip(),
            'name':        name,
            'sector':      str(row.get('Sector', '')).strip(),
            'asset_class': asset_cls,
            'weight_pct':  safe_float(row.get('Weight (%)')),
            'market_value':safe_float(row.get('Market Value')),
            'location':    str(row.get('Location', '')).strip(),
            'currency':    str(row.get('Currency', '')).strip(),
        })

    return results


def parse_excel_wqtm_sheet(xl):
    """
    WisdomTree format: Date, Fund Name, Fund Ticker Symbol, Security Description,
    Security Ticker, Shares, Mkt Value, Weight %
    Weight is ratio — multiply by 100.
    """
    results = {}
    df = xl.parse('WQTM', header=0)
    etf_fund_id = FUND_ID_MAP.get('WQTM')
    if not etf_fund_id:
        return results

    for _, row in df.iterrows():
        try:
            scraped_date = pd.to_datetime(row.iloc[0]).strftime('%Y-%m-%d')
        except:
            continue

        name = str(row.iloc[3]).strip()
        if not name or name == 'nan':
            continue

        key = (etf_fund_id, scraped_date)
        if key not in results:
            results[key] = []

        results[key].append({
            'ticker':      str(row.iloc[4]).strip(),
            'name':        name,
            'sector':      None,
            'asset_class': 'Equity',
            'weight_pct':  safe_float(row.iloc[7], multiply=100),
            'market_value':safe_float(row.iloc[6]),
            'location':    None,
            'currency':    None,
        })

    return results


def parse_excel_natp_sheet(xl):
    """
    NATP format: FUND, Date, Security Description, Shares, Market Value (Base),
    Trading Currency, SEDOL/CUSIP, Exposure Country, Region, ISIN, Weight
    Weight is ratio — multiply by 100.
    """
    results = {}
    df = xl.parse('NATP', header=0)
    df.columns = [str(c).strip() for c in df.columns]
    etf_fund_id = FUND_ID_MAP.get('NATP')
    if not etf_fund_id:
        return results

    for _, row in df.iterrows():
        fund_code = str(row.iloc[0]).strip().upper()
        if fund_code != 'NATP':
            continue

        try:
            scraped_date = pd.to_datetime(row.iloc[1]).strftime('%Y-%m-%d')
        except:
            continue

        name = str(row.iloc[2]).strip()
        if not name or name == 'nan':
            continue

        key = (etf_fund_id, scraped_date)
        if key not in results:
            results[key] = []

        results[key].append({
            'ticker':      str(row.iloc[6]).strip(),  # SEDOL/CUSIP
            'name':        name,
            'sector':      None,
            'asset_class': 'Equity',
            'weight_pct':  safe_float(row.iloc[10], multiply=100),
            'market_value':safe_float(row.iloc[4]),
            'location':    str(row.iloc[7]).strip(),
            'currency':    str(row.iloc[5]).strip(),
        })

    return results


def parse_excel_fcbr_sheet(xl):
    """
    FCBR format: ETF, Date, Security Name, Identifier, CUSIP, Classification,
    Shares or Quantity, Market Value, Weighting
    Weighting is ratio — multiply by 100.
    """
    results = {}
    df = xl.parse('FCBR', header=0)
    etf_fund_id = FUND_ID_MAP.get('FCBR')
    if not etf_fund_id:
        return results

    for _, row in df.iterrows():
        fund_code = str(row.iloc[0]).strip().upper()
        if fund_code != 'FCBR':
            continue

        try:
            scraped_date = pd.to_datetime(row.iloc[1]).strftime('%Y-%m-%d')
        except:
            continue

        name = str(row.iloc[2]).strip()
        if not name or name == 'nan':
            continue

        key = (etf_fund_id, scraped_date)
        if key not in results:
            results[key] = []

        results[key].append({
            'ticker':      str(row.iloc[3]).strip(),
            'name':        name,
            'sector':      str(row.iloc[5]).strip(),
            'asset_class': 'Equity',
            'weight_pct':  safe_float(row.iloc[8], multiply=100),
            'market_value':safe_float(row.iloc[7]),
            'location':    None,
            'currency':    None,
        })

    return results


def generate_mapping_suggestions(conn):
    """Auto-generate ticker mapping suggestions against instruments table."""
    print("\nGenerating ticker mapping suggestions...")

    instruments = conn.execute(
        "SELECT fund_id, name FROM instruments WHERE fund_id LIKE 'YF:%'"
    ).fetchall()

    inst_by_name = {}
    inst_by_ticker = {}
    for fid, iname in instruments:
        if iname:
            inst_by_name[iname.lower().strip()] = fid
        ticker_part = fid.replace('YF:', '').replace('.L', '').replace('.IS', '').upper()
        inst_by_ticker[ticker_part] = fid

    unmapped = conn.execute("""
        SELECT DISTINCT ticker, name FROM etf_holdings
        WHERE (ticker, name) NOT IN (
            SELECT source_ticker, source_name FROM etf_holding_ticker_map
        )
    """).fetchall()

    new_suggestions = 0
    for ticker, name in unmapped:
        yahoo_fund_id = None
        confidence = 0.0

        # 1. Exact ticker match
        t = ticker.upper().split()[0]  # take first word (e.g. "INTC UQ" → "INTC")
        if t in inst_by_ticker:
            yahoo_fund_id = inst_by_ticker[t]
            confidence = 0.95

        # 2. Name exact match
        if not yahoo_fund_id:
            name_lower = name.lower().strip()
            if name_lower in inst_by_name:
                yahoo_fund_id = inst_by_name[name_lower]
                confidence = 0.9

        # 3. Partial name match
        if not yahoo_fund_id:
            for inst_name, fid in inst_by_name.items():
                if len(inst_name) > 5 and inst_name in name_lower:
                    yahoo_fund_id = fid
                    confidence = 0.6
                    break
                elif len(name_lower) > 5 and name_lower[:10] in inst_name:
                    yahoo_fund_id = fid
                    confidence = 0.4
                    break

        try:
            conn.execute("""
                INSERT OR IGNORE INTO etf_holding_ticker_map
                    (source_ticker, source_name, yahoo_fund_id, confidence, reviewed)
                VALUES (?, ?, ?, ?, 0)
            """, (ticker, name, yahoo_fund_id, confidence))
            if conn.execute("SELECT changes()").fetchone()[0] > 0:
                new_suggestions += 1
        except:
            pass

    conn.commit()
    print(f"  Added {new_suggestions} new mapping suggestions")


def process_holdings_dict(conn, results, source_label):
    """Insert a dict of {(fund_id, date): [holdings]} into DB."""
    total_inserted = 0
    total_skipped  = 0

    for (etf_fund_id, scraped_date), holdings in sorted(results.items()):
        if already_imported(conn, etf_fund_id, scraped_date):
            print(f"  SKIP {etf_fund_id} {scraped_date} — already imported")
            total_skipped += 1
            continue

        inserted, errors = insert_holdings(conn, etf_fund_id, scraped_date, holdings)
        total_inserted += inserted
        status = f"{inserted} rows"
        if errors:
            status += f", {errors} errors"
        print(f"  {etf_fund_id} {scraped_date}: {status}")

    return total_inserted, total_skipped


def import_historical_excel(conn):
    """Import from Funds Database.xlsx."""
    if not EXCEL_PATH.exists():
        print(f"Excel file not found: {EXCEL_PATH}")
        return

    print(f"\nImporting historical data from {EXCEL_PATH}...")
    xl = pd.ExcelFile(EXCEL_PATH)

    total_inserted = 0

    # Funds sheet (iShares multi-ETF format)
    print("\n  Sheet: Funds")
    results = parse_excel_funds_sheet(xl)
    inserted, skipped = process_holdings_dict(conn, results, 'Funds')
    total_inserted += inserted
    print(f"  → {inserted} rows inserted, {skipped} dates skipped")

    # WQTM sheet
    if 'WQTM' in xl.sheet_names:
        print("\n  Sheet: WQTM")
        results = parse_excel_wqtm_sheet(xl)
        inserted, skipped = process_holdings_dict(conn, results, 'WQTM')
        total_inserted += inserted
        print(f"  → {inserted} rows inserted, {skipped} dates skipped")

    # NATP sheet
    if 'NATP' in xl.sheet_names:
        print("\n  Sheet: NATP")
        results = parse_excel_natp_sheet(xl)
        inserted, skipped = process_holdings_dict(conn, results, 'NATP')
        total_inserted += inserted
        print(f"  → {inserted} rows inserted, {skipped} dates skipped")

    # FCBR sheet
    if 'FCBR' in xl.sheet_names:
        print("\n  Sheet: FCBR")
        results = parse_excel_fcbr_sheet(xl)
        inserted, skipped = process_holdings_dict(conn, results, 'FCBR')
        total_inserted += inserted
        print(f"  → {inserted} rows inserted, {skipped} dates skipped")

    print(f"\nHistorical import complete: {total_inserted} total rows inserted")


def import_csv_files(conn):
    """Process ongoing CSV/XLS files from import folder."""
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    archive_dir = IMPORT_DIR / 'archive'
    archive_dir.mkdir(exist_ok=True)

    files = sorted(list(IMPORT_DIR.glob('*.csv')) + list(IMPORT_DIR.glob('*.xls')))
    if not files:
        print(f"\nNo files found in {IMPORT_DIR}")
        return

    print(f"\nProcessing {len(files)} files from {IMPORT_DIR}...")
    total_inserted = 0

    for filepath in files:
        prefix = filepath.stem.split('_')[0].upper()
        etf_fund_id = FUND_ID_MAP.get(prefix)

        if not etf_fund_id:
            print(f"\n  SKIP {filepath.name} — unknown prefix '{prefix}'")
            print(f"  Add '{prefix}': 'YF:...' to FUND_ID_MAP in this script")
            continue

        print(f"\n  {filepath.name} → {etf_fund_id}")

        # Parse file
        try:
            if filepath.suffix.lower() == '.csv':
                holdings, scraped_date = parse_ishares_csv(str(filepath))
            else:
                holdings, scraped_date = parse_ishares_xls(str(filepath))
        except Exception as e:
            print(f"  ERROR parsing file: {e}")
            continue

        if not scraped_date:
            scraped_date = datetime.now().strftime('%Y-%m-%d')
            print(f"  WARNING: could not read date from file, using today: {scraped_date}")

        print(f"  Date: {scraped_date}, Holdings: {len(holdings)}")

        if already_imported(conn, etf_fund_id, scraped_date):
            print(f"  SKIP — {etf_fund_id} {scraped_date} already in DB")
            filepath.rename(archive_dir / filepath.name)
            continue

        inserted, errors = insert_holdings(conn, etf_fund_id, scraped_date, holdings)
        total_inserted += inserted
        print(f"  Inserted: {inserted} rows" + (f", Errors: {errors}" if errors else ""))

        # Archive processed file
        filepath.rename(archive_dir / filepath.name)
        print(f"  Archived to archive/{filepath.name}")

    print(f"\nCSV import complete: {total_inserted} total rows inserted")


def main():
    parser = argparse.ArgumentParser(description='ETF Holdings Importer')
    parser.add_argument('--historical', action='store_true',
                        help='Import from Funds Database.xlsx')
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)

    if args.historical:
        import_historical_excel(conn)

    import_csv_files(conn)
    generate_mapping_suggestions(conn)

    # Summary
    total = conn.execute("SELECT COUNT(*) FROM etf_holdings").fetchone()[0]
    funds = conn.execute("SELECT COUNT(DISTINCT etf_fund_id) FROM etf_holdings").fetchone()[0]
    dates = conn.execute("SELECT COUNT(DISTINCT scraped_date) FROM etf_holdings").fetchone()[0]
    print(f"\n=== DB Summary ===")
    print(f"  Total holdings rows: {total:,}")
    print(f"  ETFs tracked:        {funds}")
    print(f"  Unique dates:        {dates}")

    conn.close()


if __name__ == '__main__':
    main()