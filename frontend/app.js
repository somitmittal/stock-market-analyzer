/**
 * Stock Market Analyzer — Indian Market (NSE/BSE)
 *
 * Renders OHLCV candlestick chart using TradingView Lightweight Charts,
 * overlays SMA lines, entry/exit markers, and price level lines.
 * Searches and auto-resolves NSE/BSE symbols.
 */

const API = "/api";

let chart = null;
let candleSeries = null;
let volumeSeries = null;
let smaSeriesMap = {};
let currentData = null;
let searchDebounce = null;
let activeInterval = "1d";

// DOM references
const symbolInput = document.getElementById("symbolInput");
const periodSelect = document.getElementById("periodSelect");
const exchangeSelect = document.getElementById("exchangeSelect");
const analyzeBtn = document.getElementById("analyzeBtn");
const chartContainer = document.getElementById("chartContainer");
const emptyState = document.getElementById("emptyState");
const loadingOverlay = document.getElementById("loadingOverlay");
const loadingSymbol = document.getElementById("loadingSymbol");
const sidebar = document.getElementById("sidebar");
const chartLegend = document.getElementById("chartLegend");
const priceDisplay = document.getElementById("priceDisplay");
const searchDropdown = document.getElementById("searchDropdown");

// ──────────────────────────────────────
// Init
// ──────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  analyzeBtn.addEventListener("click", () => runAnalysis());
  symbolInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      searchDropdown.classList.add("hidden");
      runAnalysis();
    }
    if (e.key === "Escape") searchDropdown.classList.add("hidden");
  });

  symbolInput.addEventListener("input", () => {
    clearTimeout(searchDebounce);
    const q = symbolInput.value.trim();
    if (q.length < 1) {
      searchDropdown.classList.add("hidden");
      return;
    }
    searchDebounce = setTimeout(() => searchStocks(q), 200);
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-wrapper")) {
      searchDropdown.classList.add("hidden");
    }
  });

  // Period selector re-zooms chart without re-fetching
  periodSelect.addEventListener("change", () => {
    if (currentData?.chart?.candles) {
      zoomToPeriod(currentData.chart.candles, periodSelect.value);
    }
  });

  // Quick-pick buttons
  document.querySelectorAll(".quick-pick").forEach((el) => {
    el.addEventListener("click", () => {
      symbolInput.value = el.dataset.symbol;
      runAnalysis();
    });
  });

  // Timeframe buttons (D / W / M)
  document.querySelectorAll(".tf-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.interval === activeInterval) return;
      document.querySelectorAll(".tf-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeInterval = btn.dataset.interval;
      if (symbolInput.value.trim()) runAnalysis();
    });
  });

  // Sidebar close button
  document.getElementById("sidebarClose").addEventListener("click", () => {
    sidebar.classList.add("hidden");
    if (chart) resizeChart();
  });

  // Collapsible sections
  document.querySelectorAll(".toggle-title").forEach((el) => {
    el.addEventListener("click", () => {
      const target = document.getElementById(el.dataset.target);
      if (!target) return;
      const collapsed = el.classList.toggle("collapsed");
      target.style.display = collapsed ? "none" : "";
    });
  });

  window.addEventListener("resize", () => {
    if (chart) resizeChart();
  });

  // Auto-analyze if symbol passed via query param
  const params = new URLSearchParams(window.location.search);
  const autoSymbol = params.get("symbol");
  if (autoSymbol) {
    symbolInput.value = autoSymbol;
    runAnalysis();
  }
});

