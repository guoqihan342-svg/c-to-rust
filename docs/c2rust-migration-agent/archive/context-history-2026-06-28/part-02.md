## 22. 2026-06-26 C oracle harness draft call/compare

本轮继续第 21 节的下一步：真实 C harness 从只写 fixture 路径，推进到对当前最小
`real-fdb-calc-crc32.json` case 生成受限的内联调用和 `return_code` 比较。

### TDD 过程

新增生成器红测：

```powershell
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_oracle_harness_draft_calls_bound_empty_buffer_fixture
```

红测先失败于 harness 仍只有 TODO，缺少：

- `static const uint8_t empty_crc_zero_buf[] = { 0 };`
- `fdb_calc_crc32((uint32_t)0u, empty_crc_zero_buf, (size_t)0u)`
- `if (actual_empty_crc_zero_return_code != (uint32_t)0u)`

### 实现

`validation/tools/auto_migrate.py` 新增了受限 harness 片段生成逻辑：

- 只支持当前已声明签名：
  `uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size);`
- 只在 `behavior_fields == ["return_code"]` 时生成调用和比较。
- 从 fixture path / expected ref 解析 `cases[N]`，读取 `crc`、`buf`、`size` 和
  `return_code`。
- 对不支持的 case 或签名继续输出 TODO/diagnostic，不提升任何 evidence 状态。
- 空 buffer 生成 `static const uint8_t empty_crc_zero_buf[] = { 0 };`，保证即使
  `size=0` 也有稳定地址可传入。

刷新后的 harness draft 现在包含：

```c
static const uint8_t empty_crc_zero_buf[] = { 0 };

uint32_t actual_empty_crc_zero_return_code =
  fdb_calc_crc32((uint32_t)0u, empty_crc_zero_buf, (size_t)0u);

if (actual_empty_crc_zero_return_code != (uint32_t)0u) {
  fprintf(stderr, "empty-crc-zero return_code mismatch: expected 0 got %llu\n",
          (unsigned long long)actual_empty_crc_zero_return_code);
  return 1;
}
```

实际文件中调用保持单行输出，方便单测精确断言：

- `validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/l3-real-fdb-calc-crc32-c-oracle-harness-draft.c`

### 状态边界

刷新命令：

```powershell
python validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json
```

刷新后的状态仍然 fail-closed：

- `oracle.status: DRAFT_GENERATED`
- `oracle.toolchain_status: COMPILE_NOT_EXECUTED`
- `oracle.semantic_pass: false`
- `compile_execution.status: compiler_not_found`
- `compile_execution.toolchain_status_after_attempt: COMPILE_NOT_EXECUTED`
- `fixture_binding.expected_output_status: declared_not_executed`

本轮没有、也不应把任何证据提升为 `C_ORACLE_GENERATED` 或
`accepted_evidence_bound`。

### 并行审查结论

本轮两个 explorer 子智能体均为只读：

- C harness boundary explorer 确认当前最小 C 代码应只内联简单 fixture 输入、调用真实
  C 函数、比较返回值；不支持或缺失字段时必须保留 TODO/diagnostic。
- validator/test coverage explorer 确认 validator 当前绑定 harness sha 和 draft ref，可挡住
  文件漂移，但不证明 harness 已包含 call/compare；因此本轮红测应放在
  `test_auto_migrate.py`，不在 validator 中硬编码 real-fdb 内容。

### 本轮最终验证命令

```powershell
python -B -m unittest validation.tools.test_extract_source_slice validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence
python -B validation/tools/validate_auto_translation_evidence.py --target-id flashdb --slice-id real-fdb-calc-crc32 --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json
rg -n '"path"\s*:\s*null|let _fixture = ''''|"toolchain_status"\s*:\s*"C_ORACLE_GENERATED"|"semantic_pass"\s*:\s*true|"status"\s*:\s*"accepted_evidence_bound"' validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32 validation/l2_slices/fixtures/real-fdb-calc-crc32.json validation/slice-specs/flashdb-real-fdb-calc-crc32.json
openspec validate add-c2rust-baseline-migration-pipeline --strict
openspec validate --all --strict
git diff --check
```

验证结果：

- 66 个 Python 单测通过。
- real-fdb validator 通过，且 `semantic_pass=false`。
- 空 fixture path / 空 replay fixture / 禁止状态扫描无匹配。
- `openspec validate add-c2rust-baseline-migration-pipeline --strict` 通过。
- `openspec validate --all --strict` 37/37 通过。
- `git diff --check` 通过，仅有 Windows CRLF 提示。

下一步建议：

1. 在有 C 编译器的环境下复跑 compile attempt，确认进入 `compile_failed` 或
   `compile_succeeded_not_oracle` 诊断。
2. 将 C harness 从 draft 生成推进到真实执行记录：编译、运行、捕获 stdout/stderr/exit code，
   并仍保持未通过 diff gates 前不提升语义状态。
3. 扩展 fixture case 覆盖非空 buffer，再推动 Rust replay 和 schema-aware diff gates。

## 23. 2026-06-26 compile-success harness execution record

本轮继续第 22 节的下一步，但不依赖本机安装真实 C 编译器：先用 fake compiler
覆盖 `compile_succeeded_not_oracle` 分支，补齐“编译成功后运行 harness 可执行文件并记录结果”的
draft 证据结构。

