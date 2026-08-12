import { invoke, isTauri } from "@tauri-apps/api/core";
import { useEffect } from "react";

import { recordClientLog } from "../../lib/diagnostics/clientLog";

interface LaunchRecoveryStatus {
  previousUncleanExit: boolean;
}

export function DesktopLifecycleMonitor({
  showToast,
}: {
  showToast: (message: string, type?: "success" | "error" | "warning" | "info") => void;
}) {
  useEffect(() => {
    if (!isTauri()) return;
    let cancelled = false;

    void invoke<LaunchRecoveryStatus>("get_launch_recovery_status")
      .then((status) => {
        if (!cancelled && status.previousUncleanExit) {
          showToast("检测到上次异常退出，已恢复安全的窗口与持久化工作区状态", "warning");
        }
      })
      .catch((error) => recordClientLog("warning", "读取异常退出状态失败", error));

    return () => {
      cancelled = true;
    };
  }, [showToast]);

  return null;
}
