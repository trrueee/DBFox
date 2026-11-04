"""Sectioned workbook calculations and source/progress contracts."""
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from uuid import uuid4

from openpyxl import Workbook, load_workbook
import pytest

from dbfox_dlc_api import AttachmentResourceHandle, ToolInputError
from engine.agent.progress_guard import observation_evidence_signatures
from verification.testkit.workbook_fixtures import sectioned_plan
from verification.tests.system.test_workbook_analysis import build_runtime, query, tool


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    return build_runtime(tmp_path_factory.mktemp("sectioned-workbook-dlc"))


@pytest.fixture
def plan(tmp_path):
    path = sectioned_plan(tmp_path / "plan.xlsx")
    return AttachmentResourceHandle(id="att_" + uuid4().hex, session_id="session_" + uuid4().hex,
        project_id="project-plan", display_name="plan.xlsx", path=path, byte_count=path.stat().st_size,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def prepare(runtime, plan, **changes):
    prepare_tool = tool(runtime, "workbook_prepare")
    options = {"attachment_id": plan.id, "sheet": "Sheet1", "header_row": 3,
        "columns": ["课程代码", "课程名称", "开课学期", "学分"],
        "column_types": {"开课学期": "text", "学分": "decimal"},
        "regions": [{"data_range": r, "context_cells": {"课程类别": cell}} for r, cell in
            (("A4:E13", "A2"), ("A17:E44", "A16"), ("A49:E64", "A47"), ("A67:E92", "A65"))]}
    options.update(changes)
    validated = prepare_tool.input_model.model_validate(options)
    return prepare_tool.service.prepare(plan, project_id=plan.project_id,
        **validated.model_dump(exclude={"attachment_id", "regions"}), regions=validated.regions)


def test_sectioned_plan_calculation_and_source_provenance(runtime, plan):
    handle = prepare(runtime, plan)
    assert handle.row_count == 7
    assert handle.source.unselected_nonempty_rows > 0
    assert [c.source_column for c in handle.columns] == [2, 3, 4, 5, None]
    assert [r.context_cells for r in handle.source.regions] == [
        {"课程类别": "A2"}, {"课程类别": "A16"}, {"课程类别": "A47"}, {"课程类别": "A65"}]
    result, _, _ = query(runtime, handle,
        'SELECT "课程类别", SUM("学分") AS credits FROM data GROUP BY "课程类别" ORDER BY MIN(__source_row)')
    assert [Decimal(row["credits"]) for row in result.output.rows] == [Decimal("8.5"), Decimal("3.25"), Decimal("4"), Decimal("4")]
    # Only the explicitly selected listed courses are summed; 164 and section
    # requirement labels are not added to the course inventory.
    result, _, _ = query(runtime, handle,
        'SELECT SUM("学分") AS credits FROM data WHERE __source_row < 65')
    assert Decimal(result.output.rows[0]["credits"]) == Decimal("15.75")
    result, _, _ = query(runtime, handle,
        'SELECT __source_row, "课程代码", "开课学期" FROM data ORDER BY __source_row')
    assert [int(row["__source_row"]) for row in result.output.rows] == [4, 5, 17, 18, 49, 67, 68]
    assert result.output.rows[0]["课程代码"] == "0001"
    assert result.output.rows[2]["开课学期"] == "1,2"  # Never divide credits among options.
    assert prepare(runtime, plan).id == handle.id
    assert prepare(runtime, plan, regions=[{"data_range": "A4:E13"}]).id != handle.id


def test_header_selection_ignores_unselected_blank_and_invalid_columns(runtime, plan):
    # K112 is styled but empty; header F:K must not invalidate selected A:E.
    handle = prepare(runtime, plan, regions=[{"data_range": "A4:E13"}], columns=["课程名称", "学分"],
                     column_types={"学分": "decimal"})
    assert handle.row_count == 2
    with pytest.raises(ToolInputError, match="重复|不存在"):
        prepare(runtime, plan, columns=["学分", "学分"])
    with pytest.raises(ToolInputError, match="不存在"):
        prepare(runtime, plan, columns=["不存在"], column_types={})
    workbook = load_workbook(plan.path)
    workbook["Sheet1"]["B4"] = 1
    workbook["Sheet1"]["B4"].number_format = "0000"
    workbook.save(plan.path); workbook.close()
    numeric_code = replace(plan, content_sha256=hashlib.sha256(plan.path.read_bytes()).hexdigest())
    handle = prepare(runtime, numeric_code)
    result, _, _ = query(runtime, handle, 'SELECT "课程代码" FROM data WHERE __source_row=4')
    assert result.output.rows[0]["课程代码"] == "0001"


@pytest.mark.parametrize("regions,match", [
    ([{"data_range": "A4:E18"}, {"data_range": "A17:E44"}], "重叠"),
    ([{"data_range": "A3:E13"}], "表头之后"),
    ([{"data_range": "A4:D13"}], "全部所选字段"),
    ([{"data_range": "A4:E113"}], "实际数据边界"),
    ([{"data_range": "A:E"}], "单元格范围"),
    ([{"data_range": "Sheet1!A4:E13"}], "单元格范围"),
    ([{"data_range": "A4:E13", "context_cells": {"课程类别": "E14"}}], "非空文本"),
    ([{"data_range": "A4:E13", "context_cells": {"课程类别": "A2"}}, {"data_range": "A17:E44"}], "相同"),
    ([{"data_range": "A4:E13", "context_cells": {"学分": "A2"}}], "重复"),
])
def test_region_boundaries_reject_ambiguous_or_duplicate_calculations(runtime, plan, regions, match):
    with pytest.raises(ToolInputError, match=match):
        prepare(runtime, plan, regions=regions)


def test_regions_do_not_silently_drop_subtotals_repeated_headers_or_bad_records(runtime, plan):
    with pytest.raises(ToolInputError, match="汇总行"):
        prepare(runtime, plan, regions=[{"data_range": "A4:E14"}])
    with pytest.raises(ToolInputError, match="重复表头"):
        prepare(runtime, plan, regions=[{"data_range": "A48:E64"}])
    with pytest.raises(ToolInputError, match="实际存在"):
        prepare(runtime, plan, exclude_rows={100: "明确排除"})
    workbook = load_workbook(plan.path)
    workbook["Sheet1"]["E18"] = None
    workbook.save(plan.path); workbook.close()
    altered = replace(plan, content_sha256=hashlib.sha256(plan.path.read_bytes()).hexdigest())
    with pytest.raises(ToolInputError, match="第18行.*缺少"):
        prepare(runtime, altered)
    # Selecting just the numeric column must still notice the missing amount in
    # a nonempty business row, rather than treating that row as an empty line.
    with pytest.raises(ToolInputError, match="第18行.*缺少"):
        prepare(runtime, altered, columns=["学分"], column_types={"学分": "decimal"})


def test_inspection_reaches_later_notes_and_has_stable_durable_progress(runtime, plan):
    inspect = tool(runtime, "workbook_inspect")
    service = inspect.service
    list_report = service.inspect(plan)
    top = service.inspect(plan, sheet="Sheet1")
    later = service.inspect(plan, sheet="Sheet1", cell_range="A65:K112")
    assert top["table"]["candidate_headers"][0]["row"] == 3
    assert top["table"]["candidate_headers"][0]["columns"] == ["A3", "B3", "C3", "D3", "E3"]
    assert any(row["row"] == 4 for row in top["table"]["samples"])
    assert any(row["row"] == 100 for row in later["table"]["samples"])
    assert later["table"]["next_range"] is None
    assert not later["full_data_scanned"]
    other = service.inspect(plan, sheet="必修课程（开课学期）")
    observations = [inspect.project_observation(status="success", output={"workbook": report}, artifacts=())
                    for report in (list_report, top, later, other)]
    signatures = [observation_evidence_signatures(tool_name="workbook_inspect", status="success", facts=o.facts, error_code="")
                  for o in observations]
    assert len({next(iter(s)) for s in signatures}) == 4
    repeated = inspect.project_observation(status="success", output={"workbook": service.inspect(plan, sheet="Sheet1")}, artifacts=())
    assert repeated.facts == observations[1].facts
    assert "课程A" not in json.dumps(observations[1].facts, ensure_ascii=False)
    assert len(json.dumps({"workbook": later}, ensure_ascii=False).encode()) < inspect.execution.max_output_bytes
    prepared = prepare(runtime, plan)
    projection = tool(runtime, "workbook_prepare").project_observation(status="success", output={
        "database_id": prepared.id, "resource_version": prepared.scope_version, "row_count": prepared.row_count,
        "source": prepared.source.model_dump(mode="json")}, artifacts=())
    assert projection.facts["row_count"] == 7 and projection.facts["source"]["regions"]


def test_inspection_is_bounded_and_redacts_sensitive_later_pages(runtime, tmp_path):
    path = tmp_path / "sensitive.xlsx"
    workbook = Workbook(); sheet = workbook.active; sheet.title = "数据"
    sheet.append(["姓名", "password"])
    for _ in range(70):
        sheet.append(["测试记录" * 100, "private-value-must-not-leak"])
    workbook.save(path); workbook.close()
    source = AttachmentResourceHandle(id="att_" + uuid4().hex, session_id="private-session", project_id="private-project",
        display_name=path.name, path=path, byte_count=path.stat().st_size,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    service = tool(runtime, "workbook_inspect").service
    report = service.inspect(source, sheet="数据", cell_range="A35:B70")
    assert "private-value-must-not-leak" not in json.dumps(report)
    assert report["table"]["samples"][0]["truncated_columns"] == ["A"]
    assert report["table"]["next_range"] == "A71:B71"
    with pytest.raises(ToolInputError, match="64行"):
        service.inspect(source, sheet="数据", cell_range="A1:B70")


def test_inspection_byte_budget_pages_without_skipping_rows(runtime, tmp_path):
    path = tmp_path / "wide.xlsx"
    workbook = Workbook(); sheet = workbook.active; sheet.title = "宽表"
    sheet.append([f"field_{i}" for i in range(16)])
    for _ in range(40):
        sheet.append(["有界文本" * 40] * 16)
    workbook.save(path); workbook.close()
    source = AttachmentResourceHandle(id="att_" + uuid4().hex, session_id="wide-session", project_id="wide-project",
        display_name=path.name, path=path, byte_count=path.stat().st_size,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    inspect = tool(runtime, "workbook_inspect")
    cell_range, seen = "A1:P41", []
    while cell_range:
        report = inspect.service.inspect(source, sheet="宽表", cell_range=cell_range)
        assert len(json.dumps({"workbook": report}, ensure_ascii=False).encode()) < inspect.execution.max_output_bytes
        seen.extend(row["row"] for row in report["table"]["samples"])
        cell_range = report["table"]["next_range"]
    assert seen == list(range(1, 42))
