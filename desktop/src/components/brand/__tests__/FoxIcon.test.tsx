import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it } from "vitest";
import { FoxIcon } from "../FoxIcon";

describe("FoxIcon", () => {
  it("renders the tight fox asset from the public asset pack by default", () => {
    render(<FoxIcon />);

    const icon = screen.getByRole("img", { name: "DataBox fox icon" });

    expect(icon).toHaveAttribute("src", "/assets/fox/svg/fox-icon-tight.svg");
    expect(icon).toHaveAttribute("width", "24");
    expect(icon).toHaveAttribute("height", "24");
  });

  it("supports the AI tight variant and custom sizing", () => {
    render(<FoxIcon variant="ai-tight" size={32} alt="Ask DataBox" />);

    const icon = screen.getByRole("img", { name: "Ask DataBox" });

    expect(icon).toHaveAttribute("src", "/assets/fox/svg/fox-icon-ai-tight.svg");
    expect(icon).toHaveAttribute("width", "32");
    expect(icon).toHaveAttribute("height", "32");
  });

  it("renders the transparent app mark for shell and workspace chrome", () => {
    render(<FoxIcon variant="app" size={20} alt="DataBox app" />);

    const icon = screen.getByRole("img", { name: "DataBox app" });

    expect(icon).toHaveAttribute(
      "src",
      "/assets/fox/png/fox-icon-app-transparent-512.png",
    );
    expect(icon).toHaveAttribute("width", "20");
    expect(icon).toHaveAttribute("height", "20");
  });
});
