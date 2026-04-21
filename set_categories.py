# set_categories.py
# Sets category for each instrument individually.
# Safe to run multiple times — only updates, never deletes.
# Run: python3 set_categories.py

import sqlite3

CATEGORIES = {
    # ── DEFENCE
    'YF:NATP.L':          'Defence',
    'YF:DFEU.L':          'Defence',
    'YF:QQ.L':            'Defence',
    'YF:BA.L':            'Defence',

    # ── GOLD
    'YF:GC=F':            'Gold',
    'YF:SPGP.L':          'Gold',
    'YF:IGLN.L':          'Gold',
    'YF:PHPP.L':          'Gold',
    'CALC:XAUGBP':        'Gold',
    'GB00B3VNFD68:GBP':   'Gold',   # SL BlackRock Gold & General

    # ── SILVER
    'YF:SI=F':            'Silver',
    'YF:ISLN.L':          'Silver',

    # ── COMMODITIES (Agriculture)
    'YF:AIGA.L':          'Agriculture',
    'YF:WEAP.L':          'Agriculture',
    'YF:ZW=F':            'Agriculture',
    'YF:CC=F':            'Agriculture',
    'YF:COCO':            'Agriculture',

    # ── COMMODITIES (Energy)
    'YF:CL=F':            'Energy',
    'YF:BZ=F':            'Energy',
    'YF:NG=F':            'Energy',
    'YF:NRGT.L':          'Energy',
    'YF:NGSP.L':          'Energy',

    # ── COMMODITIES (Metals)
    'YF:HG=F':            'Copper',
    'YF:COPB.L':          'Copper',
    'YF:MINE.L':          'Copper',

    # ── CRYPTO
    'YF:BTC-GBP':         'Crypto',
    'YF:ETH-GBP':         'Crypto',

    # ── TECH / AI
    'YF:AINF.L':          'Tech/AI',
    'YF:XAIX.L':          'Tech/AI',
    'YF:QWTM.L':          'Tech/AI',
    'YF:QANT.L':          'Tech/AI',
    'YF:FCBR.L':          'Tech/AI',
    'YF:PLAY.L':          'Tech/AI',
    'YF:NVDA':            'Tech/AI',
    'YF:GOOG':            'Tech/AI',
    'YF:ASML':            'Tech/AI',
    'YF:QCOM':            'Tech/AI',
    'YF:MU':              'Tech/AI',

    # ── NATURAL RESOURCES
    'YF:JPM':             'Natural Resources',
    'GB00B61JR401:GBP':   'Natural Resources',  # SL JPM Natural Resources

    # ── INFRASTRUCTURE
    'GB00BF0TZK67:GBP':   'Infrastructure',     # L&G Global Infrastructure
    'GB00B3K5WJ87:GBP':   'Infrastructure',     # SL Macquarie Global Infrastructure

    # ── EMERGING MARKETS
    'LU1408526199:GBP':   'Emerging Markets',   # Robeco Emerging Stars
    'GB00BL0DTP33:GBP':   'Emerging Markets',   # JPM Emerging Markets ESG
    'COMPOSITE:HSBC_EM':  'Emerging Markets',
    'YF:EEM':             'Emerging Markets',
    'YF:HMCH.L':          'Emerging Markets',   # HSBC MSCI China
    'GB00B7Z71453:GBP':   'Emerging Markets',   # SL China
    'GB0031728438:GBP':   'Emerging Markets',   # SL Asia Pacific Ex Japan
    'GB00B849FB47:GBP':   'Emerging Markets',   # SL iShares Pacific
    'COMPOSITE:HSBC_ASIA_PAC': 'Emerging Markets',

    # ── GLOBAL EQUITY
    'YF:URTH':            'Global Equity',
    'YF:VWRL.L':          'Global Equity',
    'LU2092165666:GBP':   'Global Equity',      # HSBC Islamic Global Equity
    'COMPOSITE:HSBC_SHARIA': 'Global Equity',

    # ── US EQUITY
    'YF:^GSPC':           'US Equity',
    'YF:^IXIC':           'US Equity',
    'YF:CSP1.L':          'US Equity',
    'YF:UIFS.L':          'US Equity',
    'YF:AMZN':            'US Equity',
    'YF:NVO':             'US Equity',
    'YF:LLY':             'US Equity',
    'COMPOSITE:HSBC_NORTH_AMERICA': 'US Equity',
    'GB00B3VGBC62:GBP':   'US Equity',          # L&G PMC North America

    # ── UK EQUITY
    'YF:^FTSE':           'UK Equity',
    'YF:^FTMC':           'UK Equity',
    'YF:HSBA.L':          'UK Equity',
    'YF:GSK.L':           'UK Equity',
    'YF:DATA.L':          'UK Equity',
    'YF:BRBY.L':          'UK Equity',
    'YF:HFG.L':           'UK Equity',
    'YF:CCH.L':           'UK Equity',
    'GB00BJH4XW03:GBP':   'UK Equity',          # L&G Future World ESG UK
    'GB00B0ZGQD71:GBP':   'UK Equity',          # Schroder UK Smaller Companies
    'GB00B2PLJQ03:GBP':   'UK Equity',          # Artemis UK Special Situations
    'COMPOSITE:HSBC_UK_ACTIVE': 'UK Equity',

    # ── EUROPEAN EQUITY
    'YF:^STOXX50E':       'European Equity',
    'YF:HCAN.L':          'European Equity',
    'GB00B4YKRJ18:GBP':   'European Equity',    # L&G PMC Europe Ex UK
    'COMPOSITE:HSBC_EUROPE': 'European Equity',

    # ── JAPAN EQUITY
    'YF:^N225':           'Japan Equity',
    'YF:XDJP.L':          'Japan Equity',
    'GB00B4ZFV486:GBP':   'Japan Equity',       # L&G PMC Japan
    'COMPOSITE:HSBC_JAPAN': 'Japan Equity',

    # ── FINANCIALS
    'YF:JPM':             'Financials',
    'YF:CSCA.L':          'Financials',         # iShares MSCI Canada

    # ── PHARMA / HEALTHCARE
    'YF:NVO':             'Healthcare',
    'YF:LLY':             'Healthcare',

    # ── TURKISH EQUITY
    'YF:XU030.IS':        'Turkish Equity',

    # ── FX / RATES
    'YF:GBPUSD=X':        'FX',
    'YF:CNY=X':           'FX',

    # ── CASH & ASSETS
    'CASH:GBP':           'Cash',
    'CASH:USD':           'Cash',
    'ASSET:HOUSE':        'Asset',
}


def main():
    conn = sqlite3.connect('data/funds.db')

    # Ensure category column exists
    try:
        conn.execute('ALTER TABLE instruments ADD COLUMN category TEXT')
        print('Added category column')
    except Exception:
        pass  # already exists

    updated = 0
    skipped = []

    for fund_id, category in CATEGORIES.items():
        result = conn.execute(
            'UPDATE instruments SET category=? WHERE fund_id=?',
            (category, fund_id)
        )
        if result.rowcount > 0:
            updated += 1
        else:
            skipped.append(fund_id)

    conn.commit()

    # Set remaining uncategorised instruments to their asset_type as fallback
    conn.execute("""
        UPDATE instruments SET category = asset_type
        WHERE category IS NULL OR category = ''
    """)
    conn.commit()
    conn.close()

    print(f'\nUpdated: {updated} instruments')
    if skipped:
        print(f'Not found in DB (skipped): {len(skipped)}')
        for s in skipped:
            print(f'  {s}')

    print('\nDone. Review with:')
    print('SELECT fund_id, name, category FROM instruments ORDER BY category, name;')


if __name__ == '__main__':
    main()