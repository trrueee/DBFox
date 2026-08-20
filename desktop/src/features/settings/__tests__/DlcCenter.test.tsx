import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  DlcLifecycleItem,
  DlcPackageInspection,
} from "../../../lib/api/generated/types.gen";
import {
  inspectDlcPackage,
  installDlcPackage,
  listDlcs,
  pickDlcPackage,
  restartDlcRuntime,
  setDlcEnabled,
  trustDlcPublisher,
  uninstallDlc,
} from "../../../lib/dlcLifecycle";
import { DlcCenter } from "../DlcCenter";

vi.mock("../../../lib/dlcLifecycle", () => ({
  canManageDlcPackages: () => true,
  inspectDlcPackage: vi.fn(),
  installDlcPackage: vi.fn(),
  listDlcs: vi.fn(),
  pickDlcPackage: vi.fn(),
  restartDlcRuntime: vi.fn(),
  setDlcEnabled: vi.fn(),
  trustDlcPublisher: vi.fn(),
  uninstallDlc: vi.fn(),
}));

const mockListDlcs = vi.mocked(listDlcs);
const mockPickDlcPackage = vi.mocked(pickDlcPackage);
const mockInspectDlcPackage = vi.mocked(inspectDlcPackage);
const mockTrustDlcPublisher = vi.mocked(trustDlcPublisher);
const mockInstallDlcPackage = vi.mocked(installDlcPackage);
const mockSetDlcEnabled = vi.mocked(setDlcEnabled);
const mockRestartDlcRuntime = vi.mocked(restartDlcRuntime);
const mockUninstallDlc = vi.mocked(uninstallDlc);

const baseItem: DlcLifecycleItem = {
  activation_failure: null,
  active: false,
  active_digest: null,
  backend_entrypoint_present: true,
  description: "Echoes the current selection.",
  desired_enabled: false,
  display_name: "Acme Echo",
  dlc_id: "acme.echo",
  frontend_entrypoint_present: true,
  permissions: ["artifact.read"],
  publisher: "Acme",
  publisher_fingerprint: "a".repeat(64),
  restart_state: "none",
  selected_digest: "b".repeat(64),
  state: "installed_disabled",
  trust_status: "trusted_signed",
  version: "1.0.0",
};

const baseInspection: DlcPackageInspection = {
  backend_entrypoint_present: true,
  description: "Echoes the current selection.",
  display_name: "Acme Echo",
  dlc_id: "acme.echo",
  frontend_entrypoint_present: true,
  package_digest: "b".repeat(64),
  permissions: ["artifact.read"],
  publisher: "Acme",
  publisher_fingerprint: "a".repeat(64),
  trust_required: false,
  trust_status: "trusted_signed",
  version: "1.0.0",
};

function renderCenter() {
  return render(<DlcCenter showToast={vi.fn()} />);
}

