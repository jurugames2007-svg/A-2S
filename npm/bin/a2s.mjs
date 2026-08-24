#!/usr/bin/env node

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { findPython, packageEnvironment, spawnPython } from "../lib/python.mjs";
import {
  ensureOmniRoute, shouldEnsureOmniRoute, shouldWatchOmniRoute,
} from "../lib/omniroute.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "../..");
const args = process.argv.slice(2);

let python;
try {
  python = findPython();
} catch (error) {
  console.error(`[A²S npm] ${error.message}`);
  process.exit(1);
}

let gatewayWatch = null;
if (shouldEnsureOmniRoute(args)) {
  const gateway = await ensureOmniRoute();
  if (gateway.started && gateway.usable) {
    console.error(`[A²S npm] OmniRoute incluido listo en ${gateway.url} (runtime dist directo)`);
  } else if (gateway.state === "auth-required") {
    console.error("[A²S npm] OmniRoute está vivo pero exige clave. Define " +
      "A2S_OMNIROUTE_KEY; A²S continuará con su fallback seguro.");
  } else if (gateway.state === "failed") {
    console.error(`[A²S npm] OmniRoute no pudo iniciarse (${gateway.detail || "error"}). ` +
      "A²S continuará con su fallback seguro y reintentará en segundo plano.");
  }

  if (shouldWatchOmniRoute(args)) {
    process.env.A2S_OMNIROUTE_PARENT_WATCHDOG = "1";
    let lastWarning = "";
    let checking = false;
    gatewayWatch = setInterval(async () => {
      if (checking) return;
      checking = true;
      try {
        const current = await ensureOmniRoute({ timeoutMs: 20_000 });
        if (current.started && current.usable) {
          console.error("[A²S npm] OmniRoute se recuperó automáticamente.");
          lastWarning = "";
        } else if (current.state === "failed" && current.detail !== lastWarning) {
          lastWarning = current.detail;
          console.error(`[A²S npm] Supervisor OmniRoute: ${current.detail}`);
        }
      } finally {
        checking = false;
      }
    }, 15_000);
    gatewayWatch.unref();
  }
}

const child = spawnPython(python, ["-m", "a2s", ...process.argv.slice(2)], {
  cwd: process.cwd(),
  env: packageEnvironment(packageRoot),
});

let forwarding = false;
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    if (forwarding) return;
    forwarding = true;
    if (!child.killed) child.kill(signal);
  });
}

child.on("error", (error) => {
  if (gatewayWatch) clearInterval(gatewayWatch);
  console.error(`[A²S npm] No se pudo iniciar ${python.label}: ${error.message}`);
  process.exitCode = 1;
});

child.on("exit", (code, signal) => {
  if (gatewayWatch) clearInterval(gatewayWatch);
  if (signal) {
    process.exitCode = signal === "SIGINT" ? 130 : 143;
  } else {
    process.exitCode = code ?? 1;
  }
});
