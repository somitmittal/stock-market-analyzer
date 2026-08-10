"""
Stock data fetching module — Indian market focused.
Uses yfinance for NSE/BSE price data, fundamentals, and financial statements.
"""
import yfinance as yf
import pandas as pd
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Optional
import csv
import io
import os
import json
import time

_NSE_SYMBOLS_CACHE: dict = {"data": None, "ts": 0}
_NSE_CACHE_FILE = os.path.join(os.path.dirname(__file__), "nse_symbols.json")

_SECTOR_TAGS: dict[str, str] = {}  # populated lazily from fallback list


def resolve_indian_symbol(symbol: str, exchange: str = "NSE") -> str:
    """
    Ensure a symbol has the correct yfinance suffix for Indian markets.
    If user types 'RELIANCE', convert to 'RELIANCE.NS' or 'RELIANCE.BO'.
    """
    symbol = symbol.strip().upper()
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
    return symbol + suffix


def get_stock_data(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"No data found for {symbol}. Check the symbol — for NSE use symbols like RELIANCE, TCS, INFY.")
    return df


def search_nse_symbols(query: str, limit: int = 15) -> list[dict]:
    """
    Search NSE equity symbols with ranked relevance.
    Priority: exact symbol > symbol starts-with > name/tag word match > symbol contains.
    Sector tags (defence, pharma, auto, etc.) work regardless of data source.
    """
    query = query.strip().upper()
    if not query:
        return []

    symbols = _load_nse_symbols()
    tags_map = _get_sector_tags()

    exact = []
    sym_starts = []
    name_word_starts = []
    sym_contains = []

    for item in symbols:
        sym = item["symbol"].upper()
        name = item["name"].upper()
        tags = tags_map.get(sym, "").upper()
        searchable = name + " " + tags
        if sym == query:
            exact.append(item)
        elif sym.startswith(query):
            sym_starts.append(item)
        elif any(w.startswith(query) for w in searchable.split()):
            name_word_starts.append(item)
        elif query in sym:
            sym_contains.append(item)

    results = exact + sym_starts + name_word_starts + sym_contains

    if not any(r["symbol"].upper() == query for r in results):
        results.append({"symbol": query, "name": f"{query} (direct lookup)"})

    return results[:limit]


def _get_sector_tags() -> dict[str, str]:
    """Sector/keyword tags for search — built once from fallback list."""
    global _SECTOR_TAGS
    if _SECTOR_TAGS:
        return _SECTOR_TAGS
    fallback = _get_fallback_symbols()
    _SECTOR_TAGS = {item["symbol"].upper(): item.get("tags", "") for item in fallback}
    return _SECTOR_TAGS


def _load_nse_symbols() -> list[dict]:
    """Load NSE symbol list from cache or fetch, merged with fallback for coverage."""
    now = time.time()
    if _NSE_SYMBOLS_CACHE["data"] and (now - _NSE_SYMBOLS_CACHE["ts"]) < 86400:
        return _NSE_SYMBOLS_CACHE["data"]

    api_symbols = []
    if os.path.exists(_NSE_CACHE_FILE):
        try:
            age = now - os.path.getmtime(_NSE_CACHE_FILE)
            if age < 86400:
                with open(_NSE_CACHE_FILE, "r") as f:
                    api_symbols = json.load(f)
        except Exception:
            pass

    if not api_symbols:
        api_symbols = _fetch_nse_symbols()
        if api_symbols:
            try:
                with open(_NSE_CACHE_FILE, "w") as f:
                    json.dump(api_symbols, f)
            except Exception:
                pass

    merged = _merge_with_fallback(api_symbols)
    _NSE_SYMBOLS_CACHE["data"] = merged
    _NSE_SYMBOLS_CACHE["ts"] = now
    return merged


def _merge_with_fallback(api_symbols: list[dict]) -> list[dict]:
    """Merge API symbols with fallback list so curated stocks are always searchable."""
    existing = {item["symbol"].upper() for item in api_symbols}
    fallback = _get_fallback_symbols()
    merged = list(api_symbols)
    for item in fallback:
        if item["symbol"].upper() not in existing:
            merged.append({"symbol": item["symbol"], "name": item["name"]})
    return merged


