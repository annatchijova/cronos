/* CRONOS dashboard — vanilla JS, no build step.
 * Read-only client of the /api endpoints. Fractions arrive as "p/q" strings;
 * every percentage here is computed with integer arithmetic, mirroring the
 * project's no-floats-in-the-decision-path principle. */
"use strict";

// ── i18n ─────────────────────────────────────────────────────────────────────
const I18N = {
  en: {
    traces: "traces", agents: "agents", chain: "chain", quality: "quality",
    verified: "VERIFIED", broken: "BROKEN", all_agents: "All agents",
    chain_intact: "Chain intact — entries verified:",
    chain_broken: "Chain verification FAILED — errors:",
    page: "page", of: "of", no_traces: "no traces recorded — run: python demo_seed.py --reset",
    load_error: "could not reach the CRONOS API",
    decision: "DECISION", confidence: "CONFIDENCE", objective: "OBJECTIVE",
    warnings: "CONFIDENCE WARNINGS", contradictions: "CONTRADICTIONS",
    timeline: "Step timeline", hypotheses: "Hypotheses", evidence: "Evidence",
    memories: "Recalled memories", tools: "Tool calls",
    devils: "Devil's advocate", narrative: "Narrative", seal: "Seal",
    kept: "KEPT", discarded: "DISCARDED", supports: "supports", refutes: "refutes",
    opened: "opened", closed: "closed", version: "version", hash: "entry hash",
    chain_ok_badge: "⛓ CHAIN OK", chain_bad_badge: "⛓ CHAIN BROKEN",
    not_found: "trace not found",
  },
  es: {
    traces: "trazas", agents: "agentes", chain: "cadena", quality: "calidad",
    verified: "VERIFICADA", broken: "ROTA", all_agents: "Todos los agentes",
    chain_intact: "Cadena íntegra — entradas verificadas:",
    chain_broken: "La verificación de la cadena FALLÓ — errores:",
    page: "página", of: "de", no_traces: "sin trazas registradas — ejecutá: python demo_seed.py --reset",
    load_error: "no se pudo contactar la API de CRONOS",
    decision: "DECISIÓN", confidence: "CONFIANZA", objective: "OBJETIVO",
    warnings: "ADVERTENCIAS DE CONFIANZA", contradictions: "CONTRADICCIONES",
    timeline: "Línea de tiempo", hypotheses: "Hipótesis", evidence: "Evidencia",
    memories: "Memorias recuperadas", tools: "Llamadas a herramientas",
    devils: "Abogado del diablo", narrative: "Narrativa", seal: "Sello",
    kept: "MANTENIDA", discarded: "DESCARTADA", supports: "respalda", refutes: "refuta",
    opened: "abierta", closed: "cerrada", version: "versión", hash: "hash de entrada",
    chain_ok_badge: "⛓ CADENA OK", chain_bad_badge: "⛓ CADENA ROTA",
    not_found: "traza no encontrada",
  },
};

function lang() { return document.body.dataset.language === "es" ? "es" : "en"; }
function t(key) { return I18N[lang()][key] || key; }

const toggle = document.getElementById("language-toggle");
function setLanguage(language) {
  document.body.dataset.language = language;
  document.documentElement.lang = language;
  toggle.textContent = language === "en" ? "ES" : "EN";
  try { localStorage.setItem("cronos-language", language); } catch (_) {}
  render(); // re-render dynamic strings
}
toggle.addEventListener("click", () => setLanguage(lang() === "en" ? "es" : "en"));
try {
  const preferred = localStorage.getItem("cronos-language");
  if (preferred === "en" || preferred === "es") {
    document.body.dataset.language = preferred;
    document.documentElement.lang = preferred;
    toggle.textContent = preferred === "en" ? "ES" : "EN";
  }
} catch (_) {}

