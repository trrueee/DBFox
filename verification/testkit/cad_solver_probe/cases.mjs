/** Same numeric checks for Node and real browser deployments. */
export function runSolverCases(module, GcsWrapper, SolveStatus, assert) {
  const results = [];
  const near = (actual, expected) => assert.ok(
    Math.abs(actual - expected) < 1e-7, `${actual} differs from ${expected}`,
  );
  const point = (id, x, y, fixed = false) => ({ id, type: "point", x, y, fixed });
  const distance = (id, a, b, value) => ({
    id, type: "p2p_distance", p1_id: a, p2_id: b, distance: value,
  });
  function withSolver(name, primitives, inspect) {
    const solver = new GcsWrapper(new module.GcsSystem(), module);
    solver.set_max_iterations(100);
    solver.set_convergence_threshold(1e-10);
    const start = performance.now();
    try {
      solver.push_primitives_and_params(primitives);
      results.push({ name, ...inspect(solver), elapsed_ms: performance.now() - start });
    } finally {
      solver.destroy_gcs_module();
    }
  }
  function successful(solver) {
    const status = solver.solve();
    assert.equal(status, SolveStatus.Success);
    assert.equal(solver.has_gcs_conflicting_constraints(), false);
    solver.apply_solution();
    return structuredClone(solver.sketch_index.get_primitives());
  }
  function checkRectangle(primitives, width) {
    const points = Object.fromEntries(primitives.filter(p => p.type === "point").map(p => [p.id, p]));
    for (const [id, x, y] of [["a", 0, 0], ["b", width, 0], ["c", width, 10], ["d", 0, 10]]) {
      near(points[id].x, x);
      near(points[id].y, y);
    }
  }
  withSolver("same_sketch_width_78_to_82", [
    { type: "param", name: "phone_width", value: 78 },
    point("a", 0, 0, true), point("b", 77, 1), point("c", 77, 11), point("d", 1, 11),
    { id: "bottom", type: "horizontal_pp", p1_id: "a", p2_id: "b" },
    { id: "right", type: "vertical_pp", p1_id: "b", p2_id: "c" },
    { id: "top", type: "horizontal_pp", p1_id: "c", p2_id: "d" },
    { id: "left", type: "vertical_pp", p1_id: "d", p2_id: "a" },
    distance("width", "a", "b", "phone_width"), distance("thickness", "b", "c", 10),
  ], solver => {
    const before = successful(solver);
    checkRectangle(before, 78);
    assert.equal(solver.gcs.dof(), 0);
    solver.set_sketch_param("phone_width", 82);
    const after = successful(solver);
    checkRectangle(after, 82);
    assert.deepEqual(before.map(p => p.id), after.map(p => p.id));
    for (let n = 0; n < 200; n++) {
      const width = n % 2 ? 82 : 78;
      solver.set_sketch_param("phone_width", width);
      checkRectangle(successful(solver), width);
    }
    return { before, after, repeated_solves: 200, dof: solver.gcs.dof() };
  });
  withSolver("angle_65_degrees", [
    point("origin", 0, 0, true), point("tip", 12, 24),
    distance("length", "origin", "tip", 30),
    { id: "tilt", type: "p2p_angle", p1_id: "origin", p2_id: "tip", angle: 65 * Math.PI / 180 },
  ], solver => {
    const solved = successful(solver);
    const tip = solved.find(p => p.id === "tip");
    near(Math.hypot(tip.x, tip.y), 30);
    near(Math.atan2(tip.y, tip.x) * 180 / Math.PI, 65);
    return { tip, dof: solver.gcs.dof() };
  });
  withSolver("underconstrained_distance", [
    point("a", 0, 0, true), point("b", 70, 20), distance("width", "a", "b", 78),
  ], solver => {
    const solved = successful(solver);
    const p = solved.find(p => p.id === "b");
    near(Math.hypot(p.x, p.y), 78);
    assert.equal(solver.gcs.dof(), 1);
    return { dof: solver.gcs.dof(), point: p };
  });
  withSolver("conflicting_distances", [
    point("a", 0, 0, true), point("b", 77, 1),
    distance("width78", "a", "b", 78), distance("width82", "a", "b", 82),
  ], solver => {
    const before = structuredClone(solver.sketch_index.get_primitives());
    const status = solver.solve();
    const conflicts = solver.get_gcs_conflicting_constraints();
    assert.ok(status !== SolveStatus.Success || solver.has_gcs_conflicting_constraints());
    assert.deepEqual(solver.sketch_index.get_primitives(), before);
    return { status, conflicts, has_conflicts: solver.has_gcs_conflicting_constraints(), solution_applied: false };
  });
  withSolver("impossible_triangle_3_4_10", [
    point("a", 0, 0, true), point("b", 3, 0), point("c", 2, 2),
    distance("ab", "a", "b", 3), distance("bc", "b", "c", 4), distance("ca", "c", "a", 10),
  ], solver => {
    const status = solver.solve();
    assert.ok(status !== SolveStatus.Success || solver.has_gcs_conflicting_constraints());
    return { status, conflicts: solver.get_gcs_conflicting_constraints(), solution_applied: false };
  });
  return results;
}