def _fetch_nse_symbols() -> list[dict]:
    """
    Fetch the COMPLETE NSE equity list (~2200 stocks).
    Tries multiple sources: NSE CSV dump, NSE API, then yfinance validation.
    """
    # Method 1: NSE equity master CSV — most complete source
    symbols = _fetch_nse_csv()
    if symbols and len(symbols) > 500:
        return symbols

    # Method 2: NSE API for major indices (gets ~200 F&O stocks)
    symbols = _fetch_nse_api()
    if symbols and len(symbols) > 100:
        return symbols

    # Method 3: Fallback curated list
    return _get_fallback_symbols()


def _fetch_nse_csv() -> list[dict]:
    """Fetch full equity list from NSE's CSV endpoint."""
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        # Hit main page first to get cookies (NSE requires this)
        session.get("https://www.nseindia.com", timeout=10)

        # Fetch the full equity stock list
        res = session.get(
            "https://www.nseindia.com/api/equity-stockIndices?index=BROAD%20MARKET%20INDICES",
            timeout=15,
        )
        symbols = []
        if res.ok:
            data = res.json().get("data", [])
            for d in data:
                sym = d.get("symbol", "").strip()
                name = d.get("meta", {}).get("companyName", "") or d.get("companyName", "") or sym
                if sym and sym != "NIFTY 50":
                    symbols.append({"symbol": sym, "name": name})

        # Also try all listed equities
        for idx_name in [
            "NIFTY%2050", "NIFTY%20NEXT%2050", "NIFTY%20MIDCAP%2050",
            "NIFTY%20MIDCAP%20100", "NIFTY%20SMALLCAP%20100",
            "NIFTY%20SMALLCAP%20250", "NIFTY%20500",
            "NIFTY%20TOTAL%20MARKET",
        ]:
            try:
                r = session.get(
                    f"https://www.nseindia.com/api/equity-stockIndices?index={idx_name}",
                    timeout=10,
                )
                if r.ok:
                    for d in r.json().get("data", []):
                        sym = d.get("symbol", "").strip()
                        name = d.get("meta", {}).get("companyName", "") or sym
                        if sym and not any(s["symbol"] == sym for s in symbols):
                            symbols.append({"symbol": sym, "name": name})
            except Exception:
                continue

        if symbols:
            return symbols
    except Exception:
        pass
    return []


def _fetch_nse_api() -> list[dict]:
    """Fetch F&O securities list from NSE API."""
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        session.get("https://www.nseindia.com", timeout=10)
        res = session.get(
            "https://www.nseindia.com/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O",
            timeout=10,
        )
        if res.ok:
            data = res.json().get("data", [])
            return [{"symbol": d["symbol"], "name": d.get("meta", {}).get("companyName", d["symbol"])} for d in data]
    except Exception:
        pass
    return []


