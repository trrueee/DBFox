"""Workbench delivery uses one live Invocation and one scoped receipt."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep

from engine.agent.artifact import Artifact
from engine.main import app
from engine.tools.builtin.workbench import OpenArtifactTool
from engine.workbench_presentations import WorkbenchPresentationBroker, WorkbenchPresentationReceipt


def _artifact() -> Artifact:
    return Artifact(id="result", title="Report", session_id="source", run_id="run", type="test.workbench.report")


def _claim(broker: WorkbenchPresentationBroker, invocation_id: str):
    deadline = monotonic() + 2
    while monotonic() < deadline:
        claimed = broker.claim("source", invocation_id)
        if claimed is not None:
            return claimed
        sleep(0.01)
    raise AssertionError("The Workbench did not receive a live request")


def test_http_receipt_is_scoped_to_a_single_claim(client, monkeypatch):
    broker = WorkbenchPresentationBroker()
    monkeypatch.setattr(app.state, "workbench_presentations", broker, raising=False)
    path = "/api/v1/conversations/source/workbench-presentations/invocation"
    wrong_path = path.replace("/source/", "/other/")

    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(broker.present, artifact=_artifact(), invocation_id="invocation",
                                 project_id="p1", cancelled=lambda: False, deadline=None)
        assert client.post(f"{wrong_path}/claim").json() is None
        assert client.post(f"{path}/receipt", json={"outcome": "opened"}).status_code == 404
        deadline = monotonic() + 2
        while monotonic() < deadline:
            claim = client.post(f"{path}/claim")
            assert claim.status_code == 200
            if claim.json() is not None:
                break
            sleep(0.01)
        assert claim.json()["artifact_id"] == "result"
        assert client.post(f"{path}/claim").json() is None
        assert client.post(f"{wrong_path}/receipt", json={"outcome": "opened"}).status_code == 404
        assert client.post(f"{path}/receipt", json={"outcome": "opened"}).status_code == 204
        assert result.result(timeout=2) == "opened"
    assert client.post(f"{path}/receipt", json={"outcome": "opened"}).status_code == 404


def test_cancellation_after_claim_does_not_report_opened_or_redeliver():
    broker = WorkbenchPresentationBroker()
    cancel = Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(broker.present, artifact=_artifact(), invocation_id="claimed",
                                 project_id="p1", cancelled=cancel.is_set, deadline=None)
        assert _claim(broker, "claimed").artifact_id == "result"
        OpenArtifactTool(broker).cancel("claimed")
        cancel.set()
        assert not broker.acknowledge("source", "claimed", WorkbenchPresentationReceipt(outcome="opened"))
        assert result.result(timeout=2) == "unconfirmed"
    assert broker.claim("source", "claimed") is None
    assert not broker.acknowledge("source", "claimed", WorkbenchPresentationReceipt(outcome="opened"))

    outcome = broker.present(artifact=_artifact(), invocation_id="expired", project_id="p1",
                             cancelled=lambda: False, deadline=monotonic() - 1)
    assert outcome == "not_opened"
