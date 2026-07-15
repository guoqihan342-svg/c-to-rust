from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .c2rust_project_baseline_cargo import CargoPreparation
from .c2rust_project_baseline_process import Runner, run_recorded_process
from .c2rust_project_baseline_scenarios import LoadedBaselineScenarios
from .c2rust_project_baseline_workdirs import (
    portable_package_workdir, portable_repository_workdir,
    repository_working_directory,
)


ProcessRefs = tuple[dict[str, Any], dict[str, Any], dict[str, Any]]
ProcessRecord = tuple[dict[str, Any], ProcessRefs]


@dataclass(frozen=True, slots=True)
class CargoExecutionBatch:
    records: tuple[ProcessRecord, ...]
    blockers: tuple[str, ...]
    execution_plan: dict[str, Any]


def execute_generated_cargo(
    *, repository: Path, generated_root: Path,
    preparation: CargoPreparation, cargo_path: str,
    cargo_prefix: Sequence[str], environment: Mapping[str, str],
    timeout_seconds: int, out_root: Path,
    scenarios: LoadedBaselineScenarios | None,
    runner: Runner | None,
) -> CargoExecutionBatch:
    plan = _execution_plan(preparation, scenarios)
    if scenarios is not None and any(
        scenario.timeout_seconds > timeout_seconds
        for wrapper in scenarios.wrappers
        for scenario in wrapper.scenarios
    ):
        return CargoExecutionBatch(
            (), ("c2rust_scenario_timeout_exceeds_policy",), plan,
        )
    records: list[ProcessRecord] = []
    blockers: list[str] = []
    for index, manifest in enumerate(preparation.manifests):
        record = run_recorded_process(
            [
                cargo_path, *cargo_prefix, "check", "--offline", "--all-targets",
                "--manifest-path", manifest.as_posix(),
            ],
            cwd=manifest.parent, environment=environment,
            timeout_seconds=timeout_seconds, out_root=out_root,
            purpose=f"cargo-check-all-targets-{index}", runner=runner,
            portable_argv=[
                "cargo", *cargo_prefix, "check", "--offline", "--all-targets",
                "--manifest-path", manifest.relative_to(generated_root).as_posix(),
            ],
            portable_working_directory=portable_package_workdir(
                generated_root, manifest.parent,
            ),
        )
        records.append(record)
        if record[0]["status"] != "passed":
            blockers.append("c2rust_cargo_check_failed")
    if blockers:
        return CargoExecutionBatch(
            tuple(records), tuple(dict.fromkeys(blockers)), plan,
        )
    if scenarios is None:
        _run_legacy_wrappers(
            records, blockers, repository, generated_root, preparation,
            cargo_path, cargo_prefix, environment, timeout_seconds,
            out_root, runner,
        )
    else:
        _run_declared_scenarios(
            records, blockers, repository, generated_root, preparation,
            scenarios, cargo_path, cargo_prefix, environment,
            out_root, runner,
        )
    return CargoExecutionBatch(
        tuple(records), tuple(dict.fromkeys(blockers)), plan,
    )


def _run_legacy_wrappers(
    records: list[ProcessRecord], blockers: list[str], repository: Path,
    generated_root: Path, preparation: CargoPreparation, cargo_path: str,
    cargo_prefix: Sequence[str], environment: Mapping[str, str],
    timeout_seconds: int, out_root: Path, runner: Runner | None,
) -> None:
    for wrapper in preparation.wrappers:
        manifest = generated_root.joinpath(*Path(wrapper["manifest_path"]).parts)
        working = repository_working_directory(
            repository, wrapper["source_working_directory"],
        )
        record = run_recorded_process(
            [
                cargo_path, *cargo_prefix, "run", "--offline", "--manifest-path",
                manifest.as_posix(), "--bin", wrapper["name"],
            ],
            cwd=working, environment=environment,
            timeout_seconds=timeout_seconds, out_root=out_root,
            purpose=f"cargo-run-wrapper-{wrapper['name']}", runner=runner,
            portable_argv=[
                "cargo", *cargo_prefix, "run", "--offline", "--manifest-path",
                wrapper["manifest_path"], "--bin", wrapper["name"],
            ],
            portable_working_directory=portable_repository_workdir(
                repository, working,
            ),
        )
        records.append(record)
        if record[0]["status"] != "passed":
            blockers.append("c2rust_wrapper_execution_failed")


def _run_declared_scenarios(
    records: list[ProcessRecord], blockers: list[str], repository: Path,
    generated_root: Path, preparation: CargoPreparation,
    scenarios: LoadedBaselineScenarios, cargo_path: str,
    cargo_prefix: Sequence[str], environment: Mapping[str, str],
    out_root: Path, runner: Runner | None,
) -> None:
    by_path = {
        item["translated_module_path"]: item for item in preparation.wrappers
    }
    for wrapper_plan in scenarios.wrappers:
        wrapper = by_path[wrapper_plan.translated_module_path]
        manifest = generated_root.joinpath(*Path(wrapper["manifest_path"]).parts)
        for scenario in wrapper_plan.scenarios:
            working = repository_working_directory(
                repository, scenario.working_directory,
            )
            scenario_environment = dict(environment)
            scenario_environment.update(dict(scenario.environment))
            command = [
                cargo_path, *cargo_prefix, "run", "--offline", "--manifest-path",
                manifest.as_posix(), "--bin", wrapper["name"], "--",
                *scenario.argv,
            ]
            portable = [
                "cargo", *cargo_prefix, "run", "--offline", "--manifest-path",
                wrapper["manifest_path"], "--bin", wrapper["name"], "--",
                *scenario.argv,
            ]
            record = run_recorded_process(
                command, cwd=working, environment=scenario_environment,
                timeout_seconds=scenario.timeout_seconds, out_root=out_root,
                purpose=f"cargo-run-scenario-{scenario.id}", runner=runner,
                portable_argv=portable,
                portable_working_directory=portable_repository_workdir(
                    repository, working,
                ),
                stdin=scenario.stdin,
                expected_returncodes=(scenario.expected_exit,),
                allowed_environment_keys=tuple(
                    key for key, _ in scenario.environment
                ),
            )
            records.append(record)
            if record[0]["status"] != "passed":
                blockers.append("c2rust_scenario_execution_failed")


def _execution_plan(
    preparation: CargoPreparation,
    scenarios: LoadedBaselineScenarios | None,
) -> dict[str, Any]:
    if scenarios is None:
        purposes = [
            f"cargo-run-wrapper-{item['name']}"
            for item in preparation.wrappers
        ]
        return {
            "mode": "legacy-all-wrappers",
            "contract_sha256": None,
            "wrapper_count": len(preparation.wrappers),
            "scenario_count": 0,
            "compile_only_wrapper_count": 0,
            "expected_run_purposes": purposes,
        }
    purposes = [
        f"cargo-run-scenario-{scenario.id}"
        for wrapper in scenarios.wrappers
        for scenario in wrapper.scenarios
    ]
    return {
        "mode": "declared-scenarios",
        "contract_sha256": scenarios.content_sha256,
        "wrapper_count": len(scenarios.wrappers),
        "scenario_count": scenarios.scenario_count,
        "compile_only_wrapper_count": sum(
            item.execution_mode == "compile_only"
            for item in scenarios.wrappers
        ),
        "expected_run_purposes": purposes,
    }


__all__ = ["CargoExecutionBatch", "execute_generated_cargo"]
