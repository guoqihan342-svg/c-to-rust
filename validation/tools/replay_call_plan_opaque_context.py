from __future__ import annotations

from pathlib import Path as _Path
import re
from typing import Any

from validation.tools.replay_call_plan_v2 import _plan_sha256


__all__ = [
    "build_opaque_context_plan",
    "supports_opaque_context_plan",
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
CONTEXT_KEYS = {"parameter", "c_type", "rust_type", "state", "name", "source"}
STATE_KEYS = {
    "fixture_field", "required_value", "rust_field", "rust_type", "constant",
}
NAME_KEYS = {"fixture_field", "rust_field", "rust_type", "initializer"}
INPUT_KEYS = {
    "parameter", "c_type", "rust_type", "fixture_field", "codec", "nullable",
}
RETURN_KEYS = {"c_type", "rust_type", "fixture_field", "codec"}
STRING_CODECS = {
    "string_ref": ("&str", False),
    "optional_string_ref": ("Option<&str>", True),
}


_PARTS_DIR = _Path(__file__).with_name("_replay_call_plan_opaque_context_parts")
for _PART_NAME in (
    "part_00.pyfrag",
    "part_01.pyfrag",
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
