import { execFile } from "node:child_process";
import { access, mkdtemp, readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const runtimeRoot = await mkdtemp(join(process.cwd(), ".electron-packaged-smoke-"));
const executable = await findExecutable();
const resultPath = join(runtimeRoot, "electron-smoke-result.json");
const output = [];
let child;
let succeeded = false;

try {
  child = execFile(executable, [], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      DBFOX_ELECTRON_SMOKE: "1",
      DBFOX_RUNTIME_DIR: runtimeRoot,
    },
    windowsHide: true,
    maxBuffer: 1024 * 1024,
  });
  child.stdout?.on("data", (chunk) => output.push(chunk));
  child.stderr?.on("data", (chunk) => output.push(chunk));

  const exitedBeforeProof = new Promise((_, reject) => {
    child.once("error", reject);
    child.once("exit", async (code, signal) => {
      try {
        await access(resultPath);
      } catch {
        reject(new Error(
          `Packaged Electron exited before proof (code=${String(code)}, signal=${String(signal)})`,
        ));
      }
    });
  });
  await Promise.race([waitForFile(resultPath, 60_000), exitedBeforeProof]);
  const proof = JSON.parse(await readFile(resultPath, "utf8"));
  if (proof.marker !== "DBFOX_ELECTRON_HOST_READY"
    || proof.runtime !== "electron"
    || proof.generation !== 1
    || proof.inactiveDlcAssetStatus !== 403
    || proof.packaged !== true) {
    throw new Error(`Unexpected packaged Electron proof: ${JSON.stringify(proof)}`);
  }
  console.log(JSON.stringify(proof));
  succeeded = true;
} catch (error) {
  process.stderr.write(Buffer.concat(output).toString("utf8").slice(-16_384));
  process.stderr.write(`\nPackaged Electron smoke runtime preserved at ${runtimeRoot}\n`);
  throw error;
} finally {
  if (child?.pid && child.exitCode === null) await terminate(child.pid);
  if (succeeded) await rm(runtimeRoot, { recursive: true, force: true });
}

async function findExecutable() {
  const candidates = process.platform === "win32"
    ? [join("release-electron", "win-unpacked", "DBFox.exe")]
    : process.platform === "darwin"
      ? [
          join("release-electron", `mac-${process.arch}`, "DBFox.app", "Contents", "MacOS", "DBFox"),
          join("release-electron", "mac", "DBFox.app", "Contents", "MacOS", "DBFox"),
        ]
      : [
          join("release-electron", "linux-unpacked", "dbfox"),
          join("release-electron", "linux-unpacked", "DBFox"),
        ];
  for (const candidate of candidates) {
    try {
      await access(candidate);
      return candidate;
    } catch {
      // Continue to the next platform-specific builder layout.
    }
  }
  throw new Error(`Packaged Electron executable not found: ${candidates.join(", ")}`);
}

async function waitForFile(path, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      await access(path);
      return;
    } catch {
      await new Promise((resolveDelay) => setTimeout(resolveDelay, 200));
    }
  }
  throw new Error("Timed out waiting for packaged Electron smoke proof");
}

async function terminate(pid) {
  try {
    if (process.platform === "win32") {
      await execFileAsync("taskkill", ["/PID", String(pid), "/T", "/F"], { windowsHide: true });
    } else {
      process.kill(pid, "SIGTERM");
    }
  } catch {
    // The application normally exits itself immediately after writing proof.
  }
}
