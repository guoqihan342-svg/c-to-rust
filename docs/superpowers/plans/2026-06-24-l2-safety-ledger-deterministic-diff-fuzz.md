# L2 Safety Ledger And Deterministic Diff Fuzz Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create OpenSpec change `add-l2-safety-ledger-and-deterministic-diff-fuzz` to harden existing L2 slice evidence with a machine-readable unsafe ledger, deterministic C/Rust differential corpus expansion, and L2 negative-diff proof.

**Architecture:** Keep the project small and local-first. Do not add `cargo-fuzz`, `proptest`, `quickcheck`, or AI-dependent verification in this change; expand the existing C oracle fixture generator and Rust evidence emitter so all evidence remains reproducible, fast, and checked by OpenSpec gates.

**Tech Stack:** Rust 2021, `serde_json`, existing L2 crate `validation/l2_slices`, Python 3 oracle generator, WSL/Linux C toolchain for oracle regeneration, OpenSpec 1.3.1, PowerShell verification commands.

---

## Scope

This plan implements only the immediate L2 hardening slice:

- L2 unsafe ledger evidence, even when unsafe count is zero.
- Deterministic fuzz-like C oracle corpus for `zlib-adler32`.
- L2 negative diff report proving the diff gate catches a mutated oracle value.
- OpenSpec and gate documentation updates.

This plan intentionally does not implement:

- Full `cargo-fuzz` or property-test dependency.
- Pointer dependency graph or pointer KG.
- Hayroll-level macro and conditional-compilation translation.
- L3 template productization.

Those are next changes after this L2 evidence hardening lands.

## Parallel Execution Model

Use bounded parallel workers with disjoint write sets:

- Worker A: OpenSpec artifacts and `validation/gates.md`.
- Worker B: `validation/l2_slices/tools/generate_oracles.py` corpus expansion.
- Worker C: `validation/l2_slices/src/bin/emit_reports.rs` ledger and negative diff.
- Worker D: read-only verification review after integration.

Only one worker should edit `emit_reports.rs`. Only one worker should edit `generate_oracles.py`.

## File Map

- Create: `openspec/changes/add-l2-safety-ledger-and-deterministic-diff-fuzz/proposal.md`
- Create: `openspec/changes/add-l2-safety-ledger-and-deterministic-diff-fuzz/design.md`
- Create: `openspec/changes/add-l2-safety-ledger-and-deterministic-diff-fuzz/tasks.md`
- Create: `openspec/changes/add-l2-safety-ledger-and-deterministic-diff-fuzz/specs/supercomplex-l2-slice-validation/spec.md`
- Modify: `validation/gates.md`
- Modify: `validation/l2_slices/tools/generate_oracles.py`
- Modify: `validation/l2_slices/src/bin/emit_reports.rs`
- Regenerate: `validation/l2_slices/fixtures/zlib-adler32-c-oracle.json`
- Regenerate: `validation/evidence/l2-slices/zlib-adler32-oracle.json`
- Regenerate: `validation/evidence/l2-slices/c-oracle-summary.json`
- Regenerate: `validation/evidence/l2-slices/zlib-adler32-rust-report.json`
- Regenerate: `validation/evidence/l2-slices/zlib-adler32-diff.json`
- Create: `validation/evidence/l2-slices/zlib-adler32-negative-diff.json`
- Regenerate: `validation/evidence/l2-slices/unsafe-scan.json`
- Create: `validation/evidence/l2-slices/unsafe-ledger.json`
- Regenerate: `validation/evidence/l2-slices/l2-l3-summary.json`

---

### Task 1: Preflight And Baseline Checks

**Files:**
- Read: `validation/l2_slices/src/bin/emit_reports.rs`
- Read: `validation/l2_slices/tools/generate_oracles.py`
- Read: `validation/gates.md`

- [ ] **Step 1: Confirm worktree state**

Run:

```powershell
git status --short --untracked-files=all
git branch --show-current
```

Expected:

```text
codex/flashdb-rust-skeleton
```

If there are unrelated user changes, leave them untouched and continue only if this plan's files are safe to edit.

- [ ] **Step 2: Record current L2 test baseline**

Run:

```powershell
Push-Location validation\l2_slices
cargo test
Pop-Location
```

Expected:

```text
test result: ok
```

- [ ] **Step 3: Record current report baseline**

Run:

