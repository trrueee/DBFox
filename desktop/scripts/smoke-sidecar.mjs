import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { copyFile, mkdir, mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import net from "node:net";

const targetTriplet = authoritativeHostTuple();
const sidecarName = `dbfox-engine-${targetTriplet}${process.platform === "win32" ? ".exe" : ""}`;
const sidecarPath = fileURLToPath(
  new URL(`../src-tauri/binaries/${sidecarName}`, import.meta.url),
);

if (!existsSync(sidecarPath)) {
  throw new Error(`Packaged sidecar not found: ${sidecarPath}`);
}

// Keep the smoke runtime beneath the checked-out repository. On macOS,
// os.tmpdir() commonly returns a lexical /var/... path, while /var is a
// symlink to /private/var. The production runtime deliberately rejects any
// symlinked ancestor before destructive legacy cleanup, so using os.tmpdir()
// tested an impossible production path and made the frozen smoke fail before
// health. The checkout is a normal, private directory on every CI runner and
// exercises the same no-link runtime-root contract as the installed app.
const runtimeDir = await mkdtemp(join(process.cwd(), ".dbfox-sidecar-smoke-"));
const sourceDatabase = process.env.DBFOX_SMOKE_SOURCE_DATABASE;
if (sourceDatabase) {
  if (!existsSync(sourceDatabase)) {
    throw new Error(`Smoke-test source database not found: ${sourceDatabase}`);
  }
  const dataDir = join(runtimeDir, "data");
  await mkdir(dataDir, { recursive: true });
  await copyFile(sourceDatabase, join(dataDir, "dbfox_local.db"));
}
const smokeSourcePath = join(runtimeDir, "smoke-source.sqlite");
createSmokeSourceDatabase(smokeSourcePath);
const port = await reservePort();
let token = randomBytes(32).toString("hex");
let stderr = "";
let stdout = "";
let child = launchSidecar(token);

try {
  await Promise.race([
    waitUntilHealthy(child, port, token, () => stderr),
    new Promise((_, reject) => child.once("error", reject)),
  ]);
  assertControlProtocol(stdout, port);
  for (const path of ["/", "/api/v1/health", "/api/v1/conversations"]) {
    await expectRejectedToken(path);
    await expectRejectedToken(path, "wrong-token");
  }

  for (const resource of ["datasources", "conversations"]) {
    const authenticated = await fetch(`http://127.0.0.1:${port}/api/v1/${resource}`, {
      headers: {
        "X-Local-Token": token,
        Origin: "http://tauri.localhost",
      },
      signal: AbortSignal.timeout(5000),
    });
    if (!authenticated.ok) {
      const body = await authenticated.text();
      throw new Error(
        `Authenticated ${resource} API returned HTTP ${authenticated.status}: ${body.slice(0, 500)}`,
      );
    }
  }

  const frozenContract = await verifyFrozenDataContract(smokeSourcePath);

  const oldToken = token;
  await stopProcessTree(child);
  token = randomBytes(32).toString("hex");
  stdout = "";
  stderr = "";
  child = launchSidecar(token);
  await Promise.race([
    waitUntilHealthy(child, port, token, () => stderr),
    new Promise((_, reject) => child.once("error", reject)),
  ]);
  assertControlProtocol(stdout, port);
  await expectRejectedToken("/api/v1/health", oldToken);
  const reloadedDatasources = await apiJson("/api/v1/datasources");
  if (!reloadedDatasources.some((item) => item.id === frozenContract.datasourceId)) {
    throw new Error("Frozen sidecar restart did not reload the smoke datasource");
  }
  const reloadedConversation = await apiJson(
    `/api/v1/conversations/${frozenContract.sessionId}`,
  );
  if (!Array.isArray(reloadedConversation.runs) || reloadedConversation.runs.length < 2) {
    throw new Error("Frozen sidecar restart did not reload the durable multi-turn run history");
  }

  process.stdout.write(JSON.stringify({
    status: "ok",
    pid: child.pid,
    port,
    health: "healthy",
    authenticated_api: "ok",
    stale_token_rejected: true,
    schema_sync: "ok",
    readonly_query: "ok",
    result_artifact: "ok",
    durable_turns: reloadedConversation.runs.length,
    restart_reload: "ok",
    target_triplet: targetTriplet,
  }) + "\n");
} finally {
  await stopProcessTree(child);
  if (process.env.DBFOX_SMOKE_KEEP_RUNTIME === "1") {
    process.stderr.write(`Frozen smoke runtime preserved at ${runtimeDir}\n`);
  } else {
    await rm(runtimeDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  }
}

function authoritativeHostTuple() {
  const result = spawnSync("rustc", ["--print", "host-tuple"], {
    encoding: "utf8",
    windowsHide: true,
  });
  const tuple = result.stdout?.trim();
  if (result.error || result.status !== 0 || !tuple) {
    const detail = result.error?.message || result.stderr?.trim() || `exit ${result.status}`;
    throw new Error(`Unable to resolve Sidecar target with rustc --print host-tuple: ${detail}`);
  }
  return tuple;
}

function assertControlProtocol(output, selectedPort) {
  const readyLine = output
    .split(/\r?\n/)
    .find((line) => line.startsWith("DBFOX_ENGINE_READY "));
  if (!readyLine) {
    throw new Error(`Frozen sidecar omitted READY control event. stdout: ${output}`);
  }
  let ready;
  try {
    ready = JSON.parse(readyLine.slice("DBFOX_ENGINE_READY ".length));
  } catch (error) {
    throw new Error(`Frozen sidecar emitted invalid READY JSON: ${error}`);
  }
  const requiredCapabilities = ["http", "sse", "problem-details"];
  if (ready.port !== selectedPort
    || ready.protocolVersion !== 1
    || ready.serverInfo?.name !== "dbfox-engine"
    || !ready.serverInfo?.version
    || !requiredCapabilities.every((capability) => ready.capabilities?.includes(capability))) {
    throw new Error(`Frozen sidecar emitted an incompatible READY payload: ${readyLine}`);
  }
  for (const stage of ["migrating", "maintaining", "recovering", "ready"]) {
    const event = `DBFOX_ENGINE_STAGE {"stage":"${stage}"}`;
    if (!output.includes(event)) {
      throw new Error(`Frozen sidecar omitted ${stage} control event. stdout: ${output}`);
    }
  }
}

function launchSidecar(runtimeToken) {
  const processHandle = spawn(sidecarPath, [], {
    cwd: runtimeDir,
    env: {
      ...process.env,
      DBFOX_ENGINE_PORT: String(port),
      DBFOX_ENGINE_TOKEN: runtimeToken,
      DBFOX_RUNTIME_DIR: runtimeDir,
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  processHandle.stdout?.setEncoding("utf8");
  processHandle.stdout?.on("data", (chunk) => {
    stdout = `${stdout}${chunk}`.slice(-8000);
  });
  processHandle.stderr?.setEncoding("utf8");
  processHandle.stderr?.on("data", (chunk) => {
    stderr = `${stderr}${chunk}`.slice(-4000);
  });
  return processHandle;
}

function createSmokeSourceDatabase(databasePath) {
  const script = [
    "import sqlite3, sys",
    "connection = sqlite3.connect(sys.argv[1])",
    "connection.executescript(\"\"\"CREATE TABLE smoke_items (id INTEGER PRIMARY KEY, name TEXT NOT NULL); INSERT INTO smoke_items (id, name) VALUES (1, 'alpha'), (2, 'beta');\"\"\")",
    "connection.commit()",
    "connection.close()",
  ].join("; ");
  const result = spawnSync(process.env.DBFOX_SMOKE_PYTHON || "python", [
    "-c",
    script,
    databasePath,
  ], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.error || result.status !== 0) {
    const detail = result.error?.message || result.stderr?.trim() || `exit ${result.status}`;
    throw new Error(`Unable to create the frozen-smoke SQLite source: ${detail}`);
  }
}

async function apiJson(path, { method = "GET", body } = {}) {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    method,
    headers: {
      "X-Local-Token": token,
      Origin: "http://tauri.localhost",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) {
    const responseBody = await response.text();
    throw new Error(
      `${method} ${path} returned HTTP ${response.status}: ${responseBody.slice(0, 500)}`,
    );
  }
  return response.json();
}

async function verifyFrozenDataContract(databasePath) {
  const datasource = await apiJson("/api/v1/datasources", {
    method: "POST",
    body: {
      name: "Frozen smoke SQLite",
      db_type: "sqlite",
      database_name: databasePath,
      is_read_only: true,
      env: "test",
    },
  });
  if (!datasource.id) throw new Error("Frozen datasource creation returned no id");

  const sync = await apiJson(`/api/v1/datasources/${datasource.id}/sync`, {
    method: "POST",
    body: { ai_enrich: false },
  });
  if (!sync.ok || sync.tablesSynced < 1) {
    throw new Error(`Frozen schema sync returned an invalid result: ${JSON.stringify(sync)}`);
  }
  const tables = await apiJson(
    `/api/v1/schema/tables?datasource_id=${encodeURIComponent(datasource.id)}`,
  );
  if (!tables.some((table) => table.table_name === "smoke_items")) {
    throw new Error("Frozen schema catalog omitted smoke_items");
  }

  const sessionId = `frozen-smoke-${randomBytes(12).toString("hex")}`;
  const first = await apiJson("/api/v1/agent/console/execute", {
    method: "POST",
    body: {
      datasourceId: datasource.id,
      sql: "SELECT id, name FROM smoke_items ORDER BY id",
      question: "Frozen result contract",
      sessionId,
      executionId: `smoke-query-${randomBytes(8).toString("hex")}`,
    },
  });
  if (!first.resultArtifactId || !first.runId) {
    throw new Error("Frozen console query omitted its durable result artifact");
  }
  const page = await apiJson(`/api/v1/artifacts/${first.resultArtifactId}/page`, {
    method: "POST",
    body: { page: 1, pageSize: 10, countMode: "exact" },
  });
  if (page.rowCount !== 2 || page.rows?.[0]?.name !== "alpha") {
    throw new Error(`Frozen result artifact could not be replayed: ${JSON.stringify(page)}`);
  }

  const second = await apiJson("/api/v1/agent/console/execute", {
    method: "POST",
    body: {
      datasourceId: datasource.id,
      sql: "SELECT COUNT(*) AS total FROM smoke_items",
      question: "Frozen durable second turn",
      sessionId,
      executionId: `smoke-query-${randomBytes(8).toString("hex")}`,
    },
  });
  if (!second.runId || second.runId === first.runId) {
    throw new Error("Frozen durable second turn did not create an independent run");
  }
  const snapshot = await apiJson(`/api/v1/conversations/${sessionId}`);
  if (!Array.isArray(snapshot.runs) || snapshot.runs.length < 2) {
    throw new Error("Frozen conversation projection omitted durable multi-turn history");
  }
  return { datasourceId: datasource.id, sessionId };
}

async function expectRejectedToken(path, rejectedToken) {
  const headers = { Origin: "http://tauri.localhost" };
  if (rejectedToken) headers["X-Local-Token"] = rejectedToken;
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    headers,
    signal: AbortSignal.timeout(5000),
  });
  if (response.status !== 401) {
    throw new Error(`${path} rejected-token probe returned HTTP ${response.status}, expected 401`);
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

async function waitUntilHealthy(processHandle, selectedPort, token, capturedStderr) {
  const deadline = Date.now() + 40_000;
  while (Date.now() < deadline) {
    if (processHandle.exitCode !== null) {
      throw new Error(
        `Frozen sidecar exited before health check (code ${processHandle.exitCode}): ${capturedStderr()}`,
      );
    }
    try {
      const response = await fetch(`http://127.0.0.1:${selectedPort}/api/v1/health`, {
        headers: {
          "X-Local-Token": token,
          Origin: "http://tauri.localhost",
        },
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
