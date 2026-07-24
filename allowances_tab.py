# ─────────────────────────────────────────────────────────────────────────────
# ALLOWANCES TAB — paste into dashboard.py
# ─────────────────────────────────────────────────────────────────────────────
#
# 1. Add the layout block inside the dcc.Tabs children list
# 2. Add the callbacks at the bottom of dashboard.py
# 3. Add 'tab-allowances' to the tab visibility callback
# ─────────────────────────────────────────────────────────────────────────────

# ── DEFAULT DATA ─────────────────────────────────────────────────────────────
ALLOWANCES_DEFAULT = {
    'ahmet': {
        '2021/22': {'workplace': 30222, 'sipp_done': 0,     'sipp_future': 0, 'isa': 0, 'salary': 0,      'car_bik': 0},
        '2022/23': {'workplace': 23311, 'sipp_done': 5000,  'sipp_future': 0, 'isa': 0, 'salary': 0,      'car_bik': 0},
        '2023/24': {'workplace': 24461, 'sipp_done': 15500, 'sipp_future': 0, 'isa': 0, 'salary': 125639, 'car_bik': 0},
        '2024/25': {'workplace': 38593, 'sipp_done': 25000, 'sipp_future': 0, 'isa': 0, 'salary': 147854, 'car_bik': 0},
        '2025/26': {'workplace': 33020, 'sipp_done': 30216, 'sipp_future': 0, 'isa': 0, 'salary': 148200, 'car_bik': 0},
    },
    'burcu': {
        '2021/22': {'workplace': 15640, 'sipp_done': 0,     'sipp_future': 0, 'isa': 0, 'salary': 0},
        '2022/23': {'workplace': 14228, 'sipp_done': 0,     'sipp_future': 0, 'isa': 0, 'salary': 0},
        '2023/24': {'workplace': 16470, 'sipp_done': 12000, 'sipp_future': 0, 'isa': 0, 'salary': 0},
        '2024/25': {'workplace': 37428, 'sipp_done': 8000,  'sipp_future': 0, 'isa': 0, 'salary': 118744},
        '2025/26': {'workplace': 7600,  'sipp_done': 0,     'sipp_future': 0, 'isa': 0, 'salary': 88164},
    },
    'son': {
        '2023/24': {'jisa': 9000},
        '2024/25': {'jisa': 9000},
        '2025/26': {'jisa': 9000},
    }
}

TAX_YEARS   = ['2021/22', '2022/23', '2023/24', '2024/25', '2025/26', '2026/27']
PENSION_ALLOWANCE = {'2021/22': 40000, '2022/23': 40000, '2023/24': 60000,
                     '2024/25': 60000, '2025/26': 60000, '2026/27': 60000}
ISA_LIMIT   = 20000
JISA_LIMIT  = 9000
CURRENT_YEAR = '2025/26'


# ── CARRY FORWARD LOGIC ───────────────────────────────────────────────────────

