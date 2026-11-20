import type { EngineConfig } from "../shared/desktopContract";

export const COMPUTER_STOP_ACCELERATOR = "Control+Alt+Shift+Escape";

/** Fixed authenticated endpoint; no renderer URL, command or token persistence. */
export async function stopComputerTargets(config: EngineConfig, origin: string, request: typeof fetch = fetch): Promise<void> {
  const response = await request(`http://127.0.0.1:${config.port}/api/v1/computer/stop`, {
    method: "POST", headers: { "X-Local-Token": config.token, Origin: origin }, signal: AbortSignal.timeout(3000),
  });
  if (response.status !== 202) throw new Error("Computer stop was not acknowledged");
}
