# dashboard_personal.py
# Personal finance dashboard — Calendar, Expenditure
# Run: python3 dashboard_personal.py  →  http://minipc:8052

import dash
from dash import html, dcc, Input, Output, State, ALL, MATCH, ctx
import plotly.graph_objects as go
import pandas as pd
import sqlite3
import json
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from datetime import date
import config

from data import DB_PATH, get_fx_rates, load_data, build_df_combined

# ── APP SETUP ─────────────────────────────────────────────────

app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}]
)

df          = load_data()
df_combined = build_df_combined(df)

ACCENT = "#6d3b8c"

CARD = {
    "backgroundColor": "#ffffff", "borderRadius": "8px",
    "padding": "14px 18px", "boxShadow": "0 1px 4px rgba(0,0,0,0.08)",
    "marginBottom": "12px",
}
SECTION_TITLE = {
    "color": ACCENT, "fontSize": "11px", "fontWeight": "700",
    "letterSpacing": "0.08em", "textTransform": "uppercase",
    "marginBottom": "10px", "marginTop": "0",
}
TAB_STYLE = {
    "padding": "8px 20px", "fontSize": "12px", "fontWeight": "600",
    "color": "#666", "borderBottom": "2px solid transparent", "cursor": "pointer",
}
TAB_SELECTED_STYLE = {
    "padding": "8px 20px", "fontSize": "12px", "fontWeight": "600",
    "color": ACCENT, "borderBottom": f"2px solid {ACCENT}", "cursor": "pointer",
}
SUB_TAB_STYLE = {
    "padding": "6px 16px", "fontSize": "11px", "fontWeight": "600",
    "color": "#888", "borderBottom": "2px solid transparent", "cursor": "pointer",
}
SUB_TAB_SELECTED = {
    "padding": "6px 16px", "fontSize": "11px", "fontWeight": "600",
    "color": ACCENT, "borderBottom": f"2px solid {ACCENT}", "cursor": "pointer",
}

EXP_CATEGORIES = [
    "Grocery", "Dining", "Transport", "Shopping", "Electronics",
    "Entertainment", "Health", "Childcare", "Home Services",
    "Utilities", "Subscription", "Mortgage", "Tax & Fee",
    "Income", "Investment", "Transfer", "Cash",
    "Amazon", "PAYPAL", "Holiday",
]

EXP_CAT_COLOURS = {
    "Grocery": "#27ae60", "Dining": "#e67e22", "Transport": "#2980b9",
    "Shopping": "#8e44ad", "Electronics": "#2c3e50", "Entertainment": "#f39c12",
    "Health": "#16a085", "Childcare": "#1abc9c", "Home Services": "#7f8c8d",
    "Utilities": "#c0392b", "Subscription": "#9b59b6", "Mortgage": "#c0392b",
    "Tax & Fee": "#c0392b", "Income": "#1a7a1a", "Investment": "#2E75B6",
    "Transfer": "#95a5a6", "Cash": "#bdc3c7", "Amazon": "#ff9900",
    "PAYPAL": "#003087", "Holiday": "#e74c3c",
}

SOURCES = ["Ahmet Debit", "Ahmet CC", "Burcu Debit", "Burcu CC", "Turkey"]

def fmt_bracket(val):
    """Format number: (1,245) for negative, 1,245 for positive, — for zero."""
    if val is None or val == 0:
        return "—"
    if val < 0:
        return f"({abs(val):,.0f})"
    return f"{val:,.0f}"

def fmt_bracket_color(val):
    if val is None or val == 0:
        return "#999"
    return "#c0392b" if val < 0 else "#1a7a1a"

# ── LAYOUT ────────────────────────────────────────────────────

