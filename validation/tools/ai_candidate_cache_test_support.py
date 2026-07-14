from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from validation.tools import validate_competition_run_summary as summary_validator
from validation.tools._ai_candidate_harness_parts import candidate_cache
from validation.tools._ai_candidate_harness_parts.context_callees import (
    build_external_callee_source_context,
    callee_source_input_bindings,
)
from validation.tools._ai_candidate_harness_parts.context_security import (
    canonical_json_bytes,
    sha256_bytes,
)


SOURCE = "pub fn scale(value: i32) -> i32 { value.wrapping_mul(3) }\n"
MODEL_POLICY = {
    "model": "zai/glm-5.1",
    "agent": "c2rust-migrator",
    "variant": "max",
}


def response(source: str = SOURCE) -> str:
    payload = {
        "schema_version": 1,
        "candidate": {"language": "rust", "source": source},
        "assumptions": [],
    }
    event = {
        "type": "message.part.updated",
        "part": {"type": "text", "text": json.dumps(payload)},
    }
    return json.dumps(event) + "\n"


def repair_response(source: str) -> str:
    payload = {
        "schema_version": 1,
        "repair": {"kind": "candidate", "language": "rust", "source": source},
        "assumptions": [],
    }
    event = {
        "type": "message.part.updated",
        "part": {"type": "text", "text": json.dumps(payload)},
    }
    return json.dumps(event) + "\n"


def context_pack(root: Path, slice_id: str = "cache-scale") -> dict[str, object]:
    fixture_root = root / "cache-context-source"
    callee_path = fixture_root / "src" / "helper.c"
    callee_path.parent.mkdir(parents=True, exist_ok=True)
    callee_path.write_text(
        "int helper(int value) {\n    return value * 3;\n}\n",
        encoding="utf-8",
    )
    callee_sha = sha256_bytes(callee_path.read_bytes())
    c_source = "int scale(int value) { return helper(value); }"
    boundary_payload = {
        "external_direct_callees": [
            {
                "name": "helper",
                "source_ref": "src/helper.c#helper",
                "source_files": [{"path": "src/helper.c", "sha256": callee_sha}],
                "definition_status": "real_source_bound",
            }
        ]
    }
    callee_context = build_external_callee_source_context(
        {"function_name": "scale", "c_boundary": boundary_payload},
        source_root=fixture_root,
        known_roots=(str(fixture_root),),
    )
    replay_source = "#[test]\nfn replay() { let _ = scale(1); }\n"
    replay_bytes = replay_source.encode("utf-8")
    replay_name = f"l3-{slice_id}-rust-replay-test-draft.rs"
    inputs = [
        {
            "kind": "generated_replay_contract",
            "path": replay_name,
            "sha256": sha256_bytes(replay_bytes),
            "size_bytes": len(replay_bytes),
        },
        *callee_source_input_bindings(callee_context),
    ]
    return {
        "schema_version": 4,
        "target_id": "generic-target",
        "slice_id": slice_id,
        "function_name": "scale",
        "source_root": {"status": "unavailable"},
        "source": {
            "span": {
                "status": "inline_slice_spec",
                "sha256": sha256_bytes(c_source.encode("utf-8")),
                "content": c_source,
            }
        },
        "compile_context": {},
        "c_boundary": {
            "sha256": sha256_bytes(canonical_json_bytes(boundary_payload)),
            "truncated": False,
            "payload": boundary_payload,
            "required_callee_sections": ["external_direct_callees"],
            "missing_required_callee_sections": [],
        },
        "external_callee_source_context": callee_context,
        "rust_boundary": {"payload": {"public_api": [{"name": "scale"}]}},
        "replay_api_contract": {
            "schema_version": 1,
            "contract_kind": "generated_replay_rust_source",
            "function_name": "scale",
            "status": "bound",
            "call_count": 1,
            "model_input_policy": {
                "replay_source_content": "withheld_oracle_bearing",
                "oracle_values": "withheld",
                "call_plan": "included",
                "required_candidate_api": "included_when_bound",
            },
            "source": {
                "path": replay_name,
                "sha256": sha256_bytes(replay_bytes),
                "size_bytes": len(replay_bytes),
                "content": replay_source,
            },
            "requirements": {
                "candidate_defines_function": True,
                "all_call_sites_typecheck": True,
                "parameter_count_and_order": "as_invoked_by_generated_replay",
                "return_type": "as_constrained_by_generated_replay",
            },
        },
        "bindings": {"inputs": inputs},
        "claim_boundary": {"semantic_gate": False},
    }


def candidate_manifest_schema() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[1]
        / "auto-translation-template"
        / "ai-candidate-manifest.schema.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def fresh_manifest_validation(
    manifest: dict[str, Any],
    *,
    manifest_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    return summary_validator.validate_fresh_ai_manifest(
        manifest,
        manifest_path=manifest_path,
        policy=MODEL_POLICY,
        summary_path=repo_root / "competition-run-summary.json",
        repo_root=repo_root,
    )


class CandidateCacheKeyMixin:
    def key_payload(self, context_sha: str = "a" * 64) -> dict[str, object]:
        return candidate_cache.cache_key_payload(
            context_sha,
            prompt_sha256="b" * 64,
            resolved_model="zai/glm-5.1",
            agent="c2rust-migrator",
            agent_definition_sha256="c" * 64,
            variant="max",
        )
