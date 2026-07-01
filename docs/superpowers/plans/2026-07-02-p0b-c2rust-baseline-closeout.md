英文镜像见 `2026-07-02-p0b-c2rust-baseline-closeout.en.md`。

# P0-B C2Rust Baseline Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 FlashDB `real-fdb-calc-crc32` 至少在一个真实 Linux/WSL/比赛等价环境中产出 C2Rust Rust output、output sha256 和 compile-only status，同时保持 `candidate_context_only` 边界。

**Architecture:** 不改 H7 harness 框架，不引入 LangGraph/Docker farm。P0-B 只加三类能力：blocked 工具链路径有可执行 repair playbook，真实 C2Rust live test 有 opt-in 入口，validator/reporting 拒绝把 compile-only baseline 伪装成 semantic pass。

**Tech Stack:** Python stdlib, `unittest`, `jsonschema`, existing `validation.tools.auto_migrate`, existing C2Rust baseline schemas, existing route-governance and judge-bundle tests, WSL/Linux toolchain with `clang`/`libclang`/`llvm`/`rustc`/`cargo`/C2Rust.

---

## 当前判断

`opencode-agent-harness-逐行稳定性审查.md` 对 timeout、原子写、`python3`、retry cap、SQLite lock、fencing/transaction 的判断有道理，但当前分支已把这些纳入 H7 并有测试合同。继续把它们列为 P0 会浪费剩余窗口。

P0-B4 已对 `real-fdb-calc-crc32` slice 闭合。FlashDB source 和 `compile_commands.json` 已存在，真实 WSL `c2rust-transpile 0.22.1` 可调用，且 C2Rust CLI 合同已固定：`--emit-build-files` 是布尔开关，prepared compilation database 必须以标准文件名 `compile_commands.json` 作为位置参数传入。`auto_migrate.py` 会把 normalized DB 写到 `<evidence>/<prefix>-c2rust-compile-commands/compile_commands.json`，生成 C2Rust crate 和 combined output，用 Cargo 编译 generated crate，把产出的 rlib 复制成稳定 evidence artifact，并保持 `compile.semantic_pass=false` / `correctness_role=candidate_context_only`。下一项 P0 是 P0-C：把这个 compile-only baseline 绑定到 C oracle、Rust replay、diff、negative diff 和 unsafe-ledger 证据后，才能接受任何 OpenCode/LLM 安全化 patch。

## File Structure

- Modify: `validation/tools/auto_migrate.py`
  - Add a small helper that builds `toolchain_repair` for missing/disabled C2Rust baseline generation.
  - Keep `status` as `skipped` or `blocked`; never promote repair hints to generated evidence.
  - For generated C2Rust crates, compile through the emitted `Cargo.toml` instead of concatenating crate files into one Rust source for bare `rustc`.
- Modify: `validation/auto-translation-template/c2rust-baseline-manifest.schema.json`
  - Add optional schema for `toolchain_repair`.
  - Keep generated status requirements and skipped/blocked `output=null` / `compile=null` rules unchanged.
- Modify: `validation/tools/test_auto_migrate.py`
  - Extend missing-tool test.
  - Add opt-in live C2Rust test gated by environment and real tool availability.
  - Add route integration test for generated C2Rust `output_ref`.
  - Add a generated-crate compile-only test proving Cargo is used when C2Rust emits `Cargo.toml`, and the rlib artifact is bound to the manifest.
- Modify: `validation/tools/test_validate_auto_translation_evidence.py`
  - Add validator negatives for compile candidate output drift, compile semantic spoofing, and artifact contradictions.
- Modify: `validation/tools/test_template_schema_contracts.py`
  - Add schema negatives for generated-without-compile, skipped/blocked-with-output/compile, and compile semantic spoofing.
- Modify: `validation/tools/test_route_governance_metrics_report.py`
  - Add report schema negative for `metrics.c2rust_baseline.compile_semantic_pass_count=1`.
- Modify: `validation/tools/test_judge_milestone_bundle.py`
  - Add judge bundle schema negative for raw C2Rust `compile_semantic_pass_count=1`.
