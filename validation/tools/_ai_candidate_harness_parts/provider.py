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
from .provider_command import provider_command_prefix, strip_matching_quotes
from .provider_generation import generate_candidate
from .provider_manifest import apply_generated_candidate, candidate_record, manifest_base
from .provider_readiness import evaluate_provider_readiness
from .provider_retry import run_with_empty_completion_retry
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
