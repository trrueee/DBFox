import { invoke, isTauri } from "@tauri-apps/api/core";

import {
  disableDlcApiV1DlcsDlcIdDisablePost,
  enableDlcApiV1DlcsDlcIdEnablePost,
  inspectDlcPackageApiV1DlcsPackagesInspectPost,
  installDlcPackageApiV1DlcsInstallPost,
  listDlcsApiV1DlcsGet,
  removeDlcVersionApiV1DlcsDlcIdVersionsPackageDigestDelete,
  selectDlcVersionApiV1DlcsDlcIdVersionsPackageDigestSelectPost,
  trustDlcPublisherApiV1DlcsPublishersTrustPost,
  uninstallDlcApiV1DlcsDlcIdDelete,
} from "./api/generated/sdk.gen";
import type {
  DlcLifecycleItem,
  DlcListResponse,
  DlcPackageInspection,
  DlcUninstallResponse,
  DlcVersionRemovalResponse,
} from "./api/generated/types.gen";
import {
  getRuntimeSession,
  waitEngineHealth,
  waitForEngineConfig,
} from "./api/client";

interface DlcPackageSelection {
  path?: string | null;
}

export function canManageDlcPackages(): boolean {
  return isTauri();
}

export async function pickDlcPackage(): Promise<string | null> {
  const selection = await invoke<DlcPackageSelection>("pick_dlc_package");
  return selection.path ?? null;
}

export async function listDlcs(): Promise<DlcListResponse> {
  const { data } = await listDlcsApiV1DlcsGet({ throwOnError: true });
  return data;
}

export async function inspectDlcPackage(archivePath: string): Promise<DlcPackageInspection> {
  const { data } = await inspectDlcPackageApiV1DlcsPackagesInspectPost({
    body: { archive_path: archivePath },
    throwOnError: true,
  });
  return data;
}

export async function trustDlcPublisher(
  archivePath: string,
  inspection: DlcPackageInspection,
): Promise<void> {
  await trustDlcPublisherApiV1DlcsPublishersTrustPost({
    body: {
      archive_path: archivePath,
      package_digest: inspection.package_digest,
      publisher_fingerprint: inspection.publisher_fingerprint,
    },
    throwOnError: true,
  });
}

export async function installDlcPackage(archivePath: string): Promise<DlcLifecycleItem> {
  const { data } = await installDlcPackageApiV1DlcsInstallPost({
    body: { archive_path: archivePath },
    throwOnError: true,
  });
  return data;
}

export async function setDlcEnabled(dlcId: string, enabled: boolean): Promise<DlcLifecycleItem> {
  const operation = enabled
    ? enableDlcApiV1DlcsDlcIdEnablePost
    : disableDlcApiV1DlcsDlcIdDisablePost;
  const { data } = await operation({
    path: { dlc_id: dlcId },
    throwOnError: true,
  });
  return data;
}

export async function selectDlcVersion(
  dlcId: string,
  packageDigest: string,
): Promise<DlcLifecycleItem> {
  const { data } = await selectDlcVersionApiV1DlcsDlcIdVersionsPackageDigestSelectPost({
    path: { dlc_id: dlcId, package_digest: packageDigest },
    throwOnError: true,
  });
  return data;
}

export async function removeDlcVersion(
  dlcId: string,
  packageDigest: string,
): Promise<DlcVersionRemovalResponse> {
  const { data } = await removeDlcVersionApiV1DlcsDlcIdVersionsPackageDigestDelete({
    path: { dlc_id: dlcId, package_digest: packageDigest },
    throwOnError: true,
  });
  return data;
}

export async function uninstallDlc(dlcId: string): Promise<DlcUninstallResponse> {
  const { data } = await uninstallDlcApiV1DlcsDlcIdDelete({
    path: { dlc_id: dlcId },
    throwOnError: true,
  });
  return data;
}

export async function restartDlcRuntime(): Promise<void> {
  if (!isTauri()) throw new Error("只能在 DBFox 桌面应用中重启本地引擎");
  const previousGeneration = getRuntimeSession().generation;
  await invoke("restart_python_engine");
  await waitForEngineConfig({
    afterGeneration: previousGeneration,
    attempts: 80,
    intervalMs: 250,
  });
  await waitEngineHealth({ attempts: 40, intervalMs: 250 });
}
