import { readdir, readFile } from "node:fs/promises";
import { extname, join, relative, resolve } from "node:path";

import postcss from "postcss";

const desktopRoot = resolve(import.meta.dirname, "..");
const repositoryRoot = resolve(desktopRoot, "..");
const sourceRoot = join(desktopRoot, "src");
const dlcRoot = join(repositoryRoot, "dlcs");
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
const allowedFontWeights = new Set(["400", "500", "600"]);
const violations = [];
const sharedTokenRoot = postcss.parse(
  await readFile(join(sourceRoot, tokenFile), "utf8"),
  { from: join(sourceRoot, tokenFile) },
);
const sharedTokens = new Set();
sharedTokenRoot.walkDecls((declaration) => {
  if (declaration.prop.startsWith("--")) sharedTokens.add(declaration.prop);
});

async function cssFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return cssFiles(path);
    return extname(entry.name) === ".css" ? [path] : [];
  }));
  return nested.flat();
}

async function dlcCssFiles() {
  const dlcs = await readdir(dlcRoot, { withFileTypes: true });
  const trees = await Promise.all(dlcs
    .filter((entry) => entry.isDirectory())
    .map(async (entry) => {
      const frontend = join(dlcRoot, entry.name, "frontend");
      try {
        return await cssFiles(frontend);
      } catch (error) {
        if (error?.code === "ENOENT") return [];
        throw error;
      }
    }));
  return trees.flat();
}

function report(file, declaration, message) {
  violations.push(
    `${file}:${declaration.source?.start?.line ?? 1} ${message}`,
  );
}

const desktopFiles = (await cssFiles(sourceRoot)).map((path) => ({
  path,
  file: relative(sourceRoot, path).replaceAll("\\", "/"),
  isDlc: false,
}));
const dlcFiles = (await dlcCssFiles()).map((path) => ({
  path,
  file: relative(repositoryRoot, path).replaceAll("\\", "/"),
  isDlc: true,
}));

for (const { path, file, isDlc } of [...desktopFiles, ...dlcFiles]) {
  const root = postcss.parse(await readFile(path, "utf8"), { from: path });
  const localTokens = new Set();
  if (isDlc) {
    root.walkDecls((declaration) => {
      if (declaration.prop.startsWith("--")) localTokens.add(declaration.prop);
    });
  }

  if (isDlc) {
    root.walkRules((rule) => {
      if (rule.parent?.type === "atrule" && /keyframes$/i.test(rule.parent.name)) return;
      for (const selector of rule.selectors ?? []) {
        const normalized = selector.trim();
        if (/^(?::root|html\b|body\b)/i.test(normalized)) {
          report(file, rule, "DLC CSS cannot target :root, html, or body");
        }
        if (!normalized.includes(".dbfox-")) {
          report(file, rule, "DLC selectors must be namespaced with a .dbfox-* class");
        }
      }
    });
  }

  root.walkAtRules("apply", (rule) => {
    if (/\btext-\[(?:\d+(?:\.\d+)?(?:px|rem))\]/i.test(rule.params)) {
      report(file, rule, "font-size utilities must use a shared design token");
    }
  });

  root.walkDecls((declaration) => {
    const value = declaration.value.trim();
    if (file !== tokenFile && declaration.prop === "font-size" && !value.includes("var(")) {
      report(file, declaration, "font-size must use a shared design token");
    }
    if (
      declaration.prop === "font-weight"
      && /^\d+$/.test(value)
      && !allowedFontWeights.has(value)
    ) {
      report(file, declaration, "font-weight must use the 400/500/600 typography scale");
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
    if (isDlc && declaration.prop === "font-size" && !value.includes("var(")) {
      report(file, declaration, "DLC font-size must use a shared design token");
    }
    if (isDlc && declaration.important) {
      report(file, declaration, "DLC styles cannot use !important to override host presentation");
    }
    if (isDlc) {
      for (const match of value.matchAll(/var\((--[\w-]+)/g)) {
        if (!sharedTokens.has(match[1]) && !localTokens.has(match[1])) {
          report(file, declaration, `DLC references unknown design token ${match[1]}`);
        }
      }
    }
    if (
      isDlc
      && /^(?:color|background(?:-color)?|border(?:-[a-z-]+)?|fill|stroke)$/i.test(declaration.prop)
      && (
        /#(?:[0-9a-f]{3,8})\b/i.test(value)
        || /\brgba?\(/i.test(value)
        || /\b(?:white|black)\b/i.test(value)
      )
    ) {
      report(file, declaration, "DLC app colors must use semantic DBFox tokens");
    }
    if (
      isDlc
      && declaration.prop === "box-shadow"
      && value !== "none"
      && !/^var\(--(?:focus-ring|shadow-window|shadow-card|shadow-card-hover)\)$/.test(value)
    ) {
      report(file, declaration, "DLC box-shadow must use a shared elevation or focus token");
    }
    const selector = declaration.parent?.selector?.trim() ?? "";
    const isNamespaceRoot = /^\.dbfox-[a-z0-9-]+$/i.test(selector)
      && !/(?:dialog|popover|menu|tooltip)/i.test(selector);
    if (
      isDlc
      && isNamespaceRoot
      && (
        (declaration.prop === "position" && value === "fixed")
        || (/^(?:width|height|min-width|min-height)$/.test(declaration.prop) && /(?:100vw|100vh)/.test(value))
      )
    ) {
      report(file, declaration, "DLC namespace roots cannot define app-level fixed layout");
    }
  });
}

if (violations.length) {
  process.stderr.write(`${violations.join("\n")}\n`);
  process.exitCode = 1;
}
