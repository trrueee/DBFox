"""LangSmith adapter for DBFox Agent Eval.

Provides bidirectional sync between DBFox eval cases and LangSmith datasets,
experiments, and feedback.  LangSmith is optional — all eval functionality
works without it.
"""

from __future__ import annotations

import logging
from numbers import Real
import re
from typing import Any, Callable

from pydantic import ValidationError

from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception
from engine.evaluation.schemas import (
    AgentEvalCase,
    AgentEvalCaseResult,
    AgentEvalExpectation,
    AgentEvalInput,
    AnswerExpectation,
)
from engine.llm.endpoint_policy import LlmEndpointPolicyError, validate_runtime_llm_api_base
from engine.security.credential_vault import (
    CredentialKind,
    CredentialVault,
    get_credential_vault,
)

logger = logging.getLogger("dbfox.eval.langsmith_adapter")
DEFAULT_LANGSMITH_ENDPOINT = "https://api.smith.langchain.com"
_EVAL_CATEGORIES = frozenset(
    {
        "chat",
        "schema",
        "semantic",
        "sql_generation",
        "data_lookup",
        "result_analysis",
        "policy",
        "replan",
        "artifact",
    }
)


def _feedback_source_type(feedback: Any) -> str:
    source = getattr(feedback, "feedback_source", None)
    if isinstance(source, dict):
        return str(source.get("type") or "").lower()
    return str(getattr(source, "type", "") or "").lower()


def _is_human_failure_feedback(feedback: Any) -> bool:
    if _feedback_source_type(feedback) == "model":
        return False
    score = getattr(feedback, "score", None)
    value = getattr(feedback, "value", None)
    correction = getattr(feedback, "correction", None)
    if score is False or value is False:
        return True
    if isinstance(score, Real) and not isinstance(score, bool):
        return float(score) <= 0
    return correction is not None and score is not True


def _structured_correction(feedbacks: list[Any]) -> dict[str, Any]:
    for feedback in reversed(feedbacks):
        correction = getattr(feedback, "correction", None)
        if isinstance(correction, dict):
            return correction
    return {}


def _safe_case_id(run_id: object) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(run_id)).strip("._-")
    return f"langsmith_{normalized or 'run'}"[:128]