### TDD 过程

新增生成器测试：

```powershell
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_compile_success_records_harness_execution_without_oracle_claim
```

红测过程分两步暴露问题：

1. Windows 上 `shutil.which("cc")` 能找到临时 `cc.cmd`，但旧实现随后仍执行字面量
   `cc`，`shell=False` 下 `CreateProcess` 找不到该命令。
2. 修正为用解析后的 `compiler_path` 执行后，测试失败于缺少
   `compile_execution.harness_execution`，这是目标红测失败点。

### 实现

`validation/tools/auto_migrate.py` 现在：

- 仍在 JSON 中保留原始 `compile_command_draft.argv` 和 `compile_execution.argv`。
- 实际 subprocess compile 调用使用 `[compiler_path, *argv[1:]]`，让 Windows `cc.cmd`
  以及 POSIX `cc` 都能被执行。
- 仅当 compile returncode 为 0 时解析 `-o <exe>`，运行生成的 harness 可执行文件。
- 将运行结果写入 `compile_execution.harness_execution`，不复用编译器进程的
  `returncode/stdout/stderr`。

新增 nested 字段形态：

```json
"harness_execution": {
  "status": "exited_zero_not_oracle",
  "attempted": true,
  "argv": [".../l3-compile-run-c-oracle-harness-draft.exe"],
  "working_directory": ".../compile-run",
  "executable_path": ".../l3-compile-run-c-oracle-harness-draft.exe",
  "timeout_seconds": 30,
  "semantic_pass": false,
  "returncode": 0,
  "stdout": "...",
  "stderr": "...",
  "diagnostics": [
    "C oracle harness executed, but execution output has not passed oracle diff gates."
  ]
}
```

支持的运行状态只描述进程事实，不能表达 oracle 通过：

- `exited_zero_not_oracle`
- `exited_nonzero_not_oracle`
- `execution_timeout_not_oracle`
- `executable_missing_not_oracle`
- `execution_error_not_oracle`

顶层仍保持：

- `compile_execution.status: compile_succeeded_not_oracle`
- `toolchain_status_after_attempt: COMPILE_SUCCEEDED_NOT_ORACLE`
- `semantic_pass: false`

### Validator gate

新增 validator 红测：

```powershell
python -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_harness_execution_semantic_pass_spoofing
```

红测先证明 validator 会放过 `harness_execution.semantic_pass=true`。实现后
`validate_auto_translation_evidence.py` 增加可选 nested 校验：

- 只有 `compile_succeeded_not_oracle` 可以携带 `harness_execution`。
- `harness_execution.semantic_pass` 必须是 `false`。
- `working_directory` 必须与 compile execution 一致。
- `timeout_seconds`、`stdout/stderr`、`diagnostics`、`argv/executable_path` 和
  `returncode/attempted` 必须与 status 匹配。

### real-fdb 当前状态

已重跑：

```powershell
python validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json
```

当前本机仍无 `cc`，所以 real-fdb evidence 没有进入 compile-success 分支：

- `compile_execution.status: compiler_not_found`
- `compile_execution.attempted: false`
- `toolchain_status: COMPILE_NOT_EXECUTED`
- `semantic_pass: false`
- 未写入 `compile_execution.harness_execution`

### 并行审查结论

本轮两个 explorer 子智能体均为只读：

- execution/status boundary explorer 建议把 harness 运行结果放在
  `compile_execution.harness_execution`，且所有状态都必须带 `_not_oracle` 边界。
- fake compiler test explorer 指出 Windows `cc.cmd` 能被 `shutil.which()` 找到，但原始
  `argv[0]="cc"` 不能直接执行；本轮已修正为用 `compiler_path` 启动。

下一步建议：

1. 在真实 C 编译器环境中重跑 real-fdb compile attempt，验证真实 `compile_failed` 或
   `compile_succeeded_not_oracle + harness_execution` 路径。
2. 若真实 harness 执行成功，再新增 oracle output/diff gate；在 diff 通过前仍不得提升
   `C_ORACLE_GENERATED`。
3. 扩展非空 buffer fixture，避免只覆盖 empty-buffer identity case。

## 24. 2026-06-26 non-empty CRC32 fixture case

本轮继续第 23 节的下一步：扩展 `real-fdb-calc-crc32` 的 fixture 覆盖，避免只验证
empty-buffer identity case。新增的第二个 case 使用标准 CRC32/IEEE check vector
`"123456789" -> 0xCBF43926`，十进制为 `3421780262`。

### TDD 过程

新增实际 fixture 红测：

```powershell
python -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_crc32_fixture_includes_non_empty_check_vector
```

红测先失败于当前 fixture 只有 `empty-crc-zero`，缺少
`ascii-123456789-crc-zero`。

随后更新：

- `validation/l2_slices/fixtures/real-fdb-calc-crc32.json`
- `validation/slice-specs/flashdb-real-fdb-calc-crc32.json`

并把 `test_oracle_harness_draft_calls_bound_empty_buffer_fixture` 扩展为两 case harness
断言，覆盖第二个静态 buffer、函数调用和 `return_code` 比较。

### 新增 fixture case

```json
{
  "id": "ascii-123456789-crc-zero",
  "crc": 0,
  "buf": [49, 50, 51, 52, 53, 54, 55, 56, 57],
  "size": 9,
  "return_code": 3421780262,
  "coverage_kind": "standard_crc32_check_vector",
  "status": "draft_expected_from_standard_crc32_check_vector"
}
```

