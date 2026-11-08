import { readFile } from "node:fs/promises";
import { DOMParser } from "@xmldom/xmldom";
import { expect, it } from "vitest";
import { buildUiIcons } from "../build-ui-icons.mjs";

it("publishes hash-checked offline artwork with a unique, paintable symbol for every supported state", async () => {
  const result = await buildUiIcons({ check: true });
  const bytes = await readFile(new URL(`../../${result.asset}`, import.meta.url), "utf8");
  const document = new DOMParser().parseFromString(bytes, "image/svg+xml");
  const symbols = Array.from(document.getElementsByTagName("symbol"));
  expect(symbols).toHaveLength(result.variants);
  expect(new Set(symbols.map(symbol => symbol.getAttribute("id"))).size).toBe(symbols.length);
  expect(symbols.every(symbol => symbol.getElementsByTagName("path").length > 0 || symbol.getElementsByTagName("rect").length > 0 || symbol.getElementsByTagName("circle").length > 0)).toBe(true);
  expect(bytes).not.toMatch(/<script|<style|\son[a-z]+=|https?:\/\/(?!www\.w3\.org)/i);
});
