"""
ETF Holdings Dashboard - Port 8053
Five tabs: Holdings, Overlap, Changes, Compare, Ticker Map
Canonical key: FIGI from stock_identifier_map
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
import json as _json
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dash import Dash, html, dcc, Input, Output, State, callback_context
import dash

DB_PATH = 'data/funds.db'
AUTO_APPROVE_THRESHOLD = 0.90

# ── STYLES ────────────────────────────────────────────────────────────────────
NAVY   = '#0f1e35'
BLUE   = '#1a3a5c'
ACCENT = '#2E75B6'
WHITE  = '#ffffff'
GREEN  = '#1a7a1a'
RED    = '#c0392b'
GREY   = '#f5f7fa'
ORANGE = '#e67e22'

CARD = {
    'backgroundColor': WHITE, 'borderRadius': '8px', 'padding': '16px',
    'marginBottom': '12px', 'boxShadow': '0 1px 4px rgba(0,0,0,0.08)',
}
SECTION_TITLE = {
    'fontSize': '11px', 'fontWeight': '700', 'letterSpacing': '0.08em',
    'color': BLUE, 'textTransform': 'uppercase', 'marginBottom': '10px', 'marginTop': '0',
}
TAB_STYLE     = {'backgroundColor': NAVY, 'color': '#aaa', 'border': 'none',
                 'padding': '10px 20px', 'fontSize': '12px', 'fontWeight': '600', 'letterSpacing': '0.05em'}
TAB_SELECTED  = {'backgroundColor': ACCENT, 'color': WHITE, 'border': 'none',
                 'padding': '10px 20px', 'fontSize': '12px', 'fontWeight': '600', 'letterSpacing': '0.05em'}
DROPDOWN_STYLE = {'fontSize': '12px', 'minWidth': '180px'}

# ── DB HELPERS ────────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def ensure_sources_table():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS etf_sources (
            etf_fund_id TEXT PRIMARY KEY,
            url         TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_etf_list():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT etf_fund_id FROM etf_holdings ORDER BY etf_fund_id").fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_dates_for_etf(etf_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT scraped_date FROM etf_holdings WHERE etf_fund_id=? ORDER BY scraped_date DESC",
        (etf_id,)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_latest_date(etf_id):
    dates = get_dates_for_etf(etf_id)
    return dates[0] if dates else None

def short_name(fund_id):
    return fund_id.replace('YF:', '').replace('.L', '')

# ── CONSOLIDATION ─────────────────────────────────────────────────────────────

def load_stock_map():
    """Load stock_identifier_map and build lookup dicts."""
    conn = get_conn()
    smap = pd.read_sql("""
        SELECT figi, name, bloomberg_code, base_ticker, raw_ticker,
               sedol, isin, yahoo_id, group_figi
        FROM stock_identifier_map
    """, conn)
    conn.close()
    # Build fast lookup dicts: identifier -> row index
    by_bloomberg = {}
    by_base      = {}
    by_raw       = {}
    by_sedol     = {}
    by_isin      = {}
    for idx, row in smap.iterrows():
        if row['bloomberg_code'] and str(row['bloomberg_code']) != 'nan':
            by_bloomberg[str(row['bloomberg_code']).upper().strip()] = idx
        if row['base_ticker'] and str(row['base_ticker']) != 'nan':
            by_base[str(row['base_ticker']).upper().strip()] = idx
        if row['raw_ticker'] and str(row['raw_ticker']) != 'nan':
            by_raw[str(row['raw_ticker']).upper().strip()] = idx
        if row['sedol'] and str(row['sedol']) != 'nan':
            by_sedol[str(row['sedol']).upper().strip()] = idx
        if row['isin'] and str(row['isin']) != 'nan':
            by_isin[str(row['isin']).upper().strip()] = idx
    return smap, by_bloomberg, by_base, by_raw, by_sedol, by_isin

def resolve_ticker(ticker, name, smap, by_bloomberg, by_base, by_raw, by_sedol, by_isin, isin=None):
    """Resolve a raw ticker to a group_figi. Returns (group_figi, canonical_name, yahoo_id)."""
    t  = str(ticker).strip().upper() if ticker else ''
    tb = t.split()[0] if t else ''
    idx = (by_bloomberg.get(t) or
           by_raw.get(t)       or
           by_base.get(t)      or
           (by_base.get(tb) if tb else None) or
           by_sedol.get(t)     or
           by_isin.get(t))
    # Fall back to ISIN lookup when ticker is blank/unmatched (e.g. Xtrackers)
    if idx is None and isin and str(isin).strip() and str(isin) != 'nan':
        idx = by_isin.get(str(isin).strip().upper())
    if idx is not None:
        s = smap.iloc[idx]
        # Use group_figi as canonical key — falls back to figi if not set
        gfigi = s['group_figi'] if s['group_figi'] and str(s['group_figi']) != 'nan' else s['figi']
        # Get canonical name from the parent record (where figi == group_figi)
        parent = smap[smap['figi'] == gfigi]
        cname  = parent.iloc[0]['name'] if not parent.empty and str(parent.iloc[0]['name']) != 'nan' else (
                 str(s['name']) if s['name'] and str(s['name']) != 'nan' else name)
        yahoo  = parent.iloc[0]['yahoo_id'] if not parent.empty else s.get('yahoo_id')
        return str(gfigi), cname, yahoo
    isin_key = f"|{isin}" if isin else ""
    return f"RAW:{ticker}{isin_key}|{name}", name, None

def get_consolidated_holdings(etf_id, date):
    """
    Returns DataFrame with columns:
    figi, name, sector, asset_class, weight_pct, market_value,
    location, currency, canonical_id, yahoo_id
    Grouped by FIGI, weights summed.
    """
    conn = get_conn()
    raw = pd.read_sql("""
        SELECT name, ticker, sector, asset_class,
               weight_pct, market_value, location, currency, isin
        FROM etf_holdings
        WHERE etf_fund_id = ? AND scraped_date = ?
    """, conn, params=(etf_id, date))
    conn.close()

    if raw.empty:
        return raw

    smap, by_bloomberg, by_base, by_raw, by_sedol, by_isin = load_stock_map()

    def resolve_row(row):
        figi, cname, yahoo_id = resolve_ticker(
            row['ticker'], row['name'], smap, by_bloomberg, by_base, by_raw, by_sedol, by_isin,
            isin=row.get('isin'))
        return pd.Series({'canonical_id': figi, 'canonical_name': cname, 'yahoo_id': yahoo_id})

    extra = raw.apply(resolve_row, axis=1)
    df    = pd.concat([raw, extra], axis=1)

    def agg_group(g):
        heaviest = g.loc[g['weight_pct'].idxmax()]
        return pd.Series({
            'name':         heaviest['canonical_name'],
            'sector':       heaviest['sector'],
            'asset_class':  heaviest['asset_class'],
            'weight_pct':   g['weight_pct'].sum(),
            'market_value': g['market_value'].sum() if g['market_value'].notna().any() else None,
            'location':     heaviest['location'],
            'currency':     heaviest['currency'],
            'canonical_id': g.name,
            'yahoo_id':     heaviest['yahoo_id'],
        })

    return (
        df.groupby('canonical_id', sort=False)
          .apply(agg_group)
          .reset_index(drop=True)
          .sort_values('weight_pct', ascending=False)
    )

# ── SHARED HELPERS ────────────────────────────────────────────────────────────

def th(text, align='left', width=None):
    style = {'backgroundColor': BLUE, 'color': WHITE, 'padding': '6px 10px',
             'fontSize': '11px', 'fontWeight': '600', 'textAlign': align, 'whiteSpace': 'nowrap'}
    if width:
        style['width'] = width
    return html.Th(text, style=style)

def safe_str(val):
    return str(val) if val and str(val) not in ('nan', 'None', '') else '—'

def fmt_w(w):
    try:
        return f"{float(w):.2f}%"
    except:
        return '—'

# ── APP INIT ──────────────────────────────────────────────────────────────────

app = Dash(__name__, suppress_callback_exceptions=True)
app.title = 'ETF Holdings'

try:
    from config import YAHOO_TICKERS
    ETF_NAME_MAP = {
        f"YF:{t[0]}": f"{t[0].replace('.L','').replace('.IS','')} — {t[1]}"
        for t in YAHOO_TICKERS if t[2] == 'ETF'
    }
    ETF_PROVIDER_DISPLAY = {
        f"YF:{t[0]}": (t[3] if len(t) == 4 else '—')
        for t in YAHOO_TICKERS if t[2] == 'ETF'
    }
except ImportError:
    ETF_NAME_MAP = {}
    ETF_PROVIDER_DISPLAY = {}

ensure_sources_table()
etf_list    = get_etf_list()
etf_options = [{'label': ETF_NAME_MAP.get(e, short_name(e)), 'value': e} for e in etf_list]
default_etf = etf_list[0] if etf_list else None

# ── LAYOUT ────────────────────────────────────────────────────────────────────

app.layout = html.Div([

    html.Div([
        html.Span('ETF HOLDINGS ANALYSER', style={
            'fontSize': '14px', 'fontWeight': '800', 'color': WHITE, 'letterSpacing': '0.12em'})
    ], style={'backgroundColor': NAVY, 'padding': '12px 20px', 'display': 'flex', 'alignItems': 'center'}),

    dcc.Tabs(id='etf-tabs', value='tab-holdings', children=[
        dcc.Tab(label='HOLDINGS',   value='tab-holdings',  style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label='OVERLAP',    value='tab-overlap',   style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label='CHANGES',    value='tab-changes',   style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label='COMPARE',    value='tab-compare',   style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label='TICKER MAP', value='tab-mapping',   style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label='SOURCES',    value='tab-sources',   style=TAB_STYLE, selected_style=TAB_SELECTED),
    ], style={'backgroundColor': NAVY}),

    # ── HOLDINGS TAB
    html.Div([
        html.Div([
            html.Div([
                html.Label('ETF', style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                         'display': 'block', 'marginBottom': '4px'}),
                dcc.Dropdown(id='h-etf', options=etf_options, value=default_etf,
                             clearable=False, style=DROPDOWN_STYLE),
            ], style={'marginRight': '16px'}),
            html.Div([
                html.Label('Date', style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                          'display': 'block', 'marginBottom': '4px'}),
                dcc.Dropdown(id='h-date', clearable=False, style=DROPDOWN_STYLE),
            ]),
        ], style={'display': 'flex', 'alignItems': 'flex-end', 'marginBottom': '12px'}),
        html.Div(id='h-summary-cards', style={'marginBottom': '12px'}),
        html.Div([html.P('PORTFOLIO COMPOSITION', style=SECTION_TITLE), html.Div(id='h-table')], style=CARD),
        html.Div([html.P('WEIGHT TREND — TOP 20 HOLDINGS OVER TIME', style=SECTION_TITLE),
                  dcc.Graph(id='h-heatmap', config={'displayModeBar': False})], style=CARD),
        html.Div([html.P('WEIGHT TREND — LINE CHART', style=SECTION_TITLE),
                  dcc.Graph(id='h-line', config={'displayModeBar': False})], style=CARD),
    ], id='tab-holdings-content', style={'display': 'none', 'padding': '16px', 'maxWidth': '1400px', 'margin': '0 auto'}),

    # ── OVERLAP TAB
    html.Div([
        html.Div([
            html.Label('Minimum ETFs', style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                              'display': 'block', 'marginBottom': '4px'}),
            dcc.Slider(id='o-min-etfs', min=2, max=5, step=1, value=2,
                       marks={i: str(i) for i in range(2, 6)}, tooltip={'placement': 'bottom'}),
        ], style={'marginBottom': '16px', 'maxWidth': '300px'}),
        html.Div([html.P('HOLDINGS APPEARING IN MULTIPLE ETFs', style=SECTION_TITLE),
                  html.Div(id='o-table')], style=CARD),
        html.Div([html.P('OVERLAP HEATMAP — WEIGHT % PER ETF', style=SECTION_TITLE),
                  dcc.Graph(id='o-heatmap', config={'displayModeBar': False})], style=CARD),
    ], id='tab-overlap-content', style={'display': 'none', 'padding': '16px', 'maxWidth': '1400px', 'margin': '0 auto'}),

    # ── CHANGES TAB
    html.Div([
        html.Div([
            html.Div([
                html.Label('ETF', style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                         'display': 'block', 'marginBottom': '4px'}),
                dcc.Dropdown(id='c-etf', options=etf_options, value=default_etf,
                             clearable=False, style=DROPDOWN_STYLE),
            ], style={'marginRight': '16px'}),
            html.Div([
                html.Label('From Date', style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                               'display': 'block', 'marginBottom': '4px'}),
                dcc.Dropdown(id='c-date-from', clearable=False, style=DROPDOWN_STYLE),
            ], style={'marginRight': '16px'}),
            html.Div([
                html.Label('To Date', style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                             'display': 'block', 'marginBottom': '4px'}),
                dcc.Dropdown(id='c-date-to', clearable=False, style=DROPDOWN_STYLE),
            ]),
        ], style={'display': 'flex', 'alignItems': 'flex-end', 'marginBottom': '12px'}),
        html.Div(id='c-content'),
    ], id='tab-changes-content', style={'display': 'none', 'padding': '16px', 'maxWidth': '1400px', 'margin': '0 auto'}),

    # ── COMPARE TAB
    html.Div([
        html.Div([
            html.Div([
                html.Label('ETF A', style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                           'display': 'block', 'marginBottom': '4px'}),
                dcc.Dropdown(id='cmp-etf-a', options=etf_options,
                             value=etf_list[0] if len(etf_list) > 0 else None,
                             clearable=False, style=DROPDOWN_STYLE),
            ], style={'marginRight': '16px'}),
            html.Div([
                html.Label('ETF B', style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                           'display': 'block', 'marginBottom': '4px'}),
                dcc.Dropdown(id='cmp-etf-b', options=etf_options,
                             value=etf_list[1] if len(etf_list) > 1 else None,
                             clearable=False, style=DROPDOWN_STYLE),
            ]),
            html.Div(id='cmp-date-info', style={
                'marginLeft': '24px', 'fontSize': '11px', 'color': '#888',
                'alignSelf': 'flex-end', 'paddingBottom': '6px'}),
        ], style={'display': 'flex', 'alignItems': 'flex-end', 'marginBottom': '16px'}),
        html.Div(id='cmp-summary-cards', style={'marginBottom': '12px'}),
        html.Div([
            html.Div([html.P(id='cmp-top10-a-title', style={**SECTION_TITLE, 'color': ACCENT}),
                      html.Div(id='cmp-top10-a')],
                     style={**CARD, 'flex': '1', 'marginRight': '8px', 'borderLeft': f'3px solid {ACCENT}'}),
            html.Div([html.P(id='cmp-top10-b-title', style={**SECTION_TITLE, 'color': ORANGE}),
                      html.Div(id='cmp-top10-b')],
                     style={**CARD, 'flex': '1', 'borderLeft': f'3px solid {ORANGE}'}),
        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '12px'}),
        html.Div([html.P('COMMON HOLDINGS — WEIGHT COMPARISON', style=SECTION_TITLE),
                  html.Div(id='cmp-common-table')], style=CARD),
        html.Div([
            html.Div([html.P(id='cmp-only-a-title', style={**SECTION_TITLE, 'color': ACCENT}),
                      html.Div(id='cmp-only-a')],
                     style={**CARD, 'flex': '1', 'marginRight': '8px', 'borderLeft': f'3px solid {ACCENT}'}),
            html.Div([html.P(id='cmp-only-b-title', style={**SECTION_TITLE, 'color': ORANGE}),
                      html.Div(id='cmp-only-b')],
                     style={**CARD, 'flex': '1', 'borderLeft': f'3px solid {ORANGE}'}),
        ], style={'display': 'flex', 'gap': '8px'}),
        html.Div([html.P('COMMON HOLDINGS HEATMAP', style=SECTION_TITLE),
                  dcc.Graph(id='cmp-heatmap', config={'displayModeBar': False})], style=CARD),
    ], id='tab-compare-content', style={'display': 'none', 'padding': '16px', 'maxWidth': '1400px', 'margin': '0 auto'}),

    # ── TICKER MAP TAB
    html.Div([
        html.Div([
            html.Div(id='map-summary', style={'flex': '1'}),
            html.Div([
                html.Label('Auto-approve threshold', style={'fontSize': '10px', 'color': '#888',
                           'fontWeight': '600', 'display': 'block', 'marginBottom': '4px'}),
                html.Div(dcc.Slider(id='map-threshold-slider', min=0.40, max=0.95, step=0.05,
                    value=0.90, marks={v: f'{v:.2f}' for v in [0.40, 0.60, 0.75, 0.85, 0.90, 0.95]},
                    tooltip={'placement': 'top', 'always_visible': True}),
                    style={'width': '280px', 'marginBottom': '8px'}),
                html.Button('AUTO-APPROVE', id='map-auto-approve-btn', n_clicks=0,
                    style={'backgroundColor': GREEN, 'color': WHITE, 'border': 'none',
                           'borderRadius': '4px', 'padding': '8px 16px', 'fontSize': '11px',
                           'fontWeight': '700', 'cursor': 'pointer', 'width': '100%'}),
            ], style={'textAlign': 'center', 'minWidth': '300px'}),
        ], style={**CARD, 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'}),

        html.Div([
            html.Div([
                html.Label('Show', style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                          'display': 'block', 'marginBottom': '4px'}),
                dcc.Dropdown(id='map-filter-status',
                    options=[
                        {'label': 'Unreviewed only',  'value': 'unreviewed'},
                        {'label': 'All records',      'value': 'all'},
                        {'label': 'Reviewed only',    'value': 'reviewed'},
                        {'label': 'Missing Yahoo ID', 'value': 'empty'},
                        {'label': 'Has Yahoo ID',     'value': 'has_yahoo'},
                    ],
                    value='unreviewed', clearable=False,
                    style={**DROPDOWN_STYLE, 'minWidth': '160px'}),
            ], style={'marginRight': '16px'}),
            html.Div([
                html.Label('Search name', style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                                 'display': 'block', 'marginBottom': '4px'}),
                dcc.Input(id='map-search', type='text', placeholder='Filter by name…', debounce=False,
                          style={'fontSize': '12px', 'padding': '6px 10px', 'border': '1px solid #ddd',
                                 'borderRadius': '4px', 'minWidth': '200px'}),
            ], style={'marginRight': '16px'}),
            html.Div([
                html.Label('Search Yahoo ID', style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                                     'display': 'block', 'marginBottom': '4px'}),
                dcc.Input(id='map-search-yahoo', type='text', placeholder='e.g. NVDA or .KS', debounce=False,
                          style={'fontSize': '12px', 'padding': '6px 10px', 'border': '1px solid #ddd',
                                 'borderRadius': '4px', 'minWidth': '160px'}),
            ], style={'marginRight': '16px'}),
            html.Div([
                html.Label('Search Group FIGI', style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                                       'display': 'block', 'marginBottom': '4px'}),
                dcc.Input(id='map-search-group', type='text', placeholder='e.g. BBG000BCY2S8', debounce=False,
                          style={'fontSize': '12px', 'padding': '6px 10px', 'border': '1px solid #ddd',
                                 'borderRadius': '4px', 'minWidth': '160px'}),
            ]),
        ], style={'display': 'flex', 'alignItems': 'flex-end', 'marginBottom': '12px'}),

        html.Div(id='map-edit-panel', style={'marginBottom': '12px'}),
        html.Div(id='map-feedback',   style={'marginBottom': '8px'}),
        html.Div([html.P('TICKER MAPPINGS', style=SECTION_TITLE), html.Div(id='map-table')], style=CARD),

        dcc.Store(id='map-selected-id',     data=None),
        dcc.Store(id='map-refresh-trigger', data=0),
        dcc.Store(id='map-figi-list',       data=[]),

    ], id='tab-mapping-content', style={'display': 'none', 'padding': '16px', 'maxWidth': '1400px', 'margin': '0 auto'}),

    # ── SOURCES TAB
    html.Div([
        html.Div([
            html.P('ETF DATA SOURCES', style=SECTION_TITLE),
            html.P('Edit the download URL for each ETF and click Save. Click "Open" to go to the provider page.',
                   style={'fontSize': '11px', 'color': '#888', 'marginBottom': '12px'}),
            html.Div(id='src-table'),
            html.Div(id='src-feedback', style={'marginTop': '8px'}),
        ], style=CARD),
        dcc.Store(id='src-refresh-trigger', data=0),
    ], id='tab-sources-content', style={'display': 'none', 'padding': '16px', 'maxWidth': '1400px', 'margin': '0 auto'}),

], style={'fontFamily': 'system-ui, -apple-system, sans-serif', 'backgroundColor': GREY, 'minHeight': '100vh'})


# ── TAB SWITCHER ──────────────────────────────────────────────────────────────

@app.callback(
    Output('tab-holdings-content', 'style'), Output('tab-overlap-content',  'style'),
    Output('tab-changes-content',  'style'), Output('tab-compare-content',  'style'),
    Output('tab-mapping-content',  'style'), Output('tab-sources-content', 'style'),
    Input('etf-tabs', 'value'),
)
def switch_tab(tab):
    show = {'display': 'block', 'padding': '16px', 'maxWidth': '1400px', 'margin': '0 auto'}
    hide = {'display': 'none',  'padding': '16px', 'maxWidth': '1400px', 'margin': '0 auto'}
    tabs = ['tab-holdings', 'tab-overlap', 'tab-changes', 'tab-compare', 'tab-mapping', 'tab-sources']
    return tuple(show if tab == t else hide for t in tabs)


# ── HOLDINGS CALLBACKS ────────────────────────────────────────────────────────

@app.callback(
    Output('h-date', 'options'), Output('h-date', 'value'),
    Input('h-etf', 'value'),
)
def update_h_dates(etf_id):
    if not etf_id:
        return [], None
    dates = get_dates_for_etf(etf_id)
    opts  = [{'label': d, 'value': d} for d in dates]
    return opts, dates[0] if dates else None


@app.callback(
    Output('h-summary-cards', 'children'),
    Output('h-table', 'children'), Output('h-heatmap', 'figure'), Output('h-line', 'figure'),
    Input('h-etf', 'value'), Input('h-date', 'value'),
)
def update_holdings(etf_id, date):
    empty_fig = go.Figure()
    empty_fig.update_layout(height=300, paper_bgcolor='white', plot_bgcolor='white',
        annotations=[dict(text='No data', showarrow=False, font=dict(size=14, color='#aaa'))])
    if not etf_id or not date:
        return html.Div(), html.Div('Select an ETF and date'), empty_fig, empty_fig

    df = get_consolidated_holdings(etf_id, date)
    if df.empty:
        return html.Div(), html.Div('No data'), empty_fig, empty_fig

    # Summary stats
    n_holdings   = len(df)
    top10_weight = df.sort_values('weight_pct', ascending=False).head(10)['weight_pct'].sum()
    top5_weight  = df.sort_values('weight_pct', ascending=False).head(5)['weight_pct'].sum()
    sector_sums  = df.groupby('sector')['weight_pct'].sum().sort_values(ascending=False)
    n_sectors    = df['sector'].nunique()
    top_sector   = sector_sums.index[0] if not sector_sums.empty else '—'
    top_sector_w = sector_sums.iloc[0] if not sector_sums.empty else 0
    largest_name = df.sort_values('weight_pct', ascending=False).iloc[0]['name']
    largest_w    = df['weight_pct'].max()

    def stat_card(label, value, sub, color):
        return html.Div([
            html.Div(value, style={'fontSize': '22px', 'fontWeight': '800', 'color': color}),
            html.Div(label, style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                   'textTransform': 'uppercase', 'letterSpacing': '0.06em'}),
            html.Div(sub or '', style={'fontSize': '10px', 'color': '#aaa', 'marginTop': '2px'}),
        ], style={'backgroundColor': WHITE, 'borderRadius': '8px', 'padding': '12px 20px',
                  'boxShadow': '0 1px 4px rgba(0,0,0,0.08)', 'textAlign': 'center', 'flex': '1'})

    summary_cards = html.Div([
        stat_card('Holdings', str(n_holdings), 'distinct positions', BLUE),
        stat_card('Top 5 Weight', f"{top5_weight:.1f}%", 'concentration', ACCENT),
        stat_card('Top 10 Weight', f"{top10_weight:.1f}%", 'concentration', ACCENT),
        stat_card('Sectors', str(n_sectors), f"largest: {top_sector[:18]}", BLUE),
        stat_card('Top Sector Weight', f"{top_sector_w:.1f}%", top_sector[:22], ORANGE),
        stat_card('Largest Position', f"{largest_w:.1f}%", largest_name[:22], ACCENT),
    ], style={'display': 'flex', 'gap': '10px', 'flexWrap': 'wrap'})

    max_w = df['weight_pct'].max() or 1
    rows  = []
    for i, (_, r) in enumerate(df.iterrows()):
        bg    = WHITE if i % 2 == 0 else '#f9fbfd'
        w     = r['weight_pct'] or 0
        bw    = f"{w / max_w * 100:.0f}%"
        figi  = str(r['canonical_id'])
        figi_short = figi[:16] + '…' if len(figi) > 16 else figi
        rows.append(html.Tr([
            html.Td(str(i+1), style={'padding': '4px 8px', 'fontSize': '11px', 'color': '#aaa', 'width': '30px'}),
            html.Td(figi_short, style={'padding': '4px 8px', 'fontSize': '10px', 'color': '#999',
                                       'fontFamily': 'monospace', 'width': '120px'}),
            html.Td(r['name'], style={'padding': '4px 8px', 'fontSize': '12px', 'color': BLUE, 'fontWeight': '500'}),
            html.Td(safe_str(r['sector']), style={'padding': '4px 8px', 'fontSize': '11px', 'color': '#888'}),
            html.Td([
                html.Div([
                    html.Div(style={'width': bw, 'height': '8px', 'backgroundColor': ACCENT,
                                    'borderRadius': '4px', 'display': 'inline-block'}),
                    html.Span(f" {w:.2f}%", style={'fontSize': '11px', 'color': BLUE,
                                                    'fontWeight': '600', 'marginLeft': '6px'}),
                ], style={'display': 'flex', 'alignItems': 'center'}),
            ], style={'padding': '4px 10px', 'minWidth': '150px'}),
        ], style={'backgroundColor': bg, 'borderBottom': '1px solid #f0f3f7'}))

    table = html.Div(
        html.Table([
            html.Thead(html.Tr([th('#'), th('FIGI'), th('Name'), th('Sector'), th('Weight %', 'right')])),
            html.Tbody(rows),
        ], style={'width': '100%', 'borderCollapse': 'collapse'}),
        style={'overflowX': 'auto'}
    )

    # Trend charts — use canonical_id as key
    conn  = get_conn()
    all_dates = get_dates_for_etf(etf_id)
    top20_ids = df.head(20)['canonical_id'].tolist()

    trend_rows = []
    smap, by_bloomberg, by_base, by_raw, by_sedol, by_isin = load_stock_map()
    for d in all_dates:
        df_d = get_consolidated_holdings(etf_id, d)
        for _, r in df_d[df_d['canonical_id'].isin(top20_ids)].iterrows():
            trend_rows.append({'date': d, 'canonical_id': r['canonical_id'],
                                'name': r['name'], 'weight_pct': r['weight_pct']})
    conn.close()

    heatmap_fig = empty_fig
    line_fig    = empty_fig

    if trend_rows:
        df_trend = pd.DataFrame(trend_rows)
        pivot    = df_trend.pivot_table(index='name', columns='date', values='weight_pct', aggfunc='mean')
        if date in pivot.columns:
            pivot = pivot.reindex(pivot[date].sort_values(ascending=True).index)
        else:
            pivot = pivot.reindex(pivot.iloc[:, -1].sort_values(ascending=True).index)

        heatmap_fig = go.Figure(go.Heatmap(
            z=pivot.values, x=[str(c)[:10] for c in pivot.columns],
            y=[n[:35] for n in pivot.index],
            colorscale=[[0, '#f0f7ff'], [0.5, ACCENT], [1.0, NAVY]],
            hovertemplate='<b>%{y}</b><br>%{x}<br>Weight: %{z:.2f}%<extra></extra>',
            showscale=True, colorbar=dict(title='Weight %', titleside='right', thickness=12),
        ))
        heatmap_fig.update_layout(
            height=max(300, len(top20_ids) * 30 + 80),
            margin=dict(l=220, r=60, t=20, b=60), paper_bgcolor='white', plot_bgcolor='white',
            xaxis=dict(tickangle=-45, tickfont=dict(size=10)), yaxis=dict(tickfont=dict(size=11)),
        )

        line_fig   = go.Figure()
        colors     = px.colors.qualitative.Set2 + px.colors.qualitative.Pastel
        for i, name in enumerate(reversed(pivot.index.tolist())):
            line_fig.add_trace(go.Scatter(
                x=[str(c)[:10] for c in pivot.columns], y=pivot.loc[name].values,
                mode='lines+markers', name=name[:30],
                line=dict(color=colors[i % len(colors)], width=2), marker=dict(size=5),
                hovertemplate=f'<b>{name[:30]}</b><br>%{{x}}<br>%{{y:.2f}}%<extra></extra>',
            ))
        line_fig.update_layout(
            height=400, margin=dict(l=40, r=180, t=20, b=60),
            paper_bgcolor='white', plot_bgcolor='white',
            legend=dict(font=dict(size=10), x=1.01, y=1),
            yaxis=dict(title='Weight %', gridcolor='#f0f3f7'),
            xaxis=dict(tickangle=-45, tickfont=dict(size=10), gridcolor='#f0f3f7'),
            hovermode='x unified',
        )

    return summary_cards, table, heatmap_fig, line_fig


# ── OVERLAP CALLBACKS ─────────────────────────────────────────────────────────

@app.callback(
    Output('o-table', 'children'), Output('o-heatmap', 'figure'),
    Input('o-min-etfs', 'value'),
)
def update_overlap(min_etfs):
    empty_fig = go.Figure()
    empty_fig.update_layout(height=300, paper_bgcolor='white',
        annotations=[dict(text='No data', showarrow=False, font=dict(size=14, color='#aaa'))])
    if not min_etfs:
        return html.Div(), empty_fig

    conn   = get_conn()
    latest = pd.read_sql(
        "SELECT etf_fund_id, MAX(scraped_date) as last_date FROM etf_holdings GROUP BY etf_fund_id", conn)
    conn.close()

    all_rows = []
    for _, row in latest.iterrows():
        df_e = get_consolidated_holdings(row['etf_fund_id'], row['last_date'])
        if not df_e.empty:
            df_e['etf_fund_id'] = row['etf_fund_id']
            all_rows.append(df_e)

    if not all_rows:
        return html.Div('No data'), empty_fig

    df_all     = pd.concat(all_rows, ignore_index=True)
    df_all     = df_all[df_all['weight_pct'] >= 0.5]
    figi_counts = df_all.groupby('canonical_id')['etf_fund_id'].nunique()
    overlap_ids = figi_counts[figi_counts >= min_etfs].index.tolist()

    if not overlap_ids:
        return html.Div(f'No holdings appear in {min_etfs}+ ETFs',
                        style={'color': '#aaa', 'fontSize': '13px', 'padding': '20px'}), empty_fig

    df_overlap = df_all[df_all['canonical_id'].isin(overlap_ids)].copy()
    summary    = df_overlap.groupby(['canonical_id', 'name']).agg(
        etf_count=('etf_fund_id', 'nunique'),
        etfs=('etf_fund_id', lambda x: ', '.join(sorted(set(short_name(e) for e in x)))),
        avg_weight=('weight_pct', 'mean'),
        max_weight=('weight_pct', 'max'),
    ).reset_index().sort_values('etf_count', ascending=False)

    rows = []
    for i, (_, r) in enumerate(summary.iterrows()):
        bg = WHITE if i % 2 == 0 else '#f9fbfd'
        rows.append(html.Tr([
            html.Td(str(r['canonical_id'])[:16], style={'padding': '4px 8px', 'fontSize': '10px',
                                                         'color': '#999', 'fontFamily': 'monospace'}),
            html.Td(r['name'], style={'padding': '4px 8px', 'fontSize': '12px', 'color': BLUE, 'fontWeight': '500'}),
            html.Td(str(int(r['etf_count'])), style={'padding': '4px 8px', 'fontSize': '12px',
                                                       'textAlign': 'center', 'fontWeight': '700', 'color': ACCENT}),
            html.Td(r['etfs'], style={'padding': '4px 8px', 'fontSize': '11px', 'color': '#555'}),
            html.Td(fmt_w(r['avg_weight']), style={'padding': '4px 8px', 'fontSize': '11px',
                                                    'textAlign': 'right', 'fontFamily': 'monospace'}),
            html.Td(fmt_w(r['max_weight']), style={'padding': '4px 8px', 'fontSize': '11px',
                                                    'textAlign': 'right', 'fontFamily': 'monospace', 'color': ACCENT}),
        ], style={'backgroundColor': bg, 'borderBottom': '1px solid #f0f3f7'}))

    table = html.Div(html.Table([
        html.Thead(html.Tr([th('FIGI'), th('Name'), th('# ETFs', 'center'),
                            th('ETFs'), th('Avg Weight', 'right'), th('Max Weight', 'right')])),
        html.Tbody(rows),
    ], style={'width': '100%', 'borderCollapse': 'collapse'}), style={'overflowX': 'auto'})

    top30      = summary.head(30)
    df_heat    = df_overlap[df_overlap['canonical_id'].isin(top30['canonical_id'])]
    name_map   = dict(zip(df_overlap['canonical_id'], df_overlap['name']))
    pivot      = df_heat.pivot_table(index='canonical_id', columns='etf_fund_id',
                                     values='weight_pct', aggfunc='mean').fillna(0)
    pivot.index = [name_map.get(i, i)[:35] for i in pivot.index]
    pivot.columns = [short_name(c) for c in pivot.columns]
    pivot      = pivot.reindex(pivot.sum(axis=1).sort_values(ascending=True).index)

    heat_fig = go.Figure(go.Heatmap(
        z=pivot.values, x=list(pivot.columns), y=list(pivot.index),
        colorscale=[[0, '#f0f7ff'], [0.3, ACCENT], [1.0, NAVY]],
        hovertemplate='<b>%{y}</b><br>%{x}<br>%{z:.2f}%<extra></extra>',
        showscale=True, colorbar=dict(title='Weight %', thickness=12),
    ))
    heat_fig.update_layout(
        height=max(400, len(top30) * 22 + 100),
        margin=dict(l=220, r=60, t=20, b=40), paper_bgcolor='white', plot_bgcolor='white',
        xaxis=dict(tickfont=dict(size=11)), yaxis=dict(tickfont=dict(size=10)),
    )
    return table, heat_fig


# ── CHANGES CALLBACKS ─────────────────────────────────────────────────────────

@app.callback(
    Output('c-date-from', 'options'), Output('c-date-from', 'value'),
    Output('c-date-to',   'options'), Output('c-date-to',   'value'),
    Input('c-etf', 'value'),
)
def update_c_dates(etf_id):
    if not etf_id:
        return [], None, [], None
    dates    = get_dates_for_etf(etf_id)
    opts     = [{'label': d, 'value': d} for d in dates]
    from_val = dates[1] if len(dates) > 1 else (dates[0] if dates else None)
    to_val   = dates[0] if dates else None
    return opts, from_val, opts, to_val


@app.callback(
    Output('c-content', 'children'),
    Input('c-etf', 'value'), Input('c-date-from', 'value'), Input('c-date-to', 'value'),
)
def update_changes(etf_id, date_from, date_to):
    if not etf_id or not date_from or not date_to or date_from == date_to:
        return html.Div('Select an ETF and two different dates.',
                        style={'color': '#aaa', 'fontSize': '13px', 'padding': '20px'})

    df_from = get_consolidated_holdings(etf_id, date_from)
    df_to   = get_consolidated_holdings(etf_id, date_to)

    df_from = df_from[df_from['weight_pct'] >= 0.5].set_index('canonical_id')
    df_to   = df_to[df_to['weight_pct'] >= 0.5].set_index('canonical_id')

    keys_from = set(df_from.index)
    keys_to   = set(df_to.index)
    new_pos   = keys_to - keys_from
    removed   = keys_from - keys_to
    common    = keys_from & keys_to
    increased = {k for k in common if df_to.loc[k, 'weight_pct'] > df_from.loc[k, 'weight_pct']}
    decreased = {k for k in common if df_to.loc[k, 'weight_pct'] < df_from.loc[k, 'weight_pct']}

    def get_w(df, k):
        v = df.loc[k, 'weight_pct']
        return float(v.iloc[0]) if hasattr(v, 'iloc') else float(v)

    def get_name(df, k):
        v = df.loc[k, 'name'] if k in df.index else k
        return str(v.iloc[0]) if hasattr(v, 'iloc') else str(v)

    def make_section(title, keys, df_new, df_old=None, color=BLUE):
        if not keys:
            return html.Div([html.P(f"{title} (0)", style={**SECTION_TITLE, 'color': color}),
                             html.P('None', style={'color': '#aaa', 'fontSize': '12px', 'margin': '0'})],
                            style={**CARD, 'borderLeft': f'3px solid {color}'})
        has_change = df_old is not None
        hdrs = ([th('FIGI'), th('Name'), th('From %', 'right'), th('To %', 'right'), th('Δ', 'right')]
                if has_change else [th('FIGI'), th('Name'), th('Weight %', 'right')])
        rows = []
        for k in sorted(keys, key=lambda k: -get_w(df_new, k)):
            w_new = get_w(df_new, k)
            name  = get_name(df_new, k)
            figi_short = k[:14] + '…' if len(k) > 14 else k
            if has_change and k in df_old.index:
                w_old = get_w(df_old, k)
                chg   = w_new - w_old
                rows.append(html.Tr([
                    html.Td(figi_short, style={'padding': '4px 8px', 'fontSize': '10px',
                                               'color': '#999', 'fontFamily': 'monospace'}),
                    html.Td(name, style={'padding': '4px 8px', 'fontSize': '12px', 'color': BLUE}),
                    html.Td(fmt_w(w_old), style={'padding': '4px 8px', 'fontSize': '11px',
                                                  'textAlign': 'right', 'color': '#888', 'fontFamily': 'monospace'}),
                    html.Td(fmt_w(w_new), style={'padding': '4px 8px', 'fontSize': '11px',
                                                  'textAlign': 'right', 'fontFamily': 'monospace', 'fontWeight': '600'}),
                    html.Td(f"{chg:+.2f}%", style={'padding': '4px 8px', 'fontSize': '11px',
                                                     'textAlign': 'right', 'fontFamily': 'monospace',
                                                     'fontWeight': '700', 'color': GREEN if chg > 0 else RED}),
                ], style={'borderBottom': '1px solid #f0f3f7'}))
            else:
                rows.append(html.Tr([
                    html.Td(figi_short, style={'padding': '4px 8px', 'fontSize': '10px',
                                               'color': '#999', 'fontFamily': 'monospace'}),
                    html.Td(name, style={'padding': '4px 8px', 'fontSize': '12px', 'color': BLUE}),
                    html.Td(fmt_w(w_new), style={'padding': '4px 8px', 'fontSize': '11px',
                                                  'textAlign': 'right', 'fontFamily': 'monospace',
                                                  'fontWeight': '600', 'color': color}),
                ], style={'borderBottom': '1px solid #f0f3f7'}))

        return html.Div([
            html.P(f"{title} ({len(keys)})", style={**SECTION_TITLE, 'color': color}),
            html.Div(html.Table([html.Thead(html.Tr(hdrs)), html.Tbody(rows)],
                                style={'width': '100%', 'borderCollapse': 'collapse'}),
                     style={'overflowX': 'auto'}),
        ], style={**CARD, 'borderLeft': f'3px solid {color}'})

    return html.Div([
        html.P(f"Comparing {short_name(etf_id)}: {date_from} → {date_to}",
               style={'fontSize': '12px', 'color': '#888', 'marginBottom': '12px'}),
        html.Div([
            html.Div(make_section('NEW POSITIONS', new_pos, df_to, color=GREEN),
                     style={'flex': '1', 'marginRight': '8px'}),
            html.Div(make_section('REMOVED POSITIONS', removed, df_from, color=RED),
                     style={'flex': '1'}),
        ], style={'display': 'flex', 'gap': '8px'}),
        html.Div([
            html.Div(make_section('INCREASED', increased, df_to, df_from, ACCENT),
                     style={'flex': '1', 'marginRight': '8px'}),
            html.Div(make_section('DECREASED', decreased, df_to, df_from, ORANGE),
                     style={'flex': '1'}),
        ], style={'display': 'flex', 'gap': '8px'}),
    ])


# ── COMPARE CALLBACKS ─────────────────────────────────────────────────────────

@app.callback(
    Output('cmp-date-info',     'children'),
    Output('cmp-summary-cards', 'children'),
    Output('cmp-top10-a-title', 'children'),
    Output('cmp-top10-a',       'children'),
    Output('cmp-top10-b-title', 'children'),
    Output('cmp-top10-b',       'children'),
    Output('cmp-common-table',  'children'),
    Output('cmp-only-a-title',  'children'),
    Output('cmp-only-a',        'children'),
    Output('cmp-only-b-title',  'children'),
    Output('cmp-only-b',        'children'),
    Output('cmp-heatmap',       'figure'),
    Input('cmp-etf-a', 'value'),
    Input('cmp-etf-b', 'value'),
)
def update_compare(etf_a, etf_b):
    empty_fig = go.Figure()
    empty_fig.update_layout(height=200, paper_bgcolor='white', plot_bgcolor='white',
        annotations=[dict(text='No data', showarrow=False, font=dict(size=14, color='#aaa'))])
    blank = html.Div('Select two ETFs to compare.',
                     style={'color': '#aaa', 'fontSize': '13px', 'padding': '20px'})

    if not etf_a or not etf_b or etf_a == etf_b:
        return ('Select two different ETFs', blank, 'Top 10 A', blank, 'Top 10 B', blank,
                blank, 'Only in A', blank, 'Only in B', blank, empty_fig)

    date_a = get_latest_date(etf_a)
    date_b = get_latest_date(etf_b)
    if not date_a or not date_b:
        return ('No data available', blank, 'Top 10 A', blank, 'Top 10 B', blank,
                blank, 'Only in A', blank, 'Only in B', blank, empty_fig)

    df_a = get_consolidated_holdings(etf_a, date_a)
    df_b = get_consolidated_holdings(etf_b, date_b)

    name_a = short_name(etf_a)
    name_b = short_name(etf_b)

    idx_a  = df_a.set_index('canonical_id')
    idx_b  = df_b.set_index('canonical_id')
    keys_a = set(idx_a.index)
    keys_b = set(idx_b.index)
    common = keys_a & keys_b
    only_a = keys_a - keys_b
    only_b = keys_b - keys_a

    def get_w(idx, k):
        v = idx.loc[k, 'weight_pct']
        return float(v.iloc[0]) if hasattr(v, 'iloc') else float(v)

    def get_val(idx, k, col):
        if k not in idx.index:
            return None
        v = idx.loc[k, col]
        return (v.iloc[0] if hasattr(v, 'iloc') else v)

    # Date info
    date_info = f"Latest snapshot — {name_a}: {date_a}  |  {name_b}: {date_b}"

    # Top 10 holdings by weight for each ETF
    top10_a_df = df_a.sort_values('weight_pct', ascending=False).head(10)
    top10_b_df = df_b.sort_values('weight_pct', ascending=False).head(10)
    top10_w_a  = top10_a_df['weight_pct'].sum()
    top10_w_b  = top10_b_df['weight_pct'].sum()

    # Summary cards
    # True overlap = sum of min(weight_a, weight_b) for each common holding
    overlap_weight = sum(min(get_w(idx_a, k), get_w(idx_b, k)) for k in common)

    def stat_card(label, value, sub, color):
        return html.Div([
            html.Div(value, style={'fontSize': '22px', 'fontWeight': '800', 'color': color}),
            html.Div(label, style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                   'textTransform': 'uppercase', 'letterSpacing': '0.06em'}),
            html.Div(sub or '', style={'fontSize': '10px', 'color': '#aaa', 'marginTop': '2px'}),
        ], style={'backgroundColor': WHITE, 'borderRadius': '8px', 'padding': '12px 20px',
                  'boxShadow': '0 1px 4px rgba(0,0,0,0.08)', 'textAlign': 'center', 'flex': '1'})

    summary_cards = html.Div([
        stat_card('Common Holdings', str(len(common)), 'appear in both ETFs', ACCENT),
        stat_card(f'Only in {name_a}', str(len(only_a)), f'{len(df_a)} total holdings', ACCENT),
        stat_card(f'Only in {name_b}', str(len(only_b)), f'{len(df_b)} total holdings', ORANGE),
        stat_card('Portfolio Overlap', f"{overlap_weight:.1f}%", 'sum of min(weight A, weight B)', BLUE),
        stat_card(f'Top 10 Weight — {name_a}', f"{top10_w_a:.1f}%", 'concentration of top 10', ACCENT),
        stat_card(f'Top 10 Weight — {name_b}', f"{top10_w_b:.1f}%", 'concentration of top 10', ORANGE),
    ], style={'display': 'flex', 'gap': '10px', 'marginBottom': '12px', 'flexWrap': 'wrap'})

    # Top 10 holdings tables
    def top10_table(df_top, color):
        if df_top.empty:
            return html.Div('None', style={'color': '#aaa', 'fontSize': '12px'})
        rows = []
        for i, (_, r) in enumerate(df_top.iterrows()):
            figi       = str(r['canonical_id'])
            figi_short = figi[:14] + '…' if len(figi) > 14 else figi
            rows.append(html.Tr([
                html.Td(str(i+1), style={'padding': '4px 8px', 'fontSize': '11px', 'color': '#aaa', 'width': '24px'}),
                html.Td(figi_short, style={'padding': '4px 8px', 'fontSize': '10px',
                                            'color': '#999', 'fontFamily': 'monospace'}),
                html.Td(r['name'], style={'padding': '4px 8px', 'fontSize': '12px', 'color': BLUE}),
                html.Td(fmt_w(r['weight_pct']), style={'padding': '4px 8px', 'fontSize': '11px',
                                                        'textAlign': 'right', 'fontFamily': 'monospace',
                                                        'fontWeight': '600', 'color': color}),
            ], style={'borderBottom': '1px solid #f0f3f7'}))
        return html.Div(html.Table([
            html.Thead(html.Tr([th('#'), th('FIGI'), th('Name'), th('Weight', 'right')])),
            html.Tbody(rows),
        ], style={'width': '100%', 'borderCollapse': 'collapse'}), style={'overflowX': 'auto'})

    top10_a_title = f'TOP 10 HOLDINGS — {name_a} ({top10_w_a:.1f}% of fund)'
    top10_b_title = f'TOP 10 HOLDINGS — {name_b} ({top10_w_b:.1f}% of fund)'

    # Common holdings table
    common_data = sorted([{
        'figi':     k,
        'name':     str(get_val(idx_a, k, 'name') or get_val(idx_b, k, 'name') or k),
        'sector':   str(get_val(idx_a, k, 'sector') or '—'),
        'weight_a': get_w(idx_a, k),
        'weight_b': get_w(idx_b, k),
        'diff':     get_w(idx_a, k) - get_w(idx_b, k),
    } for k in common], key=lambda x: -(x['weight_a'] + x['weight_b']) / 2)

    if common_data:
        max_w_c = max(max(r['weight_a'], r['weight_b']) for r in common_data) or 1

        def wbar(val, color):
            bw = f"{val / max_w_c * 100:.0f}%"
            return html.Div([
                html.Div(style={'width': bw, 'height': '7px', 'backgroundColor': color,
                                'borderRadius': '3px', 'display': 'inline-block'}),
                html.Span(f" {val:.2f}%", style={'fontSize': '11px', 'color': BLUE,
                                                   'fontWeight': '600', 'marginLeft': '5px'}),
            ], style={'display': 'flex', 'alignItems': 'center'})

        common_rows = []
        for i, r in enumerate(common_data):
            bg         = WHITE if i % 2 == 0 else '#f9fbfd'
            diff_color = GREEN if r['diff'] > 0 else RED if r['diff'] < 0 else '#888'
            figi_short = r['figi'][:14] + '…' if len(r['figi']) > 14 else r['figi']
            common_rows.append(html.Tr([
                html.Td(str(i+1), style={'padding': '4px 8px', 'fontSize': '11px', 'color': '#aaa', 'width': '28px'}),
                html.Td(figi_short, style={'padding': '4px 8px', 'fontSize': '10px',
                                            'color': '#999', 'fontFamily': 'monospace', 'width': '110px'}),
                html.Td(r['name'], style={'padding': '4px 8px', 'fontSize': '12px',
                                          'color': BLUE, 'fontWeight': '500'}),
                html.Td(r['sector'], style={'padding': '4px 8px', 'fontSize': '11px', 'color': '#888'}),
                html.Td(wbar(r['weight_a'], ACCENT), style={'padding': '4px 8px', 'minWidth': '130px'}),
                html.Td(wbar(r['weight_b'], ORANGE), style={'padding': '4px 8px', 'minWidth': '130px'}),
                html.Td(f"{r['diff']:+.2f}%", style={'padding': '4px 8px', 'fontSize': '11px',
                                                       'textAlign': 'right', 'fontFamily': 'monospace',
                                                       'fontWeight': '700', 'color': diff_color}),
            ], style={'backgroundColor': bg, 'borderBottom': '1px solid #f0f3f7'}))

        common_table = html.Div(html.Table([
            html.Thead(html.Tr([th('#'), th('FIGI'), th('Name'), th('Sector'),
                                th(f'{name_a} Weight'), th(f'{name_b} Weight'), th('A − B', 'right')])),
            html.Tbody(common_rows),
        ], style={'width': '100%', 'borderCollapse': 'collapse'}), style={'overflowX': 'auto'})
    else:
        common_table = html.Div('No common holdings found.',
                                style={'color': '#aaa', 'fontSize': '13px', 'padding': '12px'})

    # Only-in-A / Only-in-B tables
    def only_table(keys, idx, color):
        if not keys:
            return html.Div('None', style={'color': '#aaa', 'fontSize': '12px'})
        data = sorted([{
            'figi':   k,
            'name':   str(get_val(idx, k, 'name') or k),
            'weight': get_w(idx, k),
        } for k in keys], key=lambda x: -x['weight'])
        rows = []
        for r in data:
            figi_short = r['figi'][:14] + '…' if len(r['figi']) > 14 else r['figi']
            rows.append(html.Tr([
                html.Td(figi_short, style={'padding': '4px 8px', 'fontSize': '10px',
                                            'color': '#999', 'fontFamily': 'monospace'}),
                html.Td(r['name'], style={'padding': '4px 8px', 'fontSize': '12px', 'color': BLUE}),
                html.Td(fmt_w(r['weight']), style={'padding': '4px 8px', 'fontSize': '11px',
                                                    'textAlign': 'right', 'fontFamily': 'monospace',
                                                    'fontWeight': '600', 'color': color}),
            ], style={'borderBottom': '1px solid #f0f3f7'}))
        return html.Div(html.Table([
            html.Thead(html.Tr([th('FIGI'), th('Name'), th('Weight', 'right')])),
            html.Tbody(rows),
        ], style={'width': '100%', 'borderCollapse': 'collapse'}), style={'overflowX': 'auto'})

    only_a_title = f'ONLY IN {name_a} ({len(only_a)})'
    only_b_title = f'ONLY IN {name_b} ({len(only_b)})'

    # Heatmap
    if common_data:
        top30      = [r['name'] for r in common_data[:30]]
        hmap_data  = {name_a: {r['name']: r['weight_a'] for r in common_data if r['name'] in top30},
                      name_b: {r['name']: r['weight_b'] for r in common_data if r['name'] in top30}}
        pivot_df   = pd.DataFrame(hmap_data).fillna(0)
        pivot_df   = pivot_df.reindex(pivot_df.sum(axis=1).sort_values(ascending=True).index)
        cmp_heatmap = go.Figure(go.Heatmap(
            z=pivot_df.values, x=list(pivot_df.columns), y=[n[:35] for n in pivot_df.index],
            colorscale=[[0, '#f0f7ff'], [0.4, ACCENT], [1.0, NAVY]],
            hovertemplate='<b>%{y}</b><br>%{x}: %{z:.2f}%<extra></extra>',
            showscale=True, colorbar=dict(title='Weight %', thickness=12),
        ))
        cmp_heatmap.update_layout(
            height=max(300, len(top30) * 22 + 80),
            margin=dict(l=220, r=60, t=20, b=40), paper_bgcolor='white', plot_bgcolor='white',
            xaxis=dict(tickfont=dict(size=12, color=BLUE)), yaxis=dict(tickfont=dict(size=10)),
        )
    else:
        cmp_heatmap = empty_fig

    return (date_info, summary_cards,
            top10_a_title, top10_table(top10_a_df, ACCENT),
            top10_b_title, top10_table(top10_b_df, ORANGE),
            common_table,
            only_a_title, only_table(only_a, idx_a, ACCENT),
            only_b_title, only_table(only_b, idx_b, ORANGE),
            cmp_heatmap)


# ── TICKER MAP CALLBACKS ──────────────────────────────────────────────────────

def load_mapping_data(status_filter, search, search_yahoo, search_group=''):
    conn = get_conn()
    conditions, params = [], []

    if status_filter == 'unreviewed':
        conditions.append('s.reviewed = 0')
    elif status_filter == 'reviewed':
        conditions.append('s.reviewed = 1')
    elif status_filter == 'empty':
        conditions.append("(s.yahoo_id IS NULL OR s.yahoo_id = '')")
    elif status_filter == 'has_yahoo':
        conditions.append("(s.yahoo_id IS NOT NULL AND s.yahoo_id != '')")

    if search and str(search) not in ('', 'nan'):
        conditions.append("(LOWER(s.name) LIKE ? OR LOWER(s.bloomberg_code) LIKE ? OR LOWER(s.base_ticker) LIKE ?)")
        params += [f'%{str(search).lower()}%'] * 3

    if search_yahoo and str(search_yahoo) not in ('', 'nan'):
        conditions.append("LOWER(COALESCE(s.yahoo_id,'')) LIKE ?")
        params.append(f'%{str(search_yahoo).lower()}%')

    if search_group and str(search_group) not in ('', 'nan'):
        conditions.append("LOWER(COALESCE(s.group_figi,'')) LIKE ?")
        params.append(f'%{str(search_group).lower()}%')

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    query = f"""
        SELECT s.figi, s.name, s.base_ticker, s.exch_code, s.bloomberg_code,
               s.raw_ticker, s.sedol, s.isin, s.yahoo_id, s.security_type,
               s.group_figi, s.reviewed, s.notes,
               ROUND(MAX(h.weight_pct), 2) as max_weight
        FROM stock_identifier_map s
        LEFT JOIN etf_holdings h
            ON (UPPER(TRIM(h.ticker)) = s.bloomberg_code
                OR UPPER(TRIM(h.ticker)) = s.base_ticker
                OR UPPER(TRIM(h.ticker)) = s.raw_ticker
                OR UPPER(TRIM(h.ticker)) = s.sedol)
            AND h.scraped_date = (
                SELECT MAX(scraped_date) FROM etf_holdings WHERE etf_fund_id = h.etf_fund_id)
        {where}
        GROUP BY s.figi
        ORDER BY s.reviewed ASC, max_weight DESC NULLS LAST
    """

    df     = pd.read_sql(query, conn, params=params)
    totals = conn.execute("""
        SELECT COUNT(*),
               SUM(CASE WHEN reviewed=1 THEN 1 ELSE 0 END),
               SUM(CASE WHEN reviewed=0 THEN 1 ELSE 0 END)
        FROM stock_identifier_map
    """).fetchone()
    conn.close()
    return df, totals


@app.callback(
    Output('map-auto-approve-btn', 'children'),
    Input('map-threshold-slider', 'value'),
)
def update_btn_label(threshold):
    t = threshold or AUTO_APPROVE_THRESHOLD
    return f'AUTO-APPROVE ≥{t:.2f}'


@app.callback(
    Output('map-summary',        'children'),
    Output('map-table',          'children'),
    Output('map-feedback',       'children'),
    Output('map-figi-list',      'data'),
    Input('map-filter-status',   'value'),
    Input('map-search',          'value'),
    Input('map-search-yahoo',    'value'),
    Input('map-search-group',    'value'),
    Input('map-refresh-trigger', 'data'),
    Input('map-threshold-slider','value'),
)
def render_mapping_table(status_filter, search, search_yahoo, search_group, _trigger, threshold):
    df, totals = load_mapping_data(status_filter, search or '', search_yahoo or '', search_group or '')
    total, reviewed_count, unreviewed_count = totals

    summary = html.Div([
        html.Div([html.Span(str(total), style={'fontSize': '20px', 'fontWeight': '800', 'color': BLUE}),
                  html.Span(' total', style={'fontSize': '11px', 'color': '#888', 'marginLeft': '4px'})],
                 style={'marginRight': '24px'}),
        html.Div([html.Span(str(unreviewed_count), style={'fontSize': '20px', 'fontWeight': '800', 'color': ORANGE}),
                  html.Span(' unreviewed', style={'fontSize': '11px', 'color': '#888', 'marginLeft': '4px'})],
                 style={'marginRight': '24px'}),
        html.Div([html.Span(str(reviewed_count), style={'fontSize': '20px', 'fontWeight': '800', 'color': GREEN}),
                  html.Span(' reviewed', style={'fontSize': '11px', 'color': '#888', 'marginLeft': '4px'})]),
    ], style={'display': 'flex', 'alignItems': 'center'})

    if df.empty:
        return summary, html.Div('No records match the current filters.',
                                 style={'color': '#aaa', 'fontSize': '13px', 'padding': '20px'}), html.Div(), []

    rows = []
    for i, (_, r) in enumerate(df.iterrows()):
        bg            = WHITE if i % 2 == 0 else '#f9fbfd'
        reviewed      = bool(r['reviewed'])
        display_yahoo = str(r['yahoo_id']).replace('YF:', '') if r['yahoo_id'] and str(r['yahoo_id']) != 'nan' else '—'
        figi_short    = str(r['figi'])[:20] + '…' if len(str(r['figi'])) > 20 else str(r['figi'])
        gfigi         = str(r['group_figi']) if r.get('group_figi') and str(r.get('group_figi')) != 'nan' else str(r['figi'])
        gfigi_display = gfigi[:18] + '…' if len(gfigi) > 18 else gfigi
        is_child      = gfigi and gfigi != str(r['figi'])

        rows.append(html.Tr(
            id={'type': 'map-row', 'index': i},
            children=[
                html.Td('✓' if reviewed else '—',
                        style={'padding': '6px 8px', 'textAlign': 'center', 'width': '32px',
                               'color': GREEN if reviewed else '#ccc', 'fontWeight': '700', 'fontSize': '14px'}),
                html.Td(figi_short, style={'padding': '6px 8px', 'fontSize': '10px',
                                            'color': '#999', 'fontFamily': 'monospace', 'width': '140px'}),
                html.Td(safe_str(r['name']), style={'padding': '6px 8px', 'fontSize': '12px',
                                                     'color': BLUE, 'fontWeight': '500',
                                                     'maxWidth': '200px', 'overflow': 'hidden',
                                                     'textOverflow': 'ellipsis', 'whiteSpace': 'nowrap'}),
                html.Td(safe_str(r['bloomberg_code']), style={'padding': '6px 8px', 'fontSize': '11px',
                                                               'color': '#666', 'fontFamily': 'monospace'}),
                html.Td(safe_str(r.get('raw_ticker','')), style={'padding': '6px 8px', 'fontSize': '11px',
                                                                   'color': '#888', 'fontFamily': 'monospace'}),
                html.Td(safe_str(r['sedol']), style={'padding': '6px 8px', 'fontSize': '11px',
                                                      'color': '#aaa', 'fontFamily': 'monospace'}),
                html.Td(display_yahoo, style={'padding': '6px 8px', 'fontSize': '11px',
                                               'color': '#555', 'fontFamily': 'monospace'}),
                html.Td(gfigi_display,
                        style={'padding': '6px 8px', 'fontSize': '10px',
                               'color': ORANGE if is_child else '#aaa', 'fontFamily': 'monospace'}),
                html.Td(fmt_w(r['max_weight']) if r['max_weight'] is not None and str(r['max_weight']) != 'nan' else '—',
                        style={'padding': '6px 8px', 'fontSize': '11px', 'textAlign': 'right',
                               'fontFamily': 'monospace', 'fontWeight': '600',
                               'color': ACCENT if r['max_weight'] and r['max_weight'] >= 1.0 else '#888'}),
            ],
            style={'backgroundColor': bg, 'borderBottom': '1px solid #f0f3f7', 'cursor': 'pointer'},
            n_clicks=0,
        ))

    table = html.Div(html.Table([
        html.Thead(html.Tr([th('✓', 'center', '32px'), th('FIGI'), th('Name'),
                            th('Bloomberg'), th('Raw Ticker'), th('SEDOL'),
                            th('Yahoo ID'), th('Group FIGI'), th('Max Weight', 'right')])),
        html.Tbody(rows),
    ], style={'width': '100%', 'borderCollapse': 'collapse'}), style={'overflowX': 'auto'})

    figi_list = df['figi'].tolist()
    return summary, table, html.Div(), figi_list


@app.callback(
    Output('map-selected-id', 'data'),
    Input({'type': 'map-row', 'index': dash.ALL}, 'n_clicks'),
    State('map-figi-list', 'data'),
    prevent_initial_call=True,
)
def select_row(row_clicks, figi_list):
    ctx = callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    try:
        triggered = ctx.triggered[0]['prop_id'].split('.')[0]
        row_idx   = int(_json.loads(triggered)['index'])
        if figi_list and row_idx < len(figi_list):
            return figi_list[row_idx]
        return None
    except Exception:
        raise dash.exceptions.PreventUpdate


@app.callback(
    Output('map-edit-panel', 'children'),
    Input('map-selected-id',    'data'),
    Input('map-refresh-trigger', 'data'),
)
def render_edit_panel(selected_figi, _trigger):
    if not selected_figi:
        return html.Div()

    conn = get_conn()
    row  = conn.execute("""
        SELECT s.figi, s.name, s.base_ticker, s.exch_code, s.bloomberg_code,
               s.raw_ticker, s.sedol, s.isin, s.yahoo_id, s.security_type,
               s.group_figi, s.reviewed, s.notes,
               ROUND(MAX(h.weight_pct), 2) as max_weight
        FROM stock_identifier_map s
        LEFT JOIN etf_holdings h
            ON (UPPER(TRIM(h.ticker)) = s.bloomberg_code
                OR UPPER(TRIM(h.ticker)) = s.base_ticker
                OR UPPER(TRIM(h.ticker)) = s.raw_ticker
                OR UPPER(TRIM(h.ticker)) = s.sedol)
            AND h.scraped_date = (
                SELECT MAX(scraped_date) FROM etf_holdings WHERE etf_fund_id = h.etf_fund_id)
        WHERE s.figi = ?
        GROUP BY s.figi
    """, (selected_figi,)).fetchone()
    conn.close()

    if not row:
        return html.Div()

    figi, name, base_ticker, exch_code, bloomberg, raw_ticker, sedol, isin, yahoo_id, sec_type, group_figi, reviewed, notes, max_w = row
    display_yahoo  = str(yahoo_id).replace('YF:', '') if yahoo_id and str(yahoo_id) != 'nan' else ''
    # Show group_figi in edit box — blank means "same as figi" (standalone)
    display_group  = str(group_figi) if group_figi and str(group_figi) != 'nan' and str(group_figi) != figi else ''

    def inp(id_, val, placeholder, width='120px'):
        return dcc.Input(id=id_, value=val or '', placeholder=placeholder, debounce=False,
                         style={'fontSize': '12px', 'padding': '6px 8px', 'border': '1px solid #ddd',
                                'borderRadius': '4px', 'width': width})

    def lbl(text, child):
        return html.Div([
            html.Label(text, style={'fontSize': '10px', 'color': '#888', 'fontWeight': '600',
                                    'display': 'block', 'marginBottom': '4px'}),
            child,
        ], style={'marginRight': '10px'})

    return html.Div([
        html.P('EDIT MAPPING', style=SECTION_TITLE),
        html.Div([
            html.Span('Current FIGI: ', style={'fontSize': '10px', 'color': '#aaa'}),
            html.Span(figi, style={'fontSize': '11px', 'color': '#888', 'fontFamily': 'monospace', 'marginRight': '16px'}),
            html.Span('Type: ', style={'fontSize': '10px', 'color': '#aaa'}),
            html.Span(safe_str(sec_type), style={'fontSize': '11px', 'color': '#888', 'marginRight': '16px'}),
            html.Span('Max Weight: ', style={'fontSize': '10px', 'color': '#aaa'}),
            html.Span(fmt_w(max_w) if max_w else '—',
                      style={'fontSize': '11px', 'fontWeight': '700',
                             'color': ACCENT if max_w and max_w >= 1.0 else '#888'}),
        ], style={'marginBottom': '10px'}),
        html.Div([
            lbl('FIGI',            inp('map-edit-figi',      figi if not figi.startswith('UNRESOLVED:') else '', 'e.g. BBG000BP5H35', '140px')),
            lbl('Name',            inp('map-edit-name',      safe_str(name) if name and str(name) != '—' else '', 'Company name', '160px')),
            lbl('Bloomberg',       inp('map-edit-bloomberg', safe_str(bloomberg) if bloomberg and str(bloomberg) != '—' else '', 'e.g. BA. LN', '110px')),
            lbl('Raw Ticker',      inp('map-edit-raw',       safe_str(raw_ticker) if raw_ticker and str(raw_ticker) != '—' else '', 'as in CSV', '100px')),
            lbl('SEDOL',           inp('map-edit-sedol',     safe_str(sedol) if sedol and str(sedol) != '—' else '', 'e.g. 0263494', '90px')),
            lbl('ISIN',            inp('map-edit-isin',      safe_str(isin) if isin and str(isin) != '—' else '', 'e.g. GB0002634946', '130px')),
            lbl('Yahoo ID (no YF:)', inp('map-edit-input',   display_yahoo, 'e.g. BA.L', '110px')),
            lbl('Group FIGI',      inp('map-edit-group',     display_group, 'parent FIGI or blank', '160px')),
            lbl('Notes',           inp('map-edit-notes',     safe_str(notes) if notes and str(notes) != '—' else '', 'Optional', '110px')),
            html.Div([
                html.Label(' ', style={'display': 'block', 'marginBottom': '4px', 'fontSize': '10px'}),
                html.Div([
                    html.Button('Approve', id='map-edit-approve', n_clicks=0,
                        style={'backgroundColor': GREEN, 'color': WHITE, 'border': 'none',
                               'borderRadius': '4px', 'padding': '6px 14px', 'fontSize': '11px',
                               'fontWeight': '700', 'cursor': 'pointer', 'marginRight': '6px'}),
                    html.Button('Mark Empty', id='map-edit-empty', n_clicks=0,
                        style={'backgroundColor': '#888', 'color': WHITE, 'border': 'none',
                               'borderRadius': '4px', 'padding': '6px 10px', 'fontSize': '11px',
                               'fontWeight': '600', 'cursor': 'pointer'}),
                ]),
            ]),
        ], style={'display': 'flex', 'alignItems': 'flex-end', 'flexWrap': 'wrap', 'gap': '4px'}),
    ], style={**CARD, 'borderLeft': f'3px solid {ACCENT}'})


@app.callback(
    Output('map-refresh-trigger', 'data'),
    Output('map-feedback',        'children', allow_duplicate=True),
    Input('map-auto-approve-btn', 'n_clicks'),
    Input('map-edit-approve',     'n_clicks'),
    Input('map-edit-empty',       'n_clicks'),
    State('map-edit-figi',        'value'),
    State('map-edit-input',       'value'),
    State('map-edit-notes',       'value'),
    State('map-edit-name',        'value'),
    State('map-edit-bloomberg',   'value'),
    State('map-edit-raw',         'value'),
    State('map-edit-sedol',       'value'),
    State('map-edit-isin',        'value'),
    State('map-edit-group',       'value'),
    State('map-selected-id',      'data'),
    State('map-threshold-slider', 'value'),
    State('map-refresh-trigger',  'data'),
    prevent_initial_call=True,
)
def handle_approve_actions(auto_clicks, approve_clicks, empty_clicks,
                           figi_val, input_val, notes_val, name_val, bloomberg_val,
                           raw_val, sedol_val, isin_val, group_val,
                           selected_figi, threshold, current_trigger):
    ctx = callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate

    trigger_id    = ctx.triggered[0]['prop_id']
    trigger_value = ctx.triggered[0]['value']
    threshold     = threshold or AUTO_APPROVE_THRESHOLD
    conn          = get_conn()

    # Guard: ignore button re-render artifacts (n_clicks resets to 0 on re-render)
    if trigger_value == 0 or trigger_value is None:
        conn.close()
        raise dash.exceptions.PreventUpdate

    def feedback_ok(msg):
        return html.Div(msg, style={'backgroundColor': '#eafaf1', 'color': GREEN,
                                    'padding': '8px 14px', 'borderRadius': '4px',
                                    'fontSize': '12px', 'fontWeight': '600',
                                    'border': f'1px solid {GREEN}'})

    if 'map-auto-approve-btn' in trigger_id:
        result = conn.execute("""
            UPDATE stock_identifier_map SET reviewed = 1
            WHERE reviewed = 0 AND figi IS NOT NULL
            AND yahoo_id IS NOT NULL AND yahoo_id != ''
        """)
        count = result.rowcount
        conn.commit()
        conn.close()
        return current_trigger + 1, feedback_ok(f"✓ Auto-approved {count} records with FIGI and Yahoo ID.")

    if not selected_figi:
        conn.close()
        raise dash.exceptions.PreventUpdate

    def clean(v):
        return str(v).strip() if v and str(v).strip() not in ('', 'nan', 'None') else None

    if 'map-edit-empty' in trigger_id:
        gfigi = clean(group_val) or selected_figi
        conn.execute("""
            UPDATE stock_identifier_map
            SET yahoo_id = NULL, reviewed = 1, notes = ?,
                name           = COALESCE(NULLIF(?, ''), name),
                bloomberg_code = COALESCE(NULLIF(?, ''), bloomberg_code),
                raw_ticker     = COALESCE(NULLIF(?, ''), raw_ticker),
                sedol          = COALESCE(NULLIF(?, ''), sedol),
                isin           = COALESCE(NULLIF(?, ''), isin),
                group_figi     = ?
            WHERE figi = ?
        """, (clean(notes_val), clean(name_val), clean(bloomberg_val),
              clean(raw_val), clean(sedol_val), clean(isin_val),
              gfigi, selected_figi))
        conn.commit()
        conn.close()
        return current_trigger + 1, feedback_ok(f"✓ {selected_figi[:20]} marked reviewed — no Yahoo ID.")

    if 'map-edit-approve' in trigger_id:
        yahoo_val = clean(input_val)
        if yahoo_val:
            yahoo_val = yahoo_val.replace('YF:', '')
            yahoo_val = f'YF:{yahoo_val}'
        new_figi  = clean(figi_val) or selected_figi
        gfigi     = clean(group_val) or new_figi

        if new_figi != selected_figi:
            # FIGI changed — fetch current row, delete old, insert new
            old_row = conn.execute(
                "SELECT * FROM stock_identifier_map WHERE figi = ?", (selected_figi,)
            ).fetchone()
            conn.execute("DELETE FROM stock_identifier_map WHERE figi = ?", (selected_figi,))
            conn.execute("""
                INSERT OR REPLACE INTO stock_identifier_map
                    (figi, name, base_ticker, exch_code, bloomberg_code,
                     raw_ticker, sedol, isin, yahoo_id, security_type, group_figi, reviewed, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (new_figi,
                  clean(name_val)      or (old_row[1] if old_row else None),
                  old_row[2] if old_row else None,
                  old_row[3] if old_row else None,
                  clean(bloomberg_val) or (old_row[4] if old_row else None),
                  clean(raw_val)       or (old_row[5] if old_row else None),
                  clean(sedol_val)     or (old_row[6] if old_row else None),
                  clean(isin_val)      or (old_row[7] if old_row else None),
                  yahoo_val            or (old_row[8] if old_row else None),
                  old_row[9] if old_row else None,
                  gfigi,
                  clean(notes_val)))
        else:
            conn.execute("""
                UPDATE stock_identifier_map
                SET yahoo_id = ?, reviewed = 1, notes = ?,
                    name           = COALESCE(NULLIF(?, ''), name),
                    bloomberg_code = COALESCE(NULLIF(?, ''), bloomberg_code),
                    raw_ticker     = COALESCE(NULLIF(?, ''), raw_ticker),
                    sedol          = COALESCE(NULLIF(?, ''), sedol),
                    isin           = COALESCE(NULLIF(?, ''), isin),
                    group_figi     = ?
                WHERE figi = ?
            """, (yahoo_val, clean(notes_val), clean(name_val), clean(bloomberg_val),
                  clean(raw_val), clean(sedol_val), clean(isin_val),
                  gfigi, selected_figi))
        conn.commit()
        conn.close()
        label = yahoo_val if yahoo_val else 'unmapped'
        return current_trigger + 1, feedback_ok(f"✓ {label} saved for {new_figi[:20]}.")

    conn.close()
    raise dash.exceptions.PreventUpdate


