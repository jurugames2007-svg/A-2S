#!/usr/bin/env node

import { mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const metadata = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const temp = mkdtempSync(join(tmpdir(), "a2s-npm-e2e-"));

function command(label, executable, args, options = {}) {
  const result = spawnSync(executable, args, {
    cwd: options.cwd || root,
    env: { ...process.env, PYTHONUNBUFFERED: "1", A2S_OMNIROUTE: "off",
      ...(options.env || {}) },
    encoding: "utf8",
    stdio: options.stdio || "pipe",
    timeout: options.timeout || 120_000,
    windowsHide: true,
  });
  if (result.status !== 0) {
    process.stderr.write(result.stdout || "");
    process.stderr.write(result.stderr || "");
    if (result.error) process.stderr.write(`${result.error.message}\n`);
    throw new Error(`${label} falló (exit ${result.status ?? "?"}, ` +
      `signal ${result.signal || "—"})`);
  }
  return `${result.stdout || ""}${result.stderr || ""}`;
}

function freePort() {
  return new Promise((resolvePort, reject) => {
    const server = createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close((error) => error ? reject(error) : resolvePort(port));
    });
  });
}

async function waitFor(url, timeoutMs = 20_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return response;
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 200));
  }
  throw new Error(`timeout esperando ${url}: ${lastError?.message || "sin respuesta"}`);
}

let dashboard;
let dashboardLogs = "";
try {
  console.log("[A²S npm e2e] construyendo tarball y zipapp…");
  command("build", process.execPath, [join(root, "npm", "scripts", "build.mjs")],
    { stdio: "inherit", timeout: 180_000 });
  const tarball = readdirSync(join(root, "artifacts"))
    .find((name) => name.endsWith(".tgz"));
  if (!tarball) throw new Error("build no produjo un tarball npm");

  console.log("[A²S npm e2e] instalando tarball en prefijo aislado…");
  // El E2E valida el tarball, bins y dependencia declarada; omite únicamente
  // aceleradores nativos opcionales de OmniRoute para no duplicar varios GB
  // por plataforma dentro del prefijo efímero.
  command("npm install", npmCommand, ["install", "--ignore-scripts", "--omit=optional",
    "--no-audit", "--no-fund", "--prefix", temp,
    join(root, "artifacts", tarball)],
  { timeout: 600_000 });

  const bin = join(temp, "node_modules", ".bin",
    process.platform === "win32" ? "a2s.cmd" : "a2s");
  const version = command("a2s --version", bin, ["--version"], { cwd: temp });
  if (!version.includes(metadata.version)) {
    throw new Error(`versión inesperada: ${version.trim()}`);
  }
  const omniBin = join(temp, "node_modules", ".bin",
    process.platform === "win32" ? "omniroute.cmd" : "omniroute");
  const omniVersion = command("omniroute --version", omniBin, ["--version"], { cwd: temp });
  if (!omniVersion.includes(metadata.dependencies.omniroute)) {
    throw new Error(`OmniRoute incluido inesperado: ${omniVersion.trim()}`);
  }
  for (const commandName of ["a2s-control-plane", "a2s-agent-control-plane"]) {
    const alias = join(temp, "node_modules", ".bin",
      process.platform === "win32" ? `${commandName}.cmd` : commandName);
    const aliasVersion = command(`${commandName} --version`, alias, ["--version"],
      { cwd: temp });
    if (!aliasVersion.includes(metadata.version)) {
      throw new Error(`alias inesperado: ${aliasVersion.trim()}`);
    }
  }
  const doctor = command("a2s doctor", bin, ["doctor", "--workspace", join(temp, "workspace")],
    { cwd: temp });
  if (!doctor.includes("A²S") || !doctor.includes(metadata.version)) {
    throw new Error("doctor no confirmó el runtime empaquetado");
  }

  const port = await freePort();
  console.log(`[A²S npm e2e] iniciando Control Plane instalado en :${port}…`);
  dashboard = spawn(bin, ["dashboard", "--port", String(port), "--workspace",
    join(temp, "workspace")], {
    cwd: temp,
    env: { ...process.env, PYTHONUNBUFFERED: "1", A2S_OMNIROUTE: "off" },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  dashboard.stdout.on("data", (chunk) => { dashboardLogs += chunk; });
  dashboard.stderr.on("data", (chunk) => { dashboardLogs += chunk; });
  dashboard.once("error", (error) => { dashboardLogs += error.message; });

  const health = await waitFor(`http://127.0.0.1:${port}/healthz`);
  const healthJson = await health.json();
  if (healthJson.version !== metadata.version) {
    throw new Error(`healthz reportó ${healthJson.version}`);
  }
  const page = await (await fetch(`http://127.0.0.1:${port}/`)).text();
  if (!page.includes("A²S Control Plane")) {
    throw new Error("la GUI empaquetada no está disponible");
  }
  console.log(`[A²S npm e2e] ✔ CLI ${metadata.version}, doctor, healthz y GUI funcionan`);
} catch (error) {
  console.error(`[A²S npm e2e] ✗ ${error.message}`);
  if (dashboardLogs.trim()) console.error(dashboardLogs.trim());
  process.exitCode = 1;
} finally {
  if (dashboard && !dashboard.killed) {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/pid", String(dashboard.pid), "/t", "/f"], {
        stdio: "ignore", windowsHide: true,
      });
    } else {
      dashboard.kill("SIGTERM");
    }
  }
  await new Promise((resolveWait) => setTimeout(resolveWait, 250));
  rmSync(temp, { recursive: true, force: true });
}
