import { createRef } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { FolderSimpleIcon, PlusIcon, SidebarSimpleIcon } from "..";
import { StandardIcon } from "../../resources/StandardIcon";
import { ProviderIcon } from "../../ProviderIcon";

afterEach(cleanup);

it("exposes an optional accessible image name and forwards native SVG attributes and refs", () => {
  const ref = createRef<SVGSVGElement>();
  render(<FolderSimpleIcon ref={ref} aria-label="项目文件夹" size={24} className="project-icon" />);
  const icon = screen.getByRole("img", { name: "项目文件夹" });
  expect(ref.current).toBe(icon);
  expect(icon.getAttribute("width")).toBe("24");
  expect(icon.getAttribute("aria-hidden")).toBeNull();
  expect(icon.querySelector("use")?.getAttribute("href")).toMatch(/assets\/ui-icons\/phosphor-[a-f0-9]+\.svg#folder-simple-regular$/);
});

it("keeps control glyphs decorative and supports selected and directional states without CSS path overrides", () => {
  const { container } = render(<><PlusIcon /><FolderSimpleIcon weight="fill" /><SidebarSimpleIcon mirrored /></>);
  const icons = container.querySelectorAll("svg");
  expect(Array.from(icons).every(icon => icon.getAttribute("aria-hidden") === "true")).toBe(true);
  expect(icons[0].querySelector("use")?.getAttribute("href")).toContain("#plus-regular");
  expect(icons[1].querySelector("use")?.getAttribute("href")).toContain("#folder-simple-fill");
  expect(icons[2].querySelector("use")?.getAttribute("transform")).toBe("translate(256 0) scale(-1 1)");
});

it("uses the same artwork for isolated DLC controls and recognizable offline provider marks", () => {
  const { container } = render(<><StandardIcon name="game-controller" /><ProviderIcon provider="openai" /><ProviderIcon provider="custom" /></>);
  expect(container.querySelector("use")?.getAttribute("href")).toContain("#game-controller-regular");
  const brand = container.querySelectorAll("svg")[1];
  expect(brand.querySelector("path")?.getAttribute("d")?.length).toBeGreaterThan(100);
  expect(brand.querySelector("path")?.getAttribute("fill-rule")).toBe("evenodd");
  expect(container.querySelectorAll("svg")[2].querySelector("use")?.getAttribute("href")).toContain("#plugs-connected-regular");
  expect(container.querySelector("text")).toBeNull();
});
