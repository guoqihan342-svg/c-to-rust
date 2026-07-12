from __future__ import annotations

import os
from pathlib import Path
import shlex
from typing import Any, Callable

from .candidate_cache import (
    agent_definition_sha256,
    cache_key_payload,
    cache_key_sha256,
    candidate_generation_lock,
    load_candidate_cache,
    store_candidate_cache,
)
from .context import atomic_write_bytes, atomic_write_json, canonical_json_bytes, sha256_bytes, sha256_path
from .context_replay import materialize_replay_api_contract
from .context_scope import prompt_scope_for_context
from .model_identity import (
    COMPETITION_LOGICAL_MODEL,
    DEFAULT_RESOLVED_MODEL,
    resolve_model_identity,
)
from .prompt_transport import prompt_file_arguments, prompt_transport_contract
from .provider_readiness import evaluate_provider_readiness
from .provider_receipt import write_invocation_receipt
from .provider_response import (
    MAX_ASSUMPTIONS,
    MAX_ASSUMPTION_BYTES,
    MAX_CANDIDATE_BYTES,
    assistant_text_from_jsonl,
    parse_candidate_response,
    render_prompt,
    text_fragments,
)
from .provider_runtime import (
    MAX_PROVIDER_STDERR_BYTES,
    MAX_PROVIDER_STDOUT_BYTES,
    OPENCODE_LOG_PATH_ENV,
    PROVIDER_AUTH_SENTINEL,
    PROVIDER_BALANCE_SENTINEL,
    PROVIDER_INVOCATION_SENTINEL,
    ProviderExecution,
    append_provider_log_diagnostic,
    appended_provider_log_diagnostic,
    classify_provider_failure,
    decode_timeout_output,
    opencode_log_candidates,
    snapshot_opencode_log,
    subprocess,
    subprocess_runner,
)


