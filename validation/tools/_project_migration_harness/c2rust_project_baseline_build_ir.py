from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .build_facts import (
    file_binding, json_sha256, resolve_repository_path,
)
from .build_ir_validation import verify_build_ir_artifact
from .build_ir_validation_io import read_bound, strict_object
from .c2rust_project_baseline_compile_db import (
    MAX_COMPILE_DATABASE_BYTES, MAX_COMPILE_DATABASE_ENTRIES,
)
from .compile_database import parse_compile_entry


_UNIT_KEY_DOMAIN = b"c2rust-project-build-ir-unit-v1\0"


class C2RustBuildIRBindingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BoundBuildIRCompileUnit:
    unit_id: str
    unit_key: str
    entry_index: int
    entry_sha256: str
    database_bytes: bytes
    database_sha256: str

    @property
    def database_binding(self) -> dict[str, Any]:
        return {
            "path": f"units/{self.unit_key}/input/compile_commands.json",
            "sha256": self.database_sha256,
            "size_bytes": len(self.database_bytes),
        }

    def database_payload(self) -> list[dict[str, Any]]:
        value = json.loads(self.database_bytes.decode("utf-8"))
        assert isinstance(value, list)
        return value


@dataclass(frozen=True, slots=True)
class ReopenedBuildIRCompileDatabase:
    build_ir_sha256: str
    semantic_sha256: str
    build_ir_bytes: bytes
    database_path: str
    database_sha256: str
    database_size_bytes: int
    units: tuple[BoundBuildIRCompileUnit, ...]

    def build_ir_payload(self) -> dict[str, Any]:
        value = json.loads(self.build_ir_bytes.decode("utf-8"))
        assert isinstance(value, dict)
        return value

    @property
    def database_binding(self) -> dict[str, Any]:
        return {
            "path": self.database_path,
            "sha256": self.database_sha256,
            "size_bytes": self.database_size_bytes,
        }


def stable_unit_key(unit_id: str) -> str:
    if type(unit_id) is not str or not unit_id:
        raise C2RustBuildIRBindingError("c2rust_build_ir_unit_id_invalid")
    try:
        encoded = unit_id.encode("utf-8")
    except UnicodeError as error:
        raise C2RustBuildIRBindingError(
            "c2rust_build_ir_unit_id_invalid"
        ) from error
    return hashlib.sha256(_UNIT_KEY_DOMAIN + encoded).hexdigest()


def reopen_build_ir_compile_database(
    *, repo_root: str | Path, artifact_root: str | Path,
    build_ir_reference: Mapping[str, Any],
    compile_database: str | Path,
) -> ReopenedBuildIRCompileDatabase:
    try:
        root = Path(repo_root).resolve(strict=True)
        artifact_base = Path(artifact_root).resolve(strict=True)
        build_ir_data = read_bound(
            artifact_base, build_ir_reference, "build_ir",
        )
        build_ir = strict_object(build_ir_data, "build_ir")
        verification = verify_build_ir_artifact(
            root, artifact_base, build_ir_reference,
        )
        if verification.get("status") != "verified":
            _fail("c2rust_build_ir_verification_failed")
        database_path = resolve_repository_path(root, compile_database)
        database_ref = file_binding(
            root, database_path, max_bytes=MAX_COMPILE_DATABASE_BYTES,
        )
        database_data = database_path.read_bytes()
        if (
            len(database_data) != database_ref["size_bytes"]
            or hashlib.sha256(database_data).hexdigest()
            != database_ref["sha256"]
        ):
            _fail("c2rust_build_ir_compile_database_drift")
        _validate_database_binding(build_ir, database_ref)
        entries = _strict_database(database_data)
        units = tuple(
            _bind_unit(root, database_path, entries, unit)
            for unit in build_ir["translation_units"]
        )
        keys = [unit.unit_key for unit in units]
        if len(keys) != len(set(keys)):
            _fail("c2rust_build_ir_unit_key_collision")
        return ReopenedBuildIRCompileDatabase(
            str(build_ir_reference["sha256"]),
            str(build_ir["semantic_sha256"]),
            build_ir_data,
            str(database_ref["path"]),
            str(database_ref["sha256"]),
            int(database_ref["size_bytes"]),
            units,
        )
    except C2RustBuildIRBindingError:
        raise
    except (KeyError, OSError, TypeError, UnicodeError, ValueError) as error:
        raise C2RustBuildIRBindingError(
            "c2rust_build_ir_input_invalid"
        ) from error


def _validate_database_binding(
    build_ir: Mapping[str, Any], database_ref: Mapping[str, Any],
) -> None:
    metadata = build_ir.get("build_metadata")
    expected = {
        **dict(database_ref), "kind": "file", "materialized": True,
    }
    if not isinstance(metadata, list) or metadata != [expected]:
        _fail("c2rust_build_ir_compile_database_binding_mismatch")


