from __future__ import annotations

from pathlib import Path as _C2RSplitPath
from sys import _getframe as _C2RSplitFrame

_C2R_SPLIT_PARTS_DIR = _C2RSplitPath(_C2RSplitFrame().f_code.co_filename).with_name("part_00_split_parts")
_C2R_SPLIT_PART_NAMES = (
    "part_00.pyfrag",
    "part_01.pyfrag",
    "part_02.pyfrag",
    "part_03.pyfrag",
    "part_04.pyfrag",
    "part_05.pyfrag",
    "part_06.pyfrag",
    "part_07.pyfrag",
    "part_08.pyfrag",
    "part_09.pyfrag",
    "part_10.pyfrag",
    "part_11.pyfrag",
    "part_12.pyfrag",
)
_C2R_SPLIT_SOURCE = "".join(
    (_C2R_SPLIT_PARTS_DIR / _C2R_SPLIT_PART_NAME).read_text(encoding="utf-8")
    for _C2R_SPLIT_PART_NAME in _C2R_SPLIT_PART_NAMES
)
exec(compile(_C2R_SPLIT_SOURCE, __file__, "exec"), globals())
for _C2R_SPLIT_TEMP_NAME in (
    "_C2RSplitPath",
    "_C2RSplitFrame",
    "_C2R_SPLIT_PARTS_DIR",
    "_C2R_SPLIT_PART_NAMES",
    "_C2R_SPLIT_SOURCE",
):
    globals().pop(_C2R_SPLIT_TEMP_NAME, None)
del _C2R_SPLIT_TEMP_NAME
