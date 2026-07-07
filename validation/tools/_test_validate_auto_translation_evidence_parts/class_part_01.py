class _ValidateAutoTranslationEvidenceTestsPart01:
    def test_rejects_c2rust_candidate_claiming_semantic_pass(self) -> None:
        module = load_validator_module()
        route = {"candidate_generation": self._candidate_selection_record()}

        semantic_claim = json.loads(json.dumps(route))
        semantic_claim["candidate_generation"]["candidate_set"][2]["semantic_pass"] = True
        semantic_claim["candidate_generation"]["c2rust_baseline"]["semantic_pass"] = True
        with self.assertRaises(SystemExit) as raised:
            module.validate_typed_ir_candidate_binding(
                Path("unused"),
                "unused",
                semantic_claim,
                {"candidate_generation": semantic_claim["candidate_generation"]},
            )
        self.assertIn("semantic_pass", str(raised.exception))

        role_claim = json.loads(json.dumps(route))
        role_claim["candidate_generation"]["candidate_set"][2]["correctness_role"] = "semantic_source"
        role_claim["candidate_generation"]["c2rust_baseline"]["correctness_role"] = "semantic_source"
        with self.assertRaises(SystemExit) as raised:
            module.validate_typed_ir_candidate_binding(
                Path("unused"),
                "unused",
                role_claim,
                {"candidate_generation": role_claim["candidate_generation"]},
            )
        self.assertIn("correctness_role", str(raised.exception))

    def test_committed_real_fdb_crc32_c2rust_baseline_contract_is_current(self) -> None:
        module = load_validator_module()
        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "flashdb"
            / "auto-translation"
            / "real-fdb-calc-crc32"
        )
        prefix = "l3-real-fdb-calc-crc32"
        slice_spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"

        module.validate_route_baseline_profile_refs(evidence_dir, prefix, slice_spec_path)

        baseline_path = evidence_dir / f"{prefix}-c2rust-baseline-manifest.json"
        route_path = evidence_dir / f"{prefix}-route-decision.json"
        profile_path = evidence_dir / f"{prefix}-validation-profile.json"
        baseline = module.load_json(baseline_path)
        route = module.load_json(route_path)
        profile = module.load_json(profile_path)

        self.assertEqual(baseline["status"], "generated")
        self.assertEqual(baseline["reason"], "generated_by_c2rust")
        self.assertEqual(baseline["correctness_role"], "candidate_context_only")
        self.assertEqual(
            baseline["output"]["sha256"],
            "7ea393d1d09f0f4f91127247599b4d91c3be3c350e70cc384902e1c8db34b316",
        )
        self.assertEqual(
            self._sha256(REPO_ROOT / baseline["output"]["path"]),
            baseline["output"]["sha256"],
        )
        self.assertEqual(baseline["compile"]["status"], "passed")
        self.assertTrue(baseline["compile"]["attempted"])
        self.assertIs(baseline["compile"]["semantic_pass"], False)
        self.assertEqual(
            baseline["compile"]["artifact"]["sha256"],
            "4d0d490231ca443d76b759346557a2fc319f167092cdd37e6bde83705d7b73bf",
        )
        self.assertEqual(
            self._sha256(REPO_ROOT / baseline["compile"]["artifact"]["path"]),
            baseline["compile"]["artifact"]["sha256"],
        )

        route_candidate = route["candidate_generation"]["c2rust_baseline"]
        profile_candidate = profile["candidate_generation"]["c2rust_baseline"]
        self.assertEqual(route_candidate, profile_candidate)
        self.assertEqual(route_candidate["baseline_manifest"]["sha256"], self._sha256(baseline_path))
        self.assertEqual(route_candidate["output_ref"], module.c2rust_baseline_expected_output_ref(baseline))
        self.assertIs(route_candidate["semantic_pass"], False)
        self.assertIs(route_candidate["generated_draft_semantic_pass"], False)

    def test_rejects_c2rust_candidate_status_reason_drift_from_baseline_manifest(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-c2rust-binding"
            baseline_path = evidence_dir / f"{prefix}-c2rust-baseline-manifest.json"
            baseline = {
                "schema_version": 1,
                "status": "skipped",
                "reason": "blocked_by_missing_tools",
                "correctness_role": "candidate_context_only",
                "output": None,
            }
            self._write_json(baseline_path, baseline)

            candidate_generation = self._candidate_selection_record()
            c2rust_candidate = candidate_generation["candidate_set"][2]
            c2rust_candidate["baseline_manifest"] = self._ref(baseline_path, "skipped")
            c2rust_candidate["output_ref"] = None
            candidate_generation["c2rust_baseline"] = c2rust_candidate

            drifted = json.loads(json.dumps(candidate_generation))
            drifted["candidate_set"][2]["status"] = "blocked"
            drifted["candidate_set"][2]["reason"] = "baseline_generation_not_enabled"
            drifted["c2rust_baseline"] = drifted["candidate_set"][2]

            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    {"candidate_generation": drifted},
                    {"candidate_generation": drifted},
                )
            self.assertIn("c2rust_baseline status drift", str(raised.exception))

    def test_rejects_c2rust_generated_output_ref_drift_from_baseline_manifest(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            prefix = "l3-c2rust-output"
            compile_commands = evidence_dir / "compile_commands.json"
            generation_stdout = evidence_dir / "c2rust.stdout.log"
            generation_stderr = evidence_dir / "c2rust.stderr.log"
            generated_file = evidence_dir / "generated" / "src" / "lib.rs"
            generated_file.parent.mkdir(parents=True)
            compile_commands.write_text(
                json.dumps([{"directory": evidence_dir.as_posix(), "command": "cc -c demo.c", "file": "demo.c"}]),
                encoding="utf-8",
            )
            generation_stdout.write_text("c2rust ok\n", encoding="utf-8")
            generation_stderr.write_text("", encoding="utf-8")
            generated_file.write_text("pub unsafe fn generated() {}\n", encoding="utf-8")
            output_path = evidence_dir / "c2rust-output.rs"
            output_path.write_text("pub unsafe fn generated() {}\n", encoding="utf-8")
            generated_ref = {
                "path": generated_file.as_posix(),
                "sha256": self._sha256(generated_file),
            }
            baseline_path = evidence_dir / f"{prefix}-c2rust-baseline-manifest.json"
            baseline = {
                "schema_version": 1,
                "status": "generated",
                "reason": "generated_by_c2rust",
                "correctness_role": "candidate_context_only",
                "generation": {
                    "compile_commands": {
                        "path": compile_commands.as_posix(),
                        "sha256": self._sha256(compile_commands),
                    },
                    "command": {
                        "argv": ["c2rust", "transpile", "--emit-build-files", compile_commands.as_posix()],
                        "working_directory": evidence_dir.as_posix(),
                        "stdout_log": generation_stdout.as_posix(),
                        "stderr_log": generation_stderr.as_posix(),
                        "timeout_seconds": 120,
                        "exit_status": "passed",
                        "returncode": 0,
                    },
                    "generated_files": [generated_ref],
                },
                "output": {
                    "path": output_path.as_posix(),
                    "status": "generated",
                    "sha256": self._sha256(output_path),
                    "source_files": [generated_ref],
                },
                "compile": {
                    "status": "failed",
                    "attempted": True,
                    "semantic_pass": False,
                    "candidate_output": {
                        "path": output_path.as_posix(),
                        "status": "generated",
                        "sha256": self._sha256(output_path),
                    },
                    "command": {
                        "argv": ["rustc", "--crate-type", "lib", output_path.as_posix()],
                        "working_directory": evidence_dir.as_posix(),
                        "stdout_log": (evidence_dir / "rustc.stdout.log").as_posix(),
                        "stderr_log": (evidence_dir / "rustc.stderr.log").as_posix(),
                        "timeout_seconds": 120,
                        "exit_status": "failed",
                        "returncode": 1,
                    },
                    "artifact": None,
                    "diagnostics": ["unit test compile failure placeholder"],
                },
            }
            self._write_json(baseline_path, baseline)

            candidate_generation = self._candidate_selection_record()
            c2rust_candidate = candidate_generation["candidate_set"][2]
            c2rust_candidate["status"] = "generated"
            c2rust_candidate["reason"] = "generated_by_c2rust"
            c2rust_candidate["baseline_manifest"] = self._ref(baseline_path, "generated")
            c2rust_candidate["output_ref"] = None
            candidate_generation["c2rust_baseline"] = c2rust_candidate

            with self.assertRaises(SystemExit) as raised:
                module.validate_typed_ir_candidate_binding(
                    evidence_dir,
                    prefix,
                    {"candidate_generation": candidate_generation},
                    {"candidate_generation": candidate_generation},
                )
            self.assertIn("c2rust_baseline output_ref drift", str(raised.exception))

    def test_rejects_cache_missing_route_baseline_profile_identities(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            cache_path = evidence_dir / "l3-adler32-step-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache.pop("route_decision_identity", None)
            cache_path.write_text(json.dumps(cache), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
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
            self.assertIn("route_decision_identity", result.stderr + result.stdout)

    def test_rejects_cache_missing_competition_environment_identity_when_profile_binds_it(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            profile = json.loads(
                (evidence_dir / "l3-adler32-step-validation-profile.json").read_text(encoding="utf-8")
            )
            self.assertIn("competition_environment", profile)

            cache_path = evidence_dir / "l3-adler32-step-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache.pop("competition_environment_identity", None)
            cache["cache_input_fields"] = [
                field for field in cache.get("cache_input_fields", []) if field != "competition_environment_identity"
            ]
            cache_path.write_text(json.dumps(cache), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
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
            self.assertIn("competition_environment_identity", result.stderr + result.stdout)

    def test_rejects_cache_route_baseline_profile_identity_sha_drift(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            cache_path = evidence_dir / "l3-adler32-step-auto-cache-metadata.json"
            original_cache = json.loads(cache_path.read_text(encoding="utf-8"))
            for key in [
                "c2rust_baseline_identity",
                "route_decision_identity",
                "validation_profile_identity",
            ]:
                with self.subTest(key=key):
                    cache = json.loads(json.dumps(original_cache))
                    cache[key]["sha256"] = f"stale-{key}"
                    cache_path.write_text(json.dumps(cache), encoding="utf-8")

                    result = subprocess.run(
                        [
                            sys.executable,
                            str(VALIDATOR),
                            "--target-id",
                            "zlib-ng",
                            "--slice-id",
                            "adler32-step",
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
                    self.assertIn(key, result.stderr + result.stdout)

    def test_rejects_generated_c2rust_baseline_without_output(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            baseline_path = evidence_dir / "l3-adler32-step-c2rust-baseline-manifest.json"
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            baseline["status"] = "generated"
            baseline["reason"] = "test-forged-generated-status"
            baseline["selected_command"] = {
                "name": "c2rust",
                "path": "fake-c2rust",
                "available": True,
                "version_status": "OK",
                "version": "fake",
            }
            baseline["output"] = None
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
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
            self.assertIn("object", result.stderr + result.stdout)

    def test_rejects_generated_c2rust_baseline_without_compile_status(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            baseline_path = evidence_dir / "l3-adler32-step-c2rust-baseline-manifest.json"
            output_path = evidence_dir / "l3-adler32-step-c2rust-baseline-output.rs"
            output_path.write_text("pub fn adler32_step(x: u32) -> u32 { x }\n", encoding="utf-8")
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            baseline["status"] = "generated"
            baseline["reason"] = "test-forged-generated-status"
            baseline["selected_command"] = {
                "name": "c2rust",
                "path": "fake-c2rust",
                "available": True,
                "version_status": "OK",
                "version": "fake",
            }
            baseline["output"] = {
                "path": output_path.as_posix(),
                "status": "generated",
                "sha256": self._sha256(output_path),
                "source_files": [],
            }
            baseline.pop("compile", None)
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
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
            self.assertIn("compile", result.stderr + result.stdout)

    def test_rejects_generated_c2rust_baseline_generated_file_sha_drift(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            tmp_path = Path(tmp)
            compile_commands = tmp_path / "compile_commands.json"
            stdout_log = tmp_path / "c2rust.stdout.log"
            stderr_log = tmp_path / "c2rust.stderr.log"
            generated_file = tmp_path / "generated" / "src" / "lib.rs"
            output_file = tmp_path / "c2rust-baseline-output.rs"
            artifact_file = tmp_path / "c2rust-baseline-output.rlib"
            generated_file.parent.mkdir(parents=True)
            compile_commands.write_text(
                json.dumps([{"directory": str(tmp_path), "command": "cc -c demo.c", "file": "demo.c"}]),
                encoding="utf-8",
            )
            stdout_log.write_text("c2rust ok\n", encoding="utf-8")
            stderr_log.write_text("", encoding="utf-8")
            generated_file.write_text("pub fn generated() {}\n", encoding="utf-8")
            output_file.write_text("pub fn generated() {}\n", encoding="utf-8")
            artifact_file.write_text("fake rlib\n", encoding="utf-8")

            generated_ref = {"path": generated_file.as_posix(), "sha256": "not-the-real-sha"}
            output_ref = {
                "path": output_file.as_posix(),
                "status": "generated",
                "sha256": self._sha256(output_file),
                "source_files": [generated_ref],
            }
            baseline = {
                "generation": {
                    "compile_commands": {
                        "path": compile_commands.as_posix(),
                        "sha256": self._sha256(compile_commands),
                    },
                    "command": {
                        "argv": ["c2rust", "transpile", "--emit-build-files", compile_commands.as_posix()],
                        "working_directory": tmp_path.as_posix(),
                        "stdout_log": stdout_log.as_posix(),
                        "stderr_log": stderr_log.as_posix(),
                        "timeout_seconds": 120,
                        "exit_status": "passed",
                        "returncode": 0,
                    },
                    "generated_files": [generated_ref],
                },
                "compile": {
                    "status": "passed",
                    "attempted": True,
                    "semantic_pass": False,
                    "candidate_output": {
                        "path": output_file.as_posix(),
                        "status": "generated",
                        "sha256": self._sha256(output_file),
                    },
                    "command": {
                        "argv": ["rustc", "--crate-type", "lib", output_file.as_posix()],
                        "working_directory": tmp_path.as_posix(),
                        "stdout_log": stdout_log.as_posix(),
                        "stderr_log": stderr_log.as_posix(),
                        "timeout_seconds": 60,
                        "exit_status": "passed",
                        "returncode": 0,
                    },
                    "artifact": {
                        "path": artifact_file.as_posix(),
                        "status": "compiled",
                        "sha256": self._sha256(artifact_file),
                    },
                    "diagnostics": [],
                },
            }

            with self.assertRaises(SystemExit) as raised:
                module.validate_c2rust_baseline_generation_status(
                    baseline,
                    output_ref,
                    tmp_path / "c2rust-baseline-manifest.json",
                )

            self.assertIn("generated_files[0]", str(raised.exception))

    def test_rejects_c2rust_compile_candidate_output_drift(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            baseline, output_ref, manifest_path = self._c2rust_compile_fixture(Path(tmp))
            baseline["compile"]["candidate_output"]["sha256"] = "not-the-output-sha"

            with self.assertRaises(SystemExit) as raised:
                module.validate_c2rust_baseline_compile_status(baseline, output_ref, manifest_path)

            self.assertIn("c2rust_baseline compile candidate_output drift", str(raised.exception))

    def test_rejects_c2rust_compile_semantic_pass_spoof(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            baseline, output_ref, manifest_path = self._c2rust_compile_fixture(Path(tmp))
            baseline["compile"]["semantic_pass"] = True

            with self.assertRaises(SystemExit) as raised:
                module.validate_c2rust_baseline_compile_status(baseline, output_ref, manifest_path)

            self.assertIn("c2rust_baseline compile status cannot claim semantic_pass", str(raised.exception))

    def test_rejects_c2rust_compile_artifact_contradictions(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            baseline, output_ref, manifest_path = self._c2rust_compile_fixture(Path(tmp))
            baseline["compile"]["status"] = "failed"

            with self.assertRaises(SystemExit) as raised:
                module.validate_c2rust_baseline_compile_status(baseline, output_ref, manifest_path)

            self.assertIn("c2rust_baseline compile artifact must be null unless compile passed", str(raised.exception))

        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            baseline, output_ref, manifest_path = self._c2rust_compile_fixture(Path(tmp))
            baseline["compile"]["artifact"] = None

            with self.assertRaises(SystemExit) as raised:
                module.validate_c2rust_baseline_compile_status(baseline, output_ref, manifest_path)

            self.assertIn("c2rust_baseline.compile.artifact", str(raised.exception))

        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            baseline, output_ref, manifest_path = self._c2rust_compile_fixture(Path(tmp))
            baseline["compile"]["artifact"]["sha256"] = "not-the-artifact-sha"

            with self.assertRaises(SystemExit) as raised:
                module.validate_c2rust_baseline_compile_status(baseline, output_ref, manifest_path)

            self.assertIn("c2rust_baseline.compile.artifact sha256 mismatch", str(raised.exception))

    def test_rejects_l4_refused_route_with_generated_candidate_manifest(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            prefix = "l3-adler32-step"
            route_path = evidence_dir / f"{prefix}-route-decision.json"
            profile_path = evidence_dir / f"{prefix}-validation-profile.json"

            route = json.loads(route_path.read_text(encoding="utf-8"))
            route["level"] = "L4"
            route["status"] = "refused"
            route["translator"] = {"kind": "refuse", "candidate_generation_allowed": False}
            route["verification_profile"] = "L4-dev"
            self._write_json(route_path, route)

            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["status"] = "blocked"
            profile["profile"] = "L4-dev"
            profile["route_level"] = "L4"
            profile["skipped_gates"] = [{"gate": "candidate_generation", "reason": "route_refused"}]
            self._write_json(profile_path, profile)

            route_ref = self._ref(route_path, "refused")
            route_ref["level"] = "L4"
            profile_ref = self._ref(profile_path, "blocked")
            profile_ref["profile"] = "L4-dev"

            for file_name in [
                f"{prefix}-auto-translation-manifest.json",
                f"{prefix}-evidence-manifest.json",
                f"{prefix}-final-verification.json",
            ]:
                path = evidence_dir / file_name
                payload = json.loads(path.read_text(encoding="utf-8"))
                if file_name.endswith("evidence-manifest.json"):
                    payload["evidence"]["route_decision"] = route_ref
                    payload["evidence"]["validation_profile"] = profile_ref
                else:
                    payload["route_decision"] = route_ref
                    payload["validation_profile"] = profile_ref
                if file_name.endswith("auto-translation-manifest.json"):
                    payload["status"] = "candidate_generated"
                self._write_json(path, payload)

            cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache["route_decision_identity"] = {"status": "refused", "sha256": self._sha256_json(route)}
            cache["validation_profile_identity"] = {"status": "blocked", "sha256": self._sha256_json(profile)}
            cache["dependent_artifacts"]["route_decision"] = route_ref
            cache["dependent_artifacts"]["validation_profile"] = profile_ref
            self._write_json(cache_path, cache)

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
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
            self.assertIn(
                "L4/refused route cannot have generated candidate evidence",
                result.stderr + result.stdout,
            )

    def test_rejects_l4_refused_route_with_nested_candidate_artifacts(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"
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

            evidence_dir = out_root / "zlib-ng" / "auto-translation" / "adler32-step"
            prefix = "l3-adler32-step"
            route_path = evidence_dir / f"{prefix}-route-decision.json"
            profile_path = evidence_dir / f"{prefix}-validation-profile.json"

            route = json.loads(route_path.read_text(encoding="utf-8"))
            route["level"] = "L4"
            route["status"] = "refused"
            route["translator"] = {"kind": "refuse", "candidate_generation_allowed": False}
            route["verification_profile"] = "L4-dev"
            self._write_json(route_path, route)

            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["status"] = "blocked"
            profile["profile"] = "L4-dev"
            profile["route_level"] = "L4"
            profile["skipped_gates"] = [{"gate": "candidate_generation", "reason": "route_refused"}]
            self._write_json(profile_path, profile)

            route_ref = self._ref(route_path, "refused")
            route_ref["level"] = "L4"
            profile_ref = self._ref(profile_path, "blocked")
            profile_ref["profile"] = "L4-dev"

            for file_name in [
                f"{prefix}-auto-translation-manifest.json",
                f"{prefix}-evidence-manifest.json",
                f"{prefix}-final-verification.json",
            ]:
                path = evidence_dir / file_name
                payload = json.loads(path.read_text(encoding="utf-8"))
                if file_name.endswith("evidence-manifest.json"):
                    payload["evidence"]["route_decision"] = route_ref
                    payload["evidence"]["validation_profile"] = profile_ref
                else:
                    payload["route_decision"] = route_ref
                    payload["validation_profile"] = profile_ref
                if file_name.endswith("auto-translation-manifest.json"):
                    payload["status"] = "candidate_refused"
                    payload.setdefault("generated_artifacts", []).append(
                        {"kind": "rust_draft", "status": "draft_generated"}
                    )
                self._write_json(path, payload)

            cache_path = evidence_dir / f"{prefix}-auto-cache-metadata.json"
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            cache["route_decision_identity"] = {"status": "refused", "sha256": self._sha256_json(route)}
            cache["validation_profile_identity"] = {"status": "blocked", "sha256": self._sha256_json(profile)}
            cache["dependent_artifacts"]["route_decision"] = route_ref
            cache["dependent_artifacts"]["validation_profile"] = profile_ref
            self._write_json(cache_path, cache)

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--target-id",
                    "zlib-ng",
                    "--slice-id",
                    "adler32-step",
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
            self.assertIn(
                "L4/refused route cannot contain candidate artifact status",
                result.stderr + result.stdout,
            )

    def test_l4_refused_status_scanner_rejects_draft_and_accepted_artifact_statuses(self) -> None:
        validator = load_validator_module()

        paths = validator.candidate_status_paths(
            {
                "generated_artifacts": [
                    {"status": "draft_generated"},
                    {"status": "accepted_after_gates"},
                    {"status": "accepted_evidence_bound"},
                ]
            }
        )

        self.assertIn("$.generated_artifacts[0].status", paths)
        self.assertIn("$.generated_artifacts[1].status", paths)
        self.assertIn("$.generated_artifacts[2].status", paths)

    def test_rejects_l4_unsupported_control_flow_cfg_without_relooper_refusal_contract(self) -> None:
        validator = load_validator_module()
        cfg = {
            "unsupported_control_flow": [
                {
                    "id": "unsupported-1",
                    "kind": "goto",
                    "reason": "goto requires CFG/relooper support",
                    "source_span": {"file": "slice-spec", "line_start": 1, "line_end": 1},
                    "translation_effect": "requires_relooper",
                }
            ],
            "functions": [
                {
                    "name": "again",
                    "basic_blocks": [{"id": "entry", "kind": "entry", "statements": []}],
                    "edges": [],
                    "structured_control_flow": {
                        "has_goto": True,
                        "has_switch": False,
                        "relooper_required": False,
                        "relooper_refusals": [],
                    },
                }
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            validator.validate_unsupported_control_flow_cfg_contract(cfg, "unit-test-cfg")

        self.assertIn("unsupported control-flow CFG contract", str(raised.exception))

    def test_l4_refused_repair_playbook_rejects_missing_required_fields(self) -> None:
        validator = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            evidence_dir = Path(tmp)
            blocked_path = evidence_dir / "l3-demo-self-healing-blocked-repairs.json"
            blocked_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "target_id": "demo",
                        "slice_id": "demo",
                        "status": "recorded",
                        "blocked_repairs": [
                            {
                                "repair_id": "repair-route-refused-1",
                                "blocked_reason": "route refused",
                                "forbidden_change": "unsupported_control_flow",
                                "candidate_patch_id": "patch-route-refused-1",
                                "source_span": {"file": "candidate.rs", "line_start": 1, "line_end": 1},
                                "human_action_required": True,
                            }
                        ],
                        "cache_invalidation_keys": ["source_commit=1234567"],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as raised:
                validator.validate_l4_refused_repair_playbook(evidence_dir, "l3-demo")

            self.assertIn("repair playbook", str(raised.exception))
