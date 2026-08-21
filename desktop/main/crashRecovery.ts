import { mkdir, open, rm, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import type { LaunchRecoveryStatus } from "../shared/desktopContract";

export class CrashRecoveryMarker {
  readonly #path: string;
  readonly #status: LaunchRecoveryStatus;
  #cleared = false;

  private constructor(path: string, previousUncleanExit: boolean) {
    this.#path = path;
    this.#status = { previousUncleanExit };
  }

  static async initialize(path: string): Promise<CrashRecoveryMarker> {
    let previousUncleanExit = true;
    try {
      const handle = await open(path, "r");
      await handle.close();
    } catch (error) {
      if (error instanceof Error && "code" in error && error.code === "ENOENT") previousUncleanExit = false;
      else throw error;
    }
    await mkdir(dirname(path), { recursive: true, mode: 0o700 });
    await writeFile(path, "active\n", { encoding: "utf8", mode: 0o600 });
    return new CrashRecoveryMarker(path, previousUncleanExit);
  }

  status(): LaunchRecoveryStatus {
    return { ...this.#status };
  }

  async clear(): Promise<void> {
    if (this.#cleared) return;
    this.#cleared = true;
    await rm(this.#path, { force: true });
  }
}
