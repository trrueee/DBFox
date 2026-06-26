import type { ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SqlEditor } from "../SqlEditor";

vi.mock("@monaco-editor/react", () => ({
  default: ({ theme, loading }: { theme?: string; loading?: ReactNode }) => (
    <div data-testid="monaco-editor-mock" data-theme={theme}>
      {loading}
    </div>
  ),
}));

describe("SqlEditor", () => {
  beforeEach(() => cleanup());

  it("uses a dark Monaco theme with a silent loading surface when requested", () => {
    render(<SqlEditor value="" onChange={vi.fn()} appearance="dark" />);

    const editor = screen.getByTestId("monaco-editor-mock");

    expect(editor.getAttribute("data-theme")).toBe("dbfoxDark");
    expect(screen.queryByText("Loading...")).toBeNull();
    expect(editor.querySelector(".sql-editor-loading")).toBeTruthy();
  });
});