def _get_fallback_symbols() -> list[dict]:
    """Comprehensive list of NSE stocks with sector tags for search."""
    stocks = [
        # Nifty 50
        ("RELIANCE", "Reliance Industries", "energy oil conglomerate"),
        ("TCS", "Tata Consultancy Services", "IT software tech"),
        ("HDFCBANK", "HDFC Bank", "banking finance private"),
        ("INFY", "Infosys", "IT software tech"),
        ("ICICIBANK", "ICICI Bank", "banking finance private"),
        ("HINDUNILVR", "Hindustan Unilever", "FMCG consumer"),
        ("ITC", "ITC Limited", "FMCG cigarette hotel"),
        ("SBIN", "State Bank of India", "banking finance PSU"),
        ("BHARTIARTL", "Bharti Airtel", "telecom"),
        ("BAJFINANCE", "Bajaj Finance", "NBFC finance lending"),
        ("KOTAKBANK", "Kotak Mahindra Bank", "banking finance private"),
        ("LT", "Larsen & Toubro", "infra engineering construction"),
        ("HCLTECH", "HCL Technologies", "IT software tech"),
        ("AXISBANK", "Axis Bank", "banking finance private"),
        ("ASIANPAINT", "Asian Paints", "paints consumer"),
        ("MARUTI", "Maruti Suzuki", "auto car automobile"),
        ("SUNPHARMA", "Sun Pharma", "pharma healthcare"),
        ("TITAN", "Titan Company", "jewellery watches consumer"),
        ("ULTRACEMCO", "UltraTech Cement", "cement building"),
        ("WIPRO", "Wipro", "IT software tech"),
        ("ADANIENT", "Adani Enterprises", "conglomerate infra"),
        ("NTPC", "NTPC Limited", "power energy PSU"),
        ("POWERGRID", "Power Grid Corp", "power energy PSU"),
        ("TATAMOTORS", "Tata Motors", "auto car automobile EV"),
        ("TATASTEEL", "Tata Steel", "metal steel"),
        ("ONGC", "Oil & Natural Gas Corp", "energy oil PSU"),
        ("JSWSTEEL", "JSW Steel", "metal steel"),
        ("M&M", "Mahindra & Mahindra", "auto SUV tractor automobile"),
        ("COALINDIA", "Coal India", "mining coal PSU"),
        ("ADANIPORTS", "Adani Ports", "infra logistics port"),
        ("TECHM", "Tech Mahindra", "IT software tech telecom"),
        ("INDUSINDBK", "IndusInd Bank", "banking finance private"),
        ("HINDALCO", "Hindalco Industries", "metal aluminium"),
        ("DRREDDY", "Dr Reddy's Labs", "pharma healthcare"),
        ("CIPLA", "Cipla", "pharma healthcare"),
        ("GRASIM", "Grasim Industries", "cement textile conglomerate"),
        ("DIVISLAB", "Divi's Labs", "pharma API"),
        ("BPCL", "Bharat Petroleum", "energy oil PSU"),
        ("EICHERMOT", "Eicher Motors", "auto motorcycle Royal Enfield"),
        ("APOLLOHOSP", "Apollo Hospitals", "healthcare hospital"),
        ("BRITANNIA", "Britannia Industries", "FMCG food biscuit"),
        ("NESTLEIND", "Nestle India", "FMCG food consumer"),
        ("TATACONSUM", "Tata Consumer Products", "FMCG tea coffee food"),
        ("HEROMOTOCO", "Hero MotoCorp", "auto motorcycle two-wheeler"),
        ("BAJAJ-AUTO", "Bajaj Auto", "auto motorcycle two-wheeler"),
        ("BAJAJFINSV", "Bajaj Finserv", "NBFC finance insurance"),
        ("TRENT", "Trent", "retail fashion Westside Zudio"),
        ("JIOFIN", "Jio Financial Services", "NBFC finance fintech"),
        ("SHRIRAMFIN", "Shriram Finance", "NBFC finance lending"),
        # Nifty Next 50
        ("SBILIFE", "SBI Life Insurance", "insurance life"),
        ("HDFCLIFE", "HDFC Life Insurance", "insurance life"),
        ("PIDILITIND", "Pidilite Industries", "adhesive chemical consumer"),
        ("HAVELLS", "Havells India", "electrical consumer appliance"),
        ("SIEMENS", "Siemens India", "capital goods engineering"),
        ("ABB", "ABB India", "capital goods engineering automation"),
        ("GODREJCP", "Godrej Consumer Products", "FMCG consumer"),
        ("DABUR", "Dabur India", "FMCG ayurveda consumer"),
        ("AMBUJACEM", "Ambuja Cements", "cement building"),
        ("SHREECEM", "Shree Cement", "cement building"),
        ("TORNTPHARM", "Torrent Pharma", "pharma healthcare"),
        ("LUPIN", "Lupin", "pharma healthcare"),
        ("BIOCON", "Biocon", "pharma biotech healthcare"),
        ("AUROPHARMA", "Aurobindo Pharma", "pharma healthcare"),
        ("DLF", "DLF Limited", "real estate property"),
        ("MARICO", "Marico", "FMCG consumer oil"),
        ("COLPAL", "Colgate Palmolive India", "FMCG consumer"),
        ("BERGEPAINT", "Berger Paints", "paints consumer"),
        ("ICICIPRULI", "ICICI Prudential Life", "insurance life"),
        ("ICICIGI", "ICICI Lombard General", "insurance general"),
        ("MCDOWELL-N", "United Spirits", "liquor alcohol FMCG"),
        ("INDIGO", "InterGlobe Aviation", "airline aviation travel"),
        ("CHOLAFIN", "Cholamandalam Investment", "NBFC finance"),
        ("MAXHEALTH", "Max Healthcare", "healthcare hospital"),
        ("POLYCAB", "Polycab India", "cable wire electrical"),
        ("PERSISTENT", "Persistent Systems", "IT software tech"),
        ("TATAELXSI", "Tata Elxsi", "IT design engineering tech"),
        ("COFORGE", "Coforge", "IT software tech"),
        ("MPHASIS", "Mphasis", "IT software tech"),
        ("LTIM", "LTIMindtree", "IT software tech"),
        ("PIIND", "PI Industries", "chemical agrochem"),
        ("NAUKRI", "Info Edge India", "internet jobs recruitment"),
        ("PAGEIND", "Page Industries", "textile garment Jockey"),
        ("MUTHOOTFIN", "Muthoot Finance", "NBFC gold loan finance"),
        ("MOTHERSON", "Samvardhana Motherson", "auto ancillary"),
        ("BOSCHLTD", "Bosch", "auto ancillary engineering"),
        # Banking & Finance
        ("BANKBARODA", "Bank of Baroda", "banking finance PSU"),
        ("PNB", "Punjab National Bank", "banking finance PSU"),
        ("CANBK", "Canara Bank", "banking finance PSU"),
        ("IOB", "Indian Overseas Bank", "banking finance PSU"),
        ("YESBANK", "Yes Bank", "banking finance private"),
        ("BANDHANBNK", "Bandhan Bank", "banking finance microfinance"),
        ("FEDERALBNK", "Federal Bank", "banking finance private"),
        ("IDFCFIRSTB", "IDFC First Bank", "banking finance private"),
        ("RBLBANK", "RBL Bank", "banking finance private"),
        ("AUBANK", "AU Small Finance Bank", "banking finance SFB"),
        ("MANAPPURAM", "Manappuram Finance", "NBFC gold loan finance"),
        ("LICHSGFIN", "LIC Housing Finance", "housing finance NBFC"),
        ("SBICARD", "SBI Cards", "credit card finance"),
        ("HDFCAMC", "HDFC AMC", "mutual fund AMC finance"),
        ("BAJAJHLDNG", "Bajaj Holdings", "finance holding"),
        ("POONAWALLA", "Poonawalla Fincorp", "NBFC finance lending"),
        ("IRFC", "Indian Railway Finance", "finance railway PSU"),
        ("RECLTD", "REC Limited", "power finance PSU"),
        ("PFC", "Power Finance Corp", "power finance PSU"),
        # IT & Tech
        ("LTTS", "L&T Technology Services", "IT engineering tech"),
        ("HAPPSTMNDS", "Happiest Minds", "IT software tech"),
        ("ZOMATO", "Zomato", "food delivery internet tech"),
        ("PAYTM", "One 97 Communications", "fintech payments digital"),
        ("DELHIVERY", "Delhivery", "logistics delivery ecommerce"),
        ("NYKAA", "FSN E-Commerce Nykaa", "beauty ecommerce retail"),
        ("IRCTC", "IRCTC", "railway travel booking PSU"),
        ("POLICYBZR", "PB Fintech PolicyBazaar", "insurance fintech"),
        ("CARTRADE", "CarTrade Tech", "auto marketplace tech"),
        # Energy & Power
        ("ADANIGREEN", "Adani Green Energy", "renewable solar power green"),
        ("ADANIPOWER", "Adani Power", "power energy thermal"),
        ("TATAPOWER", "Tata Power", "power energy renewable"),
        ("IOC", "Indian Oil Corporation", "energy oil refinery PSU"),
        ("GAIL", "GAIL India", "gas energy PSU"),
        ("HINDPETRO", "Hindustan Petroleum", "energy oil refinery PSU"),
        ("PETRONET", "Petronet LNG", "gas energy LNG"),
        ("NHPC", "NHPC Limited", "hydro power energy PSU"),
        ("SJVN", "SJVN Limited", "hydro power energy PSU renewable"),
        ("TORNTPOWER", "Torrent Power", "power energy utility"),
        ("JSWENERGY", "JSW Energy", "power energy"),
        ("IDEA", "Vodafone Idea", "telecom"),
        # Metals & Mining
        ("VEDL", "Vedanta", "metal mining oil zinc aluminium"),
        ("NATIONALUM", "National Aluminium", "metal aluminium PSU"),
        ("SAIL", "Steel Authority of India", "metal steel PSU"),
        ("NMDC", "NMDC", "mining iron ore PSU"),
        ("JINDALSTEL", "Jindal Steel & Power", "metal steel"),
        ("JSL", "Jindal Stainless", "metal stainless steel"),
        ("MOIL", "MOIL Limited", "mining manganese PSU"),
        # Auto & Auto Ancillary
        ("ASHOKLEY", "Ashok Leyland", "auto truck commercial vehicle"),
        ("TVSMOTOR", "TVS Motor", "auto motorcycle two-wheeler"),
        ("MRF", "MRF Limited", "tyre auto ancillary"),
        ("BALKRISIND", "Balkrishna Industries", "tyre auto ancillary"),
        ("ESCORTS", "Escorts Kubota", "tractor auto farm equipment"),
        ("EXIDEIND", "Exide Industries", "battery auto ancillary"),
        ("AMARAJABAT", "Amara Raja Energy", "battery auto ancillary"),
        ("SOLARINDS", "Solar Industries", "explosives defence chemical"),
        # Pharma & Healthcare
        ("LALPATHLAB", "Dr Lal PathLabs", "diagnostics healthcare pathology"),
        ("IPCALAB", "IPCA Laboratories", "pharma healthcare"),
        ("ALKEM", "Alkem Laboratories", "pharma healthcare"),
        ("NATCOPHARMA", "Natco Pharma", "pharma healthcare generic"),
        ("LAURUSLABS", "Laurus Labs", "pharma API healthcare"),
        ("GLENMARK", "Glenmark Pharma", "pharma healthcare"),
        ("ZYDUSLIFE", "Zydus Lifesciences", "pharma healthcare"),
        ("SYNGENE", "Syngene International", "pharma CDMO biotech"),
        ("FORTIS", "Fortis Healthcare", "healthcare hospital"),
        ("METROPOLIS", "Metropolis Healthcare", "diagnostics healthcare"),
        ("MEDANTA", "Global Health Medanta", "healthcare hospital"),
        # FMCG & Consumer
        ("GODREJIND", "Godrej Industries", "conglomerate chemical"),
        ("EMAMILTD", "Emami", "FMCG consumer personal care"),
        ("JYOTHYLAB", "Jyothy Labs", "FMCG consumer"),
        ("RADICO", "Radico Khaitan", "liquor alcohol"),
        ("VBL", "Varun Beverages", "beverages pepsi FMCG"),
        ("DEVYANI", "Devyani International", "QSR food restaurant pizza"),
        ("JUBLFOOD", "Jubilant FoodWorks", "QSR food restaurant Dominos"),
        # Infra & Real Estate
        ("OBEROIRLTY", "Oberoi Realty", "real estate property"),
        ("GODREJPROP", "Godrej Properties", "real estate property"),
        ("PRESTIGE", "Prestige Estates", "real estate property"),
        ("BRIGADE", "Brigade Enterprises", "real estate property"),
        ("PHOENIXLTD", "The Phoenix Mills", "real estate mall retail"),
        ("LODHA", "Macrotech Developers Lodha", "real estate property"),
        # Cement & Building
        ("ACC", "ACC Limited", "cement building"),
        ("RAMCOCEM", "Ramco Cements", "cement building"),
        ("JKCEMENT", "JK Cement", "cement building"),
        ("DALMIACEM", "Dalmia Bharat", "cement building"),
        ("STARCEMENT", "Star Cement", "cement building"),
        ("JKLAKSHMI", "JK Lakshmi Cement", "cement building"),
        # Defence & PSU
        ("HAL", "Hindustan Aeronautics", "defence aerospace PSU"),
        ("BEL", "Bharat Electronics", "defence electronics PSU"),
        ("BDL", "Bharat Dynamics", "defence missile PSU"),
        ("GRSE", "Garden Reach Shipbuilders", "defence shipbuilding PSU"),
        ("COCHINSHIP", "Cochin Shipyard", "defence shipbuilding PSU"),
        ("MAZAGON", "Mazagon Dock Shipbuilders", "defence shipbuilding PSU submarine"),
        ("MIDHANI", "Mishra Dhatu Nigam", "defence alloy metal PSU"),
        ("DATAPATTNS", "Data Patterns India", "defence electronics"),
        # Chemicals
        ("DEEPAKFERT", "Deepak Fertilisers", "fertiliser chemical"),
        ("DEEPAKNTR", "Deepak Nitrite", "chemical speciality"),
        ("ATUL", "Atul Limited", "chemical speciality"),
        ("CLEAN", "Clean Science & Technology", "chemical speciality"),
        ("TATACHEM", "Tata Chemicals", "chemical soda ash"),
        ("FLUOROCHEM", "Gujarat Fluorochemicals", "chemical fluorine"),
        ("UPL", "UPL Limited", "agrochemical pesticide"),
        ("SRF", "SRF Limited", "chemical fluorine packaging"),
        ("AARTI", "Aarti Industries", "chemical speciality"),
        ("NAVINFLUOR", "Navin Fluorine", "chemical fluorine"),
        # Textiles & Retail
        ("RAYMOND", "Raymond", "textile fashion garment"),
        ("ABFRL", "Aditya Birla Fashion", "retail fashion textile"),
        ("SHOPERSTOP", "Shoppers Stop", "retail department store"),
        ("DMART", "Avenue Supermarts DMart", "retail grocery supermarket"),
        ("RELAXO", "Relaxo Footwears", "footwear consumer"),
        ("BATA", "Bata India", "footwear consumer shoes"),
        # Others
        ("VOLTAS", "Voltas", "AC cooling appliance consumer"),
        ("BLUESTARLT", "Blue Star", "AC cooling appliance"),
        ("CROMPTON", "Crompton Greaves Consumer", "electrical fan appliance"),
        ("DIXON", "Dixon Technologies", "electronics EMS manufacturing"),
        ("KAYNES", "Kaynes Technology", "electronics EMS manufacturing"),
        ("SUNTV", "Sun TV Network", "media entertainment television"),
        ("PVRINOX", "PVR INOX", "entertainment cinema multiplex"),
        ("SONATSOFTW", "Sonata Software", "IT software tech"),
        ("ROUTE", "Route Mobile", "CPaaS messaging cloud tech"),
        ("LATENTVIEW", "Latent View Analytics", "data analytics tech"),
        ("CAMS", "Computer Age Management", "mutual fund AMC registrar"),
        ("KPITTECH", "KPIT Technologies", "IT auto tech engineering"),
        ("ANGELONE", "Angel One", "broking stock market finance"),
        ("CDSL", "Central Depository Services", "depository stock market finance"),
        ("BSE", "BSE Limited", "stock exchange market finance"),
        ("MCX", "Multi Commodity Exchange", "commodity exchange market"),
        ("IEX", "Indian Energy Exchange", "power exchange energy"),
        ("LICI", "Life Insurance Corp", "insurance life PSU LIC"),
        ("INDIANB", "Indian Bank", "banking finance PSU"),
        ("CENTRALBK", "Central Bank of India", "banking finance PSU"),
        ("UNIONBANK", "Union Bank of India", "banking finance PSU"),
        ("MAHABANK", "Bank of Maharashtra", "banking finance PSU"),
        ("SUZLON", "Suzlon Energy", "renewable wind energy green"),
        ("INOXWIND", "Inox Wind", "renewable wind energy green"),
        ("BOROSIL", "Borosil Renewables", "solar glass renewable green"),
        ("TATACOMM", "Tata Communications", "telecom data"),
        ("HFCL", "HFCL Limited", "telecom fibre cable defence"),
        ("RAILTEL", "RailTel Corporation", "telecom railway PSU"),
        ("RVNL", "Rail Vikas Nigam", "railway infra PSU"),
        ("HUDCO", "HUDCO", "housing finance PSU"),
        ("CGPOWER", "CG Power & Industrial", "electrical capital goods"),
        ("KALYANKJIL", "Kalyan Jewellers", "jewellery gold retail"),
        ("SENCO", "Senco Gold", "jewellery gold retail"),
        ("PGEL", "PG Electroplast", "electronics EMS manufacturing"),
    ]
    return [{"symbol": s, "name": n, "tags": t} for s, n, t in stocks]