```powershell
Push-Location validation\l2_slices
cargo run --bin emit_reports
Pop-Location
Get-Content validation\evidence\l2-slices\l2-l3-summary.json | Select-String '"status"'
```

Expected:

```text
"status": "passed"
```

- [ ] **Step 4: Confirm current gap**

Run:

```powershell
Test-Path validation\evidence\l2-slices\unsafe-ledger.json
Test-Path validation\evidence\l2-slices\zlib-adler32-negative-diff.json
```

Expected before implementation:

```text
False
False
```

---

### Task 2: Create OpenSpec Change

**Files:**
- Create: `openspec/changes/add-l2-safety-ledger-and-deterministic-diff-fuzz/proposal.md`
- Create: `openspec/changes/add-l2-safety-ledger-and-deterministic-diff-fuzz/design.md`
- Create: `openspec/changes/add-l2-safety-ledger-and-deterministic-diff-fuzz/tasks.md`
- Create: `openspec/changes/add-l2-safety-ledger-and-deterministic-diff-fuzz/specs/supercomplex-l2-slice-validation/spec.md`

- [ ] **Step 1: Create directories**

Run:

```powershell
New-Item -ItemType Directory -Force openspec\changes\add-l2-safety-ledger-and-deterministic-diff-fuzz\specs\supercomplex-l2-slice-validation | Out-Null
```

Expected: command exits with code 0.

- [ ] **Step 2: Write proposal**

Create `openspec/changes/add-l2-safety-ledger-and-deterministic-diff-fuzz/proposal.md`:

```markdown
# Proposal: Harden L2 Safety And Differential Evidence

## Purpose

当前 L2 slices 已有 C oracle、Rust report、schema-aware diff 和 unsafe scan，但证据还没有形成完整的 unsafe ledger，也没有证明 L2 diff 能捕获故意错误的 negative diff。`zlib-adler32` 现有 fixture 数量较少，适合作为第一个小而精的 deterministic differential corpus 扩展点。

## Proposed Changes

- 为 `validation/l2_slices` 生成 `unsafe-ledger.json`，即使 first-party non-test unsafe 数量为 0 也必须产出账本证据。
- 扩展 `zlib-adler32` C oracle fixture，使用固定 seed 的 deterministic byte corpus 覆盖 Adler32 长度边界、NMAX 周边和随机形态输入。
- 生成 `zlib-adler32-negative-diff.json`，通过故意篡改一个 C oracle value 证明 L2 diff gate 能捕获 mismatch。
- 更新 L2 summary 和 `validation/gates.md`，让新的证据成为 L2 pass 的一部分。

## Non-Goals

- 不引入 `cargo-fuzz`、`proptest`、`quickcheck` 或新 Rust 依赖。
- 不实现 pointer dependency graph。
- 不实现完整 C macro/条件编译翻译。
- 不产品化 L3 模板；该工作留给后续 change。

## Risks

- C oracle regeneration 依赖 WSL/Linux C toolchain 和已有 zlib-ng build artifact。
- 过大的 corpus 会拖慢本地验证，因此本 change 使用固定上限的 deterministic corpus。
```

- [ ] **Step 3: Write design**

Create `openspec/changes/add-l2-safety-ledger-and-deterministic-diff-fuzz/design.md`:

```markdown
# Design: L2 Safety Ledger And Deterministic Diff Fuzz

## Purpose

本 change 把已有 L2 证据从“固定 fixture 对比”升级为“有账本的安全证据 + 可重复的 deterministic differential corpus + negative diff 自检”。设计保持本地优先、少依赖、速度快，并避免把 research-grade fuzz 或符号执行提前引入当前小切片。

## Approach

`validation/l2_slices/tools/generate_oracles.py` 继续作为 C oracle fixture 入口。`zlib-adler32` 的输入从 7 个手写向量扩展为边界长度和固定 seed LCG byte buffers 的组合。生成出的 JSON fixture 仍由现有 Rust tests 和 `emit_reports` 消费。

`validation/l2_slices/src/bin/emit_reports.rs` 继续负责 Rust report、diff 和 summary。它新增 `unsafe-ledger.json`，并为 `zlib-adler32` 生成 negative diff evidence。Negative diff 的语义是：故意把第一个 C oracle value 变更为 `value ^ 1`，diff 必须检测出 mismatch；检测到 mismatch 时 negative diff report 的 `status` 为 `passed`。

## Evidence Format

`unsafe-ledger.json` includes:

- `schema_version`
- `crate`
- `scope`
- `policy`
- `first_party_non_test_unsafe_count`
- `registered_unsafe`
- `introduced_unsafe`
- `audit_status`
- `scan_report`
- `audited_modules`

`zlib-adler32-negative-diff.json` includes:

- `schema_version`
- `level`
- `slice_id`
- `status`
- `mutation`
- `case_id`
- `detected`
- `first_mismatch`

## Validation

Required commands:

```powershell
Push-Location validation\l2_slices
cargo fmt -- --check
cargo test
cargo run --bin emit_reports
Pop-Location
openspec validate add-l2-safety-ledger-and-deterministic-diff-fuzz --strict
openspec validate --all
git diff --check
```
```

