import { createRuntime, TICK_MS } from './runtime.js';
import { errorText, part } from './model.js';

export function createViewport(React) {
  const h = React.createElement;
  return function Viewport({ snapshot, sceneId, selection, onSelect, onMove, readOnly = false, busy, playing, setPlaying, resetKey, stepKey, seed, onState, onInputs, onError, registerCleanup }) {
    const parent = React.useRef(null);
    const container = React.useRef(null);
    const engine = React.useRef(null);
    const live = React.useRef({});
    live.current = { snapshot, sceneId, selection, onSelect, onMove, readOnly, busy, playing, setPlaying, onState, onInputs, onError };
    const [ready, setReady] = React.useState(false);
    const [runtimeScene, setRuntimeScene] = React.useState(null);

    React.useEffect(() => {
      const controller = new AbortController();
      let runtime;
      let frame;
      let last;
      let accumulator = 0;
      let wasPlaying = false;
      let stopped = false;
      let drag;
      const keys = new Set();
      const recorded = [];
      let lastInputTick = -1;
      setReady(false);
      const element = container.current;
      const game = snapshot.document;
      const templates = new Map(game.entities.map((item) => [item.id, item]));
      function publish() {
        if (runtime) {
          live.current.onState(runtime.snapshot());
          setRuntimeScene(runtime.scene);
        }
      }
      function actions() {
        if (!runtime) return;
        const next = [...keys].sort();
        const controllers = game.behaviors.filter((item) => item.enabled && item.spec.kind === 'player_control');
        for (const behavior of controllers) {
          runtime.setActions(behavior.spec.entity_id, next);
          const event = { tick: runtime.tick, entity_id: behavior.spec.entity_id, actions: next };
          const duplicate = recorded.findIndex((item) => item.tick === event.tick && item.entity_id === event.entity_id);
          if (duplicate >= 0) recorded[duplicate] = event;
          else if (recorded.length < 1024 && event.tick < 7200) recorded.push(event);
          else { live.current.setPlaying(false); live.current.onError('输入记录已达 1024 条，请重置后继续。'); }
        }
        recorded.sort((left, right) => left.tick - right.tick || (left.entity_id < right.entity_id ? -1 : left.entity_id > right.entity_id ? 1 : 0));
        live.current.onInputs(structuredClone(recorded));
        lastInputTick = runtime.tick;
      }
      function clearInput() { if (keys.size) { keys.clear(); actions(); } }
      const keyMap = { ArrowUp: 'up', KeyW: 'up', ArrowDown: 'down', KeyS: 'down', ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right' };
      const pressed = new Set();
      const keydown = (event) => {
        if (!live.current.playing || !keyMap[event.code] || event.ctrlKey || event.metaKey || event.altKey) return;
        event.preventDefault();
        if (pressed.has(event.code)) return;
        pressed.add(event.code);
        keys.clear(); pressed.forEach((code) => keys.add(keyMap[code])); actions();
      };
      const keyup = (event) => {
        if (!keyMap[event.code]) return;
        event.preventDefault();
        pressed.delete(event.code);
        keys.clear(); pressed.forEach((code) => keys.add(keyMap[code])); actions();
      };
      const blur = () => { pressed.clear(); clearInput(); live.current.setPlaying(false); };
      const visibility = () => { if (document.visibilityState === 'hidden') blur(); };
      function point(event) {
        const bounds = runtime.canvas.getBoundingClientRect();
        return { x: (event.clientX - bounds.left) * runtime.scene.width / bounds.width, y: (event.clientY - bounds.top) * runtime.scene.height / bounds.height };
      }
      function restore() {
        if (drag) runtime?.previewPositions(drag.origins);
        drag = undefined;
      }
      const pointerdown = (event) => {
        if (!runtime || event.button !== 0 || live.current.busy || live.current.playing || live.current.readOnly) return;
        element.focus();
        const start = point(event);
        const id = runtime.pick(start.x, start.y)?.split(':')[0];
        if (!id) { live.current.onSelect([]); return; }
        const selected = event.shiftKey ? [...new Set([...live.current.selection, id])].slice(0, 128) : live.current.selection.includes(id) ? live.current.selection : [id];
        live.current.onSelect(selected);
        if (runtime.tick !== 0) return;
        const origins = selected.map((identity) => ({ id: identity, ...part(templates.get(identity), 'transform').spec }));
        drag = { start, origins, dx: 0, dy: 0, pointer: event.pointerId };
        element.setPointerCapture(event.pointerId);
      };
      const pointermove = (event) => {
        if (!drag || drag.pointer !== event.pointerId) return;
        const next = point(event);
        drag.dx = Math.round(next.x - drag.start.x);
        drag.dy = Math.round(next.y - drag.start.y);
        runtime.previewPositions(drag.origins.map((item) => ({ id: item.id, x: item.x + drag.dx, y: item.y + drag.dy })));
      };
      const pointerup = (event) => {
        if (!drag || drag.pointer !== event.pointerId) return;
        const finished = drag;
        drag = undefined;
        if (element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId);
        if (finished.dx || finished.dy) void live.current.onMove(finished.origins.map((item) => item.id), finished.dx, finished.dy).then((saved) => { if (!saved && !stopped) runtime.previewPositions(finished.origins); });
      };
      const pointercancel = () => restore();
      const observer = new IntersectionObserver((entries) => { if (!entries.some((entry) => entry.isIntersecting)) blur(); });
      observer.observe(element);
      element.addEventListener('keydown', keydown);
      element.addEventListener('keyup', keyup);
      element.addEventListener('blur', blur);
      element.addEventListener('pointerdown', pointerdown);
      element.addEventListener('pointermove', pointermove);
      element.addEventListener('pointerup', pointerup);
      element.addEventListener('pointercancel', pointercancel);
      element.addEventListener('lostpointercapture', pointercancel);
      document.addEventListener('visibilitychange', visibility);

      const stop = () => {
        if (stopped) return;
        stopped = true;
        controller.abort();
        cancelAnimationFrame(frame);
        observer.disconnect();
        element.removeEventListener('keydown', keydown); element.removeEventListener('keyup', keyup); element.removeEventListener('blur', blur);
        element.removeEventListener('pointerdown', pointerdown); element.removeEventListener('pointermove', pointermove); element.removeEventListener('pointerup', pointerup);
        element.removeEventListener('pointercancel', pointercancel); element.removeEventListener('lostpointercapture', pointercancel);
        document.removeEventListener('visibilitychange', visibility);
        runtime?.destroy();
        if (engine.current === runtime) engine.current = null;
      };
      const unregister = registerCleanup(stop);
      createRuntime({ document: { ...game, initial_scene_id: sceneId }, rgba_assets: snapshot.rgba_assets, parent: parent.current, seed, signal: controller.signal }).then((created) => {
        if (stopped) { created.destroy(); return; }
        runtime = created;
        engine.current = runtime;
        runtime.render(); publish(); setReady(true);
        live.current.onInputs([]);
        const animate = (now) => {
          if (stopped) return;
          const play = live.current.playing && !live.current.busy && document.visibilityState !== 'hidden';
          if (play && !wasPlaying) { last = now; accumulator = 0; if (lastInputTick !== runtime.tick) actions(); }
          if (!play && wasPlaying) clearInput();
          wasPlaying = play;
          try {
            if (play && !runtime.done) {
              accumulator += Math.min(100, now - (last ?? now));
              last = now;
              let stepped = false;
              while (accumulator >= TICK_MS && !runtime.done) { runtime.step(false); accumulator -= TICK_MS; stepped = true; }
              if (stepped) { runtime.render(); publish(); }
              if (runtime.done) live.current.setPlaying(false);
            }
          } catch (error) { live.current.setPlaying(false); live.current.onError(errorText(error)); }
          frame = requestAnimationFrame(animate);
        };
        frame = requestAnimationFrame(animate);
      }).catch((error) => { if (!stopped) live.current.onError(errorText(error)); });
      return () => { unregister(); stop(); };
    }, [snapshot, sceneId, seed, resetKey, registerCleanup]);

    React.useEffect(() => {
      if (!stepKey || !engine.current || playing || busy) return;
      try { engine.current.step(); live.current.onState(engine.current.snapshot()); setRuntimeScene(engine.current.scene); }
      catch (error) { live.current.onError(errorText(error)); }
    }, [stepKey]);

    const scene = runtimeScene ?? snapshot.document.scenes.find((item) => item.id === sceneId);
    return h('div', { className: 'game-viewport-frame' },
      h('div', { ref: container, className: 'game-viewport', tabIndex: 0, role: 'application', 'aria-label': readOnly ? '固定版本游戏预览：播放时使用方向键或 WASD' : '游戏预览：播放时使用方向键或 WASD；编辑时拖动实体，Shift 多选', style: { aspectRatio: `${scene.width} / ${scene.height}` } }, h('div', { ref: parent, className: 'game-canvas-parent' }),
        !playing && selection.map((id) => {
          const entity = snapshot.document.entities.find((item) => item.id === id && item.scene_id === scene.id && item.enabled);
          const transform = part(entity, 'transform')?.spec;
          if (!transform) return null;
          return h('span', { key: id, className: 'game-selection-box', style: { left: `${(transform.x - transform.width / 2) / scene.width * 100}%`, top: `${(transform.y - transform.height / 2) / scene.height * 100}%`, width: `${transform.width / scene.width * 100}%`, height: `${transform.height / scene.height * 100}%` } }, h('span', null, entity.name));
        }), !ready && h('div', { className: 'game-viewport-loading', role: 'status' }, '正在启动 Phaser 场景…')),
      h('p', { className: 'game-help' }, readOnly ? 'WASD / 方向键移动 · 点击预览获取键盘焦点 · 固定版本只读' : 'WASD / 方向键移动 · 点击预览获取键盘焦点 · Shift 多选 · 重置到 tick 0 后可拖动实体'),
    );
  };
}
