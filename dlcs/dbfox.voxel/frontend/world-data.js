/** Read-only projections of the versioned backend chunk contract. */
export const WORLD_KIND = "dbfox.voxel.world";
export const REPRESENTATION = "dbfox.voxel.world.v1";
export const CHUNK_SIZE = 16;
export const MAX_INSTANCES = 60000;
const MAX_CHUNKS = 8192;

export const chunkKey = (layerId, coord) => `${layerId}:${coord.join(",")}`;
export const chunkOffset = (x, y, z) => x + 16 * z + 256 * y;
export const volumeOffset = (x, y, z, size) => x + size[0] * z + size[0] * size[2] * y;
export const axisIndex = (axis) => ({ x: 0, y: 1, z: 2 })[axis];
export const planeAxes = (axis) => ({ x: [2, 1], y: [0, 2], z: [0, 1] })[axis];

function checkAbort(signal) {
  if (signal?.aborted) throw new DOMException("Read cancelled", "AbortError");
}

function validWorld(world, worldId) {
  const doc = world?.document;
  if (world?.world_id !== worldId || !Number.isInteger(world.version) || world.version < 1
    || doc?.schema_version !== 1 || !Array.isArray(doc.size) || doc.size.length !== 3
    || doc.size.some((n) => !Number.isInteger(n) || n < 1 || n > 256)
    || !Array.isArray(doc.layers) || !doc.layers.length || doc.layers.length > 16
    || !Array.isArray(doc.palette) || doc.palette.length > 256) {
    throw new Error("世界数据不符合版本合同，请刷新后重试。");
  }
  return world;
}

/** Publish a complete revision only after all of its fixed-version pages arrive. */
export async function loadWorld(invoke, worldId, { previous = null, signal, onProgress } = {}) {
  checkAbort(signal);
  const world = validWorld(await invoke("worlds.get", { world_id: worldId }, signal), worldId);
  checkAbort(signal);
  if (world.status !== "active") throw new Error("这个世界已删除。可从历史快照查看已保存的内容。");
  return loadChunks(world, (parameters) => invoke("worlds.chunks", { world_id: worldId, version: world.version, ...parameters }, signal),
    { previous, signal, onProgress });
}

async function loadChunks(world, readPage, { previous = null, signal, onProgress } = {}) {
  const worldId = world.world_id;
  if (previous?.world.world_id === worldId && previous.world.version === world.version) {
    if (previous.world.content_hash !== world.content_hash) throw new Error("同一版本的内容标识发生变化。");
    return previous;
  }
  const useDelta = previous?.world.world_id === worldId && previous.world.version < world.version;
  const sinceVersion = useDelta ? previous.world.version : null;
  const chunks = useDelta ? new Map(previous.chunks) : new Map();
  const layers = new Set(world.document.layers.map((layer) => layer.id));
  const palette = new Set(world.document.palette.map((entry) => entry.index));
  const cursors = new Set();
  let after = null;
  let count = 0;
  do {
    checkAbort(signal);
    const page = await readPage({ since_version: sinceVersion, limit: 16, after });
    checkAbort(signal);
    if (page.world_id !== worldId || page.version !== world.version || page.since_version !== sinceVersion
      || !Array.isArray(page.chunks) || page.chunks.length > 16) throw new Error("分块页面的世界版本不一致。");
    for (const chunk of page.chunks) {
      if (!Array.isArray(chunk.coord) || chunk.coord.length !== 3
        || chunk.coord.some((n, i) => !Number.isInteger(n) || n < 0 || n >= Math.ceil(world.document.size[i] / 16))) {
        throw new Error("分块坐标无效。");
      }
      const key = chunkKey(chunk.layer_id, chunk.coord);
      if (chunk.values === null) {
        chunks.delete(key);
      } else {
        if (!layers.has(chunk.layer_id) || !Array.isArray(chunk.values) || chunk.values.length !== 4096
          || chunk.values.some((value) => !Number.isInteger(value) || value < 0 || value > 255 || !palette.has(value))) {
          throw new Error("分块内容损坏或引用了不存在的调色板颜色。");
        }
        chunks.set(key, { layer_id: chunk.layer_id, coord: chunk.coord, hash: chunk.hash, values: Uint8Array.from(chunk.values) });
      }
      count += 1;
    }
    if (chunks.size > MAX_CHUNKS || count > MAX_CHUNKS * 2) throw new Error("世界分块超过工作台加载上限。");
    onProgress?.(count);
    after = page.next_after;
    if (after != null) {
      if (typeof after !== "string" || !after || cursors.has(after)) throw new Error("分块分页游标重复或无效。");
      cursors.add(after);
    }
  } while (after != null);
  // Layer removals are metadata changes; tombstones are still accepted above.
  for (const [key, chunk] of chunks) if (!layers.has(chunk.layer_id)) chunks.delete(key);
  checkAbort(signal);
  return { world, chunks };
}

/** The Artifact access owns authorization; only immutable representation pages enter here. */
export async function loadSnapshot(access, artifactId, payload, signal) {
  const read = async (operation, parameters) => {
    checkAbort(signal);
    const result = await access.read(artifactId, REPRESENTATION, { operation, parameters }, signal);
    checkAbort(signal);
    if (result.representation_type !== REPRESENTATION || result.representation_version !== 1
      || result.operation !== operation || result.consistency !== "durable_snapshot"
      || result.source_version !== String(payload.version) || result.source_fingerprint !== payload.content_hash) {
      throw new Error("快照页面不属于这个固定版本。");
    }
    return result.payload;
  };
  const world = validWorld(await read("manifest", {}), payload.world_id);
  if (world.project_id !== payload.project_id || world.version !== payload.version || world.content_hash !== payload.content_hash) {
    throw new Error("快照清单的身份与版本不一致。");
  }
  const result = await loadChunks(world, (parameters) => read("chunks", parameters), { signal });
  if (result.chunks.size !== world.chunk_count) throw new Error("快照分块不完整。");
  return result;
}

