import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

type Locator = { project_id: string; document_id: string; title: string; version: number; content_hash: string; report_id: string | null };
type ArtifactModule = { parseLocator(payload: unknown): Locator };

async function owner<T>(name: string): Promise<T> {
  const file = resolve(process.cwd(), '../dlcs/dbfox.shader/frontend', name);
  const bundled = execFileSync(process.execPath, ['-e', "require('esbuild').build({entryPoints:[process.argv[1]],bundle:true,format:'esm',platform:'browser',write:false}).then(r=>process.stdout.write(r.outputFiles[0].text))", file], { encoding: 'utf8', windowsHide: true });
  return import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(bundled).toString('base64')}`) as Promise<T>;
}

describe('Independent Shader Artifact contract against actual production Agent output', () => {
  it('accepts every real producer document/report/preview locator, including the public nullable report id', async () => {
    const module = await owner<ArtifactModule>('artifacts.js');
    const proof = JSON.parse(readFileSync(resolve(process.cwd(), '../verification/testkit/shader_independent/evidence/electron-native-agent-fixed.json'), 'utf8')) as { artifacts: { type: string; payload: Locator }[] };
    expect(proof.artifacts).toHaveLength(8);
    const revisions = proof.artifacts.filter(item => item.type === 'dbfox.shader.document-revision');
    expect(revisions).toHaveLength(4);
    expect(revisions.every(item => item.payload.report_id === null)).toBe(true);
    for (const item of proof.artifacts) expect(module.parseLocator(item.payload)).toEqual(item.payload);
  });
  it.each([false, true, 0, {}, []])('still rejects a non-null, non-string report id: %j', async value => {
    const module = await owner<ArtifactModule>('artifacts.js');
    expect(() => module.parseLocator({ project_id: 'project', document_id: 'document', title: 'Revision', version: 1, content_hash: 'a'.repeat(64), report_id: value })).toThrow('report identity');
  });
});

type Invoke = (name: string, input: Record<string, unknown>, options: { signal: AbortSignal }) => Promise<unknown>;
type Renderer = { capabilities: object; execute(...args: unknown[]): Promise<object>; dispose(): void };
type Executor = { dispose(): void; reconnect(): void; getSnapshot(): { state: string } };
type ExecutorModule = { createExecutor(host: { operations: { invoke: Invoke } }, identity: { clientId: string; packageDigest: string; nextCounter(): number }, options: { makeCanvas(): HTMLCanvasElement; rendererFactory(): Renderer; visibility: EventTarget & { visibilityState: string } }): Executor };
const retired: Executor[] = [];
afterEach(() => { retired.splice(0).forEach(executor => executor.dispose()); vi.useRealTimers(); });
function pending<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
const identity = () => { let counter = 0; return { clientId: 'independent-client', packageDigest: 'd'.repeat(64), nextCounter: () => ++counter }; };

describe('Independent activation retirement at real async frontend boundaries (no successful GPU simulation)', () => {
  it('detaches an attach reply arriving after dispose, and frees its canvas listener/renderer exactly once', async () => {
    vi.useFakeTimers();
    const module = await owner<ExecutorModule>('executor.js');
    const attach = pending<object>(); const canvas = document.createElement('canvas');
    const remove = vi.spyOn(canvas, 'removeEventListener');
    const renderer = { capabilities: {}, execute: vi.fn(async () => { throw new Error('No GPU success is simulated'); }), dispose: vi.fn() };
    const invoke = vi.fn<Invoke>(async name => name === 'compute.attach' ? attach.promise : {});
    const executor = module.createExecutor({ operations: { invoke } }, identity(), { makeCanvas: () => canvas, rendererFactory: () => renderer, visibility: Object.assign(new EventTarget(), { visibilityState: 'visible' }) }); retired.push(executor);
    executor.dispose(); executor.dispose();
    attach.resolve({ epoch: 'late-epoch', lease: 'late-lease', server_status: 'ready' });
    await vi.advanceTimersByTimeAsync(0);
    expect(invoke.mock.calls.map(call => call[0])).toEqual(['compute.attach', 'compute.detach']);
    expect(invoke.mock.calls[1][1]).toEqual({ epoch: 'late-epoch', lease: 'late-lease', reason: 'deactivate' });
    expect(renderer.dispose).toHaveBeenCalledTimes(1);
    expect(remove.mock.calls.filter(call => call[0] === 'webglcontextlost')).toHaveLength(1);
    expect(executor.getSnapshot().state).toBe('closed');
  });

  it('drops a late negative computation after dispose without completing or replaying its original request', async () => {
    vi.useFakeTimers();
    const module = await owner<ExecutorModule>('executor.js'); const computed = pending<object>();
    const renderer = { capabilities: {}, execute: vi.fn(() => computed.promise), dispose: vi.fn() };
    let deliveries = 0;
    const invoke = vi.fn<Invoke>(async name => {
      if (name === 'compute.attach') return { epoch: 'epoch', lease: 'lease', server_status: 'ready' };
      if (name === 'compute.next' && deliveries++ === 0) return { status: 'request', request: { remaining_ms: 10000, kind: 'compile', snapshot: {}, request_id: 'original-request' } };
      return { status: 'idle' };
    });
    const executor = module.createExecutor({ operations: { invoke } }, identity(), { makeCanvas: () => document.createElement('canvas'), rendererFactory: () => renderer, visibility: Object.assign(new EventTarget(), { visibilityState: 'visible' }) }); retired.push(executor);
    await vi.advanceTimersByTimeAsync(0);
    expect(renderer.execute).toHaveBeenCalledTimes(1);
    executor.dispose();
    computed.resolve({ compiled: false, rendered: false, diagnostics: [{ code: 'INDEPENDENT_NEGATIVE_FIXTURE' }] });
    await vi.advanceTimersByTimeAsync(15000);
    expect(invoke.mock.calls.some(call => call[0] === 'compute.complete')).toBe(false);
    expect(invoke.mock.calls.filter(call => call[0] === 'compute.attach')).toHaveLength(1);
    expect(renderer.dispose).toHaveBeenCalledTimes(1);
    expect(executor.getSnapshot().state).toBe('closed');
  });

  it('uses a fresh registration on visibility resume and removes all activation listeners when disabled', async () => {
    vi.useFakeTimers();
    const module = await owner<ExecutorModule>('executor.js');
    const visibility = Object.assign(new EventTarget(), { visibilityState: 'visible' });
    const remove = vi.spyOn(visibility, 'removeEventListener');
    const renderers: Renderer[] = [];
    const invoke = vi.fn<Invoke>(async name => name === 'compute.attach' ? { epoch: 'epoch', lease: 'lease', server_status: 'ready' } : { status: 'idle' });
    const executor = module.createExecutor({ operations: { invoke } }, identity(), { makeCanvas: () => document.createElement('canvas'), visibility, rendererFactory: () => {
      const renderer = { capabilities: {}, execute: vi.fn(async () => { throw new Error('No computation requested'); }), dispose: vi.fn() }; renderers.push(renderer); return renderer;
    } }); retired.push(executor);
    await vi.advanceTimersByTimeAsync(0);
    visibility.visibilityState = 'hidden'; visibility.dispatchEvent(new Event('visibilitychange'));
    await vi.advanceTimersByTimeAsync(1000);
    expect(executor.getSnapshot().state).toBe('unavailable');
    visibility.visibilityState = 'visible'; visibility.dispatchEvent(new Event('visibilitychange'));
    await vi.advanceTimersByTimeAsync(0);
    expect(invoke.mock.calls.filter(call => call[0] === 'compute.attach').map(call => call[1].registration_counter)).toEqual([1, 2]);
    executor.dispose(); visibility.dispatchEvent(new Event('visibilitychange')); executor.reconnect();
    await vi.advanceTimersByTimeAsync(1000);
    expect(renderers).toHaveLength(2);
    renderers.forEach(renderer => expect(renderer.dispose).toHaveBeenCalledTimes(1));
    expect(remove.mock.calls.filter(call => call[0] === 'visibilitychange')).toHaveLength(1);
  });
});
