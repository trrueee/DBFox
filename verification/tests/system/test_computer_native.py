"""Real window observations and input verified through a fixture-owned output file."""
from pathlib import Path
import os
import subprocess
import sys
import time

import pytest
from sqlalchemy.orm import sessionmaker

from engine.computer.contracts import ActInput, ComputerError, ShareInput
from engine.computer.runtime import ComputerRuntime
from engine.models import AgentSession, Project
from verification.support.metadata import create_migrated_metadata_engine

pytestmark = pytest.mark.platform_contract


def test_native_window_input_and_stop_against_actual_controls(tmp_path: Path) -> None:
    from engine.local_execution.broker import supported
    if not supported():
        pytest.skip("Requires a normal Windows 11 desktop")
    from engine.local_execution.windows import WindowsProcess
    result_file = tmp_path / "saved.txt"
    title = "DBFox Computer Fixture " + tmp_path.name
    command = [sys.executable, "-m", "verification.testkit.computer_window", "--result", str(result_file), "--title", title]
    job = WindowsProcess.launch(Path(sys.executable), subprocess.list2cmdline(command), Path.cwd(), dict(os.environ), interactive=False)
    metadata = create_migrated_metadata_engine(tmp_path / "computer.sqlite")
    sessions = sessionmaker(bind=metadata)
    with sessions.begin() as db:
        db.add(Project(id="p", name="Native computer fixture"))
        db.flush()
        db.add(AgentSession(id="s", project_id="p"))
    runtime = ComputerRuntime(sessions, tmp_path / "computer")
    try:
        deadline = time.monotonic() + 8
        while True:
            if job.root_exit_code() is not None:
                error = job.read("stderr", 4096)
                pytest.fail("Native fixture exited: " + (error or b"").decode("utf-8", errors="replace"))
            target = next((item for item in runtime.inventory() if item.target.title == title), None)
            if target:
                break
            assert time.monotonic() < deadline, "The dedicated native fixture window never appeared"
            time.sleep(.1)
        grant = runtime.share("s", ShareInput(inventory_id=target.inventory_id, permission="control", duration_minutes=5))
        ref = runtime.ref(grant)
        before = runtime.observe("s", ref, "observe", lambda: False)
        assert runtime.read_capture(before).startswith(b"\x89PNG")
        runtime.act("s", ref, before, ActInput(target_id=grant.id, observation_artifact_id="fixture-artifact", action="focus"), "focus", lambda: False)
        focused = runtime.observe("s", ref, "focused", lambda: False)
        edit = next(node for node in focused.nodes if node.role == "Edit")
        runtime.act("s", ref, focused, ActInput(target_id=grant.id, observation_artifact_id="fixture-artifact",
                    action="type_text", node_id=edit.id, text="Native literal +{ENTER} fixture"), "type", lambda: False)
        edited = runtime.observe("s", ref, "edited", lambda: False)
        save = next(node for node in edited.nodes if node.name == "Save fixture" and node.role == "Button")
        runtime.act("s", ref, edited, ActInput(target_id=grant.id, observation_artifact_id="fixture-artifact",
                    action="click", node_id=save.id), "save", lambda: False)
        deadline = time.monotonic() + 2
        while not result_file.exists() and time.monotonic() < deadline:
            time.sleep(.05)
        assert result_file.read_text(encoding="utf-8") == "Native literal +{ENTER} fixture"
        observed = runtime.observe("s", ref, "saved", lambda: False)
        assert any("Saved: Native literal" in node.name for node in observed.nodes)
        runtime.stop("s", target_id=grant.id)
        with pytest.raises(ComputerError):
            runtime.act("s", ref, observed, ActInput(target_id=grant.id, observation_artifact_id="fixture-artifact",
                        action="click", node_id=save.id), "after-stop", lambda: False)
    finally:
        runtime.close()
        job.close()
        metadata.dispose()
