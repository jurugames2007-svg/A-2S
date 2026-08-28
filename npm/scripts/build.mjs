#!/usr/bin/env node

import { chmodSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { findPython, packageEnvironment, runPythonSync, exitCode } from "../lib/python.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const artifacts = join(root, "artifacts");
const live = join(artifacts, "a2s.pyz");
const metadata = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));

function fail(message, result = null) {
  console.error(`[A²S build] ${message}`);
  if (result?.error) console.error(result.error.message);
  process.exit(result ? exitCode(result) : 1);
}

rmSync(artifacts, { recursive: true, force: true });
mkdirSync(artifacts, { recursive: true });

let python;
try {
  python = findPython();
} catch (error) {
  fail(error.message);
}

console.log(`[A²S build] Python: ${python.label}`);
const buildLive = runPythonSync(python, ["-m", "a2s", "build-live", "--output", live], {
  cwd: root,
  env: packageEnvironment(root),
});
if (exitCode(buildLive) !== 0) fail("falló la creación del zipapp", buildLive);
try { chmodSync(live, 0o755); } catch (_) { /* Windows no aplica modo POSIX */ }

const verifyLive = runPythonSync(python, [live, "--version"], {
  cwd: root,
  env: packageEnvironment(root),
  stdio: "pipe",
  encoding: "utf8",
  timeout: 30_000,
});
if (exitCode(verifyLive) !== 0 || !String(verifyLive.stdout).includes(metadata.version)) {
  fail("el zipapp generado no superó el smoke test de versión", verifyLive);
}

const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const packed = spawnSync(npmCommand, ["pack", "--json", "--ignore-scripts",
  "--pack-destination", artifacts], {
  cwd: root,
  encoding: "utf8",
  windowsHide: true,
  shell: process.platform === "win32",
});
if (packed.status !== 0) {
  process.stderr.write(packed.stderr || packed.stdout || "");
  fail("npm pack falló", packed);
}

let tarball = `${metadata.name}-${metadata.version}.tgz`;
try {
  const info = JSON.parse(packed.stdout);
  tarball = info[0]?.filename || tarball;
} catch (_) { /* npm antiguo: el nombre semver sigue siendo determinista */ }

console.log("\n[A²S build] Artefactos verificados:");
console.log(`  - ${live}`);
console.log(`  - ${join(artifacts, tarball)}`);
console.log("\nInstalación local global:");
console.log(`  npm install -g ./artifacts/${tarball}`);
console.log("  a2s --version");
console.log("  a2s dashboard");