def calc_carry_forward(person_data, person, years):
    """
    Calculate carry forward for each year.
    Returns dict: {year: {'allowance': x, 'carry_forward': x, 'available': x,
                          'used': x, 'remaining': x, 'unused': x}}
    """
    results = {}
    # Track remaining unused per year (after carry forward consumed)
    unused_by_year = {}  # year -> unused allowance remaining available to carry

    for yr in years:
        data = person_data.get(person, {}).get(yr, {})
        allowance = PENSION_ALLOWANCE.get(yr, 60000)

        # Gross pension used this year
        workplace  = data.get('workplace', 0) or 0
        sipp_done  = data.get('sipp_done', 0) or 0
        sipp_future= data.get('sipp_future', 0) or 0
        sipp_gross_done   = sipp_done * 1.25
        sipp_gross_future = sipp_future * 1.25
        total_used = workplace + sipp_gross_done + sipp_gross_future

        # Carry forward: unused from previous 3 years (oldest first)
        prev_3 = [y for y in years if y < yr][-3:]
        carry_fwd = sum(unused_by_year.get(y, 0) for y in prev_3)
        available = allowance + carry_fwd

        # Consume current year allowance first, then oldest carry forward
        remaining_to_use = total_used
        current_unused = max(0, allowance - remaining_to_use)
        remaining_to_use = max(0, remaining_to_use - allowance)

        # Consume carry forward oldest first
        carry_pool = {y: unused_by_year.get(y, 0) for y in prev_3}
        for y in sorted(carry_pool.keys()):
            if remaining_to_use <= 0:
                break
            consumed = min(carry_pool[y], remaining_to_use)
            carry_pool[y] -= consumed
            remaining_to_use -= consumed
            unused_by_year[y] = carry_pool[y]

        # This year's unused = what's left of current year allowance
        unused_by_year[yr] = current_unused
        remaining = max(0, available - total_used)

        results[yr] = {
            'allowance':    allowance,
            'carry_fwd':    carry_fwd,
            'available':    available,
            'workplace':    workplace,
            'sipp_done':    sipp_done,
            'sipp_future':  sipp_future,
            'sipp_gross_done':   sipp_gross_done,
            'sipp_gross_future': sipp_gross_future,
            'total_used':   total_used,
            'remaining':    remaining,
            'unused':       current_unused,
            'salary':       data.get('salary', 0) or 0,
            'car_bik':      data.get('car_bik', 0) or 0,
            'isa':          data.get('isa', 0) or 0,
        }
    return results


def calc_100k(salary, car_bik, workplace, sipp_done_gross, sipp_future_gross):
    """Calculate adjusted income and how much more SIPP needed to reach £100k."""
    # Adjusted income = salary + car BIK - personal pension contributions
    # Pension contributions reduce adjusted income
    total_pension_gross = workplace + sipp_done_gross + sipp_future_gross
    # Net income after pension relief
    adjusted = salary + car_bik - total_pension_gross
    gap = max(0, adjusted - 100000)
    # Additional net SIPP needed to bridge gap
    additional_sipp_net = gap / 1.25
    return adjusted, gap, additional_sipp_net


# ── LAYOUT ────────────────────────────────────────────────────────────────────
# Add this Tab inside the dcc.Tabs children list:
#
# dcc.Tab(label='ALLOWANCES', value='tab-allowances',
#         style=TAB_STYLE, selected_style=TAB_SELECTED),
#
# Add this Div alongside the other tab content divs:

ALLOWANCES_LAYOUT = html.Div([

    dcc.Store(id='allowances-data', data=ALLOWANCES_DEFAULT),

    # ── AHMET SECTION
    html.Div([
        html.P('AHMET', style=SECTION_TITLE),

        # Input table
        html.Div([
            html.P('PENSION & INCOME INPUTS', style={**SECTION_TITLE, 'marginBottom': '8px'}),
            html.Div(id='ahmet-input-table'),
        ], style=CARD),

        # Results table
        html.Div([
            html.P('PENSION ALLOWANCE & CARRY FORWARD', style={**SECTION_TITLE, 'marginBottom': '8px'}),
            html.Div(id='ahmet-results-table'),
        ], style=CARD),

        # ISA
        html.Div([
            html.P('ISA ALLOWANCE', style={**SECTION_TITLE, 'marginBottom': '8px'}),
            html.Div(id='ahmet-isa-table'),
        ], style=CARD),

    ], style={'marginBottom': '16px'}),

    # ── BURCU SECTION
    html.Div([
        html.P('BURCU', style=SECTION_TITLE),

        html.Div([
            html.P('PENSION & INCOME INPUTS', style={**SECTION_TITLE, 'marginBottom': '8px'}),
            html.Div(id='burcu-input-table'),
        ], style=CARD),

        html.Div([
            html.P('PENSION ALLOWANCE & CARRY FORWARD', style={**SECTION_TITLE, 'marginBottom': '8px'}),
            html.Div(id='burcu-results-table'),
        ], style=CARD),

        html.Div([
            html.P('ISA ALLOWANCE', style={**SECTION_TITLE, 'marginBottom': '8px'}),
            html.Div(id='burcu-isa-table'),
        ], style=CARD),

    ], style={'marginBottom': '16px'}),

    # ── SON SECTION
    html.Div([
        html.P('SON — JISA', style=SECTION_TITLE),
        html.Div([
            html.Div(id='son-jisa-table'),
        ], style=CARD),
    ], style={'marginBottom': '16px'}),

], id='tab-allowances-content',
   style={'display': 'none', 'padding': '16px', 'maxWidth': '1400px', 'margin': '0 auto'})


