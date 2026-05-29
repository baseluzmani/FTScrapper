# dashboard.py
# Financial dashboard — Portfolio, P&L, Summary, Transactions, Charts tabs.
# Run with: python3 dashboard.py
# Then open: http://localhost:8050

import dash
import config
from dash import html, dcc, Input, Output, State, ALL, ctx
import plotly.graph_objects as go
import pandas as pd
import sqlite3
from datetime import datetime
from collections import defaultdict

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
    '  .portfolio-history-card { display: none !important; }'
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
        html.Div([
            html.A('→ Personal', href='http://minipc:8052',
                   style={'fontSize': '11px', 'color': '#2E75B6', 'textDecoration': 'none',
                          'fontWeight': '600', 'marginRight': '16px'}),
            html.Span(id='data-date-label',
                      style={'fontSize': '11px', 'color': '#999'}),
        ], style={'display': 'flex', 'alignItems': 'center'}),
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
            dcc.Tab(label='Portfolio',    value='tab-portfolio',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            dcc.Tab(label='P&L',          value='tab-pnl',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            dcc.Tab(label='Summary',      value='tab-summary',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            dcc.Tab(label='Transactions', value='tab-transactions',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            dcc.Tab(label='Charts',       value='tab-charts',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            dcc.Tab(label='Accounts',     value='tab-accounts',
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
        ],
        style={'backgroundColor': '#fff', 'borderBottom': '1px solid #eee', 'marginBottom': '0'}
    ),

    # ── PORTFOLIO TAB
    html.Div([
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

        html.Div([
            html.P("ADD / UPDATE HOLDING", style=SECTION_TITLE),
            html.Div([
                html.Div([
                    html.Label("Fund:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='portfolio-fund-select', options=portfolio_options,
                                 placeholder='Select fund...', style={'fontSize': '12px'}),
                ], style={'flex': '3', 'marginRight': '12px'}),
                html.Div([
                    html.Label("Units:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='portfolio-units-input', type='number', placeholder='e.g. 1250.5', step=0.0001,
                              style={'padding': '7px', 'fontSize': '12px', 'border': '1px solid #ccc',
                                     'borderRadius': '4px', 'width': '140px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label(" ", style={'fontSize': '11px', 'display': 'block', 'marginBottom': '4px'}),
                    html.Button("Save", id='portfolio-save-btn', n_clicks=0, style={
                        'backgroundColor': '#1a7a1a', 'color': 'white', 'border': 'none',
                        'borderRadius': '4px', 'padding': '7px 16px', 'fontSize': '12px',
                        'cursor': 'pointer', 'marginRight': '8px'}),
                    html.Button("Remove", id='portfolio-remove-btn', n_clicks=0, style={
                        'backgroundColor': '#c0392b', 'color': 'white', 'border': 'none',
                        'borderRadius': '4px', 'padding': '7px 16px', 'fontSize': '12px', 'cursor': 'pointer'}),
                ]),
            ], style={'display': 'flex', 'alignItems': 'flex-end'}),
            html.Div(id='portfolio-status', style={'fontSize': '12px', 'color': '#2E75B6', 'marginTop': '8px', 'fontWeight': '600'}),
        ], style=CARD),

        html.Div([
            html.P("CASH ACCOUNTS", style=SECTION_TITLE),
            html.Div(id='cash-accounts-table-div'),
            html.Div([
                html.Div([
                    html.Label("Account:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='cash-name-input', type='text', placeholder='e.g. Barclays',
                              style={'padding': '7px', 'fontSize': '12px', 'border': '1px solid #ccc', 'borderRadius': '4px', 'width': '130px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label("Currency:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='cash-currency-select',
                                 options=[{'label': 'GBP', 'value': 'GBP'}, {'label': 'USD', 'value': 'USD'}, {'label': 'TRY', 'value': 'TRY'}],
                                 value='GBP', clearable=False, style={'fontSize': '12px', 'width': '90px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label("Amount:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='cash-amount-input', type='number', placeholder='e.g. 45000', step=0.01,
                              style={'padding': '7px', 'fontSize': '12px', 'border': '1px solid #ccc', 'borderRadius': '4px', 'width': '130px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label(" ", style={'fontSize': '11px', 'display': 'block', 'marginBottom': '4px'}),
                    html.Button("Add", id='cash-add-btn', n_clicks=0, style={
                        'backgroundColor': '#1a7a1a', 'color': 'white', 'border': 'none',
                        'borderRadius': '4px', 'padding': '7px 16px', 'fontSize': '12px', 'cursor': 'pointer'}),
                ]),
            ], style={'display': 'flex', 'alignItems': 'flex-end', 'marginTop': '12px', 'flexWrap': 'wrap', 'gap': '4px'}),
            html.Div(id='cash-status', style={'fontSize': '12px', 'color': '#2E75B6', 'marginTop': '8px', 'fontWeight': '600'}),
        ], style=CARD),

        html.Div([
            html.P("ADD TRANSACTION", style=SECTION_TITLE),
            html.Div([
                html.Div([
                    html.Label("Fund:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='txn-fund-select', options=portfolio_options, placeholder='Select fund...', style={'fontSize': '12px'}),
                ], style={'flex': '3', 'marginRight': '12px'}),
                html.Div([
                    html.Label("Account:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='txn-account-input', type='text', placeholder='e.g. AB ISA',
                              style={'padding': '7px', 'fontSize': '12px', 'border': '1px solid #ccc', 'borderRadius': '4px', 'width': '120px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label("Date:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.DatePickerSingle(id='txn-date-input', date=datetime.today().date(), display_format='DD MMM YYYY'),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label("Type:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='txn-type-select',
                                 options=[{'label': 'BUY', 'value': 'BUY'}, {'label': 'SELL', 'value': 'SELL'}, {'label': 'DIVIDEND', 'value': 'DIVIDEND'}],
                                 value='BUY', clearable=False, style={'fontSize': '12px', 'width': '110px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label("Quantity:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='txn-qty-input', type='number', placeholder='e.g. 100', step=0.0001,
                              style={'padding': '7px', 'fontSize': '12px', 'border': '1px solid #ccc', 'borderRadius': '4px', 'width': '100px'}),
                ], style={'marginRight': '12px'}),
                html.Div(id='txn-price-div', children=[
                    html.Label("Price:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='txn-price-input', type='number', placeholder='e.g. 248.3', step=0.0001,
                              style={'padding': '7px', 'fontSize': '12px', 'border': '1px solid #ccc', 'borderRadius': '4px', 'width': '100px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label("FX Rate:", style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='txn-fx-input', type='number', placeholder='1.0', value=1.0, step=0.0001,
                              style={'padding': '7px', 'fontSize': '12px', 'border': '1px solid #ccc', 'borderRadius': '4px', 'width': '80px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label(" ", style={'fontSize': '11px', 'display': 'block', 'marginBottom': '4px'}),
                    html.Button("Add", id='txn-add-btn', n_clicks=0, style={
                        'backgroundColor': '#1a7a1a', 'color': 'white', 'border': 'none',
                        'borderRadius': '4px', 'padding': '7px 16px', 'fontSize': '12px', 'cursor': 'pointer'}),
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
        html.Div([
            html.Div([
                html.P("P&L SUMMARY", style={**SECTION_TITLE, 'marginBottom': '0'}),
                html.Div([
                    html.Span(id='pnl-total-label', style={'fontSize': '20px', 'fontWeight': '700', 'color': '#1a3a5c'}),
                ]),
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}),
        ], style=CARD),
        html.Div([
            html.Button("Show Closed Positions", id='pnl-toggle-btn', n_clicks=0, style={
                'backgroundColor': '#1a3a5c', 'color': 'white', 'border': 'none',
                'borderRadius': '4px', 'padding': '6px 14px', 'fontSize': '11px',
                'cursor': 'pointer', 'marginBottom': '8px', 'marginRight': '8px'}),
            html.Button("Compact View", id='pnl-compact-btn', n_clicks=0, style={
                'backgroundColor': '#2E75B6', 'color': 'white', 'border': 'none',
                'borderRadius': '4px', 'padding': '6px 14px', 'fontSize': '11px',
                'cursor': 'pointer', 'marginBottom': '8px'}),
        ]),
        dcc.Store(id='pnl-show-closed', data=False),
        dcc.Store(id='pnl-compact',     data=False),
        html.Div(id='pnl-table-div', style={'overflowX': 'auto', 'width': '100%'}),
    ], id='pnl-tab-content', style={
        'display': 'none', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto', 'overflowX': 'hidden',
    }),

    # ── SUMMARY TAB
    html.Div([
        html.Div([
            html.Label("Compare with:", style={'fontSize': '11px', 'color': '#666', 'marginRight': '8px', 'alignSelf': 'center'}),
            dcc.Dropdown(id='summary-snapshot-select', options=get_snapshot_options(),
                         value=get_latest_snapshot_value(), clearable=False,
                         style={'fontSize': '12px', 'width': '160px'}),
        ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '12px'}),
        html.Div(id='summary-table-div'),
    ], id='summary-tab-content', style={
        'display': 'none', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto', 'overflowX': 'hidden',
    }),

    # ── TRANSACTIONS TAB
    html.Div([
        html.Div([
            html.P('TRANSACTIONS', style={**SECTION_TITLE, 'marginBottom': '8px'}),
            html.Div([
                html.Div([
                    html.Label('Fund:', style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='txn-filter-fund', options=[], multi=True,
                                 placeholder='All funds...', style={'fontSize': '12px', 'minWidth': '200px'}),
                ], style={'marginRight': '16px'}),
                html.Div([
                    html.Label('From:', style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.DatePickerSingle(id='txn-filter-from', display_format='DD MMM YYYY', placeholder='Start date'),
                ], style={'marginRight': '16px'}),
                html.Div([
                    html.Label('To:', style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.DatePickerSingle(id='txn-filter-to', display_format='DD MMM YYYY', placeholder='End date'),
                ], style={'marginRight': '16px'}),
                html.Div([
                    html.Label('Type:', style={'fontSize': '11px', 'color': '#666', 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='txn-filter-type',
                                 options=[{'label': 'All', 'value': 'ALL'}, {'label': 'BUY', 'value': 'BUY'},
                                          {'label': 'SELL', 'value': 'SELL'}, {'label': 'DIVIDEND', 'value': 'DIVIDEND'}],
                                 value='ALL', clearable=False, style={'fontSize': '12px', 'width': '110px'}),
                ]),
            ], style={'display': 'flex', 'alignItems': 'flex-end', 'flexWrap': 'wrap', 'gap': '8px'}),
        ], style=CARD),
        html.Div(id='transactions-table-div', style={'overflowX': 'auto', 'width': '100%'}),
    ], id='transactions-tab-content', style={
        'display': 'none', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto', 'overflowX': 'hidden',
    }),

    # ── CHARTS TAB
    html.Div([
        html.Div([
            html.P('PORTFOLIO BREAKDOWN', style={**SECTION_TITLE, 'marginBottom': '4px'}),
            html.Span('Inner ring: Asset Type  |  Outer ring: Category within each asset type',
                      style={'fontSize': '11px', 'color': '#aaa'}),
            html.Div([
                html.Div([
                    dcc.Graph(id='sunburst-chart', config={'displayModeBar': False},
                              style={'height': '500px'}),
                ], style={'flex': '1'}),
                html.Div(id='charts-breakdown-div', style={
                    'flexShrink': '0', 'width': '380px', 'marginLeft': '12px',
                    'overflowY': 'auto', 'maxHeight': '500px',
                }),
            ], style={'display': 'flex', 'alignItems': 'flex-start'}),
        ], style=CARD),

        html.Div([
            html.P('NET WORTH HISTORY', style={**SECTION_TITLE, 'marginBottom': '4px'}),
            dcc.Graph(id='networth-history-chart', config={'displayModeBar': False}),
        ], style=CARD),

        html.Div([
            html.P('PORTFOLIO VALUE BY CATEGORY', style={**SECTION_TITLE, 'marginBottom': '4px'}),
            html.Span('Stacked area — categories below threshold grouped as Other',
                      style={'fontSize': '11px', 'color': '#aaa'}),
            dcc.Graph(id='portfolio-history-chart', config={'displayModeBar': False}),
        ], style=CARD),

    ], id='charts-tab-content', style={
        'display': 'none', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto', 'overflowX': 'hidden',
    }),

    # ── ACCOUNTS TAB
    html.Div([
        html.Div([
            html.P("ACCOUNT VIEW", style={**SECTION_TITLE, 'marginBottom': '0'}),
            html.Span(id='accounts-total-label', style={
                'fontSize': '20px', 'fontWeight': '700',
                'color': '#1a3a5c', 'letterSpacing': '0.02em',
            }),
        ], style={**CARD, 'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}),
        html.Div(id='accounts-table-div'),
    ], id='accounts-tab-content', style={
        'display': 'none', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto', 'overflowX': 'hidden',
    }),

    # Shared stores
    dcc.Store(id='sort-state-holdings', data={'col': 'YTD', 'asc': False}),
    dcc.Store(id='sort-state-market',   data={'col': 'YTD', 'asc': False}),
    dcc.Store(id='db-reload-trigger',   data=0),
    dcc.Store(id='portfolio-reload',    data=0),
    dcc.Interval(id='auto-refresh', interval=60*60*1000, n_intervals=0),

], style={
    'fontFamily': '"DM Sans", -apple-system, BlinkMacSystemFont, sans-serif',
    'backgroundColor': '#f0f3f7',
    'minHeight': '100vh',
    'overflowX': 'hidden',
})


# ── 4. TAB VISIBILITY ──────────────────────────────────────────

@app.callback(
    Output('portfolio-tab-content',    'style'),
    Output('pnl-tab-content',          'style'),
    Output('summary-tab-content',      'style'),
    Output('transactions-tab-content', 'style'),
    Output('charts-tab-content',       'style'),
    Output('accounts-tab-content',     'style'),
    Output('data-date-label',          'children'),
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
    base = {'padding': '12px 16px 16px 16px', 'maxWidth': '1400px', 'margin': '0 auto', 'overflowX': 'hidden'}
    show = {**base, 'display': 'block'}
    hide = {**base, 'display': 'none'}

    if tab == 'tab-portfolio':
        return show, hide, hide, hide, hide, hide, date_label
    elif tab == 'tab-pnl':
        return hide, show, hide, hide, hide, hide, date_label
    elif tab == 'tab-summary':
        return hide, hide, show, hide, hide, hide, date_label
    elif tab == 'tab-transactions':
        return hide, hide, hide, show, hide, hide, date_label
    elif tab == 'tab-charts':
        return hide, hide, hide, hide, show, hide, date_label
    elif tab == 'tab-accounts':
        return hide, hide, hide, hide, hide, show, date_label
    return show, hide, hide, hide, hide, hide, date_label



# ── 5. PORTFOLIO CALLBACKS ─────────────────────────────────────


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

    portfolio = [p for p in portfolio if not p['fund_id'].startswith('CASH:')]

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
                "SELECT SUM(value_gbp) FROM snapshot_cash WHERE snapshot_id = ?", (snap_id,)
            ).fetchone()
            snap_cash_total = cash_row[0] if cash_row and cash_row[0] else None
        snap_conn.close()

    if not portfolio:
        return html.P("No holdings yet.", style={'color': '#999', 'fontSize': '12px', 'padding': '12px'}), "£0.00", html.Div()

    snap_cols = ([f'{snap_label}', 'Chg', 'Chg %'] if snap_label else [])
    all_cols  = ['Fund', 'Category', 'CCY', 'Units', 'Price', 'Value', '%'] + snap_cols

    def th_style(i):
        base = {'backgroundColor': '#1a3a5c', 'color': 'white', 'padding': '6px 8px',
                'fontSize': '11px', 'fontWeight': '600', 'whiteSpace': 'nowrap', 'width': '1%'}
        return {**base, 'textAlign': 'left' if i == 0 else 'right'}

    header = html.Tr([html.Th(c, style=th_style(i)) for i, c in enumerate(all_cols)])

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
                price = None; gbp = None; value = None
        else:
            price = get_latest_price(df_combined, fid)
            gbp   = to_gbp(price, punit, curr, gbpusd, fx_rates) if price else None
            value = gbp * units if gbp is not None else None

        rows_data.append({
            'fund_id': fid, 'name': name, 'type': atype, 'category': cat,
            'currency': curr, 'units': units, 'price': price, 'gbp_price': gbp, 'value': value,
        })

    if cash_accounts:
        cash_total_gbp = calc_cash_total_gbp(cash_accounts, fx_rates)
        rows_data.append({
            'fund_id': 'CASH:TOTAL', 'name': 'Cash', 'type': 'Cash', 'category': 'Cash',
            'currency': 'GBP', 'units': cash_total_gbp, 'price': None, 'gbp_price': 1.0, 'value': cash_total_gbp,
        })
        if snap_cash_total is not None:
            snap_holdings['CASH:TOTAL'] = snap_cash_total

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
        fid   = r['fund_id']

        if r['fund_id'].startswith(('CASH:', 'ASSET:')):
            units_str = f"{units:,.0f}"
        elif units == int(units):
            units_str = f"{int(units):,}"
        else:
            units_str = f"{units:,.4f}".rstrip('0').rstrip('.')

        price = r['price']
        punit = instruments.get(fid, {}).get('price_unit', '')
        curr  = instruments.get(fid, {}).get('currency', '')
        if r['fund_id'] == 'CASH:TOTAL':
            price_str = 'Mixed'; units_str = f"{r['value']:,.0f}"
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
            html.Td(html.Span(ndisp, title=name), style={'padding': '5px 8px', 'fontSize': '12px', 'color': '#1a3a5c', 'whiteSpace': 'nowrap', 'width': '1%'}),
            html.Td(r['category'], style={'padding': '5px 8px', 'fontSize': '10px', 'textAlign': 'left', 'color': '#444', 'fontWeight': '500', 'whiteSpace': 'nowrap', 'width': '1%'}),
            html.Td(r['currency'], style={'padding': '5px 8px', 'fontSize': '11px', 'textAlign': 'right', 'color': '#666', 'width': '1%', 'whiteSpace': 'nowrap'}),
            html.Td(units_str, style={'padding': '5px 8px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'width': '1%', 'whiteSpace': 'nowrap'}),
            html.Td(price_str, style={'padding': '5px 8px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap'}),
            html.Td(f"{r['value']:,.0f}" if r['value'] else 'N/A', style={'padding': '5px 8px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600', 'color': '#1a3a5c', 'width': '1%', 'whiteSpace': 'nowrap'}),
            html.Td(f"{pct:.1f}%" if pct else 'N/A', style={'padding': '5px 8px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap'}),
        ] + ([
            html.Td(f"{snap_holdings.get(fid, 0):,.0f}" if snap_holdings.get(fid) else 'NEW',
                    style={'padding': '5px 8px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap'}),
            html.Td(f"{(r['value'] or 0):+,.0f}" if not snap_holdings.get(fid)
                    else f"{((r['value'] or 0) - snap_holdings[fid]):+,.0f}",
                    style={'padding': '5px 8px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600',
                           'color': '#1a7a1a' if (r['value'] or 0) >= snap_holdings.get(fid, 0) else '#c0392b', 'width': '1%', 'whiteSpace': 'nowrap'}),
            html.Td('NEW' if not snap_holdings.get(fid)
                    else ('SOLD' if not r['value']
                          else f"{((r['value'] / snap_holdings[fid] - 1) * 100):+.1f}%"
                               if snap_holdings[fid] > 0 else '—'),
                    style={'padding': '5px 8px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600',
                           'color': '#1a7a1a' if (r['value'] or 0) >= snap_holdings.get(fid, 0) else '#c0392b', 'width': '1%', 'whiteSpace': 'nowrap'}),
        ] if snap_label else []), style={'borderBottom': '1px solid #f0f3f7'}))

    snap_total   = sum(snap_holdings.values()) if snap_holdings else 0
    snap_change  = total - snap_total if snap_total else None
    snap_chg_pct = (snap_change / snap_total * 100) if snap_total else None
    chg_color    = '#1a7a1a' if (snap_change or 0) >= 0 else '#c0392b'

    rows.append(html.Tr([
        html.Td("TOTAL", colSpan=5, style={'padding': '8px 8px', 'fontSize': '12px', 'fontWeight': '700', 'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total:,.0f}", style={'padding': '8px 8px', 'fontSize': '12px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c'}),
        html.Td("100%", style={'padding': '8px 8px', 'fontSize': '11px', 'textAlign': 'center', 'color': '#666', 'borderTop': '2px solid #1a3a5c'}),
    ] + ([
        html.Td(f"{snap_total:,.0f}", style={'padding': '8px 8px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': '#555', 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{snap_change:+,.0f}" if snap_change is not None else '—', style={'padding': '8px 8px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': chg_color, 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{snap_chg_pct:+.1f}%" if snap_chg_pct is not None else '—', style={'padding': '8px 8px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': chg_color, 'borderTop': '2px solid #1a3a5c'}),
    ] if snap_label else [])))

    table = html.Div(
        html.Table([html.Thead(header), html.Tbody(rows)],
                   style={'width': '100%', 'borderCollapse': 'collapse', 'tableLayout': 'auto'}),
        style={**CARD, 'overflowX': 'auto', 'padding': '0'}
    )

    # Category breakdown
    cat_totals = defaultdict(float)
    for r in rows_data:
        if r['category']:
            cat_totals[r['category']] += (r['value'] or 0)

    snap_cat = {}
    if snap_label:
        try:
            _sc = sqlite3.connect(DB_PATH)
            _sr = _sc.execute("SELECT id FROM portfolio_snapshots WHERE snap_date = ?", (snapshot_date,)).fetchone()
            if _sr:
                snap_cat = {r[0]: r[1] for r in _sc.execute(
                    "SELECT category, value_gbp FROM snapshot_categories WHERE snapshot_id = ?", (_sr[0],)).fetchall()}
            _sc.close()
        except Exception:
            snap_cat = {}

    def cat_th_style(i):
        base = {'backgroundColor': '#1a3a5c', 'color': 'white', 'padding': '5px 6px',
                'fontSize': '10px', 'fontWeight': '600', 'whiteSpace': 'nowrap'}
        return {**base, 'textAlign': 'left' if i == 0 else 'right', 'width': '1%' if i > 0 else 'auto'}

    # Asset type breakdown
    asset_totals = defaultdict(float)
    for r in rows_data:
        if r.get('type'):
            asset_totals[r['type']] += (r['value'] or 0)

    snap_asset = {}
    if snap_label:
        try:
            _sc2 = sqlite3.connect(DB_PATH)
            _sr2 = _sc2.execute("SELECT id FROM portfolio_snapshots WHERE snap_date = ?", (snapshot_date,)).fetchone()
            if _sr2:
                snap_asset = {r[0]: r[1] for r in _sc2.execute("""
                    SELECT i.asset_type, SUM(sh.value_gbp)
                    FROM snapshot_holdings sh
                    JOIN instruments i ON sh.fund_id = i.fund_id
                    WHERE sh.snapshot_id = ?
                    GROUP BY i.asset_type
                    UNION ALL
                    SELECT 'Cash', SUM(value_gbp) FROM snapshot_cash WHERE snapshot_id = ?
                """, (_sr2[0], _sr2[0])).fetchall() if r[0]}
            _sc2.close()
        except Exception:
            snap_asset = {}

    asset_header = html.Tr([html.Th(c, style=cat_th_style(i)) for i, c in enumerate(
        ['Asset Type', 'Value £k', '%'] + ([snap_label, 'Chg'] if snap_label else []))])
    asset_rows = []
    all_assets = set(asset_totals.keys()) | set(snap_asset.keys())
    for atype, val in sorted([(a, asset_totals.get(a, 0)) for a in all_assets], key=lambda x: x[1], reverse=True):
        pct = val / total * 100 if total else 0
        snap_asset_val = snap_asset.get(atype, 0) if snap_asset else 0
        a_chg = (val - snap_asset_val) if snap_asset else None
        a_chg_color = '#1a7a1a' if (a_chg or 0) >= 0 else '#c0392b'
        asset_rows.append(html.Tr([
            html.Td(atype, style={'padding': '4px 6px', 'fontSize': '11px', 'color': '#1a3a5c', 'fontWeight': '500', 'whiteSpace': 'nowrap'}),
            html.Td(f"{val/1000:.1f}", style={'padding': '4px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600', 'width': '1%', 'whiteSpace': 'nowrap'}),
            html.Td(f"{pct:.1f}%", style={'padding': '4px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap'}),
        ] + ([
            html.Td(f"{snap_asset_val/1000:.1f}" if snap_asset_val else '—', style={'padding': '4px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap'}),
            html.Td(f"{a_chg/1000:+.1f}" if a_chg is not None else '—', style={'padding': '4px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600', 'color': a_chg_color, 'width': '1%', 'whiteSpace': 'nowrap'}),
        ] if snap_label else []), style={'borderBottom': '1px solid #f0f3f7'}))

    snap_asset_total = sum(snap_asset.values()) if snap_asset else 0
    asset_chg_total  = total - snap_asset_total if snap_asset_total else None
    asset_chg_color  = '#1a7a1a' if (asset_chg_total or 0) >= 0 else '#c0392b'
    asset_rows.append(html.Tr([
        html.Td("TOTAL", style={'padding': '6px 6px', 'fontSize': '11px', 'fontWeight': '700', 'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total/1000:.1f}", style={'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'borderTop': '2px solid #1a3a5c'}),
        html.Td("100%", style={'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'borderTop': '2px solid #1a3a5c'}),
    ] + ([
        html.Td(f"{snap_asset_total/1000:.1f}" if snap_asset_total else '—', style={'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{asset_chg_total/1000:+.1f}" if asset_chg_total is not None else '—', style={'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': asset_chg_color, 'borderTop': '2px solid #1a3a5c'}),
    ] if snap_label else [])))

    # Category rows
    cat_cols   = ['Category', 'Value £k', '%'] + ([snap_label, 'Chg'] if snap_label else [])
    cat_header = html.Tr([html.Th(c, style=cat_th_style(i)) for i, c in enumerate(cat_cols)])
    cat_rows   = []
    all_cats   = set(cat_totals.keys()) | set(snap_cat.keys())
    for cat, val in sorted([(c, cat_totals.get(c, 0)) for c in all_cats], key=lambda x: x[1], reverse=True):
        pct = val / total * 100 if total else 0
        snap_cat_val = snap_cat.get(cat, 0) if snap_cat else 0
        cat_chg      = (val - snap_cat_val) if snap_cat else None
        cat_chg_color= '#1a7a1a' if (cat_chg or 0) >= 0 else '#c0392b'
        cat_rows.append(html.Tr([
            html.Td(cat, style={'padding': '4px 6px', 'fontSize': '11px', 'color': '#1a3a5c', 'fontWeight': '500', 'whiteSpace': 'nowrap'}),
            html.Td(f"{val/1000:.1f}", style={'padding': '4px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600', 'width': '1%', 'whiteSpace': 'nowrap'}),
            html.Td(f"{pct:.1f}%", style={'padding': '4px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap'}),
        ] + ([
            html.Td(f"{snap_cat_val/1000:.1f}" if snap_cat_val else '—', style={'padding': '4px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap'}),
            html.Td(f"{cat_chg/1000:+.1f}" if cat_chg is not None else '—', style={'padding': '4px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600', 'color': cat_chg_color, 'width': '1%', 'whiteSpace': 'nowrap'}),
        ] if snap_label else []), style={'borderBottom': '1px solid #f0f3f7'}))

    snap_cat_total = sum(snap_cat.values()) if snap_cat else 0
    cat_chg_total  = total - snap_cat_total if snap_cat_total else None
    cat_chg_color  = '#1a7a1a' if (cat_chg_total or 0) >= 0 else '#c0392b'
    cat_rows.append(html.Tr([
        html.Td("TOTAL", style={'padding': '6px 6px', 'fontSize': '11px', 'fontWeight': '700', 'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total/1000:.1f}", style={'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c', 'width': '1%', 'whiteSpace': 'nowrap'}),
        html.Td("100%", style={'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right', 'color': '#666', 'borderTop': '2px solid #1a3a5c', 'width': '1%', 'whiteSpace': 'nowrap'}),
    ] + ([
        html.Td(f"{snap_cat_total/1000:.1f}" if snap_cat_total else '—', style={'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': '#555', 'borderTop': '2px solid #1a3a5c', 'width': '1%', 'whiteSpace': 'nowrap'}),
        html.Td(f"{cat_chg_total/1000:+.1f}" if cat_chg_total is not None else '—', style={'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': cat_chg_color, 'borderTop': '2px solid #1a3a5c', 'width': '1%', 'whiteSpace': 'nowrap'}),
    ] if snap_label else [])))

    cat_table = html.Div([
        html.P("BY CATEGORY  (£k)", style={**SECTION_TITLE, 'borderBottom': '1px solid #e0e0e0', 'paddingBottom': '4px'}),
        html.Table([html.Thead(cat_header), html.Tbody(cat_rows)],
                   style={'width': '100%', 'borderCollapse': 'collapse', 'tableLayout': 'auto'}),
        html.P("BY ASSET TYPE  (£k)", style={**SECTION_TITLE, 'borderBottom': '1px solid #e0e0e0', 'paddingBottom': '4px', 'marginTop': '16px'}),
        html.Table([html.Thead(asset_header), html.Tbody(asset_rows)],
                   style={'width': '100%', 'borderCollapse': 'collapse', 'tableLayout': 'auto'}),
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
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO portfolio_holdings (fund_id, units, updated_at) VALUES (?, ?, ?)",
            (fund_id, float(units), datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit(); conn.close()
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
        'padding': '6px 14px', 'fontSize': '11px', 'cursor': 'pointer', 'marginBottom': '8px',
    }
    return new_state, label, style


@app.callback(
    Output('pnl-compact',      'data'),
    Output('pnl-compact-btn',  'children'),
    Output('pnl-compact-btn',  'style'),
    Input('pnl-compact-btn',   'n_clicks'),
    State('pnl-compact',       'data'),
    prevent_initial_call=True,
)
def toggle_compact(n_clicks, compact):
    new_state = not compact
    label = "Full View" if new_state else "Compact View"
    style = {
        'backgroundColor': '#e67e22' if new_state else '#2E75B6',
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
    Input("pnl-compact",      "data"),
)
def update_pnl(tab, _, show_closed, compact):
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
    total_label   = ""

    def th(c, i):
        return html.Th(c, style={"backgroundColor": "#1a3a5c", "color": "white",
                                  "padding": "6px 10px", "fontSize": "11px", "fontWeight": "600",
                                  "textAlign": "left" if i == 0 else "right", "whiteSpace": "nowrap"})

    if compact:
        header = html.Tr([th(c, i) for i, c in enumerate(
            ["Fund", "Price", "1D", "1D %", "1W %", "1M %", "3M %", "YTD %"])])
    else:
        header = html.Tr([th(c, i) for i, c in enumerate(
            ["Fund", "Category", "Price", "Avg Cost", "Qty", "Value",
             "P&L", "P&L %", "1D", "1D %", "1W %", "1M %", "3M %", "YTD %"])])

    open_df   = pnl_df[pnl_df["Qty"] > 0]
    closed_df = pnl_df[pnl_df["Qty"] == 0]

    range_1d = range_1w = range_1m = range_3m = range_ytd = (0, 0)
    ret_lists = [[], [], [], [], []]
    _ytd = ytd_date()
    for fid in pnl_df["fund_id"]:
        for i, days in enumerate([1, 5, 21, 63, None]):
            r = calc_return(df_combined, fid, days_back=days) if days else calc_return(df_combined, fid, from_date=_ytd)
            if r is not None:
                ret_lists[i].append(r)
    range_1d  = (min(ret_lists[0]), max(ret_lists[0])) if ret_lists[0] else (0, 0)
    range_1w  = (min(ret_lists[1]), max(ret_lists[1])) if ret_lists[1] else (0, 0)
    range_1m  = (min(ret_lists[2]), max(ret_lists[2])) if ret_lists[2] else (0, 0)
    range_3m  = (min(ret_lists[3]), max(ret_lists[3])) if ret_lists[3] else (0, 0)
    range_ytd = (min(ret_lists[4]), max(ret_lists[4])) if ret_lists[4] else (0, 0)

    def fmt_num(value, symbol="", suffix=""):
        if value < 100:
            return f"{symbol}{value:,.2f}{suffix}"
        return f"{symbol}{value:,.0f}{suffix}"

    def format_native_price(price, fund_id):
        if price is None: return "—"
        inst  = instruments.get(fund_id, {})
        punit = inst.get("price_unit", "pound")
        curr  = inst.get("currency", "GBP")
        sym   = {"GBP": "£", "USD": "$", "TRY": "₺"}.get(curr, "")
        if punit == "pence": return fmt_num(price, suffix="p")
        elif punit == "point": return fmt_num(price)
        return fmt_num(price, symbol=sym)

    def make_rows(df_subset, is_closed=False, compact=compact):
        result = []
        for _, r in df_subset.iterrows():
            pnl     = r["PnL"]
            pnl_pct = r["PnL Pct"]
            color   = "#1a7a1a" if pnl and pnl >= 0 else "#c0392b"
            name    = r["Fund"]
            ndisp   = name if len(name) <= 35 else name[:35] + "…"
            fid     = r["fund_id"]
            cp      = get_latest_price(df_combined, fid)
            price_str = format_native_price(cp, fid) if cp else "—"
            inst    = instruments.get(fid, {})
            punit   = inst.get("price_unit", "pound")
            curr    = inst.get("currency", "GBP")
            avg_gbp = r["Avg Cost"]
            if r["Qty"] > 0 and avg_gbp > 0:
                if punit == "pence" and curr == "GBP":
                    avg_str = fmt_num(avg_gbp * 100, suffix="p")
                elif curr == "USD":
                    avg_str = fmt_num(avg_gbp * fx_rates.get("USD", 1.26), symbol="$")
                elif curr == "TRY":
                    avg_str = fmt_num(avg_gbp * fx_rates.get("TRY", 43.0), symbol="₺")
                else:
                    avg_str = fmt_num(avg_gbp, symbol="£")
            else:
                avg_str = "—"

            q = r["Qty"]
            if r["Qty"] > 0:
                qty_display = f"{q:,.2f}".rstrip("0").rstrip(".") if q < 100 else f"{q:,.0f}"
            else:
                qty_display = "—"
            val_display = f"{r['Current Value']:,.0f}" if r["Current Value"] else ("Closed" if r["Qty"] == 0 else "N/A")
            row_bg = "#fafafa" if is_closed else "transparent"

            r1d  = calc_return(df_combined, fid, days_back=1)
            r1w  = calc_return(df_combined, fid, days_back=5)
            r1m  = calc_return(df_combined, fid, days_back=21)
            r3m  = calc_return(df_combined, fid, days_back=63)
            rytd = calc_return(df_combined, fid, from_date=ytd_date())

            def ret_td(v, rng):
                return html.Td(f"{v:+.1f}%" if v is not None else "—",
                    style={"padding": "4px 8px", "fontSize": "11px", "textAlign": "center",
                           "fontWeight": "600", "fontFamily": "monospace",
                           "backgroundColor": heatmap_color(v, rng[0], rng[1]) if v is not None else "transparent",
                           "color": "#1a1a1a", "borderRadius": "3px"})

            if compact:
                cells = [
                    html.Td(html.Span(ndisp, title=name), style={"padding": "5px 10px", "fontSize": "12px", "color": "#1a3a5c", "whiteSpace": "nowrap"}),
                    html.Td(price_str, style={"padding": "5px 10px", "fontSize": "12px", "textAlign": "right", "fontFamily": "monospace", "color": "#555"}),
                    html.Td(f"{r['Current Value'] * r1d / 100:+,.0f}" if r["Current Value"] and r1d is not None else "—",
                            style={"padding": "4px 8px", "fontSize": "11px", "textAlign": "right", "fontFamily": "monospace",
                                   "fontWeight": "600", "color": "#1a7a1a" if (r1d or 0) >= 0 else "#c0392b"}),
                    ret_td(r1d, range_1d), ret_td(r1w, range_1w), ret_td(r1m, range_1m),
                    ret_td(r3m, range_3m), ret_td(rytd, range_ytd),
                ]
            else:
                cells = [
                    html.Td(html.Span(ndisp, title=name), style={"padding": "5px 10px", "fontSize": "12px", "color": "#1a3a5c", "whiteSpace": "nowrap"}),
                    html.Td(r["Category"], style={"padding": "5px 10px", "fontSize": "11px", "textAlign": "center", "color": "#666"}),
                    html.Td(price_str, style={"padding": "5px 10px", "fontSize": "12px", "textAlign": "right", "fontFamily": "monospace", "color": "#555"}),
                    html.Td(avg_str, style={"padding": "5px 10px", "fontSize": "12px", "textAlign": "right", "fontFamily": "monospace", "color": "#888"}),
                    html.Td(qty_display, style={"padding": "5px 10px", "fontSize": "12px", "textAlign": "right", "fontFamily": "monospace"}),
                    html.Td(val_display, style={"padding": "5px 10px", "fontSize": "12px", "textAlign": "right", "fontFamily": "monospace", "fontWeight": "600", "color": "#1a3a5c"}),
                    html.Td(f"{pnl:+,.0f}" if pnl is not None else "N/A",
                            style={"padding": "5px 10px", "fontSize": "12px", "textAlign": "right", "fontFamily": "monospace", "fontWeight": "700", "color": color}),
                    html.Td(f"{pnl_pct:+.1f}%" if pnl_pct is not None else "N/A",
                            style={"padding": "5px 10px", "fontSize": "12px", "textAlign": "right", "fontFamily": "monospace", "fontWeight": "600", "color": color}),
                    html.Td(f"{r['Current Value'] * r1d / 100:+,.0f}" if r["Current Value"] and r1d is not None else "—",
                            style={"padding": "4px 8px", "fontSize": "11px", "textAlign": "right", "fontFamily": "monospace",
                                   "fontWeight": "600", "color": "#1a7a1a" if (r1d or 0) >= 0 else "#c0392b"}),
                    ret_td(r1d, range_1d), ret_td(r1w, range_1w), ret_td(r1m, range_1m),
                    ret_td(r3m, range_3m), ret_td(rytd, range_ytd),
                ]
            result.append(html.Tr(cells, style={"borderBottom": "1px solid #f0f3f7", "backgroundColor": row_bg}))
        return result

    rows = make_rows(open_df)

    if not closed_df.empty:
        closed_pnl   = closed_df["PnL"].dropna().sum()
        closed_count = len(closed_df)
        c_color      = "#1a7a1a" if closed_pnl >= 0 else "#c0392b"
        if show_closed:
            rows.append(html.Tr([html.Td(f"CLOSED POSITIONS ({closed_count})", colSpan=8, style={
                "padding": "6px 10px", "fontSize": "11px", "fontWeight": "700",
                "color": "#666", "backgroundColor": "#f0f3f7", "borderTop": "1px solid #ddd"})]))
            rows.extend(make_rows(closed_df, is_closed=True))
        else:
            if compact:
                rows.append(html.Tr([
                    html.Td(f"Closed positions ({closed_count} instruments)", colSpan=8,
                            style={"padding": "5px 10px", "fontSize": "12px", "color": "#888", "fontStyle": "italic"}),
                ], style={"borderBottom": "1px solid #f0f3f7", "backgroundColor": "#fafafa"}))
            else:
                rows.append(html.Tr([
                    html.Td(f"Closed positions ({closed_count} instruments)", colSpan=5,
                            style={"padding": "5px 10px", "fontSize": "12px", "color": "#888", "fontStyle": "italic"}),
                    html.Td("Closed", style={"padding": "5px 10px", "textAlign": "right", "color": "#bbb", "fontSize": "12px"}),
                    html.Td(f"{closed_pnl:+,.0f}", style={"padding": "5px 10px", "fontSize": "12px",
                            "textAlign": "right", "fontFamily": "monospace", "fontWeight": "700", "color": c_color}),
                    html.Td("—", style={"padding": "5px 10px", "textAlign": "right", "color": "#bbb"}),
                    html.Td("—", style={"padding": "5px 10px", "textAlign": "right", "color": "#bbb"}),
                    html.Td("—", colSpan=5, style={"padding": "5px 10px", "textAlign": "right", "color": "#bbb"}),
                ], style={"borderBottom": "1px solid #f0f3f7", "backgroundColor": "#fafafa"}))
                
    total_1d_gbp = sum(
        r["Current Value"] * calc_return(df_combined, r["fund_id"], days_back=1) / 100
        for _, r in open_df.iterrows()
        if r["Current Value"] and calc_return(df_combined, r["fund_id"], days_back=1) is not None
    )
    d1_color = "#1a7a1a" if total_1d_gbp >= 0 else "#c0392b"

    tb = {"padding": "7px 10px", "fontSize": "12px", "textAlign": "right",
          "fontFamily": "monospace", "fontWeight": "700", "borderTop": "2px solid #1a3a5c"}

    if compact:
        rows.append(html.Tr([
            html.Td("TOTAL", style={**tb, "textAlign": "left"}),
            html.Td("", style={"borderTop": "2px solid #1a3a5c"}),
            html.Td(f"{total_1d_gbp:+,.0f}", style={**tb, "color": d1_color}),
            html.Td("", colSpan=5, style={"borderTop": "2px solid #1a3a5c"}),
        ]))
    else:
        rows.append(html.Tr([
            html.Td("TOTAL", colSpan=5, style={**tb, "textAlign": "left"}),
            html.Td(f"{total_value:,.0f}", style=tb),
            html.Td(f"{total_pnl:+,.0f}", style={**tb, "color": pnl_color}),
            html.Td(f"{total_pnl_pct:+.1f}%", style={**tb, "color": pnl_color}),
            html.Td(f"{total_1d_gbp:+,.0f}", style={**tb, "color": d1_color}),
            html.Td("", colSpan=5, style={"borderTop": "2px solid #1a3a5c"}),
        ]))

    table = html.Div(
        html.Table([html.Thead(header), html.Tbody(rows)], style={"width": "100%", "borderCollapse": "collapse"}),
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
    fx_val = 1.0; price_val = None
    is_div = ttype == 'DIVIDEND'
    price_disabled = is_div
    price_style = {'marginRight': '12px', 'opacity': '0.4' if is_div else '1'}
    if is_div:
        return fx_val, 1.0, price_disabled, price_style
    if fund_id and trade_date:
        inst  = instruments.get(fund_id, {})
        curr  = inst.get('currency', 'GBP')
        conn  = sqlite3.connect(DB_PATH)
        if curr == 'USD':
            row = conn.execute("SELECT close FROM prices WHERE fund_id = 'YF:GBPUSD=X' AND date <= ? ORDER BY date DESC LIMIT 1", (trade_date,)).fetchone()
            if row: fx_val = round(row[0], 4)
        elif curr == 'TRY':
            row = conn.execute("SELECT close FROM prices WHERE fund_id = 'YF:GBPTRY=X' AND date <= ? ORDER BY date DESC LIMIT 1", (trade_date,)).fetchone()
            if row: fx_val = round(row[0], 4)
        if not fund_id.startswith(('COMPOSITE:', 'CALC:', 'ASSET:', 'CASH:')):
            pr = conn.execute("SELECT close FROM prices WHERE fund_id = ? AND date <= ? ORDER BY date DESC LIMIT 1", (fund_id, trade_date)).fetchone()
            if pr: price_val = round(pr[0], 4)
        conn.close()
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
    conn.commit(); conn.close()
    name = instruments.get(fund_id, {}).get('name', fund_id)
    if is_div:
        div_gbp = float(qty) / float(fx_rate or 1.0)
        return f"✓ DIVIDEND {name} — {qty} received = £{div_gbp:,.2f} on {trade_date}", reload + 1, None, None
    else:
        new_units = recalc_portfolio_from_transactions(fund_id)
        return f"✓ {ttype} {qty} × {name} @ {price} on {trade_date} — Portfolio updated to {new_units:,.4f} units", reload + 1, None, None


def render_cash_table(accounts, fx_rates):
    if not accounts:
        return html.P("No cash accounts yet.", style={'color': '#999', 'fontSize': '12px', 'marginBottom': '8px'})
    header = html.Tr([html.Th(c, style={'backgroundColor': '#1a3a5c', 'color': 'white', 'padding': '5px 8px',
                                         'fontSize': '11px', 'fontWeight': '600',
                                         'textAlign': 'left' if i == 0 else 'right', 'whiteSpace': 'nowrap'})
                      for i, c in enumerate(['Account', 'CCY', 'Amount', 'GBP Value', ''])])
    rows = []; total_gbp = 0.0
    for idx, acc in enumerate(accounts):
        amount = float(acc.get('amount', 0)); curr = acc.get('currency', 'GBP')
        sym = {'GBP': '£', 'USD': '$', 'TRY': '₺'}.get(curr, '')
        gbp_val = amount if curr == 'GBP' else amount / fx_rates.get(curr, 1.0)
        total_gbp += gbp_val
        rows.append(html.Tr([
            html.Td(acc.get('name', ''), style={'padding': '4px 8px', 'fontSize': '12px', 'color': '#1a3a5c'}),
            html.Td(curr, style={'padding': '4px 8px', 'fontSize': '11px', 'textAlign': 'right', 'color': '#666'}),
            html.Td(f"{sym}{amount:,.0f}", style={'padding': '4px 8px', 'fontSize': '12px', 'textAlign': 'right', 'fontFamily': 'monospace'}),
            html.Td(f"{gbp_val:,.0f}", style={'padding': '4px 8px', 'fontSize': '12px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600', 'color': '#1a3a5c'}),
            html.Td(html.Button("✕", id={'type': 'cash-remove-btn', 'index': acc.get('id', idx)}, n_clicks=0,
                                style={'backgroundColor': 'transparent', 'color': '#c0392b', 'border': 'none',
                                       'cursor': 'pointer', 'fontSize': '12px', 'padding': '2px 6px'}),
                    style={'padding': '4px 4px', 'textAlign': 'center'}),
        ], style={'borderBottom': '1px solid #f0f3f7'}))
    rows.append(html.Tr([
        html.Td("TOTAL", colSpan=3, style={'padding': '6px 8px', 'fontSize': '12px', 'fontWeight': '700', 'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total_gbp:,.0f}", style={'padding': '6px 8px', 'fontSize': '12px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c'}),
        html.Td("", style={'borderTop': '2px solid #1a3a5c'}),
    ]))
    return html.Table([html.Thead(header), html.Tbody(rows)], style={'width': '100%', 'borderCollapse': 'collapse'})


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
    fx_rates = get_fx_rates(df); accounts = load_cash_accounts(); triggered = ctx.triggered_id
    if triggered == 'cash-add-btn':
        if name and amount:
            add_cash_account(name, currency or 'GBP', float(amount))
            return render_cash_table(load_cash_accounts(), fx_rates), f'✓ Added {name}', None, None
        return render_cash_table(accounts, fx_rates), 'Please enter name and amount.', name, amount
    if isinstance(triggered, dict) and triggered.get('type') == 'cash-remove-btn':
        remove_cash_account(triggered['index'])
        return render_cash_table(load_cash_accounts(), fx_rates), '✓ Removed account', name, amount
    return render_cash_table(accounts, fx_rates), '', name, amount


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

    snap_holdings = {}; snap_label = None
    if snapshot_date and snapshot_date != 'none':
        snap_conn = sqlite3.connect(DB_PATH)
        snap_row  = snap_conn.execute("SELECT id FROM portfolio_snapshots WHERE snap_date = ?", (snapshot_date,)).fetchone()
        if snap_row:
            snap_id = snap_row[0]
            snap_label = pd.Timestamp(snapshot_date).strftime('%d %b %Y')
            snap_holdings = {r[0]: r[1] for r in snap_conn.execute(
                "SELECT fund_id, value_gbp FROM snapshot_holdings WHERE snapshot_id = ?", (snap_id,)).fetchall()}
        snap_conn.close()

    cash_accounts = load_cash_accounts()
    portfolio = [p for p in portfolio if not p['fund_id'].startswith('CASH:')]
    if not portfolio and not cash_accounts:
        return html.P("No holdings found.", style={'color': '#999', 'fontSize': '14px'})

    rows_data = []
    for item in portfolio:
        fid = item['fund_id']; units = item.get('units', 0)
        inst = instruments.get(fid, {}); name = inst.get('name', fid)
        curr = inst.get('currency', '?'); punit = inst.get('price_unit', '?')
        if fid.startswith('CASH:') or fid.startswith('ASSET:'):
            effective_unit = 'point' if fid == 'CASH:TRY' else punit
            gbp = to_gbp(1.0, effective_unit, curr, gbpusd, fx_rates)
            value = gbp * units if gbp else None
        elif fid.startswith('COMPOSITE:'):
            comp_def = next((c for c in getattr(config, 'COMPOSITE_FUNDS', []) if c['fund_id'] == fid), None)
            if comp_def:
                weighted_gbp = 0.0
                for c in comp_def['components']:
                    c_price = get_latest_price(df_combined, c['fund_id'])
                    c_inst  = instruments.get(c['fund_id'], {})
                    c_gbp   = to_gbp(c_price, c_inst.get('price_unit','pence'),
                                     c_inst.get('currency','GBP'), gbpusd, fx_rates)
                    if c_gbp is not None:
                        weighted_gbp += c_gbp * c['weight']
                value = weighted_gbp * units if weighted_gbp > 0 else None
            else:
                value = None
        else:
            price = get_latest_price(df_combined, fid)
            gbp   = to_gbp(price, punit, curr, gbpusd, fx_rates) if price else None
            value = gbp * units if gbp else None
        rows_data.append({'fund_id': fid, 'name': name, 'value': value})

    if cash_accounts:
        rows_data.append({'fund_id': 'CASH:TOTAL', 'name': 'Cash', 'value': calc_cash_total_gbp(cash_accounts, fx_rates)})

    total = sum(r['value'] for r in rows_data if r['value'] is not None)
    chg_cols = (['Chg k', 'Chg %'] if snap_label else [])
    all_cols  = ['Fund', 'Value k', '%'] + chg_cols

    def sum_th(i, label):
        return html.Th(label, style={'backgroundColor': '#1a3a5c', 'color': 'white', 'padding': '8px 8px',
                                      'fontSize': '12px', 'fontWeight': '600', 'whiteSpace': 'nowrap',
                                      'textAlign': 'left' if i == 0 else 'right'},
                       className='sum-fund' if i == 0 else 'sum-num')

    header = html.Tr([sum_th(i, c) for i, c in enumerate(all_cols)])
    rows = []
    for r in sorted(rows_data, key=lambda x: x['value'] or 0, reverse=True):
        fid = r['fund_id']; value = r['value']; pct = (value / total * 100) if total and value else None
        name = r['name']; ndisp = name if len(name) <= 25 else name[:25] + '…'
        snap_val  = snap_holdings.get(fid)
        chg_gbp   = (value - snap_val) if snap_val and value else None
        chg_pct   = ((value / snap_val - 1) * 100) if snap_val and value and snap_val > 0 else None
        chg_color = '#1a7a1a' if (chg_gbp or 0) >= 0 else '#c0392b'
        cells = [
            html.Td(html.Span(ndisp, title=name), className='sum-fund', style={'padding': '7px 8px', 'fontSize': '13px', 'color': '#1a3a5c', 'overflow': 'hidden', 'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap'}),
            html.Td(f"{value/1000:.1f}" if value else 'N/A', className='sum-num', style={'padding': '7px 8px', 'fontSize': '13px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600', 'whiteSpace': 'nowrap'}),
            html.Td(f"{pct:.1f}%" if pct else 'N/A', className='sum-num', style={'padding': '7px 8px', 'fontSize': '12px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'whiteSpace': 'nowrap'}),
        ]
        if snap_label:
            cells += [
                html.Td(f"{chg_gbp/1000:+.1f}" if chg_gbp is not None else '—', className='sum-num', style={'padding': '7px 8px', 'fontSize': '12px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600', 'color': chg_color, 'whiteSpace': 'nowrap'}),
                html.Td(f"{chg_pct:+.1f}%" if chg_pct is not None else '—', className='sum-num', style={'padding': '7px 8px', 'fontSize': '12px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600', 'color': chg_color, 'whiteSpace': 'nowrap'}),
            ]
        rows.append(html.Tr(cells, style={'borderBottom': '1px solid #f0f3f7'}))

    snap_total = sum(snap_holdings.values()) if snap_holdings else 0
    chg_total  = (total - snap_total) if snap_total else None
    chg_pct_tot = ((total / snap_total - 1) * 100) if snap_total and snap_total > 0 else None
    tot_color = '#1a7a1a' if (chg_total or 0) >= 0 else '#c0392b'
    total_cells = [
        html.Td("TOTAL", style={'padding': '8px 8px', 'fontSize': '13px', 'fontWeight': '700', 'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total/1000:.1f}", style={'padding': '8px 8px', 'fontSize': '13px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c', 'whiteSpace': 'nowrap'}),
        html.Td("100%", style={'padding': '8px 8px', 'fontSize': '12px', 'textAlign': 'right', 'color': '#666', 'borderTop': '2px solid #1a3a5c'}),
    ]
    if snap_label:
        total_cells += [
            html.Td(f"{chg_total/1000:+.1f}" if chg_total is not None else '—', style={'padding': '8px 8px', 'fontSize': '12px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': tot_color, 'borderTop': '2px solid #1a3a5c', 'whiteSpace': 'nowrap'}),
            html.Td(f"{chg_pct_tot:+.1f}%" if chg_pct_tot is not None else '—', style={'padding': '8px 8px', 'fontSize': '12px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': tot_color, 'borderTop': '2px solid #1a3a5c', 'whiteSpace': 'nowrap'}),
        ]
    rows.append(html.Tr(total_cells))
    return html.Div(
        html.Table([html.Thead(header), html.Tbody(rows)], style={'width': '100%', 'borderCollapse': 'collapse', 'tableLayout': 'auto'}),
        style={**CARD, 'overflowX': 'auto', 'padding': '0'}
    )


# ── CHARTS CALLBACKS ──────────────────────────────────────────

@app.callback(
    Output('sunburst-chart',       'figure'),
    Output('charts-breakdown-div', 'children'),
    Input('portfolio-reload',      'data'),
    Input('main-tabs',             'value'),
)
def update_charts(reload, tab):
    if tab != 'tab-charts':
        return go.Figure(), html.Div()

    portfolio     = load_portfolio()
    cash_accounts = load_cash_accounts()
    gbpusd        = get_gbpusd(df)
    fx_rates      = get_fx_rates(df)
    portfolio     = [p for p in portfolio if not p['fund_id'].startswith('CASH:')]

    # Build data
    rows_data = []
    for item in portfolio:
        fid   = item['fund_id']
        units = item.get('units', 0)
        inst  = instruments.get(fid, {})
        atype = inst.get('asset_type', 'Other')
        cat   = inst.get('category', 'Other')
        curr  = inst.get('currency', 'GBP')
        punit = inst.get('price_unit', 'pound')

        if fid.startswith('CASH:') or fid.startswith('ASSET:'):
            effective_unit = 'point' if fid == 'CASH:TRY' else punit
            gbp   = to_gbp(1.0, effective_unit, curr, gbpusd, fx_rates)
            value = gbp * units if gbp else None
        elif fid.startswith('COMPOSITE:'):
            comp_def = next((c for c in getattr(config, 'COMPOSITE_FUNDS', []) if c['fund_id'] == fid), None)
            if comp_def:
                weighted_gbp = 0.0
                for c in comp_def['components']:
                    c_price = get_latest_price(df_combined, c['fund_id'])
                    c_inst  = instruments.get(c['fund_id'], {})
                    c_gbp   = to_gbp(c_price, c_inst.get('price_unit','pence'),
                                     c_inst.get('currency','GBP'), gbpusd, fx_rates)
                    if c_gbp is not None:
                        weighted_gbp += c_gbp * c['weight']
                value = weighted_gbp * units if weighted_gbp > 0 else None
            else:
                value = None
        else:
            price = get_latest_price(df_combined, fid)
            gbp   = to_gbp(price, punit, curr, gbpusd, fx_rates) if price else None
            value = gbp * units if gbp else None

        if value:
            rows_data.append({'asset_type': atype, 'category': cat, 'value': value})

    if cash_accounts:
        cash_total = calc_cash_total_gbp(cash_accounts, fx_rates)
        if cash_total:
            rows_data.append({'asset_type': 'Cash', 'category': 'Cash', 'value': cash_total})

    if not rows_data:
        return go.Figure(), html.Div()

    total = sum(r['value'] for r in rows_data)

    # Build sunburst data
    # Inner ring: asset types; outer ring: category within each asset type
    from collections import defaultdict
    asset_cat = defaultdict(lambda: defaultdict(float))
    for r in rows_data:
        asset_cat[r['asset_type']][r['category']] += r['value']

    labels  = ['Portfolio']
    parents = ['']
    values  = [total]
    colours = ['#1a3a5c']

    # Colour palette for asset types
    asset_colours = {
        'Fund':      '#2E75B6', 'ETF':       '#1a7a1a', 'Stock':    '#e67e22',
        'Gold':      '#f39c12', 'Commodity': '#8e44ad', 'Cash':     '#95a5a6',
        'Crypto':    '#2c3e50', 'House':     '#c0392b', 'Index':    '#16a085',
        'Asset':     '#7f8c8d', 'Other':     '#bdc3c7',
    }

    cat_colours = [
        '#3498db','#2ecc71','#e74c3c','#f39c12','#9b59b6','#1abc9c',
        '#e67e22','#34495e','#27ae60','#2980b9','#8e44ad','#d35400',
        '#c0392b','#16a085','#f1c40f','#7f8c8d','#95a5a6','#bdc3c7',
    ]
    cat_colour_map = {}
    ci = 0

    # Collect all asset type names to detect label conflicts
    asset_type_names = set(asset_cat.keys())

    for atype, cats in sorted(asset_cat.items(), key=lambda x: sum(x[1].values()), reverse=True):
        atype_total = sum(cats.values())
        labels.append(atype)
        parents.append('Portfolio')
        values.append(atype_total)
        colours.append(asset_colours.get(atype, '#aaa'))

        for cat, val in sorted(cats.items(), key=lambda x: x[1], reverse=True):
            # Make unique: if cat name clashes with any asset type or already in labels
            if cat in asset_type_names or cat in labels:
                display_label = f"{cat} ({atype})"
            else:
                display_label = cat
            labels.append(display_label)
            parents.append(atype)
            values.append(val)
            if cat not in cat_colour_map:
                cat_colour_map[cat] = cat_colours[ci % len(cat_colours)]
                ci += 1
            colours.append(cat_colour_map[cat])

    fig = go.Figure(go.Sunburst(
        labels=labels,
        parents=parents,
        values=values,
        marker=dict(colors=colours),
        hovertemplate='<b>%{label}</b><br>£%{value:,.0f}<br>%{percentParent:.1%} of group | %{percentRoot:.1%} of total<extra></extra>',
        branchvalues='total',
        maxdepth=3,
        textinfo='label+percent parent',
        insidetextfont=dict(size=10),
        outsidetextfont=dict(size=10),
    ))
    fig.update_layout(
        height=480,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor='white',
    )

    # Breakdown tables (same as portfolio tab but for charts)
    def cat_th(i):
        base = {'backgroundColor': '#1a3a5c', 'color': 'white', 'padding': '5px 6px',
                'fontSize': '10px', 'fontWeight': '600', 'whiteSpace': 'nowrap'}
        return {**base, 'textAlign': 'left' if i == 0 else 'right', 'width': '1%' if i > 0 else 'auto'}

    # Asset type table
    asset_totals = defaultdict(float)
    for r in rows_data:
        asset_totals[r['asset_type']] += r['value']

    at_header = html.Tr([html.Th(c, style=cat_th(i)) for i, c in enumerate(['Asset Type', 'Value £k', '%'])])
    at_rows   = []
    for atype, val in sorted(asset_totals.items(), key=lambda x: x[1], reverse=True):
        pct = val / total * 100 if total else 0
        at_rows.append(html.Tr([
            html.Td(atype, style={'padding': '4px 6px', 'fontSize': '11px', 'color': '#1a3a5c', 'fontWeight': '500', 'whiteSpace': 'nowrap'}),
            html.Td(f"{val/1000:.1f}", style={'padding': '4px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600', 'width': '1%', 'whiteSpace': 'nowrap'}),
            html.Td(f"{pct:.1f}%", style={'padding': '4px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap'}),
        ], style={'borderBottom': '1px solid #f0f3f7'}))
    at_rows.append(html.Tr([
        html.Td("TOTAL", style={'padding': '6px 6px', 'fontSize': '11px', 'fontWeight': '700', 'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total/1000:.1f}", style={'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'borderTop': '2px solid #1a3a5c'}),
        html.Td("100%", style={'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'borderTop': '2px solid #1a3a5c'}),
    ]))

    # Category table
    cat_totals2 = defaultdict(float)
    for r in rows_data:
        cat_totals2[r['category']] += r['value']

    ct_header = html.Tr([html.Th(c, style=cat_th(i)) for i, c in enumerate(['Category', 'Value £k', '%'])])
    ct_rows   = []
    for cat, val in sorted(cat_totals2.items(), key=lambda x: x[1], reverse=True):
        pct = val / total * 100 if total else 0
        ct_rows.append(html.Tr([
            html.Td(cat, style={'padding': '4px 6px', 'fontSize': '11px', 'color': '#1a3a5c', 'fontWeight': '500', 'whiteSpace': 'nowrap'}),
            html.Td(f"{val/1000:.1f}", style={'padding': '4px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600', 'width': '1%', 'whiteSpace': 'nowrap'}),
            html.Td(f"{pct:.1f}%", style={'padding': '4px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'width': '1%', 'whiteSpace': 'nowrap'}),
        ], style={'borderBottom': '1px solid #f0f3f7'}))
    ct_rows.append(html.Tr([
        html.Td("TOTAL", style={'padding': '6px 6px', 'fontSize': '11px', 'fontWeight': '700', 'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total/1000:.1f}", style={'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'borderTop': '2px solid #1a3a5c'}),
        html.Td("100%", style={'padding': '6px 6px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555', 'borderTop': '2px solid #1a3a5c'}),
    ]))

    breakdown = html.Div([
        html.P("BY ASSET TYPE (£k)", style={'color': '#1a3a5c', 'fontSize': '11px', 'fontWeight': '700',
                                             'letterSpacing': '0.08em', 'textTransform': 'uppercase',
                                             'marginBottom': '6px', 'marginTop': '0'}),
        html.Table([html.Thead(at_header), html.Tbody(at_rows)],
                   style={'width': '100%', 'borderCollapse': 'collapse', 'marginBottom': '16px'}),
        html.P("BY CATEGORY (£k)", style={'color': '#1a3a5c', 'fontSize': '11px', 'fontWeight': '700',
                                           'letterSpacing': '0.08em', 'textTransform': 'uppercase',
                                           'marginBottom': '6px', 'marginTop': '0'}),
        html.Table([html.Thead(ct_header), html.Tbody(ct_rows)],
                   style={'width': '100%', 'borderCollapse': 'collapse'}),
    ])

    return fig, breakdown


@app.callback(
    Output('networth-history-chart', 'figure'),
    Input('portfolio-reload', 'data'),
    Input('main-tabs',        'value'),
)
def update_networth_chart(reload, tab):
    if tab != 'tab-charts':
        return go.Figure()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('SELECT date, total_gbp FROM networth_history ORDER BY date').fetchall()
    conn.close()
    if not rows:
        return go.Figure()
    df_nw = pd.DataFrame(rows, columns=['date', 'value'])
    df_nw['date'] = pd.to_datetime(df_nw['date'])
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_nw['date'], y=df_nw['value'], mode='lines+markers',
        name='Net Worth', line=dict(color='#1a3a5c', width=2),
        marker=dict(size=4, color='#1a3a5c'),
        hovertemplate='%{x|%b %Y}: £%{y:,.0f}<extra></extra>',
    ))
    fig.update_layout(
        height=320, hovermode='x unified', plot_bgcolor='white', paper_bgcolor='white',
        showlegend=False, margin=dict(l=50, r=20, t=20, b=40),
        yaxis=dict(showgrid=True, gridcolor='#f0f0f0',
                   tickvals=[v for v in range(0, 2000001, 250000)],
                   ticktext=[f'£{v//1000}k' for v in range(0, 2000001, 250000)]),
        xaxis=dict(showgrid=False, tickfont=dict(size=10)),
    )
    return fig


@app.callback(
    Output('portfolio-history-chart', 'figure'),
    Input('portfolio-reload', 'data'),
    Input('main-tabs',        'value'),
)
def update_portfolio_history_chart(reload, tab):
    if tab != 'tab-charts':
        return go.Figure()
    threshold = getattr(config, 'CHART_CATEGORY_THRESHOLD', 0.02)
    conn  = sqlite3.connect(DB_PATH)
    rows  = conn.execute("""
        SELECT ps.snap_date, sc.category, sc.value_gbp
        FROM snapshot_categories sc
        JOIN portfolio_snapshots ps ON sc.snapshot_id = ps.id
        ORDER BY ps.snap_date
    """).fetchall()
    conn.close()
    if not rows or len(set(r[0] for r in rows)) < 2:
        return go.Figure()
    df_snap = pd.DataFrame(rows, columns=['date', 'category', 'value_gbp'])
    df_snap['date'] = pd.to_datetime(df_snap['date'])
    pivot = df_snap.pivot_table(index='date', columns='category', values='value_gbp', aggfunc='sum').fillna(0)
    latest_total = pivot.iloc[-1].sum()
    if latest_total == 0:
        return go.Figure()
    latest_shares = pivot.iloc[-1] / latest_total
    above = [c for c in pivot.columns if latest_shares.get(c, 0) >= threshold]
    below = [c for c in pivot.columns if latest_shares.get(c, 0) < threshold]
    if below:
        pivot['Other'] = pivot[below].sum(axis=1)
    cols = sorted(above, key=lambda c: pivot[c].iloc[-1], reverse=True)
    if below:
        cols = cols + ['Other']
    colours = ['#2E75B6','#1a7a1a','#c0392b','#e67e22','#8e44ad','#16a085',
               '#2c3e50','#d35400','#27ae60','#2980b9','#f39c12','#7f8c8d',
               '#c0392b','#1abc9c','#e74c3c','#95a5a6']
    fig = go.Figure()
    for i, cat in enumerate(reversed(cols)):
        colour = colours[i % len(colours)]
        fig.add_trace(go.Scatter(
            x=pivot.index, y=pivot[cat], name=cat, mode='lines', stackgroup='one',
            line=dict(width=0.5, color=colour), fillcolor=colour,
            hovertemplate=f'<b>{cat}</b><br>%{{x|%d %b %Y}}: £%{{y:,.0f}}<extra></extra>',
        ))
    fig.update_layout(
        height=420, hovermode='x unified', plot_bgcolor='white', paper_bgcolor='white',
        legend=dict(orientation='h', y=-0.25, x=0, font=dict(size=10), traceorder='reversed'),
        margin=dict(l=50, r=20, t=30, b=100),
        yaxis=dict(tickformat=',.0f', tickprefix='£', ticksuffix='k', showgrid=True, gridcolor='#f0f0f0',
                   tickvals=[v for v in range(0, 2000001, 250000)],
                   ticktext=[f'£{v//1000}k' for v in range(0, 2000001, 250000)]),
        xaxis=dict(showgrid=False, tickfont=dict(size=10)),
    )
    return fig


# ── TRANSACTIONS CALLBACKS ────────────────────────────────────

@app.callback(
    Output('txn-filter-fund', 'options'),
    Input('main-tabs', 'value'),
)
def populate_fund_filter(tab):
    if tab != 'tab-transactions':
        return []
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT DISTINCT t.fund_id, i.name FROM transactions t
        LEFT JOIN instruments i ON t.fund_id = i.fund_id ORDER BY i.name
    """).fetchall()
    conn.close()
    return [{'label': r[1] or r[0], 'value': r[0]} for r in rows]


@app.callback(
    Output('transactions-table-div', 'children'),
    Input('main-tabs',        'value'),
    Input('txn-filter-fund',  'value'),
    Input('txn-filter-from',  'date'),
    Input('txn-filter-to',    'date'),
    Input('txn-filter-type',  'value'),
    Input('txn-status',       'children'),
)
def update_transactions_table(tab, funds, date_from, date_to, txn_type, _):
    if tab != 'tab-transactions':
        return html.Div()

    gbpusd   = get_gbpusd(df)
    fx_rates = get_fx_rates(df)
    conn  = sqlite3.connect(DB_PATH)
    query = """
        SELECT t.fund_id, t.trade_date, t.type, t.quantity, t.price,
               t.currency, t.fx_rate, i.name, i.price_unit
        FROM transactions t
        LEFT JOIN instruments i ON t.fund_id = i.fund_id WHERE 1=1
    """
    params = []
    if funds:
        placeholders = ','.join('?' * len(funds))
        query += f" AND t.fund_id IN ({placeholders})"; params += funds
    if date_from:
        query += " AND t.trade_date >= ?"; params.append(date_from)
    if date_to:
        query += " AND t.trade_date <= ?"; params.append(date_to)
    if txn_type and txn_type != 'ALL':
        query += " AND t.type = ?"; params.append(txn_type)
    query += " ORDER BY t.trade_date DESC, t.fund_id"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return html.P("No transactions found.", style={'color': '#999', 'fontSize': '12px', 'padding': '12px'})

    def fmt(val, symbol='', suffix='', decimals=2):
        if val is None: return '—'
        return f"{symbol}{val:,.0f}{suffix}" if abs(val) >= 100 else f"{symbol}{val:,.{decimals}f}{suffix}"

    def native_price_str(price, price_unit, currency):
        sym = {'GBP': '£', 'USD': '$', 'TRY': '₺'}.get(currency, '')
        if price_unit == 'pence': return fmt(price, suffix='p')
        return fmt(price, symbol=sym)

    header = html.Tr([
        html.Th(c, style={'backgroundColor': '#1a3a5c', 'color': 'white', 'padding': '6px 10px',
                          'fontSize': '11px', 'fontWeight': '600',
                          'textAlign': 'left' if i == 0 else 'right', 'whiteSpace': 'nowrap'})
        for i, c in enumerate(['Date', 'Fund', 'Type', 'Qty', 'Price', 'Cost GBP',
                                'Latest Price', 'Current Value GBP', 'P&L GBP'])
    ])

    table_rows = []; total_cost = 0.0; total_value = 0.0; total_pnl = 0.0

    for fid, trade_date, ttype, qty, price, currency, fx_rate, name, price_unit in rows:
        qty = float(qty); price = float(price); fx_rate = float(fx_rate) if fx_rate else 1.0
        inst = instruments.get(fid, {}); curr = inst.get('currency', currency or 'GBP')
        punit_inst = inst.get('price_unit', price_unit or 'pound')
        cost_per_unit = txn_price_to_gbp(price, currency, fx_rate, punit_inst)
        latest_raw = get_latest_price(df_combined, fid)
        latest_gbp = to_gbp(latest_raw, punit_inst, curr, gbpusd, fx_rates) if latest_raw else None
        latest_str = native_price_str(latest_raw, punit_inst, curr) if latest_raw else '—'

        if ttype == 'BUY':
            signed_qty = qty; signed_cost = -qty * cost_per_unit
            signed_value = latest_gbp * qty if latest_gbp is not None else None
            pnl = (signed_value + signed_cost) if signed_value is not None else None
        elif ttype == 'SELL':
            signed_qty = -qty; signed_cost = qty * cost_per_unit
            signed_value = -latest_gbp * qty if latest_gbp is not None else None
            pnl = (cost_per_unit - (latest_gbp or cost_per_unit)) * qty
        elif ttype == 'DIVIDEND':
            signed_qty = None; signed_cost = qty * cost_per_unit; signed_value = None; pnl = signed_cost
        else:
            signed_qty = qty; signed_cost = -qty * cost_per_unit
            signed_value = latest_gbp * qty if latest_gbp is not None else None; pnl = None

        pnl_color  = '#1a7a1a' if (pnl or 0) >= 0 else '#c0392b'
        cost_color = '#1a7a1a' if signed_cost >= 0 else '#c0392b'
        val_color  = '#1a7a1a' if (signed_value or 0) >= 0 else '#c0392b'
        type_color = {'BUY': '#2E75B6', 'SELL': '#c0392b', 'DIVIDEND': '#1a7a1a'}.get(ttype, '#333')

        total_cost += signed_cost
        if signed_value is not None: total_value += signed_value
        if pnl is not None: total_pnl += pnl

        ndisp = (name or fid); ndisp = ndisp if len(ndisp) <= 30 else ndisp[:30] + '…'

        def fmt_signed(val, decimals=0):
            if val is None: return '—'
            return f"{val:+,.{decimals}f}" if abs(val) >= 100 else f"{val:+,.2f}"

        def fmt_qty(val):
            if val is None: return '—'
            if val == int(val): return f"{int(val):+,}"
            return f"{val:+,.4f}".rstrip('0').rstrip('.')

        table_rows.append(html.Tr([
            html.Td(trade_date, style={'padding': '4px 10px', 'fontSize': '11px', 'color': '#555', 'whiteSpace': 'nowrap'}),
            html.Td(html.Span(ndisp, title=name or fid), style={'padding': '4px 10px', 'fontSize': '12px', 'color': '#1a3a5c', 'whiteSpace': 'nowrap'}),
            html.Td(ttype, style={'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right', 'fontWeight': '600', 'color': type_color}),
            html.Td(fmt_qty(signed_qty), style={'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555'}),
            html.Td(native_price_str(price, punit_inst, curr), style={'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555'}),
            html.Td(fmt_signed(signed_cost), style={'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600', 'color': cost_color}),
            html.Td(latest_str, style={'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': '#555'}),
            html.Td(fmt_signed(signed_value) if signed_value is not None else '—', style={'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'color': val_color}),
            html.Td(fmt_signed(pnl) if pnl is not None else '—', style={'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': pnl_color}),
        ], style={'borderBottom': '1px solid #f0f3f7'}))

    pnl_color_total  = '#1a7a1a' if total_pnl  >= 0 else '#c0392b'
    cost_color_total = '#1a7a1a' if total_cost  >= 0 else '#c0392b'
    val_color_total  = '#1a7a1a' if total_value >= 0 else '#c0392b'

    table_rows.append(html.Tr([
        html.Td('TOTAL', colSpan=5, style={'padding': '7px 10px', 'fontSize': '12px', 'fontWeight': '700', 'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total_cost:+,.0f}", style={'padding': '7px 10px', 'fontSize': '12px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': cost_color_total, 'borderTop': '2px solid #1a3a5c'}),
        html.Td('', style={'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total_value:+,.0f}", style={'padding': '7px 10px', 'fontSize': '12px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': val_color_total, 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total_pnl:+,.0f}", style={'padding': '7px 10px', 'fontSize': '12px', 'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '700', 'color': pnl_color_total, 'borderTop': '2px solid #1a3a5c'}),
    ]))

    return html.Div(
        html.Table([html.Thead(header), html.Tbody(table_rows)], style={'width': '100%', 'borderCollapse': 'collapse'}),
        style={**CARD, 'overflowX': 'auto', 'padding': '0'}
    )


# ── ACCOUNTS CALLBACK ───────────────────────────────────────────

@app.callback(
    Output('accounts-table-div',  'children'),
    Output('accounts-total-label','children'),
    Input('main-tabs',            'value'),
    Input('portfolio-reload',     'data'),
)
def update_accounts(tab, reload):
    if tab != 'tab-accounts':
        return html.Div(), ''

    gbpusd    = get_gbpusd(df)
    fx_rates  = get_fx_rates(df)
    portfolio = load_portfolio()
    portfolio = [p for p in portfolio if not p['fund_id'].startswith('CASH:')]
    cash_accs = load_cash_accounts()

    # Build P&L data per fund
    pnl_df = calc_pnl(df_combined, instruments, gbpusd, fx_rates)
    pnl_map = {}
    if not pnl_df.empty:
        for _, r in pnl_df.iterrows():
            pnl_map[r['fund_id']] = r

    # Get all transactions grouped by account+fund
    conn = sqlite3.connect(DB_PATH)
    txn_rows = conn.execute("""
        SELECT t.account, t.fund_id, i.name,
               SUM(CASE WHEN t.type='BUY'  THEN t.quantity ELSE 0 END) -
               SUM(CASE WHEN t.type='SELL' THEN t.quantity ELSE 0 END) as net_qty
        FROM transactions t
        LEFT JOIN instruments i ON t.fund_id = i.fund_id
        GROUP BY t.account, t.fund_id
        HAVING net_qty > 0.0001
        ORDER BY t.account, i.name
    """).fetchall()
    conn.close()

    # Add non-transaction holdings from config
    holding_accounts = getattr(config, 'HOLDING_ACCOUNTS', {})

    # Group by account
    from collections import defaultdict, OrderedDict
    account_holdings = defaultdict(list)
    for account, fid, name, net_qty in txn_rows:
        inst  = instruments.get(fid, {})
        cat   = inst.get('category', '—')
        curr  = inst.get('currency', 'GBP')
        punit = inst.get('price_unit', 'pound')

        if fid.startswith('COMPOSITE:'):
            comp_def = next((c for c in getattr(config, 'COMPOSITE_FUNDS', [])
                             if c['fund_id'] == fid), None)
            if comp_def:
                weighted_gbp = 0.0
                for c in comp_def['components']:
                    c_price = get_latest_price(df_combined, c['fund_id'])
                    c_inst  = instruments.get(c['fund_id'], {})
                    c_gbp   = to_gbp(c_price, c_inst.get('price_unit','pence'),
                                     c_inst.get('currency','GBP'), gbpusd, fx_rates)
                    if c_gbp is not None:
                        weighted_gbp += c_gbp * c['weight']
                price_gbp = weighted_gbp if weighted_gbp > 0 else None
            else:
                price_gbp = None
        elif fid.startswith('ASSET:'):
            price_gbp = 1.0
        else:
            raw = get_latest_price(df_combined, fid)
            price_gbp = to_gbp(raw, punit, curr, gbpusd, fx_rates) if raw else None

        value = price_gbp * net_qty if price_gbp else None

        # P&L from pnl_map
        pnl_r    = pnl_map.get(fid)
        cost_gbp = pnl_r['Cost Basis'] if pnl_r is not None else None
        pnl      = pnl_r['PnL']        if pnl_r is not None else None
        pnl_pct  = pnl_r['PnL Pct']   if pnl_r is not None else None

        account_holdings[account].append({
            'fid': fid, 'name': name or fid, 'category': cat,
            'qty': net_qty, 'value': value,
            'cost': cost_gbp, 'pnl': pnl, 'pnl_pct': pnl_pct,
        })

    # Add non-transaction holdings (pension funds, house etc.)
    for fid, account in holding_accounts.items():
        row = next((p for p in portfolio if p['fund_id'] == fid), None)
        if not row:
            continue
        units = row.get('units', 0)
        inst  = instruments.get(fid, {})
        name  = inst.get('name', fid)
        cat   = inst.get('category', '—')
        curr  = inst.get('currency', 'GBP')
        punit = inst.get('price_unit', 'pound')

        if fid.startswith('COMPOSITE:'):
            comp_def = next((c for c in getattr(config, 'COMPOSITE_FUNDS', [])
                             if c['fund_id'] == fid), None)
            if comp_def:
                weighted_gbp = 0.0
                for c in comp_def['components']:
                    c_price = get_latest_price(df_combined, c['fund_id'])
                    c_inst  = instruments.get(c['fund_id'], {})
                    c_gbp   = to_gbp(c_price, c_inst.get('price_unit','pence'),
                                     c_inst.get('currency','GBP'), gbpusd, fx_rates)
                    if c_gbp is not None:
                        weighted_gbp += c_gbp * c['weight']
                price_gbp = weighted_gbp if weighted_gbp > 0 else None
            else:
                price_gbp = None
        elif fid.startswith('ASSET:'):
            price_gbp = 1.0
        else:
            raw = get_latest_price(df_combined, fid)
            price_gbp = to_gbp(raw, punit, curr, gbpusd, fx_rates) if raw else None

        value = price_gbp * units if price_gbp else None
        account_holdings[account].append({
            'fid': fid, 'name': name, 'category': cat,
            'qty': units, 'value': value,
            'cost': None, 'pnl': None, 'pnl_pct': None,
        })

    # Cash by account name
    cash_by_account = defaultdict(list)
    for acc in cash_accs:
        cash_by_account[acc['name']].append(acc)

    # All unique accounts
    all_accounts = sorted(set(list(account_holdings.keys()) + list(cash_by_account.keys())))

    def th(c, i=1):
        return html.Th(c, style={
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '5px 8px', 'fontSize': '11px', 'fontWeight': '600',
            'whiteSpace': 'nowrap', 'textAlign': 'left' if i == 0 else 'right'})

    sections = []
    grand_total = 0.0

    for account in all_accounts:
        holdings = account_holdings.get(account, [])
        cashes   = cash_by_account.get(account, [])

        # Calculate account total
        hold_total = sum(h['value'] for h in holdings if h['value']) 
        cash_total_gbp = sum(
            a['amount'] if a['currency'] == 'GBP'
            else a['amount'] / fx_rates.get(a['currency'], 1.0)
            for a in cashes
        )
        acc_total = hold_total + cash_total_gbp
        grand_total += acc_total

        # Account header
        acc_color = '#2E75B6'
        rows = []

        # Holdings rows
        for h in sorted(holdings, key=lambda x: x['value'] or 0, reverse=True):
            pnl_color = '#1a7a1a' if (h['pnl'] or 0) >= 0 else '#c0392b'
            ndisp = h['name'] if len(h['name']) <= 35 else h['name'][:35] + '…'
            q = h['qty']
            qty_str = f"{q:,.0f}" if q == int(q) else f"{q:,.4f}".rstrip('0')

            rows.append(html.Tr([
                html.Td(html.Span(ndisp, title=h['name']),
                        style={'padding': '4px 8px', 'fontSize': '11px',
                               'color': '#1a3a5c', 'whiteSpace': 'nowrap'}),
                html.Td(h['category'],
                        style={'padding': '4px 8px', 'fontSize': '10px',
                               'color': '#666', 'whiteSpace': 'nowrap'}),
                html.Td(qty_str,
                        style={'padding': '4px 8px', 'fontSize': '11px',
                               'textAlign': 'right', 'fontFamily': 'monospace'}),
                html.Td(f"{h['value']:,.0f}" if h['value'] else '—',
                        style={'padding': '4px 8px', 'fontSize': '11px',
                               'textAlign': 'right', 'fontFamily': 'monospace',
                               'fontWeight': '600', 'color': '#1a3a5c'}),
                html.Td(f"{h['cost']:,.0f}" if h['cost'] else '—',
                        style={'padding': '4px 8px', 'fontSize': '11px',
                               'textAlign': 'right', 'fontFamily': 'monospace',
                               'color': '#888'}),
                html.Td(f"{h['pnl']:+,.0f}" if h['pnl'] is not None else '—',
                        style={'padding': '4px 8px', 'fontSize': '11px',
                               'textAlign': 'right', 'fontFamily': 'monospace',
                               'fontWeight': '700', 'color': pnl_color}),
                html.Td(f"{h['pnl_pct']:+.1f}%" if h['pnl_pct'] is not None else '—',
                        style={'padding': '4px 8px', 'fontSize': '11px',
                               'textAlign': 'right', 'fontFamily': 'monospace',
                               'color': pnl_color}),
            ], style={'borderBottom': '1px solid #f5f0ff'}))

        # Cash rows
        for a in cashes:
            amount  = float(a['amount'])
            curr    = a['currency']
            sym     = {'GBP': '£', 'USD': '$', 'TRY': '₺'}.get(curr, '')
            gbp_val = amount if curr == 'GBP' else amount / fx_rates.get(curr, 1.0)
            rows.append(html.Tr([
                html.Td(f"Cash ({curr})",
                        style={'padding': '4px 8px', 'fontSize': '11px',
                               'color': '#888', 'fontStyle': 'italic',
                               'whiteSpace': 'nowrap'}),
                html.Td('Cash',
                        style={'padding': '4px 8px', 'fontSize': '10px', 'color': '#aaa'}),
                html.Td('—', style={'padding': '4px 8px', 'textAlign': 'right'}),
                html.Td(f"{gbp_val:,.0f}",
                        style={'padding': '4px 8px', 'fontSize': '11px',
                               'textAlign': 'right', 'fontFamily': 'monospace',
                               'fontWeight': '600', 'color': '#1a3a5c'}),
                html.Td(f"{sym}{abs(amount):,.0f}",
                        style={'padding': '4px 8px', 'fontSize': '10px',
                               'textAlign': 'right', 'color': '#aaa',
                               'fontFamily': 'monospace'}),
                html.Td('—', style={'padding': '4px 8px', 'textAlign': 'right'}),
                html.Td('—', style={'padding': '4px 8px', 'textAlign': 'right'}),
            ], style={'borderBottom': '1px solid #f5f0ff',
                      'backgroundColor': '#fafafa'}))

        # Account total row
        rows.append(html.Tr([
            html.Td(f"{account} TOTAL", colSpan=3,
                    style={'padding': '6px 8px', 'fontSize': '12px',
                           'fontWeight': '700', 'color': acc_color,
                           'borderTop': '2px solid #e0e8f0'}),
            html.Td(f"{acc_total:,.0f}",
                    style={'padding': '6px 8px', 'fontSize': '12px',
                           'textAlign': 'right', 'fontFamily': 'monospace',
                           'fontWeight': '700', 'color': acc_color,
                           'borderTop': '2px solid #e0e8f0'}),
            html.Td('', colSpan=3,
                    style={'borderTop': '2px solid #e0e8f0'}),
        ]))

        header = html.Tr([
            th('Fund', 0), th('Category'), th('Qty'),
            th('Value £'), th('Cost £'), th('P&L £'), th('P&L %'),
        ])

        sections.append(html.Div([
            html.P(account, style={
                'color': acc_color, 'fontSize': '12px', 'fontWeight': '700',
                'letterSpacing': '0.06em', 'textTransform': 'uppercase',
                'marginBottom': '6px', 'marginTop': '0',
                'borderLeft': f'3px solid {acc_color}',
                'paddingLeft': '8px',
            }),
            html.Div(
                html.Table(
                    [html.Thead(header), html.Tbody(rows)],
                    style={'width': '100%', 'borderCollapse': 'collapse'}),
                style={'overflowX': 'auto'}),
        ], style={**CARD, 'marginBottom': '8px'}))

    # Grand total
    sections.append(html.Div([
        html.Div([
            html.Span("GRAND TOTAL",
                      style={'fontSize': '13px', 'fontWeight': '700', 'color': '#1a3a5c'}),
            html.Span(f"£{grand_total:,.0f}",
                      style={'fontSize': '16px', 'fontWeight': '700', 'color': '#1a3a5c',
                             'fontFamily': 'monospace'}),
        ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}),
    ], style=CARD))

    return html.Div(sections), f"{grand_total:,.0f}"



# ── 11. RUN ─────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)