// ──────────────────────────────────────
// Search / Autocomplete
// ──────────────────────────────────────
async function searchStocks(query) {
  const exchange = exchangeSelect.value;
  try {
    const res = await fetch(`${API}/search?q=${encodeURIComponent(query)}&exchange=${exchange}&limit=10`);
    if (!res.ok) return;
    const data = await res.json();
    if (!data.results?.length) {
      searchDropdown.classList.add("hidden");
      return;
    }

    searchDropdown.innerHTML = data.results
      .map(
        (r) => `
      <div class="search-result" data-symbol="${r.symbol}">
        <div>
          <span class="search-result-sym">${r.symbol}</span>
          <div class="search-result-name">${r.name}</div>
        </div>
        <span class="search-result-exchange">${exchange}</span>
      </div>`
      )
      .join("");

    searchDropdown.classList.remove("hidden");

    searchDropdown.querySelectorAll(".search-result").forEach((el) => {
      el.addEventListener("click", () => {
        symbolInput.value = el.dataset.symbol;
        searchDropdown.classList.add("hidden");
        runAnalysis();
      });
    });
  } catch {
    // silently fail search
  }
}

// ──────────────────────────────────────
// Analysis Pipeline
// ──────────────────────────────────────
async function runAnalysis(symbolOverride) {
  const rawSymbol = symbolOverride || symbolInput.value.trim();
  if (!rawSymbol) return;

  const exchange = exchangeSelect.value;

  analyzeBtn.disabled = true;
  emptyState.classList.add("hidden");
  loadingOverlay.classList.remove("hidden");
  loadingSymbol.textContent = rawSymbol.toUpperCase();
  searchDropdown.classList.add("hidden");

  try {
    const res = await fetch(
      `${API}/analyze/${encodeURIComponent(rawSymbol)}?exchange=${exchange}&interval=${activeInterval}`
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Error ${res.status}`);
    }
    const data = await res.json();
    currentData = data;

    renderChart(data);
    renderSidebar(data);

    sidebar.classList.remove("hidden");
    chartLegend.classList.remove("hidden");
    priceDisplay.classList.remove("hidden");
    setTimeout(() => { if (chart) resizeChart(); }, 50);

    const displaySymbol = data.symbol.replace(".NS", " (NSE)").replace(".BO", " (BSE)");
    document.getElementById("priceName").textContent = data.company_name;
    document.getElementById("priceValue").textContent = "₹" + formatPrice(data.current_price);
    document.title = `${displaySymbol} — Stock Analyzer`;

  } catch (err) {
    showError(err.message);
  } finally {
    loadingOverlay.classList.add("hidden");
    analyzeBtn.disabled = false;
  }
}

// ──────────────────────────────────────
// Chart Rendering
// ──────────────────────────────────────
function renderChart(data) {
  if (chart) {
    chart.remove();
    chart = null;
    smaSeriesMap = {};
  }

  const { width, height } = getChartSize();

  chart = LightweightCharts.createChart(chartContainer, {
    width,
    height,
    layout: {
      background: { type: "solid", color: "#ffffff" },
      textColor: "#555555",
      fontSize: 12,
    },
    grid: {
      vertLines: { color: "#eeeeee" },
      horzLines: { color: "#eeeeee" },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: "#999999", style: 0, width: 1 },
      horzLine: { color: "#999999", style: 0, width: 1 },
    },
    rightPriceScale: {
      borderColor: "#dddddd",
      scaleMargins: { top: 0.1, bottom: 0.25 },
    },
    timeScale: {
      borderColor: "#dddddd",
      timeVisible: false,
    },
    localization: {
      priceFormatter: (price) => "₹" + price.toFixed(2),
    },
    handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
    handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
  });

  // Candlestick series
  candleSeries = chart.addCandlestickSeries({
    upColor: "#16a34a",
    downColor: "#dc2626",
    borderUpColor: "#16a34a",
    borderDownColor: "#dc2626",
    wickUpColor: "#16a34a",
    wickDownColor: "#dc2626",
  });
  candleSeries.setData(data.chart.candles);

  // Volume series
  volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
  });
  chart.priceScale("volume").applyOptions({
    scaleMargins: { top: 0.8, bottom: 0 },
  });
  volumeSeries.setData(data.chart.volumes);

  // SMA overlays
  const smaConfig = {
    sma_20: { color: "#f5c542", lineWidth: 1 },
    sma_50: { color: "#2196F3", lineWidth: 1 },
    sma_200: { color: "#e040fb", lineWidth: 1 },
  };

  if (data.sma_lines) {
    for (const [key, cfg] of Object.entries(smaConfig)) {
      const lineData = data.sma_lines[key];
      if (!lineData || lineData.length === 0) continue;
      const series = chart.addLineSeries({
        color: cfg.color,
        lineWidth: cfg.lineWidth,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
      });
      series.setData(lineData);
      smaSeriesMap[key] = series;
    }
  }

  // Entry/exit markers — clean, short labels
  if (data.chart_markers?.length) {
    const markers = data.chart_markers
      .map((m) => ({
        time: m.time,
        position: m.position,
        color: m.confidence >= 85 ? (m.shape === "arrowUp" ? "#15803d" : "#b91c1c") : m.color,
        shape: m.shape,
        text: `${m.confidence}%`,
        size: m.confidence >= 85 ? 2 : 1,
      }))
      .sort((a, b) => a.time - b.time);
    candleSeries.setMarkers(markers);
  }

  // Show SL/TP1/TP2 from the most recent open historical signal
  const histSignals = data.signals?.historical_signals || [];
  const lastSig = histSignals.length > 0 ? histSignals[histSignals.length - 1] : null;

  if (lastSig && lastSig.type === "entry" && lastSig.stop && lastSig.tp1) {
    candleSeries.createPriceLine({
      price: lastSig.price,
      color: "#16a34a",
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: `ENTRY ₹${lastSig.price}`,
    });
    candleSeries.createPriceLine({
      price: lastSig.stop,
      color: "#dc2626",
      lineWidth: 1,
      lineStyle: LightweightCharts.LineStyle.Dotted,
      axisLabelVisible: true,
      title: `SL ₹${lastSig.stop}`,
    });
    candleSeries.createPriceLine({
      price: lastSig.tp1,
      color: "#2563eb",
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: true,
      title: `TP1 ₹${lastSig.tp1}`,
    });
    if (lastSig.tp2) {
      candleSeries.createPriceLine({
        price: lastSig.tp2,
        color: "#7c3aed",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: `TP2 ₹${lastSig.tp2}`,
      });
    }
  } else if (data.signals && data.signals.confidence >= 60) {
    const signals = data.signals;
    const action = signals.action.toLowerCase();
    if (action.includes("buy")) {
      candleSeries.createPriceLine({
        price: signals.entry.price,
        color: "#16a34a",
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: `ENTRY ₹${signals.entry.price}`,
      });
      candleSeries.createPriceLine({
        price: signals.stop_loss,
        color: "#dc2626",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dotted,
        axisLabelVisible: true,
        title: `SL ₹${signals.stop_loss}`,
      });
    }
  }

  // Zoom to the selected period instead of fitting all data
  zoomToPeriod(data.chart.candles, periodSelect.value);
}

function zoomToPeriod(candles, period) {
  if (!chart || !candles || candles.length === 0) return;

  const baseDays = {
    "1mo": 30, "3mo": 90, "6mo": 180,
    "1y": 365, "2y": 730, "5y": 1825, "all": null,
  };

  const days = baseDays[period];

  if (!days) {
    chart.timeScale().fitContent();
    return;
  }

  const lastCandle = candles[candles.length - 1];
  const fromTs = lastCandle.time - days * 86400;

  let fromIdx = 0;
  for (let i = candles.length - 1; i >= 0; i--) {
    if (candles[i].time <= fromTs) {
      fromIdx = i;
      break;
    }
  }

  chart.timeScale().setVisibleRange({
    from: candles[fromIdx].time,
    to: lastCandle.time,
  });
}

function getChartSize() {
  const rect = chartContainer.getBoundingClientRect();
  return { width: rect.width || 800, height: rect.height || 600 };
}

function resizeChart() {
  if (!chart) return;
  const { width, height } = getChartSize();
  chart.resize(width, height);
}

// ──────────────────────────────────────
// Sidebar Rendering
// ──────────────────────────────────────
function renderSidebar(data) {
  const signals = data.signals;
  const tech = data.technical;
  const fund = data.fundamental;

  // Pump & dump warning
  renderPumpDumpWarning(signals.pump_dump_risk);

  // Score trend
  renderScoreTrend(signals.score_trend);
  renderDataFreshness(data);
  renderResearch(data.research);

  // Signal banner with colored badge
  const actionEl = document.getElementById("sigAction");
  actionEl.textContent = signals.action;
  const actClass = actionClass(signals.action);
  actionEl.className = "signal-action " + actClass;

  const banner = document.getElementById("signalBanner");
  banner.className = "signal-banner " + actClass + "-banner";

  const displaySym = data.symbol.replace(".NS", "").replace(".BO", "");
  const exchLabel = data.symbol.endsWith(".NS") ? "NSE" : "BSE";
  document.getElementById("sigSub").textContent = `${displaySym} · ${exchLabel} · Composite ${signals.score_breakdown.composite}`;
  document.getElementById("sigConfidence").textContent = signals.confidence + "%";

  // Trade setup
  document.getElementById("entryPrice").textContent = "₹" + formatPrice(signals.entry.price);
  document.getElementById("targetPrice").textContent = "₹" + formatPrice(signals.exit.target_price);
  document.getElementById("stopLoss").textContent = "₹" + formatPrice(signals.stop_loss);
  document.getElementById("riskReward").textContent = signals.risk_reward_ratio + " : 1";
  document.getElementById("entryProb").textContent = signals.entry.probability + "% probability";
  document.getElementById("exitProb").textContent = signals.exit.probability + "% probability";

  // Score breakdown
  const bd = signals.score_breakdown;
  document.getElementById("scoreBreakdown").innerHTML = [
    scoreBar("Technical", bd.technical),
    scoreBar("Fundamental", bd.fundamental),
    scoreBar("Earnings", bd.earnings_proximity),
    scoreBar("News", bd.news_sentiment),
    scoreBar("Composite", bd.composite),
  ].join("");

  // Entry reasons
  document.getElementById("entryReasons").innerHTML = signals.entry.reasoning
    .map((r) => `<div class="reason-item bullish">${r}</div>`)
    .join("");

  // Exit reasons
  document.getElementById("exitReasons").innerHTML = signals.exit.reasoning
    .map((r) => `<div class="reason-item bearish">${r}</div>`)
    .join("");

  // Technical indicators
  const techGrid = document.getElementById("techGrid");
  const indicators = [
    { name: "RSI", val: tech.rsi?.value, sig: tech.rsi?.signal },
    { name: "MACD", val: tech.macd?.histogram > 0 ? "Bullish" : "Bearish", sig: tech.macd?.crossover !== "none" ? tech.macd?.crossover + " cross" : tech.macd?.trend },
    { name: "Bollinger %B", val: tech.bollinger?.pct_b?.toFixed(2), sig: tech.bollinger?.signal },
    { name: "Stochastic", val: tech.stochastic?.k?.toFixed(1), sig: tech.stochastic?.signal },
    { name: "ADX", val: tech.adx?.adx?.toFixed(1), sig: tech.adx?.trend_strength + " " + tech.adx?.direction },
    { name: "Trend", val: tech.trend?.short?.replace("_", ""), sig: tech.trend?.medium?.replace("_", "") },
    { name: "Volume", val: tech.volume_analysis?.volume_signal, sig: "OBV " + tech.volume_analysis?.obv_trend },
    { name: "MA Overall", val: tech.moving_averages?.overall?.replace(/_/g, " "), sig: tech.moving_averages?.cross || "" },
  ];
  techGrid.innerHTML = indicators
    .map(
      (i) => `
    <div class="tech-chip">
      <div class="tech-name">${i.name}</div>
      <div class="tech-val">${i.val ?? "—"}</div>
      <div class="tech-signal ${signalClass(i.sig)}">${formatSignal(i.sig)}</div>
    </div>`
    )
    .join("");

  // Fundamentals
  document.getElementById("fundScoreDisplay").innerHTML = `
    <div class="fund-big-score" style="color:${scoreColor(fund.overall_score)}">${fund.overall_score}</div>
    <div class="fund-signal-label">${fund.overall_signal.replace(/_/g, " ")}</div>`;

  const allFundSignals = [
    ...(fund.valuation?.signals || []),
    ...(fund.profitability?.signals || []),
    ...(fund.growth?.signals || []),
    ...(fund.financial_health?.signals || []),
    ...(fund.analyst_sentiment?.signals || []),
  ];
  document.getElementById("fundSignals").innerHTML = allFundSignals
    .map((s) => `<div class="fund-signal-item">${s}</div>`)
    .join("");

  // News
  const newsSection = document.getElementById("newsSection");
  if (data.news?.length) {
    newsSection.innerHTML = data.news
      .map(
        (n) => `
      <div class="news-item">
        <a href="${n.link}" target="_blank" rel="noopener">${n.title}</a>
        <div class="news-meta">${n.publisher}</div>
      </div>`
      )
      .join("");
  } else {
    newsSection.innerHTML = '<div class="fund-signal-item">No recent news</div>';
  }
}

// ──────────────────────────────────────
// Pump & Dump Warning
// ──────────────────────────────────────
function renderPumpDumpWarning(pd) {
  const section = document.getElementById("pumpDumpSection");
  if (!pd || !pd.detected) {
    section.classList.add("hidden");
    return;
  }
  section.classList.remove("hidden");

  const levelEl = document.getElementById("pdLevel");
  levelEl.textContent = pd.risk_level.toUpperCase() + " RISK";
  levelEl.className = "pd-level " + pd.risk_level;

  document.getElementById("pdReasons").innerHTML = pd.reasons
    .map((r) => `<div>&#8226; ${r}</div>`)
    .join("");
}

// ──────────────────────────────────────
// Score Trend
// ──────────────────────────────────────
function renderScoreTrend(trend) {
  if (!trend || !trend.bars || trend.bars.length === 0) return;

  const dirEl = document.getElementById("trendDirection");
  dirEl.textContent = trend.direction;
  dirEl.className = "trend-direction " + trend.direction;

  const scoreEl = document.getElementById("trendScore");
  const sc = trend.current_score;
  scoreEl.textContent = (sc > 0 ? "+" : "") + sc;
  scoreEl.className = "trend-score " + (sc > 15 ? "positive" : sc < -15 ? "negative" : "neutral");

  const badgesEl = document.getElementById("trendBadges");
  let badges = "";
  if (trend.momentum_shift) {
    badges += '<span class="trend-badge momentum-shift">Momentum Shift</span>';
  }
  if (trend.volume_surge) {
    badges += '<span class="trend-badge volume-surge">Volume Surge</span>';
  }
  badgesEl.innerHTML = badges;

  const barsEl = document.getElementById("trendBars");
  const maxAbs = Math.max(1, ...trend.bars.map((b) => Math.abs(b.score)));

  barsEl.innerHTML = trend.bars
    .map((b) => {
      const pct = Math.max(8, (Math.abs(b.score) / maxAbs) * 100);
      let cls = b.score > 10 ? "positive" : b.score < -10 ? "negative" : "neutral-bar";
      if (b.volume_signal === "surge_buy" || b.volume_signal === "high_buy") cls += " surge";
      if (b.volume_signal === "surge_sell" || b.volume_signal === "high_sell") cls += " sell-surge";
      return `<div class="trend-bar ${cls}" style="height:${pct}%" title="${b.date}: ${b.score} (${b.volume_signal})"></div>`;
    })
    .join("");
}

// ──────────────────────────────────────
// Helpers
// ──────────────────────────────────────
function scoreBar(label, value) {
  if (value == null) {
    return `
      <div class="score-row">
        <span class="score-label">${label}</span>
        <div class="score-track"></div>
        <span class="score-number">N/A</span>
      </div>`;
  }
  const color = scoreColor(value);
  return `
    <div class="score-row">
      <span class="score-label">${label}</span>
      <div class="score-track">
        <div class="score-fill" style="width:${value}%;background:${color}"></div>
      </div>
      <span class="score-number">${Math.round(value)}</span>
    </div>`;
}

function renderDataFreshness(data) {
  const container = document.getElementById("dataFreshness");
  const live = data.data_provenance?.live_snapshot || {};
  const ohlcv = data.data_provenance?.ohlcv || {};
  const liveOk = live.status === "ok";
  container.innerHTML = `
    <div class="freshness-row">
      <span>Current price</span>
      <strong class="${liveOk ? "fresh" : "stale"}">${data.current_price_source || "Unknown"}</strong>
    </div>
    <div class="freshness-row">
      <span>Live fetch</span>
      <strong>${formatDateTime(live.fetched_at)}</strong>
    </div>
    <div class="freshness-row">
      <span>Price as of</span>
      <strong>${formatDateTime(data.current_price_as_of)}</strong>
    </div>
    <div class="freshness-row">
      <span>TA candle</span>
      <strong>${formatDateTime(ohlcv.as_of)}</strong>
    </div>
    ${(data.data_warnings || []).map((warning) => `<div class="data-warning">${warning}</div>`).join("")}
  `;
}

function renderResearch(research) {
  const container = document.getElementById("researchSection");
  if (!research?.available) {
    container.innerHTML = '<div class="fund-signal-item">Structured research data unavailable.</div>';
    return;
  }

  const growth = research.growth || {};
  const cash = research.cash_quality || {};
  const valuation = research.valuation || {};
  const ownership = research.ownership || {};
  const genuineVolume = research.genuine_volume || {};
  const deterioration = research.fundamental_deterioration || {};
  const sector = research.sector_context || {};
  const guidance = research.management_guidance || {};
  const orderBook = research.order_book || {};
  const pledging = ownership.pledging || {};
  const disclosures = research.recent_disclosures || {};
  const scenarios = research.multibagger_scenarios || [];

  const metrics = [
    ["Revenue YoY", formatPct(growth.revenue_yoy_pct)],
    ["Profit YoY", formatPct(growth.profit_yoy_pct)],
    ["Operating margin", formatPct(growth.operating_margin_latest_pct)],
    ["PEG", formatNumber(valuation.peg)],
    ["CFO / profit", formatNumber(cash.cash_profit_conversion)],
    ["Promoter holding", formatPct(ownership.promoter_holding_latest_pct)],
    ["Promoter pledge", pledging.available ? "Filing evidence" : "Not found"],
    ["Sector rotation", sector.status ? formatSignal(sector.status) : "N/A"],
    ["Sector vs Nifty", formatPct(sector.relative_strength_pct)],
    ["Volume / recent avg", formatMultiple(genuineVolume.volume_vs_recent_average)],
    ["Delivery", formatPct(genuineVolume.delivery_pct)],
  ];

  container.innerHTML = `
    <div class="research-grid">
      ${metrics.map(([label, value]) => `
        <div class="research-metric">
          <span>${label}</span>
          <strong>${value}</strong>
        </div>`).join("")}
    </div>
    ${deterioration.detected ? `
      <div class="research-alert">
        <strong>Fundamental deterioration</strong>
        ${deterioration.flags.map((flag) => `<div>• ${flag}</div>`).join("")}
      </div>` : '<div class="research-ok">No measured deterioration flags.</div>'}
    <div class="scenario-title">Required CAGR scenarios</div>
    <div class="scenario-list">
      ${scenarios.map((scenario) => `
        <span>${scenario.multiple} in ${scenario.years}y: <strong>${scenario.required_cagr_pct}%</strong></span>
      `).join("")}
    </div>
    ${renderFilingEvidence("Management guidance", guidance)}
    ${renderFilingEvidence("Order book", orderBook)}
    ${renderFilingEvidence("Promoter pledging", pledging)}
    ${renderDisclosureLinks(disclosures)}
    <div class="research-note">${genuineVolume.interpretation || ""}</div>
    <div class="research-note">${sector.method || sector.note || ""}</div>
    <div class="research-note">${research.moat_evidence?.note || ""}</div>
  `;
}

function renderFilingEvidence(title, evidence) {
  if (!evidence?.available) {
    return `<div class="filing-evidence unavailable"><strong>${title}</strong><span>No extractable evidence in the filing window.</span></div>`;
  }
  const excerpt = evidence.excerpts?.[0] || "Relevant filing found.";
  const source = evidence.source || {};
  const sourceLink = source.attachment_url
    ? `<a href="${escapeHtml(source.attachment_url)}" target="_blank" rel="noopener">Open BSE filing</a>`
    : "";
  return `
    <div class="filing-evidence">
      <strong>${title}</strong>
      <span>${escapeHtml(excerpt)}</span>
      <div class="filing-source">${escapeHtml(source.date || "")} ${sourceLink}</div>
    </div>`;
}

function renderDisclosureLinks(disclosures) {
  if (!disclosures?.available) return "";
  const categories = disclosures.categories || {};
  const records = [
    ...(categories.concall || []),
    ...(categories.management_guidance || []),
    ...(categories.order_book || []),
    ...(categories.shareholding || []),
  ];
  const seen = new Set();
  const unique = records.filter((record) => {
    if (!record.id || seen.has(record.id)) return false;
    seen.add(record.id);
    return true;
  });
  return `
    <div class="disclosure-list">
      <div class="scenario-title">Official filings (${disclosures.filing_window?.from || "—"} to ${disclosures.filing_window?.to || "—"})</div>
      ${unique.length ? unique.map((record) => `
        <a href="${escapeHtml(record.attachment_url || record.company_url || "#")}" target="_blank" rel="noopener">
          ${escapeHtml(record.subject || record.headline || "BSE disclosure")}
        </a>`).join("") : '<span>No relevant filings classified.</span>'}
    </div>`;
}

function formatDateTime(value) {
  if (!value) return "Unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("en-IN");
}

function formatPct(value) {
  return value == null ? "N/A" : `${Number(value).toFixed(1)}%`;
}

function formatNumber(value) {
  return value == null ? "N/A" : Number(value).toFixed(2);
}

function formatMultiple(value) {
  return value == null ? "N/A" : `${Number(value).toFixed(2)}x`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function scoreColor(val) {
  if (val >= 70) return "#26a69a";
  if (val >= 50) return "#f5c542";
  return "#ef5350";
}

function actionClass(action) {
  const a = action.toLowerCase();
  if (a.includes("buy")) return "buy";
  if (a.includes("sell")) return "sell";
  return "hold";
}

function signalClass(signal) {
  if (!signal) return "neutral";
  const s = String(signal).toLowerCase();
  if (
    s.includes("bullish") || s.includes("oversold") || s.includes("uptrend") ||
    s.includes("rising") || s.includes("golden") || s.includes("strong_bullish") ||
    s.includes("all_bullish") || s.includes("strong bullish")
  ) return "bullish";
  if (
    s.includes("bearish") || s.includes("overbought") || s.includes("downtrend") ||
    s.includes("falling") || s.includes("death")
  ) return "bearish";
  return "neutral";
}

function formatSignal(sig) {
  if (!sig) return "";
  return String(sig).replace(/_/g, " ");
}

function formatPrice(price) {
  if (price == null) return "—";
  return Number(price).toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
}

function showError(msg) {
  const toast = document.createElement("div");
  toast.className = "error-toast";
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}
