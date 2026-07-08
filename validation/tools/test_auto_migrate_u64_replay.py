import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("auto_migrate_u64_under_test", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AutoMigrateU64ReplayTests(unittest.TestCase):
    def test_unsigned_long_single_return_value_generates_u64_replay_cases(self) -> None:
        auto_migrate = load_auto_migrate_module()
        spec = {
            "function_name": "target_abi_ulong_identity",
            "c_boundary": {
                "signatures": [
                    {
                        "function": "target_abi_ulong_identity",
                        "return_type": "unsigned long",
                        "parameters": [
                            {
                                "name": "value",
                                "c_type": "unsigned long",
                                "direction": "input",
                            }
                        ],
                    }
                ]
            },
            "fixture_contract": {
                "behavior_fields": ["return_value", "status"],
            },
        }
        fixture_binding = {
            "case_count": 2,
            "case_bindings": [
                {
                    "id": "uint32-plus-one",
                    "input_payload": {"value": 4294967296},
                    "expected_outputs": {
                        "return_value": 4294967296,
                        "status": "ok",
                    },
                },
                {
                    "id": "ulong-max",
                    "input_payload": {"value": 18446744073709551615},
                    "expected_outputs": {
                        "return_value": 18446744073709551615,
                        "status": "ok",
                    },
                },
            ],
        }

        self.assertTrue(auto_migrate.single_u64_return_value_replay_supported(spec))
        source = auto_migrate.rust_replay_fixture_cases_source(spec, fixture_binding)

        self.assertIn("value: u64", source)
        self.assertIn("return_value: u64", source)
        self.assertIn("value: 4294967296u64", source)
        self.assertIn("return_value: 4294967296u64", source)
        self.assertIn("value: u64::MAX", source)
        self.assertIn("return_value: u64::MAX", source)
        self.assertIn("let actual = target_abi_ulong_identity(case.value);", source)
        self.assertIn('assert_eq!(case.status, "ok", "{} fixture status drifted", case.id);', source)


if __name__ == "__main__":
    unittest.main()
