import { mkdir, rm, truncate, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { handleAppRequest, hasPackagedRendererOrigin, parseAppUrl } from "../appProtocol";

const roots: string[] = [];
afterEach(async () => {
  for (const root of roots.splice(0)) await rm(root, { recursive: true, force: true });
});

describe("packaged Electron renderer protocol", () => {
  it("recognizes the custom-scheme origin without relying on URL.origin", () => {
    expect(new URL("dbfox-app://localhost/index.html").origin).toBe("null");
    expect(hasPackagedRendererOrigin("dbfox-app://localhost/index.html")).toBe(true);
    expect(hasPackagedRendererOrigin("dbfox-app://attacker.invalid/index.html")).toBe(false);
    expect(hasPackagedRendererOrigin("dbfox-app://localhost.attacker.invalid/index.html")).toBe(false);
  });

  it("accepts only the fixed local application origin and contained paths", () => {
    expect(parseAppUrl("dbfox-app://localhost/")).toBe("index.html");
    expect(parseAppUrl("dbfox-app://localhost/assets/index.js")).toBe("assets/index.js");
    for (const url of [
      "https://localhost/index.html",
      "dbfox-app://example.com/index.html",
      "dbfox-app://localhost/index.html?source=remote",
      "dbfox-app://localhost/assets%2fsecret.js",
      "dbfox-app://localhost/assets%5csecret.js",
      "dbfox-app://user@localhost/index.html",
    ]) expect(() => parseAppUrl(url)).toThrow();
  });

  it("serves bounded files with a strict packaged CSP", async () => {
    const root = resolve(`.app-protocol-${Date.now()}-${Math.random()}`);
    roots.push(root);
    await mkdir(join(root, "assets"), { recursive: true });
    await writeFile(join(root, "index.html"), "<!doctype html><title>DBFox</title>");
    await writeFile(join(root, "assets", "index.js"), "export default 1;");

    const index = await handleAppRequest(new Request("dbfox-app://localhost/index.html"), root);
    expect(index.status).toBe(200);
    expect(index.headers.get("content-security-policy")).toContain("script-src 'self' dlc-asset:");
    expect(index.headers.get("content-security-policy")).toContain(
      "connect-src 'self' http://127.0.0.1:* dlc-asset:",
    );
    expect(index.headers.get("content-security-policy")).not.toContain("unsafe-eval");
    expect(index.headers.get("cache-control")).toBe("no-cache");
    const asset = await handleAppRequest(new Request("dbfox-app://localhost/assets/index.js"), root);
    expect(asset.headers.get("cache-control")).toContain("immutable");
    expect(await asset.text()).toBe("export default 1;");
  });

  it("rejects oversized application assets", async () => {
    const root = resolve(`.app-protocol-${Date.now()}-${Math.random()}`);
    roots.push(root);
    await mkdir(root);
    const huge = join(root, "huge.js");
    await writeFile(huge, "x");
    await truncate(huge, 10 * 1024 * 1024 + 1);
    expect((await handleAppRequest(new Request("dbfox-app://localhost/huge.js"), root)).status).toBe(413);
  });
});
