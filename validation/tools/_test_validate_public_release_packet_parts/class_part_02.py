class _PublicReleasePacketValidatorTestsPart02:
    def test_validate_packet_rejects_summary_identity_drift_from_bound_bundle(self) -> None:
        cases = [
            (
                "entrypoint-count",
                lambda packet: packet["summary"].__setitem__("entrypoint_count", 999),
                "summary.entrypoint_count must match judge_entrypoints_run_report.entrypoint_count",
            ),
            (
                "publication-scope",
                lambda packet: packet["summary"].__setitem__("publication_scope", "full"),
                "summary.publication_scope must match judge_milestone_bundle.publication_manifest",
            ),
            (
                "readiness",
                lambda packet: packet["summary"].__setitem__(
                    "readiness",
                    {**packet["summary"]["readiness"], "executed_count": 999},
                ),
                "summary.readiness must match judge_entrypoints_run_report.summary.readiness",
            ),
        ]
        for suffix, mutate, expected_error in cases:
            with self.subTest(suffix=suffix):
                temp_dir = Path(
                    tempfile.mkdtemp(
                        prefix=f"public-release-packet-summary-{suffix}-",
                        dir=REPO_ROOT / "target",
                    )
                )
                packet_path = temp_dir / "summary" / "public-release-packet.json"
                packet = valid_packet(temp_dir)
                mutate(packet)
                write_json(packet_path, packet)

                result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

                self.assertEqual(result["status"], "failed")
                self.assertTrue(
                    any(expected_error in error for error in result["errors"]),
                    result["errors"],
                )

    def test_validate_packet_rejects_missing_workflow_metrics_summary_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-workflow-summary-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["summary"].pop("workflow_metrics")
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("workflow_metrics" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_progress_delta_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-progress-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["summary"]["progress_delta_ledger"] = {
            **packet["summary"]["progress_delta_ledger"],
            "capability_delta": {
                **packet["summary"]["progress_delta_ledger"]["capability_delta"],
                "delta_count": 999,
            },
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("summary.progress_delta_ledger must match judge_milestone_bundle.progress_delta_ledger" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_summary_proof_class_rollup_drift_from_bound_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-proof-class-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["summary"]["proof_class_rollup"] = {
            "all": ["competition-exact"],
            "highest_proof_class": "competition-exact",
            "has_competition_exact": True,
            "all_entrypoints_competition_exact": True,
            "competition_exact_host_verified": True,
            "entrypoints": [
                {
                    "id": "forged",
                    "proof_class": "competition-exact",
                    "run_id": "forged-run",
                }
            ],
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "summary.proof_class_rollup must match judge_milestone_bundle.proof_class_rollup" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_bundle_proof_class_rollup_drift_from_run_report(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-proof-class-run-report-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publishability"].update(
            {
                "status": "external_release_ready",
                "publication_scope": "full",
                "external_milestone_claim_ready": True,
                "external_milestone": True,
                "competition_exact_publishable": True,
                "focused_run": False,
            }
        )
        packet["competition_host_readiness"].update(
            {
                "status": "ready",
                "actual_highest_proof_class": "competition-exact",
                "all_entrypoints_competition_exact": True,
                "competition_exact_host_verified": True,
                "external_milestone_claim_ready": True,
                "missing_requirements": [],
                "blocker_count": 0,
            }
        )
        packet["summary"]["proof_class_rollup"].update(
            {
                "all": ["competition-exact"],
                "highest_proof_class": "competition-exact",
                "has_competition_exact": True,
                "all_entrypoints_competition_exact": True,
                "competition_exact_host_verified": True,
                "entrypoints": [
                    {
                        "id": "opencode_multi_worker_evaluate_profile",
                        "proof_class": "competition-exact",
                        "run_id": "fixture-run",
                        "competition_exact_host_attested": True,
                    }
                ],
                "non_exact_entrypoints": [],
                "host_attestation_missing_entrypoints": [],
            }
        )
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["proof_class"] = "competition-exact"
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "judge_milestone_bundle.proof_class_rollup must match recomputed "
                "judge_entrypoints_run_report.entrypoints proof_class_rollup" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_run_report_ref_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-run-ref-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        alternate_report = write_text_artifact(
            temp_dir / "summary" / "alternate-judge-entrypoints-run-report.json",
            '{"status":"passed","source":"alternate"}\n',
        )
        packet["judge_entrypoints_run_report"] = alternate_report
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("judge_entrypoints_run_report must match judge_milestone_bundle.judge_entrypoints_run_report" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_release_notes_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-notes-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        stale_notes = write_text_artifact(
            temp_dir / "summary" / "stale-milestone-release-notes.md",
            "# stale notes\n\nThese notes were not rendered from the bound milestone bundle.\n",
        )
        packet["milestone_release_notes"] = stale_notes
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("milestone_release_notes must match judge_milestone_bundle rendered release notes" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_semantic_gate_overclaim(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-overclaim-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["claim_boundary"]["semantic_gate"] = True
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("claim_boundary.semantic_gate must be false" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_local_absolute_path_leak(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-path-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["reproduction_commands"]["run_judge_entrypoints"] = "C:\\Python314\\python.exe -m validation.tools.run_judge_entrypoints"
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("forbidden local absolute path" in error for error in result["errors"]), result["errors"])

    def test_core_validation_ci_runs_public_packet_validator_tests(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/core-translator-validation-ci.yml").read_text(encoding="utf-8")
        self.assertIn("validation.tools.test_validate_public_release_packet", workflow)
