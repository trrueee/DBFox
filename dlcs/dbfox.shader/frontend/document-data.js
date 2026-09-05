import { decodeBytes, encodeBytes, sha256 } from './renderer.js';

export async function loadDocument(read, signal, version) {
  const first = await read({ section: 'summary', ...(version === undefined ? {} : { version }) }, signal);
  signal.throwIfAborted();
  const summary = first.document;
  if (!summary || !Number.isSafeInteger(summary.version)) throw new Error('Document revision is missing.');
  if (version !== undefined && summary.version !== version) throw new Error('Document read did not return the requested immutable revision.');
  const fixed = summary.version;
  const get = async (parameters) => {
    signal.throwIfAborted();
    const page = await read({ ...parameters, version: fixed }, signal);
    signal.throwIfAborted();
    if (page.document?.id !== summary.id || page.document.version !== fixed || page.document.content_hash !== summary.content_hash) throw new Error('Document pages do not belong to the same immutable revision.');
    return page;
  };
  const pages = async (section, maximum) => {
    const values = [];
    let offset = 0;
    do {
      const page = await get({ section, offset, limit: 50 });
      if (page.offset !== offset || page.total > maximum || !Array.isArray(page.items) || page.items.length > 50) throw new Error('Invalid bounded document page.');
      values.push(...page.items);
      if (!page.has_more) {
        if (values.length !== page.total) throw new Error('Document object page is incomplete.');
        break;
      }
      if (page.next_offset <= offset || page.next_offset !== values.length) throw new Error('Document page did not advance.');
      offset = page.next_offset;
    } while (values.length <= maximum);
    return values;
  };
  const stageMetadata = await pages('stages', 64);
  const stages = [];
  for (const stage of stageMetadata) {
    let source = '';
    let offset = 0;
    do {
      const page = await get({ section: 'source', stage_id: stage.id, offset, limit: 50 });
      if (page.offset !== offset || page.stage_id !== stage.id || typeof page.source !== 'string' || page.total > 16384) throw new Error('Invalid source page.');
      source += page.source;
      if (source.length > 262144) throw new Error('Stage source exceeds its budget.');
      if (!page.has_more) break;
      if (page.next_offset <= offset) throw new Error('Source page did not advance.');
      offset = page.next_offset;
    } while (offset <= 16384);
    const bytes = new TextEncoder().encode(source);
    if (bytes.length !== stage.source_bytes || await sha256(bytes) !== stage.source_hash) throw new Error('Stage source hash does not match this revision.');
    stages.push({ id: stage.id, kind: stage.kind, title: stage.title, source });
  }
  const passes = await pages('passes', 32);
  const uniforms = await pages('uniforms', 128);
  const textures = await pages('textures', 16);
  const blobs = [];
  let totalTextureBytes = 0;
  for (const texture of textures) {
    if (blobs.some((item) => item.content_hash === texture.content_hash)) continue;
    const size = texture.width * texture.height * 4;
    totalTextureBytes += size;
    if (!Number.isSafeInteger(size) || size < 4 || size > 1048576 || totalTextureBytes > 4194304) throw new Error('Texture layout exceeds its budget.');
    const bytes = new Uint8Array(size);
    let offset = 0;
    do {
      const page = await get({ section: 'texture_bytes', texture_id: texture.id, offset, limit: 16384 });
      const data = page.texture_bytes;
      if (!data || page.offset !== offset || data.texture_id !== texture.id || data.content_hash !== texture.content_hash || data.total_bytes !== size || page.total !== size) throw new Error('Texture byte page does not match this revision.');
      const selected = decodeBytes(data.rgba_base64);
      if (!selected.length || selected.length > 16384 || offset + selected.length > size || page.next_offset !== offset + selected.length || page.has_more !== (page.next_offset < size)) throw new Error('Invalid texture byte page cursor.');
      bytes.set(selected, offset); offset = page.next_offset;
    } while (offset < size);
    if (await sha256(bytes) !== texture.content_hash) throw new Error('Reassembled texture hash does not match.');
    signal.throwIfAborted();
    blobs.push({ content_hash: texture.content_hash, rgba_base64: encodeBytes(bytes) });
  }
  return {
    summary, generation: first.studio_generation,
    snapshot: { document: { id: summary.id, schema_version: first.metadata.schema_version, language: first.metadata.language, title: summary.title, stages, passes, uniforms, textures, preview: first.metadata.preview }, textures: blobs },
  };
}

export function draftOperations(document, drafts) {
  return document.stages.filter((stage) => drafts[stage.id] !== undefined && drafts[stage.id] !== stage.source)
    .map((stage) => ({ kind: 'stage_replace', stage_id: { id: stage.id }, source: drafts[stage.id] }));
}

// Explicit rebase preserves a dirty stage only when its whole original source is unchanged.
// Other document fields may have changed. A changed/deleted target remains a conflict.
export function rebaseDrafts(previous, latest, drafts) {
  const next = {};
  const conflicts = [];
  for (const [id, source] of Object.entries(drafts)) {
    const before = previous.stages.find((stage) => stage.id === id);
    const after = latest.stages.find((stage) => stage.id === id);
    if (!before || source === before.source) continue;
    if (!after || (after.source !== before.source && after.source !== source)) conflicts.push(id);
    else if (source !== after.source) next[id] = source;
  }
  return { drafts: next, conflicts };
}
