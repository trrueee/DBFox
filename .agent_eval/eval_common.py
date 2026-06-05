import os
import json
from pathlib import Path


def get_default_token_paths():
    # Try repository runtime path via engine.runtime_paths if available
    try:
        from engine.runtime_paths import private_runtime_file

        token = private_runtime_file("auth", ".local_token")
        yield Path(token)
    except Exception:
        pass

    # Fallback: AppData Roaming (Windows), and XDG on *nix
    home = Path.home()
    # Windows default used by quick_agent_run historically
    yield home / "AppData" / "Roaming" / "DataBox" / "auth" / ".local_token"
    # Common fallback inside repo
    yield Path(".local_token")


def get_local_token_path():
    for p in get_default_token_paths():
        if p and p.exists():
            return p
    return None


def get_local_token():
    p = get_local_token_path()
    if not p:
        raise FileNotFoundError("Local token not found; expected one of known locations")
    return p.read_text(encoding="utf-8").strip()


def load_eval_config(path: str | Path | None = None) -> dict:
    """Load eval config from a JSON file if it exists.

    Supported formats:
    - New format: {"llm": {"provider": ..., "model_name": ..., "api_key": ..., "api_base": ...}, "backend": {"base_url": ...}}
    - Legacy format: {"api_key": ..., "api_base": ..., "model": ..., "base_url": ...}
    """
    config_path = Path(path) if path else (Path(__file__).resolve().parent / "config.local.json")
    if not config_path.exists():
        return {"_config_path": str(config_path), "_config_exists": False}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"_config_path": str(config_path), "_config_exists": True}
        data["_config_path"] = str(config_path)
        data["_config_exists"] = True
        return data
    except Exception:
        return {"_config_path": str(config_path), "_config_exists": True}


def load_llm_config(config_path: str | Path | None = None, overrides: dict | None = None) -> dict:
    """Resolve LLM config using priority: overrides -> config.local.json -> environment variables.

    Returns: {provider, model_name, api_key, api_base, source}
    """
    overrides = overrides or {}
    config = load_eval_config(config_path)

    llm_cfg = {}
    if isinstance(config.get("llm"), dict):
        llm_cfg = config.get("llm", {})
    else:
        # Legacy support
        llm_cfg = {
            "provider": config.get("provider"),
            "model_name": config.get("model") or config.get("model_name"),
            "api_key": config.get("api_key"),
            "api_base": config.get("api_base"),
        }

    provider = overrides.get("provider") or llm_cfg.get("provider") or os.getenv("DATABOX_LLM_PROVIDER") or os.getenv("LLM_PROVIDER")
    model_name = overrides.get("model_name") or llm_cfg.get("model_name") or os.getenv("DATABOX_LLM_MODEL") or os.getenv("OPENAI_MODEL") or os.getenv("DASHSCOPE_MODEL")

    api_key = (
        overrides.get("api_key")
        or llm_cfg.get("api_key")
        or os.getenv("DATABOX_LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("QWEN_API_KEY")
    )
    api_base = (
        overrides.get("api_base")
        or llm_cfg.get("api_base")
        or os.getenv("DATABOX_LLM_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("DASHSCOPE_API_BASE")
    )

    return {
        "provider": provider,
        "model_name": model_name,
        "api_key": api_key,
        "api_base": api_base,
        "source": {
            "config_exists": bool(config.get("_config_exists")),
            "config_path": config.get("_config_path"),
        },
    }
