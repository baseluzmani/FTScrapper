# config.py
# This file contains all the settings for the scraper.
# If you want to change anything about how the scraper runs,
# this is the only file you need to touch.

# --- Fund List ---
# Each fund is a dictionary with two keys:
#   'name' : a human-readable label (used in logs and the database)
#   'id'   : the FT identifier that goes into the URL
FUNDS = [
    {"name": "SL Asia Pacific Ex Japan", "id": "GB0031728438:GBP"},
    {"name": "SL Gold", "id": "GB00B3VNFD68:GBP"},
    {"name": "SL China", "id": "GB00B7Z71453:GBP"},
    {"name": "SL JPM Natural Resources", "id": "GB00B61JR401:GBP"},
    {"name": "SL Ishares Pacific", "id": "GB00B849FB47:GBP"},
    {"name": "SL L&G Global Infrastructure", "id": "GB00BF0TZK67:GBP"},
    {"name": "HSBC Islamic Funds", "id": "LU2092165666:GBP"},
    {"name": "SL Macquarie Global Infrastructure Secs", "id": "GB00B3K5WJ87:GBP"},
]

# --- Date Settings ---
# How many days of history to pull on the very first run
FIRST_RUN_DAYS = 365

# --- Database ---
# Path to the SQLite database file.
# The 'data/' folder will be created automatically if it doesn't exist.
DB_PATH = "data/funds.db"

# --- Request Headers ---
# When our script makes an HTTP request, it needs to look like a real browser.
# Without these headers, FT's server might block the request.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Cookie": (
        "GZIP=1; spoor-id=cml6o8dna00003b7b935tb84h; "
        "usnatUUID=2646cd73-9442-44c6-ac47-cb0f7802f09c; "
        "consentDate=2026-02-03T14:05:40.206Z; "
        "FTCookieConsentGDPR=true; "
        "_cb=D-qql5BPKJFyDTaPuG; "
        "zit.data.toexclude=0; "
        "_gcl_au=1.1.977630430.1770127543.431638566.1770127599.1770127603; "
        "FTSession_s=0y6I4mrOQEuR042WEj4IO5a_0wAAAZwj07jZw8I.MEYCIQC8Juta"
        "TIZlzHzp7GqR_zRsz3PuHawEQErLOwnYdbjYFgIhANqE3GPFlouRoT1EpGwKq85x_Rj"
    ),
}

# --- Holdings ---
# These are the funds shown in the My Holdings tab.
# Add or remove entries to control what appears there.
# fund_id must exactly match the fund_id in the database.

HOLDINGS = [
    # SL Pension Funds
    {"fund_id": "GB0031728438:GBP", "display_name": "SL Asia Pacific Ex Japan"},
    {"fund_id": "GB00B3VNFD68:GBP", "display_name": "SL BlackRock Gold & General"},
    {"fund_id": "GB00B61JR401:GBP", "display_name": "SL JPM Natural Resources"},
    {"fund_id": "GB00B849FB47:GBP", "display_name": "iShares Pacific ex Japan"},
    {"fund_id": "GB00BF0TZK67:GBP", "display_name": "L&G Global Infrastructure"},
    {
        "fund_id": "GB00B3K5WJ87:GBP",
        "display_name": "SL Macquarie Global Infrastructure Secs",
    },
    # HSBC Pension Funds
    {"fund_id": "HEME:GBP", "display_name": "HSBC Emerging Markets Equities"},
    {"fund_id": "HGEA:GBP", "display_name": "HSBC Global Equities Active"},
    {"fund_id": "HSHL:GBP", "display_name": "HSBC Shariah Law Equities"},
    # ETFs
    {"fund_id": "YF:AINF.L", "display_name": "iShares AI Infrastructure ETF"},
    {"fund_id": "YF:DFEU.L", "display_name": "iShares Europe Def UETF"},
    {"fund_id": "YF:MINE.L", "display_name": "iShares Copper Miners ETF"},
    {"fund_id": "YF:NATP.L", "display_name": "Future of Defence ETF"},
    {"fund_id": "YF:QWTM.L", "display_name": "WisdomTree Quantum Computing"},
    # Stocks
    {"fund_id": "YF:AMZN", "display_name": "Amazon"},
    {"fund_id": "YF:HSBA.L", "display_name": "HSBC Holdings"},
    # Commodities
    {"fund_id": "YF:COPB.L", "display_name": "WisdomTree Copper ETC"},
    {"fund_id": "YF:WEAP.L", "display_name": "WisdomTree Wheat ETC"},
    {"fund_id": "YF:HG=F", "display_name": "Copper Futures"},
    # Indices / Benchmarks
    {"fund_id": "YF:XU030.IS", "display_name": "BIST 30"},
    {"fund_id": "YF:^FTSE", "display_name": "FTSE 100"},
]
