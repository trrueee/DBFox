import { readdir, readFile } from "node:fs/promises";
import { extname, join, relative, resolve } from "node:path";

import postcss from "postcss";

const desktopRoot = resolve(import.meta.dirname, "..");
const sourceRoot = join(desktopRoot, "src");
const tokenFile = "styles/tokens.css";
const conversationWorkspace = "features/conversation/workspace/conversationWorkspace.css";
const densityControlledPrimitives = new Set([
  "components/ui/input.css",
  "components/ui/select.css",
]);
const densityControlledSelectors = new Set([
  ".dbfox-input",
  ".dbfox-select-trigger",
]);
const violations = [];

async function cssFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return cssFiles(path);
    return extname(entry.name) === ".css" ? [path] : [];
  }));
  return nested.flat();
}

function report(file, declaration, message) {
  violations.push(
    `${file}:${declaration.source?.start?.line ?? 1} ${message}`,
  );
}

for (const path of await cssFiles(sourceRoot)) {
  const file = relative(sourceRoot, path).replaceAll("\\", "/");
  const root = postcss.parse(await readFile(path, "utf8"), { from: path });

  root.walkDecls((declaration) => {
    const value = declaration.value.trim();
    if (file !== tokenFile && declaration.prop === "font-size" && !value.includes("var(")) {
      report(file, declaration, "font-size must use a shared design token");
    }
    if (
      file === conversationWorkspace
      && (/#(?:[0-9a-f]{3,8})\b/i.test(value) || /\brgba?\(/i.test(value))
    ) {
      report(file, declaration, "conversation colors must use Agent design tokens");
    }
    if (
      densityControlledPrimitives.has(file)
      && declaration.prop === "height"
      && densityControlledSelectors.has(declaration.parent?.selector)
      && /^\d+(?:\.\d+)?px$/.test(value)
    ) {
      report(file, declaration, "shared control height must use a density design token");
    }
  });
}

if (violations.length) {
  process.stderr.write(`${violations.join("\n")}\n`);
  process.exitCode = 1;
}
