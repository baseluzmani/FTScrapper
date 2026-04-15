# dashboard.py
# Financial dashboard for FT Fund data.
# Run with: python3 dashboard.py
# Then open: http://localhost:8050

import dash
from dash import html, dcc, Input, Output, State, ALL, ctx
import plotly.graph_objects as go
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import numpy as np
import config

# ── 1. DATA LAYER ──────────────────────────────────────────────

DB_PATH = "data/funds.db"


def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT fund_id, fund_name, asset_type, date, open, high, low, close, volume
        FROM fund_prices
        ORDER BY fund_id, date
    """,
        conn,
    )
    conn.close()
    df["date"] = pd.to_datetime(df["date"])
    return df


def build_composite_data(df):
    """
    Build synthetic price series for each composite fund defined in config.COMPOSITE_FUNDS.
    Uses a rebased index approach:
      - Find the common date range across all components
      - Rebase each component to 100 on the first common date
      - Weighted average of rebased prices = composite index
    Returns a DataFrame in the same format as the real fund data.
    """
    composites = getattr(config, "COMPOSITE_FUNDS", [])
    if not composites:
        return pd.DataFrame()

    rows = []

    for comp in composites:
        fund_id = comp["fund_id"]
        fund_name = comp["display_name"]
        asset_type = comp.get("asset_type", "Fund")
        components = comp["components"]

        # Get price series for each component
        series = {}
        for c in components:
            cid = c["fund_id"]
            cdf = df[df["fund_id"] == cid][["date", "close"]].sort_values("date")
            if not cdf.empty:
                series[cid] = cdf.set_index("date")["close"]

        if len(series) == 0:
            continue

        # Find common dates across all components
        common_dates = None
        for s in series.values():
            dates = set(s.index)
            common_dates = dates if common_dates is None else common_dates & dates

        if not common_dates or len(common_dates) < 2:
            continue

        common_dates = sorted(common_dates)
        base_date = common_dates[0]

        # Rebase each component to 100 on base_date and apply weight
        composite_series = pd.Series(0.0, index=common_dates)
        for c in components:
            cid = c["fund_id"]
            weight = c["weight"]
            if cid not in series:
                continue
            s = series[cid].loc[common_dates]
            base_val = s.loc[base_date]
            if base_val == 0:
                continue
            rebased = (s / base_val) * 100
            composite_series += rebased * weight

        # Build rows in standard format
        for date, price in composite_series.items():
            rows.append(
                {
                    "fund_id": fund_id,
                    "fund_name": fund_name,
                    "asset_type": asset_type,
                    "date": date,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 0,
                }
            )

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    result["date"] = pd.to_datetime(result["date"])
    return result


def get_latest_price(df, fund_id):
    fund_df = df[df["fund_id"] == fund_id]
    if fund_df.empty:
        return None
    return fund_df.loc[fund_df["date"].idxmax(), "close"]


def calc_return(df, fund_id, days_back=None, from_date=None):
    fund_df = df[df["fund_id"] == fund_id].sort_values("date")
    if fund_df.empty:
        return None
    latest_price = fund_df.iloc[-1]["close"]
    if from_date:
        past_df = fund_df[fund_df["date"] <= pd.Timestamp(from_date)]
    else:
        past_df = fund_df[
            fund_df["date"] <= fund_df["date"].max() - timedelta(days=days_back)
        ]
    if past_df.empty:
        return None
    past_price = past_df.iloc[-1]["close"]
    if past_price == 0:
        return None
    return ((latest_price / past_price) - 1) * 100


def ytd_date():
    dec31 = datetime(datetime.now().year - 1, 12, 31)
    while dec31.weekday() >= 5:
        dec31 -= timedelta(days=1)
    return dec31.strftime("%Y-%m-%d")


def build_returns_table(df, since_date):
    funds = df[["fund_id", "fund_name", "asset_type"]].drop_duplicates(
        subset=["fund_id"]
    )
    rows = []
    for _, fund in funds.iterrows():
        fid = fund["fund_id"]
        fname = fund["fund_name"]
        atype = fund["asset_type"] if pd.notna(fund["asset_type"]) else "—"
        latest = get_latest_price(df, fid)
        rows.append(
            {
                "fund_id": fid,
                "Fund": fname,
                "Type": atype,
                "Price": round(latest, 2) if latest else None,
                "1D": calc_return(df, fid, days_back=1),
                "1W": calc_return(df, fid, days_back=5),
                "1M": calc_return(df, fid, days_back=21),
                "3M": calc_return(df, fid, days_back=63),
                "YTD": calc_return(df, fid, from_date=ytd_date()),
                "Since": calc_return(df, fid, from_date=since_date),
            }
        )
    result = pd.DataFrame(rows)
    result = result.sort_values("YTD", ascending=False, na_position="last")
    return result


def heatmap_color(val, vmin, vmax):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "rgb(240,240,240)"
    if val == 0:
        return "rgb(255,255,255)"
    if val > 0:
        intensity = min(val / max(abs(vmax), 0.001), 1.0)
        r = int(255 - intensity * 180)
        g = int(255 - intensity * 50)
        b = int(255 - intensity * 180)
        return f"rgb({r},{g},{b})"
    else:
        intensity = min(abs(val) / max(abs(vmin), 0.001), 1.0)
        r = int(255 - intensity * 50)
        g = int(255 - intensity * 180)
        b = int(255 - intensity * 180)
        return f"rgb({r},{g},{b})"


def get_top4_funds(df, from_date):
    funds = df["fund_id"].unique()
    returns = []
    for fid in funds:
        r = calc_return(df, fid, from_date=from_date)
        if r is not None:
            returns.append((fid, r))
    returns.sort(key=lambda x: x[1], reverse=True)
    return [fid for fid, _ in returns[:4]]


def render_returns_table(table_df, since_label, sort_state, header_type="market"):
    return_cols = ["1D", "1W", "1M", "3M", "YTD", "Since"]

    col_ranges = {}
    for col in return_cols:
        vals = table_df[col].dropna()
        col_ranges[col] = (vals.min(), vals.max()) if len(vals) > 0 else (0, 0)

    col_defs = [
        ("Fund", "Fund", False),
        ("Type", "Type", False),
        ("Price", "Price", False),
        ("1D %", "1D", True),
        ("1W %", "1W", True),
        ("1M %", "1M", True),
        ("3M %", "3M", True),
        ("YTD %", "YTD", True),
        (f"Since {since_label}", "Since", True),
    ]

    def sort_arrow(col_key):
        if sort_state["col"] == col_key:
            return " ▲" if sort_state["asc"] else " ▼"
        return " ⇅"

    header = html.Tr(
        [
            html.Th(
                f"{label}{sort_arrow(key)}",
                id={"type": f"sort-header-{header_type}", "col": key},
                n_clicks=0,
                style={
                    "backgroundColor": "#1a3a5c",
                    "color": "white",
                    "padding": "6px 12px",
                    "fontSize": "11px",
                    "fontWeight": "600",
                    "textAlign": "center" if label != "Fund" else "left",
                    "letterSpacing": "0.04em",
                    "whiteSpace": "nowrap",
                    "cursor": "pointer",
                    "userSelect": "none",
                },
            )
            for label, key, _ in col_defs
        ]
    )

    rows = []
    for _, row in table_df.iterrows():
        cells = [
            html.Td(
                row["Fund"],
                style={
                    "padding": "5px 12px",
                    "fontSize": "12px",
                    "fontWeight": "500",
                    "color": "#1a3a5c",
                    "whiteSpace": "nowrap",
                },
            ),
            html.Td(
                row["Type"],
                style={
                    "padding": "5px 12px",
                    "fontSize": "11px",
                    "textAlign": "center",
                    "color": "#666",
                    "whiteSpace": "nowrap",
                },
            ),
            html.Td(
                f"{row['Price']:.2f}" if row["Price"] else "N/A",
                style={
                    "padding": "5px 12px",
                    "fontSize": "12px",
                    "textAlign": "center",
                    "fontFamily": "monospace",
                    "color": "#333",
                },
            ),
        ]
        for col in return_cols:
            val = row[col]
            vmin, vmax = col_ranges[col]
            bg = heatmap_color(val, vmin, vmax)
            formatted = (
                f"{val:+.1f}%" if val is not None and not np.isnan(val) else "N/A"
            )
            cells.append(
                html.Td(
                    formatted,
                    style={
                        "padding": "5px 12px",
                        "fontSize": "12px",
                        "textAlign": "center",
                        "fontWeight": "600",
                        "fontFamily": "monospace",
                        "backgroundColor": bg,
                        "color": "#1a1a1a",
                        "borderRadius": "3px",
                    },
                )
            )
        rows.append(html.Tr(cells, style={"borderBottom": "1px solid #f0f3f7"}))

    return html.Table(
        [html.Thead(header), html.Tbody(rows)],
        style={"width": "100%", "borderCollapse": "collapse"},
    )


def build_relative_chart(df_combined, selected_funds, since_date):
    """Build a relative returns chart from a combined df (real + composite)."""
    fig = go.Figure()
    if not selected_funds:
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
        fund_df = df_combined[df_combined["fund_id"] == fund_id].copy()
        fund_df = fund_df[fund_df["date"] >= start].sort_values("date")
        if fund_df.empty or len(fund_df) < 2:
            continue

        base_price = fund_df.iloc[0]["close"]
        if base_price == 0:
            continue
        fund_df["return"] = ((fund_df["close"] / base_price) - 1) * 100
        fund_name = fund_df.iloc[0]["fund_name"]

        fig.add_trace(
            go.Scatter(
                x=fund_df["date"],
                y=fund_df["return"],
                mode="lines",
                name=fund_name,
                line=dict(width=2),
                hovertemplate="%{x|%d %b %Y}: %{y:.1f}%<extra>"
                + fund_name
                + "</extra>",
            )
        )

        idx_max = fund_df["return"].idxmax()
        idx_min = fund_df["return"].idxmin()
        last_row = fund_df.iloc[-1]

        for point, label, ay in [
            (fund_df.loc[idx_max], f"H: {fund_df.loc[idx_max, 'return']:+.1f}%", -18),
            (fund_df.loc[idx_min], f"L: {fund_df.loc[idx_min, 'return']:+.1f}%", 18),
            (last_row, f"▶ {last_row['return']:+.1f}%", 0),
        ]:
            fig.add_annotation(
                x=point["date"],
                y=point["return"],
                text=label,
                showarrow=True,
                arrowhead=0,
                arrowwidth=1,
                ax=20,
                ay=ay,
                font=dict(size=9, color="#333"),
                bgcolor="rgba(255,255,255,0.85)",
                bordercolor="#ccc",
                borderwidth=1,
                borderpad=2,
            )

    fig.update_layout(
        yaxis_tickformat="+.1f",
        yaxis_ticksuffix="%",
        hovermode="x unified",
        legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=10)),
        margin=dict(l=40, r=80, t=10, b=80),
        plot_bgcolor="white",
        paper_bgcolor="white",
        height=400,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#f0f0f0", tickfont=dict(size=10))
    fig.update_yaxes(
        showgrid=True,
        gridcolor="#f0f0f0",
        zeroline=True,
        zerolinecolor="#bbb",
        zerolinewidth=1,
        tickfont=dict(size=10),
    )
    return fig


# ── 2. APP SETUP ───────────────────────────────────────────────

app = dash.Dash(__name__, suppress_callback_exceptions=True)

df = load_data()

# Build composite data and merge with real data
df_composite = build_composite_data(df)
df_combined = (
    pd.concat([df, df_composite], ignore_index=True) if not df_composite.empty else df
)

# Fund options for dropdowns — real funds only (composites added separately)
funds = df[["fund_id", "fund_name"]].drop_duplicates()
fund_options = [
    {"label": row["fund_name"], "value": row["fund_id"]} for _, row in funds.iterrows()
]

# Add composite funds to options
composite_options = [
    {"label": c["display_name"], "value": c["fund_id"]}
    for c in getattr(config, "COMPOSITE_FUNDS", [])
]
all_fund_options = fund_options + composite_options

DEFAULT_DATE = "2025-12-31"
max_date = df["date"].max().date()
min_date = df["date"].min().date()
top4_default = get_top4_funds(df_combined, DEFAULT_DATE)

# Holdings options — real + composite
holding_ids_default = [h["fund_id"] for h in config.HOLDINGS]
composite_ids = [c["fund_id"] for c in getattr(config, "COMPOSITE_FUNDS", [])]
holdings_options = [
    o
    for o in all_fund_options
    if o["value"] in holding_ids_default or o["value"] in composite_ids
]

# ── 3. STYLES ──────────────────────────────────────────────────

CARD = {
    "backgroundColor": "#ffffff",
    "borderRadius": "8px",
    "padding": "14px 18px",
    "boxShadow": "0 1px 4px rgba(0,0,0,0.08)",
    "marginBottom": "12px",
}
SECTION_TITLE = {
    "color": "#1a3a5c",
    "fontSize": "11px",
    "fontWeight": "700",
    "letterSpacing": "0.08em",
    "textTransform": "uppercase",
    "marginBottom": "10px",
    "marginTop": "0",
}
TAB_STYLE = {
    "padding": "8px 20px",
    "fontSize": "12px",
    "fontWeight": "600",
    "color": "#666",
    "borderBottom": "2px solid transparent",
    "cursor": "pointer",
}
TAB_SELECTED_STYLE = {
    "padding": "8px 20px",
    "fontSize": "12px",
    "fontWeight": "600",
    "color": "#2E75B6",
    "borderBottom": "2px solid #2E75B6",
    "cursor": "pointer",
}

# ── 4. LAYOUT ──────────────────────────────────────────────────

app.layout = html.Div(
    [
        # Header
        html.Div(
            [
                html.Div(
                    [
                        html.Span(
                            "FUND",
                            style={
                                "color": "#2E75B6",
                                "fontWeight": "800",
                                "fontSize": "18px",
                                "letterSpacing": "0.1em",
                            },
                        ),
                        html.Span(
                            " DASHBOARD",
                            style={
                                "color": "#1a3a5c",
                                "fontWeight": "300",
                                "fontSize": "18px",
                                "letterSpacing": "0.1em",
                            },
                        ),
                    ]
                ),
                html.Span(
                    id="data-date-label",
                    style={"fontSize": "11px", "color": "#999", "alignSelf": "center"},
                ),
            ],
            style={
                "display": "flex",
                "justifyContent": "space-between",
                "alignItems": "center",
                "padding": "12px 20px",
                "backgroundColor": "#fff",
                "borderBottom": "2px solid #2E75B6",
                "marginBottom": "0",
            },
        ),
        # Tabs
        dcc.Tabs(
            id="main-tabs",
            value="tab-holdings",
            children=[
                dcc.Tab(
                    label="My Holdings",
                    value="tab-holdings",
                    style=TAB_STYLE,
                    selected_style=TAB_SELECTED_STYLE,
                ),
                dcc.Tab(
                    label="Market Overview",
                    value="tab-market",
                    style=TAB_STYLE,
                    selected_style=TAB_SELECTED_STYLE,
                ),
                dcc.Tab(
                    label="Data Editor",
                    value="tab-editor",
                    style=TAB_STYLE,
                    selected_style=TAB_SELECTED_STYLE,
                ),
            ],
            style={
                "backgroundColor": "#fff",
                "borderBottom": "1px solid #eee",
                "marginBottom": "0",
            },
        ),
        # ── HOLDINGS TAB
        html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.P(
                                    "MY HOLDINGS",
                                    style={**SECTION_TITLE, "marginBottom": "0"},
                                ),
                                html.Div(
                                    [
                                        html.Label(
                                            "Since:",
                                            style={
                                                "fontSize": "11px",
                                                "color": "#666",
                                                "marginRight": "6px",
                                                "alignSelf": "center",
                                            },
                                        ),
                                        dcc.DatePickerSingle(
                                            id="holdings-since-date",
                                            date=DEFAULT_DATE,
                                            min_date_allowed=min_date,
                                            max_date_allowed=max_date,
                                            display_format="DD MMM YYYY",
                                        ),
                                    ],
                                    style={"display": "flex", "alignItems": "center"},
                                ),
                            ],
                            style={
                                "display": "flex",
                                "justifyContent": "space-between",
                                "alignItems": "center",
                            },
                        ),
                    ],
                    style=CARD,
                ),
                html.Div(id="holdings-table-div"),
                html.Div(
                    [
                        html.Div(
                            [
                                html.P(
                                    "RELATIVE RETURNS",
                                    style={**SECTION_TITLE, "marginBottom": "0"},
                                ),
                            ],
                            style={"marginBottom": "10px"},
                        ),
                        html.Div(
                            [
                                html.Label(
                                    "Funds shown:",
                                    style={
                                        "fontSize": "11px",
                                        "color": "#666",
                                        "marginRight": "8px",
                                        "alignSelf": "center",
                                        "whiteSpace": "nowrap",
                                    },
                                ),
                                dcc.Dropdown(
                                    id="holdings-chart-selector",
                                    options=holdings_options,
                                    value=holding_ids_default,
                                    multi=True,
                                    placeholder="Select funds...",
                                    style={"fontSize": "12px", "flex": "1"},
                                ),
                            ],
                            style={
                                "display": "flex",
                                "alignItems": "center",
                                "marginBottom": "10px",
                            },
                        ),
                        dcc.Graph(
                            id="holdings-relative-chart",
                            config={"displayModeBar": False},
                        ),
                    ],
                    style=CARD,
                ),
            ],
            id="holdings-tab-content",
            style={
                "display": "block",
                "padding": "12px 16px 16px 16px",
                "maxWidth": "1200px",
                "margin": "0 auto",
            },
        ),
        # ── MARKET TAB
        html.Div(
            [
                html.Div(
                    [
                        html.P("LATEST PRICES & RETURNS", style=SECTION_TITLE),
                        html.Div(id="market-table-div"),
                    ],
                    style=CARD,
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.P(
                                    "RELATIVE RETURNS",
                                    style={**SECTION_TITLE, "marginBottom": "0"},
                                ),
                                html.Div(
                                    [
                                        html.Label(
                                            "From:",
                                            style={
                                                "fontSize": "11px",
                                                "color": "#666",
                                                "marginRight": "6px",
                                                "alignSelf": "center",
                                            },
                                        ),
                                        dcc.DatePickerSingle(
                                            id="market-since-date",
                                            date=DEFAULT_DATE,
                                            min_date_allowed=min_date,
                                            max_date_allowed=max_date,
                                            display_format="DD MMM YYYY",
                                        ),
                                    ],
                                    style={"display": "flex", "alignItems": "center"},
                                ),
                            ],
                            style={
                                "display": "flex",
                                "justifyContent": "space-between",
                                "alignItems": "center",
                                "marginBottom": "10px",
                            },
                        ),
                        html.Div(
                            [
                                html.Label(
                                    "Funds shown:",
                                    style={
                                        "fontSize": "11px",
                                        "color": "#666",
                                        "marginRight": "8px",
                                        "alignSelf": "center",
                                        "whiteSpace": "nowrap",
                                    },
                                ),
                                dcc.Dropdown(
                                    id="chart-fund-selector",
                                    options=all_fund_options,
                                    value=top4_default,
                                    multi=True,
                                    placeholder="Select funds...",
                                    style={"fontSize": "12px", "flex": "1"},
                                ),
                            ],
                            style={
                                "display": "flex",
                                "alignItems": "center",
                                "marginBottom": "10px",
                            },
                        ),
                        dcc.Graph(
                            id="relative-chart", config={"displayModeBar": False}
                        ),
                    ],
                    style=CARD,
                ),
            ],
            id="market-tab-content",
            style={
                "display": "none",
                "padding": "12px 16px 16px 16px",
                "maxWidth": "1200px",
                "margin": "0 auto",
            },
        ),
        # ── EDITOR TAB
        html.Div(
            [
                html.Div(
                    [
                        html.P("DATA EDITOR", style=SECTION_TITLE),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Label(
                                            "Fund:",
                                            style={
                                                "fontSize": "11px",
                                                "color": "#666",
                                                "marginBottom": "4px",
                                                "display": "block",
                                            },
                                        ),
                                        dcc.Dropdown(
                                            id="editor-fund-filter",
                                            options=fund_options,
                                            placeholder="Select a fund...",
                                            style={"fontSize": "12px"},
                                        ),
                                    ],
                                    style={"flex": "2", "marginRight": "12px"},
                                ),
                                html.Div(
                                    [
                                        html.Label(
                                            "From:",
                                            style={
                                                "fontSize": "11px",
                                                "color": "#666",
                                                "marginBottom": "4px",
                                                "display": "block",
                                            },
                                        ),
                                        dcc.DatePickerSingle(
                                            id="editor-date-from",
                                            date=(
                                                datetime.today() - timedelta(days=30)
                                            ).date(),
                                            min_date_allowed=min_date,
                                            max_date_allowed=max_date,
                                            display_format="DD MMM YYYY",
                                        ),
                                    ],
                                    style={"marginRight": "12px"},
                                ),
                                html.Div(
                                    [
                                        html.Label(
                                            "To:",
                                            style={
                                                "fontSize": "11px",
                                                "color": "#666",
                                                "marginBottom": "4px",
                                                "display": "block",
                                            },
                                        ),
                                        dcc.DatePickerSingle(
                                            id="editor-date-to",
                                            date=datetime.today().date(),
                                            min_date_allowed=min_date,
                                            max_date_allowed=max_date,
                                            display_format="DD MMM YYYY",
                                        ),
                                    ],
                                    style={"marginRight": "12px"},
                                ),
                                html.Div(
                                    [
                                        html.Label(
                                            " ",
                                            style={
                                                "fontSize": "11px",
                                                "display": "block",
                                                "marginBottom": "4px",
                                            },
                                        ),
                                        html.Button(
                                            "Search",
                                            id="editor-search-btn",
                                            n_clicks=0,
                                            style={
                                                "backgroundColor": "#1a3a5c",
                                                "color": "white",
                                                "border": "none",
                                                "borderRadius": "4px",
                                                "padding": "7px 16px",
                                                "fontSize": "12px",
                                                "cursor": "pointer",
                                            },
                                        ),
                                    ]
                                ),
                            ],
                            style={"display": "flex", "alignItems": "flex-end"},
                        ),
                    ],
                    style=CARD,
                ),
                html.Div(id="editor-results-div"),
                html.Div(id="editor-form-div"),
                html.Div(
                    id="editor-status",
                    style={
                        "fontSize": "12px",
                        "color": "#2E75B6",
                        "padding": "8px 0",
                        "fontWeight": "600",
                    },
                ),
                dcc.Store(id="editor-selected", data={}),
            ],
            id="editor-tab-content",
            style={
                "display": "none",
                "padding": "12px 16px 16px 16px",
                "maxWidth": "1200px",
                "margin": "0 auto",
            },
        ),
        # Shared stores
        dcc.Store(id="sort-state-holdings", data={"col": "YTD", "asc": False}),
        dcc.Store(id="sort-state-market", data={"col": "YTD", "asc": False}),
        dcc.Store(id="db-reload-trigger", data=0),
    ],
    style={
        "fontFamily": '"DM Sans", -apple-system, BlinkMacSystemFont, sans-serif',
        "backgroundColor": "#f0f3f7",
        "minHeight": "100vh",
    },
)


# ── 5. TAB VISIBILITY ──────────────────────────────────────────


@app.callback(
    Output("holdings-tab-content", "style"),
    Output("market-tab-content", "style"),
    Output("editor-tab-content", "style"),
    Output("data-date-label", "children"),
    Input("main-tabs", "value"),
    Input("db-reload-trigger", "data"),
)
def switch_tab(tab, reload_trigger):
    global df, df_composite, df_combined
    if reload_trigger:
        df = load_data()
        df_composite = build_composite_data(df)
        df_combined = (
            pd.concat([df, df_composite], ignore_index=True)
            if not df_composite.empty
            else df
        )

    date_label = f"Data as of {df['date'].max().strftime('%d %b %Y')}"
    base = {"padding": "12px 16px 16px 16px", "maxWidth": "1200px", "margin": "0 auto"}
    show = {**base, "display": "block"}
    hide = {**base, "display": "none"}

    if tab == "tab-holdings":
        return show, hide, hide, date_label
    elif tab == "tab-market":
        return hide, show, hide, date_label
    elif tab == "tab-editor":
        return hide, hide, show, date_label
    return show, hide, hide, date_label


# ── 6. HOLDINGS CALLBACKS ──────────────────────────────────────


@app.callback(
    Output("holdings-table-div", "children"),
    Output("sort-state-holdings", "data"),
    Input("holdings-since-date", "date"),
    Input({"type": "sort-header-holdings", "col": ALL}, "n_clicks"),
    State("sort-state-holdings", "data"),
)
def update_holdings(since_date, n_clicks, sort_state):
    since_date = since_date or DEFAULT_DATE
    since_label = pd.Timestamp(since_date).strftime("%d %b %y")

    triggered = ctx.triggered_id
    if (
        triggered
        and isinstance(triggered, dict)
        and triggered.get("type") == "sort-header-holdings"
    ):
        clicked_col = triggered["col"]
        if sort_state["col"] == clicked_col:
            sort_state["asc"] = not sort_state["asc"]
        else:
            sort_state["col"] = clicked_col
            sort_state["asc"] = False

    holding_ids = [h["fund_id"] for h in config.HOLDINGS]
    holding_names = {h["fund_id"]: h["display_name"] for h in config.HOLDINGS}

    # Add composite funds
    composites = getattr(config, "COMPOSITE_FUNDS", [])
    composite_ids = [c["fund_id"] for c in composites]
    comp_names = {c["fund_id"]: c["display_name"] for c in composites}

    all_ids = holding_ids + composite_ids
    all_names = {**holding_names, **comp_names}

    holdings_df = df_combined[df_combined["fund_id"].isin(all_ids)].copy()
    if holdings_df.empty:
        return (
            html.P(
                "No holdings found. Check config.py HOLDINGS list.",
                style={"color": "#999", "fontSize": "12px"},
            ),
            sort_state,
        )

    table_df = build_returns_table(holdings_df, since_date)
    table_df["Fund"] = table_df["fund_id"].map(lambda fid: all_names.get(fid, fid))

    sort_col = sort_state["col"]
    sort_asc = sort_state["asc"]
    if sort_col in table_df.columns:
        table_df = table_df.sort_values(
            sort_col, ascending=sort_asc, na_position="last"
        )

    sections = []
    for asset_type, group in table_df.groupby("Type", sort=False):
        sections.append(
            html.Div(
                [
                    html.P(
                        asset_type.upper(),
                        style={
                            **SECTION_TITLE,
                            "borderBottom": "1px solid #e0e0e0",
                            "paddingBottom": "4px",
                        },
                    ),
                    render_returns_table(
                        group, since_label, sort_state, header_type="holdings"
                    ),
                ],
                style=CARD,
            )
        )

    return html.Div(sections), sort_state


@app.callback(
    Output("holdings-relative-chart", "figure"),
    Input("holdings-chart-selector", "value"),
    Input("holdings-since-date", "date"),
)
def update_holdings_chart(selected_funds, since_date):
    return build_relative_chart(
        df_combined, selected_funds or [], since_date or DEFAULT_DATE
    )


# ── 7. MARKET CALLBACKS ────────────────────────────────────────


@app.callback(
    Output("market-table-div", "children"),
    Output("sort-state-market", "data"),
    Input("market-since-date", "date"),
    Input({"type": "sort-header-market", "col": ALL}, "n_clicks"),
    State("sort-state-market", "data"),
)
def update_market_table(since_date, n_clicks, sort_state):
    since_date = since_date or DEFAULT_DATE

    triggered = ctx.triggered_id
    if (
        triggered
        and isinstance(triggered, dict)
        and triggered.get("type") == "sort-header-market"
    ):
        clicked_col = triggered["col"]
        if sort_state["col"] == clicked_col:
            sort_state["asc"] = not sort_state["asc"]
        else:
            sort_state["col"] = clicked_col
            sort_state["asc"] = False

    table_df = build_returns_table(df_combined, since_date)
    sort_col = sort_state["col"]
    sort_asc = sort_state["asc"]
    if sort_col in table_df.columns:
        table_df = table_df.sort_values(
            sort_col, ascending=sort_asc, na_position="last"
        )

    since_label = pd.Timestamp(since_date).strftime("%d %b %y")
    return (
        render_returns_table(table_df, since_label, sort_state, header_type="market"),
        sort_state,
    )


@app.callback(
    Output("chart-fund-selector", "value"),
    Input("market-since-date", "date"),
    State("chart-fund-selector", "value"),
)
def update_top4(since_date, current):
    top4 = get_top4_funds(df_combined, since_date)
    return current if current else top4


@app.callback(
    Output("relative-chart", "figure"),
    Input("chart-fund-selector", "value"),
    Input("market-since-date", "date"),
)
def update_market_chart(selected_funds, since_date):
    return build_relative_chart(
        df_combined, selected_funds or [], since_date or DEFAULT_DATE
    )


# ── 8. EDITOR CALLBACKS ────────────────────────────────────────


@app.callback(
    Output("editor-results-div", "children"),
    Input("editor-search-btn", "n_clicks"),
    State("editor-fund-filter", "value"),
    State("editor-date-from", "date"),
    State("editor-date-to", "date"),
    prevent_initial_call=True,
)
def search_records(n_clicks, fund_id, date_from, date_to):
    if not fund_id:
        return html.P(
            "Please select a fund first.", style={"color": "#999", "fontSize": "12px"}
        )

    conn = sqlite3.connect(DB_PATH)
    records = pd.read_sql_query(
        """
        SELECT date, open, high, low, close, volume
        FROM fund_prices
        WHERE fund_id = ? AND date >= ? AND date <= ?
        ORDER BY date DESC
    """,
        conn,
        params=(fund_id, date_from, date_to),
    )
    conn.close()

    if records.empty:
        return html.P("No records found.", style={"color": "#999", "fontSize": "12px"})

    header = html.Tr(
        [
            html.Th(
                c,
                style={
                    "backgroundColor": "#1a3a5c",
                    "color": "white",
                    "padding": "6px 12px",
                    "fontSize": "11px",
                    "fontWeight": "600",
                    "textAlign": "center",
                    "whiteSpace": "nowrap",
                },
            )
            for c in ["Date", "Open", "High", "Low", "Close", "Volume", "Action"]
        ]
    )

    rows = []
    for _, row in records.iterrows():
        rows.append(
            html.Tr(
                [
                    html.Td(
                        row["date"],
                        style={
                            "padding": "5px 12px",
                            "fontSize": "12px",
                            "textAlign": "center",
                            "whiteSpace": "nowrap",
                        },
                    ),
                    html.Td(
                        f"{row['open']:.4f}",
                        style={
                            "padding": "5px 12px",
                            "fontSize": "12px",
                            "textAlign": "center",
                            "fontFamily": "monospace",
                        },
                    ),
                    html.Td(
                        f"{row['high']:.4f}",
                        style={
                            "padding": "5px 12px",
                            "fontSize": "12px",
                            "textAlign": "center",
                            "fontFamily": "monospace",
                        },
                    ),
                    html.Td(
                        f"{row['low']:.4f}",
                        style={
                            "padding": "5px 12px",
                            "fontSize": "12px",
                            "textAlign": "center",
                            "fontFamily": "monospace",
                        },
                    ),
                    html.Td(
                        f"{row['close']:.4f}",
                        style={
                            "padding": "5px 12px",
                            "fontSize": "12px",
                            "textAlign": "center",
                            "fontFamily": "monospace",
                        },
                    ),
                    html.Td(
                        str(int(row["volume"])),
                        style={
                            "padding": "5px 12px",
                            "fontSize": "12px",
                            "textAlign": "center",
                        },
                    ),
                    html.Td(
                        html.Button(
                            "Edit",
                            id={
                                "type": "edit-btn",
                                "date": row["date"],
                                "fund": fund_id,
                            },
                            n_clicks=0,
                            style={
                                "backgroundColor": "#2E75B6",
                                "color": "white",
                                "border": "none",
                                "borderRadius": "3px",
                                "padding": "3px 10px",
                                "fontSize": "11px",
                                "cursor": "pointer",
                            },
                        ),
                        style={"padding": "5px 12px", "textAlign": "center"},
                    ),
                ],
                style={"borderBottom": "1px solid #f0f3f7"},
            )
        )

    return html.Div(
        [
            html.P(
                f"{len(records)} records found",
                style={"fontSize": "11px", "color": "#999", "marginBottom": "8px"},
            ),
            html.Table(
                [html.Thead(header), html.Tbody(rows)],
                style={"width": "100%", "borderCollapse": "collapse"},
            ),
        ],
        style=CARD,
    )


@app.callback(
    Output("editor-form-div", "children"),
    Output("editor-selected", "data"),
    Input({"type": "edit-btn", "date": ALL, "fund": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def show_edit_form(n_clicks):
    if not any(n_clicks):
        return html.Div(), {}

    triggered = ctx.triggered_id
    if not triggered:
        return html.Div(), {}

    date = triggered["date"]
    fund = triggered["fund"]

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT close FROM fund_prices WHERE fund_id=? AND date=?", (fund, date)
    ).fetchone()
    conn.close()

    if not row:
        return html.Div(), {}

    current_close = row[0]

    form = html.Div(
        [
            html.P("EDIT RECORD", style=SECTION_TITLE),
            html.P(
                f"Fund: {fund}  |  Date: {date}",
                style={"fontSize": "12px", "color": "#666", "marginBottom": "12px"},
            ),
            html.Div(
                [
                    html.Label(
                        "Close Price:",
                        style={
                            "fontSize": "12px",
                            "marginRight": "8px",
                            "alignSelf": "center",
                        },
                    ),
                    dcc.Input(
                        id="editor-close-input",
                        type="number",
                        value=round(current_close, 4),
                        step=0.0001,
                        style={
                            "padding": "6px",
                            "fontSize": "12px",
                            "border": "1px solid #ccc",
                            "borderRadius": "4px",
                            "width": "150px",
                            "marginRight": "12px",
                        },
                    ),
                    html.Button(
                        "Save",
                        id="editor-save-btn",
                        n_clicks=0,
                        style={
                            "backgroundColor": "#1a7a1a",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "4px",
                            "padding": "7px 16px",
                            "fontSize": "12px",
                            "cursor": "pointer",
                            "marginRight": "8px",
                        },
                    ),
                    html.Button(
                        "Cancel",
                        id="editor-cancel-btn",
                        n_clicks=0,
                        style={
                            "backgroundColor": "#999",
                            "color": "white",
                            "border": "none",
                            "borderRadius": "4px",
                            "padding": "7px 16px",
                            "fontSize": "12px",
                            "cursor": "pointer",
                        },
                    ),
                ],
                style={"display": "flex", "alignItems": "center"},
            ),
        ],
        style=CARD,
    )

    return form, {"fund": fund, "date": date}


@app.callback(
    Output("editor-status", "children"),
    Output("editor-form-div", "children", allow_duplicate=True),
    Output("db-reload-trigger", "data"),
    Input("editor-save-btn", "n_clicks"),
    Input("editor-cancel-btn", "n_clicks"),
    State("editor-close-input", "value"),
    State("editor-selected", "data"),
    State("db-reload-trigger", "data"),
    prevent_initial_call=True,
)
def save_or_cancel(save_clicks, cancel_clicks, new_close, selected, reload_trigger):
    triggered = ctx.triggered_id

    if triggered == "editor-cancel-btn":
        return "", html.Div(), reload_trigger

    if triggered == "editor-save-btn" and new_close is not None and selected:
        fund = selected.get("fund")
        date = selected.get("date")
        if not fund or not date:
            return "Error: no record selected.", html.Div(), reload_trigger

        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE fund_prices SET close=? WHERE fund_id=? AND date=?",
            (float(new_close), fund, date),
        )
        conn.commit()
        conn.close()

        return (
            f"✓ Saved: {fund} on {date} → close updated to {new_close}",
            html.Div(),
            (reload_trigger or 0) + 1,
        )

    return "", html.Div(), reload_trigger


# ── 9. RUN ─────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)
