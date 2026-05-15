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
    {"name": "HSBC Islamic Global Equity", "id": "LU2092165666:GBP"},
    {"name": "SL Macquarie Global Infrastructure Secs", "id": "GB00B3K5WJ87:GBP"},
    {"name": "Robeco Emerging Stars Equities G GBP", "id": "LU1408526199:GBP"},
    {"name": "JPMorgan Emerging Markets ESG Equity C", "id": "GB00BL0DTP33:GBP"},
    {"name": "Schroder Life UK Smaller Companies", "id": "GB00B0ZGQD71:GBP"},
    {"name": "Artemis UK Special Situations Fund", "id": "GB00B2PLJQ03:GBP"},
    {"name": "L&G PMC North America Equity Index", "id": "GB00B3VGBC62:GBP"},
    {"name": "L&G PMC Europe Ex UK Equity Index", "id": "GB00B4YKRJ18:GBP"},
    {"name": "L&G PMC Japan Equity Index", "id": "GB00B4ZFV486:GBP"},
    {"name": "L&G PMC Asia Pac ex Japan Dev Eq", "id": "GB00B4WT1Y33:GBP"},
    {"name": "L&G Future World ESG Optimised UK Index Fund", "id": "GB00BJH4XW03:GBP"},
    {"name": "Fidelity Funds - Latin America Fund W-Acc-GBP", "id": "LU1033664027:GBP"},
    {"name": "Fidelity Asia Fund W Acc", "id": "GB00B6Y7NF43:GBX"},
    {"name": "Fid Fil UK HSBC Islamic 0 GBP", "id": "0P0001EWE2"},
]

# --- Date Settings ---
# How many days of history to pull on the very first run
FIRST_RUN_DAYS = 365

CHART_CATEGORY_THRESHOLD = 0.02  # categories below 2% of total grouped as 'Other' in the history trend chart

# --- Dashboard Settings ---
DEFAULT_SINCE_DATE = '2026-03-01'  # Default date for returns calculations

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

# --- Yahoo Finance Tickers ---
# Format: (ticker, display_name, asset_type)
# Asset types: Index, ETF, Commodity, Stock

