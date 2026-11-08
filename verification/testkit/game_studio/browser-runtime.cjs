async (page) => page.evaluate(async () => {
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  const invoke = async (name, input) => {
    const response = await fetch('/operation', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, input }) });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  };
  const { readGame } = await import('/dlcs/dbfox.game/frontend/model.js');
  const { createRuntime, runPlaytest } = await import('/dlcs/dbfox.game/frontend/runtime.js');
  const library = await invoke('games.list', {});
  const snapshot = await readGame(invoke, library.items[0].id);
  const fox = snapshot.document.entities.find((entity) => entity.tags.includes('player'));
  const input = { document: snapshot.document, rgba_assets: snapshot.rgba_assets, seed: 42, ticks: 3600 };
  const stationary = await runPlaytest(input);
  assert(stationary.outcome === 'lost' && stationary.ticks_completed < 3600, 'Standing fox must be caught by actual slime encounters');
  const runtime = await createRuntime({ ...input, headless: true });
  const inputs = [];
  let previous = '';
  const directions = [[], ['right'], ['down'], ['left'], ['up'], ['right', 'down'], ['left', 'down'], ['left', 'up'], ['right', 'up']];
  try {
    while (!runtime.done) {
      const state = runtime.snapshot();
      const player = state.entities.find((entity) => entity.id === fox.id);
      const enemies = state.entities.filter((entity) => entity.id.includes(':'));
      const score = (actions) => {
        const dx = Number(actions.includes('right')) - Number(actions.includes('left'));
        const dy = Number(actions.includes('down')) - Number(actions.includes('up'));
        const length = Math.hypot(dx, dy) || 1;
        let minimum = 500;
        for (const time of [0.25, 0.5, 1]) {
          const x = Math.max(30, Math.min(770, player.x + dx / length * 230 * time));
          const y = Math.max(30, Math.min(570, player.y + dy / length * 230 * time));
          for (const enemy of enemies) minimum = Math.min(minimum, Math.hypot(x - enemy.x - enemy.vx * time, y - enemy.y - enemy.vy * time));
        }
        const x = player.x + dx / length * 115;
        const y = player.y + dy / length * 115;
        return minimum - Math.max(0, 55 - x, x - 745, 55 - y, y - 545) * 2 - Math.hypot(x - 400, y - 380) * 0.03;
      };
      const actions = [...directions].sort((left, right) => score(right) - score(left))[0];
      if (runtime.tick % 10 === 0 && actions.join() !== previous) {
        inputs.push({ tick: runtime.tick, entity_id: fox.id, actions });
        previous = actions.join();
        runtime.setActions(fox.id, actions);
      }
      runtime.step(false);
    }
    const scripted = runtime.snapshot();
    assert(scripted.outcome === 'won' && scripted.ticks_completed === 3600, `Survival route failed: ${scripted.outcome} at ${scripted.ticks_completed}`);
    assert(scripted.events.some((event) => event.kind === 'spawn'), 'Win must include real spawned opponents');
    assert(inputs.length <= 1024, 'Demonstrated route must fit the public input contract');
    const replay = await runPlaytest({ ...input, inputs });
    assert(JSON.stringify(scripted) === JSON.stringify(replay), 'Recorded route must reproduce the actual run');
    const visible = await createRuntime({ ...input, ticks: 120, inputs, parent: document.body });
    let canvasReport;
    try { for (let tick = 0; tick < 120; tick += 1) visible.step(); canvasReport = visible.snapshot(); }
    finally { visible.destroy(); }
    const headless = await runPlaytest({ ...input, ticks: 120, inputs });
    assert(JSON.stringify(canvasReport) === JSON.stringify(headless), 'Canvas and HEADLESS must share authoritative simulation');
    let deadlineName;
    try { await runPlaytest(input, { deadline: performance.now() - 1 }); }
    catch (error) { deadlineName = error.name; }
    assert(deadlineName === 'TimeoutError', 'Deadline must retain the executor error classification');
    const cancellation = new AbortController();
    let abortName;
    try { await runPlaytest(input, { signal: cancellation.signal, onProgress: () => cancellation.abort() }); }
    catch (error) { abortName = error.name; }
    assert(abortName === 'AbortError', 'Cancellation must stop the real engine');
    const dense = structuredClone(snapshot.document);
    dense.behaviors = []; dense.rules = [];
    dense.entities = Array.from({ length: 512 }, (_, index) => ({ ...structuredClone(fox), id: crypto.randomUUID(), name: `Dense ${index}`, components: fox.components.map((component) => ({ ...structuredClone(component), id: crypto.randomUUID() })) }));
    const denseStart = performance.now();
    const denseReport = await runPlaytest({ document: dense, seed: 1, ticks: 10 });
    const denseMilliseconds = performance.now() - denseStart;
    assert(denseReport.outcome === 'budget_exceeded' && denseReport.ticks_completed === 1, '512 overlapping bodies must terminate at the explicit overlap candidate budget');
    window.gameSurvivalEvidence = { version: snapshot.revision.version, contentHash: snapshot.revision.content_hash, stationary: { outcome: stationary.outcome, ticks: stationary.ticks_completed }, won: { outcome: scripted.outcome, ticks: scripted.ticks_completed, events: scripted.event_count }, inputs, deterministicReplay: true, canvasHeadlessEqual: true, timeout: deadlineName, cancel: abortName, dense: { bodies: 512, outcome: denseReport.outcome, ticks: denseReport.ticks_completed, milliseconds: denseMilliseconds } };
  } finally { runtime.destroy(); }
  assert(document.querySelectorAll('canvas').length === 0, 'All runtime instances must release canvases');
  return { ...window.gameSurvivalEvidence, inputs: window.gameSurvivalEvidence.inputs.length, canvases: 0 };
})
