#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path as _C2RPartPath

_C2R_PARTS_DIR = _C2RPartPath(__file__).with_name("_opencode_agent_harness_parts")
for _C2R_PART_NAME in (
    "part_00.py",
    "part_01.py",
    "part_02.py",
    "part_03.py",
    "part_04.py",
    "part_05.py",
    "part_06.py",
    "part_07.py",
    "part_08.py",
    "part_09.py",
):
    _C2R_PART_PATH = _C2R_PARTS_DIR / _C2R_PART_NAME
    exec(
        compile(
            _C2R_PART_PATH.read_text(encoding="utf-8"),
            str(_C2R_PART_PATH),
            "exec",
        ),
        globals(),
    )
for _C2R_PART_TEMP_NAME in (
    "_C2RPartPath",
    "_C2R_PARTS_DIR",
    "_C2R_PART_NAME",
    "_C2R_PART_PATH",
):
    globals().pop(_C2R_PART_TEMP_NAME, None)
del _C2R_PART_TEMP_NAME
