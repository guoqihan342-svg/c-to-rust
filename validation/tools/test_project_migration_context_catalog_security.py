from __future__ import annotations

import copy
import json
import unittest

from validation.tools._project_migration_harness.context_catalog import (
    validate_context_catalog,
)
from validation.tools._project_migration_harness.context_index_store import (
    prepare_context_indexes,
)
from validation.tools.test_project_migration_context_plan_indexes import _bundle


class ProjectMigrationContextCatalogSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        _contexts, _payloads, prepared = prepare_context_indexes(
            _bundle(1), out_root_rel="target/run",
        )
        encoded = prepared["catalogs"]["group-0"]["payload"]
        self.catalog = json.loads(encoded.decode("utf-8"))

    def test_generated_catalog_reopens(self) -> None:
        self.assertEqual(self.catalog, validate_context_catalog(self.catalog))

    def test_catalog_rejects_cross_scc_payload_and_unsafe_page_path(self) -> None:
        cross_scc = copy.deepcopy(self.catalog)
        cross_scc["pages"][0]["payload"]["scc_id"] = "group-1"
        with self.assertRaisesRegex(ValueError, "metadata is invalid"):
            validate_context_catalog(cross_scc)

        unsafe_path = copy.deepcopy(self.catalog)
        unsafe_path["pages"][0]["reference"]["path"] = "../outside.json"
        with self.assertRaisesRegex(ValueError, "reference is invalid"):
            validate_context_catalog(unsafe_path)

    def test_catalog_rejects_page_identity_fact_and_size_drift(self) -> None:
        mutations = []
        page_id = copy.deepcopy(self.catalog)
        page_id["pages"][0]["page_id"] = "../forged"
        mutations.append(page_id)
        facts = copy.deepcopy(self.catalog)
        facts["pages"][0]["metadata"]["fact_refs"] = ["f" * 64]
        mutations.append(facts)
        size = copy.deepcopy(self.catalog)
        size["pages"][0]["metadata"]["materialized_bytes"] = 0
        mutations.append(size)

        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    validate_context_catalog(mutation)


if __name__ == "__main__":
    unittest.main()
