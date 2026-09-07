import Phaser from './vendor/phaser.js';

export const ENGINE = 'phaser-arcade-4.2.1';
export const TICK_MS = 1000 / 60;
const MAX_ACTORS = 512;
const MAX_TICK_ACTIONS = 4096;
const MAX_TOTAL_ACTIONS = 1_000_000;
const MAX_EVENTS = 1024;

function compare(left, op, right) {
  if (op === 'eq') return left === right;
  if (op === 'ne') return left !== right;
  if (op === 'lt') return left < right;
  if (op === 'le') return left <= right;
  if (op === 'gt') return left > right;
  return left >= right;
}

function finite(value) {
  return Number.isFinite(value) && Math.abs(value) <= 1e9;
}

function abortError() {
  return new DOMException('Game execution cancelled', 'AbortError');
}

function color(value) {
  return Number.parseInt(value.slice(1), 16);
}

function assetCanvas(asset, rgbaAssets) {
  const encoded = rgbaAssets[asset.content_hash];
  if (typeof encoded !== 'string') throw new Error('Immutable asset bytes are missing.');
  const binary = atob(encoded);
  if (binary.length !== asset.width * asset.height * 4) throw new Error('Immutable asset byte count is invalid.');
  const canvas = document.createElement('canvas');
  canvas.width = asset.width;
  canvas.height = asset.height;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Canvas 2D is unavailable.');
  const pixels = new Uint8ClampedArray(binary.length);
  for (let i = 0; i < binary.length; i += 1) pixels[i] = binary.charCodeAt(i);
  context.putImageData(new ImageData(pixels, asset.width, asset.height), 0, 0);
  return canvas;
}

function builtinTexture(scene, shape, tint) {
  const key = `game-builtin-${shape}-${tint}`;
  if (scene.textures.exists(key)) return key;
  const graphics = scene.make.graphics({ x: 0, y: 0 });
  graphics.fillStyle(tint, 1);
  if (shape === 'fox') {
    graphics.fillTriangle(3, 1, 5, 18, 15, 10);
    graphics.fillTriangle(29, 1, 27, 18, 17, 10);
    graphics.fillEllipse(16, 19, 28, 24);
    graphics.fillStyle(0xffedd2, 1);
    graphics.fillTriangle(3, 19, 16, 29, 14, 20);
    graphics.fillTriangle(29, 19, 16, 29, 18, 20);
    graphics.fillStyle(0x182735, 1);
    graphics.fillCircle(10, 17, 2);
    graphics.fillCircle(22, 17, 2);
    graphics.fillCircle(16, 25, 2);
  } else {
    graphics.fillEllipse(16, 20, 30, 24);
    graphics.fillRoundedRect(2, 19, 28, 12, 5);
    graphics.fillStyle(0xffffff, .8);
    graphics.fillEllipse(10, 14, 7, 4);
    graphics.fillStyle(0x172938, 1);
    graphics.fillCircle(11, 23, 2);
    graphics.fillCircle(21, 23, 2);
  }
  graphics.generateTexture(key, 32, 32);
  graphics.destroy();
  return key;
}

