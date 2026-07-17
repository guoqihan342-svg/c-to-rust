from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.rust_project_ir_v3_topology_products import (
    input_occurrence_id,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_validation import (
    module_id_for_target_candidate, validate_rust_project_ir_v3,
)
from validation.tools.test_project_migration_rust_project_ir_v3_validation import (
    _payload, _rehash, _sha,
)
from validation.tools.project_migration_rust_project_ir_v3_link_test_support import (
    attach_link_expectation,
)


class RustProjectIRV3OccurrenceValidationTests(unittest.TestCase):
    def test_explicit_object_occurrence_mapping_is_valid(self) -> None:
        payload = _explicit_payload(["source-a", "source-b"])

        validate_rust_project_ir_v3(payload)

        target, module = payload["targets"][0], payload["modules"][0]
        self.assertEqual(module["source_unit_ids"], [
            item["source_unit_id"] for item in target["input_occurrences"]
        ])
        self.assertEqual({module["module_id"]}, {
            item["module_id"] for item in target["input_occurrences"]
        })

    def test_explicit_occurrence_identity_and_mapping_drift_are_rejected(self) -> None:
        cases = [
            ("identity", "occurrence_id", "input-occurrence-forged",
             "occurrence identity"),
            ("source", "source_unit_id", "source-forged",
             "link object mapping"),
            ("module", "module_id", "module-forged",
             "link object mapping"),
        ]
        for label, field, replacement, error in cases:
            with self.subTest(label=label):
                payload = _explicit_payload(["source-a"])
                payload["targets"][0]["input_occurrences"][0][field] = replacement
                _rehash(payload)
                with self.assertRaisesRegex(ValueError, error):
                    validate_rust_project_ir_v3(payload)

    def test_explicit_object_occurrence_repeats_are_kept_but_gaps_rejected(self) -> None:
        duplicate = _explicit_payload(["source-a"])
        target = duplicate["targets"][0]
        repeated = copy.deepcopy(target["input_occurrences"][0])
        repeated["ordinal"] = 1
        repeated["occurrence_id"] = _occurrence_id(target, 1)
        target["input_occurrences"].append(repeated)
        attach_link_expectation(target)
        _rehash(duplicate)
        validate_rust_project_ir_v3(duplicate)

        gap = _explicit_payload(["source-a", "source-b"])
        target = gap["targets"][0]
        second = target["input_occurrences"][1]
        second["ordinal"] = 2
        second["occurrence_id"] = _occurrence_id(target, 2)
        target["input_occurrences"].insert(1, {
            "ordinal": 1, "occurrence_id": _occurrence_id(target, 1),
            "role": "link-input", "dependency_target_id": "target-a",
            "object_target_id": None, "source_unit_id": None, "module_id": None,
            "binding_sha256": _sha("package-input"),
        })
        _rehash(gap)
        with self.assertRaisesRegex(ValueError, "link input mapping"):
            validate_rust_project_ir_v3(gap)


def _explicit_payload(source_units: list[str]) -> dict:
    payload = _payload()
    target, module = payload["targets"][0], payload["modules"][0]
    module_id = module_id_for_target_candidate(
        module["target_namespace_id"], module["unit_id"],
        module["candidate_sha256"], source_units,
    )
    module["module_id"] = module_id
    module["source_unit_ids"] = list(source_units)
    payload["packages"][0]["module_ids"] = [module_id]
    target["module_ids"] = [module_id]
    target["input_occurrences"] = [{
        "ordinal": ordinal, "occurrence_id": _occurrence_id(target, ordinal),
        "role": "link-input", "dependency_target_id": None,
        "object_target_id": f"object-{source}", "source_unit_id": source,
        "module_id": module_id, "binding_sha256": _sha(f"binding-{source}"),
    } for ordinal, source in enumerate(source_units)]
    attach_link_expectation(target)
    _rehash(payload)
    return payload


def _occurrence_id(target: dict, ordinal: int) -> str:
    return input_occurrence_id(
        target["evidence"]["build_ir_sha256s"][0],
        target["build_ir_target_id"], ordinal,
    )


if __name__ == "__main__":
    unittest.main()
