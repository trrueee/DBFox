import { createHash } from "node:crypto";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { verifyPackagedSidecar } from "../nodeEngineHost";

const roots: string[] = [];
afterEach(async () => {
  for (const root of roots.splice(0)) await rm(root, { recursive: true, force: true });
});

describe("packaged Electron Sidecar integrity", () => {
  it("accepts only the exact executable bound by the final artifact manifest", async () => {
    const root = resolve(`.packaged-sidecar-${Date.now()}-${Math.random()}`);
    roots.push(root);
    await mkdir(root);
    const executable = join(root, process.platform === "win32" ? "dbfox-engine.exe" : "dbfox-engine");
    const manifest = join(root, "dbfox-engine-runtime-manifest.json");
    const bytes = Buffer.from("frozen-sidecar");
    await writeFile(executable, bytes);
    await writeFile(manifest, JSON.stringify({
      schema_version: 3,
      target_triplet: "test-target",
      sidecar_filename: executable.split(/[\\/]/).pop(),
      sidecar_sha256: createHash("sha256").update(bytes).digest("hex"),
    }));

    await expect(verifyPackagedSidecar(executable, manifest)).resolves.toBeUndefined();
    await writeFile(executable, "tampered");
    await expect(verifyPackagedSidecar(executable, manifest)).rejects.toThrow("integrity verification failed");
  });

  it("rejects a manifest naming a different executable", async () => {
    const root = resolve(`.packaged-sidecar-${Date.now()}-${Math.random()}`);
    roots.push(root);
    await mkdir(root);
    const executable = join(root, process.platform === "win32" ? "dbfox-engine.exe" : "dbfox-engine");
    const manifest = join(root, "dbfox-engine-runtime-manifest.json");
    await writeFile(executable, "sidecar");
    await writeFile(manifest, JSON.stringify({
      schema_version: 3,
      target_triplet: "test-target",
      sidecar_filename: "other-sidecar",
      sidecar_sha256: "a".repeat(64),
    }));
    await expect(verifyPackagedSidecar(executable, manifest)).rejects.toThrow("resource contract");
  });
});
