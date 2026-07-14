from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .candidate_cache import (
    agent_definition_sha256,
    candidate_generation_lock,
    store_candidate_cache,
)
from .context import atomic_write_bytes, atomic_write_json, sha256_bytes, sha256_path
from .context_replay import materialize_replay_api_contract
from .model_identity import DEFAULT_RESOLVED_MODEL
from .prompt_transport import prompt_file_arguments
from .provider_command import provider_command_prefix
from .provider_generation_cache import load_cached_candidate
from .provider_manifest import CandidateArtifactPaths, candidate_record, manifest_base
from .provider_readiness import evaluate_provider_readiness
from .provider_response import parse_candidate_response, render_prompt
from .provider_retry import run_with_empty_completion_retry
from .provider_runtime import ProviderExecution, classify_provider_failure, subprocess_runner


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
    paths = CandidateArtifactPaths.for_slice(out_dir, slice_id)

    replay_materialization_error = False
    try:
        materialize_replay_api_contract(context_pack, out_dir)
    except ValueError:
        replay_materialization_error = True
    atomic_write_json(paths.context, context_pack)
    prompt = render_prompt(context_pack)
    atomic_write_bytes(paths.prompt, prompt.encode("utf-8"))
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
        atomic_write_bytes(paths.response, b"")
        base = manifest_base(
            target_id,
            slice_id,
            resolved_model,
            agent,
            variant,
            paths.context,
            paths.prompt,
            paths.response,
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
        atomic_write_json(paths.manifest, manifest)
        return manifest

    agent_definition_sha = agent_definition_sha256(
        agent,
        Path(__file__).resolve().parents[3],
    )
    cache_payload = None
    cache_evidence: dict[str, Any] = {"status": "disabled"}
    if cache_root is not None:
        cached_manifest, cache_payload, cache_evidence = load_cached_candidate(
            cache_root,
            context_pack,
            paths,
            target_id=target_id,
            slice_id=slice_id,
            resolved_model=resolved_model,
            agent=agent,
            agent_definition_sha256=agent_definition_sha,
            variant=variant,
            provider_preflight=provider_preflight,
        )
        if cached_manifest is not None:
            return cached_manifest
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
        *prompt_file_arguments(paths.prompt),
    ]
    retry_result = run_with_empty_completion_retry(
        argv,
        timeout_seconds,
        runner or subprocess_runner,
        resolved_model=resolved_model,
        agent=agent,
        variant=variant,
        prompt_path=paths.prompt,
        response_path=paths.response,
        receipt_path=paths.invocation_receipt,
        session_identity_path=paths.session_identity,
    )
    final_attempt = retry_result.final_attempt
    execution = final_attempt.execution
    response_bytes = execution.stdout.encode("utf-8")

    base = manifest_base(
        target_id,
        slice_id,
        resolved_model,
        agent,
        variant,
        paths.context,
        paths.prompt,
        final_attempt.response_path,
        provider_invocations=retry_result.provider_invocations,
        provider_preflight=provider_preflight,
        cache_evidence=cache_evidence,
    )
    base["provider_attempts"] = retry_result.attempt_bindings()
    base["bindings"]["invocation_receipt"] = {
        "path": final_attempt.receipt_path.name,
        "sha256": sha256_path(final_attempt.receipt_path),
    }
    failure = classify_provider_failure(execution)
    if failure is not None:
        retry_record = retry_result.retry_record(result="blocked")
        if retry_record is not None:
            base["provider_retry"] = retry_record
        manifest = {
            **base,
            "status": "blocked",
            "candidates": [],
            "failure": failure,
        }
        atomic_write_json(paths.manifest, manifest)
        return manifest

    try:
        parsed = parse_candidate_response(execution.stdout)
    except ValueError as error:
        retry_record = retry_result.retry_record(result="blocked")
        if retry_record is not None:
            base["provider_retry"] = retry_record
        manifest = {
            **base,
            "status": "blocked",
            "candidates": [],
            "failure": {"kind": "invalid_ai_response", "message": str(error)},
        }
        atomic_write_json(paths.manifest, manifest)
        return manifest

    candidate_source = parsed["candidate"]["source"]
    atomic_write_bytes(paths.candidate, candidate_source.encode("utf-8"))
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
        context_path=paths.context,
        prompt_path=paths.prompt,
        candidate_path=paths.candidate,
    )
    retry_record = retry_result.retry_record(result="generated")
    if retry_record is not None:
        base["provider_retry"] = retry_record
    manifest = {**base, "status": "generated", "candidates": [candidate]}
    atomic_write_json(paths.manifest, manifest)
    return manifest


__all__ = ["DEFAULT_AGENT", "DEFAULT_VARIANT", "Runner", "generate_candidate"]
