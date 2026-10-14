/**
 * Nivesh — research, paper trading, and ₹100 mutual fund SIPs.
 */

const API = "/api";
const AUTH_TOKEN_KEY = "stock_analyzer_token";

let chart = null;
let candleSeries = null;
let volumeSeries = null;
let currentData = null;
let searchDebounce = null;
let activeInterval = "1d";
let chartExpanded = false;
let authMode = "login";
let activePortfolioId = null;
let analysisRequestId = 0;
let tradeSide = "BUY";
let tradeInputMode = "amount";
let fundInvestMode = "sip";
let selectedFundId = null;
let fundCategory = "All";
let currentView = "markets";
// Avoid re-hitting /markets (8 quotes) on every nav flip — matches backend QUOTE_TTL (60s).
const MARKETS_CLIENT_TTL_MS = 60_000;
let marketsLoadedAt = 0;
let marketsInFlight = null;

const symbolInput = document.getElementById("symbolInput");
const periodSelect = document.getElementById("periodSelect");
const exchangeSelect = document.getElementById("exchangeSelect");
const analyzeBtn = document.getElementById("analyzeBtn");
const chartContainer = document.getElementById("chartContainer");
const chartCard = document.getElementById("chartCard");
const emptyState = document.getElementById("emptyState");
const stockDashboard = document.getElementById("stockDashboard");
const loadingOverlay = document.getElementById("loadingOverlay");
const loadingSymbol = document.getElementById("loadingSymbol");
const searchDropdown = document.getElementById("searchDropdown");

document.addEventListener("DOMContentLoaded", () => {
  setupNav();
  setupAuthUI();
  setupTradeUI();
  setupFundsUI();
  setupResearchUI();
  refreshAuthUI();
  loadMarkets();

  const params = new URLSearchParams(window.location.search);
  if (params.get("view")) showView(params.get("view"));
  if (params.get("symbol")) {
    symbolInput.value = params.get("symbol");
    showView("research");
    runAnalysis();
  }
});

function setupNav() {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.view));
  });
  document.querySelectorAll("[data-goto]").forEach((btn) => {
    btn.addEventListener("click", () => showView(btn.dataset.goto));
  });
  document.getElementById("refreshMarkets")?.addEventListener("click", () => loadMarkets(true));
  document.getElementById("loginFromRail")?.addEventListener("click", () => openAuthModal("login"));
}

function showView(name) {
  currentView = name;
  document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".nav-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.view === name);
  });
  const view = document.getElementById(`view-${name}`);
  if (view) view.classList.add("active");
  if (name === "markets") loadMarkets();
  if (name === "funds") loadFunds();
  if (name === "portfolio") loadPortfolioOverview();
  if (name === "research" && chart) setTimeout(resizeChart, 50);
}

function getToken() { return localStorage.getItem(AUTH_TOKEN_KEY); }
function setToken(t) { localStorage.setItem(AUTH_TOKEN_KEY, t); }
function clearToken() { localStorage.removeItem(AUTH_TOKEN_KEY); }
function authHeaders() {
  const token = getToken();
  return token
    ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }
    : { "Content-Type": "application/json" };
}
function requireAuth(action = "continue") {
  if (getToken()) return true;
  showToast(`Login to ${action}`);
  openAuthModal("login");
  return false;
}

