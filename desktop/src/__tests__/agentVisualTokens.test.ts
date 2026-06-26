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

function tokenValue(tokens: string, selector: ":root" | ".dark", token: string): string {
  const block = tokens.match(new RegExp(`${selector.replace(".", "\\.")}\\s*{([\\s\\S]*?)}`))?.[1] || "";
  return block.match(new RegExp(`${token}:\\s*([^;]+);`))?.[1].trim() || "";
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
      "--surface-base",
      "--surface-panel",
      "--surface-card",
      "--surface-card-hover",
      "--border-subtle",
      "--border-strong",
      "--radius-sm",
      "--radius-md",
      "--radius-lg",
      "--radius-xl",
      "--radius-pill",
      "--shadow-card",
      "--shadow-card-hover",
    ]) {
      expect(tokens).toContain(token);
    }

    expect(tokens).toMatch(/\.dark\s*{[\s\S]*--agent-stage-understanding:/);
    expect(tokens).toMatch(/\.dark\s*{[\s\S]*--ui-font-body:/);
    expect(tokens).toMatch(/\.dark\s*{[\s\S]*--agent-chart-1:/);
    expect(tokens).toMatch(/\.dark\s*{[\s\S]*--trust-danger:/);
  });

  it("sets desktop typography scale for readable Chinese UI", () => {
    const tokens = read("styles/tokens.css");
    const expected = {
      "--ui-font-nano": "9px",
      "--ui-font-micro": "10px",
      "--ui-font-caption": "11px",
      "--ui-font-label": "12px",
      "--ui-font-control": "13px",
      "--ui-font-body": "14px",
      "--ui-font-input": "14px",
      "--ui-font-section-title": "15px",
      "--ui-font-title": "18px",
      "--ui-font-display": "24px",
      "--ui-font-code": "13px",
      "--ui-font-data": "12px",
      "--agent-font-micro": "10px",
      "--agent-font-caption": "11px",
      "--agent-font-label": "12px",
      "--agent-font-ui": "13px",
      "--agent-font-code": "13px",
      "--agent-font-input": "15px",
      "--agent-font-title": "15px",
      "--agent-font-body": "15px",
      "--agent-font-subtitle": "17px",
      "--agent-font-display": "20px",
    };

    for (const selector of [":root", ".dark"] as const) {
      for (const [token, value] of Object.entries(expected)) {
        expect(tokenValue(tokens, selector, token), `${selector} ${token}`).toBe(value);
      }
    }
  });

  it("keeps system text tokens high contrast instead of washed out gray", () => {
    const tokens = read("styles/tokens.css");

    expect(tokenValue(tokens, ":root", "--color-text-primary")).toBe("#0F172A");
    expect(tokenValue(tokens, ":root", "--color-text-secondary")).toBe("#334155");
    expect(tokenValue(tokens, ":root", "--color-text-muted")).toBe("#475569");
    expect(tokenValue(tokens, ".dark", "--color-text-primary")).toBe("#F8FAFC");
    expect(tokenValue(tokens, ".dark", "--color-text-secondary")).toBe("#CBD5E1");
    expect(tokenValue(tokens, ".dark", "--color-text-muted")).toBe("#94A3B8");
  });

  it("keeps chat bubbles neutral and answer text aligned with user body size", () => {
    const tokens = read("styles/tokens.css");
    const css = read("features/conversation/workspace/conversationWorkspace.css");

    expect(tokenValue(tokens, ":root", "--agent-user-bg")).toBe("#F3F4F6");
    expect(tokenValue(tokens, ":root", "--agent-user-border")).toBe("#D1D5DB");
    expect(tokenValue(tokens, ":root", "--agent-user-text")).toBe("#374151");
    expect(tokenValue(tokens, ".dark", "--agent-user-bg")).toBe("#1F2937");
    expect(tokenValue(tokens, ".dark", "--agent-user-border")).toBe("#4B5563");
    expect(tokenValue(tokens, ".dark", "--agent-user-text")).toBe("#E5E7EB");

    expect(css).toMatch(/\.conv-message-user \.conv-message-body p,[\s\S]*?font-size:\s*var\(--agent-font-body\);/);
    expect(css).toMatch(/\.conv-answer-document \.hifi-md-p,[\s\S]*?font-size:\s*var\(--agent-font-body\);/);
    expect(css).toMatch(/\.conv-run-status-copy strong\s*{[\s\S]*?font-size:\s*var\(--agent-font-ui\);/);
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
    const source = read("features/workspace/artifacts/useChartTheme.ts");

    expect(source).toContain("--agent-chart-1");
    expect(source).toContain("--agent-chart-tooltip-shadow");
    expect(source).not.toMatch(/#[0-9A-Fa-f]{3,8}/);
    expect(source).not.toMatch(/\brgba?\(/);
    expect(source).not.toMatch(/theme\s*===\s*["']dark["']/);
  });

  it("keeps high-frequency UI surfaces behind tokens", () => {
    for (const relativePath of [
      "App.css",
      "features/conversation/workspace/conversationWorkspace.css",
      "components/data-grid/data-grid.css",
    ]) {
      const source = read(relativePath);
      expect(source, relativePath).not.toMatch(/background:\s*#(?:fff|ffffff|f8fafc|f1f5f9|fbfcfe)\b/i);
      expect(source, relativePath).not.toMatch(/border(?:-color)?:\s*#(?:e2e8f0|e8edf4|cbd5e1)\b/i);
    }
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
