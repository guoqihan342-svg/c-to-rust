import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from validation.tools.validate_flashdb_version_binding import validate_version_binding


class ValidateFlashDbVersionBindingTests(unittest.TestCase):
    def test_rejects_missing_cache_key_inputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="version-binding-test-") as tmp:
            root = Path(tmp)
            cargo = self._write_cargo_toml(root, version="0.1.0")
            manifest = self._write_manifest(root, cargo, include_cache_keys=False)

            with self.assertRaises(SystemExit) as raised:
                validate_version_binding(manifest, cargo)

            self.assertIn("cache_key_inputs", str(raised.exception))

    def test_rejects_package_version_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="version-binding-test-") as tmp:
            root = Path(tmp)
            cargo = self._write_cargo_toml(root, version="0.2.0")
            manifest = self._write_manifest(root, cargo, package_version="0.1.0")

            with self.assertRaises(SystemExit) as raised:
                validate_version_binding(manifest, cargo)

            self.assertIn("package_version", str(raised.exception))

    def test_rejects_cargo_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="version-binding-test-") as tmp:
            root = Path(tmp)
            cargo = self._write_cargo_toml(root, version="0.1.0")
            manifest = self._write_manifest(root, cargo, cargo_toml_sha256="a" * 64)

            with self.assertRaises(SystemExit) as raised:
                validate_version_binding(manifest, cargo)

            self.assertIn("cargo_toml_sha256", str(raised.exception))

    def test_accepts_complete_version_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="version-binding-test-") as tmp:
            root = Path(tmp)
            cargo = self._write_cargo_toml(root, version="0.1.0")
            manifest = self._write_manifest(root, cargo)

            report = validate_version_binding(manifest, cargo)

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["package_version"], "0.1.0")
            self.assertIn("rustc_version", report["checked_fields"])

    def _write_manifest(
        self,
        root: Path,
        cargo_toml: Path,
        *,
        package_version: str = "0.1.0",
        include_cache_keys: bool = True,
        cargo_toml_sha256: str | None = None,
    ) -> Path:
        cargo_lock = cargo_toml.with_name("Cargo.lock")
        payload = {
            "schema_version": 1,
            "command": "version-manifest",
            "agent_contract_version": "0.1.0",
            "context_schema_version": "0.1.0",
            "patch_plan_schema_version": "0.1.0",
            "fixture_schema_version": 1,
            "evidence_schema_version": 1,
            "package_name": "flashdb_rust",
            "package_version": package_version,
            "cargo_toml_sha256": cargo_toml_sha256 or self._sha256(cargo_toml),
            "cargo_lock_sha256": self._sha256(cargo_lock),
            "rustc_version": "rustc 1.95.0",
            "cargo_version": "cargo 1.95.0",
            "openspec_version": "OpenSpec 1.4.1",
            "flashdb_source_commit": "93d175549da579b8abac07bd175ce4c3f9dde829",
            "flashdb_feature_matrix": {"FDB_USING_KVDB": True},
            "command_arguments": ["version-manifest"],
            "fixture_sha256": None,
            "ai_metadata": {"used": False, "provider": "not_configured"},
        }
        if include_cache_keys:
            payload["cache_key_inputs"] = [
                "agent_contract_version",
                "context_schema_version",
                "patch_plan_schema_version",
                "fixture_schema_version",
                "evidence_schema_version",
                "package_version",
                "cargo_toml_sha256",
                "cargo_lock_sha256",
                "rustc_version",
                "cargo_version",
                "openspec_version",
                "flashdb_source_commit",
                "flashdb_feature_matrix",
                "command_arguments",
                "fixture_sha256",
                "ai_metadata",
            ]
        path = root / "version-manifest.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _write_cargo_toml(self, root: Path, *, version: str) -> Path:
        path = root / "Cargo.toml"
        path.write_text(
            f'[package]\nname = "flashdb_rust"\nversion = "{version}"\nedition = "2021"\n',
            encoding="utf-8",
        )
        path.with_name("Cargo.lock").write_text("# test lock\n", encoding="utf-8")
        return path

    def _sha256(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
