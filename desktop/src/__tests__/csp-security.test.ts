import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

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
  it("keeps boot assets external and rejects application style attributes", () => {
    const index = readFileSync(join(process.cwd(), "index.html"), "utf8");
    const styleTags = [...index.matchAll(/<style\b([^>]*)>([\s\S]*?)<\/style>/gi)];
    expect(styleTags).toHaveLength(0);
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
