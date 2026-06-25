#!/usr/bin/env python3
"""Validate FlashDB Rust version/config binding evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_FIELDS = [
    "schema_version",
    "command",
    "agent_contract_version",
    "context_schema_version",
    "patch_plan_schema_version",
    "fixture_schema_version",
    "evidence_schema_version",
    "package_name",
    "package_version",
    "cargo_toml_sha256",
    "cargo_lock_sha256",
    "rustc_version",
    "cargo_version",
    "openspec_version",
    "flashdb_source_commit",
    "flashdb_feature_matrix",
    "command_arguments",
    "fixture_sha256",
    "ai_metadata",
    "cache_key_inputs",
]
REQUIRED_CACHE_KEYS = [
    "agent_contract_version",
    "context_schema_version",
    "patch_plan_schema_version",
    "fixture_schema_version",
    "evidence_schema_version",
    "package_version",
    "cargo_toml_sha256",
    "cargo_lock_sha256",
    "rustc_version",
    "cargo_version",
    "openspec_version",
    "flashdb_source_commit",
    "flashdb_feature_matrix",
    "command_arguments",
    "fixture_sha256",
    "ai_metadata",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--cargo-toml", type=Path, default=REPO_ROOT / "flashDB_rust" / "Cargo.toml")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    report = validate_version_binding(args.manifest, args.cargo_toml)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def validate_version_binding(manifest_path: Path, cargo_toml_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    missing = [field for field in REQUIRED_FIELDS if field not in manifest]
    require(not missing, f"version manifest missing required fields: {', '.join(missing)}")
    require(manifest.get("command") == "version-manifest", "version manifest command must be version-manifest")
    require(manifest.get("schema_version") == 1, "version manifest schema_version must be 1")

    cache_keys = manifest.get("cache_key_inputs")
    require(isinstance(cache_keys, list) and cache_keys, "cache_key_inputs must be a non-empty list")
    missing_cache_keys = [field for field in REQUIRED_CACHE_KEYS if field not in cache_keys]
    require(not missing_cache_keys, f"cache_key_inputs missing binding keys: {', '.join(missing_cache_keys)}")

    cargo = tomllib.loads(cargo_toml_path.read_text(encoding="utf-8"))
    package = cargo.get("package", {})
    require(
        manifest.get("package_name") == package.get("name"),
        f"package_name drift: {manifest.get('package_name')} != {package.get('name')}",
    )
    require(
        manifest.get("package_version") == package.get("version"),
        f"package_version drift: {manifest.get('package_version')} != {package.get('version')}",
    )

    cargo_lock_path = cargo_toml_path.with_name("Cargo.lock")
    expected_hashes = {
        "cargo_toml_sha256": sha256(cargo_toml_path),
        "cargo_lock_sha256": sha256(cargo_lock_path),
    }
    for key, expected in expected_hashes.items():
        value = str(manifest.get(key, "")).lower()
        require(value == expected, f"{key} drift: {value} != {expected}")
    for key in ("rustc_version", "cargo_version", "openspec_version"):
        value = str(manifest.get(key, ""))
        require(value and value != "NOT_FOUND", f"{key} is missing or NOT_FOUND")
    require(
        len(str(manifest.get("flashdb_source_commit", ""))) >= 7,
        "flashdb_source_commit must be recorded",
    )
    require(isinstance(manifest.get("command_arguments"), list), "command_arguments must be recorded")
    require("ai_metadata" in manifest, "ai_metadata must be recorded")

    return {
        "schema_version": 1,
        "status": "passed",
        "manifest": rel(manifest_path),
        "cargo_toml": rel(cargo_toml_path),
        "package_name": manifest["package_name"],
        "package_version": manifest["package_version"],
        "checked_fields": REQUIRED_FIELDS,
        "cache_key_inputs": cache_keys,
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
