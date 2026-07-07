class _OpenCodeAgentHarnessTestPart08:
    def test_opencode_preflight_fails_closed_when_glm_model_is_not_listed(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"
            resolved_opencode = Path(tmp) / "bin" / "opencode.CMD"
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        stdout="openai/gpt-5.1\nopencode/deepseek-v4-flash-free\n",
                        stderr="",
                    )
                raise AssertionError("opencode run must not start when GLM-5.1 is unavailable")

            with patch.object(harness, "resolve_subprocess_command", return_value=str(resolved_opencode)):
                result = harness.run_opencode_preflight(
                    out_root=out_root,
                    run_id="preflight-run",
                    opencode_model="GLM-5.1",
                    opencode_agent="c2rust-migrator",
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], str(resolved_opencode))
            self.assertEqual(calls[0][1], "models")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["root_cause_key"], "opencode_model_unavailable")
            blocker = result["h9_blocker"]
            self.assertEqual(blocker["status"], "blocked")
            self.assertEqual(blocker["root_cause_key"], "opencode_model_unavailable")
            self.assertEqual(blocker["required_agent_tool"], "opencode")
            self.assertEqual(blocker["required_agent"], "c2rust-migrator")
            self.assertEqual(blocker["required_model"], "GLM-5.1")
            self.assertEqual(blocker["required_variant"], "max")
            self.assertEqual(blocker["required_proof_class"], "competition-exact")
            self.assertFalse(blocker["local_simulation_closes_p0_h9"])
            self.assertFalse(blocker["opencode_run_launched"])
            self.assertEqual(blocker["observed_model_availability"]["status"], "unavailable")
            self.assertEqual(blocker["next_required_action"], "rerun_on_real_opencode_glm51_max_host")
            self.assertEqual(result["argv"][0], "opencode")
            self.assertEqual(result["argv"][result["argv"].index("--dir") + 1], ".")
            self.assertFalse(result["marker_exists"])
            self.assertFalse(result["opencode_run_launched"])
            self.assertEqual(result["contract_verification"]["status"], "not-observed")
            self.assertEqual(result["contract_verification"]["contract_failure_reason"], "opencode_model_unavailable")
            availability = result["opencode_model_availability"]
            self.assertEqual(availability["status"], "unavailable")
            self.assertEqual(availability["required_model"], "GLM-5.1")
            self.assertFalse(availability["model_listed"])
            self.assertEqual(availability["failure_reason"], "required_model_not_listed")
            self.assertEqual(availability["argv"], ["opencode", "models"])
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["root_cause_key"], "opencode_model_unavailable")
            self.assertEqual(report["h9_blocker"], blocker)
            contract = json.loads((REPO_ROOT / report["handoff_contract"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(contract["opencode_argv"], result["argv"])
            serialized_report = json.dumps(report, sort_keys=True)
            serialized_contract = json.dumps(contract, sort_keys=True)
            self.assertNotIn(str(resolved_opencode), serialized_report)
            self.assertNotIn(str(resolved_opencode), serialized_contract)
            self.assertNotIn(str(REPO_ROOT), serialized_report)
            self.assertNotIn(str(REPO_ROOT), serialized_contract)
            stdout = (REPO_ROOT / report["opencode_model_availability"]["logs"]["stdout"]).read_text(encoding="utf-8")
            self.assertIn("openai/gpt-5.1", stdout)

    def test_opencode_model_probe_rejects_near_match_model_ids(self) -> None:
        stdout = "zhipu/GLM-5.10\nopencode/not-GLM-5.1\nzhipu/glm-5.1\n"
        self.assertFalse(harness.opencode_models_output_mentions_required_model(stdout, "GLM-5.1"))
        self.assertTrue(harness.opencode_models_output_mentions_required_model("GLM-5.1\n", "GLM-5.1"))
        self.assertTrue(harness.opencode_models_output_mentions_required_model("zhipu/GLM-5.1\n", "GLM-5.1"))

    def test_opencode_launch_policy_defaults_to_repo_owned_agent_and_rejects_wrong_agent(self) -> None:
        policy = harness.opencode_launch_policy(
            opencode_command="opencode",
            opencode_model="GLM-5.1",
            opencode_agent=None,
            opencode_variant="max",
            opencode_skip_permissions=False,
        )
        self.assertEqual(policy["opencode_agent"], "c2rust-migrator")
        with self.assertRaisesRegex(SystemExit, "opencode_agent must be c2rust-migrator"):
            harness.opencode_launch_policy(
                opencode_command="opencode",
                opencode_model="GLM-5.1",
                opencode_agent="default",
                opencode_variant="max",
                opencode_skip_permissions=False,
            )

    def test_validate_opencode_preflight_report_rejects_missing_model_availability(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            payload.pop("opencode_model_availability")
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight model availability is missing"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_unavailable_glm_model(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            payload["opencode_model_availability"].update(
                {
                    "status": "unavailable",
                    "failure_reason": "required_model_not_listed",
                    "model_listed": False,
                }
            )
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight model availability is not passed"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_wrong_model_probe_argv(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            payload["opencode_model_availability"]["argv"] = ["opencode", "list-models"]
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight model availability argv"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_report_argv_drift_from_handoff(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            payload["argv"] = [
                "opencode",
                "run",
                "--dir",
                ".",
                "--format",
                "json",
                "--variant",
                "max",
                "--model",
                "openai/gpt-5.1",
                "Execute test preflight marker.",
            ]
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight report argv must match handoff_contract.opencode_argv"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_local_absolute_report_argv(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            handoff_path = REPO_ROOT / payload["handoff_contract"]["path"]
            handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
            bad_argv = list(payload["argv"])
            bad_argv[0] = "C:/Users/me/AppData/Roaming/npm/opencode.CMD"
            payload["argv"] = bad_argv
            handoff_payload["opencode_argv"] = bad_argv
            handoff_payload["opencode_command_line"] = harness.shell_command_line(bad_argv)
            handoff_path.write_text(json.dumps(handoff_payload, sort_keys=True) + "\n", encoding="utf-8")
            payload["handoff_contract"]["sha256"] = harness.sha256_file(handoff_path)
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight report argv must be portable"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_model_probe_log_hash_drift(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            stdout_path = REPO_ROOT / payload["opencode_model_availability"]["logs"]["stdout"]
            stdout_path.write_text("openai/gpt-5.1\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight model availability stdout hash mismatch"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_model_probe_stdout_without_glm(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            stdout_text = "openai/gpt-5.1\nopencode/not-GLM-5.1\n"
            stdout_path = REPO_ROOT / payload["opencode_model_availability"]["logs"]["stdout"]
            stdout_path.write_text(stdout_text, encoding="utf-8")
            payload["opencode_model_availability"]["stdout_sha256"] = harness.sha256_text(stdout_text)
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight model availability stdout missing GLM-5.1"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_recomputes_marker_contract_from_session_evidence(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            session_path = REPO_ROOT / payload["opencode_session_evidence"]["path"]
            session_payload = json.loads(session_path.read_text(encoding="utf-8"))
            session_payload["session_events"][0]["part"]["state"]["input"]["command"] = (
                "python3 -B validation/tools/opencode_agent_harness.py list-workers --db target/fake.sqlite3"
            )
            session_path.write_text(json.dumps(session_payload, sort_keys=True) + "\n", encoding="utf-8")
            payload["opencode_session_evidence"]["sha256"] = harness.sha256_file(session_path)
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight session contract"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_marker_hash_drift(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            marker_path = REPO_ROOT / payload["marker_path"]
            marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
            marker_payload["tampered_after_preflight_report"] = True
            marker_path.write_text(json.dumps(marker_payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, r"opencode preflight marker.sha256 mismatch"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_validate_opencode_preflight_report_rejects_invalid_marker_payload(self) -> None:
        with temp_repo_dir() as tmp:
            preflight_report = write_passing_opencode_preflight_report(
                Path(tmp) / "opencode-preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            marker_path = REPO_ROOT / payload["marker_path"]
            marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
            marker_payload["report_kind"] = "not-opencode-preflight-marker"
            marker_path.write_text(json.dumps(marker_payload, sort_keys=True) + "\n", encoding="utf-8")
            payload["marker"]["sha256"] = harness.sha256_file(marker_path)
            preflight_report.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "opencode preflight marker payload invalid"):
                harness.validate_opencode_preflight_report(
                    preflight_report,
                    expected_run_id="run-test",
                    repo_root=REPO_ROOT,
                )

    def test_opencode_preflight_defaults_to_glm_51_model(self) -> None:
        argv = harness.build_opencode_preflight_argv(
            opencode_command="opencode",
            opencode_model=None,
            opencode_agent="c2rust-migrator",
            opencode_variant="max",
            opencode_skip_permissions=False,
            marker_command=["python3", "-B", "validation/tools/opencode_agent_harness.py", "write-preflight-marker"],
            marker_path=Path("target/opencode-preflight/harness/opencode-preflight-marker.json"),
            contract_path=Path("target/opencode-preflight/harness/opencode-preflight-contract.json"),
            repo_root=REPO_ROOT,
        )

        self.assertIn("--model", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "GLM-5.1")
        self.assertIn("--agent", argv)
        self.assertEqual(argv[argv.index("--agent") + 1], "c2rust-migrator")

    def test_opencode_preflight_rejects_non_glm_model(self) -> None:
        with self.assertRaisesRegex(SystemExit, "opencode_model must be GLM-5.1"):
            harness.build_opencode_preflight_argv(
                opencode_command="opencode",
                opencode_model="gpt-5.4",
                opencode_agent="c2rust-migrator",
                opencode_variant="max",
                opencode_skip_permissions=False,
                marker_command=["python3", "-B", "validation/tools/opencode_agent_harness.py", "write-preflight-marker"],
                marker_path=Path("target/opencode-preflight/harness/opencode-preflight-marker.json"),
                contract_path=Path("target/opencode-preflight/harness/opencode-preflight-contract.json"),
                repo_root=REPO_ROOT,
            )

    def test_opencode_preflight_allows_deepseek_for_local_rehearsal_only(self) -> None:
        argv = harness.build_opencode_preflight_argv(
            opencode_command="opencode",
            opencode_model="deepseek/deepseek-chat",
            opencode_agent="c2rust-migrator",
            opencode_variant="max",
            opencode_skip_permissions=False,
            opencode_allow_non_competition_model=True,
            marker_command=["python3", "-B", "validation/tools/opencode_agent_harness.py", "write-preflight-marker"],
            marker_path=Path("target/opencode-preflight/harness/opencode-preflight-marker.json"),
            contract_path=Path("target/opencode-preflight/harness/opencode-preflight-contract.json"),
            repo_root=REPO_ROOT,
        )

        self.assertIn("--model", argv)
        self.assertEqual(argv[argv.index("--model") + 1], "deepseek/deepseek-chat")
        self.assertIn("--agent", argv)
        self.assertEqual(argv[argv.index("--agent") + 1], "c2rust-migrator")

    def test_opencode_model_probe_allows_deepseek_for_local_rehearsal_only(self) -> None:
        with temp_repo_dir() as tmp:
            logs_dir = Path(tmp) / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(argv, 0, stdout="deepseek/deepseek-chat\n", stderr="")

            result = harness.run_opencode_model_availability_probe(
                opencode_command="opencode",
                opencode_model="deepseek/deepseek-chat",
                opencode_allow_non_competition_model=True,
                logs_dir=logs_dir,
                opencode_process_env={},
                timeout_seconds=5,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["required_model"], "deepseek/deepseek-chat")
        self.assertTrue(result["model_listed"])

    def test_opencode_preflight_rejects_non_max_variant(self) -> None:
        with self.assertRaisesRegex(SystemExit, "opencode_variant must be max"):
            harness.build_opencode_preflight_argv(
                opencode_command="opencode",
                opencode_model="GLM-5.1",
                opencode_agent="c2rust-migrator",
                opencode_variant="lite",
                opencode_skip_permissions=False,
                marker_command=["python3", "-B", "validation/tools/opencode_agent_harness.py", "write-preflight-marker"],
                marker_path=Path("target/opencode-preflight/harness/opencode-preflight-marker.json"),
                contract_path=Path("target/opencode-preflight/harness/opencode-preflight-contract.json"),
                repo_root=REPO_ROOT,
            )

    def test_opencode_preflight_rejects_non_opencode_command(self) -> None:
        with self.assertRaisesRegex(SystemExit, "opencode_command must be opencode"):
            harness.build_opencode_preflight_argv(
                opencode_command="codex",
                opencode_model="GLM-5.1",
                opencode_agent="c2rust-migrator",
                opencode_variant="max",
                opencode_skip_permissions=False,
                marker_command=["python3", "-B", "validation/tools/opencode_agent_harness.py", "write-preflight-marker"],
                marker_path=Path("target/opencode-preflight/harness/opencode-preflight-marker.json"),
                contract_path=Path("target/opencode-preflight/harness/opencode-preflight-contract.json"),
                repo_root=REPO_ROOT,
            )

    def test_opencode_preflight_rejects_marker_when_first_shell_command_differs(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                write_valid_preflight_marker(marker_path, run_id="preflight-run")
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": "python -m validation.tools.opencode_agent_harness init-run --run-id wrong"},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            result = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-run",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["root_cause_key"], "opencode_contract_not_executed")
            self.assertTrue(result["marker_exists"])
            self.assertEqual(result["contract_verification"]["status"], "not-executed")
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["root_cause_key"], "opencode_contract_not_executed")

    def test_opencode_preflight_reports_failure_when_process_crashes(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"

            def crash_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="opencode: not found\n")

            result = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-run",
                command_runner=crash_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["process_returncode"], 1)
            self.assertEqual(result["root_cause_key"], "opencode_process_failed")
            self.assertFalse(result["marker_exists"])
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["root_cause_key"], "opencode_process_failed")
            stderr = (REPO_ROOT / report["logs"]["stderr"]).read_text(encoding="utf-8")
            self.assertIn("opencode: not found", stderr)

    def test_run_worker_process_once_times_out_fail_closed(self) -> None:
        seen_kwargs: dict[str, object] = {}

        def timeout_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            seen_kwargs.update(kwargs)
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"), output="partial stdout", stderr="partial stderr")

        completed = harness.run_worker_process_once(
            argv=["opencode", "run"],
            command_runner=timeout_runner,
            repo_root=REPO_ROOT,
            timeout_seconds=7,
        )

        self.assertEqual(seen_kwargs["timeout"], 7)
        self.assertEqual(completed.returncode, 124)
        self.assertIn("partial stdout", completed.stdout)
        self.assertIn("partial stderr", completed.stderr)
        self.assertIn("timed out after 7 seconds", completed.stderr)

    def test_run_captured_process_with_timeout_kills_process_tree(self) -> None:
        seen_kwargs: dict[str, object] = {}
        killed_pids: list[int] = []

        class HungProcess:
            pid = 4321
            returncode = None

            def communicate(self, timeout: int | None = None) -> tuple[str, str]:
                raise subprocess.TimeoutExpired(
                    ["opencode", "run"],
                    timeout,
                    output="partial stdout",
                    stderr="partial stderr",
                )

        def popen_factory(argv: list[str], **kwargs: object) -> HungProcess:
            seen_kwargs.update(kwargs)
            return HungProcess()

        def kill_process_tree(process: HungProcess) -> None:
            killed_pids.append(process.pid)
            process.returncode = -9

        completed = harness.run_captured_process_with_timeout(
            ["opencode", "run"],
            cwd=REPO_ROOT,
            env={"OPENCODE_CONFIG_HOME": "isolated"},
            timeout_seconds=3,
            popen_factory=popen_factory,
            process_tree_killer=kill_process_tree,
        )

        self.assertEqual(killed_pids, [4321])
        self.assertEqual(seen_kwargs["cwd"], REPO_ROOT)
        self.assertTrue(seen_kwargs["text"])
        self.assertEqual(seen_kwargs["encoding"], "utf-8")
        self.assertEqual(seen_kwargs["errors"], "replace")
        self.assertIs(seen_kwargs["stdout"], subprocess.PIPE)
        self.assertIs(seen_kwargs["stderr"], subprocess.PIPE)
        self.assertEqual(seen_kwargs["env"], {"OPENCODE_CONFIG_HOME": "isolated"})
        self.assertEqual(completed.returncode, 124)
        self.assertIn("partial stdout", completed.stdout)
        self.assertIn("partial stderr", completed.stderr)
        self.assertIn("timed out after 3 seconds", completed.stderr)

    def test_run_worker_process_once_real_subprocess_timeout(self) -> None:
        started_at = time.monotonic()

        completed = harness.run_worker_process_once(
            argv=[sys.executable, "-B", "-c", "import time; time.sleep(5)"],
            command_runner=subprocess.run,
            repo_root=REPO_ROOT,
            timeout_seconds=1,
        )

        elapsed = time.monotonic() - started_at
        self.assertLess(elapsed, 4.0)
        self.assertEqual(completed.returncode, 124)
        self.assertEqual(completed.stdout, "")
        self.assertIn("timed out after 1 seconds", completed.stderr)

    def test_run_captured_process_with_timeout_stops_child_holding_pipes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            heartbeat = Path(tmp) / "child-heartbeat.txt"
            child_code = (
                "import pathlib, sys, time\n"
                "path = pathlib.Path(sys.argv[1])\n"
                "for idx in range(80):\n"
                "    path.write_text(str(idx), encoding='utf-8')\n"
                "    print(f'child heartbeat {idx}', flush=True)\n"
                "    time.sleep(0.1)\n"
            )
            parent_code = (
                "import os, subprocess, sys, time\n"
                "heartbeat = sys.argv[1]\n"
                "child_code = sys.argv[2]\n"
                "subprocess.Popen(\n"
                "    [sys.executable, '-B', '-c', child_code, heartbeat],\n"
                "    stdout=sys.stdout,\n"
                "    stderr=sys.stderr,\n"
                "    close_fds=False,\n"
                ")\n"
                "deadline = time.time() + 3\n"
                "while not os.path.exists(heartbeat) and time.time() < deadline:\n"
                "    time.sleep(0.05)\n"
                "print('parent ready', flush=True)\n"
                "time.sleep(30)\n"
            )

            started_at = time.monotonic()
            completed = harness.run_captured_process_with_timeout(
                [sys.executable, "-B", "-c", parent_code, str(heartbeat), child_code],
                cwd=REPO_ROOT,
                timeout_seconds=1,
            )

            elapsed = time.monotonic() - started_at
            self.assertLess(elapsed, 7.0)
            self.assertEqual(completed.returncode, 124)
            self.assertTrue(heartbeat.exists())
            first_heartbeat = heartbeat.read_text(encoding="utf-8")
            time.sleep(0.6)
            self.assertEqual(heartbeat.read_text(encoding="utf-8"), first_heartbeat)
            self.assertIn("timed out after 1 seconds", completed.stderr)

    def test_opencode_preflight_timeout_records_124_and_logs(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"
            seen_kwargs: dict[str, object] = {}

            def timeout_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                seen_kwargs.update(kwargs)
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"), output="", stderr="agent hung")

            result = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-run",
                command_runner=timeout_runner,
                timeout_seconds=9,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(seen_kwargs["timeout"], 9)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["process_returncode"], 124)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["timeout_seconds"], 9)
            self.assertEqual(result["root_cause_key"], "process_timeout")
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertTrue(report["timed_out"])
            stderr = (REPO_ROOT / report["logs"]["stderr"]).read_text(encoding="utf-8")
            self.assertIn("agent hung", stderr)
            self.assertIn("timed out after 9 seconds", stderr)

    def test_opencode_preflight_default_runner_uses_process_tree_timeout(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"
            seen_kwargs: dict[str, object] = {}

            def captured_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                seen_kwargs.update(kwargs)
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                return subprocess.CompletedProcess(
                    argv,
                    124,
                    stdout="",
                    stderr="timed out after 5 seconds\n",
                )

            with patch.object(harness, "run_captured_process_with_timeout", side_effect=captured_runner) as runner:
                result = harness.run_opencode_preflight(
                    out_root=out_root,
                    run_id="preflight-run",
                    timeout_seconds=5,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(runner.call_count, 2)
            self.assertEqual(seen_kwargs["cwd"], REPO_ROOT)
            self.assertEqual(seen_kwargs["timeout_seconds"], 5)
            self.assertIn("XDG_CONFIG_HOME", seen_kwargs["env"])
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["process_returncode"], 124)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["root_cause_key"], "process_timeout")

    def test_run_worker_timeout_writes_blocked_summary_and_repair_hint(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            worker_out_root = out_root / "workers" / "worker-a"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-timeout",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-timeout",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=worker_out_root,
                repo_root=REPO_ROOT,
            )
            seen_kwargs: dict[str, object] = {}

            def timeout_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                seen_kwargs.update(kwargs)
                raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"), output="worker stdout", stderr="worker stderr")

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-timeout",
                worker_id="worker-a",
                command_runner=timeout_runner,
                timeout_seconds=5,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(seen_kwargs["timeout"], 5)
            self.assertEqual(result["process_returncode"], 124)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["timeout_seconds"], 5)
            self.assertEqual(result["summary_status"], "blocked")
            self.assertEqual(result["repair_hint"]["root_cause_key"], "process_timeout")
            summary = json.loads((worker_out_root / "summary" / "competition-run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "blocked")
            metrics = json.loads((worker_out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(metrics["root_cause_counts"], {"process_timeout": 1})

    def test_execute_merge_plan_timeout_records_124(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-timeout",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            seen_kwargs: dict[str, object] = {}

            def timeout_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                seen_kwargs.update(kwargs)
                raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"), output="merge stdout", stderr="merge stderr")

            result = harness.execute_merge_plan(
                db_path=db_path,
                run_id="run-timeout",
                out_root=out_root,
                merge_plan={"argv": ["python3", "-B", "validation/tools/run_competition.py"]},
                command_runner=timeout_runner,
                timeout_seconds=11,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(seen_kwargs["timeout"], 11)
            self.assertEqual(result["exit_code"], 124)
            self.assertEqual(result["process_returncode"], 124)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["timeout_seconds"], 11)
            self.assertEqual(result["root_cause_key"], "process_timeout")
            stderr = (out_root / "harness" / "run-plan-merge.stderr.log").read_text(encoding="utf-8")
            self.assertIn("merge stderr", stderr)
            self.assertIn("timed out after 11 seconds", stderr)

    def test_execute_merge_plan_default_runner_uses_process_tree_timeout(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-timeout",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            seen_kwargs: dict[str, object] = {}

            def captured_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                seen_kwargs.update(kwargs)
                return subprocess.CompletedProcess(
                    argv,
                    124,
                    stdout="",
                    stderr="timed out after 13 seconds\n",
                )

            with patch.object(harness, "run_captured_process_with_timeout", side_effect=captured_runner) as runner:
                result = harness.execute_merge_plan(
                    db_path=db_path,
                    run_id="run-timeout",
                    out_root=out_root,
                    merge_plan={"argv": ["python3", "-B", "validation/tools/run_competition.py"]},
                    timeout_seconds=13,
                    repo_root=REPO_ROOT,
                )

            runner.assert_called_once()
            self.assertEqual(seen_kwargs["cwd"], REPO_ROOT)
            self.assertEqual(seen_kwargs["timeout_seconds"], 13)
            self.assertIsNone(seen_kwargs.get("env"))
            self.assertEqual(result["exit_code"], 124)
            self.assertEqual(result["process_returncode"], 124)
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["root_cause_key"], "process_timeout")

    def test_opencode_database_locked_matches_equivalent_sqlite_busy_signals(self) -> None:
        for stderr in [
            "sqlite3.OperationalError: database is locked",
            "sqlite3.OperationalError: database table is locked",
            "SQLITE_BUSY: database is busy",
            "sqlite_busy while opening agent store",
            "sqlite busy while opening agent store",
        ]:
            with self.subTest(stderr=stderr):
                self.assertTrue(harness.opencode_database_locked(subprocess.CompletedProcess(["opencode"], 1, stdout="", stderr=stderr)))
        self.assertFalse(harness.opencode_database_locked(subprocess.CompletedProcess(["opencode"], 1, stdout="", stderr="syntax error")))

    def test_atomic_write_text_preserves_existing_file_when_replace_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "harness" / "report.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("old\n", encoding="utf-8")

            with patch.object(harness.os, "replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    harness.atomic_write_text(target, "new\n")

            self.assertEqual(target.read_text(encoding="utf-8"), "old\n")
            self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])

    def test_atomic_write_json_uses_canonical_json_format(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "report.json"

            harness.atomic_write_json(target, {"b": 2, "a": 1})

            self.assertEqual(target.read_text(encoding="utf-8"), '{\n  "a": 1,\n  "b": 2\n}\n')

    def test_opencode_preflight_cli_dispatches_flags(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "opencode-preflight",
            "--run-id",
            "preflight-run",
            "--out-root",
            "target/opencode-preflight",
            "--opencode-variant",
            "max",
            "--opencode-skip-permissions",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "run_opencode_preflight",
            return_value={"status": "passed", "exit_code": 0},
        ) as runner:
            self.assertEqual(harness.main(), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "passed")
        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs["run_id"], "preflight-run")
        self.assertEqual(runner.call_args.kwargs["out_root"], Path("target/opencode-preflight"))
        self.assertEqual(runner.call_args.kwargs["opencode_variant"], "max")
        self.assertTrue(runner.call_args.kwargs["opencode_skip_permissions"])

    def test_run_worker_opencode_rejects_failed_preflight_report_before_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = out_root / "harness" / "opencode-preflight-report.json"
            preflight_report.parent.mkdir(parents=True, exist_ok=True)
            preflight_report.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "run-test",
                        "status": "failed",
                        "exit_code": 1,
                        "marker_exists": False,
                        "contract_verification": {"status": "not-observed"},
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "opencode preflight report is not passed"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])