# ── HELPER: Build input table ─────────────────────────────────────────────────

def build_input_table(person, data, include_car=False):
    """Build editable input table for a person."""
    def th(text, align='right'):
        return html.Th(text, style={
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '6px 10px', 'fontSize': '11px', 'fontWeight': '600',
            'textAlign': align, 'whiteSpace': 'nowrap'
        })

    headers = ['Year', 'Salary', 'Workplace Pension', 'SIPP Done (net)',
               'SIPP Future (net)', 'ISA Done']
    if include_car:
        headers.insert(2, 'Car BIK')

    header_row = html.Tr([th(h, 'left' if i == 0 else 'right')
                          for i, h in enumerate(headers)])

    def inp(val, iid, small=False):
        return dcc.Input(
            id=iid, type='number', value=val or 0,
            debounce=True,
            style={
                'width': '100px' if not small else '80px',
                'fontSize': '11px', 'textAlign': 'right',
                'border': '1px solid #ddd', 'borderRadius': '4px',
                'padding': '3px 6px', 'fontFamily': 'monospace',
            }
        )

    rows = []
    for yr in TAX_YEARS:
        d = data.get(person, {}).get(yr, {})
        is_current = yr == CURRENT_YEAR
        bg = '#f0f7ff' if is_current else ('white' if TAX_YEARS.index(yr) % 2 == 0 else '#f9fbfd')
        cells = [
            html.Td(yr, style={'padding': '4px 10px', 'fontSize': '12px',
                               'fontWeight': '700' if is_current else '400',
                               'color': '#1a3a5c', 'whiteSpace': 'nowrap'}),
            html.Td(inp(d.get('salary', 0), f'{person}-salary-{yr}'),
                    style={'padding': '4px 6px'}),
        ]
        if include_car:
            cells.append(html.Td(inp(d.get('car_bik', 0), f'{person}-car-{yr}'),
                                 style={'padding': '4px 6px'}))
        cells += [
            html.Td(inp(d.get('workplace', 0), f'{person}-workplace-{yr}'),
                    style={'padding': '4px 6px'}),
            html.Td(inp(d.get('sipp_done', 0), f'{person}-sipp-done-{yr}'),
                    style={'padding': '4px 6px'}),
            html.Td(inp(d.get('sipp_future', 0), f'{person}-sipp-future-{yr}'),
                    style={'padding': '4px 6px'}),
            html.Td(inp(d.get('isa', 0), f'{person}-isa-{yr}'),
                    style={'padding': '4px 6px'}),
        ]
        rows.append(html.Tr(cells, style={'backgroundColor': bg,
                                           'borderBottom': '1px solid #f0f3f7'}))

    return html.Div(
        html.Table([html.Thead(header_row), html.Tbody(rows)],
                   style={'width': '100%', 'borderCollapse': 'collapse'}),
        style={'overflowX': 'auto'}
    )


