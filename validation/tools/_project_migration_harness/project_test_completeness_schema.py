from __future__ import annotations


CLAIM_BOUNDARY = {
    "semantic_gate": False, "translation_coverage_numerator": 0,
}
TOP_KEYS = {
    "schema_version", "artifact_kind", "status", "inventory_sha256",
    "mapping_sha256", "rust_project_ir_sha256", "case_ids",
    "source_target_ids", "counts", "blockers", "claim_boundary",
    "completeness_sha256",
}
COUNT_KEYS = {
    "inventory_case_count", "mapped_case_count", "inventory_target_count",
    "mapped_target_count", "silent_skip_count", "zero_test_mapping_count",
    "required_test_omission_count", "extra_mapped_test_count",
    "duplicate_mapped_test_count", "required_target_omission_count",
    "extra_mapped_target_count", "duplicate_rust_target_binding_count",
    "duplicate_source_target_binding_count", "source_target_binding_drift_count",
}
MAPPING_KEYS = {
    "source_target_id", "source_executable_paths", "test_ids",
    "rust_package_id", "rust_package_name", "rust_target_id",
    "rust_target_name",
}


__all__ = ["CLAIM_BOUNDARY", "COUNT_KEYS", "MAPPING_KEYS", "TOP_KEYS"]
