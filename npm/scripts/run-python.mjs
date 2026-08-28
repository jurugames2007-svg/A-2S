#!/usr/bin/env node

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { findPython, packageEnvironment, runPythonSync, exitCode } from "../lib/python.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
let python;
try {
  python = findPython();
} catch (error) {
  console.error(`[A²S npm] ${error.message}`);
  process.exit(1);
}

const result = runPythonSync(python, process.argv.slice(2), {
  cwd: root,
  env: packageEnvironment(root),
});
process.exit(exitCode(result));
