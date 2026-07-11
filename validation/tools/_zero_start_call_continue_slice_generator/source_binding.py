from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .common import sha256_bytes, sha256_text
from .constants import DEFAULT_INPUT, U32_MAX


CASE_IDS = [
    "zero-start-ordinary",
    "zero-start-u32-wrap",
    "sentinel-hit",
    "zero-miss",
    "ordinary-miss",
]
REQUIRED_INPUTS = {
    "db_observed_initial",
    "db_add_rhs",
    "sector_seed",
    "sector_addr",
    "sector_header_data_size",
    "alias_start_initial",
    "owner_traversed_initial",
    "scripted_return",
}


def normalized_span(text: str, line_start: int, line_end: int, *, trim: bool) -> str:
    lines = text.splitlines()
    if line_start < 1 or line_end < line_start or line_end > len(lines):
        raise ValueError(f"invalid source span {line_start}-{line_end}")
    value = "\n".join(lines[line_start - 1 : line_end])
    return value.strip() if trim else value + "\n"


def load_generator_input(path: Path = DEFAULT_INPUT) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_generator_input(value)
    return value


def validate_generator_input(value: dict[str, Any]) -> None:
    if value.get("schema_version") != 1:
        raise ValueError("generator input schema_version must be 1")
    source = value.get("source")
    if not isinstance(source, dict):
        raise ValueError("generator input source must be an object")
    if source.get("source_root") != "sources/FlashDB":
        raise ValueError("generator input must preserve the repo-owned FlashDB source root")
    if source.get("source_branch") != "competition":
        raise ValueError("generator input must bind the competition branch")
    if not is_sha(source.get("source_commit"), 40):
        raise ValueError("generator input source_commit must be a full git commit")
    if not is_sha(source.get("file_sha256"), 64):
        raise ValueError("generator input file_sha256 must be sha256-shaped")
    containing = source.get("containing_function")
    fragment = source.get("fragment")
    if not isinstance(containing, dict) or not isinstance(fragment, dict):
        raise ValueError("generator input source spans must be objects")
    if containing.get("hash_mode") != "trimmed_normalized_span":
        raise ValueError("containing function hash mode drifted")
    if fragment.get("hash_mode") != "normalized_line_span_with_newline":
        raise ValueError("fragment hash mode drifted")
    if sha256_text(str(fragment.get("text", ""))) != fragment.get("sha256"):
        raise ValueError("generator input fragment text sha256 mismatch")
    if not is_sha(containing.get("sha256"), 64):
        raise ValueError("containing function sha256 must be sha256-shaped")
    cases = value.get("cases")
    if not isinstance(cases, list) or [case.get("id") for case in cases] != CASE_IDS:
        raise ValueError("generator input must contain the five ordered P0-T21 cases")
    for case in cases:
        inputs = case.get("inputs")
        if not isinstance(inputs, dict) or set(inputs) != REQUIRED_INPUTS:
            raise ValueError(f"{case.get('id')} input shape drifted")
        if any(not isinstance(item, int) or not 0 <= item <= U32_MAX for item in inputs.values()):
            raise ValueError(f"{case.get('id')} inputs must be u32 values")


def validate_source_checkout(source_root: Path, generator_input: dict[str, Any]) -> None:
    source = generator_input["source"]
    root = source_root.resolve()
    actual_commit = git_output(root, "rev-parse", "HEAD")
    actual_branch = git_output(root, "rev-parse", "--abbrev-ref", "HEAD")
    actual_repository = git_output(root, "config", "--get", "remote.origin.url")
    if actual_commit != source["source_commit"]:
        raise ValueError(f"source commit mismatch: {actual_commit} != {source['source_commit']}")
    if actual_branch != source["source_branch"]:
        raise ValueError(f"source branch mismatch: {actual_branch} != {source['source_branch']}")
    if normalize_repository(actual_repository) != normalize_repository(source["source_repository"]):
        raise ValueError("source repository mismatch")
    source_path = root / source["file"]
    raw = source_path.read_bytes()
    if sha256_bytes(raw) != source["file_sha256"]:
        raise ValueError("source file sha256 mismatch")
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    validate_span(text, source["containing_function"], trim=True)
    actual_fragment = validate_span(text, source["fragment"], trim=False)
    if source["containing_function"]["declaration_text"] not in normalized_span(
        text,
        source["containing_function"]["line_start"],
        source["containing_function"]["line_end"],
        trim=True,
    ):
        raise ValueError("containing function declaration mismatch")
    if actual_fragment != source["fragment"]["text"]:
        raise ValueError("source fragment text mismatch")


def validate_span(text: str, span: dict[str, Any], *, trim: bool) -> str:
    actual = normalized_span(text, span["line_start"], span["line_end"], trim=trim)
    if sha256_text(actual) != span["sha256"]:
        raise ValueError("source span sha256 mismatch")
    return actual


def git_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def normalize_repository(value: str) -> str:
    return value.strip().rstrip("/").removesuffix(".git").lower()


def is_sha(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(
        character in "0123456789abcdef" for character in value
    )
