import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const desktopDirectory = resolve(scriptDirectory, "..");
const toolchainFile = resolve(desktopDirectory, "src-tauri", "rust-toolchain.toml");
const toolchainSource = readFileSync(toolchainFile, "utf8");
const channel = toolchainSource.match(/^\s*channel\s*=\s*"([^"]+)"/m)?.[1];

if (!channel) {
  throw new Error(`Unable to read Rust channel from ${toolchainFile}`);
}

const [command, ...args] = process.argv.slice(2);
if (!command) {
  throw new Error("A Rust-backed command is required.");
}

const environment = { ...process.env };
if (process.platform === "win32") {
  environment.RUSTUP_TOOLCHAIN = `${channel}-x86_64-pc-windows-msvc`;
}

const result = spawnSync(command, args, {
  cwd: desktopDirectory,
  env: environment,
  stdio: "inherit",
  shell: process.platform === "win32",
});

if (result.error) {
  throw result.error;
}
process.exit(result.status ?? 1);
