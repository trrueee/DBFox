"""Calibration of the evaluator before it is trusted to grade an Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from verification.bench.capabilities.dbfox_data.agent.schema import EvalCase, Verdict
from verification.bench.capabilities.dbfox_data.agent.scoring import (
    TrialScore,
    TrialTrace,
    score_trial,
)


class CalibrationFixture(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,79}$")
    kind: Literal["golden", "sabotaged", "equivalent", "infrastructure"]
    case: EvalCase
    trace: TrialTrace
    expected_verdict: Verdict
    expected_safety_veto: bool = False


class CalibrationSuite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    suite_id: str
    fixtures: tuple[CalibrationFixture, ...] = Field(min_length=1)


class CalibrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_id: str
    expected_verdict: Verdict
    actual: TrialScore
    calibrated: bool


def load_calibration(path: Path) -> CalibrationSuite:
    return CalibrationSuite.model_validate_json(path.read_text(encoding="utf-8"))


def run_calibration(suite: CalibrationSuite) -> tuple[CalibrationResult, ...]:
    return tuple(
        CalibrationResult(
            fixture_id=fixture.fixture_id,
            expected_verdict=fixture.expected_verdict,
            actual=(actual := score_trial(fixture.case, fixture.trace)),
            calibrated=(
                actual.verdict is fixture.expected_verdict
                and actual.safety_veto is fixture.expected_safety_veto
            ),
        )
        for fixture in suite.fixtures
    )
