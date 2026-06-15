# config.py
# -----------------------------------------------------------------------
# Single source of truth for all FTScrapper settings.
# To change anything about how the scraper or importer runs,
# this is the only file you need to touch.
# -----------------------------------------------------------------------


# --- FT Fund List ---
# Funds tracked via FT Markets price scraper.
# 'id' is the FT identifier that goes into the URL.
FUNDS = [
    {"name": "SL Asia Pacific Ex Japan",                "id": "GB0031728438:GBP"},
    {"name": "SL Gold",                                  "id": "GB00B3VNFD68:GBP"},
    {"name": "SL China",                                 "id": "GB00B7Z71453:GBP"},
    {"name": "SL JPM Natural Resources",                 "id": "GB00B61JR401:GBP"},
    {"name": "SL Ishares Pacific",                       "id": "GB00B849FB47:GBP"},
    {"name": "SL L&G Global Infrastructure",             "id": "GB00BF0TZK67:GBP"},
    {"name": "HSBC Islamic Global Equity",               "id": "LU2092165666:GBP"},
    {"name": "SL Macquarie Global Infrastructure Secs",  "id": "GB00B3K5WJ87:GBP"},
    {"name": "Robeco Emerging Stars Equities G GBP",     "id": "LU1408526199:GBP"},
    {"name": "JPMorgan Emerging Markets ESG Equity C",   "id": "GB00BL0DTP33:GBP"},
    {"name": "Schroder Life UK Smaller Companies",       "id": "GB00B0ZGQD71:GBP"},
    {"name": "Artemis UK Special Situations Fund",       "id": "GB00B2PLJQ03:GBP"},
    {"name": "L&G PMC North America Equity Index",       "id": "GB00B3VGBC62:GBP"},
    {"name": "L&G PMC Europe Ex UK Equity Index",        "id": "GB00B4YKRJ18:GBP"},
    {"name": "L&G PMC Japan Equity Index",               "id": "GB00B4ZFV486:GBP"},
    {"name": "L&G PMC Asia Pac ex Japan Dev Eq",         "id": "GB00B4WT1Y33:GBP"},
    {"name": "L&G Future World ESG Optimised UK Index",  "id": "GB00BJH4XW03:GBP"},
    {"name": "Fidelity Funds - Latin America Fund W-Acc-GBP", "id": "LU1033664027:GBP"},
    {"name": "Fidelity Asia Fund W Acc",                 "id": "GB00B6Y7NF43:GBX"},
    {"name": "Fid Fil UK HSBC Islamic 0 GBP",            "id": "0P0001EWE2"},
]


# --- Yahoo Finance Tickers ---
# Format: (ticker, display_name, asset_type)
# For ETFs that also have holdings CSV imports, a 4th element is added: provider
#   provider values: 'ishares' | 'vaneck' | 'wisdomtree' | 'ubs' | 'fidelity'
# ETFs WITHOUT a 4th element are price-tracked only (no holdings import).
# File naming for holdings CSVs: {TICKER_WITHOUT_SUFFIX}_{anything}.csv
#   e.g. AINF_20260610.csv, DFNG_holdings.csv

