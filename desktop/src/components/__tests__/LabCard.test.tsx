import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi } from "vitest";
import { LabCard } from "../LabCard";

describe("LabCard accessibility", () => {
  it("renders with role='button' and tabIndex=0 when onClick is provided", () => {
    const handleClick = vi.fn();
    render(<LabCard onClick={handleClick}>Clickable Card</LabCard>);

    const card = screen.getByText("Clickable Card");
    expect(card).toHaveAttribute("role", "button");
    expect(card).toHaveAttribute("tabindex", "0");
  });

  it("does not have role or tabIndex when onClick is absent", () => {
    render(<LabCard>Static Card</LabCard>);

    const card = screen.getByText("Static Card");
    expect(card).not.toHaveAttribute("role");
    expect(card).not.toHaveAttribute("tabindex");
  });

  it("triggers onClick on Enter and Space keypresses", () => {
    const handleClick = vi.fn();
    render(<LabCard onClick={handleClick}>Interactive Card</LabCard>);

    const card = screen.getByText("Interactive Card");

    // Click triggers
    fireEvent.click(card);
    expect(handleClick).toHaveBeenCalledTimes(1);

    // Enter key triggers
    fireEvent.keyDown(card, { key: "Enter", code: "Enter" });
    expect(handleClick).toHaveBeenCalledTimes(2);

    // Space key triggers
    fireEvent.keyDown(card, { key: " ", code: "Space" });
    expect(handleClick).toHaveBeenCalledTimes(3);

    // Other keys do not trigger
    fireEvent.keyDown(card, { key: "Escape", code: "Escape" });
    expect(handleClick).toHaveBeenCalledTimes(3);
  });
});
