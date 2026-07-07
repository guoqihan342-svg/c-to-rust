class _JudgeEntrypointsValidatorTestsPart00:
    def test_default_flashdb_judge_entrypoints_passes(self) -> None:
        result = validator.validate_config(validator.DEFAULT_CONFIG, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["entrypoint_count"], 4)
        self.assertEqual(result["proof_class_contract"]["proof_class_default"], "local-simulation")
        self.assertEqual(result["source_pin_contract"]["canonical_commit"], "f9d0421315c564fb890a1b14eee77b290e0d7bbe")
        self.assertIn(
            "93d175549da579b8abac07bd175ce4c3f9dde829",
            result["source_pin_contract"]["allowed_historical_evidence_commits"],
        )
        self.assertEqual(result["test_contract"]["repair_round_cap"], 5)
        self.assertIn("planner", result["test_contract"]["required_agent_roles"])
        self.assertFalse(result["claim_boundary"]["generated_draft_semantic_pass"])
        self.assertEqual(result["claim_boundary"]["translation_coverage_numerator"], 0)
        self.assertEqual(
            [entry["id"] for entry in result["entrypoints"]],
            [
                "competition_environment_smoke",
                "before_after_judge_demo",
                "multi_worker_evaluate_profile",
                "opencode_multi_worker_evaluate_profile",
            ],
        )
        for entry in result["entrypoints"]:
            self.assertEqual(entry["status"], "passed")
            if entry["id"] == "competition_environment_smoke":
                self.assertEqual(entry["smoke_contract"]["status"], "passed")
                self.assertEqual(entry["review_checklist"]["status"], "skipped")
                continue
            self.assertEqual(entry["profile"]["status"], "present")
            self.assertEqual(entry["profile_contract"]["status"], "passed")
            self.assertEqual(entry["tracked_manifest"]["status"], "present")
        smoke = result["entrypoints"][0]
        self.assertEqual(smoke["priority"], 0)
        smoke_focus = " ".join(smoke["judge_focus"]).lower()
        self.assertIn("competition environment", smoke_focus)
        self.assertIn("smoke", smoke_focus)
        smoke_summary = smoke["expected_artifacts"]["competition_smoke_summary"]
        self.assertIn(smoke_summary["status"], {"missing", "present"})
        self.assertEqual(
            smoke_summary["path"],
            "target/competition-smoke-flashdb-judge-entrypoint/summary/competition-smoke-summary.json",
        )
        self.assertEqual(smoke["smoke_contract"]["reproduction_out_root"], "target/competition-smoke-flashdb-judge-entrypoint")
        before_after = result["entrypoints"][1]
        self.assertEqual(before_after["review_checklist"]["status"], "present")
        self.assertEqual(
            before_after["review_checklist"]["path"],
            "config/competition-env/review-checklists/flashdb-harness-internal-review.json",
        )
        self.assertFalse(before_after["review_checklist_contract"]["semantic_gate"])
        self.assertFalse(before_after["review_checklist_contract"]["review_is_semantic_acceptance"])
        opencode_entry = result["entrypoints"][3]
        self.assertEqual(
            opencode_entry["profile_contract"]["opencode_launch_policy"],
            {
                "opencode_command": "opencode",
                "opencode_model": "GLM-5.1",
                "opencode_agent": "c2rust-migrator",
                "opencode_variant": "max",
                "opencode_skip_permissions": True,
                "auto_retry": True,
            },
        )

    def test_default_flashdb_judge_entrypoints_validates_competition_env_bundle(self) -> None:
        result = validator.validate_config(validator.DEFAULT_CONFIG, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        bundle = result["competition_env_bundle_contract"]
        self.assertEqual(bundle["status"], "passed")
        self.assertEqual(bundle["report_kind"], "competition-env-bundle")
        self.assertEqual(bundle["bundle_root"], "config/competition-env")
        self.assertFalse(bundle["semantic_gate"])
        self.assertGreater(bundle["file_count"], 10)
        required_paths = {
            "config/competition-env/environment.json",
            "config/competition-env/env.sh",
            "config/competition-env/toolchain-check.sh",
            "config/competition-env/smoke.sh",
            "config/competition-env/apt/sources.list",
            "config/competition-env/pip/pip.conf",
            "config/competition-env/npm/.npmrc",
            "config/competition-env/cargo/config.toml",
            "config/competition-env/rust/rust-toolchain.toml",
            "config/competition-env/judge-entrypoints/flashdb-harness.json",
            "config/competition-env/review-checklists/flashdb-harness-internal-review.json",
            "config/competition-env/review-checklists/opencode-glm-host-acceptance.json",
            "config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json",
        }
        self.assertTrue(required_paths.issubset(set(bundle["files"])))
        self.assertEqual(
            bundle["canonical_environment_profile"],
            {
                "path": "config/competition-env/environment.json",
                "profile_id": "huawei-competition-ubuntu-24.04",
                "sha256": validator.sha256_file(REPO_ROOT / "config/competition-env/environment.json"),
            },
        )
        required_external_refs = {
            "requirements.txt",
            "opencode.json",
            "scripts/bootstrap_flashdb_sources.sh",
            "scripts/c2rust-migrator.py",
            "crates/c2r-translator/Cargo.lock",
            "validation/l2_slices/Cargo.lock",
            "flashDB_rust/Cargo.lock",
            ".github/workflows/core-translator-validation-ci.yml",
            ".opencode/agents/c2rust-migrator.md",
        }
        self.assertTrue(required_external_refs.issubset(set(bundle["external_refs"])))

    def test_competition_env_bundle_rejects_codex_or_plugin_external_refs(self) -> None:
        manifest_path = REPO_ROOT / "config" / "competition-env" / "bundle-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        forbidden_paths = [
            ".codex/skills/c2rust-migration/SKILL.md",
            "docs/superpowers/plans/legacy.md",
            ".opencode/node_modules/package/index.js",
            ".opencode/package.json",
            ".opencode/package-lock.json",
        ]
        for forbidden_path in forbidden_paths:
            with self.subTest(forbidden_path=forbidden_path):
                payload = json.loads(json.dumps(manifest))
                payload["external_refs"].append(
                    {
                        "path": forbidden_path,
                        "role": "forbidden-dev-tooling",
                        "sha256": "0" * 64,
                    }
                )
                with tempfile.TemporaryDirectory(prefix="competition-env-bundle-") as tmp:
                    candidate = Path(tmp) / "bundle-manifest.json"
                    candidate.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "competition env bundle unexpected external_ref"):
                        validator.validate_competition_env_bundle_contract(
                            load_default_config(),
                            repo_root=REPO_ROOT,
                            manifest_path=candidate,
                        )

    def test_context_pack_entrypoints_must_be_repo_relative_when_declared(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="context-pack-entrypoints-", dir=target_dir))
        context_pack = temp_dir / "out" / "harness" / "context-pack.json"
        agent_index = temp_dir / "out" / "harness" / "agent-index.json"
        primary_report = temp_dir / "out" / "harness" / "evaluate-report.json"
        ledger = temp_dir / "out" / "state" / "opencode-agent-harness.sqlite3"
        payload = {
            "report_kind": "context-pack",
            "entrypoints": {
                "primary_report": repo_relative(primary_report),
                "evaluate_report": repo_relative(primary_report),
                "run_plan_report": "C:\\temp\\stale-run-plan.json",
                "worker_plan": None,
            },
            "context_management_contract": {
                "contract_kind": "context-management",
                "schema_version": 1,
                "chat_output_is_evidence": False,
                "semantic_gate": False,
                "evidence_policy": "on-disk-artifacts-only",
                "context_pack": repo_relative(context_pack),
                "agent_index": repo_relative(agent_index),
                "primary_report": repo_relative(primary_report),
                "report_entrypoint": "evaluate_report",
                "resume_protocol": {
                    "checkpoint_backend": "sqlite",
                    "ledger_path": repo_relative(ledger),
                    "worker_state_source": "agent-index.agents_by_worker_id",
                },
                "pipeline": [
                    {"stage": "plan"},
                    {"stage": "translate", "fanout": True},
                    {"stage": "verify"},
                    {"stage": "repair", "max_rounds": 5},
                ],
            },
        }

        with self.assertRaisesRegex(ValueError, "context_pack.entrypoints.run_plan_report"):
            validator.validate_context_management_contract(
                payload,
                path_text=repo_relative(context_pack),
                expected_artifacts={
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                },
                repo_root=REPO_ROOT,
            )

    def test_context_management_pipeline_must_match_canonical_stages(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="context-pack-pipeline-", dir=target_dir))
        context_pack = temp_dir / "out" / "harness" / "context-pack.json"
        agent_index = temp_dir / "out" / "harness" / "agent-index.json"
        primary_report = temp_dir / "out" / "harness" / "evaluate-report.json"
        ledger = temp_dir / "out" / "state" / "opencode-agent-harness.sqlite3"
        payload = {
            "report_kind": "context-pack",
            "entrypoints": {
                "primary_report": repo_relative(primary_report),
                "evaluate_report": repo_relative(primary_report),
            },
            "context_management_contract": {
                "contract_kind": "context-management",
                "schema_version": 1,
                "chat_output_is_evidence": False,
                "semantic_gate": False,
                "evidence_policy": "on-disk-artifacts-only",
                "context_pack": repo_relative(context_pack),
                "agent_index": repo_relative(agent_index),
                "primary_report": repo_relative(primary_report),
                "report_entrypoint": "evaluate_report",
                "resume_protocol": {
                    "checkpoint_backend": "sqlite",
                    "ledger_path": repo_relative(ledger),
                    "worker_state_source": "agent-index.agents_by_worker_id",
                },
                "pipeline": [
                    {"stage": "plan"},
                    {"stage": "translate", "fanout": True},
                    {"stage": "audit"},
                    {"stage": "verify"},
                    {"stage": "repair", "max_rounds": 5},
                ],
            },
        }

        with self.assertRaisesRegex(
            ValueError,
            "context_management_contract.pipeline stages must be \\['plan', 'translate', 'verify', 'repair'\\]",
        ):
            validator.validate_context_management_contract(
                payload,
                path_text=repo_relative(context_pack),
                expected_artifacts={
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                },
                repo_root=REPO_ROOT,
            )

    def test_agent_coordination_roles_must_match_canonical_set(self) -> None:
        payload = {
            "report_kind": "agent-index",
            "agent_coordination_contract": {
                "contract_kind": "agent-coordination",
                "schema_version": 1,
                "chat_output_is_evidence": False,
                "semantic_gate": False,
                "checkpoint_backend": "sqlite",
                "worker_count": 1,
                "roles": {
                    "planner": {},
                    "worker": {"isolation": "per-worker out_root"},
                    "repairer": {"round_cap": 5},
                    "verifier": {},
                    "reporter": {},
                    "observer": {},
                },
            },
            "agents": [
                {
                    "worker_id": "worker-001",
                    "assignment_path": "target/out/harness/assignments/worker-001.json",
                    "request_path": "target/out/harness/assignments/worker-001-request.json",
                    "summary_path": "target/out/workers/worker-001/summary/competition-run-summary.json",
                    "report_path": "target/out/workers/worker-001/harness/run-worker-report.json",
                    "isolated_out_root": "target/out/workers/worker-001",
                }
            ],
            "agents_by_worker_id": {
                "worker-001": {
                    "worker_id": "worker-001",
                    "assignment_path": "target/out/harness/assignments/worker-001.json",
                    "request_path": "target/out/harness/assignments/worker-001-request.json",
                    "summary_path": "target/out/workers/worker-001/summary/competition-run-summary.json",
                    "report_path": "target/out/workers/worker-001/harness/run-worker-report.json",
                    "isolated_out_root": "target/out/workers/worker-001",
                }
            },
        }

        with self.assertRaisesRegex(
            ValueError,
            "agent_coordination_contract.roles must be \\['planner', 'worker', 'repairer', 'verifier', 'reporter'\\]",
        ):
            validator.validate_agent_coordination_contract(
                payload,
                path_text="target/out/harness/agent-index.json",
            )

    def test_expected_artifacts_rejects_drive_prefix_with_artifact_name(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "expected_artifacts.command_log: path must not use a drive prefix",
        ):
            validator.validate_expected_artifacts(
                {"command_log": "F:/agent/local/commands.jsonl"},
                require_local_artifacts=False,
                repo_root=REPO_ROOT,
            )

    def test_expected_artifacts_rejects_parent_traversal_with_artifact_name(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "expected_artifacts.competition_smoke_summary: path must not contain parent traversal",
        ):
            validator.validate_expected_artifacts(
                {"competition_smoke_summary": "target/../summary/competition-smoke-summary.json"},
                require_local_artifacts=False,
                repo_root=REPO_ROOT,
            )

    def test_expected_artifacts_rejects_empty_path_with_artifact_name(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "expected_artifacts.command_log: path must be a non-empty string",
        ):
            validator.validate_expected_artifacts(
                {"command_log": ""},
                require_local_artifacts=False,
                repo_root=REPO_ROOT,
            )

    def test_competition_env_bundle_rejects_hash_drift(self) -> None:
        source_manifest = REPO_ROOT / "config/competition-env/bundle-manifest.json"
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            if entry["path"] == "config/competition-env/pip/pip.conf":
                entry["sha256"] = "0" * 64
                break
        else:
            raise AssertionError("missing pip config in competition env bundle manifest")
        temp_config = write_temp_config(load_default_config())
        temp_manifest = temp_config.parent / "bundle-manifest.json"
        write_json(temp_manifest, manifest)

        with self.assertRaisesRegex(ValueError, "competition env bundle file sha256 mismatch"):
            validator.validate_competition_env_bundle_contract(
                load_default_config(),
                manifest_path=temp_manifest,
                repo_root=REPO_ROOT,
            )

    def test_competition_env_bundle_rejects_unexpected_file_ref(self) -> None:
        source_manifest = REPO_ROOT / "config/competition-env/bundle-manifest.json"
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        unexpected_file = "config/competition-env/bundle-manifest.json"
        manifest["files"].append(
            {
                "path": unexpected_file,
                "role": "unexpected-config-input",
                "sha256": validator.sha256_file(REPO_ROOT / unexpected_file),
            }
        )
        temp_config = write_temp_config(load_default_config())
        temp_manifest = temp_config.parent / "bundle-manifest.json"
        write_json(temp_manifest, manifest)

        with self.assertRaisesRegex(
            ValueError,
            "competition env bundle unexpected file: config/competition-env/bundle-manifest.json",
        ):
            validator.validate_competition_env_bundle_contract(
                load_default_config(),
                manifest_path=temp_manifest,
                repo_root=REPO_ROOT,
            )

    def test_competition_env_bundle_rejects_external_ref_hash_drift(self) -> None:
        source_manifest = REPO_ROOT / "config/competition-env/bundle-manifest.json"
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        manifest["external_refs"] = [
            {
                "path": "requirements.txt",
                "role": "python-dependency-lock",
                "sha256": "0" * 64,
            }
        ]
        temp_config = write_temp_config(load_default_config())
        temp_manifest = temp_config.parent / "bundle-manifest.json"
        write_json(temp_manifest, manifest)

        with self.assertRaisesRegex(ValueError, "competition env bundle external_ref sha256 mismatch"):
            validator.validate_competition_env_bundle_contract(
                load_default_config(),
                manifest_path=temp_manifest,
                repo_root=REPO_ROOT,
            )

    def test_competition_env_bundle_rejects_unexpected_external_ref(self) -> None:
        source_manifest = REPO_ROOT / "config/competition-env/bundle-manifest.json"
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        unexpected_ref = "docs/c2rust-migration-agent/future-vision-and-mvp.en.md"
        manifest["external_refs"].append(
            {
                "path": unexpected_ref,
                "role": "unexpected-review-input",
                "sha256": validator.sha256_file(REPO_ROOT / unexpected_ref),
            }
        )
        temp_config = write_temp_config(load_default_config())
        temp_manifest = temp_config.parent / "bundle-manifest.json"
        write_json(temp_manifest, manifest)

        with self.assertRaisesRegex(
            ValueError,
            "competition env bundle unexpected external_ref: docs/c2rust-migration-agent/future-vision-and-mvp.en.md",
        ):
            validator.validate_competition_env_bundle_contract(
                load_default_config(),
                manifest_path=temp_manifest,
                repo_root=REPO_ROOT,
            )

    def test_competition_env_bundle_rejects_opencode_config_plugins(self) -> None:
        source_manifest = REPO_ROOT / "config/competition-env/bundle-manifest.json"
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        temp_config = write_temp_config(load_default_config())
        temp_manifest = temp_config.parent / "bundle-manifest.json"
        write_json(temp_manifest, manifest)
        original_load_json = validator.load_json

        def load_json_with_plugin(path: Path) -> dict:
            if Path(path).as_posix().endswith("opencode.json"):
                return {"$schema": "https://opencode.ai/config.json", "plugin": ["superpowers"]}
            return original_load_json(path)

        with mock.patch.object(validator, "load_json", side_effect=load_json_with_plugin):
            with self.assertRaisesRegex(ValueError, "opencode.json plugin must be empty"):
                validator.validate_competition_env_bundle_contract(
                    load_default_config(),
                    manifest_path=temp_manifest,
                    repo_root=REPO_ROOT,
                )

    def test_competition_env_bundle_rejects_opencode_agent_required_preflight_tool_drift(self) -> None:
        source_manifest = REPO_ROOT / "config/competition-env/bundle-manifest.json"
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        temp_config = write_temp_config(load_default_config())
        temp_manifest = temp_config.parent / "bundle-manifest.json"
        write_json(temp_manifest, manifest)
        original_read_text = Path.read_text

        def read_text_with_required_openspec(path: Path, *args: object, **kwargs: object) -> str:
            text = original_read_text(path, *args, **kwargs)
            if Path(path).as_posix().endswith(".opencode/agents/c2rust-migrator.md"):
                return text.replace(
                    "  --opencode-variant max\n```",
                    "  --opencode-variant max\nopenspec validate --all --strict\n```",
                )
            return text

        with mock.patch.object(Path, "read_text", read_text_with_required_openspec):
            with self.assertRaisesRegex(
                ValueError,
                "OpenCode agent runbook Required Preflight must not depend on OpenSpec or superpowers",
            ):
                validator.validate_competition_env_bundle_contract(
                    load_default_config(),
                    manifest_path=temp_manifest,
                    repo_root=REPO_ROOT,
                )

    def test_competition_env_bundle_rejects_glm_host_acceptance_model_drift(self) -> None:
        source_manifest = REPO_ROOT / "config/competition-env/bundle-manifest.json"
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        temp_config = write_temp_config(load_default_config())
        temp_manifest = temp_config.parent / "bundle-manifest.json"
        write_json(temp_manifest, manifest)
        original_load_json = validator.load_json

        def load_json_with_model_drift(path: Path) -> dict:
            payload = original_load_json(path)
            if Path(path).as_posix().endswith(
                "config/competition-env/review-checklists/opencode-glm-host-acceptance.json"
            ):
                payload["required_model"] = "GLM-5.10"
            return payload

        with mock.patch.object(validator, "load_json", side_effect=load_json_with_model_drift):
            with self.assertRaisesRegex(ValueError, "opencode-glm-host-acceptance required_model must be GLM-5.1"):
                validator.validate_competition_env_bundle_contract(
                    load_default_config(),
                    manifest_path=temp_manifest,
                    repo_root=REPO_ROOT,
                )

    def test_competition_env_bundle_rejects_glm_host_acceptance_agent_drift(self) -> None:
        source_manifest = REPO_ROOT / "config/competition-env/bundle-manifest.json"
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        temp_config = write_temp_config(load_default_config())
        temp_manifest = temp_config.parent / "bundle-manifest.json"
        write_json(temp_manifest, manifest)
        original_load_json = validator.load_json

        def load_json_with_agent_drift(path: Path) -> dict:
            payload = original_load_json(path)
            if Path(path).as_posix().endswith(
                "config/competition-env/review-checklists/opencode-glm-host-acceptance.json"
            ):
                payload["required_agent"] = "default"
            return payload

        with mock.patch.object(validator, "load_json", side_effect=load_json_with_agent_drift):
            with self.assertRaisesRegex(
                ValueError,
                "opencode-glm-host-acceptance required_agent must be c2rust-migrator",
            ):
                validator.validate_competition_env_bundle_contract(
                    load_default_config(),
                    manifest_path=temp_manifest,
                    repo_root=REPO_ROOT,
                )

    def test_competition_env_bundle_rejects_bootstrap_source_pin_drift(self) -> None:
        source_manifest = REPO_ROOT / "config/competition-env/bundle-manifest.json"
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        temp_config = write_temp_config(load_default_config())
        temp_manifest = temp_config.parent / "bundle-manifest.json"
        write_json(temp_manifest, manifest)
        original_read_text = Path.read_text

        def read_text_with_bootstrap_drift(path: Path, *args: object, **kwargs: object) -> str:
            text = original_read_text(path, *args, **kwargs)
            if Path(path).as_posix().endswith("scripts/bootstrap_flashdb_sources.sh"):
                return text.replace(
                    'FLASHDB_COMMIT="f9d0421315c564fb890a1b14eee77b290e0d7bbe"',
                    'FLASHDB_COMMIT="0000000000000000000000000000000000000000"',
                )
            return text

        with mock.patch.object(Path, "read_text", read_text_with_bootstrap_drift):
            with self.assertRaisesRegex(ValueError, "bootstrap_flashdb_sources.sh FLASHDB_COMMIT must match"):
                validator.validate_competition_env_bundle_contract(
                    load_default_config(),
                    manifest_path=temp_manifest,
                    repo_root=REPO_ROOT,
                )

    def test_environment_profile_hash_mismatch_preserves_claim_boundary_for_test_contract(self) -> None:
        config = load_default_config()
        config["environment_profile"]["sha256"] = "0" * 64
        temp_config = write_temp_config(config)

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        joined_errors = "\n".join(result["errors"])
        self.assertIn("artifact ref sha256 mismatch for config/competition-env/environment.json", joined_errors)
        self.assertNotIn("test_contract.semantic_claim_source must match claim_boundary", joined_errors)

    def test_test_contract_requires_portable_python3_b_command_contract(self) -> None:
        config = load_default_config()
        config["test_contract"].pop("commands_must_use_portable_python3_b", None)
        config["test_contract"]["commands_must_use_python_b"] = True
        temp_config = write_temp_config(config)

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("test_contract.commands_must_use_portable_python3_b must be true" in error for error in result["errors"]),
            result["errors"],
        )

    def test_test_contract_required_harness_features_must_match_canonical_set(self) -> None:
        config = load_default_config()
        config["test_contract"]["required_harness_features"] = [
            feature
            for feature in config["test_contract"]["required_harness_features"]
            if feature != "h6_judge_reports"
        ]
        temp_config = write_temp_config(config)

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "test_contract.required_harness_features must be "
                "['h1_evaluate_one_click', 'h2_multi_worker_fanout', "
                "'h3_precise_repair_self_heal', 'h4_before_after_exhibit', "
                "'h5_context_management', 'h6_judge_reports']"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_opencode_profile_requires_explicit_launch_policy_fields(self) -> None:
        config = load_default_config()
        entry = entrypoint_by_id(config, "opencode_multi_worker_evaluate_profile")
        source_profile = json.loads((REPO_ROOT / entry["profile"]["path"]).read_text(encoding="utf-8"))
        source_profile.pop("opencode_skip_permissions", None)
        temp_config = write_temp_config(config)
        profile_path = temp_config.parent / "opencode-profile-missing-policy.json"
        write_json(profile_path, source_profile)
        profile_rel = repo_relative(profile_path)
        entry["profile"]["path"] = profile_rel
        entry["profile"]["sha256"] = validator.sha256_file(profile_path)
        entry["command"] = entry["command"].replace(
            "config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json",
            profile_rel,
        )
        manifest = json.loads((REPO_ROOT / entry["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest_profile = validator.manifest_profile_payload(manifest)
        manifest_profile["path"] = profile_rel
        manifest_profile["sha256"] = entry["profile"]["sha256"]
        command_key = validator.expected_manifest_reproduction_command_key(entry)
        manifest["reproduction"][command_key] = entry["command"]
        manifest_path = temp_config.parent / "opencode-missing-policy-tracked-manifest.json"
        entry["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
        temp_config.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        opencode_entry = entrypoint_by_id(result, "opencode_multi_worker_evaluate_profile")
        self.assertEqual(opencode_entry["status"], "failed")
        self.assertIn(
            "opencode_multi_worker_evaluate_profile opencode profile opencode_skip_permissions must be a boolean",
            result["errors"],
        )

    def test_opencode_profile_binds_repo_owned_agent_runbook(self) -> None:
        result = validator.validate_config(validator.DEFAULT_CONFIG, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        opencode_entry = entrypoint_by_id(result, "opencode_multi_worker_evaluate_profile")
        self.assertEqual(
            opencode_entry["profile_contract"]["opencode_launch_policy"]["opencode_agent"],
            "c2rust-migrator",
        )
        self.assertIs(opencode_entry["profile_contract"]["opencode_launch_policy"]["auto_retry"], True)

    def test_opencode_profile_requires_auto_retry_enabled(self) -> None:
        policy = opencode_launch_policy()
        policy["auto_retry"] = False

        with self.assertRaisesRegex(ValueError, "opencode profile auto_retry must be true"):
            validator.validate_opencode_profile_launch_policy(policy, entry_id="opencode_multi_worker_evaluate_profile")

    def test_opencode_profile_rejects_wrong_agent_runbook(self) -> None:
        config = load_default_config()
        entry = entrypoint_by_id(config, "opencode_multi_worker_evaluate_profile")
        source_profile = json.loads((REPO_ROOT / entry["profile"]["path"]).read_text(encoding="utf-8"))
        source_profile["opencode_agent"] = "default"
        temp_config = write_temp_config(config)
        profile_path = temp_config.parent / "opencode-profile-wrong-agent.json"
        write_json(profile_path, source_profile)
        profile_rel = repo_relative(profile_path)
        entry["profile"]["path"] = profile_rel
        entry["profile"]["sha256"] = validator.sha256_file(profile_path)
        entry["command"] = entry["command"].replace(
            "config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json",
            profile_rel,
        )
        manifest = json.loads((REPO_ROOT / entry["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest_profile = validator.manifest_profile_payload(manifest)
        manifest_profile["path"] = profile_rel
        manifest_profile["sha256"] = entry["profile"]["sha256"]
        command_key = validator.expected_manifest_reproduction_command_key(entry)
        manifest["reproduction"][command_key] = entry["command"]
        manifest_path = temp_config.parent / "opencode-wrong-agent-tracked-manifest.json"
        entry["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
        temp_config.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertIn(
            "opencode_multi_worker_evaluate_profile opencode profile opencode_agent must be c2rust-migrator",
            result["errors"],
        )

    def test_multi_worker_entrypoint_requires_multi_worker_profile(self) -> None:
        config = load_default_config()
        entry = entrypoint_by_id(config, "multi_worker_evaluate_profile")
        source_profile = json.loads((REPO_ROOT / entry["profile"]["path"]).read_text(encoding="utf-8"))
        source_profile["workers"] = source_profile["workers"][:1]
        source_profile["max_workers"] = 1
        temp_config = write_temp_config(config)
        profile_path = temp_config.parent / "explicit-workers-single-worker.json"
        write_json(profile_path, source_profile)
        profile_rel = repo_relative(profile_path)
        entry["profile"]["path"] = profile_rel
        entry["profile"]["sha256"] = validator.sha256_file(profile_path)
        entry["command"] = entry["command"].replace(
            "config/competition-env/planned-batches/flashdb-fdb-utils-explicit-workers.json",
            profile_rel,
        )
        manifest = json.loads((REPO_ROOT / entry["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest_profile = validator.manifest_profile_payload(manifest)
        manifest_profile["path"] = profile_rel
        manifest_profile["sha256"] = entry["profile"]["sha256"]
        command_key = validator.expected_manifest_reproduction_command_key(entry)
        manifest["reproduction"][command_key] = entry["command"]
        manifest_path = temp_config.parent / "single-worker-tracked-manifest.json"
        entry["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
        temp_config.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertIn(
            "multi_worker_evaluate_profile multi-worker profile workers must contain at least 2 workers",
            result["errors"],
        )

    def test_opencode_profile_requires_explicit_model(self) -> None:
        config = load_default_config()
        entry = entrypoint_by_id(config, "opencode_multi_worker_evaluate_profile")
        source_profile = json.loads((REPO_ROOT / entry["profile"]["path"]).read_text(encoding="utf-8"))
        source_profile["opencode_model"] = None
        temp_config = write_temp_config(config)
        profile_path = temp_config.parent / "opencode-profile-null-model.json"
        write_json(profile_path, source_profile)
        profile_rel = repo_relative(profile_path)
        entry["profile"]["path"] = profile_rel
        entry["profile"]["sha256"] = validator.sha256_file(profile_path)
        entry["command"] = entry["command"].replace(
            "config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json",
            profile_rel,
        )
        temp_config.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertIn(
            "opencode_multi_worker_evaluate_profile opencode profile opencode_model must be a non-empty string",
            result["errors"],
        )

    def test_opencode_entrypoint_requires_opencode_profile_mode(self) -> None:
        config = load_default_config()
        entry = entrypoint_by_id(config, "opencode_multi_worker_evaluate_profile")
        source_profile = json.loads((REPO_ROOT / entry["profile"]["path"]).read_text(encoding="utf-8"))
        source_profile["mode"] = "deterministic"
        temp_config = write_temp_config(config)
        profile_path = temp_config.parent / "opencode-profile-deterministic-mode.json"
        write_json(profile_path, source_profile)
        profile_rel = repo_relative(profile_path)
        entry["profile"]["path"] = profile_rel
        entry["profile"]["sha256"] = validator.sha256_file(profile_path)
        entry["command"] = entry["command"].replace(
            "config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json",
            profile_rel,
        )
        manifest = json.loads((REPO_ROOT / entry["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest_profile = validator.manifest_profile_payload(manifest)
        manifest_profile["path"] = profile_rel
        manifest_profile["sha256"] = entry["profile"]["sha256"]
        command_key = validator.expected_manifest_reproduction_command_key(entry)
        manifest["reproduction"][command_key] = entry["command"]
        manifest_path = temp_config.parent / "opencode-deterministic-mode-tracked-manifest.json"
        entry["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
        temp_config.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertIn(
            "opencode_multi_worker_evaluate_profile opencode profile mode must be opencode",
            result["errors"],
        )

    def test_opencode_profile_requires_glm_51_model(self) -> None:
        policy = opencode_launch_policy()
        policy["opencode_model"] = "gpt-5.4"

        with self.assertRaisesRegex(ValueError, "opencode profile opencode_model must be GLM-5.1"):
            validator.validate_opencode_profile_launch_policy(policy, entry_id="opencode_multi_worker_evaluate_profile")

    def test_opencode_profile_requires_opencode_command(self) -> None:
        policy = opencode_launch_policy()
        policy["opencode_command"] = "codex"

        with self.assertRaisesRegex(ValueError, "opencode profile opencode_command must be opencode"):
            validator.validate_opencode_profile_launch_policy(policy, entry_id="opencode_multi_worker_evaluate_profile")

    def test_opencode_profile_requires_max_variant(self) -> None:
        policy = opencode_launch_policy()
        policy["opencode_variant"] = "default"

        with self.assertRaisesRegex(ValueError, "opencode profile opencode_variant must be max"):
            validator.validate_opencode_profile_launch_policy(policy, entry_id="opencode_multi_worker_evaluate_profile")

    def test_opencode_launch_policy_binding_requires_glm_51(self) -> None:
        policy = opencode_launch_policy()
        policy["opencode_model"] = "gpt-5.4"
        policy_sha = opencode_launch_policy_sha256(policy)

        with self.assertRaisesRegex(ValueError, "launch_policy.opencode_model must be GLM-5.1"):
            validator.validate_opencode_launch_policy_binding(
                policy,
                policy_sha,
                "opencode_agent_runtime.opencode_preflight_report",
            )

    def test_opencode_launch_policy_binding_requires_max_variant(self) -> None:
        policy = opencode_launch_policy()
        policy["opencode_variant"] = "default"
        policy_sha = opencode_launch_policy_sha256(policy)

        with self.assertRaisesRegex(ValueError, "launch_policy.opencode_variant must be max"):
            validator.validate_opencode_launch_policy_binding(
                policy,
                policy_sha,
                "opencode_agent_runtime.opencode_preflight_report",
            )

    def test_opencode_launch_policy_binding_requires_repo_owned_agent(self) -> None:
        policy = opencode_launch_policy()
        policy["opencode_agent"] = None
        policy_sha = opencode_launch_policy_sha256(policy)

        with self.assertRaisesRegex(ValueError, "launch_policy.opencode_agent must be c2rust-migrator"):
            validator.validate_opencode_launch_policy_binding(
                policy,
                policy_sha,
                "opencode_agent_runtime.opencode_preflight_report",
            )

    def test_opencode_launch_policy_binding_rejects_wrong_agent(self) -> None:
        policy = opencode_launch_policy()
        policy["opencode_agent"] = "default"
        policy_sha = opencode_launch_policy_sha256(policy)

        with self.assertRaisesRegex(ValueError, "launch_policy.opencode_agent must be c2rust-migrator"):
            validator.validate_opencode_launch_policy_binding(
                policy,
                policy_sha,
                "opencode_agent_runtime.opencode_preflight_report",
            )

    def test_cli_writes_judge_entrypoints_readiness_report(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-readiness-", dir=target_dir))
        report_path = temp_dir / "summary" / "judge-entrypoints-readiness.json"

        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "validation.tools.validate_judge_entrypoints",
                "--config",
                validator.DEFAULT_CONFIG.relative_to(REPO_ROOT).as_posix(),
                "--out",
                repo_relative(report_path),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(report_path.is_file())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["report_kind"], "judge-entrypoints-readiness")
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["semantic_gate"])
        self.assertEqual(report["claim_boundary"]["semantic_claim_source"], "accepted_evidence_binding")
        self.assertEqual(report["entrypoint_count"], 4)
        self.assertIn("4 judge entrypoints ready", report["summary"]["headline"])
        self.assertEqual(report["summary"]["readiness"]["configured_count"], 4)
        self.assertEqual(report["summary"]["readiness"]["validation_status"], "passed")
        self.assertFalse(report["summary"]["claim_boundary"]["semantic_gate"])
        self.assertEqual(
            [entry["id"] for entry in report["summary"]["entrypoints"]],
            [
                "competition_environment_smoke",
                "before_after_judge_demo",
                "multi_worker_evaluate_profile",
                "opencode_multi_worker_evaluate_profile",
            ],
        )
        smoke_focus = " ".join(report["summary"]["entrypoints"][0]["judge_focus"]).lower()
        self.assertIn("competition environment", smoke_focus)
        self.assertIn("smoke", smoke_focus)

    def test_readiness_summary_classifies_stale_opencode_worker_report_artifact(self) -> None:
        summary = validator.build_readiness_summary(
            {
                "status": "failed",
                "entrypoint_count": 4,
                "entrypoints": [
                    {
                        "id": "opencode_multi_worker_evaluate_profile",
                        "purpose": "harness-architecture-opencode-multi-worker-evaluate",
                        "status": "failed",
                        "proof_class": "local-simulation",
                        "run_id": "harness-flashdb-opencode-explicit-workers-evaluate-profile-20260701",
                    }
                ],
                "claim_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                },
                "errors": [
                    "context ledger missing artifacts row for worker report: "
                    "flashdb-opencode-worker-001-fdb-calc-crc32"
                ],
            }
        )

        self.assertEqual(summary["readiness"]["blocker_count"], 1)
        self.assertEqual(
            summary["readiness"]["blocker_root_cause_counts"],
            {"opencode_artifacts_require_regeneration": 1},
        )
        self.assertEqual(
            summary["blockers"][0]["recommended_action"],
            "regenerate OpenCode artifacts on a real GLM-5.1/OpenCode host; do not hand-edit target artifacts",
        )
        self.assertEqual(summary["blockers"][0]["proof_class_effect"], "h9_release_blocker")
