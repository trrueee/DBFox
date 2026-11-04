import { copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import postcss from "postcss";

const desktop = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(desktop, "../dlcs/dbfox_data/frontend");
const vendor = join(source, "vendor");
await mkdir(join(vendor, "licenses"), { recursive: true });
const result = await build({
  absWorkingDir: desktop,
  entryPoints: [join(source, "vendor-src/workbook-runtime.js")], outfile: join(vendor, "workbook-runtime.js"),
  bundle: true, format: "esm", platform: "browser", target: "chrome142", minify: true, legalComments: "eof", metafile: true,
  nodePaths: [join(desktop, "node_modules")], define: { "process.env.NODE_ENV": '"production"' },
  plugins: [{ name: "dbfox-public-react-sdk", setup(context) {
    context.onResolve({ filter: /^react$/ }, () => ({ path: join(source, "vendor-src/host-react.js") }));
    context.onResolve({ filter: /^react-dom$/ }, () => ({ path: join(source, "vendor-src/host-react-dom.js") }));
  } }],
});
// Theme only the vendor's surrounding controls. Workbook cell formatting is
// source data drawn on canvas and is deliberately not rewritten here.
const cssPath = join(vendor, "workbook-runtime.css");
const css = postcss.parse(await readFile(cssPath, "utf8"));
css.prepend(postcss.rule({ selector: ".dbfox-workbook-view", nodes: [
  postcss.decl({ prop: "--tw-gradient-to", value: "transparent" }),
] }));
css.walkRules(rule => {
  if (rule.parent?.type === "atrule" && /keyframes$/i.test(rule.parent.name)) return;
  rule.selectors = rule.selectors.map(selector => selector.startsWith(".dbfox-workbook-view") ? selector
    : `.dbfox-workbook-view ${selector.replace(/^(?:html|body|:root)\b/, "")}`.trim());
});
css.walkDecls(declaration => {
  declaration.important = false;
  if (declaration.prop === "font-size") declaration.value = "var(--ui-font-caption)";
  if (declaration.prop === "font-weight" && /^\d+$/.test(declaration.value)) declaration.value = Number(declaration.value) > 500 ? "600" : "400";
  if (declaration.prop === "box-shadow" && declaration.value !== "none") declaration.value = "var(--shadow-card)";
  if (/^(?:color|background(?:-color)?|border(?:-[a-z-]+)?|fill|stroke)$/i.test(declaration.prop)) {
    const token = /border/.test(declaration.prop) ? "--border-default" : /background/.test(declaration.prop) ? "--agent-surface" : "--text-primary";
    declaration.value = declaration.value.replace(/#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|\b(?:white|black)\b/gi, color => {
      // Preserve alpha when theming vendor overlays; opaque selection masks
      // would cover the workbook's own canvas text and formatting.
      const rgba = color.match(/^rgba\([^,]+,[^,]+,[^,]+,\s*([\d.]+)\)$/i);
      const alpha = /^#[0-9a-f]{8}$/i.test(color) ? parseInt(color.slice(7), 16) / 255
        : /^#[0-9a-f]{4}$/i.test(color) ? parseInt(color.slice(4), 16) / 15
        : rgba ? Number(rgba[1]) : 1;
      return alpha < 1 ? `color-mix(in srgb, var(${token}) ${(alpha * 100).toFixed(3)}%, transparent)` : `var(${token})`;
    });
  }
});
await writeFile(cssPath, css.toString());
if (Object.keys(result.metafile.inputs).some(path => /node_modules[\\/]react[\\/](?:index|cjs[\\/]react(?:\.production)?\.)/.test(path)))
  throw new Error("Workbook vendor must share Host React");
const bytes = (await readFile(join(vendor, "workbook-runtime.js"))).byteLength;
if (bytes > 4 * 1024 * 1024) throw new Error("Workbook vendor exceeded its 4 MiB raw JS budget");
await copyFile(join(source, "vendor-src/licenses/fortune-sheet-MIT.txt"), join(vendor, "licenses/fortune-sheet-MIT.txt"));
const packages = new Map();
for (const input of Object.keys(result.metafile.inputs)) {
  if (!input.replaceAll("\\", "/").includes("node_modules/")) continue;
  let folder = dirname(resolve(desktop, input));
  while (folder !== dirname(folder)) {
    try {
      const pkg = JSON.parse(await readFile(join(folder, "package.json"), "utf8"));
      if (pkg.name && pkg.version) { packages.set(pkg.name, { root: folder, version: pkg.version, license: pkg.license || pkg.licenses?.map(value => value.type).join(" OR ") }); break; }
    } catch (error) { if (error.code !== "ENOENT") throw error; }
    folder = dirname(folder);
  }
}
for (const [name, pkg] of packages) {
  const licenses = (await readdir(pkg.root)).filter(file => /^licen[cs]e(?:[.-].*)?$/i.test(file));
  if (!licenses.length && !name.startsWith("@fortune-sheet/")) throw new Error(`Missing license text: ${name}`);
  for (const file of licenses) await copyFile(join(pkg.root, file), join(vendor, "licenses", name.replaceAll("/", "-").replaceAll("@", "") + "-" + file));
}
await writeFile(join(vendor, "licenses/packages.json"), JSON.stringify(Object.fromEntries([...packages].map(([name, p]) => [name, { version: p.version, license: p.license }])), null, 2) + "\n");
await writeFile(join(vendor, "bundle-manifest.json"), JSON.stringify({ schemaVersion: 1, bytes,
  packages: { "@fortune-sheet/react": "1.0.4", "@fortune-sheet/core": "1.0.4", "uuid": "11.1.1" },
  hostReact: true }, null, 2) + "\n");
console.log(`Workbook vendor: ${bytes} bytes, shared Host React/ReactDOM`);
