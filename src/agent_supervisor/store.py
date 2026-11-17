from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def read(self, relative: str) -> dict[str, Any]:
        path = self.root / relative
        return json.loads(path.read_text(encoding="utf-8"))

    def exists(self, relative: str) -> bool:
        return (self.root / relative).exists()

    def write(self, relative: str, payload: dict[str, Any]) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.write("\n")
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return path
