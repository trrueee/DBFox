// Read-only projections of the backend contract. Durable edits stay in SceneStore.
export const SCENE_KIND = "dbfox.scene.document";
export const LIBRARY_KIND = "dbfox.scene.library";
export const ARTIFACT_TYPE = "dbfox.scene.revision";
export const REPRESENTATION_TYPE = "dbfox.scene.document.v1";

export function requestId() {
  return crypto.randomUUID();
}

export async function listScenes(invoke, signal) {
  const scenes = [];
  let offset = 0;
  for (;;) {
    signal?.throwIfAborted();
    const page = await invoke("scenes.list", { offset, limit: 100 }, signal);
    scenes.push(...page.scenes);
    offset += page.scenes.length;
    if (offset >= page.total) return scenes;
    if (!page.scenes.length) throw new Error("场景列表分页未完成，请刷新。");
  }
}

export async function readScene(invoke, sceneId, signal, firstPage) {
  const first = firstPage || await invoke("scenes.get", {
    scene_id: sceneId, section: "objects", offset: 0, limit: 100,
  }, signal);
  const version = first.scene.version;
  if (first.scene.id !== sceneId) throw new Error("场景读取目标不一致。");
  const result = { scene: first.scene, settings: first.settings, objects: [], materials: [], geometries: [] };
  for (const section of ["objects", "materials", "geometries"]) {
    let offset = 0;
    for (;;) {
      signal?.throwIfAborted();
      const page = section === "objects" && offset === 0 ? first : await invoke("scenes.get", {
        scene_id: sceneId, version, section, offset, limit: 100,
      }, signal);
      if (page.scene.id !== sceneId || page.scene.version !== version || page.offset !== offset) {
        throw new Error("场景分页版本不一致，请刷新。");
      }
      const items = page[section];
      result[section].push(...items);
      offset += items.length;
      if (offset >= page.total) break;
      if (!items.length) throw new Error("场景分页未完成，请刷新。");
    }
  }
  return result;
}

// The public Representation boundary pins every page to an exported revision.
// Reuse the editor's paging without consulting its mutable management head.
export async function readSceneArtifact(access, artifactId, payload, signal) {
  const operations = { objects: "objects_page", materials: "materials_page", geometries: "geometry_catalog" };
  return readScene(async (_name, input, pageSignal) => {
    const result = await access.read(artifactId, REPRESENTATION_TYPE, {
      operation: operations[input.section], parameters: { offset: input.offset, limit: input.limit },
    }, pageSignal);
    pageSignal?.throwIfAborted();
    const scene = result?.payload?.scene;
    if (result?.consistency !== "durable_snapshot" || result.source_version !== String(payload.version) ||
        result.source_fingerprint !== payload.content_hash || scene?.id !== payload.scene_id ||
        scene.project_id !== payload.project_id || scene.version !== payload.version || scene.content_hash !== payload.content_hash) {
      throw new Error("场景预览版本不一致，请重新读取此工件。");
    }
    return result.payload;
  }, payload.scene_id, signal);
}

export function hierarchy(snapshot) {
  const root = { id: "scene-root", name: snapshot.scene.title, kind: "scene", children: [] };
  const items = new Map(snapshot.objects.map((object) => [object.id, { ...object, children: [] }]));
  for (const object of snapshot.objects) {
    (object.parent_id ? items.get(object.parent_id) : root).children.push(items.get(object.id));
  }
  return root;
}

export function parentCandidates(objects, id) {
  const excluded = new Set([id]);
  // Valid canonical hierarchies have at most 64 levels.
  for (let depth = 0; depth < 64; depth += 1) {
    let added = false;
    for (const node of objects) {
      if (excluded.has(node.parent_id) && !excluded.has(node.id)) {
        excluded.add(node.id);
        added = true;
      }
    }
    if (!added) break;
  }
  return objects.filter((object) => !excluded.has(object.id));
}

export function referenceFor(snapshot, object) {
  return {
    label: object ? `${snapshot.scene.title} / ${object.name}` : snapshot.scene.title,
    authority: { kind: SCENE_KIND, id: snapshot.scene.id },
    object: { kind: object ? "dbfox.scene.object" : SCENE_KIND, id: object?.id || snapshot.scene.id, version: snapshot.scene.version },
    locator: object ? `/objects/${encodeURIComponent(object.id)}` : "/",
  };
}
