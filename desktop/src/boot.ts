const bootIndicator = document.getElementById("boot-indicator");
const bootMessage = document.getElementById("boot-msg");

export function setBootIndicatorMessage(message: string): void {
  if (bootMessage) bootMessage.textContent = message;
}

export function hideBootIndicator(): void {
  bootIndicator?.classList.add("is-hidden");
}

export function showBootIndicatorError(): void {
  bootIndicator?.setAttribute("data-state", "error");
  setBootIndicatorMessage("DBFox 启动失败，请重试或查看诊断日志。");
}

function handleBootstrapFailure(): void {
  showBootIndicatorError();
}

window.addEventListener("error", handleBootstrapFailure, true);
window.addEventListener("unhandledrejection", handleBootstrapFailure);
