import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

import { unzipSync } from "fflate";
import { afterEach, describe, expect, it } from "vitest";

import { CrashRecoveryMarker } from "../crashRecovery";
import { exportDiagnosticBundle, redactText, sanitizeSnapshot } from "../diagnosticBundle";
import { isPublicIp, matchesImageSignature, validateExternalImageUrl } from "../externalImage";

const roots: string[] = [];
afterEach(async () => {
  for (const root of roots.splice(0)) await rm(root, { recursive: true, force: true });
});

describe("Electron native security contracts", () => {
  it("rejects private image destinations and mismatched signatures", () => {
    expect(validateExternalImageUrl("https://example.com/image.png").hostname).toBe("example.com");
    for (const url of ["http://example.com/a.png", "https://user:secret@example.com/a.png", "https://localhost/a.png", " https://example.com/a.png"]) {
      expect(() => validateExternalImageUrl(url)).toThrow();
    }
    for (const ip of ["127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.1.1", "203.0.113.1", "::1", "fd00::1", "2001:db8::1"]) {
      expect(isPublicIp(ip)).toBe(false);
    }
    expect(isPublicIp("1.1.1.1")).toBe(true);
    expect(matchesImageSignature(Buffer.from("<html>"), "png")).toBe(false);
    expect(matchesImageSignature(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), "png")).toBe(true);
  });

  it("redacts bounded diagnostic snapshots and ZIP contents", async () => {
    expect(redactText("authorization: Bearer secret")).not.toContain("secret");
    expect(JSON.stringify(sanitizeSnapshot({ token: "secret", nested: { ok: true } }))).not.toContain("secret");
    const root = resolve(`.diagnostics-${Date.now()}-${Math.random()}`);
    roots.push(root);
    await mkdir(root);
    await writeFile(join(root, "dbfox-host.log"), "password=host-secret\nhealthy\n");
    const result = await exportDiagnosticBundle(
      root,
      { engineSnapshot: { password: "engine-secret" }, webviewSnapshot: { content: "api_key=web-secret" } },
      "test",
      { state: "ready", error: null, stage: null, generation: 2, restartCount: 0 },
    );
    const archive = unzipSync(await readFile(result.path));
    const all = Object.values(archive).map((bytes) => new TextDecoder().decode(bytes)).join("\n");
    expect(all).toContain("[REDACTED]");
    for (const secret of ["engine-secret", "web-secret", "host-secret"]) expect(all).not.toContain(secret);
  });

  it("retains a marker only across an unclean session", async () => {
    const root = resolve(`.crash-marker-${Date.now()}-${Math.random()}`);
    roots.push(root);
    const path = join(root, "session-active-v1");
    const first = await CrashRecoveryMarker.initialize(path);
    expect(first.status().previousUncleanExit).toBe(false);
    const second = await CrashRecoveryMarker.initialize(path);
    expect(second.status().previousUncleanExit).toBe(true);
    await second.clear();
    const third = await CrashRecoveryMarker.initialize(path);
    expect(third.status().previousUncleanExit).toBe(false);
    await third.clear();
  });
});
