"use strict";

const $ = (selector) => document.querySelector(selector);
const state = { running: false, eventCount: 0, iterations: 0, source: null };

function widthClass(percent) {
  const bounded = Math.max(0, Math.min(100, Number(percent) || 0));
  return `w-${Math.round(bounded / 5) * 5}`;
}

function text(node, value) {
  if (node) node.textContent = value == null ? "—" : String(value);
}

function toast(message, error = false) {
  const node = document.createElement("div");
  node.className = `toast${error ? " error" : ""}`;
  node.textContent = message;
  $("#toast-region").appendChild(node);
  window.setTimeout(() => node.remove(), 4200);
}

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
  if (response.status === 401) {
    const token = window.prompt("Control Plane protegido. Introduce el token emitido por a2s token:");
    if (!token) throw new Error("Autenticación requerida");
    const login = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token }) });
    if (!login.ok) throw new Error("Token inválido o expirado");
    return api(path, options);
  }
  let data = {};
  try { data = await response.json(); } catch (_) { data = {}; }
  if (!response.ok) throw new Error(data.error || data.status || `HTTP ${response.status}`);
  return data;
}

function setConnection(ok, label = "ONLINE") {
  const pill = $("#system-pill");
  const dot = $("#side-dot");
  pill.classList.toggle("ok", ok);
  pill.classList.toggle("bad", !ok);
  dot.classList.toggle("ok", ok);
  dot.classList.toggle("bad", !ok);
  text(pill.querySelector("span"), label);
  text($("#side-state"), ok ? "Sistema operativo" : "Sin conexión");
}

function updateMissionControls(running) {
  state.running = running;
  $("#start").disabled = running;
  $("#demo").disabled = running;
  $("#stop").disabled = !running;
  text($("#metric-state"), running ? "RUNNING" : "IDLE");
  text($("#metric-state-note"), running ? "Agente ejecutando la directiva" : "Listo para recibir objetivo");
  $("#metric-state").closest(".metric").classList.toggle("primary", running);
}

const EVENT_META = {
  run_start: ["▶", "Misión iniciada", "step_start"],
  plan_created: ["◇", "Plan construido", "replan"],
  speculative_plan: ["⋈", "Planificación especulativa", "replan"],
  step_start: ["→", "Paso en ejecución", "step_start"],
  evaluation: ["✓", "Resultado evaluado", "evaluation"],
  retry: ["↻", "Reintento adaptativo", "retry"],
  failure_handled: ["↻", "Contramedida aplicada", "retry"],
  split: ["⑂", "División fractal", "replan"],
  replan: ["◇", "Replanificación", "replan"],
  goal_check: ["◎", "Verificación de objetivo", "evaluation"],
  run_end: ["■", "Misión finalizada", "run_end"],
  operator_stop: ["!", "Parada solicitada", "failed"],
  ecosystem_scan: ["+", "Radar actualizado", "success"],
};

function eventDetail(event) {
  if (event.event === "run_start") return `${event.goal || ""} · proveedor ${event.provider || "—"}`;
  if (event.event === "step_start") return `${event.goal || ""} · ${event.approach || ""}`;
  if (event.event === "evaluation") return `${event.goal || ""} · ${event.verdict || ""} · ${event.reason || ""}`;
  if (event.event === "goal_check") return `${event.achieved ? "CUMPLIDO" : "pendiente"} · ${event.reason || ""}`;
  if (event.event === "replan" || event.event === "plan_created") return (event.steps || []).join(" → ");
  if (event.event === "failure_handled") return event.countermeasure || "";
  if (event.event === "run_end" || event.event === "operator_stop") return event.note || "";
  if (event.event === "ecosystem_scan") return `${event.added || 0} nuevos · ${event.total || 0} totales`;
  return event.note || event.status || event.goal || event.event || "evento";
}

