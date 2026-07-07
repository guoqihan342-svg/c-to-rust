def validate_config(
    config_path: Path,
    *,
    require_local_artifacts: bool = False,
    repo_root: Path = REPO_ROOT,
    entrypoint_ids: list[str] | None = None,
) -> dict[str, Any]:
    config_path = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_json(config_path)
    errors: list[str] = []
    entrypoint_results: list[dict[str, Any]] = []
    claim_boundary: dict[str, Any] = {}
    competition_env_bundle_contract: dict[str, Any] = {}
    environment_profile_contract: dict[str, Any] = {}
    source_pin_contract: dict[str, Any] = {}

    try:
        if config.get("schema_version") != 1:
            raise ValueError("schema_version must be 1")
        if config.get("manifest_kind") != "judge-entrypoints":
            raise ValueError("manifest_kind must be judge-entrypoints")
        if config.get("status") != "active":
            raise ValueError("status must be active")
    except ValueError as error:
        errors.append(str(error))

    try:
        claim_boundary = validate_claim_boundary(config)
    except (KeyError, ValueError) as error:
        errors.append(str(error))

    try:
        environment_profile_contract = validate_competition_environment_profile_contract(
            config["environment_profile"],
            repo_root=repo_root,
        )
        competition_env_bundle_contract = validate_competition_env_bundle_contract(config, repo_root=repo_root)
        assert_no_local_absolute_path(str(config.get("source_pin", {}).get("checkout_command", "")))
    except (KeyError, ValueError) as error:
        errors.append(str(error))

    try:
        config = config_for_selected_entrypoints(config, entrypoint_ids or [])
    except ValueError as error:
        errors.append(str(error))
        return {
            "status": "failed",
            "config": {"path": repo_relative(config_path, repo_root), "sha256": sha256_file(config_path)},
            "entrypoint_count": 0,
            "entrypoints": [],
            "claim_boundary": claim_boundary,
            "environment_profile_contract": environment_profile_contract,
            "competition_env_bundle_contract": competition_env_bundle_contract,
            "proof_class_contract": {},
            "source_pin_contract": source_pin_contract,
            "test_contract": {},
            "require_local_artifacts": require_local_artifacts,
            "errors": errors,
        }

    entrypoints = config.get("entrypoints")
    if not isinstance(entrypoints, list) or not entrypoints:
        errors.append("entrypoints must be a non-empty list")
        entrypoints = []

    dict_entrypoints = [entry for entry in entrypoints if isinstance(entry, dict)]
    try:
        proof_class_contract = validate_proof_class_contract(config, dict_entrypoints)
    except ValueError as error:
        proof_class_contract = {}
        errors.append(str(error))
    try:
        source_pin_contract = validate_source_pin_contract(config, repo_root=repo_root)
    except ValueError as error:
        source_pin_contract = {}
        errors.append(str(error))

    valid_entrypoints: list[dict[str, Any]] = []
    for entry in entrypoints:
        try:
            if not isinstance(entry, dict):
                raise ValueError("entrypoint must be an object")
            valid_entrypoints.append(entry)
            command = entry.get("command")
            validate_entrypoint_command_contract(command, entry.get("id"))
            assert_no_local_absolute_path(command)
            for command_text in entry.get("verification_commands", []):
                validate_portable_python3_b_command(command_text, "verification command")
                assert_no_local_absolute_path(str(command_text))
            audit_command = entry.get("audit_command")
            if isinstance(audit_command, str):
                validate_portable_python3_b_command(audit_command, "audit command")
                assert_no_local_absolute_path(audit_command)
            expected_artifacts = entry.get("expected_artifacts", {})
            review_checklist_result = validate_entrypoint_review_checklist_ref(entry, repo_root=repo_root)
            if is_competition_smoke_entrypoint(entry):
                smoke_contract = validate_competition_smoke_entrypoint_contract(entry)
                entry_result = entrypoint_metadata(entry)
                entry_result.update(
                    {
                        "status": "passed",
                        "smoke_contract": smoke_contract,
                        "review_checklist": review_checklist_result["ref"],
                        "review_checklist_contract": review_checklist_result["contract"],
                        "expected_artifacts": validate_expected_artifacts(
                            expected_artifacts,
                            require_local_artifacts=require_local_artifacts,
                            repo_root=repo_root,
                        ),
                        "harness_contracts": validate_harness_artifact_contracts(
                            expected_artifacts,
                            require_local_artifacts=require_local_artifacts,
                            repo_root=repo_root,
                            environment_profile=config.get("environment_profile"),
                            smoke_contract=smoke_contract,
                            entrypoint=entry,
                        ),
                    }
                )
                entrypoint_results.append(
                    entry_result
                )
                continue
            entry_result = entrypoint_metadata(entry)
            entry_result.update(
                {
                    "status": "passed",
                    "profile": validate_ref(entry["profile"], repo_root=repo_root),
                    "profile_contract": (
                        validate_entrypoint_profile_contract(
                            entry,
                            config=config,
                            source_pin_contract=source_pin_contract,
                            repo_root=repo_root,
                        )
                        if source_pin_contract
                        else {"status": "skipped", "reason": "source_pin_contract_failed"}
                    ),
                    "tracked_manifest": validate_ref(entry["tracked_manifest"], repo_root=repo_root),
                    "tracked_manifest_contract": validate_tracked_manifest_contract(
                        entry,
                        config=config,
                        claim_boundary=claim_boundary,
                        source_pin_contract=source_pin_contract,
                        repo_root=repo_root,
                    ),
                    "review_checklist": review_checklist_result["ref"],
                    "review_checklist_contract": review_checklist_result["contract"],
                    "expected_artifacts": validate_expected_artifacts(
                        expected_artifacts,
                        require_local_artifacts=require_local_artifacts,
                        repo_root=repo_root,
                    ),
                    "harness_contracts": validate_harness_artifact_contracts(
                        expected_artifacts,
                        require_local_artifacts=require_local_artifacts,
                        repo_root=repo_root,
                        environment_profile=config.get("environment_profile"),
                        entrypoint=entry,
                    ),
                }
            )
            entrypoint_results.append(
                entry_result
            )
        except (KeyError, ValueError) as error:
            entrypoint_results.append({"id": entry.get("id") if isinstance(entry, dict) else None, "status": "failed"})
            errors.append(str(error))

    try:
        test_contract = validate_test_contract(config, entrypoints=valid_entrypoints, claim_boundary=claim_boundary)
    except ValueError as error:
        test_contract = {}
        errors.append(str(error))

    return {
        "status": "failed" if errors else "passed",
        "config": {"path": repo_relative(config_path, repo_root), "sha256": sha256_file(config_path)},
        "entrypoint_count": len(entrypoint_results),
        "entrypoints": entrypoint_results,
        "claim_boundary": claim_boundary,
        "environment_profile_contract": environment_profile_contract,
        "competition_env_bundle_contract": competition_env_bundle_contract,
        "proof_class_contract": proof_class_contract,
        "source_pin_contract": source_pin_contract,
        "test_contract": test_contract,
        "require_local_artifacts": require_local_artifacts,
        "errors": errors,
    }


def config_for_selected_entrypoints(config: dict[str, Any], entrypoint_ids: list[str]) -> dict[str, Any]:
    if not entrypoint_ids:
        return config
    raw_entrypoints = config.get("entrypoints")
    if not isinstance(raw_entrypoints, list) or not raw_entrypoints:
        raise ValueError("entrypoints must be a non-empty list")
    entrypoints = [entry for entry in raw_entrypoints if isinstance(entry, dict)]
    by_id = {str(entry.get("id")): entry for entry in entrypoints}
    missing = [entrypoint_id for entrypoint_id in entrypoint_ids if entrypoint_id not in by_id]
    if missing:
        raise ValueError(f"unknown entrypoint id: {', '.join(missing)}")

    filtered = json.loads(json.dumps(config))
    filtered["entrypoints"] = [by_id[entrypoint_id] for entrypoint_id in entrypoint_ids]
    contract = filtered.get("test_contract")
    if isinstance(contract, dict) and isinstance(contract.get("required_entrypoint_ids"), list):
        contract["required_entrypoint_ids"] = list(entrypoint_ids)
    return filtered


if __name__ == "__main__":
    raise SystemExit(main())
