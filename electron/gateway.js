/** Gestión del gateway OmniRoute desde Node (sin dependencias).
 *  Usado por el proceso principal de Electron Y testeable con node a secas:
 *  toda la lógica de proceso/salud vive aquí, separada de la ventana. */
"use strict";

const { spawn } = require("child_process");
const http = require("http");
const net = require("net");

const PUERTO = parseInt(process.env.OMNIROUTE_PORT || "20128", 10);
const BASE = `http://127.0.0.1:${PUERTO}`;

/** ¿Hay algo escuchando en el puerto del gateway? (sin dependencias) */
function puertoAbierto(puerto = PUERTO, host = "127.0.0.1") {
  return new Promise((resolve) => {
    const s = net.connect({ host, port: puerto, timeout: 600 });
    s.on("connect", () => { s.destroy(); resolve(true); });
    s.on("error", () => resolve(false));
    s.on("timeout", () => { s.destroy(); resolve(false); });
  });
}

/** GET JSON del gateway (usado para /health, /v1/models, etc.). */
function getJson(path, timeoutMs = 4000) {
  return new Promise((resolve) => {
    const req = http.get(`${BASE}${path}`, { timeout: timeoutMs }, (res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        try { resolve({ status: res.statusCode, json: JSON.parse(body) }); }
        catch (_) { resolve({ status: res.statusCode, json: null, body }); }
      });
    });
    req.on("error", (e) => resolve({ status: 0, error: e.message }));
    req.on("timeout", () => { req.destroy(); resolve({ status: 0, error: "timeout" }); });
  });
}

/** POST JSON al gateway (chat de prueba). */
function postJson(path, payload, timeoutMs = 30000, token = "omniroute-local") {
  return new Promise((resolve) => {
    const data = JSON.stringify(payload);
    const req = http.request(`${BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json",
                 "Authorization": `Bearer ${token}`,
                 "Content-Length": Buffer.byteLength(data) },
      timeout: timeoutMs,
    }, (res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        try { resolve({ status: res.statusCode, json: JSON.parse(body) }); }
        catch (_) { resolve({ status: res.statusCode, body }); }
      });
    });
    req.on("error", (e) => resolve({ status: 0, error: e.message }));
    req.on("timeout", () => { req.destroy(); resolve({ status: 0, error: "timeout" }); });
    req.write(data);
    req.end();
  });
}

/** Arranca `omniroute` como proceso hijo si no hay ya uno en el puerto.
 *  Devuelve {started, child|null, log[]}. */
async function asegurarGateway(log = []) {
  if (await puertoAbierto()) {
    log.push("gateway ya estaba escuchando en :" + PUERTO);
    return { started: false, child: null, log };
  }
  const bin = process.platform === "win32" ? "omniroute.cmd" : "omniroute";
  const child = spawn(bin, [], { stdio: ["ignore", "pipe", "pipe"],
                                env: process.env });
  child.stdout.on("data", (d) => log.push(String(d).trim()));
  child.stderr.on("data", (d) => log.push(String(d).trim()));
  child.on("exit", (code) => log.push(`gateway terminó (exit ${code})`));
  for (let i = 0; i < 40; i++) {                 // hasta ~20s esperando el puerto
    await new Promise((r) => setTimeout(r, 500));
    if (await puertoAbierto()) {
      log.push(`gateway arriba en :${PUERTO} (pid ${child.pid})`);
      return { started: true, child, log };
    }
  }
  log.push("el gateway no abrió el puerto en 20s");
  return { started: false, child, log };
}

module.exports = { PUERTO, BASE, puertoAbierto, getJson, postJson, asegurarGateway };

/* Prueba directa:  node gateway.js  */
if (require.main === module) {
  (async () => {
    const log = [];
    const r = await asegurarGateway(log);
    console.log(log.join("\n"));
    console.log("health:", JSON.stringify(await getJson("/health")).slice(0, 200));
    const chat = await postJson("/v1/chat/completions",
      { model: "auto", messages: [{ role: "user", content: "ping" }] }, 20000);
    console.log("chat:", JSON.stringify(chat).slice(0, 300));
    process.exit(0);
  })();
}
