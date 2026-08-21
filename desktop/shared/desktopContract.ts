export const DESKTOP_CHANNELS = Object.freeze({
  getEngineConfig: "dbfox:engine:get-config",
  getEngineStatus: "dbfox:engine:get-status",
  restartEngine: "dbfox:engine:restart",
  engineState: "dbfox:engine-state",
});

export type EngineStartupState = "starting" | "restarting" | "ready" | "failed" | "stopped";

export interface EngineStartupStatus {
  state: EngineStartupState;
  error: string | null;
  stage: string | null;
  generation: number;
  restartCount: number;
}

export interface EngineConfig {
  port: number;
  token: string;
  generation: number;
  protocolVersion: number;
  serverInfo: {
    name: string;
    version: string;
  };
  capabilities: string[];
}

export interface DbfoxDesktopBridge {
  readonly runtime: "electron";
  readonly engine: {
    getConfig(): Promise<EngineConfig>;
    getStatus(): Promise<EngineStartupStatus>;
    restart(): Promise<void>;
    subscribe(listener: (status: EngineStartupStatus) => void): () => void;
  };
}