function setupAuthUI() {
  const modal = document.getElementById("authModal");
  const form = document.getElementById("authForm");
  document.getElementById("loginBtn").addEventListener("click", () => openAuthModal("login"));
  document.getElementById("logoutBtn").addEventListener("click", () => {
    clearToken();
    refreshAuthUI();
    loadPortfolioOverview();
    loadUserWatchlist();
  });
  document.getElementById("authModalClose").addEventListener("click", () => modal.close());
  document.getElementById("authToggleMode").addEventListener("click", () => {
    authMode = authMode === "login" ? "register" : "login";
    updateAuthModalMode();
  });
  document.getElementById("portfolioListsBtn").addEventListener("click", openPortfolioModal);
  document.getElementById("portfolioModalClose").addEventListener("click", () => document.getElementById("portfolioModal").close());
  document.getElementById("concallModalClose").addEventListener("click", () => document.getElementById("concallModal").close());
  document.getElementById("createPortfolioBtn").addEventListener("click", createPortfolio);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("authEmail").value.trim();
    const password = document.getElementById("authPassword").value;
    const name = document.getElementById("authName").value.trim();
    const errEl = document.getElementById("authError");
    errEl.classList.add("hidden");
    try {
      const endpoint = authMode === "login" ? "/auth/login" : "/auth/register";
      const body = authMode === "login" ? { email, password } : { email, password, name };
      const res = await fetch(`${API}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(formatApiError(data.detail) || "Authentication failed");
      setToken(data.token);
      modal.close();
      await refreshAuthUI();
      showToast(authMode === "register" ? "Welcome — ₹1,00,000 paper cash ready" : "Logged in", "success");
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove("hidden");
    }
  });
}

function openAuthModal(mode = "login") {
  authMode = mode;
  updateAuthModalMode();
  document.getElementById("authError").classList.add("hidden");
  document.getElementById("authModal").showModal();
}

function updateAuthModalMode() {
  const isLogin = authMode === "login";
  document.getElementById("authModalTitle").textContent = isLogin ? "Login" : "Create account";
  document.getElementById("authSubmit").textContent = isLogin ? "Login" : "Sign up";
  document.getElementById("authToggleMode").textContent = isLogin ? "Create account" : "Already have an account?";
  document.getElementById("authName").closest("label").style.display = isLogin ? "none" : "block";
}

async function refreshAuthUI() {
  const token = getToken();
  const loginBtn = document.getElementById("loginBtn");
  const logoutBtn = document.getElementById("logoutBtn");
  const listsBtn = document.getElementById("portfolioListsBtn");
  const userLabel = document.getElementById("userLabel");
  const railLogin = document.getElementById("loginFromRail");
  if (!token) {
    loginBtn.classList.remove("hidden");
    logoutBtn.classList.add("hidden");
    listsBtn.classList.add("hidden");
    userLabel.classList.add("hidden");
    railLogin.classList.remove("hidden");
    document.getElementById("railCash").textContent = "Login for ₹1L demo";
    loadUserWatchlist();
    return;
  }
  try {
    const res = await fetch(`${API}/auth/me`, { headers: authHeaders() });
    if (!res.ok) throw new Error();
    const data = await res.json();
    loginBtn.classList.add("hidden");
    logoutBtn.classList.remove("hidden");
    listsBtn.classList.remove("hidden");
    userLabel.textContent = data.user.name || data.user.email;
    userLabel.classList.remove("hidden");
    railLogin.classList.add("hidden");
    await refreshWallet();
    loadUserWatchlist();
  } catch {
    clearToken();
    refreshAuthUI();
  }
}

async function refreshWallet() {
  if (!getToken()) return;
  try {
    const res = await fetch(`${API}/wallet`, { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById("railCash").textContent = "₹" + formatPrice(data.cash_balance);
  } catch { /* ignore */ }
}

function setupResearchUI() {
  analyzeBtn.addEventListener("click", () => {
    showView("research");
    runAnalysis();
  });
  symbolInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { searchDropdown.classList.add("hidden"); showView("research"); runAnalysis(); }
    if (e.key === "Escape") searchDropdown.classList.add("hidden");
  });
  symbolInput.addEventListener("input", () => {
    clearTimeout(searchDebounce);
    const q = symbolInput.value.trim();
    if (!q) { searchDropdown.classList.add("hidden"); return; }
    searchDebounce = setTimeout(() => searchStocks(q), 200);
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-wrapper")) searchDropdown.classList.add("hidden");
  });
  periodSelect.addEventListener("change", () => {
    if (currentData?.chart?.candles) zoomToPeriod(currentData.chart.candles, periodSelect.value);
  });
  document.querySelectorAll(".quick-pick").forEach((el) => {
    el.addEventListener("click", () => {
      symbolInput.value = el.dataset.symbol;
      showView("research");
      runAnalysis();
    });
  });
  document.querySelectorAll(".tf-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.interval === activeInterval) return;
      document.querySelectorAll(".tf-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeInterval = btn.dataset.interval;
      if (symbolInput.value.trim()) runAnalysis();
    });
  });
  document.getElementById("chartExpandBtn").addEventListener("click", toggleChartExpand);
  window.addEventListener("resize", () => { if (chart) resizeChart(); });
  document.getElementById("tradeBuyBtn").addEventListener("click", () => openTrade("BUY"));
  document.getElementById("tradeSellBtn").addEventListener("click", () => openTrade("SELL"));
  document.getElementById("addWatchBtn").addEventListener("click", addCurrentToWatchlist);
}

async function searchStocks(q) {
  try {
    const res = await fetch(`${API}/search?q=${encodeURIComponent(q)}&exchange=${exchangeSelect.value}`);
    const data = await res.json();
    const results = data.results || [];
    if (!results.length) { searchDropdown.classList.add("hidden"); return; }
    searchDropdown.innerHTML = results.map((r) => `
      <button type="button" class="search-item" data-symbol="${escapeHtml(r.symbol)}">
        <strong>${escapeHtml(r.symbol)}</strong>
        <span class="filing-meta">${escapeHtml(r.name || "")}</span>
      </button>`).join("");
    searchDropdown.classList.remove("hidden");
    searchDropdown.querySelectorAll(".search-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        symbolInput.value = btn.dataset.symbol;
        searchDropdown.classList.add("hidden");
        showView("research");
        runAnalysis();
      });
    });
  } catch { searchDropdown.classList.add("hidden"); }
}

async function runAnalysis(symbolOverride) {
  const rawSymbol = symbolOverride || symbolInput.value.trim();
  if (!rawSymbol) return;
  const requestId = ++analysisRequestId;
  const requestedSymbol = normalizeSymbol(rawSymbol);
  analyzeBtn.disabled = true;
  loadingOverlay.classList.remove("hidden");
  loadingSymbol.textContent = requestedSymbol;
  searchDropdown.classList.add("hidden");
  try {
    const res = await fetch(
      `${API}/analyze/${encodeURIComponent(rawSymbol)}?exchange=${exchangeSelect.value}&interval=${activeInterval}&_=${requestId}`,
      { cache: "no-store" }
    );
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(formatApiError(err.detail) || `Error ${res.status}`);
    }
    const data = await res.json();
    if (requestId !== analysisRequestId) return;
    if (normalizeSymbol(data.symbol) !== requestedSymbol) {
      throw new Error(`Received analysis for ${data.symbol}, expected ${requestedSymbol}.`);
    }
    currentData = data;
    emptyState.classList.add("hidden");
    stockDashboard.classList.remove("hidden");
    renderDashboard(currentData);
    renderChart(currentData);
    setTimeout(() => { if (chart) resizeChart(); }, 50);
    document.title = `${currentData.company_name} — Nivesh`;
  } catch (err) {
    showToast(err.message);
  } finally {
    loadingOverlay.classList.add("hidden");
    analyzeBtn.disabled = false;
  }
}

function normalizeSymbol(value) {
  return String(value || "").trim().toUpperCase().replace(/\.(NS|BO)$/i, "");
}

const VERDICT_SECTION_ORDER = [
  ["business", "1. Business"],
  ["quarterly_results", "2. Latest quarterly results"],
  ["balance_sheet", "3. Balance sheet & cash flows"],
  ["valuation", "4. Valuation vs peers & forward FY"],
  ["price_action", "5. Price action"],
  ["technicals", "6. Technicals"],
  ["insider_buying", "7. Ownership"],
  ["news_and_concalls", "8. News & concalls"],
  ["macro_risks", "9. Macro risks"],
];

function renderDashboard(data) {
  const verdict = data.verdict || {};
  const displaySym = data.symbol.replace(".NS", "").replace(".BO", "");
  const exch = data.symbol.endsWith(".BO") ? "BSE" : "NSE";

  document.getElementById("heroName").textContent = data.company_name;
  document.getElementById("heroMeta").textContent = `${displaySym} · ${exch}`;
  document.getElementById("heroPrice").textContent = "₹" + formatPrice(data.current_price);

  const recommendation = verdict.recommendation || "Research";
  const sigEl = document.getElementById("heroSignal");
  sigEl.textContent = `AI view: ${recommendation}`;
  sigEl.className = "signal-pill " + actionClass(recommendation);

  const banner = document.getElementById("verdictBanner");
  if (verdict.recommendation) {
    banner.classList.remove("hidden");
    banner.className = `verdict-banner ${actionClass(verdict.recommendation)}`;
    const sourceBadge = verdict.analysis_source === "gemini"
      ? '<span class="verdict-source">Gemini AI</span>'
      : "";
    banner.innerHTML = `
      <div class="verdict-banner-main">
        <span class="verdict-label">AI research view</span>
        <strong class="verdict-action">${escapeHtml(verdict.recommendation)}</strong>
        <span class="verdict-confidence">${escapeHtml(verdict.confidence || "")} confidence</span>
        ${sourceBadge}
      </div>
      <p class="verdict-rationale">${escapeHtml(verdict.rationale || "")}</p>
      <p class="form-hint" style="margin-top:8px">This is research context — not a brokerage recommendation. Use Buy/Sell for paper trades.</p>`;
  } else {
    banner.classList.add("hidden");
  }

  renderDataQuality(data);
  renderVerdictSections(verdict);
}

function renderDataQuality(data) {
  const box = document.getElementById("dataQuality");
  const summary = document.getElementById("dataQualitySummary");
  const list = document.getElementById("dataQualityList");
  const warnings = data.data_warnings || [];
  if (!warnings.length) { box.classList.add("hidden"); return; }
  const blocking = warnings.filter((w) => /rate limit|unavailable|errors for/i.test(w));
  box.classList.remove("hidden");
  box.classList.toggle("has-gaps", blocking.length > 0);
  summary.textContent = blocking.length
    ? `Incomplete data — ${blocking.length} issue${blocking.length === 1 ? "" : "s"}`
    : "Data coverage";
  list.innerHTML = warnings
    .map((w) => `<li class="${/rate limit|unavailable|errors for/i.test(w) ? "gap" : ""}">${escapeHtml(w)}</li>`)
    .join("");
}

function renderVerdictSections(verdict) {
  const container = document.getElementById("verdictSections");
  const sections = verdict.sections || {};
  container.innerHTML = VERDICT_SECTION_ORDER.map(([key, label]) => {
    const section = sections[key] || {};
    return renderVerdictSectionCard(label, section);
  }).join("");
}

function renderVerdictSectionCard(label, section) {
  const assessment = section.assessment ? formatAssessment(section.assessment) : "—";
  const summary = section.summary ? `<p class="section-summary">${escapeHtml(section.summary)}</p>` : "";
  const positives = (section.positives || []).length
    ? `<div class="pn-col positives"><h4>Positives</h4><ul>${section.positives.map((p) => `<li>${escapeHtml(p)}</li>`).join("")}</ul></div>`
    : `<div class="pn-col positives"><h4>Positives</h4><p class="form-hint">None flagged.</p></div>`;
  const negatives = (section.negatives || []).length
    ? `<div class="pn-col negatives"><h4>Risks</h4><ul>${section.negatives.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul></div>`
    : `<div class="pn-col negatives"><h4>Risks</h4><p class="form-hint">None flagged.</p></div>`;
  return `
    <article class="verdict-section card">
      <div class="verdict-section-header">
        <h3>${escapeHtml(label)}</h3>
        <span class="assessment-badge ${assessmentClass(section.assessment)}">${escapeHtml(assessment)}</span>
      </div>
      ${summary}
      <div class="pn-grid">${positives}${negatives}</div>
    </article>`;
}

// ── Markets / watchlist ──────────────────────────────
async function loadMarkets(force = false) {
  const el = document.getElementById("marketWatch");
  const fresh =
    !force &&
    marketsLoadedAt > 0 &&
    Date.now() - marketsLoadedAt < MARKETS_CLIENT_TTL_MS &&
    el.querySelector(".watch-row");
  if (fresh) {
    loadUserWatchlist();
    return;
  }
  if (marketsInFlight) {
    await marketsInFlight;
    return;
  }

  el.textContent = "Loading quotes…";
  marketsInFlight = (async () => {
    try {
      const res = await fetch(`${API}/markets`);
      const data = await res.json();
      el.innerHTML = renderWatchRows(data.watch || [], false);
      bindWatchRows(el);
      marketsLoadedAt = Date.now();
    } catch (err) {
      el.innerHTML = `<p class="form-error">${escapeHtml(err.message)}</p>`;
    } finally {
      marketsInFlight = null;
    }
  })();
  await marketsInFlight;
  loadUserWatchlist();
}

async function loadUserWatchlist() {
  const el = document.getElementById("userWatchlist");
  if (!getToken()) {
    el.innerHTML = '<p class="form-hint">Login to save a personal watchlist.</p>';
    return;
  }
  try {
    const res = await fetch(`${API}/watchlist`, { headers: authHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || "Failed");
    const items = data.items || [];
    el.innerHTML = items.length
      ? renderWatchRows(items, true)
      : '<p class="form-hint">Empty — open a stock and tap + Watchlist.</p>';
    bindWatchRows(el);
  } catch (err) {
    el.innerHTML = `<p class="form-error">${escapeHtml(err.message)}</p>`;
  }
}

function renderWatchRows(items, showRemove) {
  return items.map((item) => {
    const chg = item.change_pct;
    const chgClass = chg == null ? "" : chg >= 0 ? "chg-up" : "chg-down";
    const chgText = chg == null ? "—" : `${chg >= 0 ? "+" : ""}${Number(chg).toFixed(2)}%`;
    return `
      <div class="watch-row" data-symbol="${escapeHtml(item.symbol)}" data-exchange="${escapeHtml(item.exchange || "NSE")}">
        <div>
          <strong>${escapeHtml(item.symbol)}</strong>
          <span class="muted">${escapeHtml(item.exchange || "NSE")}</span>
        </div>
        <div class="px">${item.ltp != null ? "₹" + formatPrice(item.ltp) : "—"}</div>
        <div class="${chgClass}">${chgText}${showRemove ? ` <button type="button" class="btn-ghost btn-sm" data-remove-watch="${escapeHtml(item.symbol)}">×</button>` : ""}</div>
      </div>`;
  }).join("");
}

function bindWatchRows(container) {
  container.querySelectorAll(".watch-row").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (e.target.closest("[data-remove-watch]")) return;
      symbolInput.value = row.dataset.symbol;
      exchangeSelect.value = row.dataset.exchange || "NSE";
      showView("research");
      runAnalysis();
    });
  });
  container.querySelectorAll("[data-remove-watch]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await fetch(`${API}/watchlist/${encodeURIComponent(btn.dataset.removeWatch)}?exchange=NSE`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      loadUserWatchlist();
    });
  });
}

async function addCurrentToWatchlist() {
  if (!requireAuth("save watchlist")) return;
  const stock = getStockForPortfolio();
  if (!stock) return showToast("Open a stock first");
  const res = await fetch(`${API}/watchlist`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(stock),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return showToast(formatApiError(data.detail) || "Could not add");
  showToast(`Added ${stock.symbol} to watchlist`, "success");
  loadUserWatchlist();
}

// ── Trade ticket (Zerodha amount/qty) ─────────────────
function setupTradeUI() {
  document.getElementById("tradeModalClose").addEventListener("click", () => document.getElementById("tradeModal").close());
  document.getElementById("tradeForm").addEventListener("submit", submitTrade);
  document.querySelectorAll("#tradeInputMode .toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      tradeInputMode = btn.dataset.mode;
      document.querySelectorAll("#tradeInputMode .toggle").forEach((b) => b.classList.toggle("active", b === btn));
      document.getElementById("tradeAmountLabel").classList.toggle("hidden", tradeInputMode !== "amount");
      document.getElementById("tradeQtyLabel").classList.toggle("hidden", tradeInputMode !== "qty");
      updateTradePreview();
    });
  });
  document.getElementById("tradeAmount").addEventListener("input", updateTradePreview);
  document.getElementById("tradeQty").addEventListener("input", updateTradePreview);
}

function openTrade(side) {
  if (!requireAuth("place paper trades")) return;
  if (!currentData) return showToast("Open a stock first");
  tradeSide = side;
  document.getElementById("tradeTitle").textContent = `${side === "BUY" ? "Buy" : "Sell"} ${normalizeSymbol(currentData.symbol)}`;
  document.getElementById("tradeMeta").textContent =
    `${currentData.company_name} · LTP ₹${formatPrice(currentData.current_price)} · paper market order`;
  document.getElementById("tradeError").classList.add("hidden");
  document.getElementById("tradeSubmit").textContent = side === "BUY" ? "Buy with paper cash" : "Sell from holdings";
  document.getElementById("tradeSubmit").className = side === "BUY" ? "btn-buy" : "btn-sell";
  updateTradePreview();
  document.getElementById("tradeModal").showModal();
}

function updateTradePreview() {
  if (!currentData) return;
  const price = Number(currentData.current_price) || 0;
  let qty = 0;
  let amount = 0;
  if (tradeInputMode === "amount") {
    amount = Number(document.getElementById("tradeAmount").value) || 0;
    qty = price ? amount / price : 0;
  } else {
    qty = Number(document.getElementById("tradeQty").value) || 0;
    amount = qty * price;
  }
  document.getElementById("tradePreview").textContent =
    `≈ ${qty.toFixed(4)} shares · ₹${formatPrice(amount)} at ₹${formatPrice(price)}`;
}

async function submitTrade(e) {
  e.preventDefault();
  const err = document.getElementById("tradeError");
  err.classList.add("hidden");
  const stock = getStockForPortfolio();
  const body = {
    symbol: stock.symbol,
    exchange: stock.exchange,
    side: tradeSide,
  };
  if (tradeInputMode === "amount") body.amount = Number(document.getElementById("tradeAmount").value);
  else body.quantity = Number(document.getElementById("tradeQty").value);
  try {
    const res = await fetch(`${API}/trade/order`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(formatApiError(data.detail) || "Order failed");
    document.getElementById("tradeModal").close();
    showToast(`${data.side} filled · ${data.quantity} @ ₹${formatPrice(data.price)}`, "success");
    await refreshWallet();
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
}

// ── Mutual funds ─────────────────────────────────────
function setupFundsUI() {
  document.getElementById("fundSearch").addEventListener("input", () => loadFunds());
  document.getElementById("onlyHundred").addEventListener("change", () => loadFunds());
  document.getElementById("fundModalClose").addEventListener("click", () => document.getElementById("fundModal").close());
  document.getElementById("fundForm").addEventListener("submit", submitFundInvest);
  document.querySelectorAll("#fundMode .toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      fundInvestMode = btn.dataset.mode;
      document.querySelectorAll("#fundMode .toggle").forEach((b) => b.classList.toggle("active", b === btn));
      document.getElementById("fundFreqLabel").classList.toggle("hidden", fundInvestMode !== "sip");
    });
  });
}

async function loadFunds() {
  const q = document.getElementById("fundSearch").value.trim();
  const only100 = document.getElementById("onlyHundred").checked;
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (fundCategory && fundCategory !== "All") params.set("category", fundCategory);
  if (only100) params.set("max_min_sip", "100");
  const grid = document.getElementById("fundsGrid");
  grid.textContent = "Loading funds…";
  try {
    const res = await fetch(`${API}/funds?${params}`);
    const data = await res.json();
    const cats = ["All", ...(data.categories || [])];
    document.getElementById("fundCategories").innerHTML = cats.map((c) =>
      `<button type="button" class="chip ${c === fundCategory ? "active" : ""}" data-cat="${escapeHtml(c)}">${escapeHtml(c)}</button>`
    ).join("");
    document.querySelectorAll("#fundCategories .chip").forEach((btn) => {
      btn.addEventListener("click", () => { fundCategory = btn.dataset.cat; loadFunds(); });
    });
    grid.innerHTML = (data.funds || []).map(renderFundCard).join("")
      || '<p class="form-hint">No funds match.</p>';
    grid.querySelectorAll("[data-invest]").forEach((btn) => {
      btn.addEventListener("click", () => openFundInvest(btn.dataset.invest, btn.dataset.min));
    });
  } catch (err) {
    grid.innerHTML = `<p class="form-error">${escapeHtml(err.message)}</p>`;
  }
}

function renderFundCard(fund) {
  return `
    <article class="fund-card">
      <div class="fund-meta">
        <span class="tag">${escapeHtml(fund.category)}</span>
        <span class="tag">${escapeHtml(fund.risk)}</span>
        <span class="tag score">Score ${fund.score}</span>
      </div>
      <h3>${escapeHtml(fund.name)}</h3>
      <p class="form-hint">${escapeHtml(fund.tagline)}</p>
      <div class="fund-stats">
        <div><span>1Y</span><strong>${formatPct(fund.returns_1y)}</strong></div>
        <div><span>3Y</span><strong>${formatPct(fund.returns_3y)}</strong></div>
        <div><span>Min SIP</span><strong>₹${fund.min_sip}</strong></div>
      </div>
      <div class="actions">
        <button type="button" class="btn-primary btn-sm" data-invest="${escapeHtml(fund.id)}" data-min="${fund.min_sip}">SIP / Invest</button>
      </div>
    </article>`;
}

function openFundInvest(fundId, minSip) {
  if (!requireAuth("invest in funds")) return;
  selectedFundId = fundId;
  document.getElementById("fundModalTitle").textContent = "Invest in fund";
  document.getElementById("fundModalMeta").textContent = `Fund ID: ${fundId} · min SIP ₹${minSip}`;
  document.getElementById("fundAmount").value = Math.max(100, Number(minSip) || 100);
  document.getElementById("fundAmount").min = minSip || 100;
  document.getElementById("fundError").classList.add("hidden");
  document.getElementById("fundModal").showModal();
}

async function submitFundInvest(e) {
  e.preventDefault();
  const err = document.getElementById("fundError");
  err.classList.add("hidden");
  const amount = Number(document.getElementById("fundAmount").value);
  try {
    let res;
    if (fundInvestMode === "sip") {
      res = await fetch(`${API}/funds/sip`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({
          fund_id: selectedFundId,
          amount,
          frequency: document.getElementById("fundFrequency").value,
          invest_now: true,
        }),
      });
    } else {
      res = await fetch(`${API}/funds/buy`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ fund_id: selectedFundId, amount }),
      });
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(formatApiError(data.detail) || "Investment failed");
    document.getElementById("fundModal").close();
    showToast(fundInvestMode === "sip" ? "SIP started · first installment invested" : "One-time investment done", "success");
    await refreshWallet();
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
}

// ── Portfolio overview ───────────────────────────────
async function loadPortfolioOverview() {
  const root = document.getElementById("portfolioRoot");
  if (!getToken()) {
    root.innerHTML = '<p class="form-hint">Login to see stocks, mutual funds, and SIPs.</p>';
    return;
  }
  root.innerHTML = '<div class="loader-inline"></div>';
  try {
    const res = await fetch(`${API}/portfolio/overview`, { headers: authHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || "Failed");
    const s = data.summary || {};
    root.innerHTML = `
      <div class="stat-strip">
        <div class="stat"><span>Total value</span><strong>₹${formatPrice(s.total_value)}</strong></div>
        <div class="stat"><span>Cash</span><strong>₹${formatPrice(s.cash)}</strong></div>
        <div class="stat"><span>Stocks</span><strong>₹${formatPrice(s.stocks_value)}</strong></div>
        <div class="stat"><span>Mutual funds</span><strong>₹${formatPrice(s.mf_value)}</strong></div>
      </div>
      <div class="card">
        <div class="card-header"><h2>Stock holdings</h2></div>
        ${renderPositionsTable(data.stocks || [])}
      </div>
      <div class="card">
        <div class="card-header"><h2>Mutual fund holdings</h2></div>
        ${renderMfTable(data.mutual_funds || [])}
      </div>
      <div class="card">
        <div class="card-header"><h2>Active SIPs</h2></div>
        ${renderSips(data.sips || [])}
      </div>`;
    root.querySelectorAll("[data-pause-sip]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await fetch(`${API}/funds/sips/${btn.dataset.pauseSip}/pause`, {
          method: "POST",
          headers: authHeaders(),
        });
        loadPortfolioOverview();
      });
    });
    root.querySelectorAll("[data-open-symbol]").forEach((btn) => {
      btn.addEventListener("click", () => {
        symbolInput.value = btn.dataset.openSymbol;
        showView("research");
        runAnalysis();
      });
    });
  } catch (err) {
    root.innerHTML = `<p class="form-error">${escapeHtml(err.message)}</p>`;
  }
}

function renderPositionsTable(rows) {
  if (!rows.length) return '<p class="form-hint">No stock positions yet. Buy from Research.</p>';
  return `<table class="hold-table">
    <thead><tr><th>Symbol</th><th>Qty</th><th>Avg</th><th>LTP</th><th>P&L</th></tr></thead>
    <tbody>${rows.map((r) => `
      <tr>
        <td><button type="button" class="holding-link" data-open-symbol="${escapeHtml(r.symbol)}"><strong>${escapeHtml(r.symbol)}</strong></button></td>
        <td>${Number(r.quantity).toFixed(4)}</td>
        <td>₹${formatPrice(r.avg_price)}</td>
        <td>₹${formatPrice(r.ltp)}</td>
        <td class="${r.pnl >= 0 ? "chg-up" : "chg-down"}">₹${formatPrice(r.pnl)} (${formatPct(r.pnl_pct)})</td>
      </tr>`).join("")}</tbody></table>`;
}

function renderMfTable(rows) {
  if (!rows.length) return '<p class="form-hint">No mutual funds yet. Start a ₹100 SIP.</p>';
  return `<table class="hold-table">
    <thead><tr><th>Fund</th><th>Units</th><th>Invested</th><th>Value</th><th>P&L</th></tr></thead>
    <tbody>${rows.map((r) => `
      <tr>
        <td><strong>${escapeHtml(r.fund?.name || r.fund_id)}</strong></td>
        <td>${Number(r.units).toFixed(4)}</td>
        <td>₹${formatPrice(r.invested_amount)}</td>
        <td>₹${formatPrice(r.value)}</td>
        <td class="${r.pnl >= 0 ? "chg-up" : "chg-down"}">₹${formatPrice(r.pnl)}</td>
      </tr>`).join("")}</tbody></table>`;
}

function renderSips(rows) {
  if (!rows.length) return '<p class="form-hint">No active SIPs.</p>';
  return rows.map((s) => `
    <div class="holding-row">
      <div>
        <strong>${escapeHtml(s.fund?.name || s.fund_id)}</strong>
        <span class="filing-meta">₹${formatPrice(s.amount)} · ${escapeHtml(s.frequency)} · next ${escapeHtml(s.next_date)} · ${escapeHtml(s.status)}</span>
      </div>
      ${s.status === "active" ? `<button type="button" class="btn-ghost btn-sm" data-pause-sip="${s.id}">Pause</button>` : ""}
    </div>`).join("");
}

// ── Legacy research portfolios modal ─────────────────
async function openPortfolioModal() {
  if (!getToken()) { openAuthModal("login"); return; }
  document.getElementById("portfolioModal").showModal();
  await loadPortfolios();
}

async function loadPortfolios() {
  const overview = document.getElementById("portfolioOverview");
  const summaryEl = document.getElementById("portfolioSummary");
  overview.innerHTML = '<div class="loader-inline"></div>';
  summaryEl.classList.add("hidden");
  try {
    const res = await fetch(`${API}/portfolios?include_holdings=true`, { headers: authHeaders() });
    const data = await res.json();
    if (!res.ok) throw new Error(formatApiError(data.detail) || "Failed to load");
    const portfolios = data.portfolios || [];
    if (!portfolios.length) {
      activePortfolioId = null;
      overview.innerHTML = '<p class="form-hint">No lists yet. Create one above.</p>';
      return;
    }
    if (!activePortfolioId || !portfolios.some((p) => p.id === activePortfolioId)) {
      activePortfolioId = portfolios[0].id;
    }
    const summary = data.summary || {};
    summaryEl.textContent = `${summary.portfolio_count || portfolios.length} lists · ${summary.holding_count || 0} stocks`;
    summaryEl.classList.remove("hidden");
    overview.innerHTML = portfolios.map(renderPortfolioCard).join("");
    bindPortfolioCardEvents(overview);
  } catch (err) {
    overview.innerHTML = `<p class="form-error">${escapeHtml(err.message)}</p>`;
  }
}

function renderPortfolioCard(portfolio) {
  const holdings = portfolio.holdings || [];
  const holdingsHtml = holdings.length
    ? holdings.map((holding) => `
        <div class="holding-row">
          <button type="button" class="holding-link" data-symbol="${escapeHtml(holding.symbol)}" data-exchange="${escapeHtml(holding.exchange)}">
            <strong>${escapeHtml(holding.symbol)}</strong>
            <span class="filing-meta">${escapeHtml(holding.exchange)}</span>
          </button>
          <button class="btn-ghost btn-sm" data-action="remove" data-portfolio-id="${portfolio.id}" data-symbol="${escapeHtml(holding.symbol)}">Remove</button>
        </div>`).join("")
    : '<p class="form-hint">No holdings yet.</p>';
  return `
    <section class="portfolio-card" data-id="${portfolio.id}">
      <div class="portfolio-card-header">
        <div>
          <h4>${escapeHtml(portfolio.name)}</h4>
          <span class="filing-meta">${holdings.length} stock${holdings.length === 1 ? "" : "s"}</span>
        </div>
        <button type="button" class="btn-primary btn-sm" data-action="add-current" data-portfolio-id="${portfolio.id}">Add current</button>
      </div>
      <div class="portfolio-holdings">${holdingsHtml}</div>
    </section>`;
}

function bindPortfolioCardEvents(container) {
  container.querySelectorAll("[data-action='add-current']").forEach((btn) => {
    btn.addEventListener("click", () => {
      activePortfolioId = Number(btn.dataset.portfolioId);
      addCurrentStockToPortfolio();
    });
  });
  container.querySelectorAll("[data-action='remove']").forEach((btn) => {
    btn.addEventListener("click", () => removeHolding(Number(btn.dataset.portfolioId), btn.dataset.symbol));
  });
  container.querySelectorAll(".holding-link").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.getElementById("portfolioModal").close();
      symbolInput.value = btn.dataset.symbol;
      exchangeSelect.value = btn.dataset.exchange || "NSE";
      showView("research");
      runAnalysis(btn.dataset.symbol);
    });
  });
}

async function createPortfolio() {
  const name = document.getElementById("newPortfolioName").value.trim();
  if (!name) return;
  const res = await fetch(`${API}/portfolios`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ name }),
  });
  if (res.ok) {
    const data = await res.json();
    document.getElementById("newPortfolioName").value = "";
    activePortfolioId = data.id;
    await loadPortfolios();
  }
}

function getStockForPortfolio() {
  if (currentData?.symbol) {
    const sym = currentData.symbol.toUpperCase();
    return {
      symbol: sym.replace(".NS", "").replace(".BO", ""),
      exchange: sym.endsWith(".BO") ? "BSE" : "NSE",
    };
  }
  const raw = symbolInput.value.trim();
  if (!raw) return null;
  const upper = raw.toUpperCase();
  if (upper.endsWith(".NS")) return { symbol: upper.replace(".NS", ""), exchange: "NSE" };
  if (upper.endsWith(".BO")) return { symbol: upper.replace(".BO", ""), exchange: "BSE" };
  return { symbol: upper, exchange: exchangeSelect.value };
}

async function addCurrentStockToPortfolio(portfolioId = activePortfolioId) {
  if (!portfolioId) return showToast("Create a list first");
  const stock = getStockForPortfolio();
  if (!stock) return showToast("Open a stock first");
  const res = await fetch(`${API}/portfolios/${portfolioId}/holdings`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(stock),
  });
  if (res.ok) {
    showToast(`Added ${stock.symbol}`, "success");
    await loadPortfolios();
  } else {
    const data = await res.json().catch(() => ({}));
    showToast(formatApiError(data.detail) || "Could not add");
  }
}

async function removeHolding(portfolioId, symbol) {
  await fetch(`${API}/portfolios/${portfolioId}/holdings/${encodeURIComponent(symbol)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  await loadPortfolios();
}

// ── Chart ────────────────────────────────────────────
function toggleChartExpand() {
  chartExpanded = !chartExpanded;
  chartCard.classList.toggle("expanded", chartExpanded);
  document.getElementById("chartExpandBtn").textContent = chartExpanded ? "Collapse" : "Expand";
  setTimeout(() => { if (chart) resizeChart(); }, 260);
}

function renderChart(data) {
  if (chart) { chart.remove(); chart = null; }
  const { width, height } = getChartSize();
  chart = LightweightCharts.createChart(chartContainer, {
    width, height,
    layout: { background: { type: "solid", color: "#fffdf8" }, textColor: "#5f6f68" },
    grid: { vertLines: { color: "#eee8da" }, horzLines: { color: "#eee8da" } },
    rightPriceScale: { borderColor: "#d9d0be", scaleMargins: { top: 0.1, bottom: 0.22 } },
    timeScale: { borderColor: "#d9d0be" },
    localization: { priceFormatter: (p) => "₹" + p.toFixed(2) },
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: "#0f8a62", downColor: "#c2410c",
    borderUpColor: "#0f8a62", borderDownColor: "#c2410c",
    wickUpColor: "#0f8a62", wickDownColor: "#c2410c",
  });
  candleSeries.setData(data.chart.candles);
  volumeSeries = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "vol" });
  chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  volumeSeries.setData(data.chart.volumes);
  const smaCfg = { sma_20: "#b45309", sma_50: "#0f766e", sma_200: "#7c3aed" };
  if (data.sma_lines) {
    for (const [key, color] of Object.entries(smaCfg)) {
      if (!data.sma_lines[key]?.length) continue;
      const s = chart.addLineSeries({
        color, lineWidth: 1, crosshairMarkerVisible: false,
        lastValueVisible: false, priceLineVisible: false,
      });
      s.setData(data.sma_lines[key]);
    }
  }
  if (data.chart_markers?.length) {
    candleSeries.setMarkers(data.chart_markers.map((m) => ({
      time: m.time, position: m.position, color: m.color,
      shape: m.shape, text: `${m.confidence}%`, size: m.confidence >= 85 ? 2 : 1,
    })).sort((a, b) => a.time - b.time));
  }
  document.getElementById("chartLegend").classList.remove("hidden");
  zoomToPeriod(data.chart.candles, periodSelect.value);
}

function zoomToPeriod(candles, period) {
  if (!chart || !candles?.length) return;
  const days = { "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825, all: null }[period];
  if (!days) { chart.timeScale().fitContent(); return; }
  const last = candles[candles.length - 1];
  const fromTs = last.time - days * 86400;
  let fromIdx = 0;
  for (let i = candles.length - 1; i >= 0; i--) {
    if (candles[i].time <= fromTs) { fromIdx = i; break; }
  }
  chart.timeScale().setVisibleRange({ from: candles[fromIdx].time, to: last.time });
}

function getChartSize() {
  const rect = chartContainer.getBoundingClientRect();
  return { width: rect.width || 800, height: rect.height || 300 };
}
function resizeChart() {
  if (!chart) return;
  const { width, height } = getChartSize();
  chart.resize(width, height);
}

// ── Helpers ──────────────────────────────────────────
function formatPct(v) { return v == null ? "—" : `${Number(v).toFixed(1)}%`; }
function formatPrice(p) {
  return p == null ? "—" : Number(p).toLocaleString("en-IN", { maximumFractionDigits: 2 });
}
function formatAssessment(value) { return String(value || "").replaceAll("_", " "); }
function assessmentClass(value) {
  const v = String(value || "").toLowerCase();
  if (["strong", "phenomenal", "clean", "bullish", "positive", "low_risk", "attractive", "buy_dip", "fair", "growth_premium"].includes(v)) return "good";
  if (["weak", "risky", "bearish", "negative", "high_risk", "expensive", "trim"].includes(v)) return "bad";
  return "neutral";
}
function escapeHtml(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
function actionClass(a) {
  const x = String(a || "").toLowerCase();
  if (x.includes("buy")) return "buy";
  if (x.includes("sell")) return "sell";
  return "hold";
}
function formatApiError(detail) {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
  return String(detail);
}
function showToast(msg, type = "error") {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  t.style.background = type === "success" ? "#0f8a62" : "#0c1f1a";
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => t.classList.add("hidden"), 4000);
}
function showError(msg) { showToast(msg, "error"); }
function updateAddStockButtonState() { /* kept for compatibility */ }
