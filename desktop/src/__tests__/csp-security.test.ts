import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const desktopRoot = resolve(process.cwd());
const sourceRoot = join(process.cwd(), "src");

function applicationSourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const filePath = join(directory, entry);
    const relativePath = filePath.slice(sourceRoot.length + 1);
    if (relativePath.includes("__tests__")) return [];
    if (statSync(filePath).isDirectory()) return applicationSourceFiles(filePath);
    return /\.(?:ts|tsx|html)$/.test(filePath) ? [filePath] : [];
  });
}

describe("desktop CSP contracts", () => {
  it("ships a strict release policy without permissive inline script or style sources", () => {
    const config = JSON.parse(readFileSync(join(desktopRoot, "src-tauri", "tauri.conf.json"), "utf8"));
    const csp = config.app.security.csp as string;

    expect(csp).not.toContain("unsafe-inline");
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("script-src-attr 'none'");
    expect(csp).toContain("style-src 'self'");
    expect(csp).toContain("style-src-attr 'none'");
    expect(config.app.security.devCsp).toBeNull();
    expect(config.app.security.dangerousDisableAssetCspModification).toBe(false);
  });

  it("keeps boot assets external and rejects application style attributes", () => {
    const index = readFileSync(join(process.cwd(), "index.html"), "utf8");
    const styleTags = [...index.matchAll(/<style\b([^>]*)>([\s\S]*?)<\/style>/gi)];
    expect(styleTags).toHaveLength(1);
    expect(styleTags[0][1]).toContain("data-tauri-csp-style-nonce");
    expect(styleTags[0][2].trim()).toBe("");
    expect(index).not.toMatch(/<script(?![^>]*\bsrc=)[^>]*>/i);

    for (const sourcePath of applicationSourceFiles(sourceRoot)) {
      const source = readFileSync(sourcePath, "utf8");
      expect(sourcePath).toBeTruthy();
      expect(source).not.toMatch(/\bstyle\s*=\s*\{/);
      expect(source).not.toMatch(/\.style\s*[.=]/);
      expect(source).not.toContain("cssText");
      expect(source).not.toMatch(/setAttribute\(\s*["']style/i);
    }
  });
});
