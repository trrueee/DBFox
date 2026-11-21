import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ComputerApprovalDetails } from "../ComputerApprovalDetails";

afterEach(cleanup);

describe("computer approval target evidence", () => {
  it("distinguishes coordinate inputs and identifies their immutable observation", () => {
    const base = { action: "click", target: "Synthetic fixture", element: "画面位置", observed_at: 1_700_000_000_000,
      observation_artifact_id: "artifact_observation", image_width: 1280, image_height: 800 };
    const { rerender } = render(<ComputerApprovalDetails review={{ ...base, position: { x: 0.1, y: 0.9 } }} />);
    expect(screen.getByText("X 0.1 · Y 0.9（相对观察画面）")).toBeTruthy();
    expect(screen.getByText("artifact_observation")).toBeTruthy();
    expect(screen.getByText("1280 × 800")).toBeTruthy();
    rerender(<ComputerApprovalDetails review={{ ...base, position: { x: 0.8, y: 0.2 } }} />);
    expect(screen.queryByText("X 0.1 · Y 0.9（相对观察画面）")).toBeNull();
    expect(screen.getByText("X 0.8 · Y 0.2（相对观察画面）")).toBeTruthy();
  });

  it("does not invent a position for element-based input or malformed review values", () => {
    render(<ComputerApprovalDetails review={{ action: "click", target: "Synthetic fixture", element: "Save", position: { x: "0.5", y: null } }} />);
    expect(screen.getByText("Save")).toBeTruthy();
    expect(screen.queryByText("画面落点")).toBeNull();
  });
});
