// The frontend only displays what /api/ask returns. It never calculates revenue itself.
const $ = (id) => document.getElementById(id);
const currency = document.body.dataset.currency || "";
let chart = null;
const fmt = (v) => (typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v ?? "—"));
const title = (k) => k.replace(/_/g, " ");

function show(el, on) { el.hidden = !on; }

async function ask(question) {
  show($("error"), false); show($("result"), false); show($("loading"), true);
  $("ask-btn").disabled = true;
  try {
    const res = await fetch("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data?.error?.message || "Request failed (" + res.status + ")");
    render(data);
  } catch (e) {
    $("error").textContent = e.message || "Could not reach the server.";
    show($("error"), true);
  } finally {
    show($("loading"), false); $("ask-btn").disabled = false;
  }
}

function render(d) {
  show($("result"), true);
  $("answer").textContent = d.answer;
  $("method").textContent = d.interpretation_method === "claude"
    ? "Interpreted by Claude" : "Interpreted by rule-based fallback (not an LLM)";
  const unsupported = d.status !== "success";
  $("cards").replaceChildren(); $("table").replaceChildren();
  show($("chart-wrap"), false);
  if (chart) { chart.destroy(); chart = null; }
  if (unsupported) { $("dq").textContent = ""; return; }

  for (const [k, v] of Object.entries(d.metrics)) {
    if (v === null || typeof v === "object" || (typeof v === "string" && v.length > 60)) continue;
    const c = document.createElement("div"); c.className = "card";
    const l = document.createElement("div"); l.className = "label"; l.textContent = title(k);
    const val = document.createElement("div"); val.className = "value";
    val.textContent = fmt(v) + (/revenue|change/.test(k) && typeof v === "number" && !k.includes("percentage") ? " " + currency : "") + (k.includes("percentage") ? "%" : "");
    c.append(l, val); $("cards").append(c);
  }
  for (const key of ["top_products", "top_regions"]) {
    if (d.metrics[key]) {
      const c = document.createElement("div"); c.className = "card";
      c.innerHTML = '<div class="label"></div><div class="value"></div>';
      c.children[0].textContent = title(key); c.children[1].textContent = d.metrics[key].join(", ");
      $("cards").prepend(c);
    }
  }

  const rows = d.supporting_data;
  if (rows.length) {
    const cols = Object.keys(rows[0]);
    const thead = document.createElement("tr");
    cols.forEach((c) => { const th = document.createElement("th"); th.textContent = title(c); thead.append(th); });
    $("table").append(thead);
    rows.forEach((r) => {
      const tr = document.createElement("tr");
      cols.forEach((c) => { const td = document.createElement("td"); td.textContent = fmt(r[c]); tr.append(td); });
      $("table").append(tr);
    });
    drawChart(d, rows);
  }
  const q = d.data_quality;
  $("dq").textContent = q && q.stored !== undefined
    ? `Data-quality note: ${q.stored} transactions stored, ${q.eligible} counted. Excluded: ${q.returned} returned, `
      + `${q.zero_quantity} zero-quantity, ${q.missing_price} missing-price. ${q.rejected_rows} rows rejected at import.` : "";
}

function drawChart(d, rows) {
  if (typeof Chart === "undefined") return; // chart library blocked/offline: tables still work
  let labels, values, type = "bar", label = "Net revenue (" + currency + ")";
  if (d.intent === "monthly_trend") { labels = rows.map((r) => r.month); values = rows.map((r) => r.revenue); type = "line"; }
  else if (d.intent === "top_product" || d.intent === "top_region") { labels = rows.map((r) => r.name); values = rows.map((r) => r.revenue); }
  else if (d.intent === "revenue_comparison") { labels = rows.map((r) => r.month); values = rows.map((r) => r.revenue); }
  else return;
  show($("chart-wrap"), true);
  chart = new Chart($("chart"), {
    type, data: { labels, datasets: [{ label, data: values, backgroundColor: "#2f5bea", borderColor: "#2f5bea", tension: 0.25 }] },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
  });
}

$("ask-form").addEventListener("submit", (e) => { e.preventDefault(); const q = $("question").value.trim(); if (q) ask(q); });
$("examples").addEventListener("click", (e) => {
  if (e.target.tagName === "BUTTON") { $("question").value = e.target.textContent; ask(e.target.textContent); }
});
