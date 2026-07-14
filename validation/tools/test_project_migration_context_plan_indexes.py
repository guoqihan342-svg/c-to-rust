from __future__ import annotations

import copy
import gc
import hashlib
import json
from pathlib import Path
import tempfile
import tracemalloc
import unittest

from validation.tools._project_migration_harness.context_index_store import (
    prepare_context_indexes,
)
from validation.tools._project_migration_harness.context_plan_indexes import (
    prepare_plan_context_indexes,
)
from validation.tools._project_migration_harness.portfolio import (
    PortfolioError,
    plan_portfolio,
)


class ProjectMigrationContextPlanIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="context-plan-index-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_streamed_plan_indexes_match_retained_contract(self) -> None:
        bundle = _bundle(3, content_bytes=32)
        retained, _payloads, prepared = prepare_context_indexes(
            bundle, out_root_rel="target/run",
        )

        streamed, proofs, summary = prepare_plan_context_indexes(
            bundle, out_root=self.root, out_root_rel="target/run",
            **_budgets(),
        )

        self.assertEqual(retained, streamed)
        self.assertEqual(
            {"logical_page_count": 3, "logical_group_count": 3}, summary,
        )
        self.assertFalse((self.root / "context/pages").exists())
        for scc_id, catalog in prepared["catalogs"].items():
            path = self.root / catalog["local_reference"]["path"]
            self.assertEqual(catalog["payload"], path.read_bytes())
        result = _plan(streamed, proofs)
        self.assertEqual(3, len(result["ledger_units"]))

    def test_proofs_are_host_issued_and_exactly_cover_dag_pages(self) -> None:
        bindings, proofs, _summary = prepare_plan_context_indexes(
            _bundle(2), out_root=self.root, out_root_rel="target/run",
            **_budgets(),
        )
        with self.assertRaisesRegex(PortfolioError, "not host-issued"):
            _plan(bindings, {"references": []})

        missing = {"group-0": copy.deepcopy(bindings["group-0"])}
        with self.assertRaisesRegex(PortfolioError, "proof coverage drifted"):
            _plan(missing, proofs)

        drifted = copy.deepcopy(bindings)
        drifted["group-0"]["pages"][0]["sha256"] = "f" * 64
        with self.assertRaisesRegex(PortfolioError, "proof binding drifted"):
            _plan(drifted, proofs)

    def test_group_proof_rejects_metadata_and_cross_group_swaps(self) -> None:
        bindings, proofs, _summary = prepare_plan_context_indexes(
            _bundle(2), out_root=self.root, out_root_rel="target/run",
            **_budgets(),
        )
        mutations = []
        page_id = copy.deepcopy(bindings)
        page_id["group-0"]["pages"][0]["page_id"] = "page-forged"
        mutations.append(page_id)
        catalog = copy.deepcopy(bindings)
        catalog["group-0"]["catalog"]["sha256"] = "e" * 64
        mutations.append(catalog)
        swapped = copy.deepcopy(bindings)
        swapped["group-0"]["pages"], swapped["group-1"]["pages"] = (
            swapped["group-1"]["pages"], swapped["group-0"]["pages"],
        )
        mutations.append(swapped)

        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                with self.assertRaisesRegex(PortfolioError, "proof binding drifted"):
                    _plan(mutation, proofs)

    def test_budget_and_page_metadata_fail_before_catalog_write(self) -> None:
        oversized = self.root / "oversized"
        with self.assertRaisesRegex(ValueError, "exceeds byte budget"):
            prepare_plan_context_indexes(
                _bundle(1, content_bytes=8 * 1024),
                out_root=oversized, out_root_rel="target/oversized",
                max_page_bytes=1024,
            )
        self.assertFalse((oversized / "context/catalog").exists())

        for field, value in (("page_id", ""), ("materialized_bytes", 0)):
            with self.subTest(field=field):
                bundle = _bundle(1)
                bundle["pages"][0][field] = value
                output = self.root / field
                with self.assertRaises(ValueError):
                    prepare_plan_context_indexes(
                        bundle, out_root=output,
                        out_root_rel=f"target/{field}", **_budgets(),
                    )
                self.assertFalse((output / "context/catalog").exists())

    def test_late_group_budget_failure_leaves_no_sticky_catalogs(self) -> None:
        output = self.root / "late-budget"
        with self.assertRaisesRegex(ValueError, "exceeds byte budget"):
            prepare_plan_context_indexes(
                _bundle(2, content_bytes=[16, 8 * 1024]),
                out_root=output, out_root_rel="target/late-budget",
                max_page_bytes=1024,
            )
        self.assertFalse((output / "context/catalog").exists())

        contexts, _proofs, summary = prepare_plan_context_indexes(
            _bundle(2), out_root=output,
            out_root_rel="target/late-budget", **_budgets(),
        )
        self.assertEqual({"group-0", "group-1"}, set(contexts))
        self.assertEqual(2, summary["logical_group_count"])

    def test_proofs_cannot_be_combined_with_unverified_payloads(self) -> None:
        bindings, proofs, _summary = prepare_plan_context_indexes(
            _bundle(1), out_root=self.root, out_root_rel="target/run",
            **_budgets(),
        )
        dag = _dag(bindings)
        page = bindings["group-0"]["pages"][0]
        with self.assertRaisesRegex(PortfolioError, "cannot be combined"):
            plan_portfolio(
                dag, out_root="target/run", max_concurrency=2,
                max_attempts=3, context_byte_budget=2_000_000,
                context_token_budget=2_000_000,
                context_page_payloads={page["path"]: b"untrusted"},
                context_page_proof_set=proofs,
            )

    def test_group_page_limit_remains_a_blocked_reason(self) -> None:
        bundle = _bundle(2)
        bundle["pages"][1]["scc_id"] = "group-0"
        bundle["pages"][1]["part_index"] = 1
        _refresh_page_metadata(bundle, 1)
        bindings, proofs, _summary = prepare_plan_context_indexes(
            bundle, out_root=self.root, out_root_rel="target/run",
            **_budgets(),
        )

        result = plan_portfolio(
            _dag(bindings), out_root="target/run", max_concurrency=2,
            max_attempts=3, context_byte_budget=2_000_000,
            context_token_budget=2_000_000, context_page_limit=1,
            context_page_proof_set=proofs,
        )

        self.assertIn(
            "context_page_limit_exceeded", result["blocked_groups"][0]["reasons"],
        )

    def test_streamed_plan_index_peak_is_bounded_by_one_group(self) -> None:
        bundle = _bundle(12, content_bytes=256 * 1024)
        retained_peak = _peak(lambda: prepare_context_indexes(
            bundle, out_root_rel="target/retained",
        ))
        streamed_peak = _peak(lambda: prepare_plan_context_indexes(
            bundle, out_root=self.root / "streamed",
            out_root_rel="target/streamed",
            **_budgets(),
        ))

        self.assertLess(streamed_peak * 2, retained_peak)


