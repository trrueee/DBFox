import { createHash, randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync } from "node:child_process";
import net from "node:net";

const rendererOrigin = "dbfox-app://localhost";
const targetTriplet = platformTargetTriplet();
const sidecarName = `dbfox-engine${process.platform === "win32" ? ".exe" : ""}`;
const sidecarPath = fileURLToPath(
  new URL(`../electron-resources/sidecar/${sidecarName}`, import.meta.url),
);
const repositoryRoot = fileURLToPath(new URL("../../", import.meta.url));
const systemDlcDirectory = fileURLToPath(
  new URL("../electron-resources/system-dlcs/", import.meta.url),
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
const dlcFixture = buildPackagedDlcFixture(join(runtimeDir, "fixture-packages"));
const githubDlcFixture = buildPackagedGithubDlcFixture(join(runtimeDir, "fixture-packages"));
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

  for (const resource of ["projects", "conversations", "dlcs"]) {
    const authenticated = await fetch(`http://127.0.0.1:${port}/api/v1/${resource}`, {
      headers: {
        "X-Local-Token": token,
        Origin: rendererOrigin,
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

  await verifySystemDlcsActive();
  const frozenContract = await verifyFrozenDataContract(smokeSourcePath);
  const dlcContract = await preparePackagedDlcLifecycle(dlcFixture);
  const githubDlcContract = await preparePackagedGithubDlcLifecycle(
    githubDlcFixture,
    frozenContract.projectId,
  );

  await restartFrozenSidecar();
  const reloadedProfiles = await apiJson(
    `/api/v1/dlcs/dbfox.data/operations/profiles.list?project_id=${encodeURIComponent(frozenContract.projectId)}`,
    { method: "POST", body: {} },
  );
  if (!reloadedProfiles.profiles?.some((item) => item.databases?.some((database) => database.id === frozenContract.databaseId))) {
    throw new Error("Frozen sidecar restart did not reload the System Data database resource");
  }
  const reloadedConversation = await apiJson(
    `/api/v1/conversations/${frozenContract.sessionId}`,
  );
  if (!Array.isArray(reloadedConversation.runs) || reloadedConversation.runs.length < 2) {
    throw new Error("Frozen sidecar restart did not reload the durable multi-turn run history");
  }
  await verifyPackagedDlcActive(dlcContract);
  await verifyPackagedGithubDlcActive(githubDlcContract);
  await preparePackagedDlcUpdate(dlcContract);

  await restartFrozenSidecar();
  await verifyPackagedDlcActiveVersion(
    dlcContract,
    dlcContract.update_package_digest,
    "2.0.0",
  );
  const rollback = await apiJson(
    `/api/v1/dlcs/acme.echo/versions/${dlcContract.package_digest}/select`,
    { method: "POST" },
  );
  if (rollback.state !== "enable_pending_restart"
    || rollback.selected_digest !== dlcContract.package_digest
    || rollback.active_digest !== dlcContract.update_package_digest) {
    throw new Error(`Packaged DLC rollback selection was not restart-bound: ${JSON.stringify(rollback)}`);
  }

  await restartFrozenSidecar();
  await verifyPackagedDlcActive(dlcContract);
  const reselectedUpdate = await apiJson(
    `/api/v1/dlcs/acme.echo/versions/${dlcContract.update_package_digest}/select`,
    { method: "POST" },
  );
  if (reselectedUpdate.state !== "enable_pending_restart"
    || reselectedUpdate.active_digest !== dlcContract.package_digest) {
    throw new Error(`Packaged DLC update reselection lost active truth: ${JSON.stringify(reselectedUpdate)}`);
  }
  const disabled = await apiJson("/api/v1/dlcs/acme.echo/disable", { method: "POST" });
  if (disabled.state !== "disable_pending_restart" || !disabled.active) {
    throw new Error(`DLC disable did not preserve active truth until restart: ${JSON.stringify(disabled)}`);
  }
  const githubDisabled = await apiJson("/api/v1/dlcs/dbfox.github/disable", { method: "POST" });
  if (githubDisabled.state !== "disable_pending_restart" || !githubDisabled.active) {
    throw new Error(
      `dbfox.github disable did not preserve active truth until restart: ${JSON.stringify(githubDisabled)}`,
    );
  }

  await restartFrozenSidecar();
  const dlcEvidence = await verifyPackagedDlcInactiveAndUninstall(dlcContract);
  const githubDlcEvidence = await verifyPackagedGithubDlcInactiveAndUninstall(
    githubDlcContract,
  );

  const evidence = {
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
    packaged_dlc: dlcEvidence,
    packaged_github_dlc: githubDlcEvidence,
    target_triplet: targetTriplet,
  };
  const reportsDir = join(repositoryRoot, "reports");
  await mkdir(reportsDir, { recursive: true });
  await writeFile(
    join(reportsDir, `dlc-packaged-e2e-${targetTriplet}.json`),
    `${JSON.stringify(evidence, null, 2)}\n`,
    "utf8",
  );

  process.stdout.write(`${JSON.stringify(evidence)}\n`);
} finally {
  await stopProcessTree(child);
  if (process.env.DBFOX_SMOKE_KEEP_RUNTIME === "1") {
    process.stderr.write(`Frozen smoke runtime preserved at ${runtimeDir}\n`);
  } else {
    await rm(runtimeDir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
  }
}

function platformTargetTriplet() {
  const architecture = { x64: "x86_64", arm64: "aarch64" }[process.arch];
  const suffix = {
    win32: "pc-windows-msvc",
    darwin: "apple-darwin",
    linux: "unknown-linux-gnu",
  }[process.platform];
  if (!architecture || !suffix) {
    throw new Error(`Unsupported Sidecar target: ${process.platform}/${process.arch}`);
  }
  return `${architecture}-${suffix}`;
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
      DBFOX_SYSTEM_DLC_DIR: systemDlcDirectory,
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

async function restartFrozenSidecar() {
  const staleToken = token;
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
  await expectRejectedToken("/api/v1/health", staleToken);
}

function createSmokeSourceDatabase(databasePath) {
  const script = [
    "import sqlite3, sys",
    "connection = sqlite3.connect(sys.argv[1])",
    "connection.executescript(\"\"\"CREATE TABLE smoke_items (id INTEGER PRIMARY KEY, name TEXT NOT NULL); INSERT INTO smoke_items (id, name) VALUES (1, 'alpha'), (2, 'beta');\"\"\")",
    "connection.commit()",
    "connection.close()",
  ].join("; ");
  const result = spawnSync(resolveSmokePython(), [
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

function buildPackagedDlcFixture(outputDir) {
  const result = spawnSync(resolveSmokePython(), [
    "-m",
    "verification.testkit.build_dlc_e2e_fixture",
    "--output-dir",
    outputDir,
  ], {
    cwd: repositoryRoot,
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.error || result.status !== 0) {
    const detail = result.error?.message || result.stderr?.trim() || `exit ${result.status}`;
    throw new Error(`Unable to build packaged DLC fixture: ${detail}`);
  }
  const outputLine = result.stdout.trim().split(/\r?\n/).at(-1);
  let fixture;
  try {
    fixture = JSON.parse(outputLine || "");
  } catch (error) {
    throw new Error(`Packaged DLC fixture builder emitted invalid JSON: ${error}`);
  }
  if (!existsSync(fixture.valid_archive)
    || !existsSync(fixture.update_archive)
    || !existsSync(fixture.tampered_archive)) {
    throw new Error(`Packaged DLC fixture builder omitted its archives: ${JSON.stringify(fixture)}`);
  }
  return fixture;
}

function buildPackagedGithubDlcFixture(outputDir) {
  const result = spawnSync(resolveSmokePython(), [
    "-m",
    "scripts.build_dbfox_github_dlc_fixture",
    "--output-dir",
    outputDir,
  ], {
    cwd: repositoryRoot,
    encoding: "utf8",
    windowsHide: true,
  });
  if (result.error || result.status !== 0) {
    const detail = result.error?.message || result.stderr?.trim() || `exit ${result.status}`;
    throw new Error(`Unable to build dbfox.github DLC fixture: ${detail}`);
  }
  const outputLine = result.stdout.trim().split(/\r?\n/).at(-1);
  let fixture;
  try {
    fixture = JSON.parse(outputLine || "");
  } catch (error) {
    throw new Error(`dbfox.github fixture builder emitted invalid JSON: ${error}`);
  }
  if (!existsSync(fixture.archive)) {
    throw new Error(`dbfox.github fixture builder omitted its archive: ${JSON.stringify(fixture)}`);
  }
  return fixture;
}

function resolveSmokePython() {
  const configured = process.env.SIDECAR_PYTHON || process.env.DBFOX_SMOKE_PYTHON;
  if (!configured) return "python";
  if (isAbsolute(configured)) return configured;
  if (configured.includes("/") || configured.includes("\\")) {
    return resolve(repositoryRoot, configured);
  }
  return configured;
}

async function preparePackagedDlcLifecycle(fixture) {
  const initialList = await apiJson("/api/v1/dlcs");
  if (initialList.dlcs.some((item) => item.dlc_id === "acme.echo")) {
    throw new Error("Packaged DLC fixture was unexpectedly installed before the test");
  }
  const systemData = initialList.dlcs.find((item) => item.dlc_id === "dbfox.data");
  const systemWorkspace = initialList.dlcs.find((item) => item.dlc_id === "dbfox.workspace");
  if (!systemData || !systemData.desired_enabled || !systemData.active) {
    throw new Error(`dbfox.data System DLC is inactive: ${JSON.stringify(systemData)}`);
  }
  if (!systemWorkspace || !systemWorkspace.desired_enabled || !systemWorkspace.active) {
    throw new Error(`dbfox.workspace System DLC is inactive: ${JSON.stringify(systemWorkspace)}`);
  }

  for (const endpoint of ["/api/v1/dlcs/packages/inspect", "/api/v1/dlcs/install"]) {
    await expectApiProblem(endpoint, {
      method: "POST",
      body: { archive_path: fixture.tampered_archive },
      expectedStatus: 400,
      expectedCode: "HASH_MISMATCH",
    });
  }
  const afterTamper = await apiJson("/api/v1/dlcs");
  if (afterTamper.dlcs.some((item) => item.dlc_id === "acme.echo")) {
    throw new Error("Tampered DLC package entered the installed registry");
  }

  const inspection = await apiJson("/api/v1/dlcs/packages/inspect", {
    method: "POST",
    body: { archive_path: fixture.valid_archive },
  });
  if (inspection.package_digest !== fixture.package_digest
    || inspection.publisher_fingerprint !== fixture.publisher_fingerprint
    || inspection.trust_required !== true
    || inspection.backend_entrypoint_present !== true
    || inspection.frontend_entrypoint_present !== true) {
    throw new Error(`Packaged DLC inspection returned an invalid contract: ${JSON.stringify(inspection)}`);
  }
  await expectApiProblem("/api/v1/dlcs/install", {
    method: "POST",
    body: { archive_path: fixture.valid_archive },
    expectedStatus: 409,
    expectedCode: "TRUST_REQUIRED",
  });

  const trust = await apiJson("/api/v1/dlcs/publishers/trust", {
    method: "POST",
    body: {
      archive_path: fixture.valid_archive,
      package_digest: fixture.package_digest,
      publisher_fingerprint: fixture.publisher_fingerprint,
    },
  });
  if (!trust.trusted || trust.publisher_fingerprint !== fixture.publisher_fingerprint) {
    throw new Error(`Packaged DLC publisher trust failed: ${JSON.stringify(trust)}`);
  }

  const installed = await apiJson("/api/v1/dlcs/install", {
    method: "POST",
    body: { archive_path: fixture.valid_archive },
  });
  if (installed.state !== "installed_disabled"
    || installed.desired_enabled
    || installed.active
    || installed.selected_digest !== fixture.package_digest) {
    throw new Error(`Packaged DLC did not install disabled: ${JSON.stringify(installed)}`);
  }

  const markerPath = join(runtimeDir, "dlcs", "data", "acme.echo", "activation-marker.txt");
  if (existsSync(markerPath)) {
    throw new Error("Packaged DLC backend executed during inspect, trust, or install");
  }
  await expectApiProblem("/api/v1/dlcs/acme.echo/operations/echo", {
    method: "POST",
    body: { message: "must not execute before restart" },
    expectedStatus: 404,
    expectedCode: "DLC_NOT_ACTIVE",
  });

  const enabled = await apiJson("/api/v1/dlcs/acme.echo/enable", { method: "POST" });
  if (enabled.state !== "enable_pending_restart" || !enabled.desired_enabled || enabled.active) {
    throw new Error(`Packaged DLC enable did not require restart: ${JSON.stringify(enabled)}`);
  }
  if (existsSync(markerPath)) {
    throw new Error("Packaged DLC backend executed before the controlled restart");
  }

  return {
    ...fixture,
    markerPath,
    packageDir: join(runtimeDir, "dlcs", "packages", `sha256-${fixture.package_digest}`),
    updatePackageDir: join(
      runtimeDir,
      "dlcs",
      "packages",
      `sha256-${fixture.update_package_digest}`,
    ),
  };
}

async function preparePackagedDlcUpdate(contract) {
  const markerBeforeInstall = await readFile(contract.markerPath, "utf8");
  const inspection = await apiJson("/api/v1/dlcs/packages/inspect", {
    method: "POST",
    body: { archive_path: contract.update_archive },
  });
  if (inspection.version !== "2.0.0"
    || inspection.package_digest !== contract.update_package_digest
    || inspection.trust_required) {
    throw new Error(`Packaged DLC update inspection was invalid: ${JSON.stringify(inspection)}`);
  }
  const installed = await apiJson("/api/v1/dlcs/install", {
    method: "POST",
    body: { archive_path: contract.update_archive },
  });
  if (installed.selected_digest !== contract.package_digest
    || installed.active_digest !== contract.package_digest
    || installed.installed_versions.length !== 2
    || !existsSync(contract.packageDir)
    || !existsSync(contract.updatePackageDir)
    || (await readFile(contract.markerPath, "utf8")) !== markerBeforeInstall) {
    throw new Error(`Installing an update changed selection, execution, or old bytes: ${JSON.stringify(installed)}`);
  }

  const selected = await apiJson(
    `/api/v1/dlcs/acme.echo/versions/${contract.update_package_digest}/select`,
    { method: "POST" },
  );
  if (selected.state !== "enable_pending_restart"
    || selected.selected_digest !== contract.update_package_digest
    || selected.active_digest !== contract.package_digest
    || (await readFile(contract.markerPath, "utf8")) !== markerBeforeInstall) {
    throw new Error(`Selecting an update mutated active runtime truth: ${JSON.stringify(selected)}`);
  }
  await expectApiProblem(
    `/api/v1/dlcs/acme.echo/versions/${contract.update_package_digest}`,
    { method: "DELETE", expectedStatus: 409, expectedCode: "DLC_VERSION_SELECTED" },
  );
  await expectApiProblem(
    `/api/v1/dlcs/acme.echo/versions/${contract.package_digest}`,
    { method: "DELETE", expectedStatus: 409, expectedCode: "DLC_VERSION_ACTIVE" },
  );
}

async function preparePackagedGithubDlcLifecycle(fixture, projectId) {
  const initialList = await apiJson("/api/v1/dlcs");
  if (initialList.dlcs.some((item) => item.dlc_id === "dbfox.github")) {
    throw new Error("dbfox.github was unexpectedly installed before the conformance flow");
  }
  await expectApiProblem("/api/v1/dlcs/dbfox.github/operations/bindings.list", {
    method: "POST",
    body: {},
    expectedStatus: 404,
    expectedCode: "DLC_NOT_ACTIVE",
  });

  const statePath = join(runtimeDir, "dlcs", "data", "dbfox.github", "state.sqlite3");
  const stateBeforeInstall = await fileDigestOrNull(statePath);
  const inspection = await apiJson("/api/v1/dlcs/packages/inspect", {
    method: "POST",
    body: { archive_path: fixture.archive },
  });
  if (inspection.dlc_id !== "dbfox.github"
    || inspection.package_digest !== fixture.package_digest
    || inspection.publisher_fingerprint !== fixture.publisher_fingerprint
    || inspection.trust_required !== true
    || inspection.permissions.join(",") !== "network:api.github.com") {
    throw new Error(`dbfox.github inspection returned an invalid contract: ${JSON.stringify(inspection)}`);
  }
  await apiJson("/api/v1/dlcs/publishers/trust", {
    method: "POST",
    body: {
      archive_path: fixture.archive,
      package_digest: fixture.package_digest,
      publisher_fingerprint: fixture.publisher_fingerprint,
    },
  });
  const installed = await apiJson("/api/v1/dlcs/install", {
    method: "POST",
    body: { archive_path: fixture.archive },
  });
  if (installed.state !== "installed_disabled"
    || installed.desired_enabled
    || installed.active
    || installed.selected_digest !== fixture.package_digest) {
    throw new Error(`dbfox.github did not install disabled: ${JSON.stringify(installed)}`);
  }

  if (await fileDigestOrNull(statePath) !== stateBeforeInstall) {
    throw new Error("dbfox.github altered DLC-owned state during inspect, trust, or install");
  }
  const enabled = await apiJson("/api/v1/dlcs/dbfox.github/enable", { method: "POST" });
  if (enabled.state !== "enable_pending_restart" || !enabled.desired_enabled || enabled.active) {
    throw new Error(`dbfox.github enable did not require restart: ${JSON.stringify(enabled)}`);
  }
  if (await fileDigestOrNull(statePath) !== stateBeforeInstall) {
    throw new Error("dbfox.github altered DLC-owned state before the controlled restart");
  }

  return {
    ...fixture,
    projectId,
    statePath,
    packageDir: join(runtimeDir, "dlcs", "packages", `sha256-${fixture.package_digest}`),
  };
}

async function fileDigestOrNull(path) {
  if (!existsSync(path)) return null;
  return createHash("sha256").update(await readFile(path)).digest("hex");
}

async function verifyPackagedDlcActive(contract) {
  await verifyPackagedDlcActiveVersion(contract, contract.package_digest, "1.0.0");
}

async function verifyPackagedDlcActiveVersion(contract, expectedDigest, expectedVersion) {
  const lifecycle = await apiJson("/api/v1/dlcs/acme.echo");
  if (lifecycle.state !== "active"
    || !lifecycle.active
    || lifecycle.version !== expectedVersion
    || lifecycle.active_digest !== expectedDigest
    || lifecycle.selected_digest !== expectedDigest) {
    throw new Error(`Packaged DLC did not activate its exact digest: ${JSON.stringify(lifecycle)}`);
  }
  const activation = await apiJson("/api/v1/dlcs/activation");
  const activeIdentity = activation.active_dlcs.find((item) => item.dlc_id === "acme.echo");
  if (activeIdentity?.package_digest !== expectedDigest
    || activeIdentity.frontend_entrypoint !== "frontend/index.js") {
    throw new Error(`Activation projection omitted the packaged DLC identity: ${JSON.stringify(activation)}`);
  }
  if (!existsSync(contract.markerPath)
    || (await readFile(contract.markerPath, "utf8")) !== expectedDigest) {
    throw new Error("Packaged DLC activation marker omitted the exact active digest");
  }

  const echo = await apiJson("/api/v1/dlcs/acme.echo/operations/echo", {
    method: "POST",
    body: { message: "hello packaged DLC" },
  });
  if (echo.message !== "hello packaged DLC" || echo.package_digest !== expectedDigest) {
    throw new Error(`Packaged DLC backend operation returned invalid output: ${JSON.stringify(echo)}`);
  }

  const packageDir = expectedDigest === contract.package_digest
    ? contract.packageDir
    : contract.updatePackageDir;
  const installedFrontend = await readFile(join(packageDir, "frontend", "index.js"), "utf8");
  if (!installedFrontend.includes("acme.echo.dock")
    || !installedFrontend.includes("acme.echo.message")) {
    throw new Error("Installed packaged DLC omitted its visible Dock or Artifact contribution");
  }
}

async function verifyPackagedGithubDlcActive(contract) {
  const lifecycle = await apiJson("/api/v1/dlcs/dbfox.github");
  if (lifecycle.state !== "active"
    || !lifecycle.active
    || lifecycle.active_digest !== contract.package_digest
    || lifecycle.selected_digest !== contract.package_digest) {
    throw new Error(`dbfox.github did not activate its exact digest: ${JSON.stringify(lifecycle)}`);
  }
  const activation = await apiJson("/api/v1/dlcs/activation");
  const activeIdentity = activation.active_dlcs.find((item) => item.dlc_id === "dbfox.github");
  if (activeIdentity?.package_digest !== contract.package_digest
    || activeIdentity.frontend_entrypoint !== "frontend/index.js") {
    throw new Error(`Activation projection omitted dbfox.github: ${JSON.stringify(activation)}`);
  }

  const bindings = await apiJson(
    `/api/v1/dlcs/dbfox.github/operations/bindings.list?project_id=${encodeURIComponent(contract.projectId)}`,
    { method: "POST", body: {} },
  );
  if (!Array.isArray(bindings.bindings) || bindings.bindings.length !== 0) {
    throw new Error(`dbfox.github bindings operation returned invalid output: ${JSON.stringify(bindings)}`);
  }
  if (!existsSync(contract.statePath)) {
    throw new Error("Active dbfox.github did not establish its DLC-owned state database");
  }
  const installedFrontend = await readFile(join(contract.packageDir, "frontend", "index.js"), "utf8");
  for (const contribution of [
    "dbfox.github.file",
    "dbfox.github.file_snapshot",
    "extensionHost.operations.invoke",
  ]) {
    if (!installedFrontend.includes(contribution)) {
      throw new Error(`Installed dbfox.github frontend omitted ${contribution}`);
    }
  }
}

async function verifyPackagedDlcInactiveAndUninstall(contract) {
  const lifecycle = await apiJson("/api/v1/dlcs/acme.echo");
  if (lifecycle.state !== "installed_disabled" || lifecycle.active || lifecycle.desired_enabled) {
    throw new Error(`Packaged DLC remained active after disable and restart: ${JSON.stringify(lifecycle)}`);
  }
  const activation = await apiJson("/api/v1/dlcs/activation");
  if (activation.active_dlcs.some((item) => item.dlc_id === "acme.echo")) {
    throw new Error("Restarted activation projection retained the disabled packaged DLC");
  }
  await expectApiProblem("/api/v1/dlcs/acme.echo/operations/echo", {
    method: "POST",
    body: { message: "must not execute after restart" },
    expectedStatus: 404,
    expectedCode: "DLC_NOT_ACTIVE",
  });

  const removeOld = await apiJson(
    `/api/v1/dlcs/acme.echo/versions/${contract.package_digest}`,
    { method: "DELETE" },
  );
  if (!removeOld.executable_bytes_removed
    || existsSync(contract.packageDir)
    || !existsSync(contract.updatePackageDir)) {
    throw new Error(`Explicit old-version removal was incomplete: ${JSON.stringify(removeOld)}`);
  }
  const remaining = await apiJson("/api/v1/dlcs/acme.echo");
  if (remaining.installed_versions.length !== 1
    || remaining.selected_digest !== contract.update_package_digest) {
    throw new Error(`Old-version removal changed the selected package: ${JSON.stringify(remaining)}`);
  }

  const uninstall = await apiJson("/api/v1/dlcs/acme.echo", { method: "DELETE" });
  if (!uninstall.executable_bytes_removed || !uninstall.data_retained) {
    throw new Error(`Packaged DLC uninstall returned invalid retention truth: ${JSON.stringify(uninstall)}`);
  }
  if (existsSync(contract.packageDir) || existsSync(contract.updatePackageDir)) {
    throw new Error("Inactive packaged DLC executable bytes remained after uninstall");
  }
  if (!existsSync(contract.markerPath)
    || (await readFile(contract.markerPath, "utf8")) !== contract.package_digest) {
    throw new Error("Packaged DLC-owned data was not retained after uninstall");
  }
  const finalList = await apiJson("/api/v1/dlcs");
  if (finalList.dlcs.some((item) => item.dlc_id === "acme.echo")) {
    throw new Error("Uninstalled packaged DLC remained in the lifecycle projection");
  }

  return {
    dlc_id: "acme.echo",
    package_digest: contract.package_digest,
    publisher_fingerprint: contract.publisher_fingerprint,
    tampered_rejected: true,
    install_execution_blocked: true,
    install_disabled: true,
    enable_restart_active_exact_digest: true,
    side_by_side_install_preserved_selection: true,
    update_restart_active_exact_digest: true,
    rollback_restart_active_exact_digest: true,
    selected_and_active_delete_blocked: true,
    old_version_removed_explicitly: true,
    backend_operation: "ok",
    frontend_dock_and_artifact: "ok",
    disable_restart_absent: true,
    executable_bytes_removed: true,
    data_retained: true,
  };
}

async function verifyPackagedGithubDlcInactiveAndUninstall(contract) {
  const lifecycle = await apiJson("/api/v1/dlcs/dbfox.github");
  if (lifecycle.state !== "installed_disabled" || lifecycle.active || lifecycle.desired_enabled) {
    throw new Error(`dbfox.github remained active after restart: ${JSON.stringify(lifecycle)}`);
  }
  const activation = await apiJson("/api/v1/dlcs/activation");
  if (activation.active_dlcs.some((item) => item.dlc_id === "dbfox.github")) {
    throw new Error("Activation projection retained disabled dbfox.github");
  }
  await expectApiProblem("/api/v1/dlcs/dbfox.github/operations/bindings.list", {
    method: "POST",
    body: {},
    expectedStatus: 404,
    expectedCode: "DLC_NOT_ACTIVE",
  });

  const uninstall = await apiJson("/api/v1/dlcs/dbfox.github", { method: "DELETE" });
  if (!uninstall.executable_bytes_removed || !uninstall.data_retained) {
    throw new Error(`dbfox.github uninstall returned invalid retention truth: ${JSON.stringify(uninstall)}`);
  }
  if (existsSync(contract.packageDir)) {
    throw new Error("Inactive dbfox.github executable bytes remained after uninstall");
  }
  if (!existsSync(contract.statePath)) {
    throw new Error("dbfox.github DLC-owned state was not retained after uninstall");
  }
  const finalList = await apiJson("/api/v1/dlcs");
  if (finalList.dlcs.some((item) => item.dlc_id === "dbfox.github")) {
    throw new Error("Uninstalled dbfox.github remained in the lifecycle projection");
  }

  return {
    dlc_id: "dbfox.github",
    package_digest: contract.package_digest,
    publisher_fingerprint: contract.publisher_fingerprint,
    absent_without_package: true,
    install_execution_blocked: true,
    install_disabled: true,
    enable_restart_active_exact_digest: true,
    backend_operation: "ok",
    frontend_contributions: "ok",
    disable_restart_absent: true,
    executable_bytes_removed: true,
    data_retained: true,
  };
}

async function apiJson(path, { method = "GET", body } = {}) {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    method,
    headers: {
      "X-Local-Token": token,
      Origin: rendererOrigin,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) {
    const responseBody = await response.text();
    throw new Error(
      `${method} ${path} returned HTTP ${response.status}: ${responseBody.slice(0, 500)}\n${stderr}`,
    );
  }
  return response.json();
}

async function expectApiProblem(path, {
  method = "GET",
  body,
  expectedStatus,
  expectedCode,
}) {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    method,
    headers: {
      "X-Local-Token": token,
      Origin: rendererOrigin,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  });
  const responseBody = await response.json();
  if (response.status !== expectedStatus || responseBody.code !== expectedCode) {
    throw new Error(
      `${method} ${path} returned HTTP ${response.status}/${responseBody.code}, expected ${expectedStatus}/${expectedCode}: ${JSON.stringify(responseBody).slice(0, 500)}`,
    );
  }
  return responseBody;
}

async function verifyFrozenDataContract(databasePath) {
  const project = await apiJson("/api/v1/projects", {
    method: "POST",
    body: { name: "Frozen System Data smoke" },
  });
  if (!project.id) throw new Error("Frozen Project creation returned no id");

  const profile = await apiJson(
    `/api/v1/dlcs/dbfox.data/operations/profiles.create?project_id=${encodeURIComponent(project.id)}`,
    {
      method: "POST",
      body: {
        name: "Frozen smoke SQLite",
        provider: "sqlite",
        is_read_only: true,
        environment: "test",
        initial_database_name: databasePath,
        initial_database_display_name: "smoke-source.sqlite",
      },
    },
  );
  const database = profile.databases?.[0];
  if (!database?.id) throw new Error("System Data profile creation returned no database resource");

  const sync = await apiJson(
    `/api/v1/dlcs/dbfox.data/operations/catalog.refresh?project_id=${encodeURIComponent(project.id)}`,
    {
    method: "POST",
      body: { database_id: database.id },
    },
  );
  if (sync.tables_synced < 1) {
    throw new Error(`Frozen schema sync returned an invalid result: ${JSON.stringify(sync)}`);
  }
  const tables = await apiJson(
    `/api/v1/dlcs/dbfox.data/operations/catalog.tables?project_id=${encodeURIComponent(project.id)}`,
    { method: "POST", body: { database_id: database.id, limit: 50 } },
  );
  if (!tables.tables?.some((table) => table.table_name === "smoke_items")) {
    throw new Error(
      `Frozen schema catalog omitted smoke_items: ${JSON.stringify(tables)}`,
    );
  }

  const first = await apiJson(
    `/api/v1/dlcs/dbfox.data/operations/console.execute?project_id=${encodeURIComponent(project.id)}`,
    {
    method: "POST",
    body: {
      database_id: database.id,
      sql: "SELECT id, name FROM smoke_items ORDER BY id",
      question: "Frozen result contract",
      execution_id: `smoke-query-${randomBytes(8).toString("hex")}`,
    },
  });
  const sessionId = first.session_id;
  if (!sessionId || !first.result_artifact_id || !first.run_id) {
    throw new Error("Frozen console query omitted its durable Session/Run/Artifact chain");
  }
  const page = await apiJson(`/api/v1/artifacts/${first.result_artifact_id}/page`, {
    method: "POST",
    body: { page: 1, pageSize: 10, countMode: "exact" },
  });
  if (page.rowCount !== 2 || page.rows?.[0]?.name !== "alpha") {
    throw new Error(`Frozen result artifact could not be replayed: ${JSON.stringify(page)}`);
  }

  const second = await apiJson(
    `/api/v1/dlcs/dbfox.data/operations/console.execute?project_id=${encodeURIComponent(project.id)}`,
    {
    method: "POST",
    body: {
      database_id: database.id,
      sql: "SELECT COUNT(*) AS total FROM smoke_items",
      question: "Frozen durable second turn",
      session_id: sessionId,
      execution_id: `smoke-query-${randomBytes(8).toString("hex")}`,
    },
  });
  if (!second.run_id || second.run_id === first.run_id) {
    throw new Error("Frozen durable second turn did not create an independent run");
  }
  const snapshot = await apiJson(`/api/v1/conversations/${sessionId}`);
  if (!Array.isArray(snapshot.runs) || snapshot.runs.length < 2) {
    throw new Error("Frozen conversation projection omitted durable multi-turn history");
  }
  return { databaseId: database.id, projectId: project.id, sessionId };
}

async function verifySystemDlcsActive() {
  const activation = await apiJson("/api/v1/dlcs/activation");
  const activeIds = new Set(
    (activation.active_dlcs ?? []).map((item) => item.dlc_id),
  );
  const missing = ["dbfox.data", "dbfox.workspace"].filter(
    (dlcId) => !activeIds.has(dlcId),
  );
  if (missing.length > 0) {
    throw new Error(
      `Frozen System DLC activation omitted ${missing.join(", ")}: ${JSON.stringify(activation)}\n${stderr}`,
    );
  }
}

async function expectRejectedToken(path, rejectedToken) {
  const headers = { Origin: rendererOrigin };
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
          Origin: rendererOrigin,
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
