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
    """Load portfolio from JSON. Returns list of {fund_id, units}."""
    if not os.path.exists(PORTFOLIO_PATH):
        return []
    try:
        with open(PORTFOLIO_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def save_portfolio(portfolio):
    """Save portfolio list to JSON."""
    os.makedirs('data', exist_ok=True)
    with open(PORTFOLIO_PATH, 'w') as f:
        json.dump(portfolio, f, indent=2)


def get_gbpusd(df):
    """Get latest GBP/USD rate from database."""
    fx_df = df[df['fund_id'] == 'YF:GBPUSD=X'].sort_values('date')
    if fx_df.empty:
        return 1.26  # fallback
    return fx_df.iloc[-1]['close']


def to_gbp(price, price_unit, currency, gbpusd):
    """Convert a price to GBP pounds."""
    if price is None:
        return None
    # Convert pence to pounds
    if price_unit == 'pence':
        price = price / 100
    # Convert USD to GBP
    if currency == 'USD':
        price = price / gbpusd
    # Points/ratios are not convertible to GBP value
    if price_unit in ('point', 'ratio'):
        return None
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
        intensity = min(val / max(abs(vmax), 0.001), 1.0)
        r = int(255 - intensity * 180)
        g = int(255 - intensity * 50)
        b = int(255 - intensity * 180)
        return f'rgb({r},{g},{b})'
    else:
        intensity = min(abs(val) / max(abs(vmin), 0.001), 1.0)
        r = int(255 - intensity * 50)
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

app = dash.Dash(__name__, suppress_callback_exceptions=True)

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

holding_ids_default   = [h['fund_id'] for h in config.HOLDINGS]
composite_ids         = [c['fund_id'] for c in getattr(config, 'COMPOSITE_FUNDS', [])]
all_holding_ids       = holding_ids_default + composite_ids
top4_holdings_default = get_top4_by_ytd(df_combined, all_holding_ids)

# Portfolio fund options — all funds in instruments table
# Include fixed-price instruments (CASH/ASSET), exclude points/ratios
portfolio_options = [
    {'label': f"{v['name']} ({k})", 'value': k}
    for k, v in sorted(instruments.items(), key=lambda x: x[1]['name'])
    if v['price_unit'] not in ('point', 'ratio')
    or k.startswith('CASH:') or k.startswith('ASSET:')
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

        html.Div([
            html.Div([
                html.Div(id='holdings-table-div'),
            ], style={'flex': '2', 'minWidth': '0', 'overflow': 'hidden'}),

            html.Div([
                html.Div([
                    html.P("RELATIVE RETURNS", style={**SECTION_TITLE, 'marginBottom': '4px'}),
                    html.Span(id='holdings-chart-info', style={'fontSize': '11px', 'color': '#aaa'}),
                ], style={'marginBottom': '8px'}),
                dcc.Graph(id='holdings-relative-chart', config={'displayModeBar': False}),
            ], style={
                'flex': '1', 'minWidth': '260px', 'backgroundColor': '#fff',
                'borderRadius': '8px', 'padding': '14px 18px',
                'boxShadow': '0 1px 4px rgba(0,0,0,0.08)',
                'marginBottom': '12px', 'marginLeft': '12px',
            }),
        ], style={'display': 'flex', 'alignItems': 'flex-start'}),

        dcc.Store(id='holdings-selected-funds', data=top4_holdings_default),

    ], id='holdings-tab-content', style={
        'display': 'block', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto',
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

        html.Div([
            html.Div([
                html.Div(id='market-table-div'),
            ], style={'flex': '2', 'minWidth': '0', 'overflow': 'hidden'}),

            html.Div([
                html.Div([
                    html.P("RELATIVE RETURNS", style={**SECTION_TITLE, 'marginBottom': '4px'}),
                    html.Span(id='market-chart-info', style={'fontSize': '11px', 'color': '#aaa'}),
                ], style={'marginBottom': '8px'}),
                dcc.Graph(id='relative-chart', config={'displayModeBar': False}),
            ], style={
                'flex': '1', 'minWidth': '260px', 'backgroundColor': '#fff',
                'borderRadius': '8px', 'padding': '14px 18px',
                'boxShadow': '0 1px 4px rgba(0,0,0,0.08)',
                'marginBottom': '12px', 'marginLeft': '12px',
            }),
        ], style={'display': 'flex', 'alignItems': 'flex-start'}),

        dcc.Store(id='market-selected-funds', data=top4_default),

    ], id='market-tab-content', style={
        'display': 'none', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto',
    }),

    # ── PORTFOLIO TAB
    html.Div([
        # Header
        html.Div([
            html.Div([
                html.P("PORTFOLIO", style={**SECTION_TITLE, 'marginBottom': '0'}),
                html.Span(id='portfolio-total-label', style={
                    'fontSize': '20px', 'fontWeight': '700',
                    'color': '#1a3a5c', 'letterSpacing': '0.02em',
                }),
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}),
        ], style=CARD),

        # Side-by-side: main table (left) + category breakdown (right)
        html.Div([
            html.Div(id='portfolio-table-div', style={
                'flex': '3', 'minWidth': '0',
            }),
            html.Div(id='portfolio-category-div', style={
                'flex': '1', 'minWidth': '220px',
                'marginLeft': '12px',
            }),
        ], style={'display': 'flex', 'alignItems': 'flex-start'}),

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

    ], id='portfolio-tab-content', style={
        'display': 'none', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto',
    }),

    # Shared stores
    dcc.Store(id='sort-state-holdings', data={'col': 'YTD', 'asc': False}),
    dcc.Store(id='sort-state-market',   data={'col': 'YTD', 'asc': False}),
    dcc.Store(id='db-reload-trigger',   data=0),
    dcc.Store(id='portfolio-reload',    data=0),

], style={
    'fontFamily': '"DM Sans", -apple-system, BlinkMacSystemFont, sans-serif',
    'backgroundColor': '#f0f3f7',
    'minHeight': '100vh',
})