// ── helpers ──────────────────────────────────────────────────────────────────
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// "37/50" → integer percent (rounded), or null.
function fractionPct(s) {
  if (!s || typeof s !== "string") return null;
  const parts = s.split("/");
  if (parts.length !== 2) return null;
  const p = parseInt(parts[0], 10), q = parseInt(parts[1], 10);
  if (!Number.isFinite(p) || !Number.isFinite(q) || q === 0) return null;
  return Math.round((100 * p) / q); // display-only rounding
}

// Port of slack/output.py:_confidence_bar — 10 monospace cells.
function confidenceBar(pq) {
  const pct = fractionPct(pq);
  if (pct === null) return "[··········]";
  const filled = Math.round(pct / 10);
  return "[" + "█".repeat(filled) + "░".repeat(10 - filled) + "]";
}

async function getJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(String(resp.status));
  return resp.json();
}

const QUALITY_ORDER = ["FULL", "PARTIAL", "MINIMAL", "EMPTY"];
const QUALITY_COLOR = { FULL: "var(--mint)", PARTIAL: "var(--amber)", MINIMAL: "var(--cyan)", EMPTY: "var(--red)" };

// ── state ────────────────────────────────────────────────────────────────────
const state = { agent: "", offset: 0, limit: 20, stats: null, page: null, detail: null, verify: null };

// ── stats strip ──────────────────────────────────────────────────────────────
function renderStats() {
  const box = document.getElementById("stats");
  box.replaceChildren();
  const s = state.stats;
  if (!s) return;

  const total = el("div", "signal");
  total.append(el("b", "", String(s.total)), el("span", "", t("traces")));
  box.append(total);

  const agents = el("div", "signal");
  agents.append(el("b", "", String(s.agents.length)), el("span", "", t("agents")));
  box.append(agents);

  const chain = el("div", "signal");
  chain.append(el("b", "", s.chain_ok ? "⛓ " + t("verified") : "⛓ " + t("broken")),
               el("span", "", t("chain") + " SHA-256"));
  chain.firstChild.style.color = s.chain_ok ? "var(--mint)" : "var(--red)";
  box.append(chain);

  const quality = el("div", "signal");
  quality.append(el("b", "", t("quality")));
  const bar = el("div", "quality-bar");
  const totalQ = QUALITY_ORDER.reduce((acc, q) => acc + (s.quality_counts[q] || 0), 0);
  QUALITY_ORDER.forEach((q) => {
    const n = s.quality_counts[q] || 0;
    if (!n || !totalQ) return;
    const seg = el("i");
    seg.style.width = Math.round((100 * n) / totalQ) + "%";
    seg.style.background = QUALITY_COLOR[q];
    seg.title = q + ": " + n;
    bar.append(seg);
  });
  quality.append(bar);
  const legend = el("span", "", QUALITY_ORDER.map((q) => q[0] + ":" + (s.quality_counts[q] || 0)).join(" "));
  legend.style.display = "block"; legend.style.marginTop = "6px";
  quality.append(legend);
  box.append(quality);

  const pill = document.getElementById("chain-pill");
  pill.replaceChildren();
  const badge = el("span", "chain-pill " + (s.chain_ok ? "ok" : "broken"),
                   s.chain_ok ? "⛓ " + t("verified") : "⛓ " + t("broken"));
  pill.append(badge);
}

// ── agent filter ─────────────────────────────────────────────────────────────
function renderAgentFilter() {
  const sel = document.getElementById("agent-filter");
  sel.replaceChildren();
  const all = el("option", "", t("all_agents"));
  all.value = "";
  sel.append(all);
  (state.stats ? state.stats.agents : []).forEach((a) => {
    const opt = el("option", "", a.agent_id + " (" + a.count + ")");
    opt.value = a.agent_id;
    sel.append(opt);
  });
  sel.value = state.agent;
}

