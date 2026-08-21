import { mkdir, rm, symlink, truncate, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  DlcAssetAuthority,
  handleDlcAssetRequest,
  parseDlcAssetUrl,
} from "../dlcAssetProtocol";

const roots: string[] = [];
const digest = "0123456789abcdef".repeat(4);

afterEach(async () => {
  for (const root of roots.splice(0)) await rm(root, { recursive: true, force: true });
});

describe("Electron DLC asset protocol", () => {
  it("parses only a local digest-bound contained URL", () => {
    expect(parseDlcAssetUrl(`dlc-asset://localhost/${digest}/frontend/index.js`)).toEqual({
      packageDigest: digest,
      subpath: "index.js",
    });
    for (const url of [
      `https://localhost/${digest}/index.js`,
      `dlc-asset://example.com/${digest}/index.js`,
      "dlc-asset://localhost/short/index.js",
      `dlc-asset://localhost/${digest}/%2e%2e/secret.txt`,
      `dlc-asset://localhost/${digest}/assets%2fsecret.txt`,
      `dlc-asset://localhost/${digest}/assets%5csecret.txt`,
    ]) expect(() => parseDlcAssetUrl(url)).toThrow();
  });

  it("serves only active frontend digests with bounded immutable responses", async () => {
    const root = resolve(`.dlc-assets-${Date.now()}-${Math.random()}`);
    roots.push(root);
    const frontend = join(root, `sha256-${digest}`, "frontend");
    await mkdir(frontend, { recursive: true });
    await writeFile(join(frontend, "index.js"), "export default 1;");
    const authority = new DlcAssetAuthority();
    const url = `dlc-asset://localhost/${digest}/index.js`;

    expect((await handleDlcAssetRequest(authority, new Request(url), root)).status).toBe(403);
    authority.updateProjection({
      snapshot_id: "snapshot",
      active_dlcs: [{
        dlc_id: "acme.echo", package_version: "1.0.0", package_digest: `sha256:${digest}`,
        frontend_entrypoint: "frontend/index.js",
      }],
    });
    const response = await handleDlcAssetRequest(authority, new Request(url), root);
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("export default 1;");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    expect(response.headers.get("cache-control")).toContain("immutable");
    expect(() => authority.updateProjection({
      snapshot_id: "invalid",
      active_dlcs: [{
        dlc_id: "acme.invalid", package_version: "1.0.0", package_digest: "short",
        frontend_entrypoint: "frontend/index.js",
      }],
    })).toThrow("Invalid active DLC item");
    expect(authority.isActive(digest)).toBe(false);
  });

  it("rejects symlink escapes and oversized assets", async () => {
    const root = resolve(`.dlc-assets-${Date.now()}-${Math.random()}`);
    const outside = resolve(`.dlc-outside-${Date.now()}-${Math.random()}`);
    roots.push(root, outside);
    const frontend = join(root, `sha256-${digest}`, "frontend");
    await mkdir(frontend, { recursive: true });
    await mkdir(outside, { recursive: true });
    await writeFile(join(outside, "secret.js"), "secret");
    await symlink(outside, join(frontend, "escape"), process.platform === "win32" ? "junction" : "dir");
    await writeFile(join(frontend, "huge.js"), "x");
    await truncate(join(frontend, "huge.js"), 20 * 1024 * 1024 + 1);
    const authority = activeAuthority();

    expect((await handleDlcAssetRequest(authority, new Request(`dlc-asset://localhost/${digest}/escape/secret.js`), root)).status).toBe(403);
    expect((await handleDlcAssetRequest(authority, new Request(`dlc-asset://localhost/${digest}/huge.js`), root)).status).toBe(413);
  });
});

function activeAuthority(): DlcAssetAuthority {
  const authority = new DlcAssetAuthority();
  authority.updateProjection({
    snapshot_id: "snapshot",
    active_dlcs: [{
      dlc_id: "acme.echo", package_version: "1.0.0", package_digest: digest,
      frontend_entrypoint: "frontend/index.js",
    }],
  });
  return authority;
}
