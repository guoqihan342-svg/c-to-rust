from __future__ import annotations

from pathlib import Path as _Path
import re
from typing import Any

from validation.tools.replay_call_plan_v2 import _plan_sha256


__all__ = [
    "supports_record_pointer_identity_plan",
    "build_record_pointer_identity_plan",
]


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RUST_KEYWORDS = {
    "Self", "as", "async", "await", "break", "const", "continue", "crate",
    "dyn", "else", "enum", "extern", "false", "fn", "for", "if", "impl",
    "in", "let", "loop", "match", "mod", "move", "mut", "pub", "ref",
    "return", "self", "static", "struct", "super", "trait", "true", "type",
    "union", "unsafe", "use", "where", "while",
}
RECORD_KEYS = {"parameter", "fixture_root", "rust_type", "fields", "defaults"}
INPUT_FIELD_KEYS = {
    "fixture_path", "rust_field_path", "rust_type_path", "fixture_scalar_type",
    "rust_scalar_type", "conversion",
}
OUTPUT_FIELD_KEYS = {
    "initial_fixture_path", "expected_output", "rust_field_path", "rust_type_path",
    "fixture_scalar_type", "rust_scalar_type", "conversion",
}
DEFAULT_KEYS = {"rust_field_path", "rust_type_path", "rust_scalar_type", "value"}
SAFE_NULL_POINTER_RUST_TYPE = "Option<core::ptr::NonNull<core::ffi::c_void>>"


_PARTS_DIR = _Path(__file__).with_name("_replay_call_plan_record_identity_parts")
for _PART_NAME in (
    "part_00.pyfrag",
    "part_01.pyfrag",
    "part_02.pyfrag",
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
del _PARTS_DIR, _PART_NAME, _PART_PATH, _Path
