"""LangSmith adapter for DBFox Agent Eval.

Provides bidirectional sync between DBFox eval cases and LangSmith datasets,
experiments, and feedback.  LangSmith is optional — all eval functionality
works without it.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from engine.evaluation.schemas import AgentEvalCase, AgentEvalCaseResult

logger = logging.getLogger("dbfox.eval.langsmith_adapter")


class LangSmithAdapter:
    """Bridges DBFox eval cases to LangSmith datasets and experiments.

    Usage:
        adapter = LangSmithAdapter()
        adapter.sync_dataset("dbfox-regression", cases)
        adapter.run_experiment("dbfox-regression", my_agent_runner)
    """

    def __init__(self) -> None:
        self._ls_client = None

    @property
    def available(self) -> bool:
        """Check if LangSmith is installed and configured."""
        if self._ls_client is not None:
            return True
        try:
            import langsmith  # noqa: F401
            import os
            if os.environ.get("LANGCHAIN_API_KEY"):
                self._ls_client = True
                return True
        except ImportError:
            pass
        return False

    def sync_dataset(
        self,
        dataset_name: str,
        cases: list[AgentEvalCase],
    ) -> None:
        """Sync DBFox eval cases to a LangSmith dataset.

        Creates the dataset if it doesn't exist; upserts examples.
        """
        if not self.available:
            logger.warning("LangSmith not available — skipping dataset sync.")
            return

        try:
            from langsmith import Client  # type: ignore[import-untyped]
            client = Client()

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
            logger.warning("LangSmith sync failed: %s", exc)

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
        if not self.available:
            logger.warning("LangSmith not available — skipping experiment.")
            return []

        try:
            from langsmith import Client  # type: ignore[import-untyped]
            client = Client()

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
            logger.warning("LangSmith experiment failed: %s", exc)
            return []

    def upload_feedback(
        self,
        run_id: str,
        scores: dict[str, float],
        *,
        comment: str | None = None,
    ) -> None:
        """Upload feedback scores to a LangSmith run."""
        if not self.available:
            return
        try:
            from langsmith import Client  # type: ignore[import-untyped]
            client = Client()
            for key, score in scores.items():
                client.create_feedback(
                    run_id=run_id,
                    key=key,
                    score=score,
                    comment=comment,
                )
        except Exception as exc:
            logger.warning("LangSmith feedback upload failed: %s", exc)

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