- [ ] **Step 4: Write tasks**

Create `openspec/changes/add-l2-safety-ledger-and-deterministic-diff-fuzz/tasks.md`:

```markdown
# Tasks

- [ ] 1. Add OpenSpec requirements for L2 unsafe ledger, deterministic corpus, and negative diff evidence.
- [ ] 2. Update `validation/gates.md` so L2 pass criteria require unsafe ledger and negative diff evidence.
- [ ] 3. Expand `zlib-adler32` C oracle fixture generation with fixed-seed deterministic byte buffers.
- [ ] 4. Regenerate `zlib-adler32-c-oracle.json`, `zlib-adler32-oracle.json`, and `c-oracle-summary.json`.
- [ ] 5. Update `emit_reports.rs` to produce `unsafe-ledger.json`.
- [ ] 6. Update `emit_reports.rs` to produce `zlib-adler32-negative-diff.json`.
- [ ] 7. Update L2 summary to reference unsafe ledger and negative diff status.
- [ ] 8. Run L2 Rust formatting, tests, and report generation.
- [ ] 9. Run OpenSpec validation and whitespace validation.
```

- [ ] **Step 5: Write spec delta**

Create `openspec/changes/add-l2-safety-ledger-and-deterministic-diff-fuzz/specs/supercomplex-l2-slice-validation/spec.md`:

```markdown
## ADDED Requirements

### Requirement: L2 unsafe ledger evidence

The system SHALL emit a machine-readable unsafe ledger for the L2 slice crate whenever L2 slice evidence is generated.

系统在生成 L2 slice 证据时，必须同时生成机器可读的 unsafe ledger。

#### Scenario: Safe L2 crate still produces a ledger

- **WHEN** `validation/l2_slices` contains zero first-party non-test unsafe usages
- **THEN** the L2 evidence directory contains `unsafe-ledger.json`
- **AND** the ledger records `first_party_non_test_unsafe_count` as `0`
- **AND** the ledger records `audit_status` as `passed`

### Requirement: Deterministic differential corpus for L2 pure functions

The system SHALL use bounded deterministic input corpora for L2 pure-function differential evidence when full fuzzing is not installed.

当未安装完整 fuzz 工具链时，系统必须为 L2 纯函数差分证据使用有界、可重复的 deterministic input corpus。

#### Scenario: Adler32 corpus is reproducible

- **WHEN** the `zlib-adler32` C oracle fixture is regenerated
- **THEN** the fixture includes fixed boundary lengths and fixed-seed generated byte buffers
- **AND** the oracle summary records the expanded deterministic case count
- **AND** repeated generation from the same source commit and generator produces the same fixture bytes

### Requirement: L2 negative diff self-check

The system SHALL emit negative diff evidence for at least one L2 slice to prove the L2 diff gate detects an intentional oracle mismatch.

系统必须至少为一个 L2 slice 生成 negative diff 证据，以证明 L2 diff 门禁能捕获故意制造的 oracle mismatch。

#### Scenario: Mutated Adler32 oracle value is rejected

- **WHEN** the `zlib-adler32` negative diff mutates one oracle `value`
- **THEN** the diff detects the mismatch
- **AND** `zlib-adler32-negative-diff.json` records `status` as `passed`
- **AND** the L2 summary references the negative diff result
```

- [ ] **Step 6: Validate new OpenSpec change before code edits**

Run:

```powershell
openspec validate add-l2-safety-ledger-and-deterministic-diff-fuzz --strict
```

Expected:

