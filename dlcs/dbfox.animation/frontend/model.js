export const KIND = "dbfox.animation.document", LIBRARY = "dbfox.animation.library", ARTIFACT = "dbfox.animation.revision", REPRESENTATION = "dbfox.animation.document.v1";
export const sections = ["targets", "tracks", "keyframes", "curves", "clips", "markers"];
export const identity = (prefix) => `${prefix}.${crypto.randomUUID()}`;
export async function readDocument(invoke, animationId, signal) {
  const first = await invoke("animations.get", { animation_id: animationId, section: "tracks", offset: 0, limit: 100 }, signal);
  const result = { animation: first.animation, title: first.animation.title, schema_version: 1, timing: first.timing };
  for (const section of sections) {
    result[section] = [];
    let offset = 0;
    for (;;) {
      const page = section === "tracks" && offset === 0 ? first : await invoke("animations.get", { animation_id: animationId, version: first.animation.version, section, offset, limit: 100 }, signal);
      if (page.animation.version !== first.animation.version || page.animation.content_hash !== first.animation.content_hash) throw new Error("读取期间版本改变，请刷新。");
      result[section].push(...page.items);
      if (!page.has_more) break;
      if (page.next_offset <= offset || page.next_offset > 20000) throw new Error("分页合同无效。");
      offset = page.next_offset;
    }
  }
  return result;
}
export function reference(document, key, track) {
  const summary = document.animation;
  return { label: `${summary.title}${key ? ` / ${key.id}` : track ? ` / ${track.name}` : ""}`,
    object: { kind: key ? "dbfox.animation.keyframe" : track ? "dbfox.animation.track" : KIND,
      id: key?.id || track?.id || summary.id, version: summary.version },
    authority: { kind: KIND, id: summary.id },
    locator: key ? `/keyframes/${encodeURIComponent(key.id)}` : track ? `/tracks/${encodeURIComponent(track.id)}` : "/" };
}
export function visibleKeys(keys, trackIds, start, end) {
  const ids = new Set(trackIds);
  return keys.filter((key) => ids.has(key.track_id) && key.tick >= start && key.tick <= end);
}