LOGICAL_MODEL = COMPETITION_LOGICAL_MODEL
DEFAULT_AGENT = "c2rust-candidate"
DEFAULT_VARIANT = "max"
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
    cache_root: Path | None = None,
    _cache_generation_lock_held: bool = False,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    target_id = str(context_pack["target_id"])
    slice_id = str(context_pack["slice_id"])
    prefix = f"l3-{slice_id}"
    context_path = out_dir / f"{prefix}-ai-context-pack.json"
    prompt_path = out_dir / f"{prefix}-ai-prompt.txt"
    response_path = out_dir / f"{prefix}-ai-response.jsonl"
    invocation_receipt_path = out_dir / f"{prefix}-ai-invocation-receipt.json"
    session_identity_path = out_dir / f"{prefix}-ai-session-export-identity.json"
    candidate_path = out_dir / f"{prefix}-ai-rust-candidate.rs"
    cache_entry_path = out_dir / f"{prefix}-ai-cache-entry.json"
    manifest_path = out_dir / f"{prefix}-ai-candidate-manifest.json"

    replay_materialization_error = False
    try:
        materialize_replay_api_contract(context_pack, out_dir)
    except ValueError:
        replay_materialization_error = True
    atomic_write_json(context_path, context_pack)
    prompt = render_prompt(context_pack)
    atomic_write_bytes(prompt_path, prompt.encode("utf-8"))
    provider_preflight = evaluate_provider_readiness(context_pack)
    if replay_materialization_error:
        provider_preflight = {
            "status": "blocked",
            "source_span_status": provider_preflight.get(
                "source_span_status", "invalid_context_shape"
            ),
            "replay_api_contract_status": "binding_mismatch",
        }
    if provider_preflight["status"] != "ready":
        atomic_write_bytes(response_path, b"")
        base = manifest_base(
            target_id,
            slice_id,
            resolved_model,
            agent,
            variant,
            context_path,
            prompt_path,
            response_path,
            provider_invocations=0,
            provider_preflight=provider_preflight,
            cache_evidence=(
                {"status": "not_checked", "reason": "context_not_provider_ready"}
                if cache_root is not None
                else {"status": "disabled"}
            ),
        )
        manifest = {
            **base,
            "status": "blocked",
            "candidates": [],
            "failure": {
                "kind": "context_not_provider_ready",
                "message": "ContextPack is not ready for provider invocation",
            },
        }
        atomic_write_json(manifest_path, manifest)
        return manifest
    agent_definition_sha = agent_definition_sha256(
        agent,
        Path(__file__).resolve().parents[3],
    )
    cache_payload = None
    cache_evidence: dict[str, Any] = {"status": "disabled"}
    if cache_root is not None:
        cache_payload = cache_key_payload(
            sha256_path(context_path),
            prompt_sha256=sha256_path(prompt_path),
            resolved_model=resolved_model,
            agent=agent,
            agent_definition_sha256=agent_definition_sha,
            variant=variant,
        )
        cache_key = cache_key_sha256(cache_payload)
        cached, cache_reason = load_candidate_cache(
            cache_root,
            cache_payload,
            parse_candidate_response,
        )
        if cached is not None:
            atomic_write_bytes(cache_entry_path, cached.entry_bytes)
            atomic_write_bytes(response_path, cached.response_bytes)
            atomic_write_bytes(candidate_path, cached.candidate_bytes)
            cache_evidence = {
                "status": "hit",
                "key_sha256": cache_key,
                "entry_sha256": cached.entry_sha256,
                "entry": {
                    "path": cache_entry_path.name,
                    "sha256": sha256_path(cache_entry_path),
                },
                "raw_response_sha256": sha256_bytes(cached.response_bytes),
                "candidate_sha256": sha256_bytes(cached.candidate_bytes),
            }
            base = manifest_base(
                target_id,
                slice_id,
                resolved_model,
                agent,
                variant,
                context_path,
                prompt_path,
                response_path,
                provider_invocations=0,
                provider_preflight=provider_preflight,
                cache_evidence=cache_evidence,
            )
            candidate = candidate_record(
                cached.parsed,
                context_pack=context_pack,
                resolved_model=resolved_model,
                context_path=context_path,
                prompt_path=prompt_path,
                candidate_path=candidate_path,
            )
            manifest = {**base, "status": "generated", "candidates": [candidate]}
            atomic_write_json(manifest_path, manifest)
            return manifest
        cache_evidence = {
            "status": "miss",
            "key_sha256": cache_key,
            "miss_reason": cache_reason,
            "stored": False,
        }
        if not _cache_generation_lock_held:
            try:
                with candidate_generation_lock(
                    cache_root,
                    cache_payload,
                    timeout_seconds=timeout_seconds + 30,
                ):
                    return generate_candidate(
                        context_pack,
                        out_dir=out_dir,
                        opencode_command=opencode_command,
                        resolved_model=resolved_model,
                        agent=agent,
                        variant=variant,
                        timeout_seconds=timeout_seconds,
                        runner=runner,
                        cache_root=cache_root,
                        _cache_generation_lock_held=True,
                    )
            except TimeoutError:
                return generate_candidate(
                    context_pack,
                    out_dir=out_dir,
                    opencode_command=opencode_command,
                    resolved_model=resolved_model,
                    agent=agent,
                    variant=variant,
                    timeout_seconds=timeout_seconds,
                    runner=runner,
                    cache_root=None,
                    _cache_generation_lock_held=True,
                )
    argv = [
        *provider_command_prefix(opencode_command),
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
        *prompt_file_arguments(prompt_path),
    ]
    execution = (runner or subprocess_runner)(argv, timeout_seconds)
    response_bytes = execution.stdout.encode("utf-8")
    atomic_write_bytes(response_path, response_bytes[:MAX_PROVIDER_STDOUT_BYTES])
    persisted_response = response_path.read_text(encoding="utf-8", errors="replace")
    write_invocation_receipt(
        execution,
        resolved_model=resolved_model,
        agent=agent,
        variant=variant,
        persisted_response=persisted_response,
        prompt_path=prompt_path,
        response_path=response_path,
        receipt_path=invocation_receipt_path,
        session_identity_path=session_identity_path,
    )

    base = manifest_base(
        target_id,
        slice_id,
        resolved_model,
        agent,
        variant,
        context_path,
        prompt_path,
        response_path,
        provider_invocations=1,
        provider_preflight=provider_preflight,
        cache_evidence=cache_evidence,
    )
    base["bindings"]["invocation_receipt"] = {
        "path": invocation_receipt_path.name,
        "sha256": sha256_path(invocation_receipt_path),
    }
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
    if cache_root is not None and cache_payload is not None:
        stored = store_candidate_cache(
            cache_root,
            cache_payload,
            response_bytes,
            candidate_source.encode("utf-8"),
            parse_candidate_response,
        )
        cache_evidence["stored"] = stored
        if not stored:
            cache_evidence["miss_reason"] = "store_failed"
        base["cache"] = cache_evidence
    candidate = candidate_record(
        parsed,
        context_pack=context_pack,
        resolved_model=resolved_model,
        context_path=context_path,
        prompt_path=prompt_path,
        candidate_path=candidate_path,
    )
    manifest = {**base, "status": "generated", "candidates": [candidate]}
    atomic_write_json(manifest_path, manifest)
    return manifest


