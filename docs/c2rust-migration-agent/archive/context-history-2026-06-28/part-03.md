## 32. 2026-06-26 call-expression legacy manifest route/profile backfill

本轮承接第 31 节的第一条下一步：把 legacy call-expression fixture 补齐到可以直接通过当前
`--require-semantic-pass` validator，而不再只依赖测试 helper 临时回填。

### 红测

先复现上一轮留下的直接失败：

```powershell
python -B -m unittest validation.tools.test_call_expression_l3_evidence.CallExpressionL3EvidenceTests.test_call_expression_auto_translation_semantic_gate_passes
```

失败点在 `validate_auto_translation_evidence.py` schema 阶段：`l3-call-expression-evidence-manifest.json`
的 `evidence` 缺少 `c2rust_baseline` required property，因此还没有进入 semantic `load_ref()`。

### 持久 evidence 三件套

新增落盘 fixture：

- `validation/evidence/demo/auto-translation/call-expression/l3-call-expression-c2rust-baseline-manifest.json`
- `validation/evidence/demo/auto-translation/call-expression/l3-call-expression-route-decision.json`
- `validation/evidence/demo/auto-translation/call-expression/l3-call-expression-validation-profile.json`

语义选择：

- C2Rust baseline 是 `status: skipped`，`correctness_role: candidate_context_only`，不得作为语义等价证明。
- route decision 是 `status: recorded`、`level: L0`、`verification_profile: L0-dev`。这是按当前正式
  `auto_migrate.py` route 逻辑来的：call-expression pointer graph 没有 pointer surface，因此是 scalar-only L0。
- validation profile 是 `status: passed`、`profile: L0-dev`、`route_level: L0`、`skipped_gates: []`。

同步更新：

- `l3-call-expression-auto-translation-manifest.json`
- `l3-call-expression-evidence-manifest.json`
- `l3-call-expression-final-verification.json`
- `l3-call-expression-auto-cache-metadata.json`

其中普通 refs 使用文件字节 sha；cache identity 使用 `json.dumps(payload, sort_keys=True)` 的 canonical JSON sha。
这两类 sha 不能混用。

### 关键绑定值

- baseline ref: `status=skipped`,
  `sha256=5a51b4cec6db030effe03906be26c3e75c3b25aca4cd3063c3bb337a148a5f57`
- route ref: `status=recorded`, `level=L0`,
  `sha256=fa4b7514f5bcefcd6fb4d7c256268e9df40a00a5085e86d22ce6e88470288a19`
- profile ref: `status=passed`, `profile=L0-dev`,
  `sha256=c3f9f760260836a5da8e28524cd7dc05287096a1c25a96d842d1b2e5728de5f0`

cache identity:

- `c2rust_baseline_identity.sha256=d3c06611a51b11cb55ce2dd25df16d8ac5deeea24d27c90397d4598bc54fce87`
- `route_decision_identity.sha256=6b8de9bff3f7801b8656dc24a0ba41b459607b753491bb91e17a5d1b1b49bff5`
- `validation_profile_identity.sha256=c7363c575867d3fc3cacf72c7e8bec9064f01e866720d1cce3613ae8fa605ace`

### 验证

直接 validator 现在通过：

```powershell
python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id call-expression --require-semantic-pass
```

输出 `semantic_pass: true`，并检查了 `c2rust_baseline`、`route_decision`、`validation_profile`、
`c_oracle`、`rust_report`、`schema_diff`、`negative_diff`、`unsafe_scan`、`unsafe_ledger`、
`final_verification`、`version_or_config_binding`。

完整 call-expression 测试通过：

```powershell
python -B -m unittest validation.tools.test_call_expression_l3_evidence
```

### 并行审查结论

本轮两个 explorer 均为只读：

- Sartre 确认最初失败链先卡在 manifest schema 缺 `c2rust_baseline`，并列出后续会挡住的
  route/baseline/profile 交叉绑定、semantic `load_ref()`、cache identity 和 diff gate 规则。
- Turing 确认当前持久三件套绑定值正确，提醒新增三个 fixture 仍是 untracked，需要纳入工作树；
  同时确认持久 fixture 不应照搬测试 helper 的 `unit_test_backfill_for_legacy_fixture` 占位值。

下一步建议：

1. 继续推进 real-fdb harness execution，从 `compiler_not_found` 进入真实可执行 oracle/harness 输出校验。
2. 如需进一步去除测试 helper 遗留，可把 `_backfill_route_baseline_profile_evidence()` 改为刷新 copied fixture refs，
   而不是生成 unit-test backfill payload；当前 direct call-expression 测试已覆盖落盘 fixture。
## 33. 2026-06-26 real-fdb WSL C harness execution

本轮承接第 32 节的 real-fdb harness execution，把 `real-fdb-calc-crc32`
从 `compiler_not_found` 推进到真实 WSL 编译和 harness 执行，但仍保持 fail-closed：

- `c_oracle_status.status` 仍为 `DRAFT_GENERATED`
- `toolchain_status` 变为 `COMPILE_SUCCEEDED_NOT_ORACLE`
- `compile_execution.status` 为 `compile_succeeded_not_oracle`
- `harness_execution.status` 为 `exited_zero_not_oracle`
- `output_gate.status` 为 `matched_not_oracle`
- 顶层和所有子 gate 的 `semantic_pass` 仍为 `false`
- 整体 auto-translation 状态仍为 `candidate_refused`

### 工具链和 build profile

`validation/tools/auto_migrate.py` 新增/收紧：
- `cc` 缺失时按顺序探测 `gcc`、`clang`
- Windows 本地没有 C 编译器时探测 `wsl.exe`，在 WSL 内执行 `cc/gcc/clang`
- WSL 编译和 harness 执行使用 `wslpath` 转换绝对路径
- `compile_execution` 记录 `requested_compiler`、`compiler_candidates`、`compiler_name`、
  `compiler_path`、`toolchain_adapter`、`execution_argv`
- WSL `wslpath` 非零或 timeout 会写结构化 `compile_failed` / `compile_timeout` evidence，
  不再让 Python traceback 中断 evidence 生成
- `build_profile.link_source_files` 可声明 link-only 源文件，不污染 `c_boundary.files`

`validation/slice-specs/flashdb-real-fdb-calc-crc32.json` 更新：
- include path 从 `inc` 扩展为 `inc` + `tests`
- 增加 `build_profile.link_source_files`:
  `src/fdb_file.c`, sha256 `c27b7bc5e57253774a29f363305ba3ffdcf8c9afea3a8674ea03a33c83d2e02d`

原因：`tests/fdb_cfg.h` 打开 `FDB_USING_FILE_POSIX_MODE`，从而通过 `fdb_def.h`
启用 `FDB_USING_FILE_MODE`；`fdb_utils.c` 内的 `_fdb_flash_*` 包装函数会引用
`_fdb_file_read/_fdb_file_write/_fdb_file_erase`，这些定义在 `src/fdb_file.c`。

### Validator 收紧

`validation/tools/validate_auto_translation_evidence.py` 同步：
- 认可并校验 `build_profile.link_source_files` 生成的 compile command
- 校验新的 link strategy:
  `compile_harness_with_declared_c_boundary_and_build_profile_sources`
