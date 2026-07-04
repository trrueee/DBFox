import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { describe, expect, it } from "vitest";

// Consolidated from the former scattered *.styles.test.ts files.
// Keep style-contract assertions here so file count stays manageable.
// Source: desktop/src/__tests__/AppResizableShell.styles.test.ts
{

const appSource = join(process.cwd(), "src/App.tsx");
const appCss = join(process.cwd(), "src/App.css");
const treeSource = join(process.cwd(), "src/features/datasource/DataSourceTree.tsx");
const treeCss = join(process.cwd(), "src/features/datasource/DataSourceTree.css");

describe("App resizable shell", () => {
  it("uses the DBFox resizable primitive instead of the hand-rolled sidebar dragger", () => {
    const source = readFileSync(appSource, "utf8");
    const css = readFileSync(appCss, "utf8");
    const tree = readFileSync(treeSource, "utf8");
    const treeStyles = readFileSync(treeCss, "utf8");

    expect(source).toContain("ResizablePanelGroup");
    expect(source).toContain("ResizablePanel");
    expect(source).toContain("ResizableHandle");
    expect(source).toContain('from "./components/ui"');
    expect(source).not.toContain("useSidebarLayout");
    expect(source).not.toContain("handleResizeStart");
    expect(source).not.toContain("sidebarWidth");
    expect(source).not.toContain("app-resizer");
    expect(css).toContain(".app-body-split");
    expect(css).not.toContain(".app-resizer");
    expect(tree).not.toContain("sidebarWidth");
    expect(tree).not.toContain("CSSProperties");
    expect(treeStyles).toContain("width: 100%");
    expect(treeStyles).not.toContain("--sidebar-width");
  });
});

}
// Source: desktop/src/components/__tests__/CommandPalette.styles.test.ts
{

const sourcePath = join(process.cwd(), "src/components/CommandPalette.tsx");
const cssPath = join(process.cwd(), "src/components/CommandPalette.css");
const commandCssPath = join(process.cwd(), "src/components/ui/command.css");
const appCssPath = join(process.cwd(), "src/App.css");

const commandSelectors = [
  ".dbfox-command-panel",
  ".dbfox-command-search",
  ".dbfox-command-search-icon",
  ".dbfox-command-input",
  ".dbfox-command-kbd",
  ".dbfox-command-list",
  ".dbfox-command-empty",
  ".dbfox-command-group",
  ".dbfox-command-category",
  ".dbfox-command-item",
  ".dbfox-command-item-icon",
  ".dbfox-command-item-label",
];

describe("CommandPalette styles and foundation", () => {
  it("uses cmdk for command palette behavior and keeps DBFox presentation local", () => {
    const source = readFileSync(sourcePath, "utf8");
    const appCss = readFileSync(appCssPath, "utf8");

    expect(source).not.toContain('from "cmdk"');
    expect(source).toContain('from "./ui"');
    expect(source).toContain('import "./CommandPalette.css";');
    expect(existsSync(cssPath)).toBe(true);
    expect(existsSync(commandCssPath)).toBe(true);

    expect(source).not.toMatch(/selectedIndex|flatIndexMap|filteredCommands|listRef|window\.addEventListener\("keydown"/);
    expect(source).not.toMatch(/hifi-command-/);
    expect(appCss).not.toMatch(/hifi-command-|dbfox-command-/);

    const localCss = readFileSync(cssPath, "utf8");
    expect(localCss).toContain(".dbfox-command-overlay");
    expect(localCss).toContain(".dbfox-command-footer");
    expect(localCss).not.toContain(".dbfox-command-item");

    const commandCss = readFileSync(commandCssPath, "utf8");
    for (const selector of commandSelectors) {
      expect(commandCss).toContain(selector);
    }
  });
});

}
// Source: desktop/src/components/__tests__/DialogSurfaces.styles.test.ts
{

const componentDir = join(process.cwd(), "src/components");

const utilityClassPattern = /\b(?:sm:max-w-|p-\d|px-\d|py-\d|gap-\d|space-y-|border-\[|bg-\[|text-\[|font-semibold|font-mono|rounded(?:-|\b)|flex items-|items-center|items-start|justify-|whitespace-pre-wrap|overflow-auto|max-h-\[|w-\d|h-\d|shrink-0|mt-\d)/;

const surfaces = [
  {
    sourcePath: join(componentDir, "SettingsDialog.tsx"),
    cssPath: join(componentDir, "SettingsDialog.css"),
    importStatement: 'import "./SettingsDialog.css"',
    selectors: [
      ".settings-dialog-content",
      ".settings-dialog-header",
      ".settings-dialog-title",
      ".settings-dialog-title-icon",
      ".settings-dialog-footer",
      ".settings-dialog-actions",
      ".settings-dialog-save",
      ".settings-button-indicator",
    ],
  },
  {
    sourcePath: join(componentDir, "ConfirmDialog.tsx"),
    cssPath: join(componentDir, "ConfirmDialog.css"),
    importStatement: 'import "./ConfirmDialog.css"',
    selectors: [
      ".confirm-dialog-content",
      ".confirm-dialog-title-row",
      ".confirm-dialog-icon",
      ".confirm-dialog-icon--danger",
      ".confirm-dialog-icon--warning",
      ".confirm-dialog-icon--info",
      ".confirm-dialog-message",
    ],
  },
  {
    sourcePath: join(componentDir, "DangerConfirmDialog.tsx"),
    cssPath: join(componentDir, "DangerConfirmDialog.css"),
    importStatement: 'import "./DangerConfirmDialog.css"',
    selectors: [
      ".danger-confirm-dialog-content",
      ".danger-confirm-dialog-title-row",
      ".danger-confirm-dialog-summary",
      ".danger-confirm-dialog-code",
      ".danger-confirm-dialog-input",
      ".danger-confirm-dialog-input--valid",
      ".danger-confirm-dialog-warning",
    ],
  },
];

describe("dialog business surfaces", () => {
  it("keeps dialog-specific presentation in local CSS files", () => {
    for (const surface of surfaces) {
      const source = readFileSync(surface.sourcePath, "utf8");
      const css = readFileSync(surface.cssPath, "utf8");

      expect(source).toContain(surface.importStatement);
      expect(source).not.toMatch(utilityClassPattern);
      for (const selector of surface.selectors) {
        expect(css).toContain(selector);
      }
    }
  });
});

}

// Source: desktop/src/components/__tests__/ErDiagram.styles.test.ts
{

const sourcePath = join(process.cwd(), "src/components/ErDiagram.tsx");
const cssPath = join(process.cwd(), "src/components/ErDiagram.css");

const erDiagramSelectors = [
  ".er-diagram",
  ".er-diagram__viewport",
  ".er-card",
  ".er-card--focus",
  ".er-card--secondary",
  ".er-card__handle",
  ".er-card__header",
  ".er-card__status",
  ".er-card__title",
  ".er-card__annotate",
  ".er-card__fields",
  ".er-card__field",
  ".er-card__field-marker",
  ".er-card__field-marker--pk",
  ".er-card__field-marker--fk",
  ".er-card__field-name",
  ".er-card__field-name--primary",
  ".er-card__field-type",
  ".er-card__toggle",
  ".er-card__comment",
  ".er-edge-label",
  ".er-edge-label--inferred",
  ".er-flow-controls",
  ".er-flow-minimap",
];

describe("ErDiagram styles", () => {
  it("keeps React Flow diagram presentation in local CSS without JSX inline styles", () => {
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain('import "./ErDiagram.css";');
    expect(existsSync(cssPath)).toBe(true);
    expect(source).not.toContain("style={{");
    expect(source).not.toContain("style={");
    expect(source).not.toContain("currentTarget.style");
    expect(source).not.toMatch(/onMouseEnter|onMouseLeave/);
    expect(source).not.toContain('viewMode === "module"');
    expect(source).not.toContain("moduleGroups");

    const css = readFileSync(cssPath, "utf8");
    for (const selector of erDiagramSelectors) {
      expect(css).toContain(selector);
    }
  });
});

}

// Source: desktop/src/components/__tests__/ImageCell.styles.test.ts
{

const imageCellSource = join(process.cwd(), "src/components/ImageCell.tsx");
const imageCellCss = join(process.cwd(), "src/components/ImageCell.css");
const appCss = join(process.cwd(), "src/App.css");

describe("ImageCell foundation", () => {
  it("delegates image preview positioning to DBFox HoverCard and lightbox to Dialog", () => {
    const source = readFileSync(imageCellSource, "utf8");

    expect(source).toContain('import "./ImageCell.css";');
    expect(source).toContain("HoverCard");
    expect(source).toContain("HoverCardContent");
    expect(source).toContain("HoverCardTrigger");
    expect(source).toContain("Dialog");
    expect(source).toContain("DialogContent");
    expect(source).not.toContain("createPortal");
    expect(source).not.toContain("getBoundingClientRect");
    expect(source).not.toContain("window.innerWidth");
    expect(source).not.toContain("popoverPos");
  });

  it("keeps image cell presentation local instead of App.css fixed-position popovers", () => {
    expect(existsSync(imageCellCss)).toBe(true);
    const css = readFileSync(imageCellCss, "utf8");
    const globalCss = readFileSync(appCss, "utf8");

    for (const selector of [
      ".hifi-img-cell",
      ".hifi-img-thumb",
      ".hifi-img-url",
      ".hifi-img-hover-card",
      ".hifi-img-lightbox",
      ".hifi-img-lightbox-bar",
    ]) {
      expect(css).toContain(selector);
      expect(globalCss).not.toContain(selector);
    }
    expect(globalCss).not.toContain(".hifi-img-popover");
  });
});

}

// Source: desktop/src/components/__tests__/LlmConfigPanel.styles.test.ts
{

const panelSource = join(process.cwd(), "src/components/LlmConfigPanel.tsx");
const panelCss = join(process.cwd(), "src/components/LlmConfigPanel.css");
const appCssForLlmPanel = join(process.cwd(), "src/App.css");

const requiredSelectors = [
  ".hifi-settings-page",
  ".hifi-settings-dialog-body",
  ".hifi-settings-page-header",
  ".hifi-settings-page-icon",
  ".hifi-settings-page-title",
  ".hifi-settings-page-desc",
  ".hifi-settings-body",
  ".hifi-settings-section-head",
  ".hifi-settings-section-icon",
  ".hifi-settings-section-title",
  ".hifi-settings-section-subtitle",
  ".hifi-settings-field",
  ".hifi-settings-label",
  ".hifi-settings-hint",
  ".hifi-settings-input",
  ".hifi-settings-input-compact",
  ".hifi-settings-eye-btn",
  ".hifi-model-chips",
  ".hifi-model-chip",
  ".hifi-model-chip.active",
  ".hifi-settings-divider",
  ".hifi-settings-status-list",
  ".hifi-settings-status-row",
  ".hifi-settings-mono",
  ".hifi-settings-saved",
  ".hifi-settings-footer",
  ".hifi-settings-secret-field",
  ".hifi-settings-input--secret",
  ".hifi-settings-input--mono",
  ".hifi-settings-input--custom-model",
  ".hifi-settings-status-badge",
  ".hifi-settings-status-value",
  ".hifi-settings-submit-btn",
  ".hifi-settings-validation",
];

describe("LlmConfigPanel form foundation", () => {
  it("uses react-hook-form and zod while keeping visual classes local", () => {
    const source = readFileSync(panelSource, "utf8");
    const css = readFileSync(panelCss, "utf8");
    const appCss = readFileSync(appCssForLlmPanel, "utf8");

    expect(source).toContain('from "react-hook-form"');
    expect(source).toContain('from "@hookform/resolvers/zod"');
    expect(source).toContain('from "zod"');
    expect(source).toContain("useForm<ApiConfig>");
    expect(source).toContain("useWatch");
    expect(source).not.toContain("watch,");
    expect(source).not.toContain("watch();");
    expect(source).toContain("zodResolver");
    expect(source).toContain("llmConfigSchema");
    expect(source).toContain('import "./LlmConfigPanel.css"');
    expect(source).not.toMatch(/\b(pr-\d|mt-\d|gap-\d(?:\.\d)?|font-mono|truncate|max-w-\[|text-\[)/);
    for (const selector of requiredSelectors) {
      expect(css).toContain(selector);
    }
    expect(appCss).not.toMatch(/\.hifi-settings-|\.hifi-model-|\.hifi-shortcuts-/);
  });
});

}

// Source: desktop/src/components/__tests__/ToastRadix.styles.test.ts
{

const toastSource = join(process.cwd(), "src/components/Toast.tsx");
const toastCss = join(process.cwd(), "src/components/Toast.css");
const packageJson = join(process.cwd(), "package.json");

const requiredSelectors = [
  ".dbfox-toast-viewport",
  ".dbfox-toast-root",
  ".dbfox-toast-root--success",
  ".dbfox-toast-root--error",
  ".dbfox-toast-root--warning",
  ".dbfox-toast-root--info",
  ".dbfox-toast-icon",
  ".dbfox-toast-message",
  ".dbfox-toast-close",
];

describe("Toast Radix foundation", () => {
  it("wraps Radix Toast while keeping DBFox presentation in local CSS", () => {
    const source = readFileSync(toastSource, "utf8");
    const css = readFileSync(toastCss, "utf8");
    const pkg = readFileSync(packageJson, "utf8");

    expect(pkg).toContain('"@radix-ui/react-toast"');
    expect(source).toContain('from "@radix-ui/react-toast"');
    expect(source).toContain('import "./Toast.css"');
    expect(source).not.toContain('from "gsap"');
    expect(source).not.toContain("style={{");
    expect(source).not.toContain("onMouseEnter");
    expect(source).not.toContain("onMouseLeave");
    for (const selector of requiredSelectors) {
      expect(css).toContain(selector);
    }
  });
});

}

// Source: desktop/src/components/data-grid/__tests__/DataGridCell.styles.test.ts
{

const dataGridCellSource = join(process.cwd(), "src/components/data-grid/DataGridCell.tsx");
const cellValuePreviewSource = join(process.cwd(), "src/components/data-grid/CellValuePreview.tsx");
const cellValuePreviewCss = join(process.cwd(), "src/components/data-grid/CellValuePreview.css");
const dataTableSource = join(process.cwd(), "src/components/DataTable.tsx");

describe("DataGridCell preview foundation", () => {
  it("delegates long content positioning to the shared DBFox HoverCard preview", () => {
    const source = readFileSync(dataGridCellSource, "utf8");
    const previewSource = readFileSync(cellValuePreviewSource, "utf8");

    expect(source).toContain("CellValuePreview");
    expect(source).not.toContain("HoverCard");
    expect(previewSource).toContain("HoverCard");
    expect(previewSource).toContain("HoverCardContent");
    expect(previewSource).toContain("HoverCardTrigger");
    expect(source).not.toContain("onPreviewChange");
    expect(source).not.toContain("getBoundingClientRect");
    expect(source).not.toContain("DOMRect");
    expect(source).not.toContain("style={{");
    expect(previewSource).not.toContain("style={{");
  });

  it("removes the parent-level fixed preview overlay and keeps preview styling local", () => {
    const tableSource = readFileSync(dataTableSource, "utf8");
    const css = readFileSync(cellValuePreviewCss, "utf8");

    expect(tableSource).not.toContain("const [preview");
    expect(tableSource).not.toContain("setPreview");
    expect(tableSource).not.toContain("window.innerWidth");
    expect(tableSource).not.toContain("data-grid-preview animate-fade-in");

    expect(css).toContain(".dbfox-cell-preview-trigger");
    expect(css).toContain(".dbfox-cell-preview-card");
    expect(css).toContain(".dbfox-cell-preview-header");
    expect(css).toContain(".dbfox-cell-preview-body");
    expect(css).toContain(".dbfox-cell-preview-footer");
    expect(css).not.toContain("position: fixed");
  });
});

}

// Source: desktop/src/components/data-grid/__tests__/DataGridColumnMenu.styles.test.ts
{

const dataTableSource = join(process.cwd(), "src/components/DataTable.tsx");
const headerCellSource = join(process.cwd(), "src/components/data-grid/DataGridHeaderCell.tsx");
const columnMenuSource = join(process.cwd(), "src/components/data-grid/DataGridColumnMenu.tsx");
const dataGridCss = join(process.cwd(), "src/components/data-grid/data-grid.css");

describe("DataGrid column menu foundation", () => {
  it("uses DBFox DropdownMenu instead of parent-managed menu state", () => {
    const tableSource = readFileSync(dataTableSource, "utf8");
    const headerSource = readFileSync(headerCellSource, "utf8");
    const menuSource = readFileSync(columnMenuSource, "utf8");

    expect(headerSource).toContain("DropdownMenu");
    expect(headerSource).toContain("DropdownMenuTrigger");
    expect(headerSource).toContain("Tooltip");
    expect(headerSource).toContain("TooltipTrigger");
    expect(headerSource).toContain("TooltipContent");
    expect(headerSource).toContain("列操作");
    expect(menuSource).toContain("DropdownMenuContent");
    expect(menuSource).toContain("DropdownMenuItem");
    expect(menuSource).not.toContain('className="data-grid-menu" onClick');

    expect(tableSource).not.toContain("openColumnMenu");
    expect(tableSource).not.toContain("setOpenColumnMenu");
    expect(headerSource).not.toContain("menuOpen");
    expect(headerSource).not.toContain("onToggleMenu");
  });

  it("lets Radix own overlay positioning while DBFox owns menu appearance", () => {
    const css = readFileSync(dataGridCss, "utf8");

    expect(css).toContain(".data-grid-menu");
    expect(css).toContain(".data-grid-menu-item");
    expect(css).not.toContain("position: absolute");
    expect(css).not.toContain("top: 30px");
    expect(css).not.toContain("right: 0");
  });
});

}

// Source: desktop/src/components/data-grid/__tests__/DataGridContextMenu.styles.test.ts
{

const dataTableSource = join(process.cwd(), "src/components/DataTable.tsx");
const contextMenuSource = join(process.cwd(), "src/components/data-grid/DataGridContextMenu.tsx");
const typesSource = join(process.cwd(), "src/components/data-grid/types.ts");
const dataGridCss = join(process.cwd(), "src/components/data-grid/data-grid.css");

describe("DataGrid context menu foundation", () => {
  it("uses DBFox ContextMenu instead of parent-managed x/y state", () => {
    const tableSource = readFileSync(dataTableSource, "utf8");
    const menuSource = readFileSync(contextMenuSource, "utf8");
    const types = readFileSync(typesSource, "utf8");

    expect(tableSource).toContain("ContextMenu");
    expect(tableSource).toContain("ContextMenuTrigger");
    expect(menuSource).toContain("ContextMenuContent");
    expect(menuSource).toContain("ContextMenuItem");
    expect(menuSource).toContain("ContextMenuSeparator");

    expect(tableSource).not.toContain("setContextMenu");
    expect(tableSource).not.toContain("contextMenu");
    expect(tableSource).not.toContain("clientX");
    expect(tableSource).not.toContain("clientY");
    expect(types).not.toContain("DataGridContextMenuState");
  });

  it("removes fixed backdrop positioning while keeping DBFox menu styling local", () => {
    const menuSource = readFileSync(contextMenuSource, "utf8");
    const css = readFileSync(dataGridCss, "utf8");
    const contextMenuCss = css.match(/\.data-grid-context-menu\s*\{[\s\S]*?\}/)?.[0] ?? "";

    expect(menuSource).not.toContain('style={{ position: "fixed"');
    expect(menuSource).not.toContain("style={{ left:");
    expect(menuSource).not.toContain("onClose");
    expect(contextMenuCss).toContain(".data-grid-context-menu");
    expect(contextMenuCss).not.toContain("position: fixed");
    expect(contextMenuCss).not.toContain("z-index: 3000");
  });
});

}

// Source: desktop/src/components/data-grid/__tests__/DataTableTanStackCore.styles.test.ts
{

const dataTableSource = join(process.cwd(), "src/components/DataTable.tsx");
const dataGridCss = join(process.cwd(), "src/components/data-grid/data-grid.css");
const packageJson = join(process.cwd(), "package.json");

describe("DataTable TanStack core", () => {
  it("uses TanStack Table for sorting, filtering, column visibility, and row modeling", () => {
    const source = readFileSync(dataTableSource, "utf8");
    const manifest = readFileSync(packageJson, "utf8");

    expect(manifest).toContain('"@tanstack/react-table"');
    expect(source).toContain('from "@tanstack/react-table"');
    expect(source).toContain("useReactTable");
    expect(source).toContain("getCoreRowModel");
    expect(source).toContain("getFilteredRowModel");
    expect(source).toContain("getSortedRowModel");
    expect(source).toContain("table.getRowModel().rows");
    expect(source).not.toContain("useDataTableView");
    expect(source).not.toContain("visibleRows.map");
  });

  it("keeps the data-grid visual frame polished with local CSS boundaries", () => {
    const css = readFileSync(dataGridCss, "utf8");

    expect(css).toMatch(/\.data-grid-root\s*{[^}]*border:\s*1px solid var\(--border-light\);/s);
    expect(css).toMatch(/\.data-grid-root\s*{[^}]*border-radius:\s*8px;/s);
    expect(css).toMatch(/\.data-grid-root\s*{[^}]*box-shadow:/s);
    expect(css).toMatch(/\.data-grid-table\s*{[^}]*border-collapse:\s*separate;/s);
    expect(css).toMatch(/\.data-grid-table\s*{[^}]*border-spacing:\s*0;/s);
  });
});

}

// Source: desktop/src/components/data-grid/__tests__/DataTableVirtualization.styles.test.ts
{

const dataTableSource = join(process.cwd(), "src/components/DataTable.tsx");
const dataGridCss = join(process.cwd(), "src/components/data-grid/data-grid.css");
const packageJson = join(process.cwd(), "package.json");

describe("DataTable virtualization foundation", () => {
  it("uses TanStack Virtual for large result rendering without handwritten row-window math", () => {
    const source = readFileSync(dataTableSource, "utf8");
    const css = readFileSync(dataGridCss, "utf8");
    const manifest = readFileSync(packageJson, "utf8");

    expect(manifest).toContain('"@tanstack/react-virtual"');
    expect(source).toContain('from "@tanstack/react-virtual"');
    expect(source).toContain("useVirtualizer");
    expect(source).toContain("rowVirtualizer");
    expect(source).toContain("virtualRows.map");
    expect(source).not.toContain("visibleRows.map((row, rowIndex)");
    expect(css).toContain(".data-grid-virtual-spacer");
    expect(css).toContain(".data-grid-virtual-spacer-cell");
  });
});

}

// Source: desktop/src/components/ui/__tests__/badge.styles.test.ts
{

const badgeSource = join(process.cwd(), "src/components/ui/badge.tsx");
const badgeCss = join(process.cwd(), "src/components/ui/badge.css");

const utilityClassPattern =
  /\b(?:inline-flex|items-|rounded|px-\d|py-\d|text-\[|font-|transition-|focus:|focus-visible:|ring-|bg-\[|border(?:\b|-\[))/;

const requiredSelectors = [
  ".dbfox-badge",
  ".dbfox-badge--default",
  ".dbfox-badge--secondary",
  ".dbfox-badge--success",
  ".dbfox-badge--warning",
  ".dbfox-badge--destructive",
  ".dbfox-badge--outline",
];

describe("Badge primitive styles", () => {
  it("keeps Badge presentation in local CSS while preserving the variants helper", () => {
    const source = readFileSync(badgeSource, "utf8");
    const css = readFileSync(badgeCss, "utf8");

    expect(source).toContain('import "./badge.css"');
    expect(source).toContain("function badgeVariants");
    expect(source).not.toContain("class-variance-authority");
    expect(source).not.toMatch(utilityClassPattern);
    for (const selector of requiredSelectors) {
      expect(css).toContain(selector);
    }
  });
});

}

// Source: desktop/src/components/ui/__tests__/base-primitives.styles.test.ts
{

const uiDir = join(process.cwd(), "src/components/ui");

const utilityClassPattern =
  /\b(?:inline-flex|flex|grid|items-|justify-|gap-\d|px-\d|py-\d|p-\d|m-\d|mt-\d|min-h-|h-\d|w-\d|size-|rounded|border(?:\b|-\[)|bg-\[|text-\[|font-|leading-|transition-|duration-|ease-|focus-visible:|hover:|disabled:|active:|animate-spin|whitespace-|shrink-0|max-w-|overflow-|opacity-|cursor-|\[&_svg\])/;

const primitiveStyleContracts = [
  {
    sourcePath: join(uiDir, "button.tsx"),
    cssPath: join(uiDir, "button.css"),
    importStatement: 'import "./button.css"',
    forbidden: ["class-variance-authority", "bg-[", "text-[", "px-", "[&_svg]"],
    selectors: [
      ".dbfox-button",
      ".dbfox-button--default",
      ".dbfox-button--destructive",
      ".dbfox-button--outline",
      ".dbfox-button--secondary",
      ".dbfox-button--ghost",
      ".dbfox-button--link",
      ".dbfox-button--sm",
      ".dbfox-button--lg",
      ".dbfox-button--icon",
      ".dbfox-button--icon-sm",
    ],
  },
  {
    sourcePath: join(uiDir, "input.tsx"),
    cssPath: join(uiDir, "input.css"),
    importStatement: 'import "./input.css"',
    forbidden: ["bg-transparent", "focus-visible:", "placeholder:", "file:"],
    selectors: [".dbfox-input"],
  },
  {
    sourcePath: join(uiDir, "label.tsx"),
    cssPath: join(uiDir, "label.css"),
    importStatement: 'import "./label.css"',
    forbidden: ["class-variance-authority", "peer-disabled:", "leading-none"],
    selectors: [".dbfox-label"],
  },
  {
    sourcePath: join(uiDir, "state.tsx"),
    cssPath: join(uiDir, "state.css"),
    importStatement: 'import "./state.css"',
    forbidden: ["bg-[", "border-[", "animate-spin", "max-w-md", "mt-"],
    selectors: [
      ".dbfox-empty-state",
      ".dbfox-empty-state__icon",
      ".dbfox-empty-state__title",
      ".dbfox-empty-state__description",
      ".dbfox-empty-state__action",
      ".dbfox-error-state",
      ".dbfox-error-state__icon",
      ".dbfox-error-state__content",
      ".dbfox-error-state__title",
      ".dbfox-error-state__description",
      ".dbfox-error-state__retry",
      ".dbfox-loading-state",
      ".dbfox-loading-state__icon",
    ],
  },
];

describe("base UI primitive styles", () => {
  it("keeps base primitive presentation in local CSS files", () => {
    for (const contract of primitiveStyleContracts) {
      const source = readFileSync(contract.sourcePath, "utf8");
      const css = readFileSync(contract.cssPath, "utf8");

      expect(source).toContain(contract.importStatement);
      expect(source).not.toMatch(utilityClassPattern);
      for (const forbidden of contract.forbidden) {
        expect(source).not.toContain(forbidden);
      }
      for (const selector of contract.selectors) {
        expect(css).toContain(selector);
      }
    }
  });
});

}

// Source: desktop/src/components/ui/__tests__/command.styles.test.ts
{

const commandSource = join(process.cwd(), "src/components/ui/command.tsx");
const commandCss = join(process.cwd(), "src/components/ui/command.css");

const commandSelectors = [
  ".dbfox-command-panel",
  ".dbfox-command-search",
  ".dbfox-command-search-icon",
  ".dbfox-command-input",
  ".dbfox-command-kbd",
  ".dbfox-command-list",
  ".dbfox-command-empty",
  ".dbfox-command-group",
  ".dbfox-command-category",
  ".dbfox-command-item",
  ".dbfox-command-item-icon",
  ".dbfox-command-item-label",
];

describe("DBFox Command primitive styles", () => {
  it("wraps cmdk with local DBFox classes", () => {
    const source = readFileSync(commandSource, "utf8");
    const css = readFileSync(commandCss, "utf8");

    expect(source).toContain('from "cmdk"');
    expect(source).toContain('import "./command.css"');
    expect(source).toContain('"dbfox-command-panel"');
    expect(source).toContain('"dbfox-command-input"');
    expect(source).toContain('"dbfox-command-item"');
    expect(source).not.toContain("cmdk-command");
    for (const selector of commandSelectors) {
      expect(css).toContain(selector);
    }
  });
});

}

// Source: desktop/src/components/ui/__tests__/context-menu.styles.test.ts
{

const contextMenuSource = join(process.cwd(), "src/components/ui/context-menu.tsx");
const contextMenuCss = join(process.cwd(), "src/components/ui/context-menu.css");

describe("DBFox ContextMenu primitive styles", () => {
  it("wraps Radix ContextMenu with local DBFox classes", () => {
    const source = readFileSync(contextMenuSource, "utf8");
    const css = readFileSync(contextMenuCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-context-menu"');
    expect(source).toContain('import "./context-menu.css"');
    expect(source).toContain('"dbfox-context-menu-content"');
    expect(source).toContain('"dbfox-context-menu-item"');
    expect(source).toContain('"dbfox-context-menu-separator"');
    expect(source).not.toContain("rounded-[var(--radius-md)]");
    expect(source).not.toContain("data-[state=open]:animate-in");
    expect(source).not.toContain("focus:bg-[hsl(var(--accent))]");
    expect(css).toContain(".dbfox-context-menu-content");
    expect(css).toContain(".dbfox-context-menu-item");
    expect(css).toContain(".dbfox-context-menu-separator");
  });
});

}

// Source: desktop/src/components/ui/__tests__/dialog.styles.test.ts
{

const dialogSource = join(process.cwd(), "src/components/ui/dialog.tsx");
const dialogCss = join(process.cwd(), "src/components/ui/dialog.css");

describe("DBFox Dialog primitive styles", () => {
  it("wraps Radix Dialog with local DBFox classes", () => {
    const source = readFileSync(dialogSource, "utf8");
    const css = readFileSync(dialogCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-dialog"');
    expect(source).toContain('import "./dialog.css"');
    expect(source).toContain('"dbfox-dialog-overlay"');
    expect(source).toContain('"dbfox-dialog-content"');
    expect(source).toContain('"dbfox-dialog-close"');
    expect(source).toContain('"dbfox-dialog-header"');
    expect(source).toContain('"dbfox-dialog-footer"');
    expect(source).toContain('"dbfox-dialog-title"');
    expect(source).toContain('"dbfox-dialog-description"');
    expect(source).not.toContain("fixed inset-0");
    expect(source).not.toContain("left-[50%]");
    expect(source).not.toContain("shadow-panel-elevated");
    expect(source).not.toContain("absolute right-4");
    expect(source).not.toContain("space-y-1.5");
    expect(source).not.toContain("sm:flex-row");
    expect(css).toContain(".dbfox-dialog-overlay");
    expect(css).toContain(".dbfox-dialog-content");
    expect(css).toContain(".dbfox-dialog-close");
    expect(css).toContain(".dbfox-dialog-title");
    expect(css).toContain(".dbfox-dialog-description");
  });
});

}

// Source: desktop/src/components/ui/__tests__/dropdown-menu.styles.test.ts
{

const dropdownMenuSource = join(process.cwd(), "src/components/ui/dropdown-menu.tsx");
const dropdownMenuCss = join(process.cwd(), "src/components/ui/dropdown-menu.css");

describe("DBFox DropdownMenu primitive styles", () => {
  it("wraps Radix DropdownMenu with local DBFox classes", () => {
    const source = readFileSync(dropdownMenuSource, "utf8");
    const css = readFileSync(dropdownMenuCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-dropdown-menu"');
    expect(source).toContain('import "./dropdown-menu.css"');
    expect(source).toContain('"dbfox-dropdown-menu-content"');
    expect(source).toContain('"dbfox-dropdown-menu-item"');
    expect(source).toContain('"dbfox-dropdown-menu-separator"');
    expect(source).not.toContain("rounded-[var(--radius-md)]");
    expect(source).not.toContain("data-[state=open]:animate-in");
    expect(source).not.toContain("focus:bg-[hsl(var(--accent))]");
    expect(css).toContain(".dbfox-dropdown-menu-content");
    expect(css).toContain(".dbfox-dropdown-menu-item");
    expect(css).toContain(".dbfox-dropdown-menu-separator");
  });
});

}

// Source: desktop/src/components/ui/__tests__/hover-card.styles.test.ts
{

const hoverCardSource = join(process.cwd(), "src/components/ui/hover-card.tsx");
const hoverCardCss = join(process.cwd(), "src/components/ui/hover-card.css");

describe("DBFox HoverCard primitive styles", () => {
  it("wraps Radix HoverCard with local DBFox classes", () => {
    const source = readFileSync(hoverCardSource, "utf8");
    const css = readFileSync(hoverCardCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-hover-card"');
    expect(source).toContain('import "./hover-card.css"');
    expect(source).toContain('"dbfox-hover-card-content"');
    expect(source).toContain('"dbfox-hover-card-arrow"');
    expect(source).not.toContain("min-w-64");
    expect(source).not.toContain("rounded-[var(--radius-md)]");
    expect(source).not.toContain("data-[state=open]:animate-in");
    expect(css).toContain(".dbfox-hover-card-content");
    expect(css).toContain(".dbfox-hover-card-arrow");
  });
});

}

// Source: desktop/src/components/ui/__tests__/panel-toolbar.styles.test.ts
{

const uiDir = join(process.cwd(), "src/components/ui");

const utilityClassPattern =
  /\b(?:flex|grid|items-|justify-|gap-\d|min-h-|min-w-|shrink-0|flex-\d|rounded|border(?:\b|-\[)|bg-\[|text-\[|font-|leading-|truncate|p-\d|px-\d|py-\d|m-\d)/;

const contracts = [
  {
    sourcePath: join(uiDir, "panel.tsx"),
    cssPath: join(uiDir, "panel.css"),
    importStatement: 'import "./panel.css"',
    selectors: [
      ".dbfox-panel",
      ".dbfox-panel__header",
      ".dbfox-panel__title",
      ".dbfox-panel__description",
      ".dbfox-panel__body",
      ".dbfox-panel__footer",
    ],
  },
  {
    sourcePath: join(uiDir, "toolbar.tsx"),
    cssPath: join(uiDir, "toolbar.css"),
    importStatement: 'import "./toolbar.css"',
    selectors: [
      ".dbfox-toolbar",
      ".dbfox-toolbar__title",
      ".dbfox-toolbar__group",
    ],
  },
];

describe("Panel and Toolbar primitive styles", () => {
  it("keeps foundational layout and typography in local CSS", () => {
    for (const contract of contracts) {
      const source = readFileSync(contract.sourcePath, "utf8");
      const css = readFileSync(contract.cssPath, "utf8");

      expect(source).toContain(contract.importStatement);
      expect(source).not.toMatch(utilityClassPattern);
      for (const selector of contract.selectors) {
        expect(css).toContain(selector);
      }
    }
  });
});

}

// Source: desktop/src/components/ui/__tests__/popover.styles.test.ts
{

const popoverSource = join(process.cwd(), "src/components/ui/popover.tsx");
const popoverCss = join(process.cwd(), "src/components/ui/popover.css");

describe("DBFox Popover primitive styles", () => {
  it("wraps Radix Popover with local DBFox classes", () => {
    const source = readFileSync(popoverSource, "utf8");
    const css = readFileSync(popoverCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-popover"');
    expect(source).toContain('import "./popover.css"');
    expect(source).toContain('"dbfox-popover-content"');
    expect(source).toContain('"dbfox-popover-arrow"');
    expect(source).not.toContain("min-w-64");
    expect(source).not.toContain("rounded-[var(--radius-md)]");
    expect(source).not.toContain("data-[state=open]:animate-in");
    expect(css).toContain(".dbfox-popover-content");
    expect(css).toContain(".dbfox-popover-arrow");
  });
});

}

// Source: desktop/src/components/ui/__tests__/resizable.styles.test.ts
{

const resizableSource = join(process.cwd(), "src/components/ui/resizable.tsx");
const resizableCss = join(process.cwd(), "src/components/ui/resizable.css");

const requiredSelectors = [
  ".dbfox-resizable-panel-group",
  ".dbfox-resizable-panel",
  ".dbfox-resizable-handle",
  ".dbfox-resizable-handle__rail",
  ".dbfox-resizable-handle__grip",
];

describe("DBFox Resizable primitive styles", () => {
  it("wraps react-resizable-panels with local DBFox classes", () => {
    const source = readFileSync(resizableSource, "utf8");
    const css = readFileSync(resizableCss, "utf8");

    expect(source).toContain('from "react-resizable-panels"');
    expect(source).toContain('import "./resizable.css"');
    expect(source).toContain('"dbfox-resizable-panel-group"');
    expect(source).toContain('"dbfox-resizable-panel"');
    expect(source).toContain('"dbfox-resizable-handle"');
    for (const selector of requiredSelectors) {
      expect(css).toContain(selector);
    }
  });
});

}

// Source: desktop/src/components/ui/__tests__/scroll-area.styles.test.ts
{

const scrollAreaSource = join(process.cwd(), "src/components/ui/scroll-area.tsx");
const scrollAreaCss = join(process.cwd(), "src/components/ui/scroll-area.css");

describe("DBFox ScrollArea primitive styles", () => {
  it("wraps Radix ScrollArea with local DBFox classes", () => {
    const source = readFileSync(scrollAreaSource, "utf8");
    const css = readFileSync(scrollAreaCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-scroll-area"');
    expect(source).toContain('import "./scroll-area.css"');
    expect(source).toContain('"dbfox-scroll-area"');
    expect(source).toContain('"dbfox-scroll-area-viewport"');
    expect(source).toContain('"dbfox-scroll-area-scrollbar"');
    expect(source).toContain('"dbfox-scroll-area-thumb"');
    expect(source).not.toContain("h-full w-full");
    expect(source).not.toContain("bg-[hsl(var(--border))]");
    expect(css).toContain(".dbfox-scroll-area");
    expect(css).toContain(".dbfox-scroll-area-viewport");
    expect(css).toContain(".dbfox-scroll-area-scrollbar");
    expect(css).toContain(".dbfox-scroll-area-thumb");
  });
});

}

// Source: desktop/src/components/ui/__tests__/select.styles.test.ts
{

const selectSource = join(process.cwd(), "src/components/ui/select.tsx");
const selectCss = join(process.cwd(), "src/components/ui/select.css");

describe("Select primitive foundation", () => {
  it("wraps Radix Select behind the DBFox Select API", () => {
    const source = readFileSync(selectSource, "utf8");

    expect(source).toContain('from "@radix-ui/react-select"');
    expect(source).toContain("SelectPrimitive.Root");
    expect(source).toContain("SelectPrimitive.Trigger");
    expect(source).toContain("SelectPrimitive.Content");
    expect(source).toContain("SelectPrimitive.Item");
    expect(source).not.toContain("<select");
  });

  it("keeps Select visual styling in local CSS", () => {
    const css = readFileSync(selectCss, "utf8");

    expect(css).toContain(".dbfox-select-trigger");
    expect(css).toContain(".dbfox-select-content");
    expect(css).toContain(".dbfox-select-item");
    expect(css).toContain(".dbfox-select-scroll-button");
  });
});

}

// Source: desktop/src/components/ui/__tests__/tabs.styles.test.ts
{

const tabsSource = join(process.cwd(), "src/components/ui/tabs.tsx");
const tabsCss = join(process.cwd(), "src/components/ui/tabs.css");

describe("DBFox Tabs primitive styles", () => {
  it("wraps Radix Tabs with local DBFox classes", () => {
    const source = readFileSync(tabsSource, "utf8");
    const css = readFileSync(tabsCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-tabs"');
    expect(source).toContain('import "./tabs.css"');
    expect(source).toContain('"dbfox-tabs-list"');
    expect(source).toContain('"dbfox-tabs-trigger"');
    expect(source).toContain('"dbfox-tabs-content"');
    expect(source).not.toContain("inline-flex items-center");
    expect(source).not.toContain("focus-visible:ring-2");
    expect(source).not.toContain("disabled:pointer-events-none");
    expect(source).not.toContain("outline-none");
    expect(css).toContain(".dbfox-tabs-list");
    expect(css).toContain(".dbfox-tabs-trigger");
    expect(css).toContain(".dbfox-tabs-content");
  });
});

}

// Source: desktop/src/components/ui/__tests__/tooltip.styles.test.ts
{

const tooltipSource = join(process.cwd(), "src/components/ui/tooltip.tsx");
const tooltipCss = join(process.cwd(), "src/components/ui/tooltip.css");

describe("DBFox Tooltip primitive styles", () => {
  it("wraps Radix Tooltip behind a local DBFox stylesheet", () => {
    const source = readFileSync(tooltipSource, "utf8");
    const css = readFileSync(tooltipCss, "utf8");

    expect(source).toContain('from "@radix-ui/react-tooltip"');
    expect(source).toContain("TooltipPrimitive.Provider");
    expect(source).toContain("TooltipPrimitive.Content");
    expect(source).toContain('import "./tooltip.css"');
    expect(source).toContain('"dbfox-tooltip-content"');
    expect(source).not.toContain("bg-[hsl(var(--foreground))]");
    expect(source).not.toContain("animate-in");
    expect(css).toContain(".dbfox-tooltip-content");
    expect(css).toContain(".dbfox-tooltip-arrow");
  });
});

}

// Source: desktop/src/features/assistant/__tests__/ContextDrawer.styles.test.ts
{

const sourcePath = join(process.cwd(), "src/features/assistant/ContextDrawer.tsx");
const localCss = join(process.cwd(), "src/features/assistant/ContextDrawer.css");
const appCss = join(process.cwd(), "src/App.css");

const drawerSelectors = [
  ".context-drawer",
  ".context-drawer.is-open",
  ".context-drawer.is-closed",
  ".context-drawer__surface",
  ".context-drawer__header",
  ".context-drawer__title",
  ".context-drawer__icon",
  ".context-drawer__close",
  ".context-drawer__body",
  ".context-drawer__stack",
  ".context-drawer__eyebrow",
  ".context-drawer__empty",
  ".context-drawer__info-list",
  ".context-drawer__info-row",
  ".context-drawer__info-row--long",
  ".context-drawer__info-label",
  ".context-drawer__info-value",
];

const retiredAppSelectors = [
  ".hifi-assistant-panel",
  ".hifi-assistant-header",
  ".hifi-assistant-title",
  ".hifi-ai-badge",
  ".hifi-context-bar",
  ".hifi-context-chips",
  ".hifi-assistant-messages",
  ".hifi-assistant-footer",
  ".hifi-ai-bubble",
  ".hifi-ai-msg-container",
  ".hifi-ai-avatar",
  ".hifi-ai-msg-bubble",
  ".hifi-user-bubble",
  ".hifi-suggest-chip",
  ".hifi-chat-input-wrapper",
  ".hifi-chat-input",
  ".hifi-chat-send-btn",
];

describe("ContextDrawer styles", () => {
  it("keeps assistant drawer styling local without hifi assistant selectors", () => {
    expect(existsSync(localCss)).toBe(true);

    const source = readFileSync(sourcePath, "utf8");
    expect(source).toContain('import "./ContextDrawer.css";');
    expect(source).not.toMatch(/hifi-assistant-(header|title)/);
    expect(source).not.toContain("style=");
    expect(source).not.toMatch(/text-slate|bg-slate|border-slate|flex-1|p-3|gap-1\.5|font-bold/);

    const css = readFileSync(localCss, "utf8");
    for (const selector of drawerSelectors) {
      expect(css).toContain(selector);
    }

    const globalCss = readFileSync(appCss, "utf8");
    for (const selector of retiredAppSelectors) {
      expect(globalCss).not.toContain(selector);
    }
  });
});

}

// Source: desktop/src/features/conversation/__tests__/ConversationHistoryPanel.styles.test.ts
{

const sourcePath = join(process.cwd(), "src/features/conversation/ConversationHistoryPanel.tsx");
const cssPath = join(process.cwd(), "src/features/conversation/ConversationHistoryPanel.css");
const appCssPath = join(process.cwd(), "src/App.css");

const selectors = [
  ".conversation-history",
  ".conversation-history__body",
  ".conversation-history__toolbar",
  ".conversation-history__count",
  ".conversation-history__list",
  ".conversation-history__item",
  ".conversation-history__item--active",
  ".conversation-history__item-head",
  ".conversation-history__title",
  ".conversation-history__preview",
  ".conversation-history__meta",
  ".conversation-history__delete",
];

describe("ConversationHistoryPanel styles", () => {
  it("uses WorkspaceShell and local CSS without Tailwind or global guide chip styles", () => {
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain('import "./ConversationHistoryPanel.css";');
    expect(source).toContain("WorkspaceShell");
    expect(source).toContain("from \"../../components/ui\"");
    expect(source).toContain("<Button");
    expect(source).toContain("<EmptyState");
    for (const token of [
      "hifi-",
      "p-4",
      "flex flex-col",
      "text-slate",
      "bg-white",
      "rounded-xl",
      "hover:",
      "group",
      "line-clamp",
    ]) {
      expect(source).not.toContain(token);
    }

    expect(existsSync(cssPath)).toBe(true);
    const css = readFileSync(cssPath, "utf8");
    for (const selector of selectors) {
      expect(css).toContain(selector);
    }

    const appCss = readFileSync(appCssPath, "utf8");
    expect(appCss).not.toContain("hifi-guide-chip-prod");
  });
});

}

// Source: desktop/src/features/conversation/workspace/__tests__/ConversationWorkspaceSplitPane.styles.test.ts
{

const workspaceSourcePath = join(process.cwd(), "src/features/conversation/workspace/ConversationWorkspace.tsx");
const dockSourcePath = join(process.cwd(), "src/features/conversation/workspace/ArtifactDock.tsx");
const cssPath = join(process.cwd(), "src/features/conversation/workspace/conversationWorkspace.css");

describe("conversation workspace split pane foundation", () => {
  it("delegates artifact split resizing to react-resizable-panels", () => {
    const workspaceSource = readFileSync(workspaceSourcePath, "utf8");
    const dockSource = readFileSync(dockSourcePath, "utf8");

    expect(workspaceSource).toContain('from "react-resizable-panels"');
    expect(workspaceSource).toContain("<PanelGroup");
    expect(workspaceSource).toContain("<PanelResizeHandle");
    expect(workspaceSource).toContain('className="conv-artifact-panel-group"');
    expect(workspaceSource).toContain('className="conv-artifact-main-panel"');
    expect(workspaceSource).toContain('className="conv-artifact-dock-panel"');

    expect(dockSource).not.toContain("PointerEvent");
    expect(dockSource).not.toContain("onPointerDown");
    expect(dockSource).not.toContain("window.addEventListener");
    expect(dockSource).not.toContain("dockWidth");
    expect(dockSource).not.toContain("--conv-artifact-width");
  });

  it("uses percentage split sizes so the artifact dock is not capped to pixels", () => {
    const workspaceSource = readFileSync(workspaceSourcePath, "utf8");

    expect(workspaceSource).toContain('defaultSize="72%"');
    expect(workspaceSource).toContain('minSize="48%"');
    expect(workspaceSource).toContain('defaultSize="28%"');
    expect(workspaceSource).toContain('minSize="22%"');
    expect(workspaceSource).toContain('maxSize="44%"');
    expect(workspaceSource).not.toContain("defaultSize={72}");
    expect(workspaceSource).not.toContain("defaultSize={28}");
    expect(workspaceSource).not.toContain("maxSize={44}");
  });

  it("keeps split pane presentation in local CSS without inline width variables", () => {
    expect(existsSync(cssPath)).toBe(true);
    const css = readFileSync(cssPath, "utf8");

    expect(css).toContain(".conv-artifact-panel-group");
    expect(css).toContain(".conv-artifact-main-panel");
    expect(css).toContain(".conv-artifact-dock-panel");
    expect(css).toContain(".conv-artifact-resizer");
    expect(css).not.toContain("width: var(--conv-artifact-width");
  });

  it("keeps safety SQL dock previews on the shared GitHub Light code surface tokens", () => {
    const css = readFileSync(cssPath, "utf8");
    const safetySqlRule = css.match(/\.conv-dock-safety-sql\s*\{[^}]+\}/)?.[0] ?? "";

    expect(safetySqlRule).toContain("background: var(--sql-code-surface)");
    expect(safetySqlRule).toContain("border: 1px solid var(--sql-code-border)");
  });
});

}

// Source: desktop/src/features/datasource/__tests__/DataSourceTree.styles.test.ts
{

const sourcePath = join(process.cwd(), "src/features/datasource/DataSourceTree.tsx");
const cssPath = join(process.cwd(), "src/features/datasource/DataSourceTree.css");

describe("DataSourceTree mature interaction foundation", () => {
  it("uses DBFox primitives for datasource dropdown, scroll body, and icon hints", () => {
    const source = readFileSync(sourcePath, "utf8");
    const css = readFileSync(cssPath, "utf8");

    expect(source).toContain("DropdownMenu");
    expect(source).toContain("DropdownMenuTrigger");
    expect(source).toContain("DropdownMenuContent");
    expect(source).toContain("DropdownMenuItem");
    expect(source).toContain("ScrollArea");
    expect(source).toContain("Tooltip");
    expect(source).toContain("TooltipTrigger");
    expect(source).toContain("TooltipContent");
    expect(source).not.toContain("dbDropdownOpen");
    expect(source).not.toContain("dbDropdownRef");
    expect(source).not.toContain("document.addEventListener");
    expect(source).not.toContain('style={{ display: "flex", alignItems: "center" }}');
    expect(source).not.toContain("cursor-pointer");
    expect(css).toContain(".ds-tree-scroll-area");
    expect(css).toContain(".ds-db-dropdown");
    expect(css).toContain(".ds-tree-status");
  });
});

}

// Source: desktop/src/features/datasource-management/__tests__/DataSourceManagement.styles.test.ts
{

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
    expect(formSource).toContain("useWatch");
    expect(formSource).not.toContain("watch,");
    expect(formSource).not.toContain("watch();");
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

}

// Source: desktop/src/features/workspace/__tests__/MultiTableWorkspace.styles.test.ts
{

const sourcePath = join(process.cwd(), "src/features/workspace/MultiTableWorkspace.tsx");
const cssPath = join(process.cwd(), "src/features/workspace/MultiTableWorkspace.css");
const appCssPath = join(process.cwd(), "src/App.css");

const selectors = [
  ".multi-table-workspace",
  ".multi-table-workspace__summary",
  ".multi-table-workspace__summary-icon",
  ".multi-table-workspace__summary-title",
  ".multi-table-workspace__summary-copy",
  ".multi-table-workspace__actions",
  ".multi-table-workspace__action",
  ".multi-table-workspace__action-title",
  ".multi-table-workspace__action-copy",
  ".multi-table-workspace__prompt",
  ".multi-table-workspace__prompt-title",
  ".multi-table-workspace__prompt-row",
];

describe("MultiTableWorkspace styles", () => {
  it("uses the workspace shell, shared controls, and local CSS without Tailwind or App.css business styles", () => {
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain('import "./MultiTableWorkspace.css";');
    expect(source).toContain("WorkspaceShell");
    expect(source).toContain("from \"../../components/ui\"");
    for (const primitive of ["Button", "Input", "EmptyState"]) {
      expect(source).toContain(`<${primitive}`);
    }
    expect(source).not.toMatch(/hifi-|bg-|border-|rounded-|grid-cols-|text-|flex-|gap-|p-|mt-|mb-|opacity-/);

    expect(existsSync(cssPath)).toBe(true);
    const localCss = readFileSync(cssPath, "utf8");
    for (const selector of selectors) {
      expect(localCss).toContain(selector);
    }

    const appCss = readFileSync(appCssPath, "utf8");
    expect(appCss).not.toContain("hifi-multi-table-workspace");
  });
});

}

// Source: desktop/src/features/workspace/__tests__/SmartQueryHome.styles.test.ts
{

const smartQueryHomeSource = join(process.cwd(), "src/features/workspace/SmartQueryHome.tsx");
const smartQueryHeroSource = join(process.cwd(), "src/features/workspace/smartQuery/SmartQueryHero.tsx");
const askInputSource = join(process.cwd(), "src/features/workspace/smartQuery/AskInputBox.tsx");
const localCss = join(process.cwd(), "src/features/workspace/SmartQueryHome.css");
const appCss = join(process.cwd(), "src/App.css");

const localSelectors = [
  ".smart-query-home",
  ".smart-query-home__content",
  ".smart-query-hero",
  ".smart-query-hero__fox",
  ".smart-query-hero__title",
  ".smart-query-gradient-text",
  ".smart-query-hero__subtitle",
  ".smart-query-hero__pattern",
  ".ask-input",
  ".ask-input__textarea",
  ".ask-input__textarea:focus",
  ".ask-input__send",
];

const retiredAppSelectors = [
  ".hifi-query-home",
  ".hifi-query-home-content",
  ".hifi-hero",
  ".hifi-hero-fox",
  ".hifi-hero-title",
  ".hifi-gradient-text",
  ".hifi-hero-subtitle",
  ".hifi-hero-pattern",
  ".hifi-ask-input-container",
  ".hifi-ask-input",
  ".hifi-ask-send-btn",
  ".hifi-section-header",
  ".hifi-text-btn",
  ".hifi-recommend-grid",
  ".hifi-recommend-card",
  ".hifi-recommend-icon",
  ".hifi-recommend-text",
  ".hifi-tag",
  ".hifi-recent-tabs",
  ".hifi-recent-tab",
  ".hifi-recent-grid",
  ".hifi-recent-card",
  ".hifi-recent-name",
  ".hifi-recent-desc",
];

describe("SmartQueryHome styles", () => {
  it("keeps smart-query home, hero, and input styles local", () => {
    expect(existsSync(localCss)).toBe(true);

    const css = readFileSync(localCss, "utf8");
    for (const selector of localSelectors) {
      expect(css).toContain(selector);
    }

    const sources = [
      readFileSync(smartQueryHomeSource, "utf8"),
      readFileSync(smartQueryHeroSource, "utf8"),
      readFileSync(askInputSource, "utf8"),
    ];

    for (const source of sources) {
      expect(source).toContain("SmartQueryHome.css");
      expect(source).not.toContain("style=");
      expect(source).not.toMatch(/hifi-query-home|hifi-hero|hifi-gradient-text|hifi-ask-input|hifi-tab-pane/);
    }

    const askInput = readFileSync(askInputSource, "utf8");
    expect(askInput).toContain('from "../../../components/ui";');
    expect(askInput).toContain("<Button");
    expect(askInput).not.toMatch(/<button\b/);
  });

  it("removes migrated and unused smart-query business selectors from App.css", () => {
    const globalCss = readFileSync(appCss, "utf8");
    for (const selector of retiredAppSelectors) {
      expect(globalCss).not.toContain(selector);
    }
  });
});

}

// Source: desktop/src/features/workspace/__tests__/SqlConsoleWorkspace.styles.test.ts
{

const sourcePath = join(process.cwd(), "src/features/workspace/SqlConsoleWorkspace.tsx");
const localCss = join(process.cwd(), "src/features/workspace/SqlConsoleWorkspace.css");
const appCss = join(process.cwd(), "src/App.css");

const localSelectors = [
  ".hifi-sql-workspace",
  ".sql-console-toolbar",
  ".sql-console-action-icon",
  ".sql-console-datasource-label",
  ".sql-console-selection-meta",
  ".sql-console",
  ".sql-console-scroll",
  ".sql-console-status",
  ".sql-console-status.is-warning",
  ".sql-console-input-stack",
  ".sql-console-highlight",
  ".sql-console-input",
  ".sql-console-statement",
  ".sql-console-statement--read",
  ".sql-console-statement--write",
  ".sql-console-statement--ddl",
  ".sql-console-token-keyword",
  ".sql-console-token-function",
  ".sql-console-token-string",
  ".sql-console-token-number",
  ".sql-console-token-comment",
  ".sql-console-info",
  ".sql-console-info.warn",
  ".sql-console-stmt",
  ".sql-console-prompt-label",
  ".sql-console-sql",
  ".sql-console-running",
  ".sql-console-error",
  ".sql-console-result",
  ".sql-console-result-meta",
  ".sql-console-table-wrap",
  ".sql-console-table",
  ".sql-console-null",
  ".sql-console-empty",
  ".sql-console-prompt",
];

describe("SqlConsoleWorkspace styles", () => {
  it("keeps SQL console styling local instead of in App.css", () => {
    expect(existsSync(localCss)).toBe(true);

    const css = readFileSync(localCss, "utf8");
    for (const selector of localSelectors) {
      expect(css).toContain(selector);
    }

    const source = readFileSync(sourcePath, "utf8");
    expect(source).toContain('import "./SqlConsoleWorkspace.css";');
    expect(source).not.toContain("h-full");
    expect(source).not.toContain("overflow-hidden");
    expect(source).not.toContain("border-0");
    expect(source).not.toContain("bg-transparent");
    expect(source).not.toContain("size-3.5");
    expect(source).not.toContain("SqlEditor");
    expect(source).toContain("<textarea");

    const globalCss = readFileSync(appCss, "utf8");
    expect(globalCss).not.toMatch(/\.hifi-sql-workspace|\.sql-console/);
  });

  it("does not draw a boxed editor surface in the terminal prompt", () => {
    const css = readFileSync(localCss, "utf8");

    expect(css).not.toContain(".sql-console-editor-inline");
    expect(css).not.toContain("height: 188px");
    expect(css).toMatch(/\.sql-console-input\s*{[\s\S]*?background:\s*transparent;/);
    expect(css).toMatch(/\.sql-console-input\s*{[\s\S]*?border:\s*0;/);
  });

  it("renders syntax highlighting as a transparent overlay behind the textarea", () => {
    const css = readFileSync(localCss, "utf8");
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain('aria-label="SQL 高亮预览"');
    expect(source).toContain("renderSqlConsoleHighlight");
    expect(css).toMatch(/\.sql-console-input\s*{[\s\S]*?color:\s*transparent;/);
    expect(css).toMatch(/\.sql-console-input\s*{[\s\S]*?caret-color:\s*#34d399;/);
    expect(css).toMatch(/\.sql-console-highlight\s*{[\s\S]*?pointer-events:\s*none;/);
    expect(css).toMatch(/\.sql-console-token-keyword\s*{[\s\S]*?color:\s*#93c5fd;/);
    expect(css).toMatch(/\.sql-console-token-string\s*{[\s\S]*?color:\s*#86efac;/);
    expect(css).toMatch(/\.sql-console-token-number\s*{[\s\S]*?color:\s*#fdba74;/);
  });
});

}

// Source: desktop/src/features/workspace/__tests__/WorkspaceTabs.styles.test.ts
{

const sourcePath = join(process.cwd(), "src/features/workspace/WorkspaceTabs.tsx");
const localCss = join(process.cwd(), "src/features/workspace/WorkspaceTabs.css");
const appCss = join(process.cwd(), "src/App.css");

const localSelectors = [
  ".workspace-tabs",
  ".workspace-tabs__root",
  ".workspace-tabs__scroll",
  ".workspace-tab",
  ".workspace-tab.is-active",
  ".workspace-tab__main",
  ".workspace-tab__icon",
  ".workspace-tab__icon--table",
  ".workspace-tab__icon--sql",
  ".workspace-tab__title",
  ".workspace-tab__close",
  ".workspace-tabs__add",
];

const retiredAppSelectors = [
  ".hifi-workspace-tab-bar",
  ".hifi-workspace-tabs-scroll",
  ".hifi-workspace-tab",
  ".hifi-tab-close",
  ".hifi-tab-add-btn",
  ".hifi-workspace-tab-actions",
  ".hifi-right-drawer-toggle-btn",
];

describe("WorkspaceTabs styles", () => {
  it("keeps workspace tab chrome styles local without inline styles or Tailwind residue", () => {
    expect(existsSync(localCss)).toBe(true);

    const css = readFileSync(localCss, "utf8");
    for (const selector of localSelectors) {
      expect(css).toContain(selector);
    }

    const source = readFileSync(sourcePath, "utf8");
    expect(source).toContain('import "./WorkspaceTabs.css";');
    expect(source).toContain('from "../../components/ui";');
    expect(source).toContain("Tabs");
    expect(source).toContain("TabsList");
    expect(source).toContain("TabsTrigger");
    expect(source).toContain("Tooltip");
    expect(source).toContain("TooltipTrigger");
    expect(source).toContain("TooltipContent");
    expect(source).toContain("<Button");
    expect(source).not.toContain('title={`关闭 ${tab.title}`}');
    expect(source).not.toContain('title="新建 SQL 查询"');
    expect(source).not.toContain('role="tablist"');
    expect(source).not.toContain('role="tab"');
    expect(source).not.toContain("style=");
    expect(source).not.toMatch(/hifi-workspace-tab|hifi-tab-close|hifi-tab-add-btn/);
    expect(source).not.toMatch(/text-(blue|green|orange|purple|indigo|pink|rose)-500|truncate|max-w-|ml-|opacity-/);

    const globalCss = readFileSync(appCss, "utf8");
    for (const selector of retiredAppSelectors) {
      expect(globalCss).not.toContain(selector);
    }
  });
});

}

// Source: desktop/src/features/workspace/artifacts/__tests__/ArtifactViews.styles.test.ts
{

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

}

// Source: desktop/src/features/workspace/artifacts/__tests__/TableArtifactView.styles.test.ts
{

const tableArtifactSource = join(process.cwd(), "src/features/workspace/artifacts/TableArtifactView.tsx");
const artifactTableGridSource = join(process.cwd(), "src/features/workspace/artifacts/table/ArtifactTableGrid.tsx");
const artifactTableToolbarSource = join(process.cwd(), "src/features/workspace/artifacts/table/ArtifactTableToolbar.tsx");
const artifactTableFooterSource = join(process.cwd(), "src/features/workspace/artifacts/table/ArtifactTableFooter.tsx");
const artifactTableCss = join(process.cwd(), "src/features/workspace/artifacts/table/ArtifactTable.css");
const appCss = join(process.cwd(), "src/App.css");

const artifactTableSelectors = [
  ".artifact-table-grid",
  ".artifact-table-head",
  ".artifact-table-head-button",
  ".artifact-table-column-name",
  ".artifact-table-type-badge",
  ".artifact-table-cell",
  ".artifact-table-null-pill",
  ".artifact-table-meta",
  ".artifact-table-toolbar-stack",
  ".artifact-table-toolbar",
  ".artifact-table-toolbar-main",
  ".artifact-table-inline-toolbar",
  ".artifact-table-search-shell",
  ".artifact-table-search-icon",
  ".artifact-table-search",
  ".artifact-table-control-row",
  ".artifact-table-control-field",
  ".artifact-table-control-select",
  ".artifact-table-control-input",
  ".artifact-table-footer",
  ".artifact-table-footer-text",
  ".artifact-table-footer-controls",
  ".artifact-table-truncated",
  ".artifact-table-pagination",
  ".artifact-table-page-button",
  ".artifact-table-page-number",
  ".artifact-table-page-size",
  ".artifact-table-workspace",
  ".artifact-table-alert",
  ".artifact-table-alert-icon",
  ".artifact-table-container",
  ".artifact-table-loading-bar",
  ".artifact-table-action-button",
  ".artifact-table-inline-error",
  ".artifact-table-inline-table",
];

describe("TableArtifactView styles", () => {
  it("keeps artifact table business styles in a local feature stylesheet", () => {
    const source = readFileSync(tableArtifactSource, "utf8");
    const globalCss = readFileSync(appCss, "utf8");

    expect(source).toContain('import "./table/ArtifactTable.css";');
    expect(existsSync(artifactTableCss)).toBe(true);

    const localCss = readFileSync(artifactTableCss, "utf8");
    for (const selector of artifactTableSelectors) {
      expect(localCss).toContain(selector);
      expect(globalCss).not.toContain(selector);
    }
  });

  it("uses UI primitives for artifact table controls instead of raw controls and Tailwind utilities", () => {
    const toolbarSource = readFileSync(artifactTableToolbarSource, "utf8");
    const footerSource = readFileSync(artifactTableFooterSource, "utf8");
    const controlSources = [toolbarSource, footerSource].join("\n");

    expect(toolbarSource).toContain('from "../../../../components/ui";');
    expect(toolbarSource).toContain("Button");
    expect(toolbarSource).toContain("Input");
    expect(toolbarSource).toContain("Select");
    expect(toolbarSource).toContain("Toolbar");
    expect(toolbarSource).toContain("ToolbarGroup");
    expect(toolbarSource).toContain("Popover");
    expect(toolbarSource).toContain("PopoverContent");
    expect(toolbarSource).toContain("PopoverTrigger");
    expect(toolbarSource).not.toContain('from "@radix-ui/react-popover"');
    expect(toolbarSource).not.toContain("filterOpen");
    expect(toolbarSource).not.toContain("sortOpen");
    expect(footerSource).toContain('from "../../../../components/ui";');
    expect(footerSource).toContain("Button");
    expect(footerSource).toContain("Select");

    expect(controlSources).not.toMatch(/<(button|input|select)\b/);
    expect(controlSources).not.toMatch(
      /\b(flex|items-center|justify-center|gap-\d|px-\d|py-\d|mb-\d|h-\d|min-w-\[|pl-\d|pr-\d|text-\[|rounded|relative|absolute|opacity-\d|cursor-not-allowed|animate-spin)\b/,
    );
  });

  it("renders table filter and sort controls in DBFox popover surfaces", () => {
    const toolbarSource = readFileSync(artifactTableToolbarSource, "utf8");
    const css = readFileSync(artifactTableCss, "utf8");

    expect(toolbarSource).toContain('className="artifact-table-popover-content"');
    expect(toolbarSource).toContain('className="artifact-table-popover-actions"');
    expect(css).toContain(".artifact-table-popover-content");
    expect(css).toContain(".artifact-table-popover-actions");
  });

  it("uses TanStack Table as the artifact result table row and column engine", () => {
    const gridSource = readFileSync(artifactTableGridSource, "utf8");

    expect(gridSource).toContain('from "@tanstack/react-table"');
    expect(gridSource).toContain("useReactTable");
    expect(gridSource).toContain("getCoreRowModel");
    expect(gridSource).toContain("flexRender");
    expect(gridSource).toContain("CellValuePreview");
    expect(gridSource).not.toContain("hifi-table");
    expect(gridSource).not.toContain("numericColumns = columns.map");
  });

  it("owns the artifact table visual frame locally instead of inheriting the legacy grid look", () => {
    const css = readFileSync(artifactTableCss, "utf8");

    expect(css).toContain("border-collapse: separate");
    expect(css).toContain("border-spacing: 0");
    expect(css).toContain("box-shadow: inset 0 0 0 1px var(--agent-border)");
    expect(css).toContain(".artifact-table-grid thead th");
    expect(css).toContain(".artifact-table-grid tbody td");
    expect(css).toContain(".artifact-table-row");
  });

  it("keeps TableArtifactView shell and actions on local classes and Button primitives", () => {
    const source = readFileSync(tableArtifactSource, "utf8");

    expect(source).toContain('from "../../../components/ui";');
    expect(source).toContain("Button");
    expect(source).not.toMatch(/<button\b/);
    expect(source).not.toMatch(
      /\b(flex|flex-col|flex-shrink-0|items-center|gap-\d|m-\d|mb-\d|p-\d|h-full|w-full|overflow-hidden|overflow-auto|relative|absolute|top-0|left-0|right-0|mt-\d(?:\.\d)?|text-\[|rounded)\b/,
    );
  });
});

}

// Source: desktop/src/features/workspace/table/__tests__/TableErPane.styles.test.ts
{

const tableErSource = join(process.cwd(), "src/features/workspace/table/TableErPane.tsx");
const tableErCss = join(process.cwd(), "src/features/workspace/table/TableErPane.css");
const appCss = join(process.cwd(), "src/App.css");

const tableErSelectors = [
  ".table-er-pane",
  ".table-er-pane__state",
  ".table-er-pane__header",
  ".table-er-pane__caption",
  ".table-er-pane__meta",
  ".table-er-pane__toolbar",
  ".table-er-pane__control",
  ".table-er-pane__select",
  ".table-er-pane__toggle",
  ".table-er-pane__canvas",
  ".table-er-pane__diagram-loading",
];

describe("TableErPane styles", () => {
  it("keeps ER diagram styling local and uses shared state components", () => {
    const source = readFileSync(tableErSource, "utf8");
    const globalCss = readFileSync(appCss, "utf8");

    expect(source).not.toContain('import { ErDiagram } from "../../../components/ErDiagram";');
    expect(source).toContain('lazy(async () =>');
    expect(source).toContain('import("../../../components/ErDiagram")');
    expect(source).toContain("<Suspense");
    expect(source).toContain('import { Button, EmptyState, ErrorState, LoadingState, Select, Toolbar, ToolbarGroup } from "../../../components/ui";');
    expect(source).toContain('import "./TableErPane.css";');
    expect(existsSync(tableErCss)).toBe(true);
    expect(source).not.toContain("style=");
    expect(source).not.toMatch(/table-er-node|p-4|text-slate|text-red|bg-red|rounded-lg|rounded-xl|shadow-inner|font-mono|flex-1|flex-wrap|gap-6|min-w-max|w-\[160px\]/);

    const localCss = readFileSync(tableErCss, "utf8");
    for (const selector of tableErSelectors) {
      expect(localCss).toContain(selector);
      expect(globalCss).not.toContain(selector);
    }
  });
});

}

// Source: desktop/src/features/workspace/table/__tests__/TablePreviewPane.styles.test.ts
{

const tablePreviewSource = join(process.cwd(), "src/features/workspace/table/TablePreviewPane.tsx");
const tablePreviewCss = join(process.cwd(), "src/features/workspace/table/TablePreviewPane.css");
const appCss = join(process.cwd(), "src/App.css");

const tablePreviewSelectors = [
  ".hifi-table-preview-pane",
  ".hifi-table-toolbar",
  ".hifi-preview-toolbar-btn",
  ".hifi-preview-search",
  ".hifi-preview-control-row",
  ".hifi-result-control-field",
  ".hifi-result-control-value",
  ".hifi-preview-loading-bar",
  ".hifi-preview-notice",
  ".hifi-preview-error",
  ".hifi-preview-skeleton",
  ".hifi-preview-skeleton-row",
  ".hifi-preview-empty",
  ".hifi-preview-empty-icon",
  ".hifi-preview-empty-title",
  ".hifi-preview-empty-copy",
  ".hifi-preview-empty-actions",
  ".table-preview-grid",
  ".table-preview-head",
  ".table-preview-row",
  ".table-preview-cell",
  ".table-preview-null-pill",
  ".hifi-table-footer",
  ".hifi-pagination",
  ".hifi-page-num",
  ".hifi-preview-page-btn",
];

const retiredResultSelectors = [
  ".hifi-result-workspace",
  ".hifi-result-control-row",
  ".hifi-result-table-wrap",
  ".hifi-result-inline-table",
  ".hifi-result-table-head",
  ".hifi-result-table-head-button",
  ".hifi-result-error",
  ".hifi-sql-card",
  ".hifi-sql-card-action",
];

describe("TablePreviewPane styles", () => {
  it("keeps table preview business styles in a local feature stylesheet", () => {
    const source = readFileSync(tablePreviewSource, "utf8");
    const globalCss = readFileSync(appCss, "utf8");

    expect(source).toContain('import "./TablePreviewPane.css";');
    expect(existsSync(tablePreviewCss)).toBe(true);

    const localCss = readFileSync(tablePreviewCss, "utf8");
    for (const selector of tablePreviewSelectors) {
      expect(localCss).toContain(selector);
      expect(globalCss).not.toContain(selector);
    }
    for (const selector of retiredResultSelectors) {
      expect(globalCss).not.toContain(selector);
    }
  });

  it("uses TanStack Table for the preview table body and owns the visual frame locally", () => {
    const source = readFileSync(tablePreviewSource, "utf8");
    const css = readFileSync(tablePreviewCss, "utf8");

    expect(source).toContain('from "@tanstack/react-table"');
    expect(source).toContain("useReactTable");
    expect(source).toContain("getCoreRowModel");
    expect(source).toContain("flexRender");
    expect(source).toContain("Popover");
    expect(source).toContain("PopoverContent");
    expect(source).toContain("PopoverTrigger");
    expect(source).toContain("CellValuePreview");
    expect(source).not.toContain('from "@radix-ui/react-popover"');
    expect(source).not.toContain("filterOpen");
    expect(source).not.toContain("sortOpen");
    expect(source).not.toContain('className="hifi-table hifi-preview-table"');

    expect(css).toContain("border-collapse: separate");
    expect(css).toContain("border-spacing: 0");
    expect(css).toContain(".table-preview-grid thead th");
    expect(css).toContain(".table-preview-grid tbody td");
    expect(css).toContain(".table-preview-popover-content");
    expect(css).toContain(".table-preview-popover-actions");
    expect(css).toContain("box-shadow: inset 0 0 0 1px var(--agent-border)");
  });
});

}

// Source: desktop/src/features/workspace/artifacts/__tests__/EmptyArtifactsState.styles.test.ts
{

const emptyArtifactsSource = join(process.cwd(), "src/features/workspace/artifacts/EmptyArtifactsState.tsx");
const emptyArtifactsCss = join(process.cwd(), "src/features/workspace/artifacts/EmptyArtifactsState.css");
const emptyArtifactsAppCss = join(process.cwd(), "src/App.css");

const emptyArtifactsSelectors = [
  ".hifi-ai-card",
  ".hifi-ai-card-header",
  ".hifi-ai-card-body",
  ".hifi-artifact-empty",
  ".hifi-artifact-empty-header",
  ".hifi-artifact-empty-icon",
  ".hifi-artifact-empty-body",
];

describe("EmptyArtifactsState styles", () => {
  it("keeps empty artifact presentation in the artifact feature stylesheet", () => {
    const source = readFileSync(emptyArtifactsSource, "utf8");
    const globalCss = readFileSync(emptyArtifactsAppCss, "utf8");

    expect(source).toContain('import "./EmptyArtifactsState.css";');
    expect(existsSync(emptyArtifactsCss)).toBe(true);

    const localCss = readFileSync(emptyArtifactsCss, "utf8");
    for (const selector of emptyArtifactsSelectors) {
      expect(localCss).toContain(selector);
      expect(globalCss).not.toContain(selector);
    }
  });
});

}

// Source: desktop/src/pages/__tests__/AgentEvalPage.styles.test.ts
{

const sourcePath = join(process.cwd(), "src/pages/AgentEvalPage.tsx");
const cssPath = join(process.cwd(), "src/pages/AgentEvalPage.css");
const appCssPath = join(process.cwd(), "src/App.css");

const localSelectors = [
  ".agent-eval-page",
  ".agent-eval-header",
  ".agent-eval-header__title",
  ".agent-eval-header__datasource",
  ".agent-eval-header__actions",
  ".agent-eval-form",
  ".agent-eval-form__row",
  ".agent-eval-form__inline",
  ".agent-eval-body",
  ".agent-eval-panel",
  ".agent-eval-list",
  ".agent-eval-task",
  ".agent-eval-task__name",
  ".agent-eval-task__question",
  ".agent-eval-chip",
  ".agent-eval-chip--keyword",
  ".agent-eval-run",
  ".agent-eval-run__head",
  ".agent-eval-run__rate",
  ".agent-eval-run__rate--good",
  ".agent-eval-run__rate--warn",
  ".agent-eval-run__rate--bad",
  ".agent-eval-case",
  ".agent-eval-case__status",
  ".agent-eval-case__status--passed",
  ".agent-eval-case__status--failed",
  ".agent-eval-case__status--error",
  ".agent-eval-case__reasons",
];

describe("AgentEvalPage styles", () => {
  it("keeps agent evaluation presentation local and uses shared UI primitives", () => {
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain('import "./AgentEvalPage.css";');
    expect(source).toContain("from \"../components/ui\"");
    for (const primitive of ["Button", "Input", "Panel", "PanelBody", "PanelHeader", "PanelTitle", "EmptyState", "LoadingState"]) {
      expect(source).toContain(`<${primitive}`);
    }
    expect(source).not.toContain("hifi-eval");
    expect(source).not.toContain("hifi-agent-running-spinner");

    expect(existsSync(cssPath)).toBe(true);
    const localCss = readFileSync(cssPath, "utf8");
    for (const selector of localSelectors) {
      expect(localCss).toContain(selector);
    }
    expect(localCss).not.toContain("hifi-eval");

    const appCss = readFileSync(appCssPath, "utf8");
    expect(appCss).not.toContain("hifi-eval");
  });
});

}

// Source: desktop/src/pages/__tests__/DiagnosticsPage.styles.test.ts
{

const sourcePath = join(process.cwd(), "src/pages/DiagnosticsPage.tsx");
const localCss = join(process.cwd(), "src/pages/DiagnosticsPage.css");
const appCss = join(process.cwd(), "src/App.css");

const localSelectors = [
  ".diagnostics-page",
  ".diagnostics-page--workspace",
  ".diagnostics-page-header",
  ".diagnostics-page-title",
  ".diagnostics-page-subtitle",
  ".diagnostics-actions",
  ".diagnostics-toggle-label",
  ".diagnostics-toggle-checkbox",
  ".diagnostics-badge",
  ".diagnostics-error",
  ".diagnostics-summary",
  ".diagnostics-metric",
  ".diagnostics-source-toolbar",
  ".diagnostics-source-picker",
  ".diagnostics-source-trigger",
  ".diagnostics-source-menu",
  ".diagnostics-source-option",
  ".diagnostics-source-option.is-active",
  ".diagnostics-source-count",
  ".diagnostics-sources",
  ".diagnostics-source",
  ".diagnostics-source-header",
  ".diagnostics-log-status",
  ".diagnostics-log-status--ok",
  ".diagnostics-log-status--missing",
  ".diagnostics-source-content",
  ".diagnostics-empty",
];

describe("DiagnosticsPage styles", () => {
  it("keeps diagnostics page styling local and out of App.css", () => {
    expect(existsSync(localCss)).toBe(true);

    const css = readFileSync(localCss, "utf8");
    for (const selector of localSelectors) {
      expect(css).toContain(selector);
    }

    const source = readFileSync(sourcePath, "utf8");
    expect(source).toContain('import "./DiagnosticsPage.css";');
    expect(source).not.toContain("style=");

    const globalCss = readFileSync(appCss, "utf8");
    expect(globalCss).not.toMatch(/\.hifi-diagnostics-|\.hifi-log-status/);
  });

  it("uses shared UI primitives for diagnostic actions and states", () => {
    const source = readFileSync(sourcePath, "utf8");

    expect(source).toContain('from "../components/ui";');
    expect(source).toContain("<Button");
    expect(source).toContain("<ErrorState");
    expect(source).toContain("<EmptyState");
    expect(source).not.toMatch(/<button\b/);
    expect(source).not.toContain("hifi-btn");
    expect(source).not.toContain("hifi-page-header");
    expect(source).not.toContain("workspace-page-toolbar");
  });
});

}


// Source: desktop/src/features/workspace/__tests__/WorkspaceLocalStyles.test.ts
{

const tableWorkspaceSource = join(process.cwd(), "src/features/workspace/TableWorkspace.tsx");
const tableWorkspaceCss = join(process.cwd(), "src/features/workspace/TableWorkspace.css");
const tableSchemaSource = join(process.cwd(), "src/features/workspace/table/TableSchemaPane.tsx");
const tableSchemaCss = join(process.cwd(), "src/features/workspace/table/TableSchemaPane.css");
const askContextSource = join(process.cwd(), "src/features/workspace/smartQuery/AskContextDropZone.tsx");
const askContextCss = join(process.cwd(), "src/features/workspace/smartQuery/AskContextDropZone.css");
const appCss = join(process.cwd(), "src/App.css");

const tableWorkspaceSelectors = [
  ".table-workspace",
  ".table-workspace__tabs",
  ".table-workspace__tab",
  ".table-workspace__tab.is-active",
  ".table-workspace__body",
];

const tableSchemaSelectors = [
  ".table-schema-pane",
  ".table-schema-pane__caption",
  ".table-schema-pane__loading",
  ".table-schema-pane__error",
  ".table-schema-table",
  ".table-schema-table__type",
  ".table-schema-constraints",
  ".table-schema-constraint",
  ".table-schema-constraint--primary",
  ".table-schema-constraint--foreign",
  ".table-schema-muted",
  ".table-schema-confidence",
  ".table-schema-confidence--high",
  ".table-schema-confidence--medium",
  ".table-schema-confidence--low",
  ".table-schema-tag",
];

const askContextSelectors = [
  ".ask-context-dropzone",
  ".ask-context-dropzone:hover",
  ".ask-context-dropzone__icon",
  ".ask-context-dropzone__label",
  ".ask-context-dropzone__placeholder",
  ".ask-context-dropzone__chips",
  ".ask-context-chip",
  ".ask-context-chip__remove",
  ".ask-context-dropzone__clear",
];

const retiredAppSelectors = [
  ".hifi-breadcrumb",
  ".hifi-subtabs",
  ".hifi-subtab",
  ".hifi-constraint-badge",
  ".hifi-er-container",
  ".hifi-er-zoom-controls",
  ".hifi-er-zoom-btn",
  ".hifi-table-workspace",
  ".hifi-workspace-subtabs",
  ".hifi-workspace-subtab",
  ".hifi-subtab-content",
  ".hifi-drop-zone",
  ".hifi-context-chip",
];

describe("workspace local styles", () => {
  it("keeps table workspace layout styles local", () => {
    expect(existsSync(tableWorkspaceCss)).toBe(true);

    const source = readFileSync(tableWorkspaceSource, "utf8");
    expect(source).toContain('import "./TableWorkspace.css";');
    expect(source).not.toMatch(/hifi-table-workspace|hifi-workspace-subtabs|hifi-workspace-subtab|hifi-subtab-content/);
    expect(source).not.toMatch(/flex-1|overflow-auto|hifi-tab-pane/);

    const css = readFileSync(tableWorkspaceCss, "utf8");
    for (const selector of tableWorkspaceSelectors) {
      expect(css).toContain(selector);
    }
  });

  it("keeps schema pane styling local without inline styles", () => {
    expect(existsSync(tableSchemaCss)).toBe(true);

    const source = readFileSync(tableSchemaSource, "utf8");
    expect(source).toContain('import "./TableSchemaPane.css";');
    expect(source).not.toContain("style=");
    expect(source).not.toMatch(/hifi-table|hifi-constraint-badge|text-slate|text-blue|bg-red|rounded-lg|font-mono|ml-1/);

    const css = readFileSync(tableSchemaCss, "utf8");
    for (const selector of tableSchemaSelectors) {
      expect(css).toContain(selector);
    }
  });

  it("keeps smart-query drop zone styling local", () => {
    expect(existsSync(askContextCss)).toBe(true);

    const source = readFileSync(askContextSource, "utf8");
    expect(source).toContain('import "./AskContextDropZone.css";');
    expect(source).not.toMatch(/hifi-drop-zone|hifi-context-chip/);
    expect(source).not.toMatch(/text-indigo|text-slate|bg-indigo|border-indigo|flex-wrap|rounded|font-mono|ml-1/);

    const css = readFileSync(askContextCss, "utf8");
    for (const selector of askContextSelectors) {
      expect(css).toContain(selector);
    }
  });

  it("keeps migrated workspace business selectors out of App.css", () => {
    const globalCss = readFileSync(appCss, "utf8");
    for (const selector of retiredAppSelectors) {
      expect(globalCss).not.toContain(selector);
    }
  });
});

}


// Source: desktop/src/__tests__/agentVisualTokens.test.ts
{

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

  it("keeps MarkdownContent base styles owned by the query result feature", () => {
    const source = read("features/workspace/queryResult/MarkdownContent.tsx");
    const css = read("features/workspace/queryResult/MarkdownContent.css");
    const appCss = read("App.css");

    expect(source).toContain('import "./MarkdownContent.css";');
    expect(css).toContain(".hifi-markdown-content");
    expect(css).toContain(".hifi-md-table");
    expect(appCss).not.toContain("/* ===== Markdown Content ===== */");
    expect(appCss).not.toMatch(/^\.hifi-markdown-content/m);
    expect(appCss).not.toMatch(/^\.hifi-md-/m);
  });

  it("keeps retired agent conversation hifi styles out of App.css", () => {
    const appCss = read("App.css");

    expect(appCss).not.toMatch(/\.(?:hifi-query-result|hifi-approval|hifi-agent-running|hifi-agent-cancel|hifi-agent-regenerate|hifi-answer|hifi-followup|hifi-artifact-chip|hifi-thinking|hifi-agent-timeline|hifi-agent-json)/);
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

}
