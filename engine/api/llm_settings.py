from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from engine.crypto import decrypt_password, encrypt_password
from engine.db import get_db

router = APIRouter()

LLM_PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "openai": {
        "provider": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini"],
    },
    "deepseek": {
        "provider": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "dashscope": {
        "provider": "dashscope",
        "label": "阿里云百炼 / 通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo", "qwen-coder-plus"],
    },
    "siliconflow": {
        "provider": "siliconflow",
        "label": "SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["Qwen/Qwen3-Coder-480B-A35B-Instruct", "deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-R1"],
    },
    "moonshot": {
        "provider": "moonshot",
        "label": "Moonshot / Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    },
    "zhipu": {
        "provider": "zhipu",
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-plus", "glm-4-air", "glm-4-flash"],
    },
    "openrouter": {
        "provider": "openrouter",
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "deepseek/deepseek-chat"],
    },
    "custom": {
        "provider": "custom",
        "label": "自定义 OpenAI Compatible",
        "base_url": "",
        "models": [],
    },
}


class LLMConfigRequest(BaseModel):
    provider: str = Field(default="deepseek")
    model: str = Field(default="deepseek-chat")
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = 0.2
    max_tokens: int = 4096
    enabled: bool = True


class LLMResolveRequest(BaseModel):
    provider: str = Field(default="auto")
    model: str = Field(default="")
    base_url: str | None = None


def _ensure_llm_settings_table(db: Session) -> None:
    db.execute(text(
        """
        CREATE TABLE IF NOT EXISTS llm_settings (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            base_url TEXT NOT NULL,
            api_key_ciphertext TEXT NOT NULL DEFAULT '',
            api_key_nonce TEXT NOT NULL DEFAULT '',
            temperature REAL NOT NULL DEFAULT 0.2,
            max_tokens INTEGER NOT NULL DEFAULT 4096,
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    ))
    db.commit()


def _infer_provider_from_model(model: str, provider: str | None = None) -> str:
    explicit_provider = (provider or "").strip().lower()
    if explicit_provider and explicit_provider != "auto":
        return explicit_provider

    normalized_model = model.strip().lower()
    if normalized_model.startswith("gpt-") or normalized_model.startswith("o1") or normalized_model.startswith("o3"):
        return "openai"
    if normalized_model.startswith("deepseek"):
        return "deepseek"
    if normalized_model.startswith("qwen"):
        return "dashscope"
    if normalized_model.startswith("glm"):
        return "zhipu"
    if normalized_model.startswith("moonshot") or normalized_model.startswith("kimi"):
        return "moonshot"
    if "/" in normalized_model:
        return "siliconflow"
    return "custom"


def _resolve_base_url(provider: str, model: str, base_url: str | None = None) -> tuple[str, str]:
    resolved_provider = _infer_provider_from_model(model, provider)
    if resolved_provider == "custom":
        return resolved_provider, (base_url or "").strip()
    preset = LLM_PROVIDER_PRESETS.get(resolved_provider)
    if not preset:
        return "custom", (base_url or "").strip()
    return resolved_provider, str(preset["base_url"])


def _mask_api_key(ciphertext: str, nonce: str) -> tuple[bool, str]:
    if not ciphertext or not nonce:
        return False, ""
    try:
        plain = decrypt_password(ciphertext, nonce)
    except Exception:
        return True, "已保存，无法预览"
    if len(plain) <= 8:
        return True, "********"
    return True, f"{plain[:4]}...{plain[-4:]}"


def _config_row_to_dict(row: Any) -> dict[str, Any]:
    if not row:
        provider, base_url = _resolve_base_url("deepseek", "deepseek-chat")
        return {
            "id": "active",
            "provider": provider,
            "model": "deepseek-chat",
            "base_url": base_url,
            "temperature": 0.2,
            "max_tokens": 4096,
            "enabled": True,
            "has_api_key": False,
            "api_key_preview": "",
            "updated_at": None,
        }

    mapping = row._mapping
    has_api_key, api_key_preview = _mask_api_key(str(mapping["api_key_ciphertext"] or ""), str(mapping["api_key_nonce"] or ""))
    return {
        "id": mapping["id"],
        "provider": mapping["provider"],
        "model": mapping["model"],
        "base_url": mapping["base_url"],
        "temperature": mapping["temperature"],
        "max_tokens": mapping["max_tokens"],
        "enabled": bool(mapping["enabled"]),
        "has_api_key": has_api_key,
        "api_key_preview": api_key_preview,
        "updated_at": mapping["updated_at"],
    }


@router.get("/llm/providers")
def api_list_llm_providers() -> list[dict[str, Any]]:
    return list(LLM_PROVIDER_PRESETS.values())


@router.get("/llm/config")
def api_get_llm_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    _ensure_llm_settings_table(db)
    row = db.execute(text("SELECT * FROM llm_settings WHERE id = 'active' LIMIT 1")).first()
    return _config_row_to_dict(row)


@router.post("/llm/config")
def api_save_llm_config(req: LLMConfigRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    _ensure_llm_settings_table(db)
    provider, base_url = _resolve_base_url(req.provider, req.model, req.base_url)
    if not base_url:
        raise HTTPException(status_code=400, detail={"code": "LLM_BASE_URL_REQUIRED", "message": "自定义模型必须填写 Base URL。"})

    existing = db.execute(text("SELECT api_key_ciphertext, api_key_nonce FROM llm_settings WHERE id = 'active' LIMIT 1")).first()
    if req.api_key is not None and req.api_key.strip():
        api_key_ciphertext, api_key_nonce = encrypt_password(req.api_key.strip())
    elif existing:
        api_key_ciphertext = str(existing._mapping["api_key_ciphertext"] or "")
        api_key_nonce = str(existing._mapping["api_key_nonce"] or "")
    else:
        api_key_ciphertext = ""
        api_key_nonce = ""

    db.execute(text(
        """
        INSERT INTO llm_settings (
            id, provider, model, base_url, api_key_ciphertext, api_key_nonce,
            temperature, max_tokens, enabled, updated_at
        ) VALUES (
            'active', :provider, :model, :base_url, :api_key_ciphertext, :api_key_nonce,
            :temperature, :max_tokens, :enabled, CURRENT_TIMESTAMP
        )
        ON CONFLICT(id) DO UPDATE SET
            provider = excluded.provider,
            model = excluded.model,
            base_url = excluded.base_url,
            api_key_ciphertext = excluded.api_key_ciphertext,
            api_key_nonce = excluded.api_key_nonce,
            temperature = excluded.temperature,
            max_tokens = excluded.max_tokens,
            enabled = excluded.enabled,
            updated_at = CURRENT_TIMESTAMP
        """
    ), {
        "provider": provider,
        "model": req.model.strip(),
        "base_url": base_url,
        "api_key_ciphertext": api_key_ciphertext,
        "api_key_nonce": api_key_nonce,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "enabled": 1 if req.enabled else 0,
    })
    db.commit()
    return api_get_llm_config(db)


@router.post("/llm/resolve")
def api_resolve_llm_config(req: LLMResolveRequest) -> dict[str, str]:
    provider, base_url = _resolve_base_url(req.provider, req.model, req.base_url)
    return {"provider": provider, "base_url": base_url}


@router.get("/llm/resolve")
def api_resolve_llm_config_get(
    provider: str = Query(default="auto"),
    model: str = Query(default=""),
    base_url: str | None = Query(default=None),
) -> dict[str, str]:
    resolved_provider, resolved_base_url = _resolve_base_url(provider, model, base_url)
    return {"provider": resolved_provider, "base_url": resolved_base_url}
