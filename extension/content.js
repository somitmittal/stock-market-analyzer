/**
 * Content script for TradingView chart overlay.
 * Injects entry/exit signal markers and a floating analysis panel.
 */

(() => {
  let panelEl = null;
  let currentData = null;

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === "overlaySignals" && msg.data) {
      currentData = msg.data;
      injectPanel(msg.data);
      injectChartMarkers(msg.data);
      sendResponse({ success: true });
    }
  });

  function injectPanel(data) {
    if (panelEl) panelEl.remove();

    const signals = data.signals;
    const actionColor = getActionColor(signals.action);

    panelEl = document.createElement("div");
    panelEl.id = "sma-overlay-panel";
    panelEl.innerHTML = `
      <div class="sma-panel-header">
        <div class="sma-panel-title">
          <span class="sma-logo">📊</span>
          <span>${data.company_name}</span>
          <span class="sma-symbol">${data.symbol}</span>
        </div>
        <div class="sma-panel-controls">
          <button class="sma-btn-minimize" title="Minimize">—</button>
          <button class="sma-btn-close" title="Close">✕</button>
        </div>
      </div>
      <div class="sma-panel-body">
        <div class="sma-signal-hero">
          <div class="sma-action" style="color:${actionColor}">${signals.action}</div>
          <div class="sma-confidence">${signals.confidence}%</div>
        </div>
        <div class="sma-price-row">
          <div class="sma-price-item">
            <span class="sma-label">Current</span>
            <span class="sma-val">${data.current_price}</span>
          </div>
          <div class="sma-price-item">
            <span class="sma-label">Entry</span>
            <span class="sma-val sma-green">${signals.entry.price}</span>
          </div>
          <div class="sma-price-item">
            <span class="sma-label">Target</span>
            <span class="sma-val sma-green">${signals.exit.target_price}</span>
          </div>
          <div class="sma-price-item">
            <span class="sma-label">Stop Loss</span>
            <span class="sma-val sma-red">${signals.stop_loss}</span>
          </div>
        </div>
        <div class="sma-scores">
          ${renderScoreBar("Technical", signals.score_breakdown.technical)}
          ${renderScoreBar("Fundamental", signals.score_breakdown.fundamental)}
          ${renderScoreBar("Composite", signals.score_breakdown.composite)}
        </div>
        <div class="sma-reasons-section">
          <div class="sma-reasons-title">Key Signals</div>
          ${signals.entry.reasoning.slice(0, 3).map(r =>
            `<div class="sma-reason sma-reason-bull">${r}</div>`
          ).join("")}
          ${signals.exit.reasoning.slice(0, 3).map(r =>
            `<div class="sma-reason sma-reason-bear">${r}</div>`
          ).join("")}
        </div>
        <div class="sma-rr">
          Risk/Reward: <strong>${signals.risk_reward_ratio}:1</strong>
        </div>
      </div>
    `;

    document.body.appendChild(panelEl);
    makeDraggable(panelEl);

    panelEl.querySelector(".sma-btn-close").addEventListener("click", () => {
      panelEl.remove();
      panelEl = null;
    });

    panelEl.querySelector(".sma-btn-minimize").addEventListener("click", () => {
      const body = panelEl.querySelector(".sma-panel-body");
      body.style.display = body.style.display === "none" ? "block" : "none";
    });
  }

  function injectChartMarkers(data) {
    const histSignals = data.signals?.historical_signals;
    if (!histSignals?.length) return;

    removeExistingMarkers();

    const chartContainer = document.querySelector(".chart-markup-table") ||
                          document.querySelector("[class*='chart-container']") ||
                          document.querySelector(".layout__area--center");

    if (!chartContainer) return;

    const markersContainer = document.createElement("div");
    markersContainer.id = "sma-chart-markers";
    markersContainer.className = "sma-markers-layer";

    const tooltip = document.createElement("div");
    tooltip.className = "sma-marker-tooltip";
    tooltip.style.display = "none";
    document.body.appendChild(tooltip);

    const recentSignals = histSignals.slice(-20);
    const totalSignals = recentSignals.length;

    recentSignals.forEach((signal, idx) => {
      const marker = document.createElement("div");
      const isEntry = signal.type === "entry";
      marker.className = `sma-chart-marker ${isEntry ? "sma-marker-entry" : "sma-marker-exit"}`;

      const xPercent = ((idx + 1) / (totalSignals + 1)) * 100;
      marker.style.left = `${xPercent}%`;
      marker.style.bottom = isEntry ? "20%" : "80%";

      marker.innerHTML = isEntry ? "▲" : "▼";

      marker.addEventListener("mouseenter", (e) => {
        tooltip.style.display = "block";
        tooltip.style.left = e.pageX + 10 + "px";
        tooltip.style.top = e.pageY - 10 + "px";
        tooltip.innerHTML = `
          <div class="sma-tt-type ${isEntry ? "sma-green" : "sma-red"}">${signal.type.toUpperCase()}</div>
          <div class="sma-tt-date">${signal.date}</div>
          <div class="sma-tt-price">₹${signal.price}</div>
          <div class="sma-tt-reason">${signal.reason}</div>
          <div class="sma-tt-strength">${signal.strength}</div>
        `;
      });

      marker.addEventListener("mouseleave", () => {
        tooltip.style.display = "none";
      });

      markersContainer.appendChild(marker);
    });

    chartContainer.style.position = "relative";
    chartContainer.appendChild(markersContainer);

    injectPriceLevelLines(chartContainer, data);
  }

  function injectPriceLevelLines(container, data) {
    const signals = data.signals;
    const levels = [
      { price: signals.entry.price, label: "Entry", color: "#10b981", style: "dashed" },
      { price: signals.exit.target_price, label: "Target", color: "#6366f1", style: "dashed" },
      { price: signals.stop_loss, label: "Stop Loss", color: "#ef4444", style: "dotted" },
    ];

    const linesContainer = document.createElement("div");
    linesContainer.id = "sma-price-lines";
    linesContainer.className = "sma-price-lines-layer";

    levels.forEach(({ price, label, color, style }) => {
      const line = document.createElement("div");
      line.className = "sma-price-line";
      line.style.borderBottom = `2px ${style} ${color}`;

      const tag = document.createElement("div");
      tag.className = "sma-price-tag";
      tag.style.background = color;
      tag.textContent = `${label}: ₹${price}`;
      line.appendChild(tag);

      linesContainer.appendChild(line);
    });

    container.appendChild(linesContainer);
  }

  function removeExistingMarkers() {
    document.getElementById("sma-chart-markers")?.remove();
    document.getElementById("sma-price-lines")?.remove();
    document.querySelectorAll(".sma-marker-tooltip").forEach(el => el.remove());
  }

  function renderScoreBar(label, value) {
    const color = value >= 70 ? "#10b981" : value >= 50 ? "#f59e0b" : "#ef4444";
    return `
      <div class="sma-score-row">
        <span class="sma-score-label">${label}</span>
        <div class="sma-score-track">
          <div class="sma-score-fill" style="width:${value}%;background:${color}"></div>
        </div>
        <span class="sma-score-num">${value}</span>
      </div>`;
  }

  function getActionColor(action) {
    const a = action.toLowerCase();
    if (a.includes("buy")) return "#10b981";
    if (a.includes("sell")) return "#ef4444";
    return "#f59e0b";
  }

  function makeDraggable(el) {
    const header = el.querySelector(".sma-panel-header");
    let isDragging = false, startX, startY, origX, origY;

    header.addEventListener("mousedown", (e) => {
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      const rect = el.getBoundingClientRect();
      origX = rect.left;
      origY = rect.top;
      e.preventDefault();
    });

    document.addEventListener("mousemove", (e) => {
      if (!isDragging) return;
      el.style.left = origX + (e.clientX - startX) + "px";
      el.style.top = origY + (e.clientY - startY) + "px";
      el.style.right = "auto";
    });

    document.addEventListener("mouseup", () => { isDragging = false; });
  }
})();
