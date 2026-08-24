import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import {
  appendFileSync, closeSync, existsSync, mkdirSync, openSync, readFileSync,
  rmSync, writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { homedir } from "node:os";
import { request } from "node:http";
import { dirname, join } from "node:path";

const DEFAULT_PORT = 20128;
const require = createRequire(import.meta.url);

function enabled() {
  return String(process.env.A2S_OMNIROUTE || "").trim().toLowerCase() !== "off";
}

function configuredPort() {
  const raw = Number.parseInt(process.env.OMNIROUTE_PORT || String(DEFAULT_PORT), 10);
  return Number.isInteger(raw) && raw > 0 && raw <= 65535 ? raw : DEFAULT_PORT;
}

function endpoint(port) {
  return `http://127.0.0.1:${port}/v1`;
}

function probe(port, timeoutMs = 1_500) {
  return new Promise((resolve) => {
    const headers = { "User-Agent": "A2S/npm (+bundled-omniroute)" };
    const key = String(process.env.A2S_OMNIROUTE_KEY || "").trim();
    if (key) headers.Authorization = `Bearer ${key}`;
    const req = request({
      hostname: "127.0.0.1",
      port,
      path: "/v1/models",
      method: "GET",
      headers,
      timeout: timeoutMs,
    }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => {
        if (body.length < 200_000) body += chunk;
      });
      response.on("end", () => {
        const status = response.statusCode || 0;
        if (status === 401 || status === 403) {
          resolve({ ready: true, usable: false, authRequired: true, status });
          return;
        }
        if (status < 200 || status >= 300) {
          resolve({ ready: false, usable: false, status });
          return;
        }
        try {
          const payload = JSON.parse(body);
          const validCatalog = payload && Array.isArray(payload.data);
          resolve({ ready: validCatalog, usable: validCatalog, status });
        } catch (_) {
          resolve({ ready: false, usable: false, status });
        }
      });
    });
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.on("error", () => resolve({ ready: false, usable: false, status: 0 }));
    req.end();
  });
}

function packageRoot() {
  return dirname(require.resolve("omniroute/package.json"));
}

function serverEntry(root) {
  for (const relative of ["dist/server-ws.mjs", "dist/server.js",
    "app/server-ws.mjs", "app/server.js"]) {
    const candidate = join(root, relative);
    if (existsSync(candidate)) return candidate;
  }
  throw new Error(`runtime publicado de OmniRoute no encontrado en ${root}`);
}

function defaultDataDir() {
  if (process.env.DATA_DIR?.trim()) return process.env.DATA_DIR.trim();
  const home = homedir();
  const legacy = join(home, ".omniroute");
  if (existsSync(legacy)) return legacy;
  if (process.platform === "win32") {
    return join(process.env.APPDATA || join(home, "AppData", "Roaming"), "omniroute");
  }
  if (process.env.XDG_CONFIG_HOME?.trim()) {
    return join(process.env.XDG_CONFIG_HOME.trim(), "omniroute");
  }
  return legacy;
}

