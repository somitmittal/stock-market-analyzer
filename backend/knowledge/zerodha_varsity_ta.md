# Technical Analysis Knowledge Base

Distilled from Zerodha Varsity Module 2 — Technical Analysis (22 Chapters).
Source: https://zerodha.com/varsity/module/technical-analysis/

This document serves as the authoritative TA reference for the signal engine.
All rules, thresholds, and frameworks below are derived from institutional
best practices as taught by Zerodha Varsity.

---

## 1. Core Assumptions of Technical Analysis

1. **Markets discount everything** — all known and unknown information is
   reflected in the current price. Insider activity shows up in price/volume
   before news becomes public.
2. **The "how" matters more than the "why"** — focus on price reaction, not
   the cause behind it.
3. **Price moves in trends** — once established, a trend persists until a
   clear reversal. Major moves are phased, not instantaneous.
4. **History repeats itself** — market participants react to price movements
   in remarkably similar ways every time, driven by greed and fear.

---

## 2. The Grand Checklist (6-Point Trade Qualification)

Every trade must satisfy these in order. If points 1-3 fail, skip the trade.
Points 4-5 are confirmatory — scale position size based on them.

| # | Checklist Item | Required? | Action if missing |
|---|----------------|-----------|-------------------|
| 1 | Recognizable candlestick pattern | **Mandatory** | Skip trade |
| 2 | S&R confirms (stoploss within 4% of S&R) | **Mandatory** | Skip trade |
| 3 | Volume confirms (above 10-day average) | **Mandatory** | Skip trade |
| 4 | Dow Theory confirms (trend, formations) | Confirmatory | Proceed with caution |
| 5 | Indicators confirm (RSI, MACD) | Confirmatory | Proceed, reduce size |
| 6 | RRR >= 1.5 | **Mandatory** | Skip trade |

---

## 3. Candlestick Patterns

### Single Candle Patterns

| Pattern | Bias | Key Rule |
|---------|------|----------|
| Bullish Marubozu | Bullish | No shadows; buy near close, SL at low |
| Bearish Marubozu | Bearish | No shadows; sell near close, SL at high |
| Doji | Indecision | Tiny body; reversal when at S&R with prior trend |
| Spinning Top | Indecision | Small body, equal shadows; trend uncertainty |
| Hammer | Bullish | Long lower shadow (2x body), small upper shadow; must appear after downtrend |
| Hanging Man | Bearish | Same shape as hammer but appears after uptrend |
| Shooting Star | Bearish | Long upper shadow (2x body), small lower shadow; after uptrend |
| Inverted Hammer | Bullish | Same shape as shooting star but appears after downtrend |

### Multi-Candle Patterns

| Pattern | Candles | Bias | Key Rule |
|---------|---------|------|----------|
| Bullish Engulfing | 2 | Bullish | P2 (green) body completely engulfs P1 (red) body; after downtrend |
| Bearish Engulfing | 2 | Bearish | P2 (red) body completely engulfs P1 (green) body; after uptrend |
| Bullish Harami | 2 | Bullish | P2 small green body contained within P1 large red body |
| Bearish Harami | 2 | Bearish | P2 small red body contained within P1 large green body |
| Morning Star | 3 | Bullish | P1 red, P2 small-body (doji/spinning), P3 green closing above P1 midpoint |
| Evening Star | 3 | Bearish | P1 green, P2 small-body, P3 red closing below P1 midpoint |

### Pattern Rules

- **Prior trend is critical**: bullish patterns require a prior downtrend;
  bearish patterns require a prior uptrend. Without prior trend, the pattern
  is meaningless.
- **Be flexible with definitions**: a small shadow on a marubozu is acceptable
  if the shadow length is < 1-2% of the candle range.
- **Buy strength, sell weakness**: buy on green candle days (close > open),
  sell on red candle days (close < open).
- **Risk taker vs risk averse**: risk taker enters on the pattern day itself;
  risk averse waits for next-day confirmation (P2 continues in expected
  direction).

