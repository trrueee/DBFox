"""Composition root for the default DBFox completion policy.

Runtime product behavior stays the same as before; Completion Core no longer
imports a concrete data capability or Artifact family.
"""

from __future__ import annotations


def default_completion_constraints():
    from engine.agent.completion_data import DataResultCitationConstraint

    return (DataResultCitationConstraint(),)


def default_completion_support():
    from engine.agent.completion_data import DataCompletionSupport

    return DataCompletionSupport()
