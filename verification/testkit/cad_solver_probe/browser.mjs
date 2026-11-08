import { init_planegcs_module, GcsWrapper, SolveStatus } from "/package/dist/index.js";

import { runSolverCases } from "/cases.mjs";

const result = { user_agent: navigator.userAgent, path: location.pathname };
// A local candidate-policy probe only. This never changes DBFox's actual CSP.
try { new Function("return 1")(); result.javascript_eval = "allowed"; }
catch (error) { result.javascript_eval = error.name; }
const diagnostics = [];
try {
  const module = await init_planegcs_module({ print: s => diagnostics.push(s), printErr: s => diagnostics.push(s) });
  const assert = {
    ok: (value, message = "assertion failed") => { if (!value) throw new Error(message); },
    equal: (actual, expected) => { if (actual !== expected) throw new Error(`${actual} !== ${expected}`); },
    deepEqual: (actual, expected) => { if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error("structures differ"); },
  };
  result.results = runSolverCases(module, GcsWrapper, SolveStatus, assert);
  result.passed = result.results.length;
  result.ok = true;
} catch (error) {
  result.ok = false;
  result.error = { name: error.name, message: error.message };
}
result.diagnostics = diagnostics;
window.probeResult = result;
document.querySelector("pre").textContent = JSON.stringify(result, null, 2);