---

## 4. Support and Resistance

### Construction Rules

1. Load at least **6-12 months** of data for short-term S&R; **12-18 months**
   for long-term S&R; **2+ years** for plotting major levels.
2. Identify **3 or more price action zones** at the same price level:
   - Price hesitated to move up (resistance)
   - Price hesitated to move down (support)
   - Sharp price reversals
3. Zones must be **well spaced in time** — the farther apart, the stronger.
4. Connect zones with a horizontal line.

### Key Principles

- S&R is a **zone**, not a single price point. Allow +/- 1-2% tolerance.
- More touches + more time spacing = stronger level.
- Support becomes resistance after breakdown; resistance becomes support after
  breakout (role reversal).
- **For long trades**: stoploss should be at or near support.
- **For short trades**: stoploss should be at or near resistance.
- If stoploss is more than **4% away** from S&R, the trade setup is weak —
  skip it.

---

## 5. Volume

### The Volume-Price Table

| Price Direction | Volume Direction | Interpretation |
|-----------------|-----------------|----------------|
| Increasing | Increasing | **Bullish** — smart money buying |
| Increasing | Decreasing | **Caution** — weak hands buying, possible bull trap |
| Decreasing | Increasing | **Bearish** — smart money selling |
| Decreasing | Decreasing | **Caution** — weak hands selling, possible bear trap |

### Volume Rules

- **High volume** = today's volume > **10-day average** volume.
- **Low volume** = today's volume < 10-day average volume.
- High volume indicates **institutional/smart money** participation.
- Low volume indicates **retail** participation — unreliable moves.
- When buying, ensure volume is above average — you're buying alongside
  smart money.
- When selling, ensure volume is above average — you're selling alongside
  smart money.
- **Never take a trade on low-volume days** — the move lacks conviction.

### Abnormal Volume (Engine-Specific)

Beyond the 10-day average check, compare current volume to rolling maximums:
- Near 3-month high volume = Level 1 (high)
- Near 6-month high volume = Level 2 (heavy)
- Near yearly high volume = Level 3 (extreme)

Abnormal volume on a **green candle** = institutional buying (strong buy signal).
Abnormal volume on a **red candle** = institutional selling (strong sell signal).

---

## 6. Moving Averages

### Types

- **SMA (Simple Moving Average)**: equal weight to all data points.
- **EMA (Exponential Moving Average)**: more weight to recent data.
  **Always prefer EMA** for trading — it reacts faster to price changes.

### Key Properties

- MA is a **trend-following** system.
- Works brilliantly when there is a trend.
- **Fails in sideways/range-bound markets** (generates whipsaws).
- Price above EMA = bullish outlook. Price below EMA = bearish outlook.

### Crossover System (reduces false signals in sideways markets)

| Combination | Use Case |
|-------------|----------|
| 9 EMA / 21 EMA | Short-term trades (few sessions) |
| 25 EMA / 50 EMA | Medium-term trades (few weeks) |
| 50 EMA / 100 EMA | Multi-month trades |
| 100 EMA / 200 EMA | Long-term investments (1+ year) |

- **Buy** when shorter EMA crosses above longer EMA.
- **Exit** when shorter EMA crosses below longer EMA.
- Take ALL signals — don't cherry-pick. The one big winner compensates
  for many small losses.

---

## 7. RSI (Relative Strength Index)

- **Period**: 14 (default). Shorter = more volatile; longer = smoother.
- **Oscillates**: 0 to 100.
- **Oversold**: 0-30 (look for buying opportunities).
- **Overbought**: 70-100 (look for selling opportunities).

### Critical Nuances

1. **Prolonged overbought (>70 for weeks/months)**: the stock has strong
   positive momentum. Do NOT short — look for buying opportunities instead.
   Example: Eicher Motors rallying 100% YoY.

2. **Prolonged oversold (<30 for weeks/months)**: the stock has persistent
   negative momentum. Do NOT buy — look for selling/avoiding instead.
   Example: Suzlon Energy declining -34% YoY.