def candidate_record(
    parsed: dict[str, Any],
    *,
    context_pack: dict[str, Any],
    resolved_model: str,
    context_path: Path,
    prompt_path: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    identity = resolve_model_identity(resolved_model)
    return {
        "candidate_id": identity.candidate_id,
        "purpose": "rust_draft",
        "kind": "opencode-ai",
        "provider_label": identity.provider_label,
        "model_label": identity.logical_model,
        "resolved_model": resolved_model,
        "competition_eligible": identity.competition_eligible,
        "evaluation_scope": identity.evaluation_scope,
        "prompt_scope": prompt_scope_for_context(context_pack),
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


def provider_command_prefix(command: str) -> list[str]:
    if not isinstance(command, str) or not command.strip():
        raise ValueError("OpenCode command must be non-empty")
    direct = Path(command)
    if direct.is_file():
        return [command]
    tokens = shlex.split(command, posix=os.name != "nt")
    normalized = [strip_matching_quotes(token) for token in tokens]
    if not normalized or any(not token for token in normalized):
        raise ValueError("OpenCode command could not be parsed")
    return normalized


def strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


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


def manifest_base(
    target_id: str,
    slice_id: str,
    resolved_model: str,
    agent: str,
    variant: str,
    context_path: Path,
    prompt_path: Path,
    response_path: Path,
    *,
    provider_invocations: int,
    provider_preflight: dict[str, str],
    cache_evidence: dict[str, Any],
) -> dict[str, Any]:
    identity = resolve_model_identity(resolved_model)
    return {
        "schema_version": 8,
        "target_id": target_id,
        "slice_id": slice_id,
        "ai_required_for_default_pipeline": True,
        "provider_invocations": provider_invocations,
        "provider_preflight": provider_preflight,
        "cache": cache_evidence,
        "generator": {
            "tool": "opencode",
            "provider": identity.provider_label,
            "logical_model": identity.logical_model,
            "resolved_model": resolved_model,
            "competition_eligible": identity.competition_eligible,
            "evaluation_scope": identity.evaluation_scope,
            "agent": agent,
            "variant": variant,
            "prompt_transport": prompt_transport_contract(),
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
            "competition_eligible": identity.competition_eligible,
        },
        "cache_invalidation_keys": [
            f"context_pack:{sha256_path(context_path)}",
            f"prompt:{sha256_path(prompt_path)}",
            f"raw_response:{sha256_path(response_path)}",
        ],
    }
