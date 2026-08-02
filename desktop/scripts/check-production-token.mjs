import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";

const desktopDirectory = resolve(import.meta.dirname, "..");
const distDirectory = resolve(desktopDirectory, "dist");
const envPath = resolve(desktopDirectory, ".env.local");

function filesBelow(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? filesBelow(path) : [path];
  });
}

const knownTokens = new Set();
if (existsSync(envPath)) {
  const envSource = readFileSync(envPath, "utf8");
  const match = envSource.match(/^VITE_LOCAL_ENGINE_TOKEN\s*=\s*["']?([^\s"']+)/m);
  if (match?.[1]) knownTokens.add(match[1]);
}
if (process.env.VITE_LOCAL_ENGINE_TOKEN) {
  knownTokens.add(process.env.VITE_LOCAL_ENGINE_TOKEN);
}

const leaks = [];
for (const path of filesBelow(distDirectory)) {
  if (statSync(path).size === 0) continue;
  const content = readFileSync(path);
  for (const token of knownTokens) {
    if (token.length >= 16 && content.includes(Buffer.from(token))) {
      leaks.push(path);
    }
  }
}

if (leaks.length > 0) {
  throw new Error(`Production bundle contains a development engine token: ${leaks.join(", ")}`);
}
console.log("  ✓ Production bundle contains no known development engine token");