function addEvent(event, scroll = true) {
  if (!event || !event.event) return;
  const feed = $("#event-feed");
  if (feed.querySelector(".empty")) feed.replaceChildren();
  const [icon, title, cls] = EVENT_META[event.event] || ["·", event.event, ""];
  const verdictClass = event.verdict === "success" || event.success ? " success" :
    (event.verdict === "failed" || event.verdict === "blocked" || event.success === false ? " failed" : "");
  const item = document.createElement("li");
  item.className = `event ${cls}${verdictClass}`;
  const iconNode = document.createElement("span");
  iconNode.className = "event-icon";
  iconNode.textContent = icon;
  const content = document.createElement("div");
  const heading = document.createElement("b");
  heading.textContent = title;
  const detail = document.createElement("small");
  detail.textContent = eventDetail(event).slice(0, 520);
  content.append(heading, detail);
  const stamp = document.createElement("time");
  stamp.textContent = (event.at || "").slice(11, 19) || "LIVE";
  item.append(iconNode, content, stamp);
  feed.appendChild(item);
  while (feed.children.length > 220) feed.firstElementChild.remove();
  if (scroll) feed.scrollTop = feed.scrollHeight;
  state.eventCount += 1;

  if (event.event === "run_start") updateMissionControls(true);
  if (event.event === "evaluation") {
    state.iterations += 1;
    text($("#metric-iterations"), state.iterations);
  }
  if (event.event === "run_end") {
    updateMissionControls(false);
    text($("#metric-state"), event.success ? "VERIFIED" : "PARTIAL");
    text($("#metric-state-note"), event.success ? "Objetivo verificado" : "Estado persistido y reanudable");
    toast(event.success ? "Misión verificada correctamente" : "Misión cerrada sin verificación completa", !event.success);
  }
}

function connectEvents() {
  if (state.source) state.source.close();
  const source = new EventSource("/api/events");
  state.source = source;
  source.onopen = () => setConnection(true);
  source.onmessage = (message) => {
    try { addEvent(JSON.parse(message.data)); } catch (_) { /* evento malformado ignorado */ }
  };
  source.onerror = () => {
    setConnection(false, "RECONNECTING");
    source.close();
    window.setTimeout(connectEvents, 2500);
  };
}

async function loadState() {
  const data = await api("/api/state");
  setConnection(true);
  updateMissionControls(Boolean(data.running));
  state.iterations = Number(data.iterations || 0);
  text($("#metric-iterations"), state.iterations);
  const feed = $("#event-feed");
  if ((data.events || []).length) {
    feed.replaceChildren();
    state.eventCount = 0;
    data.events.forEach((event) => addEvent(event, false));
    feed.scrollTop = feed.scrollHeight;
  }
  if (data.report) {
    text($("#metric-state"), data.report.success ? "VERIFIED" : "PARTIAL");
    text($("#metric-state-note"), `${data.report.iterations} iteraciones · ${data.report.wall_seconds}s`);
  }
}

function quotaClass(value) {
  if (value === "exhausted") return "bad";
  if (value === "approaching_limit") return "warn";
  return "";
}

function renderPool(data) {
  const status = data.status || {};
  const preview = data.preview || {};
  text($("#metric-endpoints"), status.totals?.endpoints_active || 0);
  text($("#metric-pool-note"), `${status.totals?.total_calls || 0} llamadas registradas`);
  text($("#routing-strategy"), status.strategy || "—");
  const list = $("#provider-list");
  list.replaceChildren();
  (status.endpoints || []).forEach((endpoint) => {
    const row = document.createElement("div");
    row.className = "provider";
    const name = document.createElement("div");
    name.className = "provider-name";
    const dot = document.createElement("i");
    if (!endpoint.active || endpoint.circuit_open) dot.className = "down";
    const nameText = document.createElement("b");
    nameText.textContent = endpoint.name;
    name.append(dot, nameText);
    const model = document.createElement("div");
    model.className = "provider-model";
    model.textContent = endpoint.model || (endpoint.role === "fallback_only" ? "núcleo determinista" : "sin modelo");
    const tier = document.createElement("small");
    tier.textContent = endpoint.role === "fallback_only" ? "FALLBACK" : String(endpoint.cost_tier || "—").toUpperCase();
    const quota = document.createElement("div");
    const usage = endpoint.rpm_effective > 0 ? Math.min(100, (endpoint.window_used / endpoint.rpm_effective) * 100) : 0;
    const quotaText = document.createElement("small");
    quotaText.textContent = endpoint.rpm_effective > 0 ? `${endpoint.window_used}/${endpoint.rpm_effective} RPM` : "CUOTA UNKNOWN";
    const quotaTrack = document.createElement("div"); quotaTrack.className = "quota";
    const quotaFill = document.createElement("i"); quotaFill.className = widthClass(usage); quotaTrack.appendChild(quotaFill);
    quota.append(quotaText, quotaTrack);
    row.append(name, model, tier, quota);
    list.appendChild(row);
  });
  if (!(status.endpoints || []).length) list.innerHTML = '<p class="empty-copy">No hay endpoints configurados; queda el núcleo heurístico.</p>';
  renderPreview(preview);
}