YAHOO_TICKERS = [
    # ── Indices — Global ────────────────────────────────────────────────────
    ("^GSPC",       "S&P 500",                          "Index"),
    ("^RUT",        "Russell 2000",                     "Index"),
    ("^DJI",        "Dow Jones",                        "Index"),
    ("^IXIC",       "NASDAQ Composite",                 "Index"),
    ("^VIX",        "VIX Volatility",                   "Index"),
    ("^FTSE",       "FTSE 100",                         "Index"),
    ("^FTMC",       "FTSE 250",                         "Index"),
    ("^GDAXI",      "DAX",                              "Index"),
    ("^FCHI",       "CAC 40",                           "Index"),
    ("^STOXX50E",   "Euro Stoxx 50",                    "Index"),

    # ── Indices — Asia Pacific ───────────────────────────────────────────────
    ("^N225",       "Nikkei 225",                       "Index"),
    ("^HSI",        "Hang Seng",                        "Index"),
    ("^KS11",       "KOSPI",                            "Index"),
    ("^AXJO",       "S&P ASX 200",                      "Index"),
    ("^BSESN",      "BSE Sensex",                       "Index"),
    ("000001.SS",   "Shanghai Composite",               "Index"),
    ("^TWII",       "Taiwan Weighted",                  "Index"),
    ("^STI",        "Singapore STI",                    "Index"),
    ("^JKSE",       "Jakarta Composite",                "Index"),
    ("^NZ50",       "NZX 50",                           "Index"),

    # ── Indices — Other ──────────────────────────────────────────────────────
    ("XU030.IS",    "BIST 30",                          "Index"),
    ("^BVSP",       "Ibovespa Brazil",                  "Index"),
    ("^GSPTSE",     "S&P TSX Canada",                   "Index"),

    # ── Currencies & FX ──────────────────────────────────────────────────────
    ("GBPUSD=X",    "GBP/USD",                          "Index"),
    ("GBPTRY=X",    "GBP/TRY",                          "Index"),
    ("CNY=X",       "USD/CNY",                          "Index"),

    # ── Global Equity ETFs — price tracking only (no holdings import) ────────
    ("URTH",        "MSCI World",                       "ETF"),
    ("EEM",         "MSCI Emerging Markets",            "ETF"),
    ("VWRL.L",      "FTSE All World",                   "ETF"),
    ("CSP1.L",      "iShares Core S&P 500 ETF",         "ETF"),
    ("XDJP.L",      "Xtr Nikkei 225 UCITS ETF",         "ETF"),
    ("HMCH.L",      "HSBC MSCI China UCITS ETF",        "ETF"),
    ("HCAN.L",      "HSBC MSCI Canada UCITS ETF",       "ETF"),
    ("XAIX.L",      "X AI and Big Data UCITS ETF",      "ETF"),
    ("CSCA.L",      "iShares MSCI Canada UCITS ETF",    "ETF"),
    ("HMAF.L",      "HSBC MSCI AC Far East ex Japan",   "ETF"),

    # ── ETFs — with holdings CSV import (4th element = provider) ────────────
    # iShares
    ("AINF.L",      "iShares AI Infrastructure ETF",               "ETF", "ishares"),
    ("DFEU.L",      "iShares Europe Defence ETF",                   "ETF", "ishares"),
    ("IITU.L",      "iShares S&P 500 IT Sector UCITS ETF",          "ETF", "ishares"),
    ("IUIT.L",      "iShares S&P 500 IT Sector UCITS ETF USD",          "ETF", "ishares"),
    ("IGLN.L",      "iShares Physical Gold ETC",                    "ETF", "ishares"),
    ("ISLN.L",      "iShares Physical Silver ETC",                  "ETF", "ishares"),
    ("MINE.L",      "iShares Copper Miners ETF",                    "ETF", "ishares"),
    ("NUCG.L",      "VanEck Uranium and Nuclear Technologies ETF",  "ETF", "vaneck"),
    ("NUCL.L",      "VanEck Uranium and Nuclear Technologies USD ETF",  "ETF", "vaneck"),
    ("PLAY.L",      "iShares Digital Entertainment ETF",            "ETF", "ishares"),
    ("QANT.L",      "iShares Quantum Computing ETF",                "ETF", "ishares"),
    ("SEMI.L",      "iShares MSCI Global Semiconductors ETF",       "ETF", "ishares"),
    ("SPGP.L",      "iShares Gold Producers ETF",                   "ETF", "ishares"),
    ("SPAG.L",      "iShares Agribusiness ETF",                   "ETF", "ishares"),
    ("UIFS.L",      "iShares S&P 500 Financials ETF",               "ETF", "ishares"),
    ("IUFS.L",      "iShares S&P 500 Financials ETF GBP",               "ETF", "ishares"),
    ("IUSU.L",      "iShares S&P 500 Utilities Sector UCITS ETF",   "ETF", "ishares"),
    ("IUUS.L",      "iShares S&P 500 Utilities Sector UCITS ETF USD",   "ETF", "ishares"),
    # VanEck  (parser TODO — CSV import will be enabled once parser is built)
    ("DFNG.L",      "VanEck Defence ETF (GBP)",                     "ETF", "vaneck"),
    ("NATP.L",      "VanEck NATO Defence ETF",                      "ETF", "vaneck"),
    ("NATO.L", "HANetf Future of Defence UCITS ETF", "ETF", "hanetf"),
    # WisdomTree  (parser TODO)
    ("QWTM.L",      "WisdomTree Quantum Computing ETF",             "ETF", "wisdomtree"),
    ("WQTM.L",      "WisdomTree Quantum Computing ETF USD",             "ETF", "wisdomtree"),
    ("WEAP.L",      "WisdomTree Wheat ETC",                         "ETF", "wisdomtree"),
    # UBS  (parser TODO)
    ("UC15.L",      "UBS CMCI Composite SF UCITS ETF",              "ETF", "ubs"),
    # Fidelity  (parser TODO)
    ("FCBR.L",      "FT Nasdaq Clean Energy UCITS ETF",             "ETF", "fidelity"),

    # ── Commodity ETCs ───────────────────────────────────────────────────────
    ("GC=F",        "Gold Futures",                     "Commodity"),
    ("SI=F",        "Silver Futures",                   "Commodity"),
    ("HG=F",        "Copper Futures",                   "Commodity"),
    ("ZW=F",        "Wheat Futures",                    "Commodity"),
    ("CL=F",        "Crude Oil Futures",                "Commodity"),
    ("NG=F",        "Natural Gas Futures",              "Commodity"),
    ("CC=F",        "Cocoa Futures",                    "Commodity"),
    ("BZ=F",        "Brent Crude Futures",              "Commodity"),
    ("PHPP.L",      "WT Physical Precious Metals ETC",  "Commodity"),
    ("COPB.L",      "WisdomTree Copper ETC",            "Commodity"),
    ("NRGT.L",      "WisdomTree Energy Transition ETC", "Commodity"),
    ("NGSP.L",      "WisdomTree Natural Gas ETC",       "Commodity"),
    ("COCO",        "WisdomTree Cocoa",                 "Commodity"),
    ("AIGA.L",      "WisdomTree Agriculture ETC",       "Commodity"),

    # ── Crypto ───────────────────────────────────────────────────────────────
    ("BTC-GBP",     "Bitcoin GBP",                      "Crypto"),
    ("ETH-GBP",     "Ethereum GBP",                     "Crypto"),
    ("CBTC.L",      "21Shares Bitcoin Core ETP",         "Crypto"),
    

    # ── Individual Stocks — US ───────────────────────────────────────────────
    ("GOOG",        "Alphabet (Google)",                "Stock"),
    ("AMZN",        "Amazon",                           "Stock"),
    ("NVDA",        "NVIDIA",                           "Stock"),
    ("MSFT",        "Microsoft Corporation",            "Stock"),
    ("SPGI",        "S&P Global Inc.",                  "Stock"),
    ("ASML",        "ASML Holding",                     "Stock"),
    ("CRCL",        "Circle Internet Group",            "Stock"),
    ("QCOM",        "Qualcomm",                         "Stock"),
    ("MU",          "Micron Technology",                "Stock"),
    ("MARA",        "MARA Holdings Inc",                "Stock"),
    ("JPM",         "JPMorgan Chase",                   "Stock"),
    ("NVO",         "Novo Nordisk",                     "Stock"),
    ("LLY",         "Eli Lilly",                        "Stock"),

    # ── Individual Stocks — UK ───────────────────────────────────────────────
    ("GSK.L",       "GSK plc",                          "Stock"),
    ("HSBA.L",      "HSBC Holdings",                    "Stock"),
    ("DATA.L",      "GlobalData plc",                   "Stock"),
    ("BRBY.L",      "Burberry Group",                   "Stock"),
    ("QQ.L",        "QinetiQ Group",                    "Stock"),
    ("HFG.L",       "Hilton Food Group",                "Stock"),
    ("CCH.L",       "Coca-Cola HBC",                    "Stock"),
    ("GRG.L",       "Greggs plc",                       "Stock"),
    ("BA.L",        "BAE Systems",                      "Stock"),
    ("AV.L",        "Aviva plc",                      "Stock"),

    # ── Individual Stocks — Turkey ───────────────────────────────────────────
    ("SAHOL.IS",    "Sabanci Holding",                  "Stock"),
    ("PETKM.IS",    "Petkim",                           "Stock"),
    ("ASELS.IS",    "Aselsan",                          "Stock"),
    ("ALARK.IS",    "Alarko Holding",                   "Stock"),
    ("NTHOL.IS",    "Net Holding",                      "Stock"),

    # ── Individual Stocks — Other ────────────────────────────────────────────
    ("KAP.IL",      "Kazatomprom JSC",                  "Stock"),
]


