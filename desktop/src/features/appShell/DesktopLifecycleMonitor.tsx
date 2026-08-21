import { useEffect } from "react";

import { recordClientLog } from "../../lib/diagnostics/clientLog";
import { getDesktopLaunchRecoveryStatus, isEngineDesktopHost } from "../../lib/desktopHost";

export function DesktopLifecycleMonitor({
  showToast,
}: {
  showToast: (message: string, type?: "success" | "error" | "warning" | "info") => void;
}) {
  useEffect(() => {
    if (!isEngineDesktopHost()) return;
    let cancelled = false;

    void getDesktopLaunchRecoveryStatus()
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
