import { init_planegcs_module, GcsWrapper, SolveStatus } from "/package/dist/index.js";

const result = { user_agent: navigator.userAgent, path: location.pathname };
// A local candidate-policy probe only. This never changes DBFox's actual CSP.
try { new Function("return 1")(); result.javascript_eval = "allowed"; }
catch (error) { result.javascript_eval = error.name; }
const diagnostics = [];
let solver;
try {
  const module = await init_planegcs_module({ print: s => diagnostics.push(s), printErr: s => diagnostics.push(s) });
  solver = new GcsWrapper(new module.GcsSystem(), module);
  solver.push_primitives_and_params([
    { id: "anchor", type: "point", x: 0, y: 0, fixed: true },
    { id: "end", type: "point", x: 77, y: 1, fixed: false },
    { type: "param", name: "phone_width", value: 78 },
    { id: "horizontal", type: "horizontal_pp", p1_id: "anchor", p2_id: "end" },
    { id: "width", type: "p2p_distance", p1_id: "anchor", p2_id: "end", distance: "phone_width" },
  ]);
  result.widths = [];
  for (const width of [78, 82]) {
    solver.set_sketch_param("phone_width", width);
    if (solver.solve() !== SolveStatus.Success) throw new Error("solve failed");
    solver.apply_solution();
    const point = solver.sketch_index.get_primitives().find(p => p.id === "end");
    if (Math.abs(point.x - width) > 1e-7 || Math.abs(point.y) > 1e-7) throw new Error("dimension mismatch");
    result.widths.push(point.x);
  }
  result.ok = true;
} catch (error) {
  result.ok = false;
  result.error = { name: error.name, message: error.message };
} finally {
  solver?.destroy_gcs_module();
}
result.diagnostics = diagnostics;
window.probeResult = result;
document.querySelector("pre").textContent = JSON.stringify(result, null, 2);
