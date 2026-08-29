import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JsonTree } from "../json";

describe("JsonTree", () => {
  it("uses a labelled tree with localized expand and collapse controls", () => {
    render(<JsonTree data={{ user: { name: "Ada", active: true } }} />);

    expect(screen.getByRole("tree", { name: "JSON 结构" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "折叠 JSON 节点" })).toHaveLength(2);
  });

  it("supports keyboard expansion without custom click-only state", () => {
    render(<JsonTree data={{ user: { name: "Ada" } }} />);

    const rootToggle = screen.getAllByRole("button", { name: "折叠 JSON 节点" })[0];
    fireEvent.keyDown(rootToggle, { key: "ArrowLeft" });

    expect(screen.getByRole("button", { name: "展开 JSON 节点" }).getAttribute("aria-expanded")).toBe("false");
    fireEvent.keyDown(screen.getByRole("button", { name: "展开 JSON 节点" }), { key: "ArrowRight" });
    expect(screen.getAllByRole("button", { name: "折叠 JSON 节点" })[0].getAttribute("aria-expanded")).toBe("true");
  });

  it("bounds initial rendering for deep and wide values", () => {
    const items = Array.from({ length: 25 }, (_, index) => ({ id: index }));
    render(<JsonTree data={{ items, nested: { levelTwo: { levelThree: "bounded" } } }} />);

    const collapsedToggles = screen.getAllByRole("button", { name: "展开 JSON 节点" });
    expect(collapsedToggles).toHaveLength(2);
    expect(screen.queryByText("bounded")).toBeNull();
    expect(screen.queryByText("24")).toBeNull();
  });

  it("does not emit inline styles that violate the renderer CSP", () => {
    const { container } = render(<JsonTree data={{ answer: 42 }} />);

    expect(container.querySelector("[style]")).toBeNull();
  });
});
