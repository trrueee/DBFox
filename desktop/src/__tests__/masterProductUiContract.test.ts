import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

function productionSourceFiles(directory: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(directory)) {
    if (entry === "__tests__") continue;
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      files.push(...productionSourceFiles(path));
    } else if (/\.(?:ts|tsx)$/.test(entry) && !entry.endsWith(".d.ts")) {
      files.push(path);
    }
  }
  return files;
}

function cssBlock(source: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return source.match(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\n\\}`))?.[1] ?? "";
}

function hexVariable(block: string, name: string): string {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const value = block.match(new RegExp(`${escaped}:\\s*(#[0-9a-f]{6})`, "i"))?.[1];
  if (!value) throw new Error(`Missing hex token ${name}`);
  return value;
}

function contrastRatio(foreground: string, background: string): number {
  const luminance = (hex: string) => {
    const channels = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255);
    const [red, green, blue] = channels.map((channel) => (
      channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    ));
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  };
  const light = Math.max(luminance(foreground), luminance(background));
  const dark = Math.min(luminance(foreground), luminance(background));
  return (light + 0.05) / (dark + 0.05);
}

describe("master product UI contract", () => {
  const root = process.cwd();
  const sourceRoot = join(root, "src");

  it("uses capability-neutral product language and removes the legacy drawer", () => {
    const forbiddenCopy = /AI\s*问数|智能问数|提交问数|数据库客户端/;
    const failures = productionSourceFiles(sourceRoot).flatMap((file) => {
      const source = readFileSync(file, "utf8");
      return forbiddenCopy.test(source) ? [relative(sourceRoot, file).replaceAll("\\", "/")] : [];
    });

    expect(failures).toEqual([]);
    expect(existsSync(join(sourceRoot, "features/assistant/ContextDrawer.tsx"))).toBe(false);
    expect(existsSync(join(sourceRoot, "features/assistant/ContextDrawer.css"))).toBe(false);
    expect(readFileSync(join(root, "index.html"), "utf8")).toContain("<title>DBFox — Agent 工作空间</title>");
  });

  it("loads canonical tokens first and keeps the specified default geometry", () => {
    const main = readFileSync(join(sourceRoot, "main.tsx"), "utf8");
    const tokens = readFileSync(join(sourceRoot, "styles/tokens.css"), "utf8");
    const layout = readFileSync(join(sourceRoot, "features/appShell/ResizableWorkspaceLayout.tsx"), "utf8");

    expect(main.indexOf('import "./styles/tokens.css"')).toBeLessThan(main.indexOf('import "./index.css"'));
    expect(layout).toContain("defaultSize={sidebarCollapsed ? 48 : sidebarDefaultWidth}");
    expect(layout).toContain("minSize={sidebarCollapsed ? 48 : 240}");
    expect(layout).toContain("maxSize={sidebarCollapsed ? 48 : settingsOpen ? 320 : 336}");
    expect(tokens).toContain("--ui-font-control: calc(14px + var(--appearance-ui-font-adjust))");
    expect(tokens).toContain("--ui-font-body: calc(14px + var(--appearance-ui-font-adjust))");
    expect(tokens).toContain("--agent-font-body: calc(14px + var(--appearance-agent-font-adjust))");
  });

  it("keeps Fluent-derived semantic color roles readable in light and dark themes", () => {
    const tokens = readFileSync(join(sourceRoot, "styles/tokens.css"), "utf8");
    const button = readFileSync(join(sourceRoot, "components/ui/button.css"), "utf8");
    const themes = [cssBlock(tokens, ":root"), cssBlock(tokens, ".dark")];

    for (const theme of themes) {
      const panel = hexVariable(theme, "--color-panel");
      expect(contrastRatio(hexVariable(theme, "--color-text-primary"), panel)).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(hexVariable(theme, "--color-text-muted"), panel)).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(hexVariable(theme, "--color-on-primary"), hexVariable(theme, "--color-primary-fill"))).toBeGreaterThanOrEqual(4.5);
      expect(contrastRatio(hexVariable(theme, "--color-on-danger"), hexVariable(theme, "--color-danger-fill"))).toBeGreaterThanOrEqual(4.5);
    }

    expect(tokens).toContain("Default semantic colors follow Fluent 2");
    expect(button).toContain("background: var(--color-primary-fill)");
    expect(button).not.toContain("background: var(--color-primary);");
  });

  it("uses only the 14/16/20 Lucide size scale in production UI", () => {
    const failures = productionSourceFiles(sourceRoot).flatMap((file) => {
      const source = readFileSync(file, "utf8");
      const invalid = [...source.matchAll(/\bsize=\{(\d+)\}/g)]
        .map((match) => Number(match[1]))
        .filter((size) => ![14, 16, 20].includes(size));
      const isBrandIcon = file.endsWith(join("components", "TitleBar.tsx"))
        || file.endsWith(join("components", "EngineStartupGate.tsx"));
      return invalid.filter((size) => !(isBrandIcon && [24, 52].includes(size))).map(
        (size) => `${relative(sourceRoot, file).replaceAll("\\", "/")}: ${size}px`,
      );
    });

    expect(failures).toEqual([]);
  });

  it("keeps startup presentation neutral and makes Design Lab render production components", () => {
    const boot = readFileSync(join(sourceRoot, "boot.css"), "utf8");
    const cspSafe = readFileSync(join(sourceRoot, "csp-safe.css"), "utf8");
    const designLab = readFileSync(join(sourceRoot, "design-lab/DesignLab.tsx"), "utf8");

    expect(boot).not.toContain("radial-gradient");
    expect(cspSafe).not.toContain("radial-gradient");
    expect(designLab).toContain('import { AgentTimeline }');
    expect(designLab).toContain('import { ApprovalCard }');
    expect(designLab).toContain('import { AgentQuestion }');
    expect(designLab).toContain("<AgentTimeline");
    expect(designLab).toContain("<ApprovalCard");
    expect(designLab).toContain("<AgentQuestion");
    expect(designLab).toContain("<UnifiedComposer");
  });
});
