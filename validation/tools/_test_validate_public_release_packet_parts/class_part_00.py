class _PublicReleasePacketValidatorTestsPart00:
    def test_validate_packet_binds_hashes_and_claim_boundary(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["packet"]["path"], repo_relative(packet_path))
        self.assertEqual(result["artifact_refs"]["checked_count"], 4)
        self.assertFalse(result["claim_boundary"]["semantic_gate"])
        self.assertEqual(result["claim_boundary"]["translation_coverage_numerator"], 0)
        self.assertEqual(
            packet["before_after_repair_exhibit"]["sources"][0]["before_after_units"][0]["patch_origin"]["source"],
            "accepted_safe_evidence",
        )
        self.assertFalse(packet["before_after_repair_exhibit"]["semantic_gate"])
        self.assertEqual(packet["before_after_repair_exhibit"]["translation_coverage_numerator"], 0)
        self.assertEqual(packet["publishability"]["status"], "internal_preview")
        self.assertFalse(packet["publishability"]["competition_exact_publishable"])
        self.assertEqual(packet["publishability"]["required_agent"], "c2rust-migrator")
        self.assertEqual(packet["publishability"]["required_model"], "GLM-5.1")
        self.assertEqual(packet["publishability"]["required_variant"], "max")
        self.assertEqual(packet["competition_host_readiness"]["status"], "blocked")
        self.assertEqual(packet["competition_host_readiness"]["required_agent"], "c2rust-migrator")
        self.assertEqual(packet["competition_host_readiness"]["required_model"], "GLM-5.1")
        self.assertEqual(packet["competition_host_readiness"]["required_variant"], "max")
        self.assertEqual(packet["competition_host_readiness"]["required_proof_class"], "competition-exact")
        self.assertFalse(packet["competition_host_readiness"]["competition_exact_host_verified"])
        self.assertIn(
            "competition_exact_host_verified",
            packet["competition_host_readiness"]["missing_requirements"],
        )
        self.assertEqual(
            [entry["stage"] for entry in packet["harness_architecture_summary"]["contract_matrix"]],
            ["plan", "translate", "verify", "repair", "report"],
        )
        self.assertFalse(packet["harness_architecture_summary"]["semantic_gate"])
        self.assertEqual(packet["evidence_cost_retention"]["rollup"]["artifact_count"], 3)
        self.assertEqual(packet["evidence_cost_retention"]["rollup"]["total_bytes"], 120)
        notes_text = (REPO_ROOT / packet["milestone_release_notes"]["path"]).read_text(encoding="utf-8")
        self.assertIn("| raw C2Rust | manifest_status_observed | no | 0 | 2 manifests / 2 sources / 0 compile-pass |", notes_text)

    def test_validate_packet_rejects_passed_bundle_without_published_artifact_refs(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-empty-published-refs-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))

        packet["publication_manifest"]["published_artifact_refs"] = []
        packet["publication_manifest"]["published_artifact_count"] = 0
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        packet["summary"]["published_artifact_ref_status"] = packet_validator.expected_published_artifact_ref_status(
            packet["publication_manifest"]
        )
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("passed bundle must publish at least one hash-bound artifact ref" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_passed_bundle_without_published_judge_evidence_index(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-no-judge-index-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        refs = [
            ref
            for ref in packet["publication_manifest"]["published_artifact_refs"]
            if ref.get("artifact_name") != "judge_evidence_index"
        ]
        packet["publication_manifest"]["published_artifact_refs"] = refs
        packet["publication_manifest"]["published_artifact_count"] = len(refs)
        packet["summary"]["published_artifact_ref_status"] = packet_validator.expected_published_artifact_ref_status(
            packet["publication_manifest"]
        )
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("passed bundle must publish a present judge_evidence_index artifact ref" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_competition_config_archive_drift_from_bound_run_report(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)

        run_report_path = REPO_ROOT / packet["judge_entrypoints_run_report"]["path"]
        run_report_payload = json.loads(run_report_path.read_text(encoding="utf-8"))
        drifted_archive = json.loads(json.dumps(packet["competition_config_archive"]))
        drifted_archive["external_ref_count"] += 1
        run_report_payload["competition_config_archive"] = drifted_archive
        write_json(run_report_path, run_report_payload)
        run_report_ref = {
            "path": repo_relative(run_report_path),
            "status": "present",
            "sha256": judge_validator.sha256_file(run_report_path),
        }
        packet["judge_entrypoints_run_report"] = run_report_ref
        packet["publication_manifest"]["judge_entrypoints_run_report"] = run_report_ref
        for ref in packet["publication_manifest"]["published_artifact_refs"]:
            if ref.get("artifact_name") == "judge_entrypoints_run_report":
                ref.update(run_report_ref)

        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["judge_entrypoints_run_report"] = run_report_ref
        bundle_payload["publication_manifest"]["judge_entrypoints_run_report"] = run_report_ref
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)

        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "competition_config_archive must match judge_entrypoints_run_report.competition_config_archive" in error
                for error in result["errors"]
            )
        )

    def test_public_release_packet_schema_requires_summary_blockers(self) -> None:
        schema = json.loads((REPO_ROOT / "validation" / "public-release-packet.schema.json").read_text(encoding="utf-8"))
        self.assertIn("blockers", schema["properties"]["summary"]["required"])
        self.assertEqual(schema["properties"]["summary"]["properties"]["blockers"]["items"]["type"], "string")
        self.assertIn("published_artifact_ref_status", schema["properties"]["summary"]["required"])
        ref_status = schema["properties"]["summary"]["properties"]["published_artifact_ref_status"]
        self.assertEqual(ref_status["properties"]["semantic_gate"]["const"], False)
        self.assertEqual(ref_status["properties"]["translation_coverage_numerator"]["const"], 0)
        self.assertIn("harness_architecture_summary", schema["required"])
        self.assertIn("evidence_cost_retention", schema["required"])
        self.assertIn("competition_host_readiness", schema["required"])
        publishability = schema["properties"]["publishability"]
        self.assertIn("required_variant", publishability["required"])
        self.assertEqual(publishability["properties"]["required_variant"]["const"], "max")
        host_readiness = schema["properties"]["competition_host_readiness"]
        self.assertEqual(host_readiness["$ref"], "#/$defs/competitionHostReadiness")
        host_readiness = schema["$defs"]["competitionHostReadiness"]
        self.assertEqual(host_readiness["properties"]["report_kind"]["const"], "competition-host-readiness")
        self.assertEqual(host_readiness["properties"]["required_agent_tool"]["const"], "opencode")
        self.assertEqual(host_readiness["properties"]["required_agent"]["const"], "c2rust-migrator")
        self.assertEqual(host_readiness["properties"]["required_model"]["const"], "GLM-5.1")
        self.assertEqual(host_readiness["properties"]["required_variant"]["const"], "max")
        self.assertEqual(host_readiness["properties"]["required_proof_class"]["const"], "competition-exact")
        self.assertEqual(host_readiness["properties"]["semantic_gate"]["const"], False)
        self.assertEqual(host_readiness["properties"]["translation_coverage_numerator"]["const"], 0)
        self.assertIn("release_tag_readiness", schema["properties"]["publication_manifest"]["required"])
        tag_readiness = schema["properties"]["publication_manifest"]["properties"]["release_tag_readiness"]
        self.assertEqual(tag_readiness["$ref"], "#/$defs/releaseTagReadiness")
        tag_readiness = schema["$defs"]["releaseTagReadiness"]
        self.assertEqual(tag_readiness["properties"]["report_kind"]["const"], "release-tag-readiness")
        self.assertEqual(tag_readiness["properties"]["semantic_gate"]["const"], False)
        self.assertEqual(tag_readiness["properties"]["translation_coverage_numerator"]["const"], 0)
        preflight_summary = schema["$defs"]["opencodePreflightProofSummary"]
        self.assertIn("opencode_agent", preflight_summary["required"])
        self.assertIn("opencode_variant", preflight_summary["required"])
        self.assertEqual(preflight_summary["properties"]["opencode_agent"]["const"], "c2rust-migrator")
        self.assertEqual(preflight_summary["properties"]["opencode_variant"]["const"], "max")
        before_after_rollup = schema["properties"]["before_after_repair_exhibit"]["properties"]["rollup"]
        self.assertIn("verified_baseline_unit_count", before_after_rollup["required"])
        self.assertIn("missing_verified_baseline_unit_count", before_after_rollup["required"])
        self.assertIn("all_units_verified_baseline_bound", before_after_rollup["required"])

    def test_public_release_packet_schema_requires_before_after_verified_baseline_rollup(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-baseline-rollup-", dir=REPO_ROOT / "target"))
        packet = valid_packet(temp_dir)
        schema = judge_validator.load_json(packet_validator.PACKET_SCHEMA)

        for field in (
            "verified_baseline_unit_count",
            "missing_verified_baseline_unit_count",
            "all_units_verified_baseline_bound",
        ):
            with self.subTest(field=field):
                missing_rollup = json.loads(json.dumps(packet))
                missing_rollup["before_after_repair_exhibit"]["rollup"].pop(field)
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(missing_rollup, schema)

        invalid_rollup = json.loads(json.dumps(packet))
        invalid_rollup["before_after_repair_exhibit"]["rollup"]["all_units_verified_baseline_bound"] = "true"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid_rollup, schema)

    def test_validate_packet_rejects_harness_contract_matrix_missing_report_stage(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-harness-matrix-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["harness_architecture_summary"]["contract_matrix"] = [
            entry
            for entry in packet["harness_architecture_summary"]["contract_matrix"]
            if entry["stage"] != "report"
        ]
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("harness_architecture_summary" in error and "contract_matrix" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_evidence_cost_retention_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-evidence-cost-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["evidence_cost_retention"]["rollup"]["total_bytes"] += 1
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "evidence_cost_retention must match judge_milestone_bundle.evidence_cost_retention" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_requires_opencode_patch_boundary(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-boundary-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet.pop("opencode_patch_boundary")
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("opencode_patch_boundary" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_requires_glm_preflight_proof_when_opencode_runtime_enabled(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-preflight-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"].pop("opencode_preflight_proof_summary")
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("opencode_preflight_proof_summary" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_non_glm_preflight_proof(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-non-glm-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["required_model"] = "gpt-5.1"
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("required_model must be GLM-5.1" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_rejects_wrong_opencode_agent_in_preflight_proof(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-agent-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["opencode_agent"] = "general"
        sync_packet_bound_bundle(packet, rebuild_release_notes=False)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("opencode_agent" in error and "c2rust-migrator" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_wrong_opencode_variant_in_preflight_proof(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-variant-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["opencode_variant"] = "small"
        sync_packet_bound_bundle(packet, rebuild_release_notes=False)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("opencode_variant" in error and "max" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_allows_competition_exact_preflight_when_host_ready(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-exact-ready-", dir=REPO_ROOT / "target"))
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
        rewrite_bound_run_report(
            packet,
            lambda payload: (
                payload["entrypoints"][0].update(
                    {
                        "proof_class": "competition-exact",
                        "competition_exact_host_attested": True,
                    }
                ),
                payload["validation"]["proof_class_contract"]["entrypoints"].__setitem__(
                    "opencode_multi_worker_evaluate_profile",
                    "competition-exact",
                ),
            ),
        )
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["proof_class"] = "competition-exact"
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed", result["errors"])

    def test_validate_packet_rejects_host_ready_when_proof_class_rollup_is_local_simulation(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-host-ready-rollup-drift-", dir=REPO_ROOT / "target"))
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
                "all_entrypoints_competition_exact": True,
                "competition_exact_host_verified": True,
                "external_milestone_claim_ready": True,
                "missing_requirements": [],
                "blocker_count": 0,
            }
        )
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["proof_class"] = "competition-exact"
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "competition_host_readiness.all_entrypoints_competition_exact must match "
                "judge_milestone_bundle.proof_class_rollup.all_entrypoints_competition_exact" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_competition_exact_preflight_when_host_blocked(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-exact-blocked-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["proof_class"] = "competition-exact"
        sync_packet_bound_bundle(packet, rebuild_release_notes=False)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("proof_class must not claim competition-exact without host attestation" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_preflight_runtime_env_sha_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-runtime-env-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        proof = packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]
        proof["opencode_runtime_env_sha256"] = "0" * 64
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("opencode_runtime_env_sha256" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_accepts_deep_bound_opencode_safety_attempt(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-attempt-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        attempt_ref = write_opencode_safety_transform_attempt_fixture(temp_dir)
        attach_opencode_safety_attempt(packet, attempt_ref)
        attach_bound_opencode_judge_index(packet, temp_dir, attempt_ref)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed", result["errors"])

    def test_validate_packet_rejects_opencode_safety_attempt_missing_from_published_judge_evidence_index(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-attempt-missing-index-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        attempt_ref = write_opencode_safety_transform_attempt_fixture(temp_dir)
        attach_opencode_safety_attempt(packet, attempt_ref)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("judge_evidence_index must bind opencode_safety_transform_attempt" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_published_judge_index_opencode_attempt_source_mismatch(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-index-attempt-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        attempt_ref = write_opencode_safety_transform_attempt_fixture(temp_dir)
        attach_opencode_safety_attempt(packet, attempt_ref)

        index_payload = judge_entrypoint_fixtures.valid_opencode_judge_index_payload()
        judge_entrypoint_fixtures.materialize_opencode_judge_index_artifacts(
            index_payload,
            temp_dir / "judge-out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **judge_entrypoint_fixtures.opencode_launch_policy(),
                "auto_retry": True,
            },
        )
        index_payload["evidence_artifact_refs"]["opencode_safety_transform_attempt"] = json.loads(
            json.dumps(attempt_ref)
        )
        worker = index_payload["opencode_agent_runtime"]["workers"][0]
        worker["opencode_safety_transform_attempt"] = json.loads(json.dumps(attempt_ref))
        other_attempt_path = temp_dir / "judge-out" / "workers" / "worker-a" / "harness" / "other-attempt.json"
        write_json(other_attempt_path, {"report_kind": "test-opencode-safety-transform-attempt", "id": "drifted"})
        worker_report_path = REPO_ROOT / worker["worker_report"]["path"]
        worker_report = json.loads(worker_report_path.read_text(encoding="utf-8"))
        worker_report["opencode_safety_transform_attempt"] = {
            "path": repo_relative(other_attempt_path),
            "sha256": judge_validator.sha256_file(other_attempt_path),
        }
        write_json(worker_report_path, worker_report)
        worker["worker_report"]["sha256"] = judge_validator.sha256_file(worker_report_path)

        index_path = temp_dir / "judge-out" / "harness" / "judge-evidence-index.json"
        write_json(index_path, index_payload)
        index_ref = {
            "artifact_name": "judge_evidence_index",
            "entrypoint_id": "opencode_multi_worker_evaluate_profile",
            "path": repo_relative(index_path),
            "status": "present",
            "sha256": judge_validator.sha256_file(index_path),
        }
        remove_published_artifact_ref(
            packet,
            artifact_name="judge_evidence_index",
            entrypoint_id="opencode_multi_worker_evaluate_profile",
        )
        append_published_artifact_ref(packet, index_ref)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publication_manifest"] = json.loads(json.dumps(packet["publication_manifest"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "publication_manifest.published_artifact_refs[].judge_evidence_index contract failed" in error
                and "worker_report.opencode_safety_transform_attempt must match opencode_safety_transform_attempt"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_opencode_safety_attempt_boundary_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-attempt-hash-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        attempt_ref = write_opencode_safety_transform_attempt_fixture(temp_dir)
        attach_opencode_safety_attempt(packet, attempt_ref)
        packet["opencode_patch_boundary"]["opencode_safety_transform_attempt"]["sha256"] = "0" * 64
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("opencode_safety_transform_attempt.sha256 must match" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_opencode_safety_attempt_non_five_round_cap(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-attempt-rounds-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        attempt_ref = write_opencode_safety_transform_attempt_fixture(temp_dir, max_repair_rounds=4)
        attach_opencode_safety_attempt(packet, attempt_ref)
        packet["opencode_patch_boundary"]["opencode_safety_transform_attempt"]["max_repair_rounds"] = 4
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("attempt_contract.max_repair_rounds must be 5" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_opencode_safety_attempt_retry_patch_event_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-attempt-events-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        attempt_ref = write_opencode_safety_transform_attempt_fixture(temp_dir)
        attempt_path = REPO_ROOT / attempt_ref["path"]
        payload = json.loads(attempt_path.read_text(encoding="utf-8"))
        evidence_root = attempt_path.parent / "attempt-evidence"
        rollback = write_text_artifact(evidence_root / "rollback.json", '{"status":"rolled_back"}\n')
        patch_events = write_text_artifact(evidence_root / "patch-events.jsonl", '{"event":"repair"}\n')
        payload["safety_transform_units"][0]["accepted_retry_hint"] = {
            "status": "revalidated_passed",
            "repair_rounds": 1,
            "auto_recovered": True,
            "rollback_ids": [rollback["path"]],
            "rollback_evidence": [rollback],
            "patch_events_path": patch_events["path"],
            "patch_events_sha256": "0" * 64,
        }
        write_json(attempt_path, payload)
        attempt_ref["sha256"] = judge_validator.sha256_file(attempt_path)
        attach_opencode_safety_attempt(packet, attempt_ref)
        attempt_summary = packet["opencode_patch_boundary"]["opencode_safety_transform_attempt"]
        attempt_summary["accepted_retry_hint_status"] = "revalidated_passed"
        attempt_summary["accepted_retry_hint_statuses"] = ["revalidated_passed"]
        attempt_summary["rollback_ref_count"] = 1
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("patch_events_sha256" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_rejects_preflight_session_without_shell_call(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-no-shell-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        rewrite_packet_preflight_session(
            packet,
            {
                "schema_version": 1,
                "process_returncode": 0,
                "parsed": True,
                "format": "jsonl",
                "session_events": [],
            },
        )
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "contract_verification.status recomputed from opencode_session_evidence must be executed" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_failed_preflight_session_evidence_contract(self) -> None:
        cases = [
            ("nonzero_returncode", {"process_returncode": 1}, "process_returncode must be 0"),
            ("unparsed_session", {"parsed": False}, "parsed must be true"),
            ("non_jsonl_format", {"format": "text"}, "format must be jsonl"),
        ]
        for case_name, updates, expected_error in cases:
            with self.subTest(case=case_name):
                temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-session-contract-", dir=REPO_ROOT / "target"))
                packet_path = temp_dir / "summary" / "public-release-packet.json"
                packet = valid_packet(temp_dir)
                preflight_payload = json.loads(packet_preflight_path(packet).read_text(encoding="utf-8"))
                session_path = REPO_ROOT / preflight_payload["opencode_session_evidence"]["path"]
                session_payload = json.loads(session_path.read_text(encoding="utf-8"))
                session_payload.update(updates)
                rewrite_packet_preflight_session(packet, session_payload)
                sync_packet_bound_bundle(packet)
                write_json(packet_path, packet)

                result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

                self.assertEqual(result["status"], "failed")
                self.assertTrue(
                    any(f"opencode_session_evidence.{expected_error}" in error for error in result["errors"]),
                    result["errors"],
                )

    def test_validate_packet_rejects_preflight_first_shell_mismatch_even_if_marker_runs_later(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-late-marker-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        marker_command_line = packet_preflight_marker_command_line(packet)
        rewrite_packet_preflight_session(
            packet,
            {
                "schema_version": 1,
                "process_returncode": 0,
                "parsed": True,
                "format": "jsonl",
                "session_events": [
                    {
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": "python3 -B -c 'print(1)'", "workdir": str(REPO_ROOT)}},
                        }
                    },
                    {
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": marker_command_line, "workdir": str(REPO_ROOT)}},
                        }
                    },
                ],
            },
        )
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("first_shell_command_mismatch_worker_command_seen_later" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_preflight_session_evidence_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-session-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        preflight_payload = json.loads(packet_preflight_path(packet).read_text(encoding="utf-8"))
        session_path = REPO_ROOT / preflight_payload["opencode_session_evidence"]["path"]
        session_payload = json.loads(session_path.read_text(encoding="utf-8"))
        session_payload["session_events"] = []
        write_json(session_path, session_payload)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("opencode_session_evidence sha256 mismatch" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_deep_validates_preflight_even_when_runtime_flag_false(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-runtime-flag-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"]["opencode_runtime_enabled"] = False
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["preflight_report"]["sha256"] = "0" * 64
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("opencode-preflight-report" in error and "sha256 mismatch" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_opencode_runtime_enabled_drift_from_bound_bundle(self) -> None:
        temp_dir = Path(
            tempfile.mkdtemp(prefix="public-release-packet-opencode-runtime-enabled-drift-", dir=REPO_ROOT / "target")
        )
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["opencode_patch_boundary"]["opencode_runtime_enabled"] = False
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "opencode_patch_boundary.opencode_runtime_enabled must match "
                "judge_milestone_bundle.opencode_runtime.enabled_entrypoint_count" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_preflight_handoff_contract_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-opencode-handoff-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        preflight_payload = json.loads(packet_preflight_path(packet).read_text(encoding="utf-8"))
        handoff_path = REPO_ROOT / preflight_payload["handoff_contract"]["path"]
        handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff_payload["worker_command_line"] = "python3 -B -c 'print(1)'"
        write_json(handoff_path, handoff_payload)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("handoff_contract sha256 mismatch" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_preflight_handoff_missing_opencode_run_argv(self) -> None:
        temp_dir = Path(
            tempfile.mkdtemp(prefix="public-release-packet-opencode-handoff-missing-argv-", dir=REPO_ROOT / "target")
        )
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        preflight_path = packet_preflight_path(packet)
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        handoff_path = REPO_ROOT / preflight_payload["handoff_contract"]["path"]
        handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff_payload.pop("opencode_argv")
        write_json(handoff_path, handoff_payload)
        preflight_payload["handoff_contract"]["sha256"] = judge_validator.sha256_file(handoff_path)
        write_json(preflight_path, preflight_payload)
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["preflight_report"]["sha256"] = (
            judge_validator.sha256_file(preflight_path)
        )
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("handoff_contract.opencode_argv must be a non-empty string list" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_preflight_handoff_launch_policy_drift(self) -> None:
        temp_dir = Path(
            tempfile.mkdtemp(prefix="public-release-packet-opencode-handoff-policy-", dir=REPO_ROOT / "target")
        )
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        preflight_path = packet_preflight_path(packet)
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        handoff_path = REPO_ROOT / preflight_payload["handoff_contract"]["path"]
        handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff_payload["launch_policy"]["opencode_skip_permissions"] = True
        handoff_payload["launch_policy_sha256"] = judge_validator.sha256_text(
            json.dumps(handoff_payload["launch_policy"], sort_keys=True)
        )
        write_json(handoff_path, handoff_payload)
        preflight_payload["handoff_contract"]["sha256"] = judge_validator.sha256_file(handoff_path)
        write_json(preflight_path, preflight_payload)
        packet["opencode_patch_boundary"]["opencode_preflight_proof_summary"]["preflight_report"]["sha256"] = (
            judge_validator.sha256_file(preflight_path)
        )
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("handoff_contract.launch_policy must match preflight_report.launch_policy" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_preflight_marker_payload_run_id_drift(self) -> None:
        temp_dir = Path(
            tempfile.mkdtemp(prefix="public-release-packet-opencode-marker-payload-", dir=REPO_ROOT / "target")
        )
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        preflight_payload = json.loads(packet_preflight_path(packet).read_text(encoding="utf-8"))
        marker_path = REPO_ROOT / preflight_payload["marker_path"]
        marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
        marker_payload["run_id"] = "different-run"
        write_json(marker_path, marker_payload)
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("marker.run_id must match preflight_report.run_id" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_artifact_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["judge_milestone_bundle"]["sha256"] = "0" * 64
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("sha256 mismatch" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_requires_archive_bundle_manifest_file_ref(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        del packet["competition_config_archive"]["files"]["config/competition-env/bundle-manifest.json"]
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_config_archive.files must include config/competition-env/bundle-manifest.json" in error for error in result["errors"]),
            result["errors"],
        )
