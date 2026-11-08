import { createRenderer, RenderFailure } from './renderer.js';

export function packageDigestFromUrl(moduleUrl) {
  const url = new URL(moduleUrl);
  const match = /^\/([a-f0-9]{64})\/frontend\/[^?#]+$/.exec(url.pathname);
  if (url.protocol !== 'dlc-asset:' || url.hostname !== 'localhost' || url.port || url.username || url.password || url.search || url.hash || !match) {
    throw new Error('GPU execution requires the installed, content-addressed DLC asset URL.');
  }
  return match[1];
}

function delay(ms, signal) {
  return new Promise((resolve) => {
    const finish = () => { clearTimeout(timer); signal.removeEventListener('abort', finish); resolve(); };
    const timer = setTimeout(finish, ms);
    signal.addEventListener('abort', finish, { once: true });
    if (signal.aborted) finish();
  });
}

// One instance per Host activation; each callback captures only that activation.
// The identity counter belongs to the ESM caller so re-register cannot reuse it.
export function createExecutor(host, identity, { makeCanvas = () => document.createElement('canvas'), rendererFactory = createRenderer, visibility = document } = {}) {
  let closed = false;
  let current = null;
  let status = Object.freeze({ state: 'starting', message: 'Starting WebGL 2 executor…' });
  const listeners = new Set();
  const publish = (state, message) => { status = Object.freeze({ state, message }); listeners.forEach((listener) => listener()); };
  const invoke = (name, input, signal) => host.operations.invoke(name, input, { signal });

  async function detach(lease, reason) {
    if (!lease) return;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1000);
    try { await invoke('compute.detach', { epoch: lease.epoch, lease: lease.lease, reason }, controller.signal); }
    catch { /* The backend lease and Tool deadline bound an unreachable detach. */ }
    finally { clearTimeout(timeout); }
  }

  function retire(reason, message) {
    const old = current;
    current = null;
    if (old) {
      old.controller.abort();
      old.canvas.removeEventListener('webglcontextlost', old.contextLost);
      old.renderer?.dispose();
      void detach(old.lease, reason);
    }
    publish(closed ? 'closed' : 'unavailable', message);
  }

  async function start() {
    if (closed || current || visibility.visibilityState === 'hidden') return;
    const controller = new AbortController();
    const canvas = makeCanvas();
    const owner = { controller, canvas, renderer: null, lease: null, job: null, counter: identity.nextCounter(), contextLost: null };
    current = owner;
    const alive = () => !closed && current === owner && !controller.signal.aborted;
    owner.contextLost = (event) => { event.preventDefault(); if (alive()) retire('context_lost', 'WebGL context was lost. Reconnect explicitly to accept future work.'); };
    canvas.addEventListener('webglcontextlost', owner.contextLost);
    publish('starting', 'Starting WebGL 2 executor…');
    try {
      owner.renderer = rendererFactory(canvas);
      const lease = await invoke('compute.attach', {
        client_id: identity.clientId, registration_counter: owner.counter,
        package_digest: identity.packageDigest, available: true, capabilities: owner.renderer.capabilities,
      }, controller.signal);
      if (!alive()) { void detach(lease, 'deactivate'); return; }
      owner.lease = lease;
      if (lease.server_status !== 'ready') throw new Error('The GPU executor lease is unavailable.');
      const leaseInput = { epoch: lease.epoch, lease: lease.lease, registration_counter: owner.counter };
      publish('ready', 'WebGL 2 ready · available while this app is visible');

      async function perform(request) {
        const deadline = performance.now() + request.remaining_ms;
        const timeout = setTimeout(() => { if (alive()) retire('network_error', 'GPU deadline expired. The request will not be replayed.'); }, request.remaining_ms);
        publish('computing', request.kind === 'preview' ? 'Rendering an authorized immutable revision…' : 'Compiling an authorized immutable revision…');
        try {
          let result;
          try { result = await owner.renderer.execute(request.snapshot, { kind: request.kind, signal: controller.signal, deadline }); }
          catch (error) {
            if (!alive()) return;
            if (error instanceof RenderFailure && ['CONTEXT_LOST', 'COMPUTE_TIMEOUT', 'EXECUTOR_UNAVAILABLE'].includes(error.code)) throw error;
            result = { compiled: false, rendered: false, diagnostics: [{ severity: 'error', code: error instanceof RenderFailure ? error.code : 'GPU_ERROR', message: error instanceof RenderFailure ? error.message : 'WebGL execution failed.' }], logs: [], log_truncated: 0 };
          }
          if (!alive() || performance.now() >= deadline) throw new RenderFailure('COMPUTE_TIMEOUT', 'The computation deadline expired before handoff.');
          // Copy exact frozen request proof, never source it from a mutable Workbench.
          await invoke('compute.complete', {
            ...leaseInput, package_digest: identity.packageDigest,
            request_id: request.request_id, claim: request.claim, invocation_id: request.invocation_id,
            document_id: request.document_id, version: request.version, content_hash: request.content_hash,
            request_hash: request.request_hash, result,
          }, controller.signal);
          if (alive()) publish('ready', 'WebGL 2 ready · computation handed to its original Tool');
        } catch (error) {
          if (alive()) retire(error instanceof RenderFailure && error.code === 'CONTEXT_LOST' ? 'context_lost' : 'network_error', 'GPU handoff stopped. Its outcome is not replayed; inspect the original Run.');
        } finally { clearTimeout(timeout); }
      }

      while (alive()) {
        const next = await invoke('compute.next', leaseInput, controller.signal);
        if (!alive()) break;
        if (next.status === 'request') {
          if (!next.request || owner.job) throw new Error('The owner returned overlapping compute work.');
          const job = perform(next.request);
          owner.job = job;
          void job.finally(() => { if (owner.job === job) owner.job = null; });
        }
        // Renew the lease even while KHR compilation is awaiting completion.
        await delay(500, controller.signal);
      }
    } catch {
      if (alive()) retire('network_error', 'GPU executor unavailable. Reconnect explicitly; no computation is retried.');
    }
  }

  const onVisibility = () => {
    if (visibility.visibilityState === 'hidden') retire('hidden', 'GPU executor paused while the app is hidden.');
    else void start(); // A fresh epoch only; old requests were cancelled, never replayed.
  };
  const onPageHide = () => retire('hidden', 'GPU executor stopped because the renderer is leaving.');
  visibility.addEventListener('visibilitychange', onVisibility);
  globalThis.addEventListener('pagehide', onPageHide);
  void start();
  return {
    getSnapshot: () => status,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    reconnect() { if (!closed && !current) void start(); },
    dispose() {
      if (closed) return;
      closed = true;
      visibility.removeEventListener('visibilitychange', onVisibility);
      globalThis.removeEventListener('pagehide', onPageHide);
      retire('deactivate', 'GPU executor deactivated.');
      listeners.clear();
    },
  };
}