describe("DlcCenter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListDlcs.mockResolvedValue({ snapshot_id: "snapshot-1", dlcs: [] });
    mockPickDlcPackage.mockResolvedValue("C:\\fixtures\\acme.echo.dbfox-dlc");
    mockInspectDlcPackage.mockResolvedValue(baseInspection);
    mockTrustDlcPublisher.mockResolvedValue(undefined);
    mockInstallDlcPackage.mockResolvedValue(baseItem);
    mockRestartDlcRuntime.mockResolvedValue(undefined);
  });

  afterEach(cleanup);

  it("shows a safe empty state before any package is installed", async () => {
    renderCenter();

    expect(await screen.findByText("尚未安装 DLC 扩展")).toBeTruthy();
    expect(screen.getByText(/检查和安装阶段不会执行扩展代码/)).toBeTruthy();
  });

  it("installs an already trusted package disabled", async () => {
    renderCenter();
    await screen.findByText("尚未安装 DLC 扩展");

    fireEvent.click(screen.getByRole("button", { name: "从文件安装" }));
    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(screen.getByText("发布者公钥已受信任")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "安装（默认禁用）" }));

    await waitFor(() => expect(mockInstallDlcPackage).toHaveBeenCalledWith(
      "C:\\fixtures\\acme.echo.dbfox-dlc",
    ));
    expect(await screen.findByText("已安装，未启用")).toBeTruthy();
    expect(screen.getByText("禁用")).toBeTruthy();
    expect(screen.getByText("未激活")).toBeTruthy();
  });

  it("requires a distinct publisher trust confirmation before install", async () => {
    mockInspectDlcPackage.mockResolvedValue({
      ...baseInspection,
      trust_required: true,
      trust_status: "untrusted",
    });
    renderCenter();
    await screen.findByText("尚未安装 DLC 扩展");

    fireEvent.click(screen.getByRole("button", { name: "从文件安装" }));
    expect(await screen.findByText("发布者尚未受信任")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "安装（默认禁用）" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "信任此发布者" }));

    await waitFor(() => expect(mockTrustDlcPublisher).toHaveBeenCalledWith(
      "C:\\fixtures\\acme.echo.dbfox-dlc",
      expect.objectContaining({ package_digest: baseInspection.package_digest }),
    ));
    expect(await screen.findByRole("button", { name: "安装（默认禁用）" })).toBeTruthy();
    expect(mockInstallDlcPackage).not.toHaveBeenCalled();
  });

  it("keeps desired and active truth separate through enable and restart", async () => {
    const pending: DlcLifecycleItem = {
      ...baseItem,
      desired_enabled: true,
      restart_state: "required",
      state: "enable_pending_restart",
    };
    const active: DlcLifecycleItem = {
      ...pending,
      active: true,
      active_digest: pending.selected_digest,
      restart_state: "none",
      state: "active",
    };
    mockListDlcs.mockResolvedValueOnce({ snapshot_id: "snapshot-1", dlcs: [baseItem] });
    mockSetDlcEnabled.mockResolvedValue(pending);
    renderCenter();
    await screen.findByText("已安装，未启用");

    fireEvent.click(screen.getByRole("button", { name: "启用" }));
    expect(await screen.findByText("等待重启启用")).toBeTruthy();
    expect(screen.getByText("启用")).toBeTruthy();
    expect(screen.getByText("未激活")).toBeTruthy();

    mockListDlcs.mockResolvedValueOnce({ snapshot_id: "snapshot-2", dlcs: [active] });
    fireEvent.click(screen.getAllByRole("button", { name: "立即重启" })[0]);
    await waitFor(() => expect(mockRestartDlcRuntime).toHaveBeenCalledOnce());
    expect(await screen.findByText("当前已激活")).toBeTruthy();
    expect(screen.getByText("已激活")).toBeTruthy();

    mockSetDlcEnabled.mockResolvedValueOnce({
      ...active,
      desired_enabled: false,
      restart_state: "required",
      state: "disable_pending_restart",
    });
    fireEvent.click(screen.getByRole("button", { name: "停用" }));
    expect(await screen.findByText("等待重启停用")).toBeTruthy();
    expect(screen.getByText("禁用")).toBeTruthy();
    expect(screen.getByText("已激活")).toBeTruthy();
  });

  it("renders activation failures and blocks uninstall while runtime is active", async () => {
    mockListDlcs.mockResolvedValue({
      snapshot_id: "snapshot-broken",
      dlcs: [{
        ...baseItem,
        active: true,
        active_digest: baseItem.selected_digest,
        desired_enabled: false,
        restart_state: "failed",
        state: "activation_failed",
        activation_failure: { code: "ENTRYPOINT_IMPORT_FAILED", message: "backend failed closed" },
      }],
    });
    renderCenter();

    expect(await screen.findByText("激活失败")).toBeTruthy();
    expect(screen.getByText("backend failed closed")).toBeTruthy();
    expect(screen.getByText("停用并重启后才可卸载")).toBeTruthy();
    expect(screen.getByRole("button", { name: "卸载" }).hasAttribute("disabled")).toBe(true);
  });

  it("confirms inactive uninstall and states that DLC data is retained", async () => {
    mockListDlcs.mockResolvedValue({ snapshot_id: "snapshot-1", dlcs: [baseItem] });
    mockUninstallDlc.mockResolvedValue({
      data_retained: true,
      dlc_id: baseItem.dlc_id,
      executable_bytes_removed: true,
      package_digest: baseItem.selected_digest,
    });
    renderCenter();
    await screen.findByText("已安装，未启用");

    fireEvent.click(screen.getByRole("button", { name: "卸载" }));
    expect(await screen.findByText(/DLC 自己的数据目录默认保留/)).toBeTruthy();
    expect(screen.getByText(/APP_DATA\/dlcs\/data\/acme.echo/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "确认卸载" }));

    await waitFor(() => expect(mockUninstallDlc).toHaveBeenCalledWith("acme.echo"));
    expect(await screen.findByText("尚未安装 DLC 扩展")).toBeTruthy();
  });
});