# ── SOURCES CALLBACKS ─────────────────────────────────────────────────────────

@app.callback(
    Output('src-table', 'children'),
    Input('src-refresh-trigger', 'data'),
)
def render_sources_table(_trigger):
    conn  = get_conn()
    urls  = dict(conn.execute("SELECT etf_fund_id, url FROM etf_sources").fetchall())
    conn.close()

    rows = []
    for i, etf_id in enumerate(sorted(etf_list)):
        bg       = WHITE if i % 2 == 0 else '#f9fbfd'
        label    = ETF_NAME_MAP.get(etf_id, short_name(etf_id))
        provider = ETF_PROVIDER_DISPLAY.get(etf_id, '—')
        url_val  = urls.get(etf_id, '') or ''
        rows.append(html.Tr([
            html.Td(label, style={'padding': '8px', 'fontSize': '12px', 'color': BLUE,
                                  'fontWeight': '500', 'whiteSpace': 'nowrap'}),
            html.Td(provider, style={'padding': '8px', 'fontSize': '11px', 'color': '#888',
                                     'textTransform': 'capitalize'}),
            html.Td(
                dcc.Input(id={'type': 'src-url-input', 'index': etf_id}, value=url_val,
                          type='text', placeholder='Paste download URL…', debounce=False,
                          style={'fontSize': '12px', 'padding': '6px 8px', 'border': '1px solid #ddd',
                                 'borderRadius': '4px', 'width': '100%'}),
                style={'padding': '8px', 'minWidth': '320px'}
            ),
            html.Td(
                html.A('Open', href=url_val or '#', target='_blank',
                       style={'fontSize': '11px', 'color': WHITE, 'backgroundColor': ACCENT if url_val else '#ccc',
                              'padding': '6px 12px', 'borderRadius': '4px', 'textDecoration': 'none',
                              'fontWeight': '600', 'pointerEvents': 'auto' if url_val else 'none'}),
                style={'padding': '8px', 'textAlign': 'center', 'width': '70px'}
            ),
            html.Td(
                html.Button('Save', id={'type': 'src-save-btn', 'index': etf_id}, n_clicks=0,
                    style={'backgroundColor': GREEN, 'color': WHITE, 'border': 'none',
                           'borderRadius': '4px', 'padding': '6px 12px', 'fontSize': '11px',
                           'fontWeight': '600', 'cursor': 'pointer'}),
                style={'padding': '8px', 'textAlign': 'center', 'width': '70px'}
            ),
        ], style={'backgroundColor': bg, 'borderBottom': '1px solid #f0f3f7'}))

    return html.Table([
        html.Thead(html.Tr([th('ETF'), th('Provider'), th('Download URL'), th('', 'center'), th('', 'center')])),
        html.Tbody(rows),
    ], style={'width': '100%', 'borderCollapse': 'collapse'})