- Update after real evidence: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/*`, route metrics, judge bundle/public packet.

### Task 1: Toolchain Repair Manifest

**Files:**
- Modify: `validation/tools/auto_migrate.py`
- Modify: `validation/tools/test_auto_migrate.py`
- Modify: `validation/auto-translation-template/c2rust-baseline-manifest.schema.json`

- [ ] **Step 1: Write the failing test**

Add this assertion block inside `AutoMigrateTests.test_c2rust_baseline_manifest_records_tool_probe_without_generation_claim` after `tool_probe` assertions:

```python
repair = manifest["toolchain_repair"]
self.assertEqual(repair["status"], "required")
self.assertEqual(repair["reason"], "blocked_by_missing_tools")
self.assertEqual(repair["required_commands"], ["c2rust-transpile", "c2rust"])
self.assertEqual(repair["rerun_env"]["C2RUST_BASELINE_GENERATION"], "1")
self.assertEqual(
    repair["rerun_command"][:5],
    ["python3", "-B", "-m", "validation.tools.auto_migrate", "--slice-spec"],
)
self.assertIn("validation/slice-specs/", repair["rerun_command"][5])
self.assertEqual(repair["correctness_role"], "candidate_context_only")
self.assertFalse(any(str(item).startswith(("C:\\", "F:\\", "/mnt/")) for item in repair["rerun_command"]))
```

Run:

```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_c2rust_baseline_manifest_records_tool_probe_without_generation_claim -q
```

Expected: FAIL because `toolchain_repair` is missing.

- [ ] **Step 2: Implement the minimal helper**

Add a helper near `c2rust_command_candidates()`:

```python
def c2rust_toolchain_repair(reason: str, *, slice_spec: Path) -> dict[str, Any]:
    return {
        "status": "required",
        "reason": reason,
        "required_commands": ["c2rust-transpile", "c2rust"],
        "required_dependencies": ["rustc", "cargo", "clang", "libclang"],
        "competition_environment": {
            "profile": "config/competition-env/environment.json",
            "proof_class": "local_or_wsl_until_competition_run",
        },
        "rerun_env": {"C2RUST_BASELINE_GENERATION": "1"},
        "rerun_command": [
            "python3",
            "-B",
            "-m",
            "validation.tools.auto_migrate",
            "--slice-spec",
            rel(slice_spec),
            "--out-root",
            "validation/evidence",
        ],
        "correctness_role": "candidate_context_only",
        "must_not_claim": [
            "toolchain repair proves C2Rust generated output",
            "compile-only C2Rust output proves semantic equivalence",
        ],
    }
```

Then include `"toolchain_repair": c2rust_toolchain_repair(reason, slice_spec=slice_spec)` when `selected is None`, `generation_enabled` is false, or `compile_commands is None`. For generated status, write `"toolchain_repair": None`.

- [ ] **Step 3: Update schema**

Add an optional top-level property:

```json
"toolchain_repair": {
  "anyOf": [
    {"type": "null"},
    {
      "type": "object",
      "required": ["status", "reason", "required_commands", "rerun_env", "rerun_command", "correctness_role"],
      "properties": {
        "status": {"const": "required"},
        "reason": {"type": "string", "minLength": 1},
        "required_commands": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
        "required_dependencies": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "competition_environment": {"type": "object"},
        "rerun_env": {"type": "object"},
        "rerun_command": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
        "correctness_role": {"const": "candidate_context_only"},
        "must_not_claim": {"type": "array", "items": {"type": "string", "minLength": 1}}
      }
    }
  ]
}
```

Run:

```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_c2rust_baseline_manifest_records_tool_probe_without_generation_claim -q
```

Expected: OK.

### Task 2: Opt-In Live C2Rust Integration Target

**Files:**
- Modify: `validation/tools/test_auto_migrate.py`

- [ ] **Step 1: Add the live test**

Add this test near the existing mock generated test:

```python
def test_live_c2rust_baseline_generates_flashdb_crc32_when_enabled(self) -> None:
    auto_migrate = load_auto_migrate_module()
    c2rust = auto_migrate.shutil.which("c2rust-transpile") or auto_migrate.shutil.which("c2rust")
    rustc = auto_migrate.shutil.which("rustc")
    if os.environ.get("C2RUST_BASELINE_LIVE_TEST") != "1" or not c2rust or not rustc:
        self.skipTest("requires C2RUST_BASELINE_LIVE_TEST=1 plus real c2rust/c2rust-transpile and rustc")

    slice_spec = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"
    spec = json.loads(slice_spec.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="c2rust-live-") as tmp:
        evidence_dir = Path(tmp) / "flashdb" / "auto-translation" / "real-fdb-calc-crc32"
        evidence_dir.mkdir(parents=True)
        with mock.patch.dict(os.environ, {"C2RUST_BASELINE_GENERATION": "1"}):
            manifest = auto_migrate.emit_c2rust_baseline_manifest(spec, slice_spec, evidence_dir)

    self.assertEqual(manifest["status"], "generated")
    self.assertEqual(manifest["output"]["status"], "generated")
    self.assertEqual(manifest["compile"]["status"], "passed")
    self.assertFalse(manifest["compile"]["semantic_pass"])
    self.assertEqual(manifest["correctness_role"], "candidate_context_only")
```

Run without tools:

```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_live_c2rust_baseline_generates_flashdb_crc32_when_enabled -q
```

Expected: SKIPPED unless the opt-in environment and tools are present.

- [ ] **Step 2: Run the live target when C2Rust exists**

On Linux/WSL after exposing C2Rust on PATH:

```bash
cd /mnt/f/agent/crustpaper/0630
C2RUST_BASELINE_LIVE_TEST=1 C2RUST_BASELINE_GENERATION=1 \
python3 -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_live_c2rust_baseline_generates_flashdb_crc32_when_enabled -q
```

Expected: OK with generated output and compile-only passed. If it fails, capture the failing command, stdout/stderr log paths, and toolchain version in `toolchain_repair`; do not commit handwritten generated output.

### Task 3: Route and Validator Anti-Spoof Coverage

**Files:**
- Modify: `validation/tools/test_auto_migrate.py`
- Modify: `validation/tools/test_validate_auto_translation_evidence.py`

- [ ] **Step 1: Route integration test**

Add a test that passes a generated C2Rust baseline with a real output ref into `emit_route_decision()`:

```python
def test_emit_route_decision_carries_generated_c2rust_output_ref(self) -> None:
    auto_migrate = load_auto_migrate_module()
    with tempfile.TemporaryDirectory(prefix="auto-migrate-route-") as tmp:
        evidence_dir = Path(tmp)
        output = evidence_dir / "c2rust-output.rs"
        output.write_text("pub unsafe fn generated() {}\n", encoding="utf-8")
        spec = {"target_id": "demo", "slice_id": "route-c2rust", "source_commit": "1234567"}
        baseline = {
            "status": "generated",
            "reason": "generated_by_c2rust",
            "correctness_role": "candidate_context_only",
            "output": {"path": output.as_posix(), "status": "generated", "sha256": auto_migrate.sha256(output)},
            "compile": {"status": "passed", "attempted": True, "semantic_pass": False},
        }
        route = auto_migrate.emit_route_decision(spec, evidence_dir, {"status": "candidate_generated"}, baseline)

    c2rust_candidate = route["candidate_generation"]["c2rust_baseline"]
    self.assertEqual(c2rust_candidate["status"], "generated")
    self.assertEqual(c2rust_candidate["output_ref"]["sha256"], auto_migrate.sha256(output))
    self.assertFalse(c2rust_candidate["semantic_pass"])
    self.assertFalse(c2rust_candidate["generated_draft_semantic_pass"])
```

Run:

```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_emit_route_decision_carries_generated_c2rust_output_ref -q
```

Expected: OK after any small fixture adjustments required by `emit_route_decision`.

- [ ] **Step 2: Validator negatives**

Add focused tests to `ValidateAutoTranslationEvidenceTests` using the existing baseline fixture style:

```python
def test_rejects_c2rust_compile_candidate_output_drift(self) -> None:
    # Build a generated baseline whose compile.candidate_output sha differs from output.sha256.
    # validate_c2rust_baseline_compile_status must raise:
    # "c2rust_baseline compile candidate_output drift"
```

```python
def test_rejects_c2rust_compile_semantic_pass_spoof(self) -> None:
    # Set compile.semantic_pass = True on a generated baseline.
    # Expected failure: "c2rust_baseline compile status cannot claim semantic_pass"
```

```python
def test_rejects_c2rust_compile_artifact_contradictions(self) -> None:
    # Case A: compile.status = "failed" with non-null artifact.
    # Case B: compile.status = "passed" with artifact path missing or sha drift.
    # Expected failures must come from validate_c2rust_baseline_compile_status.
```

Run:

```powershell
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests -q
```

Expected: OK, with each negative failing for the intended reason before the fixture is corrected.

### Task 4: Schema and Reporting Guardrails

**Files:**
- Modify: `validation/tools/test_template_schema_contracts.py`
- Modify: `validation/tools/test_route_governance_metrics_report.py`
- Modify: `validation/tools/test_judge_milestone_bundle.py`

- [ ] **Step 1: Baseline manifest schema negatives**

Add one test that loads `c2rust-baseline-manifest.schema.json` and asserts `jsonschema.ValidationError` for:

```python
generated_without_compile = {"schema_version": 1, "status": "generated", "output": {"status": "generated"}}
skipped_with_output = {"schema_version": 1, "status": "skipped", "output": {"status": "generated"}, "compile": None}
blocked_with_compile = {"schema_version": 1, "status": "blocked", "output": None, "compile": {"semantic_pass": False}}
compile_semantic_spoof = {
    "schema_version": 1,
    "status": "generated",
    "output": {"status": "generated"},
    "generation": {"compile_commands": {"path": "compile_commands.json"}, "command": {"exit_status": "passed"}, "generated_files": [{"path": "out.rs", "sha256": "x"}]},
    "compile": {"semantic_pass": True},
}
```

Run:

```powershell
python -B -m unittest validation.tools.test_template_schema_contracts.TemplateSchemaContractTests -q
```

Expected: OK after schemas reject these shapes.

- [ ] **Step 2: Reporting semantic spoof negatives**

For route governance metrics, mutate a valid report:

```python
report["metrics"]["c2rust_baseline"]["compile_semantic_pass_count"] = 1
with self.assertRaises(jsonschema.ValidationError):
    jsonschema.validate(report, schema)
```

For judge milestone bundle, mutate:

```python
raw = report["quantitative_evaluation"]["baseline_comparison"]["raw_c2rust"]["c2rust_baseline_rollup"]
raw["compile_semantic_pass_count"] = 1
with self.assertRaises(jsonschema.ValidationError):
    jsonschema.validate(report, schema)
```

Run:

```powershell
python -B -m unittest validation.tools.test_route_governance_metrics_report.RouteGovernanceMetricsReportTests -q
python -B -m unittest validation.tools.test_judge_milestone_bundle.JudgeMilestoneBundleTests -q
```

Expected: OK, and both schemas pin C2Rust compile-only semantic pass count to zero.

### Task 5: Real Evidence Run and Publication Refresh

**Files:**
- Update after successful run: `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-c2rust-baseline-manifest.json`
- Update generated outputs under the same evidence directory only if produced by real C2Rust.
- Refresh route metrics and judge packet artifacts under `target/` first, then commit only intended durable evidence.

- [x] **Step 1: Build or expose real C2Rust**

Preferred WSL commands:

```bash
command -v clang
command -v rustc
command -v cargo
command -v c2rust-transpile || command -v c2rust
```

If C2Rust is not available, try the reference checkout only as a toolchain build source:

```bash
cd /mnt/f/agent/c2rust-master
cargo build --release
```

Expected: a runnable `c2rust` or `c2rust-transpile`. Current WSL evidence has a runnable `c2rust-transpile 0.22.1` through `/mnt/f/agent/c2rust-master/target/release`. If build fails in another environment, record failure logs as toolchain repair diagnostics; do not mark baseline generated.

- [x] **Step 2: Fix and verify C2Rust compilation database handoff**

The C2Rust command must be shaped as:

```bash
c2rust-transpile --emit-build-files --output-dir <output-dir> <path/to/compile_commands.json>
```

Acceptance:

```python
prepared = evidence_dir / f"{prefix}-c2rust-compile-commands" / "compile_commands.json"
assert prepared.name == "compile_commands.json"
assert argv[-1] == str(prepared)
```

Verified focused tests:

```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_c2rust_command_candidates_accepts_explicit_command_override validation.tools.test_auto_migrate.AutoMigrateTests.test_prepare_c2rust_compile_commands_normalizes_makefile_relative_entry validation.tools.test_auto_migrate.AutoMigrateTests.test_c2rust_baseline_manifest_generates_output_when_explicitly_enabled -q
```

Current result: real WSL `auto_migrate` now reaches `status=generated` / `reason=generated_by_c2rust` and writes C2Rust-generated files under `l3-real-fdb-calc-crc32-c2rust-baseline-generated/`.

- [x] **Step 3: Replace bare-rustc compile-only with generated-crate Cargo compile**

Write a red test near `test_c2rust_baseline_manifest_generates_output_when_explicitly_enabled`:

```python
def test_c2rust_baseline_manifest_compiles_generated_crate_with_cargo(self) -> None:
    auto_migrate = load_auto_migrate_module()
    with tempfile.TemporaryDirectory(prefix="auto-migrate-c2rust-crate-") as tmp:
        evidence_dir = Path(tmp)
        output_dir = evidence_dir / "l3-c2rust-generated-c2rust-baseline-generated"

        # Fake C2Rust writes Cargo.toml, lib.rs, and src/fdb_utils.rs.
        # The fake runner must fail if compile uses bare rustc against the combined output,
        # and pass only when argv invokes cargo build/check from the generated crate root.
```

Minimal implementation:

- `run_c2rust_baseline_generation()` should record generated crate metadata when `output_dir / "Cargo.toml"` exists, for example `output.crate_root` and `output.cargo_toml`.
- `compile_c2rust_baseline_output()` should accept an optional `crate_root`.
- If `crate_root/Cargo.toml` exists and `cargo` is available, run Cargo from the generated crate root instead of bare `rustc` on the combined file.
- Use an explicit compile-only adapter, for example env overrides `RUSTUP_TOOLCHAIN=stable` and `RUSTC_BOOTSTRAP=1`, because C2Rust emits old nightly feature attributes and a `rust-toolchain.toml` pinned to an old toolchain.
- On success, copy the generated `target/debug/*.rlib` to a stable `*-c2rust-baseline-output.rlib` evidence artifact with repo-relative path and sha256; keep `compile.semantic_pass=false`.
- If Cargo is unavailable or fails, keep `compile.status=failed` with stdout/stderr logs and diagnostics; do not convert compile failure into semantic failure or success.

结果：已在 `validation/tools/auto_migrate.py` 实现 `compile_strategy=cargo_generated_crate`、`env_overrides={"RUSTUP_TOOLCHAIN":"stable","RUSTC_BOOTSTRAP":"1"}`、稳定 rlib evidence 绑定，并在 `validation/tools/test_auto_migrate.py` 用 focused 红绿测试固定。

- [x] **Step 4: Run the real FlashDB baseline**

```bash
cd /mnt/f/agent/crustpaper/0630
export PATH="/mnt/f/agent/c2rust-master/target/release:$PATH"
export C2RUST_BASELINE_GENERATION=1
python3 -B -m validation.tools.auto_migrate \
  --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json \
  --out-root validation/evidence \
  --accept-existing-evidence
```

Expected successful evidence:

```json
{
  "status": "generated",
  "correctness_role": "candidate_context_only",
  "output": {"status": "generated"},
  "compile": {"status": "passed", "semantic_pass": false}
}
```

If status remains `blocked` or `skipped`, keep that evidence honest and make sure `toolchain_repair` names the next concrete action.

结果：WSL run 产出 `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-c2rust-baseline-manifest.json`，其中 `status=generated`、`reason=generated_by_c2rust`、`correctness_role=candidate_context_only`、`compile.status=passed`、`compile.command.compile_strategy=cargo_generated_crate`、artifact 为 `l3-real-fdb-calc-crc32-c2rust-baseline-output.rlib`，且 `compile.semantic_pass=false`。

- [x] **Step 5: Verify after evidence refresh**

Run:

```powershell
python -B -m unittest validation.tools.test_auto_migrate -q
python -B -m unittest validation.tools.test_validate_auto_translation_evidence -q
python -B -m unittest validation.tools.test_template_schema_contracts -q
python -B -m unittest validation.tools.test_route_governance_metrics_report -q
python -B -m unittest validation.tools.test_judge_milestone_bundle -q
python -B -m validation.tools.validate_auto_translation_evidence --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --evidence-root validation/evidence --require-semantic-pass
python -B -m unittest validation.tools.test_doc_mirror_contract -q
```

Expected: all selected tests and validators pass. The final validator semantic pass still comes from accepted evidence or downstream semantic gates, not from C2Rust compile-only output.

本轮实际结果：

- `python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_c2rust_baseline_manifest_generates_output_when_explicitly_enabled -q` 已通过。
- WSL `C2RUST_BASELINE_GENERATION=1 python3 -B -m validation.tools.auto_migrate ... --accept-existing-evidence` 已通过并刷新 evidence。
- `python -B -m validation.tools.validate_auto_translation_evidence --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --evidence-root validation/evidence --require-semantic-pass` 已通过；semantic pass 来源仍是 `accepted_evidence_binding`，不是 C2Rust compile-only draft。
