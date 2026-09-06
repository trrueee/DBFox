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
    if (!page.document || ['id', 'version', 'content_hash', 'title', 'deleted'].some((key) => page.document[key] !== summary[key])) throw new Error('Document pages do not belong to the same immutable revision.');
    return page;
  };
  // Verify the owner's original bytes before parsing; JavaScript must not try
  // to reproduce Python's floating-point JSON spelling or rebuild another model.
  let canonical;
  let documentOffset = 0;
  do {
    const page = await get({ section: 'document_bytes', offset: documentOffset, limit: 16384 });
    if (page.section !== 'document_bytes' || page.offset !== documentOffset
      || !Number.isSafeInteger(page.total) || page.total < 1 || page.total > 1048608
      || typeof page.document_bytes !== 'string') throw new Error('Invalid canonical document byte page.');
    if (canonical === undefined) canonical = new Uint8Array(page.total);
    if (page.total !== canonical.length) throw new Error('Canonical document byte length changed.');
    const bytes = decodeBytes(page.document_bytes);
    if (!bytes.length || bytes.length > 16384 || encodeBytes(bytes) !== page.document_bytes
      || documentOffset + bytes.length > canonical.length || page.next_offset !== documentOffset + bytes.length
      || page.has_more !== (page.next_offset < canonical.length)) throw new Error('Invalid canonical document byte cursor.');
    canonical.set(bytes, documentOffset);
    documentOffset = page.next_offset;
  } while (documentOffset < canonical.length);
  if (await sha256(canonical) !== summary.content_hash) throw new Error('Canonical document hash does not match this revision.');
  signal.throwIfAborted();
  const envelope = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(canonical));
  const document = envelope.document;
  const metadata = first.metadata;
  if (!document || envelope.deleted !== summary.deleted || typeof envelope.deleted !== 'boolean'
    || document.id !== summary.id || document.title !== summary.title
    || document.schema_version !== 1 || document.language !== 'glsl-es-300'
    || metadata?.schema_version !== document.schema_version || metadata.language !== document.language
    || !metadata.preview || !document.preview
    || ['pass_id', 'width', 'height', 'time_seconds'].some((key) => metadata.preview[key] !== document.preview[key])) throw new Error('Document summary does not match its canonical bytes.');
  for (const [section, count, maximum] of [['stages', 'stage_count', 64], ['passes', 'pass_count', 32], ['uniforms', 'uniform_count', 128], ['textures', 'texture_count', 16]]) {
    if (!Array.isArray(document[section]) || document[section].length > maximum || metadata[count] !== document[section].length) throw new Error('Document object count does not match its canonical bytes.');
  }
  if (metadata.source_bytes !== document.stages.reduce((sum, stage) => sum + new TextEncoder().encode(stage.source).length, 0)) throw new Error('Document source count does not match its canonical bytes.');
  const textures = document.textures;
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
    snapshot: { document, textures: blobs },
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
