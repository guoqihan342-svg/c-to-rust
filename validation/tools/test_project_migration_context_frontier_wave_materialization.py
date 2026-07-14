from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.context_frontier_cas import (
    write_frontier_cas_json,
)
from validation.tools._project_migration_harness.context_frontier_wave import (
    build_context_expansion_query,
)
from validation.tools._project_migration_harness.context_frontier_wave_materialization import (
    materialize_context_frontier_wave_selection,
)
from validation.tools._project_migration_harness.context_frontier_wave_selection import (
    CLAIM_BOUNDARY,
)
from validation.tools._project_migration_harness.context_required_facts import (
    context_retrieval_ready,
)
from validation.tools.project_migration_context_frontier_wave_materialization_test_support import (
    DIRECTIVE_KIND,
    RUN_ID,
    TARGET,
    context_fixture,
    derive_directives,
    digest,
    failure_evidence,
)


class ProjectMigrationContextFrontierWaveMaterializationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="frontier-wave-materialization-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_materializes_expansion_or_failure_fact_dynamic_selection(self) -> None:
        cases = ("expansion-query", "failure-fact")
        for case in cases:
            with self.subTest(case=case):
                bundle, refs, entries, retrieval = context_fixture()
                failures = [] if case == "expansion-query" else [failure_evidence()]
                request = (
                    {
                        "family": "include-adjacency",
                        "anchor_fact_sha256": refs["include"],
                    }
                    if case == "expansion-query"
                    else {
                        "family": "verified-failure-fact",
                        "failure_evidence_sha256": failures[0]["sha256"],
                    }
                )
                query = build_context_expansion_query(
                    run_id=RUN_ID,
                    unit_id=TARGET,
                    query_epoch=2,
                    requests=[request],
                )
                directives = derive_directives(bundle, query, failures)
                directive_ref = write_frontier_cas_json(
                    self.root, DIRECTIVE_KIND, directives,
                )
                original_entries = deepcopy(entries)

                pages, rebound, materialization = (
                    materialize_context_frontier_wave_selection(
                        directives,
                        directives_reference=directive_ref,
                        context_bundle=bundle,
                        entries=entries,
                        retrieval=retrieval,
                    )
                )

                selected = directives["allowed_deferred_fact_refs"]
                host_refs = [
                    item["sha256"] for item in directives["host_failure_facts"]
                ]
                expected_refs = [*selected, *host_refs]
                supplemental = pages[-1]
                payload = json.loads(supplemental["payload"].decode("utf-8"))

                self.assertEqual(original_entries, entries)
                self.assertEqual(len(entries) + 1, len(pages))
                self.assertEqual(expected_refs, supplemental["fact_refs"])
                self.assertEqual(
                    expected_refs,
                    [item["sha256"] for item in payload["facts"]],
                )
                self.assertEqual(
                    "frontier-wave-expansion",
                    supplemental["page_metadata"]["classification"],
                )
                self.assertEqual(
                    supplemental["page_id"], materialization["supplemental_page_id"],
                )
                self.assertEqual(
                    query["sha256"],
                    directives["input_bindings"]["expansion_query_sha256"],
                )
                self.assertEqual(
                    directives["sha256"], rebound["frontier_wave_selection_sha256"],
                )
                self.assertEqual(
                    directive_ref["sha256"],
                    rebound["frontier_wave_selection_artifact_sha256"],
                )
                self.assertEqual(
                    directives["host_failure_fact_set_sha256"],
                    rebound["frontier_host_failure_fact_set_sha256"],
                )
                self.assertEqual(
                    directive_ref, materialization["selection_directives"],
                )
                self.assertTrue(materialization["selection_ready"])
                self.assertTrue(context_retrieval_ready({"retrieval": rebound}))

                if case == "expansion-query":
                    self.assertEqual(
                        sorted(refs.values()),
                        directives["allowed_deferred_fact_refs"],
                    )
                    self.assertEqual([], host_refs)
                else:
                    self.assertEqual([], selected)
                    self.assertEqual(1, len(host_refs))
                    self.assertEqual("host_verifier_failure", payload["facts"][0]["kind"])

    def test_blocked_baseline_remains_fail_closed_after_materialization(self) -> None:
        bundle, _refs, entries, retrieval = context_fixture(blocked=True)
        failed = failure_evidence()
        query = build_context_expansion_query(
            run_id=RUN_ID,
            unit_id=TARGET,
            query_epoch=3,
            requests=[{
                "family": "verified-failure-fact",
                "failure_evidence_sha256": failed["sha256"],
            }],
        )
        directives = derive_directives(bundle, query, [failed])
        directive_ref = write_frontier_cas_json(
            self.root, DIRECTIVE_KIND, directives,
        )

        pages, rebound, materialization = (
            materialize_context_frontier_wave_selection(
                directives,
                directives_reference=directive_ref,
                context_bundle=bundle,
                entries=entries,
                retrieval=retrieval,
            )
        )

        self.assertEqual("blocked", retrieval["selection_status"])
        self.assertEqual("blocked", rebound["selection_status"])
        self.assertEqual(
            retrieval["selection_blockers"], rebound["selection_blockers"],
        )
        self.assertGreater(rebound["unresolved_required_fact_count"], 0)
        self.assertFalse(materialization["selection_ready"])
        self.assertFalse(context_retrieval_ready({"retrieval": rebound}))
        self.assertEqual(CLAIM_BOUNDARY, materialization["claim_boundary"])
        self.assertEqual(
            [directives["host_failure_facts"][0]["sha256"]],
            pages[-1]["fact_refs"],
        )

    def test_rejects_tampered_directive_and_cas_binding(self) -> None:
        bundle, refs, entries, retrieval = context_fixture()
        query = build_context_expansion_query(
            run_id=RUN_ID,
            unit_id=TARGET,
            query_epoch=4,
            requests=[{
                "family": "include-adjacency",
                "anchor_fact_sha256": refs["include"],
            }],
        )
        directives = derive_directives(bundle, query, [])
        directive_ref = write_frontier_cas_json(
            self.root, DIRECTIVE_KIND, directives,
        )

        def materialize(value: dict, reference: dict) -> None:
            materialize_context_frontier_wave_selection(
                value,
                directives_reference=reference,
                context_bundle=bundle,
                entries=entries,
                retrieval=retrieval,
            )

        stale_digest = deepcopy(directives)
        stale_digest["selection_ready"] = True
        with self.assertRaisesRegex(ValueError, "directives header is invalid"):
            materialize(stale_digest, directive_ref)

        stale_cas = deepcopy(directives)
        stale_cas["wave_index"] += 1
        stale_cas_payload = {
            key: value for key, value in stale_cas.items() if key != "sha256"
        }
        stale_cas["sha256"] = content_sha256(stale_cas_payload)
        with self.assertRaisesRegex(ValueError, "CAS reference binding drifted"):
            materialize(stale_cas, directive_ref)

        drifted_reference = {
            **directive_ref,
            "sha256": digest("tampered-directive-cas"),
        }
        with self.assertRaisesRegex(ValueError, "CAS reference binding drifted"):
            materialize(directives, drifted_reference)


if __name__ == "__main__":
    unittest.main()