该值来自标准 CRC32 check vector：

```powershell
python -c "import zlib; print(hex(zlib.crc32(b'123456789') & 0xffffffff)); print(zlib.crc32(b'123456789') & 0xffffffff)"
```

输出：

- `0xcbf43926`
- `3421780262`

FlashDB 源码中的 `fdb_calc_crc32()` 使用 reflected CRC32 table，并对输入 `crc`
执行初始/结束异或；`crc=0`、`buf="123456789"`、`size=9` 与上述 check vector 一致。

### real-fdb evidence 刷新

已重跑：

```powershell
python validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json
```

刷新后：

- `fixture_binding.case_count: 2`
- 第二个 `case_bindings[].expected_outputs: {"return_code": 3421780262}`
- `test-translation-generated.json.source_test_inputs.fixtures[0].operation_count: 2`
- harness draft 包含：
  - `/* fixture cases: 2 */`
  - `static const uint8_t ascii_123456789_crc_zero_buf[] = { 49u, 50u, 51u, 52u, 53u, 54u, 55u, 56u, 57u };`
  - `fdb_calc_crc32((uint32_t)0u, ascii_123456789_crc_zero_buf, (size_t)9u)`
  - `if (actual_ascii_123456789_crc_zero_return_code != (uint32_t)3421780262u)`

### 状态边界

新增非空 case 会覆盖 `crc32_table` 路径，但仍只是 draft fixture/harness 扩展：

- `compile_execution.status: compiler_not_found`
- `toolchain_status: COMPILE_NOT_EXECUTED`
- `semantic_pass: false`
- 无 `compile_execution.harness_execution`
- 未出现 `C_ORACLE_GENERATED`
- 未出现 `accepted_evidence_bound`

### 并行审查结论

本轮两个 explorer 子智能体均为只读：

- CRC case explorer 确认 `123456789 -> 0xCBF43926` 与 FlashDB 源码算法一致，适合作为
  最小非空 draft case。
- Evidence/validator explorer 确认当前生成器和 validator 已支持多 case；需要保持 fixture、
  slice spec、oracle status、harness、replay/manifest operation count 和 cache identity 一起刷新。

下一步建议：

1. 在真实 C 编译器环境下复跑 real-fdb compile attempt，让非空 case 进入真实 compile/run 诊断。
2. 为 `harness_execution` 增加后续 oracle output/diff gate，而不是直接提升
   `C_ORACLE_GENERATED`。
3. 扩展 Rust replay draft，使它不仅记录 fixture path，也能显式枚举并断言两个 fixture case。

## 25. 2026-06-26 Rust replay draft fixture case enumeration

本轮继续第 24 节的下一步：Rust replay draft 不再只记录 fixture path，而是显式枚举
`real-fdb-calc-crc32` 当前绑定的两个 fixture case。同时保持 draft 边界：该文件不调用
Rust 实现，不 claim semantic pass，并用 draft-only panic 防止被误读为可通过 replay test。

### TDD 过程

新增红测：

```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_rust_replay_draft_enumerates_bound_fixture_cases_without_semantic_claim
```

第一轮红测失败于现有 draft 缺少 `struct FixtureCase`。实现最小枚举后，根据并行
explorer 审查再收紧测试，要求：

- Rust 字符串使用双引号，而不是 Python `repr()` 生成的单引号。
- draft 包含 `const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;`。
- 两个 case 都包含 `id`、`crc`、`buf`、`size`、`return_code`。
- draft 包含 `panic!("draft only: ...")`，避免 fixture 自检变成绿色 replay。
- draft 不包含 `fdb_calc_crc32(` 调用。
- `test-translation-generated.json.status` 仍为 `recorded`。
- `generated_draft_semantic_pass` 仍为 `false`。
- `translation_mappings[0].status` 仍为 `gap`。

### 生成器更新

`validation/tools/auto_migrate.py` 新增/更新：

- `generate_rust_replay_test_draft()` 复用 `oracle_fixture_binding()` 解析 fixture case。
- `rust_replay_fixture_cases_source()` 仅在 `behavior_fields == ["return_code"]` 时生成
  case 枚举；其它形状仍保留 TODO。
- `rust_replay_fixture_case_literal()` 只接受 `crc: u32`、`buf: [u8]`、`size == len(buf)`
  和 `return_code: u32` 的 case。
- `rust_string_literal()` 用 JSON 字符串规则生成合法 Rust string literal。

当前 real-fdb draft 关键内容：

```rust
let _fixture = "validation/l2_slices/fixtures/real-fdb-calc-crc32.json";
let _api = "fdb_calc_crc32";
const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;

FixtureCase { id: "empty-crc-zero", crc: 0u32, buf: &[], size: 0usize, return_code: 0u32 },
FixtureCase { id: "ascii-123456789-crc-zero", crc: 0u32, buf: &[49u8, 50u8, 51u8, 52u8, 53u8, 54u8, 55u8, 56u8, 57u8], size: 9usize, return_code: 3421780262u32 },

panic!("draft only: generated Rust API assertions are not bound; Rust implementation is not called");
```

### real-fdb evidence 刷新

已重跑：

```powershell
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json
```

