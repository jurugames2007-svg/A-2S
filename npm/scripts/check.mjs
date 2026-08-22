#!/usr/bin/env node

import { readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { findPython, packageEnvironment, runPythonSync, exitCode } from "../lib/python.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const env = packageEnvironment(root, { PYTHONWARNINGS: "default" });

function stop(label, result) {
  const code = result.status ?? 1;
  console.error(`\n[A²S check] ✗ ${label} (exit ${code})`);
  process.exit(exitCode(result));
}

function pythonStep(python, label, args) {
  console.log(`\n[A²S check] ${label}`);
  const result = runPythonSync(python, args, { cwd: root, env });
  if (exitCode(result) !== 0) stop(label, result);
}

function nodeStep(label, args) {
  console.log(`\n[A²S check] ${label}`);
  const result = spawnSync(process.execPath, args, {
    cwd: root, env, stdio: "inherit", windowsHide: true,
  });
  if ((result.status ?? 1) !== 0) stop(label, result);
}

function scriptsUnder(directory) {
  const found = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) found.push(...scriptsUnder(path));
    else if (entry.name.endsWith(".mjs")) found.push(path);
  }
  return found;
}

let python;
try {
  python = findPython();
} catch (error) {
  console.error(`[A²S check] ${error.message}`);
  process.exit(1);
}
console.log(`[A²S check] Runtime: Node ${process.version} · ${python.label}`);

for (const script of [join(root, "a2s", "ui", "app.js"),
  join(root, "electron", "main.js"), join(root, "electron", "gateway.js"),
  ...scriptsUnder(join(root, "npm"))]) {
  nodeStep(`sintaxis ${script.slice(root.length + 1)}`, ["--check", script]);
}

pythonStep(python, "compilación Python", ["-m", "compileall", "-q", "a2s", "tests", "tools"]);
pythonStep(python, "pureza stdlib", ["tools/check_purity.py"]);
pythonStep(python, "complejidad", ["tools/check_cc.py", "35"]);
pythonStep(python, "suite completa", ["-m", "unittest", "discover", "-s", "tests", "-v"]);
pythonStep(python, "auditoría viva", ["-m", "a2s", "audit"]);

console.log("\n[A²S check] ✔ todos los gates pasaron");