function renderPreview(preview) {
  const rows = preview.candidates || [];
  const selected = rows.find((row) => row.selected);
  text($("#selected-provider"), preview.selected || "Sin ruta");
  text($("#selected-model"), selected?.model || (selected?.role === "fallback_only" ? "núcleo heurístico local" : "—"));
  text($("#preview-stamp"), `${preview.kind || "general"} · ${preview.at || "—"} · upstream: NO`);
  const bars = $("#factor-bars");
  bars.replaceChildren();
  Object.entries(selected?.factors || {}).forEach(([key, value]) => {
    const row = document.createElement("div");
    row.className = `factor${key === "quota_risk" ? " negative" : ""}`;
    const label = document.createElement("label"); label.textContent = key.replace("_", " ");
    const track = document.createElement("div"); track.className = "factor-track";
    const fill = document.createElement("i"); fill.className = widthClass(Number(value) * 100); track.appendChild(fill);
    const output = document.createElement("output"); output.textContent = Number(value).toFixed(2);
    row.append(label, track, output); bars.appendChild(row);
  });
  const body = $("#route-table");
  body.replaceChildren();
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    if (row.selected) tr.className = "selected";
    const reason = (row.reasons || []).join(", ") || (row.selected ? "mejor utilidad" : "elegible");
    [row.name, row.model || "—"].forEach((value) => { const td = document.createElement("td"); td.textContent = value; tr.appendChild(td); });
    const eligible = document.createElement("td");
    const eChip = document.createElement("span"); eChip.className = `status-chip${row.eligible ? "" : " bad"}`; eChip.textContent = row.eligible ? "ELIGIBLE" : "BLOCKED"; eligible.appendChild(eChip);
    const quota = document.createElement("td");
    const qChip = document.createElement("span"); qChip.className = `status-chip ${quotaClass(row.quota_state)}`; qChip.textContent = row.quota_state; quota.appendChild(qChip);
    const score = document.createElement("td"); score.textContent = Number(row.utility || 0).toFixed(3);
    const why = document.createElement("td"); why.textContent = reason;
    tr.append(eligible, quota, score, why); body.appendChild(tr);
  });
}

async function loadPool() {
  const kind = $("#route-kind").value;
  const data = await api(`/api/pool?kind=${encodeURIComponent(kind)}`);
  renderPool(data);
}

function renderKnowledge(data) {
  const ecosystem = data.ecosystem || {};
  text($("#metric-knowledge"), data.cards_total || 0);
  text($("#metric-knowledge-note"), `${ecosystem.total || 0} proyectos en radar`);
  text($("#project-count"), ecosystem.total || 0);
  text($("#card-count"), data.cards_total || 0);
  const projects = $("#project-list");
  projects.replaceChildren();
  (ecosystem.projects || []).forEach((project) => {
    const row = document.createElement("article"); row.className = "project";
    const fit = document.createElement("div"); fit.className = "fit-score"; fit.textContent = project.fit_score;
    const main = document.createElement("div");
    const title = document.createElement("h3"); const link = document.createElement("a");
    link.href = project.url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = project.repo; title.appendChild(link);
    const desc = document.createElement("p"); desc.textContent = project.description || "Sin descripción pública.";
    const lessons = document.createElement("div"); lessons.className = "lesson-list";
    (project.lessons || []).forEach((lesson) => { const span = document.createElement("span"); span.textContent = lesson; lessons.appendChild(span); });
    main.append(title, desc, lessons);
    const meta = document.createElement("div"); meta.className = "project-meta";
    const license = document.createElement("b"); license.textContent = project.license;
    meta.append(license, document.createElement("br"), document.createTextNode(`★ ${project.stars || 0}`), document.createElement("br"), document.createTextNode(project.language || "—"));
    row.append(fit, main, meta); projects.appendChild(row);
  });
  const cards = $("#card-list");
  cards.replaceChildren();
  (data.cards || []).slice().reverse().forEach((card) => {
    const row = document.createElement("article"); row.className = "knowledge-card";
    const title = document.createElement("h3"); title.textContent = card.repo;
    const summary = document.createElement("p"); summary.textContent = card.summary;
    const meta = document.createElement("small"); meta.textContent = `${card.license} · usos ${card.used} · éxitos ${card.wins}`;
    row.append(title, summary, meta); cards.appendChild(row);
  });
  if (!(data.cards || []).length) cards.innerHTML = '<p class="empty-copy">Aún no hay fichas. Usa <code>a2s learn</code> para estudiar READMEs con trazabilidad.</p>';
}

async function loadKnowledge() { renderKnowledge(await api("/api/knowledge")); }

