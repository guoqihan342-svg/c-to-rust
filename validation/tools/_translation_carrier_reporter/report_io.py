from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .errors import ReporterError


def write_reports_atomically(
    paths: dict[str, Path],
    reports: dict[str, dict[str, Any]],
    artifacts: dict[Path, bytes],
) -> None:
    if set(paths) != set(reports):
        raise ReporterError("report path set does not match generated report set")
    output_dir = next(iter(paths.values())).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary: list[tuple[Path, Path]] = []
    try:
        for path, content in artifacts.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temp.write_bytes(content)
            temporary.append((temp, path))
        for name, path in paths.items():
            temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temp.write_bytes((json.dumps(reports[name], indent=2) + "\n").encode("utf-8"))
            temporary.append((temp, path))
        for temp, path in temporary:
            os.replace(temp, path)
    finally:
        for temp, _ in temporary:
            temp.unlink(missing_ok=True)