```text
Change 'add-l2-safety-ledger-and-deterministic-diff-fuzz' is valid
```

---

### Task 3: Update L2 Gate Documentation

**Files:**
- Modify: `validation/gates.md`

- [ ] **Step 1: Locate L2 criteria**

Run:

```powershell
rg -n "L2|unsafe|ledger|negative" validation\gates.md
```

Expected: output includes the L2 pass criteria section around the existing unsafe accounting language.

- [ ] **Step 2: Update L2 evidence wording**

Modify the L2 evidence section so it includes these exact bullets:

```markdown
- C oracle fixture and Rust replay report for each slice.
- Schema-aware diff report for each slice.
- Unsafe scan plus unsafe ledger, even when first-party unsafe count is zero.
- At least one L2 negative diff report proving the diff gate catches an intentional mismatch.
- Patch log and reporting boundary for the named slice only.
```

- [ ] **Step 3: Validate documentation formatting**

Run:

```powershell
git diff -- validation/gates.md
```

Expected: only the L2 evidence wording changes; L0/L1/L3 sections remain unchanged.

---

### Task 4: Expand Zlib Adler32 Deterministic Corpus

**Files:**
- Modify: `validation/l2_slices/tools/generate_oracles.py`
- Regenerate: `validation/l2_slices/fixtures/zlib-adler32-c-oracle.json`
- Regenerate: `validation/evidence/l2-slices/zlib-adler32-oracle.json`
- Regenerate: `validation/evidence/l2-slices/c-oracle-summary.json`

- [ ] **Step 1: Add seeded deterministic byte generator**

In `validation/l2_slices/tools/generate_oracles.py`, add this helper after `make_pattern`:

```python
def make_lcg_pattern(seed: int, length: int) -> bytes:
    value = seed & 0xFFFFFFFF
    out = []
    for _ in range(length):
        value = (1103515245 * value + 12345) & 0xFFFFFFFF
        out.append((value >> 16) & 0xFF)
    return bytes(out)
```

- [ ] **Step 2: Replace zlib vector construction**

In `generate_zlib`, replace the current `vectors = [...]` block with:

```python
    vectors = [
        ("empty", "empty", 0),
        ("ascii", "ascii", 21),
        ("inc_256", "inc", 256),
        ("nmax_5552", "inc", 5552),
        ("nmax_plus_1", "inc", 5553),
        ("lcg_32768", "lcg", 32768),
        ("ff_128", "ff", 128),
    ]
    deterministic_lengths = [
        0, 1, 2, 3, 4, 15, 16, 31, 32, 63, 64, 127, 128,
        255, 256, 511, 512, 1023, 1024, 2047, 2048,
        5551, 5552, 5553, 8191, 8192,
    ]
    deterministic_seeds = [
        0x00000001,
        0x12345678,
        0x5A5A5A5A,
        0xC0FFEE00,
        0xFFFFFFFF,
    ]
    for seed in deterministic_seeds:
        for length in deterministic_lengths:
            vectors.append((f"lcg_{seed:08x}_{length}", "lcg_seeded", length, seed))
```

- [ ] **Step 3: Update static row generation**

In `generate_zlib`, replace:

```python
    static_rows = []
    for case_id, kind, length in vectors:
        data = make_pattern(kind, length)
        static_rows.append((case_id, hex_bytes(data)))
```

with:

```python
    static_rows = []
    for vector in vectors:
        if len(vector) == 3:
            case_id, kind, length = vector
            data = make_pattern(kind, length)
        else:
            case_id, kind, length, seed = vector
            if kind != "lcg_seeded":
                raise ValueError(kind)
            data = make_lcg_pattern(seed, length)
        static_rows.append((case_id, hex_bytes(data)))
```

- [ ] **Step 4: Regenerate C oracle fixtures**

Run in WSL/Linux where the existing zlib-ng build paths are available:

```powershell
wsl python3 /mnt/c/Users/Administrator/Documents/c-to-rust-flashdb/validation/l2_slices/tools/generate_oracles.py
```

Expected output includes:

```json
"status": "passed"
```

Expected `zlib-adler32` case count is `137` because `7 + (5 * 26) = 137`.

- [ ] **Step 5: Verify regenerated fixture count**

Run:

```powershell
$cases = Get-Content validation\l2_slices\fixtures\zlib-adler32-c-oracle.json -Raw | ConvertFrom-Json
$cases.Count
```

