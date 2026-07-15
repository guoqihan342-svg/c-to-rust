from __future__ import annotations

import copy
import json
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.cargo_compiler_artifact_evidence import (
    CargoCompilerArtifactEvidenceError,
    parse_cargo_compiler_artifact_evidence,
    validate_cargo_compiler_artifact_evidence,
)


class ProjectMigrationCargoCompilerArtifactEvidenceTests(unittest.TestCase):
    def test_normalizes_artifact_facts_and_keeps_claims_false(self) -> None:
        artifact = _artifact(
            name="core", kind=["lib", "lib"], crate_types=["rlib", "lib"],
            features=["zeta", "alpha", "alpha"],
            filenames=[
                r"C:\work\pkg\target\debug\libcore.rlib",
                r"C:\work\pkg\target\debug\libcore.rmeta",
            ],
        )
        data = _stream(artifact, _finished())

        result = parse_cargo_compiler_artifact_evidence(data)

        self.assertEqual(1, result["artifact_count"])
        normalized = result["artifacts"][0]
        self.assertEqual(["lib", "rlib"], normalized["target"]["crate_types"])
        self.assertEqual(["alpha", "zeta"], normalized["features"])
        self.assertEqual("C:/work/pkg/Cargo.toml", normalized["manifest_path"])
        self.assertEqual(content_sha256(result["artifacts"]), result["artifact_set_sha256"])
        core = {key: value for key, value in result.items() if key != "content_sha256"}
        self.assertEqual(content_sha256(core), result["content_sha256"])
        self.assertFalse(result["interface_closure"])
        self.assertFalse(result["semantic_gate"])
        self.assertEqual(0, result["translation_coverage_numerator"])

    def test_multiple_targets_are_sorted_and_exact_duplicates_deduplicated(self) -> None:
        library = _artifact(name="library", kind=["lib"], crate_types=["rlib"])
        binary = _artifact(
            name="command", kind=["bin"], crate_types=["bin"],
            filenames=["/workspace/pkg/target/debug/command"],
            executable="/workspace/pkg/target/debug/command",
        )
        first = parse_cargo_compiler_artifact_evidence(
            _stream(binary, library, binary, _finished())
        )
        second = parse_cargo_compiler_artifact_evidence(
            _stream(library, binary, _finished())
        )

        self.assertEqual(2, first["artifact_count"])
        self.assertEqual(second["artifacts"], first["artifacts"])
        self.assertEqual(second["artifact_set_sha256"], first["artifact_set_sha256"])

    def test_accepts_known_non_artifact_events_without_project_assumptions(self) -> None:
        artifact = _artifact()
        compiler_message = {
            "reason": "compiler-message", "package_id": artifact["package_id"],
            "manifest_path": artifact["manifest_path"], "target": artifact["target"],
            "message": {"level": "warning", "message": "bounded diagnostic"},
        }
        build_script = {
            "reason": "build-script-executed", "package_id": artifact["package_id"],
            "linked_libs": [], "linked_paths": [], "cfgs": ["feature=\"x\""],
            "env": [["OUT", "value"]], "out_dir": "/workspace/pkg/target/out",
        }

        result = parse_cargo_compiler_artifact_evidence(
            _stream(compiler_message, build_script, artifact, _finished())
        )

        self.assertEqual(1, result["artifact_count"])

    def test_requires_strict_utf8_json_objects_and_fixed_event_shapes(self) -> None:
        invalid = (
            b"\xff",
            b"[]\n" + _stream(_artifact(), _finished()),
            b'{"reason":"compiler-artifact","reason":"build-finished"}\n',
            b'{"reason":"build-finished","success":NaN}\n',
            b'{"reason":"build-finished","success":Infinity}\n',
            _stream({"reason": []}, _finished()),
            _stream({"reason": "future-cargo-event"}, _finished()),
            _stream({**_artifact(), "unexpected": True}, _finished()),
            _stream({**_artifact(), "package_id": "\ud800"}, _finished()),
        )
        for data in invalid:
            with self.subTest(data=data[:80]):
                with self.assertRaises(CargoCompilerArtifactEvidenceError):
                    parse_cargo_compiler_artifact_evidence(data)

    def test_requires_one_terminal_successful_build_finished(self) -> None:
        artifact = _artifact()
        cases = {
            "missing": _stream(artifact),
            "failed": _stream(artifact, _finished(False)),
            "multiple": _stream(artifact, _finished(), _finished()),
            "not-terminal": _stream(artifact, _finished(), artifact),
        }
        for label, data in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(CargoCompilerArtifactEvidenceError):
                    parse_cargo_compiler_artifact_evidence(data)

    def test_rejects_path_and_nested_field_anomalies(self) -> None:
        cases = []
        relative = _artifact()
        relative["manifest_path"] = "relative/Cargo.toml"
        cases.append(relative)
        traversal = _artifact()
        traversal["filenames"] = ["/workspace/pkg/../outside/output"]
        cases.append(traversal)
        wrong_fresh = _artifact()
        wrong_fresh["fresh"] = 1
        cases.append(wrong_fresh)
        target_drift = _artifact()
        target_drift["target"] = {**target_drift["target"], "new_field": False}
        cases.append(target_drift)
        profile_drift = _artifact()
        profile_drift["profile"] = {**profile_drift["profile"], "lto": "off"}
        cases.append(profile_drift)
        detached_executable = _artifact(executable="/workspace/pkg/target/debug/other")
        cases.append(detached_executable)
        for artifact in cases:
            with self.subTest(artifact=artifact):
                with self.assertRaises(CargoCompilerArtifactEvidenceError):
                    parse_cargo_compiler_artifact_evidence(
                        _stream(artifact, _finished())
                    )

    def test_validation_rejects_tamper_and_source_rebinding(self) -> None:
        data = _stream(_artifact(), _finished())
        result = parse_cargo_compiler_artifact_evidence(data)
        self.assertEqual(
            result, validate_cargo_compiler_artifact_evidence(result, data),
        )

        stale = copy.deepcopy(result)
        stale["artifacts"][0]["fresh"] = not stale["artifacts"][0]["fresh"]
        with self.assertRaisesRegex(ValueError, "artifact_set_sha256_drift"):
            validate_cargo_compiler_artifact_evidence(stale)

        rebound = copy.deepcopy(stale)
        rebound["artifact_set_sha256"] = content_sha256(rebound["artifacts"])
        core = {key: value for key, value in rebound.items() if key != "content_sha256"}
        rebound["content_sha256"] = content_sha256(core)
        with self.assertRaisesRegex(ValueError, "source_reparse_drift"):
            validate_cargo_compiler_artifact_evidence(rebound, data)

        forged_claim = {**result, "interface_closure": True}
        with self.assertRaisesRegex(ValueError, "claim_boundary"):
            validate_cargo_compiler_artifact_evidence(forged_claim)


