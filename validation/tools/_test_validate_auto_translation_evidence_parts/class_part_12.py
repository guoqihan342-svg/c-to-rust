class _ValidateAutoTranslationEvidenceTestsPart12:
    def semantic_binding_fixture(self, root: Path, module: object) -> dict[str, object]:
        accepted_dir = root / "accepted"
        wrapper_dir = root / "wrappers"
        accepted_dir.mkdir(parents=True)
        wrapper_dir.mkdir(parents=True)
        paths = {}
        path_sha256 = {}
        for key in module.SEMANTIC_ACCEPTED_EVIDENCE_KEYS:
            path = accepted_dir / f"{key}.json"
            path.write_bytes(json.dumps({"key": key, "status": "passed"}, sort_keys=True).encode("utf-8"))
            paths[key] = path.relative_to(root).as_posix()
            path_sha256[key] = module.sha256(path)
        binding = {
            "status": "accepted",
            "paths": paths,
            "path_sha256": path_sha256,
            "generated_draft_semantic_pass": False,
        }

        def clone(value: object) -> object:
            return json.loads(json.dumps(value))

        acceptance = {
            "status": "passed",
            "generated_draft_semantic_pass": True,
            "accepted_evidence_binding": clone(binding),
        }
        auto_manifest = {
            "accepted_evidence_binding": clone(binding),
            "claim_boundary": {"generated_draft_acceptance": clone(acceptance)},
        }
        manifest = {"claim_boundary": {"generated_draft_acceptance": clone(acceptance)}}
        profile = {"generated_draft_acceptance": clone(acceptance)}
        final = {
            "accepted_evidence_binding": clone(binding),
            "generated_draft_acceptance": clone(acceptance),
        }
        test_translation = {"generated_draft_acceptance": clone(acceptance)}

        reports = {}
        evidence_refs = {}
        for key, accepted_key in (
            ("unsafe_scan", "accepted_unsafe_scan"),
            ("unsafe_ledger", "accepted_unsafe_ledger"),
        ):
            wrapper_path = wrapper_dir / f"{key}.json"
            wrapper_path.write_bytes(b"{}")
            reports[key] = {
                accepted_key: {
                    "path": paths[key],
                    "sha256": path_sha256[key],
                    "status": "passed",
                }
            }
            evidence_refs[key] = {"path": wrapper_path.relative_to(root).as_posix()}
        return {
            "auto_manifest": auto_manifest,
            "manifest": manifest,
            "profile": profile,
            "final": final,
            "test_translation": test_translation,
            "reports": reports,
            "evidence_refs": evidence_refs,
            "paths": paths,
        }

    def call_semantic_binding_validator(self, module: object, root: Path, fixture: dict[str, object]) -> None:
        module.validate_semantic_accepted_evidence_bindings(
            fixture["auto_manifest"],
            fixture["manifest"],
            fixture["profile"],
            fixture["final"],
            fixture["test_translation"],
            fixture["reports"],
            fixture["evidence_refs"],
            repo_root=root,
        )

    def semantic_noalias_fixture(self) -> tuple[dict, dict, dict, dict, dict]:
        pair = ["db", "kv"]
        precondition = {"kind": "noalias", "required": True, "applies_to": pair}
        gate = {
            "decision": "requires_noalias_contract",
            "requires_noalias": True,
            "complete_alias_safety": True,
            "preconditions": [precondition],
        }
        spec = {
            "c_boundary": {
                "pointer_contract": {
                    "aliasing_proven": True,
                    "noalias_required": [pair],
                }
            }
        }
        pointer_graph = {
            "alias_contract": {
                "decision": "requires_noalias_contract",
                "requires_noalias": True,
                "complete_alias_safety": True,
                "proven": True,
            },
            "safe_boundary_preconditions": [precondition],
            "alias_risks": [
                {
                    "pointer_nodes": pair,
                    "requires_noalias": True,
                    "gate_decision": "requires_noalias_contract",
                }
            ],
        }
        auto_manifest = {"claim_boundary": {"alias_gate": gate}}
        manifest = {"claim_boundary": {"alias_gate": gate}}
        final = {"alias_gate": gate}
        return spec, pointer_graph, auto_manifest, manifest, final

    def test_semantic_binding_accepts_complete_minimal_fixture(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-binding-") as tmp:
            root = Path(tmp)
            fixture = self.semantic_binding_fixture(root, module)
            self.call_semantic_binding_validator(module, root, fixture)

    def test_semantic_binding_rejects_non_oracle_hash_drift(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-binding-") as tmp:
            root = Path(tmp)
            fixture = self.semantic_binding_fixture(root, module)
            unsafe_scan_path = root / fixture["paths"]["unsafe_scan"]
            unsafe_scan_path.write_bytes(b"drifted")
            fixture["reports"]["unsafe_scan"]["accepted_unsafe_scan"]["sha256"] = module.sha256(
                unsafe_scan_path
            )
            with self.assertRaisesRegex(SystemExit, "path_sha256.unsafe_scan mismatch"):
                self.call_semantic_binding_validator(module, root, fixture)

    def test_semantic_binding_rejects_duplicate_binding_drift(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-binding-") as tmp:
            root = Path(tmp)
            fixture = self.semantic_binding_fixture(root, module)
            fixture["profile"]["generated_draft_acceptance"]["accepted_evidence_binding"][
                "path_sha256"
            ]["unsafe_ledger"] = "0" * 64
            with self.assertRaisesRegex(SystemExit, "accepted_evidence_binding drift across artifacts"):
                self.call_semantic_binding_validator(module, root, fixture)

    def test_semantic_binding_rejects_unsafe_self_reference(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-binding-") as tmp:
            root = Path(tmp)
            fixture = self.semantic_binding_fixture(root, module)
            holder_path = fixture["evidence_refs"]["unsafe_scan"]["path"]
            fixture["reports"]["unsafe_scan"]["accepted_unsafe_scan"]["path"] = holder_path
            with self.assertRaisesRegex(SystemExit, "self-referential unsafe_scan.accepted_unsafe_scan.path"):
                self.call_semantic_binding_validator(module, root, fixture)

    def test_semantic_binding_rejects_parent_traversal(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-binding-") as tmp:
            root = Path(tmp)
            fixture = self.semantic_binding_fixture(root, module)
            for document in (
                fixture["auto_manifest"],
                fixture["manifest"],
                fixture["profile"],
                fixture["final"],
                fixture["test_translation"],
            ):
                for _, binding in module.find_accepted_evidence_bindings(document, "fixture"):
                    binding["paths"]["diff"] = "../outside.json"
            with self.assertRaisesRegex(SystemExit, "safe repo-relative POSIX path"):
                self.call_semantic_binding_validator(module, root, fixture)

    def test_semantic_binding_requires_every_path_and_sha_key(self) -> None:
        module = load_validator_module()
        for field in ("paths", "path_sha256"):
            for key in module.SEMANTIC_ACCEPTED_EVIDENCE_KEYS:
                with self.subTest(field=field, key=key):
                    with tempfile.TemporaryDirectory(prefix="auto-validator-binding-") as tmp:
                        root = Path(tmp)
                        fixture = self.semantic_binding_fixture(root, module)
                        for document in (
                            fixture["auto_manifest"],
                            fixture["manifest"],
                            fixture["profile"],
                            fixture["final"],
                            fixture["test_translation"],
                        ):
                            for _, binding in module.find_accepted_evidence_bindings(document, "fixture"):
                                binding[field].pop(key)
                        with self.assertRaisesRegex(SystemExit, rf"{field}.{key}"):
                            self.call_semantic_binding_validator(module, root, fixture)

    def test_semantic_noalias_contract_accepts_matching_proven_pair(self) -> None:
        module = load_validator_module()
        module.validate_semantic_noalias_contract(*self.semantic_noalias_fixture())

    def test_semantic_noalias_contract_rejects_not_applicable_current_bug(self) -> None:
        module = load_validator_module()
        spec, pointer_graph, auto_manifest, manifest, final = self.semantic_noalias_fixture()
        for gate in (
            pointer_graph["alias_contract"],
            auto_manifest["claim_boundary"]["alias_gate"],
            manifest["claim_boundary"]["alias_gate"],
            final["alias_gate"],
        ):
            gate["decision"] = "not_applicable"
            gate["requires_noalias"] = False
            gate["complete_alias_safety"] = False
        with self.assertRaisesRegex(SystemExit, "cannot be not_applicable"):
            module.validate_semantic_noalias_contract(
                spec, pointer_graph, auto_manifest, manifest, final
            )

    def test_semantic_noalias_contract_rejects_declared_pair_drift(self) -> None:
        module = load_validator_module()
        spec, pointer_graph, auto_manifest, manifest, final = self.semantic_noalias_fixture()
        pointer_graph["safe_boundary_preconditions"][0]["applies_to"] = ["db", "other"]
        with self.assertRaisesRegex(SystemExit, "does not match slice spec noalias_required"):
            module.validate_semantic_noalias_contract(
                spec, pointer_graph, auto_manifest, manifest, final
            )

    def test_semantic_noalias_contract_ignores_slice_without_declared_pairs(self) -> None:
        module = load_validator_module()
        module.validate_semantic_noalias_contract(
            {"c_boundary": {"pointer_contract": {"noalias_required": []}}},
            {},
            {},
            {},
            {},
        )
