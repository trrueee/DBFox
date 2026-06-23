import { readdirSync, readFileSync, statSync } from "node:fs";
import { relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

const srcRoot = resolve(__dirname, "..");

function read(relativePath: string): string {
  return readFileSync(resolve(srcRoot, relativePath), "utf8");
}

function listSourceFiles(root: string, extensions: Set<string>): string[] {
  return readdirSync(root).flatMap((entry) => {
    const fullPath = resolve(root, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      if (entry === "__tests__" || entry === "dist") return [];
      return listSourceFiles(fullPath, extensions);
    }
    return extensions.has(fullPath.slice(fullPath.lastIndexOf("."))) ? [fullPath] : [];
  });
}

describe("agent visual tokens", () => {
  it("defines semantic agent tokens for stages and trust states in both themes", () => {
    const tokens = read("styles/tokens.css");

    for (const token of [
      "--ui-font-caption",
      "--ui-font-control",
      "--ui-font-body",
      "--ui-font-title",
      "--agent-font-body",
      "--agent-font-caption",
      "--agent-stage-understanding",
      "--agent-stage-executing",
      "--agent-stage-repairing",
      "--agent-chart-1",
      "--agent-chart-tooltip-shadow",
      "--trust-safe",
      "--trust-warning",
      "--trust-danger",
    ]) {
      expect(tokens).toContain(token);
    }

    expect(tokens).toMatch(/\.dark\s*{[\s\S]*--agent-stage-understanding:/);
    expect(tokens).toMatch(/\.dark\s*{[\s\S]*--ui-font-body:/);
    expect(tokens).toMatch(/\.dark\s*{[\s\S]*--agent-chart-1:/);
    expect(tokens).toMatch(/\.dark\s*{[\s\S]*--trust-danger:/);
  });

  it("keeps conversation workspace colors behind tokens", () => {
    const css = read("features/conversation/workspace/conversationWorkspace.css");

    expect(css).not.toMatch(/#[0-9A-Fa-f]{3,8}/);
    expect(css).not.toMatch(/\brgba?\(/);
    expect(css).not.toMatch(/(?:background|color|border(?:-color)?):\s*(?:white|black|slate|blue)\b/i);
    expect(css).not.toMatch(/font-size:\s*(?:\d+(?:\.\d+)?px|\d+(?:\.\d+)?rem|\d+(?:\.\d+)?em)/);
    expect(css).toContain("var(--agent-surface)");
    expect(css).toContain("var(--agent-font-body)");
    expect(css).toContain("var(--trust-warning)");
  });

  it("keeps artifact views off hardcoded Tailwind color utilities", () => {
    for (const relativePath of [
      "features/workspace/artifacts/MarkdownArtifactView.tsx",
      "features/workspace/artifacts/SqlArtifactView.tsx",
      "features/workspace/artifacts/TableArtifactView.tsx",
      "features/workspace/artifacts/ChartArtifactView.tsx",
    ]) {
      const source = read(relativePath);
      expect(source).not.toMatch(/\b(?:text|bg|border)-(?:slate|blue|gray|red|amber|white)-?\d*/);
      expect(source).not.toMatch(/style=\{\{[^}]*height:\s*["']\d/);
    }
  });

  it("keeps chart rendering colors behind agent tokens", () => {
    const source = read("features/workspace/artifacts/ChartArtifactView.tsx");

    expect(source).toContain("--agent-chart-1");
    expect(source).toContain("--agent-chart-tooltip-shadow");
    expect(source).not.toMatch(/#[0-9A-Fa-f]{3,8}/);
    expect(source).not.toMatch(/\brgba?\(/);
    expect(source).not.toMatch(/theme\s*===\s*["']dark["']/);
  });

  it("keeps UI typography on shared tokens across source files", () => {
    const cssFiles = listSourceFiles(srcRoot, new Set([".css"]))
      .filter((file) => !relative(srcRoot, file).replaceAll("\\", "/").startsWith("styles/tokens.css"));
    const componentFiles = listSourceFiles(srcRoot, new Set([".tsx"]));

    for (const file of cssFiles) {
      const source = readFileSync(file, "utf8");
      expect(source, relative(srcRoot, file)).not.toMatch(/font-size:\s*(?:\d+(?:\.\d+)?px|\d+(?:\.\d+)?rem|\d+(?:\.\d+)?em)/);
    }

    for (const file of componentFiles) {
      const source = readFileSync(file, "utf8");
      expect(source, relative(srcRoot, file)).not.toMatch(/text-\[(?:\d+(?:\.\d+)?px|\d+(?:\.\d+)?rem|\d+(?:\.\d+)?em)\]/);
      expect(source, relative(srcRoot, file)).not.toMatch(/(?<![\w-])(?:[a-z-]+:)*text-(?:xs|sm|base|lg|xl|2xl|3xl|4xl|5xl|6xl)(?![\w-])/);
    }
  });
});
