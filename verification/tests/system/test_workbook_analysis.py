"""Golden business calculations through actual Data SQL validation/Artifact execution."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import importlib
import json
from pathlib import Path
from uuid import uuid4

import pytest

from dbfox_dlc_api import ATTACHMENT_RESOURCE_KIND, AttachmentResourceHandle, SessionResourceDiscoveryContext
from engine.agent.artifact import Artifact, ArtifactRelation, ArtifactRelationType
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.resource import ResourceScopeRef
from engine.runtime_composition import build_product_tool_registry
from engine.tools.runtime import ToolKey, ToolRunContext
from scripts.build_dbfox_data_dlc_fixture import build_dbfox_data_dlc_fixture

FIXTURES = Path(__file__).parent / "fixtures" / "conversation_attachments"
BASE_WHERE = '"订单状态" = \'已完成\' AND "支付时间" >= DATE \'2026-10-01\' AND "支付时间" < DATE \'2026-11-01\' AND "币种" = \'CNY\''


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    root = tmp_path_factory.mktemp("workbook-dlc")
    return build_runtime(root)


def build_runtime(root):
    built = build_dbfox_data_dlc_fixture(root / "archives")
    service = DlcPackageService(root / "runtime")
    service.trust_publisher_from_file(built.archive, expected_package_digest=built.package_digest,
                                    expected_publisher_key_id=built.publisher_fingerprint)
    service.install_from_file(built.archive)
    service.set_desired_enabled("dbfox.data", True)
    snapshot = ContributionCompiler(service.storage_root).compile(built_ins=BuiltinContributionSet())
    assert snapshot.activation_failures == ()
    return snapshot, build_product_tool_registry(snapshot)


def tool(runtime, name):
    return runtime[1].require_key(ToolKey(owner_id="dbfox.data", local_name=name))


def source(name="first/orders.xlsx", *, session_id=None):
    path = FIXTURES / name
    return AttachmentResourceHandle(id="att_" + uuid4().hex, session_id=session_id or "session_" + uuid4().hex,
                                    project_id="project-workbook", display_name=path.name,
                                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    byte_count=path.stat().st_size, content_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), path=path)


def prepared(runtime, file=None, **options):
    src = file or source()
    service = tool(runtime, "workbook_prepare").service
    return service.prepare(src, project_id=src.project_id, sheet="订单明细", header_row=1, **options)


def query(runtime, handle, sql):
    validate, execute = tool(runtime, "sql_validate"), tool(runtime, "sql_execute_readonly")
    ref = ResourceScopeRef(kind="dbfox.data.database", id=handle.id, version=handle.scope_version)
    context = lambda name, **kwargs: ToolRunContext.for_invocation(request=None, tool_name=name,
        invocation_id="invocation_" + uuid4().hex, idempotency_key=uuid4().hex,
        scope_refs=(ref,), resources={ref.canonical(): handle}, **kwargs)
    outcome = validate.run(validate.input_model.model_validate({"database_id": handle.id, "sql": sql}), context("sql_validate"))
    if not outcome.output.can_execute:
        module = importlib.import_module(validate.__class__.__module__.rsplit(".", 1)[0] + ".workbook_query")
        module.validate_workbook_query(sql)
        with module.open_workbook_query(handle) as diagnostic:
            diagnostic.execute("EXPLAIN " + sql)
    assert outcome.output.can_execute, outcome.output.model_dump()
    safety_draft, sql_draft = outcome.artifacts
    safety = Artifact(id="safety_" + uuid4().hex, session_id=handle.session_id, run_id="run-workbook", type=safety_draft.type,
                      title=safety_draft.title, payload=safety_draft.payload, resource_refs=(ref,))
    validated = Artifact(id="sql_" + uuid4().hex, session_id=handle.session_id, run_id="run-workbook", type=sql_draft.type,
                         title=sql_draft.title, payload=sql_draft.payload, resource_refs=(ref,),
                         relations=[ArtifactRelation(relation=ArtifactRelationType.VALIDATED_BY, artifact_id=safety.id)])
    artifacts = {safety.id: safety, validated.id: validated}
    observation = validate.project_observation(status="success", output=outcome.output.model_dump(), artifacts=(safety, validated))
    assert observation.facts["validation_artifact_id"] == validated.id
    result = execute.run(execute.input_model.model_validate({"database_id": handle.id, "validation_artifact_id": validated.id}),
                         context("sql_execute_readonly", artifact_loader=artifacts.get,
                                 artifact_relation_loader=lambda _id, _relation: ()))
    assert result.artifacts[0].payload["source"] == handle.source.model_dump(mode="json")
    return result, validated, safety


def test_original_order_totals_and_category_followup(runtime):
    handle = prepared(runtime)
    assert handle.row_count == 17
    assert handle.source.null_counts["完成时间"] > 0
    assert handle.source.currency_values["币种"] == ("CNY",)
    golden = json.loads((FIXTURES / "expected-results.json").read_text(encoding="utf-8"))["cases"]
    for case, suffix in (("original_oct", ""), ("original_oct_home", ' AND "商品类别" = \'家居\'')):
        result, _sql, _safety = query(runtime, handle,
            'SELECT SUM("商品实付金额") AS sales, COUNT(*) AS details, COUNT(DISTINCT "订单编号") AS orders FROM data WHERE ' + BASE_WHERE + suffix)
        row = result.output.rows[0]
        assert Decimal(row["sales"]) == Decimal(golden[case]["total_cents"]) / 100
        assert int(row["details"]) == golden[case]["detail_count"]
        assert int(row["orders"]) == golden[case]["order_count"]
    assert not hasattr(handle, "profile")  # No synthetic network connection.


def test_tied_leaders_and_empty_vs_zero_orders(runtime):
    handle = prepared(runtime)
    september = BASE_WHERE.replace("2026-10-01", "2026-09-01").replace("2026-11-01", "2026-10-01")
    result, _, _ = query(runtime, handle,
        'WITH sales AS (SELECT "商品编码", SUM("商品实付金额") AS amount FROM data WHERE ' + september +
        ' AND "商品类别" = \'家居\' GROUP BY "商品编码") SELECT "商品编码", amount FROM sales WHERE amount=(SELECT MAX(amount) FROM sales) ORDER BY "商品编码"')
    assert [r["商品编码"] for r in result.output.rows] == ["P01", "P02"]
    assert all(Decimal(r["amount"]) == 90 for r in result.output.rows)
    for sku, expected_count, amount in (("not-present", 0, None), ("P05", 1, Decimal(0))):
        outcome, _, _ = query(runtime, handle, 'SELECT COUNT(*) AS n, SUM("商品实付金额") AS amount FROM data WHERE ' + BASE_WHERE + f' AND "商品编码" = \'{sku}\'')
        assert int(outcome.output.rows[0]["n"]) == expected_count
        actual = outcome.output.rows[0]["amount"]
        assert (Decimal(actual) if actual is not None else None) == amount


def test_exact_small_decimals_and_source_rows(runtime):
    handle = prepared(runtime)
    result, _, _ = query(runtime, handle, 'SELECT SUM("商品实付金额") AS sales, MIN(__source_row) AS first_row FROM data WHERE "商品编码" = \'P06\'')
    assert Decimal(result.output.rows[0]["sales"]) == Decimal("0.30")
    assert int(result.output.rows[0]["first_row"]) > 1


def test_workbook_sample_tool_reports_its_supported_boundary(runtime):
    handle = prepared(runtime)
    preview = tool(runtime, "data_preview")
    ref = ResourceScopeRef(kind="dbfox.data.database", id=handle.id, version=handle.scope_version)
    context = ToolRunContext.for_invocation(request=None, tool_name="data_preview",
        invocation_id="workbook-preview", idempotency_key=uuid4().hex,
        scope_refs=(ref,), resources={ref.canonical(): handle})
    with pytest.raises(Exception, match="workbook_inspect.*sql_validate"):
        preview.run(preview.input_model.model_validate({"database_id":handle.id,"table":"main.data"}), context)


def test_overlapping_workbook_reads_keep_configuration_locked(runtime):
    handle = prepared(runtime)
    module = importlib.import_module(tool(runtime, "sql_validate").__class__.__module__.rsplit(".", 1)[0] + ".workbook_query")
    # Keep both connections open: sequential reads cannot catch the shared
    # DuckDB instance rejecting a second SET lock_configuration statement.
    with module.open_workbook_query(handle) as first, module.open_workbook_query(handle) as second:
        assert first.execute("SELECT COUNT(*) FROM data").fetchone()[0] == 17
        assert second.execute("SELECT COUNT(*) FROM data").fetchone()[0] == 17
        assert second.execute("SELECT current_setting('enable_external_access')").fetchone()[0] is False
        with pytest.raises(Exception, match="locked"):
            second.execute("SET memory_limit = '1GB'")


def test_invalid_data_requires_explicit_exclusion(runtime):
    service = tool(runtime, "workbook_prepare").service
    src = source("invalid-amount.xlsx")
    with pytest.raises(Exception, match="混合类型"):
        prepared(runtime, src)
    with pytest.raises(Exception, match="第4行"):
        prepared(runtime, src, column_types={"商品实付金额": "decimal"})
    handle = prepared(runtime, src, column_types={"商品实付金额": "decimal"}, exclude_rows={4: "用户明确排除待核对金额"})
    assert handle.row_count == 16 and handle.source.excluded_rows == {4: "用户明确排除待核对金额"}
    assert service.prepare(src, project_id=src.project_id, sheet="订单明细", header_row=1,
                           column_types={"商品实付金额": "decimal"}, exclude_rows={4: "用户明确排除待核对金额"}).id == handle.id
    with pytest.raises(Exception, match="不存在"):
        prepared(runtime, source("missing-amount.xlsx"), columns=["商品实付金额"])


def test_sheet_ambiguity_empty_and_immutable_id_scoping(runtime):
    service = tool(runtime, "workbook_prepare").service
    ambiguous = source("sheet-choice.xlsx")
    report = service.inspect(ambiguous)
    assert report["table"] is None and len(report["sheets"]) == 2
    with pytest.raises(Exception, match="表头|明细"):
        service.prepare(source("empty.xlsx"), project_id="project-workbook", sheet="订单明细", header_row=1)
    one, two = source(session_id="same-conversation"), source("second/orders.xlsx", session_id="same-conversation")
    a, b = prepared(runtime, one), prepared(runtime, two)
    assert a.id != b.id and a.source.attachment_id != b.source.attachment_id
    provider = runtime[0].session_resource_contributions[0].provider
    context = SessionResourceDiscoveryContext(session_id=one.session_id, project_id=one.project_id, input_boundary=1,
        resource_refs=(ResourceScopeRef(kind=ATTACHMENT_RESOURCE_KIND, id=one.id, version=one.content_sha256),))
    assert [r.id for r in provider(context)] == [a.id]
    assert provider(context.model_copy(update={"session_id": "different-conversation"})) == ()
    assert provider(context.model_copy(update={"resource_refs": ()})) == ()


@pytest.mark.parametrize("sql", [
    "SELECT * FROM read_csv('anything.csv')", "SELECT * FROM other_table",
    "SELECT current_setting('memory_limit') FROM data", "SELECT TRY_CAST('bad' AS DECIMAL) FROM data",
    "SELECT * FROM data; SELECT * FROM data", "ATTACH 'anything' AS other", "SELECT * FROM information_schema.tables",
])
def test_workbook_sql_restrictions_use_existing_validation(runtime, sql):
    handle = prepared(runtime)
    validate = tool(runtime, "sql_validate")
    ref = ResourceScopeRef(kind="dbfox.data.database", id=handle.id, version=handle.scope_version)
    context = ToolRunContext.for_invocation(request=None, tool_name="sql_validate", idempotency_key="reject",
                                           scope_refs=(ref,), resources={ref.canonical(): handle})
    outcome = validate.run(validate.input_model.model_validate({"database_id": handle.id, "sql": sql}), context)
    assert not outcome.output.can_execute


def test_original_styled_preview_and_stale_formula_cache(runtime):
    module = importlib.import_module(tool(runtime, "workbook_inspect").__class__.__module__.rsplit(".", 1)[0] + ".workbook_view")
    src = source("P03-stale-cache.xlsx")
    data = module.preview(src, "订单预览")
    cells = {(c["r"], c["c"]): c for c in data["sheets"][0]["cells"]}
    assert cells[4, 0]["v"] == "000001"
    assert cells[4, 2]["v"] == 46296
    assert cells[25, 5]["v"] == 999.5 and cells[25, 5]["formula"] == "=SUM(F5:F24)"
    assert data["sha256"] == src.content_sha256 and data["readonly"]


def test_derived_file_rebuild_and_owner_retirement(runtime):
    src = source()
    handle = prepared(runtime, src)
    handle.path.unlink()
    rebuilt = prepared(runtime, src)
    assert rebuilt.id == handle.id and rebuilt.scope_version == handle.scope_version
    outcome, _, _ = query(runtime, rebuilt, 'SELECT COUNT(*) AS n FROM data')
    assert int(outcome.output.rows[0]["n"]) == 17
    store = tool(runtime, "workbook_prepare").service.store
    store.retire_session(src.session_id)
    store.retire_session(src.session_id)
    assert store.get_workbook(handle.id) is None and not handle.path.exists()
    assert src.path.exists()


def test_oversized_merge_is_rejected_before_normal_parser(runtime, tmp_path):
    from dataclasses import replace
    import zipfile
    src = source("P01-styled.xlsx")
    target = tmp_path / "merge-bomb.xlsx"
    with zipfile.ZipFile(src.path) as original, zipfile.ZipFile(target, "w") as altered:
        for name in original.namelist():
            content = original.read(name)
            if name == "xl/worksheets/sheet1.xml":
                import re
                content, changed = re.subn(rb'(<(?:\w+:)?mergeCell\b[^>]*\bref=")[^"]+"', rb'\g<1>A1:XFD1048576"', content, count=1)
                assert changed == 1
            altered.writestr(name, content)
    hostile = replace(src, path=target, byte_count=target.stat().st_size, content_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    module = importlib.import_module(tool(runtime, "workbook_inspect").__class__.__module__.rsplit(".", 1)[0] + ".workbook_view")
    with pytest.raises(Exception, match="合并区域"):
        module.preview(hostile, "订单预览")