Expected:

```text
137
```

---

### Task 5: Add Unsafe Ledger Report

**Files:**
- Modify: `validation/l2_slices/src/bin/emit_reports.rs`
- Create: `validation/evidence/l2-slices/unsafe-ledger.json`
- Regenerate: `validation/evidence/l2-slices/l2-l3-summary.json`

- [ ] **Step 1: Add safety evidence struct**

In `validation/l2_slices/src/bin/emit_reports.rs`, add this after `struct SliceResult`:

```rust
#[derive(Debug)]
struct SafetyEvidence {
    scan: Value,
    ledger: Value,
}
```

- [ ] **Step 2: Update main report flow**

Replace:

```rust
    let scan = emit_safety_scan(&crate_dir, &evidence_dir)?;
    emit_summary(&evidence_dir, &slices, &scan)?;
```

with:

```rust
    let safety = emit_safety_evidence(&crate_dir, &evidence_dir)?;
    let negative_diffs = emit_negative_diffs(&fixtures_dir, &evidence_dir)?;
    emit_summary(&evidence_dir, &slices, &safety, &negative_diffs)?;
```

- [ ] **Step 3: Rename and extend safety scan**

Replace `fn emit_safety_scan(...) -> Result<Value, Box<dyn Error>>` with:

```rust
fn emit_safety_evidence(
    crate_dir: &Path,
    evidence_dir: &Path,
) -> Result<SafetyEvidence, Box<dyn Error>> {
    let src_dir = crate_dir.join("src");
    let mut hits = Vec::new();
    scan_rust_files(&src_dir, &mut |path, line_no, line| {
        if line
            .split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
            .any(|token| token == "unsafe")
        {
            hits.push(json!({
                "path": relative_path(path),
                "line": line_no,
                "text": line.trim()
            }));
        }
    })?;
    let status = if hits.is_empty() { "passed" } else { "failed" };
    let scan = json!({
        "schema_version": 1,
        "crate": "validation/l2_slices",
        "scope": "first-party Rust source under validation/l2_slices/src",
        "unsafe_count": hits.len(),
        "status": status,
        "hits": hits
    });
    write_json(&evidence_dir.join("unsafe-scan.json"), &scan)?;

    let ledger = json!({
        "schema_version": 1,
        "crate": "validation/l2_slices",
        "scope": "first-party non-test Rust source under validation/l2_slices/src",
        "policy": {
            "first_party_non_test_unsafe_limit": 0,
            "registered_unsafe_required": true,
            "audit_required_even_when_zero": true
        },
        "first_party_non_test_unsafe_count": scan["unsafe_count"],
        "registered_unsafe": [],
        "introduced_unsafe": [],
        "audit_status": status,
        "scan_report": "validation/evidence/l2-slices/unsafe-scan.json",
        "audited_modules": [
            "validation/l2_slices/src/sqlite_varint.rs",
            "validation/l2_slices/src/zlib_adler32.rs",
            "validation/l2_slices/src/zstd_xxh32.rs"
        ]
    });
    write_json(&evidence_dir.join("unsafe-ledger.json"), &ledger)?;

    Ok(SafetyEvidence { scan, ledger })
}
```

- [ ] **Step 4: Run the report generator to prove ledger exists**

Run:

```powershell
Push-Location validation\l2_slices
cargo run --bin emit_reports
Pop-Location
Test-Path validation\evidence\l2-slices\unsafe-ledger.json
```

Expected:

```text
True
```

---

### Task 6: Add L2 Negative Diff Evidence

**Files:**
- Modify: `validation/l2_slices/src/bin/emit_reports.rs`
- Create: `validation/evidence/l2-slices/zlib-adler32-negative-diff.json`

- [ ] **Step 1: Add negative diff result struct**

In `validation/l2_slices/src/bin/emit_reports.rs`, add this after `SafetyEvidence`:

```rust
#[derive(Debug)]
struct NegativeDiffResult {
    slice_id: &'static str,
    status: &'static str,
    report_path: &'static str,
}
```

- [ ] **Step 2: Add negative diff emitter**

Add this function after `emit_zstd_xxh32`:

