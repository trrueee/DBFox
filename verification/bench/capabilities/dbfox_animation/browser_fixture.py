"""Prepare the real signed owner in isolated metadata, without credentials."""
import json
from pathlib import Path
import sys
from .runtime import AnimationRuntime


def prepare(directory):
    with AnimationRuntime(directory) as runtime:
        small = runtime.seed("animation-browser-project")
        large = runtime.seed("animation-large-project",large=True)
        payload = {"project_id":"animation-browser-project","animation":small,"large_project_id":"animation-large-project","large_animation":large,"package_digest":runtime.package.package_digest}
        (directory / "browser-fixture.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
        print(json.dumps({"runtime":str(directory),"package_digest":runtime.package.package_digest}))


if __name__ == "__main__":
    prepare(Path(sys.argv[1]).resolve())