function loadEnvFile(path, target) {
  if (!existsSync(path)) return "";
  const content = readFileSync(path, "utf8");
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const at = trimmed.indexOf("=");
    if (at <= 0) continue;
    const key = trimmed.slice(0, at).trim();
    if (target[key] !== undefined) continue;
    target[key] = trimmed.slice(at + 1).trim().replace(/^["']|["']$/g, "");
  }
  return content;
}

function directRuntime(port) {
  const root = packageRoot();
  const entry = serverEntry(root);
  const dataDir = defaultDataDir();
  const envPath = join(dataDir, ".env");
  const env = { ...process.env };
  mkdirSync(dataDir, { recursive: true });
  let envText = loadEnvFile(envPath, env);

  // Replica únicamente el bootstrap imprescindible del CLI. Evita cargar
  // tsx/src (la ruta que puede quedar en deadlock) y nunca reemplaza la clave
  // de una base ya existente.
  if (!env.STORAGE_ENCRYPTION_KEY) {
    const dbPath = join(dataDir, "storage.sqlite");
    if (existsSync(dbPath)) {
      throw new Error(`falta STORAGE_ENCRYPTION_KEY para ${dbPath}`);
    }
    env.STORAGE_ENCRYPTION_KEY = randomBytes(32).toString("hex");
    const separator = envText.trim() ? "\n" : "";
    appendFileSync(envPath,
      `${separator}STORAGE_ENCRYPTION_KEY=${env.STORAGE_ENCRYPTION_KEY}\n`,
      { encoding: "utf8", mode: 0o600 });
    envText += `${separator}STORAGE_ENCRYPTION_KEY=<generated>\n`;
  }

  Object.assign(env, {
    DATA_DIR: dataDir,
    OMNIROUTE_PORT: String(port),
    PORT: String(port),
    DASHBOARD_PORT: String(port),
    API_PORT: String(port),
    HOSTNAME: "127.0.0.1",
    OMNIROUTE_SERVER_HOST: "127.0.0.1",
    NODE_ENV: "production",
    OMNIROUTE_NO_UPDATE_NOTIFIER: "1",
  });
  // La autenticación del Control Plane A²S es independiente y está apagada por
  // defecto. No se inyecta INITIAL_PASSWORD: el gateway actúa como sidecar local.
  delete env.INITIAL_PASSWORD;
  return { root, entry, dataDir, env };
}

function pidPath(dataDir = defaultDataDir()) {
  return join(dataDir, "server", "a2s-direct.json");
}

function managedProcessInfo(dataDir = defaultDataDir(), expectedPort = null) {
  try {
    const info = JSON.parse(readFileSync(pidPath(dataDir), "utf8"));
    if (expectedPort !== null && Number(info.port) !== Number(expectedPort)) return null;
    process.kill(Number(info.pid), 0);
    return info;
  } catch (_) {
    return null;
  }
}

async function enforceNoLogin(port) {
  if (process.env.A2S_OMNIROUTE_LOGIN === "on") return { changed: false, optedOut: true };
  const dataDir = defaultDataDir();
  if (!managedProcessInfo(dataDir, port)) return { changed: false, unmanaged: true };
  const dbPath = join(dataDir, "storage.sqlite");
  if (!existsSync(dbPath)) return { changed: false, missing: true };
  let database;
  try {
    // Node 22+ incluye SQLite. Se silencia sólo su aviso experimental; cualquier
    // error real se conserva. El gateway sigue ligado a loopback.
    const emitWarning = process.emitWarning;
    let DatabaseSync;
    try {
      process.emitWarning = () => {};
      ({ DatabaseSync } = await import("node:sqlite"));
    } finally {
      process.emitWarning = emitWarning;
    }
    database = new DatabaseSync(dbPath);
    database.exec("PRAGMA busy_timeout=5000");
    const current = database.prepare(
      "SELECT value FROM key_value WHERE namespace='settings' AND key='requireLogin'"
    ).get();
    if (current?.value !== "false") {
      database.prepare(
        "INSERT INTO key_value(namespace,key,value) VALUES('settings','requireLogin','false') " +
        "ON CONFLICT(namespace,key) DO UPDATE SET value=excluded.value"
      ).run();
    }
    return { changed: current?.value !== "false" };
  } catch (error) {
    return { changed: false, detail: error.message };
  } finally {
    try { database?.close(); } catch (_) { /* best effort */ }
  }
}

function launchDirect(port) {
  return new Promise((resolve) => {
    let runtime;
    try {
      runtime = directRuntime(port);
    } catch (error) {
      resolve({ ok: false, detail: error.message });
      return;
    }
    mkdirSync(join(runtime.dataDir, "server"), { recursive: true });
    const logPath = join(runtime.dataDir, "a2s-omniroute.log");
    let logFd;
    try {
      logFd = openSync(logPath, "a", 0o600);
      const child = spawn(process.execPath, [runtime.entry], {
        cwd: dirname(runtime.entry),
        env: runtime.env,
        stdio: ["ignore", logFd, logFd],
        detached: true,
        windowsHide: true,
      });
      child.once("error", (error) => resolve({ ok: false, detail: error.message }));
      child.once("spawn", () => {
        writeFileSync(pidPath(runtime.dataDir), JSON.stringify({
          pid: child.pid,
          port,
          startedAt: new Date().toISOString(),
          entry: runtime.entry,
        }), { encoding: "utf8", mode: 0o600 });
        child.unref();
        try { closeSync(logFd); } catch (_) { /* best effort */ }
        resolve({ ok: true, pid: child.pid, mode: "direct-dist" });
      });
    } catch (error) {
      if (logFd !== undefined) {
        try { closeSync(logFd); } catch (_) { /* best effort */ }
      }
      resolve({ ok: false, detail: error.message });
    }
  });
}

async function waitUntilReady(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let last = { ready: false, usable: false, status: 0 };
  while (Date.now() < deadline) {
    last = await probe(port);
    if (last.ready) return last;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  return last;
}

/**
 * Garantiza que el gateway incluido esté vivo sin pasar por el cargador
 * tsx/src de OmniRoute. Si cae, una llamada posterior lo vuelve a levantar.
 */
export async function ensureOmniRoute({ timeoutMs = 60_000 } = {}) {
  if (!enabled()) return { state: "disabled", started: false, usable: false };
  const configured = String(process.env.A2S_OMNIROUTE_URL || "").trim();
  if (configured && process.env.A2S_OMNIROUTE_MANAGED !== "1") {
    return { state: "configured", started: false, usable: true, url: configured };
  }

  const port = configuredPort();
  let status = await probe(port);
  if (!status.ready) {
    const launched = await launchDirect(port);
    if (!launched.ok) {
      status = await waitUntilReady(port, Math.min(timeoutMs, 10_000));
      if (!status.ready) {
        return { state: "failed", started: false, usable: false,
          detail: launched.detail };
      }
    } else {
      status = await waitUntilReady(port, timeoutMs);
    }
    if (!status.ready) {
      return { state: "failed", started: true, usable: false,
        detail: `OmniRoute no respondió con un catálogo válido en :${port}` };
    }
    status.started = true;
  }

  const url = endpoint(port);
  let login = { changed: false };
  if (status.usable) {
    process.env.A2S_OMNIROUTE_URL = url;
    process.env.A2S_OMNIROUTE_MANAGED = "1";
    login = await enforceNoLogin(port);
  }
  return {
    state: status.usable ? "ready" : "auth-required",
    started: Boolean(status.started),
    usable: status.usable,
    authRequired: Boolean(status.authRequired),
    loginRequired: (login.optedOut || login.detail || login.unmanaged || login.missing)
      ? undefined : false,
    mode: "direct-dist",
    url,
  };
}

export async function omniRouteStatus() {
  const port = configuredPort();
  const status = await probe(port);
  let processInfo = null;
  try {
    processInfo = JSON.parse(readFileSync(pidPath(), "utf8"));
    process.kill(Number(processInfo.pid), 0);
    processInfo.alive = true;
  } catch (_) {
    if (processInfo) processInfo.alive = false;
  }
  return { ...status, port, url: endpoint(port), process: processInfo };
}

export function stopOmniRoute() {
  let info;
  const path = pidPath();
  try {
    info = JSON.parse(readFileSync(path, "utf8"));
    process.kill(Number(info.pid), "SIGTERM");
    rmSync(path, { force: true });
    return { stopped: true, pid: Number(info.pid) };
  } catch (error) {
    return { stopped: false, detail: error.message };
  }
}

const REASONING_COMMANDS = new Set([
  "run", "supervise", "swarm", "demo", "learn", "serve", "fsm", "watch",
  "dashboard", "doctor", "pool-status", "pool-check", "route-preview", "grow",
  "research", "book",
]);

const LONG_RUNNING_COMMANDS = new Set([
  "dashboard", "serve", "watch", "grow", "research", "book",
]);

export function shouldEnsureOmniRoute(args = process.argv.slice(2)) {
  if (!enabled() || args.length === 0) return false;
  if (args.some((arg) => arg === "--version" || arg === "-V" ||
      arg === "-h" || arg === "--help")) return false;
  const providerIndex = args.indexOf("--provider");
  if ((providerIndex >= 0 && args[providerIndex + 1] === "heuristic") ||
      args.includes("--provider=heuristic")) return false;
  return REASONING_COMMANDS.has(args[0]);
}

export function shouldWatchOmniRoute(args = process.argv.slice(2)) {
  return shouldEnsureOmniRoute(args) && LONG_RUNNING_COMMANDS.has(args[0]);
}