```rust
fn emit_negative_diffs(
    fixtures_dir: &Path,
    evidence_dir: &Path,
) -> Result<Vec<NegativeDiffResult>, Box<dyn Error>> {
    let fixture_path = fixtures_dir.join("zlib-adler32-c-oracle.json");
    let cases: Vec<ChecksumCase> = read_json(&fixture_path)?;
    let case = cases
        .first()
        .ok_or("zlib-adler32 fixture must contain at least one case")?;
    let input = hex_to_bytes(&case.input_hex)?;
    let rust_value = zlib_adler32::adler32(&input);
    let mutated_c_value = case.value ^ 1;
    let detected = mutated_c_value != rust_value;
    let status = if detected { "passed" } else { "failed" };
    let first_mismatch = if detected {
        Some(json!({
            "case_id": case.id,
            "field": "value",
            "mutated_c_value": mutated_c_value,
            "rust_value": rust_value
        }))
    } else {
        None
    };
    let report_path = "validation/evidence/l2-slices/zlib-adler32-negative-diff.json";
    write_json(
        &evidence_dir.join("zlib-adler32-negative-diff.json"),
        &json!({
            "schema_version": 1,
            "level": "L2",
            "slice_id": "zlib-adler32",
            "status": status,
            "mutation": "first oracle case value is replaced with value ^ 1",
            "case_id": case.id,
            "detected": detected,
            "first_mismatch": first_mismatch
        }),
    )?;

    Ok(vec![NegativeDiffResult {
        slice_id: "zlib-adler32",
        status,
        report_path,
    }])
}
```

- [ ] **Step 3: Update summary function signature**

Replace:

```rust
fn emit_summary(
    evidence_dir: &Path,
    slices: &[SliceResult],
    scan: &Value,
) -> Result<(), Box<dyn Error>> {
```

with:

```rust
fn emit_summary(
    evidence_dir: &Path,
    slices: &[SliceResult],
    safety: &SafetyEvidence,
    negative_diffs: &[NegativeDiffResult],
) -> Result<(), Box<dyn Error>> {
```

- [ ] **Step 4: Update all_passed logic**

Inside `emit_summary`, replace:

```rust
        && scan["status"] == "passed";
```

with:

```rust
        && safety.scan["status"] == "passed"
        && safety.ledger["audit_status"] == "passed"
        && negative_diffs.iter().all(|diff| diff.status == "passed");
```

- [ ] **Step 5: Add summary fields**

Inside the JSON written by `emit_summary`, replace:

```rust
            "safety_check": scan,
```

with:

```rust
            "safety_check": safety.scan,
            "unsafe_ledger_check": safety.ledger,
            "negative_diff_check": {
                "status": if negative_diffs.iter().all(|diff| diff.status == "passed") { "passed" } else { "failed" },
                "reports": negative_diffs.iter().map(|diff| {
                    json!({
                        "slice_id": diff.slice_id,
                        "status": diff.status,
                        "report": diff.report_path
                    })
                }).collect::<Vec<_>>()
            },
```

- [ ] **Step 6: Run focused report generation**

Run:

```powershell
Push-Location validation\l2_slices
cargo run --bin emit_reports
Pop-Location
Get-Content validation\evidence\l2-slices\zlib-adler32-negative-diff.json -Raw | ConvertFrom-Json | Select-Object status,detected
```

Expected:

```text
status detected
------ --------
passed     True
```

---

### Task 7: Run L2 Tests And Evidence Assertions

**Files:**
- Test: `validation/l2_slices/tests/oracle_fixtures.rs`
- Evidence: `validation/evidence/l2-slices/*.json`

- [ ] **Step 1: Format L2 crate**

Run:

```powershell
Push-Location validation\l2_slices
cargo fmt -- --check
Pop-Location
```

Expected: exit code 0.

- [ ] **Step 2: Run L2 tests**

Run:

```powershell
Push-Location validation\l2_slices
cargo test
Pop-Location
```

Expected:

```text
test result: ok
```

- [ ] **Step 3: Regenerate L2 reports**

Run:

```powershell
Push-Location validation\l2_slices
cargo run --bin emit_reports
Pop-Location
```

Expected:

```text
Finished
```

- [ ] **Step 4: Assert evidence files exist and pass**

Run:

