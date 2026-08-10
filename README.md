# Stock Market Analyzer

A Chrome extension + Python backend that analyzes stocks using technical indicators, fundamentals, balance sheets, earnings data, and news — then provides **entry/exit signals with probability scores** overlaid directly on TradingView charts.

## What It Does

- **Technical Analysis**: RSI, MACD, Bollinger Bands, Stochastic, ADX, ATR, Moving Averages (SMA/EMA), Volume/OBV, Support/Resistance, Candlestick Patterns, Golden/Death Cross detection
- **Fundamental Analysis**: PE ratio, P/B, profit margins, ROE, debt-to-equity, current ratio, free cash flow, earnings growth, revenue growth
- **Balance Sheet & Income Statement**: Total assets, liabilities, equity, cash position, net debt, revenue, EBITDA
- **Earnings**: Upcoming dates, EPS estimates, surprise history
- **News Sentiment**: Keyword-based sentiment scoring from Google News and yfinance
- **Signal Engine**: Combines all the above into a weighted composite score producing entry price, target price, stop loss, and probability scores

## Architecture

```
stock-market-analyzer/
├── backend/                    # Python FastAPI server
│   ├── main.py                 # API endpoints
│   ├── requirements.txt
│   ├── analysis/
│   │   ├── technical.py        # RSI, MACD, Bollinger, etc.
│   │   ├── fundamental.py      # Valuation, profitability, health
│   │   └── scoring.py          # Entry/exit signal generation
│   └── data/
│       └── fetcher.py          # yfinance data + news fetching
├── extension/                  # Chrome Extension (Manifest V3)
│   ├── manifest.json
│   ├── popup.html/css/js       # Extension popup UI
│   ├── content.js              # TradingView chart overlay
│   ├── content-styles.css      # Overlay styles
│   └── background.js           # Service worker
└── README.md
```

## Setup

### 1. Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the server
python main.py
# → API running at http://localhost:8899
```

### 2. Chrome Extension

1. Open Chrome → `chrome://extensions/`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select the `extension/` folder
5. The extension icon appears in your toolbar

## Usage

### From the Extension Popup

1. Click the extension icon in Chrome toolbar
2. Enter a stock symbol (e.g., `RELIANCE.NS` for NSE, `AAPL` for US stocks)
3. Select a time period
4. Click **Analyze**
5. View the full analysis: action, confidence, entry/exit prices, score breakdown, indicators, fundamentals, and news

### On TradingView

1. Navigate to any chart on [tradingview.com](https://www.tradingview.com)
2. Open the extension popup and analyze a stock
3. With "Chart overlay" checked, the extension injects:
   - A floating analysis panel (draggable, minimizable)
   - Entry/exit signal markers on the chart
   - Price level lines for entry, target, and stop loss

### API Endpoints (Direct)

| Endpoint | Description |
|---|---|
| `GET /analyze/{symbol}` | Full analysis (technical + fundamental + signals) |
| `GET /technical/{symbol}` | Technical indicators only |
| `GET /fundamental/{symbol}` | Fundamental analysis only |
| `GET /signals/{symbol}` | Entry/exit signals with historical markers |
| `GET /news/{symbol}` | Recent news articles |

Query params: `period` (1mo, 3mo, 6mo, 1y, 2y, 5y), `interval` (1d, 1wk, 1mo)

**Example:**
```bash
curl http://localhost:8899/analyze/RELIANCE.NS?period=1y
```

## Stock Symbol Format

| Market | Format | Example |
|---|---|---|
| NSE India | `SYMBOL.NS` | `RELIANCE.NS`, `TCS.NS`, `INFY.NS` |
| BSE India | `SYMBOL.BO` | `RELIANCE.BO` |
| US (NYSE/NASDAQ) | `SYMBOL` | `AAPL`, `GOOGL`, `MSFT` |
| UK | `SYMBOL.L` | `BARC.L` |

## Signal Scoring

The composite score (0–100) drives the action recommendation:

| Score | Action |
|---|---|
| 75–95 | STRONG BUY |
| 65–74 | BUY / LEAN BUY |
| 50–64 | HOLD |
| 35–49 | LEAN SELL |
| 5–34 | SELL / STRONG SELL |

**Weights**: Technical 50% · Fundamental 30% · Earnings proximity 10% · News sentiment 10%

## Disclaimer

This tool is for **educational and informational purposes only**. It is not financial advice. Always do your own research and consult a qualified financial advisor before making investment decisions. Past performance does not guarantee future results.
