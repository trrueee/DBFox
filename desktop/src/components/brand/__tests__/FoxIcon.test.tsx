import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { describe, expect, it } from "vitest";
import { FoxIcon } from "../FoxIcon";

describe("FoxIcon", () => {
  it("renders the app asset from the public asset pack by default", () => {
    render(<FoxIcon />);

    const icon = screen.getByRole("img", { name: "DBFox fox icon" });

    expect(icon).toHaveAttribute(
      "src",
      "/assets/fox/png/fox-icon-app-transparent-512.png",
    );
    expect(icon).toHaveAttribute("width", "24");
    expect(icon).toHaveAttribute("height", "24");
  });

  it("supports the AI tight variant and custom sizing", () => {
    render(<FoxIcon variant="ai-tight" size={32} alt="Ask DBFox" />);

    const icon = screen.getByRole("img", { name: "Ask DBFox" });

    expect(icon).toHaveAttribute("src", "/assets/fox/png/fox-icon-ai-tight-256.png");
    expect(icon).toHaveAttribute("width", "32");
    expect(icon).toHaveAttribute("height", "32");
  });

  it("renders the shared vector app mark for shell and workspace chrome", () => {
    render(<FoxIcon variant="app" size={20} alt="DBFox app" />);

    const icon = screen.getByRole("img", { name: "DBFox app" });

    expect(icon).toHaveAttribute("src", "/assets/fox/png/fox-icon-app-transparent-512.png");
    expect(icon).toHaveAttribute("width", "20");
    expect(icon).toHaveAttribute("height", "20");
  });
});
