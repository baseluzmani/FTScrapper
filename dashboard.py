# dashboard.py
# Financial dashboard for FT Fund data.
# Run with: python3 dashboard.py
# Then open: http://localhost:8050

import dash
from dash import html, dcc, Input, Output, State, ALL, ctx
import plotly.graph_objects as go
import pandas as pd
import sqlite3
import json
import os
from datetime import datetime, timedelta
import numpy as np
import config

# ── 1. DATA LAYER ──────────────────────────────────────────────

DB_PATH        = "data/funds.db"
PORTFOLIO_PATH = "data/portfolio.json"
GBPUSD         = None  # cached FX rate


def load_data():
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
    return {r[0]: {'name': r[1], 'asset_type': r[2], 'currency': r[3], 'price_unit': r[4], 'category': r[5] or '—'}
            for r in rows}


def load_portfolio():
    """Load holdings from portfolio_holdings table."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT fund_id, units FROM portfolio_holdings ORDER BY fund_id").fetchall()
        conn.close()
        return [{'fund_id': r[0], 'units': r[1]} for r in rows]
    except Exception:
        return []


def save_portfolio(portfolio):
    """Save holdings to portfolio_holdings table."""
    from datetime import datetime
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


def save_cash_accounts(accounts):
    """Save cash accounts to SQLite — full replace of all rows."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM cash_accounts")
    for acc in accounts:
        conn.execute(
            "INSERT INTO cash_accounts (name, currency, amount) VALUES (?, ?, ?)",
            (acc['name'], acc['currency'], float(acc['amount']))
        )
    conn.commit()
    conn.close()


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


def get_fx_rates(df):
    """Get latest FX rates from database. Returns dict of currency -> GBP rate."""
    rates = {}
    # GBPUSD=X gives how many USD per 1 GBP
    fx = df[df['fund_id'] == 'YF:GBPUSD=X'].sort_values('date')
    rates['USD'] = fx.iloc[-1]['close'] if not fx.empty else 1.26

    # GBPTRY=X gives how many TRY per 1 GBP
    fx2 = df[df['fund_id'] == 'YF:GBPTRY=X'].sort_values('date')
    rates['TRY'] = fx2.iloc[-1]['close'] if not fx2.empty else 43.0

    return rates


def get_gbpusd(df):
    """Get latest GBP/USD rate from database."""
    return get_fx_rates(df)['USD']


def to_gbp(price, price_unit, currency, gbpusd, fx_rates=None):
    """Convert a price to GBP pounds."""
    if price is None:
        return None
    # Convert pence to pounds
    if price_unit == 'pence':
        price = price / 100
    # Points/ratios — Turkish stocks are priced as points in TRY
    # We convert TRY points to GBP
    if price_unit == 'point':
        if currency == 'TRY' and fx_rates:
            price = price / fx_rates['TRY']
        else:
            return None
    elif price_unit == 'ratio':
        return None
    # Convert USD to GBP
    if currency == 'USD':
        price = price / (fx_rates['USD'] if fx_rates else gbpusd)
    return price


def build_calculated_series(df):
    """Build calculated price series not available directly from Yahoo.
    CALC:XAUGBP = GC=F (Gold Futures USD) / GBPUSD=X
    """
    rows = []

    # Use Gold Futures (GC=F) as proxy for gold spot price in USD
    xauusd = df[df['fund_id'] == 'YF:GC=F'].set_index('date')['close']
    gbpusd = df[df['fund_id'] == 'YF:GBPUSD=X'].set_index('date')['close']

    if xauusd.empty or gbpusd.empty:
        return pd.DataFrame()

    common_dates = sorted(set(xauusd.index) & set(gbpusd.index))
    for date in common_dates:
        gbpusd_val = gbpusd.loc[date]
        if gbpusd_val == 0:
            continue
        price = xauusd.loc[date] / gbpusd_val
        rows.append({
            'fund_id':    'CALC:XAUGBP',
            'fund_name':  'Gold / GBP (Spot)',
            'asset_type': 'Commodity',
            'date':       date,
            'open':       price,
            'high':       price,
            'low':        price,
            'close':      price,
            'volume':     0,
        })

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

        common_dates     = sorted(common_dates)
        base_date        = common_dates[0]
        composite_series = pd.Series(0.0, index=common_dates)

        for c in components:
            cid    = c['fund_id']
            weight = c['weight']
            if cid not in series:
                continue
            s        = series[cid].loc[common_dates]
            base_val = s.loc[base_date]
            if base_val == 0:
                continue
            composite_series += (s / base_val) * 100 * weight

        for date, price in composite_series.items():
            rows.append({
                'fund_id':    fund_id,
                'fund_name':  fund_name,
                'asset_type': asset_type,
                'date':       date,
                'open':       price,
                'high':       price,
                'low':        price,
                'close':      price,
                'volume':     0,
            })

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    result['date'] = pd.to_datetime(result['date'])
    return result


def get_latest_price(df, fund_id):
    fund_df = df[df['fund_id'] == fund_id]
    if fund_df.empty:
        return None
    return fund_df.loc[fund_df['date'].idxmax(), 'close']


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


def ytd_date():
    dec31 = datetime(datetime.now().year - 1, 12, 31)
    while dec31.weekday() >= 5:
        dec31 -= timedelta(days=1)
    return dec31.strftime('%Y-%m-%d')


def build_returns_table(df, since_date):
    funds = df[['fund_id', 'fund_name', 'asset_type']].drop_duplicates(subset=['fund_id'])
    rows = []
    for _, fund in funds.iterrows():
        fid    = fund['fund_id']
        fname  = fund['fund_name']
        atype  = fund['asset_type'] if pd.notna(fund['asset_type']) else '—'
        latest = get_latest_price(df, fid)
        rows.append({
            'fund_id': fid,
            'Fund':    fname,
            'Type':    atype,
            'Price':   round(latest, 2) if latest else None,
            '1D':      calc_return(df, fid, days_back=1),
            '1W':      calc_return(df, fid, days_back=5),
            '1M':      calc_return(df, fid, days_back=21),
            '3M':      calc_return(df, fid, days_back=63),
            'YTD':     calc_return(df, fid, from_date=ytd_date()),
            'Since':   calc_return(df, fid, from_date=since_date),
        })
    result = pd.DataFrame(rows)
    result = result.sort_values('YTD', ascending=False, na_position='last')
    return result


def heatmap_color(val, vmin, vmax):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 'rgb(240,240,240)'
    if val == 0:
        return 'rgb(255,255,255)'
    if val > 0:
        intensity = min(abs(val) / 3.0, 1.0)
        r = int(255 - intensity * 180)
        g = 255
        b = int(255 - intensity * 180)
        return f'rgb({r},{g},{b})'
    else:
        intensity = min(abs(val) / 3.0, 1.0)
        r = 255
        g = int(255 - intensity * 180)
        b = int(255 - intensity * 180)
        return f'rgb({r},{g},{b})'


def get_top4_by_ytd(df, fund_ids):
    returns = []
    for fid in fund_ids:
        r = calc_return(df, fid, from_date=ytd_date())
        if r is not None:
            returns.append((fid, r))
    returns.sort(key=lambda x: x[1], reverse=True)
    return [fid for fid, _ in returns[:4]]


def get_top4_funds(df, from_date):
    funds = df['fund_id'].unique()
    returns = []
    for fid in funds:
        r = calc_return(df, fid, from_date=from_date)
        if r is not None:
            returns.append((fid, r))
    returns.sort(key=lambda x: x[1], reverse=True)
    return [fid for fid, _ in returns[:4]]


def render_returns_table(table_df, since_label, sort_state, header_type='market',
                         selected_funds=None, clickable=False):
    return_cols    = ['1D', '1W', '1M', '3M', 'YTD', 'Since']
    selected_funds = selected_funds or []

    col_ranges = {}
    for col in return_cols:
        vals = table_df[col].dropna()
        col_ranges[col] = (vals.min(), vals.max()) if len(vals) > 0 else (0, 0)

    col_defs = [
        ('Fund',       'Fund',  False),
        ('Type',       'Type',  False),
        ('Price',      'Price', False),
        ('1D %',       '1D',    True),
        ('1W %',       '1W',    True),
        ('1M %',       '1M',    True),
        ('3M %',       '3M',    True),
        ('YTD %',      'YTD',   True),
        (since_label,  'Since', True),
    ]

    def sort_arrow(col_key):
        if sort_state['col'] == col_key:
            return ' ▲' if sort_state['asc'] else ' ▼'
        return ' ⇅'

    header = html.Tr([
        html.Th(
            f"{label}{sort_arrow(key)}",
            id={'type': f'sort-header-{header_type}', 'col': key},
            n_clicks=0,
            style={
                'backgroundColor': '#1a3a5c', 'color': 'white',
                'padding': '5px 8px', 'fontSize': '10px', 'fontWeight': '600',
                'textAlign': 'center' if label != 'Fund' else 'left',
                'letterSpacing': '0.03em', 'whiteSpace': 'nowrap',
                'cursor': 'pointer', 'userSelect': 'none',
            }
        ) for label, key, _ in col_defs
    ])

    rows = []
    for _, row in table_df.iterrows():
        fid         = row['fund_id']
        is_selected = fid in selected_funds
        row_bg      = '#e8f0f8' if is_selected else 'transparent'
        row_style   = {
            'borderBottom': '1px solid #f0f3f7',
            'backgroundColor': row_bg,
            'cursor': 'pointer' if clickable else 'default',
        }

        max_len   = 30
        fund_name = str(row['Fund']) if row['Fund'] and str(row['Fund']) != 'nan' else row['fund_id']
        fund_disp = fund_name if len(fund_name) <= max_len else fund_name[:max_len] + '…'

        cells = [
            html.Td(
                html.Div([
                    html.Span('● ', style={
                        'color': '#2E75B6', 'fontSize': '10px',
                        'marginRight': '4px',
                        'opacity': '1' if is_selected else '0',
                    }),
                    html.Span(fund_disp, title=fund_name),
                ]),
                style={
                    'padding': '4px 6px', 'fontSize': '11px',
                    'fontWeight': '600' if is_selected else '500',
                    'color': '#1a3a5c', 'whiteSpace': 'nowrap',
                    'maxWidth': '200px', 'overflow': 'hidden',
                }
            ),
            html.Td(row['Type'], style={
                'padding': '4px 6px', 'fontSize': '10px',
                'textAlign': 'center', 'color': '#666', 'whiteSpace': 'nowrap',
            }),
            html.Td(
                f"{row['Price']:.2f}" if row['Price'] else 'N/A',
                style={
                    'padding': '4px 6px', 'fontSize': '11px',
                    'textAlign': 'center', 'fontFamily': 'monospace', 'color': '#333',
                }
            ),
        ]
        for col in return_cols:
            val = row[col]
            vmin, vmax = col_ranges[col]
            bg = heatmap_color(val, vmin, vmax)
            formatted = f"{val:+.1f}%" if val is not None and not np.isnan(val) else 'N/A'
            cells.append(html.Td(formatted, style={
                'padding': '4px 6px', 'fontSize': '11px',
                'textAlign': 'center', 'fontWeight': '600',
                'fontFamily': 'monospace', 'backgroundColor': bg,
                'color': '#1a1a1a', 'borderRadius': '3px',
            }))

        if clickable:
            row_type = 'market-row' if header_type == 'market' else 'holding-row'
            tr = html.Tr(
                cells,
                id={'type': row_type, 'fund_id': fid},
                n_clicks=0,
                style=row_style,
            )
        else:
            tr = html.Tr(cells, style=row_style)

        rows.append(tr)

    return html.Table(
        [html.Thead(header), html.Tbody(rows)],
        style={'width': '100%', 'borderCollapse': 'collapse'}
    )


