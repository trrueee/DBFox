import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const dataSourceListSource = join(process.cwd(), "src/features/datasource-management/DataSourceList.tsx");
const dataSourceDetailSource = join(process.cwd(), "src/features/datasource-management/DataSourceDetail.tsx");
const dataSourceFormSource = join(process.cwd(), "src/features/datasource-management/DataSourceForm.tsx");
const schemaSyncPanelSource = join(process.cwd(), "src/features/datasource-management/SchemaSyncPanel.tsx");
const dataSourcesPageSource = join(process.cwd(), "src/pages/DataSourcesPage.tsx");
const localCss = join(process.cwd(), "src/features/datasource-management/DataSourceManagement.css");
const appCss = join(process.cwd(), "src/App.css");

const managedSources = [dataSourceListSource, dataSourceDetailSource, dataSourceFormSource, schemaSyncPanelSource];

const localSelectors = [
  ".ds-page",
  ".ds-page--workspace",
  ".ds-page-header",
  ".ds-page-title",
  ".ds-page-toolbar",
  ".ds-page-toolbar__meta",
  ".ds-page-empty",
  ".ds-page-console",
  ".ds-page-detail-shell",
  ".hifi-datasource-page",
  ".hifi-datasource-form",
  ".hifi-datasource-console",
  ".hifi-datasource-list",
  ".hifi-datasource-list-item",
  ".hifi-datasource-list-item.active",
  ".hifi-datasource-detail",
  ".ds-management-search-bar",
  ".ds-management-search-shell",
  ".ds-management-search-icon",
  ".ds-management-search-input",
  ".ds-management-list-scroll",
  ".ds-management-list-item-main",
  ".ds-management-list-item-title",
  ".ds-management-list-item-meta",
  ".ds-management-badge",
  ".ds-management-health-dot",
  ".ds-detail",
  ".ds-detail-header",
  ".ds-detail-identity",
  ".ds-detail-icon",
  ".ds-detail-title-row",
  ".ds-detail-title",
  ".ds-detail-badge",
  ".ds-detail-badge--readonly",
  ".ds-detail-path",
  ".ds-detail-actions",
  ".ds-detail-button",
  ".ds-detail-button--danger",
  ".ds-detail-tabs",
  ".ds-detail-tab",
  ".ds-detail-section-stack",
  ".ds-detail-section-heading",
  ".ds-detail-summary-grid",
  ".ds-detail-sync-feedback",
  ".ds-detail-error",
  ".ds-detail-error-title",
  ".ds-detail-error-body",
  ".ds-detail-tile",
  ".ds-detail-tile__label",
  ".ds-detail-tile__value",
  ".ds-detail-tile__value--emphasized",
  ".ds-detail-health",
  ".ds-detail-health__dot",
  ".ds-detail-health__text",
  ".ds-detail-health__latency",
  ".ds-form",
  ".ds-form-section",
  ".ds-form-section--divided",
  ".ds-form-db-grid",
  ".ds-form-db-option",
  ".ds-form-db-option.is-active",
  ".ds-form-db-option__icon",
  ".ds-form-grid",
  ".ds-form-grid--two",
  ".ds-form-grid--connection",
  ".ds-form-grid--ssh",
  ".ds-form-inline-row",
  ".ds-form-grow-field",
  ".ds-form-field",
  ".ds-form-label",
  ".ds-form-checkbox-row",
  ".ds-form-checkbox",
  ".ds-form-nested-panel",
  ".ds-form-error",
  ".ds-form-test-result",
  ".ds-form-test-result--success",
  ".ds-form-test-result--error",
  ".ds-form-test-result--testing",
  ".ds-form-test-result__content",
  ".ds-form-sync-section",
  ".ds-form-actions",
  ".ds-sync-panel",
  ".ds-sync-panel__label",
  ".ds-sync-panel__checkbox",
  ".ds-sync-panel__feedback",
];

describe("datasource management styles", () => {
  it("keeps list and sync panel styling in local CSS without inline styles", () => {
    expect(existsSync(localCss)).toBe(true);

    const css = readFileSync(localCss, "utf8");
    for (const selector of localSelectors) {
      expect(css).toContain(selector);
    }

    for (const sourcePath of managedSources) {
      const source = readFileSync(sourcePath, "utf8");
      expect(source).toContain('import "./DataSourceManagement.css";');
      expect(source).not.toContain("style=");
    }
  });

  it("uses the shared Input primitive for the datasource list search box", () => {
    const source = readFileSync(dataSourceListSource, "utf8");

    expect(source).toContain('from "../../components/ui";');
    expect(source).toContain("<Input");
    expect(source).not.toMatch(/<input\b/);
  });

  it("uses the shared Button primitive for datasource detail actions", () => {
    const source = readFileSync(dataSourceDetailSource, "utf8");

    expect(source).toContain('from "../../components/ui";');
    expect(source).toContain("<Button");
    expect(source).not.toMatch(/<button\b/);
  });

  it("uses shared form primitives for datasource form controls", () => {
    const source = readFileSync(dataSourceFormSource, "utf8");

    expect(source).toContain('from "../../components/ui";');
    expect(source).toContain("<Input");
    expect(source).toContain("<Select");
    expect(source).toContain("<Button");
    expect(source).not.toMatch(/<button\b/);
    expect(source).not.toMatch(/<select\b/);
    expect(source).not.toContain('className="hifi-input"');
    expect(source).not.toContain('className="hifi-select"');
    expect(source).not.toContain("hifi-btn");
  });

  it("uses react-hook-form and zod for datasource form validation", () => {
    const formSource = readFileSync(dataSourceFormSource, "utf8");
    const pageSource = readFileSync(dataSourcesPageSource, "utf8");

    expect(formSource).toContain('from "react-hook-form"');
    expect(formSource).toContain('from "@hookform/resolvers/zod"');
    expect(formSource).toContain('from "zod"');
    expect(formSource).toContain("datasourceFormSchema");
    expect(formSource).toContain("zodResolver");
    expect(pageSource).not.toContain("const validateForm");
  });

  it("keeps the datasource page shell on shared primitives and local styles", () => {
    const source = readFileSync(dataSourcesPageSource, "utf8");
    const globalCss = readFileSync(appCss, "utf8");

    expect(source).toContain('from "../components/ui";');
    expect(source).toContain("<Button");
    expect(source).toContain("<EmptyState");
    expect(source).toContain('import "../features/datasource-management/DataSourceManagement.css";');
    expect(source).not.toMatch(/<button\b/);
    expect(source).not.toContain("style=");
    expect(source).not.toContain("hifi-btn");
    expect(source).not.toContain("hifi-empty-state");
    expect(source).not.toContain("hifi-page-header");
    expect(source).not.toContain("hifi-datasource-console");
    expect(source).not.toContain("hifi-datasource-page");

    expect(globalCss).not.toMatch(/\.hifi-datasource-(page|form|console|list|detail|metrics|config-grid)/);
  });
});
