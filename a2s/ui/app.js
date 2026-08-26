"use strict";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  running: false,
  eventCount: 0,
  iterations: 0,
  source: null,
  chatBusy: false,
  activeView: "overview",
  selectedArtifact: null,
  recursos: { q: "", cat: "" },
};

/* ------------------------------------------------------------------ */
/* Utilidades                                                          */
/* ------------------------------------------------------------------ */

function widthClass(percent) {
  const bounded = Math.max(0, Math.min(100, Number(percent) || 0));
  return `w-${Math.round(bounded / 5) * 5}`;
}

function text(node, value) {
  if (node) node.textContent = value == null ? "—" : String(value);
}

function el(tag, className, parent) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (parent) parent.appendChild(node);
  return node;
}

function toast(message, error = false) {
  const node = document.createElement("div");
  node.className = `toast${error ? " error" : ""}`;
  node.textContent = message;
  $("#toast-region").appendChild(node);
  window.setTimeout(() => node.remove(), 4200);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  if (response.status === 401) {
    const token = window.prompt("Control Plane protegido. Introduce el token emitido por a2s token:");
    if (!token) throw new Error("Autenticación requerida");
    const login = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    if (!login.ok) throw new Error("Token inválido o expirado");
    return api(path, options);
  }
  let data = {};
  try { data = await response.json(); } catch (_) { data = {}; }
  if (!response.ok) throw new Error(data.error || data.status || `HTTP ${response.status}`);
  return data;
}

function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function fmtSize(bytes) {
  if (!bytes && bytes !== 0) return "—";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0; let n = Number(bytes) || 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
}

function fmtTime(iso) {
  return (iso || "").slice(11, 19) || "";
}

function fmtMtime(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleString();
}

/* ------------------------------------------------------------------ */
/* Conexión / estado                                                   */
/* ------------------------------------------------------------------ */

function setConnection(ok, label = "ONLINE") {
  const pill = $("#system-pill");
  pill.classList.toggle("ok", ok);
  pill.classList.toggle("bad", !ok);
  text(pill.querySelector("span"), label);
}

function setChatState(label, cls = "") {
  const dot = $("#chat-dot");
  const st = $("#chat-state");
  dot.className = "";
  if (cls) $("#chat-status")?.classList;
  const wrap = dot.parentElement;
  wrap.classList.remove("busy", "off");
  if (cls) wrap.classList.add(cls);
  if (st) text(st, label);
}

function updateMissionControls(running) {
  state.running = running;
  if ($("#start")) $("#start").disabled = running;
  if ($("#demo")) $("#demo").disabled = running;
  if ($("#stop")) $("#stop").disabled = !running;
  text($("#metric-state"), running ? "RUNNING" : "IDLE");
  text($("#metric-state-note"), running ? "Agente ejecutando la directiva" : "Listo para recibir objetivo");
  $("#metric-state").closest(".metric").classList.toggle("primary", running);
}

/* ------------------------------------------------------------------ */
/* Navegación por pestañas (pills)                                     */
/* ------------------------------------------------------------------ */

function switchView(name) {
  state.activeView = name;
  $$(".pill").forEach((p) => p.classList.toggle("active", p.dataset.view === name));
  $$(".view-panel").forEach((v) => v.classList.toggle("active", v.id === name));
  if (name === "results") loadArtifacts().catch((e) => toast(e.message, true));
  if (name === "routing") loadPool().catch((e) => toast(e.message, true));
  if (name === "ecosystem") loadKnowledge().catch((e) => toast(e.message, true));
  if (name === "recursos") loadRecursos().catch((e) => toast(e.message, true));
}

/* ------------------------------------------------------------------ */
/* Eventos SSE                                                         */
/* ------------------------------------------------------------------ */

const EVENT_META = {
  job_start: ["✎", "Trabajo en paralelo", "step_start"],
  job_done: ["■", "Trabajo terminado", "success"],
  studio_progress: ["✎", "Proceso en vivo", "step_start"],
  artifact_ready: ["⬚", "Artefacto listo", "success"],
  run_start: ["▶", "Misión iniciada", "step_start"],
  capability_protocol: ["◉", "Capacidades adaptativas", "replan"],
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
  step_done: ["✓", "Paso completado", "success"],
  growth_cycle: ["🌱", "Crecimiento: estudio autónomo", "success"],
  pcb_admit: ["#", "PCB admitido", "step_start"],
  pcb_resume: ["↻", "Colas reanudadas", "replan"],
};