class LangSmithAdapter:
    """Bridges DBFox eval cases to LangSmith datasets and experiments.

    Usage:
        adapter = LangSmithAdapter(
            credential_id="cred_langsmith_api_key_...",
        )
        adapter.sync_dataset("dbfox-regression", cases)
        adapter.run_experiment("dbfox-regression", my_agent_runner)
    """

    def __init__(
        self,
        *,
        credential_id: str | None = None,
        credential_vault: CredentialVault | None = None,
        endpoint: str | None = None,
    ) -> None:
        """Create an optional LangSmith integration with an opaque credential.

        LangSmith credentials are never inferred from process environment or
        dotenv files.  The credential is resolved only while an operation is
        being performed, from the OS-backed credential vault.
        """
        self._credential_id = str(credential_id or "").strip()
        self._credential_vault = credential_vault
        self._endpoint = str(endpoint or DEFAULT_LANGSMITH_ENDPOINT).strip()

    @property
    def available(self) -> bool:
        """Check whether a vault credential can configure a LangSmith client."""
        return self._create_client() is not None

    def _create_client(self) -> Any | None:
        """Resolve a transient LangSmith client without any environment fallback."""
        if not self._credential_id:
            return None

        # LangSmith is optional telemetry rather than an LLM provider, but it
        # still receives a vault-held bearer credential.  Its optional endpoint
        # override therefore passes through the same runtime DNS/IP admission
        # boundary before the vault is read.  This prevents the otherwise
        # unused override from becoming an SSRF/credential-exfiltration path.
        try:
            safe_endpoint = validate_runtime_llm_api_base(self._endpoint)
        except LlmEndpointPolicyError:
            return None

        try:
            from langsmith import Client  # type: ignore[import-untyped]
        except ImportError:
            return None

        try:
            vault = self._credential_vault or get_credential_vault()
            secret = vault.get(
                self._credential_id,
                expected_kind=CredentialKind.LANGSMITH_API_KEY,
            )
            if not secret:
                return None
            return Client(api_key=secret, api_url=safe_endpoint)
        except Exception:
            # LangSmith is optional.  Do not expose vault/provider details or
            # keep a plaintext fallback alive when its secure dependency fails.
            return None

    def sync_dataset(
        self,
        dataset_name: str,
        cases: list[AgentEvalCase],
    ) -> None:
        """Sync DBFox eval cases to a LangSmith dataset.

        Creates the dataset if it doesn't exist; upserts examples.
        """
        client = self._create_client()
        if client is None:
            logger.warning("LangSmith not available — skipping dataset sync.")
            return

        try:
            # Create or get dataset
            try:
                dataset = client.create_dataset(dataset_name)
            except Exception:
                datasets = list(client.list_datasets(dataset_name=dataset_name))
                dataset = datasets[0] if datasets else client.create_dataset(dataset_name)

            for case in cases:
                inputs = {"question": case.input.question}
                if case.input.workspace_context:
                    inputs["workspace_context"] = case.input.workspace_context
                outputs = case.expected.model_dump(mode="json")
                client.create_example(
                    inputs=inputs,
                    outputs=outputs,
                    dataset_id=dataset.id,
                    metadata={"case_id": case.id, "category": case.category},
                )

            logger.info("Synced %d cases to LangSmith dataset '%s'.", len(cases), dataset_name)
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_EVAL_RUN,
                exc=exc,
                level="warning",
            )

    def run_experiment(
        self,
        dataset_name: str,
        agent_runner: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        experiment_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Run a LangSmith experiment against a dataset.

        Args:
            dataset_name: Name of the LangSmith dataset.
            agent_runner: Async function that takes inputs dict and returns outputs dict.
            experiment_name: Optional experiment name prefix.

        Returns:
            List of experiment result dicts.
        """
        client = self._create_client()
        if client is None:
            logger.warning("LangSmith not available — skipping experiment.")
            return []

        try:
            datasets = list(client.list_datasets(dataset_name=dataset_name))
            if not datasets:
                logger.warning("Dataset '%s' not found in LangSmith.", dataset_name)
                return []

            examples = list(client.list_examples(dataset_id=datasets[0].id))
            results: list[dict[str, Any]] = []

            for example in examples:
                inputs = example.inputs
                outputs = agent_runner(inputs)
                client.create_run(
                    name=experiment_name or "dbfox-agent-eval",
                    inputs=inputs,
                    outputs=outputs,
                    reference_example_id=example.id,
                    run_type="chain",
                )
                results.append({"example_id": example.id, "outputs": outputs})

            logger.info("Experiment completed: %d examples evaluated.", len(results))
            return results
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_EVAL_RUN,
                exc=exc,
                level="warning",
            )
            return []

    def upload_feedback(
        self,
        run_id: str,
        scores: dict[str, float],
        *,
        comment: str | None = None,
    ) -> None:
        """Upload feedback scores to a LangSmith run."""
        client = self._create_client()
        if client is None:
            return
        try:
            for key, score in scores.items():
                client.create_feedback(
                    run_id=run_id,
                    key=key,
                    score=score,
                    comment=comment,
                )
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_EVAL_RUN,
                exc=exc,
                level="warning",
            )

    def import_annotated_failures(
        self,
        project_name: str,
    ) -> list[AgentEvalCase]:
        """Import human-annotated failure runs from LangSmith as new eval cases."""
        normalized_project = project_name.strip()
        if not normalized_project:
            return []
        client = self._create_client()
        if client is None:
            return []
        try:
            runs = list(
                client.list_runs(
                    project_name=normalized_project,
                    is_root=True,
                    select=["id", "inputs", "extra", "tags", "error"],
                    limit=500,
                )
            )
            run_ids = [getattr(run, "id", None) for run in runs]
            run_ids = [run_id for run_id in run_ids if run_id is not None]
            feedback_by_run: dict[str, list[Any]] = {}
            for offset in range(0, len(run_ids), 100):
                for feedback in client.list_feedback(run_ids=run_ids[offset : offset + 100]):
                    run_id = getattr(feedback, "run_id", None)
                    if run_id is None or not _is_human_failure_feedback(feedback):
                        continue
                    feedback_by_run.setdefault(str(run_id), []).append(feedback)

            cases: list[AgentEvalCase] = []
            for run in runs:
                run_id = getattr(run, "id", None)
                feedbacks = feedback_by_run.get(str(run_id), [])
                if run_id is None or not feedbacks:
                    continue
                inputs = getattr(run, "inputs", None)
                if not isinstance(inputs, dict):
                    continue
                question = str(inputs.get("question") or "").strip()
                if not question:
                    continue
                correction = _structured_correction(feedbacks)
                raw_expected = correction.get("expected")
                if not isinstance(raw_expected, dict):
                    raw_expected = inputs.get("expected")
                try:
                    expected = (
                        AgentEvalExpectation.model_validate(raw_expected)
                        if isinstance(raw_expected, dict)
                        else AgentEvalExpectation(answer=AnswerExpectation())
                    )
                except ValidationError:
                    continue

                extra = getattr(run, "extra", None)
                metadata = extra.get("metadata", {}) if isinstance(extra, dict) else {}
                raw_category = correction.get("category") or (
                    metadata.get("eval_category") if isinstance(metadata, dict) else None
                )
                category = str(raw_category or "chat")
                if category not in _EVAL_CATEGORIES:
                    category = "chat"
                workspace_context = inputs.get("workspace_context")
                if not isinstance(workspace_context, dict):
                    workspace_context = None
                feedback_keys = sorted(
                    {
                        str(getattr(feedback, "key", "")).strip()
                        for feedback in feedbacks
                        if str(getattr(feedback, "key", "")).strip()
                    }
                )
                tags = sorted(
                    {
                        *[str(tag) for tag in (getattr(run, "tags", None) or [])],
                        "annotated-failure",
                        "langsmith-import",
                    }
                )
                cases.append(
                    AgentEvalCase(
                        id=_safe_case_id(run_id),
                        category=category,  # type: ignore[arg-type]
                        description=str(correction.get("description") or "Imported LangSmith failure"),
                        input=AgentEvalInput(
                            question=question,
                            workspace_context=workspace_context,
                            datasource_fixture=inputs.get("datasource_fixture"),
                            project_semantics_fixture=inputs.get("project_semantics_fixture"),
                        ),
                        expected=expected,
                        metadata={
                            "imported_from": "langsmith",
                            "langsmith_run_id": str(run_id),
                            "feedback_keys": feedback_keys,
                        },
                        tags=tags,
                    )
                )
            return sorted(cases, key=lambda case: case.id)
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.AGENT_EVAL_RUN,
                exc=exc,
                level="warning",
            )
            return []
