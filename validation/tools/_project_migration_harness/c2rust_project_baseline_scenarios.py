from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .c2rust_project_baseline_scenario_validation import (
    load_scenario_contract_json, parse_scenario,
)


SCHEMA_VERSION = 1
MAX_WRAPPERS = 20_000
MAX_SCENARIOS = 100_000
_TOP_FIELDS = frozenset({"schema_version", "wrappers"})
_WRAPPER_FIELDS = frozenset({
    "translated_module_path", "execution_mode", "scenarios",
})


class BaselineScenarioContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BoundBaselineScenarioContract:
    repository_root: Path
    source_path: str
    source_bytes: bytes
    source_sha256: str
    parsed: Any


@dataclass(frozen=True, slots=True)
class BaselineScenario:
    id: str
    argv: tuple[str, ...]
    working_directory: str
    environment: tuple[tuple[str, str], ...]
    stdin: bytes
    expected_exit: int
    timeout_seconds: int

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "argv": list(self.argv),
            "working_directory": self.working_directory,
            "environment": dict(self.environment),
            "stdin_utf8": self.stdin.decode("utf-8"),
            "expected_exit": self.expected_exit,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True, slots=True)
class WrapperExecution:
    translated_module_path: str
    execution_mode: str
    scenarios: tuple[BaselineScenario, ...]

    def payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "translated_module_path": self.translated_module_path,
            "execution_mode": self.execution_mode,
        }
        if self.execution_mode == "scenarios":
            result["scenarios"] = [item.payload() for item in self.scenarios]
        return result


@dataclass(frozen=True, slots=True)
class LoadedBaselineScenarios:
    wrappers: tuple[WrapperExecution, ...]
    canonical_payload: bytes
    content_sha256: str

    @property
    def scenario_count(self) -> int:
        return sum(len(item.scenarios) for item in self.wrappers)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "wrappers": [item.payload() for item in self.wrappers],
        }


def load_baseline_scenarios(
    repo_root: Path,
    contract_path: Path,
    wrappers: Sequence[Mapping[str, Any]],
) -> LoadedBaselineScenarios:
    bound = bind_baseline_scenario_contract(repo_root, contract_path)
    return project_baseline_scenarios(repo_root, bound, wrappers)


def bind_baseline_scenario_contract(
    repo_root: Path, contract_path: Path,
) -> BoundBaselineScenarioContract:
    root = Path(repo_root).resolve(strict=True)
    parsed, source, relative = load_scenario_contract_json(
        root, contract_path, BaselineScenarioContractError,
    )
    return BoundBaselineScenarioContract(
        root, relative, source, hashlib.sha256(source).hexdigest(), parsed,
    )


def project_baseline_scenarios(
    repo_root: Path,
    bound: BoundBaselineScenarioContract,
    wrappers: Sequence[Mapping[str, Any]],
) -> LoadedBaselineScenarios:
    root = Path(repo_root).resolve(strict=True)
    if root != bound.repository_root:
        raise BaselineScenarioContractError(
            "c2rust_scenario_repository_binding_mismatch"
        )
    known_paths = _wrapper_paths(wrappers)
    executions = _parse_contract(
        root, bound.parsed, known_paths,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "wrappers": [item.payload() for item in executions],
    }
    canonical = canonical_json_bytes(payload)
    return LoadedBaselineScenarios(
        executions, canonical, hashlib.sha256(canonical).hexdigest(),
    )


def _wrapper_paths(
    wrappers: Sequence[Mapping[str, Any]],
) -> frozenset[str]:
    if (
        isinstance(wrappers, (str, bytes))
        or not isinstance(wrappers, Sequence)
        or not wrappers
        or len(wrappers) > MAX_WRAPPERS
    ):
        raise BaselineScenarioContractError("c2rust_scenario_wrappers_invalid")
    paths: set[str] = set()
    names: set[str] = set()
    for wrapper in wrappers:
        if not isinstance(wrapper, Mapping):
            raise BaselineScenarioContractError("c2rust_scenario_wrapper_invalid")
        path = wrapper.get("translated_module_path")
        name = wrapper.get("name")
        if (
            not isinstance(path, str) or not path
            or not isinstance(name, str) or not name
            or path in paths or name in names
        ):
            raise BaselineScenarioContractError(
                "c2rust_scenario_wrapper_identity_invalid"
            )
        paths.add(path)
        names.add(name)
    return frozenset(paths)


def _parse_contract(
    repo_root: Path, value: Any, known_paths: frozenset[str],
) -> tuple[WrapperExecution, ...]:
    _exact_fields(value, _TOP_FIELDS, "contract")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise BaselineScenarioContractError(
            "c2rust_scenario_schema_version_invalid"
        )
    entries = value["wrappers"]
    if (
        not isinstance(entries, list) or not entries
        or len(entries) > MAX_WRAPPERS
    ):
        raise BaselineScenarioContractError(
            "c2rust_scenario_contract_wrappers_invalid"
        )
    result: list[WrapperExecution] = []
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()
    scenario_count = 0
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise BaselineScenarioContractError(
                "c2rust_scenario_wrapper_entry_invalid"
            )
        mode = entry.get("execution_mode")
        expected = (
            _WRAPPER_FIELDS
            if mode == "scenarios"
            else _WRAPPER_FIELDS - {"scenarios"}
        )
        _exact_fields(entry, expected, "wrapper_entry")
        path = entry["translated_module_path"]
        if (
            not isinstance(path, str) or path not in known_paths
            or path in seen_paths
        ):
            raise BaselineScenarioContractError(
                "c2rust_scenario_wrapper_mapping_invalid"
            )
        seen_paths.add(path)
        if mode == "compile_only":
            result.append(WrapperExecution(path, mode, ()))
            continue
        if mode != "scenarios":
            raise BaselineScenarioContractError(
                "c2rust_scenario_execution_mode_invalid"
            )
        raw_scenarios = entry["scenarios"]
        if not isinstance(raw_scenarios, list) or not raw_scenarios:
            raise BaselineScenarioContractError(
                "c2rust_scenario_list_invalid"
            )
        if len(raw_scenarios) > MAX_SCENARIOS - scenario_count:
            raise BaselineScenarioContractError(
                "c2rust_scenario_count_limit_exceeded"
            )
        scenarios = tuple(
            parse_scenario(
                repo_root, item, BaselineScenario,
                BaselineScenarioContractError,
            )
            for item in raw_scenarios
        )
        scenario_count += len(scenarios)
        for scenario in scenarios:
            if scenario.id in seen_ids:
                raise BaselineScenarioContractError(
                    "c2rust_scenario_id_duplicate"
                )
            seen_ids.add(scenario.id)
        ordered = tuple(sorted(scenarios, key=lambda item: item.id))
        result.append(WrapperExecution(path, mode, ordered))
    if seen_paths != known_paths:
        raise BaselineScenarioContractError(
            "c2rust_scenario_wrapper_mapping_incomplete"
        )
    return tuple(sorted(result, key=lambda item: item.translated_module_path))


def _exact_fields(value: Any, expected: frozenset[str], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise BaselineScenarioContractError(f"c2rust_scenario_{label}_fields_invalid")


__all__ = [
    "BaselineScenario", "BaselineScenarioContractError",
    "BoundBaselineScenarioContract", "LoadedBaselineScenarios",
    "WrapperExecution", "bind_baseline_scenario_contract",
    "load_baseline_scenarios", "project_baseline_scenarios",
]