- 当 evidence 声明 `toolchain_adapter` / `execution_argv` 时，要求 provenance 自洽
- WSL compile execution 必须由 `wsl` / `wsl.exe` launcher 执行，且命令中包含记录的 compiler path
- WSL harness execution 必须同样记录 WSL launcher 和可审计 execution argv

这些校验只增强审计性，不把 compile/harness 成功提升为 oracle success。

### 验证

手工 WSL 最小命令先确认：
- `-I FlashDB/inc`
- `-I FlashDB/tests`
- `src/fdb_utils.c`
- `src/fdb_file.c`

输出两个 fixture marker：
- `fixture case empty-crc-zero return_code matched`
- `fixture case ascii-123456789-crc-zero return_code matched`

自动迁移命令：
```powershell
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json
```

生成的 `l3-real-fdb-calc-crc32-c-oracle-status.json` 记录：
- adapter: `wsl`
- compiler: `/usr/bin/cc`
- harness return code: `0`
- output gate matched fragment count: `2`

schema/fail-closed validator 通过：
```powershell
python -B validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json
```

完整相关回归通过：
```powershell
python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence
```

结果：`Ran 84 tests ... OK`

### 并行审查结论

本轮两个只读 explorer 均已关闭：
- Ptolemy 确认 `_fdb_file_*` 位于 `src/fdb_file.c`，当前 profile 下不需要 `src/fdb.c`、
  `src/fdb_kvdb.c`、`src/fdb_tsdb.c` 或 `-lpthread`
- Boole 确认没有 fail-open semantic pass 路径，同时指出 WSL path failure、fallback 测试隔离、
  WSL provenance validator 三个缺口；本轮均已补测试并修正

下一步建议：
1. 继续从 `COMPILE_SUCCEEDED_NOT_ORACLE` 推进到 accepted C oracle / Rust replay / schema diff 链路。
2. 若要长期支持 WSL，可把 distro、`uname`、compiler version 纳入 cache input 和 evidence provenance。
3. 再补 `cc/gcc` 缺失 fallback 到 `clang`、全部候选缺失、WSL harness nonzero/timeout 的负例覆盖。

## 34. 2026-06-26 real-fdb Rust replay / diff evidence groundwork

本轮承接第 33 节，但没有把 C harness 的 `*_NOT_ORACLE` 状态提升为语义通过。新增的是
real-fdb `fdb_calc_crc32` 的 Rust replay 实现和可重复生成的 Rust-side evidence：

- `validation/l2_slices/src/fdb_calc_crc32.rs`
- `validation/l2_slices/tests/fdb_calc_crc32.rs`
- `validation/l2_slices/fixtures/real-fdb-calc-crc32.json`
- `validation/l2_slices/src/bin/emit_reports.rs`
- `validation/tools/test_real_fdb_calc_crc32_l3_evidence.py`

Rust 实现按 FlashDB CRC32 逻辑逐字节处理：
- 初始 `crc ^ !0u32`
- 每字节低位移位 8 次
- 多项式 `0xEDB8_8320`
- 返回 `crc ^ !0u32`

fixture 当前覆盖两个 case：
- empty buffer identity：`crc=0`，返回 `0`
- 标准 `123456789` CRC32 check vector：返回 `3421780262`

`cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports` 现在会额外生成：
- `validation/evidence/flashdb/l3-real-fdb-calc-crc32-rust-report.json`
- `validation/evidence/flashdb/l3-real-fdb-calc-crc32-diff.json`
- `validation/evidence/flashdb/l3-real-fdb-calc-crc32-negative-diff.json`

这三个文件只证明 Rust replay 对当前 fixture 的 `return_code` 一致，并且 negative diff 能抓到
`return_code` mutation。它们不是 accepted C oracle，也不会让 auto-translation 的语义门禁通过。

### 验证

先红后绿：
- 新增 Python 回归测试后，首次运行失败在缺少
  `validation/evidence/flashdb/l3-real-fdb-calc-crc32-rust-report.json`
- 补 `emit_real_fdb_calc_crc32()` 后同一测试通过

已通过命令：
```powershell
cargo test --manifest-path validation/l2_slices/Cargo.toml fdb_calc_crc32_matches_real_flashdb_c_oracle_fixture
python -B -m unittest validation.tools.test_real_fdb_calc_crc32_l3_evidence
```

### 并行审查结论

本轮两个只读 explorer 均已关闭：
- Hypatia 确认 C oracle promotion 必须走 accepted evidence，且 real-fdb 带 `crc32_table`
  global dependency，不能复用普通 demo 的提升路径。
- Einstein 确认当前语义通过仍卡在 C oracle acceptance、L4 route/profile、accepted Rust report、
  schema diff、negative diff 和 manifest/final verification 链路。

下一步建议：
1. 产出真正 accepted C oracle report，且保留 `crc32_table` global linkage provenance。
2. 把本轮生成的 Rust report/diff/negative diff 绑定进 `fixture_contract` accepted evidence。
3. 解除 real-fdb 当前 L4 route，或明确新增 accepted-evidence route 策略；否则
   `semantic_pass_for_run()` 仍会拒绝。

## 35. 2026-06-26 L4 accepted-evidence authoritative policy hardening

本轮从第 34 节的第三个阻塞点继续：L4/refused route 默认仍不能语义通过，但允许 slice spec
显式声明 accepted evidence 作为权威证据链，从而表达“生成草稿未被验收，语义通过绑定到已有 accepted
C oracle / Rust report / diff / negative diff / unsafe evidence”。

核心改动：
- `validation/tools/auto_migrate.py`
  - 新增 `claim_boundary.accepted_evidence_authoritative=true` 显式开关。
  - 只有同时满足 `--accept-existing-evidence` 成功解析出 `accepted.status=accepted`，且 route 为
    `L4/refused` 时，才会在 route policy 写入：
    - `accepted_evidence_authoritative=true`
    - `generated_draft_semantic_pass=false`
    - `verification_profile=L4-accepted-evidence`
  - `emit_validation_profile()` 对该显式路线不再把 `candidate_generation` 记为 skipped gate。
  - `semantic_pass_for_run()` 仍默认拒绝 L4；只有 profile 同时声明
    `accepted_evidence_authoritative=true` 和 `generated_draft_semantic_pass=false` 时才允许通过。
  - auto manifest、L3 evidence manifest、final verification 都同步写入 authoritative / generated-draft
    边界字段。
  - `promote_accepted_oracle()` 对带 global dependency 的 slice 保留 draft oracle 中的
    `fixture_binding`、`harness_contract`、`global_linkage_requirements`、`compile_command_draft`、
    `compile_execution`，避免 real-fdb `crc32_table` 这类全局依赖在 accepted oracle promotion
    时丢失审计字段。

- `validation/tools/validate_auto_translation_evidence.py`
  - L4/refused 的 candidate artifact status 扫描保持默认 fail-closed。
  - 只有 auto manifest、route policy、accepted evidence binding、claim boundary 一致声明
    authoritative，且 slice spec 本身也声明
    `claim_boundary.accepted_evidence_authoritative=true`，才跳过 L4/refused candidate status 扫描。
  - semantic pass 对 L4/refused 同样回查 slice spec 授权，防止手工篡改 evidence artifacts 绕过
    spec claim boundary。

新增/加强测试：
- 默认 L4/refused + `--accept-existing-evidence` 仍为 `candidate_refused`，且
  `semantic_pass=false`、authoritative 字段全为 false。