// ── list view ────────────────────────────────────────────────────────────────
function renderList() {
  const box = document.getElementById("trace-list");
  box.replaceChildren();
  const page = state.page;
  if (!page) return;

  if (!page.traces.length) {
    box.append(el("div", "empty", t("no_traces")));
  }
  page.traces.forEach((row) => {
    const item = el("a", "list-row");
    item.href = "#/trace/" + encodeURIComponent(row.trace_id);

    item.append(el("span", "qdot q-" + (row.quality || "UNKNOWN")));

    const main = el("div", "list-main");
    main.append(el("p", "", row.decision || row.objective || "—"));
    main.append(el("small", "",
      row.agent_id + " · " + (row.closed_at || "").replace("T", " ").slice(0, 19) +
      " · #" + (row.entry_hash || "").slice(0, 7)));
    item.append(main);

    const conf = el("div", "conf-cell");
    conf.append(el("span", "conf-bar", confidenceBar(row.confidence)));
    const pct = fractionPct(row.confidence);
    conf.append(el("span", "conf-pct", pct === null ? "—" : pct + "%"));
    item.append(conf);

    const badges = el("div", "badges");
    badges.append(el("span", "mini-pill quality-" + (row.quality || "UNKNOWN"), row.quality || "?"));
    if (row.contradiction_count > 0) {
      badges.append(el("span", "mini-pill contra", "⚠ " + row.contradiction_count));
    }
    badges.append(el("span", "mini-pill " + (row.chain_ok ? "chain-ok" : "chain-bad"),
                     row.chain_ok ? "⛓ OK" : "⛓ ✗"));
    item.append(badges);
    box.append(item);
  });

  const pageNum = Math.floor(state.offset / state.limit) + 1;
  const pages = Math.max(1, Math.ceil(page.total / state.limit));
  document.getElementById("page-info").textContent =
    t("page") + " " + pageNum + " " + t("of") + " " + pages + " · " + page.total + " " + t("traces");
  document.getElementById("prev-btn").disabled = state.offset === 0;
  document.getElementById("next-btn").disabled = state.offset + state.limit >= page.total;
  document.getElementById("window-title").textContent =
    "cronos://traces" + (state.agent ? "/" + state.agent : "");
}

function renderVerify() {
  const box = document.getElementById("verify-result");
  box.replaceChildren();
  const v = state.verify;
  if (!v) { box.className = "verify-result"; return; }
  box.className = "verify-result show" + (v.chain_ok ? "" : " bad");
  box.append(el("span", "", (v.chain_ok ? t("chain_intact") : t("chain_broken")) + " " + v.entries));
  if (v.errors && v.errors.length) {
    const ul = el("ul");
    v.errors.forEach((e) => ul.append(el("li", "", e)));
    box.append(ul);
  }
}

// ── detail view ──────────────────────────────────────────────────────────────
function panel(titleKey) {
  const p = el("div", "panel");
  const body = el("div", "panel-body");
  if (titleKey) body.append(el("h3", "", t(titleKey)));
  p.append(body);
  return [p, body];
}