刷新后：

- `l3-real-fdb-calc-crc32-rust-replay-test-draft.rs` 显式枚举两个 fixture case。
- `test-translation-generated.json.generated_draft_semantic_pass: false`
- `test-translation-generated.json.source_test_inputs.fixtures[0].operation_count: 2`
- `test-translation-generated.json.translation_mappings[0].status: gap`
- `auto-translation-manifest.json.replay.generated_draft_semantic_pass: false`
- `auto-translation-manifest.json.status: candidate_refused`
- `auto-translation-manifest.json.claim_boundary.semantic_pass: false`

C oracle 状态仍未提升：

- `c-oracle-status.json.status: DRAFT_GENERATED`
- `toolchain_status: COMPILE_NOT_EXECUTED`
- `compile_execution.status: compiler_not_found`
- `compile_execution.attempted: false`
- `semantic_pass: false`
- 无 `compile_execution.harness_execution`

### 并行审查结论

本轮两个 explorer 子智能体均为只读：

- Rust replay draft explorer 指出单引号不是合法 Rust string literal，并要求 draft
  不能成为无条件通过的绿色测试；本轮已改为双引号和 draft-only panic。
- Evidence/validator explorer 确认当前不需要改 validator；刷新证据时必须保持
  `candidate_refused`、`semantic_pass=false`、`generated_draft_semantic_pass=false`、
  replay mapping `gap` 和 C oracle `compiler_not_found` 边界。

下一步建议：

1. 在真实 C 编译器环境中复跑 real-fdb compile attempt，观察真实 `compile_failed` 或
   `compile_succeeded_not_oracle + harness_execution`。
2. 为成功执行的 harness 增加 oracle output/diff gate；在 diff 通过前仍不得提升
   `C_ORACLE_GENERATED`。
3. 后续 Rust replay 要先绑定真实 Rust API 调用和 accepted C oracle 输出，再移除
   draft-only panic。

## 26. 2026-06-26 harness output gate recorded as not-oracle

本轮继续第 25 节的下一步：为成功执行的 C oracle harness 增加结构化 stdout marker
检查，但仍不把它当作 C oracle 通过。该 gate 只记录在
`compile_execution.harness_execution.output_gate` 下，所有状态都带 `_not_oracle`。

### TDD 过程

新增红测：

```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_harness_output_gate_matches_fixture_stdout_without_oracle_claim validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_harness_output_gate_semantic_pass_spoofing
```

第一轮红测结果：

- `auto_migrate.py` 缺少 `c_oracle_harness_output_gate()`。
- validator 会放过 `output_gate.semantic_pass=true`。

实现后又根据并行 explorer 审查补了一个截断边界红测：

```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_harness_output_gate_uses_raw_stdout_before_report_truncation
```

该红测先失败于 output gate 使用已截断 stdout，导致 marker 在 4000 字符之后时被误判为
`mismatch_not_oracle`。实现改为：用原始 stdout 计算 output gate，写入报告的
`harness_execution.stdout` 仍可截断。

### 生成器更新

`validation/tools/auto_migrate.py` 新增/更新：

- `c_oracle_harness_execution()` 接收 `spec` 和 `fixture_binding`。
- 成功/失败/超时/缺少 executable 的 harness 执行结果均可携带 `output_gate`。
- `c_oracle_harness_output_gate()` 生成结构化 gate：
  - `gate: c_oracle_harness_output`
  - `semantic_pass: false`
  - `compared_fields`
  - `fixture_expected_output_status`
  - `expected_stdout_fragments`
  - `matched_stdout_fragments`
  - `missing_stdout_fragments`
  - `boundary`
- `c_oracle_expected_stdout_fragments()` 从 fixture binding 推导 marker，例如：
  - `fixture case empty-crc-zero return_code matched`
  - `fixture case ascii-123456789-crc-zero return_code matched`

状态集合：

- `matched_not_oracle`
- `mismatch_not_oracle`
- `unsupported_not_oracle`
- `not_run_not_oracle`

即使 stdout marker 全部匹配，也只是 `matched_not_oracle`，不能推进
`C_ORACLE_GENERATED` 或 `semantic_pass=true`。

### Validator 更新

`validation/tools/validate_auto_translation_evidence.py` 现在在
`validate_harness_execution()` 中校验可选 `output_gate`：

- `semantic_pass` 必须为 `false`。
- `gate` 必须是 `c_oracle_harness_output`。
- `compared_fields`、`expected_stdout_fragments`、`matched_stdout_fragments`、
  `missing_stdout_fragments` 必须是字符串数组。
- `fixture_expected_output_status` 必须是字符串。
- `matched_not_oracle` 要求 harness 已 `exited_zero_not_oracle`、`returncode == 0`、
  `matched_stdout_fragments == expected_stdout_fragments` 且无 missing。
- `mismatch_not_oracle` 要求有 missing，且 matched/missing 分区等于 expected。
- `unsupported_not_oracle` 不允许携带 expected/matched/missing。
- `not_run_not_oracle` 不能出现在 exited-zero harness 下。

### real-fdb evidence 刷新

已重跑：

```powershell
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json
```

当前本机仍无 `cc`：

