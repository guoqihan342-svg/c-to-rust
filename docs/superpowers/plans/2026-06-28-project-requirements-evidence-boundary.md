英文镜像见 `2026-06-28-project-requirements-evidence-boundary.en.md`。

# Project Requirements Evidence Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the repository's OpenSpec context, roadmap wording, route/evidence documentation, and validator/generator report wording with the approved project requirements and fail-closed evidence boundary.

**Architecture:** This is a boundary-alignment change, not a translator capability change. The work is split into OpenSpec context repair, active spec Purpose repair, claim-language documentation repair, generator report wording repair, validator CLI output clarification, and final validation. Translator behavior and historical evidence content stay untouched unless a later reviewed task explicitly regenerates one named evidence package.

**Tech Stack:** Markdown/OpenSpec, Python 3.12 unittest, `validation/tools/auto_migrate.py`, `validation/tools/validate_auto_translation_evidence.py`, PowerShell, ripgrep, Git.

---

## File Structure

- Modify: `openspec/project.md`
  - Responsibility: Current project context for future OpenSpec changes.
- Modify: `openspec/specs/bounded-auto-translation-pipeline/spec.md`
  - Responsibility: Active automatic translation pipeline requirements.
- Modify: `openspec/specs/pointer-arithmetic-output-write-l3-demo-slice/spec.md`
  - Responsibility: Active bounded pointer output-write demo requirements.
- Modify: `docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.md`
  - Responsibility: Chinese route/evidence explanation.
- Modify: `docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.en.md`
  - Responsibility: English route/evidence explanation mirror.
- Modify: `validation/gates.md`
  - Responsibility: Validation claim-language authority.
- Modify: `validation/tools/auto_migrate.py`
  - Responsibility: Generated auto-translation report wording.
- Modify: `validation/tools/test_auto_migrate.py`
  - Responsibility: Regression tests for generated report wording.
- Modify: `validation/tools/validate_auto_translation_evidence.py`
  - Responsibility: Validator CLI summary fields.
- Modify: `validation/tools/test_validate_auto_translation_evidence.py`
  - Responsibility: Regression tests for validator CLI semantic claim source.
- Do not modify in this plan: `crates/c2r-translator/**`, `validation/evidence/**`, `openspec/changes/archive/**`, generated Rust drafts, schemas.

OpenSpec anchors must keep their exact parser-facing spelling and hierarchy: `## Purpose`, `## Requirements`, `### Requirement:`, `#### Scenario:`, `- **WHEN**`, `- **THEN**`, `- **AND**`. If an execution worker touches change files, it must also preserve `## ADDED Requirements`, `## MODIFIED Requirements`, `## REMOVED Requirements`, and `- [ ]` task checkbox syntax.

### Task 1: Baseline Guard And Worktree Boundary

**Files:**
- Read: `git status`
- Read: `docs/superpowers/specs/2026-06-27-project-requirements-evidence-boundary-design.md`
- Do not modify files in this task.

- [ ] **Step 1: Record current worktree state**

Run:

```powershell
git status --short --branch --untracked-files=all
```

Expected: the branch may be ahead by the prior design commit and may contain existing modified files. Do not revert or stage unrelated changes.

- [ ] **Step 2: Re-read the approved design**

Run:

```powershell
Get-Content -LiteralPath docs\superpowers\specs\2026-06-27-project-requirements-evidence-boundary-design.md
```

Expected: the design states that this round does not change translator behavior, does not install clang, and does not regenerate all validation evidence.

- [ ] **Step 3: Confirm current OpenSpec baseline**

Run:

```powershell
openspec validate --all --strict
```

Expected: `38/38` specs pass before edits. If the command is unavailable, record the exact shell error in the final handoff and continue with file-level checks.

### Task 2: Repair OpenSpec Project Context

**Files:**
- Modify: `openspec/project.md`
- Do not modify: `openspec/specs/**`, `docs/**`, `validation/**`, `crates/c2r-translator/**`

