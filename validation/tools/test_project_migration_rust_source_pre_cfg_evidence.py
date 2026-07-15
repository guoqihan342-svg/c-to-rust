from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.rust_source_pre_cfg_evidence import (
    materialize_rust_source_pre_cfg_evidence,
    reopen_rust_source_pre_cfg_evidence,
)
from validation.tools._project_migration_harness.rust_source_pre_cfg_process import (
    RustSourceProcessResult,
)
from validation.tools._project_migration_harness.rust_source_pre_cfg_receipt import (
    validate_rust_source_pre_cfg_receipt,
)


MODULE = (
    "validation.tools._project_migration_harness."
    "rust_source_pre_cfg_evidence"
)


class RustSourcePreCfgEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="rust-source-pre-cfg-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / "target/run"
        self.database = self.out / "state/project-migration.sqlite3"
        self.database.parent.mkdir(parents=True)
        self.database.touch()
        self.tool_root = self.root / "tool"
        self.binary = (
            self.tool_root / "target/debug/c2r_rust_source_witness.exe"
        )
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"fixture parser binary")
        self.domain_ref = write_content_addressed_json(
            self.out, "domain-fixture", {"fixture": "domain"},
        )
        self.b2a_ref = write_content_addressed_json(
            self.out, "b2a-fixture", {"fixture": "b2a"},
        )
        self.topology_ref = write_content_addressed_json(
            self.out, "topology-fixture", {"fixture": "topology"},
        )
        self.source = b"pub fn add(value: i32) -> i32 { value + 1 }\n"
        self.source_sha = hashlib.sha256(self.source).hexdigest()
        self.raw = _ready_witness(self.source)
        self.context = {
            "domain_reference": self.domain_ref,
            "domain": {"domain_sha256": "1" * 64},
            "b2a_reference": self.b2a_ref,
            "b2a": {
                "verification_context_sha256": "2" * 64,
                "materialization": {"generation": {"sha256": "3" * 64}},
            },
            "topology_reference": self.topology_ref,
            "topology": {
                "receipt_sha256": "4" * 64,
                "witness": {"witness_sha256": "5" * 64},
                "status": "ready",
            },
            "sources": [{
                "unit_id": "unit-a", "artifact_id": "artifact-a",
                "source_sha256": self.source_sha,
                "source_size_bytes": len(self.source), "source": self.source,
            }],
        }

    def test_materialize_and_deep_reopen_bind_raw_and_derived_cas(self) -> None:
        with patch(
            f"{MODULE}.reopen_rust_source_pre_cfg_context",
            return_value=self.context,
        ) as reopen_context:
            result = self._materialize()
            reopened = self._reopen(result["reference"])

        self.assertEqual(result["receipt"], reopened)
        self.assertEqual(2, reopen_context.call_count)
        self.assertEqual("ready", reopened["status"])
        candidate = reopened["candidates"][0]
        self.assertEqual(self.source_sha, candidate["source_sha256"])
        self.assertEqual(1, candidate["facts"]["signature_count"])
        self.assertEqual(0, candidate["facts"]["blocker_count"])
        self.assertFalse(reopened["parser_binary"]["sandboxed"])
        self.assertFalse(reopened["claim_boundary"]["section_closure"])

    def test_raw_output_binary_and_domain_drift_fail_closed(self) -> None:
        with self._context_patch():
            result = self._materialize()
        candidate = result["receipt"]["candidates"][0]
        raw_path = self.out.joinpath(
            *Path(candidate["raw_outputs"]["stdout_ref"]["path"]).parts
        )
        raw_path.write_bytes(b"{}\n")
        with self._context_patch(), self.assertRaises(LedgerError):
            self._reopen(result["reference"])

        raw_path.write_bytes(self.raw)
        self.binary.write_bytes(b"changed parser binary")
        with self._context_patch(), self.assertRaises((LedgerError, ValueError)):
            self._reopen(result["reference"])

        self.binary.write_bytes(b"fixture parser binary")
        changed = copy.deepcopy(self.context)
        changed["domain"]["domain_sha256"] = "9" * 64
        with patch(
            f"{MODULE}.reopen_rust_source_pre_cfg_context",
            return_value=changed,
        ), self.assertRaises(LedgerError):
            self._reopen(result["reference"])

    def test_topology_blocker_propagates_without_granting_closure(self) -> None:
        changed = copy.deepcopy(self.context)
        changed["topology"]["status"] = "blocked"
        with patch(
            f"{MODULE}.reopen_rust_source_pre_cfg_context",
            return_value=changed,
        ):
            result = self._materialize()

        self.assertEqual("blocked", result["receipt"]["status"])
        self.assertFalse(result["receipt"]["claim_boundary"]["semantic_gate"])
        self.assertEqual(
            0,
            result["receipt"]["claim_boundary"][
                "translation_coverage_numerator"
            ],
        )

    def test_failed_process_and_self_consistent_receipt_tamper_are_rejected(self) -> None:
        def failed_runner(**_kwargs):
            return RustSourceProcessResult(
                True, 1, b"", b"failed", False, False,
                content_sha256({
                    "argv": ["c2r_rust_source_witness"],
                    "stdin_sha256": self.source_sha,
                }),
            )

        with self._context_patch(), self.assertRaisesRegex(
            LedgerError, "execution failed",
        ):
            self._materialize(parser_runner=failed_runner)

        with self._context_patch():
            result = self._materialize()
        changed = copy.deepcopy(result["receipt"])
        changed["candidates"][0]["facts"]["signature_count"] = 0
        core = {key: changed[key] for key in changed if key != "receipt_sha256"}
        changed["receipt_sha256"] = content_sha256(core)
        validated = validate_rust_source_pre_cfg_receipt(changed)
        self.assertEqual(0, validated["candidates"][0]["facts"]["signature_count"])
        # Deep reopen derives the summary from raw syn output, so hash-consistent
        # receipt tampering still cannot survive the evidence domain.
        tampered_ref = write_content_addressed_json(
            self.out, "rust-source-pre-cfg-witness-receipt", changed,
        )
        with self._context_patch(), self.assertRaises(LedgerError):
            self._reopen(tampered_ref)

    def _materialize(self, *, parser_runner=None) -> dict:
        return materialize_rust_source_pre_cfg_evidence(
            ledger_path=self.database, out_root=self.out,
            validation_domain=self.domain_ref,
            cargo_topology_evidence=self.topology_ref,
            repo_root=self.root / "repo", artifact_root=self.root,
            harness_root=self.root, quarantine_root=self.root / "quarantine",
            tool_root=self.tool_root, parser_binary=self.binary,
            parser_runner=parser_runner or self._parser_runner,
        )

    def _reopen(self, reference: dict) -> dict:
        return reopen_rust_source_pre_cfg_evidence(
            self.database, reference,
            repo_root=self.root / "repo", artifact_root=self.root,
            harness_root=self.root, quarantine_root=self.root / "quarantine",
            tool_root=self.tool_root, parser_binary=self.binary,
            parser_runner=self._parser_runner,
        )

    def _parser_runner(self, **_kwargs) -> RustSourceProcessResult:
        return RustSourceProcessResult(
            True, 0, self.raw, b"", False, False,
            content_sha256({
                "argv": ["c2r_rust_source_witness"],
                "stdin_sha256": self.source_sha,
            }),
        )

    def _context_patch(self):
        return patch(
            f"{MODULE}.reopen_rust_source_pre_cfg_context",
            return_value=self.context,
        )


