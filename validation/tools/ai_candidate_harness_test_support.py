from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from validation.tools import ai_candidate_harness


def minimal_spec(source_root: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "target_id": "generic-target",
        "slice_id": "generic-scale",
        "function_name": "scale_value",
        "c_source": "int scale_value(int value) { return value * 3; }",
        "source_file": "src/math.c",
        "source_commit": "abc123",
        "source_file_hashes": {"src/math.c": "a" * 64},
        "function_source_span": {"file": "src/math.c", "sha256": "b" * 64},
        "build_profile": {
            "include_paths": [f"{source_root}/include"],
            "defines": ["FEATURE=1"],
            "api_key": "must-not-leak",
        },
        "c_boundary": {"signatures": [{"function": "scale_value", "return_type": "int"}]},
        "rust_boundary": {"public_api": [{"name": "scale_value"}]},
    }


def jsonl_response(source: str) -> str:
    payload = json.dumps(
        {
            "schema_version": 1,
            "candidate": {"language": "rust", "source": source},
            "assumptions": [],
        }
    )
    return json.dumps({"type": "message.part.updated", "part": {"type": "text", "text": payload}}) + "\n"


def empty_completion_response(session_id: str = "ses_empty") -> str:
    return "\n".join(
        json.dumps(event)
        for event in (
            {
                "type": "step_start",
                "sessionID": session_id,
                "part": {"type": "step-start", "sessionID": session_id},
            },
            {
                "type": "step_finish",
                "sessionID": session_id,
                "part": {
                    "type": "step-finish",
                    "sessionID": session_id,
                    "reason": "unknown",
                    "tokens": {
                        "input": 0,
                        "output": 0,
                        "reasoning": 0,
                        "cache": {"write": 0, "read": 0},
                    },
                },
            },
        )
    ) + "\n"


def build_provider_context(spec_path: Path) -> dict[str, object]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    function_name = str(spec["function_name"])
    replay_path = spec_path.with_name(
        f"l3-{spec['slice_id']}-rust-replay-test-draft.rs"
    )
    replay_path.write_text(
        f"#[test]\nfn replay() {{ let _ = {function_name}(1); }}\n",
        encoding="utf-8",
    )
    return ai_candidate_harness.build_context_pack(
        spec_path,
        replay_test_path=replay_path,
    )


class ManifestSchemaAssertions:
    def assert_manifest_schema(self, manifest: dict[str, object]) -> None:
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "auto-translation-template"
            / "ai-candidate-manifest.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft7Validator(schema).validate(manifest)
