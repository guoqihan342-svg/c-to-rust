class _ValidateAutoTranslationEvidenceTestsPart06:
    def _ref(self, path: Path, status: str) -> dict:
        return {"path": path.as_posix(), "status": status, "sha256": self._sha256(path)}

    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _sha256(self, path: Path) -> str:
        return load_validator_module().sha256(path)

    def _sha256_json(self, payload: dict) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()

    def test_rejects_missing_alias_gate_in_manifest_and_final_verification(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            evidence_dir = out_root / "demo" / "auto-translation" / "copy-i32-ptr-arith"
            for file_name in [
                "l3-copy-i32-ptr-arith-evidence-manifest.json",
                "l3-copy-i32-ptr-arith-final-verification.json",
            ]:
                path = evidence_dir / file_name
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload.get("claim_boundary", {}).pop("alias_gate", None)
                payload.pop("alias_gate", None)
                path.write_text(json.dumps(payload), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("alias gate", result.stderr + result.stdout)

    def test_rejects_empty_alias_risk_and_noalias_precondition_for_unknown_alias(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "demo-copy-i32-ptr-arith.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            out_root = tmp_path / "evidence"

            subprocess.run(
                [
                    sys.executable,
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            pointer_graph_path = (
                out_root
                / "demo"
                / "auto-translation"
                / "copy-i32-ptr-arith"
                / "l3-copy-i32-ptr-arith-pointer-graph.json"
            )
            pointer_graph = json.loads(pointer_graph_path.read_text(encoding="utf-8"))
            pointer_graph["alias_risks"] = []
            pointer_graph["safe_boundary_preconditions"] = []
            pointer_graph_path.write_text(json.dumps(pointer_graph), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "demo",
                    "--slice-id",
                    "copy-i32-ptr-arith",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("alias gate", result.stderr + result.stdout)
