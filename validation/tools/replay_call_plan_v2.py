from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RUST_TYPE_RE = re.compile(r"^[A-Za-z0-9_&'\[\]<>:(),; ]+$")
ACTUAL_RE = re.compile(
    r"^(?:return(?:\.[A-Za-z_][A-Za-z0-9_]*)*|"
    r"binding\.[A-Za-z_][A-Za-z0-9_]*(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+))+)$"
)
ENTRY_RECORD_STATE_KINDS = {
    "record_u32_field_constant_state",
    "record_u32_field_wrapping_add_state",
    "record_u32_field_scalar_wrapping_add_state",
    "record_u32_field_postfix_increment_state",
}


_PARTS_DIR = Path(__file__).with_name("_replay_call_plan_v2_parts")
for _PART_NAME in (
    "part_00.pyfrag",
    "part_00_tail.pyfrag",
    "part_01.pyfrag",
    "part_02.pyfrag",
    "part_03.pyfrag",
    "part_04.pyfrag",
):
    _PART_PATH = _PARTS_DIR / _PART_NAME
    exec(
        compile(
            _PART_PATH.read_text(encoding="utf-8"),
            str(_PART_PATH),
            "exec",
        ),
        globals(),
    )
for _TEMP_NAME in ("_PARTS_DIR", "_PART_NAME", "_PART_PATH"):
    globals().pop(_TEMP_NAME, None)
del _TEMP_NAME
