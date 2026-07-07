class _PublicReleasePacketValidatorTestsPart01:
    def test_validate_packet_requires_archive_external_reproduction_refs(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-refs-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["competition_config_archive"]["external_refs"] = {}
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_config_archive.external_refs missing required refs" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_publication_archive_external_ref_projection_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-publication-refs-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        dropped_ref = next(iter(packet["publication_manifest"]["competition_config_archive"]["external_refs"]))
        del packet["publication_manifest"]["competition_config_archive"]["external_refs"][dropped_ref]
        packet["publication_manifest"]["competition_config_archive"]["external_ref_count"] -= 1

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
                "publication_manifest.competition_config_archive.external_refs must match competition_config_archive.external_refs"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_publication_archive_summary_projection_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-publication-summary-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publication_manifest"]["competition_config_archive"]["file_count"] += 1

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
                "publication_manifest.competition_config_archive.file_count must match competition_config_archive.file_count"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_requires_archive_manifest_listed_config_files(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-manifest-files-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        del packet["competition_config_archive"]["files"]["config/competition-env/environment.json"]
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_config_archive.files missing bundle-manifest listed files" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_archive_bundle_manifest_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["competition_config_archive"]["files"]["config/competition-env/bundle-manifest.json"]["sha256"] = "0" * 64
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_config_archive.files.config/competition-env/bundle-manifest.json" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_archive_file_role_drift_from_bundle_manifest(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-role-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["competition_config_archive"]["files"]["config/competition-env/environment.json"]["role"] = "wrong-role"
        manifest_payload = json.loads(json.dumps(packet["competition_config_archive"]))
        manifest_payload.pop("materialized_manifest", None)
        archive_manifest_path = REPO_ROOT / packet["competition_config_archive"]["materialized_manifest"]["path"]
        write_json(archive_manifest_path, manifest_payload)
        packet["competition_config_archive"]["materialized_manifest"]["sha256"] = judge_validator.sha256_file(
            archive_manifest_path
        )
        packet["publication_manifest"]["competition_config_archive"]["materialized_manifest"] = json.loads(
            json.dumps(packet["competition_config_archive"]["materialized_manifest"])
        )
        run_report_path = REPO_ROOT / packet["judge_entrypoints_run_report"]["path"]
        run_report_payload = json.loads(run_report_path.read_text(encoding="utf-8"))
        run_report_payload["competition_config_archive"] = json.loads(json.dumps(packet["competition_config_archive"]))
        write_json(run_report_path, run_report_payload)
        packet["judge_entrypoints_run_report"]["sha256"] = judge_validator.sha256_file(run_report_path)
        packet["publication_manifest"]["judge_entrypoints_run_report"] = json.loads(
            json.dumps(packet["judge_entrypoints_run_report"])
        )
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["judge_entrypoints_run_report"] = json.loads(json.dumps(packet["judge_entrypoints_run_report"]))
        bundle_payload["publication_manifest"]["judge_entrypoints_run_report"] = json.loads(
            json.dumps(packet["judge_entrypoints_run_report"])
        )
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
                "competition_config_archive.files.config/competition-env/environment.json.role must match bundle-manifest"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_requires_materialized_archive_manifest(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-manifest-ref-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        del packet["competition_config_archive"]["materialized_manifest"]
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_config_archive.materialized_manifest must be an object" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_materialized_archive_manifest_payload_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-manifest-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        manifest_path = REPO_ROOT / packet["competition_config_archive"]["materialized_manifest"]["path"]
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_payload["file_count"] = 0
        write_json(manifest_path, manifest_payload)
        packet["competition_config_archive"]["materialized_manifest"]["sha256"] = judge_validator.sha256_file(manifest_path)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publication_manifest"] = packet["publication_manifest"]
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_config_archive.materialized_manifest payload must match" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_materialized_archive_manifest_wrong_fixed_path(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-archive-manifest-path-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        wrong_manifest_path = temp_dir / "not-summary" / "competition-config-archive" / "manifest.json"
        manifest_payload = json.loads(json.dumps(packet["competition_config_archive"]))
        manifest_payload.pop("materialized_manifest", None)
        write_json(wrong_manifest_path, manifest_payload)
        wrong_manifest_ref = {
            "path": repo_relative(wrong_manifest_path),
            "status": "present",
            "sha256": judge_validator.sha256_file(wrong_manifest_path),
        }
        packet["competition_config_archive"]["materialized_manifest"] = wrong_manifest_ref
        packet["publication_manifest"]["competition_config_archive"]["materialized_manifest"] = wrong_manifest_ref
        run_report_path = REPO_ROOT / packet["judge_entrypoints_run_report"]["path"]
        run_report_payload = json.loads(run_report_path.read_text(encoding="utf-8"))
        run_report_payload["competition_config_archive"] = json.loads(json.dumps(packet["competition_config_archive"]))
        write_json(run_report_path, run_report_payload)
        packet["judge_entrypoints_run_report"]["sha256"] = judge_validator.sha256_file(run_report_path)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["judge_entrypoints_run_report"] = json.loads(json.dumps(packet["judge_entrypoints_run_report"]))
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "competition_config_archive.materialized_manifest.path must be "
                f"{temp_dir.relative_to(REPO_ROOT).as_posix()}/summary/competition-config-archive/manifest.json"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_publication_manifest_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-bundle-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publication_manifest"] = {
            **packet["publication_manifest"],
            "publication_scope": "focused-run",
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("publication_manifest must match judge_milestone_bundle.publication_manifest" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_publication_manifest_missing_identity_fields(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-manifest-identity-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        for field in ("report_kind", "bundle_version", "source_commit", "repo_commit", "target_source_pin"):
            del packet["publication_manifest"][field]
            del bundle_payload["publication_manifest"][field]
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("publication_manifest.report_kind must be publication-manifest" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_bound_bundle_schema_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-bundle-schema-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload.pop("retention_policy")
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
                "judge_milestone_bundle must match validation/judge-milestone-bundle.schema.json" in error
                and "retention_policy" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_public_release_packet_schema_requires_publication_manifest_identity(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-schema-identity-", dir=REPO_ROOT / "target"))
        packet = valid_packet(temp_dir)
        for field in (
            "report_kind",
            "bundle_version",
            "source_commit",
            "repo_commit",
            "target_source_pin",
            "published_artifact_refs",
            "published_artifact_count",
            "release_tag_readiness",
        ):
            del packet["publication_manifest"][field]
        schema = judge_validator.load_json(packet_validator.PACKET_SCHEMA)

        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(packet, schema)

    def test_validate_packet_rejects_status_drift_from_bound_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-status-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["status"] = "blocked"
        bundle_payload["blockers"] = ["blocked-for-test"]
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text("# invalid status fixture\n", encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("public_release_packet.status must match judge_milestone_bundle.status" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_requires_summary_blockers_from_bound_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-summary-blockers-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        blocker = "validated_artifact_sha256_mismatch:before_after_judge_demo:judge_evidence_index"
        bundle_payload["status"] = "blocked"
        bundle_payload["blockers"] = [blocker]
        write_json(bundle_path, bundle_payload)
        packet["status"] = "blocked"
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text("# invalid status fixture\n", encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("summary.blockers must match judge_milestone_bundle.blockers" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_invalid_bound_bundle_status(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-invalid-bundle-status-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["status"] = "green"
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text("# invalid status fixture\n", encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("judge_milestone_bundle.status must be passed or blocked" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_bound_bundle_missing_blockers_field(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-missing-bundle-blockers-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload.pop("blockers")
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text("# missing blockers fixture\n", encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("judge_milestone_bundle.blockers must be a string list" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_quantitative_evaluation_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-scorecard-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["quantitative_evaluation"] = {
            **packet["quantitative_evaluation"],
            "project_slice_counts": {
                **packet["quantitative_evaluation"]["project_slice_counts"],
                "workflow_units_total": 999,
            },
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("quantitative_evaluation must match judge_milestone_bundle.quantitative_evaluation" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_before_after_repair_exhibit_drift_from_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-before-after-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["before_after_repair_exhibit"] = {
            **packet["before_after_repair_exhibit"],
            "rollup": {
                **packet["before_after_repair_exhibit"]["rollup"],
                "bound_unit_count": 999,
            },
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "before_after_repair_exhibit must match judge_milestone_bundle.before_after_repair_exhibit" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_before_after_verified_baseline_accounting_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-before-after-accounting-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        mutated = json.loads(json.dumps(packet["before_after_repair_exhibit"]))
        mutated["rollup"]["bound_unit_count"] = 2
        mutated["rollup"]["verified_baseline_unit_count"] = 1
        mutated["rollup"]["missing_verified_baseline_unit_count"] = 0
        mutated["rollup"]["all_units_verified_baseline_bound"] = True
        packet["before_after_repair_exhibit"] = mutated
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["before_after_repair_exhibit"] = mutated
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("before_after_repair_exhibit verified baseline accounting mismatch" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_before_after_rollup_source_mismatch_even_when_bundle_matches(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-before-after-source-rollup-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        mutated = json.loads(json.dumps(packet["before_after_repair_exhibit"]))
        mutated["rollup"]["bound_unit_count"] = 2
        mutated["rollup"]["verified_baseline_unit_count"] = 1
        mutated["rollup"]["missing_verified_baseline_unit_count"] = 1
        mutated["rollup"]["all_units_verified_baseline_bound"] = False
        packet["before_after_repair_exhibit"] = mutated
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["before_after_repair_exhibit"] = mutated
        write_json(bundle_path, bundle_payload)
        packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
        notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
        notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
        packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("before_after_repair_exhibit rollup must match sources" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_before_after_patch_or_unsafe_rollup_source_mismatch(self) -> None:
        drift_cases = {
            "measured_unsafe_unit_count": 2,
            "accepted_patch_unit_count": 2,
        }
        for field, spoofed_value in drift_cases.items():
            with self.subTest(field=field):
                temp_dir = Path(
                    tempfile.mkdtemp(
                        prefix=f"public-release-packet-before-after-{field.replace('_', '-')}-",
                        dir=REPO_ROOT / "target",
                    )
                )
                packet_path = temp_dir / "summary" / "public-release-packet.json"
                packet = valid_packet(temp_dir)
                mutated = json.loads(json.dumps(packet["before_after_repair_exhibit"]))
                mutated["rollup"][field] = spoofed_value
                packet["before_after_repair_exhibit"] = mutated
                bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
                bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
                bundle_payload["before_after_repair_exhibit"] = mutated
                write_json(bundle_path, bundle_payload)
                packet["judge_milestone_bundle"]["sha256"] = judge_validator.sha256_file(bundle_path)
                notes_path = REPO_ROOT / packet["milestone_release_notes"]["path"]
                notes_path.write_text(milestone_release_notes.build_release_notes(bundle_payload), encoding="utf-8")
                packet["milestone_release_notes"]["sha256"] = judge_validator.sha256_file(notes_path)
                write_json(packet_path, packet)

                result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

                self.assertEqual(result["status"], "failed")
                self.assertTrue(
                    any("before_after_repair_exhibit rollup must match sources" in error for error in result["errors"]),
                    result["errors"],
                )

    def test_validate_packet_rejects_before_after_unsafe_reduction_total_source_mismatch(self) -> None:
        drift_cases = (
            ("unsafe_reduced_by", 99),
            ("unsafe_reduction.baseline_total_unsafe", 99),
            ("unsafe_reduction.current_total_unsafe", 99),
            ("unsafe_reduction.reduced_by", 99),
        )
        for field, spoofed_value in drift_cases:
            with self.subTest(field=field):
                temp_dir = Path(
                    tempfile.mkdtemp(
                        prefix=f"public-release-packet-before-after-{field.replace('.', '-').replace('_', '-')}-",
                        dir=REPO_ROOT / "target",
                    )
                )
                packet_path = temp_dir / "summary" / "public-release-packet.json"
                packet = valid_packet(temp_dir)
                mutated = json.loads(json.dumps(packet["before_after_repair_exhibit"]))
                if field == "unsafe_reduced_by":
                    mutated["rollup"][field] = spoofed_value
                else:
                    _, nested_field = field.split(".", maxsplit=1)
                    mutated["rollup"]["unsafe_reduction"][nested_field] = spoofed_value
                packet["before_after_repair_exhibit"] = mutated
                bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
                bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
                bundle_payload["before_after_repair_exhibit"] = mutated
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
                        "before_after_repair_exhibit unsafe reduction rollup must match sources" in error
                        for error in result["errors"]
                    ),
                    result["errors"],
                )

    def test_validate_packet_requires_publishability_from_bound_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-publishability-missing-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet.pop("publishability", None)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("publishability" in error for error in result["errors"]), result["errors"])

    def test_validate_packet_rejects_publishability_drift_from_bound_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-publishability-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publishability"] = {
            "status": "external_release_ready",
            "scope": "full",
            "publication_scope": "full",
            "external_milestone_claim_ready": True,
            "external_milestone": True,
            "blocker_count": 0,
            "blockers": [],
            "all_entrypoints_run_publishable": True,
            "focused_run": False,
            "competition_exact_publishable": True,
            "required_agent_tool": "opencode",
            "required_agent": "c2rust-migrator",
            "required_model": "GLM-5.1",
            "required_variant": "max",
            "opencode_glm51_required": True,
            "opencode_glm51_preflight_status": "passed",
            "opencode_glm51_publishable": True,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "target_artifacts_regenerable": True,
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("publishability must match judge_milestone_bundle.publishability" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_internal_preview_publication_scope_full(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-publishability-scope-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publishability"]["publication_scope"] = "full"
        write_json(bundle_path, bundle_payload)
        packet["publishability"] = json.loads(json.dumps(bundle_payload["publishability"]))
        packet["judge_milestone_bundle"]["sha256"] = packet_validator.judge_validator.sha256_file(bundle_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("publishability.publication_scope must match external readiness" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_publishability_required_variant_drift_even_when_bundle_matches(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-publishability-variant-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publishability"]["required_variant"] = "lite"
        write_json(bundle_path, bundle_payload)
        packet["publishability"] = json.loads(json.dumps(bundle_payload["publishability"]))
        packet["judge_milestone_bundle"]["sha256"] = packet_validator.judge_validator.sha256_file(bundle_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("publishability.required_variant" in error and "max" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_external_ready_when_host_readiness_blocked(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-host-readiness-blocked-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["publishability"].update(
            {
                "status": "external_release_ready",
                "publication_scope": "full",
                "external_milestone_claim_ready": True,
                "external_milestone": True,
                "competition_exact_publishable": True,
                "focused_run": False,
            }
        )
        write_json(bundle_path, bundle_payload)
        packet["publishability"] = json.loads(json.dumps(bundle_payload["publishability"]))
        packet["judge_milestone_bundle"]["sha256"] = packet_validator.judge_validator.sha256_file(bundle_path)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("competition_host_readiness.status must be ready" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_competition_exact_publishable_without_host_attestation(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-exact-publishable-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["publishability"]["competition_exact_publishable"] = True
        packet["competition_host_readiness"]["all_entrypoints_competition_exact"] = True
        sync_packet_bound_bundle(packet)
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "publishability.competition_exact_publishable requires competition_host_readiness.competition_exact_host_verified=true"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_competition_host_readiness_drift_from_bound_bundle(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-host-readiness-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["competition_host_readiness"] = {
            **packet["competition_host_readiness"],
            "status": "ready",
            "competition_exact_host_verified": True,
            "missing_requirements": [],
            "blocker_count": 0,
        }
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "competition_host_readiness must match judge_milestone_bundle.competition_host_readiness" in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_passed_bundle_with_bad_published_artifact_ref_status(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-bad-published-ref-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        bad_ref = {
            "artifact_name": "judge_evidence_index",
            "path": "target/competition-out/summary/judge-evidence-index.json",
            "status": "sha256_mismatch",
            "sha256": "0" * 64,
        }
        append_published_artifact_ref(packet, bad_ref)
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
            any("passed bundle cannot publish bad artifact ref status" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_passed_bundle_with_non_present_published_artifact_ref_status(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-missing-published-ref-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        missing_ref = {
            "artifact_name": "judge_evidence_index",
            "path": "target/competition-out/summary/judge-evidence-index.json",
            "status": "missing",
        }
        append_published_artifact_ref(packet, missing_ref)
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
                "passed bundle cannot publish non-present artifact ref status: judge_evidence_index:missing"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_opencode_attempt_ref_when_boundary_absent_even_if_ref_unhealthy(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-unhealthy-attempt-ref-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        blocker = "blocked-for-test"
        packet["status"] = "blocked"
        packet["summary"]["blockers"] = [blocker]
        packet["publishability"]["status"] = "blocked"
        packet["publishability"]["scope"] = "blocked"
        packet["publishability"]["publication_scope"] = "blocked"
        packet["publishability"]["blocker_count"] = 1
        packet["publishability"]["blockers"] = [blocker]
        unhealthy_attempt_ref = {
            "artifact_name": "opencode_safety_transform_attempt",
            "path": "target/competition-out/summary/opencode-safety-transform-attempt.json",
            "status": "sha256_mismatch",
            "sha256": "0" * 64,
        }
        append_published_artifact_ref(packet, unhealthy_attempt_ref)

        bundle_path = REPO_ROOT / packet["judge_milestone_bundle"]["path"]
        bundle_payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        bundle_payload["status"] = "blocked"
        bundle_payload["blockers"] = [blocker]
        bundle_payload["publishability"] = json.loads(json.dumps(packet["publishability"]))
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
                "opencode_patch_boundary.opencode_safety_transform_attempt.status must not be absent"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_validate_packet_rejects_published_artifact_ref_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-published-ref-hash-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        artifact_ref = write_text_artifact(temp_dir / "harness" / "judge-evidence-index.json", "{}\n")
        bad_ref = {
            **artifact_ref,
            "artifact_name": "judge_evidence_index",
            "sha256": "0" * 64,
        }
        append_published_artifact_ref(packet, bad_ref)
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
            any("publication_manifest.published_artifact_refs[].sha256 mismatch" in error for error in result["errors"]),
            result["errors"],
        )

    def test_validate_packet_rejects_published_artifact_ref_status_summary_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="public-release-packet-published-ref-summary-drift-", dir=REPO_ROOT / "target"))
        packet_path = temp_dir / "summary" / "public-release-packet.json"
        packet = valid_packet(temp_dir)
        packet["summary"]["published_artifact_ref_status"]["total_count"] = 999
        write_json(packet_path, packet)

        result = packet_validator.validate_packet(packet_path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "summary.published_artifact_ref_status must match judge_milestone_bundle.publication_manifest.published_artifact_refs"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )
