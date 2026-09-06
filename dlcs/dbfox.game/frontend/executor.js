import { ENGINE, runPlaytest } from './runtime.js';

export function packageDigestFromUrl(moduleUrl) {
  const url = new URL(moduleUrl);
  const match = /^\/([a-f0-9]{64})\/frontend\/[^?#]+$/.exec(url.pathname);
  if (url.protocol !== 'dlc-asset:' || url.hostname !== 'localhost' || url.port || url.username || url.password || url.search || url.hash || !match) {
    throw new Error('Playtest requires the installed, content-addressed Game package.');
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

/** One activation accepts only the backend's single claimed, immutable request. */
export function createExecutor(host, identity, { execute = runPlaytest, visibility = document } = {}) {
  let closed = false;
  let current;
  let status = Object.freeze({ state: 'starting', message: '正在连接 Phaser 执行器…' });
  const listeners = new Set();
  const publish = (state, message) => { status = Object.freeze({ state, message }); listeners.forEach((listener) => listener()); };
  const invoke = (name, input, signal) => host.operations.invoke(name, input, { signal });

  async function detach(lease) {
    if (!lease) return;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1000);
    try { await invoke('playtest.detach', lease, controller.signal); }
    catch { /* The server lease and original Tool deadline bound unreachable detach. */ }
    finally { clearTimeout(timeout); }
  }

  function retire(message) {
    const owner = current;
    current = undefined;
    owner?.controller.abort();
    if (owner) void detach(owner.lease);
    publish(closed ? 'closed' : 'unavailable', message);
  }

  async function start() {
    if (closed || current || visibility.visibilityState === 'hidden') return;
    const controller = new AbortController();
    const owner = { controller, counter: identity.nextCounter(), lease: undefined, job: undefined };
    current = owner;
    const alive = () => !closed && current === owner && !controller.signal.aborted;
    publish('starting', '正在连接 Phaser 执行器…');
    try {
      const attachment = await invoke('playtest.attach', {
        client_id: identity.clientId, registration_counter: owner.counter,
        package_digest: identity.packageDigest, engine: ENGINE, available: true,
      }, controller.signal);
      const lease = { epoch: attachment.epoch, lease: attachment.lease, registration_counter: owner.counter };
      if (!alive()) { void detach(lease); return; }
      owner.lease = lease;
      if (!attachment.available) throw new Error('Phaser executor is unavailable.');
      publish('ready', 'Phaser 4.2.1 已连接 · 应用可见时可运行 playtest');

      async function perform(request) {
        const deadline = performance.now() + request.remaining_ms;
        const timeout = setTimeout(() => { if (alive()) retire('Playtest 超时；原请求不会重放。'); }, request.remaining_ms);
        publish('running', '正在执行固定版本的 Phaser playtest…');
        try {
          let result;
          try {
            if (request.snapshot.document.id !== request.game_id || request.snapshot.revision.version !== request.version || request.snapshot.revision.content_hash !== request.source_hash) throw new Error('Frozen snapshot proof does not match.');
            const report = await execute({
              document: request.snapshot.document, rgba_assets: request.snapshot.rgba_assets,
              seed: request.input.seed, ticks: request.input.ticks, inputs: request.input.inputs,
            }, { signal: controller.signal, deadline });
            result = { report };
          } catch (error) {
            if (!alive()) return;
            result = { error: error?.name === 'TimeoutError' ? 'DEADLINE_EXCEEDED' : 'ENGINE_FAILURE' };
          }
          if (!alive() || performance.now() >= deadline) throw new Error('Playtest deadline expired.');
          const acknowledgement = await invoke('playtest.complete', {
            ...lease, package_digest: identity.packageDigest,
            request_id: request.request_id, invocation_id: request.invocation_id,
            game_id: request.game_id, version: request.version, source_hash: request.source_hash,
            input_hash: request.input_hash, claim_id: request.claim_id, ...result,
          }, controller.signal);
          if (!acknowledgement.accepted) throw new Error('Playtest handoff was rejected.');
          if (alive()) publish('ready', 'Phaser 结果已交回原 Tool；耐久结果由原 Run 结算');
        } catch {
          if (alive()) retire('Playtest 交接中断；请查看原 Run，不自动重放。');
        } finally { clearTimeout(timeout); }
      }

      while (alive()) {
        const next = await invoke('playtest.next', lease, controller.signal);
        if (!alive()) break;
        if (next.status === 'request') {
          if (!next.request || owner.job) throw new Error('Overlapping playtest requests are invalid.');
          const job = perform(next.request);
          owner.job = job;
          void job.finally(() => { if (owner.job === job) owner.job = undefined; });
        }
        // Keep the lease alive while accelerated stepping yields between batches.
        await delay(500, controller.signal);
      }
    } catch {
      if (alive()) retire('Phaser 执行器连接中断。可手动重新连接以接收新的请求。');
    }
  }

  const visible = () => {
    if (visibility.visibilityState === 'hidden') retire('应用隐藏，Phaser playtest 已停止。');
    else void start();
  };
  const leaving = () => retire('窗口离开，Phaser playtest 已停止。');
  visibility.addEventListener('visibilitychange', visible);
  globalThis.addEventListener('pagehide', leaving);
  void start();
  return {
    getSnapshot: () => status,
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    reconnect() { if (!closed && !current) void start(); },
    dispose() {
      if (closed) return;
      closed = true;
      visibility.removeEventListener('visibilitychange', visible);
      globalThis.removeEventListener('pagehide', leaving);
      retire('Game 执行器已卸载。');
      listeners.clear();
    },
  };
}