def build_results_table(results):
    """Build pension allowance results table."""
    def th(text, align='right'):
        return html.Th(text, style={
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '6px 10px', 'fontSize': '11px', 'fontWeight': '600',
            'textAlign': align, 'whiteSpace': 'nowrap'
        })

    def td(val, color=None, bold=False, align='right', prefix='£'):
        if val is None:
            text = '—'
        else:
            text = f"{prefix}{val:,.0f}"
        style = {
            'padding': '4px 10px', 'fontSize': '11px',
            'textAlign': align, 'fontFamily': 'monospace',
            'fontWeight': '700' if bold else '400',
        }
        if color:
            style['color'] = color
        return html.Td(text, style=style)

    headers = ['Year', 'Allowance', 'Carry Fwd', 'Available',
               'Workplace', 'SIPP Gross', 'Total Used', 'Remaining',
               'Adjusted Income', 'Gap to £100k', 'Extra SIPP Needed']

    header_row = html.Tr([th(h, 'left' if i == 0 else 'right')
                          for i, h in enumerate(headers)])

    rows = []
    for yr in TAX_YEARS:
        r = results.get(yr, {})
        if not r:
            continue
        is_current = yr == CURRENT_YEAR
        bg = '#f0f7ff' if is_current else ('white' if TAX_YEARS.index(yr) % 2 == 0 else '#f9fbfd')

        rem = r.get('remaining', 0)
        rem_color = '#1a7a1a' if rem > 0 else '#c0392b'

        salary  = r.get('salary', 0)
        car_bik = r.get('car_bik', 0)
        adj, gap, extra_sipp = calc_100k(
            salary, car_bik,
            r.get('workplace', 0),
            r.get('sipp_gross_done', 0),
            r.get('sipp_gross_future', 0)
        ) if salary > 0 else (0, 0, 0)

        adj_color  = '#c0392b' if adj > 100000 else '#1a7a1a'
        gap_color  = '#c0392b' if gap > 0 else '#1a7a1a'

        sipp_gross_total = r.get('sipp_gross_done', 0) + r.get('sipp_gross_future', 0)

        rows.append(html.Tr([
            html.Td(yr, style={'padding': '4px 10px', 'fontSize': '12px',
                               'fontWeight': '700' if is_current else '400',
                               'color': '#1a3a5c', 'whiteSpace': 'nowrap'}),
            td(r.get('allowance')),
            td(r.get('carry_fwd')),
            td(r.get('available'), bold=True),
            td(r.get('workplace')),
            td(sipp_gross_total),
            td(r.get('total_used'), bold=True),
            td(rem, color=rem_color, bold=True),
            td(adj if salary > 0 else None, color=adj_color if salary > 0 else None),
            td(gap if salary > 0 else None, color=gap_color if salary > 0 else None),
            td(extra_sipp if salary > 0 and gap > 0 else None, color='#c0392b'),
        ], style={'backgroundColor': bg, 'borderBottom': '1px solid #f0f3f7'}))

    return html.Div(
        html.Table([html.Thead(header_row), html.Tbody(rows)],
                   style={'width': '100%', 'borderCollapse': 'collapse'}),
        style={'overflowX': 'auto'}
    )


def build_isa_table(results):
    """Build ISA allowance table."""
    def th(text, align='right'):
        return html.Th(text, style={
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '6px 10px', 'fontSize': '11px', 'fontWeight': '600',
            'textAlign': align, 'whiteSpace': 'nowrap'
        })

    header_row = html.Tr([
        th('Year', 'left'), th('Limit'), th('Done'), th('Remaining')
    ])

    rows = []
    for yr in TAX_YEARS:
        r = results.get(yr, {})
        if not r:
            continue
        is_current = yr == CURRENT_YEAR
        bg = '#f0f7ff' if is_current else ('white' if TAX_YEARS.index(yr) % 2 == 0 else '#f9fbfd')
        isa_done = r.get('isa', 0)
        isa_rem  = ISA_LIMIT - isa_done
        rem_color = '#1a7a1a' if isa_rem >= 0 else '#c0392b'

        rows.append(html.Tr([
            html.Td(yr, style={'padding': '4px 10px', 'fontSize': '12px',
                               'fontWeight': '700' if is_current else '400',
                               'color': '#1a3a5c'}),
            html.Td(f"£{ISA_LIMIT:,}", style={'padding': '4px 10px', 'fontSize': '11px',
                                               'textAlign': 'right', 'fontFamily': 'monospace'}),
            html.Td(f"£{isa_done:,}", style={'padding': '4px 10px', 'fontSize': '11px',
                                              'textAlign': 'right', 'fontFamily': 'monospace'}),
            html.Td(f"£{isa_rem:,}", style={'padding': '4px 10px', 'fontSize': '11px',
                                             'textAlign': 'right', 'fontFamily': 'monospace',
                                             'fontWeight': '700', 'color': rem_color}),
        ], style={'backgroundColor': bg, 'borderBottom': '1px solid #f0f3f7'}))

    return html.Div(
        html.Table([html.Thead(header_row), html.Tbody(rows)],
                   style={'width': '100%', 'borderCollapse': 'collapse'}),
        style={'overflowX': 'auto'}
    )


