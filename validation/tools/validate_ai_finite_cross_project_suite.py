#!/usr/bin/env python3
"""Validate the bounded, real-project AI translation preflight suite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from validation.tools._ai_finite_cross_project_contract import (
    DEFAULT_SUITE,
    PROVENANCE_KINDS,
    REQUIRED_PROJECTS,
    SuiteContractError,
    load_json,
    validate_policy,
    validate_project_sources,
)
from validation.tools._ai_finite_cross_project_preflight import (
    preflight_item,
    preflight_project_source,
    validate_item_shape,
)


def validate_suite(suite_path: Path | str, repo_root: Path | str | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[2]
    path = Path(suite_path)
    if not path.is_absolute():
        path = root / path
    suite = load_json(path, "AI finite cross-project suite")
    validate_policy(suite)
    project_sources = validate_project_sources(suite["project_sources"])
    project_source_reasons: dict[str, list[str]] = {}
    project_source_cache: dict[tuple[str, str, str], list[str]] = {}
    for project_id, source in project_sources.items():
        cache_key = (source["repository"], source["root"], source["commit"])
        if cache_key not in project_source_cache:
            project_source_cache[cache_key] = preflight_project_source(source, root)
        project_source_reasons[project_id] = project_source_cache[cache_key]

    items = suite["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise SuiteContractError("suite.items must contain 1..20 entries")
    shaped = [validate_item_shape(item, index) for index, item in enumerate(items)]
    ids = [item["id"] for item, _ in shaped]
    families = [item["construct_family"] for item, _ in shaped]
    projects = {item["project_id"] for item, _ in shaped}
    if len(ids) != len(set(ids)):
        raise SuiteContractError("suite item ids must be unique")
    if len(families) != len(set(families)):
        raise SuiteContractError("construct_family must be unique; duplicate families cannot inflate coverage")
    if len(families) < 10:
        raise SuiteContractError("suite must contain at least 10 distinct construct families")
    if len(projects) < 3 or not REQUIRED_PROJECTS.issubset(projects):
        raise SuiteContractError("suite must include real FlashDB, zlib-ng, and libuv entries")

    results = [
        preflight_item(item, span, root, project_sources, project_source_reasons)
        for item, span in shaped
    ]
    ready = sum(item["status"] == "ready" for item in results)
    blocked = len(results) - ready
    provenance_counts = {
        kind: sum(item["provenance_kind"] == kind for item, _ in shaped)
        for kind in sorted(PROVENANCE_KINDS)
    }
    return {
        "schema_version": 1,
        "suite_id": suite["suite_id"],
        "contract_status": "passed",
        "status": "ready" if blocked == 0 else "blocked",
        "purpose": "preflight-only",
        "summary": {
            "items_total": len(results),
            "ready": ready,
            "blocked": blocked,
            "real_projects": len(projects),
            "construct_families": len(set(families)),
            "provenance_counts": provenance_counts,
            "model_invocations": 0,
            "translations_executed": 0,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
        "items": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default=DEFAULT_SUITE)
    parser.add_argument("--require-all-ready", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = validate_suite(args.suite)
    except SuiteContractError as exc:
        print(json.dumps({"contract_status": "failed", "error": str(exc)}, ensure_ascii=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True))
    if args.require_all_ready and report["status"] != "ready":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
