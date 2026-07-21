import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { formatBundleReport, inspectBundle } from "./bundleBudget.mjs";

const scriptsDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const distDir = process.env.DBFOX_BUNDLE_DIST_DIR || resolve(scriptsDir, "..", "dist");
const report = inspectBundle(distDir);
console.log(formatBundleReport(report));