/** Offline JSON file, assembled from the already verified immutable representation. */
export function snapshotFile(snapshot, artifactId) {
  const parts = [JSON.stringify({ schema_version: 1, representation_type: REPRESENTATION, artifact_id: artifactId,
    manifest: snapshot.world }).slice(0, -1), ',"chunks":['];
  let first = true;
  for (const chunk of snapshot.chunks.values()) {
    if (!first) parts.push(",");
    parts.push(JSON.stringify({ ...chunk, values: Array.from(chunk.values) }));
    first = false;
  }
  parts.push("]}");
  return new Blob(parts, { type: "application/json" });
}

export function voxelAt(chunks, layerId, point) {
  const coord = point.map((value) => Math.floor(value / 16));
  return chunks.get(chunkKey(layerId, coord))?.values[chunkOffset(point[0] % 16, point[1] % 16, point[2] % 16)] || 0;
}

export function slicePoint(axis, index, u, v) {
  const point = [0, 0, 0];
  const [a, b] = planeAxes(axis);
  point[axisIndex(axis)] = index;
  point[a] = u;
  point[b] = v;
  return point;
}

export function strokeBounds(axis, index, start, end) {
  const a = slicePoint(axis, index, ...start);
  const b = slicePoint(axis, index, ...end);
  return { min: a.map((value, i) => Math.min(value, b[i])), max: a.map((value, i) => Math.max(value, b[i]) + 1) };
}

export function validateBounds(bounds, size) {
  if (!bounds || !Array.isArray(bounds.min) || !Array.isArray(bounds.max)
    || bounds.min.length !== 3 || bounds.max.length !== 3
    || bounds.min.some((n, i) => !Number.isInteger(n) || !Number.isInteger(bounds.max[i]) || n < 0
      || bounds.max[i] <= n || bounds.max[i] > size[i])) throw new Error("选区必须在世界内，终点不包含在选区中。");
  const volume = bounds.min.reduce((count, n, i) => count * (bounds.max[i] - n), 1);
  if (volume > 2097152) throw new Error("单次操作最多 2,097,152 个方块，请缩小选区。");
  return bounds;
}

/** Layers compose bottom-to-top; no projection is ever sent back as world truth. */
export async function composeVisible(snapshot, hidden, signal) {
  const size = snapshot.world.document.size;
  const result = new Uint8Array(size[0] * size[1] * size[2]);
  const byLayer = new Map();
  for (const chunk of snapshot.chunks.values()) {
    if (!byLayer.has(chunk.layer_id)) byLayer.set(chunk.layer_id, []);
    byLayer.get(chunk.layer_id).push(chunk);
  }
  let processed = 0;
  for (const layer of snapshot.world.document.layers) {
    if (hidden.has(layer.id)) continue;
    for (const chunk of byLayer.get(layer.id) || []) {
      checkAbort(signal);
      const [ox, oy, oz] = chunk.coord.map((n) => n * 16);
      for (let y = 0; y < 16 && oy + y < size[1]; y += 1) {
        for (let z = 0; z < 16 && oz + z < size[2]; z += 1) {
          for (let x = 0; x < 16 && ox + x < size[0]; x += 1) {
            const value = chunk.values[chunkOffset(x, y, z)];
            if (value) result[volumeOffset(ox + x, oy + y, oz + z, size)] = value;
          }
        }
      }
      processed += 1;
      if (processed % 16 === 0) await new Promise((resolve) => setTimeout(resolve, 0));
    }
  }
  checkAbort(signal);
  return { values: result, size };
}

/** Instancing budget is explicit; only exposed cells need a cube instance. */
export async function surfaceInstances(composite, bounds, signal, maximum = MAX_INSTANCES) {
  const { values, size } = composite;
  // Numeric controls can temporarily contain an empty or out-of-range value.
  // Constrain preview work independently of the canonical mutation validator.
  const lo = size.map((n, i) => Math.max(0, Math.min(n, Math.floor(Number(bounds?.min[i]) || 0))));
  const hi = size.map((n, i) => Math.max(lo[i], Math.min(n, Math.ceil(Number(bounds?.max[i]) || (bounds ? 0 : n)))));
  const positions = new Uint16Array(maximum * 3);
  const colors = new Uint8Array(maximum);
  let count = 0;
  for (let y = lo[1]; y < hi[1]; y += 1) {
    checkAbort(signal);
    for (let z = lo[2]; z < hi[2]; z += 1) {
      for (let x = lo[0]; x < hi[0]; x += 1) {
        const index = volumeOffset(x, y, z, size);
        const value = values[index];
        if (!value) continue;
        const exposed = x === lo[0] || x === hi[0] - 1 || y === lo[1] || y === hi[1] - 1 || z === lo[2] || z === hi[2] - 1
          || !values[index - 1] || !values[index + 1] || !values[index - size[0]] || !values[index + size[0]]
          || !values[index - size[0] * size[2]] || !values[index + size[0] * size[2]];
        if (!exposed) continue;
        if (count === maximum) return { positions, colors, count, truncated: true };
        positions.set([x, y, z], count * 3);
        colors[count] = value;
        count += 1;
      }
    }
    if ((y - lo[1]) % 8 === 7) await new Promise((resolve) => setTimeout(resolve, 0));
  }
  return { positions, colors, count, truncated: false };
}
