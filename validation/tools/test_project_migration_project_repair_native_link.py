from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._ai_candidate_harness_parts.provider_runtime import (
    ProviderExecution,
)
from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.controller import (
    run_and_ingest_opencode_project_repair,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.project_native_link_state import (
    recover_project_native_link_state,
)
from validation.tools._project_migration_harness.project_repair_ingest import (
    ingest_project_repair_response,
)
from validation.tools._project_migration_harness.project_repair_prompt import (
    render_project_repair_prompt,
)
from validation.tools._project_migration_harness.project_repair_worker_request import (
    read_bound_rust_project_ir,
)
from validation.tools._project_migration_harness.rust_project_cargo import (
    reconstruct_cargo_project_from_ir,
)
from validation.tools.project_migration_project_repair_native_test_support import (
    materialized_native_repair_case,
    native_link_proposal,
    native_repair_response,
)
from validation.tools.project_migration_runtime_test_support import (
    LOGICAL_MODEL,
    RESOLVED_MODEL,
)


class ProjectRepairNativeLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-repair-native-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / "target/run"
        self.ledger = ProjectLedger(
            self.out / "state/project-migration.sqlite3"
        )

    def test_prompt_exposes_only_bounded_portable_native_facts(self) -> None:
        request, _request_ref, base_ir, _manifest = materialized_native_repair_case(
            self.root, self.out, self.ledger, "prompt",
        )

        prompt = json.loads(render_project_repair_prompt(
            request, harness_root=self.root,
        ))
        serialized = json.dumps(prompt, sort_keys=True)
        planning = prompt["project_repair_context"]["native_link_planning"]

        self.assertEqual(3, prompt["project_repair_context"]["schema_version"])
        self.assertEqual(
            "native-link-plan-set",
            request["output_contract"]["kind"],
        )
        self.assertEqual(
            base_ir["native_link_requirements"],
            planning["context"]["requirements"],
        )
        self.assertNotIn("/private", serialized)
        self.assertNotIn("build_ir_binding", serialized)
        self.assertNotIn("target/run", serialized)
        self.assertFalse(
            prompt["project_repair_context"]["claim_boundary"][
                "semantic_acceptance"
            ]
        )

    def test_valid_plan_reopens_build_ir_and_recoordinates_candidate(self) -> None:
        request, _request_ref, base_ir, manifest = materialized_native_repair_case(
            self.root,
            self.out,
            self.ledger,
            "round-trip",
            external_arguments="/private/libalpha.so /private/libbeta.a",
        )
        prompt = json.loads(render_project_repair_prompt(
            request, harness_root=self.root,
        ))
        planning = prompt["project_repair_context"]["native_link_planning"]
        requirements = planning["context"]["requirements"]
        response = native_repair_response(
            request,
            planning["plan_set_id"],
            [native_link_proposal(item) for item in reversed(requirements)],
        )

        result = ingest_project_repair_response(
            request,
            response,
            ledger=self.ledger,
            harness_root=self.root,
            out_root=self.out,
            out_root_rel="target/run",
        )

        self.assertEqual("resolved", result["status"])
        self.assertEqual("candidate-ready", result["coordinator_status"])
        self.assertNotEqual(base_ir["ir_sha256"], result["candidate_ir_sha256"])
        candidate = read_bound_rust_project_ir(
            self.root, result["artifacts"]["rust_project_ir_candidate"],
        )
        state = recover_project_native_link_state(candidate, manifest, self.out)
        self.assertEqual("candidate-ready", state["status"])
        self.assertFalse(state["resolution_gate"])
        self.assertFalse(candidate["claim_boundary"]["semantic_gate"])
        cargo = reconstruct_cargo_project_from_ir(candidate, self.out)
        build_script = cargo.files["build.rs"].decode("ascii")
        for requirement in requirements:
            kind = native_link_proposal(requirement)["rustc_link_kind"]
            self.assertIn(
                f"cargo:rustc-link-lib={kind}={requirement['portable_name']}",
                build_script,
            )
        latest = self.ledger.load_latest_project_interface_receipt(
            run_id=request["run_id"]
        )
        self.assertEqual(2, latest[0])
        self.assertEqual("candidate-ready", latest[1]["status"])

    def test_incomplete_proposal_set_is_retryable_and_never_bound(self) -> None:
        request, _request_ref, base_ir, _manifest = materialized_native_repair_case(
            self.root,
            self.out,
            self.ledger,
            "incomplete",
            external_arguments="/private/libalpha.so /private/libbeta.a",
        )
        prompt = json.loads(render_project_repair_prompt(
            request, harness_root=self.root,
        ))
        planning = prompt["project_repair_context"]["native_link_planning"]
        requirements = planning["context"]["requirements"]
        self.assertEqual(2, len(requirements))
        response = native_repair_response(
            request,
            planning["plan_set_id"],
            [native_link_proposal(requirements[0])],
        )

        result = ingest_project_repair_response(
            request,
            response,
            ledger=self.ledger,
            harness_root=self.root,
            out_root=self.out,
            out_root_rel="target/run",
        )

        self.assertEqual("retry-ready", result["status"])
        self.assertEqual(
            "invalid_project_repair_ir_candidate", result["error_code"]
        )
        self.assertEqual([], base_ir["native_link_plans"])

    def test_path_bearing_link_name_is_rejected_before_host_binding(self) -> None:
        request, _request_ref, _base_ir, _manifest = materialized_native_repair_case(
            self.root, self.out, self.ledger, "path-rejected",
        )
        prompt = json.loads(render_project_repair_prompt(
            request, harness_root=self.root,
        ))
        planning = prompt["project_repair_context"]["native_link_planning"]
        requirement = planning["context"]["requirements"][0]
        proposal = native_link_proposal(requirement)
        proposal["rustc_link_name"] = "/private/libnebula.so"

        result = ingest_project_repair_response(
            request,
            native_repair_response(
                request, planning["plan_set_id"], [proposal],
            ),
            ledger=self.ledger,
            harness_root=self.root,
            out_root=self.out,
            out_root_rel="target/run",
        )

        self.assertEqual("retry-ready", result["status"])
        self.assertEqual("invalid_project_repair_response", result["error_code"])

    def test_unsafe_host_context_reference_blocks_prompt_materialization(self) -> None:
        request, _request_ref, _base_ir, _manifest = materialized_native_repair_case(
            self.root, self.out, self.ledger, "unsafe-reference",
        )
        forged = copy.deepcopy(request)
        forged["native_link_context"]["path"] = "../outside/context.json"
        projection = {
            key: value for key, value in forged.items()
            if key not in {"effective_input_sha256", "execution_binding"}
        }
        forged["effective_input_sha256"] = content_sha256(projection)
        binding = forged["execution_binding"]
        binding["effective_input_sha256"] = forged["effective_input_sha256"]
        binding["binding_sha256"] = content_sha256({
            key: value for key, value in binding.items()
            if key != "binding_sha256"
        })

        with self.assertRaisesRegex(
            ValueError, "native link context reference is invalid",
        ):
            render_project_repair_prompt(forged, harness_root=self.root)

    def test_isolated_opencode_runtime_carries_native_plan_to_host_ingest(self) -> None:
        request, request_ref, _base_ir, _manifest = (
            materialized_native_repair_case(
                self.root, self.out, self.ledger, "runtime",
            )
        )
        prompt = json.loads(render_project_repair_prompt(
            request, harness_root=self.root,
        ))
        planning = prompt["project_repair_context"]["native_link_planning"]
        requirement = planning["context"]["requirements"][0]
        response = native_repair_response(
            request,
            planning["plan_set_id"],
            [native_link_proposal(requirement)],
        )

        def runner(
            _argv: list[str], _timeout: int, *,
            environment: dict[str, str], cwd: Path,
        ) -> ProviderExecution:
            self.assertTrue(environment)
            self.assertTrue(cwd.is_dir())
            event = {
                "type": "text",
                "text": json.dumps(response),
                "sessionID": "session-native-project-repair",
            }
            return ProviderExecution(
                0,
                json.dumps(event) + "\n",
                "",
                identity_receipt={
                    "source": "runner-contract",
                    "session_id": "session-native-project-repair",
                    "provider_id": "opencode",
                    "model_id": "deepseek-v4-flash-free",
                    "agent": "c2rust-candidate",
                    "variant": "max",
                    "opencode_version": "test-double",
                },
            )

        with mock.patch(
            "validation.tools._project_migration_harness.project_repair_runtime."
            "subprocess_runner_with_environment",
            side_effect=runner,
        ):
            result = run_and_ingest_opencode_project_repair(
                request_ref,
                request["preflight_binding"]["preflight"],
                ledger=self.ledger,
                harness_root=self.root,
                out_root=self.out,
                out_root_rel="target/run",
                logical_model=LOGICAL_MODEL,
                resolved_model=RESOLVED_MODEL,
            )

        self.assertEqual("resolved", result["status"])
        self.assertTrue(result["generation"]["model_launched"])
        prompt_ref = result["generation"]["artifacts"]["prompt"]
        persisted_prompt = (
            self.root / Path(*prompt_ref["path"].split("/"))
        ).read_text(encoding="utf-8")
        self.assertNotIn("/private", persisted_prompt)
        with self.ledger.connect() as connection:
            kinds = {
                str(row["kind"]) for row in connection.execute(
                    "select kind from project_repair_artifacts where run_id=?",
                    (request["run_id"],),
                ).fetchall()
            }
        self.assertIn("native-link-context", kinds)
        self.assertIn("provider-invocation_receipt", kinds)

if __name__ == "__main__":
    unittest.main()
