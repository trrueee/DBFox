export const DOCUMENT = "dbfox.pixel.document";
export const VIEW = "dbfox.pixel.studio";
export const ARTIFACT = "dbfox.pixel.revision";
export const REPRESENTATION = "dbfox.pixel.sprite.v1";
export const requestId = (prefix = "pixel") => `${prefix}_${crypto.randomUUID().replaceAll("-", "")}`;
export const errorText = (error) => (typeof error?.message === "string" ? error.message : "Pixel 操作失败。").slice(0, 360);
export function checkAbort(signal) { if (signal?.aborted) throw new DOMException("已取消", "AbortError"); }

export async function listDocuments(invoke, signal, includeDeleted = false) {
  const documents = [];
  for (let page = 0; page < 128; page++) {
    const result = await invoke("documents.list", { page, page_size: 32, include_deleted: includeDeleted }, signal);
    checkAbort(signal);
    documents.push(...result.documents);
    if (!result.has_more) return documents;
  }
  throw new Error("文档目录超出显示预算，请在项目资源中缩小范围。");
}

export async function readFrame(invoke, snapshot, frameId, signal) {
  const result = await invoke("frames.read", { document_id: snapshot.summary.document_id, revision: snapshot.summary.revision, frame_id: frameId }, signal);
  checkAbort(signal);
  if (result.document_id !== snapshot.summary.document_id || result.revision !== snapshot.summary.revision || result.content_hash !== snapshot.summary.content_hash || result.frame.id !== frameId ||
      result.canvas.width !== snapshot.summary.width || result.canvas.height !== snapshot.summary.height || JSON.stringify(result.palette) !== JSON.stringify(snapshot.document.palette)) {
    throw new Error("帧与文档版本不一致；未显示混合版本。");
  }
  const size = result.canvas.width * result.canvas.height;
  if (result.frame.cels.length !== snapshot.document.layers.length || result.frame.cels.some((cel, index) => cel.layer_id !== snapshot.document.layers[index].id || cel.pixels.length !== size || cel.pixels.some((value) => !Number.isInteger(value) || value < 0 || value >= result.palette.length))) {
    throw new Error("帧像素合同无效；未显示损坏内容。");
  }
  return result.frame;
}

// A read-only composition of a single immutable revision. Never written back.
export function composite(document, frame) {
  const size = document.canvas.width * document.canvas.height;
  const indices = new Uint8Array(size);
  if (!frame) return indices;
  document.layers.forEach((layer, index) => {
    if (!layer.visible) return;
    const cel = frame.cels[index];
    for (let offset = 0; offset < size; offset++) if (cel.pixels[offset]) indices[offset] = cel.pixels[offset];
  });
  return indices;
}

export function drawFrame(canvas, document, frame, zoom = 1) {
  if (!canvas || !document) return;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Canvas 2D 不可用，无法绘制像素。");
  const { width, height } = document.canvas;
  canvas.width = width * zoom;
  canvas.height = height * zoom;
  context.imageSmoothingEnabled = false;
  context.clearRect(0, 0, canvas.width, canvas.height);
  const indices = composite(document, frame);
  for (let offset = 0; offset < indices.length; offset++) {
    const index = indices[offset];
    if (!index) continue;
    context.fillStyle = document.palette[index].color;
    context.fillRect((offset % width) * zoom, Math.floor(offset / width) * zoom, zoom, zoom);
  }
}

export function pointAt(event, canvas, size, clamp = true) {
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  const x = Math.floor((event.clientX - rect.left) * size.width / rect.width);
  const y = Math.floor((event.clientY - rect.top) * size.height / rect.height);
  if (!clamp && (x < 0 || y < 0 || x >= size.width || y >= size.height)) return null;
  return { x: Math.max(0, Math.min(size.width - 1, x)), y: Math.max(0, Math.min(size.height - 1, y)) };
}
export function rectBetween(a, b) { return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), width: Math.abs(a.x - b.x) + 1, height: Math.abs(a.y - b.y) + 1 }; }

export function gestureOperations(gesture) {
  const { tool, points, frameId: frame_id, layerId: layer_id, color: palette_index } = gesture;
  const first = points[0], last = points[points.length - 1];
  const target = { frame_id, layer_id, palette_index: tool === "eraser" ? 0 : palette_index };
  if (tool === "fill") return [{ kind: "fill", ...target, x: first.x, y: first.y }];
  if (tool === "rectangle") return [{ kind: "rect", ...target, rect: rectBetween(first, last), filled: gesture.filled }];
  if (tool === "select") return [];
  const segments = points.length === 1 ? [[first, first]] : points.slice(1).map((point, index) => [points[index], point]);
  if (segments.length > 128) throw new Error("本次笔迹超过 128 段，已全部取消。请分成较短笔迹重新绘制。");
  return segments.map(([a, b]) => ({ kind: "line", ...target, x0: a.x, y0: a.y, x1: b.x, y1: b.y }));
}

export function referenceFor(snapshot, frameId, layerId, rect) {
  const { document_id, revision, title } = snapshot.summary;
  const parts = [`pixel://${document_id}`, `revision=${revision}`, `frame=${encodeURIComponent(frameId)}`, `layer=${encodeURIComponent(layerId)}`];
  if (rect) parts.push(`rect=${rect.x},${rect.y},${rect.width},${rect.height}`);
  return { label: `${title} · ${frameId} / ${layerId}${rect ? ` · ${rect.width}×${rect.height} 选区` : ""} · r${revision}`,
    authority: { kind: DOCUMENT, id: document_id }, object: { kind: "dbfox.pixel.frame", id: frameId, version: String(revision) }, locator: parts.join(";") };
}

export function parseSummary(value) {
  if (!value || typeof value.document_id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(value.document_id) || typeof value.project_id !== "string" || !value.project_id ||
      !Number.isInteger(value.revision) || value.revision < 1 || typeof value.title !== "string" || !/^[a-f0-9]{64}$/.test(value.content_hash) ||
      !Number.isInteger(value.width) || value.width < 1 || value.width > 128 || !Number.isInteger(value.height) || value.height < 1 || value.height > 128) throw new Error("Pixel 修订元数据无效。");
  return value;
}
