#!/usr/bin/env node

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { findPython, packageEnvironment, spawnPython } from "../lib/python.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "../..");

let python;
try {
  python = findPython();
} catch (error) {
  console.error(`[A²S npm] ${error.message}`);
  process.exit(1);
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
  console.error(`[A²S npm] No se pudo iniciar ${python.label}: ${error.message}`);
  process.exitCode = 1;
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.exitCode = signal === "SIGINT" ? 130 : 143;
  } else {
    process.exitCode = code ?? 1;
  }
});
