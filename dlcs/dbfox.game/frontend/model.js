export const GAME_KIND = 'dbfox.game.project';
export const LIBRARY_KIND = 'dbfox.game.library';
export const DOCUMENT = 'dbfox.game.document.v1';
export const REPORT = 'dbfox.game.playtest.v1';
export const requestId = () => crypto.randomUUID();
export const byId = (id) => ({ id });
export const errorText = (error) => String(error?.message || 'Game 操作失败。').slice(0, 360);
export const part = (entity, kind) => entity?.components.find((item) => item.spec.kind === kind);

function checkSignal(signal) {
  if (signal?.aborted) throw new DOMException('Read cancelled', 'AbortError');
}

export async function collectPages(read, input, signal, expected) {
  const items = [];
  let offset = 0;
  let initial;
  do {
    checkSignal(signal);
    const page = await read({ ...input, offset, limit: 50 }, signal);
    checkSignal(signal);
    initial ??= page;
    const revision = expected ?? initial.game;
    if (revision && (page.game?.id !== revision.id || page.game?.version !== revision.version || page.game?.content_hash !== revision.content_hash)) throw new Error('固定版本读取发生变化，请重新加载。');
    if (page.total !== initial.total || page.total > 8192 || page.offset !== offset || page.next_offset !== offset + page.items.length || (page.has_more && page.next_offset <= offset)) throw new Error('Game 分页边界无效。');
    items.push(...page.items);
    offset = page.next_offset;
    if (!page.has_more) {
      if (offset !== page.total) throw new Error('Game 分页内容不完整。');
      return { ...initial, items };
    }
    if (!revision && input.version === undefined) input = { ...input, version: initial.library_version };
  } while (offset < 8192);
  throw new Error('Game 分页超过上限。');
}

export async function listGames(invoke, signal) {
  return collectPages((input, requestSignal) => invoke('games.list', input, requestSignal), {}, signal);
}

export async function loadDocument(read, summary, signal) {
  const first = await read({ section: 'summary' }, signal);
  const fixed = summary ?? first.game;
  if (!fixed || first.game?.id !== fixed.id || first.game?.version !== fixed.version || first.game?.content_hash !== fixed.content_hash) throw new Error('Game 固定版本摘要无效。');
  const metadata = first.metadata;
  const canonical = { id: fixed.id, title: fixed.title, schema_version: metadata.schema_version, engine: metadata.engine, tick_hz: metadata.tick_hz, initial_scene_id: metadata.initial_scene_id };
  for (const section of ['scenes', 'entities', 'behaviors', 'rules', 'variables', 'assets']) {
    const page = await collectPages(read, { section }, signal, fixed);
    if (page.items.length !== metadata.counts[section]) throw new Error('Game 对象数量与固定版本不一致。');
    canonical[section] = page.items;
  }
  const rgbaAssets = {};
  let totalBytes = 0;
  for (const asset of canonical.assets) {
    if (rgbaAssets[asset.content_hash]) continue;
    const bytes = new Uint8Array(asset.width * asset.height * 4);
    totalBytes += bytes.length;
    if (bytes.length > 1048576 || totalBytes > 4194304) throw new Error('Game 图片超过读取预算。');
    let offset = 0;
    do {
      checkSignal(signal);
      const page = await read({ section: 'asset_bytes', asset_id: asset.id, offset, limit: 16384 }, signal);
      if (page.game?.version !== fixed.version || page.game?.content_hash !== fixed.content_hash || page.game?.id !== fixed.id || page.metadata.asset.content_hash !== asset.content_hash || page.total !== bytes.length || page.offset !== offset) throw new Error('Game 图片固定版本无效。');
      const chunk = atob(page.metadata.rgba_base64);
      if (page.next_offset !== offset + chunk.length || page.next_offset > bytes.length || !chunk.length) throw new Error('Game 图片分页无效。');
      for (let index = 0; index < chunk.length; index += 1) bytes[offset + index] = chunk.charCodeAt(index);
      offset = page.next_offset;
      if (page.has_more !== (offset < bytes.length)) throw new Error('Game 图片末页无效。');
    } while (offset < bytes.length);
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map((value) => value.toString(16).padStart(2, '0')).join('');
    if (hash !== asset.content_hash) throw new Error('Game 图片 SHA-256 校验失败。');
    let binary = '';
    for (let index = 0; index < bytes.length; index += 16384) binary += String.fromCharCode(...bytes.subarray(index, index + 16384));
    rgbaAssets[hash] = btoa(binary);
  }
  checkSignal(signal);
  return { revision: fixed, document: canonical, rgba_assets: rgbaAssets, library_version: first.library_version };
}

export async function readGame(invoke, gameId, signal, head) {
  const current = head ?? await invoke('games.head', { game_id: gameId }, signal);
  return loadDocument((input, requestSignal) => invoke('games.get', { ...input, game_id: gameId, version: current.game.version }, requestSignal), current.game, signal);
}

/** Canonical object selectors remain subjects under the one Game resource. */
export function referenceFor(snapshot, object, kind = 'entity') {
  return {
    label: `${snapshot.document.title}${object ? ' / ' + (object.name ?? object.spec?.name ?? kind) : ''}`,
    authority: { kind: GAME_KIND, id: snapshot.document.id },
    object: { kind: object ? `dbfox.game.${kind}` : GAME_KIND, id: object?.id ?? snapshot.document.id, version: snapshot.revision.version },
    ...(object ? { locator: `/${kind === 'entity' ? 'entities' : kind + 's'}/${object.id}` } : {}),
  };
}

/** Input ID selectors are explicit; no canonical DTO is replaced wholesale. */
export function inputSpec(spec) {
  if (Array.isArray(spec)) return spec.map(inputSpec);
  if (!spec || typeof spec !== 'object') return spec;
  return Object.fromEntries(Object.entries(spec).map(([key, value]) => [key,
    (key.endsWith('_id') || key === 'target') && typeof value === 'string' && value !== 'left' && value !== 'right' ? byId(value) : inputSpec(value),
  ]));
}
