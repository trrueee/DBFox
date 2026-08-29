import { gzipSync } from "node:zlib";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

export const ENTRY_BUDGET = Object.freeze({
  maxRawBytes: 650 * 1024,
  maxGzipBytes: 200 * 1024,
});

const REQUIRED_ROUTE_CHUNKS = Object.freeze([
  "ConversationWorkspace-",
]);

function metric(filePath) {
  const source = readFileSync(filePath);
  return Object.freeze({ rawBytes: source.length, gzipBytes: gzipSync(source, { level: 9 }).length });
}

function formatBytes(bytes) {
  return `${bytes.toLocaleString("en-US")} B`;
}

function assertWithinBudget(label, actual, budget) {
  const violations = [];
  if (actual.rawBytes > budget.maxRawBytes) {
    violations.push(`raw ${formatBytes(actual.rawBytes)} > ${formatBytes(budget.maxRawBytes)}`);
  }
  if (actual.gzipBytes > budget.maxGzipBytes) {
    violations.push(`gzip ${formatBytes(actual.gzipBytes)} > ${formatBytes(budget.maxGzipBytes)}`);
  }
  if (violations.length > 0) {
    throw new Error(`${label} exceeds its bundle budget: ${violations.join(", ")}`);
  }
}

export function inspectBundle(distDir) {
  const assetsDir = join(distDir, "assets");
  const files = readdirSync(assetsDir).filter((file) => file.endsWith(".js"));
  const indexHtml = readFileSync(join(distDir, "index.html"), "utf8");
  const entryMatch = indexHtml.match(/<script\b[^>]*\bsrc=["'](?:\.\/)?assets\/([^"']+\.js)["'][^>]*>/i);
  const entry = entryMatch?.[1];
  if (!entry || !files.includes(entry)) {
    throw new Error(`Could not find the Vite entry asset declared by ${join(distDir, "index.html")}.`);
  }

  const missingRouteChunks = REQUIRED_ROUTE_CHUNKS.filter((prefix) => !files.some((file) => file.startsWith(prefix)));
  if (missingRouteChunks.length > 0) {
    throw new Error(`Core workspace routes must remain independently loaded: ${missingRouteChunks.join(", ")}`);
  }

  const entryMetrics = metric(join(assetsDir, entry));
  assertWithinBudget("Initial desktop entry", entryMetrics, ENTRY_BUDGET);

  return Object.freeze({
    entry: Object.freeze({ file: entry, ...entryMetrics }),
  });
}

export function formatBundleReport(report) {
  return [
    `Initial entry: ${report.entry.file} · raw ${formatBytes(report.entry.rawBytes)} · gzip ${formatBytes(report.entry.gzipBytes)}`,
  ].join("\n");
}