# ── 5. TAB VISIBILITY ──────────────────────────────────────────

@app.callback(
    Output('holdings-tab-content',  'style'),
    Output('market-tab-content',    'style'),
    Output('portfolio-tab-content', 'style'),
    Output('data-date-label',       'children'),
    Input('main-tabs',         'value'),
    Input('db-reload-trigger', 'data'),
)
def switch_tab(tab, reload_trigger):
    global df, df_composite, df_combined, instruments
    if reload_trigger:
        df           = load_data()
        df_composite = build_composite_data(df)
        df_calc      = build_calculated_series(df)
        df_combined  = pd.concat(
            [x for x in [df, df_composite, df_calc] if not x.empty],
            ignore_index=True
        )
        instruments  = load_instruments()

    date_label = f"Data as of {df['date'].max().strftime('%d %b %Y')}"
    base = {'padding': '12px 16px 16px 16px', 'maxWidth': '1400px', 'margin': '0 auto'}
    base_port = {'padding': '12px 16px 16px 16px', 'maxWidth': '1400px', 'margin': '0 auto'}
    show      = {**base,      'display': 'block'}
    show_port = {**base_port, 'display': 'block'}
    hide      = {**base,      'display': 'none'}
    hide_port = {**base_port, 'display': 'none'}

    if tab == 'tab-holdings':
        return show, hide, hide_port, date_label
    elif tab == 'tab-market':
        return hide, show, hide_port, date_label
    elif tab == 'tab-portfolio':
        return hide, hide, show_port, date_label
    return show, hide, hide_port, date_label


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

    holding_ids   = [h['fund_id'] for h in config.HOLDINGS]
    holding_names = {h['fund_id']: h['display_name'] for h in config.HOLDINGS}
    composites    = getattr(config, 'COMPOSITE_FUNDS', [])
    composite_ids = [c['fund_id'] for c in composites]
    comp_names    = {c['fund_id']: c['display_name'] for c in composites}
    all_ids       = holding_ids + composite_ids
    all_names     = {**holding_names, **comp_names}

    holdings_df = df_combined[df_combined['fund_id'].isin(all_ids)].copy()
    if holdings_df.empty:
        return html.P("No holdings found.", style={'color': '#999', 'fontSize': '12px'}), sort_state

    table_df = build_returns_table(holdings_df, since_date)
    table_df['Fund'] = table_df['fund_id'].map(lambda fid: all_names.get(fid, fid))

    sort_col = sort_state['col']
    sort_asc = sort_state['asc']
    if sort_col in table_df.columns:
        table_df = table_df.sort_values(sort_col, ascending=sort_asc, na_position='last')

    sections = []
    for asset_type, group in table_df.groupby('Type', sort=False):
        sections.append(html.Div([
            html.P(asset_type.upper(), style={
                **SECTION_TITLE, 'borderBottom': '1px solid #e0e0e0', 'paddingBottom': '4px',
            }),
            render_returns_table(
                group, since_label, sort_state,
                header_type='holdings', selected_funds=selected_funds, clickable=True,
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
    return render_returns_table(
        table_df, since_label, sort_state,
        header_type='market', selected_funds=selected_funds, clickable=True,
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
)
def update_portfolio(reload, tab):
    portfolio  = load_portfolio()
    gbpusd     = get_gbpusd(df)

    if not portfolio:
        return html.P(
            "No holdings yet. Add a fund below.",
            style={'color': '#999', 'fontSize': '12px', 'padding': '12px'}
        ), "£0.00", html.Div()

    header = html.Tr([
        html.Th(c, style={
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '6px 12px', 'fontSize': '11px', 'fontWeight': '600',
            'textAlign': 'left' if i == 0 else 'center', 'whiteSpace': 'nowrap',
        }) for i, c in enumerate(['Fund', 'Category', 'Type', 'Currency', 'Units', 'Price', 'Value (£)', '% of Portfolio'])
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
        # Fixed-price instruments (cash, house) use 1.0 as price
        # Units = the actual value in the instrument's currency
        if fid.startswith('CASH:') or fid.startswith('ASSET:'):
            price = 1.0
        else:
            price = get_latest_price(df_combined, fid)
        gbp   = to_gbp(price, punit, curr, gbpusd) if price else None
        value = gbp * units if gbp is not None else None
        rows_data.append({
            'fund_id': fid, 'name': name, 'type': atype, 'category': cat,
            'currency': curr, 'units': units,
            'price': price, 'gbp_price': gbp, 'value': value,
        })

    total = sum(r['value'] for r in rows_data if r['value'] is not None)

    rows = []
    for r in sorted(rows_data, key=lambda x: x['value'] or 0, reverse=True):
        pct   = (r['value'] / total * 100) if total and r['value'] else None
        name  = r['name']
        ndisp = name if len(name) <= 35 else name[:35] + '…'

        # Units: no trailing zeros, no decimals if whole number
        units = r['units']
        if r['fund_id'].startswith(('CASH:', 'ASSET:')):
            units_str = f"{units:,.0f}"
        elif units == int(units):
            units_str = f"{int(units):,}"
        else:
            # Strip trailing zeros from 4dp
            units_str = f"{units:,.4f}".rstrip('0').rstrip('.')

        # Price: convert pence to pounds for GBP pence instruments, show 1dp
        price = r['price']
        fid   = r['fund_id']
        punit = instruments.get(fid, {}).get('price_unit', '')
        curr  = instruments.get(fid, {}).get('currency', '')
        if r['fund_id'].startswith(('CASH:', 'ASSET:')):
            price_str = 'Fixed'
        elif price is None:
            price_str = 'N/A'
        elif punit == 'pence' and curr == 'GBP':
            price_str = f"{price / 100:.1f}"
        else:
            price_str = f"{price:.1f}"

        rows.append(html.Tr([
            html.Td(html.Span(ndisp, title=name), style={
                'padding': '5px 12px', 'fontSize': '12px',
                'color': '#1a3a5c', 'whiteSpace': 'nowrap',
            }),
            html.Td(r['category'], style={
                'padding': '5px 12px', 'fontSize': '11px',
                'textAlign': 'center', 'color': '#444', 'fontWeight': '500',
            }),
            html.Td(r['type'], style={
                'padding': '5px 12px', 'fontSize': '11px',
                'textAlign': 'center', 'color': '#666',
            }),
            html.Td(r['currency'], style={
                'padding': '5px 12px', 'fontSize': '11px',
                'textAlign': 'center', 'color': '#666',
            }),
            html.Td(units_str, style={
                'padding': '5px 12px', 'fontSize': '12px',
                'textAlign': 'right', 'fontFamily': 'monospace',
            }),
            html.Td(price_str, style={
                'padding': '5px 12px', 'fontSize': '12px',
                'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555',
            }),
            html.Td(
                f"£{r['value']:,.0f}" if r['value'] else 'N/A',
                style={
                    'padding': '5px 12px', 'fontSize': '12px',
                    'textAlign': 'right', 'fontFamily': 'monospace',
                    'fontWeight': '600', 'color': '#1a3a5c',
                }
            ),
            html.Td(
                f"{pct:.1f}%" if pct else 'N/A',
                style={
                    'padding': '5px 12px', 'fontSize': '12px',
                    'textAlign': 'center', 'fontFamily': 'monospace', 'color': '#555',
                }
            ),
        ], style={'borderBottom': '1px solid #f0f3f7'}))

    # Total row
    rows.append(html.Tr([
        html.Td("TOTAL", colSpan=6, style={
            'padding': '8px 12px', 'fontSize': '12px',
            'fontWeight': '700', 'color': '#1a3a5c',
            'borderTop': '2px solid #1a3a5c',
        }),
        html.Td(f"£{total:,.2f}", style={
            'padding': '8px 12px', 'fontSize': '13px',
            'textAlign': 'right', 'fontFamily': 'monospace',
            'fontWeight': '700', 'color': '#1a3a5c',
            'borderTop': '2px solid #1a3a5c',
        }),
        html.Td("100%", style={
            'padding': '8px 12px', 'fontSize': '12px',
            'textAlign': 'center', 'color': '#666',
            'borderTop': '2px solid #1a3a5c',
        }),
    ]))

    table = html.Table(
        [html.Thead(header), html.Tbody(rows)],
        style={'width': '100%', 'borderCollapse': 'collapse'}
    )

    # ── Category breakdown table
    from collections import defaultdict
    cat_totals = defaultdict(float)
    for r in rows_data:
        if r['value']:
            cat_totals[r['category']] += r['value']

    cat_header = html.Tr([
        html.Th(c, style={
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '6px 10px', 'fontSize': '11px', 'fontWeight': '600',
            'textAlign': 'left' if i == 0 else 'right', 'whiteSpace': 'nowrap',
        }) for i, c in enumerate(['Category', 'Value (£)', '%'])
    ])

    cat_rows = []
    for cat, val in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True):
        pct = val / total * 100 if total else 0
        cat_rows.append(html.Tr([
            html.Td(cat, style={
                'padding': '5px 10px', 'fontSize': '12px',
                'color': '#1a3a5c', 'fontWeight': '500',
            }),
            html.Td(f"£{val:,.0f}", style={
                'padding': '5px 10px', 'fontSize': '12px',
                'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600',
            }),
            html.Td(f"{pct:.1f}%", style={
                'padding': '5px 10px', 'fontSize': '12px',
                'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555',
            }),
        ], style={'borderBottom': '1px solid #f0f3f7'}))

    cat_rows.append(html.Tr([
        html.Td("TOTAL", style={
            'padding': '7px 10px', 'fontSize': '12px',
            'fontWeight': '700', 'color': '#1a3a5c',
            'borderTop': '2px solid #1a3a5c',
        }),
        html.Td(f"£{total:,.0f}", style={
            'padding': '7px 10px', 'fontSize': '12px',
            'textAlign': 'right', 'fontFamily': 'monospace',
            'fontWeight': '700', 'color': '#1a3a5c',
            'borderTop': '2px solid #1a3a5c',
        }),
        html.Td("100%", style={
            'padding': '7px 10px', 'fontSize': '12px',
            'textAlign': 'right', 'color': '#666',
            'borderTop': '2px solid #1a3a5c',
        }),
    ]))

    cat_table = html.Div([
        html.P("BY CATEGORY", style={**SECTION_TITLE, 'borderBottom': '1px solid #e0e0e0', 'paddingBottom': '4px'}),
        html.Table(
            [html.Thead(cat_header), html.Tbody(cat_rows)],
            style={'width': '100%', 'borderCollapse': 'collapse'}
        ),
    ], style=CARD)

    return html.Div(table, style=CARD), f"£{total:,.2f}", cat_table


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
        # Update or add
        existing = next((i for i, x in enumerate(portfolio) if x['fund_id'] == fund_id), None)
        if existing is not None:
            portfolio[existing]['units'] = float(units)
            msg = f"✓ Updated {fund_id} → {units} units"
        else:
            portfolio.append({'fund_id': fund_id, 'units': float(units)})
            msg = f"✓ Added {fund_id} → {units} units"
        save_portfolio(portfolio)
        return msg, reload + 1, None

    if triggered == 'portfolio-remove-btn':
        before = len(portfolio)
        portfolio = [x for x in portfolio if x['fund_id'] != fund_id]
        if len(portfolio) < before:
            save_portfolio(portfolio)
            return f"✓ Removed {fund_id}", reload + 1, None
        return f"Fund not found in portfolio.", reload, units

    return '', reload, units


# ── 9. RUN ─────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)