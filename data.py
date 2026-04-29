# data.py
# All data loading, calculation and database functions.
# No Dash imports — pure Python/pandas/sqlite3.

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import config

DB_PATH = "data/funds.db"


# ── DATABASE: PRICES & INSTRUMENTS ────────────────────────────

def load_data():
    """Load all price data joined with instrument names."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT p.fund_id, i.name as fund_name, i.asset_type, p.date,
               p.open, p.high, p.low, p.close, p.volume
        FROM prices p
        LEFT JOIN instruments i ON p.fund_id = i.fund_id
        ORDER BY p.fund_id, p.date
    """, conn)
    conn.close()
    df['date'] = pd.to_datetime(df['date'])
    return df


def load_instruments():
    """Load instruments table into a dict keyed by fund_id."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT fund_id, name, asset_type, currency, price_unit, category FROM instruments"
    ).fetchall()
    conn.close()
    return {
        r[0]: {
            'name': r[1], 'asset_type': r[2], 'currency': r[3],
            'price_unit': r[4], 'category': r[5] or '—'
        }
        for r in rows
    }


# ── DATABASE: PORTFOLIO HOLDINGS ──────────────────────────────

def load_portfolio():
    """Load holdings from portfolio_holdings table."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT fund_id, units FROM portfolio_holdings ORDER BY fund_id"
        ).fetchall()
        conn.close()
        return [{'fund_id': r[0], 'units': r[1]} for r in rows]
    except Exception:
        return []


def save_portfolio(portfolio):
    """Upsert holdings into portfolio_holdings table."""
    now  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(DB_PATH)
    for item in portfolio:
        conn.execute(
            "INSERT OR REPLACE INTO portfolio_holdings (fund_id, units, updated_at) VALUES (?, ?, ?)",
            (item['fund_id'], float(item['units']), now)
        )
    conn.commit()
    conn.close()


def delete_holding(fund_id):
    """Remove a holding from portfolio_holdings table."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM portfolio_holdings WHERE fund_id = ?", (fund_id,))
    conn.commit()
    conn.close()


def upsert_holding(fund_id, units):
    """Insert or update a single holding."""
    now  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO portfolio_holdings (fund_id, units, updated_at) VALUES (?, ?, ?)",
        (fund_id, float(units), now)
    )
    conn.commit()
    conn.close()


def recalc_portfolio_from_transactions(fund_id):
    """Recalculate units for a fund from BUY/SELL transactions and update DB."""
    conn = sqlite3.connect(DB_PATH)
    txns = conn.execute(
        "SELECT type, quantity FROM transactions WHERE fund_id = ? AND type != 'DIVIDEND' ORDER BY trade_date",
        (fund_id,)
    ).fetchall()
    conn.close()

    total_qty = 0.0
    for ttype, qty in txns:
        if ttype == "BUY":
            total_qty += float(qty)
        elif ttype == "SELL":
            total_qty -= float(qty)
    total_qty = max(total_qty, 0.0)

    now  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect(DB_PATH)
    if total_qty > 0:
        conn.execute(
            "INSERT OR REPLACE INTO portfolio_holdings (fund_id, units, updated_at) VALUES (?, ?, ?)",
            (fund_id, total_qty, now)
        )
    else:
        conn.execute("DELETE FROM portfolio_holdings WHERE fund_id = ?", (fund_id,))
    conn.commit()
    conn.close()
    return total_qty


# ── DATABASE: CASH ACCOUNTS ───────────────────────────────────

def load_cash_accounts():
    """Load cash accounts from SQLite database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT id, name, currency, amount FROM cash_accounts ORDER BY id"
        ).fetchall()
        conn.close()
        return [{'id': r[0], 'name': r[1], 'currency': r[2], 'amount': r[3]} for r in rows]
    except Exception:
        return []