def get_fundamentals(symbol: str) -> dict:
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}

    return {
        "company_name": info.get("longName", symbol),
        "sector": info.get("sector", "N/A"),
        "industry": info.get("industry", "N/A"),
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "pb_ratio": info.get("priceToBook"),
        "dividend_yield": info.get("dividendYield"),
        "eps": info.get("trailingEps"),
        "revenue": info.get("totalRevenue"),
        "profit_margin": info.get("profitMargins"),
        "operating_margin": info.get("operatingMargins"),
        "roe": info.get("returnOnEquity"),
        "roa": info.get("returnOnAssets"),
        "debt_to_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "quick_ratio": info.get("quickRatio"),
        "free_cash_flow": info.get("freeCashflow"),
        "earnings_growth": info.get("earningsGrowth"),
        "revenue_growth": info.get("revenueGrowth"),
        "52_week_high": info.get("fiftyTwoWeekHigh"),
        "52_week_low": info.get("fiftyTwoWeekLow"),
        "50_day_avg": info.get("fiftyDayAverage"),
        "200_day_avg": info.get("twoHundredDayAverage"),
        "beta": info.get("beta"),
        "short_ratio": info.get("shortRatio"),
        "recommendation": info.get("recommendationKey"),
        "target_mean_price": info.get("targetMeanPrice"),
        "target_high_price": info.get("targetHighPrice"),
        "target_low_price": info.get("targetLowPrice"),
        "number_of_analysts": info.get("numberOfAnalystOpinions"),
    }


