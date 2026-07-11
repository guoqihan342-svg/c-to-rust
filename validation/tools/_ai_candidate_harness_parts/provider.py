from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any, Callable

from .context import atomic_write_bytes, atomic_write_json, canonical_json_bytes, sha256_bytes, sha256_path


LOGICAL_MODEL = "GLM-5.1"
DEFAULT_RESOLVED_MODEL = "zai/glm-5.1"
DEFAULT_AGENT = "c2rust-migrator"
DEFAULT_VARIANT = "max"


@dataclass(frozen=True)
class ProviderExecution:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


Runner = Callable[[list[str], int], ProviderExecution]


def generate_candidate(
    context_pack: dict[str, Any],
    *,
    out_dir: Path,
    opencode_command: str = "opencode",
    resolved_model: str = DEFAULT_RESOLVED_MODEL,
    agent: str = DEFAULT_AGENT,
    variant: str = DEFAULT_VARIANT,
    timeout_seconds: int = 180,
    runner: Runner | None = None,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    target_id = str(context_pack["target_id"])
    slice_id = str(context_pack["slice_id"])
    prefix = f"l3-{slice_id}"
    context_path = out_dir / f"{prefix}-ai-context-pack.json"
    prompt_path = out_dir / f"{prefix}-ai-prompt.txt"
    response_path = out_dir / f"{prefix}-ai-response.jsonl"
    candidate_path = out_dir / f"{prefix}-ai-rust-candidate.rs"
    manifest_path = out_dir / f"{prefix}-ai-candidate-manifest.json"

    atomic_write_json(context_path, context_pack)
    prompt = render_prompt(context_pack)
    atomic_write_bytes(prompt_path, prompt.encode("utf-8"))
    argv = [
        opencode_command,
        "run",
        "--pure",
        "--format",
        "json",
        "--print-logs",
        "--log-level",
        "ERROR",
        "--model",
        resolved_model,
        "--agent",
        agent,
        "--variant",
        variant,
        prompt,
    ]
    execution = (runner or subprocess_runner)(argv, timeout_seconds)
    atomic_write_bytes(response_path, execution.stdout.encode("utf-8"))

    base = manifest_base(
        target_id,
        slice_id,
        resolved_model,
        agent,
        variant,
        context_path,
        prompt_path,
        response_path,
    )
    failure = classify_provider_failure(execution)
    if failure is not None:
        manifest = {
            **base,
            "status": "blocked",
            "candidates": [],
            "failure": failure,
        }
        atomic_write_json(manifest_path, manifest)
        return manifest

    try:
        parsed = parse_candidate_response(execution.stdout)
    except ValueError as error:
        manifest = {
            **base,
            "status": "blocked",
            "candidates": [],
            "failure": {"kind": "invalid_ai_response", "message": str(error)},
        }
        atomic_write_json(manifest_path, manifest)
        return manifest

    candidate_source = parsed["candidate"]["source"]
    atomic_write_bytes(candidate_path, candidate_source.encode("utf-8"))
    candidate = {
        "candidate_id": "opencode-glm51-1",
        "purpose": "rust_draft",
        "kind": "opencode-ai",
        "provider_label": "zai",
        "model_label": LOGICAL_MODEL,
        "resolved_model": resolved_model,
        "prompt_scope": [
            "slice_spec",
            "source_spans",
            "type_map_excerpt",
            "cfg_excerpt",
            "pointer_graph_excerpt",
            "root_cause_summary",
        ],
        "input_artifact_hashes": {
            "context_pack": sha256_path(context_path),
            "prompt": sha256_path(prompt_path),
        },
        "output_hash": sha256_path(candidate_path),
        "artifact": {"path": candidate_path.name, "sha256": sha256_path(candidate_path)},
        "applied": False,
        "semantic_pass": False,
        "accepted_by_gates": [],
        "rejected_by_gates": [],
        "assumptions": parsed.get("assumptions", []),
    }
    manifest = {**base, "status": "generated", "candidates": [candidate]}
    atomic_write_json(manifest_path, manifest)
    return manifest


def apply_generated_candidate(
    manifest: dict[str, Any],
    *,
    out_dir: Path,
    canonical_draft_path: Path,
) -> dict[str, Any]:
    if manifest.get("status") != "generated":
        return manifest
    candidates = manifest.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise ValueError("generated AI manifest must contain exactly one candidate")
    candidate = candidates[0]
    if not isinstance(candidate, dict):
        raise ValueError("generated AI candidate must be an object")
    artifact = candidate.get("artifact")
    if not isinstance(artifact, dict):
        raise ValueError("generated AI candidate artifact binding is missing")
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("generated AI candidate id is missing")
    relative_path = artifact.get("path")
    expected_sha256 = artifact.get("sha256")
    if not isinstance(relative_path, str) or not relative_path or Path(relative_path).is_absolute():
        raise ValueError("generated AI candidate artifact path must be relative")
    candidate_path = (out_dir / relative_path).resolve()
    try:
        candidate_path.relative_to(out_dir.resolve())
    except ValueError as error:
        raise ValueError("generated AI candidate artifact escapes output directory") from error
    if not candidate_path.is_file():
        raise ValueError("generated AI candidate artifact does not exist")
    actual_sha256 = sha256_path(candidate_path)
    if actual_sha256 != expected_sha256 or candidate.get("output_hash") != actual_sha256:
        raise ValueError("generated AI candidate artifact sha256 drifted")
    canonical_draft_path = canonical_draft_path.resolve()
    try:
        canonical_draft_path.relative_to(out_dir.resolve())
    except ValueError as error:
        raise ValueError("canonical Rust draft escapes output directory") from error
    atomic_write_bytes(canonical_draft_path, candidate_path.read_bytes())
    canonical_sha256 = sha256_path(canonical_draft_path)
    candidate["applied"] = True
    candidate["applied_artifact"] = {
        "path": canonical_draft_path.name,
        "sha256": canonical_sha256,
    }
    candidate["rust_draft_sha256"] = canonical_sha256
    manifest["selected_candidate_id"] = candidate_id
    manifest_path = out_dir / f"l3-{manifest['slice_id']}-ai-candidate-manifest.json"
    atomic_write_json(manifest_path, manifest)
    return manifest


def render_prompt(context_pack: dict[str, Any]) -> str:
    context_json = json.dumps(context_pack, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return (
        "Task mode: generate-candidate\n"
        "Generate one Rust candidate for the declared C slice. Do not call tools, inspect files, "
        "or modify the repository. Preserve C integer, alias, ABI, side-effect, and return semantics. "
        "Use unsafe only when the boundary cannot be represented safely. Return exactly one JSON object "
        "with this shape and no markdown: "
        '{"schema_version":1,"candidate":{"language":"rust","source":"..."},"assumptions":[]}\n'
        f"ContextPack: {context_json}"
    )


def parse_candidate_response(stdout: str) -> dict[str, Any]:
    text = assistant_text_from_jsonl(stdout).strip()
    if not text:
        raise ValueError("OpenCode response contained no assistant text")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"assistant text is not one JSON object: {error.msg}") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("candidate response schema_version must be 1")
    candidate = payload.get("candidate")
    if not isinstance(candidate, dict) or candidate.get("language") != "rust":
        raise ValueError("candidate response requires candidate.language=rust")
    source = candidate.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("candidate response requires non-empty candidate.source")
    assumptions = payload.get("assumptions", [])
    if not isinstance(assumptions, list) or not all(isinstance(item, str) for item in assumptions):
        raise ValueError("candidate response assumptions must be a string array")
    return payload


def assistant_text_from_jsonl(stdout: str) -> str:
    fragments: list[str] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        fragments.extend(text_fragments(event))
    return "".join(fragments)


def text_fragments(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    fragments: list[str] = []
    part = value.get("part")
    if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
        fragments.append(part["text"])
    if value.get("type") in {"text", "text-delta"} and isinstance(value.get("text"), str):
        fragments.append(value["text"])
    message = value.get("message")
    if isinstance(message, dict) and message.get("role") == "assistant":
        content = message.get("content")
        if isinstance(content, str):
            fragments.append(content)
    return fragments


def classify_provider_failure(execution: ProviderExecution) -> dict[str, str] | None:
    combined = f"{execution.stderr}\n{execution.stdout}".lower()
    if execution.timed_out:
        return {"kind": "provider_timeout", "message": "OpenCode candidate generation timed out"}
    if "insufficient balance" in combined or "no resource package" in combined:
        return {"kind": "provider_insufficient_balance", "message": "GLM provider balance or resource package is unavailable"}
    if "unauthorized" in combined or "invalid api key" in combined or "authentication" in combined:
        return {"kind": "provider_authentication_failed", "message": "OpenCode provider authentication failed"}
    if execution.returncode != 0:
        return {"kind": "opencode_failed", "message": f"OpenCode exited with code {execution.returncode}"}
    return None


def manifest_base(
    target_id: str,
    slice_id: str,
    resolved_model: str,
    agent: str,
    variant: str,
    context_path: Path,
    prompt_path: Path,
    response_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "target_id": target_id,
        "slice_id": slice_id,
        "ai_required_for_default_pipeline": True,
        "generator": {
            "tool": "opencode",
            "provider": "zai",
            "logical_model": LOGICAL_MODEL,
            "resolved_model": resolved_model,
            "agent": agent,
            "variant": variant,
        },
        "bindings": {
            "context_pack": {"path": context_path.name, "sha256": sha256_path(context_path)},
            "prompt": {"path": prompt_path.name, "sha256": sha256_path(prompt_path)},
            "raw_response": {"path": response_path.name, "sha256": sha256_path(response_path)},
        },
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "candidate_requires_common_validation": True,
        },
        "cache_invalidation_keys": [
            f"context_pack:{sha256_path(context_path)}",
            f"prompt:{sha256_path(prompt_path)}",
            f"raw_response:{sha256_path(response_path)}",
        ],
    }


def subprocess_runner(argv: list[str], timeout_seconds: int) -> ProviderExecution:
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        return ProviderExecution(
            returncode=124,
            stdout=decode_timeout_output(error.stdout),
            stderr=decode_timeout_output(error.stderr),
            timed_out=True,
        )
    return ProviderExecution(completed.returncode, completed.stdout, completed.stderr)


def decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