function eventDetail(event) {
  if (event.event === "run_start") return `${event.goal || ""} · proveedor ${event.provider || "—"}`;
  if (event.event === "capability_protocol") {
    const protocol = event.protocol || {};
    return `${(protocol.need_types || []).join(", ")} · ${(protocol.capabilities || []).map((cap) => cap.label).join(", ")}`;
  }
  if (event.event === "step_start") return `${event.goal || ""} · ${event.approach || ""}`;
  if (event.event === "evaluation") return `${event.goal || ""} · ${event.verdict || ""} · ${event.reason || ""}`;
  if (event.event === "goal_check") return `${event.achieved ? "CUMPLIDO" : "pendiente"} · ${event.reason || ""}`;
  if (event.event === "replan" || event.event === "plan_created") return (event.steps || []).join(" → ");
  if (event.event === "failure_handled") return event.countermeasure || "";
  if (event.event === "run_end" || event.event === "operator_stop") return event.note || "";
  if (event.event === "ecosystem_scan") return `${event.added || 0} nuevos · ${event.total || 0} totales`;
  if (event.event === "step_done") return event.reason || event.status || "";
  if (event.event === "studio_progress") return `${event.percent || 0}% · ${event.note || ""}`;
  return event.note || event.status || event.goal || event.event || "evento";
}

function addEvent(event, scroll = true) {
  if (!event || !event.event) return;
  const feed = $("#event-feed");
  if (feed.querySelector(".empty")) feed.replaceChildren();
  const [icon, title, cls] = EVENT_META[event.event] || ["·", event.event, ""];
  const verdictClass = event.verdict === "success" || event.success ? " success"
    : (event.verdict === "failed" || event.verdict === "blocked" || event.success === false ? " failed" : "");
  const item = el("li", `event ${cls}${verdictClass}`);
  const iconNode = el("span", "event-icon"); iconNode.textContent = icon;
  const content = el("div");
  const heading = el("b"); heading.textContent = title;
  const detail = el("small"); detail.textContent = eventDetail(event).slice(0, 520);
  content.append(heading, detail);
  const stamp = el("time"); stamp.textContent = fmtTime(event.at) || "LIVE";
  item.append(iconNode, content, stamp);
  feed.appendChild(item);
  while (feed.children.length > 220) feed.firstElementChild.remove();
  if (scroll) feed.scrollTop = feed.scrollHeight;
  state.eventCount += 1;

  if (event.event === "run_start") { updateMissionControls(true); setChatState("Trabajando…", "busy"); }
  if (event.event === "capability_protocol") renderProtocol(event.protocol || {});
  if (event.event === "evaluation") {
    state.iterations += 1;
    text($("#metric-iterations"), state.iterations);
  }
  if (event.event === "run_end") {
    updateMissionControls(false);
    text($("#metric-state"), event.success ? "VERIFIED" : "PARTIAL");
    text($("#metric-state-note"), event.success ? "Objetivo verificado" : "Estado persistido y reanudable");
    toast(event.success ? "Misión verificada correctamente" : "Misión cerrada sin verificación completa", !event.success);
    setChatState("Listo", "");
    // Refrescar resultados automáticamente cuando termine una misión.
    loadArtifacts().catch(() => {});
    if (event.success) {
      appendAssistantBubble("✔ Misión verificada. Revisa la pestaña **Resultados** para ver los archivos que produje.");
    }
  }

  // Eventos de chat
  if (event.event === "chat_typing") { showTyping(); setChatState("Escribiendo…", "busy"); }
  if (event.event === "chat_message") {
    removeTyping();
    appendBubble(event.role || "assistant", event.content || "", { error: event.error, mission: event.mission_id });
    setChatState("Listo", "");
  }
  if (event.event === "chat_idle") { removeTyping(); state.chatBusy = false; setChatState("Listo", ""); }
  if (event.event === "chat_cleared") { renderChatHistory([]); renderProtocol({}); }
  if (event.event === "job_start") {
    setChatState("Creando/buscando…", "busy");
  }
  if (event.event === "job_done") {
    loadArtifacts(true).catch(() => {});
    if (event.ok) {
      appendAssistantBubble("Listo. Ya tienes archivos nuevos en **Resultados**.");
    } else if (event.error) {
      appendAssistantBubble(`El trabajo se detuvo: ${event.error}`);
    }
  }
  if (event.event === "studio_progress") {
    updateStudioProcess(event);
    setChatState(`Creando ${event.percent || 0}%`, "busy");
  }
  if (event.event === "artifact_ready") {
    loadArtifacts(true).then(() => {
      const arts = event.artifacts || [];
      const pdf = arts.find((p) => String(p).toLowerCase().endsWith(".pdf"));
      const html = arts.find((p) => String(p).toLowerCase().endsWith(".html"));
      if (pdf) selectArtifact(pdf);
      else if (html) selectArtifact(html);
    }).catch(() => {});
    switchView("results");
  }
  if (event.event === "operator_stop") {
    updateMissionControls(false);
    setChatState("Listo", "");
  }
}

function connectEvents() {
  if (state.source) state.source.close();
  const source = new EventSource("/api/events");
  state.source = source;
  source.onopen = () => setConnection(true);
  source.onmessage = (message) => {
    try { addEvent(JSON.parse(message.data)); } catch (_) { /* evento malformado */ }
  };
  source.onerror = () => {
    setConnection(false, "RECONNECTING");
    source.close();
    window.setTimeout(connectEvents, 2500);
  };
}

