"""Generic Artifact representation discovery and read endpoints."""

from __future__ import annotations

from collections.abc import Iterator
import logging
import re
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from engine.agent.artifact import Artifact, ArtifactStatus
from engine.agent.repositories.artifact import ArtifactRepository
from engine.app.safe_errors import (
    SafeLogOperation,
    fixed_error_detail,
    log_unexpected_exception,
)
from engine.db import get_db
from engine.representation import (
    ArtifactRepresentationContext,
    ArtifactRepresentationDescriptor,
    ArtifactRepresentationError,
    ArtifactRepresentationRequest,
    ArtifactRepresentationResult,
    ArtifactRepresentationStream,
    execute_artifact_representation,
)
from engine.errors import DBFoxError
from engine.json_codec import dumps
from engine.runtime_composition import get_active_runtime_snapshot
from engine.security.audit import SecurityAuditService


logger = logging.getLogger("dbfox.api.agent.representations")
router = APIRouter()

_MAX_JSON_RESULT_BYTES = 8 * 1024 * 1024
_MAX_STREAM_BYTES = 64 * 1024 * 1024
_SAFE_FILE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_SAFE_METADATA_KEY = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


def _representation_error(code: str, *, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=fixed_error_detail(code),
    )


def _provider_failure(*, stream: bool, error: Exception) -> HTTPException:
    log_unexpected_exception(
        logger,
        operation=(
            SafeLogOperation.ARTIFACT_REPRESENTATION_STREAM
            if stream
            else SafeLogOperation.ARTIFACT_REPRESENTATION_READ
        ),
        exc=error,
    )
    return _representation_error("PROVIDER_FAILURE", status_code=500)


def _root_artifact(artifacts: ArtifactRepository, artifact_id: str) -> Artifact:
    artifact = artifacts.get(artifact_id)
    if artifact is None or artifact.status is not ArtifactStatus.COMPLETED:
        raise ArtifactRepresentationError(
            "NOT_FOUND",
            "The requested Artifact is unavailable.",
            status_code=404,
        )
    return artifact


def _context_for(
    artifacts: ArtifactRepository,
    root: Artifact,
) -> ArtifactRepresentationContext:
    allowed: dict[str, Artifact] = {root.id: root}
    pending = [relation.artifact_id for relation in root.relations]
    while pending and len(allowed) < 64:
        related_id = pending.pop()
        if related_id in allowed:
            continue
        related = artifacts.get(related_id)
        if (
            related is None
            or related.status is not ArtifactStatus.COMPLETED
            or related.session_id != root.session_id
        ):
            continue
        allowed[related.id] = related
        pending.extend(relation.artifact_id for relation in related.relations)

    def load_related(artifact_id: str) -> Artifact | None:
        return allowed.get(artifact_id)

    return ArtifactRepresentationContext(artifact_loader=load_related)


def _resolve(
    db: Session,
    artifact_id: str,
    representation_type: str,
    request: ArtifactRepresentationRequest,
    *,
    expected_kind: Literal["json", "stream"],
) -> tuple[Artifact, ArtifactRepresentationDescriptor, object]:
    artifacts = ArtifactRepository(db)
    artifact = _root_artifact(artifacts, artifact_id)
    contribution = get_active_runtime_snapshot().get_artifact_representation(
        artifact.type,
        representation_type,
    )
    if contribution is None:
        raise ArtifactRepresentationError(
            "UNSUPPORTED_REPRESENTATION",
            "The Artifact does not provide the requested representation.",
            status_code=409,
        )
    descriptor, result = execute_artifact_representation(
        artifact=artifact,
        representation_type=representation_type,
        request=request,
        provider=contribution.provider,
        context=_context_for(artifacts, artifact),
        expected_kind=expected_kind,
    )
    return artifact, descriptor, result


def _safe_file_name(value: str) -> str:
    candidate = _SAFE_FILE_NAME.sub("-", str(value).strip()).strip(".-")
    return candidate[:128] or "dbfox-artifact.bin"


def _stream_headers(result: ArtifactRepresentationStream) -> dict[str, str]:
    headers = {
        "Content-Disposition": f'attachment; filename="{_safe_file_name(result.file_name)}"'
    }
    for key, value in result.metadata.items():
        normalized_key = str(key).strip().lower()
        normalized_value = str(value).strip()
        if (
            _SAFE_METADATA_KEY.fullmatch(normalized_key) is not None
            and len(normalized_value) <= 256
            and "\r" not in normalized_value
            and "\n" not in normalized_value
        ):
            headers[f"X-DBFox-Representation-{normalized_key}"] = normalized_value
    return headers