- 显式 authoritative 的 L4/refused accepted evidence 可生成 `accepted_evidence_bound`，并能被
  `validate_auto_translation_evidence.py --require-semantic-pass` 接受。
- 未授权 spec 即使手工伪造 route/profile/manifest/final authoritative artifacts，也会被 validator
  拒绝。
- `semantic_pass_for_run()` 覆盖 L4 默认拒绝和 L4 authoritative 放行分支。
- accepted oracle promotion 对 global linkage audit 字段有单测覆盖。

本轮使用三条只读/分析子任务：
- Fermat：确认提交后工作树里的大量 evidence 改动主要是生成噪声，真实待提交范围是工具和测试文件。
- Ampere：建议优先补 accepted-evidence authoritative route/profile policy，而不是继续扩 translator surface。
- Kepler：指出 validator 还需回查 slice spec 授权；本轮已按该 review 补负例和修复。

已通过命令：
```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_semantic_pass_requires_validation_profile_passed
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_l4_refused_accept_existing_evidence_keeps_generated_draft_blocked validation.tools.test_auto_migrate.AutoMigrateTests.test_l4_refused_accept_existing_evidence_can_be_authoritative_when_requested
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_semantic_pass_allows_l4_refused_route_when_accepted_evidence_binding_is_authoritative validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_semantic_pass_rejects_l4_authoritative_artifacts_without_spec_authorization validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_l4_refused_status_scanner_rejects_draft_and_accepted_artifact_statuses
python -B -m unittest validation.tools.test_real_fdb_calc_crc32_l3_evidence validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence
```

完整相关 Python 回归结果：`Ran 89 tests ... OK`。

下一步建议：
1. 给 real-fdb `fdb_calc_crc32` 生成/绑定真正 accepted C oracle report，保留 `crc32_table`
   global linkage provenance。
2. 在 real-fdb slice spec 上显式选择是否使用
   `claim_boundary.accepted_evidence_authoritative=true`，并绑定第 34 节的 Rust report/diff/negative diff。
3. 继续扩 translator surface 时，再单独处理 `const uint8_t *p`、`const void *` cast、`size--`、
   `*p++`、`crc32_table[...]` 和 bit operations。

## 36. 2026-06-26 real-fdb accepted evidence semantic pass

本轮把 `flashdb/real-fdb-calc-crc32` 从 fail-closed evidence 推进到 accepted evidence
语义通过，但仍不声称 generated Rust draft 本身通过。translator route 仍是 `L4/refused`，
语义通过绑定到显式 accepted C oracle / Rust report / diff / negative diff / unsafe evidence。

核心改动：
- 新增 accepted C oracle 输入：
  `validation/evidence/flashdb/l3-real-fdb-calc-crc32-c-oracle.json`
  - `status=passed`
  - `toolchain_status=C_ORACLE_GENERATED`
  - `semantic_pass=true`
  - 绑定两个 fixture case 的 `return_code`
- 更新 `validation/slice-specs/flashdb-real-fdb-calc-crc32.json`
  - `claim_boundary.accepted_evidence_authoritative=true`
  - `fixture_contract.c_oracle` 绑定新 root C oracle
  - `fixture_contract.rust_report/diff/negative_diff` 绑定第 34 节生成的 root evidence
  - `fixture_contract.unsafe_scan/unsafe_ledger` 绑定 auto-translation 目录已有 passed evidence
- 刷新 `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/`
  - auto manifest 现在是 `status=accepted_evidence_bound`
  - L3 evidence manifest `semantic_pass=true`
  - validation profile `profile=L4-accepted-evidence`, `status=passed`
  - route 仍为 `L4/refused`
  - promoted c-oracle status 为 `C_ORACLE_GENERATED`
  - promoted c-oracle 保留 `crc32_table` 的 `global_linkage_requirements`、
    `harness_contract.global_dependencies`、`compile_command_draft`、`compile_execution`
- `validation/tools/validate_auto_translation_evidence.py`
  - 允许 promoted accepted oracle wrapper 的顶层 `toolchain_status=C_ORACLE_GENERATED`
    与 embedded draft compile provenance `COMPILE_SUCCEEDED_NOT_ORACLE` 并存。
  - embedded compile/harness execution 仍必须 `semantic_pass=false`。
  - WSL provenance 校验支持 Windows 8.3 短路径和 repo-relative path 到 `/mnt/<drive>/...`
    的等价映射，避免 `ADMINI~1` 这类路径导致误报。
- `validation/tools/test_auto_migrate.py`
  - 新增 real-fdb 端到端测试：运行 `auto_migrate.py --accept-existing-evidence` 到临时 out-root，
    断言 manifest/profile/oracle/global linkage，并继续调用 validator `--require-semantic-pass`。

TDD 红绿过程：
- 初始红灯：
  `--accept-existing-evidence requires fixture_contract.c_oracle`
- 绑定 accepted evidence 后，validator 红灯：
  `oracle harness compile execution toolchain status drift`
- 修 promoted wrapper 后，validator 红灯：
  `oracle harness harness execution toolchain provenance drift`
- 补 WSL 等价路径后，real-fdb 端到端测试通过。

已通过命令：
```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_accept_existing_evidence_reaches_authoritative_semantic_pass
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_accept_existing_evidence_reaches_authoritative_semantic_pass validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_wsl_compile_execution_missing_execution_argv validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_wsl_compile_execution_launcher_drift validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_compile_execution_skipped_spoofing_generated_toolchain
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --accept-existing-evidence
python -B validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass
python -B -m unittest validation.tools.test_real_fdb_calc_crc32_l3_evidence validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence
cargo fmt --manifest-path validation/l2_slices/Cargo.toml -- --check
cargo test --manifest-path validation/l2_slices/Cargo.toml
git diff --check -- validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32 validation/evidence/flashdb/l3-real-fdb-calc-crc32-c-oracle.json validation/slice-specs/flashdb-real-fdb-calc-crc32.json validation/tools/test_auto_migrate.py validation/tools/validate_auto_translation_evidence.py
```

完整相关 Python 回归结果：`Ran 90 tests ... OK`。

并行审查结论：
- Pasteur：确认 root `rust_report/diff/negative_diff` 可作为 accepted binding 输入；
  auto `unsafe_scan/unsafe_ledger` 可复用；原 auto `final_verification` 不应手工绑定，应由 accepted
  run 重新生成。
- Lovelace：确认 accepted C oracle 原始 report 最小条件是 `status=passed/expected_failed`、
  `toolchain_status=C_ORACLE_GENERATED`、`source_commit` 匹配；promoted wrapper 必须保留
  real-fdb 的 `crc32_table` global linkage audit 字段。

下一步建议：
1. 如果要减少 evidence 体积，后续可把 accepted C oracle 的 provenance 从手工 root JSON
   提升为可重复生成脚本，但不要改变当前 semantic boundary。
2. 继续扩 translator surface 时，仍应独立处理 `const void*` cast、byte cursor post-increment、
   `size--` 和 `crc32_table[...]`；当前 semantic pass 不代表 translator 已支持这些语法。
3. 提交时只 stage real-fdb evidence/spec/tool/test/CONTEXT 这一组；旧 demo/l2/libuv evidence
   仍有换行/生成噪声，继续不要带入提交。

