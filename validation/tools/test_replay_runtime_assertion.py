from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools.auto_migrate import run_generated_rust_replay_once
from validation.tools.replay_assertion_inventory import (
    ASSERTION_MARKER_PREFIX,
    assertion_id_for,
    build_replay_assertion_inventory,
    validate_inventory_fixture_identity,
    validate_inventory_replay_source,
    validated_runtime_localization,
)
from validation.tools.replay_call_plan import (
    build_replay_call_plan,
    render_declarative_replay_cases,
    replay_call_plan_marker,
)
from validation.tools.replay_runtime_assertion import (
    authenticate_runtime_assertion_id,
    localized_runtime_assertion_details,
    runtime_assertion_failure_envelope,
)
from validation.tools import test_replay_call_plan as plan_test_support


class ReplayRuntimeAssertionTests(unittest.TestCase):
    def build_plan(self, root: Path) -> tuple[dict, dict, str]:
        spec = plan_test_support.ReplayCallPlanTests.report_spec()
        spec["fixture_contract"]["path"] = "missing-inline-fixture.json"
        spec["fixture_contract"]["cases"] = [
            {
                "id": "alpha-case",
                "input_ref": "inline",
                "inputs": {"ip": "127.0.0.1", "port": 80},
                "expected_outputs": {"code": 0, "family": 2},
            },
            {
                "id": "beta-case",
                "input_ref": "inline",
                "inputs": {"ip": "bad", "port": 81},
                "expected_outputs": {"code": -1, "family": 2},
            },
        ]
        plan = build_replay_call_plan(spec, root)
        inventory = build_replay_assertion_inventory(plan)
        rendered = render_declarative_replay_cases(spec, plan, root)
        replay_source = (
            replay_call_plan_marker(plan)
            + "#[test]\n"
            + "fn replay_contract() {\n"
            + rendered
            + "}\n"
        )
        validate_inventory_replay_source(plan, inventory, replay_source)
        return plan, inventory, replay_source

    def test_multi_case_multi_field_inventory_is_opaque_and_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory(prefix="replay-assertion-inventory-") as tmp:
            _plan, inventory, replay_source = self.build_plan(Path(tmp))

            self.assertEqual(len(inventory["assertions"]), 4)
            self.assertEqual(
                {
                    (item["case_id"], item["observable_field"])
                    for item in inventory["assertions"]
                },
                {
                    ("alpha-case", "code"),
                    ("alpha-case", "family"),
                    ("beta-case", "code"),
                    ("beta-case", "family"),
                },
            )
            for item in inventory["assertions"]:
                marker = ASSERTION_MARKER_PREFIX + item["assertion_id"]
                self.assertEqual(replay_source.count(marker), 1)
                marker_line = next(
                    line for line in replay_source.splitlines() if marker in line
                )
                self.assertNotIn(item["case_id"], marker_line)
                self.assertNotIn(item["observable_field"], marker_line)

    def test_real_runtime_panic_authenticates_only_the_replay_owned_marker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="replay-assertion-runtime-") as tmp:
            root = Path(tmp)
            _plan, inventory, replay_source = self.build_plan(root)
            candidate_source = (
                "pub struct AddrReport { pub code: i32, pub family: u16 }\n"
                "pub fn parse_addr(_ip: &str, _port: i32) -> AddrReport {\n"
                "    AddrReport { code: 99, family: 2 }\n"
                "}\n"
            )
            candidate = root / "candidate.rs"
            replay = root / "replay.rs"
            candidate.write_text(candidate_source, encoding="utf-8")
            replay.write_text(replay_source, encoding="utf-8")

            result = run_generated_rust_replay_once(candidate, replay)
            expected_id = assertion_id_for(inventory, "alpha-case", "code")

            self.assertEqual(result["phase"], "run")
            self.assertNotEqual(result["run_returncode"], 0)
            self.assertEqual(result["runtime_assertion_id"], expected_id)
            envelope = runtime_assertion_failure_envelope(expected_id, inventory)
            self.assertEqual(
                localized_runtime_assertion_details(envelope, inventory),
                {"case_id": "alpha-case", "observable_field": "code"},
            )
            serialized = json.dumps(envelope)
            for forbidden in ("expected", "actual", "127.0.0.1", "panic", "line"):
                self.assertNotIn(forbidden, serialized)

    def test_spoofed_location_duplicate_marker_and_inventory_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="replay-assertion-spoof-") as tmp:
            root = Path(tmp)
            _plan, inventory, replay_source = self.build_plan(root)
            assertion_id = inventory["assertions"][0]["assertion_id"]
            marker = ASSERTION_MARKER_PREFIX + assertion_id
            marker_line = next(
                index
                for index, line in enumerate(replay_source.splitlines(), 1)
                if marker in line
            )
            candidate = "pub fn candidate() {}\n"
            combined_line = (candidate + "\n").count("\n") + marker_line
            stderr = (
                "thread 'replay_contract' panicked at "
                f"<generated-replay>/generated_replay.rs:{combined_line}:9:\n{marker}\n"
            )

            self.assertEqual(
                authenticate_runtime_assertion_id(candidate, replay_source, stderr),
                assertion_id,
            )
            self.assertEqual(
                authenticate_runtime_assertion_id(
                    candidate,
                    replay_source,
                    stderr.replace(
                        "thread 'replay_contract'",
                        "thread 'replay_contract' (9123)",
                    ),
                ),
                assertion_id,
            )
            self.assertEqual(
                authenticate_runtime_assertion_id(
                    candidate,
                    replay_source,
                    stderr.replace(
                        "<generated-replay>/generated_replay.rs",
                        r"<generated-replay>\generated_replay.rs",
                    ),
                ),
                assertion_id,
            )
            self.assertIsNone(
                authenticate_runtime_assertion_id(
                    candidate,
                    replay_source,
                    stderr.replace("<generated-replay>", "C:/host/private"),
                )
            )
            self.assertIsNone(
                authenticate_runtime_assertion_id(marker + "\n", replay_source, stderr)
            )
            self.assertIsNone(
                authenticate_runtime_assertion_id(
                    candidate, replay_source + f"// {marker}\n", stderr
                )
            )
            self.assertIsNone(
                authenticate_runtime_assertion_id(
                    candidate, replay_source, stderr.replace(f":{combined_line}:", ":1:")
                )
            )
            drifted = copy.deepcopy(inventory)
            drifted["plan_sha256"] = "f" * 64
            self.assertIsNone(runtime_assertion_failure_envelope(assertion_id, drifted))

    def test_fixture_identity_and_repair_detail_contracts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="replay-assertion-fixture-") as tmp:
            _plan, inventory, _source = self.build_plan(Path(tmp))
            identity = {
                "cases": [{"id": "alpha-case"}, {"id": "beta-case"}],
                "behavior_fields": ["code", "family"],
            }
            validate_inventory_fixture_identity(inventory, identity)
            with self.assertRaisesRegex(ValueError, "fixture identity"):
                validate_inventory_fixture_identity(
                    inventory,
                    {**identity, "cases": list(reversed(identity["cases"]))},
                )
            self.assertEqual(
                validated_runtime_localization(
                    {"case_id": "renamed-case", "observable_field": "renamed_field"}
                ),
                {"case_id": "renamed-case", "observable_field": "renamed_field"},
            )
            self.assertIsNone(
                validated_runtime_localization(
                    {
                        "case_id": "renamed-case",
                        "observable_field": "renamed_field",
                        "expected": "must-not-cross",
                    }
                )
            )


if __name__ == "__main__":
    unittest.main()
