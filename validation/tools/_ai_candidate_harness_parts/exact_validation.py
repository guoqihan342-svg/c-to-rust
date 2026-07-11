from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import re
from typing import Any

from .context_security import (
    atomic_write_bytes,
    atomic_write_json,
    canonical_json_bytes,
    redact_metadata_text,
    sensitive_key,
    sha256_bytes,
    sha256_path,
)


MAX_INPUT_BYTES = 512_000
MAX_JSON_BYTES = 64_000
MAX_UNSAFE_TOKENS = 128
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
UNSAFE_RE = re.compile(r"\bunsafe\b")
POINTER_RE = re.compile(
    r"\*\s*(?:const|mut)\b|\b(?:core|std)::ptr\b|"
    r"\b(?:addr_of|addr_of_mut)!|\b(?:as_ptr|as_mut_ptr|from_raw|into_raw)\b"
)
RAW_STRING_RE = re.compile(r'(?:br|r)(?P<hashes>#{0,255})"')
CHAR_LITERAL_RE = re.compile(r"'(?:\\(?:u\{[0-9a-fA-F_]+\}|x[0-9a-fA-F]{2}|.)|[^\\'\n])'")
GATES = (
    "rustc",
    "generated_replay",
    "schema_diff",
    "negative_mutation",
    "unsafe_scan",
    "unsafe_ledger",
    "alias_contract",
    "abi_contract",
    "oracle_contract",
    "final_verification",
)
Runner = Callable[..., Mapping[str, Any]]


