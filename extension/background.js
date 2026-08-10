const API_BASE = "http://localhost:8899";

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "analyze") {
    fetchAnalysis(request.symbol, request.period, request.interval)
      .then(data => sendResponse({ success: true, data }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true; // async response
  }

  if (request.action === "getSignals") {
    fetchSignals(request.symbol, request.period)
      .then(data => sendResponse({ success: true, data }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
});

async function fetchAnalysis(symbol, period = "1y", interval = "1d") {
  const url = `${API_BASE}/analyze/${encodeURIComponent(symbol)}?period=${period}&interval=${interval}`;
  const res = await fetch(url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `API error: ${res.status}`);
  }
  return res.json();
}

async function fetchSignals(symbol, period = "1y") {
  const url = `${API_BASE}/signals/${encodeURIComponent(symbol)}?period=${period}`;
  const res = await fetch(url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `API error: ${res.status}`);
  }
  return res.json();
}
