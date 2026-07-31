import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { copyFile, mkdir, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import net from "node:net";

const sidecarName = process.platform === "win32"
  ? "dbfox-engine-x86_64-pc-windows-msvc.exe"
  : "dbfox-engine";
const sidecarPath = fileURLToPath(
  new URL(`../src-tauri/binaries/${sidecarName}`, import.meta.url),
);

if (!existsSync(sidecarPath)) {
  throw new Error(`Packaged sidecar not found: ${sidecarPath}`);
}

const runtimeDir = await mkdtemp(join(tmpdir(), "dbfox-sidecar-smoke-"));
const sourceDatabase = process.env.DBFOX_SMOKE_SOURCE_DATABASE;
if (sourceDatabase) {
  if (!existsSync(sourceDatabase)) {
    throw new Error(`Smoke-test source database not found: ${sourceDatabase}`);
  }
  const dataDir = join(runtimeDir, "data");
  await mkdir(dataDir, { recursive: true });
  await copyFile(sourceDatabase, join(dataDir, "dbfox_local.db"));
}
const port = await reservePort();
const token = randomBytes(32).toString("hex");
let stderr = "";
let stdout = "";
const child = spawn(sidecarPath, [], {
  cwd: runtimeDir,
  env: {
    ...process.env,
    DBFOX_ENGINE_PORT: String(port),
    DBFOX_ENGINE_TOKEN: token,
    DBFOX_RUNTIME_DIR: runtimeDir,
  },
  stdio: ["ignore", "pipe", "pipe"],
  windowsHide: true,
});
child.stdout?.setEncoding("utf8");
child.stdout?.on("data", (chunk) => {
  stdout = `${stdout}${chunk}`.slice(-8000);
});
child.stderr?.setEncoding("utf8");
child.stderr?.on("data", (chunk) => {
  stderr = `${stderr}${chunk}`.slice(-4000);
});

try {
  await Promise.race([
    waitUntilHealthy(child, port, () => stderr),
    new Promise((_, reject) => child.once("error", reject)),
  ]);
  assertControlProtocol(stdout, port);
  const authenticated = await fetch(`http://127.0.0.1:${port}/api/v1/datasources`, {
    headers: {
      "X-Local-Token": token,
      Origin: "http://tauri.localhost",
    },
    signal: AbortSignal.timeout(5000),
  });
  if (!authenticated.ok) {
    throw new Error(`Authenticated API returned HTTP ${authenticated.status}`);
  }
  process.stdout.write(JSON.stringify({
    status: "ok",
    pid: child.pid,
    port,
    health: "healthy",
    authenticated_api: "ok",
  }) + "\n");
} finally {
  await stopProcessTree(child);
  await rm(runtimeDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
}

function assertControlProtocol(output, selectedPort) {
  const ready = `DBFOX_ENGINE_READY {"port":${selectedPort}}`;
  if (!output.includes(ready)) {
    throw new Error(`Frozen sidecar omitted READY control event. stdout: ${output}`);
  }
  for (const stage of ["migrating", "maintaining", "recovering", "ready"]) {
    const event = `DBFOX_ENGINE_STAGE {"stage":"${stage}"}`;
    if (!output.includes(event)) {
      throw new Error(`Frozen sidecar omitted ${stage} control event. stdout: ${output}`);
    }
  }
}

async function reservePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  const selected = typeof address === "object" && address ? address.port : 0;
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  if (!selected) throw new Error("Unable to reserve a local smoke-test port");
  return selected;
}

async function waitUntilHealthy(processHandle, selectedPort, capturedStderr) {
  const deadline = Date.now() + 40_000;
  while (Date.now() < deadline) {
    if (processHandle.exitCode !== null) {
      throw new Error(
        `Frozen sidecar exited before health check (code ${processHandle.exitCode}): ${capturedStderr()}`,
      );
    }
    try {
      const response = await fetch(`http://127.0.0.1:${selectedPort}/api/v1/health`, {
        signal: AbortSignal.timeout(2000),
      });
      if (response.ok && (await response.json()).status === "healthy") return;
    } catch {
      // The one-file executable needs a few seconds to unpack and migrate its database.
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Frozen sidecar health check timed out: ${capturedStderr()}`);
}

async function stopProcessTree(processHandle) {
  if (!processHandle.pid || processHandle.exitCode !== null) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(processHandle.pid), "/T", "/F"], {
      stdio: "ignore",
      windowsHide: true,
    });
  } else {
    processHandle.kill("SIGTERM");
  }
  if (processHandle.exitCode !== null) return;
  await Promise.race([
    new Promise((resolve) => processHandle.once("exit", resolve)),
    new Promise((resolve) => setTimeout(resolve, 5000)),
  ]);
}
