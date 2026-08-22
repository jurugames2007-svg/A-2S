#!/usr/bin/env node

import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

for (const [label, script] of [
  ["quality gates", "check.mjs"],
  ["npm package E2E", "test-package.mjs"],
]) {
  console.log(`\n[A²S release] ${label}`);
  const result = spawnSync(process.execPath, [join(root, "npm", "scripts", script)], {
    cwd: root,
    env: process.env,
    stdio: "inherit",
    windowsHide: true,
  });
  if (result.status !== 0) {
    console.error(`[A²S release] ✗ ${label}`);
    process.exit(result.status ?? 1);
  }
}

console.log("\n[A²S release] ✔ release local lista en artifacts/");
