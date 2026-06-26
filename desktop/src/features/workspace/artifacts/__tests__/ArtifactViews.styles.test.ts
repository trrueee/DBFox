import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const artifactCardSource = join(process.cwd(), "src/features/workspace/artifacts/ArtifactCard.tsx");
const sqlSource = join(process.cwd(), "src/features/workspace/artifacts/SqlArtifactView.tsx");
const markdownSource = join(process.cwd(), "src/features/workspace/artifacts/MarkdownArtifactView.tsx");
const chartSource = join(process.cwd(), "src/features/workspace/artifacts/ChartArtifactView.tsx");
const tableSource = join(process.cwd(), "src/features/workspace/artifacts/TableArtifactView.tsx");
const gridSource = join(process.cwd(), "src/features/workspace/artifacts/table/ArtifactTableGrid.tsx");
const artifactCardCss = join(process.cwd(), "src/features/workspace/artifacts/ArtifactCard.css");
const artifactViewsCss = join(process.cwd(), "src/features/workspace/artifacts/ArtifactViews.css");
const appCss = join(process.cwd(), "src/App.css");

const artifactCardSelectors = [
  ".artifact-card",
  ".artifact-card-header",
  ".artifact-card-title",
  ".artifact-card-badge",
  ".artifact-card-desc",
  ".artifact-card-meta",
  ".artifact-card-body",
  ".artifact-card-actions",
  ".artifact-pill",
  ".artifact-pill--warning",
];

const artifactViewSelectors = [
  ".sql-artifact__editor",
  ".artifact-action-button",
  ".chart-artifact-card",
  ".chart-artifact__meta-row",
  ".chart-artifact__formula",
  ".chart-artifact__muted",
  ".chart-artifact__body",
  ".chart-artifact__body.is-expanded",
  ".chart-artifact__body.is-compact",
  ".chart-artifact__echarts",
  ".chart-artifact__type-button",
];

describe("artifact view styles", () => {
  it("keeps the shared artifact card shell and pills in local CSS", () => {
    const source = readFileSync(artifactCardSource, "utf8");
    const localCss = readFileSync(artifactCardCss, "utf8");
    const globalCss = readFileSync(appCss, "utf8");

    expect(source).toContain('import "./ArtifactCard.css";');
    expect(existsSync(artifactCardCss)).toBe(true);
    for (const selector of artifactCardSelectors) {
      expect(localCss).toContain(selector);
      expect(globalCss).not.toContain(selector);
    }
  });

  it("uses shared Button primitives and local classes for SQL, Markdown, and chart actions", () => {
    const sources = [sqlSource, markdownSource, chartSource].map((path) => readFileSync(path, "utf8"));
    const combined = sources.join("\n");
    const localCss = readFileSync(artifactViewsCss, "utf8");
    const globalCss = readFileSync(appCss, "utf8");

    expect(existsSync(artifactViewsCss)).toBe(true);
    expect(combined).toContain('import "./ArtifactViews.css";');
    expect(combined).toContain('from "../../../components/ui";');
    expect(combined).toContain("<Button");
    expect(combined).not.toMatch(/<button\b/);
    expect(combined).not.toMatch(/hifi-guide-btn|hifi-artifact-action|hifi-chart|hifi-artifact-pill|flex flex-wrap|items-center|gap-1/);
    expect(combined).not.toMatch(/className="[^"]*\bfont-mono\b/);
    expect(combined).not.toMatch(/style=\{/);
    expect(chartSource).not.toContain("chartFillStyle");

    for (const selector of artifactViewSelectors) {
      expect(localCss).toContain(selector);
      expect(globalCss).not.toContain(selector);
    }
  });

  it("wraps highlighted SQL previews instead of clipping long statements", () => {
    const localCss = readFileSync(artifactViewsCss, "utf8");
    const sqlBlockRule = localCss.match(/\.sql-code-block\s*\{[^}]+\}/)?.[0] ?? "";

    expect(sqlBlockRule).toContain("white-space: pre-wrap");
    expect(sqlBlockRule).toContain("overflow-wrap: anywhere");
    expect(sqlBlockRule).not.toContain("min-width: max-content");
    expect(localCss).toContain(".sql-token-keyword");
    expect(localCss).toContain(".sql-token-function");
    expect(localCss).toContain(".sql-token-string");
  });

  it("uses GitHub Light SQL syntax colors for artifact surfaces", () => {
    const localCss = readFileSync(artifactViewsCss, "utf8");
    const ruleFor = (selector: string) => localCss.match(new RegExp(`${selector.replace(".", "\\.")}\\s*\\{[^}]+\\}`))?.[0] ?? "";
    const sqlBlockRule = ruleFor(".sql-code-block");

    expect(sqlBlockRule).toContain("background: #f6f8fa");
    expect(sqlBlockRule).toContain("border: 1px solid #d0d7de");
    expect(sqlBlockRule).toContain("color: #24292f");
    expect(sqlBlockRule).toContain('font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace');
    expect(sqlBlockRule).toContain("line-height: 1.75");
    expect(ruleFor(".sql-token-keyword")).toContain("color: #0550ae");
    expect(ruleFor(".sql-token-keyword")).toContain("font-weight: 600");
    expect(ruleFor(".sql-token-function")).toContain("color: #8250df");
    expect(ruleFor(".sql-token-function")).toContain("font-weight: 600");
    expect(ruleFor(".sql-token-string")).toContain("color: #116329");
    expect(ruleFor(".sql-token-number")).toContain("color: #953800");
    expect(ruleFor(".sql-token-comment")).toContain("color: #6e7781");
    expect(ruleFor(".sql-token-operator,\\s*.sql-token-punctuation")).toContain("color: #57606a");
    expect(ruleFor(".sql-token-identifier")).toContain("color: #24292f");
  });

  it("uses artifact-local pill and sort indicator classes for table metadata", () => {
    const table = readFileSync(tableSource, "utf8");
    const grid = readFileSync(gridSource, "utf8");
    const combined = [table, grid].join("\n");

    expect(combined).not.toMatch(/hifi-artifact-pill|hifi-artifact-sort-indicator|hifi-result-empty/);
    expect(combined).toContain("artifact-pill");
    expect(combined).toContain("artifact-table-sort-indicator");
    expect(combined).toContain("artifact-table-empty");
  });
});
