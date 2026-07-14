from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from validation.tools import validate_judge_entrypoints as judge_validator


def execute_verified_c_oracle(
    *,
    repo_root: Path,
    out_dir: Path,
    c_oracle: dict[str, Any],
) -> dict[str, Any]:
    from validation.tools import auto_migrate

    repo_root = repo_root.resolve()
    out_dir = out_dir.resolve()
    spec_path = repo_root / "validation/slice-specs/flashdb-real-fdb-calc-crc32.json"
    spec = _read_json(spec_path)
    harness_ref = c_oracle.get("provenance", {}).get("harness_draft_ref")
    if not isinstance(harness_ref, dict):
        raise ValueError("accepted C oracle harness ref is missing")
    harness_path = _verified_ref(harness_ref, repo_root, "C oracle harness")
    source_refs = _verified_source_refs(spec, c_oracle, repo_root)

    compiler_resolution = auto_migrate.resolve_c_compiler("cc")
    if compiler_resolution.get("path") is None:
        raise ValueError("a local or WSL C compiler is required for CRC32 semantic evidence")
    compiler_version = _compiler_version(compiler_resolution)
    fixture_binding = auto_migrate.oracle_fixture_binding(spec)
    target_root = repo_root / "target"
    target_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="crc32-real-c-oracle-", dir=target_root) as tmp:
        tmp_dir = Path(tmp)
        harness_copy = tmp_dir / "c-oracle-harness.c"
        shutil.copyfile(harness_path, harness_copy)
        compile_command = auto_migrate.c_oracle_compile_command(spec, harness_copy, tmp_dir)
        execution = auto_migrate.c_oracle_compile_execution(
            compile_command,
            tmp_dir,
            False,
            spec,
            fixture_binding,
        )
        harness_execution = execution.get("harness_execution")
        if (
            execution.get("attempted") is not True
            or execution.get("returncode") != 0
            or not isinstance(harness_execution, dict)
            or harness_execution.get("attempted") is not True
            or harness_execution.get("returncode") != 0
        ):
            raise ValueError(f"real CRC32 C oracle compile/execution failed: {execution}")
        output_gate = harness_execution.get("output_gate")
        if (
            not isinstance(output_gate, dict)
            or output_gate.get("status") != "matched_not_oracle"
            or output_gate.get("missing_stdout_fragments") != []
        ):
            raise ValueError("real CRC32 C oracle output did not match every fixture marker")
        executable_path = auto_migrate.c_oracle_output_executable(compile_command["argv"], tmp_dir)
        if executable_path is None or not executable_path.is_file():
            raise ValueError("real CRC32 C oracle executable is missing after a passed run")
        executable_sha256 = judge_validator.sha256_file(executable_path)

    log_payloads = {
        "c_compile_stdout": str(execution.get("stdout") or ""),
        "c_compile_stderr": str(execution.get("stderr") or ""),
        "c_replay_stdout": str(harness_execution.get("stdout") or ""),
        "c_replay_stderr": str(harness_execution.get("stderr") or ""),
    }
    artifacts: dict[str, dict[str, Any]] = {}
    for key, text in log_payloads.items():
        path = out_dir / f"l3-real-fdb-calc-crc32-c2rust-safety-{key.replace('_', '-')}.log"
        _write_text(path, text)
        artifacts[key] = _ref(path, repo_root, "passed" if key == "c_replay_stdout" else "captured")

    actual_compile_argv = execution.get("execution_argv")
    actual_run_argv = harness_execution.get("execution_argv", harness_execution.get("argv"))
    return {
        "status": "passed",
        "semantic_pass": True,
        "gate": "real_c_compile_execute_and_fixture_output",
        "toolchain": {
            "adapter": execution.get("toolchain_adapter"),
            "compiler_name": execution.get("compiler_name"),
            "compiler_version": compiler_version,
        },
        "compile": {
            "attempted": True,
            "returncode": 0,
            "canonical_argv": compile_command["argv"],
            "actual_argv_sha256": _sha256_json(actual_compile_argv),
            "executable_sha256": executable_sha256,
        },
        "execution": {
            "attempted": True,
            "returncode": 0,
            "actual_argv_sha256": _sha256_json(actual_run_argv),
            "matched_stdout_fragments": output_gate["matched_stdout_fragments"],
            "missing_stdout_fragments": [],
        },
        "inputs": {
            "slice_spec": _ref(spec_path, repo_root, "bound"),
            "harness": _ref(harness_path, repo_root, "compiled"),
            "source_files": source_refs,
        },
        "artifacts": artifacts,
        "claim_boundary": {
            "accepted_c_oracle_top_level_flag_was_not_trusted_without_reexecution": True,
            "fixture_markers_are_accepted_only_after_real_c_compile_and_execution": True,
        },
    }