def validate_exact_candidate(
    candidate_path: Path,
    *,
    candidate_sha256: str,
    generated_replay_test: Path,
    fresh_oracle_proof: Mapping[str, Any],
    unsafe_policy: Mapping[str, Any],
    unsafe_ledger: Mapping[str, Any],
    target_contract: Mapping[str, Any],
    attempt_dir: Path,
    compile_runner: Runner,
    replay_runner: Runner,
    alias_proof: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return ten exact, SHA-bound gate payloads for one frozen candidate.

    The injected runners execute only; this validator owns every acceptance
    decision. The returned mapping can be passed to extract_gate_failure_facts.
    """
    selected_sha = _sha(candidate_sha256, "candidate_sha256")
    candidate = _read(candidate_path, "candidate")
    replay_bytes = _read(generated_replay_test, "generated replay test")
    root = _new_dir(attempt_dir)
    frozen = root / "candidate.rs"
    replay_test = root / "generated-replay-test.rs"
    atomic_write_bytes(frozen, candidate)
    atomic_write_bytes(replay_test, replay_bytes)
    actual_sha = sha256_bytes(candidate)
    if actual_sha != selected_sha:
        return _persist(root, selected_sha, _binding_failures(selected_sha, actual_sha))

    target, target_sha, target_error = _target(target_contract)
    oracle, oracle_values = _oracle(
        fresh_oracle_proof, selected_sha, target_sha, target_error
    )
    rustc = _compile(
        compile_runner, frozen, root / "compile", selected_sha,
        target, target_sha, target_error,
    )
    replay = _replay(
        replay_runner, frozen, replay_test, root / "replay", selected_sha,
        target, target_sha, oracle_values.get("shared_fixture_identity"),
        oracle_values.get("shared_fixture_identity_sha256"),
        rustc["status"] == "passed",
    )
    schema_diff = _diff(selected_sha, oracle, oracle_values, replay)
    negative = _negative(
        replay_runner, frozen, replay_test, replay_bytes, root, selected_sha,
        target, target_sha, oracle_values.get("shared_fixture_identity"),
        oracle_values.get("shared_fixture_identity_sha256"),
        rustc["status"] == replay["status"] == "passed",
    )
    source = _mask_noncode(candidate.decode("utf-8"))
    scan, tokens, policy = _unsafe_scan(source, selected_sha, unsafe_policy)
    ledger = _ledger(selected_sha, unsafe_ledger, tokens, policy)
    alias = _alias(selected_sha, source, alias_proof, target_sha, target_error)
    abi = _abi(selected_sha, rustc, replay, oracle, target_sha, target_error)
    gates = {
        "rustc": rustc,
        "generated_replay": replay,
        "schema_diff": schema_diff,
        "negative_mutation": negative,
        "unsafe_scan": scan,
        "unsafe_ledger": ledger,
        "alias_contract": alias,
        "abi_contract": abi,
        "oracle_contract": oracle,
    }
    unchanged = sha256_path(frozen) == selected_sha
    accepted = unchanged and all(
        value.get("candidate_sha256") == selected_sha
        and value.get("status") == ("expected_failed" if key == "negative_mutation" else "passed")
        for key, value in gates.items()
    )
    reason = "candidate_sha_drift" if not unchanged else "required_gate_failed"
    gates["final_verification"] = _gate(
        selected_sha,
        "passed" if accepted else "failed",
        semantic_pass=accepted,
        required_gates=list(gates),
        failures=[] if accepted else [_fact(reason, "Exact validation did not accept this candidate.")],
    )
    return _persist(root, selected_sha, gates)


def _compile(
    runner: Runner, candidate: Path, work: Path, candidate_sha: str,
    target: dict[str, Any], target_sha: str | None, target_error: str | None,
) -> dict[str, Any]:
    if target_error:
        return _failed(candidate_sha, "invalid_target_contract", target_error)
    result = _run(runner, candidate_path=candidate, work_dir=_mkdir(work), target_contract=target)
    error = _execution_binding(result, candidate_sha, target_sha)
    if error is None and result.get("status") == "passed" and result.get("returncode") == 0:
        return _gate(candidate_sha, "passed", returncode=0, target_contract_sha256=target_sha)
    return _failed(
        candidate_sha, error or "compile_failed",
        "The exact candidate did not compile for the target contract.",
        returncode=_integer(result.get("returncode")), target_contract_sha256=target_sha,
    )


def _replay(
    runner: Runner, candidate: Path, replay_test: Path, work: Path,
    candidate_sha: str, target: dict[str, Any], target_sha: str | None,
    fixture_identity: Any, fixture_sha: Any, prerequisite: bool,
) -> dict[str, Any]:
    test_sha = sha256_path(replay_test)
    if not prerequisite:
        return _failed(candidate_sha, "rustc_prerequisite_failed", "Replay requires rustc success.")
    result = _run(
        runner, candidate_path=candidate, replay_test_path=replay_test,
        work_dir=_mkdir(work), target_contract=target,
        shared_fixture_identity=fixture_identity, mode="positive",
    )
    error = _replay_binding(result, candidate_sha, test_sha, target_sha, fixture_sha)
    try:
        outputs = _observables(result)
    except ValueError:
        outputs, error = None, error or "invalid_observable_outputs"
    passed = (
        error is None and result.get("status") == "passed"
        and result.get("phase") == "run" and result.get("returncode") == 0
        and outputs is not None
    )
    execution = {
        "status": "passed" if passed else "failed",
        "phase": _phase(result.get("phase")),
        "returncode": _integer(result.get("returncode")),
    }
    base = {
        "generated_draft_replay_pass": passed,
        "replay_execution": execution,
        "replay_test_sha256": test_sha,
    }
    if not passed:
        return _failed(
            candidate_sha, error or "replay_failed",
            "The exact candidate replay did not run successfully.", **base,
        )
    output_sha = sha256_bytes(canonical_json_bytes(outputs))
    if result.get("observable_outputs_sha256") != output_sha:
        return _failed(
            candidate_sha, "observable_output_sha256_mismatch",
            "Replay output hash does not bind its observables.", **base,
        )
    return _gate(
        candidate_sha, "passed", **base,
        shared_fixture_identity_sha256=fixture_sha,
        observable_outputs=outputs, observable_outputs_sha256=output_sha,
        target_contract_sha256=target_sha,
    )


def _oracle(
    proof: Mapping[str, Any], candidate_sha: str,
    target_sha: str | None, target_error: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if target_error:
        return _failed(candidate_sha, "invalid_target_contract", target_error), {}
    if not isinstance(proof, Mapping) or _forbidden_oracle_reference(proof):
        return _failed(candidate_sha, "fresh_oracle_required", "Historical oracle reports are forbidden."), {}
    try:
        identity = _safe_json(proof["shared_fixture_identity"])
        outputs = _observables(proof)
    except (KeyError, ValueError):
        return _failed(candidate_sha, "fresh_oracle_invalid", "Fresh oracle payload is invalid."), {}
    fixture_sha = sha256_bytes(canonical_json_bytes(identity))
    output_sha = sha256_bytes(canonical_json_bytes(outputs))
    valid = (
        proof.get("schema_version") == 1 and proof.get("status") == "passed"
        and _valid_sha(proof.get("oracle_run_sha256"))
        and proof.get("target_contract_sha256") == target_sha
    )
    if not valid:
        return _failed(candidate_sha, "fresh_oracle_invalid", "Fresh oracle bindings are invalid."), {}
    values = {
        "shared_fixture_identity": identity,
        "shared_fixture_identity_sha256": fixture_sha,
        "observable_outputs": outputs,
        "observable_outputs_sha256": output_sha,
    }
    return _gate(
        candidate_sha, "passed", fresh=True, provenance="fresh_run",
        oracle_run_sha256=proof["oracle_run_sha256"],
        shared_fixture_identity=identity,
        shared_fixture_identity_sha256=fixture_sha,
        observable_outputs=outputs, observable_outputs_sha256=output_sha,
        target_contract_sha256=target_sha,
    ), values


def _diff(
    candidate_sha: str, oracle: Mapping[str, Any], oracle_values: Mapping[str, Any],
    replay: Mapping[str, Any],
) -> dict[str, Any]:
    if oracle.get("status") != "passed" or replay.get("status") != "passed":
        return _failed(candidate_sha, "comparison_prerequisite_failed", "Oracle and replay must pass.")
    mismatch = _first_mismatch(oracle_values["observable_outputs"], replay["observable_outputs"])
    fixture_match = (
        oracle_values["shared_fixture_identity_sha256"]
        == replay.get("shared_fixture_identity_sha256")
    )
    if mismatch is None and fixture_match:
        return _gate(
            candidate_sha, "passed", first_mismatch=None,
            shared_fixture_identity_sha256=oracle_values["shared_fixture_identity_sha256"],
            oracle_observable_outputs_sha256=oracle_values["observable_outputs_sha256"],
            replay_observable_outputs_sha256=replay["observable_outputs_sha256"],
        )
    first = mismatch or {
        "path": "$fixture", "expected": oracle_values["shared_fixture_identity_sha256"],
        "actual": replay.get("shared_fixture_identity_sha256"),
    }
    return _failed(
        candidate_sha, "value_mismatch" if mismatch else "fixture_mismatch",
        "C oracle and Rust replay differ.", first_mismatch=first,
    )


def _negative(
    runner: Runner, candidate: Path, original: Path, test_bytes: bytes, root: Path,
    candidate_sha: str, target: dict[str, Any], target_sha: str | None,
    fixture_identity: Any, fixture_sha: Any, prerequisite: bool,
) -> dict[str, Any]:
    mutated, count = re.subn(r"\bassert_eq\s*!", "assert_ne!", test_bytes.decode("utf-8"), count=1)
    if count != 1:
        return _failed(candidate_sha, "mutation_not_applicable", "Replay has no key assert_eq!.")
    mutated_path = root / "negative-replay-test.rs"
    atomic_write_bytes(mutated_path, mutated.encode("utf-8"))
    if not prerequisite:
        return _failed(candidate_sha, "replay_prerequisite_failed", "Negative replay requires a passing replay.")
    result = _run(
        runner, candidate_path=candidate, replay_test_path=mutated_path,
        work_dir=_mkdir(root / "negative-replay"), target_contract=target,
        shared_fixture_identity=fixture_identity, mode="negative",
    )
    mutated_sha = sha256_path(mutated_path)
    error = _replay_binding(result, candidate_sha, mutated_sha, target_sha, fixture_sha)
    detected = (
        error is None and result.get("status") == "failed" and result.get("phase") == "run"
        and isinstance(result.get("returncode"), int) and result.get("returncode") != 0
    )
    fields = {
        "mutation_detected": detected,
        "original_replay_test_sha256": sha256_path(original),
        "mutated_replay_test_sha256": mutated_sha,
        "replay_execution": {
            "status": "expected_failed" if detected else "failed",
            "phase": _phase(result.get("phase")),
            "returncode": _integer(result.get("returncode")),
        },
    }
    if detected:
        return _gate(candidate_sha, "expected_failed", **fields)
    kind = error or ("mutation_compile_failed" if result.get("phase") == "compile" else "mutation_survived")
    return _failed(candidate_sha, kind, "The negative mutation was not detected.", **fields)


def _unsafe_scan(
    source: str, candidate_sha: str, policy_input: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, int]], dict[str, Any] | None]:
    matches = list(UNSAFE_RE.finditer(source))
    tokens = [
        {"ordinal": index, "line": source.count("\n", 0, match.start()) + 1}
        for index, match in enumerate(matches, 1)
    ]
    policy = dict(policy_input) if isinstance(policy_input, Mapping) else {}
    maximum = policy.get("max_unsafe_tokens")
    valid = (
        policy.get("schema_version") == 1 and policy.get("require_ledger") is True
        and isinstance(maximum, int) and not isinstance(maximum, bool)
        and 0 <= maximum <= MAX_UNSAFE_TOKENS
    )
    if not valid:
        return _failed(candidate_sha, "unsafe_policy_invalid", "Unsafe policy is invalid."), tokens, None
    fields = {
        "unsafe_token_count": len(tokens), "unsafe_locations": tokens,
        "policy_sha256": sha256_bytes(canonical_json_bytes(policy)),
    }
    if len(tokens) > maximum:
        return _failed(candidate_sha, "unsafe_budget_exceeded", "Unsafe budget exceeded.", **fields), tokens, policy
    return _gate(candidate_sha, "passed", **fields), tokens, policy


def _ledger(
    candidate_sha: str, ledger: Mapping[str, Any],
    observed: list[dict[str, int]], policy: dict[str, Any] | None,
) -> dict[str, Any]:
    entries = ledger.get("entries") if isinstance(ledger, Mapping) else None
    valid = (
        policy is not None and isinstance(ledger, Mapping)
        and ledger.get("schema_version") == 1 and ledger.get("status") == "passed"
        and ledger.get("provenance") == "current_candidate"
        and ledger.get("candidate_sha256") == candidate_sha and isinstance(entries, list)
    )
    if not valid:
        return _failed(candidate_sha, "unsafe_ledger_invalid", "Current-candidate ledger is required.")
    normalized = []
    for entry in entries:
        if (
            not isinstance(entry, Mapping) or not isinstance(entry.get("justification"), str)
            or not entry["justification"].strip()
        ):
            return _failed(candidate_sha, "unsafe_entry_invalid", "Unsafe entries need justification.")
        normalized.append({"ordinal": entry.get("ordinal"), "line": entry.get("line")})
    if normalized != observed:
        return _failed(candidate_sha, "unregistered_unsafe", "Ledger does not match unsafe tokens.")
    return _gate(
        candidate_sha, "passed", entry_count=len(entries),
        ledger_sha256=sha256_bytes(canonical_json_bytes(dict(ledger))),
    )


def _alias(
    candidate_sha: str, source: str, proof: Mapping[str, Any] | None,
    target_sha: str | None, target_error: str | None,
) -> dict[str, Any]:
    count = len(POINTER_RE.findall(source))
    if target_error:
        return _failed(candidate_sha, "invalid_target_contract", target_error)
    if count == 0:
        return _gate(candidate_sha, "passed", required=False, raw_pointer_token_count=0)
    conditions = proof.get("conditions") if isinstance(proof, Mapping) else None
    valid = (
        isinstance(proof, Mapping) and proof.get("schema_version") == 1
        and proof.get("status") == "passed" and proof.get("provenance") == "current_candidate"
        and proof.get("candidate_sha256") == candidate_sha
        and proof.get("target_contract_sha256") == target_sha
        and isinstance(conditions, list) and bool(conditions)
        and all(isinstance(item, str) and item.strip() for item in conditions)
    )
    if not valid:
        return _failed(candidate_sha, "alias_proof_missing", "Raw pointers require an exact alias proof.")
    return _gate(
        candidate_sha, "passed", required=True, raw_pointer_token_count=count,
        alias_proof_sha256=sha256_bytes(canonical_json_bytes(dict(proof))),
    )


def _abi(
    candidate_sha: str, rustc: Mapping[str, Any], replay: Mapping[str, Any],
    oracle: Mapping[str, Any], target_sha: str | None, target_error: str | None,
) -> dict[str, Any]:
    passed = (
        target_error is None
        and all(item.get("status") == "passed" for item in (rustc, replay, oracle))
        and all(item.get("target_contract_sha256") == target_sha for item in (rustc, replay, oracle))
    )
    if not passed:
        return _failed(candidate_sha, "abi_target_binding_failed", "ABI target bindings are incomplete.")
    return _gate(
        candidate_sha, "passed", target_contract_sha256=target_sha,
        replay_compile_proven=True,
    )


def _target(value: Mapping[str, Any]) -> tuple[dict[str, Any], str | None, str | None]:
    target = dict(value) if isinstance(value, Mapping) else {}
    valid = (
        target.get("schema_version") == 1
        and isinstance(target.get("target_triple"), str) and bool(target["target_triple"].strip())
        and target.get("pointer_width") in {16, 32, 64, 128}
        and target.get("endianness") in {"little", "big"}
        and isinstance(target.get("calling_convention"), str)
        and bool(target["calling_convention"].strip())
    )
    try:
        target = _safe_json(target) if valid else {}
    except ValueError:
        valid = False
    if not valid:
        return {}, None, "Target contract requires explicit ABI fields and bounded safe JSON."
    return target, sha256_bytes(canonical_json_bytes(target)), None


def _execution_binding(result: Mapping[str, Any], candidate_sha: str, target_sha: Any) -> str | None:
    if result.get("candidate_sha256") != candidate_sha:
        return "candidate_sha256_mismatch"
    if result.get("target_contract_sha256") != target_sha:
        return "target_contract_sha256_mismatch"
    return None


def _replay_binding(
    result: Mapping[str, Any], candidate_sha: str, test_sha: str,
    target_sha: Any, fixture_sha: Any,
) -> str | None:
    return (
        _execution_binding(result, candidate_sha, target_sha)
        or ("replay_test_sha256_mismatch" if result.get("replay_test_sha256") != test_sha else None)
        or (
            "shared_fixture_identity_sha256_mismatch"
            if result.get("shared_fixture_identity_sha256") != fixture_sha else None
        )
    )


def _run(runner: Runner, **kwargs: Any) -> Mapping[str, Any]:
    try:
        result = runner(**kwargs)
    except Exception:
        return {"status": "failed", "runner_error": True}
    return result if isinstance(result, Mapping) else {"status": "failed", "malformed": True}


def _observables(payload: Mapping[str, Any]) -> Any:
    if "observable_outputs" not in payload:
        raise ValueError("missing observable outputs")
    return _safe_json(payload["observable_outputs"])


def _safe_json(value: Any) -> Any:
    def visit(item: Any) -> Any:
        if item is None or isinstance(item, (bool, int)):
            return item
        if isinstance(item, float):
            if item != item or item in {float("inf"), float("-inf")}:
                raise ValueError("non-finite number")
            return item
        if isinstance(item, str):
            if redact_metadata_text(item) != item:
                raise ValueError("host-specific or sensitive text")
            return item
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, Mapping):
            output = {}
            for key, child in item.items():
                if not isinstance(key, str) or sensitive_key(key):
                    raise ValueError("unsafe key")
                output[key] = visit(child)
            return output
        raise ValueError("non-JSON value")

    safe = visit(value)
    if len(canonical_json_bytes(safe)) > MAX_JSON_BYTES:
        raise ValueError("JSON payload exceeds limit")
    return safe


def _first_mismatch(expected: Any, actual: Any, path: str = "$") -> dict[str, Any] | None:
    if type(expected) is not type(actual):
        return {"path": path, "expected": expected, "actual": actual}
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            return {"path": path, "expected_keys": sorted(expected), "actual_keys": sorted(actual)}
        for key in sorted(expected):
            found = _first_mismatch(expected[key], actual[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return {"path": path, "expected_length": len(expected), "actual_length": len(actual)}
        for index, (left, right) in enumerate(zip(expected, actual)):
            found = _first_mismatch(left, right, f"{path}[{index}]")
            if found:
                return found
        return None
    return None if expected == actual else {"path": path, "expected": expected, "actual": actual}


def _mask_noncode(data: str) -> str:
    # Preserve newlines so token locations remain stable; nested comments are bounded by input size.
    chars, index, state, depth, quote = list(data), 0, "code", 0, ""
    while index < len(chars):
        pair = data[index:index + 2]
        raw = RAW_STRING_RE.match(data, index) if state == "code" else None
        if raw:
            delimiter = '"' + raw.group("hashes")
            end = data.find(delimiter, raw.end())
            stop = len(chars) if end < 0 else end + len(delimiter)
            for position in range(index, stop):
                if chars[position] != "\n":
                    chars[position] = " "
            index = stop
            continue
        if state == "code" and pair == "//":
            state = "line"
        elif state == "code" and pair == "/*":
            state, depth = "block", 1
        elif state == "block" and pair == "/*":
            depth += 1
        elif state == "block" and pair == "*/":
            chars[index:index + 2] = [" ", " "]
            depth -= 1
            state = "code" if depth == 0 else "block"
            index += 2
            continue
        elif state == "code" and data[index] == '"':
            state, quote = "quote", data[index]
        elif state == "code" and data[index] == "'" and CHAR_LITERAL_RE.match(data, index):
            state, quote = "quote", data[index]
        elif state == "quote" and data[index] == "\\":
            chars[index] = " "
            if index + 1 < len(chars) and chars[index + 1] != "\n":
                chars[index + 1] = " "
            index += 2
            continue
        elif state == "quote" and data[index] == quote:
            chars[index], state = " ", "code"
            index += 1
            continue
        if state != "code" and chars[index] != "\n":
            chars[index] = " "
        if state == "line" and data[index] == "\n":
            state = "code"
        index += 1
    return "".join(chars)


def _persist(
    root: Path, candidate_sha: str, gates: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    for index, name in enumerate(GATES, 1):
        atomic_write_json(root / f"{index:02d}-{name}.json", gates[name])
    atomic_write_json(root / "gate-index.json", {
        "schema_version": 1,
        "candidate_sha256": candidate_sha,
        "gates": {
            name: {
                "path": f"{index:02d}-{name}.json",
                "sha256": sha256_path(root / f"{index:02d}-{name}.json"),
            }
            for index, name in enumerate(GATES, 1)
        },
    })
    return gates


def _binding_failures(candidate_sha: str, actual_sha: str) -> dict[str, dict[str, Any]]:
    gates = {
        name: _failed(
            candidate_sha, "candidate_sha256_mismatch",
            "Candidate bytes do not match the selected SHA-256.",
            expected=candidate_sha, actual=actual_sha,
        )
        for name in GATES
    }
    gates["final_verification"]["semantic_pass"] = False
    return gates


def _gate(
    candidate_sha: str, status: str, *, failures: list[dict[str, Any]] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    payload = {"candidate_sha256": candidate_sha, "status": status, **fields}
    if failures:
        payload["failures"] = failures
    return payload


def _failed(candidate_sha: str, kind: str, message: str, **fields: Any) -> dict[str, Any]:
    return _gate(candidate_sha, "failed", failures=[_fact(kind, message)], **fields)


def _fact(kind: str, message: str) -> dict[str, str]:
    return {"kind": kind, "message": message}


def _new_dir(path: Path) -> Path:
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError("attempt_dir must be a new independent directory")
    resolved = path.resolve()
    if resolved == Path(resolved.anchor):
        raise ValueError("attempt_dir cannot be a filesystem root")
    resolved.mkdir(parents=True, exist_ok=False)
    return resolved


def _read(path: Path, label: str) -> bytes:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    data = path.read_bytes()
    if not data or len(data) > MAX_INPUT_BYTES or b"\0" in data:
        raise ValueError(f"{label} must be non-empty, NUL-free, and bounded")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{label} must be UTF-8") from error
    return data


def _mkdir(path: Path) -> Path:
    path.mkdir(exist_ok=False)
    return path


def _sha(value: str, label: str) -> str:
    normalized = str(value).lower()
    if not SHA_RE.fullmatch(normalized):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return normalized


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _phase(value: Any) -> str:
    return value if value in {"compile", "run"} else "unknown"


def _forbidden_oracle_reference(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            lowered = str(key).lower()
            if (
                lowered in {"path", "report", "artifact_ref", "report_ref"}
                or lowered.endswith(("_path", "_report", "_ref"))
                or "accepted" in lowered or "historical" in lowered
                or _forbidden_oracle_reference(child)
            ):
                return True
    elif isinstance(value, list):
        return any(_forbidden_oracle_reference(child) for child in value)
    elif isinstance(value, str):
        normalized = value.replace("\\", "/").lower()
        return "validation/evidence/" in normalized or "/accepted/" in normalized
    return False