def build_jisa_table(son_data):
    """Build JISA table for son."""
    def th(text, align='right'):
        return html.Th(text, style={
            'backgroundColor': '#1a3a5c', 'color': 'white',
            'padding': '6px 10px', 'fontSize': '11px', 'fontWeight': '600',
            'textAlign': align, 'whiteSpace': 'nowrap'
        })

    header_row = html.Tr([
        th('Year', 'left'), th('Limit'), th('Done'), th('Future'), th('Remaining')
    ])

    jisa_years = ['2023/24', '2024/25', '2025/26', '2026/27']
    rows = []
    for yr in jisa_years:
        d = son_data.get(yr, {})
        is_current = yr == CURRENT_YEAR
        bg = '#f0f7ff' if is_current else ('white' if jisa_years.index(yr) % 2 == 0 else '#f9fbfd')
        done   = d.get('jisa', 0) or 0
        future = d.get('jisa_future', 0) or 0
        rem    = JISA_LIMIT - done - future
        rem_color = '#1a7a1a' if rem >= 0 else '#c0392b'

        rows.append(html.Tr([
            html.Td(yr, style={'padding': '4px 10px', 'fontSize': '12px',
                               'fontWeight': '700' if is_current else '400',
                               'color': '#1a3a5c'}),
            html.Td(f"£{JISA_LIMIT:,}", style={'padding': '4px 10px', 'fontSize': '11px',
                                                'textAlign': 'right', 'fontFamily': 'monospace'}),
            html.Td(dcc.Input(id=f'son-jisa-done-{yr}', type='number', value=done,
                              debounce=True,
                              style={'width': '90px', 'fontSize': '11px', 'textAlign': 'right',
                                     'border': '1px solid #ddd', 'borderRadius': '4px',
                                     'padding': '3px 6px', 'fontFamily': 'monospace'}),
                    style={'padding': '4px 6px'}),
            html.Td(dcc.Input(id=f'son-jisa-future-{yr}', type='number', value=future,
                              debounce=True,
                              style={'width': '90px', 'fontSize': '11px', 'textAlign': 'right',
                                     'border': '1px solid #ddd', 'borderRadius': '4px',
                                     'padding': '3px 6px', 'fontFamily': 'monospace'}),
                    style={'padding': '4px 6px'}),
            html.Td(f"£{rem:,}", style={'padding': '4px 10px', 'fontSize': '11px',
                                         'textAlign': 'right', 'fontFamily': 'monospace',
                                         'fontWeight': '700', 'color': rem_color}),
        ], style={'backgroundColor': bg, 'borderBottom': '1px solid #f0f3f7'}))

    return html.Div(
        html.Table([html.Thead(header_row), html.Tbody(rows)],
                   style={'width': '100%', 'borderCollapse': 'collapse'}),
        style={'overflowX': 'auto'}
    )


# ── CALLBACKS ─────────────────────────────────────────────────────────────────
# Add these callbacks to dashboard.py

