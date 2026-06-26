from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from engine.evaluation.retrieval_ab.variants import normalize_variant_names

DEFAULT_ENV_FILE = Path.home() / ".dbfox" / "dbfox-eval.env"
DEFAULT_TINY_SPIDER_CASES = Path("engine/tests/fixtures/spider_tiny/dev.json")


@dataclass(frozen=True)
class RetrievalAbConfig:
    benchmark: str
    cases_path: Path
    db_ids: tuple[str, ...]
    variants: tuple[str, ...]
    mode: str
    model: str | None
    execute: bool
    retrieval_top_k: int
    vector_top_k: int
    keyword_top_k: int
    temperature: float
    report_dir: Path

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any],
        *,
        env: Mapping[str, str] | None = None,
    ) -> "RetrievalAbConfig":
        source_env = os.environ if env is None else env
        benchmark = str(values.get("benchmark") or "spider").strip().lower()
        cases_value = values.get("cases") or values.get("cases_path") or _default_spider_cases_path(source_env)
        variants_value = values.get("variants") or source_env.get("DBFOX_SCHEMA_RETRIEVAL_MODE") or "keyword"
        model = values.get("model") or source_env.get("OPENAI_MODEL_NAME")
        return cls(
            benchmark=benchmark,
            cases_path=Path(str(cases_value)),
            db_ids=_split_csv(values.get("dbs") or values.get("db_ids")),
            variants=normalize_variant_names(variants_value),
            mode=_normalize_mode(values.get("mode") or source_env.get("DBFOX_RETRIEVAL_AB_MODE") or "live"),
            model=str(model) if model else None,
            execute=_as_bool(values.get("execute"), default=False),
            retrieval_top_k=_as_int(source_env.get("DBFOX_RETRIEVAL_TOP_K"), 20),
            vector_top_k=_as_int(source_env.get("DBFOX_RETRIEVAL_VECTOR_TOP_K"), 30),
            keyword_top_k=_as_int(source_env.get("DBFOX_RETRIEVAL_KEYWORD_TOP_K"), 30),
            temperature=_as_float(source_env.get("DBFOX_EVAL_TEMPERATURE"), 0.0),
            report_dir=Path(str(values.get("report_dir") or "reports/retrieval_ab")),
        )


def _split_csv(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        raw = value
    else:
        raw = str(value).split(",")
    return tuple(str(item).strip() for item in raw if str(item).strip())


def _normalize_mode(value: Any) -> str:
    mode = str(value or "live").strip().lower().replace("_", "-")
    if mode not in {"live", "retrieval-only", "ai-assisted-retrieval"}:
        raise ValueError("Retrieval A/B mode must be 'live', 'retrieval-only', or 'ai-assisted-retrieval'.")
    return mode


def _default_spider_cases_path(env: Mapping[str, str]) -> Path:
    root = str(env.get("DBFOX_SPIDER_ROOT") or env.get("SPIDER_ROOT") or "").strip()
    if root:
        return Path(root) / "dev.json"
    return DEFAULT_TINY_SPIDER_CASES


def load_env_file(
    path: str | Path,
    *,
    env: dict[str, str] | None = None,
    override: bool = False,
) -> bool:
    target_env = env if env is not None else os.environ
    env_path = Path(path)
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if override or key not in target_env or not str(target_env.get(key) or "").strip():
            target_env[key] = value.strip().strip("\"'")
    return True


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(value: Any, default: int) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