async function fireAction(id, topic) {
  const spec = (state.actions || []).find((item) => item.id === id) || {};
  let chosen = topic || "";
  if (!chosen && spec.ask) {
    chosen = window.prompt(spec.ask, spec.topic || "") || "";
    if (!chosen.trim()) return;
  }
  try {
    const result = await api("/api/action", {
      method: "POST",
      body: JSON.stringify({ id, topic: chosen }),
    });
    toast(result.message || "Hecho");
    if (result.view) {
      switchView(result.view);
      if (result.view === "results") loadArtifacts(true).catch(() => {});
    }
    if (result.pcb) {
      text($("#metric-pcb"), String((result.pcb.ready || 0) + (result.pcb.running || 0)));
      text($("#metric-pcb-note"),
        `${result.pcb.ready || 0} en espera · ${result.pcb.parked || 0} pausados`);
    }
    appendAssistantBubble(result.message || spec.title || id);
  } catch (error) {
    toast(error.message, true);
  }
}

function renderActions(actions) {
  const board = $("#action-board");
  if (!board) return;
  state.actions = actions || [];
  board.replaceChildren();
  state.actions.forEach((item) => {
    const btn = el("button", "action-card");
    btn.type = "button";
    btn.dataset.action = item.id;
    const title = el("b"); title.textContent = item.title;
    const blurb = el("small"); blurb.textContent = item.blurb;
    const go = el("span", "go"); go.textContent = "PULSAR";
    btn.append(title, blurb, go);
    btn.addEventListener("click", () => fireAction(item.id));
    board.appendChild(btn);
  });
}

async function loadActions() {
  try {
    const data = await api("/api/actions");
    renderActions(data.actions || []);
  } catch (_) {
    renderActions([]);
  }
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
  if (data.pcb) {
    text($("#metric-pcb"), String((data.pcb.ready || 0) + (data.pcb.running || 0)));
    text($("#metric-pcb-note"),
      `${data.pcb.ready || 0} ready · ${data.pcb.parked || 0} parked · ${data.pcb.applied || 0} mejoras`);
  }
}

/* ------------------------------------------------------------------ */
/* Chat                                                                */
/* ------------------------------------------------------------------ */

function renderProtocol(protocol) {
  const chips = $("#protocol-chips");
  if (!protocol || !protocol.capabilities) {
    text($("#protocol-types"), "clasifica cada necesidad");
    if (chips) chips.innerHTML = "<span>selección mínima pertinente</span>";
    return;
  }
  text($("#protocol-types"), (protocol.need_types || []).join(" · ") || "adaptativo");
  if (!chips) return;
  chips.replaceChildren();
  protocol.capabilities.slice(0, 5).forEach((capability) => {
    const chip = el("span");
    chip.textContent = `✓ ${capability.label || capability.id}`;
    chip.title = capability.purpose || "";
    chips.appendChild(chip);
  });
}

function renderChat(history) {
  const thread = $("#chat-thread");
  thread.replaceChildren();
  // Mensaje de bienvenida siempre.
  appendAssistantBubble("Hola. Soy **Aegis**. Pulsa un botón o escríbeme como se lo dirías a una persona. No hace falta terminal ni saber programar.");
  (history || []).forEach((m) => appendBubble(m.role, m.content, { error: m.error, mission: m.mission_id, at: m.at }));
  scrollChat();
}

function renderChatHistory(history) { renderChat(history); }

function appendBubble(role, content, opts = {}) {
  const thread = $("#chat-thread");
  // Quitar saludo inicial si ya hay mensajes reales.
  const welcome = thread.querySelector(".chat-msg.assistant:first-child .quick-row");
  if (welcome && thread.children.length === 1) { /* dejar welcome */ }
  const wrap = el("div", `chat-msg ${role === "user" ? "user" : "assistant"}`);
  const bubble = el("div", `bubble${opts.error ? " error" : ""}`);
  bubble.innerHTML = renderRich(content);
  wrap.appendChild(bubble);
  if (opts.at) {
    const t = el("time"); t.textContent = fmtTime(opts.at); t.style.cssText = "display:block;margin-top:4px;opacity:.55;font-size:9px;";
    bubble.appendChild(t);
  }
  thread.appendChild(wrap);
  scrollChat();
}

function appendAssistantBubble(content) { appendBubble("assistant", content); }

