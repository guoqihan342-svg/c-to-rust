from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation.tools._project_migration_harness.context_index_store import (
    materialize_selected_context_indexes, prepare_context_indexes,
)


class ProjectMigrationContextIndexStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="context-store-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_only_selected_group_pages_are_materialized(self) -> None:
        facts = {
            "a" * 64: {"kind": "compile_unit", "payload": {
                "unit_id": "unit", "compiler": "cc", "language": "c",
                "working_directory": ".", "redacted_define_count": 0,
            }}
        }
        pages = [
            self.page("selected", "selected-page", "a" * 64, facts),
            self.page("blocked", "blocked-page", "a" * 64, facts),
        ]
        bundle = {
            "shared_facts": facts, "pages": pages,
            "model_input_policy": {}, "claim_boundary": {},
        }

        contexts, payloads, prepared = prepare_context_indexes(
            bundle, out_root_rel="target/run"
        )
        refs, report_ref = materialize_selected_context_indexes(
            prepared, out_root=self.root, selected_scc_ids=["selected"]
        )

        self.assertEqual({"selected", "blocked"}, set(contexts))
        self.assertEqual(2, len(payloads))
        self.assertEqual(1, len(refs))
        self.assertTrue((self.root / "context/pages/selected-page.json").is_file())
        self.assertFalse((self.root / "context/pages/blocked-page.json").exists())
        report = json.loads((self.root / report_ref["path"]).read_text())
        self.assertEqual(1, report["materialized_page_count"])
        self.assertEqual(1, report["omitted_blocked_page_count"])

    def test_selection_receipt_is_bound_to_stable_materialized_pages(self) -> None:
        bundle = self.bundle("cc")
        first = self.prepare_with_receipt(bundle, "a" * 64, "target/first")
        relocated = self.prepare_with_receipt(bundle, "a" * 64, "other/root")
        page_changed = self.prepare_with_receipt(
            self.bundle("clang"), "a" * 64, "target/first"
        )
        receipt_changed = self.prepare_with_receipt(
            bundle, "b" * 64, "target/first"
        )

        first_retrieval = first[0]["selected"]["retrieval"]
        self.assertEqual(first_retrieval, relocated[0]["selected"]["retrieval"])
        self.assertEqual(
            first_retrieval["materialized_page_set_sha256"],
            receipt_changed[0]["selected"]["retrieval"][
                "materialized_page_set_sha256"
            ],
        )
        self.assertNotEqual(
            first_retrieval["materialized_page_set_sha256"],
            page_changed[0]["selected"]["retrieval"][
                "materialized_page_set_sha256"
            ],
        )
        self.assertNotEqual(
            first_retrieval["selection_materialization_sha256"],
            page_changed[0]["selected"]["retrieval"][
                "selection_materialization_sha256"
            ],
        )
        self.assertNotEqual(
            first_retrieval["selection_materialization_sha256"],
            receipt_changed[0]["selected"]["retrieval"][
                "selection_materialization_sha256"
            ],
        )

        materialize_selected_context_indexes(
            first[2], out_root=self.root, selected_scc_ids=["selected"]
        )
        group = json.loads(
            (self.root / "context/groups/selected.json").read_text()
        )
        for key in (
            "materialized_page_set_sha256", "selection_materialization_sha256",
        ):
            self.assertEqual(first_retrieval[key], group["retrieval"][key])

    def test_materialization_fails_closed_on_page_or_receipt_drift(self) -> None:
        for drift in ("page", "receipt"):
            with self.subTest(drift=drift):
                prepared = self.prepare_with_receipt(
                    self.bundle("cc"), "a" * 64, "target/run"
                )[2]
                if drift == "page":
                    prepared["by_scc"]["selected"][0]["page_metadata"][
                        "page_id"
                    ] = "changed-page"
                else:
                    prepared["retrieval"]["selected"][
                        "selection_receipt_sha256"
                    ] = "b" * 64
                with self.assertRaisesRegex(ValueError, "materialization drifted"):
                    materialize_selected_context_indexes(
                        prepared, out_root=self.root / drift,
                        selected_scc_ids=["selected"],
                    )

    def bundle(self, compiler: str) -> dict[str, object]:
        facts = {
            "a" * 64: {"kind": "compile_unit", "payload": {
                "unit_id": "unit", "compiler": compiler, "language": "c",
                "working_directory": ".", "redacted_define_count": 0,
            }}
        }
        return {
            "shared_facts": facts,
            "pages": [self.page("selected", "selected-page", "a" * 64, facts)],
            "model_input_policy": {}, "claim_boundary": {},
        }

    @staticmethod
    def prepare_with_receipt(
        bundle: dict[str, object], receipt: str, out_root_rel: str,
    ) -> tuple[dict, dict, dict]:
        retrieval = {
            "selected": {
                "scc_id": "selected", "selection_receipt_sha256": receipt,
                "selection_status": "ready", "selection_blockers": [],
                "fact_refs": [],
            }
        }
        with patch(
            "validation.tools._project_migration_harness.context_index_store."
            "validate_retrieval_bundle",
            return_value=retrieval,
        ):
            return prepare_context_indexes(bundle, out_root_rel=out_root_rel)

    @staticmethod
    def page(
        scc_id: str, page_id: str, digest: str, facts: dict[str, object]
    ) -> dict[str, object]:
        materialized = {
            "wave_index": 0, "scc_id": scc_id,
            "classification": "independent", "dependency_count": 0,
            "dependency_set_sha256": hashlib.sha256(b"[]").hexdigest(),
            "part_index": 0,
            "facts": [{"sha256": digest, **facts[digest]}],
        }
        compact = json.dumps(
            materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return {
            **{key: materialized[key] for key in (
                "wave_index", "scc_id", "classification", "dependency_count",
                "dependency_set_sha256", "part_index",
            )},
            "page_id": page_id, "fact_refs": [digest],
            "materialized_sha256": hashlib.sha256(compact).hexdigest(),
            "materialized_bytes": len(compact), "estimated_tokens": len(compact),
        }


if __name__ == "__main__":
    unittest.main()