- [ ] **Step 1: Replace the stale project context**

Replace the full contents of `openspec/project.md` with:

```markdown
# Project Context

## Purpose

This repository is an agent-facing C-to-Rust migration pipeline. It combines candidate generation with fail-closed validation so that Rust translation candidates are accepted only when evidence ties them back to the original C behavior.

Correctness comes from the C oracle, Rust replay, schema-aware diff, negative diff, unsafe ledger, version/config binding, and final verification evidence. Typed IR, C2Rust, LLM output, handwritten recipes, and generated Rust drafts are candidate sources only; they are not correctness sources.

## OpenSpec Workflow

1. Create a unique verb-led change ID under `openspec/changes/`.
2. Draft `proposal.md` for why the change exists, what is in scope, and expected impact.
3. Draft behavior-first delta specs under `openspec/changes/<change-id>/specs/<capability>/spec.md`.
4. Draft `design.md` for architecture decisions and implementation sequencing.
5. Draft `tasks.md` as the step-by-step checklist.
6. Validate the change with `openspec validate <change-id> --strict` when the OpenSpec CLI is available.
7. Do not implement product code until the proposal is reviewed and approved.

## Conventions

- Specs describe externally visible behavior with MUST/SHALL language and concrete scenarios.
- Preserve OpenSpec parser anchors such as `## Purpose`, `## Requirements`, `### Requirement:`, `#### Scenario:`, `WHEN`, `THEN`, and `AND`.
- Keep implementation details in `design.md` and delivery steps in `tasks.md`.
- Prefer small, reviewable stages with clear acceptance criteria.
- Every public claim must state whether it is L1 native baseline, candidate generation, L2 compile/safety evidence, L3 named-slice semantic evidence, or L4 refusal/accepted-evidence-authoritative binding.
- `config/competition-env/environment.json` is the default competition environment profile. New validation evidence generated for that profile must record the profile id and environment hash.
- Go and CMake are not default competition-environment dependencies. Gates that require missing tools must be optional, skipped with explicit evidence, or run in a declared compatible environment.

## Non-Goals

