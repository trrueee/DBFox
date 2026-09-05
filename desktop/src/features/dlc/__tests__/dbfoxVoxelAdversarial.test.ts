import { readFile } from "node:fs/promises";
import { createHash, webcrypto } from "node:crypto";
import { resolve } from "node:path";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

type Chunk = { layer_id: string; coord: number[]; hash: string; values: number[] | null };
interface World {
  world_id: string; project_id: string; version: number; content_hash: string; chunk_count: number; nonzero_count: number;
  document: { schema_version: number; size: number[]; layers: { id: string }[]; palette: { index: number }[] };
}
interface Snapshot { world: World; chunks: Map<string, { values: Uint8Array }> }
interface Module {
  loadWorld(invoke: (name: string, input: Record<string, unknown>) => Promise<unknown>, worldId: string, options?: { previous?: Snapshot; signal?: AbortSignal }): Promise<Snapshot>;
  loadSnapshot(access: { read: (...args: unknown[]) => Promise<unknown> }, id: string, payload: World, signal?: AbortSignal): Promise<Snapshot>;
}
let data: Module;
let exported: { manifest: World; chunks: Chunk[]; artifact_id: string };
beforeEach(() => vi.stubGlobal("crypto", webcrypto));
afterEach(() => vi.unstubAllGlobals());
beforeAll(async () => {
  const source = await readFile(resolve(process.cwd(), "../dlcs/dbfox.voxel/frontend/world-data.js"), "utf8");
  data = await import(/* @vite-ignore */ `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`) as Module;
  // Reuse actual publicly downloaded bytes from independent Electron verification.
  exported = JSON.parse(await readFile(resolve(process.cwd(), "../verification/bench/capabilities/dbfox_voxel/evidence/world_c653aa199f7841aaa72bf1dcddc14629-v8.voxel.json"), "utf8"));
});
const page = (world: World, chunks: Chunk[], since: unknown = null, after: string | null = null) => ({
  world_id: world.world_id, version: world.version, since_version: since, chunks, next_after: after, metadata_changed: false,
});
const canonical = (value: unknown): string => Array.isArray(value) ? `[${value.map(canonical).join(",")}]`
  : value !== null && typeof value === "object" ? `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical((value as Record<string, unknown>)[key])}`).join(",")}}`
  : JSON.stringify(value);
const fingerprint = (world: World, chunks: Chunk[]) => {
  const hash = createHash("sha256").update(canonical(world.document));
  [...chunks].sort((a, b) => a.layer_id < b.layer_id ? -1 : a.layer_id > b.layer_id ? 1 : a.coord[0] - b.coord[0] || a.coord[1] - b.coord[1] || a.coord[2] - b.coord[2])
    .forEach(chunk => hash.update("\n" + canonical([chunk.layer_id, ...chunk.coord, chunk.hash])));
  return "sha256:" + hash.digest("hex");
};
const rehash = (chunk: Chunk) => { chunk.hash = "sha256:" + createHash("sha256").update(Uint8Array.from(chunk.values!)).digest("hex"); };

describe("Independent Voxel hostile page substitution", () => {
  it("accepts all original native-download bytes before introducing faults", async () => {
    const { manifest, chunks } = structuredClone(exported);
    const snapshot = await data.loadWorld(async name => name === "worlds.get" ? manifest : page(manifest, chunks), manifest.world_id);
    expect(snapshot.chunks.size).toBe(4);
    expect([...snapshot.chunks.values()].reduce((sum, chunk) => sum + [...chunk.values].filter(Boolean).length, 0)).toBe(1135);
  });
  it("rejects a prematurely terminated full page instead of publishing missing geometry", async () => {
    const { manifest, chunks } = structuredClone(exported);
    await expect(data.loadWorld(async name => name === "worlds.get" ? manifest : page(manifest, chunks.slice(0, 3)), manifest.world_id).then(() => "published")).rejects.toThrow();
  });
  it("rejects a missing delta tombstone instead of retaining geometry under a newer empty summary", async () => {
    const { manifest, chunks } = structuredClone(exported);
    const previous = await data.loadWorld(async name => name === "worlds.get" ? manifest : page(manifest, chunks), manifest.world_id);
    const newer = { ...manifest, version: manifest.version + 1, content_hash: fingerprint(manifest, []), chunk_count: 0, nonzero_count: 0 };
    await expect(data.loadWorld(async name => name === "worlds.get" ? newer : page(newer, [], manifest.version), manifest.world_id, { previous }).then(() => "published")).rejects.toThrow();
    expect(previous.chunks.size).toBe(4);
    expect(previous.world.version).toBe(8);
  });
  it("rejects same-version content substituted behind an unchanged chunk hash", async () => {
    const { manifest, chunks } = structuredClone(exported);
    const values = chunks[0].values!;
    const index = values.findIndex(value => value !== 0);
    values[index] = values[index] === 2 ? 3 : 2;
    const read = async (_id: unknown, _type: unknown, request: unknown) => {
      const operation = (request as { operation: string }).operation;
      return { representation_type: "dbfox.voxel.world.v1", representation_version: 1, operation, consistency: "durable_snapshot",
        source_version: String(manifest.version), source_fingerprint: manifest.content_hash, payload: operation === "manifest" ? manifest : page(manifest, chunks) };
    };
    await expect(data.loadSnapshot({ read }, exported.artifact_id, manifest).then(() => "published")).rejects.toThrow();
  });
  it("rejects duplicate coordinates across pages even when a later page replaces earlier bytes", async () => {
    const { manifest, chunks } = structuredClone(exported);
    let calls = 0;
    await expect(data.loadWorld(async name => {
      if (name === "worlds.get") return manifest;
      calls++;
      return calls === 1 ? page(manifest, chunks, null, "second-page") : page(manifest, [chunks[0]]);
    }, manifest.world_id).then(() => "published")).rejects.toThrow();
  });
  it("rejects cursor cycles and retains the caller's previous immutable map", async () => {
    const { manifest, chunks } = structuredClone(exported);
    const previous = await data.loadWorld(async name => name === "worlds.get" ? manifest : page(manifest, chunks), manifest.world_id);
    const newer = { ...manifest, version: manifest.version + 1 };
    await expect(data.loadWorld(async name => name === "worlds.get" ? newer : page(newer, [], manifest.version, "loop"), manifest.world_id, { previous })).rejects.toThrow();
    expect(previous.chunks.size).toBe(4);
  });
  it("rejects a valid per-chunk hash substituted under an old source fingerprint with unchanged counts", async () => {
    const { manifest, chunks } = structuredClone(exported);
    const offset = chunks[0].values!.findIndex(Boolean);
    chunks[0].values![offset] = chunks[0].values![offset] === 2 ? 3 : 2;
    rehash(chunks[0]);
    expect(fingerprint(manifest, chunks)).not.toBe(manifest.content_hash);
    await expect(data.loadWorld(async name => name === "worlds.get" ? manifest : page(manifest, chunks), manifest.world_id).then(() => "published")).rejects.toThrow();
  });
  it("rejects relocation with valid bytes and identical counts behind the old fingerprint", async () => {
    const { manifest, chunks } = structuredClone(exported);
    [chunks[0].coord, chunks[1].coord] = [chunks[1].coord, chunks[0].coord];
    expect(fingerprint(manifest, chunks)).not.toBe(manifest.content_hash);
    await expect(data.loadWorld(async name => name === "worlds.get" ? manifest : page(manifest, chunks), manifest.world_id).then(() => "published")).rejects.toThrow();
  });
  it("accepts a coherent changed world and rejects its metadata-only forgery", async () => {
    const { manifest, chunks } = structuredClone(exported);
    const offset = chunks[0].values!.findIndex(Boolean);
    chunks[0].values![offset] = chunks[0].values![offset] === 2 ? 3 : 2;
    rehash(chunks[0]);
    manifest.content_hash = fingerprint(manifest, chunks);
    const accepted = await data.loadWorld(async name => name === "worlds.get" ? manifest : page(manifest, chunks), manifest.world_id);
    expect(accepted.chunks.size).toBe(4);
    Object.assign(manifest.document.layers[0], { name: "forged-layer-label" });
    expect(fingerprint(manifest, chunks)).not.toBe(manifest.content_hash);
    await expect(data.loadWorld(async name => name === "worlds.get" ? manifest : page(manifest, chunks), manifest.world_id).then(() => "published")).rejects.toThrow();
  });
  it("does not publish a valid final page arriving after cancellation", async () => {
    const { manifest, chunks } = structuredClone(exported);
    const controller = new AbortController();
    let release!: (value: unknown) => void;
    let entered!: () => void;
    const enteredPromise = new Promise<void>(resolveEntered => { entered = resolveEntered; });
    const pending = data.loadWorld(async name => {
      if (name === "worlds.get") return manifest;
      entered();
      return new Promise(resolvePage => { release = resolvePage; });
    }, manifest.world_id, { signal: controller.signal });
    await enteredPromise;
    controller.abort();
    release(page(manifest, chunks));
    await expect(pending.then(() => "published")).rejects.toThrow();
  });
});
