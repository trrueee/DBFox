import { useMemo, useSyncExternalStore } from "react";
import type { ApiConfig } from "../lib/api/types";
import { API_CONFIG_CHANGED_EVENT, API_CONFIG_STORAGE_KEY, DEFAULT_API_CONFIG, getStoredApiConfig } from "../lib/llmConfig";

function subscribe(listener: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key === API_CONFIG_STORAGE_KEY || event.key === null) listener();
  };
  window.addEventListener(API_CONFIG_CHANGED_EVENT, listener);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(API_CONFIG_CHANGED_EVENT, listener);
    window.removeEventListener("storage", onStorage);
  };
}

const serverSnapshot = JSON.stringify(DEFAULT_API_CONFIG);

/** The saved metadata contains an opaque vault reference, never the editable key. */
export function useSavedApiConfig(): ApiConfig {
  const snapshot = useSyncExternalStore(subscribe,
    () => JSON.stringify(getStoredApiConfig()), () => serverSnapshot);
  return useMemo(() => JSON.parse(snapshot) as ApiConfig, [snapshot]);
}
