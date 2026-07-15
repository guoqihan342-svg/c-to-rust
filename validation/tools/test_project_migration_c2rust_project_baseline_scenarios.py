from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import canonical_json_bytes
from validation.tools._project_migration_harness.c2rust_project_baseline_scenarios import (
    BaselineScenarioContractError, load_baseline_scenarios,
)


class BaselineScenarioContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="c2rust-scenarios-")
        self.repo = Path(self.temporary.name) / "repo"
        (self.repo / "build/tests").mkdir(parents=True)
        (self.repo / "fixtures").mkdir()
        self.contract = self.repo / "build/scenarios.json"
        self.wrappers = [
            {"name": "bin-a", "translated_module_path": "src/a.rs"},
            {"name": "bin-b", "translated_module_path": "src/b.rs"},
        ]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_multiple_scenarios_and_compile_only_are_canonical(self) -> None:
        self._write({
            "schema_version": 1,
            "wrappers": [
                {
                    "translated_module_path": "src/b.rs",
                    "execution_mode": "compile_only",
                },
                {
                    "translated_module_path": "src/a.rs",
                    "execution_mode": "scenarios",
                    "scenarios": [
                        self._scenario("case-z", ["fixtures/input.xml"]),
                        self._scenario("case-a", [], stdin="<root/>\n"),
                    ],
                },
            ],
        })

        loaded = load_baseline_scenarios(
            self.repo, Path("build/scenarios.json"), self.wrappers,
        )

        self.assertEqual(2, loaded.scenario_count)
        self.assertEqual(
            ["src/a.rs", "src/b.rs"],
            [item.translated_module_path for item in loaded.wrappers],
        )
        self.assertEqual(
            ["case-a", "case-z"],
            [item.id for item in loaded.wrappers[0].scenarios],
        )
        self.assertEqual("compile_only", loaded.wrappers[1].execution_mode)
        self.assertEqual(
            loaded.canonical_payload,
            canonical_json_bytes(loaded.to_payload()),
        )

    def test_input_order_does_not_change_contract_identity(self) -> None:
        first = self._payload()
        self._write(first)
        one = load_baseline_scenarios(self.repo, self.contract, self.wrappers)
        first["wrappers"].reverse()
        first["wrappers"][1]["scenarios"].reverse()
        self._write(first)
        two = load_baseline_scenarios(self.repo, self.contract, self.wrappers)
        self.assertEqual(one.content_sha256, two.content_sha256)
        self.assertEqual(one.canonical_payload, two.canonical_payload)

    def test_wrapper_mapping_must_be_exact_and_complete(self) -> None:
        cases = {
            "incomplete": {
                "schema_version": 1,
                "wrappers": [self._compile_only("src/a.rs")],
            },
            "unknown": {
                "schema_version": 1,
                "wrappers": [
                    self._compile_only("src/a.rs"),
                    self._compile_only("src/unknown.rs"),
                ],
            },
            "duplicate": {
                "schema_version": 1,
                "wrappers": [
                    self._compile_only("src/a.rs"),
                    self._compile_only("src/a.rs"),
                ],
            },
        }
        for label, payload in cases.items():
            with self.subTest(label=label):
                self._write(payload)
                with self.assertRaisesRegex(
                    BaselineScenarioContractError, "wrapper_mapping",
                ):
                    load_baseline_scenarios(
                        self.repo, self.contract, self.wrappers,
                    )

    def test_duplicate_scenario_ids_and_unknown_fields_are_rejected(self) -> None:
        payload = self._payload()
        payload["wrappers"][0]["scenarios"][1]["id"] = "case-a"
        self._write(payload)
        with self.assertRaisesRegex(BaselineScenarioContractError, "id_duplicate"):
            load_baseline_scenarios(self.repo, self.contract, self.wrappers)
        payload = self._payload()
        payload["wrappers"][0]["unexpected"] = True
        self._write(payload)
        with self.assertRaisesRegex(BaselineScenarioContractError, "fields_invalid"):
            load_baseline_scenarios(self.repo, self.contract, self.wrappers)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        self.contract.write_text(
            '{"schema_version":1,"schema_version":1,"wrappers":[]}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(BaselineScenarioContractError, "duplicate_key"):
            load_baseline_scenarios(self.repo, self.contract, self.wrappers)

    def test_working_directory_and_contract_path_cannot_escape(self) -> None:
        payload = self._payload()
        payload["wrappers"][0]["scenarios"][0]["working_directory"] = "../outside"
        self._write(payload)
        with self.assertRaisesRegex(BaselineScenarioContractError, "relative_path"):
            load_baseline_scenarios(self.repo, self.contract, self.wrappers)
        outside = self.repo.parent / "outside.json"
        outside.write_text(json.dumps(self._payload()), encoding="utf-8")
        with self.assertRaisesRegex(BaselineScenarioContractError, "contract_path"):
            load_baseline_scenarios(self.repo, outside, self.wrappers)

    def test_reserved_environment_and_nul_argv_are_rejected(self) -> None:
        payload = self._payload()
        payload["wrappers"][0]["scenarios"][0]["environment"] = {
            "PATH": "fixtures",
        }
        self._write(payload)
        with self.assertRaisesRegex(BaselineScenarioContractError, "environment_key"):
            load_baseline_scenarios(self.repo, self.contract, self.wrappers)
        payload = self._payload()
        payload["wrappers"][0]["scenarios"][0]["argv"] = ["bad\0arg"]
        self._write(payload)
        with self.assertRaisesRegex(BaselineScenarioContractError, "argv_invalid"):
            load_baseline_scenarios(self.repo, self.contract, self.wrappers)

    def _payload(self) -> dict:
        return {
            "schema_version": 1,
            "wrappers": [
                {
                    "translated_module_path": "src/a.rs",
                    "execution_mode": "scenarios",
                    "scenarios": [
                        self._scenario("case-a", []),
                        self._scenario("case-z", ["fixtures/input.xml"]),
                    ],
                },
                self._compile_only("src/b.rs"),
            ],
        }

    def _scenario(
        self, identifier: str, argv: list[str], *, stdin: str = "",
    ) -> dict:
        return {
            "id": identifier,
            "argv": argv,
            "working_directory": "build/tests",
            "environment": {"CASE_MODE": "strict"},
            "stdin_utf8": stdin,
            "expected_exit": 0,
            "timeout_seconds": 30,
        }

    @staticmethod
    def _compile_only(path: str) -> dict:
        return {
            "translated_module_path": path,
            "execution_mode": "compile_only",
        }

    def _write(self, value: dict) -> None:
        self.contract.write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