def _strict_database(data: bytes) -> list[dict[str, Any]]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                _fail("c2rust_build_ir_compile_database_duplicate_key")
            result[key] = value
        return result

    def constant(_value: str) -> Any:
        _fail("c2rust_build_ir_compile_database_json_invalid")

    try:
        value = json.loads(
            data.decode("utf-8-sig"), object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise C2RustBuildIRBindingError(
            "c2rust_build_ir_compile_database_json_invalid"
        ) from error
    if (
        not isinstance(value, list) or not value
        or len(value) > MAX_COMPILE_DATABASE_ENTRIES
        or not all(isinstance(item, dict) for item in value)
    ):
        _fail("c2rust_build_ir_compile_database_entries_invalid")
    return value


def _bind_unit(
    root: Path, database_path: Path, entries: list[dict[str, Any]],
    unit: Any,
) -> BoundBuildIRCompileUnit:
    if not isinstance(unit, Mapping):
        _fail("c2rust_build_ir_unit_invalid")
    provenance = unit.get("provenance")
    if (
        not isinstance(provenance, Mapping)
        or provenance.get("raw_fact_role") != "discovery"
    ):
        _fail("c2rust_build_ir_unit_provenance_invalid")
    index = provenance.get("entry_index")
    if type(index) is not int or not 0 <= index < len(entries):
        _fail("c2rust_build_ir_entry_index_invalid")
    entry = entries[index]
    digest = json_sha256(entry)
    if provenance.get("entry_sha256") != digest:
        _fail("c2rust_build_ir_entry_sha256_mismatch")
    parsed, rejection = parse_compile_entry(
        entry, index, root, database_path.parent,
    )
    if parsed is None or rejection is not None:
        _fail("c2rust_build_ir_compile_entry_invalid")
    _validate_unit_facts(unit, parsed)
    expected_id = json_sha256({
        "source": parsed["source"]["path"],
        "working_directory": parsed["working_directory"],
        "expanded_argv_sha256": parsed["expanded_argv_sha256"],
        "output": parsed["output"],
        "response_files": parsed["response_files"],
    })
    unit_id = unit.get("unit_id")
    if unit_id != expected_id:
        _fail("c2rust_build_ir_unit_identity_mismatch")
    key = stable_unit_key(unit_id)
    payload = canonical_json_bytes([entry])
    return BoundBuildIRCompileUnit(
        unit_id, key, index, digest, payload,
        hashlib.sha256(payload).hexdigest(),
    )


def _validate_unit_facts(
    unit: Mapping[str, Any], parsed: Mapping[str, Any],
) -> None:
    source = unit.get("source")
    source_fact = {
        key: source.get(key) if isinstance(source, Mapping) else None
        for key in ("path", "sha256", "size_bytes")
    }
    if source_fact != parsed["source"]:
        _fail("c2rust_build_ir_source_mismatch")
    if unit.get("working_directory") != parsed["working_directory"]:
        _fail("c2rust_build_ir_working_directory_mismatch")
    output = unit.get("output")
    if not isinstance(output, Mapping) or output.get("path") != parsed["output"]:
        _fail("c2rust_build_ir_output_mismatch")
    arguments = unit.get("compile_arguments")
    if not isinstance(arguments, Mapping):
        _fail("c2rust_build_ir_compile_arguments_mismatch")
    if arguments.get("expanded_argv_sha256") != parsed["expanded_argv_sha256"]:
        _fail("c2rust_build_ir_expanded_argv_mismatch")
    response = arguments.get("response_files")
    response_facts = [
        {key: item.get(key) for key in ("path", "sha256", "size_bytes")}
        for item in response if isinstance(item, Mapping)
    ] if isinstance(response, list) else None
    expected_response = [
        {key: item.get(key) for key in ("path", "sha256", "size_bytes")}
        for item in parsed["response_files"]
    ]
    if response_facts != expected_response:
        _fail("c2rust_build_ir_response_files_mismatch")
    carried = {
        "compiler": parsed["compiler"],
        "compiler_wrappers": parsed["compiler_wrappers"],
        "language": parsed["language"],
        "includes": parsed["includes"],
        "defines": parsed["defines"],
        "redacted_define_count": parsed["redacted_define_count"],
    }
    if any(unit.get(key) != value for key, value in carried.items()):
        _fail("c2rust_build_ir_compile_facts_mismatch")
    if arguments.get("semantic_flags") != parsed["semantic_flags"]:
        _fail("c2rust_build_ir_compile_facts_mismatch")


def _fail(code: str) -> None:
    raise C2RustBuildIRBindingError(code)


__all__ = [
    "BoundBuildIRCompileUnit", "C2RustBuildIRBindingError",
    "ReopenedBuildIRCompileDatabase", "reopen_build_ir_compile_database",
    "stable_unit_key",
]
