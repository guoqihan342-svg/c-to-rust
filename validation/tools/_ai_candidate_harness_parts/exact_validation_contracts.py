from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .context_security import canonical_json_bytes, sha256_bytes
from .exact_validation_artifacts import failed, gate, safe_json


MAX_UNSAFE_TOKENS = 128
UNSAFE_RE = re.compile(r"\bunsafe\b")
POINTER_RE = re.compile(
    r"\*\s*(?:const|mut)\b|\b(?:core|std)::ptr\b|"
    r"\b(?:addr_of|addr_of_mut)!|\b(?:as_ptr|as_mut_ptr|from_raw|into_raw)\b"
)
RAW_STRING_RE = re.compile(r'(?:br|r)(?P<hashes>#{0,255})"')
CHAR_LITERAL_RE = re.compile(
    r"'(?:\\(?:u\{[0-9a-fA-F_]+\}|x[0-9a-fA-F]{2}|.)|[^\\'\n])'"
)


def unsafe_scan_gate(
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
        policy.get("schema_version") == 1
        and policy.get("require_ledger") is True
        and isinstance(maximum, int)
        and not isinstance(maximum, bool)
        and 0 <= maximum <= MAX_UNSAFE_TOKENS
    )
    if not valid:
        return (
            failed(
                candidate_sha,
                "unsafe_policy_invalid",
                "Unsafe policy is invalid.",
            ),
            tokens,
            None,
        )
    fields = {
        "unsafe_token_count": len(tokens),
        "unsafe_locations": tokens,
        "policy_sha256": sha256_bytes(canonical_json_bytes(policy)),
    }
    if len(tokens) > maximum:
        return (
            failed(
                candidate_sha,
                "unsafe_budget_exceeded",
                "Unsafe budget exceeded.",
                **fields,
            ),
            tokens,
            policy,
        )
    return gate(candidate_sha, "passed", **fields), tokens, policy


def unsafe_ledger_gate(
    candidate_sha: str,
    ledger: Mapping[str, Any],
    observed: list[dict[str, int]],
    policy: dict[str, Any] | None,
) -> dict[str, Any]:
    entries = ledger.get("entries") if isinstance(ledger, Mapping) else None
    valid = (
        policy is not None
        and isinstance(ledger, Mapping)
        and ledger.get("schema_version") == 1
        and ledger.get("status") == "passed"
        and ledger.get("provenance") == "current_candidate"
        and ledger.get("candidate_sha256") == candidate_sha
        and isinstance(entries, list)
    )
    if not valid:
        return failed(
            candidate_sha,
            "unsafe_ledger_invalid",
            "Current-candidate ledger is required.",
        )
    normalized = []
    for entry in entries:
        if (
            not isinstance(entry, Mapping)
            or not isinstance(entry.get("justification"), str)
            or not entry["justification"].strip()
        ):
            return failed(
                candidate_sha,
                "unsafe_entry_invalid",
                "Unsafe entries need justification.",
            )
        normalized.append({"ordinal": entry.get("ordinal"), "line": entry.get("line")})
    if normalized != observed:
        return failed(
            candidate_sha,
            "unregistered_unsafe",
            "Ledger does not match unsafe tokens.",
        )
    return gate(
        candidate_sha,
        "passed",
        entry_count=len(entries),
        ledger_sha256=sha256_bytes(canonical_json_bytes(dict(ledger))),
    )


def alias_gate(
    candidate_sha: str,
    source: str,
    proof: Mapping[str, Any] | None,
    target_sha: str | None,
    target_error: str | None,
) -> dict[str, Any]:
    count = len(POINTER_RE.findall(source))
    if target_error:
        return failed(candidate_sha, "invalid_target_contract", target_error)
    if count == 0:
        return gate(
            candidate_sha,
            "passed",
            required=False,
            raw_pointer_token_count=0,
        )
    conditions = proof.get("conditions") if isinstance(proof, Mapping) else None
    valid = (
        isinstance(proof, Mapping)
        and proof.get("schema_version") == 1
        and proof.get("status") == "passed"
        and proof.get("provenance") == "current_candidate"
        and proof.get("candidate_sha256") == candidate_sha
        and proof.get("target_contract_sha256") == target_sha
        and isinstance(conditions, list)
        and bool(conditions)
        and all(isinstance(item, str) and item.strip() for item in conditions)
    )
    if not valid:
        return failed(
            candidate_sha,
            "alias_proof_missing",
            "Raw pointers require an exact alias proof.",
        )
    return gate(
        candidate_sha,
        "passed",
        required=True,
        raw_pointer_token_count=count,
        alias_proof_sha256=sha256_bytes(canonical_json_bytes(dict(proof))),
    )


def abi_gate(
    candidate_sha: str,
    rustc: Mapping[str, Any],
    replay: Mapping[str, Any],
    oracle: Mapping[str, Any],
    target_sha: str | None,
    target_error: str | None,
) -> dict[str, Any]:
    passed = (
        target_error is None
        and all(item.get("status") == "passed" for item in (rustc, replay, oracle))
        and all(
            item.get("target_contract_sha256") == target_sha
            for item in (rustc, replay, oracle)
        )
    )
    if not passed:
        return failed(
            candidate_sha,
            "abi_target_binding_failed",
            "ABI target bindings are incomplete.",
        )
    return gate(
        candidate_sha,
        "passed",
        target_contract_sha256=target_sha,
        replay_compile_proven=True,
    )


def target_contract(
    value: Mapping[str, Any],
) -> tuple[dict[str, Any], str | None, str | None]:
    target = dict(value) if isinstance(value, Mapping) else {}
    valid = (
        target.get("schema_version") == 1
        and isinstance(target.get("target_triple"), str)
        and bool(target["target_triple"].strip())
        and target.get("pointer_width") in {16, 32, 64, 128}
        and target.get("endianness") in {"little", "big"}
        and isinstance(target.get("calling_convention"), str)
        and bool(target["calling_convention"].strip())
    )
    try:
        target = safe_json(target) if valid else {}
    except ValueError:
        valid = False
    if not valid:
        return (
            {},
            None,
            "Target contract requires explicit ABI fields and bounded safe JSON.",
        )
    return target, sha256_bytes(canonical_json_bytes(target)), None


def mask_noncode(data: str) -> str:
    # Preserve newlines so token locations remain stable; nested comments are bounded by input size.
    chars, index, state, depth, quote = list(data), 0, "code", 0, ""
    while index < len(chars):
        pair = data[index : index + 2]
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
            chars[index : index + 2] = [" ", " "]
            depth -= 1
            state = "code" if depth == 0 else "block"
            index += 2
            continue
        elif state == "code" and data[index] == '"':
            state, quote = "quote", data[index]
        elif (
            state == "code"
            and data[index] == "'"
            and CHAR_LITERAL_RE.match(data, index)
        ):
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