def _artifact(
    *, name: str = "unit", kind: list[str] | None = None,
    crate_types: list[str] | None = None, features: list[str] | None = None,
    filenames: list[str] | None = None, executable: str | None = None,
) -> dict:
    return {
        "reason": "compiler-artifact",
        "package_id": "path+file:///workspace/pkg#neutral-package@0.1.0",
        "manifest_path": r"C:\work\pkg\Cargo.toml" if name == "core"
        else "/workspace/pkg/Cargo.toml",
        "target": {
            "kind": kind or ["lib"], "crate_types": crate_types or ["rlib"],
            "name": name, "src_path": f"/workspace/pkg/src/{name}.rs",
            "edition": "2021", "doc": True, "doctest": True, "test": True,
        },
        "profile": {
            "opt_level": "0", "debuginfo": 2, "debug_assertions": True,
            "overflow_checks": True, "test": False,
        },
        "features": features or [],
        "filenames": filenames or [f"/workspace/pkg/target/debug/{name}.rmeta"],
        "executable": executable, "fresh": False,
    }


def _finished(success: bool = True) -> dict:
    return {"reason": "build-finished", "success": success}


def _stream(*events: dict) -> bytes:
    return ("\n".join(
        json.dumps(event, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        for event in events
    ) + "\n").encode("utf-8")


if __name__ == "__main__":
    unittest.main()
