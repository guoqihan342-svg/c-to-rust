class _JudgeEntrypointsValidatorTestsPart08:
    def test_entrypoint_command_rejects_bare_python_launcher(self) -> None:
        config = load_default_config()
        entry = entrypoint_by_id(config, "before_after_judge_demo")
        command = entry["command"]
        if command.startswith("python3 -B "):
            command = command.replace("python3 -B ", "python -B ", 1)
        entry["command"] = command
        path = write_temp_config(config)

        result = validator.validate_config(path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("entrypoint command must use portable python3 -B" in error for error in result["errors"]),
            result["errors"],
        )

    def test_competition_smoke_entrypoint_rejects_python_c_spoof(self) -> None:
        config = load_default_config()
        entry = entrypoint_by_id(config, "competition_environment_smoke")
        entry["command"] = (
            "python3 -B -c \"import sys; sys.exit(0)\" "
            "validation/tools/run_competition_smoke.py "
            f"--proof-class {entry['proof_class']} "
            f"--run-id {entry['run_id']} "
            "--out-root target/competition-smoke-flashdb-judge-entrypoint"
        )
        path = write_temp_config(config)

        result = validator.validate_config(path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any(
                "competition_environment_smoke command must execute validation/tools/run_competition_smoke.py as argv[2]"
                in error
                for error in result["errors"]
            ),
            result["errors"],
        )

    def test_verification_command_rejects_bare_python_launcher(self) -> None:
        config = load_default_config()
        entry = entrypoint_by_id(config, "before_after_judge_demo")
        entry["verification_commands"][0] = entry["verification_commands"][0].replace("python3 -B ", "python -B ", 1)
        path = write_temp_config(config)

        result = validator.validate_config(path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("verification command must use portable python3 -B" in error for error in result["errors"]),
            result["errors"],
        )

    def test_audit_command_rejects_python3_without_b_flag(self) -> None:
        config = load_default_config()
        entry = entrypoint_by_id(config, "before_after_judge_demo")
        entry["audit_command"] = entry["audit_command"].replace("python3 -B ", "python3 ", 1)
        path = write_temp_config(config)

        result = validator.validate_config(path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("audit command must use portable python3 -B" in error for error in result["errors"]),
            result["errors"],
        )

    def test_historical_profile_commit_must_be_declared_in_source_pin_policy(self) -> None:
        config = load_default_config()
        config["source_pin_policy"]["allowed_historical_evidence_commits"] = []
        path = write_temp_config(config)

        result = validator.validate_config(path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("profile uses commits outside source_pin_policy" in error for error in result["errors"]),
            result["errors"],
        )

    def test_environment_profile_requires_opencode_glm_runtime_contract(self) -> None:
        config = load_default_config()
        temp_config = write_temp_config(config)
        temp_dir = temp_config.parent
        environment = json.loads((REPO_ROOT / config["environment_profile"]["path"]).read_text(encoding="utf-8"))
        environment.pop("opencode_runtime", None)
        environment_path = temp_dir / "environment-without-opencode-runtime.json"
        write_json(environment_path, environment)
        config["environment_profile"] = {
            "path": repo_relative(environment_path),
            "profile_id": environment["profile_id"],
            "sha256": validator.sha256_file(environment_path),
        }
        write_json(temp_config, config)

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("environment_profile.opencode_runtime must be an object" in error for error in result["errors"]),
            result["errors"],
        )

    def test_environment_profile_preflight_template_requires_max_variant(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="environment-opencode-variant-", dir=REPO_ROOT / "target"))
        config = load_default_config()
        environment = json.loads((REPO_ROOT / config["environment_profile"]["path"]).read_text(encoding="utf-8"))
        environment["opencode_runtime"]["preflight_command_template"] = environment["opencode_runtime"][
            "preflight_command_template"
        ].replace("--opencode-variant max", "--opencode-variant default")
        environment_path = temp_dir / "environment-with-default-opencode-variant.json"
        write_json(environment_path, environment)
        profile_ref = {
            "path": repo_relative(environment_path),
            "profile_id": environment["profile_id"],
            "sha256": validator.sha256_file(environment_path),
        }

        with self.assertRaisesRegex(ValueError, "--opencode-variant max"):
            validator.validate_competition_environment_profile_contract(profile_ref, repo_root=REPO_ROOT)

    def test_environment_profile_preflight_template_requires_repo_owned_agent(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="environment-opencode-agent-", dir=REPO_ROOT / "target"))
        config = load_default_config()
        environment = json.loads((REPO_ROOT / config["environment_profile"]["path"]).read_text(encoding="utf-8"))
        environment["opencode_runtime"]["preflight_command_template"] = environment["opencode_runtime"][
            "preflight_command_template"
        ].replace(" --opencode-agent c2rust-migrator", "")
        environment_path = temp_dir / "environment-without-opencode-agent.json"
        write_json(environment_path, environment)
        profile_ref = {
            "path": repo_relative(environment_path),
            "profile_id": environment["profile_id"],
            "sha256": validator.sha256_file(environment_path),
        }

        with self.assertRaisesRegex(ValueError, "--opencode-agent c2rust-migrator"):
            validator.validate_competition_environment_profile_contract(profile_ref, repo_root=REPO_ROOT)

    def test_environment_profile_preflight_template_rejects_wrong_agent(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="environment-opencode-wrong-agent-", dir=REPO_ROOT / "target"))
        config = load_default_config()
        environment = json.loads((REPO_ROOT / config["environment_profile"]["path"]).read_text(encoding="utf-8"))
        environment["opencode_runtime"]["preflight_command_template"] = environment["opencode_runtime"][
            "preflight_command_template"
        ].replace("--opencode-agent c2rust-migrator", "--opencode-agent default")
        environment_path = temp_dir / "environment-with-wrong-opencode-agent.json"
        write_json(environment_path, environment)
        profile_ref = {
            "path": repo_relative(environment_path),
            "profile_id": environment["profile_id"],
            "sha256": validator.sha256_file(environment_path),
        }

        with self.assertRaisesRegex(ValueError, "--opencode-agent c2rust-migrator"):
            validator.validate_competition_environment_profile_contract(profile_ref, repo_root=REPO_ROOT)

    def test_environment_profile_requires_structured_max_variant(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="environment-opencode-required-variant-", dir=REPO_ROOT / "target"))
        config = load_default_config()
        environment = json.loads((REPO_ROOT / config["environment_profile"]["path"]).read_text(encoding="utf-8"))
        environment["opencode_runtime"]["required_variant"] = "lite"
        environment_path = temp_dir / "environment-with-lite-required-variant.json"
        write_json(environment_path, environment)
        profile_ref = {
            "path": repo_relative(environment_path),
            "profile_id": environment["profile_id"],
            "sha256": validator.sha256_file(environment_path),
        }

        with self.assertRaisesRegex(ValueError, "required_variant must be max"):
            validator.validate_competition_environment_profile_contract(profile_ref, repo_root=REPO_ROOT)

    def test_environment_profile_preflight_template_rejects_duplicate_opencode_variant_override(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="environment-opencode-variant-duplicate-", dir=REPO_ROOT / "target"))
        config = load_default_config()
        environment = json.loads((REPO_ROOT / config["environment_profile"]["path"]).read_text(encoding="utf-8"))
        environment["opencode_runtime"]["preflight_command_template"] += " --opencode-variant default"
        environment_path = temp_dir / "environment-with-duplicate-opencode-variant.json"
        write_json(environment_path, environment)
        profile_ref = {
            "path": repo_relative(environment_path),
            "profile_id": environment["profile_id"],
            "sha256": validator.sha256_file(environment_path),
        }

        with self.assertRaisesRegex(ValueError, "duplicate --opencode-variant"):
            validator.validate_competition_environment_profile_contract(profile_ref, repo_root=REPO_ROOT)

    def test_environment_profile_preflight_template_rejects_opencode_command_override(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="environment-opencode-command-override-", dir=REPO_ROOT / "target"))
        config = load_default_config()
        environment = json.loads((REPO_ROOT / config["environment_profile"]["path"]).read_text(encoding="utf-8"))
        environment["opencode_runtime"]["preflight_command_template"] += " --opencode-command codex"
        environment_path = temp_dir / "environment-with-opencode-command-override.json"
        write_json(environment_path, environment)
        profile_ref = {
            "path": repo_relative(environment_path),
            "profile_id": environment["profile_id"],
            "sha256": validator.sha256_file(environment_path),
        }

        with self.assertRaisesRegex(ValueError, "unexpected --opencode-command"):
            validator.validate_competition_environment_profile_contract(profile_ref, repo_root=REPO_ROOT)

    def test_tracked_manifest_reproduction_command_must_match_entrypoint_command(self) -> None:
        config = load_default_config()
        temp_config = write_temp_config(config)
        entry = entrypoint_by_id(config, "multi_worker_evaluate_profile")
        manifest = json.loads((REPO_ROOT / entry["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest["reproduction"]["evaluate_profile_command"] = manifest["reproduction"]["evaluate_profile_command"].replace(
            "--run-id harness-flashdb-explicit-workers-evaluate-profile-20260701",
            "--run-id wrong-evaluate-run",
        )
        manifest_path = temp_config.parent / "drifted-explicit-workers-manifest.json"
        entry["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
        write_json(temp_config, config)

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("tracked manifest reproduction command must match entrypoint command" in error for error in result["errors"]),
            result["errors"],
        )

    def test_tracked_manifest_claim_boundary_must_match_judge_config(self) -> None:
        config = load_default_config()
        temp_config = write_temp_config(config)
        entry = entrypoint_by_id(config, "multi_worker_evaluate_profile")
        manifest = json.loads((REPO_ROOT / entry["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest["claim_boundary"]["semantic_claim_source"] = "generated_draft"
        manifest_path = temp_config.parent / "drifted-claim-boundary-manifest.json"
        entry["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
        write_json(temp_config, config)

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("tracked manifest claim_boundary.semantic_claim_source must match judge config" in error for error in result["errors"]),
            result["errors"],
        )

    def test_tracked_manifest_source_commits_must_follow_source_pin_policy(self) -> None:
        config = load_default_config()
        temp_config = write_temp_config(config)
        entry = entrypoint_by_id(config, "multi_worker_evaluate_profile")
        manifest = json.loads((REPO_ROOT / entry["tracked_manifest"]["path"]).read_text(encoding="utf-8"))
        manifest["workers"][0]["source_commit"] = "bad-commit"
        manifest_path = temp_config.parent / "drifted-source-commit-manifest.json"
        entry["tracked_manifest"] = temp_json_ref(manifest_path, manifest)
        write_json(temp_config, config)

        result = validator.validate_config(temp_config, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("tracked manifest uses commits outside source_pin_policy" in error for error in result["errors"]),
            result["errors"],
        )

    def test_tracked_manifest_reproduction_out_root_bounds_expected_artifacts(self) -> None:
        config = load_default_config()
        entrypoint_by_id(config, "before_after_judge_demo")["expected_artifacts"]["merge_plan"] = "target/outside-harness/merge-plan.json"
        path = write_temp_config(config)

        result = validator.validate_config(path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("expected_artifacts.merge_plan must be under reproduction --out-root" in error for error in result["errors"]),
            result["errors"],
        )

    def test_merge_plan_argv_rejects_local_absolute_paths(self) -> None:
        with self.assertRaisesRegex(ValueError, "local absolute path"):
            validator.validate_local_absolute_path_policy(
                {"merge_plan": {"argv": ["C:\\Python314\\python.exe", "validation/tools/run_competition.py"]}},
                label="merge-plan",
            )

    def test_merge_plan_argv_rejects_linux_local_absolute_paths(self) -> None:
        with self.assertRaisesRegex(ValueError, "local absolute path"):
            validator.validate_local_absolute_path_policy(
                {"merge_plan": {"argv": ["/tmp/python/bin/python", "validation/tools/run_competition.py"]}},
                label="merge-plan",
            )

    def test_competition_smoke_command_log_rejects_wsl_unc_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": [
                            "\\\\wsl$\\Ubuntu\\home\\runner\\toolchain-check.sh",
                            "//wsl.localhost/Ubuntu/home/runner/python",
                        ],
                        "returncode": 0,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_wsl_unc_alias_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": [
                            "//wsl$/Ubuntu/home/runner/toolchain-check.sh",
                            "\\\\wsl.localhost\\Ubuntu\\home\\runner\\python",
                        ],
                        "returncode": 0,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_wsl_drive_mount_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": [
                            "/mnt/c/Users/runner/toolchain-check.sh",
                            "bash -lc 'python /mnt/c/Users/runner/tool.py'",
                        ],
                        "returncode": 0,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_wsl_paths_in_output_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": ["bash", "-lc", "echo ok"],
                        "returncode": 0,
                        "stdout": "include path: /mnt/c/Users/runner/FlashDB/inc",
                        "stderr": r"output path: \\wsl$\Ubuntu\home\runner\project\target\out.json",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "output contains forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_include_flag_host_paths_in_output_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": ["bash", "-lc", "echo ok"],
                        "returncode": 0,
                        "workdir": ".",
                        "stdout": (
                            "cc args: -I/mnt/c/Users/runner/FlashDB/include "
                            "-isystem//wsl.localhost/Ubuntu/home/runner/sysroot"
                        ),
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "output contains forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_root_only_flag_host_paths_in_output_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": ["bash", "-lc", "echo ok"],
                        "returncode": 0,
                        "workdir": ".",
                        "stdout": "cc args: -I/mnt/c -L/workspace --sysroot=/opt",
                        "stderr": r"link args: -L\\server\share -L//server/share",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "output contains forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_nested_tool_output_host_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": ["bash", "-lc", "echo ok"],
                        "returncode": 0,
                        "workdir": ".",
                        "tool_output": {
                            "stdout": "source path: /root/work/project/src/fdb.c",
                            "stderr": "compiler path: /usr/bin/clang",
                            "source": "/workspace/project/src/fdb.c",
                            "include_dirs": ["//wsl$/Ubuntu/home/runner/project/include"],
                            "artifacts": {"output": r"\\server\share\project\target\out.json"},
                        },
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_parent_traversal_workdir(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": ["bash", "-lc", "echo ok"],
                        "returncode": 0,
                        "workdir": "../outside-repo",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "workdir must be repo-relative POSIX"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_requires_workdir(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": ["bash", "-lc", "echo ok"],
                        "returncode": 0,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "workdir must be present"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_non_root_workdir(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": ["bash", "-lc", "echo ok"],
                        "returncode": 0,
                        "workdir": "validation/tools",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "workdir must be repo root"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_cwd_workdir_disagreement(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": ["bash", "-lc", "echo ok"],
                        "returncode": 0,
                        "cwd": "target/competition-smoke",
                        "workdir": ".",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "cwd must match workdir"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_non_string_workdir(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": ["bash", "-lc", "echo ok"],
                        "returncode": 0,
                        "cwd": {"path": "."},
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "cwd must be a string"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_tilde_repo_input_argument(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "core-auto-evidence-validator",
                        "command": [
                            "python3",
                            "-B",
                            "validation/tools/validate_auto_translation_evidence.py",
                            "--slice-spec",
                            "~/slice.json",
                        ],
                        "returncode": 0,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "command repo input --slice-spec must be repo-relative POSIX"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_requires_step(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "command": ["python3", "-B", "-c", "print('bypassed step contract')"],
                        "returncode": 0,
                        "workdir": ".",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "step must be a non-empty string"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_python_step_without_python3_b(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "evidence-governance",
                        "command": ["python", "-B", "validation/tools/evidence_governance.py"],
                        "returncode": 0,
                        "workdir": ".",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "step evidence-governance command must use portable python3 -B"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_python_step_c_flag_spoof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "evidence-governance",
                        "command": [
                            "python3",
                            "-B",
                            "-c",
                            "print('validation/tools/evidence_governance.py')",
                        ],
                        "returncode": 0,
                        "workdir": ".",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "step evidence-governance command must execute validation/tools/evidence_governance.py as argv\\[2\\]"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_lightweight_unittest_without_module_mode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "lightweight-unittest",
                        "command": [
                            "python3",
                            "-B",
                            "validation/tools/test_competition_environment_profile.py",
                        ],
                        "returncode": 0,
                        "workdir": ".",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "step lightweight-unittest command must run python3 -B -m unittest"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_parent_traversal_out_root_ref(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "vendored-clang-verification",
                        "command": [
                            "python3",
                            "-B",
                            "validation/tools/verify_vendored_clang.py",
                            "--out",
                            "out-root:../summary/vendored-clang-verification.json",
                        ],
                        "returncode": 0,
                        "workdir": ".",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "command repo input --out must be repo-relative POSIX"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_common_ci_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": [
                            "/workspace/project/config/competition-env/toolchain-check.sh",
                            "/__w/repo/repo/python",
                            "/opt/hostedtoolcache/Python/python",
                            "/builds/group/project/tool",
                            "/root/work/project/tool",
                            "/usr/bin/clang",
                        ],
                        "returncode": 0,
                        "stdout": "source path: /workspace/project/src/fdb.c; compiler: /usr/bin/clang",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_generic_unc_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": [r"\\server\share\toolchain-check.bat", "//server/share/toolchain-check.sh"],
                        "returncode": 0,
                        "stderr": r"include path: \\server\share\project\include and //server/share/project/include",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_host_path_workdir_forms(self) -> None:
        # Drift matrix cell: workdir field x each host path form. The existing
        # workdir tests only lock parent-traversal / missing / non-root /
        # cwd-disagreement / non-string; none pin that a Windows drive, UNC,
        # WSL (\\wsl$, //wsl$, //wsl.localhost) or /mnt/c / Linux-absolute
        # workdir is rejected fail-closed.
        host_workdirs = {
            "windows-drive": "C:\\Users\\runner\\repo",
            "windows-drive-forward": "C:/Users/runner/repo",
            "windows-unc": "\\\\server\\share\\repo",
            "wsl-unc-backslash": "\\\\wsl$\\Ubuntu\\home\\runner\\repo",
            "wsl-localhost-backslash": "\\\\wsl.localhost\\Ubuntu\\home\\runner\\repo",
            "wsl-slash-alias": "//wsl$/Ubuntu/home/runner/repo",
            "wsl-localhost-slash": "//wsl.localhost/Ubuntu/home/runner/repo",
            "wsl-drive-mount": "/mnt/c/Users/runner/repo",
            "linux-home": "/home/runner/repo",
            "linux-root": "/root/work/repo",
        }
        for label, workdir in host_workdirs.items():
            with self.subTest(workdir=label):
                with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
                    command_log = Path(tmp) / "commands.jsonl"
                    command_log.write_text(
                        json.dumps(
                            {
                                "step": "environment-check",
                                "command": ["bash", "-lc", "echo ok"],
                                "returncode": 0,
                                "workdir": workdir,
                            },
                            sort_keys=True,
                        )
                        + "\n",
                        encoding="utf-8",
                    )

                    with self.assertRaisesRegex(
                        ValueError, "workdir contains forbidden local absolute path"
                    ):
                        validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_host_path_cwd_forms(self) -> None:
        # Drift matrix cell: cwd field x each host path form, with a repo-root
        # workdir="." so the earlier workdir gate passes and the cwd branch is
        # what fails closed.
        host_cwds = {
            "windows-drive": "C:\\Users\\runner\\repo",
            "windows-unc": "\\\\server\\share\\repo",
            "wsl-unc-backslash": "\\\\wsl$\\Ubuntu\\home\\runner\\repo",
            "wsl-slash-alias": "//wsl$/Ubuntu/home/runner/repo",
            "wsl-localhost-slash": "//wsl.localhost/Ubuntu/home/runner/repo",
            "wsl-drive-mount": "/mnt/c/Users/runner/repo",
            "linux-usr": "/usr/local/repo",
        }
        for label, cwd in host_cwds.items():
            with self.subTest(cwd=label):
                with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
                    command_log = Path(tmp) / "commands.jsonl"
                    command_log.write_text(
                        json.dumps(
                            {
                                "step": "environment-check",
                                "command": ["bash", "-lc", "echo ok"],
                                "returncode": 0,
                                "cwd": cwd,
                                "workdir": ".",
                            },
                            sort_keys=True,
                        )
                        + "\n",
                        encoding="utf-8",
                    )

                    # The cwd/workdir scan labels both fields "workdir" in the
                    # forbidden-path message; the point is the host cwd is
                    # rejected fail-closed rather than silently accepted.
                    with self.assertRaisesRegex(
                        ValueError, "workdir contains forbidden local absolute path"
                    ):
                        validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_host_path_repo_input_flag_values(self) -> None:
        # Drift matrix cell: repo-input flag values (--out / --output /
        # --coverage-report / --slice-spec) x host path forms. Existing tests
        # only lock ~/ (tilde) and ../ (parent traversal) for these flags; none
        # pin that a Windows drive, UNC, WSL or /mnt/c value supplied to a
        # source/output flag is rejected fail-closed.
        script_by_step = {
            "core-auto-evidence-validator": "validation/tools/validate_auto_translation_evidence.py",
            "vendored-clang-verification": "validation/tools/verify_vendored_clang.py",
            "translator-coverage-matrix": "validation/tools/translator_coverage_matrix.py",
        }
        host_values = {
            "windows-drive": "C:\\out\\summary.json",
            "windows-drive-forward": "C:/out/summary.json",
            "windows-unc": "\\\\server\\share\\out.json",
            "wsl-unc-backslash": "\\\\wsl$\\Ubuntu\\home\\runner\\out.json",
            "wsl-slash-alias": "//wsl$/Ubuntu/home/runner/out.json",
            "wsl-localhost-slash": "//wsl.localhost/Ubuntu/home/runner/out.json",
            "wsl-drive-mount": "/mnt/c/Users/runner/out.json",
            "linux-home": "/home/runner/out.json",
        }
        flag_by_step = {
            "core-auto-evidence-validator": "--slice-spec",
            "vendored-clang-verification": "--out",
            "translator-coverage-matrix": "--coverage-report",
        }
        for step, flag in flag_by_step.items():
            for label, value in host_values.items():
                with self.subTest(step=step, flag=flag, value=label):
                    with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
                        command_log = Path(tmp) / "commands.jsonl"
                        command_log.write_text(
                            json.dumps(
                                {
                                    "step": step,
                                    "command": ["python3", "-B", script_by_step[step], flag, value],
                                    "returncode": 0,
                                    "workdir": ".",
                                },
                                sort_keys=True,
                            )
                            + "\n",
                            encoding="utf-8",
                        )

                        with self.assertRaisesRegex(
                            ValueError, "command contains forbidden local absolute path"
                        ):
                            validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_rejects_host_path_output_flag_value(self) -> None:
        # Drift matrix cell: --output flag value x host path form. --output is
        # in COMPETITION_SMOKE_REPO_INPUT_FLAGS/OUTPUT_FLAGS but no negative
        # test locks a host absolute value for it specifically.
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                json.dumps(
                    {
                        "step": "milestone-release-report",
                        "command": [
                            "python3",
                            "-B",
                            "validation/tools/milestone_release_report.py",
                            "--output",
                            "\\\\wsl$\\Ubuntu\\home\\runner\\project\\target\\report.json",
                        ],
                        "returncode": 0,
                        "workdir": ".",
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "command contains forbidden local absolute path"):
                validator.validate_competition_smoke_command_log_contract(command_log)

    def test_competition_smoke_command_log_accepts_repo_relative_workdir_cwd_and_flag_values(self) -> None:
        # Green control for the drift matrix: legitimate repo-relative cwd,
        # workdir, and repo-input flag values (including an out-root:-prefixed
        # output) must pass so the negative cells above are not vacuously green.
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            command_log = Path(tmp) / "commands.jsonl"
            command_log.write_text(
                "".join(
                    json.dumps(entry, sort_keys=True) + "\n"
                    for entry in [
                        {
                            "step": "environment-check",
                            "command": ["bash", "-lc", "echo ok"],
                            "returncode": 0,
                            "cwd": ".",
                            "workdir": ".",
                        },
                        {
                            "step": "core-auto-evidence-validator",
                            "command": [
                                "python3",
                                "-B",
                                "validation/tools/validate_auto_translation_evidence.py",
                                "--slice-spec",
                                "validation/slice-specs/flashdb-real-fdb-calc-crc32.json",
                            ],
                            "returncode": 0,
                            "workdir": ".",
                        },
                        {
                            "step": "vendored-clang-verification",
                            "command": [
                                "python3",
                                "-B",
                                "validation/tools/verify_vendored_clang.py",
                                "--out",
                                "out-root:summary/vendored-clang-verification.json",
                            ],
                            "returncode": 0,
                            "workdir": ".",
                        },
                    ]
                ),
                encoding="utf-8",
            )

            result = validator.validate_competition_smoke_command_log_contract(command_log)

            self.assertEqual(result["status"], "passed")
