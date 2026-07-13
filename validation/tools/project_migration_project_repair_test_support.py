from __future__ import annotations

import hashlib
import json
from pathlib import Path

from validation.tools._project_migration_harness.artifacts import write_json_artifact
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.project_interface_coordinator import (
    coordinate_project_interfaces,
)
from validation.tools._project_migration_harness.project_repair_worker_request import (
    materialize_project_repair_request,
)
from validation.tools._project_migration_harness.rust_project_ir import build_rust_project_ir
from validation.tools._project_migration_harness.rust_project_ir_validation import (
    module_id_for_candidate,
)
from validation.tools.project_migration_rust_project_test_support import (
    bound_ir,
    descriptor,
)


def sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def coordinated_case(
    label: str, *, conflict: bool = True, max_attempts: int = 2,
    unit_id: str = "unit-a", dag_sha256: str | None = None,
    additional_conflict: bool = False,
) -> tuple[dict, dict]:
    build_sha = sha(f"build:{label}")
    candidate_sha = sha(f"candidate:{label}")
    module_id = module_id_for_candidate(candidate_sha)
    bound_evidence = evidence(build_sha, unit_id, candidate_sha)
    ir = build_rust_project_ir(
        migration_dag_ref={
            "path": f"facts/{label}-dag.json", "sha256": dag_sha256 or sha("dag"),
            "size_bytes": 1,
        },
        build_ir_refs=[{
            "path": f"facts/{label}-build-ir.json", "sha256": build_sha,
            "size_bytes": 1,
        }],
        candidate_refs=[{
            "unit_id": unit_id, "artifact_id": f"candidate-{label}",
            "source": {"path": f"candidates/{label}.rs", "sha256": candidate_sha,
                       "size_bytes": 4},
        }],
        crate={
            "crate_id": f"crate-{label}", "edition": "2021",
            "crate_types": ["rlib"], "root_module_id": module_id,
            "targets": ["library"], "evidence": bound_evidence,
        },
        modules=[{
            "module_id": module_id, "parent_module_id": None,
            "rust_path": "src/lib.rs", "unit_id": unit_id,
            "candidate_sha256": candidate_sha, "visibility": "crate",
            "evidence": bound_evidence,
        }],
        public_api=[
            {"declaration_id": f"api-left-{label}", "module_id": module_id,
             "symbol": "shared", "kind": "function", "signature": "fn()->i32",
             "visibility": "public", "evidence": bound_evidence},
            {"declaration_id": f"api-right-{label}", "module_id": module_id,
             "symbol": "shared" if conflict else "independent",
             "kind": "function", "signature": "fn()->u32",
             "visibility": "public", "evidence": bound_evidence},
            *([{
                "declaration_id": f"api-other-left-{label}",
                "module_id": module_id, "symbol": "other",
                "kind": "function", "signature": "fn()->i32",
                "visibility": "public", "evidence": bound_evidence,
            }, {
                "declaration_id": f"api-other-right-{label}",
                "module_id": module_id, "symbol": "other",
                "kind": "function", "signature": "fn()->u64",
                "visibility": "public", "evidence": bound_evidence,
            }] if additional_conflict else []),
        ],
    )
    return ir, coordinate_project_interfaces(
        ir, max_repairs=32, max_attempts_per_item=max_attempts,
    )


def evidence(build_sha: str, unit_id: str, candidate_sha: str) -> dict:
    return {
        "build_ir_sha256s": [build_sha], "dag_unit_ids": [unit_id],
        "candidate_sha256s": [candidate_sha],
    }


def materialized_repair_case(
    root: Path, out_root: Path, ledger: ProjectLedger, label: str, *,
    run_id: str = "run", worker_id: str = "project-repairer-1",
    out_root_rel: str = "target/run", max_attempts: int = 2,
    additional_conflict: bool = False,
) -> tuple[dict, dict, dict, str]:
    candidate = descriptor(
        root, "unit-a", "pub fn shared() -> i32 { 1 }\n",
        filename=f"{label}.rs",
    )
    original, _ = bound_ir(root, [candidate], {"unit-a": []})
    with ledger.connect() as connection:
        run = connection.execute(
            "select run_id from project_runs where run_id=?", (run_id,),
        ).fetchone()
    if run is None:
        ledger.create_run(
            run_id=run_id, project_key="generic-project", source_commit="commit",
            dag_sha256=original["bindings"]["migration_dag"]["sha256"],
            units=[{
                "unit_id": "unit-a", "group_id": "unit-a", "wave_index": 0,
                "content_sha256": sha("unit-a"),
            }], assignments=[], max_concurrency=1, max_attempts=3,
        )
    duplicate = dict(original["public_api"][0])
    duplicate["declaration_id"] = f"api-duplicate-{label}"
    duplicate["signature"] = "fn()->u64"
    extra_api: list[dict] = []
    if additional_conflict:
        extra_left = dict(original["public_api"][0])
        extra_left.update({
            "declaration_id": f"api-other-left-{label}", "symbol": "other",
        })
        extra_right = dict(extra_left)
        extra_right.update({
            "declaration_id": f"api-other-right-{label}",
            "signature": "fn()->u64",
        })
        extra_api = [extra_left, extra_right]
    base = build_rust_project_ir(
        migration_dag_ref=original["bindings"]["migration_dag"],
        build_ir_refs=original["bindings"]["build_ir"],
        candidate_refs=original["bindings"]["candidates"],
        crate=original["crate"], modules=original["modules"],
        public_api=[*original["public_api"], duplicate, *extra_api],
        shared_types=original["shared_types"],
        global_ownership=original["global_ownership"],
        initialization=original["initialization"],
        ffi_boundaries=original["ffi_boundaries"], cfgs=original["cfgs"],
        features=original["features"],
        unsafe_obligations=original["unsafe_obligations"],
    )
    receipt = coordinate_project_interfaces(
        base, max_repairs=32, max_attempts_per_item=max_attempts,
    )
    ledger.register_project_interface_receipt(
        run_id=run_id, receipt=receipt, rust_project_ir=base,
    )
    base_ref = write_json_artifact(
        root, f"facts/{label}-rust-project-ir.json", base,
    )
    diagnostic_by_sha = {
        value["diagnostic_sha256"]: value for value in receipt["diagnostics"]
    }
    item = next(
        value for value in receipt["project_repair_queue"]["items"]
        if duplicate["declaration_id"] in diagnostic_by_sha[
            value["diagnostic_sha256"]
        ]["entity_ids"]
    )
    materialized = materialize_project_repair_request(
        ledger=ledger, run_id=run_id,
        queue_sha256=receipt["project_repair_queue"][
            "project_repair_queue_sha256"
        ],
        repair_id=item["repair_id"], worker_id=worker_id,
        base_rust_project_ir=base_ref, harness_root=root,
        out_root=out_root, out_root_rel=out_root_rel,
    )
    request_ref = materialized["request"]
    request = json.loads(
        (root / Path(*request_ref["path"].split("/"))).read_text(
            encoding="utf-8"
        )
    )
    return request, request_ref, base, duplicate["declaration_id"]


__all__ = [
    "coordinated_case", "evidence", "materialized_repair_case", "sha",
]