def add_cash_account(name, currency, amount):
    """Add a single cash account row."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO cash_accounts (name, currency, amount) VALUES (?, ?, ?)",
        (name, currency, float(amount))
    )
    conn.commit()
    conn.close()


def remove_cash_account(row_id):
    """Remove a single cash account by its database id."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM cash_accounts WHERE id = ?", (row_id,))
    conn.commit()
    conn.close()


def calc_cash_total_gbp(accounts, fx_rates):
    """Convert all cash accounts to GBP and return total."""
    total = 0.0
    for acc in accounts:
        amount = float(acc.get('amount', 0))
        curr   = acc.get('currency', 'GBP')
        if curr == 'GBP':
            total += amount
        elif curr == 'USD':
            total += amount / fx_rates.get('USD', 1.26)
        elif curr == 'TRY':
            total += amount / fx_rates.get('TRY', 43.0)
    return total


# ── DATABASE: SNAPSHOTS ───────────────────────────────────────

def get_snapshot_options():
    """Load snapshot dates from database for dropdown."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT snap_date FROM portfolio_snapshots ORDER BY snap_date DESC"
        ).fetchall()
        conn.close()
        options = [{'label': 'None', 'value': 'none'}]
        for r in rows:
            dt = pd.Timestamp(r[0])
            options.append({'label': dt.strftime('%d %b %Y'), 'value': r[0]})
        return options
    except Exception:
        return [{'label': 'None', 'value': 'none'}]


def get_latest_snapshot_value():
    """Return the most recent snapshot date string from database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row  = conn.execute(
            "SELECT snap_date FROM portfolio_snapshots ORDER BY snap_date DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return row[0] if row else 'none'
    except Exception:
        return 'none'


def load_snapshot(snapshot_date):
    """Load snapshot holdings, categories and cash total from database.
    Returns dict: {holdings, categories, cash_total, label} or empty if not found.
    """
    if not snapshot_date or snapshot_date == 'none':
        return {'holdings': {}, 'categories': {}, 'cash_total': None, 'label': None}
    try:
        conn     = sqlite3.connect(DB_PATH)
        snap_row = conn.execute(
            "SELECT id FROM portfolio_snapshots WHERE snap_date = ?", (snapshot_date,)
        ).fetchone()
        if not snap_row:
            conn.close()
            return {'holdings': {}, 'categories': {}, 'cash_total': None, 'label': None}

        snap_id = snap_row[0]
        label   = pd.Timestamp(snapshot_date).strftime('%d %b %Y')

        h_rows  = conn.execute(
            "SELECT fund_id, value_gbp FROM snapshot_holdings WHERE snapshot_id = ?", (snap_id,)
        ).fetchall()
        holdings = {r[0]: r[1] for r in h_rows}

        c_rows  = conn.execute(
            "SELECT category, value_gbp FROM snapshot_categories WHERE snapshot_id = ?", (snap_id,)
        ).fetchall()
        categories = {r[0]: r[1] for r in c_rows}

        cash_row   = conn.execute(
            "SELECT SUM(value_gbp) FROM snapshot_cash WHERE snapshot_id = ?", (snap_id,)
        ).fetchone()
        cash_total = cash_row[0] if cash_row and cash_row[0] else None

        conn.close()
        return {'holdings': holdings, 'categories': categories,
                'cash_total': cash_total, 'label': label}
    except Exception:
        return {'holdings': {}, 'categories': {}, 'cash_total': None, 'label': None}


# ── FX & PRICE HELPERS ────────────────────────────────────────

def get_fx_rates(df):
    """Get latest FX rates from price data. Returns dict {USD: rate, TRY: rate}."""
    rates = {}
    fx    = df[df['fund_id'] == 'YF:GBPUSD=X'].sort_values('date')
    rates['USD'] = fx.iloc[-1]['close'] if not fx.empty else 1.26
    fx2   = df[df['fund_id'] == 'YF:GBPTRY=X'].sort_values('date')
    rates['TRY'] = fx2.iloc[-1]['close'] if not fx2.empty else 43.0
    return rates


def get_gbpusd(df):
    return get_fx_rates(df)['USD']


def to_gbp(price, price_unit, currency, gbpusd, fx_rates=None):
    """Convert a price to GBP pounds."""
    if price is None:
        return None
    if price_unit == 'pence':
        price = price / 100
    if price_unit == 'point':
        if currency == 'TRY' and fx_rates:
            price = price / fx_rates['TRY']
        else:
            return None
    elif price_unit == 'ratio':
        return None
    if currency == 'USD':
        price = price / (fx_rates['USD'] if fx_rates else gbpusd)
    return price


def get_latest_price(df, fund_id):
    fund_df = df[df['fund_id'] == fund_id]
    if fund_df.empty:
        return None
    return fund_df.loc[fund_df['date'].idxmax(), 'close']


# ── PRICE SERIES BUILDERS ─────────────────────────────────────

def build_calculated_series(df):
    """CALC:XAUGBP = Gold Futures USD / GBPUSD."""
    rows   = []
    xauusd = df[df['fund_id'] == 'YF:GC=F'].set_index('date')['close']
    gbpusd = df[df['fund_id'] == 'YF:GBPUSD=X'].set_index('date')['close']
    if xauusd.empty or gbpusd.empty:
        return pd.DataFrame()
    for date in sorted(set(xauusd.index) & set(gbpusd.index)):
        gbpusd_val = gbpusd.loc[date]
        if gbpusd_val == 0:
            continue
        price = xauusd.loc[date] / gbpusd_val
        rows.append({'fund_id': 'CALC:XAUGBP', 'fund_name': 'Gold / GBP (Spot)',
                     'asset_type': 'Commodity', 'date': date,
                     'open': price, 'high': price, 'low': price, 'close': price, 'volume': 0})
    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    result['date'] = pd.to_datetime(result['date'])
    return result


def build_composite_data(df):
    """Build synthetic price series for composite funds defined in config."""
    composites = getattr(config, 'COMPOSITE_FUNDS', [])
    if not composites:
        return pd.DataFrame()
    rows = []
    for comp in composites:
        fund_id    = comp['fund_id']
        fund_name  = comp['display_name']
        asset_type = comp.get('asset_type', 'Fund')
        series     = {}
        for c in comp['components']:
            cdf = df[df['fund_id'] == c['fund_id']][['date', 'close']].sort_values('date')
            if not cdf.empty:
                series[c['fund_id']] = cdf.set_index('date')['close']
        if not series:
            continue
        common_dates = None
        for s in series.values():
            common_dates = set(s.index) if common_dates is None else common_dates & set(s.index)
        if not common_dates or len(common_dates) < 2:
            continue
        common_dates     = sorted(common_dates)
        base_date        = common_dates[0]
        composite_series = pd.Series(0.0, index=common_dates)
        for c in comp['components']:
            cid = c['fund_id']
            if cid not in series:
                continue
            s        = series[cid].loc[common_dates]
            base_val = s.loc[base_date]
            if base_val == 0:
                continue
            composite_series += (s / base_val) * 100 * c['weight']
        for date, price in composite_series.items():
            rows.append({'fund_id': fund_id, 'fund_name': fund_name, 'asset_type': asset_type,
                         'date': date, 'open': price, 'high': price,
                         'low': price, 'close': price, 'volume': 0})
    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    result['date'] = pd.to_datetime(result['date'])
    return result


def build_df_combined(df):
    """Combine raw prices with calculated and composite series."""
    df_calc      = build_calculated_series(df)
    df_composite = build_composite_data(df)
    parts = [x for x in [df, df_composite, df_calc] if not x.empty]
    return pd.concat(parts, ignore_index=True)


# ── RETURN CALCULATIONS ───────────────────────────────────────

def ytd_date():
    dec31 = datetime(datetime.now().year - 1, 12, 31)
    while dec31.weekday() >= 5:
        dec31 -= timedelta(days=1)
    return dec31.strftime('%Y-%m-%d')


def calc_return(df, fund_id, days_back=None, from_date=None):
    fund_df = df[df['fund_id'] == fund_id].sort_values('date')
    if fund_df.empty:
        return None
    latest_price = fund_df.iloc[-1]['close']
    if from_date:
        past_df = fund_df[fund_df['date'] <= pd.Timestamp(from_date)]
    else:
        past_df = fund_df[fund_df['date'] <= fund_df['date'].max() - timedelta(days=days_back)]
    if past_df.empty:
        return None
    past_price = past_df.iloc[-1]['close']
    if past_price == 0:
        return None
    return ((latest_price / past_price) - 1) * 100


def heatmap_color(val, vmin, vmax):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 'rgb(240,240,240)'
    if val == 0:
        return 'rgb(255,255,255)'
    if val > 0:
        intensity = min(abs(val) / 3.0, 1.0)
        r = int(255 - intensity * 180)
        return f'rgb({r},255,{r})'
    else:
        intensity = min(abs(val) / 3.0, 1.0)
        g = int(255 - intensity * 180)
        return f'rgb(255,{g},{g})'


# ── P&L CALCULATION ───────────────────────────────────────────

def txn_price_to_gbp(price, txn_currency, txn_fx_rate, price_unit="pound"):
    """Convert a transaction price to GBP pounds."""
    p  = float(price)
    fx = float(txn_fx_rate) if txn_fx_rate else 1.0
    c  = str(txn_currency or "GBP").strip().upper()
    if price_unit == "pence" and c == "GBP":
        p = p / 100
    if c in ("GBP", "GBPC"):
        return p
    elif c == "USD":
        return p / fx
    elif c in ("XAU", "TRY"):
        return p / fx
    return p


def calc_pnl(df_combined, instruments, gbpusd, fx_rates):
    """Calculate P&L for all holdings from transaction history."""
    conn = sqlite3.connect(DB_PATH)
    txns = pd.read_sql_query("""
        SELECT t.fund_id, t.account, t.trade_date, t.type,
               t.quantity, t.price, t.currency, t.fx_rate,
               i.name, i.price_unit, i.category
        FROM transactions t
        LEFT JOIN instruments i ON t.fund_id = i.fund_id
        ORDER BY t.fund_id, t.trade_date
    """, conn)
    conn.close()

    if txns.empty:
        return pd.DataFrame()

    results = []
    for fund_id, group in txns.groupby("fund_id"):
        inst     = instruments.get(fund_id, {})
        name     = inst.get("name", fund_id)
        category = inst.get("category", "—")
        punit    = inst.get("price_unit", "pound")
        curr     = inst.get("currency", "GBP")

        total_qty       = 0.0
        total_cost_gbp  = 0.0
        realised_pnl    = 0.0
        total_dividends = 0.0

        for _, r in group.iterrows():
            qty   = float(r["quantity"])
            price = float(r["price"])
            ttype = r["type"]
            cost_per_unit = txn_price_to_gbp(price, r["currency"], r["fx_rate"], punit)
            cost_gbp      = qty * cost_per_unit

            if ttype == "BUY":
                total_qty      += qty
                total_cost_gbp += cost_gbp
            elif ttype == "DIVIDEND":
                div_gbp         = txn_price_to_gbp(qty, r["currency"], r["fx_rate"], "pound")
                total_cost_gbp  = max(total_cost_gbp - div_gbp, 0)
                total_dividends += div_gbp
            elif ttype == "SELL":
                if total_qty > 0:
                    avg_cost        = total_cost_gbp / total_qty
                    sell_qty        = min(qty, total_qty)
                    realised_pnl   += sell_qty * (cost_per_unit - avg_cost)
                    total_cost_gbp -= sell_qty * avg_cost
                    total_qty      -= sell_qty
                    total_qty       = max(total_qty, 0)

        avg_cost_gbp = total_cost_gbp / total_qty if total_qty > 0 else 0

        if total_qty > 0:
            if fund_id.startswith("COMPOSITE:"):
                comp_def = next((c for c in getattr(config, "COMPOSITE_FUNDS", [])
                                 if c["fund_id"] == fund_id), None)
                current_price_gbp = None
                if comp_def:
                    weighted = 0.0
                    for c in comp_def["components"]:
                        cp   = get_latest_price(df_combined, c["fund_id"])
                        ci   = instruments.get(c["fund_id"], {})
                        cgbp = to_gbp(cp, ci.get("price_unit", "pence"),
                                      ci.get("currency", "GBP"), gbpusd, fx_rates)
                        if cgbp:
                            weighted += cgbp * c["weight"]
                    current_price_gbp = weighted if weighted > 0 else None
            elif fund_id.startswith(("CASH:", "ASSET:")):
                current_price_gbp = 1.0
            else:
                cp = get_latest_price(df_combined, fund_id)
                current_price_gbp = to_gbp(cp, punit, curr, gbpusd, fx_rates)

            current_value  = current_price_gbp * total_qty if current_price_gbp else None
            unrealised_pnl = (current_value - total_cost_gbp) if current_value is not None else None
        else:
            current_value  = None
            unrealised_pnl = None

        if unrealised_pnl is not None:
            total_pnl = realised_pnl + unrealised_pnl + total_dividends
        elif realised_pnl != 0 or total_dividends != 0:
            total_pnl = realised_pnl + total_dividends
        else:
            continue

        cost_basis_for_pct = total_cost_gbp + abs(realised_pnl) + total_dividends
        pnl_pct = (total_pnl / cost_basis_for_pct * 100) if cost_basis_for_pct > 0 else None

        results.append({
            "fund_id":       fund_id,
            "Fund":          name,
            "Category":      category,
            "Qty":           total_qty,
            "Avg Cost":      avg_cost_gbp,
            "Cost Basis":    total_cost_gbp,
            "Current Value": current_value,
            "Realised":      realised_pnl,
            "Dividends":     total_dividends,
            "PnL":           total_pnl,
            "PnL Pct":       pnl_pct,
        })

    return pd.DataFrame(results)


# ── PORTFOLIO VALUE HELPERS ───────────────────────────────────

def get_holding_value_gbp(fid, units, df_combined, instruments, gbpusd, fx_rates):
    """Calculate GBP value for a single holding."""
    inst  = instruments.get(fid, {})
    punit = inst.get('price_unit', '?')
    curr  = inst.get('currency', '?')

    if fid.startswith('CASH:') or fid.startswith('ASSET:'):
        effective_unit = 'point' if fid == 'CASH:TRY' else punit
        gbp = to_gbp(1.0, effective_unit, curr, gbpusd, fx_rates)
        return gbp * units if gbp is not None else None

    if fid.startswith('COMPOSITE:'):
        comp_def = next((c for c in getattr(config, 'COMPOSITE_FUNDS', [])
                         if c['fund_id'] == fid), None)
        if not comp_def:
            return None
        weighted = 0.0
        for c in comp_def['components']:
            c_price = get_latest_price(df_combined, c['fund_id'])
            c_inst  = instruments.get(c['fund_id'], {})
            c_gbp   = to_gbp(c_price, c_inst.get('price_unit', 'pence'),
                             c_inst.get('currency', 'GBP'), gbpusd, fx_rates)
            if c_gbp is not None:
                weighted += c_gbp * c['weight']
        return weighted * units if weighted > 0 else None

    price = get_latest_price(df_combined, fid)
    gbp   = to_gbp(price, punit, curr, gbpusd, fx_rates) if price else None
    return gbp * units if gbp is not None else None