function renderDetail() {
  const box = document.getElementById("detail-content");
  box.replaceChildren();
  const d = state.detail;
  if (!d) return;
  if (d.error) { box.append(el("div", "empty", t(d.error))); return; }

  // Header panel: objective + decision + callouts
  const head = el("div", "panel");
  const headBody = el("div", "panel-body");
  const bar = el("div", "window-bar");
  bar.append(el("span", "", "cronos://trace/" + d.trace_id.slice(0, 8) + "… · " + d.agent_id));
  const dots = el("span", "dots"); dots.append(el("i"), el("i"), el("i"));
  bar.append(dots);
  head.append(bar, headBody);

  const obj = el("p", "", d.objective);
  obj.style.cssText = "margin:0 0 14px;color:var(--panel-muted);font-size:13.5px";
  const objLabel = el("small", "", t("objective"));
  objLabel.style.cssText = "display:block;margin-bottom:4px;color:var(--faint);font:700 9px/1 ui-monospace,monospace;letter-spacing:.11em";
  headBody.append(objLabel, obj);

  const dec = el("div", "decision");
  dec.append(el("small", "", t("decision") + " / " + t("confidence") + " " + (d.confidence || "—") +
             " · " + d.confidence_pct + " (" + d.confidence_label + ")"));
  dec.append(el("strong", "", d.decision));
  const bigBar = el("div", "conf-bar", confidenceBar(d.confidence));
  bigBar.style.marginTop = "8px";
  dec.append(bigBar);
  headBody.append(dec);

  if (d.confidence_warnings && d.confidence_warnings.length) {
    const c = el("div", "callout warn");
    c.append(el("small", "", "⚠ " + t("warnings")));
    const ul = el("ul");
    d.confidence_warnings.forEach((w) => ul.append(el("li", "", w)));
    c.append(ul);
    headBody.append(c);
  }
  if (d.contradictions && d.contradictions.length) {
    const c = el("div", "callout contra");
    c.append(el("small", "", "✗ " + t("contradictions")));
    const ul = el("ul");
    d.contradictions.forEach((w) => ul.append(el("li", "", w)));
    c.append(ul);
    headBody.append(c);
  }
  box.append(head);

  const grid = el("div", "detail-grid");
  grid.style.marginTop = "16px";
  const colL = el("div"); const colR = el("div");
  colL.style.cssText = "display:grid;gap:16px"; colR.style.cssText = "display:grid;gap:16px";
  grid.append(colL, colR);
  box.append(grid);

  // Timeline
  const KIND_CLASS = { objective: "objective", recall: "recall", tool: "tool", hypothesis: "hypothesis", discard: "discard", evidence: "evidence", decision: "decision-k" };
  const [tlPanel, tlBody] = panel("timeline");
  (d.steps || []).forEach((s) => {
    const row = el("div", "trace-row");
    row.append(el("span", "kind " + (KIND_CLASS[s.kind] || ""), s.kind.toUpperCase()));
    let text = "";
    const p = s.payload || {};
    if (s.kind === "objective") text = p.objective || "";
    else if (s.kind === "recall") text = (p.memory_id || "") + " · " + (p.summary || "");
    else if (s.kind === "tool") text = (p.tool || "") + " → " + (p.result || "");
    else if (s.kind === "hypothesis") text = (p.label || "") + " · " + (p.description || "");
    else if (s.kind === "discard") text = (p.label || "") + " — " + (p.reason || "");
    else if (s.kind === "evidence") text = p.text || "";
    else if (s.kind === "decision") text = (p.decision || "") + " (" + (p.confidence || "") + ")";
    row.append(el("p", "", text));
    let tag = (s.timestamp || "").slice(11, 19);
    if (s.kind === "evidence") tag = p.supports ? t("supports") + " " + p.supports : (p.refutes ? t("refutes") + " " + p.refutes : tag);
    if (s.kind === "recall" && p.score) tag = p.score;
    row.append(el("span", "score", tag));
    tlBody.append(row);
  });
  colL.append(tlPanel);

  // Hypotheses
  if (d.hypotheses && d.hypotheses.length) {
    const [hp, hb] = panel("hypotheses");
    d.hypotheses.forEach((h) => {
      const hyp = el("div", "hyp " + h.status);
      hyp.append(el("small", "", h.label + " · " + (h.status === "kept" ? t("kept") : t("discarded"))));
      hyp.append(el("span", "", h.description));
      if (h.discard_reason) hyp.append(el("div", "reason", "→ " + h.discard_reason));
      hb.append(hyp);
    });
    colR.append(hp);
  }

  // Evidence
  if (d.evidence && d.evidence.length) {
    const [ep, eb] = panel("evidence");
    d.evidence.forEach((e) => {
      const row = el("div", "trace-row");
      row.append(el("span", "kind " + (e.refutes ? "discard" : "evidence"), e.refutes ? "✗" : "✓"));
      row.append(el("p", "", e.text));
      row.append(el("span", "score", e.supports ? t("supports") + " " + e.supports : (e.refutes ? t("refutes") + " " + e.refutes : "")));
      eb.append(row);
    });
    colR.append(ep);
  }

  // Memories + tools
  if (d.memories && d.memories.length) {
    const [mp, mb] = panel("memories");
    d.memories.forEach((m) => {
      const row = el("div", "trace-row");
      row.append(el("span", "kind recall", m.id));
      row.append(el("p", "", m.summary));
      row.append(el("span", "score", m.score || ""));
      mb.append(row);
    });
    colR.append(mp);
  }
  if (d.tools && d.tools.length) {
    const [tp, tb] = panel("tools");
    d.tools.forEach((tool) => {
      const row = el("div", "trace-row");
      row.append(el("span", "kind tool", tool.name));
      row.append(el("p", "", tool.result));
      row.append(el("span", "score", ""));
      tb.append(row);
    });
    colR.append(tp);
  }

  // Devil's advocate + narrative
  if (d.devils_advocate) {
    const [dp, db] = panel("devils");
    db.append(el("div", "devils", d.devils_advocate));
    colL.append(dp);
  }
  if (d.natural) {
    const [np, nb] = panel("narrative");
    nb.append(el("p", "natural", d.natural));
    colL.append(np);
  }

  // Seal metadata
  const [sp, sb] = panel("seal");
  const meta = el("ul", "meta-list");
  const items = [
    [t("hash"), d.entry_hash || "—", "hash"],
    [t("chain"), d.chain_ok ? t("chain_ok_badge") : t("chain_bad_badge")],
    [t("quality"), d.quality + " · " + d.diversity_pct],
    [t("opened"), d.started_at || "—"],
    [t("closed"), d.closed_at || "—"],
    [t("version"), "cronos " + d.cronos_version],
  ];
  items.forEach(([k, v, cls]) => {
    const li = el("li", cls || "");
    li.append(el("b", "", k.toUpperCase() + " "), document.createTextNode(String(v)));
    meta.append(li);
  });
  sb.append(meta);
  colL.append(sp);
}