def get_balance_sheet(symbol: str) -> dict:
    ticker = yf.Ticker(symbol)
    bs = ticker.balance_sheet
    if bs is None or bs.empty:
        return {"available": False}

    latest = bs.iloc[:, 0]
    return {
        "available": True,
        "date": str(bs.columns[0].date()) if hasattr(bs.columns[0], "date") else str(bs.columns[0]),
        "total_assets": _safe_val(latest, "Total Assets"),
        "total_liabilities": _safe_val(latest, "Total Liabilities Net Minority Interest"),
        "total_equity": _safe_val(latest, "Stockholders Equity"),
        "cash": _safe_val(latest, "Cash And Cash Equivalents"),
        "total_debt": _safe_val(latest, "Total Debt"),
        "net_debt": _safe_val(latest, "Net Debt"),
        "working_capital": _safe_val(latest, "Working Capital"),
    }


def get_income_statement(symbol: str) -> dict:
    ticker = yf.Ticker(symbol)
    inc = ticker.income_stmt
    if inc is None or inc.empty:
        return {"available": False}

    latest = inc.iloc[:, 0]
    return {
        "available": True,
        "date": str(inc.columns[0].date()) if hasattr(inc.columns[0], "date") else str(inc.columns[0]),
        "total_revenue": _safe_val(latest, "Total Revenue"),
        "gross_profit": _safe_val(latest, "Gross Profit"),
        "operating_income": _safe_val(latest, "Operating Income"),
        "net_income": _safe_val(latest, "Net Income"),
        "ebitda": _safe_val(latest, "EBITDA"),
    }