/** One Phaser scene owns both visible preview and accelerated fixed-step runs. */
export async function createRuntime({ document: canonical, rgba_assets: rgbaAssets = {}, parent, headless = false, seed = 1, ticks = 7200, inputs = [], signal, onEvent = () => {} }) {
  if (canonical.engine !== ENGINE || Phaser.VERSION !== '4.2.1' || canonical.tick_hz !== 60) throw new Error('Unsupported Game engine contract.');
  if (signal?.aborted) throw abortError();
  if (!Number.isInteger(seed) || seed < 0 || seed > 2 ** 31 - 1 || !Number.isInteger(ticks) || ticks < 1 || ticks > 7200) throw new Error('Invalid fixed playtest bounds.');
  const source = structuredClone(canonical);
  const sceneSpecs = new Map(source.scenes.map((item) => [item.id, item]));
  const templates = new Map(source.entities.map((item) => [item.id, item]));
  const behaviorSpecs = source.behaviors.filter((item) => item.enabled);
  const rng = new Phaser.Math.RandomDataGenerator([String(seed)]);
  const actors = new Map();
  const actionInputs = new Map();
  const variables = new Map(source.variables.map((item) => [item.id, item.initial]));
  const previousConditions = new Map();
  const previousOverlaps = new Map();
  let overlaps = new Map();
  let overlapBudget = false;
  let engineScene;
  let dynamicGroup;
  let staticGroup;
  let activeSceneId = source.initial_scene_id;
  let globalTick = 0;
  let sceneTick = 0;
  let spawnOrdinal = 0;
  let totalActions = 0;
  let tickActions = 0;
  let events = [];
  let eventCount = 0;
  let outcome;
  let reason = 'Requested ticks completed';
  let advanceRequested = false;
  let destroyed = false;
  let inputOffset = 0;
  let game;
  let resolveReady;
  let rejectReady;
  const ready = new Promise((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });

  function emit(kind, detail, entityIds = [], terminal = false) {
    // Reserve the last count for a truthful terminal budget event.
    if (!terminal && eventCount >= MAX_TOTAL_ACTIONS - 1) { fail('Game event budget exceeded'); return; }
    eventCount += 1;
    const event = { tick: globalTick, scene_id: activeSceneId, kind, detail: detail.slice(0, 256), entity_ids: entityIds };
    if (events.length < MAX_EVENTS) events.push(event);
    else if (terminal) events[MAX_EVENTS - 1] = event;
    onEvent(event);
  }

  function fail(message) {
    outcome = 'budget_exceeded';
    reason = message.slice(0, 120);
  }

  function countAction() {
    tickActions += 1;
    totalActions += 1;
    if (tickActions > MAX_TICK_ACTIONS || totalActions > MAX_TOTAL_ACTIONS) {
      fail('Game action budget exceeded');
      return false;
    }
    return true;
  }

  function addActor(template, identity, x, y, spawnedBy) {
    if (actors.size >= MAX_ACTORS) { fail('Active entity budget exceeded'); return; }
    const parts = new Map(template.components.map((item) => [item.spec.kind, item.spec]));
    const transform = parts.get('transform');
    const visual = parts.get('visual');
    const bodySpec = parts.get('body');
    const health = parts.get('health');
    const root = engineScene.add.rectangle(x ?? transform.x, y ?? transform.y, transform.width, transform.height, 0x000000, 0).setVisible(false);
    root.setData('runtimeId', identity);
    let artwork;
    if (visual && !headless) {
      if (visual.shape === 'rect') artwork = engineScene.add.rectangle(root.x, root.y, transform.width, transform.height, color(visual.color));
      else if (visual.shape === 'ellipse') artwork = engineScene.add.ellipse(root.x, root.y, transform.width, transform.height, color(visual.color));
      else {
        let key;
        if (visual.shape === 'asset') {
          const asset = source.assets.find((item) => item.id === visual.asset_id);
          key = 'game-asset-' + asset.id;
          if (!engineScene.textures.exists(key)) engineScene.textures.addCanvas(key, assetCanvas(asset, rgbaAssets));
        } else key = builtinTexture(engineScene, visual.shape, color(visual.color));
        artwork = engineScene.add.image(root.x, root.y, key).setDisplaySize(transform.width, transform.height);
      }
      artwork.setAlpha(visual.opacity).setDepth(visual.depth).setAngle(transform.angle);
    }
    if (bodySpec) {
      if (bodySpec.body_type === 'static') staticGroup.add(root);
      else dynamicGroup.add(root);
      const body = root.body;
      if (bodySpec.shape === 'circle') body.setCircle(transform.width / 2);
      else body.setSize(transform.width, transform.height, true);
      if (bodySpec.body_type === 'dynamic') {
        body.setVelocity(bodySpec.vx, bodySpec.vy);
        body.setDrag(bodySpec.drag, bodySpec.drag);
        body.setBounce(bodySpec.bounce, bodySpec.bounce);
        body.setCollideWorldBounds(bodySpec.world_bounds);
      }
    }
    actors.set(identity, { id: identity, template, parts, root, artwork, health: health?.initial, born: globalTick, spawnedBy, states: new Map() });
  }

  function removeActor(identity, record = true) {
    const actor = actors.get(identity);
    if (!actor) return;
    actors.delete(identity);
    actor.artwork?.destroy();
    if (actor.root.body) {
      (actor.parts.get('body').body_type === 'static' ? staticGroup : dynamicGroup).remove(actor.root, false, false);
      engineScene.physics.world.disable(actor.root);
    }
    actor.root.destroy();
    if (record) emit('despawn', 'Entity despawned', [identity]);
  }

  function orderedActors() {
    return [...actors.values()].sort((left, right) => left.id < right.id ? -1 : left.id > right.id ? 1 : 0);
  }

  function loadScene(identity) {
    for (const actor of [...actors.values()]) removeActor(actor.id, false);
    const spec = sceneSpecs.get(identity);
    if (!spec) throw new Error('Game scene is missing.');
    activeSceneId = identity;
    sceneTick = 0;
    previousConditions.clear();
    previousOverlaps.clear();
    overlaps.clear();
    engineScene.physics.world.setBounds(0, 0, spec.width, spec.height);
    engineScene.physics.world.gravity.set(spec.gravity_x, spec.gravity_y);
    engineScene.cameras.main.setBackgroundColor(spec.background);
    game.scale.resize(spec.width, spec.height);
    for (const template of source.entities) {
      if (template.scene_id === identity && template.enabled) addActor(template, template.id);
    }
  }

  function captureOverlap(left, right) {
    const a = left.getData('runtimeId');
    const b = right.getData('runtimeId');
    if (a === b || !actors.has(a) || !actors.has(b)) return;
    const pair = a < b ? [a, b] : [b, a];
    const key = pair.join('|');
    if (!overlaps.has(key)) {
      if (overlaps.size >= 4096) overlapBudget = true;
      else overlaps.set(key, pair);
    }
  }

  function solid(left, right) {
    return actors.get(left.getData('runtimeId'))?.parts.get('body')?.solid === true
      && actors.get(right.getData('runtimeId'))?.parts.get('body')?.solid === true;
  }

  function control(actor, behavior) {
    const spec = behavior.spec;
    const body = actor.root.body;
    if (!body || actor.parts.get('body').body_type !== 'dynamic') return;
    let velocity;
    if (spec.kind === 'player_control') {
      const actions = actionInputs.get(actor.template.id) ?? new Set();
      velocity = new Phaser.Math.Vector2(Number(actions.has('right')) - Number(actions.has('left')), Number(actions.has('down')) - Number(actions.has('up'))).normalize().scale(spec.speed);
    } else if (spec.kind === 'seek') {
      const target = actors.get(spec.target_id);
      velocity = target ? new Phaser.Math.Vector2(target.root.x - actor.root.x, target.root.y - actor.root.y).normalize().scale(spec.speed) : new Phaser.Math.Vector2();
    } else if (spec.kind === 'patrol') {
      let state = actor.states.get(behavior.id);
      if (!state) { state = { waypoint: 0, done: false }; actor.states.set(behavior.id, state); }
      let target = spec.waypoints[state.waypoint];
      let delta = new Phaser.Math.Vector2(target.x - actor.root.x, target.y - actor.root.y);
      if (delta.length() < .001 && !state.done) {
        if (state.waypoint + 1 < spec.waypoints.length) state.waypoint += 1;
        else if (spec.loop) state.waypoint = 0;
        else state.done = true;
        target = spec.waypoints[state.waypoint];
        delta = new Phaser.Math.Vector2(target.x - actor.root.x, target.y - actor.root.y);
      }
      velocity = state.done ? new Phaser.Math.Vector2() : delta.clone().normalize().scale(Math.min(spec.speed, delta.length() * 60));
    } else if (spec.kind === 'wander') {
      let state = actor.states.get(behavior.id);
      if (!state || globalTick - state.lastTurn >= spec.turn_interval_ticks) {
        state = { lastTurn: globalTick, angle: rng.realInRange(0, Math.PI * 2) };
        actor.states.set(behavior.id, state);
      }
      velocity = new Phaser.Math.Vector2().setToPolar(state.angle, spec.speed);
    }
    if (velocity) body.setVelocity(velocity.x, velocity.y);
  }

  function triggerContexts(rule) {
    const trigger = rule.spec.trigger;
    if (trigger.kind === 'elapsed_tick') return sceneTick === trigger.at_tick ? [{}] : [];
    if (trigger.kind === 'variable_compare' || trigger.kind === 'health_compare') {
      const actor = trigger.kind === 'health_compare' ? actors.get(trigger.entity_id) : undefined;
      const value = trigger.kind === 'variable_compare' ? variables.get(trigger.variable_id) : actor?.health;
      const matches = value !== undefined && compare(value, trigger.comparison, trigger.value);
      const old = previousConditions.get(rule.id) ?? false;
      previousConditions.set(rule.id, matches);
      return matches && !old ? [{}] : [];
    }
    const previous = previousOverlaps.get(rule.id) ?? new Set();
    const current = new Set();
    const matches = [];
    for (const [key, pair] of [...overlaps.entries()].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) {
      const left = actors.get(pair[0]);
      const right = actors.get(pair[1]);
      let match;
      if (left.template.tags.includes(trigger.left_tag) && right.template.tags.includes(trigger.right_tag)) match = { left: left.id, right: right.id };
      else if (right.template.tags.includes(trigger.left_tag) && left.template.tags.includes(trigger.right_tag)) match = { left: right.id, right: left.id };
      if (match) {
        current.add(key);
        if (trigger.phase === 'stay' || !previous.has(key)) matches.push(match);
      }
    }
    previousOverlaps.set(rule.id, current);
    return matches;
  }

  function advance() {
    while (inputOffset < inputs.length && inputs[inputOffset].tick === globalTick) {
      const item = inputs[inputOffset++];
      actionInputs.set(item.entity_id, new Set(item.actions));
    }
    tickActions = 0;
    overlaps = new Map();
    overlapBudget = false;
    const actorsByTemplate = new Map();
    for (const actor of orderedActors()) {
      if (!actorsByTemplate.has(actor.template.id)) actorsByTemplate.set(actor.template.id, []);
      actorsByTemplate.get(actor.template.id).push(actor);
    }
    for (const behavior of behaviorSpecs) {
      for (const actor of actorsByTemplate.get(behavior.spec.entity_id) ?? []) control(actor, behavior);
    }
    // Exactly one complete Arcade integration in both visible and headless use.
    engineScene.physics.world.singleStep();
    globalTick += 1;
    sceneTick += 1;
    for (const actor of actors.values()) {
      const body = actor.root.body;
      if (![actor.root.x, actor.root.y, body?.velocity.x ?? 0, body?.velocity.y ?? 0].every(finite)) fail('Runtime numeric bounds exceeded');
    }
    if (overlapBudget) fail('Overlap event candidate budget exceeded');
    const triggers = outcome ? [] : source.rules.filter((rule) => rule.enabled && rule.spec.scene_id === activeSceneId).map((rule) => ({ rule, contexts: triggerContexts(rule) }));
    const deferred = [];
    let nextScene;

    function action(spec, match = {}, spawnedBy) {
      if (!countAction()) return;
      const target = spec.target === 'left' || spec.target === 'right' ? match[spec.target] : spec.target;
      if (spec.kind === 'finish') { outcome = spec.result; reason = spec.message; }
      else if (spec.kind === 'variable_set' || spec.kind === 'variable_add') {
        const value = spec.kind === 'variable_set' ? spec.value : variables.get(spec.variable_id) + spec.amount;
        const type = source.variables.find((item) => item.id === spec.variable_id).value_type;
        if ((type !== 'bool' && !finite(value)) || (type === 'int' && !Number.isInteger(value))) { fail('Runtime variable bounds exceeded'); return; }
        variables.set(spec.variable_id, value);
        emit('variable', `${source.variables.find((item) => item.id === spec.variable_id).name} = ${value}`);
      } else if (spec.kind === 'damage') {
        const actor = actors.get(target);
        if (actor && actor.health !== undefined) {
          actor.health = Math.max(0, actor.health - spec.amount);
          emit('damage', `${spec.amount} damage; health ${actor.health}`, [target]);
        }
      } else if (spec.kind === 'despawn') deferred.push({ kind: 'despawn', target });
      else if (spec.kind === 'spawn') deferred.push({ ...spec, spawnedBy });
      else if (spec.kind === 'scene_change') {
        if (nextScene === undefined) nextScene = spec.scene_id;
        else emit('ignored_scene_change', 'A previous scene change already owns this tick');
      }
    }

    if (!outcome) {
      for (const { rule, contexts } of triggers) {
        for (const match of contexts) {
          if (rule.spec.trigger.kind === 'overlap') emit('overlap', rule.spec.name, [match.left, match.right]);
          if (outcome) break;
          for (const spec of rule.spec.actions) { action(spec, match); if (outcome) break; }
          if (outcome) break;
        }
        if (outcome) break;
      }
    }
    if (!outcome) {
      for (const behavior of behaviorSpecs) {
        const spec = behavior.spec;
        for (const actor of actorsByTemplate.get(spec.entity_id) ?? []) {
          if (spec.kind === 'lifetime' && globalTick - actor.born >= spec.ticks) action({ kind: 'despawn', target: actor.id });
          if (spec.kind === 'spawn' && (globalTick - actor.born) % spec.interval_ticks === 0) {
            const spawner = actor.id + '/' + behavior.id;
            const alive = [...actors.values()].filter((item) => item.spawnedBy === spawner).length;
            const count = Math.min(spec.count, spec.max_alive - alive);
            if (count > 0) action({ kind: 'spawn', template_id: spec.template_id, count, region: spec.region }, {}, spawner);
          }
          if (outcome) break;
        }
        if (outcome) break;
      }
    }
    for (const pending of deferred) {
      if (pending.kind === 'despawn') removeActor(pending.target);
      else {
        for (let i = 0; i < pending.count; i += 1) {
          if (actors.size >= MAX_ACTORS) { fail('Active entity budget exceeded'); break; }
          const template = templates.get(pending.template_id);
          const identity = `${template.id}:${++spawnOrdinal}`;
          const x = rng.realInRange(pending.region.x, pending.region.x + pending.region.width);
          const y = rng.realInRange(pending.region.y, pending.region.y + pending.region.height);
          addActor(template, identity, x, y, pending.spawnedBy);
          emit('spawn', 'Entity spawned from ' + template.name, [identity]);
        }
      }
      if (outcome === 'budget_exceeded') break;
    }
    if (!outcome && nextScene !== undefined) {
      emit('scene_change', 'Entering ' + sceneSpecs.get(nextScene).name);
      loadScene(nextScene);
    }
    for (const actor of actors.values()) actor.artwork?.setPosition(actor.root.x, actor.root.y);
    if (outcome) emit(outcome === 'budget_exceeded' ? 'budget_exceeded' : 'finish', reason, [], true);
  }

  const start = sceneSpecs.get(activeSceneId);
  game = new Phaser.Game({
    type: headless ? Phaser.HEADLESS : Phaser.CANVAS,
    parent,
    width: start.width,
    height: start.height,
    // Phaser's public canvasStyle owns its canvas; DLC CSS need not override
    // engine inline dimensions with !important or affect any Host canvas.
    canvasStyle: 'display:block;width:100%;height:100%;',
    banner: false,
    audio: { noAudio: true },
    autoFocus: false,
    input: { keyboard: false, mouse: false, touch: false, gamepad: false },
    physics: { default: 'arcade', arcade: { customUpdate: true, fixedStep: true, fps: 60, timeScale: 1, gravity: { x: 0, y: 0 } } },
    scene: {
      create() {
        try {
          engineScene = this;
          dynamicGroup = this.physics.add.group();
          staticGroup = this.physics.add.staticGroup();
          this.physics.add.overlap(dynamicGroup, dynamicGroup, captureOverlap);
          this.physics.add.overlap(dynamicGroup, staticGroup, captureOverlap);
          this.physics.add.overlap(staticGroup, staticGroup, captureOverlap);
          this.physics.add.collider(dynamicGroup, dynamicGroup, undefined, solid);
          this.physics.add.collider(dynamicGroup, staticGroup, undefined, solid);
          queueMicrotask(() => {
            if (destroyed) return;
            try { game.loop.stop(); loadScene(activeSceneId); resolveReady(); }
            catch (error) { rejectReady(error); }
          });
        } catch (error) { rejectReady(error); }
      },
      update() { if (advanceRequested && !outcome && globalTick < ticks) advance(); },
    },
  });
  const timeout = setTimeout(() => rejectReady(new Error('Phaser scene did not become ready.')), 5000);
  const abort = () => { rejectReady(abortError()); destroy(); };
  signal?.addEventListener('abort', abort, { once: true });

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    clearTimeout(timeout);
    signal?.removeEventListener('abort', abort);
    game.destroy(true, false);
    game.headlessStep(0, 0);
    actors.clear();
    events = [];
  }

  try { await ready; }
  catch (error) { destroy(); throw error; }
  finally { clearTimeout(timeout); }

  function snapshot() {
    return {
      engine: ENGINE,
      seed,
      ticks_requested: ticks,
      ticks_completed: globalTick,
      scene_tick: sceneTick,
      scene_id: activeSceneId,
      outcome: outcome ?? (globalTick < ticks ? 'running' : 'exhausted'),
      reason,
      event_count: eventCount,
      events_truncated: eventCount > events.length,
      events: structuredClone(events),
      entities: orderedActors().map((actor) => ({
        id: actor.id, template_id: actor.template.id, scene_id: activeSceneId,
        x: actor.root.x, y: actor.root.y,
        vx: actor.root.body?.velocity.x ?? 0, vy: actor.root.body?.velocity.y ?? 0,
        ...(actor.health === undefined ? {} : { health: actor.health }),
      })),
      variables: Object.fromEntries(variables),
    };
  }

  return {
    game,
    destroy,
    snapshot,
    get tick() { return globalTick; },
    get done() { return destroyed || Boolean(outcome) || globalTick >= ticks; },
    get scene() { return sceneSpecs.get(activeSceneId); },
    get canvas() { return game.canvas; },
    setActions(entityId, actions) { actionInputs.set(entityId, new Set(actions)); },
    step(draw = !headless) {
      if (destroyed || signal?.aborted) throw abortError();
      if (outcome || globalTick >= ticks) return snapshot();
      advanceRequested = true;
      try { (draw ? game.step : game.headlessStep).call(game, (globalTick + 1) * TICK_MS, TICK_MS); }
      finally { advanceRequested = false; }
      return draw ? snapshot() : undefined;
    },
    render() {
      if (!destroyed && !headless) game.step(globalTick * TICK_MS, 0);
    },
    pick(x, y) {
      const ordered = [...actors.values()].reverse().sort((a, b) => (b.parts.get('visual')?.depth ?? 0) - (a.parts.get('visual')?.depth ?? 0));
      return ordered.find((actor) => Phaser.Geom.Rectangle.Contains(actor.root.getBounds(), x, y))?.id;
    },
    previewPositions(changes) {
      if (destroyed || globalTick) return;
      for (const { id, x, y } of changes) {
        const actor = actors.get(id);
        if (!actor) continue;
        actor.root.setPosition(x, y);
        if (actor.root.body) actor.root.body.reset(x, y);
        actor.artwork?.setPosition(x, y);
      }
      this.render();
    },
  };
}

export async function runPlaytest(options, { signal, deadline = performance.now() + 20000, onProgress = () => {} } = {}) {
  const runtime = await createRuntime({ ...options, headless: true, signal });
  try {
    while (!runtime.done) {
      for (let i = 0; i < 32 && !runtime.done; i += 1) {
        if (signal?.aborted) throw abortError();
        if (performance.now() >= deadline) throw new DOMException('Playtest deadline exceeded.', 'TimeoutError');
        runtime.step(false);
      }
      onProgress(runtime.tick);
      if (!runtime.done) await new Promise((resolve) => setTimeout(resolve, 0));
    }
    // Abort destroys the Phaser instance and therefore also makes `done` true.
    // A destroyed partial run must never be reported as successful completion.
    if (signal?.aborted) throw abortError();
    return runtime.snapshot();
  } finally { runtime.destroy(); }
}
