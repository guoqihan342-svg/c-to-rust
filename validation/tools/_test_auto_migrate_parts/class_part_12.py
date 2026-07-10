class _AutoMigrateTestsPart12:
    def _colliding_unsafe_fixture(self, root: Path):
        auto_migrate = load_auto_migrate_module()
        evidence_dir = root / "demo" / "auto-translation" / "stable-unsafe"
        evidence_dir.mkdir(parents=True)
        prefix = "l3-stable-unsafe"
        draft_path = evidence_dir / f"{prefix}-rust-draft.rs"
        draft_path.write_text("pub fn stable() -> u32 { 7 }\n", encoding="utf-8")
        scan_path = evidence_dir / f"{prefix}-unsafe-scan.json"
        ledger_path = evidence_dir / f"{prefix}-unsafe-ledger.json"
        scan = {"status": "passed", "first_party_non_test_unsafe_count": 0}
        ledger = {"status": "passed", "first_party_non_test_unsafe_count": 0, "entries": []}
        auto_migrate.write_json(scan_path, scan)
        auto_migrate.write_json(ledger_path, ledger)
        accepted = {
            "status": "accepted",
            "target_id": "demo",
            "slice_id": "stable-unsafe",
            "source_commit": "abc123",
            "paths": {
                "unsafe_scan": auto_migrate.rel(scan_path),
                "unsafe_ledger": auto_migrate.rel(ledger_path),
            },
            "path_sha256": {
                "unsafe_scan": auto_migrate.sha256(scan_path),
                "unsafe_ledger": auto_migrate.sha256(ledger_path),
            },
            "reports": {"unsafe_scan": scan, "unsafe_ledger": ledger},
        }
        spec = {"target_id": "demo", "slice_id": "stable-unsafe", "source_commit": "abc123"}
        return auto_migrate, evidence_dir, spec, accepted

    def test_stabilizes_colliding_unsafe_evidence_without_self_reference(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="stable-unsafe-", dir=target_root) as tmp:
            auto_migrate, evidence_dir, spec, accepted = self._colliding_unsafe_fixture(Path(tmp))
            auto_migrate.stabilize_colliding_accepted_unsafe_evidence(spec, evidence_dir, accepted)

            self.assertEqual(accepted["unsafe_gate_source"], "generated_draft_unsafe_gates")
            for key in ("unsafe_scan", "unsafe_ledger"):
                stable_path = REPO_ROOT / accepted["paths"][key]
                payload = json.loads(stable_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["gate_source"], "generated_draft_unsafe_gates")
                self.assertNotIn(f"accepted_{key}", payload)
                self.assertEqual(accepted["path_sha256"][key], auto_migrate.sha256(stable_path))
                self.assertEqual(
                    payload["generated_rust_draft"]["sha256"],
                    auto_migrate.sha256(evidence_dir / "l3-stable-unsafe-rust-draft.rs"),
                )

    def test_rejects_colliding_unsafe_count_drift(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="stable-unsafe-", dir=target_root) as tmp:
            auto_migrate, evidence_dir, spec, accepted = self._colliding_unsafe_fixture(Path(tmp))
            accepted["reports"]["unsafe_scan"]["first_party_non_test_unsafe_count"] = 1
            with self.assertRaisesRegex(SystemExit, "count does not match"):
                auto_migrate.stabilize_colliding_accepted_unsafe_evidence(spec, evidence_dir, accepted)

    def test_leaves_external_unsafe_evidence_bindings_unchanged(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="stable-unsafe-", dir=target_root) as tmp:
            auto_migrate, evidence_dir, spec, accepted = self._colliding_unsafe_fixture(Path(tmp))
            external_dir = Path(tmp) / "accepted"
            external_dir.mkdir()
            for key in ("unsafe_scan", "unsafe_ledger"):
                path = external_dir / f"{key}.json"
                auto_migrate.write_json(path, accepted["reports"][key])
                accepted["paths"][key] = auto_migrate.rel(path)
                accepted["path_sha256"][key] = auto_migrate.sha256(path)
            before = json.loads(json.dumps(accepted))

            auto_migrate.stabilize_colliding_accepted_unsafe_evidence(spec, evidence_dir, accepted)

            self.assertEqual(accepted, before)