3. **RSI moving away from oversold after prolonged period**: RSI crossing
   above 30 after being stuck below = strong buy signal (potential bottom).

4. **RSI moving away from overbought after prolonged period**: RSI dropping
   below 70 after being stuck above = sell/profit-booking signal.

### RSI Divergence

- **Bullish divergence**: price makes lower low, RSI makes higher low.
  Requires RSI < 40 and price difference > 2%.
- **Bearish divergence**: price makes higher high, RSI makes lower high.
  Requires RSI > 60 and price difference > 2%.

---

## 8. MACD (Moving Average Convergence Divergence)

- **MACD Line** = 12-day EMA − 26-day EMA.
- **Signal Line** = 9-day EMA of the MACD Line.
- **Histogram** = MACD Line − Signal Line.

### Interpretation

- MACD Line crossing **above** Signal Line = bullish (buy).
- MACD Line crossing **below** Signal Line = bearish (sell).
- MACD Line crossing **centerline (zero)** from below = bullish momentum.
- MACD Line crossing **centerline** from above = bearish momentum.
- **Positive MACD** = short-term EMA > long-term EMA = upward momentum.
- **Negative MACD** = short-term EMA < long-term EMA = downward momentum.
- Higher magnitude = stronger momentum.

### Limitations

- MACD is a **lagging** indicator (built on moving averages).
- Works well in trending markets, unreliable in sideways.

---

## 9. Bollinger Bands

- **Middle band** = 20-day SMA.
- **Upper band** = Middle + 2 standard deviations.
- **Lower band** = Middle − 2 standard deviations.

### Trading Rules

- Price at **upper band** = overbought → sell opportunity (expect reversion).
- Price at **lower band** = oversold → buy opportunity (expect reversion).
- Target = middle band (20-day SMA).

### Envelope Expansion

- When price trends strongly, bands expand (**envelope expansion**).
- During envelope expansion, BB signals **FAIL** — do not trade reversions.
- **BB works best in sideways markets** (opposite of MA/MACD).

### Bollinger Squeeze

- When bands contract (low bandwidth) = volatility compression.
- Squeeze often precedes a strong directional move.
- A squeeze + candlestick pattern = high-confidence setup.

---

## 10. Fibonacci Retracements

### Key Levels

- **23.6%** — shallow retracement (strong trend)
- **38.2%** — moderate retracement (healthy trend)
- **61.8%** — deep retracement (the "golden ratio")

### How to Use

1. Identify a strong move (swing low to swing high for uptrend, or
   swing high to swing low for downtrend).
2. Calculate retracement levels from the move.
3. If price retraces to a Fibonacci level AND forms a candlestick pattern
   at that level, the trade confidence is very high.
4. Fibonacci levels often coincide with S&R zones — this double
   confirmation is extremely powerful.

### Calculation

For an upmove from A to B:
- 23.6% retracement = B − (B − A) × 0.236
- 38.2% retracement = B − (B − A) × 0.382
- 61.8% retracement = B − (B − A) × 0.618

For a downmove from A to B:
- 23.6% retracement = B + (A − B) × 0.236
- 38.2% retracement = B + (A − B) × 0.382
- 61.8% retracement = B + (A − B) × 0.618

---

## 11. Dow Theory

### The 9 Tenets

1. Indices discount everything.
2. Three broad market trends exist: Primary, Secondary, Minor.
3. **Primary Trend**: lasts years — the major bull/bear market direction.
4. **Secondary Trend**: counter-trend correction lasting weeks to months.
5. **Minor Trends**: daily noise — ignore for swing trading.
6. All indices must confirm (Nifty 50, Midcap, Smallcap should agree).
7. **Volumes must confirm** the trend.
8. Sideways markets can substitute secondary trends.
9. **Closing price** is the most important price of the day.

### Market Phases

```
Accumulation → Markup → Distribution → Markdown → (repeat)
```