# Store updater — collects all inputs and updates the store
ALLOWANCES_INPUTS = (
    [Input(f'ahmet-salary-{yr}',      'value') for yr in TAX_YEARS] +
    [Input(f'ahmet-car-{yr}',         'value') for yr in TAX_YEARS] +
    [Input(f'ahmet-workplace-{yr}',   'value') for yr in TAX_YEARS] +
    [Input(f'ahmet-sipp-done-{yr}',   'value') for yr in TAX_YEARS] +
    [Input(f'ahmet-sipp-future-{yr}', 'value') for yr in TAX_YEARS] +
    [Input(f'ahmet-isa-{yr}',         'value') for yr in TAX_YEARS] +
    [Input(f'burcu-salary-{yr}',      'value') for yr in TAX_YEARS] +
    [Input(f'burcu-workplace-{yr}',   'value') for yr in TAX_YEARS] +
    [Input(f'burcu-sipp-done-{yr}',   'value') for yr in TAX_YEARS] +
    [Input(f'burcu-sipp-future-{yr}', 'value') for yr in TAX_YEARS] +
    [Input(f'burcu-isa-{yr}',         'value') for yr in TAX_YEARS] +
    [Input(f'son-jisa-done-{yr}',     'value') for yr in ['2023/24','2024/25','2025/26','2026/27']] +
    [Input(f'son-jisa-future-{yr}',   'value') for yr in ['2023/24','2024/25','2025/26','2026/27']]
)

N = len(TAX_YEARS)
JISA_YEARS = ['2023/24','2024/25','2025/26','2026/27']
NJ = len(JISA_YEARS)

@app.callback(
    Output('allowances-data', 'data'),
    ALLOWANCES_INPUTS,
    State('allowances-data', 'data'),
    prevent_initial_call=True,
)
def update_allowances_store(*args):
    data = args[-1]
    vals = args[:-1]
    i = 0

    for yr in TAX_YEARS:
        data['ahmet'][yr] = data['ahmet'].get(yr, {})
        data['ahmet'][yr]['salary']      = vals[i] or 0; i+=1
    for yr in TAX_YEARS:
        data['ahmet'][yr]['car_bik']     = vals[i] or 0; i+=1
    for yr in TAX_YEARS:
        data['ahmet'][yr]['workplace']   = vals[i] or 0; i+=1
    for yr in TAX_YEARS:
        data['ahmet'][yr]['sipp_done']   = vals[i] or 0; i+=1
    for yr in TAX_YEARS:
        data['ahmet'][yr]['sipp_future'] = vals[i] or 0; i+=1
    for yr in TAX_YEARS:
        data['ahmet'][yr]['isa']         = vals[i] or 0; i+=1

    for yr in TAX_YEARS:
        data['burcu'][yr] = data['burcu'].get(yr, {})
        data['burcu'][yr]['salary']      = vals[i] or 0; i+=1
    for yr in TAX_YEARS:
        data['burcu'][yr]['workplace']   = vals[i] or 0; i+=1
    for yr in TAX_YEARS:
        data['burcu'][yr]['sipp_done']   = vals[i] or 0; i+=1
    for yr in TAX_YEARS:
        data['burcu'][yr]['sipp_future'] = vals[i] or 0; i+=1
    for yr in TAX_YEARS:
        data['burcu'][yr]['isa']         = vals[i] or 0; i+=1

    for yr in JISA_YEARS:
        data['son'][yr] = data['son'].get(yr, {})
        data['son'][yr]['jisa']        = vals[i] or 0; i+=1
    for yr in JISA_YEARS:
        data['son'][yr]['jisa_future'] = vals[i] or 0; i+=1

    return data


@app.callback(
    Output('ahmet-input-table',   'children'),
    Output('ahmet-results-table', 'children'),
    Output('ahmet-isa-table',     'children'),
    Output('burcu-input-table',   'children'),
    Output('burcu-results-table', 'children'),
    Output('burcu-isa-table',     'children'),
    Output('son-jisa-table',      'children'),
    Input('allowances-data', 'data'),
    Input('main-tabs', 'value'),
)
def update_allowances_tab(data, tab):
    if tab != 'tab-allowances':
        return [dash.no_update] * 7

    ahmet_results = calc_carry_forward(data, 'ahmet', TAX_YEARS)
    burcu_results = calc_carry_forward(data, 'burcu', TAX_YEARS)

    return (
        build_input_table('ahmet', data, include_car=True),
        build_results_table(ahmet_results),
        build_isa_table(ahmet_results),
        build_input_table('burcu', data, include_car=False),
        build_results_table(burcu_results),
        build_isa_table(burcu_results),
        build_jisa_table(data.get('son', {})),
    )