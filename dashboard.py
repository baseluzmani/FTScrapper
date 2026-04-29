# dashboard.py
# Financial dashboard — Portfolio, P&L, Summary tabs.
# Run with: python3 dashboard.py
# Then open: http://localhost:8050

import dash
from dash import html, dcc, Input, Output, State, ALL, ctx
import plotly.graph_objects as go
import pandas as pd
import sqlite3
from datetime import datetime
from collections import defaultdict

import config
from data import (
    DB_PATH, load_data, load_instruments, load_portfolio, save_portfolio,
    delete_holding, upsert_holding, load_cash_accounts, add_cash_account,
    remove_cash_account, calc_cash_total_gbp, get_fx_rates, get_gbpusd,
    to_gbp, get_latest_price, build_df_combined, calc_return, ytd_date,
    heatmap_color, calc_pnl, txn_price_to_gbp, recalc_portfolio_from_transactions,
    get_snapshot_options, get_latest_snapshot_value, load_snapshot,
    get_holding_value_gbp,
)


# ── 1. APP SETUP ───────────────────────────────────────────────

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

df          = load_data()
df_combined = build_df_combined(df)
instruments = load_instruments()

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


# ── 2. STYLES ──────────────────────────────────────────────────

CARD = {
    'backgroundColor': '#ffffff', 'borderRadius': '8px',
    'padding': '14px 18px', 'boxShadow': '0 1px 4px rgba(0,0,0,0.08)',
    'marginBottom': '12px',
}
SECTION_TITLE = {
    'color': '#1a3a5c', 'fontSize': '11px', 'fontWeight': '700',
    'letterSpacing': '0.08em', 'textTransform': 'uppercase',
    'marginBottom': '10px', 'marginTop': '0',
}
TAB_STYLE = {
    'padding': '8px 20px', 'fontSize': '12px', 'fontWeight': '600',
    'color': '#666', 'borderBottom': '2px solid transparent', 'cursor': 'pointer',
}
TAB_SELECTED_STYLE = {
    'padding': '8px 20px', 'fontSize': '12px', 'fontWeight': '600',
    'color': '#2E75B6', 'borderBottom': '2px solid #2E75B6', 'cursor': 'pointer',
}


# ── 3. LAYOUT ──────────────────────────────────────────────────

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
        html.Span(id='data-date-label',
                  style={'fontSize': '11px', 'color': '#999', 'alignSelf': 'center'}),
    ], style={
        'display': 'flex', 'justifyContent': 'space-between',
        'alignItems': 'center', 'padding': '12px 20px',
        'backgroundColor': '#fff', 'borderBottom': '2px solid #2E75B6',
        'marginBottom': '0',
    }),

    # Tabs
    dcc.Tabs(
        id='main-tabs', value='tab-portfolio',
        children=[
            dcc.Tab(label='Portfolio', value='tab-portfolio',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            dcc.Tab(label='P&L',       value='tab-pnl',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            dcc.Tab(label='Summary',   value='tab-summary',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
        ],
        style={'backgroundColor': '#fff', 'borderBottom': '1px solid #eee', 'marginBottom': '0'}
    ),

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




# ── 4. TAB VISIBILITY ──────────────────────────────────────────

@app.callback(
    Output('portfolio-tab-content', 'style'),
    Output('pnl-tab-content',       'style'),
    Output('summary-tab-content',   'style'),
    Output('data-date-label',       'children'),
    Input('main-tabs',         'value'),
    Input('db-reload-trigger', 'data'),
    Input('auto-refresh',      'n_intervals'),
)
def switch_tab(tab, reload_trigger, n_intervals):
    global df, df_combined, instruments
    if reload_trigger or n_intervals:
        df          = load_data()
        df_combined = build_df_combined(df)
        instruments = load_instruments()

    date_label = f"Data as of {df['date'].max().strftime('%d %b %Y')}"
    base = {'padding': '12px 16px 16px 16px', 'maxWidth': '1400px',
            'margin': '0 auto', 'overflowX': 'hidden'}
    show = {**base, 'display': 'block'}
    hide = {**base, 'display': 'none'}

    if tab == 'tab-portfolio':
        return show, hide, hide, date_label
    elif tab == 'tab-pnl':
        return hide, show, hide, date_label
    elif tab == 'tab-summary':
        return hide, hide, show, date_label
    return show, hide, hide, date_label


# ── 5. PORTFOLIO CALLBACKS ─────────────────────────────────────

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
    pnl_df   = calc_pnl(df_combined, instruments, gbpusd, fx_rates)

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