| Phase | Who is active | Price action |
|-------|--------------|--------------|
| **Accumulation** | Smart money (institutions) | Price bottoms, low volume, sentiment negative |
| **Markup** | Traders join | Sharp rallies, increasing volume |
| **Distribution** | Public enters, smart money exits | Price tops, high volume, sentiment euphoric |
| **Markdown** | Everyone selling | Sharp declines, panic |

### Dow Patterns

**Double Bottom/Top**:
- Price tests the same level twice, well spaced in time (2+ weeks).
- Double bottom = bullish reversal. Double top = bearish reversal.
- Triple formation = even more powerful than double.

**Range (Sideways Market)**:
- Price oscillates between support and resistance for an extended period.
- Trade within the range: buy at support, sell at resistance.
- Caused by: lack of fundamental triggers OR anticipation of big event.

**Range Breakout**:
- Stock breaks above resistance or below support after extended range.
- **True breakout** requires: (1) high volume, (2) high momentum.
- **False breakout**: low volume, weak momentum — price falls back into range.
- After breakout, minimum target = range width added to breakout point.
- Stoploss = the broken S&R level.

**Flag Formation**:
- Steep rally followed by short correction (5-15 sessions) within
  parallel lines forming a parallelogram.
- Flag = continuation pattern — price resumes rally direction.
- Correction phase has low volume (retail profit-booking);
  smart money stays invested.
- Entry: when price breaks above the flag's upper boundary.

---

## 12. Reward-to-Risk Ratio (RRR)

- **RRR** = (Target − Entry) / (Entry − Stoploss) for long trades.
- **Minimum threshold**: 1.5 for swing trades. Our engine uses 2.0
  (more conservative).
- A trade with perfect checklist alignment but RRR < 1.5 should be
  **skipped** — the risk is not worth the reward.

### RRR by Trader Type

| Trader Type | Minimum RRR |
|-------------|-------------|
| Conservative/Beginner | 2.0+ |
| Active swing trader | 1.5 |
| Aggressive trader | 1.0 |
| Scalper | 0.5-0.75 |

---

## 13. Practical Trading Process

### Part 1 — Shortlisting (daily scan)

1. Scan all stocks in your opportunity universe (e.g., Nifty 50).
2. Focus only on the **last 3-4 candles** of each chart.
3. If a recognizable candlestick pattern exists, shortlist the stock.

### Part 2 — Evaluation (15-20 min per stock)

For each shortlisted stock:

1. Assess pattern strength (flexible with minor deviations).
2. Check **prior trend** — bullish patterns need prior downtrend and
   vice versa.
3. Check **volume** — must be >= 10-day average on signal day.
4. Check **S&R** — stoploss must coincide with S&R (within 4%).
5. Check **Dow formations** — double/triple bottoms/tops, flags, ranges.
6. Establish primary and secondary trend direction.
7. Calculate **RRR** (minimum 1.5).
8. Check **RSI and MACD** — if they confirm, increase position size.

### Key Discipline Rules

- If a stock passes the checklist, take the trade and **do nothing** until
  target or stoploss is hit.
- Trail your stoploss — healthy practice.
- Deciding NOT to trade is itself a valid trading decision.
- Out of 50 stocks scanned, typically 1-2 qualify per day.

---

## 14. Timeframe Guidelines

| Trading Style | Chart Timeframe | Lookback Period | S&R Lookback |
|---------------|----------------|-----------------|--------------|
| Scalping | 1-5 min | 5 days | 2 weeks |
| Day trading | 5-15 min | 15-30 days | 1-3 months |
| Swing trading | EOD (daily) | 6-12 months | 2+ years |
| Investing | Weekly/Monthly | 2-5 years | 5+ years |

- Higher timeframe = more reliable signals.
- A bullish engulfing on a daily chart is far more reliable than on a
  5-minute chart.

---

*Last updated: 2026-08-14*
*Source: Zerodha Varsity Module 2, Chapters 1-22*