function renderRich(text) {
  // Markdown mínimo + secciones auditables del protocolo Aegis.
  let s = escapeHtml(text);
  s = s.replace(/\[(CAPACIDADES ACTIVADAS|RAZONAMIENTO RESUMIDO|RESPUESTA PRINCIPAL|DATOS ADICIONALES|SIGUIENTES PASOS)\]/g,
    '<span class="response-section">$1</span>');
  s = s.replace(/```([\s\S]*?)```/g, (_, code) => `<pre>${code}</pre>`);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  s = s.replace(/(https?:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer" style="color:var(--cyan);text-decoration:underline">$1</a>');
  s = s.replace(/\n/g, "<br>");
  return s;
}

function showTyping() {
  removeTyping();
  const thread = $("#chat-thread");
  const wrap = el("div", "chat-msg assistant");
  const bubble = el("div", "bubble");
  const t = el("span", "typing");
  t.innerHTML = "<i></i><i></i><i></i>";
  bubble.appendChild(t);
  wrap.appendChild(bubble);
  wrap.id = "chat-typing";
  thread.appendChild(wrap);
  scrollChat();
}

function removeTyping() {
  const node = $("#chat-typing");
  if (node) node.remove();
}

function scrollChat() {
  const t = $("#chat-thread");
  if (t) t.scrollTop = t.scrollHeight;
}

async function sendChat(message) {
  message = (message || "").trim();
  if (!message) return;
  appendBubble("user", message);
  $("#chat-input").value = "";
  autoGrowChat();
  showTyping();
  setChatState("En bandeja…", "busy");
  try {
    await api("/api/chat", { method: "POST", body: JSON.stringify({ message }) });
    // No bloqueamos el compositor: se puede seguir hablando.
    state.chatBusy = false;
  } catch (e) {
    removeTyping();
    appendBubble("assistant", `No pude enviar el mensaje: ${e.message}`, { error: true });
    setChatState("Listo", "");
    state.chatBusy = false;
  }
}

async function loadChat() {
  try {
    const data = await api("/api/chat");
    renderChat(data.history || []);
    renderProtocol(data.protocol || {});
  } catch (e) {
    // el chat puede no estar disponible; no es crítico
  }
}

function autoGrowChat() {
  const ta = $("#chat-input");
  if (!ta) return;
  ta.style.height = "auto";
  ta.style.height = Math.min(160, ta.scrollHeight) + "px";
}

/* ------------------------------------------------------------------ */
/* Misión                                                              */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/* Pool / routing                                                      */
/* ------------------------------------------------------------------ */

function quotaClass(value) {
  if (value === "exhausted") return "bad";
  if (value === "approaching_limit") return "warn";
  return "";
}

function renderPool(data) {
  const status = data.status || {};
  const preview = data.preview || {};
  text($("#metric-endpoints"), status.totals?.endpoints_active || 0);
  const omni = (status.endpoints || []).find((endpoint) => endpoint.name === "omniroute");
  text($("#metric-pool-note"), omni
    ? `OmniRoute ${omni.active && !omni.circuit_open ? "supervisado · gateway online" : "recuperándose"}`
    : `${status.totals?.total_calls || 0} llamadas · núcleo local activo`);
  text($("#routing-strategy"), status.strategy || "—");
  const list = $("#provider-list");
  list.replaceChildren();
  (status.endpoints || []).forEach((endpoint) => {
    const row = el("div", "provider");
    const isOmni = endpoint.name === "omniroute";
    const name = el("div", "provider-name");
    const dot = el("i"); if (!endpoint.active || endpoint.circuit_open) dot.className = "down";
    const nameText = el("b"); nameText.textContent = isOmni ? "OmniRoute · supervisado" : endpoint.name;
    name.append(dot, nameText);
    const model = el("div", "provider-model");
    model.textContent = isOmni ? `${endpoint.model || "auto"} · gateway local`
      : (endpoint.model || (endpoint.role === "fallback_only" ? "núcleo determinista" : "sin modelo"));
    const tier = el("small");
    tier.textContent = isOmni ? (endpoint.active && !endpoint.circuit_open ? "AUTO · GATEWAY ONLINE" : "RECUPERANDO")
      : (endpoint.role === "fallback_only" ? "FALLBACK" : String(endpoint.cost_tier || "—").toUpperCase());
    const quota = el("div");
    const usage = endpoint.rpm_effective > 0 ? Math.min(100, (endpoint.window_used / endpoint.rpm_effective) * 100) : 0;
    const quotaText = el("small");
    quotaText.textContent = endpoint.rpm_effective > 0 ? `${endpoint.window_used}/${endpoint.rpm_effective} RPM` : "CUOTA UNKNOWN";
    const quotaTrack = el("div", "quota"); const quotaFill = el("i"); quotaFill.className = widthClass(usage); quotaTrack.appendChild(quotaFill);
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
  const bars = $("#factor-bars"); bars.replaceChildren();
  Object.entries(selected?.factors || {}).forEach(([key, value]) => {
    const row = el("div", `factor${key === "quota_risk" ? " negative" : ""}`);
    const label = el("label"); label.textContent = key.replace("_", " ");
    const track = el("div", "factor-track");
    const fill = el("i"); fill.className = widthClass(Number(value) * 100); track.appendChild(fill);
    const output = el("output"); output.textContent = Number(value).toFixed(2);
    row.append(label, track, output); bars.appendChild(row);
  });
  const body = $("#route-table"); body.replaceChildren();
  rows.forEach((row) => {
    const tr = el("tr"); if (row.selected) tr.className = "selected";
    const reason = (row.reasons || []).join(", ") || (row.selected ? "mejor utilidad" : "elegible");
    [row.name, row.model || "—"].forEach((value) => { const td = el("td"); td.textContent = value; tr.appendChild(td); });
    const eligible = el("td");
    const eChip = el("span", `status-chip${row.eligible ? "" : " bad"}`); eChip.textContent = row.eligible ? "ELIGIBLE" : "BLOCKED"; eligible.appendChild(eChip);
    const quota = el("td");
    const qChip = el("span", `status-chip ${quotaClass(row.quota_state)}`); qChip.textContent = row.quota_state; quota.appendChild(qChip);
    const score = el("td"); score.textContent = Number(row.utility || 0).toFixed(3);
    const why = el("td"); why.textContent = reason;
    tr.append(eligible, quota, score, why); body.appendChild(tr);
  });
}

async function loadPool() {
  const kind = $("#route-kind").value;
  renderPool(await api(`/api/pool?kind=${encodeURIComponent(kind)}`));
}

/* ------------------------------------------------------------------ */
/* Conocimiento / radar                                                */
/* ------------------------------------------------------------------ */

function renderKnowledge(data) {
  const ecosystem = data.ecosystem || {};
  text($("#card-count"), data.cards_total || 0);
  text($("#project-count"), ecosystem.total || 0);
  const projects = $("#project-list"); projects.replaceChildren();
  (ecosystem.projects || []).forEach((project) => {
    const row = el("article", "project");
    const fit = el("div", "fit-score"); fit.textContent = project.fit_score;
    const main = el("div");
    const title = el("h3"); const link = el("a");
    link.href = project.url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = project.repo; title.appendChild(link);
    const desc = el("p"); desc.textContent = project.description || "Sin descripción pública.";
    const lessons = el("div", "lesson-list");
    (project.lessons || []).forEach((lesson) => { const span = el("span"); span.textContent = lesson; lessons.appendChild(span); });
    main.append(title, desc, lessons);
    const meta = el("div", "project-meta");
    const license = el("b"); license.textContent = project.license;
    meta.append(license, el("br"), document.createTextNode(`★ ${project.stars || 0}`), el("br"), document.createTextNode(project.language || "—"));
    row.append(fit, main, meta); projects.appendChild(row);
  });
  const cards = $("#card-list"); cards.replaceChildren();
  (data.cards || []).slice().reverse().forEach((card) => {
    const row = el("article", "knowledge-card");
    const title = el("h3"); title.textContent = card.repo;
    const summary = el("p"); summary.textContent = card.summary;
    const meta = el("small"); meta.textContent = `${card.license} · usos ${card.used} · éxitos ${card.wins}`;
    row.append(title, summary, meta); cards.appendChild(row);
  });
  if (!(data.cards || []).length) cards.innerHTML = '<p class="empty-copy">Aún no hay fichas.</p>';
}

async function loadKnowledge() { renderKnowledge(await api("/api/knowledge")); }

/* ------------------------------------------------------------------ */
/* Recursos (catálogo curado del operador)                             */
/* ------------------------------------------------------------------ */

async function loadRecursos() {
  const params = new URLSearchParams();
  if (state.recursos.q) params.set("q", state.recursos.q);
  if (state.recursos.cat) params.set("cat", state.recursos.cat);
  renderRecursos(await api(`/api/recursos?${params.toString()}`));
}

function renderRecursos(data) {
  text($("#recursos-total"), data.total);
  text($("#recursos-count"), (data.recursos || []).length);
  const stamp = $("#recursos-check-stamp");
  if (stamp) {
    const ck = data.check;
    stamp.textContent = ck
      ? `último check ${String(ck.at || "").slice(5, 16)} · ${ck.ok}/${ck.total} ok`
      : "sin chequeo todavía (a2s recursos --check)";
  }
  const cats = $("#recursos-cats");
  cats.replaceChildren();
  const chip = (label, value) => {
    const node = el("button", "chip" + (state.recursos.cat === value ? " active" : ""), cats);
    node.type = "button";
    node.textContent = label;
    node.addEventListener("click", () => {
      state.recursos.cat = value;
      loadRecursos().catch((e) => toast(e.message, true));
    });
  };
  chip(`Todas (${data.total})`, "");
  for (const c of data.categorias) chip(`${c.nombre} (${c.count})`, c.id);

  const list = $("#recursos-list");
  list.replaceChildren();
  if (!data.recursos.length) {
    const p = el("p", "empty-copy", list);
    p.textContent = "Sin resultados: prueba «vpn», «ghidra», «pentest» o cambia de categoría.";
    return;
  }
  for (const r of data.recursos) {
    const item = el("article", "recurso", list);
    const head = el("div", "recurso-head", item);
    if (r.url) {
      const a = document.createElement("a");
      a.className = "recurso-name";
      a.href = r.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = r.nombre;
      head.appendChild(a);
    } else {
      const s = el("span", "recurso-name", head);
      s.textContent = r.nombre;
    }
    if (r.tags && r.tags.includes("advertido")) {
      const warn = el("span", "tag warn", head);
      warn.textContent = "ADVERTIDO";
    }
    if (r.custom) {
      const propio = el("span", "tag propio", head);
      propio.textContent = "PROPIO";
    }
    const ck = data.check && data.check.results && data.check.results[r.id];
    if (ck && ck.estado && ck.estado !== "sin enlace") {
      const dot = el("span", "tag ck" + (ck.ok ? " ok" : " fail"), head);
      dot.title = `${ck.estado} · ${String(data.check.at || "").slice(0, 16)}`;
      dot.textContent = ck.ok ? "✔" : "✗";
    }
    const tag = el("span", "tag cat", head);
    tag.textContent = (r.categoria || "").toUpperCase();
    const desc = el("p", "", item);
    desc.textContent = r.desc;
    if (r.url) {
      const url = el("small", "recurso-url", item);
      url.textContent = r.url;
    }
  }
}

/* ------------------------------------------------------------------ */
/* Assurance                                                           */
/* ------------------------------------------------------------------ */

function renderAudit(report) {
  const score = Number(report.nota_medible || 0);
  text($("#audit-score"), score.toFixed(2));
  $("#score-ring").className = `score-ring ${widthClass(score * 20).replace("w-", "score-")}`;
  text($("#audit-title"), report.todos_ok ? "Todos los gates pasan" : "Hay gates por corregir");
  text($("#audit-note"), `${(report.checks || []).length} controles reproducibles · escala honesta 0–5`);
  const list = $("#audit-checks"); list.replaceChildren();
  (report.checks || []).forEach((check) => {
    const row = el("div", `check${check.ok ? "" : " bad"}`);
    const icon = el("i"); icon.textContent = check.ok ? "✓" : "!";
    const name = el("b"); name.textContent = check.nombre;
    const detail = el("small"); detail.textContent = check.detalle;
    const value = el("output"); value.textContent = `${Number(check.nota).toFixed(1)}/5`;
    row.append(icon, name, detail, value); list.appendChild(row);
  });
}

/* ------------------------------------------------------------------ */
/* Resultados / artefactos                                             */
/* ------------------------------------------------------------------ */

function updateStudioProcess(event) {
  const percent = Math.max(0, Math.min(100, Number(event.percent) || 0));
  text($("#studio-percent"), `${percent}%`);
  const bar = $("#studio-bar");
  if (bar) bar.className = widthClass(percent);
  text($("#studio-note"), event.note || "en curso");
  const log = $("#studio-log");
  if (!log) return;
  const item = el("li");
  item.textContent = `${percent}% · ${event.note || ""}`;
  log.appendChild(item);
  while (log.children.length > 40) log.firstElementChild.remove();
  log.scrollTop = log.scrollHeight;
}

const ARTIFACT_ICONS = {
  image: "IMG", pdf: "PDF", html: "WEB", text: "TXT", audio: "AUD",
  video: "VID", archive: "ZIP", binary: "BIN",
};

async function loadArtifacts(silent = false) {
  try {
    const data = await api("/api/artifacts");
    const items = data.artifacts || [];
    text($("#metric-artifacts"), items.length);
    text($("#metric-artifacts-note"), "archivos en el workspace");
    text($("#artifact-count"), items.length);
    const list = $("#artifact-list");
    list.replaceChildren();
    if (!items.length) {
      list.innerHTML = '<p class="empty-copy">Aún no hay archivos. Lanza una misión o pídeme algo por el chat.</p>';
      return;
    }
    items.forEach((a) => {
      const btn = el("button", `artifact-row${state.selectedArtifact === a.path ? " active" : ""}`);
      btn.dataset.path = a.path;
      const ico = el("span", `artifact-ico ${a.kind}`); ico.textContent = ARTIFACT_ICONS[a.kind] || "FILE";
      const main = el("div", "artifact-main");
      const name = el("span", "artifact-name"); name.textContent = a.path;
      const meta = el("span", "artifact-meta");
      meta.textContent = `${fmtSize(a.size)} · ${fmtMtime(a.mtime)}`;
      main.append(name, meta);
      btn.append(ico, main);
      btn.addEventListener("click", () => selectArtifact(a.path));
      list.appendChild(btn);
    });
    if (state.selectedArtifact) {
      // refrescar visor si sigue seleccionado
      const exists = items.some((a) => a.path === state.selectedArtifact);
      if (exists) selectArtifact(state.selectedArtifact);
      else clearViewer();
    }
  } catch (e) {
    if (!silent) toast(e.message, true);
  }
}

function clearViewer() {
  state.selectedArtifact = null;
  text($("#viewer-title"), "Sin selección");
  const dl = $("#viewer-download"); dl.hidden = true; dl.removeAttribute("href");
  $("#artifact-viewer").replaceChildren();
  $("#artifact-viewer").innerHTML = '<p class="empty-copy">Selecciona un archivo para previsualizarlo.</p>';
}

async function selectArtifact(path) {
  state.selectedArtifact = path;
  $$(".artifact-row").forEach((r) => r.classList.toggle("active", r.dataset.path === path));
  text($("#viewer-title"), path);
  const viewer = $("#artifact-viewer");
  viewer.replaceChildren();
  const loading = el("p", "loading"); loading.textContent = "Cargando…"; viewer.appendChild(loading);
  try {
    const data = await api(`/api/artifact?path=${encodeURIComponent(path)}`);
    renderViewer(data);
  } catch (e) {
    viewer.replaceChildren();
    const p = el("p", "empty-copy"); p.textContent = `No pude abrir este archivo: ${e.message}`;
    viewer.appendChild(p);
  }
}

function renderViewer(data) {
  const viewer = $("#artifact-viewer");
  viewer.replaceChildren();
  const dl = $("#viewer-download");
  dl.hidden = !data.download_url;
  if (data.download_url) dl.href = data.download_url;

  if (data.kind === "image" && data.raw_url) {
    const img = el("img");
    img.src = data.raw_url;
    img.alt = data.name;
    img.addEventListener("click", () => openMediaModal(img.src, "image"));
    viewer.appendChild(img);
    return;
  }
  if ((data.kind === "pdf" || data.kind === "html") && data.raw_url) {
    const frame = el("div", "pdf-frame");
    const object = el(data.kind === "pdf" ? "object" : "iframe");
    if (data.kind === "pdf") {
      object.setAttribute("data", data.raw_url);
      object.setAttribute("type", "application/pdf");
      const iframe = el("iframe");
      iframe.src = data.raw_url;
      object.appendChild(iframe);
    } else {
      object.src = data.raw_url;
      object.title = data.name || "HTML";
    }
    const actions = el("div", "viewer-actions");
    const full = el("button", "btn btn-secondary");
    full.textContent = "Pantalla completa";
    full.addEventListener("click", () => openMediaModal(data.raw_url, data.kind));
    actions.appendChild(full);
    frame.append(object, actions);
    viewer.appendChild(frame);
    return;
  }
  if (data.kind === "audio" && data.raw_url) {
    const audio = el("audio");
    audio.controls = true; audio.src = data.raw_url;
    viewer.appendChild(audio);
    return;
  }
  if (data.kind === "video" && data.raw_url) {
    const video = el("video");
    video.controls = true; video.src = data.raw_url;
    viewer.appendChild(video);
    return;
  }
  if (data.kind === "text") {
    if (data.name.toLowerCase().endsWith(".md") || data.name.toLowerCase().endsWith(".markdown")) {
      const div = el("div", "md-render");
      div.innerHTML = renderRich(data.text || "");
      viewer.appendChild(div);
    } else {
      const pre = el("pre");
      pre.textContent = data.text || "";
      viewer.appendChild(pre);
    }
    return;
  }
  // Binario / archivo no previsualizable
  const note = el("div", "binary-note");
  const big = el("span", "big"); big.textContent = "📦";
  const p = el("p"); p.textContent = `${data.name} · ${fmtSize(data.size)}`;
  const p2 = el("p"); p2.textContent = "No se puede previsualizar en el navegador. Descárgalo para abrirlo.";
  note.append(big, p, p2);
  viewer.appendChild(note);
}

function openMediaModal(src, kind) {
  const modal = $("#media-modal");
  const stage = $("#media-stage");
  stage.replaceChildren();
  if (kind === "image") {
    const img = el("img"); img.src = src; img.alt = ""; stage.appendChild(img);
  } else if (kind === "video") {
    const v = el("video"); v.controls = true; v.autoplay = true; v.src = src; stage.appendChild(v);
  } else if (kind === "pdf") {
    const f = el("iframe"); f.src = src; stage.appendChild(f);
  }
  modal.hidden = false;
}

function closeMediaModal() {
  $("#media-modal").hidden = true;
  $("#media-stage").replaceChildren();
}

/* ------------------------------------------------------------------ */
/* Refresco global                                                     */
/* ------------------------------------------------------------------ */

async function refreshAll() {
  $("#refresh-all").disabled = true;
  try {
    await Promise.all([
      loadState(),
      loadActions().catch(() => {}),
      loadPool().catch(() => {}),
      loadKnowledge().catch(() => {}),
      loadArtifacts(true),
    ]);
  } catch (error) {
    setConnection(false, "DEGRADED"); toast(error.message, true);
  } finally { $("#refresh-all").disabled = false; }
}

/* ------------------------------------------------------------------ */
/* Cableado de eventos UI                                              */
/* ------------------------------------------------------------------ */

function wireActions() {
  // Misión
  $("#mission-form").addEventListener("submit", (event) => { event.preventDefault(); launch(false); });
  $("#demo").addEventListener("click", () => launch(true));
  $("#stop").addEventListener("click", async () => {
    try { const result = await api("/api/stop", { method: "POST", body: "{}" }); toast(result.status); }
    catch (error) { toast(error.message, true); }
  });
  $("#clear-events").addEventListener("click", () => {
    $("#event-feed").innerHTML = '<li class="event empty"><span class="event-icon">·</span><div><b>Vista limpiada</b><small>La historia persistida no fue eliminada.</small></div></li>';
  });

  // Chat
  $("#chat-form").addEventListener("submit", (e) => { e.preventDefault(); sendChat($("#chat-input").value); });
  $("#chat-input").addEventListener("input", autoGrowChat);
  $("#chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat($("#chat-input").value); }
  });
  const stopBtn = $("#chat-stop");
  if (stopBtn) {
    stopBtn.addEventListener("click", async () => {
      try {
        const result = await api("/api/stop", { method: "POST", body: "{}" });
        toast(result.status);
      } catch (error) { toast(error.message, true); }
    });
  }
  $("#chat-clear").addEventListener("click", async () => {
    if (!window.confirm("¿Reiniciar la conversación? Se borrará el historial del chat.")) return;
    try { await api("/api/chat/clear", { method: "POST" }); } catch (e) { toast(e.message, true); }
  });
  $$(".quick").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.action) fireAction(b.dataset.action);
    else sendChat(b.dataset.text);
  }));
  const hideCoach = $("#coach-hide");
  if (hideCoach) {
    hideCoach.addEventListener("click", () => $("#coach")?.classList.add("hidden"));
  }

  // Navegación por pestañas
  $$(".pill").forEach((p) => p.addEventListener("click", () => switchView(p.dataset.view)));

  // Pool
  $("#refresh-all").addEventListener("click", refreshAll);
  $("#preview-route").addEventListener("click", async () => { try { await loadPool(); toast("Ruta simulada sin llamada upstream"); } catch (error) { toast(error.message, true); } });
  $("#route-kind").addEventListener("change", () => loadPool().catch((error) => toast(error.message, true)));

  // Resultados
  $("#refresh-artifacts").addEventListener("click", () => loadArtifacts().catch((e) => toast(e.message, true)));

  // Recursos (catálogo curado)
  const buscarRecursos = $("#recursos-buscar");
  if (buscarRecursos) {
    buscarRecursos.addEventListener("input", () => {
      state.recursos.q = buscarRecursos.value.trim();
      clearTimeout(buscarRecursos._t);
      buscarRecursos._t = setTimeout(() => loadRecursos().catch((e) => toast(e.message, true)), 250);
    });
  }
  // Recursos: formulario de añadir (recursos propios del operador)
  const addRecursos = $("#recursos-add");
  const formRecursos = $("#recursos-form");
  if (addRecursos && formRecursos) {
    addRecursos.addEventListener("click", () => {
      formRecursos.hidden = !formRecursos.hidden;
      if (!formRecursos.hidden) $("#recursos-nombre").focus();
    });
    $("#recursos-cancel").addEventListener("click", () => { formRecursos.hidden = true; });
    formRecursos.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      try {
        const result = await api("/api/recursos", {
          method: "POST",
          body: JSON.stringify({
            nombre: $("#recursos-nombre").value.trim(),
            url: $("#recursos-url").value.trim(),
            cat: $("#recursos-cat").value,
            desc: $("#recursos-desc").value.trim(),
          }),
        });
        toast(`Recurso añadido: ${result.recurso.nombre}`);
        formRecursos.reset();
        formRecursos.hidden = true;
        await loadRecursos();
      } catch (error) { toast(error.message, true); }
    });
  }

  // Modal
  $("#media-close").addEventListener("click", closeMediaModal);
  $("#media-modal").addEventListener("click", (e) => { if (e.target.id === "media-modal") closeMediaModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMediaModal(); });

  // Scout
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

  // Audit
  $("#run-audit").addEventListener("click", async () => {
    const button = $("#run-audit"); button.disabled = true; text(button, "Midiendo…");
    try { renderAudit(await api("/api/audit")); toast("Auditoría reproducible completada"); }
    catch (error) { toast(error.message, true); }
    finally { button.disabled = false; text(button, "Ejecutar auditoría"); }
  });
}

function tick() { text($("#clock"), `${new Date().toISOString().slice(11, 19)} UTC`); }

document.addEventListener("DOMContentLoaded", async () => {
  wireActions();
  tick(); window.setInterval(tick, 1000);
  await refreshAll();
  await loadChat();
  connectEvents();
  // Refresco periódico de artefactos mientras el usuario está en Resultados o hay misión.
  window.setInterval(() => {
    if (state.running || state.activeView === "results") loadArtifacts(true).catch(() => {});
  }, 6000);
});
