from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context import canonical_json_bytes
from .context_replay import validate_replay_api_contract_binding
from .context_security import sha256_bytes, sha256_path
from .repair import render_repair_prompt


def validate_repair_context_and_prompts(
    context_pack: Any,
    *,
    context_path: Path | None,
    report: dict[str, Any],
    report_path: Path,
) -> list[str]:
    if not isinstance(context_pack, dict) or context_path is None:
        return ["ai_repair_context_binding_invalid"]
    bindings = report.get("bindings")
    replay_contract = context_pack.get("replay_api_contract")
    if (
        context_pack.get("schema_version") != 4
        or not isinstance(bindings, dict)
        or bindings.get("context_pack_sha256")
        != sha256_bytes(canonical_json_bytes(context_pack))
        or bindings.get("replay_api_contract_sha256")
        != sha256_bytes(canonical_json_bytes(replay_contract))
        or validate_replay_api_contract_binding(context_pack, context_path) != "bound"
    ):
        return ["ai_repair_context_binding_invalid"]

    initial = report.get("initial_candidate")
    previous_path = bound_sibling_path(initial, report_path.parent)
    if previous_path is None:
        return ["ai_repair_round_prompt_context_mismatch"]
    rounds = report.get("rounds")
    if not isinstance(rounds, list):
        return ["ai_repair_round_prompt_context_mismatch"]
    for round_record in rounds:
        round_bindings = round_record.get("bindings") if isinstance(round_record, dict) else None
        failure_path = bound_sibling_path(
            round_bindings.get("failure_facts") if isinstance(round_bindings, dict) else None,
            report_path.parent,
        )
        prompt_path = bound_sibling_path(
            round_bindings.get("prompt") if isinstance(round_bindings, dict) else None,
            report_path.parent,
        )
        if failure_path is None or prompt_path is None:
            return ["ai_repair_round_prompt_context_mismatch"]
        try:
            candidate_source = previous_path.read_text(encoding="utf-8")
            failure_facts = json.loads(failure_path.read_text(encoding="utf-8"))
            actual_prompt = prompt_path.read_bytes()
        except (OSError, UnicodeError, json.JSONDecodeError):
            return ["ai_repair_round_prompt_context_mismatch"]
        if not isinstance(failure_facts, dict) or actual_prompt != render_repair_prompt(
            context_pack,
            candidate_source,
            failure_facts,
        ).encode("utf-8"):
            return ["ai_repair_round_prompt_context_mismatch"]
        next_candidate = (
            bound_sibling_path(round_bindings.get("candidate"), report_path.parent)
            if isinstance(round_bindings, dict) and round_bindings.get("candidate") is not None
            else None
        )
        if next_candidate is not None:
            previous_path = next_candidate
    return []


def bound_sibling_path(ref: Any, root: Path) -> Path | None:
    if not isinstance(ref, dict):
        return None
    name = ref.get("path") if "path" in ref else ref.get("name")
    expected_sha = ref.get("sha256")
    if (
        not isinstance(name, str)
        or not name
        or Path(name).name != name
        or not isinstance(expected_sha, str)
        or len(expected_sha) != 64
    ):
        return None
    path = root / name
    try:
        if path.is_symlink() or not path.is_file() or sha256_path(path) != expected_sha:
            return None
    except OSError:
        return None
    return path


__all__ = ["validate_repair_context_and_prompts"]
