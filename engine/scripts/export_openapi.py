"""Export the FastAPI contract used to generate the desktop API client."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from engine.main import app


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m engine.scripts.export_openapi <output.json>")
    output = Path(sys.argv[1]).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