- `compile_execution.status: compiler_not_found`
- `compile_execution.attempted: false`
- `toolchain_status: COMPILE_NOT_EXECUTED`
- `semantic_pass: false`
- 无 `compile_execution.harness_execution`
- 因此 real-fdb 当前也没有 `harness_execution.output_gate`

### 并行审查结论

本轮两个 explorer 子智能体均为只读：

- harness/output explorer 确认 `output_gate` 放在 `harness_execution` 下是最小合适结构；
  关键风险是 stdout marker 不是结构化 oracle diff，必须保持 `_not_oracle`。
- validator/evidence explorer 确认 `matched_not_oracle` 不能被 semantic gate 使用；
  real-fdb 当前仍必须保持 `candidate_refused`、`validation_profile.status=blocked`、
  `diff.semantic_pass=false` 和 `negative_diff.mutation_detected=false`。

下一步建议：

1. 在真实 C 编译器环境复跑 real-fdb，使 harness 实际执行并产出
   `output_gate.status=matched_not_oracle` 或 `mismatch_not_oracle`。
2. 将 stdout marker gate 之后的真正 schema-aware C/Rust diff 设计为独立 accepted gate；
   不要复用 `matched_not_oracle` 作为通过条件。
3. 如果 fixture 数量继续增加，保留“raw stdout 先比较、报告 stdout 可截断”的顺序。

## 27. 2026-06-26 require harness execution and output gate after compile success

本轮继续收紧第 26 节的 fail-closed 边界：如果 C oracle draft 编译成功并进入
`compile_succeeded_not_oracle`，validator 现在要求必须记录 `harness_execution`，且
`harness_execution` 必须携带 `output_gate`。这样避免 evidence 只记录“编译成功”而跳过
执行和 stdout gate。

### TDD 过程

新增红测：

```powershell
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_harness_execution_missing_output_gate
```

第一轮失败于 validator 放过了没有 `output_gate` 的 `harness_execution`。实现后该测试通过。

并行 explorer 随后指出另一个旁路：`compile_succeeded_not_oracle` 仍可完全省略
`harness_execution`。继续新增红测：

```powershell
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_compile_success_missing_harness_execution
```

第一轮失败于 validator 放过了缺失 `harness_execution` 的 compile-success 证据。实现后该测试通过。

### Validator 更新

`validation/tools/validate_auto_translation_evidence.py` 现在要求：

- `compile_execution.status == compile_succeeded_not_oracle` 时，`harness_execution` 必须是对象。
- `harness_execution` 必须包含 `output_gate`。
- `output_gate` 仍按第 26 节校验：
  - `semantic_pass: false`
  - `gate: c_oracle_harness_output`
  - 状态只能是 `_not_oracle`
  - matched/missing fragment 分区必须自洽

这不会改变 `compile_failed`、`compile_timeout`、`compiler_not_found` 和 `skipped_by_flag`
路径；这些路径仍不能携带 accepted oracle 语义。

### real-fdb 当前影响

当前本机仍无 `cc`，real-fdb 仍停在：

- `compile_execution.status: compiler_not_found`
- `compile_execution.attempted: false`
- `toolchain_status: COMPILE_NOT_EXECUTED`
- `semantic_pass: false`
- 无 `compile_execution.harness_execution`
- 无 `harness_execution.output_gate`

因此这次收紧不会误伤当前 real-fdb evidence。只有未来真实编译成功时，才会要求
`harness_execution + output_gate` 同时存在。

### 并行审查结论

本轮两个 explorer 子智能体均为只读：

- output-gate validator explorer 确认：生成器所有 harness execution 分支都会写
  `output_gate`；现有最大旁路是 compile success 完全省略 `harness_execution`。
- real-fdb evidence explorer 确认：当前 real-fdb 没有 `harness_execution/output_gate`，
  因为仍是 `compiler_not_found`；普通 validator 仍通过，semantic-pass 仍按预期失败。

下一步建议：

1. 在真实 C 编译器环境运行 real-fdb，验证 compile-success 分支会同时产出
   `harness_execution` 和 `output_gate`。
2. 为 `exited_nonzero_not_oracle` 或 `executable_missing_not_oracle` 也增加专门负测，
   确认这些 harness 状态同样必须携带 `output_gate`。
3. 继续设计真正 schema-aware C/Rust diff accepted gate，不要把 stdout marker gate
   当作 semantic pass。

## 28. 2026-06-26 draft schema diff prerequisite gate

本轮继续收紧 draft-only evidence 的 fail-closed 边界：`l3-*-diff.json` 和
`l3-*-negative-diff.json` 不再只写自然语言 `reason`，而是写入机器可读的
prerequisite gate，明确说明当前没有 semantic pass 是因为缺 accepted C oracle、
accepted Rust replay report 和 passed schema diff。

### TDD 过程

先新增红测：

```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_route_baseline_and_validation_profile_evidence_are_emitted
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_schema_diff_missing_draft_blockers validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_negative_diff_missing_draft_requirements
```

第一条先失败于 `diff["diff_gate"]` 缺失；后两条先失败于 validator 放过了被删掉
`blocked_by` 或 `required_inputs` 的 draft diff evidence。实现后这三条测试均通过。

### 生成器更新

`validation/tools/auto_migrate.py` 的 draft-only diff 现在写入：

