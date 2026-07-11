"""LangSmith adapter for DBFox Agent Eval.

Provides bidirectional sync between DBFox eval cases and LangSmith datasets,
experiments, and feedback.  LangSmith is optional — all eval functionality
works without it.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception
from engine.evaluation.schemas import AgentEvalCase, AgentEvalCaseResult
from engine.security.credential_vault import (
    CredentialKind,
    CredentialVault,
    get_credential_vault,
)

logger = logging.getLogger("dbfox.eval.langsmith_adapter")
DEFAULT_LANGSMITH_ENDPOINT = "https://api.smith.langchain.com"


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
            return Client(api_key=secret, api_url=self._endpoint)
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
        if not self.available:
            return []
        # Future: query LangSmith for runs with low human feedback scores
        # and convert them into AgentEvalCase definitions
        logger.info("LangSmith annotated failure import not yet implemented.")
        return []
