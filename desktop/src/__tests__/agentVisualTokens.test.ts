import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const srcRoot = resolve(__dirname, "..");

function read(relativePath: string): string {
  return readFileSync(resolve(srcRoot, relativePath), "utf8");
}

describe("agent visual tokens", () => {
  it("defines semantic agent tokens for stages and trust states in both themes", () => {
    const tokens = read("styles/tokens.css");

    for (const token of [
      "--agent-stage-understanding",
      "--agent-stage-executing",
      "--agent-stage-repairing",
      "--trust-safe",
      "--trust-warning",
      "--trust-danger",
    ]) {
      expect(tokens).toContain(token);
    }

    expect(tokens).toMatch(/\.dark\s*{[\s\S]*--agent-stage-understanding:/);
    expect(tokens).toMatch(/\.dark\s*{[\s\S]*--trust-danger:/);
  });

  it("keeps conversation workspace colors behind tokens", () => {
    const css = read("features/conversation/workspace/conversationWorkspace.css");

    expect(css).not.toMatch(/#[0-9A-Fa-f]{3,8}/);
    expect(css).not.toMatch(/\brgba?\(/);
    expect(css).not.toMatch(/(?:background|color|border(?:-color)?):\s*(?:white|black|slate|blue)\b/i);
    expect(css).toContain("var(--agent-surface)");
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
});