- `diff_gate: schema_aware_c_rust_diff`
- `accepted_diff_required: true`
- `blocked_by: ["c_oracle", "rust_replay"]`
- `required_inputs.c_oracle_required_status: C_ORACLE_GENERATED`
- `required_inputs.rust_report_required_status: passed`
- `required_inputs.*_actual_status` 记录当前 draft 状态
- `compared_fields` 来自 fixture contract behavior fields

draft-only negative diff 现在写入：

- `negative_diff_gate: schema_aware_negative_diff`
- `accepted_negative_diff_required: true`
- `blocked_by: ["schema_diff"]`
- `root_blocked_by: ["c_oracle", "rust_replay"]`
- `required_inputs.schema_diff_required_status: passed`
- `required_inputs.schema_diff_actual_status: incomplete`

这些字段仍然保持 `semantic_pass: false`、`status: incomplete`、
`mutation_detected: false`，不能被解释成 accepted evidence。

### Validator 更新

`validation/tools/validate_auto_translation_evidence.py` 新增普通路径校验：
`validate_schema_diff_contract()`。即使不传 `--require-semantic-pass`，validator 也会检查
draft/incomplete schema diff 和 negative diff 的 gate 字段：

- draft schema diff 必须是 `incomplete/draft/blocked`，且 `semantic_pass: false`。
- draft schema diff 必须声明 `diff_gate`、`accepted_diff_required`、`blocked_by`、
  `required_inputs` 和覆盖行为字段的 `compared_fields`。
- draft schema diff 不允许携带 `accepted_diff` 或真实 `first_mismatch` evidence。
- draft negative diff 必须声明 `negative_diff_gate`、`accepted_negative_diff_required`、
  `blocked_by: ["schema_diff"]` 和 `required_inputs.schema_diff_required_status: passed`。
- draft negative diff 不允许 `mutation_detected: true`、`accepted_negative_diff` 或真实
  `first_mismatch` evidence。

### real-fdb evidence 刷新

已重跑：

```powershell
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root validation/evidence
```

当前 real-fdb 仍是 L4 refused / draft-only：

- `compile_execution.status: compiler_not_found`
- `toolchain_status: COMPILE_NOT_EXECUTED`
- `diff.status: incomplete`
- `diff.blocked_by: ["c_oracle", "rust_replay"]`
- `negative_diff.status: incomplete`
- `negative_diff.blocked_by: ["schema_diff"]`
- `semantic_pass: false`

普通 validator 通过；`--require-semantic-pass` 仍应失败。

### 并行审查结论

本轮两个 explorer 均为只读：

- 生成器 explorer 确认占位 diff 的真实写入点是 `write_l3_candidate_supporting_evidence()`，
  应补 `diff_gate`、`blocked_by`、`required_inputs` 和 `compared_fields`。
- validator explorer 确认当前 `validate_semantic_pass()` 只覆盖 semantic-pass 路径，
  draft/incomplete diff 必须新增无条件 fail-closed 校验。

下一步建议：

1. 继续把 accepted/passed diff 的同名 gate 字段结构化，减少 draft 和 accepted 两条路径的形状差异。
2. 为 semantic-pass 路径补 `compared_fields`、`accepted_diff`、`accepted_negative_diff` 的更深校验。
3. 在有真实 C 编译器的环境重跑 real-fdb，推进到 harness execution 后的真正 schema-aware diff gate。

## 29. 2026-06-26 accepted diff gate fields and semantic-pass accepted refs

本轮承接第 28 节，把 `--accept-existing-evidence` 路径的 passed diff/negative-diff
也补上结构化 gate 字段，并收紧 `--require-semantic-pass` 下对 accepted diff refs 的校验。

### TDD 过程

先新增红测：

```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_l4_refused_accept_existing_evidence_keeps_generated_draft_blocked
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_semantic_pass_schema_diff_missing_accepted_ref validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_semantic_pass_negative_diff_missing_accepted_ref
```

第一条先失败于 accepted-path `diff["diff_gate"]` 缺失；后两条先失败于 semantic-pass
validator 放过缺失 `accepted_diff` / `accepted_negative_diff` 的 passed evidence。

### 生成器更新

`validation/tools/auto_migrate.py` 的 `write_accepted_supporting_evidence()` 现在为 accepted
schema diff 写入：

- `diff_gate: schema_aware_c_rust_diff`
- `accepted_diff_required: true`
- `blocked_by: []`
- `required_inputs.c_oracle_required_status: C_ORACLE_GENERATED`
- `required_inputs.rust_report_required_status: passed`
- `required_inputs.c_oracle_actual_status` 来自本轮 promoted oracle wrapper
- `required_inputs.rust_replay_actual_status` 来自本轮 replay wrapper
- `required_inputs.schema_diff_actual_status` 来自 accepted source diff report

accepted negative diff 现在写入：

- `negative_diff_gate: schema_aware_negative_diff`
- `accepted_negative_diff_required: true`
- `blocked_by: []`
- `root_blocked_by: []`
- `required_inputs.schema_diff_required_status: passed`
- `required_inputs.schema_diff_required_first_mismatch: null`
- `required_inputs.negative_diff_actual_status` 来自 accepted negative source report

L4/refused + `--accept-existing-evidence` 的整体状态仍保持 `candidate_refused`，
generated draft 仍为 `blocked`，这些 gate 字段只说明外部 accepted diff refs 被绑定，
不改变 route/refusal 结论。

### Validator 更新