def _ready_witness(source: bytes) -> bytes:
    signature = "fn add (value : i32) -> i32"
    payload = {
        "schema_version": 1,
        "artifact_kind": "rust-source-pre-cfg-witness",
        "status": "ready",
        "parser": {
            "implementation": "syn", "version": "2.0.118",
            "quote_version": "1.0.46", "protocol_version": 1,
            "crate_version": "0.1.0",
        },
        "source": {
            "sha256": hashlib.sha256(source).hexdigest(),
            "size_bytes": len(source), "encoding": "utf-8",
        },
        "modules": [{
            "module_id": "module-000000", "parent_module_id": None,
            "module_path": "crate", "kind": "root",
        }],
        "items": [{
            "item_id": "item-000000", "module_id": "module-000000",
            "item_path": "crate::add", "name": "add", "kind": "function",
            "visibility": "pub",
        }],
        "signatures": [{
            "item_id": "item-000000", "kind": "function",
            "syntax": signature,
            "syntax_sha256": hashlib.sha256(signature.encode()).hexdigest(),
            "syntax_size_bytes": len(signature), "abi": None,
            "is_unsafe": False, "is_async": False, "is_const": False,
            "is_variadic": False,
        }],
        "types": [], "globals": [], "initialization": [], "attributes": [],
        "macro_invocations": [], "blockers": [],
        "claim_boundary": {
            "phase": "pre-cfg", "candidate_only": True, "post_cfg": False,
            "section_closure": False, "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode()


if __name__ == "__main__":
    unittest.main()