app.layout = html.Div([

    # Header
    html.Div([
        html.Div([
            html.Span("PERSONAL", style={
                "color": ACCENT, "fontWeight": "800",
                "fontSize": "18px", "letterSpacing": "0.1em",
            }),
            html.Span(" DASHBOARD", style={
                "color": "#2c1a3a", "fontWeight": "300",
                "fontSize": "18px", "letterSpacing": "0.1em",
            }),
        ]),
        html.A("→ Portfolio", href="http://minipc:8050",
               style={"fontSize": "11px", "color": ACCENT, "alignSelf": "center",
                      "textDecoration": "none", "fontWeight": "600"}),
    ], style={
        "display": "flex", "justifyContent": "space-between",
        "alignItems": "center", "padding": "12px 20px",
        "backgroundColor": "#fff", "borderBottom": f"2px solid {ACCENT}",
    }),

    # Main tabs
    dcc.Tabs(id="main-tabs", value="tab-calendar",
        children=[
            dcc.Tab(label="Calendar",    value="tab-calendar",
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
            dcc.Tab(label="Expenditure", value="tab-expenditure",
                    style=TAB_STYLE, selected_style=TAB_SELECTED_STYLE),
        ],
        style={"backgroundColor": "#fff", "borderBottom": "1px solid #eee"}
    ),

    # ── CALENDAR TAB
    html.Div([
        # Filters
        html.Div([
            html.P('FINANCIAL CALENDAR', style={**SECTION_TITLE, 'marginBottom': '8px'}),
            html.Div([
                html.Div([
                    html.Label('Horizon:', style={'fontSize': '11px', 'color': '#666',
                                                  'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='cal-filter-horizon',
                                 options=[
                                     {'label': 'Next 30 days', 'value': 30},
                                     {'label': 'Next 60 days', 'value': 60},
                                     {'label': 'Next 90 days', 'value': 90},
                                     {'label': 'All future',   'value': 365},
                                 ],
                                 value=30, clearable=False,
                                 style={'fontSize': '12px', 'width': '140px'}),
                ], style={'marginRight': '16px'}),
                html.Div([
                    html.Label('Category:', style={'fontSize': '11px', 'color': '#666',
                                                    'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='cal-filter-category',
                                 options=[{'label': 'All', 'value': 'ALL'}] +
                                         [{'label': c, 'value': c} for c in
                                          ['Income','Pension','Dividend','Credit Card',
                                           'Mortgage','Utility','Subscription','Investment','Tax','Other']],
                                 value='ALL', clearable=False,
                                 style={'fontSize': '12px', 'width': '140px'}),
                ], style={'marginRight': '16px'}),
                html.Div([
                    html.Label('Status:', style={'fontSize': '11px', 'color': '#666',
                                                  'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='cal-filter-status',
                                 options=[
                                     {'label': 'All',       'value': 'ALL'},
                                     {'label': 'Pending',   'value': 'pending'},
                                     {'label': 'Due',       'value': 'due'},
                                     {'label': 'Completed', 'value': 'completed'},
                                 ],
                                 value='ALL', clearable=False,
                                 style={'fontSize': '12px', 'width': '120px'}),
                ]),
            ], style={'display': 'flex', 'alignItems': 'flex-end',
                      'flexWrap': 'wrap', 'gap': '8px'}),
        ], style=CARD),

        # Upcoming list
        html.Div(id='calendar-list-div', style={'overflowX': 'auto'}),

        # Add event form
        html.Div([
            html.P('ADD EVENT', style=SECTION_TITLE),
            html.Div([
                html.Div([
                    html.Label('Type:', style={'fontSize': '11px', 'color': '#666',
                                               'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='cal-add-frequency',
                                 options=[
                                     {'label': 'One-off',   'value': 'once'},
                                     {'label': 'Weekly',    'value': 'weekly'},
                                     {'label': 'Monthly',   'value': 'monthly'},
                                     {'label': 'Quarterly', 'value': 'quarterly'},
                                     {'label': 'Annual',    'value': 'annual'},
                                 ],
                                 value='monthly', clearable=False,
                                 style={'fontSize': '12px', 'width': '110px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label('Name:', style={'fontSize': '11px', 'color': '#666',
                                               'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='cal-add-name', type='text', placeholder='e.g. Barclays CC',
                              style={'padding': '7px', 'fontSize': '12px',
                                     'border': '1px solid #ccc', 'borderRadius': '4px',
                                     'width': '150px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label('Category:', style={'fontSize': '11px', 'color': '#666',
                                                    'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='cal-add-category',
                                 options=[{'label': c, 'value': c} for c in
                                          ['Income','Pension','Dividend','Credit Card',
                                           'Mortgage','Utility','Subscription','Investment','Tax','Other']],
                                 placeholder='Category...',
                                 style={'fontSize': '12px', 'width': '130px'}),
                ], style={'marginRight': '12px'}),
                html.Div(id='cal-date-inputs', style={'display': 'flex',
                          'alignItems': 'flex-end', 'gap': '12px'}),
                html.Div([
                    html.Label('Amount:', style={'fontSize': '11px', 'color': '#666',
                                                  'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='cal-add-amount', type='number', placeholder='e.g. 1500',
                              step=0.01,
                              style={'padding': '7px', 'fontSize': '12px',
                                     'border': '1px solid #ccc', 'borderRadius': '4px',
                                     'width': '110px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label('CCY:', style={'fontSize': '11px', 'color': '#666',
                                               'marginBottom': '4px', 'display': 'block'}),
                    dcc.Dropdown(id='cal-add-currency',
                                 options=[{'label': 'GBP', 'value': 'GBP'},
                                          {'label': 'USD', 'value': 'USD'},
                                          {'label': 'TRY', 'value': 'TRY'}],
                                 value='GBP', clearable=False,
                                 style={'fontSize': '12px', 'width': '80px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label('Account:', style={'fontSize': '11px', 'color': '#666',
                                                   'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='cal-add-account', type='text', placeholder='e.g. Barclays',
                              style={'padding': '7px', 'fontSize': '12px',
                                     'border': '1px solid #ccc', 'borderRadius': '4px',
                                     'width': '110px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label('Notes:', style={'fontSize': '11px', 'color': '#666',
                                                 'marginBottom': '4px', 'display': 'block'}),
                    dcc.Input(id='cal-add-notes', type='text', placeholder='Optional...',
                              style={'padding': '7px', 'fontSize': '12px',
                                     'border': '1px solid #ccc', 'borderRadius': '4px',
                                     'width': '120px'}),
                ], style={'marginRight': '12px'}),
                html.Div([
                    html.Label(' ', style={'fontSize': '11px', 'display': 'block',
                                           'marginBottom': '4px'}),
                    html.Button('Add', id='cal-add-btn', n_clicks=0,
                                style={'backgroundColor': '#1a7a1a', 'color': 'white',
                                       'border': 'none', 'borderRadius': '4px',
                                       'padding': '7px 16px', 'fontSize': '12px',
                                       'cursor': 'pointer'}),
                ]),
            ], style={'display': 'flex', 'alignItems': 'flex-end',
                      'flexWrap': 'wrap', 'gap': '4px'}),
            html.Div(id='cal-status', style={'fontSize': '12px', 'color': '#2E75B6',
                                              'marginTop': '8px', 'fontWeight': '600'}),
        ], style=CARD),

        # Manage Events
        html.Div([
            html.P('MANAGE EVENTS', style=SECTION_TITLE),
            html.Div(id='cal-events-list-div'),
            html.Div(id='cal-manage-status',
                     style={'fontSize': '12px', 'color': '#2E75B6',
                            'marginTop': '8px', 'fontWeight': '600'}),
        ], style=CARD),

    ], id='calendar-tab-content', style={
        'display': 'none', 'padding': '12px 16px 16px 16px',
        'maxWidth': '1400px', 'margin': '0 auto', 'overflowX': 'hidden',
    }),

    # Shared stores


    # ── EXPENDITURE TAB
    html.Div([

        # Sub-tabs
        dcc.Tabs(id="exp-sub-tabs", value="sub-overview",
            children=[
                dcc.Tab(label="Overview",     value="sub-overview",
                        style=SUB_TAB_STYLE, selected_style=SUB_TAB_SELECTED),
                dcc.Tab(label="Transactions", value="sub-transactions",
                        style=SUB_TAB_STYLE, selected_style=SUB_TAB_SELECTED),
                dcc.Tab(label="Review",       value="sub-review",
                        style=SUB_TAB_STYLE, selected_style=SUB_TAB_SELECTED),
                dcc.Tab(label="Rules",        value="sub-rules",
                        style=SUB_TAB_STYLE, selected_style=SUB_TAB_SELECTED),
            ],
            style={"backgroundColor": "#fff", "borderBottom": "1px solid #eee",
                   "marginBottom": "12px"}
        ),

        # Shared filters
        html.Div([
            html.Div([
                html.Div([
                    html.Label("From:", style={"fontSize": "11px", "color": "#666",
                                               "marginBottom": "4px", "display": "block"}),
                    dcc.DatePickerSingle(id="exp-filter-from",
                                        display_format="DD MMM YYYY",
                                        date="2025-01-01"),
                ], style={"marginRight": "16px"}),
                html.Div([
                    html.Label("To:", style={"fontSize": "11px", "color": "#666",
                                             "marginBottom": "4px", "display": "block"}),
                    dcc.DatePickerSingle(id="exp-filter-to",
                                        display_format="DD MMM YYYY",
                                        date=date.today().strftime("%Y-%m-%d")),
                ], style={"marginRight": "16px"}),
                html.Div([
                    html.Label("Category:", style={"fontSize": "11px", "color": "#666",
                                                   "marginBottom": "4px", "display": "block"}),
                    dcc.Dropdown(id="exp-filter-category",
                                 options=[{"label": c, "value": c} for c in EXP_CATEGORIES],
                                 value=[c for c in EXP_CATEGORIES
                                        if c not in ("Investment", "Income", "Transfer")],
                                 multi=True, placeholder="All categories...",
                                 style={"fontSize": "12px", "minWidth": "200px"}),
                ], style={"marginRight": "16px"}),
                html.Div([
                    html.Label("Account:", style={"fontSize": "11px", "color": "#666",
                                                  "marginBottom": "4px", "display": "block"}),
                    dcc.Dropdown(id="exp-filter-source",
                                 options=[{"label": s, "value": s} for s in SOURCES],
                                 multi=True, placeholder="All accounts...",
                                 style={"fontSize": "12px", "minWidth": "180px"}),
                ], style={"marginRight": "16px"}),
                html.Div([
                    html.Label(" ", style={"fontSize": "11px", "display": "block",
                                          "marginBottom": "4px"}),
                    html.Button("Import CSVs", id="exp-import-btn", n_clicks=0,
                                style={"backgroundColor": ACCENT, "color": "white",
                                       "border": "none", "borderRadius": "4px",
                                       "padding": "7px 14px", "fontSize": "12px",
                                       "cursor": "pointer"}),
                ]),
            ], style={"display": "flex", "alignItems": "flex-end",
                      "flexWrap": "wrap", "gap": "8px"}),
            html.Div(id="exp-import-status",
                     style={"fontSize": "12px", "color": ACCENT,
                            "marginTop": "8px", "fontWeight": "600"}),
        ], style=CARD),

        # Sub-tab content
        html.Div(id="exp-overview-div",     style={"display": "block"}),
        html.Div(id="exp-transactions-div", style={"display": "none"}),
        html.Div(id="exp-review-div",       style={"display": "none"}),
        html.Div(id="exp-rules-div",        style={"display": "none"}),

        # ── Edit Panel — always in layout, shown when a txn is selected ──
        html.Div([
            html.P("EDIT TRANSACTION", style={**SECTION_TITLE, "marginBottom": "8px"}),
            html.Div(id="exp-edit-desc",
                     style={"fontSize": "12px", "color": "#555",
                            "marginBottom": "12px", "fontStyle": "italic"}),
            html.Div([
                html.Div([
                    html.Label("Category:", style={"fontSize": "11px", "color": "#666",
                                                   "marginBottom": "4px", "display": "block"}),
                    dcc.Dropdown(id="exp-edit-cat",
                                 options=[{"label": c, "value": c} for c in EXP_CATEGORIES],
                                 clearable=False,
                                 style={"fontSize": "12px", "minWidth": "160px"}),
                ], style={"marginRight": "16px"}),
                html.Div([
                    html.Label("Subcategory:", style={"fontSize": "11px", "color": "#666",
                                                      "marginBottom": "4px", "display": "block"}),
                    dcc.Input(id="exp-edit-sub", type="text",
                              placeholder="subcategory...",
                              style={"padding": "7px", "fontSize": "12px",
                                     "border": "1px solid #ccc", "borderRadius": "4px",
                                     "width": "150px"}),
                ], style={"marginRight": "16px"}),
                html.Div([
                    html.Label("Status:", style={"fontSize": "11px", "color": "#666",
                                                 "marginBottom": "4px", "display": "block"}),
                    dcc.Dropdown(id="exp-edit-status",
                                 options=[
                                     {"label": "Confirmed",    "value": "confirmed"},
                                     {"label": "Needs Review", "value": "needs_review"},
                                     {"label": "Internal",     "value": "internal"},
                                 ],
                                 clearable=False,
                                 style={"fontSize": "12px", "width": "140px"}),
                ], style={"marginRight": "16px"}),
                html.Div([
                    html.Label("Notes:", style={"fontSize": "11px", "color": "#666",
                                                "marginBottom": "4px", "display": "block"}),
                    dcc.Input(id="exp-edit-notes", type="text",
                              placeholder="optional notes...",
                              style={"padding": "7px", "fontSize": "12px",
                                     "border": "1px solid #ccc", "borderRadius": "4px",
                                     "width": "180px"}),
                ], style={"marginRight": "16px"}),
                html.Div([
                    html.Label(" ", style={"fontSize": "11px", "display": "block",
                                          "marginBottom": "4px"}),
                    html.Button("Save", id="exp-save-btn", n_clicks=0,
                                style={"backgroundColor": ACCENT, "color": "white",
                                       "border": "none", "borderRadius": "4px",
                                       "padding": "7px 14px", "fontSize": "12px",
                                       "cursor": "pointer", "marginRight": "6px"}),
                    html.Button("Cancel", id="exp-cancel-btn", n_clicks=0,
                                style={"backgroundColor": "#aaa", "color": "white",
                                       "border": "none", "borderRadius": "4px",
                                       "padding": "7px 14px", "fontSize": "12px",
                                       "cursor": "pointer"}),
                ]),
            ], style={"display": "flex", "alignItems": "flex-end",
                      "flexWrap": "wrap", "gap": "8px"}),
            html.Div(id="exp-edit-status-msg",
                     style={"fontSize": "12px", "color": ACCENT,
                            "marginTop": "8px", "fontWeight": "600"}),
        ], id="exp-edit-panel", style={"display": "none", **CARD,
                                        "borderLeft": f"4px solid {ACCENT}"}),

        # ── Rules form — always in layout ──
        html.Div([
            html.P("ADD RULE", style={**SECTION_TITLE, "marginBottom": "8px"}),
            html.Div([
                html.Div([
                    html.Label("Pattern:", style={"fontSize": "11px", "color": "#666",
                                                  "marginBottom": "4px", "display": "block"}),
                    dcc.Input(id="exp-rule-pattern", type="text",
                              placeholder="e.g. TESCO",
                              style={"padding": "7px", "fontSize": "12px",
                                     "border": "1px solid #ccc", "borderRadius": "4px",
                                     "width": "120px"}),
                ], style={"marginRight": "12px"}),
                html.Div([
                    html.Label("Match:", style={"fontSize": "11px", "color": "#666",
                                                "marginBottom": "4px", "display": "block"}),
                    dcc.Dropdown(id="exp-rule-matchtype",
                                 options=[{"label": "Contains",    "value": "contains"},
                                          {"label": "Starts with", "value": "starts_with"},
                                          {"label": "Ends with",   "value": "ends_with"}],
                                 value="contains", clearable=False,
                                 style={"fontSize": "12px", "width": "120px"}),
                ], style={"marginRight": "12px"}),
                html.Div([
                    html.Label("Category:", style={"fontSize": "11px", "color": "#666",
                                                   "marginBottom": "4px", "display": "block"}),
                    dcc.Dropdown(id="exp-rule-category",
                                 options=[{"label": c, "value": c} for c in EXP_CATEGORIES],
                                 placeholder="Category...",
                                 style={"fontSize": "12px", "width": "140px"}),
                ], style={"marginRight": "12px"}),
                html.Div([
                    html.Label("Subcategory:", style={"fontSize": "11px", "color": "#666",
                                                      "marginBottom": "4px", "display": "block"}),
                    dcc.Input(id="exp-rule-subcategory", type="text",
                              placeholder="Optional",
                              style={"padding": "7px", "fontSize": "12px",
                                     "border": "1px solid #ccc", "borderRadius": "4px",
                                     "width": "110px"}),
                ], style={"marginRight": "12px"}),
                html.Div([
                    html.Label("Priority:", style={"fontSize": "11px", "color": "#666",
                                                   "marginBottom": "4px", "display": "block"}),
                    dcc.Input(id="exp-rule-priority", type="number", value=50,
                              style={"padding": "7px", "fontSize": "12px",
                                     "border": "1px solid #ccc", "borderRadius": "4px",
                                     "width": "70px"}),
                ], style={"marginRight": "12px"}),
                html.Div([
                    html.Label(" ", style={"fontSize": "11px", "display": "block",
                                          "marginBottom": "4px"}),
                    html.Button("Add Rule", id="exp-rule-add-btn", n_clicks=0,
                                style={"backgroundColor": "#1a7a1a", "color": "white",
                                       "border": "none", "borderRadius": "4px",
                                       "padding": "7px 14px", "fontSize": "12px",
                                       "cursor": "pointer"}),
                ]),
            ], style={"display": "flex", "alignItems": "flex-end",
                      "flexWrap": "wrap", "gap": "4px"}),
            html.Div(id="exp-rules-status",
                     style={"fontSize": "12px", "color": ACCENT,
                            "marginTop": "8px", "fontWeight": "600"}),
        ], id="exp-rules-form", style={"display": "none", **CARD}),

        dcc.Store(id="exp-reload",        data=0),
        dcc.Store(id="exp-collapsed-cats", data=EXP_CATEGORIES),
        dcc.Store(id="exp-selected-txn",  data=None),

    ], id="expenditure-tab-content", style={
        "display": "none", "padding": "12px 16px 16px 16px",
        "maxWidth": "1400px", "margin": "0 auto", "overflowX": "hidden",
    }),

    dcc.Store(id="db-reload-trigger", data=0),

], style={
    "fontFamily": '"DM Sans", -apple-system, BlinkMacSystemFont, sans-serif',
    "backgroundColor": "#f5f0f8", "minHeight": "100vh", "overflowX": "hidden",
})


# ── TAB VISIBILITY ────────────────────────────────────────────

@app.callback(
    Output("calendar-tab-content",    "style"),
    Output("expenditure-tab-content", "style"),
    Input("main-tabs", "value"),
)
def switch_tab(tab):
    base = {"padding": "12px 16px 16px 16px", "maxWidth": "1400px",
            "margin": "0 auto", "overflowX": "hidden"}
    show = {**base, "display": "block"}
    hide = {**base, "display": "none"}
    return (show, hide) if tab == "tab-calendar" else (hide, show)


# ── CALENDAR CALLBACKS ────────────────────────────────────────
# ── CALENDAR CALLBACKS ────────────────────────────────────────

CATEGORY_SIGNS = {
    'Income': 1, 'Pension': 1, 'Dividend': 1,
    'Credit Card': -1, 'Mortgage': -1, 'Utility': -1, 'Subscription': -1,
    'Investment': -1, 'Tax': -1, 'Other': 0,
}

CATEGORY_COLOURS = {
    'Income':      '#1a7a1a',
    'Pension':     '#1a7a1a',
    'Dividend':    '#1a7a1a',
    'Credit Card': '#c0392b',
    'Mortgage':    '#c0392b',
    'Utility':     '#e67e22',
    'Subscription':'#8e44ad',
    'Investment':  '#2E75B6',
    'Tax':         '#c0392b',
    'Other':       '#666',
}


def generate_instances(horizon_days=30):
    """Generate calendar instances for next horizon_days from today.
    Skips instances that already exist (preserves actual amounts/status).
    """
    from datetime import date, timedelta
    today = date.today()
    end   = today + timedelta(days=horizon_days)

    conn   = sqlite3.connect(DB_PATH)
    events = conn.execute(
        "SELECT id, name, frequency, day_of_month, month, amount, currency FROM calendar_events WHERE active = 1"
    ).fetchall()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for eid, name, freq, dom, mon, amount, currency in events:
        dates_to_create = []

        if freq == 'once':
            # One-off: due_date stored in day_of_month=day, month=month, and year in notes
            # Actually for one-off we store the full date separately — skip generation
            continue

        elif freq == 'weekly':
            d = today
            while d <= end:
                if d.weekday() == (dom or 0) % 7:
                    dates_to_create.append(d)
                d += timedelta(days=1)

        elif freq == 'monthly':
            # Generate for current and next months within horizon
            for month_offset in range(3):
                try:
                    import calendar as cal_mod
                    year  = today.year + (today.month + month_offset - 1) // 12
                    month = (today.month + month_offset - 1) % 12 + 1
                    day   = min(dom or 1, cal_mod.monthrange(year, month)[1])
                    d     = date(year, month, day)
                    if today <= d <= end:
                        dates_to_create.append(d)
                except ValueError:
                    pass

        elif freq == 'quarterly':
            for month_offset in range(12):
                try:
                    import calendar as cal_mod
                    year  = today.year + (today.month + month_offset - 1) // 12
                    month = (today.month + month_offset - 1) % 12 + 1
                    if (month - (mon or 1)) % 3 != 0:
                        continue
                    day = min(dom or 1, cal_mod.monthrange(year, month)[1])
                    d   = date(year, month, day)
                    if today <= d <= end:
                        dates_to_create.append(d)
                except ValueError:
                    pass

        elif freq == 'annual':
            for year_offset in range(2):
                try:
                    import calendar as cal_mod
                    year = today.year + year_offset
                    m    = mon or 1
                    day  = min(dom or 1, cal_mod.monthrange(year, m)[1])
                    d    = date(year, m, day)
                    if today <= d <= end:
                        dates_to_create.append(d)
                except ValueError:
                    pass

        for d in dates_to_create:
            date_str = d.strftime('%Y-%m-%d')
            # Status: due if within 7 days
            status = 'due' if (d - today).days <= 7 else 'pending'
            conn.execute("""
                INSERT OR IGNORE INTO calendar_instances
                    (event_id, due_date, amount, currency, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (eid, date_str, amount, currency or 'GBP', status, now))

        # Update status of existing pending instances to 'due' if within 7 days
        conn.execute("""
            UPDATE calendar_instances
            SET status = 'due', updated_at = ?
            WHERE event_id = ? AND status = 'pending'
              AND julianday(due_date) - julianday('now') <= 7
              AND julianday(due_date) >= julianday('now')
        """, (now, eid))

    conn.commit()
    conn.close()


@app.callback(
    Output('cal-date-inputs', 'children'),
    Input('cal-add-frequency', 'value'),
)
def update_date_inputs(frequency):
    """Show appropriate date inputs based on frequency type."""
    if frequency == 'once':
        return [html.Div([
            html.Label('Date:', style={'fontSize': '11px', 'color': '#666',
                                       'marginBottom': '4px', 'display': 'block'}),
            dcc.DatePickerSingle(id='cal-add-date', display_format='DD MMM YYYY',
                                 date=datetime.today().strftime('%Y-%m-%d')),
        ])]

    elif frequency == 'weekly':
        return [html.Div([
            html.Label('Day of Week:', style={'fontSize': '11px', 'color': '#666',
                                               'marginBottom': '4px', 'display': 'block'}),
            dcc.Dropdown(id='cal-add-dom',
                         options=[{'label': d, 'value': i} for i, d in enumerate(
                             ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'])],
                         value=0, clearable=False,
                         style={'fontSize': '12px', 'width': '120px'}),
        ])]

    elif frequency == 'monthly':
        return [html.Div([
            html.Label('Day of Month:', style={'fontSize': '11px', 'color': '#666',
                                                'marginBottom': '4px', 'display': 'block'}),
            dcc.Dropdown(id='cal-add-dom',
                         options=[{'label': str(d), 'value': d} for d in range(1, 32)],
                         value=1, clearable=False,
                         style={'fontSize': '12px', 'width': '80px'}),
        ])]

    elif frequency in ('quarterly', 'annual'):
        return [
            html.Div([
                html.Label('Month:', style={'fontSize': '11px', 'color': '#666',
                                             'marginBottom': '4px', 'display': 'block'}),
                dcc.Dropdown(id='cal-add-month',
                             options=[{'label': m, 'value': i+1} for i, m in enumerate(
                                 ['Jan','Feb','Mar','Apr','May','Jun',
                                  'Jul','Aug','Sep','Oct','Nov','Dec'])],
                             value=1, clearable=False,
                             style={'fontSize': '12px', 'width': '80px'}),
            ], style={'marginRight': '8px'}),
            html.Div([
                html.Label('Day:', style={'fontSize': '11px', 'color': '#666',
                                           'marginBottom': '4px', 'display': 'block'}),
                dcc.Dropdown(id='cal-add-dom',
                             options=[{'label': str(d), 'value': d} for d in range(1, 32)],
                             value=1, clearable=False,
                             style={'fontSize': '12px', 'width': '75px'}),
            ]),
        ]
    return []


@app.callback(
    Output('calendar-list-div', 'children'),
    Output('cal-status',        'children'),
    Input('main-tabs',           'value'),
    Input('cal-filter-horizon',  'value'),
    Input('cal-filter-category', 'value'),
    Input('cal-filter-status',   'value'),
    Input('cal-add-btn',                                'n_clicks'),
    Input({'type': 'cal-complete-btn',     'index': ALL}, 'n_clicks'),
    Input({'type': 'cal-delete-inst-btn',  'index': ALL}, 'n_clicks'),
    State('cal-add-frequency',   'value'),
    State('cal-add-name',        'value'),
    State('cal-add-category',    'value'),
    State('cal-add-amount',      'value'),
    State('cal-add-currency',    'value'),
    State('cal-add-account',     'value'),
    State('cal-add-notes',       'value'),
    State('cal-date-inputs',     'children'),
    prevent_initial_call=False,
)
def update_calendar(tab, horizon, cat_filter, status_filter, add_clicks,
                    complete_clicks, delete_inst_clicks,
                    frequency, name, category, amount, currency, account, notes,
                    date_inputs):
    if tab != 'tab-calendar':
        return html.Div(), ''

    from datetime import date, timedelta
    today  = date.today()
    status_msg = ''
    triggered  = ctx.triggered_id

    # ── Handle complete button ──
    if isinstance(triggered, dict) and triggered.get('type') == 'cal-complete-btn':
        inst_id = triggered['index']
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE calendar_instances SET status='completed', updated_at=? WHERE id=?",
                     (now, inst_id))
        conn.commit(); conn.close()
        status_msg = '✓ Marked as completed'

    # ── Handle delete instance button ──
    elif isinstance(triggered, dict) and triggered.get('type') == 'cal-delete-inst-btn':
        inst_id = triggered['index']
        conn = sqlite3.connect(DB_PATH)
        conn.execute('DELETE FROM calendar_instances WHERE id = ?', (inst_id,))
        conn.commit(); conn.close()
        status_msg = '✓ Instance deleted'

    # ── Handle Add button ──
    elif triggered == 'cal-add-btn' and add_clicks:
        if not name or not category:
            return html.Div(), 'Please enter name and category.'

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        conn = sqlite3.connect(DB_PATH)

        if frequency == 'once':
            # Extract date from date_inputs
            due_date = today.strftime('%Y-%m-%d')
            try:
                if date_inputs and isinstance(date_inputs, list):
                    for el in date_inputs:
                        if isinstance(el, dict):
                            props = el.get('props', {})
                            if 'date' in props:
                                due_date = props['date'][:10]
            except Exception:
                pass
            # Store as event + immediate instance
            conn.execute("""
                INSERT INTO calendar_events
                    (name, category, frequency, day_of_month, month, amount, currency, account, notes, created_at)
                VALUES (?, ?, 'once', NULL, NULL, ?, ?, ?, ?, ?)
            """, (name, category, amount, currency or 'GBP', account, notes, now))
            eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            status = 'due' if (date.fromisoformat(due_date) - today).days <= 7 else 'pending'
            conn.execute("""
                INSERT OR IGNORE INTO calendar_instances
                    (event_id, due_date, amount, currency, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (eid, due_date, amount, currency or 'GBP', status, now))
        else:
            # Extract dom and month from date_inputs
            dom = 1
            mon = 1
            try:
                if date_inputs and isinstance(date_inputs, list):
                    for el in date_inputs:
                        if isinstance(el, dict):
                            props = el.get('props', {})
                            children = props.get('children', [])
                            if isinstance(children, list):
                                for child in children:
                                    if isinstance(child, dict):
                                        cprops = child.get('props', {})
                                        if cprops.get('id') == 'cal-add-dom' and 'value' in cprops:
                                            dom = cprops['value']
                                        if cprops.get('id') == 'cal-add-month' and 'value' in cprops:
                                            mon = cprops['value']
            except Exception:
                pass
            conn.execute("""
                INSERT INTO calendar_events
                    (name, category, frequency, day_of_month, month, amount, currency, account, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, category, frequency, dom, mon, amount, currency or 'GBP', account, notes, now))

        conn.commit()
        conn.close()
        status_msg = f'✓ Added {name}'

    # ── Generate instances ──
    generate_instances(horizon or 30)

    # ── Load instances ──
    conn  = sqlite3.connect(DB_PATH)
    end   = (today + timedelta(days=horizon or 30)).strftime('%Y-%m-%d')
    query = """
        SELECT ci.id, ci.due_date, ce.name, ce.category, ce.frequency,
               ci.amount, ci.currency, ce.account, ci.status, ci.notes
        FROM calendar_instances ci
        JOIN calendar_events ce ON ci.event_id = ce.id
        WHERE ci.due_date >= ? AND ci.due_date <= ?
          AND ce.active = 1
    """
    params = [today.strftime('%Y-%m-%d'), end]
    if cat_filter and cat_filter != 'ALL':
        query  += " AND ce.category = ?"
        params.append(cat_filter)
    if status_filter and status_filter != 'ALL':
        query  += " AND ci.status = ?"
        params.append(status_filter)
    query += " ORDER BY ci.due_date, ce.name"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return html.P("No upcoming events in this period.",
                      style={'color': '#999', 'fontSize': '12px', 'padding': '12px'}), status_msg

    # ── Build table ──
    header = html.Tr([
        html.Th(c, style={
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '6px 10px', 'fontSize': '11px', 'fontWeight': '600',
            'textAlign': 'left' if i < 3 else 'right', 'whiteSpace': 'nowrap',
        }) for i, c in enumerate(['Date', 'Name', 'Category', 'Type', 'Account',
                                   'Amount', 'CCY', 'Status', 'Notes', ''])
    ])

    # Get latest FX rates for GBP conversion
    cal_fx = get_fx_rates(df)

    def to_gbp_amount(amount, currency):
        if not amount:
            return 0.0
        curr = currency or 'GBP'
        if curr == 'GBP':
            return float(amount)
        elif curr == 'USD':
            return float(amount) / cal_fx.get('USD', 1.26)
        elif curr == 'TRY':
            return float(amount) / cal_fx.get('TRY', 43.0)
        return float(amount)

    table_rows  = []
    total_in    = 0.0
    total_out   = 0.0

    for inst_id, due_date, name, category, frequency, amount, curr, account, status, inst_notes in rows:
        sign    = CATEGORY_SIGNS.get(category, 0)
        cat_col = CATEGORY_COLOURS.get(category, '#666')
        sym     = {'GBP': '£', 'USD': '$', 'TRY': '₺'}.get(curr or 'GBP', '')
        # Native currency display
        native  = (amount or 0) * sign if sign != 0 else (amount or 0)
        # GBP converted amount
        gbp_amt = to_gbp_amount(amount, curr)
        signed  = gbp_amt * sign if sign != 0 else gbp_amt
        # Show native if non-GBP, with GBP equivalent in brackets
        if curr and curr != 'GBP' and amount:
            signed_str = f"{sym}{abs(native):,.0f} (£{abs(signed):,.0f})"
        else:
            signed_str = f"£{abs(signed):+,.0f}" if amount else '—'
        if amount and sign < 0:
            signed_str = '-' + signed_str.lstrip('-').lstrip('+')
        elif amount and sign > 0:
            signed_str = '+' + signed_str.lstrip('-').lstrip('+')

        # Row background based on status
        days_away = (date.fromisoformat(due_date) - today).days
        if status == 'completed':
            row_bg = '#f8fff8'
        elif status == 'due' or days_away <= 7:
            row_bg = '#fff8f0'
        else:
            row_bg = 'transparent'

        status_badge_color = {
            'completed': '#1a7a1a',
            'due':       '#e67e22',
            'pending':   '#2E75B6',
        }.get(status, '#666')

        freq_label = {
            'once': 'One-off', 'weekly': 'Weekly', 'monthly': 'Monthly',
            'quarterly': 'Quarterly', 'annual': 'Annual',
        }.get(frequency, frequency)

        amount_str = f"{sym}{abs(amount):,.0f}" if amount else '—'
        signed_str = f"{signed:+,.0f}" if amount else '—'
        amount_color = '#1a7a1a' if sign >= 0 else '#c0392b'

        # Format date nicely
        dt = date.fromisoformat(due_date)
        date_display = dt.strftime('%d %b %Y')
        if days_away == 0:
            date_display += ' ⬅ TODAY'
        elif days_away == 1:
            date_display += ' (tomorrow)'

        table_rows.append(html.Tr([
            html.Td(date_display, style={
                'padding': '5px 10px', 'fontSize': '11px', 'color': '#555',
                'whiteSpace': 'nowrap', 'fontWeight': '600' if days_away <= 1 else 'normal'}),
            html.Td(name, style={
                'padding': '5px 10px', 'fontSize': '12px', 'color': '#1a3a5c',
                'whiteSpace': 'nowrap'}),
            html.Td(category, style={
                'padding': '5px 10px', 'fontSize': '11px', 'color': cat_col,
                'fontWeight': '600', 'whiteSpace': 'nowrap'}),
            html.Td(freq_label, style={
                'padding': '5px 10px', 'fontSize': '10px', 'color': '#888',
                'textAlign': 'right', 'whiteSpace': 'nowrap'}),
            html.Td(account or '—', style={
                'padding': '5px 10px', 'fontSize': '11px', 'color': '#666',
                'textAlign': 'right', 'whiteSpace': 'nowrap'}),
            html.Td(signed_str, style={
                'padding': '5px 10px', 'fontSize': '12px', 'textAlign': 'right',
                'fontFamily': 'monospace', 'fontWeight': '600', 'color': amount_color,
                'whiteSpace': 'nowrap'}),
            html.Td(curr or 'GBP', style={
                'padding': '5px 10px', 'fontSize': '11px', 'textAlign': 'right',
                'color': '#888', 'whiteSpace': 'nowrap'}),
            html.Td(
                html.Span(status.upper(), style={
                    'backgroundColor': status_badge_color, 'color': 'white',
                    'borderRadius': '3px', 'padding': '2px 6px',
                    'fontSize': '10px', 'fontWeight': '600',
                }),
                style={'padding': '5px 10px', 'textAlign': 'right'}),
            html.Td(inst_notes or '—', style={
                'padding': '5px 10px', 'fontSize': '11px', 'color': '#888',
                'whiteSpace': 'nowrap'}),
            html.Td([
                html.Button('✓', id={'type': 'cal-complete-btn', 'index': inst_id},
                            n_clicks=0, title='Mark completed',
                            style={'backgroundColor': '#1a7a1a', 'color': 'white',
                                   'border': 'none', 'borderRadius': '3px',
                                   'padding': '2px 6px', 'fontSize': '11px',
                                   'cursor': 'pointer', 'marginRight': '4px'}),
                html.Button('✕', id={'type': 'cal-delete-inst-btn', 'index': inst_id},
                            n_clicks=0, title='Delete this instance',
                            style={'backgroundColor': '#c0392b', 'color': 'white',
                                   'border': 'none', 'borderRadius': '3px',
                                   'padding': '2px 6px', 'fontSize': '11px',
                                   'cursor': 'pointer'}),
            ], style={'padding': '4px 8px', 'textAlign': 'right', 'whiteSpace': 'nowrap'}),
        ], style={'borderBottom': '1px solid #f0f3f7', 'backgroundColor': row_bg}))

        if sign > 0 and amount:
            total_in  += gbp_amt
        elif sign < 0 and amount:
            total_out += gbp_amt

    # Total row
    net = total_in - total_out
    net_color = '#1a7a1a' if net >= 0 else '#c0392b'
    table_rows.append(html.Tr([
        html.Td('TOTAL', colSpan=5, style={
            'padding': '7px 10px', 'fontSize': '12px', 'fontWeight': '700',
            'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"in: £+{total_in:,.0f}  out: £-{total_out:,.0f}  net: £{net:+,.0f}",
                style={'padding': '7px 10px', 'fontSize': '11px', 'textAlign': 'right',
                       'fontFamily': 'monospace', 'fontWeight': '700', 'color': net_color,
                       'borderTop': '2px solid #1a3a5c', 'whiteSpace': 'nowrap'}),
        html.Td('', colSpan=3, style={'borderTop': '2px solid #1a3a5c'}),
    ]))

    table = html.Div(
        html.Table([html.Thead(header), html.Tbody(table_rows)],
                   style={'width': '100%', 'borderCollapse': 'collapse'}),
        style={**CARD, 'overflowX': 'auto', 'padding': '0'}
    )
    return table, status_msg




@app.callback(
    Output('cal-events-list-div',  'children'),
    Output('cal-manage-status',    'children'),
    Input('main-tabs',             'value'),
    Input('cal-add-btn',           'n_clicks'),
    Input('cal-status',            'children'),
    Input({'type': 'cal-delete-event-btn', 'index': ALL}, 'n_clicks'),
    prevent_initial_call=False,
)
def update_manage_events(tab, add_clicks, cal_status, delete_clicks):
    """Render the manage events section with delete buttons."""
    if tab != 'tab-calendar':
        return html.Div(), ''

    manage_status = ''
    triggered = ctx.triggered_id

    # Handle delete event + all instances
    if isinstance(triggered, dict) and triggered.get('type') == 'cal-delete-event-btn':
        eid = triggered['index']
        conn = sqlite3.connect(DB_PATH)
        name_row = conn.execute("SELECT name FROM calendar_events WHERE id = ?", (eid,)).fetchone()
        conn.execute("DELETE FROM calendar_instances WHERE event_id = ?", (eid,))
        conn.execute("DELETE FROM calendar_events WHERE id = ?", (eid,))
        conn.commit(); conn.close()
        manage_status = f"✓ Deleted event and all instances: {name_row[0] if name_row else ''}"

    # Load all events
    conn  = sqlite3.connect(DB_PATH)
    rows  = conn.execute("""
        SELECT id, name, category, frequency, day_of_month, month,
               amount, currency, account, notes, active
        FROM calendar_events
        ORDER BY category, name
    """).fetchall()
    conn.close()

    if not rows:
        return html.P("No events defined yet.", style={'color': '#999', 'fontSize': '12px'}), manage_status

    freq_labels = {
        'once': 'One-off', 'weekly': 'Weekly', 'monthly': 'Monthly',
        'quarterly': 'Quarterly', 'annual': 'Annual',
    }
    month_names = ['','Jan','Feb','Mar','Apr','May','Jun',
                   'Jul','Aug','Sep','Oct','Nov','Dec']

    header = html.Tr([
        html.Th(c, style={
            'backgroundColor': '#2c3e50', 'color': 'white',
            'padding': '5px 8px', 'fontSize': '11px', 'fontWeight': '600',
            'textAlign': 'left' if i == 0 else 'right', 'whiteSpace': 'nowrap',
        }) for i, c in enumerate(['Name', 'Category', 'Frequency', 'Schedule',
                                   'Amount', 'CCY', 'Account', ''])
    ])

    table_rows = []
    for eid, name, category, frequency, dom, mon, amount, currency, account, notes, active in rows:
        cat_col = CATEGORY_COLOURS.get(category, '#666')
        sign    = CATEGORY_SIGNS.get(category, 0)
        sym     = {'GBP': '£', 'USD': '$', 'TRY': '₺'}.get(currency or 'GBP', '')
        signed  = (amount or 0) * sign if sign != 0 else (amount or 0)
        amt_str = f"{signed:+,.0f}" if amount else '—'
        amt_col = '#1a7a1a' if sign >= 0 else '#c0392b'

        # Schedule description
        if frequency == 'once':
            schedule = 'One time'
        elif frequency == 'monthly':
            schedule = f"Day {dom}" if dom else '—'
        elif frequency == 'weekly':
            days = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
            schedule = days[dom] if dom is not None and 0 <= dom <= 6 else '—'
        elif frequency == 'quarterly':
            schedule = f"{month_names[mon or 1]} day {dom}"
        elif frequency == 'annual':
            schedule = f"{month_names[mon or 1]} {dom}"
        else:
            schedule = '—'

        row_bg = '#f8f8f8' if not active else 'transparent'

        table_rows.append(html.Tr([
            html.Td(name, style={
                'padding': '4px 8px', 'fontSize': '12px', 'color': '#1a3a5c',
                'whiteSpace': 'nowrap'}),
            html.Td(category, style={
                'padding': '4px 8px', 'fontSize': '11px', 'color': cat_col,
                'fontWeight': '600', 'textAlign': 'right', 'whiteSpace': 'nowrap'}),
            html.Td(freq_labels.get(frequency, frequency), style={
                'padding': '4px 8px', 'fontSize': '11px', 'color': '#888',
                'textAlign': 'right', 'whiteSpace': 'nowrap'}),
            html.Td(schedule, style={
                'padding': '4px 8px', 'fontSize': '11px', 'color': '#555',
                'textAlign': 'right', 'whiteSpace': 'nowrap'}),
            html.Td(f"{sym}{amt_str}", style={
                'padding': '4px 8px', 'fontSize': '11px', 'textAlign': 'right',
                'fontFamily': 'monospace', 'color': amt_col, 'whiteSpace': 'nowrap'}),
            html.Td(currency or 'GBP', style={
                'padding': '4px 8px', 'fontSize': '11px', 'textAlign': 'right',
                'color': '#888', 'whiteSpace': 'nowrap'}),
            html.Td(account or '—', style={
                'padding': '4px 8px', 'fontSize': '11px', 'textAlign': 'right',
                'color': '#666', 'whiteSpace': 'nowrap'}),
            html.Td(
                html.Button('✕ Delete', id={'type': 'cal-delete-event-btn', 'index': eid},
                            n_clicks=0,
                            style={'backgroundColor': '#c0392b', 'color': 'white',
                                   'border': 'none', 'borderRadius': '3px',
                                   'padding': '3px 8px', 'fontSize': '10px',
                                   'cursor': 'pointer', 'whiteSpace': 'nowrap'}),
                style={'padding': '4px 8px', 'textAlign': 'right'}),
        ], style={'borderBottom': '1px solid #f0f3f7', 'backgroundColor': row_bg}))

    return html.Div(
        html.Table([html.Thead(header), html.Tbody(table_rows)],
                   style={'width': '100%', 'borderCollapse': 'collapse'}),
        style={'overflowX': 'auto'}
    ), manage_status


# ── TRANSACTIONS CALLBACKS ────────────────────────────────────

@app.callback(
    Output('txn-filter-fund', 'options'),
    Input('main-tabs', 'value'),
)
def populate_fund_filter(tab):
    """Populate fund dropdown from transactions table."""
    if tab != 'tab-transactions':
        return []
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT DISTINCT t.fund_id, i.name
        FROM transactions t
        LEFT JOIN instruments i ON t.fund_id = i.fund_id
        ORDER BY i.name
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

    # Load transactions with filters
    conn  = sqlite3.connect(DB_PATH)
    query = """
        SELECT t.fund_id, t.trade_date, t.type, t.quantity, t.price,
               t.currency, t.fx_rate, i.name, i.price_unit
        FROM transactions t
        LEFT JOIN instruments i ON t.fund_id = i.fund_id
        WHERE 1=1
    """
    params = []
    if funds:
        placeholders = ','.join('?' * len(funds))
        query  += f" AND t.fund_id IN ({placeholders})"
        params += funds
    if date_from:
        query  += " AND t.trade_date >= ?"
        params.append(date_from)
    if date_to:
        query  += " AND t.trade_date <= ?"
        params.append(date_to)
    if txn_type and txn_type != 'ALL':
        query  += " AND t.type = ?"
        params.append(txn_type)
    query += " ORDER BY t.trade_date DESC, t.fund_id"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return html.P("No transactions found.", style={'color': '#999', 'fontSize': '12px', 'padding': '12px'})

    def fmt(val, symbol='', suffix='', decimals=2):
        if val is None:
            return '—'
        if abs(val) >= 100:
            return f"{symbol}{val:,.0f}{suffix}"
        return f"{symbol}{val:,.{decimals}f}{suffix}"

    def native_price_str(price, price_unit, currency):
        sym = {'GBP': '£', 'USD': '$', 'TRY': '₺'}.get(currency, '')
        if price_unit == 'pence':
            return fmt(price, suffix='p')
        return fmt(price, symbol=sym)

    header = html.Tr([
        html.Th(c, style={
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '6px 10px', 'fontSize': '11px', 'fontWeight': '600',
            'textAlign': 'left' if i == 0 else 'right', 'whiteSpace': 'nowrap',
        }) for i, c in enumerate([
            'Date', 'Fund', 'Type', 'Qty', 'Price', 'Cost GBP',
            'Latest Price', 'Current Value GBP', 'P&L GBP'
        ])
    ])

    table_rows   = []
    total_cost   = 0.0
    total_value  = 0.0
    total_pnl    = 0.0

    for fid, trade_date, ttype, qty, price, currency, fx_rate, name, price_unit in rows:
        qty        = float(qty)
        price      = float(price)
        fx_rate    = float(fx_rate) if fx_rate else 1.0
        inst       = instruments.get(fid, {})
        curr       = inst.get('currency', currency or 'GBP')
        punit_inst = inst.get('price_unit', price_unit or 'pound')

        # Cost per unit in GBP
        cost_per_unit = txn_price_to_gbp(price, currency, fx_rate, punit_inst)

        # Latest price in GBP
        latest_raw = get_latest_price(df_combined, fid)
        latest_gbp = to_gbp(latest_raw, punit_inst, curr, gbpusd, fx_rates) if latest_raw else None
        latest_str = native_price_str(latest_raw, punit_inst, curr) if latest_raw else '—'

        # Ledger signage:
        # BUY:      qty +ve, cost -ve (cash out), curr_value +ve
        # SELL:     qty -ve, cost +ve (cash in),  curr_value -ve
        # DIVIDEND: qty n/a, cost +ve (cash in),  curr_value n/a
        if ttype == 'BUY':
            signed_qty   =  qty
            signed_cost  = -qty * cost_per_unit          # cash out = negative
            signed_value =  latest_gbp * qty if latest_gbp is not None else None
            # P&L = value + cost (value positive, cost negative)
            pnl = (signed_value + signed_cost) if signed_value is not None else None

        elif ttype == 'SELL':
            signed_qty   = -qty                          # sold = negative units
            signed_cost  =  qty * cost_per_unit          # cash in = positive
            signed_value = -latest_gbp * qty if latest_gbp is not None else None  # negative exposure
            # P&L: (sell - latest) * qty — nets with BUY P&L to realised
            pnl = (cost_per_unit - (latest_gbp or cost_per_unit)) * qty

        elif ttype == 'DIVIDEND':
            signed_qty   = None
            signed_cost  = qty * cost_per_unit           # cash received = positive
            signed_value = None
            pnl          = signed_cost                   # pure gain

        else:
            signed_qty   = qty
            signed_cost  = -qty * cost_per_unit
            signed_value = latest_gbp * qty if latest_gbp is not None else None
            pnl          = None

        pnl_color  = '#1a7a1a' if (pnl or 0) >= 0 else '#c0392b'
        cost_color = '#1a7a1a' if signed_cost >= 0 else '#c0392b'
        val_color  = '#1a7a1a' if (signed_value or 0) >= 0 else '#c0392b'
        type_color = {'BUY': '#2E75B6', 'SELL': '#c0392b', 'DIVIDEND': '#1a7a1a'}.get(ttype, '#333')

        # Accumulate totals
        total_cost  += signed_cost
        if signed_value is not None:
            total_value += signed_value
        if pnl is not None:
            total_pnl += pnl

        ndisp = (name or fid)
        ndisp = ndisp if len(ndisp) <= 30 else ndisp[:30] + '…'

        def fmt_signed(val, decimals=0):
            if val is None: return '—'
            return f"{val:+,.{decimals}f}" if abs(val) >= 100 else f"{val:+,.2f}"

        table_rows.append(html.Tr([
            html.Td(trade_date, style={
                'padding': '4px 10px', 'fontSize': '11px', 'color': '#555', 'whiteSpace': 'nowrap'}),
            html.Td(html.Span(ndisp, title=name or fid), style={
                'padding': '4px 10px', 'fontSize': '12px', 'color': '#1a3a5c', 'whiteSpace': 'nowrap'}),
            html.Td(ttype, style={
                'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right',
                'fontWeight': '600', 'color': type_color}),
            html.Td(fmt_signed(signed_qty, decimals=4) if signed_qty is not None else '—', style={
                'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right',
                'fontFamily': 'monospace', 'color': '#555'}),
            html.Td(native_price_str(price, punit_inst, curr), style={
                'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right',
                'fontFamily': 'monospace', 'color': '#555'}),
            html.Td(fmt_signed(signed_cost), style={
                'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right',
                'fontFamily': 'monospace', 'fontWeight': '600', 'color': cost_color}),
            html.Td(latest_str, style={
                'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right',
                'fontFamily': 'monospace', 'color': '#555'}),
            html.Td(fmt_signed(signed_value) if signed_value is not None else '—', style={
                'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right',
                'fontFamily': 'monospace', 'color': val_color}),
            html.Td(fmt_signed(pnl) if pnl is not None else '—',
                style={'padding': '4px 10px', 'fontSize': '11px', 'textAlign': 'right',
                       'fontFamily': 'monospace', 'fontWeight': '700', 'color': pnl_color}),
        ], style={'borderBottom': '1px solid #f0f3f7'}))

    # Total row
    pnl_color_total  = '#1a7a1a' if total_pnl  >= 0 else '#c0392b'
    cost_color_total = '#1a7a1a' if total_cost  >= 0 else '#c0392b'
    val_color_total  = '#1a7a1a' if total_value >= 0 else '#c0392b'

    table_rows.append(html.Tr([
        html.Td('TOTAL', colSpan=5, style={
            'padding': '7px 10px', 'fontSize': '12px', 'fontWeight': '700',
            'color': '#1a3a5c', 'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total_cost:+,.0f}", style={
            'padding': '7px 10px', 'fontSize': '12px', 'textAlign': 'right',
            'fontFamily': 'monospace', 'fontWeight': '700', 'color': cost_color_total,
            'borderTop': '2px solid #1a3a5c'}),
        html.Td('', style={'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total_value:+,.0f}", style={
            'padding': '7px 10px', 'fontSize': '12px', 'textAlign': 'right',
            'fontFamily': 'monospace', 'fontWeight': '700', 'color': val_color_total,
            'borderTop': '2px solid #1a3a5c'}),
        html.Td(f"{total_pnl:+,.0f}", style={
            'padding': '7px 10px', 'fontSize': '12px', 'textAlign': 'right',
            'fontFamily': 'monospace', 'fontWeight': '700', 'color': pnl_color_total,
            'borderTop': '2px solid #1a3a5c'}),
    ]))

    return html.Div(
        html.Table(
            [html.Thead(header), html.Tbody(table_rows)],
            style={'width': '100%', 'borderCollapse': 'collapse'}
        ),
        style={**CARD, 'overflowX': 'auto', 'padding': '0'}
    )




# ── EXPENDITURE: SUB-TAB VISIBILITY ──────────────────────────

@app.callback(
    Output("exp-overview-div",     "style"),
    Output("exp-transactions-div", "style"),
    Output("exp-review-div",       "style"),
    Output("exp-rules-div",        "style"),
    Output("exp-rules-form",       "style"),
    Input("exp-sub-tabs",          "value"),
)
def switch_exp_subtab(sub):
    show = {"display": "block"}
    hide = {"display": "none"}
    rules_form = {**show, "borderLeft": f"4px solid {ACCENT}",
                  **{k: v for k, v in CARD.items()}} if sub == "sub-rules" else hide
    return (
        show if sub == "sub-overview"     else hide,
        show if sub == "sub-transactions" else hide,
        show if sub == "sub-review"       else hide,
        show if sub == "sub-rules"        else hide,
        rules_form,
    )


# ── EXPENDITURE: EDIT PANEL ───────────────────────────────────

@app.callback(
    Output("exp-selected-txn",   "data"),
    Output("exp-reload",         "data"),
    Output("exp-edit-status-msg","children"),
    Input("exp-save-btn",        "n_clicks"),
    Input("exp-cancel-btn",      "n_clicks"),
    Input({"type": "exp-edit-btn", "index": ALL}, "n_clicks"),
    Input({"type": "exp-approve-btn", "index": ALL}, "n_clicks"),
    Input({"type": "exp-reject-btn",  "index": ALL}, "n_clicks"),
    State("exp-edit-cat",        "value"),
    State("exp-edit-sub",        "value"),
    State("exp-edit-status",     "value"),
    State("exp-edit-notes",      "value"),
    State("exp-selected-txn",    "data"),
    State("exp-reload",          "data"),
    prevent_initial_call=True,
)
def handle_edit_actions(save_clicks, cancel_clicks, edit_clicks,
                        approve_clicks, reject_clicks,
                        cat, sub, status, notes,
                        selected_txn, current_reload):
    now      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    triggered = ctx.triggered_id
    if not triggered:
        return selected_txn, current_reload, ""

    ttype = triggered.get("type") if isinstance(triggered, dict) else triggered
    tid   = triggered.get("index") if isinstance(triggered, dict) else None

    # Row edit button clicked — select this transaction
    if ttype == "exp-edit-btn":
        if not any(edit_clicks):
            return selected_txn, current_reload, ""
        return tid, current_reload, ""

    # Cancel — deselect
    elif ttype == "exp-cancel-btn":
        return None, current_reload, ""

    # Save
    elif ttype == "exp-save-btn" and save_clicks and selected_txn:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""UPDATE expenditure_transactions
                        SET category=?, subcategory=?, status=?, notes=?, updated_at=?
                        WHERE id=?""",
                     (cat, sub or None, status or "confirmed",
                      notes or None, now, selected_txn))
        # Update mapping table
        desc = conn.execute(
            "SELECT description_clean FROM expenditure_transactions WHERE id=?",
            (selected_txn,)).fetchone()
        if desc and desc[0] and cat:
            conn.execute("""INSERT OR REPLACE INTO expenditure_mappings
                            (description_clean, category, subcategory,
                             match_type, confidence, updated_at)
                            VALUES (?, ?, ?, 'manual', 1.0, ?)
                            ON CONFLICT(description_clean) DO UPDATE SET
                                category=excluded.category,
                                subcategory=excluded.subcategory,
                                updated_at=excluded.updated_at
                         """, (desc[0], cat, sub or None, now))
        # Update subcategory autocomplete
        if sub and cat:
            conn.execute("""INSERT OR REPLACE INTO expenditure_subcategories
                            (category, subcategory, use_count)
                            VALUES (?, ?,
                            COALESCE((SELECT use_count FROM expenditure_subcategories
                                      WHERE category=? AND subcategory=?), 0) + 1)
                         """, (cat, sub, cat, sub))
        conn.commit()
        conn.close()
        return None, (current_reload or 0) + 1, "✓ Saved"

    # Approve netting pair
    elif ttype == "exp-approve-btn":
        if not any(approve_clicks):
            return selected_txn, current_reload, ""
        ids = [int(x) for x in str(tid).split("_")]
        conn = sqlite3.connect(DB_PATH)
        for i in ids:
            conn.execute("""UPDATE expenditure_transactions
                            SET status='internal', category='Transfer', updated_at=?
                            WHERE id=?""", (now, i))
        conn.commit()
        conn.close()
        return selected_txn, (current_reload or 0) + 1, ""

    # Reject netting pair
    elif ttype == "exp-reject-btn":
        if not any(reject_clicks):
            return selected_txn, current_reload, ""
        ids = [int(x) for x in str(tid).split("_")]
        conn = sqlite3.connect(DB_PATH)
        for i in ids:
            conn.execute("""UPDATE expenditure_transactions
                            SET netting_id=-1, updated_at=? WHERE id=?""",
                         (now, i))
        conn.commit()
        conn.close()
        return selected_txn, (current_reload or 0) + 1, ""

    return selected_txn, current_reload, ""


@app.callback(
    Output("exp-edit-panel", "style"),
    Output("exp-edit-cat",   "value"),
    Output("exp-edit-sub",   "value"),
    Output("exp-edit-status","value"),
    Output("exp-edit-notes", "value"),
    Output("exp-edit-desc",  "children"),
    Input("exp-selected-txn","data"),
)
def load_edit_panel(selected_txn):
    panel_hide = {"display": "none"}
    panel_show = {"display": "block", "borderLeft": f"4px solid {ACCENT}", **CARD}
    if not selected_txn:
        return panel_hide, None, "", "confirmed", "", ""
    conn = sqlite3.connect(DB_PATH)
    row  = conn.execute("""SELECT description_raw, amount, source, category,
                                  subcategory, status, notes
                           FROM expenditure_transactions WHERE id=?""",
                        (selected_txn,)).fetchone()
    conn.close()
    if not row:
        return panel_hide, None, "", "confirmed", "", ""
    desc_raw, amount, source, cat, sub, status, notes = row
    amt_str  = fmt_bracket(amount)
    desc_str = f"{desc_raw}  |  {amt_str}  |  {source}"
    return panel_show, cat, sub or "", status or "confirmed", notes or "", desc_str


# ── EXPENDITURE: OVERVIEW ─────────────────────────────────────

@app.callback(
    Output("exp-overview-div",   "children"),
    Output("exp-import-status",  "children"),
    Output("exp-collapsed-cats", "data"),
    Input("exp-sub-tabs",        "value"),
    Input("exp-filter-from",     "date"),
    Input("exp-filter-to",       "date"),
    Input("exp-filter-category", "value"),
    Input("exp-filter-source",   "value"),
    Input("exp-reload",          "data"),
    Input("exp-import-btn",      "n_clicks"),
    Input({"type": "exp-collapse-btn", "index": ALL}, "n_clicks"),
    State("exp-collapsed-cats",  "data"),
    prevent_initial_call=False,
)
def update_overview(sub, date_from, date_to, cat_filter, source_filter,
                    reload, import_clicks, collapse_clicks, collapsed_cats):
    if sub != "sub-overview":
        return html.Div(), "", collapsed_cats or []

    import_status = ""
    triggered     = ctx.triggered_id
    collapsed     = list(collapsed_cats or [])

    if triggered == "exp-import-btn" and import_clicks:
        try:
            import importlib.util, io
            from contextlib import redirect_stdout
            spec = importlib.util.spec_from_file_location(
                "import_transactions", "import_transactions.py")
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            buf = io.StringIO()
            with redirect_stdout(buf):
                mod.main()
            lines = [l for l in buf.getvalue().split("\n")
                     if "New:" in l or "Total new" in l]
            import_status = "✓ " + " | ".join(lines) if lines else "✓ Import complete"
        except Exception as e:
            import_status = f"Import error: {str(e)[:100]}"

    elif isinstance(triggered, dict) and triggered.get("type") == "exp-collapse-btn":
        cat = triggered["index"]
        if cat in collapsed:
            collapsed.remove(cat)
        else:
            collapsed.append(cat)

    conn   = sqlite3.connect(DB_PATH)
    where  = ["status NOT IN ('internal', 'split')", "category IS NOT NULL"]
    params = []
    if date_from:
        where.append("date >= ?"); params.append(date_from)
    if date_to:
        where.append("date <= ?"); params.append(date_to)
    if cat_filter:
        phs = ",".join("?" * len(cat_filter))
        where.append(f"category IN ({phs})"); params.extend(cat_filter)
    if source_filter:
        phs = ",".join("?" * len(source_filter))
        where.append(f"source IN ({phs})"); params.extend(source_filter)

    rows = conn.execute(f"""
        SELECT strftime('%Y-%m', date) as ym,
               category,
               COALESCE(subcategory, '') as subcategory,
               SUM(amount) as total
        FROM expenditure_transactions
        WHERE {" AND ".join(where)}
        GROUP BY ym, category, subcategory
        ORDER BY category, subcategory, ym
    """, params).fetchall()
    conn.close()

    if not rows:
        return html.P("No data for selected filters.",
                      style={"color": "#999", "fontSize": "12px"}), import_status, collapsed

    df_piv = pd.DataFrame(rows, columns=["ym", "category", "subcategory", "total"])
    months = sorted(df_piv["ym"].unique())
    years  = sorted(set(m[:4] for m in months))

    th_base = {"backgroundColor": "#2c1a3a", "color": "white",
                "padding": "5px 8px", "fontSize": "10px", "fontWeight": "600",
                "textAlign": "right", "whiteSpace": "nowrap",
                "borderRight": "1px solid #3d2a5a"}

    year_cells = [html.Th("Category", style={**th_base, "textAlign": "left",
                                              "minWidth": "150px"})]
    for yr in years:
        yr_months = [m for m in months if m[:4] == yr]
        year_cells.append(html.Th(yr, colSpan=len(yr_months) + 1,
                                   style={**th_base, "textAlign": "center",
                                          "borderLeft": "2px solid #6d3b8c"}))

    month_names = {"01":"Jan","02":"Feb","03":"Mar","04":"Apr","05":"May",
                   "06":"Jun","07":"Jul","08":"Aug","09":"Sep","10":"Oct",
                   "11":"Nov","12":"Dec"}
    month_cells = [html.Th("", style={**th_base, "textAlign": "left"})]
    for yr in years:
        yr_months = [m for m in months if m[:4] == yr]
        for m in yr_months:
            month_cells.append(html.Th(month_names[m[5:]], style=th_base))
        month_cells.append(html.Th("Total", style={**th_base,
                                                    "backgroundColor": "#1a0a2e"}))

    table_rows = []
    cat_totals = df_piv.groupby("category")["total"].sum()
    categories = sorted(df_piv["category"].unique(),
                        key=lambda c: cat_totals.get(c, 0))

    for cat in categories:
        cat_df       = df_piv[df_piv["category"] == cat]
        is_collapsed = cat in collapsed
        cat_col      = EXP_CAT_COLOURS.get(cat, "#666")

        cat_cells = [html.Td([
            html.Button("▼" if not is_collapsed else "▶",
                id={"type": "exp-collapse-btn", "index": cat},
                n_clicks=0,
                style={"background": "none", "border": "none",
                       "cursor": "pointer", "fontSize": "9px",
                       "color": cat_col, "padding": "0 4px 0 0",
                       "verticalAlign": "middle"}),
            html.Span(cat, style={"fontWeight": "700", "color": cat_col,
                                   "fontSize": "12px"}),
        ], style={"padding": "5px 8px", "whiteSpace": "nowrap",
                  "backgroundColor": "#f8f5ff"})]

        for yr in years:
            yr_months = [m for m in months if m[:4] == yr]
            for m in yr_months:
                val = cat_df[cat_df["ym"] == m]["total"].sum()
                cat_cells.append(html.Td(
                    fmt_bracket(val) if val != 0 else "—",
                    style={"padding": "4px 8px", "fontSize": "11px",
                           "textAlign": "right", "fontFamily": "monospace",
                           "color": fmt_bracket_color(val), "fontWeight": "600",
                           "backgroundColor": "#f8f5ff", "whiteSpace": "nowrap"}))
            yr_total = cat_df[cat_df["ym"].str[:4] == yr]["total"].sum()
            cat_cells.append(html.Td(
                fmt_bracket(yr_total) if yr_total != 0 else "—",
                style={"padding": "4px 8px", "fontSize": "11px",
                       "textAlign": "right", "fontFamily": "monospace",
                       "color": fmt_bracket_color(yr_total), "fontWeight": "700",
                       "backgroundColor": "#ede8f5",
                       "borderLeft": "2px solid #6d3b8c", "whiteSpace": "nowrap"}))

        table_rows.append(html.Tr(cat_cells,
                                   style={"borderBottom": "1px solid #e8e0f0"}))

        if not is_collapsed:
            subcats = sorted(cat_df["subcategory"].unique())
            for subcat in subcats:
                sub_df  = cat_df[cat_df["subcategory"] == subcat]
                sub_cells = [html.Td(
                    html.Span(subcat or "—",
                              style={"paddingLeft": "24px", "fontSize": "11px",
                                     "color": "#555"}),
                    style={"padding": "3px 8px", "whiteSpace": "nowrap"})]
                for yr in years:
                    yr_months = [m for m in months if m[:4] == yr]
                    for m in yr_months:
                        val = sub_df[sub_df["ym"] == m]["total"].sum()
                        sub_cells.append(html.Td(
                            fmt_bracket(val) if val != 0 else "",
                            style={"padding": "3px 8px", "fontSize": "10px",
                                   "textAlign": "right", "fontFamily": "monospace",
                                   "color": fmt_bracket_color(val),
                                   "whiteSpace": "nowrap"}))
                    yr_sub = sub_df[sub_df["ym"].str[:4] == yr]["total"].sum()
                    sub_cells.append(html.Td(
                        fmt_bracket(yr_sub) if yr_sub != 0 else "",
                        style={"padding": "3px 8px", "fontSize": "10px",
                               "textAlign": "right", "fontFamily": "monospace",
                               "color": fmt_bracket_color(yr_sub), "fontWeight": "600",
                               "borderLeft": "2px solid #6d3b8c",
                               "whiteSpace": "nowrap"}))
                table_rows.append(html.Tr(sub_cells,
                    style={"borderBottom": "1px solid #f5f0ff",
                           "backgroundColor": "white"}))

    # Grand total
    total_cells = [html.Td("TOTAL",
                           style={"padding": "6px 8px", "fontSize": "12px",
                                  "fontWeight": "700", "color": "#1a0a2e",
                                  "borderTop": "2px solid #2c1a3a"})]
    for yr in years:
        yr_months = [m for m in months if m[:4] == yr]
        for m in yr_months:
            val = df_piv[df_piv["ym"] == m]["total"].sum()
            total_cells.append(html.Td(
                fmt_bracket(val) if val != 0 else "—",
                style={"padding": "6px 8px", "fontSize": "11px",
                       "textAlign": "right", "fontFamily": "monospace",
                       "color": fmt_bracket_color(val), "fontWeight": "700",
                       "borderTop": "2px solid #2c1a3a", "whiteSpace": "nowrap"}))
        yr_tot = df_piv[df_piv["ym"].str[:4] == yr]["total"].sum()
        total_cells.append(html.Td(
            fmt_bracket(yr_tot) if yr_tot != 0 else "—",
            style={"padding": "6px 8px", "fontSize": "11px",
                   "textAlign": "right", "fontFamily": "monospace",
                   "color": fmt_bracket_color(yr_tot), "fontWeight": "700",
                   "borderTop": "2px solid #2c1a3a",
                   "borderLeft": "2px solid #6d3b8c",
                   "backgroundColor": "#ede8f5", "whiteSpace": "nowrap"}))
    table_rows.append(html.Tr(total_cells))

    pivot = html.Div(
        html.Table(
            [html.Thead([html.Tr(year_cells), html.Tr(month_cells)]),
             html.Tbody(table_rows)],
            style={"width": "100%", "borderCollapse": "collapse"}),
        style={**CARD, "overflowX": "auto", "padding": "0"})

    return pivot, import_status, collapsed


# ── EXPENDITURE: TRANSACTIONS ─────────────────────────────────

@app.callback(
    Output("exp-transactions-div", "children"),
    Input("exp-sub-tabs",          "value"),
    Input("exp-filter-from",       "date"),
    Input("exp-filter-to",         "date"),
    Input("exp-filter-category",   "value"),
    Input("exp-filter-source",     "value"),
    Input("exp-reload",            "data"),
    Input("exp-selected-txn",      "data"),
    prevent_initial_call=False,
)
def update_transactions(sub, date_from, date_to, cat_filter,
                        source_filter, reload, selected_txn):
    if sub != "sub-transactions":
        return html.Div()

    conn   = sqlite3.connect(DB_PATH)
    where  = ["status NOT IN ('internal', 'split')"]
    params = []
    if date_from:
        where.append("date >= ?"); params.append(date_from)
    if date_to:
        where.append("date <= ?"); params.append(date_to)
    if cat_filter:
        phs = ",".join("?" * len(cat_filter))
        where.append(f"category IN ({phs})"); params.extend(cat_filter)
    if source_filter:
        phs = ",".join("?" * len(source_filter))
        where.append(f"source IN ({phs})"); params.extend(source_filter)

    txns = conn.execute(f"""
        SELECT id, date, description_raw, amount, source,
               category, subcategory, mapped_by, confidence, status
        FROM expenditure_transactions
        WHERE {" AND ".join(where)}
        ORDER BY date DESC, id DESC LIMIT 500
    """, params).fetchall()
    conn.close()

    if not txns:
        return html.P("No transactions found.",
                      style={"color": "#999", "fontSize": "12px", "padding": "12px"})

    total_spend  = sum(abs(r[3]) for r in txns if r[3] < 0)
    total_income = sum(r[3] for r in txns if r[3] > 0)
    net          = total_income - total_spend

    summary = html.Div([
        html.Span(f"Income: {fmt_bracket(total_income)}",
                  style={"color": "#1a7a1a", "fontWeight": "700",
                         "fontSize": "13px", "marginRight": "20px",
                         "fontFamily": "monospace"}),
        html.Span(f"Spend: {fmt_bracket(-total_spend)}",
                  style={"color": "#c0392b", "fontWeight": "700",
                         "fontSize": "13px", "marginRight": "20px",
                         "fontFamily": "monospace"}),
        html.Span(f"Net: {fmt_bracket(net)}",
                  style={"color": fmt_bracket_color(net), "fontWeight": "700",
                         "fontSize": "13px", "fontFamily": "monospace"}),
        html.Span(f"  ({len(txns)} rows)",
                  style={"color": "#999", "fontSize": "11px"}),
    ], style={**CARD, "padding": "10px 18px"})

    header = html.Tr([
        html.Th(c, style={"backgroundColor": "#2c1a3a", "color": "white",
                          "padding": "6px 8px", "fontSize": "11px",
                          "fontWeight": "600", "textAlign": "left" if i < 3 else "right",
                          "whiteSpace": "nowrap"})
        for i, c in enumerate(["Date", "Description", "Source",
                                "Amount", "Category", "Subcategory", "By", ""])
    ])

    t_rows = []
    for (txn_id, txn_date, desc_raw, amount, source,
         category, subcategory, mapped_by, confidence, status) in txns:

        amt_color  = "#1a7a1a" if amount > 0 else "#c0392b"
        is_selected = txn_id == selected_txn
        row_bg     = "#f0eafa" if is_selected else (
                     "#fff8f0" if status == "needs_review" else "transparent")
        cat_col    = EXP_CAT_COLOURS.get(category or "", "#666")

        by_map = {"manual": ("✓","#1a7a1a"), "exact": ("=","#2E75B6"),
                  "keyword": ("K","#2E75B6"), "ai": ("AI","#8e44ad")}
        if mapped_by == "fuzzy":
            pct = int((confidence or 0)*100)
            by_label, by_color = f"{pct}%", ("#e67e22" if pct < 90 else "#2E75B6")
        else:
            by_label, by_color = by_map.get(mapped_by or "", ("?","#c0392b"))

        ndisp = desc_raw if len(desc_raw) <= 38 else desc_raw[:38]+"…"

        t_rows.append(html.Tr([
            html.Td(txn_date,
                    style={"padding": "5px 8px", "fontSize": "11px",
                           "color": "#555", "whiteSpace": "nowrap"}),
            html.Td(html.Span(ndisp, title=desc_raw),
                    style={"padding": "5px 8px", "fontSize": "11px",
                           "color": "#1a3a5c", "whiteSpace": "nowrap"}),
            html.Td(source,
                    style={"padding": "5px 8px", "fontSize": "10px",
                           "color": "#888", "textAlign": "right",
                           "whiteSpace": "nowrap"}),
            html.Td(fmt_bracket(amount),
                    style={"padding": "5px 8px", "fontSize": "11px",
                           "textAlign": "right", "fontFamily": "monospace",
                           "fontWeight": "600", "color": amt_color,
                           "whiteSpace": "nowrap"}),
            html.Td(html.Span(category or "—",
                              style={"color": cat_col, "fontWeight": "600",
                                     "fontSize": "11px"}),
                    style={"padding": "5px 8px", "whiteSpace": "nowrap"}),
            html.Td(subcategory or "—",
                    style={"padding": "5px 8px", "fontSize": "11px",
                           "color": "#666", "whiteSpace": "nowrap"}),
            html.Td(html.Span(by_label,
                              style={"fontSize": "10px", "fontWeight": "700",
                                     "color": by_color}),
                    style={"padding": "5px 8px", "textAlign": "center"}),
            html.Td(
                html.Button("✎ Edit",
                    id={"type": "exp-edit-btn", "index": txn_id},
                    n_clicks=0,
                    style={"backgroundColor": ACCENT if is_selected else "#f0eafa",
                           "color": "white" if is_selected else ACCENT,
                           "border": f"1px solid {ACCENT}",
                           "borderRadius": "3px", "padding": "2px 8px",
                           "fontSize": "10px", "cursor": "pointer",
                           "whiteSpace": "nowrap"}),
                style={"padding": "4px 8px"}),
        ], style={"borderBottom": "1px solid #f0f3f7",
                  "backgroundColor": row_bg}))

    table = html.Div(
        html.Table([html.Thead(header), html.Tbody(t_rows)],
                   style={"width": "100%", "borderCollapse": "collapse"}),
        style={**CARD, "overflowX": "auto", "padding": "0"})

    return html.Div([summary, table])


# ── EXPENDITURE: REVIEW ───────────────────────────────────────

@app.callback(
    Output("exp-review-div", "children"),
    Input("exp-sub-tabs",    "value"),
    Input("exp-reload",      "data"),
    Input("exp-selected-txn","data"),
    prevent_initial_call=False,
)
def update_review(sub, reload, selected_txn):
    if sub != "sub-review":
        return html.Div()

    conn = sqlite3.connect(DB_PATH)
    review_txns = conn.execute("""
        SELECT id, date, description_raw, amount, source, category, subcategory
        FROM expenditure_transactions
        WHERE status='needs_review'
        ORDER BY date DESC LIMIT 300
    """).fetchall()

    netting = conn.execute("""
        SELECT a.id, a.date, a.description_raw, a.amount, a.source,
               b.id, b.date, b.description_raw, b.amount, b.source
        FROM expenditure_transactions a
        JOIN expenditure_transactions b
            ON ABS(a.amount) = ABS(b.amount)
            AND a.amount * b.amount < 0
            AND ABS(julianday(a.date) - julianday(b.date)) <= 5
            AND a.id < b.id
            AND a.status NOT IN ('internal','split')
            AND b.status NOT IN ('internal','split')
            AND (a.netting_id IS NULL OR a.netting_id != -1)
            AND (b.netting_id IS NULL OR b.netting_id != -1)
            AND ABS(a.amount) >= 100
        ORDER BY a.date DESC LIMIT 50
    """).fetchall()
    conn.close()

    sections = []

    if review_txns:
        rev_rows = []
        for (txn_id, txn_date, desc_raw, amount, source,
             category, subcategory) in review_txns:

            is_selected = txn_id == selected_txn
            amt_color   = "#1a7a1a" if amount > 0 else "#c0392b"
            cat_col     = EXP_CAT_COLOURS.get(category or "", "#666")
            row_bg      = "#f0eafa" if is_selected else "#fff8f0"
            ndisp       = desc_raw if len(desc_raw) <= 40 else desc_raw[:40]+"…"

            rev_rows.append(html.Tr([
                html.Td(txn_date,
                        style={"padding": "5px 8px", "fontSize": "11px",
                               "color": "#555", "whiteSpace": "nowrap"}),
                html.Td(html.Span(ndisp, title=desc_raw),
                        style={"padding": "5px 8px", "fontSize": "11px",
                               "color": "#1a3a5c"}),
                html.Td(source,
                        style={"padding": "5px 8px", "fontSize": "10px",
                               "color": "#888", "textAlign": "right"}),
                html.Td(fmt_bracket(amount),
                        style={"padding": "5px 8px", "fontSize": "11px",
                               "textAlign": "right", "fontFamily": "monospace",
                               "fontWeight": "600", "color": amt_color}),
                html.Td(html.Span(category or "—",
                                  style={"color": cat_col, "fontWeight": "600",
                                         "fontSize": "11px"}),
                        style={"padding": "5px 8px"}),
                html.Td(subcategory or "—",
                        style={"padding": "5px 8px", "fontSize": "11px",
                               "color": "#666"}),
                html.Td(
                    html.Button("✎ Edit",
                        id={"type": "exp-edit-btn", "index": txn_id},
                        n_clicks=0,
                        style={"backgroundColor": ACCENT if is_selected else "#fff8f0",
                               "color": "white" if is_selected else ACCENT,
                               "border": f"1px solid {ACCENT}",
                               "borderRadius": "3px", "padding": "2px 8px",
                               "fontSize": "10px", "cursor": "pointer"}),
                    style={"padding": "4px 8px"}),
            ], style={"borderBottom": "1px solid #f0f3f7",
                      "backgroundColor": row_bg}))

        rev_hdr = html.Tr([
            html.Th(c, style={"backgroundColor": "#e67e22", "color": "white",
                              "padding": "5px 8px", "fontSize": "11px",
                              "fontWeight": "600"})
            for c in ["Date","Description","Account","Amount",
                      "Category","Subcategory",""]
        ])
        sections.append(html.Div([
            html.P(f"NEEDS REVIEW ({len(review_txns)})",
                   style={**SECTION_TITLE,"color":"#e67e22","marginBottom":"8px"}),
            html.P("Click ✎ Edit to assign category and subcategory.",
                   style={"fontSize":"11px","color":"#aaa",
                          "marginBottom":"8px","marginTop":"-6px"}),
            html.Div(
                html.Table([html.Thead(rev_hdr), html.Tbody(rev_rows)],
                           style={"width":"100%","borderCollapse":"collapse"}),
                style={"overflowX":"auto"}),
        ], style=CARD))

    if netting:
        net_rows = []
        for (a_id,a_date,a_desc,a_amt,a_src,
             b_id,b_date,b_desc,b_amt,b_src) in netting:
            pair_id = f"{a_id}_{b_id}"
            net_rows.append(html.Tr([
                html.Td(a_date, style={"padding":"5px 8px","fontSize":"11px",
                                       "color":"#555","whiteSpace":"nowrap"}),
                html.Td(a_desc[:32], title=a_desc,
                        style={"padding":"5px 8px","fontSize":"11px"}),
                html.Td(a_src, style={"padding":"5px 8px","fontSize":"10px",
                                      "color":"#888"}),
                html.Td(fmt_bracket(a_amt),
                        style={"padding":"5px 8px","fontSize":"11px",
                               "fontFamily":"monospace",
                               "color":fmt_bracket_color(a_amt),
                               "textAlign":"right"}),
                html.Td("↔", style={"padding":"5px 4px","color":"#aaa",
                                    "textAlign":"center"}),
                html.Td(b_date, style={"padding":"5px 8px","fontSize":"11px",
                                       "color":"#555","whiteSpace":"nowrap"}),
                html.Td(b_desc[:32], title=b_desc,
                        style={"padding":"5px 8px","fontSize":"11px"}),
                html.Td(b_src, style={"padding":"5px 8px","fontSize":"10px",
                                      "color":"#888"}),
                html.Td(fmt_bracket(b_amt),
                        style={"padding":"5px 8px","fontSize":"11px",
                               "fontFamily":"monospace",
                               "color":fmt_bracket_color(b_amt),
                               "textAlign":"right"}),
                html.Td([
                    html.Button("✓ Approve",
                        id={"type":"exp-approve-btn","index":pair_id},
                        n_clicks=0,
                        style={"backgroundColor":"#1a7a1a","color":"white",
                               "border":"none","borderRadius":"3px",
                               "padding":"3px 8px","fontSize":"10px",
                               "cursor":"pointer","marginRight":"4px",
                               "whiteSpace":"nowrap"}),
                    html.Button("✕ Reject",
                        id={"type":"exp-reject-btn","index":pair_id},
                        n_clicks=0,
                        style={"backgroundColor":"#c0392b","color":"white",
                               "border":"none","borderRadius":"3px",
                               "padding":"3px 8px","fontSize":"10px",
                               "cursor":"pointer","whiteSpace":"nowrap"}),
                ], style={"padding":"4px 8px","whiteSpace":"nowrap"}),
            ], style={"borderBottom":"1px solid #f0f3f7"}))

        net_hdr = html.Tr([
            html.Th(c, style={"backgroundColor":"#95a5a6","color":"white",
                              "padding":"5px 8px","fontSize":"11px","fontWeight":"600"})
            for c in ["Date","Description","Account","Amount","",
                      "Date","Description","Account","Amount",""]
        ])
        sections.append(html.Div([
            html.P(f"NETTING CANDIDATES ({len(netting)})",
                   style={**SECTION_TITLE,"marginBottom":"8px"}),
            html.P("Matched pairs (ABS ≥ £100, within 5 days). Approve = mark both internal. Reject = dismiss permanently.",
                   style={"fontSize":"11px","color":"#aaa",
                          "marginBottom":"8px","marginTop":"-6px"}),
            html.Div(
                html.Table([html.Thead(net_hdr),html.Tbody(net_rows)],
                           style={"width":"100%","borderCollapse":"collapse"}),
                style={"overflowX":"auto"}),
        ], style=CARD))

    if not sections:
        sections = [html.P("Nothing to review — all confirmed!",
                           style={"color":"#1a7a1a","fontSize":"13px",
                                  "padding":"12px","fontWeight":"600"})]

    return html.Div(sections)


# ── EXPENDITURE: RULES ────────────────────────────────────────

@app.callback(
    Output("exp-rules-div",      "children"),
    Output("exp-rules-status",   "children"),
    Input("exp-sub-tabs",        "value"),
    Input("exp-reload",          "data"),
    Input("exp-rule-add-btn",    "n_clicks"),
    Input({"type": "exp-rule-del-btn", "index": ALL}, "n_clicks"),
    State("exp-rule-pattern",    "value"),
    State("exp-rule-matchtype",  "value"),
    State("exp-rule-category",   "value"),
    State("exp-rule-subcategory","value"),
    State("exp-rule-priority",   "value"),
    prevent_initial_call=False,
)
def update_rules(sub, reload, add_clicks, del_clicks,
                 pattern, matchtype, category, subcategory, priority):
    if sub != "sub-rules":
        return html.Div(), ""

    now      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    triggered = ctx.triggered_id
    conn     = sqlite3.connect(DB_PATH)
    status_msg = ""

    if triggered == "exp-rule-add-btn" and add_clicks and pattern and category:
        conn.execute("""INSERT INTO expenditure_rules
                        (pattern,match_type,category,subcategory,priority,active,created_at)
                        VALUES(?,?,?,?,?,1,?)""",
                     (pattern.upper(), matchtype or "contains",
                      category, subcategory, int(priority or 50), now))
        conn.commit()
        status_msg = f"✓ Rule added: {pattern.upper()} → {category}"

    elif isinstance(triggered, dict) and triggered.get("type") == "exp-rule-del-btn":
        conn.execute("DELETE FROM expenditure_rules WHERE id=?",
                     (triggered["index"],))
        conn.commit()
        status_msg = "✓ Rule deleted"

    rules = conn.execute("""
        SELECT id, pattern, match_type, category, subcategory, priority
        FROM expenditure_rules WHERE active=1
        ORDER BY priority DESC, pattern
    """).fetchall()
    conn.close()

    th = {"backgroundColor": "#2c1a3a", "color": "white",
          "padding": "5px 8px", "fontSize": "11px", "fontWeight": "600",
          "whiteSpace": "nowrap"}
    header = html.Tr([
        html.Th(c, style={**th, "textAlign": "left" if i == 0 else "right"})
        for i, c in enumerate(["Pattern","Match","Category",
                                "Subcategory","Priority",""])
    ])
    r_rows = []
    for rule_id, pat, match_type, cat, sub_cat, pri in rules:
        r_rows.append(html.Tr([
            html.Td(pat, style={"padding":"3px 8px","fontSize":"11px",
                                "fontFamily":"monospace","color":"#1a3a5c"}),
            html.Td(match_type, style={"padding":"3px 8px","fontSize":"10px",
                                       "textAlign":"right","color":"#888"}),
            html.Td(cat, style={"padding":"3px 8px","fontSize":"11px",
                                "textAlign":"right",
                                "color":EXP_CAT_COLOURS.get(cat,"#666"),
                                "fontWeight":"600"}),
            html.Td(sub_cat or "—", style={"padding":"3px 8px","fontSize":"11px",
                                            "textAlign":"right","color":"#666"}),
            html.Td(str(pri), style={"padding":"3px 8px","fontSize":"11px",
                                     "textAlign":"right","fontFamily":"monospace"}),
            html.Td(html.Button("✕",
                        id={"type":"exp-rule-del-btn","index":rule_id},
                        n_clicks=0,
                        style={"backgroundColor":"#c0392b","color":"white",
                               "border":"none","borderRadius":"3px",
                               "padding":"2px 5px","fontSize":"10px",
                               "cursor":"pointer"}),
                    style={"padding":"3px 6px","textAlign":"right"}),
        ], style={"borderBottom":"1px solid #f0f3f7"}))

    rules_table = html.Div(
        html.Table([html.Thead(header), html.Tbody(r_rows)],
                   style={"width":"100%","borderCollapse":"collapse"}),
        style={"overflowX":"auto"}
    ) if r_rows else html.P("No rules defined yet.",
                            style={"color":"#999","fontSize":"12px"})

    return rules_table, status_msg


# ── RUN ───────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8052, debug=True)