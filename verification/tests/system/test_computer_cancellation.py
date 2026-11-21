"""Stop during a blocked preflight cannot dispatch delayed native input."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from threading import Event

from PIL import Image
import pytest
from sqlalchemy.orm import sessionmaker

from engine.computer.contracts import ActInput, ComputerError, Rect, ShareInput, TargetIdentity
from engine.computer.drivers import CapturedFrame, PreparedAction
from engine.computer.native import NativeDesktop
from engine.computer.runtime import ComputerRuntime
from engine.models import AgentSession, Project
from verification.support.metadata import create_migrated_metadata_engine


def test_stop_wins_against_a_delayed_input_preflight(tmp_path: Path) -> None:
    entered, release = Event(), Event()
    dispatched = []
    image = BytesIO()
    Image.new("RGB", (10, 10)).save(image, "PNG")

    class FixtureNative(NativeDesktop):
        def targets(self):
            return (TargetIdentity(kind="window", title="Synthetic cancellation fixture", executable="fixture.exe",
                process_id=123, process_started_at=1, window_handle="123"),)

        def capture(self, grant, *, remember=True):
            return CapturedFrame(title=grant.target.title, url=None, bounds=Rect(x=0, y=0, width=10, height=10),
                png=image.getvalue(), image_width=10, image_height=10, nodes=(), truncated=False, window_handle="123")

        def prepare(self, grant, before, action, check_cancelled):
            entered.set()
            assert release.wait(5)
            return PreparedAction(lambda: dispatched.append("late input"))

    metadata = create_migrated_metadata_engine(tmp_path / "computer.sqlite")
    sessions = sessionmaker(bind=metadata)
    with sessions.begin() as db:
        db.add(Project(id="p", name="Cancellation fixture"))
        db.flush()
        db.add(AgentSession(id="s", project_id="p"))
    runtime = ComputerRuntime(sessions, tmp_path / "computer", native=FixtureNative())
    pool = ThreadPoolExecutor(1)
    try:
        option = next(item for item in runtime.inventory() if item.target.kind == "window")
        grant = runtime.share("s", ShareInput(inventory_id=option.inventory_id, permission="control"))
        ref = runtime.ref(grant)
        observation = runtime.observe("s", ref, "observe", lambda: False)
        pending = pool.submit(runtime.act, "s", ref, observation,
            ActInput(target_id=grant.id, observation_artifact_id="fixture", action="click", point={"x": .5, "y": .5}),
            "blocked-preflight", lambda: False)
        assert entered.wait(3)
        runtime.stop("s", target_id=grant.id)
        release.set()
        with pytest.raises(ComputerError):
            pending.result(timeout=3)
        assert dispatched == [] and runtime.store.get("s", grant.id).status == "paused"
    finally:
        release.set()
        pool.shutdown(wait=True)
        runtime.close()
        metadata.dispose()
