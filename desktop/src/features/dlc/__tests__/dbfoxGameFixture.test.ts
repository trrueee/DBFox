import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { describe, expect, it, vi } from 'vitest';

const frontend = resolve(process.cwd(), '../dlcs/dbfox.game/frontend');
const url = (source: string) => `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
async function loadModel() {
  return import(/* @vite-ignore */ url(await readFile(resolve(frontend, 'model.js'), 'utf8')));
}
async function loadArtifact() {
  const source = (await readFile(resolve(frontend, 'artifacts.js'), 'utf8'))
    .replace("'./model.js'", JSON.stringify(url(await readFile(resolve(frontend, 'model.js'), 'utf8'))))
    .replace("'./viewport.js'", JSON.stringify(url('export const createViewport = () => () => null;')));
  return import(/* @vite-ignore */ url(source));
}
async function loadExecutor() {
  // This fixture controls only the device runner; actual Phaser has a separate
  // real-browser/Electron suite. It never claims successful engine execution.
  const source = (await readFile(resolve(frontend, 'executor.js'), 'utf8')).replace("'./runtime.js'", JSON.stringify(url("export const ENGINE='phaser-arcade-4.2.1'; export const runPlaytest=()=>{throw new Error('Device fixture must supply execute')};")));
  return import(/* @vite-ignore */ url(source));
}

describe('Game public snapshots and executor boundaries', () => {
  it('accepts the nullable report_id emitted by the real Artifact contract', async () => {
    const { parseLocator } = await loadArtifact();
    const value = { project_id: 'project', game_id: 'game', title: 'Fox', version: 2, content_hash: 'a'.repeat(64), report_id: null };
    expect(parseLocator(value)).toEqual(value);
    expect(() => parseLocator({ ...value, report_id: 4 })).toThrow();
    expect(() => parseLocator({ ...value, version: 0 })).toThrow();
  });

  it('rejects mixed revisions while fetching bounded pages', async () => {
    const { collectPages } = await loadModel();
    const game = { id: 'game', version: 2, content_hash: 'a'.repeat(64) };
    const read = vi.fn().mockResolvedValueOnce({ game, total: 2, offset: 0, next_offset: 1, has_more: true, items: ['a'] })
      .mockResolvedValueOnce({ game: { ...game, version: 3 }, total: 2, offset: 1, next_offset: 2, has_more: false, items: ['b'] });
    await expect(collectPages(read, {})).rejects.toThrow('固定版本');
    expect(read).toHaveBeenCalledTimes(2);
  });

  it('rejects a nonadvancing page and incomplete terminal page', async () => {
    const { collectPages } = await loadModel();
    await expect(collectPages(async () => ({ total: 2, offset: 0, next_offset: 0, has_more: true, items: [] }), {})).rejects.toThrow('分页');
    await expect(collectPages(async () => ({ total: 2, offset: 0, next_offset: 1, has_more: false, items: ['one'] }), {})).rejects.toThrow('不完整');
  });

  it('does not publish a page that arrived after cancellation', async () => {
    const { collectPages } = await loadModel();
    const controller = new AbortController();
    await expect(collectPages(async () => { controller.abort(); return { total: 0, offset: 0, next_offset: 0, has_more: false, items: [] }; }, {}, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('preserves collision subjects while converting canonical ID selectors', async () => {
    const { inputSpec } = await loadModel();
    expect(inputSpec({ entity_id: 'fox', actions: [{ kind: 'damage', target: 'left' }, { kind: 'despawn', target: 'slime' }] })).toEqual({ entity_id: { id: 'fox' }, actions: [{ kind: 'damage', target: 'left' }, { kind: 'despawn', target: { id: 'slime' } }] });
  });

  it('accepts only installed content-addressed package identities', async () => {
    const { packageDigestFromUrl } = await loadExecutor();
    expect(packageDigestFromUrl(`dlc-asset://localhost/${'a'.repeat(64)}/frontend/index.js`)).toBe('a'.repeat(64));
    for (const value of ['http://localhost/frontend/index.js', `dlc-asset://localhost/${'a'.repeat(64)}/frontend/index.js?override=1`, `dlc-asset://elsewhere/${'a'.repeat(64)}/frontend/index.js`]) expect(() => packageDigestFromUrl(value)).toThrow();
  });

  it('classifies a real runner TimeoutError without retrying the claimed job', async () => {
    const { createExecutor } = await loadExecutor();
    const visibility = Object.assign(new EventTarget(), { visibilityState: 'visible' });
    let claimed = false;
    const invoke = vi.fn(async (name: string) => {
      if (name === 'playtest.attach') return { epoch: 'e', lease: 'l', available: true };
      if (name === 'playtest.next') {
        if (claimed) return { status: 'idle' };
        claimed = true;
        return { status: 'request', request: { remaining_ms: 10000, game_id: 'g', version: 2, source_hash: 'hash', snapshot: { document: { id: 'g' }, revision: { version: 2, content_hash: 'hash' }, rgba_assets: {} }, input: { ticks: 60, seed: 1, inputs: [] }, request_id: 'r', invocation_id: 'i', input_hash: 'input', claim_id: 'claim' } };
      }
      return { accepted: true };
    });
    const execute = vi.fn(async () => { throw new DOMException('Expired', 'TimeoutError'); });
    const executor = createExecutor({ operations: { invoke } }, { clientId: 'c', nextCounter: () => 1, packageDigest: 'a'.repeat(64) }, { execute, visibility });
    try {
      await vi.waitFor(() => expect(invoke).toHaveBeenCalledWith('playtest.complete', expect.objectContaining({ error: 'DEADLINE_EXCEEDED', claim_id: 'claim' }), expect.anything()));
      expect(execute).toHaveBeenCalledTimes(1);
      visibility.visibilityState = 'hidden'; visibility.dispatchEvent(new Event('visibilitychange'));
      expect(executor.getSnapshot().state).toBe('unavailable');
    } finally { executor.dispose(); }
  });
});
