from __future__ import annotations

from pathlib import Path as _C2RSplitPath

_C2R_SPLIT_PARTS_DIR = _C2RSplitPath(__file__).with_name("test_ai_run_metrics_split_parts")
_C2R_SPLIT_PART_NAMES = (
    "part_00.pyfrag",
    "part_01.pyfrag",
    "part_02.pyfrag",
)
_C2R_SPLIT_SOURCE = "".join(
    (_C2R_SPLIT_PARTS_DIR / _C2R_SPLIT_PART_NAME).read_text(encoding="utf-8")
    for _C2R_SPLIT_PART_NAME in _C2R_SPLIT_PART_NAMES
)
exec(compile(_C2R_SPLIT_SOURCE, __file__, "exec"), globals())
for _C2R_SPLIT_TEMP_NAME in (
    "_C2RSplitPath",
    "_C2R_SPLIT_PARTS_DIR",
    "_C2R_SPLIT_PART_NAMES",
    "_C2R_SPLIT_SOURCE",
):
    globals().pop(_C2R_SPLIT_TEMP_NAME, None)
del _C2R_SPLIT_TEMP_NAME
