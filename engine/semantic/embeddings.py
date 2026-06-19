import os
import logging
import time
from datetime import timedelta

import numpy as np
from sqlalchemy.orm import Session
from openai import OpenAI
from engine.models import SemanticAlias, utcnow

logger = logging.getLogger("dbfox.embeddings")

MAX_RETRIES = 3


class EmbeddingService:
    MODEL = "text-embedding-v3"
    DIMENSIONS = 1024
    THRESHOLD = 0.75

    def __init__(self, api_key: str | None = None, api_base: str | None = None, model_name: str | None = None) -> None:
        self.api_key = (
            api_key
            or os.getenv("OPENAI_API_KEY", "")
        )
        self.base_url = (
            api_base
            or os.getenv("OPENAI_API_BASE")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.model_name = self._resolve_embedding_model(
            model_name or os.getenv("DASHSCOPE_EMBEDDING_MODEL"), self.base_url
        )

    def _resolve_embedding_model(self, model_name: str | None, base_url: str) -> str:
        val = model_name
        known_chat_models = {
            "gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo",
            "qwen3-max", "qwen3-coder", "qwen-plus", "qwen-max", "qwen-turbo",
            "deepseek-v4-pro", "deepseek-chat", "deepseek-coder",
            "claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5", "claude-3-5-sonnet",
        }
        
        is_chat_model = False
        if val:
            v_lower = val.lower()
            if v_lower in known_chat_models:
                is_chat_model = True
            elif "gpt-" in v_lower or "claude-" in v_lower or "deepseek-" in v_lower:
                is_chat_model = True
            elif v_lower.startswith("qwen") and "embed" not in v_lower:
                is_chat_model = True

        if not val or is_chat_model:
            if "dashscope.aliyuncs.com" in base_url:
                return "text-embedding-v3"
            elif "api.openai.com" in base_url:
                return "text-embedding-3-small"
            elif "api.deepseek.com" in base_url:
                return "text-embedding-3-small"
            else:
                return "text-embedding-v3"
        
        return val

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts using DashScope compatible API.

        Retries with exponential backoff on rate-limit errors.
        """
        # For remote DashScope, we require an API key.
        # For local or custom endpoints (e.g. Ollama, LM Studio), API key is optional.
        is_dashscope = "dashscope.aliyuncs.com" in self.base_url
        if is_dashscope and not self.api_key:
            raise ValueError("DashScope API Key is not configured. Please set it in your Settings or environment.")
        if not texts:
            return []

        api_key = self.api_key or "local-placeholder"
        client = OpenAI(api_key=api_key, base_url=self.base_url)
        batch_size = 25
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            last_error = None
            for attempt in range(MAX_RETRIES):
                try:
                    response = client.embeddings.create(
                        model=self.model_name,
                        input=chunk,
                    )
                    embeddings = [item.embedding for item in response.data]
                    all_embeddings.extend(embeddings)
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    msg = str(e).lower()
                    if ("rate" in msg or "throttl" in msg or "limit" in msg) and attempt < MAX_RETRIES - 1:
                        wait = 2 ** attempt
                        logger.warning(
                            "DashScope rate-limited (attempt %d/%d), retrying in %ds: %s",
                            attempt + 1, MAX_RETRIES, wait, e,
                        )
                        time.sleep(wait)
                    else:
                        break
            if last_error is not None:
                logger.error("DashScope embedding API call failed after %d attempts: %s", MAX_RETRIES, last_error)
                raise last_error
        return all_embeddings

    def sync_aliases(self, db: Session, datasource_id: str) -> dict:
        """Batch generate embeddings for all semantic aliases in a data source and save to DB."""
        aliases = (
            db.query(SemanticAlias)
            .filter(
                SemanticAlias.data_source_id == datasource_id,
                SemanticAlias.target_type != "sensitive"
            )
            .all()
        )
        if not aliases:
            return {"success": True, "synced_count": 0, "message": "该数据源下没有配置别名规则。"}

        # Extract texts to embed
        texts = [a.alias for a in aliases]
        try:
            vectors = self.embed(texts)
        except Exception as e:
            logger.exception("Failed to generate embeddings during sync")
            return {"success": False, "synced_count": 0, "message": f"同步向量失败: {str(e)}"}

        # Offset embedding_synced_at by +1s so it is strictly after the
        # updated_at that SQLAlchemy's onupdate=utcnow sets during flush.
        sync_time = utcnow() + timedelta(seconds=1)
        for alias, vec in zip(aliases, vectors):
            vec_arr = np.array(vec, dtype=np.float32)
            alias.embedding_blob = vec_arr.tobytes()
            alias.embedding_synced_at = sync_time

        db.commit()
        return {"success": True, "synced_count": len(aliases), "message": f"成功同步 {len(aliases)} 个别名的向量特征。"}

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Calculate cosine similarity between two 1D arrays."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    @staticmethod
    def batch_cosine(query_vec: np.ndarray, alias_matrix: np.ndarray) -> np.ndarray:
        """Batch calculate cosine similarities between query_vec (1D) and alias_matrix (2D)."""
        dot_products = np.dot(alias_matrix, query_vec)
        matrix_norms = np.linalg.norm(alias_matrix, axis=1)
        query_norm = np.linalg.norm(query_vec)

        # Avoid division by zero
        matrix_norms[matrix_norms == 0] = 1e-8
        q_norm = query_norm if query_norm > 0 else 1e-8

        return dot_products / (matrix_norms * q_norm)