@app.callback(
    Output('src-refresh-trigger', 'data'),
    Output('src-feedback',        'children'),
    Input({'type': 'src-save-btn', 'index': dash.ALL}, 'n_clicks'),
    State({'type': 'src-url-input', 'index': dash.ALL}, 'value'),
    State({'type': 'src-url-input', 'index': dash.ALL}, 'id'),
    State('src-refresh-trigger', 'data'),
    prevent_initial_call=True,
)
def save_source_url(n_clicks_list, url_values, url_ids, current_trigger):
    ctx = callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate

    trigger_val = ctx.triggered[0]['value']
    if trigger_val == 0 or trigger_val is None:
        raise dash.exceptions.PreventUpdate

    clicked = ctx.triggered_id
    if not clicked or 'index' not in clicked:
        raise dash.exceptions.PreventUpdate
    clicked_etf = clicked['index']

    # Find the matching URL value by etf_fund_id
    url_val = ''
    for uid, uval in zip(url_ids, url_values):
        if uid['index'] == clicked_etf:
            url_val = (uval or '').strip()
            break

    conn = get_conn()
    conn.execute("""
        INSERT INTO etf_sources (etf_fund_id, url) VALUES (?, ?)
        ON CONFLICT(etf_fund_id) DO UPDATE SET url = excluded.url
    """, (clicked_etf, url_val))
    conn.commit()
    conn.close()

    label = ETF_NAME_MAP.get(clicked_etf, short_name(clicked_etf))
    feedback = html.Div(f"✓ Saved URL for {label}.",
        style={'backgroundColor': '#eafaf1', 'color': GREEN, 'padding': '8px 14px',
               'borderRadius': '4px', 'fontSize': '12px', 'fontWeight': '600',
               'border': f'1px solid {GREEN}'})
    return current_trigger + 1, feedback


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8053, debug=True)