def _plan(bindings: dict[str, dict], proofs: object) -> dict:
    return plan_portfolio(
        _dag(bindings), out_root="target/run", max_concurrency=2,
        max_attempts=3, context_byte_budget=2_000_000,
        context_token_budget=2_000_000, context_page_limit=32,
        context_page_proof_set=proofs,
    )


def _budgets() -> dict[str, int]:
    return {"max_page_bytes": 2_000_000}


def _dag(bindings: dict[str, dict]) -> dict:
    group_ids = sorted(bindings)
    return {
        "run_id": "run", "project_key": "project",
        "groups": [
            {
                "group_id": group_id,
                "classification": "independent",
                "structurally_eligible": True,
                "dependencies": [],
                "context_pack": bindings[group_id],
            }
            for group_id in group_ids
        ],
        "waves": [{"wave_index": 0, "group_ids": group_ids}],
    }


def _bundle(
    group_count: int, *, content_bytes: int | list[int] = 16,
) -> dict:
    facts: dict[str, dict] = {}
    pages = []
    for index in range(group_count):
        digest = hashlib.sha256(f"fact-{index}".encode()).hexdigest()
        size = content_bytes[index] if isinstance(content_bytes, list) else content_bytes
        fact = {
            "kind": "compile_unit",
            "payload": {
                "unit_id": f"unit-{index}",
                "compiler": "cc", "language": "c",
                "working_directory": ".", "redacted_define_count": 0,
                "content": chr(65 + index % 26) * size,
            },
        }
        facts[digest] = fact
        materialized = {
            "wave_index": 0, "scc_id": f"group-{index}",
            "classification": "independent", "dependency_count": 0,
            "dependency_set_sha256": hashlib.sha256(b"[]").hexdigest(),
            "part_index": 0,
            "facts": [{"sha256": digest, **fact}],
        }
        compact = json.dumps(
            materialized, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode()
        pages.append({
            **{key: materialized[key] for key in (
                "wave_index", "scc_id", "classification", "dependency_count",
                "dependency_set_sha256", "part_index",
            )},
            "page_id": f"page-{index}", "fact_refs": [digest],
            "materialized_sha256": hashlib.sha256(compact).hexdigest(),
            "materialized_bytes": len(compact),
            "estimated_tokens": len(compact),
        })
    return {
        "shared_facts": facts, "pages": pages,
        "model_input_policy": {}, "claim_boundary": {},
    }


def _refresh_page_metadata(bundle: dict, index: int) -> None:
    page = bundle["pages"][index]
    fields = (
        "wave_index", "scc_id", "classification", "dependency_count",
        "dependency_set_sha256", "part_index",
    )
    materialized = {
        **{key: page[key] for key in fields},
        "facts": [
            {"sha256": digest, **bundle["shared_facts"][digest]}
            for digest in page["fact_refs"]
        ],
    }
    compact = json.dumps(
        materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()
    page["materialized_sha256"] = hashlib.sha256(compact).hexdigest()
    page["materialized_bytes"] = len(compact)
    page["estimated_tokens"] = len(compact)


def _peak(callback) -> int:
    gc.collect()
    tracemalloc.start()
    try:
        callback()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
        gc.collect()


if __name__ == "__main__":
    unittest.main()
