import { delimiter } from "node:path";
import { spawn, spawnSync } from "node:child_process";

const MINIMUM = [3, 9];

function candidates() {
  const configured = process.env.A2S_PYTHON?.trim();
  if (configured) return [{ command: configured, prefix: [] }];
  if (process.platform === "win32") {
    return [
      { command: "py", prefix: ["-3"] },
      { command: "python", prefix: [] },
      { command: "python3", prefix: [] },
    ];
  }
  return [
    { command: "python3", prefix: [] },
    { command: "python", prefix: [] },
  ];
}

function parseVersion(output) {
  const match = String(output || "").match(/Python\s+(\d+)\.(\d+)(?:\.(\d+))?/i);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3] || 0)] : null;
}

function supported(version) {
  return version && (version[0] > MINIMUM[0] ||
    (version[0] === MINIMUM[0] && version[1] >= MINIMUM[1]));
}

export function findPython() {
  const attempts = [];
  for (const candidate of candidates()) {
    const probe = spawnSync(candidate.command, [...candidate.prefix, "--version"], {
      encoding: "utf8",
      windowsHide: true,
    });
    if (probe.error) {
      attempts.push(`${candidate.command}: ${probe.error.code || probe.error.message}`);
      continue;
    }
    const raw = `${probe.stdout || ""}${probe.stderr || ""}`.trim();
    const version = parseVersion(raw);
    if (probe.status === 0 && supported(version)) {
      return { ...candidate, version, label: raw };
    }
    attempts.push(`${candidate.command}: ${raw || `exit ${probe.status}`}`);
  }
  const detail = attempts.length ? `\nIntentos: ${attempts.join("; ")}` : "";
  throw new Error(
    `A²S requiere Python ${MINIMUM.join(".")} o superior. ` +
    `Instálalo o define A2S_PYTHON con la ruta del ejecutable.${detail}`,
  );
}

export function packageEnvironment(packageRoot, extra = {}) {
  const current = process.env.PYTHONPATH || "";
  return {
    ...process.env,
    ...extra,
    PYTHONPATH: current ? `${packageRoot}${delimiter}${current}` : packageRoot,
    PYTHONUNBUFFERED: "1",
    // Windows: la consola/cp1252 no representa ✔ → · y rompe cualquier print
    // con símbolos (UnicodeEncodeError). UTF-8 modo Python para TODO proceso
    // lanzado desde npm (tests, CLI, dashboard) — defensa en profundidad junto
    // a a2s._platform.force_utf8().
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
  };
}

export function runPythonSync(python, args, options = {}) {
  return spawnSync(python.command, [...python.prefix, ...args], {
    cwd: options.cwd,
    env: options.env,
    stdio: options.stdio || "inherit",
    encoding: options.encoding,
    windowsHide: true,
    timeout: options.timeout,
  });
}

export function spawnPython(python, args, options = {}) {
  return spawn(python.command, [...python.prefix, ...args], {
    cwd: options.cwd,
    env: options.env,
    stdio: options.stdio || "inherit",
    windowsHide: true,
  });
}

export function exitCode(result) {
  if (result.error) {
    if (result.error.code === "ETIMEDOUT") return 124;
    return 1;
  }
  return result.status ?? 1;
}