`validation/tools/validate_auto_translation_evidence.py` 新增 semantic-pass 专用校验：

- `validate_passed_schema_diff_report()` 要求：
  - `semantic_pass: true`
  - `first_mismatch: null`
  - `compared_fields` 为非空字符串数组并覆盖 slice behavior fields
  - `accepted_diff` 存在、path 存在、sha256 匹配、payload status 为 `passed`
  - 若存在 `diff_gate` / `accepted_diff_required` / `blocked_by`，则必须是 accepted 形态
- `validate_passed_negative_diff_report()` 要求：
  - `status` 为 `passed`、`expected_failed` 或 `failed`
  - `expected_failure: true`
  - `mutation_detected/detected: true`
  - `first_mismatch` 为真实对象，且字段落在 schema diff compared fields 内
  - `accepted_negative_diff` 存在、path 存在、sha256 匹配
  - 若存在 `negative_diff_gate` / `accepted_negative_diff_required` / `blocked_by` /
    `root_blocked_by`，则必须是 accepted 形态

这次没有把 manifest `load_ref()` 的 sha/status 全面加严；那会影响更多历史 fixture，
适合下一轮单独用红测推进。

### Evidence 修正

新 accepted-ref 校验暴露了 `validation/evidence/demo/auto-translation/call-expression/`
里两个 wrapper ref 的 sha256 已陈旧。本轮只刷新了：

- `l3-call-expression-diff.json.accepted_diff.sha256`
- `l3-call-expression-negative-diff.json.accepted_negative_diff.sha256`

没有批量改写旧 passed fixture 的 gate 字段；旧 fixture 只要 accepted refs、compared fields
和 negative mismatch 真实有效，仍保持兼容。

### 并行审查结论

本轮两个 explorer 均为只读：

- accepted-path explorer 确认字段应在 `write_accepted_supporting_evidence()` 写入，数据来源已有：
  `accepted["reports"]`、`accepted["paths"]`、promoted `oracle` 和 `replay`。
- semantic-pass explorer 确认 passed diff 不能继续绕过 `accepted_diff`、
  `accepted_negative_diff`、`compared_fields` 和 negative mismatch 校验；同时提示
  negative accepted wrapper status 与 payload status 不一定相同，不能简单套用 `require_ref()`。

下一步建议：

1. 单独加红测收紧 semantic-pass `load_ref()` 的 manifest ref sha/status 校验。
2. 为 passed diff/negative-diff 的 gate 字段缺失增加专门负例，然后决定是否批量回填旧 fixture。
3. 在真实 C 编译器环境继续推进 real-fdb，从 `compiler_not_found` 进入 harness execution。

## 30. 2026-06-26 semantic-pass manifest ref sha/status fail-closed

本轮承接第 29 节，把 `--require-semantic-pass` 路径中的 manifest evidence refs
也纳入 fail-closed 校验。此前 `load_ref()` 只按 `path` 读取文件，不校验 manifest
里记录的 `sha256` 和 `status`，因此 stale 或 spoofed manifest ref 可能绕过 semantic-pass
的后续内容校验。

### TDD 过程

先新增红测：

```powershell
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_semantic_pass_manifest_schema_diff_sha_drift validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_semantic_pass_manifest_negative_diff_status_drift
```

两条先失败于 validator 返回 0：`load_ref()` 放过了 manifest 中错误的
`schema_diff.sha256` 和与 payload 不一致的 `negative_diff.status`。

并行 explorer 随后指出 payload 缺 `status` 也会被旧逻辑放过，因此补充一条窄单元红测：

```powershell
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_semantic_pass_manifest_ref_payload_missing_status
```

该测试直接调用 `load_ref()`，确认 payload 没有 `status` 时必须失败。

### Validator 更新

`validation/tools/validate_auto_translation_evidence.py` 的 `load_ref()` 现在要求：

- manifest ref 必须有非空 `path`。
- manifest ref 必须有非空 `status`。
- manifest ref 必须有非空 `sha256`。
- `path` 必须存在，支持绝对路径和 repo-relative 路径。
- manifest `sha256` 必须等于目标文件真实 sha256。
- 目标 payload 必须有非空 `status`。
- manifest `status` 必须等于 payload `status`。

该校验只运行在 `--require-semantic-pass` 路径，不影响普通 schema-only validator。

### 测试 helper 更新

`_call_expression_semantic_pass_fixture()` 复制 legacy call-expression semantic fixture 到临时目录后，
现在会用 `_bind_manifest_ref()` 刷新临时 manifest 的：

- `schema_diff`
- `negative_diff`

这样 semantic-pass 负例可以按需修改临时 artifact 并同步 ref，避免先被无关 sha drift 拦住。
`test_rejects_semantic_pass_missing_external_callee_context_binding` 已改为复用该 helper。

### Evidence 修正

新 manifest ref 校验暴露出仓库中 call-expression legacy fixture 两个 manifest ref 已陈旧。
本轮刷新了：

- `validation/evidence/demo/auto-translation/call-expression/l3-call-expression-evidence-manifest.json`
  的 `evidence.schema_diff.sha256`
- 同文件的 `evidence.negative_diff.sha256`

没有补全该 legacy fixture 缺失的 `c2rust_baseline`、`route_decision`、`validation_profile`
manifest refs；直接对仓库落盘的 call-expression 运行 validator 仍会先被 current schema required
properties 拦住。测试路径通过 backfill helper 补齐这些 legacy refs。