function renderAudit(report) {
  const score = Number(report.nota_medible || 0);
  text($("#audit-score"), score.toFixed(2));
  $("#score-ring").className = `score-ring ${widthClass(score * 20).replace("w-", "score-")}`;
  text($("#audit-title"), report.todos_ok ? "Todos los gates pasan" : "Hay gates por corregir");
  text($("#audit-note"), `${(report.checks || []).length} controles reproducibles · escala honesta 0–5`);
  const list = $("#audit-checks"); list.replaceChildren();
  (report.checks || []).forEach((check) => {
    const row = document.createElement("div"); row.className = `check${check.ok ? "" : " bad"}`;
    const icon = document.createElement("i"); icon.textContent = check.ok ? "✓" : "!";
    const name = document.createElement("b"); name.textContent = check.nombre;
    const detail = document.createElement("small"); detail.textContent = check.detalle;
    const value = document.createElement("output"); value.textContent = `${Number(check.nota).toFixed(1)}/5`;
    row.append(icon, name, detail, value); list.appendChild(row);
  });
}

async function refreshAll() {
  $("#refresh-all").disabled = true;
  try {
    await Promise.all([loadState(), loadPool(), loadKnowledge()]);
  } catch (error) {
    setConnection(false, "DEGRADED"); toast(error.message, true);
  } finally { $("#refresh-all").disabled = false; }
}

function missionPayload(demo = false) {
  return {
    goal: $("#goal").value.trim(), demo,
    options: {
      provider: $("#provider").value, pool_strategy: $("#pool-strategy").value,
      max_time: Number($("#max-time").value), max_rounds: Number($("#max-rounds").value),
      speculative: Number($("#speculative").value),
      allow_network: $("#allow-network").checked, allow_shell: $("#allow-shell").checked,
    },
  };
}

async function launch(demo = false) {
  const status = $("#form-status"); status.className = "form-status"; text(status, "Validando directiva…");
  try {
    const result = await api("/api/start", { method: "POST", body: JSON.stringify(missionPayload(demo)) });
    text(status, result.status); updateMissionControls(true); toast("Misión aceptada por el control plane");
  } catch (error) { status.className = "form-status error"; text(status, error.message); toast(error.message, true); }
}

function wireActions() {
  $("#mission-form").addEventListener("submit", (event) => { event.preventDefault(); launch(false); });
  $("#demo").addEventListener("click", () => launch(true));
  $("#stop").addEventListener("click", async () => {
    try { const result = await api("/api/stop", { method: "POST", body: "{}" }); toast(result.status); }
    catch (error) { toast(error.message, true); }
  });
  $("#clear-events").addEventListener("click", () => {
    $("#event-feed").innerHTML = '<li class="event empty"><span class="event-icon">·</span><div><b>Vista limpiada</b><small>La historia persistida no fue eliminada.</small></div></li>';
  });
  $("#refresh-all").addEventListener("click", refreshAll);
  $("#preview-route").addEventListener("click", async () => { try { await loadPool(); toast("Ruta simulada sin llamada upstream"); } catch (error) { toast(error.message, true); } });
  $("#route-kind").addEventListener("change", () => loadPool().catch((error) => toast(error.message, true)));
  $("#run-scout").addEventListener("click", async () => {
    const button = $("#run-scout"); button.disabled = true; text(button, "Explorando…");
    try {
      const result = await api("/api/scout", { method: "POST", body: JSON.stringify({ query: $("#scout-query").value.trim(), limit: 6 }) });
      renderKnowledge({ cards: [], cards_total: Number($("#card-count").textContent || 0), ecosystem: result });
      toast(`Radar: ${result.scan.added.length} proyectos nuevos; código ejecutado: no`);
      await loadKnowledge();
    } catch (error) { toast(error.message, true); }
    finally { button.disabled = false; text(button, "Explorar GitHub"); }
  });
  $("#run-audit").addEventListener("click", async () => {
    const button = $("#run-audit"); button.disabled = true; text(button, "Midiendo…");
    try { renderAudit(await api("/api/audit")); toast("Auditoría reproducible completada"); }
    catch (error) { toast(error.message, true); }
    finally { button.disabled = false; text(button, "Ejecutar auditoría"); }
  });
}

function wireNavigation() {
  const links = [...document.querySelectorAll(".nav-link")];
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      links.forEach((link) => link.classList.toggle("active", link.getAttribute("href") === `#${entry.target.id}`));
      const titles = { overview: "Estado del sistema", routing: "Inteligencia de ruta", ecosystem: "Radar abierto", assurance: "Assurance verificable" };
      text($("#page-title"), titles[entry.target.id]);
    });
  }, { rootMargin: "-35% 0px -55% 0px" });
  document.querySelectorAll(".view-section").forEach((section) => observer.observe(section));
}

function tick() {
  text($("#clock"), `${new Date().toISOString().slice(11, 19)} UTC`);
}

document.addEventListener("DOMContentLoaded", async () => {
  wireActions(); wireNavigation(); tick(); window.setInterval(tick, 1000);
  await refreshAll(); connectEvents();
});
