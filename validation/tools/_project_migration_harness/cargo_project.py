from __future__ import annotations

from dataclasses import dataclass
import hashlib
import heapq
import json
import re
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
LAST_GOOD_MANIFEST = "migration-last-good.json"
MAX_SOURCE_BYTES = 256_000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RUST_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_RUST_KEYWORDS = {
    "Self", "as", "async", "await", "break", "const", "continue", "crate",
    "dyn", "else", "enum", "extern", "false", "fn", "for", "if", "impl",
    "in", "let", "loop", "match", "mod", "move", "mut", "pub", "ref",
    "return", "self", "static", "struct", "super", "trait", "true", "type",
    "unsafe", "use", "where", "while",
}


class ProjectInputError(ValueError):
    def __init__(self, code: str, stage: str, group_id: str | None = None):
        super().__init__(code)
        self.code = code
        self.stage = stage
        self.group_id = group_id


@dataclass(frozen=True)
class CandidateSource:
    group_id: str
    status: str
    source_path: str
    sha256: str
    source: bytes
    public_symbols: tuple[str, ...]
    required_symbols: tuple[str, ...]
    unsafe_count: int

    @property
    def module_name(self) -> str:
        return f"unit_{self.sha256}"


@dataclass(frozen=True)
class CargoProjectPlan:
    files: Mapping[str, bytes]
    last_good_manifest: Mapping[str, Any]

    @property
    def accepted_group_ids(self) -> tuple[str, ...]:
        groups = self.last_good_manifest["accepted_groups"]
        return tuple(group["group_id"] for group in groups)


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _migration_dag(manifest: Mapping[str, Any]) -> tuple[dict[str, tuple[str, ...]], list[str]]:
    raw_dag = manifest.get("dag", manifest.get("migration_dag"))
    if not isinstance(raw_dag, Mapping) or not raw_dag:
        _fail("dag_invalid", "dag")
    dependencies: dict[str, tuple[str, ...]] = {}
    for raw_group, raw_dependencies in raw_dag.items():
        group_id = _group_id(raw_group)
        if not isinstance(raw_dependencies, list):
            _fail("dag_dependencies_invalid", "dag", group_id)
        values = tuple(_group_id(value) for value in raw_dependencies)
        if len(values) != len(set(values)):
            _fail("dag_dependency_duplicate", "dag", group_id)
        dependencies[group_id] = tuple(sorted(values))
    if any(item not in dependencies for values in dependencies.values() for item in values):
        _fail("dag_dependency_unknown", "dag")
    stable_order = _topological_order(dependencies)
    raw_order = manifest.get("dag_order", manifest.get("order"))
    if raw_order is None:
        return dependencies, stable_order
    if not isinstance(raw_order, list):
        _fail("dag_order_invalid", "dag")
    order = [_group_id(value) for value in raw_order]
    if len(order) != len(set(order)) or set(order) != set(dependencies):
        _fail("dag_order_invalid", "dag")
    positions = {group_id: index for index, group_id in enumerate(order)}
    if any(positions[parent] >= positions[group] for group, parents in dependencies.items() for parent in parents):
        _fail("dag_order_violation", "dag")
    return dependencies, order


