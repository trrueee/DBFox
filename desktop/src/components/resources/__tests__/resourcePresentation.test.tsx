import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { fileKind, referenceKind, ResourceIcon } from "../resourcePresentation";

afterEach(cleanup);

describe("recognizable file presentation", () => {
  it("identifies Windows paths and uppercase extensions without treating a dotted parent as an extension", () => {
    expect(fileKind("C:\\reports\\计划.XLSX")).toBe("spreadsheet");
    expect(fileKind("docs/README.MD")).toBe("markdown");
    expect(fileKind("folder.md/README")).toBe("file");
    expect(fileKind("md")).toBe("file");
    expect(fileKind("Dockerfile")).toBe("code");
    expect(fileKind(".gitignore")).toBe("code");
  });

  it("distinguishes Excel, CSV, Markdown and PDF with local upstream artwork", () => {
    const { container } = render(<>{["计划.xlsx", "数据.csv", "README.md", "说明.pdf"].map(name => <ResourceIcon key={name} name={name} />)}</>);
    const icons = [...container.querySelectorAll("img")];
    expect(icons.map(icon => icon.getAttribute("src"))).toEqual([
      expect.stringContaining("file_type_excel.svg"),
      expect.stringContaining("file_type_markdown.svg"), expect.stringContaining("file_type_pdf.svg"),
    ]);
    expect(container.querySelector("svg.resource-icon--spreadsheet")).not.toBeNull();
    expect(icons.every(icon => icon.alt === "" && icon.getAttribute("aria-hidden") === "true")).toBe(true);
  });

  it("preserves resource semantics when a folder or table happens to have a file-like name", () => {
    const { container } = render(<><ResourceIcon kind="folder" name="reports.xlsx" expanded /><ResourceIcon kind="table" name="events.csv" /></>);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector('[data-ui-icon="folder-open"]')).not.toBeNull();
    expect(container.querySelector(".resource-icon--table")).not.toBeNull();
    const reference = { artifactId: "result", label: "report.md" };
    expect(referenceKind(reference, { type: "dbfox.workspace.file_snapshot", title: "report.md" })).toBe("markdown");
    expect(referenceKind(reference, { type: "dbfox.data.dataframe", title: "report.md" })).toBe("table");
    expect(referenceKind(reference)).toBe("artifact");
  });

  it("uses native Fluent artwork sizes for tree rows and attachment cards", () => {
    const { container } = render(<><ResourceIcon name="report.xlsx" size={16} /><ResourceIcon name="report.xlsx" size={20} /></>);
    expect([...container.querySelectorAll("img")].map(icon => icon.getAttribute("src"))).toEqual([
      expect.stringContaining("file_type_excel.svg"), expect.stringContaining("file_type_excel_20.svg"),
    ]);
  });
});
