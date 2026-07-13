from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from validation.tools.replay_assertion_inventory import (
    assertion_id_for,
    build_replay_assertion_inventory,
    render_assertion_guard,
)


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FIXTURE_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
RUST_TYPE_RE = re.compile(r"^[A-Za-z0-9_&'\[\]<>:(),; ]+$")
MAX_DYNAMIC_I32_ITEMS = 4096
MAX_NULLABLE_BYTE_BUFFER_ITEMS = 4096
SCALAR_INITIALIZER_ENCODINGS = frozenset({"u32", "i32", "usize", "bool"})
NULL_POINTER_RUST_TYPES = {
    "shared": "*const core::ffi::c_void",
    "mutable": "*mut core::ffi::c_void",
}
ACTUAL_RE = re.compile(
    r"^(?:return(?:\.[A-Za-z_][A-Za-z0-9_]*)*|"
    r"binding\.[A-Za-z_][A-Za-z0-9_]*(?:\.(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+))*)$"
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
    "part_05_identity.pyfrag",
    "part_06_buffer.pyfrag",
    "part_07_string.pyfrag",
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