### 并行审查结论

本轮两个 explorer 均为只读：

- `load_ref` explorer 确认最小安全规则是 semantic-pass 下强制校验 manifest ref 的
  `path/status/sha256`，并要求 payload 自身也有 `status`。
- fixture explorer 确认 call-expression 仓库 fixture 的 `schema_diff` 与 `negative_diff`
  manifest sha 已陈旧，应同步刷新；更大范围的 legacy fixture schema backfill 可留作后续。

下一步建议：

1. 为 passed diff/negative-diff gate 字段缺失增加专门 semantic-pass 负例。
2. 决定是否把 legacy call-expression fixture 完整 backfill 成当前 schema 可直接 validator 通过的 fixture。
3. 在真实 C 编译器环境继续推进 real-fdb harness execution。
## 31. 2026-06-26 semantic-pass passed diff gate fields fail-closed

本轮承接第 30 节下一步，把 `--require-semantic-pass` 路径下 passed
schema diff 和 passed negative diff 的 gate 元数据从“存在才校验”收紧为“必须存在且为 accepted 形态”。
这样旧 fixture 或伪造 evidence 不能只带 `accepted_diff` / `accepted_negative_diff` 就绕过前置 gate provenance。

### TDD 过程

先新增红测：

```powershell
python -B -m unittest validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_semantic_pass_schema_diff_missing_gate_fields validation.tools.test_validate_auto_translation_evidence.ValidateAutoTranslationEvidenceTests.test_rejects_semantic_pass_negative_diff_missing_gate_fields
```

两条测试起初失败于 validator 返回 0。随后将测试扩成 subTest，分别删除：

- schema diff: `diff_gate`、`accepted_diff_required`、`blocked_by`、`required_inputs`
- negative diff: `negative_diff_gate`、`accepted_negative_diff_required`、`blocked_by`、`root_blocked_by`、`required_inputs`

每次删除后都会重新绑定临时 manifest sha/status，确保失败原因来自 gate 字段本身，而不是 sha drift。

### Validator 更新

`validation/tools/validate_auto_translation_evidence.py` 现在要求：

- `validate_passed_schema_diff_report()`:
  - `diff_gate == "schema_aware_c_rust_diff"`
  - `accepted_diff_required is True`
  - `blocked_by == []`
  - `required_inputs` 必须是 dict
  - `required_inputs.c_oracle_required_status == "C_ORACLE_GENERATED"`
  - `required_inputs.rust_report_required_status == "passed"`
  - `required_inputs.schema_diff_actual_status` 只能是 `passed` 或旧兼容的 `null`
- `validate_passed_negative_diff_report()`:
  - `negative_diff_gate == "schema_aware_negative_diff"`
  - `accepted_negative_diff_required is True`
  - `blocked_by == []`
  - `root_blocked_by == []`
  - `required_inputs` 必须是 dict
  - `required_inputs.schema_diff_required_status == "passed"`
  - `required_inputs.schema_diff_required_first_mismatch is null`
  - `required_inputs.schema_diff_actual_status` 只能是 `passed` 或旧兼容的 `null`

draft/incomplete 路径已经在第 28 节强制 gate 字段，本轮只收紧 passed semantic-pass 路径。

### Evidence 和测试 helper 更新

只读 explorer 指出只在测试 helper 回填会掩盖真实 fixture 缺字段。因此本轮持久补齐了：

- `validation/evidence/demo/auto-translation/call-expression/l3-call-expression-diff.json`
- `validation/evidence/demo/auto-translation/call-expression/l3-call-expression-negative-diff.json`
- 同目录 `l3-call-expression-evidence-manifest.json` 的 `schema_diff.sha256` 和 `negative_diff.sha256`

`_call_expression_semantic_pass_fixture()` 不再临时写入这些字段，而是调用
`_assert_call_expression_passed_diff_gate_fields()` 断言源 fixture 已经具备字段。测试仍保留
`_bind_manifest_ref()`，用于负例修改临时 payload 后重新绑定 manifest ref。

直接运行仓库落盘 call-expression semantic validator 仍会先遇到旧 fixture 缺少
`c2rust_baseline`、`route_decision`、`validation_profile` manifest refs。这是第 30 节已记录的遗留 schema
backfill 问题，不属于本轮 gate 字段收紧；测试路径仍通过 legacy backfill helper 补齐这些 refs。

### 并行审查结论

本轮两个 explorer 均为只读：

- Godel 确认 passed schema diff / negative diff 的 gate 字段原先都是可选校验，并建议把负例扩成全部字段覆盖。
- Nash 确认真实 call-expression fixture 也应补齐 gate 字段，否则 helper 会掩盖坏 fixture；同时提醒 manifest
  `schema_diff` / `negative_diff` sha 必须同步刷新，embedded accepted refs 不应改动。

下一步建议：

1. 决定是否把 legacy call-expression fixture 完整 backfill 到可直接通过当前 schema validator。
2. 在真实 C 编译器环境继续推进 real-fdb harness execution，从 `compiler_not_found` 进入可执行 oracle/harness 输出校验。
3. 如果继续收紧 semantic-pass，可为 passed diff `required_inputs` 的 actual status 字段补更完整的源证据一致性校验。
