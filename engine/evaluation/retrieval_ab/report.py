from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from engine.evaluation.retrieval_ab.metrics import CaseEvaluationResult, VariantSummary


@dataclass(frozen=True)
class ReportPaths:
    summary_json: Path
    cases_csv: Path
    cases_jsonl: Path
    markdown_report: Path


def write_reports(
    *,
    output_dir: str | Path,
    benchmark: str,
    variants: tuple[str, ...],
    summaries: Iterable[VariantSummary],
    cases: Iterable[CaseEvaluationResult],
) -> ReportPaths:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = f"{benchmark}_{'_'.join(variants)}"
    summary_path = out / f"{prefix}_summary.json"
    cases_path = out / f"{prefix}_cases.csv"
    cases_jsonl_path = out / f"{prefix}_cases.jsonl"
    markdown_path = out / f"{prefix}_report.md"

    summary_rows = tuple(summaries)
    case_rows = tuple(cases)
    summary_path.write_text(
        json.dumps(
            {
                "benchmark": benchmark,
                "variants": variants,
                "summaries": [asdict(row) for row in summary_rows],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_cases_csv(cases_path, case_rows)
    _write_cases_jsonl(cases_jsonl_path, case_rows)
    markdown_path.write_text(_render_markdown(benchmark, variants, summary_rows), encoding="utf-8")
    return ReportPaths(
        summary_json=summary_path,
        cases_csv=cases_path,
        cases_jsonl=cases_jsonl_path,
        markdown_report=markdown_path,
    )


def _write_cases_csv(path: Path, cases: tuple[CaseEvaluationResult, ...]) -> None:
    fieldnames = [
        "case_id",
        "db_id",
        "variant",
        "question",
        "search_expressions",
        "mode",
        "expected_tables",
        "retrieved_tables_top5",
        "table_recall_at_5",
        "expected_columns",
        "retrieved_columns_top10",
        "column_recall_at_10",
        "actual_sql",
        "used_tables",
        "used_columns",
        "sql_uses_expected_tables",
        "sql_uses_expected_columns",
        "query_execution_success",
        "task_solved",
        "latency_ms",
        "retrieval_latency_ms",
        "embedding_build_time_ms",
        "vector_available",
        "step_count",
        "db_search_call_count",
        "failure_class",
        "failure_reason",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for case in cases:
            data = asdict(case)
            writer.writerow({field: _csv_value(data.get(field)) for field in fieldnames})


def _write_cases_jsonl(path: Path, cases: tuple[CaseEvaluationResult, ...]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for case in cases:
            fh.write(json.dumps(asdict(case), ensure_ascii=False) + "\n")


def _render_markdown(
    benchmark: str,
    variants: tuple[str, ...],
    summaries: tuple[VariantSummary, ...],
) -> str:
    lines = [
        f"# {benchmark.title()} Retrieval A/B/n Report",
        "",
        f"Variants: {', '.join(variants)}",
        "",
        "| variant | table_recall@5 | column_recall@10 | task_solve_rate | query_exec_success | p95_latency | p95_retrieval_ms | p95_embedding_ms | avg_embedding_ms | safety_violations |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in summaries:
        lines.append(
            "| "
            f"{row.variant} | "
            f"{_pct(row.table_recall_at_5)} | "
            f"{_pct(row.column_recall_at_10)} | "
            f"{_pct(row.task_solve_rate)} | "
            f"{_pct(row.query_execution_success_rate)} | "
            f"{row.p95_latency_ms if row.p95_latency_ms is not None else ''} | "
            f"{_number(row.p95_retrieval_latency_ms)} | "
            f"{_number(row.p95_embedding_build_time_ms)} | "
            f"{_number(row.avg_embedding_build_time_ms)} | "
            f"{row.safety_violations} |"
        )
    lines.extend(["", "## Failure breakdown", ""])
    lines.append("| variant | failure_class | count | rate |")
    lines.append("| --- | --- | ---: | ---: |")
    for row in summaries:
        for failure_class, count in row.failure_class_counts.items():
            rate = row.failure_class_rates.get(failure_class, 0.0)
            lines.append(f"| {row.variant} | {failure_class} | {count} | {_pct(rate)} |")
    lines.append("")
    return "\n".join(lines)


def _csv_value(value: object) -> object:
    if isinstance(value, (tuple, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _number(value: float | int | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.1f}"
