from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from validation.tools._project_migration_harness.artifacts import (
    content_sha256,
    write_json_artifact,
)
from validation.tools._project_migration_harness.ledger_run_contract import (
    derive_migration_contract,
)
from validation.tools._project_migration_harness.project_interface_coordinator import (
    coordinate_project_interfaces,
)
from validation.tools._project_migration_harness.project_repair_worker_request import (
    materialize_project_repair_request,
)
from validation.tools._project_migration_harness.rust_project_ir_derivation import (
    derive_rust_project_ir_from_candidates,
)
from validation.tools.project_migration_native_link_test_support import (
    materialize_native_build_ir,
)
from validation.tools.project_migration_project_repair_test_support import (
    project_repair_test_dispatch_permit,
    sha,
)
from validation.tools.project_migration_rust_project_test_support import descriptor


def materialized_native_repair_case(
    root: Path,
    out_root: Path,
    ledger: Any,
    label: str,
    *,
    external_arguments: str = "/private/libnebula.so.2",
) -> tuple[
    dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any],
]:
    out_root.mkdir(parents=True, exist_ok=True)
    _repo, _database, _build_ir, build_ref = materialize_native_build_ir(
        out_root, f"native-source-{label}", external_arguments,
    )
    candidate = descriptor(
        out_root, "unit", "pub fn value() -> i32 { 1 }\n",
        filename=f"{label}.rs",
    )
    verification_ref = write_json_artifact(
        out_root, f"plan/{label}-build-ir-verification.json",
        {"schema_version": 1, "status": "passed"},
    )
    admission_ref = write_json_artifact(
        out_root, f"plan/{label}-build-ir-worker-admission.json",
        {"schema_version": 1, "status": "admitted"},
    )
    manifest = {
        "schema_version": 1,
        "profile": "competition",
        "dag": {"unit": []},
        "dag_order": ["unit"],
        "unsafe_policy": {
            "allow_unsafe": True,
            "max_total": None,
            "max_per_group": None,
        },
        "build_ir": {
            "status": "bound",
            "artifact": build_ref,
            "verification": verification_ref,
            "worker_admission": admission_ref,
        },
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    manifest_ref = write_json_artifact(
        out_root, f"plan/{label}-integration-manifest.json", manifest,
    )
    rust_project_ir = derive_rust_project_ir_from_candidates(
        migration_manifest=manifest,
        migration_dag_ref=manifest_ref,
        build_ir_refs=[build_ref],
        candidate_descriptors=[candidate],
        artifact_root=out_root,
    )
    receipt = coordinate_project_interfaces(rust_project_ir)
    run_id = f"run-{label}"
    units = [{
        "unit_id": "unit",
        "group_id": "unit",
        "wave_index": 0,
        "content_sha256": sha(f"unit:{label}"),
    }]
    artifacts = {"integration_manifest": manifest_ref}
    contract, _ = derive_migration_contract(
        ledger.path,
        artifacts,
        run_id=run_id,
        dag_sha256=sha(f"dag:{label}"),
        units=units,
    )
    ledger.create_run(
        run_id=run_id,
        project_key="generic-native-project",
        source_commit="commit",
        dag_sha256=sha(f"dag:{label}"),
        units=units,
        assignments=[],
        max_concurrency=1,
        max_attempts=3,
        metadata={"artifacts": artifacts, "migration_contract": contract},
    )
    ledger.register_project_interface_receipt(
        run_id=run_id,
        receipt=receipt,
        rust_project_ir=rust_project_ir,
    )
    base_ref = write_json_artifact(
        out_root, f"facts/{label}-rust-project-ir.json", rust_project_ir,
    )
    bound_base_ref = _prefix(base_ref, "target/run")
    item = next(
        entry for entry in receipt["project_repair_queue"]["items"]
        if entry["diagnostic_code"]
        == "rust_project_ir_native_link_plan_missing"
    )
    materialized = materialize_project_repair_request(
        ledger=ledger,
        run_id=run_id,
        queue_sha256=receipt["project_repair_queue"][
            "project_repair_queue_sha256"
        ],
        repair_id=item["repair_id"],
        worker_id="project-repairer-1",
        base_rust_project_ir=bound_base_ref,
        harness_root=root,
        out_root=out_root,
        out_root_rel="target/run",
        dispatch_permit=project_repair_test_dispatch_permit(
            root,
            out_root,
            ledger,
            bound_base_ref,
            run_id=run_id,
        ),
    )
    request_ref = materialized["request"]
    request = json.loads(
        (root / Path(*request_ref["path"].split("/"))).read_text(
            encoding="utf-8"
        )
    )
    if request["effective_input_sha256"] != content_sha256({
        key: value
        for key, value in request.items()
        if key not in {"effective_input_sha256", "execution_binding"}
    }):
        raise AssertionError("native repair request fixture drifted")
    return request, request_ref, rust_project_ir, manifest


def native_repair_response(
    request: dict[str, Any], plan_set_id: str,
    proposals: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": request["run_id"],
        "role": "project-repairer",
        "project_repair_queue_sha256": request[
            "project_repair_queue_sha256"
        ],
        "repair_id": request["repair_id"],
        "attempt_id": request["execution_binding"]["attempt_id"],
        "effective_input_sha256": request["effective_input_sha256"],
        "base_rust_project_ir_sha256": request["base_rust_project_ir"][
            "ir_sha256"
        ],
        "context_sha256": request["project_repair_context"]["context_sha256"],
        "operations": [{
            "section": "native_link_plans",
            "action": "bind",
            "record_id": plan_set_id,
            "changes": {"proposals": proposals},
        }],
    }


def native_link_proposal(requirement: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": requirement["requirement_id"],
        "strategy": "rustc-link-lib",
        "rustc_link_name": requirement["portable_name"],
        "rustc_link_kind": (
            "static"
            if requirement["library_format"] == "static-archive"
            else "dylib"
        ),
    }


def _prefix(reference: dict[str, Any], root: str) -> dict[str, Any]:
    return {**reference, "path": f"{root}/{reference['path']}"}


__all__ = [
    "materialized_native_repair_case", "native_link_proposal",
    "native_repair_response",
]