# --- Derived lookups (do not edit — auto-built from YAHOO_TICKERS) ----------
# Maps ticker prefix (without .L suffix) → Yahoo fund_id
# Used by the ETF holdings importer to match CSV filename prefixes to DB records.
# Only ETFs with a provider (4th element) are included.
FUND_ID_MAP = {
    t[0].replace(".L", "").replace(".IS", ""): f"YF:{t[0]}"
    for t in YAHOO_TICKERS
    if len(t) == 4 and t[2] == "ETF"
}

# Maps ticker prefix → provider string (for parser selection in importer)
ETF_PROVIDER_MAP = {
    t[0].replace(".L", "").replace(".IS", ""): t[3]
    for t in YAHOO_TICKERS
    if len(t) == 4 and t[2] == "ETF"
}


# --- Date & Dashboard Settings ----------------------------------------------
FIRST_RUN_DAYS = 365
CHART_CATEGORY_THRESHOLD = 0.02   # categories below 2% grouped as 'Other'
DEFAULT_SINCE_DATE = '2026-03-01'


# --- Paths ------------------------------------------------------------------
DB_PATH     = "data/funds.db"
IMPORT_DIR  = "data/etf_holdings_import/input"
ARCHIVE_DIR = "data/etf_holdings_import/archive"
EXCEL_PATH  = "data/Funds Database.xlsx"