```powershell
$summary = Get-Content validation\evidence\l2-slices\l2-l3-summary.json -Raw | ConvertFrom-Json
$ledger = Get-Content validation\evidence\l2-slices\unsafe-ledger.json -Raw | ConvertFrom-Json
$negative = Get-Content validation\evidence\l2-slices\zlib-adler32-negative-diff.json -Raw | ConvertFrom-Json
$zlib = Get-Content validation\l2_slices\fixtures\zlib-adler32-c-oracle.json -Raw | ConvertFrom-Json
@(
  $summary.status
  $ledger.audit_status
  $ledger.first_party_non_test_unsafe_count
  $negative.status
  $negative.detected
  $zlib.Count
)
```

Expected:

```text
passed
passed
0
passed
True
137
```

---

### Task 8: Full Project Validation

**Files:**
- Validate: all changed files

- [ ] **Step 1: Validate OpenSpec change**

Run:

```powershell
openspec validate add-l2-safety-ledger-and-deterministic-diff-fuzz --strict
```

Expected:

```text
Change 'add-l2-safety-ledger-and-deterministic-diff-fuzz' is valid
```

- [ ] **Step 2: Validate all OpenSpec artifacts**

Run:

```powershell
openspec validate --all
```

Expected:

```text
Totals: 15 passed, 0 failed
```

The passed count may increase if this change adds a new valid spec delta; no failed specs are acceptable.

- [ ] **Step 3: Run FlashDB Rust regression tests**

Run:

```powershell
Push-Location flashDB_rust
cargo fmt -- --check
cargo test
Pop-Location
```

Expected:

```text
test result: ok
```

- [ ] **Step 4: Run whitespace validation**

Run:

```powershell
git diff --check
```

Expected: no output, exit code 0.

---

### Task 9: Review, Commit, And Push

**Files:**
- Review: all changed files

- [ ] **Step 1: Review diff**

Run:

```powershell
git diff --stat
git diff -- validation\l2_slices\src\bin\emit_reports.rs
git diff -- validation\l2_slices\tools\generate_oracles.py
git diff -- validation\gates.md
```

Expected:

- No unrelated files changed.
- `emit_reports.rs` owns ledger, negative diff, and summary references.
- `generate_oracles.py` only expands deterministic zlib corpus.
- `validation/gates.md` only strengthens L2 evidence requirements.

- [ ] **Step 2: Commit**

Run:

```powershell
git add openspec\changes\add-l2-safety-ledger-and-deterministic-diff-fuzz validation\gates.md validation\l2_slices validation\evidence\l2-slices
git commit -m "Add L2 unsafe ledger and deterministic diff evidence"
```

Expected:

```text
[codex/flashdb-rust-skeleton <sha>] Add L2 unsafe ledger and deterministic diff evidence
```

- [ ] **Step 3: Push**

Run:

```powershell
git push origin codex/flashdb-rust-skeleton
```

Expected:

```text
codex/flashdb-rust-skeleton -> codex/flashdb-rust-skeleton
```

- [ ] **Step 4: Verify remote head**

Run:

```powershell
$local = git rev-parse HEAD
$remote = git ls-remote origin refs/heads/codex/flashdb-rust-skeleton
$local
$remote
```

Expected: remote SHA starts with the same SHA printed by `git rev-parse HEAD`.

---

## Self-Review

Spec coverage:

- L2 unsafe audit gap is covered by Task 5.
- L2 deterministic differential corpus gap is covered by Task 4.
- L2 negative diff gap is covered by Task 6.
- OpenSpec traceability is covered by Task 2 and Task 8.
- Small and safe implementation boundary is preserved by avoiding new dependencies and touching only L2 evidence files.

Placeholder scan:

- No task uses TBD/TODO wording.
- Every command has expected output.
- Every file path is explicit.

Type consistency:

- `SafetyEvidence` is passed to `emit_summary`.
- `NegativeDiffResult` is passed to `emit_summary`.
- Summary JSON keeps existing `safety_check` and adds `unsafe_ledger_check` plus `negative_diff_check`, preserving compatibility with existing readers that inspect `safety_check`.

## Execution Options

Plan complete and saved to `docs/superpowers/plans/2026-06-24-l2-safety-ledger-deterministic-diff-fuzz.md`.

Two execution options:

1. Subagent-Driven (recommended): dispatch one worker for OpenSpec/docs, one worker for oracle corpus, one owner for Rust evidence generation, then review and integrate in this session.
2. Inline Execution: execute tasks in this session with checkpoints after OpenSpec, after corpus generation, after Rust evidence generation, and after final validation.
