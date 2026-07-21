import { useCallback, useState } from "react";
import type { ApiConfig, LlmConfigDraft } from "../lib/api/types";
import { enrollCredential } from "../lib/api/credentials";
import {
  createLlmConfigDraft,
  discardLlmConfigDraft,
  getStoredApiConfig,
  saveStoredApiConfig,
} from "../lib/llmConfig";

export function useApiConfig() {
  const [config, setConfig] = useState<ApiConfig>(getStoredApiConfig);
  const [draft, setDraft] = useState<LlmConfigDraft>(() => createLlmConfigDraft(getStoredApiConfig()));
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);

  const updateDraft = useCallback((partial: Partial<LlmConfigDraft>) => {
    setDraft((previous) => ({ ...previous, ...partial }));
  }, []);

  const handleSave = useCallback(async () => {
    let credentialId = draft.credentialId.trim();
    const apiKey = draft.apiKey.trim();
    if (apiKey) {
      const reference = await enrollCredential("llm_api_key", apiKey);
      credentialId = reference.id;
    }
    const next: ApiConfig = {
      credentialId,
      apiBase: draft.apiBase.trim(),
      modelName: draft.modelName.trim(),
    };
    saveStoredApiConfig(next);
    setConfig(next);
    setDraft(createLlmConfigDraft(next));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    setOpen(false);
  }, [draft]);

  const handleCancel = useCallback(() => {
    setDraft((currentDraft) => discardLlmConfigDraft(currentDraft, config));
    setOpen(false);
  }, [config]);

  return {
    config,
    draft,
    updateDraft,
    open,
    setOpen,
    saved,
    handleSave,
    handleCancel,
    isConfigured: Boolean(config.credentialId),
  } as const;
}
