from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Sequence

from engine.evaluation.retrieval_ab.metrics import RetrievalHit


SUPPORTED_VARIANTS = ("keyword", "vector", "hybrid")


def normalize_variant_names(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ("keyword",)
    if isinstance(value, str):
        raw = value.split(",")
    else:
        raw = list(value)
    names = tuple(name.strip().lower() for name in raw if str(name).strip())
    unsupported = [name for name in names if name not in SUPPORTED_VARIANTS]
    if unsupported:
        raise ValueError(
            f"Unsupported retrieval variant: {', '.join(unsupported)}. "
            f"Supported variants: {', '.join(SUPPORTED_VARIANTS)}"
        )
    return names or ("keyword",)


def fuse_rrf(
    keyword_results: Iterable[RetrievalHit],
    vector_results: Iterable[RetrievalHit],
    *,
    limit: int = 20,
    k: int = 60,
) -> tuple[RetrievalHit, ...]:
    fused: dict[tuple[str, str, str | None], _FusionState] = {}
    for rank, hit in enumerate(keyword_results, start=1):
        state = fused.setdefault(hit.key, _FusionState(hit=hit))
        state.keyword_rank = rank
        state.matched_by.add("keyword")
        state.matched_fields.update(hit.matched_fields)
    for rank, hit in enumerate(vector_results, start=1):
        state = fused.setdefault(hit.key, _FusionState(hit=hit))
        state.vector_rank = rank
        state.matched_by.add("vector")
        state.matched_fields.update(hit.matched_fields)

    ranked: list[RetrievalHit] = []
    for state in fused.values():
        score = 0.0
        if state.keyword_rank is not None:
            score += 1.0 / (k + state.keyword_rank)
        if state.vector_rank is not None:
            score += 1.0 / (k + state.vector_rank)
        matched_by = tuple(source for source in ("keyword", "vector") if source in state.matched_by)
        reason_parts: list[str] = []
        if state.keyword_rank is not None:
            reason_parts.append(f"keyword rank {state.keyword_rank}")
        if state.vector_rank is not None:
            reason_parts.append(f"vector rank {state.vector_rank}")
        ranked.append(
            replace(
                state.hit,
                score=round(score, 6),
                keyword_rank=state.keyword_rank,
                vector_rank=state.vector_rank,
                matched_by=matched_by,
                matched_fields=tuple(sorted(state.matched_fields)),
                reason="; ".join(reason_parts),
            )
        )

    ranked.sort(
        key=lambda hit: (
            -hit.score,
            hit.keyword_rank if hit.keyword_rank is not None else 1_000_000,
            hit.vector_rank if hit.vector_rank is not None else 1_000_000,
            hit.type,
            hit.ref,
        )
    )
    return tuple(ranked[:limit])


class _FusionState:
    def __init__(self, *, hit: RetrievalHit) -> None:
        self.hit = hit
        self.keyword_rank: int | None = None
        self.vector_rank: int | None = None
        self.matched_by: set[str] = set()
        self.matched_fields: set[str] = set()
