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