## 37. 2026-06-26 real-fdb accepted C oracle root report generation

本轮承接第 36 节的第一条下一步，把 root accepted C oracle 从手工 JSON 推进为
`emit_reports` 可重复生成的 report，同时不改变 semantic boundary：语义通过仍绑定到 accepted
C oracle / Rust report / diff / negative diff / unsafe evidence；generated Rust draft 仍是候选，
translator route 仍为 `L4/refused`。

核心改动：
- `validation/l2_slices/src/bin/emit_reports.rs`
  - `emit_real_fdb_calc_crc32()` 现在会同时生成：
    - `validation/evidence/flashdb/l3-real-fdb-calc-crc32-c-oracle.json`
    - `validation/evidence/flashdb/l3-real-fdb-calc-crc32-rust-report.json`
    - `validation/evidence/flashdb/l3-real-fdb-calc-crc32-diff.json`
    - `validation/evidence/flashdb/l3-real-fdb-calc-crc32-negative-diff.json`
  - root C oracle 新增 `generator` 和 `command` provenance：
    - `validation/l2_slices/src/bin/emit_reports.rs::emit_real_fdb_calc_crc32`
    - `cargo run --manifest-path validation/l2_slices/Cargo.toml --bin emit_reports`
  - root C oracle 仍保留 `toolchain_status=C_ORACLE_GENERATED`、`semantic_pass=true`、
    `status=passed` 和两个 fixture case 的 `return_code`。
- `validation/tools/test_real_fdb_calc_crc32_l3_evidence.py`
  - 同一个 `emit_reports` 回归测试现在会读取 root C oracle，并断言 target/slice/status、
    `semantic_pass`、`toolchain_status`、`generator`、`command` 和两个 return code。
- 刷新 `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/`
  - accepted evidence binding 中 root C oracle 的 sha256 更新为
    `70c3bcef167c436abcd0eb7512a65da5097628ab06ad28a3fe748936a7ff501a`。
  - auto manifest 仍为 `status=accepted_evidence_bound`，validator 仍报告 `semantic_pass=true`。

TDD 红绿过程：
- 红灯：
  `KeyError: 'generator'`
- 绿灯：
  `python -B -m unittest validation.tools.test_real_fdb_calc_crc32_l3_evidence.RealFdbCalcCrc32L3EvidenceTests.test_emit_reports_records_real_fdb_calc_crc32_replay_and_diff_gates`
  通过。

本轮并行只读审查结论：
- Franklin：确认 root `c-oracle/rust-report/diff/negative-diff` 现在都由
  `emit_real_fdb_calc_crc32()` 生成；建议后续如需继续增强，可把 `fixture_sha256`、
  `source_file_hashes`、`source_span_sha256`、`crc32_table` global dependency、
  harness/compile provenance 作为非循环 provenance 对象加入 root C oracle。
- Epicurus：确认 translator 路线仍 blocked/refused，关键表面积是 `const uint8_t *p`、
  `const void*` 到 byte buffer、`while (size--)`、`*p++`、`crc32_table[...]`
  和全局表内容输入。该方向应作为独立 translator capability change 处理，不应混入本轮 evidence
  生成化提交。

已通过命令：
```powershell
python -B -m unittest validation.tools.test_real_fdb_calc_crc32_l3_evidence.RealFdbCalcCrc32L3EvidenceTests.test_emit_reports_records_real_fdb_calc_crc32_replay_and_diff_gates
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --accept-existing-evidence
python -B validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass
python -B -m unittest validation.tools.test_real_fdb_calc_crc32_l3_evidence validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence
cargo fmt --manifest-path validation/l2_slices/Cargo.toml -- --check
cargo test --manifest-path validation/l2_slices/Cargo.toml
```

完整相关 Python 回归结果：`Ran 90 tests ... OK`。

下一步建议：
1. 若继续增强 accepted C oracle provenance，按 Franklin 建议补非循环 provenance 字段，并继续用
   `emit_reports` 单测先红后绿。
2. 若转向 translator，要先做一个窄的 byte-cursor CRC loop capability change，不要泛化到完整 C
   pointer side-effect 表达式。
3. 提交时继续只 stage real-fdb auto evidence、root C oracle、`emit_reports.rs`、对应 Python 测试和
   `CONTEXT.md`；旧 demo/l2/libuv evidence 噪声仍不带入。

## 38. 2026-06-26 real-fdb root C oracle non-cyclic provenance

本轮承接第 37 节第一条下一步，继续增强 root accepted C oracle 的 provenance，但仍保持非循环边界：
root C oracle 不写入自身 sha256，也不写入包含自身 sha256 的 status/version/evidence manifest hash。
这些 hash 仍由外层 auto evidence 绑定。

核心改动：
- `validation/l2_slices/src/bin/emit_reports.rs`
  - `emit_real_fdb_calc_crc32()` 现在会读取：
    - `validation/slice-specs/flashdb-real-fdb-calc-crc32.json`
    - `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-c-oracle-status.json`
  - root C oracle 新增 `provenance` 对象：
    - `fixture_sha256`
    - `source_file_hashes`
    - `source_span_sha256`
    - `global_dependencies`，保留 `crc32_table` linkage/hash/span
    - `harness_draft_ref`
    - `compile_execution` 摘要：`status`、`semantic_pass`、`toolchain_adapter`、
      `toolchain_status_after_attempt`
    - `evidence_refs` 仅记录 path，不记录这些 ref 的 sha256
    - `cycle_boundary` 明确说明 root self-hash 由外层 auto evidence 记录
  - 新增 `required_json_value()` helper：必需 provenance 字段缺失时 fail closed。
- `validation/tools/test_real_fdb_calc_crc32_l3_evidence.py`
  - 先红后绿新增 root C oracle provenance 断言。
  - 明确断言 `provenance` 不包含 `c_oracle_sha256`，避免把 root 文件自身 hash 写回自身。
- 刷新 `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/`
  - accepted evidence binding 中 root C oracle sha256 更新为
    `1ee9b240ea08cb1d32b2cb8f1c3108bdbc826e6994192a63034302eb1d063334`。
  - validator 仍报告 `semantic_pass=true`。

TDD 红绿过程：
- 红灯：
  `KeyError: 'provenance'`
- 绿灯：
  `python -B -m unittest validation.tools.test_real_fdb_calc_crc32_l3_evidence.RealFdbCalcCrc32L3EvidenceTests.test_emit_reports_records_real_fdb_calc_crc32_replay_and_diff_gates`
  通过。

本轮并行只读审查结论：
- Pascal：确认当前 provenance 字段都是非循环来源；不要把 `c_oracle_sha256` 或
  `c_oracle_status/version/evidence-manifest` 的 sha256 写回 root C oracle。
- Erdos：确认 auto evidence 是按 root C oracle 实际 sha256 绑定，而不是复制 provenance 全量；
  本轮只加可选 provenance 不需要改 schema/validator。若后续要让 validator 主动 rehash root
  accepted oracle 文件，需要另起一轮加负例测试和 validator 检查。