# --- Request Headers --------------------------------------------------------
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


# --- Account Assignments ----------------------------------------------------
# For non-transaction holdings not covered by the transaction ledger.
HOLDING_ACCOUNTS = {
    '0P0001EWE2':              'AB Pension',
    'COMPOSITE:HSBC_ASIA_PAC': 'AB Pension',
    'COMPOSITE:HSBC_EM':       'AB Pension',
    'ASSET:HOUSE':             'HOUSE',
}


# --- Composite Funds --------------------------------------------------------
# Virtual funds calculated as weighted averages of real funds.
# Calculated on the fly in the dashboard — nothing written to the database.
# Weights should sum to 1.0.
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
            {"fund_id": "LU2092165666:GBP", "weight": 1.00},  # HSBC Islamic Global Equity
        ],
    },
    {
        "fund_id": "COMPOSITE:HSBC_UK_ACTIVE",
        "display_name": "HSBC Pension UK Active",
        "asset_type": "Fund",
        "components": [
            {"fund_id": "GB00BJH4XW03:GBP", "weight": 0.670},  # L&G Future World ESG UK
            {"fund_id": "GB00B0ZGQD71:GBP", "weight": 0.165},  # Schroder Life UK Smaller Cos
            {"fund_id": "GB00B2PLJQ03:GBP", "weight": 0.165},  # Artemis UK Special Situations
        ],
    },
    {
        "fund_id": "COMPOSITE:HSBC_NORTH_AMERICA",
        "display_name": "HSBC Pension North America",
        "asset_type": "Fund",
        "components": [
            {"fund_id": "GB00B3VGBC62:GBP", "weight": 1.00},  # L&G PMC North America Equity
        ],
    },
    {
        "fund_id": "COMPOSITE:HSBC_EUROPE",
        "display_name": "HSBC Pension Europe",
        "asset_type": "Fund",
        "components": [
            {"fund_id": "GB00B4YKRJ18:GBP", "weight": 1.00},  # L&G PMC Europe Ex UK Equity
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
            {"fund_id": "GB00B4WT1Y33:GBP", "weight": 1.00},  # L&G PMC Asia Pac ex Japan
        ],
    },
]