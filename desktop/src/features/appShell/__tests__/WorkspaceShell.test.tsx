import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceShell } from "../WorkspaceShell";

describe("WorkspaceShell", () => {
  beforeEach(() => cleanup());

  it("renders desktop workspace chrome with header, toolbar, and body", () => {
    render(
      <WorkspaceShell
        title="Diagnostics"
        description="Inspect local runtime logs."
        toolbar={<button type="button">Refresh</button>}
      >
        <div>Log body</div>
      </WorkspaceShell>
    );

    expect(screen.getByRole("region", { name: "Diagnostics" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Diagnostics" })).toBeTruthy();
    expect(screen.getByText("Inspect local runtime logs.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeTruthy();
    expect(screen.getByText("Log body")).toBeTruthy();
  });

  it("allows callers to specialize the scroll body", () => {
    render(
      <WorkspaceShell title="Artifact result" bodyClassName="workspace-shell__body--artifact-result">
        <div>Rows</div>
      </WorkspaceShell>,
    );

    const shell = screen.getByRole("region", { name: "Artifact result" });
    expect(shell.querySelector(".workspace-shell__body")?.classList.contains("workspace-shell__body--artifact-result")).toBe(
      true,
    );
  });

  it("uses standardized loading, empty, and error body states", () => {
    const onRetry = vi.fn();
    const { rerender } = render(
      <WorkspaceShell title="Results" state={{ kind: "loading", label: "Loading rows" }}>
        Loaded rows
      </WorkspaceShell>
    );

    expect(screen.getByRole("status").textContent).toContain("Loading rows");
    expect(screen.queryByText("Loaded rows")).toBeNull();

    rerender(
      <WorkspaceShell
        title="Results"
        state={{
          kind: "empty",
          title: "No result",
          description: "Run a query to create one.",
          action: <button type="button">Run</button>,
        }}
      />
    );

    expect(screen.getByRole("heading", { name: "No result" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Run" })).toBeTruthy();

    rerender(
      <WorkspaceShell
        title="Results"
        state={{
          kind: "error",
          title: "Result failed",
          description: "The result can no longer be loaded.",
          onRetry,
        }}
      />
    );

    expect(screen.getByRole("alert").textContent).toContain("Result failed");
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
