class _ValidateAutoTranslationEvidenceTestsPart07:
    def carrier_fixture(
        self,
        root: Path,
        *,
        duplicate_fragment: bool = False,
        crlf_source: bool = False,
    ) -> tuple[Path, Path, str, dict[str, object]]:
        source_text = (
            "static uint32_t new_kv(uint32_t db, uint32_t sector, size_t kv_size)\n"
            "{\n"
            "    uint32_t empty_kv = FAILED_ADDR;\n"
            "    if ((empty_kv = alloc_kv(db, sector, kv_size)) == FAILED_ADDR) {\n"
            "        return FAILED_ADDR;\n"
            "    }\n"
            "    return empty_kv;\n"
            "}\n"
        )
        fragment_text = "    if ((empty_kv = alloc_kv(db, sector, kv_size)) == FAILED_ADDR) {\n"
        carrier_source = (
            "uint32_t alloc_kv(uint32_t db, uint32_t sector, size_t kv_size);\n"
            "static bool carrier_probe(uint32_t db, uint32_t sector, size_t kv_size)\n"
            "{\n"
            "    uint32_t empty_kv = FAILED_ADDR;\n"
            f"{fragment_text}"
            "        return true;\n"
            "    }\n"
            "    return false;\n"
            "}\n"
        )
        if duplicate_fragment:
            carrier_source += fragment_text

        source_path = root / "sources" / "upstream" / "src" / "db.c"
        source_path.parent.mkdir(parents=True)
        raw_source_text = source_text.replace("\n", "\r\n") if crlf_source else source_text
        source_path.write_bytes(raw_source_text.encode("utf-8"))
        source_bytes = source_path.read_bytes()
        source_lines = source_text.encode("utf-8").splitlines(keepends=True)
        function_bytes = b"".join(source_lines[0:8]).strip()
        fragment_bytes = source_lines[3]
        carrier = {
            "kind": "exact_source_fragment_wrapper",
            "carrier_function": "carrier_probe",
            "carrier_source_sha256": hashlib.sha256(carrier_source.encode("utf-8")).hexdigest(),
            "embedding_mode": "verbatim_once",
            "frontend_contract": "live_clang_slice_source",
            "source_text_normalization": "utf8_universal_newlines",
            "source_file_hash_mode": "raw_bytes",
            "artifact_source_hash_mode": "lf_stable_text",
            "real_source": {
                "file": "src/db.c",
                "containing_function": {
                    "name": "new_kv",
                    "line_start": 1,
                    "line_end": 8,
                    "sha256": hashlib.sha256(function_bytes).hexdigest(),
                    "hash_mode": "trimmed_normalized_span",
                    "declaration_text": "static uint32_t new_kv(",
                },
                "fragment": {
                    "kind": "if_condition_header",
                    "line_start": 4,
                    "line_end": 4,
                    "sha256": hashlib.sha256(fragment_bytes).hexdigest(),
                    "hash_mode": "normalized_line_span_with_newline",
                    "text": fragment_text,
                },
            },
            "claim_boundary": {
                "scope": "source_fragment_only",
                "whole_function_semantics_verified": False,
                "external_callee_semantics_verified": False,
                "excluded_semantics": ["real external callee behavior", "containing function control flow"],
            },
        }
        spec = {
            "target_id": "demo",
            "slice_id": "carrier",
            "source_commit": "abcdef1",
            "fixture_hash": "fixture-sha",
            "function_name": "carrier_probe",
            "c_source": carrier_source,
            "source_root": "sources/upstream",
            "source_file": "src/db.c",
            "source_file_hashes": {"src/db.c": hashlib.sha256(source_bytes).hexdigest()},
            "build_profile": {"clang_available": True},
            "translation_carrier": carrier,
        }
        spec_path = root / "slice-spec.json"
        spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        evidence_dir = root / "evidence"
        evidence_dir.mkdir()
        prefix = "l3-carrier"
        translator_input = dict(spec)
        artifact_source_hashes = {
            "src/db.c": hashlib.sha256(source_text.encode("utf-8")).hexdigest()
        }
        translator_input["source_file_hashes"] = artifact_source_hashes
        plan = {
            "target_id": spec["target_id"],
            "slice_id": spec["slice_id"],
            "source_commit": spec["source_commit"],
            "fixture_hash": spec["fixture_hash"],
            "status": "generated",
            "cache_invalidation_keys": [f"fixture_hash={spec['fixture_hash']}"],
            "translation_source": {"selected": "clang-lowered-typed-ir"},
            "translation_carrier": carrier,
        }
        lowering_report = {
            "target_id": spec["target_id"],
            "slice_id": spec["slice_id"],
            "source_commit": spec["source_commit"],
            "fixture_hash": spec["fixture_hash"],
            "status": "lowered",
            "function_name": "carrier_probe",
            "translation_carrier": carrier,
            "lowering_report": {"frontend": "clang_slice_source"},
            "metadata": {
                "clang_ast_fixture": None,
                "source_root": spec["source_root"],
                "logical_source_file": spec["source_file"],
                "source_file_hashes": artifact_source_hashes,
            },
            "typed_ir_candidate": {
                "status": "generated",
                "rust_draft_generated": True,
                "semantic_pass": False,
            },
        }
        for suffix, payload in [
            ("translator-input", translator_input),
            ("auto-translation-plan", plan),
            ("clang-lowering-report", lowering_report),
        ]:
            (evidence_dir / f"{prefix}-{suffix}.json").write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        return spec_path, evidence_dir, prefix, spec

    def test_translation_carrier_accepts_exact_real_source_binding(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            root = Path(tmp)
            spec_path, evidence_dir, prefix, _ = self.carrier_fixture(root)
            module.validate_translation_carrier_binding(
                evidence_dir, prefix, spec_path, repo_root=root
            )

    def test_translation_carrier_normalizes_crlf_source_before_span_hashing(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            root = Path(tmp)
            spec_path, evidence_dir, prefix, _ = self.carrier_fixture(
                root, crlf_source=True
            )
            module.validate_translation_carrier_binding(
                evidence_dir, prefix, spec_path, repo_root=root
            )

    def test_translation_carrier_rejects_real_source_fragment_hash_drift(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            root = Path(tmp)
            spec_path, evidence_dir, prefix, spec = self.carrier_fixture(root)
            spec["translation_carrier"]["real_source"]["fragment"]["sha256"] = "0" * 64
            spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "source fragment sha256 mismatch"):
                module.validate_translation_carrier_binding(
                    evidence_dir, prefix, spec_path, repo_root=root
                )

    def test_translation_carrier_rejects_duplicate_fragment_embedding(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            root = Path(tmp)
            spec_path, evidence_dir, prefix, _ = self.carrier_fixture(
                root, duplicate_fragment=True
            )
            with self.assertRaisesRegex(SystemExit, "embedded verbatim exactly once"):
                module.validate_translation_carrier_binding(
                    evidence_dir, prefix, spec_path, repo_root=root
                )

    def test_translation_carrier_rejects_plan_binding_drift(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            root = Path(tmp)
            spec_path, evidence_dir, prefix, _ = self.carrier_fixture(root)
            plan_path = evidence_dir / f"{prefix}-auto-translation-plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["translation_carrier"]["carrier_function"] = "other_probe"
            plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "binding drift in auto-translation plan"):
                module.validate_translation_carrier_binding(
                    evidence_dir, prefix, spec_path, repo_root=root
                )

    def test_translation_carrier_rejects_whole_function_semantic_overclaim(self) -> None:
        module = load_validator_module()
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            root = Path(tmp)
            spec_path, evidence_dir, prefix, spec = self.carrier_fixture(root)
            spec["translation_carrier"]["claim_boundary"][
                "whole_function_semantics_verified"
            ] = True
            spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "whole_function_semantics_verified=false"):
                module.validate_translation_carrier_binding(
                    evidence_dir, prefix, spec_path, repo_root=root
                )