// ── router + data flow ───────────────────────────────────────────────────────
function currentRoute() {
  const h = location.hash || "#/";
  const m = h.match(/^#\/trace\/(.+)$/);
  return m ? { view: "detail", id: decodeURIComponent(m[1]) } : { view: "list" };
}

function render() {
  const route = currentRoute();
  document.getElementById("view-list").classList.toggle("hidden", route.view !== "list");
  document.getElementById("view-detail").classList.toggle("hidden", route.view !== "detail");
  renderStats();
  renderAgentFilter();
  if (route.view === "list") { renderList(); renderVerify(); }
  else renderDetail();
}

async function loadList() {
  const params = new URLSearchParams({ limit: String(state.limit), offset: String(state.offset) });
  if (state.agent) params.set("agent_id", state.agent);
  state.page = await getJSON("/api/traces?" + params);
}

async function refresh() {
  const route = currentRoute();
  try {
    if (!state.stats) state.stats = await getJSON("/api/stats");
    if (route.view === "list") await loadList();
    else {
      try { state.detail = await getJSON("/api/traces/" + encodeURIComponent(route.id)); }
      catch (_) { state.detail = { error: "not_found" }; }
    }
  } catch (_) {
    state.page = { total: 0, traces: [] };
    if (!state.stats) state.stats = { total: 0, chain_ok: true, agents: [], quality_counts: {} };
    document.getElementById("trace-list").replaceChildren(el("div", "empty", t("load_error")));
  }
  render();
}

document.getElementById("agent-filter").addEventListener("change", (e) => {
  state.agent = e.target.value; state.offset = 0; refresh();
});
document.getElementById("prev-btn").addEventListener("click", () => {
  state.offset = Math.max(0, state.offset - state.limit); refresh();
});
document.getElementById("next-btn").addEventListener("click", () => {
  state.offset += state.limit; refresh();
});
document.getElementById("verify-btn").addEventListener("click", async () => {
  state.verify = await getJSON("/api/verify");
  state.stats = null; // chain state may have changed — reload badge
  refresh();
});
window.addEventListener("hashchange", refresh);

refresh();
