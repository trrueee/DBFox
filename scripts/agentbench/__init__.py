"""DBFox AgentBench evaluation package.

The package is intentionally located under ``scripts``: it drives the real
production Harness, but is not part of the packaged Sidecar runtime.
"""

from scripts.agentbench.schema import DatasetManifest, EvalCase, load_manifest

__all__ = ["DatasetManifest", "EvalCase", "load_manifest"]