def _topological_order(dependencies: Mapping[str, tuple[str, ...]]) -> list[str]:
    children = {group_id: [] for group_id in dependencies}
    indegree = {group_id: len(values) for group_id, values in dependencies.items()}
    for group_id, values in dependencies.items():
        for dependency in values:
            children[dependency].append(group_id)
    ready = [group_id for group_id, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        group_id = heapq.heappop(ready)
        order.append(group_id)
        for child in sorted(children[group_id]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(order) != len(dependencies):
        _fail("dag_cycle", "dag")
    return order


def _validate_candidates(
    candidates: Sequence[CandidateSource],
    dependencies: Mapping[str, tuple[str, ...]],
) -> None:
    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        _fail("candidate_descriptors_invalid", "candidate")
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, CandidateSource):
            _fail("candidate_descriptor_invalid", "candidate")
        group_id = _group_id(candidate.group_id)
        if group_id in seen or group_id not in dependencies:
            _fail("candidate_group_invalid", "candidate", group_id)
        seen.add(group_id)
        if candidate.status not in {"accepted", "blocked", "pending", "refused", "rejected"}:
            _fail("candidate_status_invalid", "candidate", group_id)
        if not isinstance(candidate.source, bytes) or not isinstance(candidate.sha256, str) or not _SHA256.fullmatch(candidate.sha256) or _digest(candidate.source) != candidate.sha256:
            _fail("candidate_hash_mismatch", "candidate", group_id)
        try:
            candidate.source.decode("utf-8")
        except UnicodeDecodeError:
            _fail("candidate_source_not_utf8", "candidate", group_id)
        if isinstance(candidate.unsafe_count, bool) or not isinstance(candidate.unsafe_count, int) or candidate.unsafe_count < 0:
            _fail("candidate_unsafe_count_invalid", "candidate", group_id)


def _validate_accepted(
    accepted: Mapping[str, CandidateSource],
    dependencies: Mapping[str, tuple[str, ...]],
    order: Sequence[str],
) -> None:
    providers: dict[str, str] = {}
    module_names: set[str] = set()
    for candidate in accepted.values():
        if candidate.module_name in module_names:
            _fail("candidate_module_conflict", "symbols", candidate.group_id)
        module_names.add(candidate.module_name)
        for symbol in candidate.public_symbols:
            if symbol in providers:
                _fail("symbol_provider_conflict", "symbols", candidate.group_id)
            providers[symbol] = candidate.group_id
    positions = {group_id: index for index, group_id in enumerate(order)}
    for group_id, candidate in accepted.items():
        if any(dependency not in accepted for dependency in dependencies[group_id]):
            _fail("accepted_dependency_missing", "dependencies", group_id)
        for symbol in candidate.required_symbols:
            provider = providers.get(symbol)
            if provider is None:
                _fail("required_symbol_missing", "dependencies", group_id)
            if provider != group_id and (
                positions[provider] >= positions[group_id]
                or not _is_ancestor(provider, group_id, dependencies)
            ):
                _fail("required_symbol_outside_dag", "dependencies", group_id)


def _is_ancestor(parent: str, group_id: str, dependencies: Mapping[str, tuple[str, ...]]) -> bool:
    pending = list(dependencies[group_id])
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == parent:
            return True
        if current not in visited:
            visited.add(current)
            pending.extend(dependencies[current])
    return False


def _unsafe_policy(raw: Any, candidates: Sequence[CandidateSource]) -> dict[str, Any]:
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping) or any(key not in {"allow_unsafe", "max_total", "max_per_group"} for key in raw):
        _fail("unsafe_policy_invalid", "unsafe")
    allow = raw.get("allow_unsafe", True)
    if not isinstance(allow, bool):
        _fail("unsafe_policy_invalid", "unsafe")
    limits: dict[str, int | None] = {}
    for key in ("max_total", "max_per_group"):
        value = raw.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            _fail("unsafe_policy_invalid", "unsafe")
        limits[key] = value
    total = sum(item.unsafe_count for item in candidates)
    if (not allow and total) or (limits["max_total"] is not None and total > limits["max_total"]):
        _fail("unsafe_policy_exceeded", "unsafe")
    if limits["max_per_group"] is not None and any(
        item.unsafe_count > limits["max_per_group"] for item in candidates
    ):
        _fail("unsafe_policy_exceeded", "unsafe")
    return {
        "allow_unsafe": allow, "max_total": limits["max_total"],
        "max_per_group": limits["max_per_group"], "observed_total": total,
        "by_group": [{"group_id": item.group_id, "unsafe_count": item.unsafe_count} for item in candidates],
        "status": "satisfied",
    }


def _symbols(value: Any, group_id: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not _RUST_IDENT.fullmatch(item) or item in _RUST_KEYWORDS
        for item in value
    ):
        _fail("candidate_symbols_invalid", "symbols", group_id)
    if len(value) != len(set(value)):
        _fail("candidate_symbols_duplicate", "symbols", group_id)
    return tuple(sorted(value))


def _group_id(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 or any(ord(char) < 32 for char in value):
        _fail("group_id_invalid", "dag")
    return value


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fail(code: str, stage: str, group_id: str | None = None) -> None:
    raise ProjectInputError(code, stage, group_id)
