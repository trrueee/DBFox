"""Signed Data DLC and real RunLoop/worker/Representation, scripted provider only."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import re

import httpx
from openai import AsyncOpenAI
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from dbfox_dlc_api import RequestedResourceRef, ToolKey
from engine.agent.context import ContextAssembler
from engine.agent.providers.openai import OpenAIModelAdapter
from engine.agent.references import ConversationInputReference
from engine.agent.repositories.session import SessionRepository
from engine.attachments import ATTACHMENT_RESOURCE_KIND, AttachmentService
from engine.api.agent_results import api_artifact_representation_read, api_artifact_representation_stream
from engine.dlc import DlcPackageService
from engine.models import AgentArtifactRecord, AgentRun, AgentToolInvocation, Project
from engine.representation import ArtifactRepresentationRequest, DATAFRAME_REPRESENTATION_TYPE
from engine.runtime_composition import (active_runtime_snapshot, authorize_conversation_resources,
    build_product_run_loop, build_product_tool_registry, discover_run_resources, initialize_runtime_snapshot, set_active_runtime_snapshot)
from scripts.build_dbfox_data_dlc_fixture import build_dbfox_data_dlc_fixture
from verification.support.metadata import create_migrated_metadata_engine
from verification.testkit.workbook_fixtures import sectioned_plan

FIXTURES = Path(__file__).parent / "fixtures" / "conversation_attachments"


class WorkbookProvider:
    """Consumes IDs and computed values from actual model-visible tool outputs."""
    def __init__(self, registry, *, followup=False):
        self.registry, self.followup = registry, followup
        self.requests, self.outputs, self.errors = [], {}, []
        self.step, self.source_id, self.database_id, self.validation_id = 0, None, None, None
        self.rows, self.result_id = None, None
        self.expected_failures = {}

    def respond(self, request):
        try:
            return self._respond(request)
        except Exception as exc:
            self.errors.append(repr(exc))
            raise

    def _respond(self, request):
        payload = json.loads(request.content)
        self.requests.append(payload)
        trusted_prompt = str(payload.get("instructions") or "") + json.dumps([
            item for item in payload["input"] if item.get("role") in ("system", "developer")
        ])
        assert "dbfox.data/workbook_analysis@1" in trusted_prompt
        assert "before workbook_prepare" in trusted_prompt
        text = json.dumps(payload["input"], ensure_ascii=False)
        if self.source_id is None:
            self.source_id = re.search(r"att_[0-9a-f]{32}", text).group()
        if self.followup and self.database_id is None:
            self.database_id = re.search(r"wb_[0-9a-f]{32}", text).group()
        for item in payload["input"]:
            if item.get("type") != "function_call_output" or item["call_id"] in self.outputs:
                continue
            result = json.loads(item["output"])
            self.outputs[item["call_id"]] = result
            if item["call_id"] in self.expected_failures:
                assert result["status"] == "failed" and result["error_code"] == self.expected_failures[item["call_id"]], result
                continue
            assert result["status"] == "succeeded", result
            facts = result["facts"]
            if "database_id" in facts:
                self.database_id = facts["database_id"]
            if "can_execute" in facts:
                assert facts["can_execute"]
                self.validation_id = facts["validation_artifact_id"]
            if "rows" in facts:
                self.rows = facts["rows"]
                self.result_id = facts["artifact_id"]
        plan = self.plan()
        items = []
        if self.step < len(plan):
            name, arguments = plan[self.step]
            wire_name = self.registry.provider_name_for_key(ToolKey(owner_id="dbfox.data", local_name=name))
            definition = next(t for t in payload["tools"] if t.get("name") == wire_name)
            if definition.get("defer_loading"):
                items += [
                    {"id": f"search_{self.step}", "type": "tool_search_call", "execution": "server", "call_id": None,
                     "status": "completed", "arguments": {"paths": [wire_name]}},
                    {"id": f"loaded_{self.step}", "type": "tool_search_output", "execution": "server", "call_id": None,
                     "status": "completed", "tools": [definition]},
                ]
            items.append({"id": f"call_{self.step}", "type": "function_call", "status": "completed",
                          "call_id": f"workbook-{self.step}", "name": wire_name, "arguments": json.dumps(arguments)})
            self.step += 1
        else:
            assert self.rows is not None
            items.append({"id": "answer", "type": "message", "role": "assistant", "status": "completed",
                "phase": "final_answer", "content": [{"type": "output_text", "annotations": [], "logprobs": [],
                "text": self.answer() + "{{cite:" + self.result_id + "}}"}]})
        events = []
        for index, item in enumerate(items):
            events.extend([{"type": "response.output_item.added", "output_index": index, "item": {**item, "status": "in_progress"}},
                           {"type": "response.output_item.done", "output_index": index, "item": item}])
        events.append({"type": "response.completed", "response": {"id": f"response_{len(self.requests)}", "object": "response",
            "created_at": 0, "model": payload["model"], "status": "completed", "output": items,
            "parallel_tool_calls": False, "tool_choice": "auto", "tools": payload["tools"]}})
        body = "".join(f"event: {e['type']}\ndata: {json.dumps({**e, 'sequence_number': i})}\n\n" for i, e in enumerate(events))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    def plan(self):
        sql = ('SELECT SUM("商品实付金额") AS sales FROM data WHERE "订单状态"=\'已完成\' '
               'AND "支付时间">=DATE \'2026-10-01\' AND "支付时间"<DATE \'2026-11-01\' AND "币种"=\'CNY\'')
        if self.followup:
            sql += ' AND "商品类别"=\'家居\''
        return ([] if self.followup else [
            ("workbook_inspect", {"attachment_id": self.source_id}),
            ("workbook_prepare", {"attachment_id": self.source_id, "sheet": "订单明细", "header_row": 1}),
        ]) + [("sql_validate", {"database_id": self.database_id, "sql": sql}),
              ("sql_execute_readonly", {"database_id": self.database_id, "validation_artifact_id": self.validation_id})]

    def answer(self):
        return f"按支付时间、已完成订单、CNY统计，商品明细销售额为{self.rows[0]['sales']}；来源为原始工作簿订单明细。"


class SectionedWorkbookProvider(WorkbookProvider):
    """Reproduces three distinct inspections then a failed preparation/recovery."""

    def __init__(self, registry, **kwargs):
        super().__init__(registry, **kwargs)
        self.expected_failures = {"workbook-3": "TOOL_INPUT_ERROR"}

    def plan(self):
        source = {"attachment_id": self.source_id}
        preparation = {**source, "sheet": "Sheet1", "header_row": 3,
                       "columns": ["课程代码", "课程名称", "开课学期", "学分"],
                       "column_types": {"开课学期": "text", "学分": "decimal"}}
        regions = [{"data_range": r, "context_cells": {"课程类别": c}} for r, c in
                   (("A4:E13", "A2"), ("A17:E44", "A16"), ("A49:E64", "A47"), ("A67:E92", "A65"))]
        return [
            ("workbook_inspect", source),
            ("workbook_inspect", {**source, "sheet": "Sheet1"}),
            ("workbook_inspect", {**source, "sheet": "必修课程（开课学期）"}),
            ("workbook_prepare", preparation),  # Rejects subtotal, then allows a recovery turn.
            ("workbook_inspect", {**source, "sheet": "Sheet1", "cell_range": "A45:K108"}),
            ("workbook_inspect", {**source, "sheet": "Sheet1", "cell_range": "A109:K112"}),
            ("workbook_prepare", {**preparation, "regions": regions}),
            ("sql_validate", {"database_id": self.database_id,
                              "sql": 'SELECT SUM("学分") AS sales FROM data WHERE __source_row < 65'}),
            ("sql_execute_readonly", {"database_id": self.database_id, "validation_artifact_id": self.validation_id}),
        ]

    def answer(self):
        return f"所选必修明细列出的学分合计{self.rows[0]['sales']}，按原表分类与行号核对；选修清单及英语可选方案未计入，不能据此断言毕业要求。"


@pytest.mark.parametrize("sectioned", [False, True], ids=["flat-orders", "sectioned-plan-recovery"])
def test_product_first_question_followup_and_private_result_lifecycle(tmp_path, monkeypatch, sectioned):
    root = tmp_path / "runtime"
    monkeypatch.setenv("DBFOX_RUNTIME_DIR", str(root))
    metadata = root / "metadata.sqlite"
    monkeypatch.setenv("DBFOX_DATABASE_URL", f"sqlite:///{metadata}")
    engine = create_migrated_metadata_engine(metadata)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("engine.runtime_composition.SessionLocal", factory)
    built = build_dbfox_data_dlc_fixture(tmp_path / "archives")
    service = DlcPackageService(root / "dlcs")
    service.trust_publisher_from_file(built.archive, expected_package_digest=built.package_digest,
                                    expected_publisher_key_id=built.publisher_fingerprint)
    service.install_from_file(built.archive)
    service.set_desired_enabled("dbfox.data", True)
    previous = active_runtime_snapshot()
    try:
        snapshot = initialize_runtime_snapshot(storage_root=service.storage_root)
        assert not snapshot.activation_failures
        registry = build_product_tool_registry(snapshot)
        with factory() as db:
            db.add(Project(id="orders-project", name="电商订单")); db.flush()
            repo = SessionRepository(db)
            conversation = repo.create(project_id="orders-project", title="订单分析")
            other = repo.create(project_id="orders-project", title="另一会话")
            data = (sectioned_plan(tmp_path / "plan.xlsx") if sectioned else FIXTURES / "first/orders.xlsx").read_bytes()
            temporary = root / "upload.tmp"; temporary.write_bytes(data)
            file = AttachmentService(db).publish(conversation.id, temporary=temporary, name="orders.xlsx",
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", size=len(data),
                digest=hashlib.sha256(data).hexdigest(), key="product-first-upload")
            reference = ConversationInputReference(label=file.display_name,
                object={"kind": ATTACHMENT_RESOURCE_KIND, "id": file.id, "version": file.content_sha256})
            refs = authorize_conversation_resources(db, conversation.id,
                [RequestedResourceRef(kind=ATTACHMENT_RESOURCE_KIND, id=file.id)])
            db.commit()
            conversation_id, foreign_id, attachment_id = conversation.id, other.id, file.id
        # Exercise the authenticated session Operation boundary used by the Dock,
        # including a staged attachment before any Agent Run exists.
        from fastapi.testclient import TestClient
        from engine.main import app, LOCAL_SECURE_TOKEN
        monkeypatch.setattr("engine.api.dlc_operations.SessionLocal", factory)
        browser = TestClient(app)
        operation_url = "/api/v1/dlcs/dbfox.data/operations/workbooks.metadata"
        operation_input = {"attachment_id": reference.object.id, "source_hash": reference.object.version}
        auth = {"X-Local-Token": LOCAL_SECURE_TOKEN}
        response = browser.post(operation_url, params={"session_id": conversation_id}, json=operation_input, headers=auth)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["attachment_id"] == attachment_id
        assert browser.post(operation_url, json=operation_input, headers=auth).status_code == 400
        assert browser.post(operation_url, params={"session_id": foreign_id}, json=operation_input, headers=auth).status_code == 404
        assert browser.post(operation_url, params={"session_id": conversation_id, "project_id": "foreign-project"}, json=operation_input, headers=auth).status_code == 404
        assert browser.post(operation_url, params={"session_id": conversation_id}, json={**operation_input, "source_hash": "0" * 64}, headers=auth).status_code == 404
        response = browser.post(operation_url.replace("metadata", "preview"), params={"session_id": conversation_id},
                                json={**operation_input, "sheet": "Sheet1" if sectioned else "订单明细"}, headers=auth)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["readonly"] is True
        assert len(response.json()["data"]["sheets"]) == 1
        browser.close()
        result_ids = []
        for followup, expected in (((False, "15.75"),) if sectioned else ((False, "1030.30"), (True, "380.30"))):
            with factory() as db:
                repo = SessionRepository(db)
                admission = repo.admit(session_id=conversation_id, resource_refs=() if followup else refs,
                    references=() if followup else (reference,), content=("分析Sheet1所列必修学分，不合计选修备选和英语方案" if sectioned
                        else "只统计家居类重新计算" if followup else "按支付时间统计十月已完成订单的商品实付销售额，仅CNY"),
                    idempotency_key=f"input-{followup}", llm_credential_id="scripted", model_name="gpt-5.4", api_base=None, request_payload={})
                if not followup:
                    AttachmentService(db).admit(conversation_id, admission.input_id, (reference,))
                lease = repo.claim(session_id=conversation_id, owner="workbook-product", ttl_seconds=240)
                assert lease
                repo.promote_next_input(lease=lease); db.commit()
                if followup:
                    context = ContextAssembler(db, contributors=snapshot.context_contributors, resource_discovery=discover_run_resources).build(admission.run_id)
                    assert not context.input_references
                    assert attachment_id in json.dumps([f.model_dump() for f in context.context_fragments])
            model = (SectionedWorkbookProvider if sectioned else WorkbookProvider)(registry, followup=followup)
            loop = build_product_run_loop(session_factory=factory, snapshot=snapshot)
            def model_factory(settings):
                client = AsyncOpenAI(api_key="test-only", base_url="https://workbook-provider.invalid/v1", max_retries=0,
                    http_client=httpx.AsyncClient(transport=httpx.MockTransport(model.respond)))
                return OpenAIModelAdapter(client=client, model_name=settings.model_name, owns_client=True)
            loop.model_factory = model_factory
            try:
                loop.execute(lease=lease, run_id=admission.run_id)
            finally:
                loop.close()
            assert not model.errors, model.errors
            from decimal import Decimal
            assert Decimal(model.rows[0]["sales"]) == Decimal(expected)
            with factory() as db:
                run = db.get(AgentRun, admission.run_id)
                assert run.status == "completed", run.result_json
                invocations = db.scalars(select(AgentToolInvocation).where(AgentToolInvocation.run_id == run.id)).all()
                assert sum(i.status == "failed" for i in invocations) == (1 if sectioned else 0)
                assert all(i.status in ("succeeded", "failed") for i in invocations)
                assert len(invocations) == (9 if sectioned else 2 if followup else 4)
                artifacts = db.scalars(select(AgentArtifactRecord).where(AgentArtifactRecord.run_id == run.id)).all()
                result = next(a for a in artifacts if a.type == "dbfox.data.result_view")
                result_ids.append(result.id)
                request = ArtifactRepresentationRequest(operation="page", parameters={"page": 1, "page_size": 10})
                page = api_artifact_representation_read(result.id, DATAFRAME_REPRESENTATION_TYPE, request, db, session_id=conversation_id)
                assert Decimal(page.payload["fields"][0]["values"][0]) == Decimal(expected)
                from fastapi import HTTPException
                for invalid_session in (None, foreign_id):
                    with pytest.raises(HTTPException) as error:
                        api_artifact_representation_read(result.id, DATAFRAME_REPRESENTATION_TYPE, request, db, session_id=invalid_session)
                    assert error.value.status_code == 404
                stream = api_artifact_representation_stream(result.id, DATAFRAME_REPRESENTATION_TYPE,
                    ArtifactRepresentationRequest(operation="export.csv", parameters={}), db, session_id=conversation_id)
                async def read_stream():
                    return [chunk async for chunk in stream.body_iterator]
                exported = asyncio.run(read_stream())
                assert "sales" in str(exported)
        with factory() as db:
            AttachmentService(db).path(attachment_id).unlink()
            with pytest.raises(Exception) as error:
                api_artifact_representation_read(result_ids[0], DATAFRAME_REPRESENTATION_TYPE,
                    ArtifactRepresentationRequest(operation="page", parameters={}), db, session_id=conversation_id)
            assert getattr(error.value, "status_code", None) == 409
    finally:
        set_active_runtime_snapshot(previous)
        engine.dispose()
