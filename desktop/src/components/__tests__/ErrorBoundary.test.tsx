import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "../ErrorBoundary";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ErrorBoundary", () => {
  it("shows the production fatal-error composition without exposing error details", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(
      <ErrorBoundary>
        <AlwaysFails />
      </ErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "DBFox 界面发生异常" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "重试渲染" })).toBeTruthy();
    expect(screen.queryByText("sensitive detail")).toBeNull();
  });

  it("retries rendering instead of claiming to reload the page", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let shouldFail = true;

    function FailsOnce() {
      if (shouldFail) throw new Error("transient");
      return <div>恢复完成</div>;
    }

    render(
      <ErrorBoundary>
        <FailsOnce />
      </ErrorBoundary>,
    );

    shouldFail = false;
    fireEvent.click(screen.getByRole("button", { name: "重试渲染" }));
    expect(screen.getByText("恢复完成")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "重新加载" })).toBeNull();
  });
});

function AlwaysFails(): never {
  throw new Error("sensitive detail");
}