def _verified_source_refs(
    spec: dict[str, Any],
    c_oracle: dict[str, Any],
    repo_root: Path,
) -> list[dict[str, Any]]:
    declared: list[tuple[str, str]] = []
    source_hashes = spec.get("source", {}).get("source_file_hashes", {})
    expected_main = source_hashes.get("src/fdb_utils.c")
    oracle_main = c_oracle.get("provenance", {}).get("source_file_hashes", {}).get("src/fdb_utils.c")
    if expected_main != oracle_main or not isinstance(expected_main, str):
        raise ValueError("CRC32 source hash drifted between slice spec and accepted C oracle")
    declared.append(("sources/FlashDB/src/fdb_utils.c", expected_main))
    for item in spec.get("build_profile", {}).get("link_source_files", []):
        if isinstance(item, dict) and isinstance(item.get("path"), str) and isinstance(item.get("sha256"), str):
            declared.append((f"sources/FlashDB/{item['path']}", item["sha256"]))
    refs = []
    for relative, expected_sha in declared:
        path = (repo_root / relative).resolve()
        stable_sha = judge_validator.sha256_file(path)
        source_bytes = path.read_bytes()
        raw_sha = hashlib.sha256(source_bytes).hexdigest()
        crlf_sha = hashlib.sha256(
            source_bytes.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        ).hexdigest()
        if expected_sha == stable_sha:
            declared_hash_mode = "lf_stable"
        elif expected_sha == raw_sha:
            declared_hash_mode = "raw_bytes_legacy"
        elif expected_sha == crlf_sha:
            declared_hash_mode = "crlf_raw_bytes_legacy"
        else:
            raise ValueError(
                "real C source sha256 mismatch: "
                f"{relative}: {expected_sha} != {stable_sha}/{raw_sha}/{crlf_sha}"
            )
        refs.append(
            {
                "path": relative,
                "sha256": stable_sha,
                "status": "bound",
                "declared_source_sha256": expected_sha,
                "declared_hash_mode": declared_hash_mode,
                "raw_sha256": raw_sha,
                "crlf_sha256": crlf_sha,
            }
        )
    return refs


def _compiler_version(resolution: dict[str, Any]) -> str:
    if resolution.get("adapter") == "wsl":
        command = [
            str(resolution["launcher"]),
            "-e",
            "sh",
            "-lc",
            f"{resolution['path']} --version",
        ]
    else:
        command = [str(resolution["path"]), "--version"]
    result = subprocess.run(command, text=True, capture_output=True, timeout=30)
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError("C compiler version probe failed")
    return result.stdout.splitlines()[0].strip()


def _verified_ref(value: dict[str, Any], repo_root: Path, label: str) -> Path:
    path_value = value.get("path")
    expected_sha = value.get("sha256")
    if not isinstance(path_value, str) or not isinstance(expected_sha, str):
        raise ValueError(f"{label} path/sha256 is missing")
    path = (repo_root / path_value).resolve()
    _inside_repo(path, repo_root, label)
    actual_sha = judge_validator.sha256_file(path)
    if actual_sha != expected_sha:
        raise ValueError(f"{label} sha256 mismatch: {expected_sha} != {actual_sha}")
    return path


def _ref(path: Path, repo_root: Path, status: str) -> dict[str, Any]:
    _inside_repo(path, repo_root, "artifact")
    return {
        "path": path.resolve().relative_to(repo_root.resolve()).as_posix(),
        "sha256": judge_validator.sha256_file(path),
        "status": status,
    }


def _inside_repo(path: Path, repo_root: Path, label: str) -> None:
    try:
        path.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes repository root: {path}") from exc


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return value


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