已通过命令：
```powershell
python -B -m unittest validation.tools.test_real_fdb_calc_crc32_l3_evidence.RealFdbCalcCrc32L3EvidenceTests.test_emit_reports_records_real_fdb_calc_crc32_replay_and_diff_gates
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --accept-existing-evidence
python -B -m unittest validation.tools.test_real_fdb_calc_crc32_l3_evidence validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence
cargo fmt --manifest-path validation/l2_slices/Cargo.toml
cargo fmt --manifest-path validation/l2_slices/Cargo.toml -- --check
cargo test --manifest-path validation/l2_slices/Cargo.toml
python -B validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass
```

完整相关 Python 回归结果：`Ran 90 tests ... OK`。

下一步建议：
1. 如果继续强化 accepted evidence，可以按 Erdos 的建议增加 validator 对
   `accepted_evidence_binding.paths.c_oracle` / `c-oracle-status.accepted_oracle` 的实际文件 hash
   rehash 检查，并补伪造 hash 负例。
2. 如果转向 translator，仍单独做受限 byte-cursor CRC loop capability change。
3. 提交时仍只 stage real-fdb auto evidence、root C oracle、`emit_reports.rs`、对应 Python 测试和
   `CONTEXT.md`。

## 39. 2026-06-26 accepted C oracle root hash fail-closed

本轮承接第 38 节第一条下一步，把 `--require-semantic-pass` 路径下的 accepted C oracle
绑定从“校验 c-oracle-status wrapper”收紧为“继续 rehash root accepted C oracle 文件”。这防止
`c-oracle-status.accepted_oracle.sha256` 或
`auto_manifest.accepted_evidence_binding.path_sha256.c_oracle` 指向的 root oracle 内容漂移后，
semantic-pass 仍误报通过。

核心改动：
- `validation/tools/validate_auto_translation_evidence.py`
  - 在 `validate_semantic_pass()` 校验 promoted accepted oracle wrapper 后调用
    `validate_accepted_c_oracle_file_binding()`。
  - 新 helper 会读取 `l3-*-auto-translation-manifest.json`，要求：
    - `c-oracle-status.accepted_oracle.path/sha256/status` 存在且 `status=passed`
    - `accepted_evidence_binding.paths.c_oracle` 存在
    - `accepted_evidence_binding.path_sha256.c_oracle` 存在
    - 两个 path 解析后指向同一文件
    - 实际 root C oracle 文件 sha256 同时匹配 `accepted_oracle.sha256` 和
      `path_sha256.c_oracle`
  - 普通 schema-only validator 不受影响；该检查只随 `--require-semantic-pass` 运行。
- `validation/tools/test_validate_auto_translation_evidence.py`
  - 新增 `test_semantic_pass_rejects_root_accepted_c_oracle_sha_drift`。
  - 测试用 `auto_migrate.py --accept-existing-evidence --out-root <temp>` 生成临时 real-fdb
    accepted evidence，再复制 root C oracle 到临时目录，记录旧 sha 后篡改
    `cases[0].return_code`，断言 validator 拒绝并报告 `accepted c_oracle` / `sha256`。

TDD 红绿过程：
- 红灯：
  `test_semantic_pass_rejects_root_accepted_c_oracle_sha_drift` 初始失败，validator 返回 0。
- 绿灯：
  增加 root C oracle rehash 后，该负例通过；相邻 L4 authoritative 正例仍通过。

本轮并行只读审查结论：
- Mill：确认 hook 应放在 `validate_semantic_pass()` 的 c_oracle 校验后，不应塞入通用
  `load_ref()`；root C oracle 是 semantic-pass 证据链的一环，只应在
  `--require-semantic-pass` 下展开校验。
- Anscombe：确认最小负例就是临时复制 root accepted C oracle，篡改 `cases[0].return_code`
  且不刷新 stale hash；预期错误可宽断言 `accepted c_oracle` 和 `sha256`。

已通过命令：
```powershell
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_semantic_pass_rejects_root_accepted_c_oracle_sha_drift
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_semantic_pass_rejects_root_accepted_c_oracle_sha_drift validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_semantic_pass_allows_l4_refused_route_when_accepted_evidence_binding_is_authoritative
python -B validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass
python -B -m unittest validation.tools.test_validate_auto_translation_evidence validation.tools.test_auto_migrate validation.tools.test_real_fdb_calc_crc32_l3_evidence
cargo fmt --manifest-path validation/l2_slices/Cargo.toml -- --check
cargo test --manifest-path validation/l2_slices/Cargo.toml
```

完整相关 Python 回归结果：`Ran 91 tests ... OK`。

当前核心翻译功能状态：
- 真实 FlashDB `fdb_calc_crc32` 切片已经有 accepted evidence 语义通过，验证器能 fail-closed
  检查 root C oracle / Rust report / diff / negative diff / unsafe / final verification 证据链。
- 这仍不代表 generated Rust draft 本身已通过；route 仍是 `L4/refused`，semantic pass 绑定到
  显式 accepted evidence。
- translator 本体下一步仍应单独做受限 byte-cursor CRC loop capability change，重点是
  `const uint8_t *p`、`const void *` cast、`size--`、`*p++` 和 `crc32_table[...]`。

下一步建议：
1. 若继续 accepted evidence hardening，可补 cache identity 或 final verification 对 root accepted
   oracle path 的更多交叉校验。
2. 若转向核心 translator，先写 byte-cursor CRC loop capability 的红测和最小实现，不要直接泛化到完整
   C pointer side-effect 表达式。

## 40. 2026-06-26 real-fdb byte-cursor CRC translator candidate

本轮承接第 39 节的核心 translator 下一步，做受限 FlashDB `fdb_calc_crc32` byte-cursor CRC loop
能力，不泛化到完整 C pointer side-effect 表达式。目标是让 generated Rust draft 能作为候选生成并通过
Rust compile check；不声称 generated draft 已语义通过。

核心改动：
- `crates/c2r-translator/src/lib.rs`
  - 在通用 unsupported 检测前加入严格 recognizer：
    `uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size)`、
    `const uint8_t *p`、`p = (const uint8_t *)buf`、`while (size--)`、
    `crc32_table[(crc ^ *p++) & 0xFF] ^ (crc >> 8)`。
  - 增加 C 类型映射：`uint8_t -> u8`、`size_t -> usize`、`const void* -> &[u8]`、
    `const uint8_t* -> &[u8]`。
  - 为该受限模式生成安全 Rust draft：
    `pub fn fdb_calc_crc32(mut crc: u32, buf: &[u8], size: usize) -> u32`，
    用 `usize` cursor 和 `crc32_update_byte()` bitwise helper 替代 `crc32_table` 与 `*p++`。
  - pointer graph 记录 `buf` 为 `&[u8]` borrowed input，read effect 包含 `*p++`，
    boundary decision 包含 `byte_cursor_post_increment_read`。
- `validation/tools/auto_migrate.py`
  - 将 `byte_cursor_post_increment_read` 归一化为 input buffer decision，并把 `buf` 的
    length companion 推断为 `size`。
  - 增加 rule mapping：`byte-cursor-post-increment-read`。
  - 修正 `--accept-existing-evidence` 的优先级：即使 translator 现在能生成 L1 candidate，
    显式 accepted evidence 运行仍强制走 `L4/refused` + `L4-accepted-evidence`，
    保持旧 semantic boundary 不漂移。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `flashdb_crc32_byte_cursor_loop_generates_safe_slice_boundary_and_rules`。