def build_relative_chart(df_combined, selected_funds, since_date):
    fig = go.Figure()
    if not selected_funds:
        fig.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', height=400,
            annotations=[dict(
                text='Click a fund in the table to add it to the chart',
                x=0.5, y=0.5, xref='paper', yref='paper',
                showarrow=False, font=dict(size=13, color='#aaa'),
            )],
            margin=dict(l=40, r=40, t=10, b=40),
        )
        return fig

    try:
        start = pd.Timestamp(since_date)
    except Exception:
        start = pd.Timestamp(DEFAULT_DATE)

    fund_returns = []
    for fund_id in selected_funds:
        r = calc_return(df_combined, fund_id, from_date=since_date)
        fund_returns.append((fund_id, r or -999))
    fund_returns.sort(key=lambda x: x[1], reverse=True)

    for fund_id, _ in fund_returns:
        all_fund_df = df_combined[df_combined['fund_id'] == fund_id].sort_values('date')
        if all_fund_df.empty:
            continue

        base_df = all_fund_df[all_fund_df['date'] <= start]
        base_price = base_df.iloc[-1]['close'] if not base_df.empty else all_fund_df.iloc[0]['close']

        if base_price == 0:
            continue

        fund_df = all_fund_df[all_fund_df['date'] >= start].copy()
        if fund_df.empty or len(fund_df) < 2:
            continue

        fund_df['return'] = ((fund_df['close'] / base_price) - 1) * 100
        fund_name = fund_df.iloc[0]['fund_name']

        fig.add_trace(go.Scatter(
            x=fund_df['date'], y=fund_df['return'],
            mode='lines', name=fund_name, line=dict(width=2),
            hovertemplate='%{x|%d %b %Y}: %{y:.1f}%<extra>' + fund_name + '</extra>',
        ))

        idx_max  = fund_df['return'].idxmax()
        idx_min  = fund_df['return'].idxmin()
        last_row = fund_df.iloc[-1]

        for point, label, ay in [
            (fund_df.loc[idx_max], f"H: {fund_df.loc[idx_max, 'return']:+.1f}%", -18),
            (fund_df.loc[idx_min], f"L: {fund_df.loc[idx_min, 'return']:+.1f}%",  18),
            (last_row,             f"▶ {last_row['return']:+.1f}%",                0),
        ]:
            fig.add_annotation(
                x=point['date'], y=point['return'], text=label,
                showarrow=True, arrowhead=0, arrowwidth=1,
                ax=20, ay=ay, font=dict(size=9, color='#333'),
                bgcolor='rgba(255,255,255,0.85)',
                bordercolor='#ccc', borderwidth=1, borderpad=2,
            )

    fig.update_layout(
        yaxis_tickformat='+.1f', yaxis_ticksuffix='%',
        hovermode='x unified',
        legend=dict(orientation='h', y=-0.22, x=0, font=dict(size=10)),
        margin=dict(l=40, r=80, t=10, b=80),
        plot_bgcolor='white', paper_bgcolor='white', height=400,
    )
    fig.update_xaxes(showgrid=True, gridcolor='#f0f0f0', tickfont=dict(size=10))
    fig.update_yaxes(
        showgrid=True, gridcolor='#f0f0f0',
        zeroline=True, zerolinecolor='#bbb', zerolinewidth=1,
        tickfont=dict(size=10),
    )
    return fig


# ── 2. APP SETUP ───────────────────────────────────────────────

