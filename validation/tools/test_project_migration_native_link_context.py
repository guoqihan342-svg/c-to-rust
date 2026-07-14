from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.native_link_context import (
    build_native_link_context,
    reopen_native_link_context,
    validate_native_link_context,
)
from validation.tools._project_migration_harness.native_link_model import (
    build_native_link_candidate,
    render_native_link_prompt,
    validate_native_link_candidate,
)
from validation.tools._project_migration_harness.orchestrator import plan_project
from validation.tools.project_migration_native_link_test_support import (
    materialize_native_build_ir,
)


class NativeLinkContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="native-link-context-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def test_context_groups_portable_identities_and_reopens_build_ir(self) -> None:
        root, database, build_ir, reference = materialize_native_build_ir(
            self.base,
            "grouped",
            "/one/private/libalpha.so.3 /two/private/libalpha.so.3 "
            "/three/private/libbeta.a",
        )

        context = build_native_link_context(
            build_ir, reference, profile="competition",
        )

        self.assertEqual("planning-required", context["status"])
        self.assertEqual(2, context["requirement_count"])
        self.assertEqual(3, context["dependency_count"])
        alpha = next(
            item for item in context["requirements"]
            if item["portable_name"] == "libalpha.so.3"
        )
        self.assertEqual(2, alpha["dependency_count"])
        serialized = json.dumps(context, sort_keys=True)
        self.assertNotIn("/one/private", serialized)
        self.assertNotIn("/two/private", serialized)
        self.assertNotIn("/three/private", serialized)
        self.assertEqual(
            "bound", reopen_native_link_context(context, self.base)["status"],
        )
        self.assertTrue(root.is_dir())
        self.assertTrue(database.is_file())

    def test_prompt_is_grouped_and_model_can_only_create_a_candidate(self) -> None:
        _root, _database, build_ir, reference = materialize_native_build_ir(
            self.base,
            "candidate", "/private/libtheta.so /elsewhere/libtheta.so",
        )
        context = build_native_link_context(
            build_ir, reference, profile="development",
        )
        prompt = render_native_link_prompt(context)
        requirement = context["requirements"][0]
        response = {
            "schema_version": 1,
            "artifact_kind": "native-link-model-response",
            "context_sha256": context["context_sha256"],
            "proposals": [{
                "requirement_id": requirement["requirement_id"],
                "strategy": "rustc-link-lib",
                "rustc_link_name": "theta",
                "rustc_link_kind": "dylib",
            }],
        }

        candidate = build_native_link_candidate(context, response)

        self.assertEqual(1, prompt.count("libtheta.so"))
        self.assertEqual("candidate", candidate["status"])
        self.assertFalse(candidate["claim_boundary"]["native_link_config_resolved"])
        self.assertFalse(candidate["claim_boundary"]["cargo_executed"])
        self.assertFalse(candidate["claim_boundary"]["semantic_gate"])
        validate_native_link_candidate(candidate, context)

    def test_no_native_dependencies_do_not_create_model_work(self) -> None:
        _root, _database, build_ir, reference = materialize_native_build_ir(
            self.base, "none", "",
        )
        context = build_native_link_context(
            build_ir, reference, profile="development",
        )

        self.assertEqual("not-required", context["status"])
        self.assertEqual(0, context["requirement_count"])
        self.assertTrue(context["claim_boundary"]["native_link_config_resolved"])
        with self.assertRaisesRegex(ValueError, "not_required"):
            render_native_link_prompt(context)

    def test_response_rejects_missing_coverage_paths_and_resolution_claims(self) -> None:
        _root, _database, build_ir, reference = materialize_native_build_ir(
            self.base,
            "reject", "/private/libgamma.so /private/libdelta.a",
        )
        context = build_native_link_context(
            build_ir, reference, profile="competition",
        )
        requirements = context["requirements"]
        base = {
            "schema_version": 1,
            "artifact_kind": "native-link-model-response",
            "context_sha256": context["context_sha256"],
            "proposals": [{
                "requirement_id": requirements[0]["requirement_id"],
                "strategy": "defer",
                "rustc_link_name": None,
                "rustc_link_kind": None,
            }],
        }
        with self.assertRaisesRegex(ValueError, "coverage"):
            build_native_link_candidate(context, base)

        injected = copy.deepcopy(base)
        injected["proposals"] = [{
            "requirement_id": item["requirement_id"],
            "strategy": "rustc-link-lib",
            "rustc_link_name": "/host/private/library",
            "rustc_link_kind": "dylib",
        } for item in requirements]
        with self.assertRaisesRegex(ValueError, "directive"):
            build_native_link_candidate(context, injected)

        forged = copy.deepcopy(base)
        forged["resolved"] = True
        with self.assertRaisesRegex(ValueError, "schema"):
            build_native_link_candidate(context, forged)

    def test_context_and_bound_build_ir_tamper_fail_closed(self) -> None:
        _root, _database, build_ir, reference = materialize_native_build_ir(
            self.base,
            "tamper", "/private/libomega.so",
        )
        context = build_native_link_context(
            build_ir, reference, profile="competition",
        )
        altered = copy.deepcopy(context)
        altered["requirements"][0]["dependency_count"] = 2
        with self.assertRaisesRegex(ValueError, "summary|sha256"):
            validate_native_link_context(altered)

        path = self.base / reference["path"]
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            reopen_native_link_context(context, self.base)

    def test_project_plan_publishes_native_link_context_before_workers(self) -> None:
        root, database, _build_ir, _reference = materialize_native_build_ir(
            self.base,
            "plan-source", "/private/libplan.so",
        )

        plan = plan_project(
            root,
            harness_root=self.base,
            out_root="plan-run",
            compile_database=database,
            profile="development",
            max_units=8,
        )

        self.assertEqual("planned", plan["status"])
        reference = plan["artifacts"]["native_link_context"]
        payload = json.loads(
            (self.base / "plan-run" / reference["path"]).read_text("utf-8")
        )
        self.assertEqual("planning-required", payload["status"])
        self.assertEqual(1, plan["execution"]["native_link_requirement_count"])
        self.assertFalse(plan["execution"]["native_link_config_resolved"])
        self.assertFalse(plan["execution"]["model_launched"])

if __name__ == "__main__":
    unittest.main()