- Do not describe native C build success as Rust translation success.
- Do not let `route_decision.level=L0` imply semantic equivalence.
- Do not treat AI, C2Rust, typed IR, or string recipes as correctness evidence.
- Do not claim full FlashDB or real-project migration from curated named-slice evidence.
```

- [ ] **Step 2: Verify the stale terms are gone**

Run:

```powershell
rg -n "DWCCA|unified API contract" openspec/project.md
```

Expected: no matches.

- [ ] **Step 3: Verify required terms are present**

Run:

```powershell
rg -n "C-to-Rust|C oracle|candidate|fail-closed|config/competition-env/environment.json|L3 named-slice" openspec/project.md
```

Expected: matches for each term family.

- [ ] **Step 4: Validate OpenSpec**

Run:

```powershell
openspec validate --all --strict
```

Expected: all specs pass.

- [ ] **Step 5: Commit Task 2 only**

Run:

```powershell
git add -- openspec/project.md
git commit -m "docs: align openspec project context"
```

Expected: commit contains only `openspec/project.md`.

### Task 3: Repair Active Spec Purpose Text

**Files:**
- Modify: `openspec/specs/bounded-auto-translation-pipeline/spec.md`
- Modify: `openspec/specs/pointer-arithmetic-output-write-l3-demo-slice/spec.md`
- Do not modify: `openspec/specs/flashdb-l3-agent-migration-loop/spec.md`, `openspec/changes/archive/**`, `validation/**`, `crates/c2r-translator/**`

- [ ] **Step 1: Replace bounded pipeline Purpose**

In `openspec/specs/bounded-auto-translation-pipeline/spec.md`, replace only the paragraph immediately below `## Purpose` with:

```markdown
This spec defines the fail-closed automatic translation pipeline for real C source slices. It requires generated slice-spec provenance, context/type/CFG/pointer evidence, candidate-only Rust draft generation, C oracle/Rust replay/diff/negative/unsafe/version gates, and cache invalidation before any named-slice L3 semantic claim is accepted.
```

- [ ] **Step 2: Replace pointer output-write Purpose**

In `openspec/specs/pointer-arithmetic-output-write-l3-demo-slice/spec.md`, replace only the paragraph immediately below `## Purpose` with:

```markdown
This spec defines the `copy_i32_ptr_arith` L3 demonstration slice for bounded pointer-arithmetic output writes. It verifies that `*(out + i) = expr` is accepted only when the pointer graph and loop bound prove safe mutable-slice output behavior, while C oracle, Rust replay, schema-aware diff, negative diff, and unsafe evidence remain authoritative.
```

- [ ] **Step 3: Confirm active spec archive placeholders are gone**

Run:

```powershell
rg -n "created by archiving|Update Purpose after archive" openspec/specs
```

Expected: no matches under `openspec/specs`. Matches under `openspec/changes/archive/**` are outside this task and should not be changed.

- [ ] **Step 4: Confirm FlashDB stale scenario is not modified**

Run:

```powershell
rg -n -C 2 "TSDB stale intermediate statuses|L3 Bilingual OpenSpec Text Integrity|Auto-Translated Slice Evidence Source" openspec/specs/flashdb-l3-agent-migration-loop/spec.md
```

Expected: matching scenarios remain present.

- [ ] **Step 5: Validate OpenSpec and whitespace**

Run:

```powershell
openspec validate --all --strict
git diff --check -- openspec/specs/bounded-auto-translation-pipeline/spec.md openspec/specs/pointer-arithmetic-output-write-l3-demo-slice/spec.md
```

Expected: OpenSpec passes and diff check has no output.

- [ ] **Step 6: Commit Task 3 only**

Run:

```powershell
git add -- openspec/specs/bounded-auto-translation-pipeline/spec.md openspec/specs/pointer-arithmetic-output-write-l3-demo-slice/spec.md
git commit -m "docs: repair active openspec purpose text"
```

Expected: commit contains only the two active spec files.

### Task 4: Align Route And Gate Claim Language

**Files:**
- Modify: `docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.md`
- Modify: `docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.en.md`
- Modify: `validation/gates.md`
- Do not modify: `validation/evidence/**`, `validation/tools/**`, `crates/c2r-translator/**`

- [ ] **Step 1: Tighten generated draft field wording in Chinese routing doc**

In `docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.md`, replace the bullet for `generated_draft_semantic_pass` with:

```markdown
- `generated_draft_semantic_pass`: 生成草稿本身是否通过语义。当前必须保持 `false`；即使 `final_verification.semantic_pass=true`，语义来源也是 accepted/named-slice evidence bundle，不是 generated draft 自身。
```

- [ ] **Step 2: Add accepted evidence source sentence in Chinese routing doc**

In the `semantic_pass_for_run()` rules section, after the rule that says `generated_draft_semantic_pass` must be false, add:

```markdown
6. 当 L4/refused 通过 `accepted_evidence_authoritative=true` 绑定外部证据时，报告必须说明已绑定 `accepted_evidence_binding`，并保持 `generated_draft_semantic_pass=false`。
```

- [ ] **Step 3: Mirror the wording in English routing doc**

In `docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.en.md`, replace the `generated_draft_semantic_pass` bullet with:

```markdown
- `generated_draft_semantic_pass`: whether the generated draft itself passed semantics. It must remain `false`; even when `final_verification.semantic_pass=true`, the semantic source is the accepted/named-slice evidence bundle, not the generated draft itself.
```

Then add this rule after the existing generated-draft rule:

```markdown
6. When L4/refused passes through `accepted_evidence_authoritative=true`, reports must state that they bind `accepted_evidence_binding` and keep `generated_draft_semantic_pass=false`.
```

- [ ] **Step 4: Add validation gate claim boundary**

In `validation/gates.md`, after the paragraph that starts with `Only L3 can support a limited semantic-equivalence claim`, add:

```markdown
For auto-translation evidence, `final_verification.semantic_pass=true` is claimable only as an accepted/named-slice evidence bundle result. It must not be read as `generated_draft_semantic_pass=true`; generated drafts, typed IR candidates, C2Rust candidates, and LLM candidates remain candidate/provenance artifacts unless the exact artifact is independently bound by an accepted/named-slice evidence bundle and passes required gates.
```

- [ ] **Step 5: Verify wording**

Run:

```powershell
rg -n "generated_draft_semantic_pass|accepted_evidence_binding|accepted/named-slice|candidate/provenance" docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.md docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.en.md validation/gates.md
```

Expected: the new boundary wording appears in all three files.

- [ ] **Step 6: Validate docs and OpenSpec**

Run:

```powershell
git diff --check -- docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.md docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.en.md validation/gates.md
openspec validate --all --strict
```

Expected: no whitespace errors and OpenSpec passes.

- [ ] **Step 7: Commit Task 4 only**

Run:

```powershell
git add -- docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.md docs/c2rust-migration-agent/l0-l4-routing-and-evidence-gates.en.md validation/gates.md
git commit -m "docs: clarify auto translation semantic claim source"
```

Expected: commit contains only the three claim-language docs.

### Task 5: Test Auto-Migrate Report Boundary Wording

**Files:**
- Modify: `validation/tools/test_auto_migrate.py`
- Do not modify yet: `validation/tools/auto_migrate.py`

- [ ] **Step 1: Add failing assertions for accepted evidence claim scope**

In `test_real_fdb_calc_crc32_accept_existing_evidence_reaches_authoritative_semantic_pass`, after the existing assertion `self.assertTrue(manifest["claim_boundary"]["accepted_evidence_authoritative"])`, add:

```python
            self.assertFalse(manifest["claim_boundary"]["generated_draft_semantic_pass"])
            self.assertIn("accepted_evidence_binding", manifest["claim_boundary"]["scope"])
            self.assertIn("generated_draft_semantic_pass remains false", manifest["claim_boundary"]["scope"])
            self.assertIn("generated Rust draft remains candidate/provenance", manifest["claim_boundary"]["scope"])
```

- [ ] **Step 2: Run the targeted failing test**

Run:

```powershell
python -B -m unittest validation.tools.test_auto_migrate.ValidateAutoMigrateTests.test_real_fdb_calc_crc32_accept_existing_evidence_reaches_authoritative_semantic_pass
```

Expected: fail because `auto_manifest_claim_scope()` still says the draft remains a candidate unless `generated_draft_semantic_pass` is true.

### Task 6: Implement Auto-Migrate Report Boundary Wording

**Files:**
- Modify: `validation/tools/auto_migrate.py`
- Modify: `validation/tools/test_auto_migrate.py`
- Do not modify: `validation/evidence/**`, `crates/c2r-translator/**`, schemas

- [ ] **Step 1: Replace accepted semantic claim scope string**

In `validation/tools/auto_migrate.py`, replace `auto_manifest_claim_scope()` with:

```python
def auto_manifest_claim_scope(semantic_pass: bool, route_decision: dict[str, Any]) -> str:
    if semantic_pass:
        return (
            "auto-translation run bound to accepted_evidence_binding; "
            "final_verification.semantic_pass=true is sourced from accepted/named-slice evidence; "
            "generated_draft_semantic_pass remains false; generated Rust draft remains candidate/provenance"
        )
    if route_decision.get("level") == "L4":
        return "refused translation route; no generated candidate can claim semantics"
    return "generated Rust candidate only; semantic acceptance requires independent L3 gates"
```

- [ ] **Step 2: Run the targeted test again**

Run:

```powershell
python -B -m unittest validation.tools.test_auto_migrate.ValidateAutoMigrateTests.test_real_fdb_calc_crc32_accept_existing_evidence_reaches_authoritative_semantic_pass
```

Expected: pass.

- [ ] **Step 3: Run the auto-migrate test module**

Run:

```powershell
python -B -m unittest validation.tools.test_auto_migrate
```

Expected: pass. If runtime is long, keep the terminal running until completion and report the exact failing test if it fails.

- [ ] **Step 4: Validate committed FlashDB auto evidence still passes**

Run:

```powershell
python -B validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass
```

Expected: JSON output with `"semantic_pass": true`. This task does not rewrite committed evidence.

- [ ] **Step 5: Commit Tasks 5 and 6**

Run:

```powershell
git add -- validation/tools/auto_migrate.py validation/tools/test_auto_migrate.py
git commit -m "test: clarify generated draft claim boundary"
```

Expected: commit contains only `auto_migrate.py` and its test.

### Task 7: Test Validator CLI Semantic Claim Source

**Files:**
- Modify: `validation/tools/test_validate_auto_translation_evidence.py`
- Do not modify yet: `validation/tools/validate_auto_translation_evidence.py`

- [ ] **Step 1: Add a failing CLI output test**

In `ValidateAutoTranslationEvidenceTests`, add this test near the existing semantic-pass tests:

```python
    def test_cli_reports_semantic_claim_source_boundaries(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-calc-crc32.json"
        with tempfile.TemporaryDirectory(prefix="auto-validator-test-") as tmp:
            out_root = Path(tmp) / "evidence"
            migrate = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--accept-existing-evidence",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(migrate.returncode, 0, f"stdout:\n{migrate.stdout}\nstderr:\n{migrate.stderr}")

            base = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "flashdb",
                    "--slice-id",
                    "real-fdb-calc-crc32",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(base.returncode, 0, f"stdout:\n{base.stdout}\nstderr:\n{base.stderr}")
            base_payload = json.loads(base.stdout)
            self.assertFalse(base_payload["semantic_pass"])
            self.assertEqual(base_payload["semantic_claim_source"], "not_evaluated")
            self.assertFalse(base_payload["generated_draft_semantic_pass"])

            required = subprocess.run(
                [
                    "python",
                    str(VALIDATOR),
                    "--target-id",
                    "flashdb",
                    "--slice-id",
                    "real-fdb-calc-crc32",
                    "--slice-spec",
                    str(spec_path),
                    "--evidence-root",
                    str(out_root),
                    "--require-semantic-pass",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
            self.assertEqual(required.returncode, 0, f"stdout:\n{required.stdout}\nstderr:\n{required.stderr}")
            required_payload = json.loads(required.stdout)
            self.assertTrue(required_payload["semantic_pass"])
            self.assertEqual(required_payload["semantic_claim_source"], "accepted_evidence_binding")
            self.assertFalse(required_payload["generated_draft_semantic_pass"])
            self.assertEqual(
                required_payload["semantic"]["semantic_claim_source"],
                "accepted_evidence_binding",
            )
            self.assertFalse(required_payload["semantic"]["generated_draft_semantic_pass"])
```

- [ ] **Step 2: Run the targeted failing test**

Run:

```powershell
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_cli_reports_semantic_claim_source_boundaries
```

Expected: fail because the validator CLI output does not yet include `semantic_claim_source` and `generated_draft_semantic_pass`.

### Task 8: Implement Validator CLI Semantic Claim Source

**Files:**
- Modify: `validation/tools/validate_auto_translation_evidence.py`
- Modify: `validation/tools/test_validate_auto_translation_evidence.py`
- Do not modify: `validation/evidence/**`, `validation/tools/auto_migrate.py`, `crates/c2r-translator/**`

- [ ] **Step 1: Add non-required semantic boundary payload**

In `main()`, replace the non-required semantic branch:

```python
        else {"semantic_pass": False, "status": "not_required"}
```

with:

```python
        else {
            "semantic_pass": False,
            "status": "not_required",
            "semantic_claim_source": "not_evaluated",
            "generated_draft_semantic_pass": False,
        }
```

- [ ] **Step 2: Add top-level CLI fields**

In the JSON object printed by `main()`, add these fields after `"semantic_pass": bool(semantic.get("semantic_pass")),`:

```python
                "semantic_claim_source": str(semantic.get("semantic_claim_source", "not_evaluated")),
                "generated_draft_semantic_pass": bool(semantic.get("generated_draft_semantic_pass", False)),
```

- [ ] **Step 3: Add accepted evidence source to semantic pass return**

In `validate_semantic_pass()`, add these fields to the returned dictionary:

```python
        "semantic_claim_source": "accepted_evidence_binding",
        "generated_draft_semantic_pass": False,
```

The return block should include both fields alongside `"semantic_pass": True`.

- [ ] **Step 4: Run the targeted test again**

Run:

```powershell
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_cli_reports_semantic_claim_source_boundaries
```

Expected: pass.

- [ ] **Step 5: Run validator test module**

Run:

```powershell
python -B -m unittest validation.tools.test_validate_auto_translation_evidence
```

Expected: pass.

- [ ] **Step 6: Run real FlashDB validator commands**

Run:

```powershell
python -B validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json
python -B validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass
```

Expected: first output has `"semantic_pass": false`, `"semantic_claim_source": "not_evaluated"`, and `"generated_draft_semantic_pass": false`; second output has `"semantic_pass": true`, `"semantic_claim_source": "accepted_evidence_binding"`, and `"generated_draft_semantic_pass": false`.

- [ ] **Step 7: Commit Tasks 7 and 8**

Run:

```powershell
git add -- validation/tools/validate_auto_translation_evidence.py validation/tools/test_validate_auto_translation_evidence.py
git commit -m "test: expose semantic claim source in validator"
```

Expected: commit contains only the validator and its test.

### Task 9: Final Boundary Verification

**Files:**
- Read: changed files from Tasks 2-8
- Do not modify files in this task.

- [ ] **Step 1: Run OpenSpec validation**

Run:

```powershell
openspec validate --all --strict
```

Expected: all specs pass.

- [ ] **Step 2: Run Python validation tests**

Run:

```powershell
python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence
```

Expected: pass.

- [ ] **Step 3: Run committed FlashDB semantic validator**

Run:

```powershell
python -B validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass
```

Expected: JSON output has `"semantic_pass": true`, `"semantic_claim_source": "accepted_evidence_binding"`, and `"generated_draft_semantic_pass": false`.

- [ ] **Step 4: Run focused text checks**

Run:

```powershell
rg -n "DWCCA|unified API contract" openspec/project.md
rg -n "created by archiving|Update Purpose after archive" openspec/specs
rg -n "generated_draft_semantic_pass|accepted_evidence_binding|accepted/named-slice|candidate/provenance" docs/c2rust-migration-agent validation/gates.md validation/tools --glob "!validation/evidence/**"
git diff --check
```

Expected: first command has no matches, second command has no matches under active specs, third command shows the new boundary wording and tests, and `git diff --check` has no output.

- [ ] **Step 5: Confirm translator stayed untouched**

Run:

```powershell
git diff --name-only HEAD -- crates/c2r-translator
```

Expected: no output for this implementation series.

- [ ] **Step 6: Review final status**

Run:

```powershell
git status --short --branch --untracked-files=all
```

Expected: only pre-existing unrelated dirty files remain. If implementation tasks created commits, the branch is ahead by those commits.

### Task 10: Push Boundary Fix Branch

**Files:**
- No file edits.

- [ ] **Step 1: Show commit series**

Run:

```powershell
git log --oneline origin/codex/flashdb-rust-skeleton..HEAD
```

Expected: includes the prior design commit plus the implementation commits from this plan.

- [ ] **Step 2: Push current branch**

Run:

```powershell
git push origin codex/flashdb-rust-skeleton
```

Expected: push succeeds and remote branch advances.

- [ ] **Step 3: Report exact pushed commit**

Run:

```powershell
git rev-parse HEAD
```

Expected: print the commit SHA that was pushed.
