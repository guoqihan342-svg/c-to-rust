from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validation.tools._project_migration_harness.artifacts import (
    content_sha256,
    write_json_artifact,
)
from validation.tools._project_migration_harness.model_safe_test_contract import (
    build_model_safe_test_contract,
    validate_model_safe_test_contract,
)
from validation.tools._project_migration_harness.model_safe_test_contract_bindings import (
    materialize_model_safe_test_contracts,
    portfolio_test_contract_references,
)
from validation.tools._project_migration_harness.project_prompt import (
    render_project_worker_prompt,
)
from validation.tools.project_migration_runtime_test_support import RuntimeHarnessCase


class ModelSafeTestContractTests(unittest.TestCase):
    def test_contract_withholds_values_and_filters_by_target_scope(self) -> None:
        for adapter in ("ctest-json-v1", "make-dry-run-v1"):
            with self.subTest(adapter=adapter):
                inventory = test_inventory(adapter=adapter)
                contract = build_model_safe_test_contract(
                    inventory,
                    group_id="unit-a",
                    target_scope=target_scope("target-a"),
                )

                encoded = json.dumps(contract, sort_keys=True)
                self.assertNotIn("literal-secret", encoded)
                self.assertNotIn("environment-secret", encoded)
                self.assertNotIn("unrelated-secret", encoded)
                self.assertEqual(adapter, contract["adapter"])
                self.assertEqual(1, contract["test_count"])
                projected = contract["tests"][0]
                self.assertEqual(
                    ["literal-option", "literal-positional", "repo-path"],
                    projected["argument_shape"],
                )
                self.assertEqual(["MODE"], projected["environment_keys"])
                self.assertEqual(["tests/input.bin"], projected["input_paths"])
                self.assertEqual(contract, validate_model_safe_test_contract(
                    contract, group_id="unit-a",
                ))

    def test_materialization_is_content_bound_and_portfolio_scoped(self) -> None:
        with tempfile.TemporaryDirectory(prefix="model-safe-test-contract-") as raw:
            output = Path(raw)
            bindings, index = materialize_model_safe_test_contracts(
                test_inventory(),
                {"groups": [
                    {"group_id": "unit-a", "target_scope": target_scope("target-a")},
                    {"group_id": "unit-b", "target_scope": target_scope("target-b")},
                ]},
                output=output,
                out_root_rel="target/run",
            )

            references = portfolio_test_contract_references({
                "model_safe_test_contracts": bindings,
            })
            self.assertEqual(["unit-a", "unit-b"], sorted(references))
            self.assertTrue((output / Path(index["path"])).is_file())
            for reference in references.values():
                relative = reference["path"].removeprefix("target/run/")
                payload = (output / Path(relative)).read_bytes()
                self.assertEqual(reference["sha256"], content_sha256(
                    json.loads(payload.decode("utf-8"))
                ))

    def test_object_only_scope_without_reachable_tests_is_accepted(self) -> None:
        empty_scope = {
            "reachable_target_ids": [], "terminal_target_ids": [],
            "scope_sha256": "a" * 64,
        }

        contract = build_model_safe_test_contract(
            test_inventory(), group_id="object-only", target_scope=empty_scope,
        )

        self.assertEqual(0, contract["test_count"])
        self.assertEqual([], contract["tests"])


class ModelSafeTestContractPromptTests(RuntimeHarnessCase):
    def test_hash_bound_contract_reaches_translator_prompt(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        contract = build_model_safe_test_contract(
            test_inventory(),
            group_id=request["group_id"],
            target_scope=target_scope("target-a"),
        )
        reference = write_json_artifact(
            self.harness,
            "target/run/harness/test-contract/current.json",
            contract,
        )
        request["input_facts"]["model_safe_test_contract"] = reference
        base = {
            key: value for key, value in request.items()
            if key not in {"effective_input_sha256", "execution_binding"}
        }
        request["effective_input_sha256"] = content_sha256(base)

        prompt = json.loads(render_project_worker_prompt(
            request, harness_root=self.harness,
        ))

        bound = prompt["bound_inputs"]["model_safe_test_contract"]
        self.assertEqual(contract["contract_sha256"], bound["contract_sha256"])
        encoded = json.dumps(prompt, sort_keys=True)
        self.assertNotIn("literal-secret", encoded)
        self.assertNotIn("environment-secret", encoded)


def test_inventory(adapter: str = "ctest-json-v1") -> dict:
    tests = [
        {
            "test_id": "test-a",
            "source_target_id": "target-a",
            "arguments": [
                {"kind": "literal", "value": "--mode=literal-secret"},
                {"kind": "literal", "value": "literal-secret"},
                {"kind": "repo-path", "path": "tests/input.bin"},
            ],
            "working_directory": "build/tests",
            "environment": {
                "MODE": {"kind": "literal", "value": "environment-secret"},
            },
            "timeout_seconds": 20,
        },
        {
            "test_id": "test-b",
            "source_target_id": "target-b",
            "arguments": [{"kind": "literal", "value": "unrelated-secret"}],
            "working_directory": "build",
            "environment": {},
            "timeout_seconds": 180,
        },
    ]
    payload = {
        "schema_version": 1,
        "artifact_kind": "project-test-inventory",
        "status": "ready",
        "adapter": adapter,
        "tests": tests,
    }
    return {**payload, "inventory_sha256": content_sha256(payload)}


def target_scope(target_id: str) -> dict:
    payload = {
        "reachable_target_ids": [target_id],
        "terminal_target_ids": [target_id],
    }
    return {**payload, "scope_sha256": content_sha256(payload)}


if __name__ == "__main__":
    unittest.main()