YAHOO_TICKERS = [
    # Indices — Global
    ("^GSPC",     "S&P 500",              "Index"),
    ("^RUT",      "Russell 2000",         "Index"),
    ("^DJI",      "Dow Jones",            "Index"),
    ("^IXIC",     "NASDAQ Composite",     "Index"),
    ("^VIX",      "VIX Volatility",       "Index"),
    ("^FTSE",     "FTSE 100",             "Index"),
    ("^FTMC",     "FTSE 250",             "Index"),
    ("^GDAXI",    "DAX",                  "Index"),
    ("^FCHI",     "CAC 40",               "Index"),
    ("^STOXX50E", "Euro Stoxx 50",        "Index"),
    # Indices — Asia Pacific
    ("^N225",     "Nikkei 225",           "Index"),
    ("^HSI",      "Hang Seng",            "Index"),
    ("^KS11",     "KOSPI",                "Index"),
    ("^AXJO",     "S&P ASX 200",          "Index"),
    ("^BSESN",    "BSE Sensex",           "Index"),
    ("000001.SS", "Shanghai Composite",   "Index"),
    ("^TWII",     "Taiwan Weighted",      "Index"),
    ("^STI",      "Singapore STI",        "Index"),
    ("^JKSE",     "Jakarta Composite",    "Index"),
    ("^NZ50",     "NZX 50",               "Index"),
    # Indices — Other
    ("XU030.IS",  "BIST 30",              "Index"),
    ("^BVSP",     "Ibovespa Brazil",      "Index"),
    ("^GSPTSE",   "S&P TSX Canada",       "Index"),
    ("HPI", "UK Halifax House Price Index", "Index"),
    # Global Equity ETFs
    ("URTH", "MSCI World", "ETF"),
    ("EEM", "MSCI Emerging Markets", "ETF"),
    ("VWRL.L", "FTSE All World", "ETF"),
    ("CSP1.L", "iShares Core S&P 500 ETF", "ETF"),
    ("XDJP.L", "Xtr Nikkei 225 UCITS ETF", "ETF"),
    ("HMCH.L", "HSBC MSCI China UCITS ETF", "ETF"),
    ("HCAN.L", "HSBC MSCI Canada UCITS ETF", "ETF"),
    ("DFEU.L", "iShares Europe Def UETF", "ETF"),
    ("XAIX.L", "X AI and Big Data UCITS ETF", "ETF"),
    ("AINF.L", "iShares AI Infrastructure ETF", "ETF"),
    ("UIFS.L", "iShares S&P 500 Financials ETF", "ETF"),
    ("FCBR.L", "FT Nasdaq Cs UCITS ETF", "ETF"),
    ("QANT.L", "iShares Quantum Computing ETF", "ETF"),
    ("QWTM.L", "WisdomTree Quantum Computing ETF", "ETF"),
    ("NATP.L", "Future of Defence UCITS ETF", "ETF"),
    ("SPGP.L", "iShares Gold Producers ETF", "ETF"),
    ("CSCA.L", "iShares MSCI Canada UCITS ETF", "ETF"),
    ("PLAY.L", "iShares Digital Entertainment ETF", "ETF"),
    ("HMAF.L", "HSBC MSCI AC FAR EAST ex JAPAN UCITS ETF", "ETF"),
    ("SEMI.L", "iShares MSCI Global Semiconductors UCITS ETF", "ETF"),
    ("IITU.L", "iShares S&P 500 IT Sector UCITS ETF USD", "ETF"),
    # Commodities — Futures
    ("GC=F", "Gold Futures", "Commodity"),
    ("SI=F", "Silver Futures", "Commodity"),
    ("HG=F", "Copper Futures", "Commodity"),
    ("ZW=F", "Wheat Futures", "Commodity"),
    ("CL=F", "Crude Oil Futures", "Commodity"),
    ("NG=F", "Natural Gas Futures", "Commodity"),
    ("CC=F", "Cocoa Futures", "Commodity"),
    ("BZ=F", "Brent Crude Futures", "Commodity"),
    # Commodity ETCs (London listed, GBP)
    ("PHPP.L", "WT Physical Precious Metals ETC", "Commodity"),
    ("COPB.L", "WisdomTree Copper ETC", "Commodity"),
    ("WEAP.L", "WisdomTree Wheat ETC", "Commodity"),
    ("MINE.L", "iShares Copper Miners ETF", "Commodity"),
    ("NRGT.L", "WisdomTree Energy Transition ETC", "Commodity"),
    ("NGSP.L", "WisdomTree Natural Gas ETC", "Commodity"),
    ("COCO", "WisdomTree Cocoa", "Commodity"),
    ("AIGA.L",   "WisdomTree Agriculture ETC",  "Commodity"),
    ("IGLN.L",   "iShares Physical Gold ETC",    "Commodity"),
    ("ISLN.L",   "iShares Physical Silver ETC",  "Commodity"),
    ("UC15.L",   "UBS CMCI Composite SF UCITS ETF USD acc",  "Commodity"),
    ("NUCG.L",   "VanEck Uranium and Nuclear Technologies UCITS ETF",  "Commodity"),
    # Currencies & FX
    ("GBPUSD=X", "GBP/USD", "Index"),
    ("GBPTRY=X",  "GBP/TRY", "Index"),
    ("CNY=X", "USD/CNY", "Index"),
    # Crypto
    ("BTC-GBP", "Bitcoin GBP", "Commodity"),
    ("ETH-GBP", "Ethereum GBP", "Commodity"),
    # Individual Stocks
    ("GOOG", "Alphabet (Google)", "Stock"),
    ("AMZN", "Amazon", "Stock"),
    ("NVDA", "NVIDIA", "Stock"),
    ("ASML", "ASML Holding", "Stock"),
    ("CRCL", "Circle Internet Group", "Stock"),
    ("QCOM", "Qualcomm", "Stock"),
    ("MU", "Micron Technology", "Stock"),
    ("JPM", "JPMorgan Chase", "Stock"),
    ("NVO", "Novo Nordisk", "Stock"),
    ("LLY", "Eli Lilly", "Stock"),
    ("GSK.L", "GSK plc", "Stock"),
    ("HSBA.L", "HSBC Holdings", "Stock"),
    ("DATA.L", "GlobalData plc", "Stock"),
    ("BRBY.L", "Burberry Group", "Stock"),
    ("QQ.L", "QinetiQ Group", "Stock"),
    ("HFG.L", "Hilton Food Group", "Stock"),
    ("CCH.L", "Coca-Cola HBC", "Stock"),
    ("BA.L", "BAE Systems", "Stock"),
    ("SAHOL.IS",  "Sabanci Holding",   "Stock"),
    ("PETKM.IS",  "Petkim",            "Stock"),
    ("ASELS.IS",  "Aselsan",           "Stock"),
    ("ALARK.IS",  "Alarko Holding",    "Stock"),   
    ("KAP.IL",  "National Atomic Company Kazatomprom JSC",    "Stock"),  
]


