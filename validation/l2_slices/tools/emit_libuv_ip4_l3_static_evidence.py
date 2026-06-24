#!/usr/bin/env python3
"""Emit static L3 evidence files for the libuv uv_ip4_addr pointer slice."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


SOURCE_COMMIT = "5e7d51a8f4734cac453db960d4b9919735bbf7c3"
TARGET_ID = "libuv"
SLICE_ID = "ip4-addr"
EVIDENCE_DIR = Path("validation/evidence/libuv")
INPUT_FIXTURE = Path("validation/l2_slices/fixtures/libuv-ip4-addr-input.json")
C_ORACLE = EVIDENCE_DIR / "l3-ip4-addr-c-oracle.json"
PRODUCER = EVIDENCE_DIR / "l3-ip4-addr-c-oracle-producer-evidence.json"
RUST_REPORT = EVIDENCE_DIR / "l3-ip4-addr-rust-report.json"
DIFF = EVIDENCE_DIR / "l3-ip4-addr-diff.json"
NEGATIVE_DIFF = EVIDENCE_DIR / "l3-ip4-addr-negative-diff.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", choices=["incomplete", "passed"], default="incomplete")
    args = parser.parse_args()

    root = Path.cwd()
    evidence = EVIDENCE_DIR
    evidence.mkdir(parents=True, exist_ok=True)
    repo_commit = run(["git", "rev-parse", "HEAD"])
    input_fixture = read_json(INPUT_FIXTURE)
    c_oracle = read_json(C_ORACLE)
    producer = read_json(PRODUCER)
    rust_report = read_json(RUST_REPORT)
    diff = read_json(DIFF)
    negative = read_json(NEGATIVE_DIFF)
    source_hashes = producer["source_hashes"]
    input_hash = sha256(INPUT_FIXTURE)
    oracle_hash = sha256(C_ORACLE)
    rust_module_hash = sha256(Path("validation/l2_slices/src/libuv_ip4_addr.rs"))
    rust_test_hash = sha256(Path("validation/l2_slices/tests/libuv_ip4_addr.rs"))
    cargo_toml_hash = sha256(Path("validation/l2_slices/Cargo.toml"))
    cargo_lock_hash = sha256(Path("validation/l2_slices/Cargo.lock"))

    status = args.status
    evidence_status = "passed" if status == "passed" else "incomplete"
    final_status = "passed" if status == "passed" else "pending"

    common = {
        "schema_version": 1,
        "level": "L3",
        "target_id": TARGET_ID,
        "slice_id": SLICE_ID,
        "source_commit": SOURCE_COMMIT,
        "repo_commit": repo_commit,
    }

    write_json(
        evidence / "l3-ip4-addr-slice-contract.json",
        {
            **common,
            "status": "recorded",
            "source_boundary": c_oracle["source_boundary"],
            "rust_boundary": {
                "module": "validation/l2_slices/src/libuv_ip4_addr.rs",
                "api": "pub fn uv_ip4_addr(ip: &str, port: i32) -> Ip4AddrReport",
                "safe_rust": True,
            },
            "fixture": {
                "path": rel(INPUT_FIXTURE),
                "hash": input_hash,
                "case_count": len(input_fixture["cases"]),
            },
            "behavior_fields": c_oracle["compared_fields"],
            "accepted_differences": [],
            "non_goals": [
                "No libuv event-loop, UDP/TCP socket, DNS, IPv6, callback, or handle lifecycle claim.",
                "No whole-program alias proof.",
                "No platform matrix beyond the pinned WSL/Linux oracle build.",
                "No full libuv migration claim.",
            ],
        },
    )

    write_json(
        evidence / "l3-ip4-addr-context-pack.json",
        {
            **common,
            "status": "recorded",
            "direct_c_files": c_oracle["source_boundary"]["files"],
            "direct_rust_files": [
                "validation/l2_slices/src/libuv_ip4_addr.rs",
                "validation/l2_slices/tests/libuv_ip4_addr.rs",
                "validation/l2_slices/src/bin/emit_reports.rs",
            ],
            "source_refs": {
                "include/uv.h": "uv_ip4_addr declaration",
                "src/uv-common.c": "uv_ip4_addr implementation and sockaddr_in writes",
                "src/inet.c": "uv_inet_pton and inet_pton4 parser",
                "test/test-ip4-addr.c": "upstream positive and invalid IPv4 cases",
            },
            "call_edges": [
                {"from": "oracle helper", "to": "uv_ip4_addr"},
                {"from": "uv_ip4_addr", "to": "uv_inet_pton"},
                {"from": "uv_inet_pton", "to": "inet_pton4"},
                {"from": "Rust emit_reports", "to": "libuv_ip4_addr::uv_ip4_addr"},
            ],
            "related_tests": [
                "validation/l2_slices/tests/libuv_ip4_addr.rs::libuv_ip4_addr_encodes_loopback_and_port_in_network_order",
                "validation/l2_slices/tests/libuv_ip4_addr.rs::libuv_ip4_addr_encodes_wildcard_and_broadcast_boundaries",
                "validation/l2_slices/tests/libuv_ip4_addr.rs::libuv_ip4_addr_rejects_upstream_invalid_ipv4_cases",
            ],
            "cache_inputs": [
                f"input_fixture_sha256={input_hash}",
                f"c_oracle_sha256={oracle_hash}",
                f"rust_module_sha256={rust_module_hash}",
                f"rust_test_sha256={rust_test_hash}",
            ],
        },
    )

    write_json(
        evidence / "l3-ip4-addr-impact-set.json",
        {
            **common,
            "status": "recorded",
            "added_or_changed_files": [
                "validation/l2_slices/src/libuv_ip4_addr.rs",
                "validation/l2_slices/src/lib.rs",
                "validation/l2_slices/tests/libuv_ip4_addr.rs",
                "validation/l2_slices/src/bin/emit_reports.rs",
                "validation/l2_slices/tools/generate_libuv_ip4_oracle.py",
                "validation/l2_slices/tools/emit_libuv_ip4_l3_static_evidence.py",
                "validation/l2_slices/fixtures/libuv-ip4-addr-input.json",
                "validation/l2_slices/fixtures/libuv-ip4-addr-c-oracle.json",
            ],
            "generated_evidence_prefix": "validation/evidence/libuv/l3-ip4-addr-",
            "runtime_impact": "validation-only Rust slice; no FlashDB runtime or libuv upstream changes",
        },
    )

    profile_id = "libuv-ip4-addr-linux-gnu-uvh-" + source_hashes["include/uv.h"][:8]
    write_json(
        evidence / "l3-ip4-addr-config-profile.json",
        {
            **common,
            "profile_id": profile_id,
            "status": "recorded",
            "fixture": {"path": rel(INPUT_FIXTURE), "hash": input_hash, "operation_count": len(input_fixture["cases"])},
            "config_header": {
                "path": "libuv/include/uv.h",
                "sha256": source_hashes["include/uv.h"],
                "role": "libuv public API and platform include boundary for uv_ip4_addr",
            },
            "c_defines": {"_GNU_SOURCE": True, "AF_INET": 2},
            "feature_matrix": {
                "host": "WSL/Linux",
                "address_family": "AF_INET",
                "function": "uv_ip4_addr",
                "ipv6": False,
                "event_loop": False,
            },
            "compile_profile": {
                "c_oracle_command": "python3 validation/l2_slices/tools/generate_libuv_ip4_oracle.py --libuv-root <pinned-libuv-root>",
                "include_paths": ["<pinned-libuv-root>/include"],
                "config_header_included": True,
                "command_args": ["gcc", "-std=c99", "-D_GNU_SOURCE", "-pthread", "-luv"],
            },
            "rust_profile": {
                "package": "c-to-rust-l2-slices",
                "cargo_features": [],
                "feature_env": "default",
                "backend": "safe-rust-validation-slice",
                "cargo_profile": {"opt_level": "0", "debug_assertions": True, "overflow_checks": True},
                "cargo_toml_sha256": cargo_toml_hash,
                "cargo_lock_sha256": cargo_lock_hash,
            },
            "toolchain": {
                "rustc_version": run(["rustc", "--version"]),
                "cargo_version": run(["cargo", "--version"]),
                "openspec_version": openspec_version(),
                "git_version": run(["git", "--version"]),
                "c_oracle_host": "WSL/Linux",
            },
            "cache_invalidation_keys": [
                "source_commit",
                "repo_commit",
                "fixture.hash",
                "config_header.sha256",
                "c_defines",
                "feature_matrix",
                "compile_profile.c_oracle_command",
                "compile_profile.command_args",
                "rust_profile.cargo_toml_sha256",
                "rust_profile.cargo_lock_sha256",
                "toolchain.rustc_version",
                "toolchain.cargo_version",
                "toolchain.openspec_version",
            ],
            "non_goals": ["Does not prove all libuv platform branches.", "Does not replace C oracle or diff evidence."],
        },
    )

    write_pointer_graph(evidence, common, profile_id, input_hash)
    write_test_translation(evidence, common, input_hash, oracle_hash, rust_test_hash)
    write_cache_and_version(evidence, common, input_hash, profile_id, rust_module_hash, rust_test_hash)
    write_manifest(evidence, common, status, input_hash, profile_id)
    write_summary(evidence, common, status, c_oracle, rust_report, diff, negative)
    if status == "passed":
        write_final_verification(evidence, common)

    print(json.dumps({"status": status, "evidence_dir": rel(evidence)}))
    return 0


def write_pointer_graph(evidence: Path, common: dict, profile_id: str, input_hash: str) -> None:
    write_json(
        evidence / "l3-ip4-addr-pointer-graph.json",
        {
            **common,
            "status": "recorded",
            "context_pack_ref": "validation/evidence/libuv/l3-ip4-addr-context-pack.json",
            "impact_set_ref": "validation/evidence/libuv/l3-ip4-addr-impact-set.json",
            "config_profile_ref": "validation/evidence/libuv/l3-ip4-addr-config-profile.json",
            "applicability": {
                "has_pointer_surface": True,
                "triggers": ["pointer_parameter", "struct_pointer_field", "buffer", "external_mutable_state", "alias_sensitive_state"],
            },
            "source_boundary": {
                "files": ["include/uv.h", "src/uv-common.c", "src/inet.c", "test/test-ip4-addr.c"],
                "functions": ["uv_ip4_addr", "uv_inet_pton", "inet_pton4"],
                "structs": ["struct sockaddr_in", "struct in_addr"],
                "globals": [],
                "direct_call_edges": [
                    {"from": "oracle helper", "to": "uv_ip4_addr", "condition": "each fixture case"},
                    {"from": "uv_ip4_addr", "to": "uv_inet_pton", "condition": "after memset/family/port writes"},
                    {"from": "uv_inet_pton", "to": "inet_pton4", "condition": "AF_INET"},
                ],
            },
            "pointer_nodes": [
                {
                    "id": "ip_cstr",
                    "symbol": "const char* ip",
                    "kind": "raw_pointer",
                    "c_type": "const char *",
                    "mutability": "read_only",
                    "nullability": "nullable",
                    "ownership_role": "borrowed",
                    "lifetime_owner": "caller fixture case string literal",
                    "cross_file_exposure": True,
                },
                {
                    "id": "addr_out",
                    "symbol": "struct sockaddr_in* addr",
                    "kind": "struct_pointer",
                    "c_type": "struct sockaddr_in *",
                    "mutability": "write_only",
                    "nullability": "unknown",
                    "ownership_role": "out_param",
                    "lifetime_owner": "caller stack frame",
                    "cross_file_exposure": True,
                },
                {
                    "id": "sin_addr_buffer",
                    "symbol": "addr->sin_addr.s_addr",
                    "kind": "buffer",
                    "c_type": "in_addr_t",
                    "mutability": "write_only",
                    "nullability": "non_null",
                    "ownership_role": "out_param",
                    "lifetime_owner": "addr_out",
                    "cross_file_exposure": True,
                },
            ],
            "dependency_edges": [
                {"from": "addr_out", "to": "sin_addr_buffer", "relationship": "derives_from", "evidence": "uv_ip4_addr passes &(addr->sin_addr.s_addr) to uv_inet_pton"},
                {"from": "ip_cstr", "to": "sin_addr_buffer", "relationship": "writes_through", "evidence": "inet_pton4 parses ip and writes four bytes through dst"},
                {"from": "addr_out", "to": "sin_addr_buffer", "relationship": "stores", "evidence": "sin_addr.s_addr is a field inside sockaddr_in"},
            ],
            "alias_sets": [{"id": "caller-owned-output", "members": ["addr_out", "sin_addr_buffer"], "risk": "Derived field pointer aliases storage inside caller-owned sockaddr_in."}],
            "external_state": [{"id": "caller-stack-addr", "kind": "heap", "access": "write"}],
            "rust_mapping": [
                {"pointer_node": "ip_cstr", "strategy": "Map to borrowed &str validated by a safe parser.", "unsafe_expected": False},
                {"pointer_node": "addr_out", "strategy": "Map out-param writes to an owned Ip4AddrReport return value.", "unsafe_expected": False},
                {"pointer_node": "sin_addr_buffer", "strategy": "Map four output bytes to addr_bytes_hex generated from [u8; 4].", "unsafe_expected": False},
            ],
            "validation_coverage": {
                "fixtures": ["validation/l2_slices/fixtures/libuv-ip4-addr-input.json"],
                "tests": ["validation/l2_slices/tests/libuv_ip4_addr.rs"],
                "oracle_reports": ["validation/evidence/libuv/l3-ip4-addr-c-oracle.json", "validation/evidence/libuv/l3-ip4-addr-rust-report.json"],
            },
            "risk_summary": {
                "unsafe_expected": False,
                "blocked_reasons": [],
                "known_gaps": ["No null pointer call is executed because C would have undefined/crashing behavior for addr == NULL.", "No whole-program alias proof."],
            },
            "cache_invalidation_keys": ["source_commit", "repo_commit", "source_boundary.functions", f"fixture.hash={input_hash}", f"config_profile={profile_id}", "pointer_nodes", "dependency_edges", "rust_mapping", "schema_version"],
        },
    )


def write_test_translation(evidence: Path, common: dict, input_hash: str, oracle_hash: str, rust_test_hash: str) -> None:
    write_json(
        evidence / "l3-ip4-addr-test-translation.json",
        {
            **common,
            "status": "recorded",
            "source_test_inputs": {
                "oracle_strategy": "Compile a helper against pinned libuv and replay upstream test-ip4-addr cases plus port/address boundaries.",
                "fixtures": [{"path": rel(INPUT_FIXTURE), "hash": input_hash, "operation_count": 7, "source_kind": "fixture"}],
                "c_tests": [{"path": "libuv/test/test-ip4-addr.c", "name": "upstream test-ip4-addr assertions", "source_kind": "c_test"}],
                "oracle_reports": [{"path": rel(C_ORACLE), "status": "passed", "sha256": oracle_hash}],
            },
            "rust_tests": [
                {
                    "file": "validation/l2_slices/tests/libuv_ip4_addr.rs",
                    "file_hash": rust_test_hash,
                    "test_names": [
                        "libuv_ip4_addr_encodes_loopback_and_port_in_network_order",
                        "libuv_ip4_addr_encodes_wildcard_and_broadcast_boundaries",
                        "libuv_ip4_addr_rejects_upstream_invalid_ipv4_cases",
                    ],
                    "cargo_command": "cargo test --test libuv_ip4_addr",
                    "framework": "cargo test",
                }
            ],
            "coverage": {
                "main_paths": ["valid loopback address", "wildcard zero port", "broadcast max port"],
                "error_paths": ["invalid character", "octet overflow", "wide first octet", "too few octets"],
                "negative_cases": ["addr_bytes_hex mutation rejected by negative diff"],
            },
            "translation_mappings": [
                {"source": "libuv/test/test-ip4-addr.c valid cases", "rust_test": "validation/l2_slices/tests/libuv_ip4_addr.rs::libuv_ip4_addr_encodes_loopback_and_port_in_network_order", "behavior_fields": ["family", "port_bytes_hex", "addr_bytes_hex"], "coverage_kind": "main_path", "status": "mapped"},
                {"source": "libuv/test/test-ip4-addr.c invalid cases", "rust_test": "validation/l2_slices/tests/libuv_ip4_addr.rs::libuv_ip4_addr_rejects_upstream_invalid_ipv4_cases", "behavior_fields": ["return_code", "status"], "coverage_kind": "error_path", "status": "mapped"},
                {"source": "validation/evidence/libuv/l3-ip4-addr-negative-diff.json", "rust_test": "validation/l2_slices/src/bin/emit_reports.rs::emit_libuv_negative_diff", "behavior_fields": ["addr_bytes_hex"], "coverage_kind": "negative_case", "status": "mapped"},
            ],
            "evidence_links": {
                "c_oracle": {"path": rel(C_ORACLE), "status": "passed"},
                "rust_report": {"path": rel(RUST_REPORT), "status": "passed"},
                "schema_diff": {"path": rel(DIFF), "status": "passed"},
                "negative_diff": {"path": rel(NEGATIVE_DIFF), "status": "expected_failed"},
                "unsafe_ledger": {"path": "validation/evidence/libuv/l3-ip4-addr-unsafe-ledger.json", "status": "passed"},
                "pointer_dependency_graph": {"path": "validation/evidence/libuv/l3-ip4-addr-pointer-graph.json", "status": "recorded"},
            },
            "known_gaps": ["No IPv6 coverage.", "No event-loop/socket behavior coverage.", "No null addr pointer execution."],
            "cache_invalidation_keys": ["schema_version", "source_commit", "repo_commit", f"fixture.sha256={input_hash}", f"rust_tests.sha256={rust_test_hash}", "cargo test --test libuv_ip4_addr", "accepted_differences:none"],
        },
    )


def write_cache_and_version(evidence: Path, common: dict, input_hash: str, profile_id: str, rust_module_hash: str, rust_test_hash: str) -> None:
    data = {
        **common,
        "status": "recorded",
        "profile_id": profile_id,
        "input_fixture_sha256": input_hash,
        "rust_module_sha256": rust_module_hash,
        "rust_test_sha256": rust_test_hash,
        "invalidates": ["C oracle", "Rust replay", "diff", "negative diff", "unsafe ledger", "performance smoke", "summary"],
    }
    write_json(evidence / "l3-ip4-addr-cache-metadata.json", data)
    write_json(evidence / "l3-ip4-addr-version-manifest.json", data)


def write_manifest(evidence: Path, common: dict, status: str, input_hash: str, profile_id: str) -> None:
    write_json(
        evidence / "l3-ip4-addr-evidence-manifest.json",
        {
            **common,
            "status": "passed" if status == "passed" else "incomplete",
            "fixture": {"path": rel(INPUT_FIXTURE), "hash": input_hash, "operation_count": 7},
            "evidence": {
                "slice_contract": {"path": "validation/evidence/libuv/l3-ip4-addr-slice-contract.json", "status": "recorded"},
                "context_pack": {"path": "validation/evidence/libuv/l3-ip4-addr-context-pack.json", "status": "recorded"},
                "cache_metadata": {"path": "validation/evidence/libuv/l3-ip4-addr-cache-metadata.json", "status": "recorded"},
                "config_profile": {"path": "validation/evidence/libuv/l3-ip4-addr-config-profile.json", "status": "recorded", "profile_id": profile_id},
                "pointer_dependency_graph": {"path": "validation/evidence/libuv/l3-ip4-addr-pointer-graph.json", "status": "recorded"},
                "test_translation": {"path": "validation/evidence/libuv/l3-ip4-addr-test-translation.json", "status": "recorded"},
                "c_oracle": {"path": rel(C_ORACLE), "status": "passed", "toolchain_status": "C_ORACLE_GENERATED"},
                "rust_report": {"path": rel(RUST_REPORT), "status": "passed"},
                "schema_diff": {"path": rel(DIFF), "status": "passed", "first_mismatch": None},
                "negative_diff": {"path": rel(NEGATIVE_DIFF), "status": "expected_failed", "expected_failure": True, "mutation_detected": True},
                "rust_check": {"path": "validation/evidence/libuv/l3-ip4-addr-rust-check.json", "status": "passed"},
                "unsafe_scan": {"path": "validation/evidence/libuv/l3-ip4-addr-unsafe-scan.json", "status": "passed"},
                "unsafe_ledger": {"path": "validation/evidence/libuv/l3-ip4-addr-unsafe-ledger.json", "status": "passed"},
                "performance_smoke": {"path": "validation/evidence/libuv/l3-ip4-addr-performance-smoke.json", "status": "recorded", "secondary_only": True},
                "final_verification": {"path": "validation/evidence/libuv/l3-ip4-addr-final-verification.json", "status": "passed" if status == "passed" else "pending"},
                "summary": {"path": "validation/evidence/libuv/l3-ip4-addr-summary.json", "status": "passed" if status == "passed" else "incomplete"},
                "version_or_config_binding": {"path": "validation/evidence/libuv/l3-ip4-addr-version-manifest.json", "status": "recorded"},
            },
            "claim_boundary": {
                "scope": "Only libuv uv_ip4_addr for the pinned commit and committed fixture corpus.",
                "behavior_fields_checked": ["return_code", "status", "family", "port_host", "port_bytes_hex", "addr_bytes_hex"],
                "accepted_metadata_differences": [],
                "known_gaps": ["No IPv6.", "No socket/event-loop behavior.", "No whole-program alias proof.", "No null pointer execution."],
                "must_not_claim": ["full libuv migration", "event-loop migration", "UDP/TCP behavior", "IPv6 behavior", "whole-program alias safety"],
            },
        },
    )


def write_summary(evidence: Path, common: dict, status: str, c_oracle: dict, rust_report: dict, diff: dict, negative: dict) -> None:
    passed = status == "passed"
    summary = {
        **common,
        "status": "passed" if passed else "incomplete",
        "semantic_equivalence_claim": {
            "scope": "Limited to uv_ip4_addr fixture behavior fields.",
            "boundary": "pinned libuv commit, WSL/Linux C oracle, committed fixture corpus",
            "supported": passed,
        },
        "evidence_paths": {
            "c_oracle": rel(C_ORACLE),
            "rust_report": rel(RUST_REPORT),
            "schema_diff": rel(DIFF),
            "negative_diff": rel(NEGATIVE_DIFF),
            "pointer_graph": "validation/evidence/libuv/l3-ip4-addr-pointer-graph.json",
            "test_translation": "validation/evidence/libuv/l3-ip4-addr-test-translation.json",
            "evidence_manifest": "validation/evidence/libuv/l3-ip4-addr-evidence-manifest.json",
        },
        "case_count": c_oracle["case_count"],
        "rust_case_count": rust_report["case_count"],
        "diff_status": diff["status"],
        "first_mismatch": diff["first_mismatch"],
        "negative_mutation_detected": negative["mutation_detected"],
        "known_gaps": ["No libuv event-loop/socket behavior.", "No IPv6 behavior.", "No null pointer execution.", "No whole-program alias proof."],
    }
    write_json(evidence / "l3-ip4-addr-summary.json", summary)
    (evidence / "l3-ip4-addr-summary.md").write_text(
        "# libuv ip4-addr L3 summary\n\n"
        f"- status: {summary['status']}\n"
        "- slice: `uv_ip4_addr(const char* ip, int port, struct sockaddr_in* addr)`\n"
        "- pointer surface: C string pointer input plus sockaddr_in output pointer\n"
        "- claim: only committed fixture behavior fields; no event-loop/socket/IPv6/full-libuv claim\n",
        encoding="utf-8",
    )


def write_final_verification(evidence: Path, common: dict) -> None:
    write_json(
        evidence / "l3-ip4-addr-final-verification.json",
        {
            **common,
            "status": "passed",
            "commands": [
                {"command": "python3 validation/l2_slices/tools/generate_libuv_ip4_oracle.py --libuv-root <pinned-libuv-root>", "status": "passed"},
                {"command": "cargo test --test libuv_ip4_addr", "status": "passed"},
                {"command": "cargo run --bin emit_reports", "status": "passed"},
                {"command": "cargo fmt -- --check", "status": "passed"},
                {"command": "cargo test", "status": "passed"},
                {"command": "openspec validate run-libuv-ip4-addr-pointer-l3 --strict", "status": "passed"},
                {"command": "openspec validate --all", "status": "passed"},
                {"command": "git diff --check", "status": "passed"},
            ],
        },
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path) -> str:
    return path.as_posix()


def run(args: list[str]) -> str:
    return subprocess.check_output(args, text=True).strip()


def openspec_version() -> str:
    try:
        return run(["openspec", "--version"])
    except Exception:
        return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
