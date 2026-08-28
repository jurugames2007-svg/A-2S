#!/usr/bin/env node

import {
  ensureOmniRoute, omniRouteStatus, stopOmniRoute,
} from "../lib/omniroute.mjs";

const command = process.argv[2] || "status";

if (command === "start") {
  const result = await ensureOmniRoute();
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.usable ? 0 : 1);
} else if (command === "stop") {
  const result = stopOmniRoute();
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.stopped ? 0 : 1);
} else if (command === "status") {
  const result = await omniRouteStatus();
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.usable ? 0 : 1);
} else {
  console.error("Uso: node npm/scripts/gateway.mjs start|status|stop");
  process.exit(2);
}