# --- Composite Funds ---
# Virtual funds calculated as weighted averages of real funds.
# Calculated on the fly in the dashboard — nothing written to the database.
# Weights should sum to 1.0.
# fund_id must exactly match what's in the database.

COMPOSITE_FUNDS = [
    {
        "fund_id": "COMPOSITE:HSBC_EM",
        "display_name": "HSBC Pension Emerging Markets",
        "asset_type": "Fund",
        "components": [
            {"fund_id": "LU1408526199:GBP", "weight": 0.50},  # Robeco Emerging Stars
            {"fund_id": "GB00BL0DTP33:GBP", "weight": 0.50},  # JPM Emerging Markets ESG
        ],
    },
    {
        "fund_id": "COMPOSITE:HSBC_SHARIA",
        "display_name": "HSBC Pension Sharia",
        "asset_type": "Fund",
        "components": [
            {
                "fund_id": "LU2092165666:GBP",
                "weight": 1.00,
            },  # HSBC Islamic Global Equity
        ],
    },
    {
        "fund_id": "COMPOSITE:HSBC_UK_ACTIVE",
        "display_name": "HSBC Pension UK Active",
        "asset_type": "Fund",
        "components": [
            {"fund_id": "GB00BJH4XW03:GBP", "weight": 0.670},  # L&G Future World ESG UK
            {
                "fund_id": "GB00B0ZGQD71:GBP",
                "weight": 0.165,
            },  # Schroder Life UK Smaller Cos
            {
                "fund_id": "GB00B2PLJQ03:GBP",
                "weight": 0.165,
            },  # Artemis UK Special Situations
        ],
    },
    {
        "fund_id": "COMPOSITE:HSBC_NORTH_AMERICA",
        "display_name": "HSBC Pension North America",
        "asset_type": "Fund",
        "components": [
            {
                "fund_id": "GB00B3VGBC62:GBP",
                "weight": 1.00,
            },  # L&G PMC North America Equity
        ],
    },
    {
        "fund_id": "COMPOSITE:HSBC_EUROPE",
        "display_name": "HSBC Pension Europe",
        "asset_type": "Fund",
        "components": [
            {
                "fund_id": "GB00B4YKRJ18:GBP",
                "weight": 1.00,
            },  # L&G PMC Europe Ex UK Equity
        ],
    },
    {
        "fund_id": "COMPOSITE:HSBC_JAPAN",
        "display_name": "HSBC Pension Japan",
        "asset_type": "Fund",
        "components": [
            {"fund_id": "GB00B4ZFV486:GBP", "weight": 1.00},  # L&G PMC Japan Equity
        ],
    },
    {
        "fund_id": "COMPOSITE:HSBC_ASIA_PAC",
        "display_name": "HSBC Pension Asia Pacific",
        "asset_type": "Fund",
        "components": [
            {
                "fund_id": "GB00B4WT1Y33:GBP",
                "weight": 1.00,
            },  # L&G PMC Asia Pac ex Japan
        ],
    },
]