- `validation/tools/test_auto_migrate.py`
  - 新增 real-fdb candidate-only 端到端测试，断言：
    `status=candidate_generated`、route `L1/recorded/tier1`、plan `draft_generated`、
    pointer node 为 `buffer/input/size`、draft 不含 `*p++`/`crc32_table`、`rust_check=passed`。

TDD 红绿过程：
- 红灯：
  - translator 单测最初失败在 `const uint8_t *p`、`size--`、`*p++` unsupported。
  - auto_migrate 目标测试最初返回 `candidate_refused`。
- 绿灯：
  - 受限 recognizer + Rust emitter + pointer normalization 后，两条目标测试均通过。
  - 回归中发现 `--accept-existing-evidence` 正例不再 authoritative；根因是 route 已变 L1，
    原 override 只接受已有 L4/refused。修正为显式 accepted evidence 请求强制 authoritative route 后通过。

本轮并行只读审查结论：
- Godel：确认 translator 主入口、route 分级和 real-fdb 当前拒绝点；建议最小写集限制在
  translator、auto_migrate 归一化和对应测试，不刷新 repo 内 real-fdb evidence。
- Galileo：确认当前语义通过是 accepted evidence authoritative，而非 generated draft semantic pass；
  若只生成候选，应保持 `semantic_pass=false`，route 用非 L4 candidate-only 状态。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml flashdb_crc32_byte_cursor_loop_generates_safe_slice_boundary_and_rules
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_byte_cursor_translator_generates_candidate_route
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml
python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence validation.tools.test_real_fdb_calc_crc32_l3_evidence
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
python -B validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle
```

完整结果：
- translator crate：`33 passed`。
- Python 相关回归：`Ran 92 tests ... OK`。
- 当前仓库 accepted evidence validator：`semantic_pass=true`。
- 临时 candidate-only auto_migrate：`status=candidate_generated`、route `L1`、`rust_check=passed`、
  `semantic_pass=false`。

当前核心翻译功能状态：
- real-fdb `fdb_calc_crc32` 的 generated Rust draft 现在能生成候选并通过 Rust compile check。
- candidate-only 路径不再是 `L4/refused`；它是 `L1/recorded`，但仍不是 semantic pass。
- `--accept-existing-evidence` 路径仍保持 `L4/refused` + accepted evidence authoritative，
  用于现有 `--require-semantic-pass` 语义通过声明。

下一步建议：
1. 若要把 generated draft 从 candidate 推进到 semantic pass，需要补真实 C oracle/Rust replay/diff/
   negative diff/unsafe/final verification gates，并让 profile/manifest/final 同步引用 generated draft。
2. 若继续扩 translator 表面积，先沿此模式小步扩展相近 byte cursor 形态，不要一次泛化所有
   `++/--` value semantics。
3. 提交时只 stage `crates/c2r-translator/*`、`validation/tools/auto_migrate.py`、
   `validation/tools/test_auto_migrate.py` 和 `CONTEXT.md`；旧 demo/l2/libuv evidence 噪声仍不带入。

## 41. 2026-06-26 real-fdb generated Rust replay gate

本轮承接第 40 节第一条下一步，但只推进 generated draft semantic pass 的第一块：
让 real-fdb `fdb_calc_crc32` generated Rust draft 执行 fixture replay，并把 auto evidence 下的
Rust report 从 draft/incomplete 推到 `passed` 或 `failed`。这仍不是 full semantic pass：
`semantic_pass=false`、`generated_draft_semantic_pass=false` 继续保持，C oracle、schema diff、
negative diff、unsafe、final verification gates 仍未完成。

核心改动：
- `validation/tools/auto_migrate.py`
  - `generate_rust_replay_test_draft()` 现在对 `return_code` fixture case 生成真实调用：
    `let actual = fdb_calc_crc32(case.crc, case.buf, case.size);`
    并断言 `actual == case.return_code`，删除旧的 TODO/panic draft-only 逻辑。
  - 新增 `run_generated_rust_replay()`：
    - 只在 `rust_check.status == "passed"` 且 plan 含 `crc32-byte-cursor-loop` 时执行。
    - 在临时目录拼接 generated `rust-draft.rs` 与 replay test，用 `rustc --test` 编译并运行。
    - 把结果写回 `l3-*-test-translation-generated.json`：
      `status=passed/failed`、`generated_draft_replay_pass=true/false`、
      `generated_draft_semantic_pass=false`、`replay_execution` 日志引用。
  - 非 accepted 分支的 `write_l3_candidate_supporting_evidence()` 现在会消费 replay 结果：
    - replay 通过时 `l3-*-rust-report.json.status=passed`
    - replay 失败时 `status=failed`
    - 两种情况都保持 `semantic_pass=false`
    - `diff.status` 仍为 `incomplete`，但 `required_inputs.rust_report_actual_status`
      会记录 `passed` 或 `failed`。
  - 新增 `generated_rust_report_cases()`，让 generated Rust report 带上与 root rust-report
    对齐的 fixture `cases[]`。
- `validation/tools/test_auto_migrate.py`
  - 更新 replay draft 单测：现在期望真实 API call，而不是 TODO/panic。
  - 新增正例 `test_real_fdb_calc_crc32_generated_replay_executes_candidate_fixture`。
  - 新增负例 `test_real_fdb_calc_crc32_generated_replay_failure_stays_non_semantic`：
    临时篡改第二个 fixture `return_code`，要求 replay/rust-report failed，且 manifest 仍不 claim semantic pass。

TDD 红绿过程：
- 红灯：
  - replay draft 仍缺 `fdb_calc_crc32(case.crc, case.buf, case.size)` 调用。
  - real-fdb generated replay 正例初始只有 TODO/panic，不能写 `status=passed`。
  - 负例初始缺 `cases[]`，且 replay 失败仍写 `rust-report.status=incomplete`。
- 绿灯：
  - 删除旧 panic、加入 generated replay runner 和 Rust report 状态消费后，三条目标测试通过。

本轮并行只读审查结论：
- Avicenna：建议最小路径是临时 Rust runner 调用 generated draft，写 auto-translation 下的
  rust-report，同时只声明 `generated_draft_replay_pass=true`，不要复用 accepted evidence 语义。
- Carver：确认 full generated semantic pass 还需要非 L4 generated path、profile/manifest/final、
  draft binding refs、schema diff/negative diff/unsafe/final gates 同步；本轮不应只改 boolean 直接 claim。

已通过命令：
```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_rust_replay_draft_enumerates_bound_fixture_cases_without_semantic_claim validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_generated_replay_executes_candidate_fixture validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_generated_replay_failure_stays_non_semantic
python -B -m unittest validation.tools.test_auto_migrate
python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence validation.tools.test_real_fdb_calc_crc32_l3_evidence
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle
python -B validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --require-semantic-pass
```

完整结果：
- `validation.tools.test_auto_migrate`：`Ran 41 tests ... OK`。
- 相关 Python 回归：`Ran 94 tests ... OK`。
- 临时 candidate-only auto_migrate：`status=candidate_generated`、route `L1`、
  `rust_check=passed`、`generated_draft_replay_pass=true`、`semantic_pass=false`。
- 当前仓库 accepted evidence validator 仍为 `semantic_pass=true`。

当前核心翻译功能状态：
- generated Rust draft 已经不只是 compile pass；它还能跑 real-fdb fixture replay，并生成 passed Rust report。
- full generated draft semantic pass 仍未完成，因为 C oracle、schema diff、negative diff、unsafe、
  final verification 还没有绑定到 exact generated draft。
- accepted evidence authoritative 路径未改变，仍是当前仓库 `--require-semantic-pass` 的语义通过来源。

下一步建议：
1. 给 generated candidate 增加 schema diff gate：当 C oracle 可用且 generated Rust report passed 时，
   比较 C oracle 与 generated Rust report 的 `return_code` cases，但仍不要复用 root accepted diff。
2. 然后补 negative diff 和 final verification，使 generated path 最终能独立进入
   `generated_draft_semantic_pass=true`。
3. 提交时只 stage `validation/tools/auto_migrate.py`、`validation/tools/test_auto_migrate.py`
   和 `CONTEXT.md`；旧 demo/l2/libuv evidence 噪声仍不带入。

## 42. 2026-06-26 typed IR crc32 emitter bridge

本轮承接第 41 节之后的 translator 架构下一步，但按收窄版执行：只给 Rust translator
增加 feature-gated typed IR emitter 地基，不接 libclang、不改 Python pipeline、不刷新仓库 evidence，
也不改变 generated draft 的 semantic-pass 边界。

核心改动：
- `crates/c2r-translator/Cargo.toml`
  - 新增 `[features]`：`default = []`、`typed-ir = []`。
  - 默认构建不启用 typed IR，保持现有字符串 recognizer 路径。
- `crates/c2r-translator/src/typed_ir.rs`
  - 新增 typed IR 数据结构：`IrType`、`IrTypeKind`、`IrExpr`、`IrStmt`、`IrFunction`、
    `IrParam`、`SourceSpan`。
  - 表达式层保留显式节点：`Binary`、`Unary(BitNot)`、`Cast { implicit }`、`Index`、
    `IncDec`、`Deref` 等，为后续 libclang lowering 承接 `Cast(implicit)`、`*p++`、
    `size--`、`crc32_table[...]`。
  - 新增 `emit_rust_from_ir()`，当前只 fail-closed 支持 `fdb_calc_crc32` byte-cursor CRC
    expression tree；非匹配函数返回 `IrEmitError`，不猜测。
  - 新增 `crc32_byte_cursor_function()` 作为当前字符串 recognizer 到 typed IR emitter 的
    临时 bridge；后续 libclang 前端应直接 lower 出等价 `IrFunction`。
- `crates/c2r-translator/src/lib.rs`
  - `typed_ir` 模块只在 `--features typed-ir` 下导出。
  - `emit_crc32_byte_cursor_rust()` 在 feature 开启时先构造 typed IR 并调用
    `typed_ir::emit_rust_from_ir()`；bridge 必须成功，不再静默回落后继续记录 typed IR rule。
  - `record_crc32_byte_cursor_rules()` 在 feature 开启时额外记录
    `typed-ir-crc32-emitter`，用于证明 crc32 candidate 的 Rust draft 开始经过 typed IR
    emitter bridge。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `typed_ir_emits_flashdb_crc32_without_string_recognizer`，直接构造 typed expression tree，
    断言 emitter 产出安全 Rust：`buf: &[u8]`、`let byte = buf[p]`、
    `crc32_update_byte(crc, byte)`，且不泄漏 `*p++` 或 `crc32_table`。
  - 新增 `typed_ir_rejects_crc32_loop_with_extra_top_level_term`，证明在合法 crc32 RHS 外层
    额外 XOR 字面量时必须 fail-closed，不能被当成标准 crc32 模板接受。
  - 现有 `flashdb_crc32_byte_cursor_loop_generates_safe_slice_boundary_and_rules` 在
    `--features typed-ir` 下断言 rule ids 包含 `typed-ir-crc32-emitter`。

TDD 红绿过程：
- 红灯 1：
  `cargo test --manifest-path crates/c2r-translator/Cargo.toml typed_ir_emits_flashdb_crc32_without_string_recognizer`
  初始失败：`E0432 could not find typed_ir in c2r_translator`。
- 绿灯 1：
  增加 `typed_ir.rs` 和 `pub mod typed_ir` 后，direct typed IR emitter focused test 通过。
- 红灯 2：
  `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir flashdb_crc32_byte_cursor_loop_generates_safe_slice_boundary_and_rules`
  初始失败：`E0425 cannot find function crc32_byte_cursor_function in module typed_ir`。
- 绿灯 2：
  增加 `crc32_byte_cursor_function()` bridge 后，`--features typed-ir` 的 crc32 focused tests 通过。
- 红灯 3：
  `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir typed_ir_rejects_crc32_loop_with_extra_top_level_term`
  初始失败：偏宽 matcher 把额外 top-level XOR 项也接受并发出标准 crc32 Rust。
- 绿灯 3：
  将 typed IR crc32 matcher 收紧为顶层 `table_lookup ^ (crc >> 8)`，并让 table index 精确匹配
  `(crc ^ *p++) & 0xFF`；负例通过，合法 crc32 focused tests 仍通过。

本轮并行只读审查结论：
- Feynman：建议第一刀加 `typed-ir` feature gate，默认不破坏旧 recognizer；typed IR emitter
  与旧 `emit_crc32_byte_cursor_rust` 使用同一输出契约，证据 schema 暂不扩展。
- Archimedes：建议本轮不改 Python。`write_translator_spec()` 目前只传 `c_source`/build profile；
  真实 TU 的 `source_root/source_file/compile_commands` contract 应单独定义并测试，且 generated
  path 必须继续保持 `semantic_pass=false`。
- Parfit：代码审查指出两个 Important：`typed-ir-crc32-emitter` rule 不能和实际 bridge 成功脱节，
  typed IR matcher 不能用宽松 contains 逻辑接受额外表达式项。本轮已按负例修正。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir crc32
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_generated_replay_executes_candidate_fixture validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_generated_replay_failure_stays_non_semantic
```

完整结果：
- 默认 translator crate：`33 passed`。
- `--features typed-ir` translator crate：`35 passed`。
- Python generated replay 正负例：`Ran 2 tests ... OK`。
- `cargo fmt --check` 通过。

当前核心翻译功能状态：
- 默认路径行为不变：现有 strict crc32 string recognizer 仍可生成 L1 candidate，semantic pass
  仍不来自 generated draft。
- `--features typed-ir` 路径下，crc32 candidate 的 Rust draft 已开始经过 typed IR emitter bridge；
  这只是 emitter 地基，不是 libclang lowering，也不是 generated semantic pass。
- Python evidence pipeline、accepted evidence authoritative 路径、`semantic_pass=false` 边界均未改变。

下一步建议：
1. 定义真实 TU/libclang 输入 contract：`source_root`、`source_file`、`compile_commands` 或完整
   compiler args、source/global dependency hash；保持 `c_source` fallback。
2. 为 translator spec 元数据透传写 Python 临时 out-root 测试，再扩 `SliceSpec` 可选字段。
3. 新增 `clang-frontend` feature 和 libclang lowering skeleton，让真实 `fdb_calc_crc32` lower 出
   与当前 bridge 等价的 `IrFunction`。
4. generated semantic pass 仍按第 41 节继续：先 schema diff gate，再 negative diff/final verification，
   不直接删除 accepted `validation/l2_slices/src/fdb_calc_crc32.rs`。

## 43. 2026-06-26 real TU translator-input metadata contract

本轮承接第 42 节第一条下一步：定义并透传真实 TU/libclang 后续所需的输入元数据，但仍不接
libclang、不改变 translator 当前 `c_source` fallback、不刷新仓库 evidence，也不改变 generated draft
的 semantic-pass 边界。

核心改动：
- `validation/tools/auto_migrate.py`
  - `write_translator_spec()` 保留原有 `function_name/c_source` fallback：
    顶层 `c_source` → `c_boundary.signatures[0].c_source` → `c_boundary.c_source`。
  - 新增真实源输入 metadata 透传：
    - `source_root` 来自 `source.source_root`
    - `source_files` 来自 `c_boundary.files[]`，保留 `path/role/sha256`
    - `source_file` 取 `role=source` 的主文件，否则取第一个 `c_boundary.files[]`
    - `source_file_hashes` 来自 `source.source_file_hashes`
    - `function_source_span` 来自匹配函数签名的 `source_span`
  - `source_file_hashes` 复用 cache identity 的合并逻辑：如果 `source.source_file_hashes` 缺失，
    也会从 `c_boundary.files[].sha256` 或可解析的真实文件补齐，避免 translator input 与 cache
    provenance 不一致。
  - 只在 slice 明确提供 `build_profile.compile_commands` 或 `compile_commands_path` 时写
    `compile_commands`；当前 real-fdb 的 `compiler_command_source=CMakeLists.txt` 只保留在
    `build_profile.compiler_command_source`，不伪装成 compile database。
- `validation/tools/test_auto_migrate.py`
  - 新增 `test_real_fdb_calc_crc32_translator_input_records_real_tu_metadata`，用临时
    `--out-root <temp>` 运行 real-fdb candidate，读取临时
    `l3-real-fdb-calc-crc32-translator-input.json`，断言上面的 metadata 都被写出，并断言
    `compile_commands` 不存在。
  - 新增 `test_translator_input_source_file_hashes_fall_back_to_c_boundary_files`，证明只有
    `c_boundary.files[].sha256` 时 translator input 仍会写出 `source_file_hashes`。
- `crates/c2r-translator/src/lib.rs`
  - `SliceSpec` 显式接收可选 metadata：
    `source_root`、`source_file`、`source_files`、`source_file_hashes`、
    `function_source_span`、`compile_commands`。
  - 新增 `SourceFileRef` 和 `SourceSpanRef`。
  - 这些字段目前只被反序列化和保留，`translate_slice()` 不消费它们，默认翻译行为不变。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `slice_spec_deserializes_real_tu_metadata_without_changing_translation`，证明带真实 TU
    metadata 的 JSON 可反序列化到 `SliceSpec`，且同一个 `c_source` 仍按旧路径正常翻译。
  - 现有 `SliceSpec` struct literal 统一补 `..SliceSpec::default()`，适配新增可选字段。

TDD 红绿过程：
- 红灯 1：
  `python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_translator_input_records_real_tu_metadata`
  初始失败：`KeyError: 'source_root'`，translator input 还没有真实源 metadata。
- 绿灯 1：
  增加 `c_boundary_source_files()`、`function_source_span()` 并在 `write_translator_spec()` 写入
  metadata 后，该 Python 测试通过。
- 红灯 2：
  `cargo test --manifest-path crates/c2r-translator/Cargo.toml slice_spec_deserializes_real_tu_metadata_without_changing_translation`
  初始失败：`SliceSpec` 没有 `source_root/source_file/source_files/source_file_hashes/
  function_source_span/compile_commands` 字段。
- 绿灯 2：
  给 `SliceSpec` 增加 serde-default 的可选 metadata 字段和对应结构后，该 Rust 测试通过。
- 红灯 3：
  `python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_translator_input_source_file_hashes_fall_back_to_c_boundary_files`
  初始失败：`KeyError: 'source_file_hashes'`，translator input 未复用 cache identity 的 hash fallback。
- 绿灯 3：
  `write_translator_spec()` 改为调用既有 `source_file_hashes(spec)` 后，该测试通过。

本轮并行只读审查结论：
- Banach：确认 `write_translator_spec()` 当前只写 `c_source`/build profile；real-fdb slice 的真实源
  信息来自 `source.source_root`、`source.source_file_hashes`、`c_boundary.files[]` 和签名
  `source_span`；当前 `compiler_command_source` 是 CMakeLists provenance，不应伪装为
  `compile_commands`。
- Socrates：确认 `c2r_translate` 通过 serde 直接读取 `SliceSpec`，新增 Option/default 字段无需改
  CLI；`translate_slice()` 当前只消费 `c_source/function_name/build_profile`，所以 metadata 保留不应
  改变翻译行为。
- Lagrange：代码审查指出 `translator-input.source_file_hashes` 应和 cache identity 的
  `source_file_hashes(spec)` fallback 对齐；本轮已用负例修正。另指出新增 public `SliceSpec`
  字段会影响外部 Rust struct literal 源码兼容；当前 crate 作为仓库内部 CLI/测试消费，仓库内构造点
  已统一补 `..SliceSpec::default()`，JSON 兼容由 serde default 保证。

已通过命令：
```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_translator_input_records_real_tu_metadata
cargo test --manifest-path crates/c2r-translator/Cargo.toml slice_spec_deserializes_real_tu_metadata_without_changing_translation
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_translator_input_source_file_hashes_fall_back_to_c_boundary_files
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_translator_input_records_real_tu_metadata validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_generated_replay_executes_candidate_fixture validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_generated_replay_failure_stays_non_semantic
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
python -B -m unittest validation.tools.test_auto_migrate
python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence validation.tools.test_real_fdb_calc_crc32_l3_evidence
git diff --check -- CONTEXT.md crates/c2r-translator/Cargo.toml crates/c2r-translator/src/lib.rs crates/c2r-translator/src/typed_ir.rs crates/c2r-translator/tests/bounded_translation.rs validation/tools/auto_migrate.py validation/tools/test_auto_migrate.py
```

完整结果：
- 默认 translator crate：`34 passed`。
- `--features typed-ir` translator crate：`36 passed`。
- `validation.tools.test_auto_migrate`：`Ran 43 tests ... OK`。
- 相关 Python 回归：`Ran 96 tests ... OK`。
- `cargo fmt --check` 和 `git diff --check` 均通过。

当前核心翻译功能状态：
- translator input 已具备真实 TU/libclang 后续需要的 source metadata contract，但还没有
  `clang-frontend` 或 libclang lowering。
- Rust `SliceSpec` 已显式保留这些 metadata，后续 libclang 前端可直接消费。
- 默认 generated candidate 行为不变：`semantic_pass=false`，accepted evidence authoritative 路径不变。

下一步建议：
1. 新增 `clang-frontend` feature 和可选 libclang 依赖 skeleton，先做环境探测和 fail-closed fallback，
   不改变默认构建。
2. 在 Rust 侧定义从真实 TU metadata 到 `ClangParseSpec` 的转换，但先只做 dry-run/diagnostic artifact。
3. 再让真实 `fdb_calc_crc32` lower 出与当前 `crc32_byte_cursor_function()` bridge 等价的
   `IrFunction`，通过 typed IR emitter 生成同一 Rust draft。