def _bounded_chunks(chunks: Iterator[str | bytes]) -> Iterator[str | bytes]:
    total = 0
    for chunk in chunks:
        if not isinstance(chunk, (str, bytes)):
            raise TypeError("Representation stream chunks must be text or bytes")
        total += len(chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
        if total > _MAX_STREAM_BYTES:
            raise RuntimeError("Representation stream exceeded its response budget")
        yield chunk


@router.get(
    "/artifacts/{artifact_id}/representations",
    response_model=list[ArtifactRepresentationDescriptor],
)
def api_artifact_representations(
    artifact_id: str,
    db: Session = Depends(get_db),
) -> list[ArtifactRepresentationDescriptor]:
    try:
        artifact = _root_artifact(ArtifactRepository(db), artifact_id)
        contributions = (
            get_active_runtime_snapshot().artifact_representations_for(artifact.type)
        )
        descriptors = [
            contribution.provider.describe(artifact)
            for contribution in contributions
        ]
        for contribution, descriptor in zip(contributions, descriptors, strict=True):
            if descriptor.representation_type != contribution.representation_type:
                raise RuntimeError(
                    "Representation provider descriptor does not match registration"
                )
        return descriptors
    except ArtifactRepresentationError as error:
        raise _representation_error(error.code, status_code=error.status_code) from None
    except (DBFoxError, ValidationError) as error:
        raise _provider_failure(stream=False, error=error) from None
    except Exception as error:
        raise _provider_failure(stream=False, error=error) from None


@router.post(
    "/artifacts/{artifact_id}/representations/{representation_type}/read",
    response_model=ArtifactRepresentationResult,
)
def api_artifact_representation_read(
    artifact_id: str,
    representation_type: str,
    request: ArtifactRepresentationRequest,
    db: Session = Depends(get_db),
) -> ArtifactRepresentationResult:
    try:
        _, descriptor, untrusted_result = _resolve(
            db,
            artifact_id,
            representation_type,
            request,
            expected_kind="json",
        )
        if not isinstance(untrusted_result, ArtifactRepresentationResult):
            raise TypeError("Canonical JSON representation dispatch returned a stream")
        result = untrusted_result
        encoded = dumps(result.model_dump(mode="json")).encode("utf-8")
        if len(encoded) > _MAX_JSON_RESULT_BYTES:
            raise RuntimeError("Representation result exceeded its response budget")
        return result
    except ArtifactRepresentationError as error:
        raise _representation_error(error.code, status_code=error.status_code) from None
    except ValidationError as error:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.ARTIFACT_REPRESENTATION_READ,
            exc=error,
        )
        raise _representation_error("INVALID_REQUEST", status_code=422) from None
    except DBFoxError as error:
        raise _provider_failure(stream=False, error=error) from None
    except Exception as error:
        raise _provider_failure(stream=False, error=error) from None


@router.post(
    "/artifacts/{artifact_id}/representations/{representation_type}/stream",
    response_class=StreamingResponse,
)
def api_artifact_representation_stream(
    artifact_id: str,
    representation_type: str,
    request: ArtifactRepresentationRequest,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    try:
        artifact, descriptor, untrusted_result = _resolve(
            db,
            artifact_id,
            representation_type,
            request,
            expected_kind="stream",
        )
        if not isinstance(untrusted_result, ArtifactRepresentationStream):
            raise TypeError("Canonical stream representation dispatch returned JSON")
        headers = _stream_headers(untrusted_result)
        stream = _bounded_chunks(untrusted_result.chunks)
    except ArtifactRepresentationError as error:
        raise _representation_error(error.code, status_code=error.status_code) from None
    except ValidationError as error:
        log_unexpected_exception(
            logger,
            operation=SafeLogOperation.ARTIFACT_REPRESENTATION_STREAM,
            exc=error,
        )
        raise _representation_error("INVALID_REQUEST", status_code=422) from None
    except DBFoxError as error:
        raise _provider_failure(stream=True, error=error) from None
    except Exception as error:
        raise _provider_failure(stream=True, error=error) from None

    SecurityAuditService(db).record(
        action="artifact.representation.stream",
        outcome="requested",
        resource_type="agent_artifact",
        resource_id=artifact.id,
        correlation_id=f"representation:{artifact.id}:{uuid4().hex}",
        details={
            "representation_type": descriptor.representation_type,
            "operation": request.operation,
        },
    )
    db.commit()
    return StreamingResponse(
        stream,
        media_type=untrusted_result.media_type,
        headers=headers,
    )
