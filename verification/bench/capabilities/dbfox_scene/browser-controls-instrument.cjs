async (page) => {
  // Observe native APIs without replacing WebGL, Three, React or product handlers.
  // Installed before mounting the owner; restore() removes every instrumentation hook.
  return page.evaluate(() => {
    if (globalThis.sceneControlsProbe) throw new Error('Probe already installed');
    const originals = { add: EventTarget.prototype.addEventListener, remove: EventTarget.prototype.removeEventListener,
      raf: requestAnimationFrame, caf: cancelAnimationFrame, timeout: setTimeout, clear: clearTimeout,
      resize: ResizeObserver, intersection: IntersectionObserver, context: HTMLCanvasElement.prototype.getContext };
    const listeners = [], frames = new Map(), timers = new Map(), observers = [], canvases = [];
    let serial = 0;
    const stack = () => new Error().stack || '';
    // The Host URLs identify the signed digest rather than the owner name.
    // This isolated fixture has exactly one active DLC.
    const owned = value => /dlc-asset:\/\/localhost\/[a-f0-9]{64}\//.test(value);
    const capture = value => typeof value === 'boolean' ? value : !!value?.capture;
    const targetName = target => target === document ? 'document' : target === window ? 'window' : target instanceof HTMLCanvasElement ? 'canvas' : 'other';
    EventTarget.prototype.addEventListener = function(type, callback, options) {
      const source = stack();
      if (owned(source) && ['document', 'window', 'canvas'].includes(targetName(this)) && callback) {
        if (!listeners.some(item => item.active && item.target === this && item.type === type && item.callback === callback && item.capture === capture(options))) {
          listeners.push({id: ++serial, target: this, name: targetName(this), type, callback, capture: capture(options), active: true, source});
        }
      }
      return originals.add.call(this, type, callback, options);
    };
    EventTarget.prototype.removeEventListener = function(type, callback, options) {
      for (const item of listeners) if (item.active && item.target === this && item.type === type && item.callback === callback && item.capture === capture(options)) {
        item.active = false;
        item.removedWithCanvasAttached = canvases.some(entry => entry.canvas.isConnected);
        item.targetConnectedOnRemove = this === document || this === window || this.isConnected;
      }
      return originals.remove.call(this, type, callback, options);
    };
    globalThis.requestAnimationFrame = callback => {
      const source = stack();
      if (!owned(source)) return originals.raf.call(window, callback);
      const item = {id: 0, active: true, ran: false, source};
      item.id = originals.raf.call(window, time => { item.active = false; item.ran = true; callback(time); });
      frames.set(item.id, item);
      return item.id;
    };
    globalThis.cancelAnimationFrame = id => { if (frames.has(id)) frames.get(id).active = false; return originals.caf.call(window, id); };
    globalThis.setTimeout = (callback, delay, ...args) => {
      const source = stack();
      if (!owned(source) || typeof callback !== 'function') return originals.timeout.call(window, callback, delay, ...args);
      const item = {id: 0, delay, active: true, ran: false, source};
      item.id = originals.timeout.call(window, () => { item.active = false; item.ran = true; callback(...args); }, delay);
      timers.set(item.id, item);
      return item.id;
    };
    globalThis.clearTimeout = id => { if (timers.has(id)) timers.get(id).active = false; return originals.clear.call(window, id); };
    for (const [name, Native] of [['ResizeObserver', originals.resize], ['IntersectionObserver', originals.intersection]]) {
      globalThis[name] = class extends Native {
        constructor(callback, options) {
          const item = {name, active: false, calls: 0, source: stack(), targets: []};
          super((...args) => { item.calls++; callback(...args); }, options);
          this.probeItem = item;
          if (owned(item.source)) observers.push(item);
        }
        observe(target, options) { this.probeItem.active = true; this.probeItem.targets.push(target); return super.observe(target, options); }
        disconnect() { this.probeItem.active = false; return super.disconnect(); }
      };
    }
    HTMLCanvasElement.prototype.getContext = function(type, ...args) {
      const result = originals.context.call(this, type, ...args);
      if (result && ['webgl', 'webgl2'].includes(type) && owned(stack()) && !canvases.some(item => item.canvas === this)) {
        canvases.push({canvas: this, gl: result, id: ++serial});
      }
      return result;
    };
    globalThis.sceneControlsProbe = {
      listeners, canvases,
      read() {
        const counts = items => ({total: items.length, active: items.filter(item => item.active).length});
        return {
          listeners: listeners.map(({id, name, type, capture, active, removedWithCanvasAttached, targetConnectedOnRemove}) => ({id, name, type, capture, active, removedWithCanvasAttached, targetConnectedOnRemove})),
          raf: {...counts([...frames.values()]), ran: [...frames.values()].filter(item => item.ran).length},
          timers: {...counts([...timers.values()]), delays: [...timers.values()].filter(item => item.active).map(item => item.delay)},
          observers: observers.map(({name, active, calls}) => ({name, active, calls})),
          canvases: canvases.map(({id, canvas, gl}) => ({id, connected: canvas.isConnected, lost: gl.isContextLost(), version: gl.getParameter(gl.VERSION)})),
          domCanvases: document.querySelectorAll('.dbfox-scene canvas').length,
          stylesheets: document.querySelectorAll('link[data-dbfox-dlc="dbfox.scene"]').length,
        };
      },
      restore() {
        EventTarget.prototype.addEventListener = originals.add;
        EventTarget.prototype.removeEventListener = originals.remove;
        globalThis.requestAnimationFrame = originals.raf; globalThis.cancelAnimationFrame = originals.caf;
        globalThis.setTimeout = originals.timeout; globalThis.clearTimeout = originals.clear;
        globalThis.ResizeObserver = originals.resize; globalThis.IntersectionObserver = originals.intersection;
        HTMLCanvasElement.prototype.getContext = originals.context;
        delete globalThis.sceneControlsProbe;
      },
    };
    return {installed: true, replacementRenderer: false};
  });
}