def get_earnings_dates(symbol: str) -> list[dict]:
    """Get upcoming and recent earnings dates."""
    ticker = yf.Ticker(symbol)
    try:
        cal = ticker.earnings_dates
        if cal is None or cal.empty:
            return []
        results = []
        for date_idx, row in cal.head(8).iterrows():
            results.append({
                "date": str(date_idx),
                "eps_estimate": _safe_series_val(row, "EPS Estimate"),
                "reported_eps": _safe_series_val(row, "Reported EPS"),
                "surprise_pct": _safe_series_val(row, "Surprise(%)"),
            })
        return results
    except Exception:
        return []


def get_news(symbol: str) -> list[dict]:
    """Fetch recent news for a stock via yfinance and RSS."""
    ticker = yf.Ticker(symbol)
    articles = []

    yf_news = getattr(ticker, "news", None)
    if yf_news:
        for item in yf_news[:10]:
            articles.append({
                "title": item.get("title", ""),
                "publisher": item.get("publisher", ""),
                "link": item.get("link", ""),
                "published": item.get("providerPublishTime", ""),
                "source": "yfinance",
            })

    clean_symbol = symbol.replace(".NS", "").replace(".BO", "")
    try:
        feed = feedparser.parse(
            f"https://news.google.com/rss/search?q={clean_symbol}+stock&hl=en-IN&gl=IN&ceid=IN:en"
        )
        for entry in feed.entries[:10]:
            articles.append({
                "title": entry.get("title", ""),
                "publisher": entry.get("source", {}).get("title", "Google News"),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": "google_news",
            })
    except Exception:
        pass

    return articles[:15]


def _safe_val(series: pd.Series, key: str) -> Optional[float]:
    try:
        val = series.get(key)
        if pd.isna(val):
            return None
        return float(val)
    except Exception:
        return None


def _safe_series_val(row, key: str):
    try:
        val = row.get(key)
        if pd.isna(val):
            return None
        return float(val)
    except Exception:
        return None