def get_snapshot_options():
    """Load snapshot dates from database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT snap_date FROM portfolio_snapshots ORDER BY snap_date DESC").fetchall()
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
        row  = conn.execute("SELECT snap_date FROM portfolio_snapshots ORDER BY snap_date DESC LIMIT 1").fetchone()
        conn.close()
        return row[0] if row else 'none'
    except Exception:
        return 'none'


app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}]
)

app.index_string = (
    '<!DOCTYPE html>'
    '<html>'
    '<head>'
    '{%metas%}'
    '<title>Fund Dashboard</title>'
    '{%favicon%}'
    '{%css%}'
    '<style>'
    '@media (max-width: 768px) {'
    '  #portfolio-table-div, #portfolio-category-div {'
    '    width: 100% !important;'
    '    margin-left: 0 !important;'
    '    flex-shrink: 1 !important;'
    '  }'
    '  #holdings-relative-chart, #relative-chart {'
    '    display: none !important;'
    '  }'
    '  .sum-fund { width: 40% !important; max-width: 40% !important; }'
    '  .sum-num  { width: 1% !important; white-space: nowrap !important; }'
    '  .portfolio-cat-panel { width: 100% !important; margin-left: 0 !important; }'
    '}'
    '@media (min-width: 769px) {'
    '  .sum-fund { width: 1% !important; white-space: nowrap !important; }'
    '  .sum-num  { width: 1% !important; white-space: nowrap !important; }'
    '}'
    '</style>'
    '</head>'
    '<body>'
    '{%app_entry%}'
    '<footer>'
    '{%config%}'
    '{%scripts%}'
    '{%renderer%}'
    '</footer>'
    '</body>'
    '</html>'
)

df           = load_data()
df_composite = build_composite_data(df)
df_calc      = build_calculated_series(df)
df_combined  = pd.concat(
    [x for x in [df, df_composite, df_calc] if not x.empty],
    ignore_index=True
)
instruments  = load_instruments()

funds = df[['fund_id', 'fund_name']].drop_duplicates()
fund_options = [
    {'label': row['fund_name'], 'value': row['fund_id']}
    for _, row in funds.iterrows()
]

composite_options = [
    {'label': c['display_name'], 'value': c['fund_id']}
    for c in getattr(config, 'COMPOSITE_FUNDS', [])
]
all_fund_options = fund_options + composite_options

DEFAULT_DATE = config.DEFAULT_SINCE_DATE
max_date     = df['date'].max().date()
min_date     = df['date'].min().date()
top4_default = get_top4_funds(df_combined, DEFAULT_DATE)

_portfolio_ids        = [h['fund_id'] for h in load_portfolio()]
top4_holdings_default = get_top4_by_ytd(df_combined, _portfolio_ids)


def _include_in_portfolio(fund_id, inst):
    unit = inst.get('price_unit', '')
    curr = inst.get('currency', '')
    if fund_id.startswith(('CASH:', 'ASSET:')):
        return True
    if unit == 'ratio':
        return False
    if unit == 'point' and curr == 'TRY':
        return True
    if unit == 'point':
        return False
    return True

portfolio_options = [
    {'label': f"{v['name']} ({k})", 'value': k}
    for k, v in sorted(instruments.items(), key=lambda x: x[1]['name'])
    if _include_in_portfolio(k, v)
]

# ── 3. STYLES ──────────────────────────────────────────────────

CARD = {
    'backgroundColor': '#ffffff',
    'borderRadius': '8px',
    'padding': '14px 18px',
    'boxShadow': '0 1px 4px rgba(0,0,0,0.08)',
    'marginBottom': '12px',
}
SECTION_TITLE = {
    'color': '#1a3a5c',
    'fontSize': '11px',
    'fontWeight': '700',
    'letterSpacing': '0.08em',
    'textTransform': 'uppercase',
    'marginBottom': '10px',
    'marginTop': '0',
}
TAB_STYLE = {
    'padding': '8px 20px',
    'fontSize': '12px',
    'fontWeight': '600',
    'color': '#666',
    'borderBottom': '2px solid transparent',
    'cursor': 'pointer',
}
TAB_SELECTED_STYLE = {
    'padding': '8px 20px',
    'fontSize': '12px',
    'fontWeight': '600',
    'color': '#2E75B6',
    'borderBottom': '2px solid #2E75B6',
    'cursor': 'pointer',
}

# ── 4. LAYOUT ──────────────────────────────────────────────────

app.layout = html.Div([

    # Header
    html.Div([
        html.Div([
            html.Span("FUND", style={
                'color': '#2E75B6', 'fontWeight': '800',
                'fontSize': '18px', 'letterSpacing': '0.1em',
            }),
            html.Span(" DASHBOARD", style={
                'color': '#1a3a5c', 'fontWeight': '300',
                'fontSize': '18px', 'letterSpacing': '0.1em',
            }),
        ]),
        html.Span(
            id='data-date-label',
            style={'fontSize': '11px', 'color': '#999', 'alignSelf': 'center'}
        ),
    ], style={
        'display': 'flex', 'justifyContent': 'space-between',
        'alignItems': 'center', 'padding': '12px 20px',
        'backgroundColor': '#fff', 'borderBottom': '2px solid #2E75B6',
        'marginBottom': '0',
    }),

    # Tabs
    dcc.Tabs(
        id='main-tabs',
        value='tab-holdings',
        children=[
            dcc.Tab(label='My Holdings',     value='tab-holdings',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            dcc.Tab(label='Market Overview', value='tab-market',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            dcc.Tab(label='Portfolio',       value='tab-portfolio',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            dcc.Tab(label='P&L',             value='tab-pnl',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            dcc.Tab(label='Summary',         value='tab-summary',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
        ],
        style={'backgroundColor': '#fff', 'borderBottom': '1px solid #eee', 'marginBottom': '0'}
    ),

    # ── HOLDINGS TAB
    html.Div([
        html.Div([
            html.Div([
                html.P("MY HOLDINGS", style={**SECTION_TITLE, 'marginBottom': '0'}),
                html.Div([
                    html.Span("Click rows to toggle chart  •  ", style={
                        'fontSize': '11px', 'color': '#aaa', 'alignSelf': 'center',
                    }),
                    html.Label("Since:", style={
                        'fontSize': '11px', 'color': '#666',
                        'marginRight': '6px', 'alignSelf': 'center',
                    }),
                    dcc.DatePickerSingle(
                        id='holdings-since-date',
                        date=DEFAULT_DATE,
                        min_date_allowed=min_date,
                        max_date_allowed=max_date,
                        display_format='DD MMM YYYY',
                    ),
                ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px'}),
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}),
        ], style=CARD),

        # FIX: flex row with minWidth:0 on table side so it shrinks properly
        html.Div([
            html.Div([
                html.Div(id='holdings-table-div'),
            ], style={'flex': '1', 'minWidth': '0', 'overflow': 'hidden'}),

            html.Div([
                html.Div([
                    html.P("RELATIVE RETURNS", style={**SECTION_TITLE, 'marginBottom': '4px'}),
                    html.Span(id='holdings-chart-info', style={'fontSize': '11px', 'color': '#aaa'}),
                ], style={'marginBottom': '8px'}),
                dcc.Graph(id='holdings-relative-chart', config={'displayModeBar': False}),
            ], style={
                'flexShrink': '0', 'width': '320px',
                'backgroundColor': '#fff',
                'borderRadius': '8px', 'padding': '14px 18px',
                'boxShadow': '0 1px 4px rgba(0,0,0,0.08)',
                'marginBottom': '12px', 'marginLeft': '12px',
            }),
        ], style={'display': 'flex', 'alignItems': 'flex-start', 'width': '100%', 'minWidth': '0'}),

        dcc.Store(id='holdings-selected-funds', data=top4_holdings_default),

    ], id='holdings-tab-content', style={
        'display': 'block', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto', 'overflowX': 'hidden',
    }),

    # ── MARKET TAB
    html.Div([
        html.Div([
            html.Div([
                html.P("MARKET OVERVIEW", style={**SECTION_TITLE, 'marginBottom': '0'}),
                html.Div([
                    html.Span("Click rows to toggle chart  •  ", style={
                        'fontSize': '11px', 'color': '#aaa', 'alignSelf': 'center',
                    }),
                    html.Label("Since:", style={
                        'fontSize': '11px', 'color': '#666',
                        'marginRight': '6px', 'alignSelf': 'center',
                    }),
                    dcc.DatePickerSingle(
                        id='market-since-date',
                        date=DEFAULT_DATE,
                        min_date_allowed=min_date,
                        max_date_allowed=max_date,
                        display_format='DD MMM YYYY',
                    ),
                ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px'}),
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}),
        ], style=CARD),

        # FIX: flex row with minWidth:0 on table side so it shrinks properly
        html.Div([
            html.Div([
                html.Div(id='market-table-div'),
            ], style={'flex': '1', 'minWidth': '0', 'overflow': 'hidden'}),

            html.Div([
                html.Div([
                    html.P("RELATIVE RETURNS", style={**SECTION_TITLE, 'marginBottom': '4px'}),
                    html.Span(id='market-chart-info', style={'fontSize': '11px', 'color': '#aaa'}),
                ], style={'marginBottom': '8px'}),
                dcc.Graph(id='relative-chart', config={'displayModeBar': False}),
            ], style={
                'flexShrink': '0', 'width': '320px',
                'backgroundColor': '#fff',
                'borderRadius': '8px', 'padding': '14px 18px',
                'boxShadow': '0 1px 4px rgba(0,0,0,0.08)',
                'marginBottom': '12px', 'marginLeft': '12px',
            }),
        ], style={'display': 'flex', 'alignItems': 'flex-start', 'width': '100%', 'minWidth': '0'}),

        dcc.Store(id='market-selected-funds', data=top4_default),

    ], id='market-tab-content', style={
        'display': 'none', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto', 'overflowX': 'hidden',
    }),

    # ── PORTFOLIO TAB
    html.Div([
        # Header card
        html.Div([
            html.Div([
                html.P("PORTFOLIO", style={**SECTION_TITLE, 'marginBottom': '0'}),
                html.Span(id='portfolio-total-label', style={
                    'fontSize': '20px', 'fontWeight': '700',
                    'color': '#1a3a5c', 'letterSpacing': '0.02em',
                }),
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}),
            html.Div([
                html.Label("Compare with:", style={
                    'fontSize': '11px', 'color': '#666',
                    'marginRight': '8px', 'alignSelf': 'center',
                }),
                dcc.Dropdown(
                    id='snapshot-select',
                    options=get_snapshot_options(),
                    value=get_latest_snapshot_value(),
                    clearable=False,
                    style={'fontSize': '12px', 'width': '160px'},
                ),
            ], style={'display': 'flex', 'alignItems': 'center', 'marginTop': '10px'}),
        ], style=CARD),

        # Side-by-side on desktop, stacked on mobile via CSS
        html.Div([
            html.Div(id='portfolio-table-div', style={
                'flex': '1', 'minWidth': '0', 'overflowX': 'auto',
            }),
            html.Div(id='portfolio-category-div', className='portfolio-cat-panel', style={
                'flexShrink': '0', 'width': '360px', 'marginLeft': '12px',
            }),
        ], style={
            'display': 'flex', 'alignItems': 'flex-start',
            'width': '100%', 'flexWrap': 'wrap',
        }),

        # Add / Edit section
        html.Div([
            html.P("ADD / UPDATE HOLDING", style=SECTION_TITLE),
            html.Div([
                html.Div([
                    html.Label("Fund:", style={
                        'fontSize': '11px', 'color': '#666',
                        'marginBottom': '4px', 'display': 'block',
                    }),
                    dcc.Dropdown(
                        id='portfolio-fund-select',
                        options=portfolio_options,
                        placeholder='Select fund...',
                        style={'fontSize': '12px'},
                    ),
                ], style={'flex': '3', 'marginRight': '12px'}),
                html.Div([
                    html.Label("Units:", style={
                        'fontSize': '11px', 'color': '#666',
                        'marginBottom': '4px', 'display': 'block',
                    }),
                    dcc.Input(
                        id='portfolio-units-input',
                        type='number',
                        placeholder='e.g. 1250.5',
                        step=0.0001,
                        style={
                            'padding': '7px', 'fontSize': '12px',
                            'border': '1px solid #ccc', 'borderRadius': '4px',
                            'width': '140px',
                        },
                    ),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label(" ", style={'fontSize': '11px', 'display': 'block', 'marginBottom': '4px'}),
                    html.Button("Save", id='portfolio-save-btn', n_clicks=0, style={
                        'backgroundColor': '#1a7a1a', 'color': 'white',
                        'border': 'none', 'borderRadius': '4px',
                        'padding': '7px 16px', 'fontSize': '12px',
                        'cursor': 'pointer', 'marginRight': '8px',
                    }),
                    html.Button("Remove", id='portfolio-remove-btn', n_clicks=0, style={
                        'backgroundColor': '#c0392b', 'color': 'white',
                        'border': 'none', 'borderRadius': '4px',
                        'padding': '7px 16px', 'fontSize': '12px', 'cursor': 'pointer',
                    }),
                ]),
            ], style={'display': 'flex', 'alignItems': 'flex-end'}),
            html.Div(id='portfolio-status', style={
                'fontSize': '12px', 'color': '#2E75B6',
                'marginTop': '8px', 'fontWeight': '600',
            }),
        ], style=CARD),

        # CASH ACCOUNTS section
        html.Div([
            html.P("CASH ACCOUNTS", style=SECTION_TITLE),
            html.Div(id='cash-accounts-table-div'),
            html.Div([
                html.Div([
                    html.Label("Account:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='cash-name-input', type='text', placeholder='e.g. Barclays',
                              style={'padding': '7px', 'fontSize': '12px', 'border': '1px solid #ccc',
                                     'borderRadius': '4px', 'width': '130px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label("Currency:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='cash-currency-select',
                                 options=[
                                     {'label': 'GBP', 'value': 'GBP'},
                                     {'label': 'USD', 'value': 'USD'},
                                     {'label': 'TRY', 'value': 'TRY'},
                                 ],
                                 value='GBP', clearable=False,
                                 style={'fontSize': '12px', 'width': '90px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label("Amount:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='cash-amount-input', type='number', placeholder='e.g. 45000',
                              step=0.01,
                              style={'padding': '7px', 'fontSize': '12px', 'border': '1px solid #ccc',
                                     'borderRadius': '4px', 'width': '130px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label(" ", style={'fontSize': '11px', 'display': 'block', 'marginBottom': '4px'}),
                    html.Button("Add", id='cash-add-btn', n_clicks=0, style={
                        'backgroundColor': '#1a7a1a', 'color': 'white', 'border': 'none',
                        'borderRadius': '4px', 'padding': '7px 16px', 'fontSize': '12px', 'cursor': 'pointer',
                    }),
                ]),
            ], style={'display': 'flex', 'alignItems': 'flex-end', 'marginTop': '12px', 'flexWrap': 'wrap', 'gap': '4px'}),
            html.Div(id='cash-status', style={'fontSize': '12px', 'color': '#2E75B6', 'marginTop': '8px', 'fontWeight': '600'}),
        ], style=CARD),

        # ADD TRANSACTION section
        html.Div([
            html.P("ADD TRANSACTION", style=SECTION_TITLE),
            html.Div([
                html.Div([
                    html.Label("Fund:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='txn-fund-select', options=portfolio_options,
                                 placeholder='Select fund...', style={'fontSize': '12px'}),
                ], style={'flex': '3', 'marginRight': '12px'}),
                html.Div([
                    html.Label("Account:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='txn-account-input', type='text', placeholder='e.g. AB ISA',
                              style={'padding': '7px', 'fontSize': '12px', 'border': '1px solid #ccc',
                                     'borderRadius': '4px', 'width': '120px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label("Date:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.DatePickerSingle(id='txn-date-input', date=datetime.today().date(),
                                         display_format='DD MMM YYYY'),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label("Type:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='txn-type-select', options=[
                        {'label': 'BUY',      'value': 'BUY'},
                        {'label': 'SELL',     'value': 'SELL'},
                        {'label': 'DIVIDEND', 'value': 'DIVIDEND'},
                    ], value='BUY', clearable=False, style={'fontSize': '12px', 'width': '110px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label("Quantity:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='txn-qty-input', type='number', placeholder='e.g. 100',
                              step=0.0001, style={'padding': '7px', 'fontSize': '12px',
                              'border': '1px solid #ccc', 'borderRadius': '4px', 'width': '100px'}),
                ], style={'marginRight': '12px'}),
                html.Div(id='txn-price-div', children=[
                    html.Label("Price:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='txn-price-input', type='number', placeholder='e.g. 248.3',
                              step=0.0001, style={'padding': '7px', 'fontSize': '12px',
                              'border': '1px solid #ccc', 'borderRadius': '4px', 'width': '100px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label("FX Rate:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='txn-fx-input', type='number', placeholder='1.0', value=1.0,
                              step=0.0001, style={'padding': '7px', 'fontSize': '12px',
                              'border': '1px solid #ccc', 'borderRadius': '4px', 'width': '80px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label(" ", style={'fontSize': '11px', 'display': 'block', 'marginBottom': '4px'}),
                    html.Button("Add", id='txn-add-btn', n_clicks=0, style={
                        'backgroundColor': '#1a7a1a', 'color': 'white', 'border': 'none',
                        'borderRadius': '4px', 'padding': '7px 16px', 'fontSize': '12px', 'cursor': 'pointer',
                    }),
                ]),
            ], style={'display': 'flex', 'alignItems': 'flex-end', 'flexWrap': 'wrap', 'gap': '4px'}),
            html.Div(id='txn-status', style={'fontSize': '12px', 'color': '#2E75B6', 'marginTop': '8px', 'fontWeight': '600'}),
        ], style=CARD),

    ], id='portfolio-tab-content', style={
        'display': 'none', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto', 'overflowX': 'hidden',
    }),

    # ── P&L TAB
    html.Div([
        # Header
        html.Div([
            html.Div([
                html.P("P&L SUMMARY", style={**SECTION_TITLE, 'marginBottom': '0'}),
                html.Div([
                    html.Span(id='pnl-total-label', style={
                        'fontSize': '20px', 'fontWeight': '700', 'color': '#1a3a5c',
                    }),
                ]),
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}),
        ], style=CARD),

        # Toggle button
        html.Div([
            html.Button(
                "Show Closed Positions",
                id='pnl-toggle-btn',
                n_clicks=0,
                style={
                    'backgroundColor': '#1a3a5c', 'color': 'white',
                    'border': 'none', 'borderRadius': '4px',
                    'padding': '6px 14px', 'fontSize': '11px',
                    'cursor': 'pointer', 'marginBottom': '8px',
                }
            ),
        ]),
        dcc.Store(id='pnl-show-closed', data=False),

        # FIX: P&L table wrapped in horizontally scrollable container
        html.Div(id='pnl-table-div', style={'overflowX': 'auto', 'width': '100%'}),

    ], id='pnl-tab-content', style={
        'display': 'none', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto', 'overflowX': 'hidden',
    }),

    # ── SUMMARY TAB
    html.Div([
        html.Div([
            html.Label("Compare with:", style={
                'fontSize': '11px', 'color': '#666',
                'marginRight': '8px', 'alignSelf': 'center',
            }),
            dcc.Dropdown(
                id='summary-snapshot-select',
                options=get_snapshot_options(),
                value=get_latest_snapshot_value(),
                clearable=False,
                style={'fontSize': '12px', 'width': '160px'},
            ),
        ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '12px'}),

        html.Div(id='summary-table-div'),

    ], id='summary-tab-content', style={
        'display': 'none', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto', 'overflowX': 'hidden',
    }),

    # Shared stores
    dcc.Store(id='sort-state-holdings', data={'col': 'YTD', 'asc': False}),
    dcc.Store(id='sort-state-market',   data={'col': 'YTD', 'asc': False}),
    dcc.Store(id='db-reload-trigger',   data=0),
    dcc.Store(id='portfolio-reload',    data=0),

    # Auto-refresh every 60 minutes
    dcc.Interval(id='auto-refresh', interval=60*60*1000, n_intervals=0),

], style={
    'fontFamily': '"DM Sans", -apple-system, BlinkMacSystemFont, sans-serif',
    'backgroundColor': '#f0f3f7',
    'minHeight': '100vh',
    'overflowX': 'hidden',   # FIX: prevent root from ever scrolling horizontally
})


# ── 5. TAB VISIBILITY ──────────────────────────────────────────

@app.callback(
    Output('holdings-tab-content',  'style'),
    Output('market-tab-content',    'style'),
    Output('portfolio-tab-content', 'style'),
    Output('pnl-tab-content',       'style'),
    Output('summary-tab-content',   'style'),
    Output('data-date-label',       'children'),
    Input('main-tabs',         'value'),
    Input('db-reload-trigger', 'data'),
    Input('auto-refresh',      'n_intervals'),
)
def switch_tab(tab, reload_trigger, n_intervals):
    global df, df_composite, df_combined, instruments
    if reload_trigger or n_intervals:
        df           = load_data()
        df_composite = build_composite_data(df)
        df_calc      = build_calculated_series(df)
        df_combined  = pd.concat(
            [x for x in [df, df_composite, df_calc] if not x.empty],
            ignore_index=True
        )
        instruments  = load_instruments()

    date_label = f"Data as of {df['date'].max().strftime('%d %b %Y')}"

    base = {
        'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px',
        'margin': '0 auto',
        'overflowX': 'hidden',
    }
    show = {**base, 'display': 'block'}
    hide = {**base, 'display': 'none'}

    if tab == 'tab-holdings':
        return show, hide, hide, hide, hide, date_label
    elif tab == 'tab-market':
        return hide, show, hide, hide, hide, date_label
    elif tab == 'tab-portfolio':
        return hide, hide, show, hide, hide, date_label
    elif tab == 'tab-pnl':
        return hide, hide, hide, show, hide, date_label
    elif tab == 'tab-summary':
        return hide, hide, hide, hide, show, date_label
    return show, hide, hide, hide, hide, date_label


# ── 6. HOLDINGS CALLBACKS ──────────────────────────────────────

@app.callback(
    Output('holdings-selected-funds', 'data'),
    Input({'type': 'holding-row', 'fund_id': ALL}, 'n_clicks'),
    State('holdings-selected-funds', 'data'),
    prevent_initial_call=True,
)
def toggle_holding(n_clicks, selected):
    if not any(n_clicks):
        return selected
    triggered = ctx.triggered_id
    if not triggered:
        return selected
    fid      = triggered['fund_id']
    selected = list(selected or [])
    if fid in selected:
        selected.remove(fid)
    else:
        selected.append(fid)
    return selected


@app.callback(
    Output('holdings-table-div',   'children'),
    Output('sort-state-holdings',  'data'),
    Input('holdings-since-date',   'date'),
    Input({'type': 'sort-header-holdings', 'col': ALL}, 'n_clicks'),
    Input('holdings-selected-funds', 'data'),
    State('sort-state-holdings',   'data'),
)
def update_holdings(since_date, n_clicks, selected_funds, sort_state):
    since_date  = since_date or DEFAULT_DATE
    since_label = pd.Timestamp(since_date).strftime('%d %b %y')

    triggered = ctx.triggered_id
    if triggered and isinstance(triggered, dict) and triggered.get('type') == 'sort-header-holdings':
        clicked_col = triggered['col']
        if sort_state['col'] == clicked_col:
            sort_state['asc'] = not sort_state['asc']
        else:
            sort_state['col'] = clicked_col
            sort_state['asc'] = False

    portfolio     = load_portfolio()
    holding_ids   = [h['fund_id'] for h in portfolio]
    all_names     = {fid: instruments.get(fid, {}).get('name', fid) for fid in holding_ids}

    holdings_df = df_combined[df_combined['fund_id'].isin(holding_ids)].copy()
    if holdings_df.empty:
        return html.P("No holdings found. Add funds in the Portfolio tab.", style={'color': '#999', 'fontSize': '12px'}), sort_state

    table_df = build_returns_table(holdings_df, since_date)
    table_df['Fund'] = table_df['fund_id'].map(lambda fid: all_names.get(fid, fid))

    sort_col = sort_state['col']
    sort_asc = sort_state['asc']
    if sort_col in table_df.columns:
        table_df = table_df.sort_values(sort_col, ascending=sort_asc, na_position='last')

    sections = []
    for cat, group in table_df.groupby('Type', sort=False):
        sections.append(html.Div([
            html.P(cat.upper(), style={
                **SECTION_TITLE, 'borderBottom': '1px solid #e0e0e0', 'paddingBottom': '4px',
            }),
            # FIX: each section table scrolls horizontally within its card
            html.Div(
                render_returns_table(
                    group, since_label, sort_state,
                    header_type='holdings', selected_funds=selected_funds, clickable=True,
                ),
                style={'overflowX': 'auto'}
            ),
        ], style=CARD))

    return html.Div(sections), sort_state


@app.callback(
    Output('holdings-relative-chart', 'figure'),
    Output('holdings-chart-info',     'children'),
    Input('holdings-selected-funds',  'data'),
    Input('holdings-since-date',      'date'),
)
def update_holdings_chart(selected_funds, since_date):
    selected_funds = selected_funds or []
    since_date     = since_date or DEFAULT_DATE
    count          = len(selected_funds)
    info           = f"{count} fund{'s' if count != 1 else ''} selected" if count else "No funds selected"
    return build_relative_chart(df_combined, selected_funds, since_date), info


# ── 7. MARKET CALLBACKS ────────────────────────────────────────

@app.callback(
    Output('market-selected-funds', 'data'),
    Input({'type': 'market-row', 'fund_id': ALL}, 'n_clicks'),
    State('market-selected-funds', 'data'),
    prevent_initial_call=True,
)
def toggle_market(n_clicks, selected):
    if not any(n_clicks):
        return selected
    triggered = ctx.triggered_id
    if not triggered:
        return selected
    fid      = triggered['fund_id']
    selected = list(selected or [])
    if fid in selected:
        selected.remove(fid)
    else:
        selected.append(fid)
    return selected


@app.callback(
    Output('market-table-div',   'children'),
    Output('sort-state-market',  'data'),
    Input('market-since-date',   'date'),
    Input({'type': 'sort-header-market', 'col': ALL}, 'n_clicks'),
    Input('market-selected-funds', 'data'),
    State('sort-state-market',   'data'),
)
def update_market_table(since_date, n_clicks, selected_funds, sort_state):
    since_date = since_date or DEFAULT_DATE

    triggered = ctx.triggered_id
    if triggered and isinstance(triggered, dict) and triggered.get('type') == 'sort-header-market':
        clicked_col = triggered['col']
        if sort_state['col'] == clicked_col:
            sort_state['asc'] = not sort_state['asc']
        else:
            sort_state['col'] = clicked_col
            sort_state['asc'] = False

    table_df = build_returns_table(df_combined, since_date)
    sort_col  = sort_state['col']
    sort_asc  = sort_state['asc']
    if sort_col in table_df.columns:
        table_df = table_df.sort_values(sort_col, ascending=sort_asc, na_position='last')

    since_label = pd.Timestamp(since_date).strftime('%d %b %y')

    # FIX: wrap market table in scrollable div
    return html.Div(
        render_returns_table(
            table_df, since_label, sort_state,
            header_type='market', selected_funds=selected_funds, clickable=True,
        ),
        style={'overflowX': 'auto'}
    ), sort_state


@app.callback(
    Output('relative-chart',    'figure'),
    Output('market-chart-info', 'children'),
    Input('market-selected-funds', 'data'),
    Input('market-since-date',     'date'),
)
def update_market_chart(selected_funds, since_date):
    selected_funds = selected_funds or []
    since_date     = since_date or DEFAULT_DATE
    count          = len(selected_funds)
    info           = f"{count} fund{'s' if count != 1 else ''} selected" if count else "No funds selected"
    return build_relative_chart(df_combined, selected_funds, since_date), info


# ── 8. PORTFOLIO CALLBACKS ─────────────────────────────────────

@app.callback(
    Output('portfolio-table-div',    'children'),
    Output('portfolio-total-label',  'children'),
    Output('portfolio-category-div', 'children'),
    Input('portfolio-reload',        'data'),
    Input('main-tabs',               'value'),
    Input('snapshot-select',         'value'),
)
def update_portfolio(reload, tab, snapshot_date):
    portfolio      = load_portfolio()
    cash_accounts  = load_cash_accounts()
    gbpusd         = get_gbpusd(df)
    fx_rates       = get_fx_rates(df)

    # Filter out any legacy CASH: entries — replaced by cash_accounts
    portfolio = [p for p in portfolio if not p['fund_id'].startswith('CASH:')]

    # Load snapshot for comparison
    snap_holdings   = {}
    snap_label      = None
    snap_cash_total = None
    if snapshot_date and snapshot_date != 'none':
        snap_conn = sqlite3.connect(DB_PATH)
        snap_row  = snap_conn.execute(
            "SELECT id FROM portfolio_snapshots WHERE snap_date = ?", (snapshot_date,)
        ).fetchone()
        if snap_row:
            snap_id    = snap_row[0]
            snap_label = pd.Timestamp(snapshot_date).strftime('%d %b %Y')
            h_rows = snap_conn.execute(
                "SELECT fund_id, value_gbp FROM snapshot_holdings WHERE snapshot_id = ?",
                (snap_id,)
            ).fetchall()
            snap_holdings = {r[0]: r[1] for r in h_rows}
            cash_row = snap_conn.execute(
                "SELECT SUM(value_gbp) FROM snapshot_cash WHERE snapshot_id = ?",
                (snap_id,)
            ).fetchone()
            snap_cash_total = cash_row[0] if cash_row and cash_row[0] else None
        snap_conn.close()

    if not portfolio:
        return html.P(
            "No holdings yet. Add a fund below.",
            style={'color': '#999', 'fontSize': '12px', 'padding': '12px'}
        ), "£0.00", html.Div()

    snap_cols = ([f'{snap_label}', 'Chg', 'Chg %'] if snap_label else [])
    all_cols  = ['Fund', 'Category', 'CCY', 'Units', 'Price', 'Value', '%'] + snap_cols

    def th_style(i):
        base = {
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '6px 8px', 'fontSize': '11px', 'fontWeight': '600',
            'whiteSpace': 'nowrap', 'width': '1%',
        }
        if i == 0:
            return {**base, 'textAlign': 'left'}
        else:
            return {**base, 'textAlign': 'right'}

    header = html.Tr([
        html.Th(c, style=th_style(i)) for i, c in enumerate(all_cols)
    ])

    rows_data = []
    for item in portfolio:
        fid   = item['fund_id']
        units = item.get('units', 0)
        inst  = instruments.get(fid, {})
        name  = inst.get('name', fid)
        atype = inst.get('asset_type', '—')
        cat   = inst.get('category', '—')
        curr  = inst.get('currency', '?')
        punit = inst.get('price_unit', '?')

        if fid.startswith('CASH:') or fid.startswith('ASSET:'):
            price = 1.0
            effective_unit = punit
            if fid == 'CASH:TRY':
                effective_unit = 'point'
            gbp   = to_gbp(price, effective_unit, curr, gbpusd, fx_rates)
            value = gbp * units if gbp is not None else None

        elif fid.startswith('COMPOSITE:'):
            comp_def = next((c for c in getattr(config, 'COMPOSITE_FUNDS', []) if c['fund_id'] == fid), None)
            if comp_def:
                weighted_gbp = 0.0
                for c in comp_def['components']:
                    c_price = get_latest_price(df_combined, c['fund_id'])
                    c_inst  = instruments.get(c['fund_id'], {})
                    c_gbp   = to_gbp(c_price, c_inst.get('price_unit','pence'), c_inst.get('currency','GBP'), gbpusd, fx_rates)
                    if c_gbp is not None:
                        weighted_gbp += c_gbp * c['weight']
                price = weighted_gbp
                gbp   = weighted_gbp if weighted_gbp > 0 else None
                value = gbp * units if gbp is not None else None
            else:
                price = None
                gbp   = None
                value = None

        else:
            price = get_latest_price(df_combined, fid)
            effective_unit = punit
            gbp   = to_gbp(price, effective_unit, curr, gbpusd, fx_rates) if price else None
            value = gbp * units if gbp is not None else None

        rows_data.append({
            'fund_id': fid, 'name': name, 'type': atype, 'category': cat,
            'currency': curr, 'units': units,
            'price': price, 'gbp_price': gbp, 'value': value,
        })

    # Add aggregated cash row from portfolio.json cash key
    if cash_accounts:
        cash_total_gbp = calc_cash_total_gbp(cash_accounts, fx_rates)
        rows_data.append({
            'fund_id': 'CASH:TOTAL',
            'name': 'Cash',
            'type': 'Cash',
            'category': 'Cash',
            'currency': 'GBP',
            'units': cash_total_gbp,
            'price': None,
            'gbp_price': 1.0,
            'value': cash_total_gbp,
        })
        # Inject snap cash total so comparison works
        if snap_cash_total is not None:
            snap_holdings['CASH:TOTAL'] = snap_cash_total

    # Add sold positions — in snapshot but not in current portfolio
    if snap_holdings:
        current_ids = {r['fund_id'] for r in rows_data}
        for fid, snap_val in snap_holdings.items():
            if fid not in current_ids and fid != 'CASH:TOTAL':
                inst = instruments.get(fid, {})
                name = inst.get('name', fid)
                rows_data.append({
                    'fund_id': fid, 'name': name, 'type': inst.get('asset_type', '—'),
                    'category': inst.get('category', '—'), 'currency': inst.get('currency', '?'),
                    'units': 0, 'price': None, 'gbp_price': None, 'value': 0,
                })

    total = sum(r['value'] for r in rows_data if r['value'] is not None)

    rows = []
    for r in sorted(rows_data, key=lambda x: x['value'] or 0, reverse=True):
        pct   = (r['value'] / total * 100) if total and r['value'] else None
        name  = r['name']
        ndisp = name if len(name) <= 35 else name[:35] + '…'

        units = r['units']
        if r['fund_id'].startswith(('CASH:', 'ASSET:')):
            units_str = f"{units:,.0f}"
        elif units == int(units):
            units_str = f"{int(units):,}"
        else:
            units_str = f"{units:,.4f}".rstrip('0').rstrip('.')

        price = r['price']
        fid   = r['fund_id']
        punit = instruments.get(fid, {}).get('price_unit', '')
        curr  = instruments.get(fid, {}).get('currency', '')
        if r['fund_id'] == 'CASH:TOTAL':
            price_str = 'Mixed'
            units_str = f"{r['value']:,.0f}"
        elif r['fund_id'].startswith(('CASH:', 'ASSET:')):
            price_str = 'Fixed'
        elif price is None:
            price_str = 'N/A'
        elif r['fund_id'].startswith('COMPOSITE:'):
            price_str = f"{price:.2f}"
        elif punit == 'pence' and curr == 'GBP':
            price_str = f"{price / 100:.1f}"
        else:
            price_str = f"{price:.1f}"

        rows.append(html.Tr([
            html.Td(html.Span(ndisp, title=name), style={
                'padding': '5px 8px', 'fontSize': '12px',
                'color': '#1a3a5c', 'whiteSpace': 'nowrap',
                'width': '1%',
            }),
            html.Td(r['category'], style={
                'padding': '5px 8px', 'fontSize': '10px',
                'textAlign': 'left', 'color': '#444', 'fontWeight': '500',
                'whiteSpace': 'nowrap', 'width': '1%',
            }),
            html.Td(r['currency'], style={
                'padding': '5px 8px', 'fontSize': '11px',
                'textAlign': 'right', 'color': '#666', 'width': '1%',
                'whiteSpace': 'nowrap',
            }),
            html.Td(units_str, style={
                'padding': '5px 8px', 'fontSize': '11px',
                'textAlign': 'right', 'fontFamily': 'monospace', 'width': '1%',
                'whiteSpace': 'nowrap',
            }),
            html.Td(price_str, style={
                'padding': '5px 8px', 'fontSize': '11px',
                'textAlign': 'right', 'fontFamily': 'monospace',
                'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap',
            }),
            html.Td(
                f"{r['value']:,.0f}" if r['value'] else 'N/A',
                style={
                    'padding': '5px 8px', 'fontSize': '11px',
                    'textAlign': 'right', 'fontFamily': 'monospace',
                    'fontWeight': '600', 'color': '#1a3a5c',
                    'width': '1%', 'whiteSpace': 'nowrap',
                }
            ),
            html.Td(
                f"{pct:.1f}%" if pct else 'N/A',
                style={
                    'padding': '5px 8px', 'fontSize': '11px',
                    'textAlign': 'right', 'fontFamily': 'monospace',
                    'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap',
                }
            ),
        ] + (
            [
                html.Td(
                    f"{snap_holdings.get(fid, 0):,.0f}" if snap_holdings.get(fid) else 'NEW',
                    style={'padding': '5px 8px', 'fontSize': '11px', 'textAlign': 'right',
                           'fontFamily': 'monospace', 'color': '#555',
                           'width': '1%', 'whiteSpace': 'nowrap'}
                ),
                html.Td(
                    # New position: no snap value
                    f"{(r['value'] or 0):+,.0f}" if not snap_holdings.get(fid)
                    # Existing or sold: show difference (value may be 0 for sold)
                    else f"{((r['value'] or 0) - snap_holdings[fid]):+,.0f}",
                    style={
                        'padding': '5px 8px', 'fontSize': '11px', 'textAlign': 'right',
                        'fontFamily': 'monospace', 'fontWeight': '600',
                        'color': '#1a7a1a' if (r['value'] or 0) >= snap_holdings.get(fid, 0) else '#c0392b',
                        'width': '1%', 'whiteSpace': 'nowrap',
                    }
                ),
                html.Td(
                    'NEW' if not snap_holdings.get(fid)
                    else ('SOLD' if not r['value']
                          else f"{((r['value'] / snap_holdings[fid] - 1) * 100):+.1f}%"
                               if snap_holdings[fid] > 0 else '—'),
                    style={
                        'padding': '5px 8px', 'fontSize': '11px', 'textAlign': 'right',
                        'fontFamily': 'monospace', 'fontWeight': '600',
                        'color': '#1a7a1a' if (r['value'] or 0) >= snap_holdings.get(fid, 0) else '#c0392b',
                        'width': '1%', 'whiteSpace': 'nowrap',
                    }
                ),
            ] if snap_label else []
        ), style={'borderBottom': '1px solid #f0f3f7'}))

    # Total row
    snap_total   = sum(snap_holdings.values()) if snap_holdings else 0
    snap_change  = total - snap_total if snap_total else None
    snap_chg_pct = (snap_change / snap_total * 100) if snap_total else None
    chg_color    = '#1a7a1a' if (snap_change or 0) >= 0 else '#c0392b'

    rows.append(html.Tr([
        html.Td("TOTAL", colSpan=5, style={
            'padding': '8px 8px', 'fontSize': '12px',
            'fontWeight': '700', 'color': '#1a3a5c',
            'borderTop': '2px solid #1a3a5c',
        }),
        html.Td(f"{total:,.0f}", style={
            'padding': '8px 8px', 'fontSize': '12px',
            'textAlign': 'right', 'fontFamily': 'monospace',
            'fontWeight': '700', 'color': '#1a3a5c',
            'borderTop': '2px solid #1a3a5c',
        }),
        html.Td("100%", style={
            'padding': '8px 8px', 'fontSize': '11px',
            'textAlign': 'center', 'color': '#666',
            'borderTop': '2px solid #1a3a5c',
        }),
    ] + ([
        html.Td(f"{snap_total:,.0f}", style={
            'padding': '8px 8px', 'fontSize': '11px', 'textAlign': 'right',
            'fontFamily': 'monospace', 'fontWeight': '700', 'color': '#555',
            'borderTop': '2px solid #1a3a5c',
        }),
        html.Td(f"{snap_change:+,.0f}" if snap_change is not None else '—', style={
            'padding': '8px 8px', 'fontSize': '11px', 'textAlign': 'right',
            'fontFamily': 'monospace', 'fontWeight': '700', 'color': chg_color,
            'borderTop': '2px solid #1a3a5c',
        }),
        html.Td(f"{snap_chg_pct:+.1f}%" if snap_chg_pct is not None else '—', style={
            'padding': '8px 8px', 'fontSize': '11px', 'textAlign': 'right',
            'fontFamily': 'monospace', 'fontWeight': '700', 'color': chg_color,
            'borderTop': '2px solid #1a3a5c',
        }),
    ] if snap_label else [])))

    # FIX: table wrapped in scrollable div so it doesn't blow out the layout
    table = html.Div(
        html.Table(
            [html.Thead(header), html.Tbody(rows)],
            style={'width': '100%', 'borderCollapse': 'collapse', 'tableLayout': 'auto'}
        ),
        style={**CARD, 'overflowX': 'auto', 'padding': '0'}
    )

    # ── Category breakdown table
    from collections import defaultdict
    cat_totals = defaultdict(float)
    for r in rows_data:
        if r['value']:
            cat_totals[r['category']] += r['value']

    # Load category snapshot from database
    snap_cat = {}
    if snap_label:
        try:
            _sc = sqlite3.connect(DB_PATH)
            _sr = _sc.execute(
                "SELECT id FROM portfolio_snapshots WHERE snap_date = ?", (snapshot_date,)
            ).fetchone()
            if _sr:
                cat_rows = _sc.execute(
                    "SELECT category, value_gbp FROM snapshot_categories WHERE snapshot_id = ?",
                    (_sr[0],)
                ).fetchall()
                snap_cat = {r[0]: r[1] for r in cat_rows}
            _sc.close()
        except Exception:
            snap_cat = {}
    cat_cols  = ['Category', 'Value £k', '%'] + ([snap_label, 'Chg'] if snap_label else [])

    def cat_th_style(i):
        base = {
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '5px 6px', 'fontSize': '10px', 'fontWeight': '600',
            'whiteSpace': 'nowrap',
        }
        return {**base, 'textAlign': 'left' if i == 0 else 'right', 'width': '1%' if i > 0 else 'auto'}

    cat_header = html.Tr([
        html.Th(c, style=cat_th_style(i)) for i, c in enumerate(cat_cols)
    ])

    cat_rows = []
    for cat, val in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True):
        pct = val / total * 100 if total else 0
        snap_cat_val = snap_cat.get(cat, 0) if snap_cat else 0
        cat_chg      = val - snap_cat_val if snap_cat_val else None
        cat_chg_color= '#1a7a1a' if (cat_chg or 0) >= 0 else '#c0392b'
        cat_rows.append(html.Tr([
            html.Td(cat, style={
                'padding': '4px 6px', 'fontSize': '11px',
                'color': '#1a3a5c', 'fontWeight': '500', 'whiteSpace': 'nowrap',
            }),
            html.Td(f"{val/1000:.1f}", style={
                'padding': '4px 6px', 'fontSize': '11px',
                'textAlign': 'right', 'fontFamily': 'monospace',
                'fontWeight': '600', 'width': '1%', 'whiteSpace': 'nowrap',
            }),
            html.Td(f"{pct:.1f}%", style={
                'padding': '4px 6px', 'fontSize': '11px',
                'textAlign': 'right', 'fontFamily': 'monospace',
                'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap',
            }),
        ] + ([
            html.Td(f"{snap_cat_val/1000:.1f}" if snap_cat_val else '—', style={
                'padding': '4px 6px', 'fontSize': '11px',
                'textAlign': 'right', 'fontFamily': 'monospace',
                'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap',
            }),
            html.Td(f"{cat_chg/1000:+.1f}" if cat_chg is not None else '—', style={
                'padding': '4px 6px', 'fontSize': '11px',
                'textAlign': 'right', 'fontFamily': 'monospace',
                'fontWeight': '600', 'color': cat_chg_color,
                'width': '1%', 'whiteSpace': 'nowrap',
            }),
        ] if snap_label else []), style={'borderBottom': '1px solid #f0f3f7'}))

    snap_cat_total = sum(snap_cat.values()) if snap_cat else 0
    cat_chg_total  = total - snap_cat_total if snap_cat_total else None
    cat_chg_color  = '#1a7a1a' if (cat_chg_total or 0) >= 0 else '#c0392b'
    cat_rows.append(html.Tr([
        html.Td("TOTAL", style={
            'padding': '6px 6px', 'fontSize': '11px',
            'fontWeight': '700', 'color': '#1a3a5c',
            'borderTop': '2px solid #1a3a5c',
        }),
        html.Td(f"{total/1000:.1f}", style={
            'padding': '6px 6px', 'fontSize': '11px',
            'textAlign': 'right', 'fontFamily': 'monospace',
            'fontWeight': '700', 'color': '#1a3a5c',
            'borderTop': '2px solid #1a3a5c', 'width': '1%', 'whiteSpace': 'nowrap',
        }),
        html.Td("100%", style={
            'padding': '6px 6px', 'fontSize': '11px',
            'textAlign': 'right', 'color': '#666',
            'borderTop': '2px solid #1a3a5c', 'width': '1%', 'whiteSpace': 'nowrap',
        }),
    ] + ([
        html.Td(f"{snap_cat_total/1000:.1f}" if snap_cat_total else '—', style={
            'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right',
            'fontFamily': 'monospace', 'fontWeight': '700', 'color': '#555',
            'borderTop': '2px solid #1a3a5c', 'width': '1%', 'whiteSpace': 'nowrap',
        }),
        html.Td(f"{cat_chg_total/1000:+.1f}" if cat_chg_total is not None else '—', style={
            'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right',
            'fontFamily': 'monospace', 'fontWeight': '700', 'color': cat_chg_color,
            'borderTop': '2px solid #1a3a5c', 'width': '1%', 'whiteSpace': 'nowrap',
        }),
    ] if snap_label else [])))

    cat_table = html.Div([
        html.P("BY CATEGORY  (£k)", style={**SECTION_TITLE, 'borderBottom': '1px solid #e0e0e0', 'paddingBottom': '4px'}),
        html.Table(
            [html.Thead(cat_header), html.Tbody(cat_rows)],
            style={'width': '100%', 'borderCollapse': 'collapse', 'tableLayout': 'auto'}
        ),
    ], style=CARD)

    return table, f"{total:,.0f}", cat_table


@app.callback(
    Output('portfolio-status',  'children'),
    Output('portfolio-reload',  'data'),
    Output('portfolio-units-input', 'value'),
    Input('portfolio-save-btn',   'n_clicks'),
    Input('portfolio-remove-btn', 'n_clicks'),
    State('portfolio-fund-select',  'value'),
    State('portfolio-units-input',  'value'),
    State('portfolio-reload',       'data'),
    prevent_initial_call=True,
)
def update_portfolio_entry(save_clicks, remove_clicks, fund_id, units, reload):
    triggered = ctx.triggered_id

    if not fund_id:
        return 'Please select a fund first.', reload, units

    portfolio = load_portfolio()

    if triggered == 'portfolio-save-btn':
        if units is None or units <= 0:
            return 'Please enter a valid number of units.', reload, units
        from datetime import datetime
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO portfolio_holdings (fund_id, units, updated_at) VALUES (?, ?, ?)",
            (fund_id, float(units), datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        conn.close()
        existing = next((x for x in portfolio if x['fund_id'] == fund_id), None)
        msg = f'✓ Updated {fund_id} to {units} units' if existing else f'✓ Added {fund_id} with {units} units'
        return msg, reload + 1, None

    if triggered == 'portfolio-remove-btn':
        existing = next((x for x in portfolio if x['fund_id'] == fund_id), None)
        if existing:
            delete_holding(fund_id)
            return f'✓ Removed {fund_id}', reload + 1, None
        return 'Fund not found in portfolio.', reload, units

    return '', reload, units


# ── 9. P&L CALLBACKS ──────────────────────────────────────────

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
    elif c == "XAU":
        return p
    elif c == "TRY":
        return p / fx
    return p


def calc_pnl(gbpusd, fx_rates):
    conn = sqlite3.connect(DB_PATH)
    txns = pd.read_sql_query(
        """SELECT t.fund_id, t.account, t.trade_date, t.type,
               t.quantity, t.price, t.currency, t.fx_rate,
               i.name, i.price_unit, i.category
        FROM transactions t
        LEFT JOIN instruments i ON t.fund_id = i.fund_id
        ORDER BY t.fund_id, t.trade_date""", conn)
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
                # Dividend received — convert to GBP and reduce cost base
                div_gbp         = txn_price_to_gbp(qty, r["currency"], r["fx_rate"], "pound")
                total_cost_gbp  = max(total_cost_gbp - div_gbp, 0)
                total_dividends += div_gbp

            elif ttype == "SELL":
                if total_qty > 0:
                    avg_cost = total_cost_gbp / total_qty
                    sell_qty = min(qty, total_qty)
                    realised_pnl   += sell_qty * (cost_per_unit - avg_cost)
                    total_cost_gbp -= sell_qty * avg_cost
                    total_qty      -= sell_qty
                    total_qty       = max(total_qty, 0)

        avg_cost_gbp = total_cost_gbp / total_qty if total_qty > 0 else 0

        if total_qty > 0:
            if fund_id.startswith("COMPOSITE:"):
                comp_def = next((c for c in getattr(config, "COMPOSITE_FUNDS", []) if c["fund_id"] == fund_id), None)
                current_price_gbp = None
                if comp_def:
                    weighted = 0.0
                    for c in comp_def["components"]:
                        cp   = get_latest_price(df_combined, c["fund_id"])
                        ci   = instruments.get(c["fund_id"], {})
                        cgbp = to_gbp(cp, ci.get("price_unit","pence"), ci.get("currency","GBP"), gbpusd, fx_rates)
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


@app.callback(
    Output('pnl-show-closed', 'data'),
    Output('pnl-toggle-btn',  'children'),
    Output('pnl-toggle-btn',  'style'),
    Input('pnl-toggle-btn',   'n_clicks'),
    State('pnl-show-closed',  'data'),
    prevent_initial_call=True,
)
def toggle_closed(n_clicks, show_closed):
    new_state = not show_closed
    label = "Hide Closed Positions" if new_state else "Show Closed Positions"
    style = {
        'backgroundColor': '#c0392b' if new_state else '#1a3a5c',
        'color': 'white', 'border': 'none', 'borderRadius': '4px',
        'padding': '6px 14px', 'fontSize': '11px',
        'cursor': 'pointer', 'marginBottom': '8px',
    }
    return new_state, label, style


@app.callback(
    Output("pnl-table-div",   "children"),
    Output("pnl-total-label", "children"),
    Input("main-tabs",        "value"),
    Input("txn-status",       "children"),
    Input("pnl-show-closed",  "data"),
)
def update_pnl(tab, _, show_closed):
    if tab != "tab-pnl":
        return html.Div(), ""

    gbpusd   = get_gbpusd(df)
    fx_rates = get_fx_rates(df)
    pnl_df   = calc_pnl(gbpusd, fx_rates)

    if pnl_df.empty:
        return html.P("No transactions found.", style={"color": "#999"}), ""

    pnl_df = pnl_df.sort_values("Current Value", ascending=False, na_position="last")

    total_cost    = pnl_df["Cost Basis"].sum()
    total_value   = pnl_df["Current Value"].dropna().sum()
    total_pnl     = pnl_df["PnL"].dropna().sum()
    total_pnl_pct = (total_pnl / (total_cost + pnl_df["Realised"].abs().sum()) * 100) if total_cost else 0
    pnl_color     = "#1a7a1a" if total_pnl >= 0 else "#c0392b"

    total_label = ""

    header = html.Tr([
        html.Th(c, style={
            "backgroundColor": "#1a3a5c", "color": "white",
            "padding": "6px 10px", "fontSize": "11px", "fontWeight": "600",
            "textAlign": "left" if i == 0 else "right", "whiteSpace": "nowrap",
        }) for i, c in enumerate(["Fund", "Category", "Price", "Avg Cost", "Qty", "Value", "Dividends", "P&L", "P&L %", "1D", "1D %", "1W %", "1M %"])
    ])

    open_df   = pnl_df[pnl_df["Qty"] > 0]
    closed_df = pnl_df[pnl_df["Qty"] == 0]

    def get_returns_for_df(df_subset):
        ret_1d, ret_1w, ret_1m = [], [], []
        for fid in df_subset["fund_id"]:
            r1d = calc_return(df_combined, fid, days_back=1)
            r1w = calc_return(df_combined, fid, days_back=5)
            r1m = calc_return(df_combined, fid, days_back=21)
            if r1d is not None: ret_1d.append(r1d)
            if r1w is not None: ret_1w.append(r1w)
            if r1m is not None: ret_1m.append(r1m)
        return (
            (min(ret_1d), max(ret_1d)) if ret_1d else (0, 0),
            (min(ret_1w), max(ret_1w)) if ret_1w else (0, 0),
            (min(ret_1m), max(ret_1m)) if ret_1m else (0, 0),
        )

    range_1d, range_1w, range_1m = get_returns_for_df(pnl_df)

    def fmt_num(value, symbol="", suffix=""):
        if value < 100:
            return f"{symbol}{value:,.2f}{suffix}"
        else:
            return f"{symbol}{value:,.0f}{suffix}"

    def format_native_price(price, fund_id):
        if price is None:
            return "—"
        inst  = instruments.get(fund_id, {})
        punit = inst.get("price_unit", "pound")
        curr  = inst.get("currency", "GBP")
        sym   = {"GBP": "£", "USD": "$", "TRY": "₺"}.get(curr, "")
        if punit == "pence":
            return fmt_num(price, suffix="p")
        elif punit == "point":
            return fmt_num(price)
        elif punit in ("dollar", "pound"):
            return fmt_num(price, symbol=sym)
        return fmt_num(price)

    def make_rows(df_subset, is_closed=False):
        result = []
        for _, r in df_subset.iterrows():
            pnl     = r["PnL"]
            pnl_pct = r["PnL Pct"]
            color   = "#1a7a1a" if pnl and pnl >= 0 else "#c0392b"
            name    = r["Fund"]
            ndisp   = name if len(name) <= 35 else name[:35] + "…"
            fid     = r["fund_id"]

            cp        = get_latest_price(df_combined, fid)
            price_str = format_native_price(cp, fid) if cp else "—"

            inst    = instruments.get(fid, {})
            punit   = inst.get("price_unit", "pound")
            curr    = inst.get("currency", "GBP")
            avg_gbp = r["Avg Cost"]
            if r["Qty"] > 0 and avg_gbp > 0:
                if punit == "pence" and curr == "GBP":
                    avg_native = avg_gbp * 100
                    avg_str    = fmt_num(avg_native, suffix="p")
                elif curr == "USD":
                    avg_native = avg_gbp * (fx_rates.get("USD", 1.26))
                    avg_str    = fmt_num(avg_native, symbol="$")
                elif curr == "TRY":
                    avg_native = avg_gbp * (fx_rates.get("TRY", 43.0))
                    avg_str    = fmt_num(avg_native, symbol="₺")
                else:
                    avg_str    = fmt_num(avg_gbp, symbol="£")
            else:
                avg_str = "—"

            if r["Qty"] > 0:
                q = r["Qty"]
                if q < 100:
                    qty_display = f"{q:,.2f}".rstrip("0").rstrip(".")
                else:
                    qty_display = f"{q:,.0f}"
            else:
                qty_display = "—"
            val_display = f"{r['Current Value']:,.0f}" if r["Current Value"] else ("Closed" if r["Qty"] == 0 else "N/A")
            row_bg      = "#fafafa" if is_closed else "transparent"

            result.append(html.Tr([
                html.Td(html.Span(ndisp, title=name), style={
                    "padding": "5px 10px", "fontSize": "12px", "color": "#1a3a5c", "whiteSpace": "nowrap",
                }),
                html.Td(r["Category"], style={
                    "padding": "5px 10px", "fontSize": "11px", "textAlign": "center", "color": "#666",
                }),
                html.Td(price_str, style={
                    "padding": "5px 10px", "fontSize": "12px", "textAlign": "right",
                    "fontFamily": "monospace", "color": "#555",
                }),
                html.Td(avg_str, style={
                    "padding": "5px 10px", "fontSize": "12px", "textAlign": "right",
                    "fontFamily": "monospace", "color": "#888",
                }),
                html.Td(qty_display, style={
                    "padding": "5px 10px", "fontSize": "12px", "textAlign": "right", "fontFamily": "monospace",
                }),
                html.Td(val_display,
                    style={"padding": "5px 10px", "fontSize": "12px", "textAlign": "right",
                           "fontFamily": "monospace", "fontWeight": "600", "color": "#1a3a5c"}
                ),
                html.Td(
                    f"{r.get('Dividends', 0):,.0f}" if r.get('Dividends', 0) else "—",
                    style={"padding": "5px 10px", "fontSize": "12px", "textAlign": "right",
                           "fontFamily": "monospace", "color": "#1a7a1a"}
                ),
                html.Td(
                    f"{pnl:+,.0f}" if pnl is not None else "N/A",
                    style={"padding": "5px 10px", "fontSize": "12px", "textAlign": "right",
                           "fontFamily": "monospace", "fontWeight": "700", "color": color}
                ),
                html.Td(
                    f"{pnl_pct:+.1f}%" if pnl_pct is not None else "N/A",
                    style={"padding": "5px 10px", "fontSize": "12px", "textAlign": "right",
                           "fontFamily": "monospace", "fontWeight": "600", "color": color}
                ),
                html.Td(
                    f"{r['Current Value'] * calc_return(df_combined, fid, days_back=1) / 100:+,.0f}"
                    if r["Current Value"] and calc_return(df_combined, fid, days_back=1) is not None
                    else "—",
                    style={
                        "padding": "4px 8px", "fontSize": "11px", "textAlign": "right",
                        "fontFamily": "monospace", "fontWeight": "600",
                        "color": "#1a7a1a" if (calc_return(df_combined, fid, days_back=1) or 0) >= 0 else "#c0392b",
                    }
                ),
            ] + [
                html.Td(
                    f"{v:+.1f}%" if v is not None else "N/A",
                    style={
                        "padding": "4px 8px", "fontSize": "11px", "textAlign": "center",
                        "fontWeight": "600", "fontFamily": "monospace",
                        "backgroundColor": heatmap_color(v, rng[0], rng[1]),
                        "color": "#1a1a1a", "borderRadius": "3px",
                    }
                )
                for v, rng in [
                    (calc_return(df_combined, fid, days_back=1),  range_1d),
                    (calc_return(df_combined, fid, days_back=5),  range_1w),
                    (calc_return(df_combined, fid, days_back=21), range_1m),
                ]
            ], style={"borderBottom": "1px solid #f0f3f7", "backgroundColor": row_bg}))
        return result

    rows = make_rows(open_df)

    if not closed_df.empty:
        closed_pnl   = closed_df["PnL"].dropna().sum()
        closed_count = len(closed_df)
        c_color      = "#1a7a1a" if closed_pnl >= 0 else "#c0392b"

        if show_closed:
            rows.append(html.Tr([
                html.Td(f"CLOSED POSITIONS ({closed_count})", colSpan=8, style={
                    "padding": "6px 10px", "fontSize": "11px", "fontWeight": "700",
                    "color": "#666", "backgroundColor": "#f0f3f7",
                    "borderTop": "1px solid #ddd",
                }),
            ]))
            rows.extend(make_rows(closed_df, is_closed=True))
        else:
            rows.append(html.Tr([
                html.Td(f"Closed positions ({closed_count} instruments)", colSpan=5, style={
                    "padding": "5px 10px", "fontSize": "12px", "color": "#888",
                    "fontStyle": "italic",
                }),
                html.Td("Closed", style={"padding": "5px 10px", "textAlign": "right", "color": "#bbb", "fontSize": "12px"}),
                html.Td(f"{closed_pnl:+,.0f}", style={
                    "padding": "5px 10px", "fontSize": "12px", "textAlign": "right",
                    "fontFamily": "monospace", "fontWeight": "700", "color": c_color,
                }),
                html.Td("—", style={"padding": "5px 10px", "textAlign": "right", "color": "#bbb"}),
                html.Td("—", style={"padding": "5px 10px", "textAlign": "right", "color": "#bbb"}),
                html.Td("—", style={"padding": "5px 10px", "textAlign": "right", "color": "#bbb"}),
                html.Td("—", style={"padding": "5px 10px", "textAlign": "right", "color": "#bbb"}),
            ], style={"borderBottom": "1px solid #f0f3f7", "backgroundColor": "#fafafa"}))

    total_1d_gbp = sum(
        r["Current Value"] * calc_return(df_combined, r["fund_id"], days_back=1) / 100
        for _, r in open_df.iterrows()
        if r["Current Value"] and calc_return(df_combined, r["fund_id"], days_back=1) is not None
    )
    d1_color = "#1a7a1a" if total_1d_gbp >= 0 else "#c0392b"

    rows.append(html.Tr([
        html.Td("TOTAL", colSpan=5, style={
            "padding": "7px 10px", "fontSize": "12px", "fontWeight": "700",
            "color": "#1a3a5c", "borderTop": "2px solid #1a3a5c",
        }),
        html.Td(f"{total_value:,.0f}", style={
            "padding": "7px 10px", "fontSize": "12px", "textAlign": "right",
            "fontFamily": "monospace", "fontWeight": "700", "borderTop": "2px solid #1a3a5c",
        }),
        html.Td(f"{pnl_df['Dividends'].sum():,.0f}" if 'Dividends' in pnl_df.columns and pnl_df['Dividends'].sum() > 0 else "—",
                style={"padding": "7px 10px", "fontSize": "12px", "textAlign": "right",
                       "fontFamily": "monospace", "fontWeight": "700", "color": "#1a7a1a",
                       "borderTop": "2px solid #1a3a5c"}),
        html.Td(f"{total_pnl:+,.0f}", style={
            "padding": "7px 10px", "fontSize": "12px", "textAlign": "right",
            "fontFamily": "monospace", "fontWeight": "700", "color": pnl_color,
            "borderTop": "2px solid #1a3a5c",
        }),
        html.Td(f"{total_pnl_pct:+.1f}%", style={
            "padding": "7px 10px", "fontSize": "12px", "textAlign": "right",
            "fontFamily": "monospace", "fontWeight": "700", "color": pnl_color,
            "borderTop": "2px solid #1a3a5c",
        }),
        html.Td(f"{total_1d_gbp:+,.0f}", style={
            "padding": "7px 10px", "fontSize": "12px", "textAlign": "right",
            "fontFamily": "monospace", "fontWeight": "700", "color": d1_color,
            "borderTop": "2px solid #1a3a5c",
        }),
        html.Td("", colSpan=3, style={"borderTop": "2px solid #1a3a5c"}),
    ]))

    # FIX: P&L table wrapped in scrollable card
    table = html.Div(
        html.Table(
            [html.Thead(header), html.Tbody(rows)],
            style={"width": "100%", "borderCollapse": "collapse"}
        ),
        style={**CARD, 'overflowX': 'auto', 'padding': '0'}
    )
    return table, total_label


def recalc_portfolio_from_transactions(fund_id):
    """Recalculate units for a fund from transaction history and update portfolio.json.
    Only updates the specific fund_id — all other holdings are untouched.
    """
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

    # Update portfolio_holdings table directly
    from datetime import datetime
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


@app.callback(
    Output('txn-fx-input',    'value'),
    Output('txn-price-input', 'value'),
    Output('txn-price-input', 'disabled'),
    Output('txn-price-div',   'style'),
    Input('txn-fund-select',  'value'),
    Input('txn-date-input',   'date'),
    Input('txn-type-select',  'value'),
    prevent_initial_call=False,
)
def auto_fill_txn_fields(fund_id, trade_date, ttype):
    """Auto-load FX rate for selected fund/date. Grey out price for dividends."""
    fx_val    = 1.0
    price_val = None
    is_div    = ttype == 'DIVIDEND'
    price_disabled = is_div
    price_style = {'marginRight': '12px', 'opacity': '0.4' if is_div else '1'}

    if is_div:
        price_val = 1.0

    if fund_id and trade_date:
        inst = instruments.get(fund_id, {})
        curr = inst.get('currency', 'GBP')
        if curr == 'USD':
            fx_id = 'YF:GBPUSD=X'
        elif curr == 'TRY':
            fx_id = 'YF:GBPTRY=X'
        else:
            return fx_val, price_val, price_disabled, price_style
        conn = sqlite3.connect(DB_PATH)
        row  = conn.execute(
            "SELECT close FROM prices WHERE fund_id = ? AND date <= ? ORDER BY date DESC LIMIT 1",
            (fx_id, trade_date)
        ).fetchone()
        conn.close()
        if row:
            fx_val = round(row[0], 4)

    return fx_val, price_val, price_disabled, price_style


@app.callback(
    Output("txn-status", "children"),
    Output("portfolio-reload", "data", allow_duplicate=True),
    Output("txn-qty-input", "value"),
    Output("txn-price-input", "value", allow_duplicate=True),
    Input("txn-add-btn", "n_clicks"),
    State("txn-fund-select",   "value"),
    State("txn-account-input", "value"),
    State("txn-date-input",    "date"),
    State("txn-type-select",   "value"),
    State("txn-qty-input",     "value"),
    State("txn-price-input",   "value"),
    State("txn-fx-input",      "value"),
    State("portfolio-reload",  "data"),
    prevent_initial_call=True,
)
def add_transaction(n_clicks, fund_id, account, trade_date, ttype, qty, price, fx_rate, reload):
    is_div = ttype == 'DIVIDEND'

    if is_div:
        if not all([fund_id, trade_date, qty]):
            return "Please fill in fund, date and quantity.", reload, qty, 1.0
        price = 1.0
    else:
        if not all([fund_id, trade_date, ttype, qty, price]):
            return "Please fill in all required fields.", reload, qty, price

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO transactions (fund_id, account, trade_date, type, quantity, price, currency, fx_rate) VALUES (?,?,?,?,?,?,?,?)",
        (fund_id, account or "", trade_date, ttype, float(qty), float(price),
         instruments.get(fund_id, {}).get("currency", "GBP"), float(fx_rate or 1.0))
    )
    conn.commit()
    conn.close()

    name = instruments.get(fund_id, {}).get('name', fund_id)

    if is_div:
        fx      = float(fx_rate or 1.0)
        div_gbp = float(qty) / fx
        msg     = f"✓ DIVIDEND {name} — {qty} received = £{div_gbp:,.2f} on {trade_date}"
        return msg, reload + 1, None, None
    else:
        new_units = recalc_portfolio_from_transactions(fund_id)
        msg       = f"✓ {ttype} {qty} × {name} @ {price} on {trade_date} — Portfolio updated to {new_units:,.4f} units"
        return msg, reload + 1, None, None


@app.callback(
    Output("pnl-status", "children"),
    Input("pnl-add-btn", "n_clicks"),
    prevent_initial_call=True,
)
def pnl_status_placeholder(n_clicks):
    return ""


# ── 10. CASH ACCOUNTS CALLBACKS ───────────────────────────────

def render_cash_table(accounts, fx_rates):
    """Render the cash accounts table with totals."""
    if not accounts:
        return html.P("No cash accounts yet. Add one below.",
                      style={'color': '#999', 'fontSize': '12px', 'marginBottom': '8px'})

    header = html.Tr([
        html.Th(c, style={
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '5px 8px', 'fontSize': '11px', 'fontWeight': '600',
            'textAlign': 'left' if i == 0 else 'right', 'whiteSpace': 'nowrap',
        }) for i, c in enumerate(['Account', 'CCY', 'Amount', 'GBP Value', ''])
    ])

    rows = []
    total_gbp = 0.0
    for idx, acc in enumerate(accounts):
        amount    = float(acc.get('amount', 0))
        curr      = acc.get('currency', 'GBP')
        sym       = {'GBP': '£', 'USD': '$', 'TRY': '₺'}.get(curr, '')
        if curr == 'GBP':
            gbp_val = amount
        elif curr == 'USD':
            gbp_val = amount / fx_rates.get('USD', 1.26)
        elif curr == 'TRY':
            gbp_val = amount / fx_rates.get('TRY', 43.0)
        else:
            gbp_val = amount
        total_gbp += gbp_val

        rows.append(html.Tr([
            html.Td(acc.get('name', ''), style={
                'padding': '4px 8px', 'fontSize': '12px', 'color': '#1a3a5c',
            }),
            html.Td(curr, style={
                'padding': '4px 8px', 'fontSize': '11px', 'textAlign': 'right', 'color': '#666',
            }),
            html.Td(f"{sym}{amount:,.0f}", style={
                'padding': '4px 8px', 'fontSize': '12px', 'textAlign': 'right',
                'fontFamily': 'monospace',
            }),
            html.Td(f"{gbp_val:,.0f}", style={
                'padding': '4px 8px', 'fontSize': '12px', 'textAlign': 'right',
                'fontFamily': 'monospace', 'fontWeight': '600', 'color': '#1a3a5c',
            }),
            html.Td(
                html.Button("✕", id={'type': 'cash-remove-btn', 'index': acc.get('id', idx)},
                            n_clicks=0, style={
                                'backgroundColor': 'transparent', 'color': '#c0392b',
                                'border': 'none', 'cursor': 'pointer', 'fontSize': '12px',
                                'padding': '2px 6px',
                            }),
                style={'padding': '4px 4px', 'textAlign': 'center'},
            ),
        ], style={'borderBottom': '1px solid #f0f3f7'}))

    # Total row
    rows.append(html.Tr([
        html.Td("TOTAL", colSpan=3, style={
            'padding': '6px 8px', 'fontSize': '12px', 'fontWeight': '700',
            'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c',
        }),
        html.Td(f"{total_gbp:,.0f}", style={
            'padding': '6px 8px', 'fontSize': '12px', 'textAlign': 'right',
            'fontFamily': 'monospace', 'fontWeight': '700', 'color': '#1a3a5c',
            'borderTop': '2px solid #1a3a5c',
        }),
        html.Td("", style={'borderTop': '2px solid #1a3a5c'}),
    ]))

    return html.Table(
        [html.Thead(header), html.Tbody(rows)],
        style={'width': '100%', 'borderCollapse': 'collapse'}
    )


@app.callback(
    Output('cash-accounts-table-div', 'children'),
    Output('cash-status', 'children'),
    Output('cash-name-input', 'value'),
    Output('cash-amount-input', 'value'),
    Input('main-tabs', 'value'),
    Input('cash-add-btn', 'n_clicks'),
    Input({'type': 'cash-remove-btn', 'index': ALL}, 'n_clicks'),
    State('cash-name-input', 'value'),
    State('cash-currency-select', 'value'),
    State('cash-amount-input', 'value'),
    prevent_initial_call=False,
)
def manage_cash_accounts(tab, add_clicks, remove_clicks, name, currency, amount):
    fx_rates  = get_fx_rates(df)
    accounts  = load_cash_accounts()
    triggered = ctx.triggered_id

    if triggered == 'cash-add-btn':
        if name and amount:
            add_cash_account(name, currency or 'GBP', float(amount))
            accounts = load_cash_accounts()
            return render_cash_table(accounts, fx_rates), f'✓ Added {name}', None, None
        return render_cash_table(accounts, fx_rates), 'Please enter name and amount.', name, amount

    if isinstance(triggered, dict) and triggered.get('type') == 'cash-remove-btn':
        row_id = triggered['index']
        remove_cash_account(row_id)
        accounts = load_cash_accounts()
        return render_cash_table(accounts, fx_rates), '✓ Removed account', name, amount

    return render_cash_table(accounts, fx_rates), '', name, amount


# ── 11. SUMMARY CALLBACKS ─────────────────────────────────────

@app.callback(
    Output('summary-table-div', 'children'),
    Input('main-tabs',                'value'),
    Input('summary-snapshot-select',  'value'),
    Input('portfolio-reload',         'data'),
)
def update_summary(tab, snapshot_date, reload):
    portfolio  = load_portfolio()
    gbpusd     = get_gbpusd(df)
    fx_rates   = get_fx_rates(df)

    # Load snapshot for comparison
    snap_holdings = {}
    snap_label    = None
    if snapshot_date and snapshot_date != 'none':
        snap_conn = sqlite3.connect(DB_PATH)
        snap_row  = snap_conn.execute(
            "SELECT id FROM portfolio_snapshots WHERE snap_date = ?", (snapshot_date,)
        ).fetchone()
        if snap_row:
            snap_id    = snap_row[0]
            snap_label = pd.Timestamp(snapshot_date).strftime('%d %b %Y')
            h_rows = snap_conn.execute(
                "SELECT fund_id, value_gbp FROM snapshot_holdings WHERE snapshot_id = ?",
                (snap_id,)
            ).fetchall()
            snap_holdings = {r[0]: r[1] for r in h_rows}
        snap_conn.close()

    cash_accounts = load_cash_accounts()
    # Filter out legacy CASH: entries
    portfolio = [p for p in portfolio if not p['fund_id'].startswith('CASH:')]

    if not portfolio and not cash_accounts:
        return html.P("No holdings found.", style={'color': '#999', 'fontSize': '14px'})

    # Build rows data — same logic as portfolio tab
    rows_data = []
    for item in portfolio:
        fid   = item['fund_id']
        units = item.get('units', 0)
        inst  = instruments.get(fid, {})
        name  = inst.get('name', fid)
        curr  = inst.get('currency', '?')
        punit = inst.get('price_unit', '?')

        if fid.startswith('CASH:') or fid.startswith('ASSET:'):
            price = 1.0
            effective_unit = punit
            if fid == 'CASH:TRY':
                effective_unit = 'point'
            gbp   = to_gbp(price, effective_unit, curr, gbpusd, fx_rates)
            value = gbp * units if gbp is not None else None
        elif fid.startswith('COMPOSITE:'):
            comp_def = next((c for c in getattr(config, 'COMPOSITE_FUNDS', []) if c['fund_id'] == fid), None)
            if comp_def:
                weighted_gbp = 0.0
                for c in comp_def['components']:
                    c_price = get_latest_price(df_combined, c['fund_id'])
                    c_inst  = instruments.get(c['fund_id'], {})
                    c_gbp   = to_gbp(c_price, c_inst.get('price_unit','pence'), c_inst.get('currency','GBP'), gbpusd, fx_rates)
                    if c_gbp is not None:
                        weighted_gbp += c_gbp * c['weight']
                gbp   = weighted_gbp if weighted_gbp > 0 else None
                value = gbp * units if gbp is not None else None
            else:
                value = None
        else:
            price = get_latest_price(df_combined, fid)
            gbp   = to_gbp(price, punit, curr, gbpusd, fx_rates) if price else None
            value = gbp * units if gbp is not None else None

        rows_data.append({'fund_id': fid, 'name': name, 'value': value})

    # Add aggregated cash row
    if cash_accounts:
        fx_rates_s     = get_fx_rates(df)
        cash_total_gbp = calc_cash_total_gbp(cash_accounts, fx_rates_s)
        rows_data.append({'fund_id': 'CASH:TOTAL', 'name': 'Cash', 'value': cash_total_gbp})

    total = sum(r['value'] for r in rows_data if r['value'] is not None)

    # Table header — no snapshot value column, just variance
    chg_cols = (['Chg k', 'Chg %'] if snap_label else [])
    all_cols  = ['Fund', 'Value k', '%'] + chg_cols

    def sum_th(i, label):
        base_style = {
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '8px 8px', 'fontSize': '12px', 'fontWeight': '600',
            'whiteSpace': 'nowrap',
            'textAlign': 'left' if i == 0 else 'right',
        }
        cls = 'sum-fund' if i == 0 else 'sum-num'
        return html.Th(label, style=base_style, className=cls)

    header = html.Tr([sum_th(i, c) for i, c in enumerate(all_cols)])

    # Build rows sorted by value descending
    rows = []
    for r in sorted(rows_data, key=lambda x: x['value'] or 0, reverse=True):
        fid   = r['fund_id']
        value = r['value']
        pct   = (value / total * 100) if total and value else None
        name  = r['name']
        ndisp = name if len(name) <= 25 else name[:25] + '…'

        snap_val  = snap_holdings.get(fid)
        chg_gbp   = (value - snap_val) if snap_val and value else None
        chg_pct   = ((value / snap_val - 1) * 100) if snap_val and value and snap_val > 0 else None
        chg_color = '#1a7a1a' if (chg_gbp or 0) >= 0 else '#c0392b'

        cells = [
            html.Td(html.Span(ndisp, title=name), className='sum-fund', style={
                'padding': '7px 8px', 'fontSize': '13px',
                'color': '#1a3a5c', 'overflow': 'hidden',
                'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap',
            }),
            html.Td(f"{value/1000:.1f}" if value else 'N/A', className='sum-num', style={
                'padding': '7px 8px', 'fontSize': '13px',
                'textAlign': 'right', 'fontFamily': 'monospace',
                'fontWeight': '600', 'whiteSpace': 'nowrap',
            }),
            html.Td(f"{pct:.1f}%" if pct else 'N/A', className='sum-num', style={
                'padding': '7px 8px', 'fontSize': '12px',
                'textAlign': 'right', 'fontFamily': 'monospace',
                'color': '#555', 'whiteSpace': 'nowrap',
            }),
        ]

        if snap_label:
            cells += [
                html.Td(f"{chg_gbp/1000:+.1f}" if chg_gbp is not None else '—', className='sum-num', style={
                    'padding': '7px 8px', 'fontSize': '12px',
                    'textAlign': 'right', 'fontFamily': 'monospace',
                    'fontWeight': '600', 'color': chg_color,
                    'whiteSpace': 'nowrap',
                }),
                html.Td(f"{chg_pct:+.1f}%" if chg_pct is not None else '—', className='sum-num', style={
                    'padding': '7px 8px', 'fontSize': '12px',
                    'textAlign': 'right', 'fontFamily': 'monospace',
                    'fontWeight': '600', 'color': chg_color,
                    'whiteSpace': 'nowrap',
                }),
            ]

        rows.append(html.Tr(cells, style={'borderBottom': '1px solid #f0f3f7'}))

    # Total row
    snap_total  = sum(snap_holdings.values()) if snap_holdings else 0
    chg_total   = (total - snap_total) if snap_total else None
    chg_pct_tot = ((total / snap_total - 1) * 100) if snap_total and snap_total > 0 else None
    tot_color   = '#1a7a1a' if (chg_total or 0) >= 0 else '#c0392b'

    total_cells = [
        html.Td("TOTAL", style={
            'padding': '8px 8px', 'fontSize': '13px',
            'fontWeight': '700', 'color': '#1a3a5c',
            'borderTop': '2px solid #1a3a5c',
        }),
        html.Td(f"{total/1000:.1f}", style={
            'padding': '8px 8px', 'fontSize': '13px',
            'textAlign': 'right', 'fontFamily': 'monospace',
            'fontWeight': '700', 'color': '#1a3a5c',
            'borderTop': '2px solid #1a3a5c', 'whiteSpace': 'nowrap',
        }),
        html.Td("100%", style={
            'padding': '8px 8px', 'fontSize': '12px',
            'textAlign': 'right', 'color': '#666',
            'borderTop': '2px solid #1a3a5c',
        }),
    ]
    if snap_label:
        total_cells += [
            html.Td(f"{chg_total/1000:+.1f}" if chg_total is not None else '—', style={
                'padding': '8px 8px', 'fontSize': '12px', 'textAlign': 'right',
                'fontFamily': 'monospace', 'fontWeight': '700', 'color': tot_color,
                'borderTop': '2px solid #1a3a5c', 'whiteSpace': 'nowrap',
            }),
            html.Td(f"{chg_pct_tot:+.1f}%" if chg_pct_tot is not None else '—', style={
                'padding': '8px 8px', 'fontSize': '12px', 'textAlign': 'right',
                'fontFamily': 'monospace', 'fontWeight': '700', 'color': tot_color,
                'borderTop': '2px solid #1a3a5c', 'whiteSpace': 'nowrap',
            }),
        ]
    rows.append(html.Tr(total_cells))

    table = html.Div(
        html.Table(
            [html.Thead(header), html.Tbody(rows)],
            style={'width': '100%', 'borderCollapse': 'collapse', 'tableLayout': 'auto'}
        ),
        style={**CARD, 'overflowX': 'auto', 'padding': '0'}
    )

    return table


# ── 11. RUN ─────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)