import re

content = open('dashboard.py').read()

# Find the start of load_cash_table callback
start_marker = "@app.callback(\n    Output('cash-accounts-table-div', 'children', allow_duplicate=False)"
# Find the end of update_cash_accounts function
end_marker = "    return render_cash_table(accounts, fx_rates), status, reload, name, amount"

start_idx = content.find(start_marker)
end_idx   = content.find(end_marker) + len(end_marker)

if start_idx == -1:
    print("START NOT FOUND")
    exit()
if end_idx == -1:
    print("END NOT FOUND")
    exit()

new_callbacks = """
@app.callback(
    Output('cash-accounts-table-div', 'children'),
    Output('cash-status', 'children'),
    Output('cash-name-input', 'value'),
    Output('cash-amount-input', 'value'),
    Input('main-tabs', 'value'),
    Input('portfolio-reload', 'data'),
    Input('cash-add-btn', 'n_clicks'),
    Input({'type': 'cash-remove-btn', 'index': ALL}, 'n_clicks'),
    State('cash-name-input', 'value'),
    State('cash-currency-select', 'value'),
    State('cash-amount-input', 'value'),
    prevent_initial_call=False,
)
def manage_cash_accounts(tab, reload, add_clicks, remove_clicks, name, currency, amount):
    fx_rates  = get_fx_rates(df)
    accounts  = load_cash_accounts()
    triggered = ctx.triggered_id

    if triggered == 'cash-add-btn':
        if name and amount:
            accounts.append({'name': name, 'currency': currency or 'GBP', 'amount': float(amount)})
            save_cash_accounts(accounts)
            return render_cash_table(accounts, fx_rates), f"✓ Added {name}", None, None
        return render_cash_table(accounts, fx_rates), 'Please enter name and amount.', name, amount

    if isinstance(triggered, dict) and triggered.get('type') == 'cash-remove-btn':
        idx = triggered['index']
        if 0 <= idx < len(accounts):
            removed = accounts.pop(idx)
            save_cash_accounts(accounts)
            return render_cash_table(accounts, fx_rates), f"✓ Removed {removed['name']}", name, amount

    return render_cash_table(accounts, fx_rates), '', name, amount"""

content = content[:start_idx] + new_callbacks + content[end_idx:]
open('dashboard.py', 'w').write(content)
print(f"Done. Replaced chars {start_idx} to {end_idx}")