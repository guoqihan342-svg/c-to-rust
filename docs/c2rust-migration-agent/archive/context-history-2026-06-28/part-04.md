## 44. 2026-06-26 clang-frontend dry-run parse spec skeleton

本轮承接第 43 节第 1/2 条下一步，但继续保持收窄边界：只在 Rust translator crate
增加 feature-gated 的 `clang-frontend` dry-run 输入面，不接真实 libclang、不改 Python pipeline、
不刷新仓库 evidence，也不改变 generated draft 的 semantic-pass 边界。

核心改动：
- `crates/c2r-translator/Cargo.toml`
  - `[features]` 新增 `clang-frontend = []`，默认仍为 `default = []`。
  - `typed-ir` 和 `clang-frontend` 相互独立；后续可以组合启用，但当前 dry-run 不依赖 typed IR。
- `crates/c2r-translator/src/lib.rs`
  - 仅在 `--features clang-frontend` 下导出 `pub mod clang_frontend;`。
  - 默认构建路径不引入 clang frontend 模块或测试 import。
- `crates/c2r-translator/src/clang_frontend.rs`
  - 新增 `ClangParseSpec`，从 `SliceSpec` 消费真实 TU metadata：
    `source_root`、`source_file`、`function_name`、`include_paths`、`defines`、
    `compile_commands`、`source_file_hashes`、`function_source_span`。
  - 新增 `ClangDryRun`，`dry_run()` 是纯函数，不访问文件系统、不调用 libclang，只返回：
    `status=ready_without_libclang`、source/function 信息、clang 参数或 compile database 引用、
    以及明确的 dry-run diagnostic。
  - 无 `compile_commands` 时从 `source_root + include_paths` 合成 `-I...`，并从 defines 合成 `-D...`。
    有 `compile_commands` 时不再合成手工参数，避免把 compile database 和 fallback args 混在一起。
  - `ClangParseSpec::from_slice_spec()` 对 `source_root`、`source_file`、非空 `function_name`、
    `source_file_hashes[source_file]`、`function_source_span`、`function_source_span.file == source_file`
    以及非空 `function_source_span.sha256` fail closed；错误类型 `ClangFrontendError` 实现 `Display`
    和 `Error`，便于后续 CLI/diagnostic artifact 直接复用。
- `validation/tools/auto_migrate.py`
  - `write_translator_spec()` 选择 `source_file` 时优先使用匹配函数的 `source_span.file`，只有找不到匹配文件时
    才回落到旧的第一个 `role=source` 文件，避免多源 slice 把 clang TU 指到错误文件。
- `validation/tools/test_auto_migrate.py`
  - 新增 `test_translator_input_source_file_prefers_matching_function_span_file`，覆盖多源文件场景。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 feature-gated 测试：
    - `clang_parse_spec_dry_run_uses_real_tu_metadata_without_libclang`
    - `clang_parse_spec_dry_run_prefers_compile_commands_over_synthesized_args`
    - `clang_parse_spec_rejects_missing_real_tu_metadata`
    - `clang_parse_spec_rejects_missing_source_hash_and_function_span`
    - `clang_parse_spec_rejects_function_span_for_a_different_source_file`
  - 测试覆盖真实 TU metadata 保留、dry-run 参数生成、compile database 优先级、缺 metadata 的诊断失败、
    source hash 覆盖和 function span 绑定。

TDD 红绿过程：
- 红灯 1：
  `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_parse_spec_dry_run_uses_real_tu_metadata_without_libclang`
  初始失败：`the package 'c2r-translator' does not contain this feature: clang-frontend`。
- 绿灯 1：
  增加 feature gate、模块导出和 `ClangParseSpec` dry-run skeleton 后，目标测试通过。
- 红灯 2：
  `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_parse_spec`
  初始失败：`ClangFrontendError` 没有实现 `Display`，不能用于 `to_string()` 断言。
- 绿灯 2：
  为 `ClangFrontendError` 增加 `Display`/`Error` 后，三条 `clang_parse_spec*` focused tests 全部通过。
- 红灯 3：
  Hooke review 后新增 `clang_parse_spec_rejects_missing_source_hash_and_function_span` 和
  `clang_parse_spec_rejects_function_span_for_a_different_source_file`；初始失败，因为 dry-run 仍会对缺
  hash/span 或 span 文件不一致的输入返回 `ClangParseSpec`。
- 绿灯 3：
  收紧 `from_slice_spec()` 的 source hash/span 校验后，两条负例通过。
- 红灯 4：
  新增 `test_translator_input_source_file_prefers_matching_function_span_file`；初始失败，translator input
  把 `source_file` 写成多源文件列表里的第一个 `role=source` 文件。
- 绿灯 4：
  `write_translator_spec()` 改为优先匹配 `function_source_span.file` 后，该 Python 负例通过。

本轮并行只读审查结论：
- Zeno：确认最小 feature gate、`ClangParseSpec` 字段边界和 dry-run 纯函数语义；建议不要把
  `clang-frontend` 绑定到 `typed-ir`，也不要在骨架里消费 snippet `c_source`。
- Planck：确认本轮不应先改 Python pipeline；上一轮 translator input metadata 已足够构造 dry-run
  `ClangParseSpec`，但真实 libclang lowering 还需要后续单独做。建议下一步先做 Rust CLI dry-run artifact，
  再考虑 Python temp out-root opt-in，不要刷新 repo evidence。
- Hooke：代码审查无 Critical；两个 Important 已处理：
  - Rust dry-run 不再接受缺失/不一致的 `source_file_hashes` 和 `function_source_span`。
  - Python translator input 不再在多源文件 slice 中盲取第一个 source 文件，而是优先使用函数 span 文件。
  Minor 中的 compile database diagnostic 也已补充；public `SliceSpec` 字段兼容风险沿用第 43 节判断：
  仓库内构造点已补 `..SliceSpec::default()`，JSON 兼容由 serde default 保证。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_parse_spec_dry_run_uses_real_tu_metadata_without_libclang
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_parse_spec
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_parse_spec_rejects
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_translator_input_source_file_prefers_matching_function_span_file
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
python -B -m unittest validation.tools.test_auto_migrate
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
git diff --check -- crates/c2r-translator/Cargo.toml crates/c2r-translator/src/lib.rs crates/c2r-translator/src/typed_ir.rs crates/c2r-translator/src/clang_frontend.rs crates/c2r-translator/tests/bounded_translation.rs validation/tools/auto_migrate.py validation/tools/test_auto_migrate.py CONTEXT.md
```

完整结果：
- 默认 translator crate：`34 passed`。
- `--features typed-ir` translator crate：`36 passed`。
- `--features clang-frontend` translator crate：`39 passed`。
- `--features typed-ir,clang-frontend` translator crate：`41 passed`。
- `validation.tools.test_auto_migrate`：`Ran 44 tests ... OK`。
- `cargo fmt --check` 和 `git diff --check` 均通过。

当前核心翻译功能状态：
- 默认生成路径不变，`clang-frontend` 默认关闭。
- Rust 侧已有真实 TU metadata 到 `ClangParseSpec` 的 fail-closed dry-run 输入面。
- 仍未接真实 libclang，仍未把 dry-run artifact 写入 CLI/Python pipeline，generated draft semantic pass
  边界仍保持不变。

下一步建议：
1. 若继续按 libclang 方向推进，先给 `c2r_translate` 增加 feature-gated dry-run diagnostic artifact，
   默认构建不产物，`--features clang-frontend` 才输出可观测 JSON。
2. 再用 Python temp `--out-root` 做显式 opt-in 接入测试，不写 `validation/evidence`。
3. 之后才接真实 libclang lowering：先小 C fixture，再 real-fdb `fdb_calc_crc32`，目标是 lower 出与
   `crc32_byte_cursor_function()` 等价的 `IrFunction`。

## 45. 2026-06-26 clang dry-run artifact under feature gate

本轮承接第 44 节第 1 条下一步，但仍保持边界：只让 Rust translator crate 在
`--features clang-frontend` 下写出可观测 dry-run diagnostic artifact；默认构建不产物，不改
Python pipeline，不刷新仓库 evidence，也不接真实 libclang。

核心改动：
- `crates/c2r-translator/src/lib.rs`
  - `write_translation_artifacts()` 在已有 8 个 artifact 后，且仅在 `#[cfg(feature = "clang-frontend")]`
    下追加 `l3-{slice_id}-clang-dry-run.json` 到 manifest。
  - artifact 内容来自 `ClangParseSpec::from_slice_spec(spec).dry_run()`：
    - metadata 完整时：`status=ready_without_libclang`，包含 `dry_run`、`metadata.source_file_hashes`、
      `metadata.function_source_span`，`errors=[]`。
    - metadata 不完整时：`status=blocked`，记录 `errors[0].kind/message`，但不阻断普通翻译 artifact
      和 Rust draft 产出。
  - 默认构建使用不可变 `artifacts` vector，避免 `unused_mut` warning；feature 开启时才 shadow 成
    mutable vector 并 push dry-run artifact。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `default_translation_artifacts_do_not_emit_clang_dry_run`，验证默认构建不写
    `l3-*-clang-dry-run.json`，manifest 也不引用它。
  - 新增 `clang_frontend_feature_writes_dry_run_artifact_from_real_tu_metadata`，验证 feature 开启时
    完整真实 TU metadata 会生成 ready dry-run JSON。
  - 新增 `clang_frontend_dry_run_artifact_records_metadata_errors_without_blocking_translation`，验证缺
    metadata 时 dry-run artifact fail closed，但普通翻译 manifest 仍保持 generated。

TDD 红绿过程：
- 红灯：
  `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_frontend`
  初始失败在 `l3-*-clang-dry-run.json` 文件不存在。
- 绿灯：
  将 dry-run artifact 追加到 `write_translation_artifacts()` 后，两个 feature-gated artifact 测试通过。
- 默认路径回归：
  `cargo test --manifest-path crates/c2r-translator/Cargo.toml default_translation_artifacts_do_not_emit_clang_dry_run`
  首次通过但有 `unused_mut` warning；随后调整 vector 构造，默认全量测试无 warning 通过。

本轮并行只读审查结论：
- Chandrasekhar：建议 dry-run artifact 落在 `write_translation_artifacts()` 而不是 CLI；文件名使用
  `l3-{slice_id}-clang-dry-run.json`；默认构建不编译 `clang_frontend`、不产物、manifest 保持现有文件集。
  本轮实现与该建议一致。
- Jason：建议本轮不改 Python；等 Rust artifact 可用后，再单独做默认关闭的 Python opt-in，例如
  `--emit-clang-dry-run`，并用 mock 测命令构造，避免真实 cargo 或 repo `validation/evidence` 写入。
  本轮遵守该边界。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml default_translation_artifacts_do_not_emit_clang_dry_run
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
python -B -m unittest validation.tools.test_auto_migrate
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check
git diff --check -- crates/c2r-translator/src/lib.rs crates/c2r-translator/tests/bounded_translation.rs CONTEXT.md
```

完整结果：
- 默认 translator crate：`35 passed`。
- `--features typed-ir` translator crate：`37 passed`。
- `--features clang-frontend` translator crate：`41 passed`。
- `--features typed-ir,clang-frontend` translator crate：`43 passed`。
- `validation.tools.test_auto_migrate`：`Ran 44 tests ... OK`。
- `cargo fmt --check` 和 `git diff --check` 均通过。

当前核心翻译功能状态：
- 默认 generated candidate 路径仍不变，`clang-frontend` 默认关闭且不写 dry-run artifact。
- Rust feature 路径已有可观测 clang dry-run diagnostic artifact，可用于下一步 Python opt-in。
- 仍未接真实 libclang，也未把 Python pipeline 默认改为启用 clang dry-run；generated semantic pass
  边界仍保持不变。

下一步建议：
1. 做 Python 显式 opt-in：新增默认关闭的 `--emit-clang-dry-run` 或等价配置，只在 temp `--out-root`
   测试中通过 `cargo run --features clang-frontend` 产出 dry-run artifact。
2. 再做真实 libclang lowering 的最小 fixture：先不碰 real-fdb，先用小 C 文件证明能 lower 出
   一个 `IrFunction` skeleton。
3. 最后把 real-fdb `fdb_calc_crc32` lower 到与 `crc32_byte_cursor_function()` 等价的 typed IR。

## 46. 2026-06-26 Python opt-in for clang dry-run artifact

本轮承接第 45 节第 1 条下一步：给 `auto_migrate.py` 增加默认关闭的显式 opt-in，
允许在临时 `--out-root` 中通过 translator 的 `clang-frontend` feature 产出
`l3-{slice_id}-clang-dry-run.json`。默认 pipeline、默认 cargo 命令、repo `validation/evidence`
和 semantic-pass 边界都不改变。

核心改动：
- `validation/tools/auto_migrate.py`
  - 新增 CLI 参数 `--emit-clang-dry-run`，默认 `False`。
  - `main()` 将 `args.emit_clang_dry_run` 传给 `run_translator()`。
  - `run_translator(..., emit_clang_dry_run=False)` 仅在 opt-in 时给 cargo 命令追加：
    `--features clang-frontend`，位置在 Cargo 参数区，即 `--manifest-path <Cargo.toml>` 之后、
    `--bin c2r_translate` 之前。
  - `emit_cache_metadata()` / `cache_identity()` 增加同名参数；opt-in 时
    `command_arguments` 记录 `--emit-clang-dry-run`，避免后续 cache/reuse 混淆默认路径和 clang
    dry-run 路径。
- `validation/tools/test_auto_migrate.py`
  - 新增 `test_run_translator_emit_clang_dry_run_enables_clang_frontend_feature`：
    mock `subprocess.run`，只断言命令构造，确认 `--features clang-frontend` 在 `--bin` 之前，
    且 `cwd/text/capture_output` 仍按原路径。
  - 新增 `test_cache_identity_records_emit_clang_dry_run_opt_in`：
    验证 cache identity 的 `command_arguments` 记录 opt-in。
  - 新增 `test_real_fdb_calc_crc32_emit_clang_dry_run_opt_in_writes_temp_artifact`：
    用真实 CLI 但只写临时 `--out-root`，并带 `--skip-c-oracle --skip-rust-check`，验证 real-fdb
    translator input 在 opt-in 下生成 `l3-real-fdb-calc-crc32-clang-dry-run.json`，状态为
    `ready_without_libclang`。

TDD 红绿过程：
- 红灯 1：
  `test_run_translator_emit_clang_dry_run_enables_clang_frontend_feature` 初始失败：
  `run_translator()` 没有 `emit_clang_dry_run` keyword。
- 红灯 2：
  `test_real_fdb_calc_crc32_emit_clang_dry_run_opt_in_writes_temp_artifact` 初始失败：
  argparse 不认识 `--emit-clang-dry-run`。
- 绿灯 1/2：
  增加 CLI flag 和 `run_translator()` opt-in cargo feature plumbing 后，两条测试通过。
- 红灯 3：
  `test_cache_identity_records_emit_clang_dry_run_opt_in` 初始失败：
  `cache_identity()` 没有 `emit_clang_dry_run` keyword。
- 绿灯 3：
  将 opt-in 贯穿到 `emit_cache_metadata()` / `cache_identity()` 后，cache identity 测试通过。

本轮并行只读审查结论：
- Hume：确认最小实现应只在 opt-in 时追加 `--features clang-frontend`，且必须放在 Cargo 参数区；
  默认 flag 为 false 时 cargo 命令完全不变。另建议 cache identity 记录该 opt-in，本轮已补。
- Ramanujan：建议用 mock 测 `run_translator()` 命令构造，断言 `--features` 在 `--bin` 之前，
  并避免 repo evidence 写入。本轮 mock 测试按该建议实现；另保留一个真实临时 `--out-root`
  集成测试，用于验证端到端 artifact 产出，未写仓库 evidence。

已通过命令：
```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_dry_run_enables_clang_frontend_feature
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_dry_run_opt_in_writes_temp_artifact
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_dry_run_opt_in
python -B -m unittest validation.tools.test_auto_migrate
python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence validation.tools.test_real_fdb_calc_crc32_l3_evidence
git diff --check -- validation/tools/auto_migrate.py validation/tools/test_auto_migrate.py CONTEXT.md
```

完整结果：
- `validation.tools.test_auto_migrate`：`Ran 47 tests ... OK`。
- 相关 Python 回归：`Ran 100 tests ... OK`。
- `git diff --check` 通过。

当前核心翻译功能状态：
- 默认 auto_migrate 路径仍不启用 clang frontend，不写 clang dry-run artifact。
- 显式 `--emit-clang-dry-run` 可在临时 out-root 中用 Rust translator feature 产出 clang dry-run JSON。
- 仍未接真实 libclang lowering；当前 dry-run artifact 只是后续 libclang 前端接入前的可观测诊断面。

下一步建议：
1. 先做最小 libclang 环境探测/feature plumbing：检测环境里是否可用 libclang，但默认仍 fail-closed。
2. 用小 C fixture 做真实 TU parse/lowering skeleton，先 lower 一个简单函数到 `IrFunction`。
3. 再将 real-fdb `fdb_calc_crc32` lower 到与 `crc32_byte_cursor_function()` 等价的 typed IR。

## 47. 2026-06-26 clang dry-run environment detection

本轮承接第 46 节第 1 条下一步：给 Rust `clang-frontend` dry-run 增加最小
libclang 环境探测字段。边界保持不变：不新增 `clang-sys`/`libloading`/`build.rs`，
不动态加载 DLL，不执行真实 libclang parse/lowering，默认构建仍不产出 clang dry-run artifact。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - 新增 `ClangEnvironment`，序列化到 `ClangDryRun.environment`：
    - `status=not_configured`：未发现非空 `LIBCLANG_PATH`。
    - `status=configured`：发现非空 `LIBCLANG_PATH`，记录 `source=LIBCLANG_PATH`
      和 `libclang_path`。
    - 两种状态都写 diagnostic，明确 real libclang parsing 仍禁用。
  - 新增 `ClangEnvironment::detect_from_env()` 纯函数，测试可注入环境 map，避免本机环境
    造成 flake。
  - `ClangParseSpec::dry_run()` 保持 `status=ready_without_libclang`，只把当前进程环境探测结果
    附加到 dry-run JSON；新增 `dry_run_with_environment()` 用于稳定测试。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_dry_run_records_missing_libclang_environment_without_parsing`，验证空环境时
    `environment.status=not_configured`，总 dry-run 状态仍是 `ready_without_libclang`。
  - 新增 `clang_dry_run_records_configured_libclang_path_without_enabling_parse`，验证设置
    `LIBCLANG_PATH` 时只记录配置状态，不开启真实 parse。

本轮未改 Python：
- `validation/tools/auto_migrate.py` 已通过 `--emit-clang-dry-run` 显式 opt-in 启用
  `--features clang-frontend`，不会解析 dry-run JSON 内部字段。
- 当前 cache identity 只区分 `--emit-clang-dry-run` opt-in，不绑定 `LIBCLANG_PATH`。只要 dry-run
  仍是临时诊断产物，这个边界可接受；若后续把 dry-run artifact 纳入可复用证据或漂移检测，需要补
  `clang_dry_run_environment_identity` 并加入 Python cache 测试。

TDD 红绿过程：
- 红灯：
  `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_dry_run_records`
  初始失败在 `dry_run_with_environment` 方法不存在。
- 绿灯：
  增加 `ClangEnvironment`、`detect_from_env()`、`dry_run_with_environment()` 后，两条聚焦测试通过。

本轮并行只读审查结论：
- Hilbert：建议环境字段嵌在 `dry_run.environment`，只检查 `LIBCLANG_PATH`，不加载 DLL，不新增
  clang 依赖，不使用 `available/loaded/version/ast` 等暗示真实解析已成功的字段。本轮实现一致。
- Herschel：确认 Python 主流程不用改；新增 JSON 字段不会破坏现有 `--emit-clang-dry-run`
  测试。另提醒 cache identity 当前未绑定 `LIBCLANG_PATH`，本节已记录为后续边界。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_dry_run_records
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
python -B -m unittest validation.tools.test_auto_migrate
python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence validation.tools.test_real_fdb_calc_crc32_l3_evidence
```

完整结果：
- 默认 translator crate：`35 passed`。
- `--features typed-ir` translator crate：`37 passed`。
- `--features clang-frontend` translator crate：`43 passed`。
- `--features typed-ir,clang-frontend` translator crate：`45 passed`。
- `validation.tools.test_auto_migrate`：`Ran 47 tests ... OK`。
- 相关 Python 回归：`Ran 100 tests ... OK`。

当前核心翻译功能状态：
- 默认 generated candidate 路径不变。
- `clang-frontend` 仍是 opt-in dry-run diagnostic surface，现在可记录 libclang 环境配置状态。
- 仍未接真实 libclang parse/lowering，也未把 real-fdb `fdb_calc_crc32` 改为由 libclang AST 驱动。

下一步建议：
1. 用小 C fixture 做真实 TU parse/lowering skeleton，先证明能从真实前端构造一个最小 `IrFunction`。
2. 明确 real parse 的启用开关和 fail-closed 错误模型，避免 `LIBCLANG_PATH` 一存在就改变默认行为。
3. 再把 real-fdb `fdb_calc_crc32` lowering 接到与 `crc32_byte_cursor_function()` 等价的 typed IR。

## 48. 2026-06-26 real clang add-one AST smoke and typed IR lowering skeleton

本轮承接第 47 节第 1 条下一步，并按用户要求先安装 clang：
- 通过 `winget install --id LLVM.LLVM --exact --source winget --accept-package-agreements --accept-source-agreements`
  安装 LLVM 22.1.8。
- 本机路径：
  - `C:\Program Files\LLVM\bin\clang.exe`
  - `C:\Program Files\LLVM\bin\libclang.dll`
- 验证：
  `clang version 22.1.8 (https://github.com/llvm/llvm-project ca7933e47d3a3451d81e72ac174dcb5aa28b59d1)`

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - 新增 `ClangFunctionSkeleton` / `ClangParamSkeleton` / `ClangTypeSkeleton` /
    `ClangStmtSkeleton` / `ClangExprSkeleton` / `ClangBinaryOperator`。
  - 新增 `lower_function_skeleton()`，在 `clang-frontend + typed-ir` 双 feature 下把前端函数模型
    lower 成 `IrFunction`。
  - 新增 `lower_function_from_clang_ast_dump()`，显式调用 `clang -Xclang -ast-dump=json -fsyntax-only`
    解析真实小 C translation unit，再把目标 `FunctionDecl` 转成 skeleton 并 lower 到 typed IR。
  - 当前 AST subset 只覆盖最小 add-one 形态：
    `FunctionDecl -> ParmVarDecl + CompoundStmt -> ReturnStmt -> BinaryOperator(+) ->
    DeclRefExpr/IntegerLiteral`，类型只覆盖 `int`。
  - 未新增 Cargo 依赖，未引入 `clang-sys` 或 `libloading`；这一步是可执行 clang 的 AST dump smoke，
    不是完整 libclang binding。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_skeleton_builds_typed_ir_for_add_one_fixture`，验证手写 skeleton 能 lower 出
    `IrFunction { name=add_one, return int, param value:int, Return(Binary(Add(value, 1))) }`。
  - 新增 `clang_ast_dump_lowers_real_add_one_translation_unit_when_enabled`，只有设置
    `C2R_RUN_CLANG_AST_TESTS=1` 时才调用真实 `clang.exe` 解析临时 `add_one.c`；默认测试不依赖本机
    LLVM 安装。

TDD 红绿过程：
- 红灯：
  `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend clang_lowering_skeleton`
  初始失败在 `lower_function_skeleton` 和 skeleton 类型未定义。
- 绿灯：
  增加 skeleton 类型和 `lower_function_skeleton()` 后，聚焦测试通过。
- 真实 clang smoke：
  安装 LLVM 后，设置 `CLANG_PATH` / `LIBCLANG_PATH` / `C2R_RUN_CLANG_AST_TESTS=1`，用真实
  `clang.exe` AST dump 解析临时 `add_one.c`，并成功 lower 到 typed IR。

本轮并行只读审查结论：
- Noether：建议真实 clang/libclang 路径不要污染默认回归；普通测试只验证 API 和 unavailable/report
  路径，真实 TU parse 用 opt-in 测试。本轮用 `C2R_RUN_CLANG_AST_TESTS=1` 实现该边界。
- Dewey：确认 add-one 的最小 `IrFunction` 形状应为 i32 return、一个 i32 param、单条
  `Return(Binary(Add(Var(value), LitInt(1))))`；不要顺手扩 typed IR emitter 到非 CRC32。本轮只做
  lowering，不改 `emit_rust_from_ir()`。

已通过命令：
```powershell
winget install --id LLVM.LLVM --exact --source winget --accept-package-agreements --accept-source-agreements
& 'C:\Program Files\LLVM\bin\clang.exe' --version
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH; $env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend clang_lowering_skeleton
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH; $env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'; $env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'; $env:C2R_RUN_CLANG_AST_TESTS = '1'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend clang_ast_dump_lowers_real_add_one_translation_unit_when_enabled -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH; $env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH; $env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'; $env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'; $env:C2R_RUN_CLANG_AST_TESTS = '1'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
python -B -m unittest validation.tools.test_auto_migrate
python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence validation.tools.test_real_fdb_calc_crc32_l3_evidence
```

完整结果：
- 默认 translator crate：`35 passed`。
- `--features clang-frontend` translator crate：`43 passed`。
- `--features typed-ir` translator crate：`37 passed`。
- `--features typed-ir,clang-frontend` translator crate：`47 passed`，其中真实 clang AST smoke 已执行。
- `validation.tools.test_auto_migrate`：`Ran 47 tests ... OK`。
- 相关 Python 回归：`Ran 100 tests ... OK`。

当前核心翻译功能状态：
- 默认 generated candidate 路径仍不变。
- `clang-frontend + typed-ir` 现在能从真实 clang AST dump 的最小 add-one TU lower 出 typed IR。
- 仍未把该路径接入 `auto_migrate.py` 默认流程，也未把 real-fdb `fdb_calc_crc32` 改为真实 AST 驱动。
- 真实测试目前是 opt-in，避免没有 LLVM 的机器默认失败。

下一步建议：
1. 把 `lower_function_from_clang_ast_dump()` 包装成报告型入口，输出 `lowered/unavailable/blocked/unsupported`
   和 errors，便于 Python pipeline opt-in 消费。
2. 扩展 AST subset：先支持 `return value + literal` 的更多整数类型/操作，再支持局部声明和赋值。
3. 再用真实 FlashDB `fdb_calc_crc32` AST 做结构审计，决定要先 lower 哪个最小子集，而不是直接跳到全函数。

## 49. 2026-06-26 clang lowering report API

本轮承接第 48 节第 1 条下一步：给 clang AST lowering 增加报告型入口，先作为 Rust API
可观察状态面，不改默认 translation pipeline，不写新的 artifact，不改 Python cache identity。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangFrontendError` 增加 `Serialize/Deserialize` derive，便于报告结构直接序列化。
  - 新增 `ClangLoweringReport`：
    - `status`: `lowered | unavailable | blocked | unsupported`
    - `frontend`, `source_file`, `function_name`, `clang_path`, `arguments`
    - `environment`, `diagnostics`, `errors`, `function_ir`
  - 新增 `lower_function_from_clang_ast_dump_report()`：
    - 缺 `CLANG_PATH` 时返回 `status=unavailable`，`function_ir=None`，错误
      `missing_clang_path`。
    - 配置 `CLANG_PATH` 时调用现有 `lower_function_from_clang_ast_dump()`，成功返回
      `status=lowered`。
  - 新增 `lower_function_skeleton_report()`，用于无需真实 clang 的 subset/unsupported 回归测试。
  - 保留原有 `lower_function_from_clang_ast_dump()` 和 `lower_function_skeleton()` 的
    `Result<IrFunction, ClangFrontendError>` API，不替换调用方。
  - 错误映射：
    - `missing_clang_path` / `clang_ast_dump_unavailable` -> `unavailable`
    - `unsupported_*` -> `unsupported`
    - 其他 `invalid_*`、`missing_*`、`clang_ast_dump_failed` 等 -> `blocked`
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_report_records_unavailable_without_clang_path`。
  - 新增 `clang_lowering_report_maps_unsupported_skeleton_without_ir`。
  - 扩展 `clang_ast_dump_lowers_real_add_one_translation_unit_when_enabled`，在真实 clang smoke 中
    同时验证 report `status=lowered` 且 `function_ir=Some(add_one)`。

本轮未改 Python / artifact：
- `validation/tools/auto_migrate.py` 仍只负责 `--emit-clang-dry-run` opt-in 和
  `--features clang-frontend`；它不消费 report API。
- 未新增 `l3-{slice_id}-clang-lowering-report.json`，也未把 report 纳入 manifest。
- cache identity 暂不记录 `CLANG_PATH` / `LIBCLANG_PATH`。如果后续把 lowering report 作为
  可复用 evidence 或影响 candidate/semantic status，必须新增独立 opt-in、环境 identity 和 cache
  drift 测试。

TDD 红绿过程：
- 红灯：
  `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend clang_lowering_report -- --nocapture`
  初始失败在 `lower_function_from_clang_ast_dump_report` 和 `lower_function_skeleton_report`
  不存在。
- 绿灯：
  增加 `ClangLoweringReport`、两个 report 入口和状态映射后，`unavailable/unsupported` 两条
  聚焦测试通过。
- 真实 clang report：
  `clang_ast_dump_lowers_real_add_one_translation_unit_when_enabled` 在
  `C2R_RUN_CLANG_AST_TESTS=1` 下继续调用真实 `clang.exe`，并验证 `status=lowered`。

本轮并行只读审查结论：
- Harvey：建议新增报告包装但保留现有 `Result<IrFunction, ClangFrontendError>` API；不要改
  `write_translation_artifacts()` 默认 pipeline，不要把 clang lowering error 写入
  `TranslationResult.errors` / `blocked-repairs` / `ArtifactManifest.status`。本轮实现遵守该边界。
- Popper：确认 Python 暂时不用改；若 report 后续进入 artifact/cache，必须独立 opt-in，且不能复用
  现在的 `--emit-clang-dry-run` 默认语义。本轮仅记录该后续边界。

已通过命令：
```powershell
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH; $env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'; $env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'; $env:C2R_RUN_CLANG_AST_TESTS = '1'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend clang_lowering_report -- --nocapture
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH; $env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'; $env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'; $env:C2R_RUN_CLANG_AST_TESTS = '1'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend clang_ast_dump_lowers_real_add_one_translation_unit_when_enabled -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH; $env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH; $env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'; $env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'; $env:C2R_RUN_CLANG_AST_TESTS = '1'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
python -B -m unittest validation.tools.test_auto_migrate
python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence validation.tools.test_real_fdb_calc_crc32_l3_evidence
```

完整结果：
- 默认 translator crate：`35 passed`。
- `--features clang-frontend` translator crate：`43 passed`。
- `--features typed-ir` translator crate：`37 passed`。
- `--features typed-ir,clang-frontend` translator crate：`49 passed`，其中真实 clang AST smoke 已执行。
- `validation.tools.test_auto_migrate`：`Ran 47 tests ... OK`。
- 相关 Python 回归：`Ran 100 tests ... OK`。

当前核心翻译功能状态：
- 默认 generated candidate 路径仍不变。
- Rust API 层已有真实 clang AST dump -> add-one typed IR 的 `lowered/unavailable/blocked/unsupported`
  报告状态。
- 仍未把 clang lowering report 作为 artifact 写出，也未让 Python pipeline/cache 消费。
- real-fdb `fdb_calc_crc32` 仍未改为真实 AST 驱动。

下一步建议：
1. 增加一个默认关闭的 Rust artifact opt-in：`l3-{slice_id}-clang-lowering-report.json`，但不要影响
   manifest status 或 semantic pass。
2. 在 Python 中单独新增 opt-in，不复用 `--emit-clang-dry-run`，并把 `CLANG_PATH`/`LIBCLANG_PATH`
   纳入 cache identity。
3. 对 real-fdb `fdb_calc_crc32` 先做 AST 结构审计 report，而不是直接 lowering 全函数。

## 50. 2026-06-26 Rust opt-in clang lowering report artifact

本轮承接第 49 节第 1 条下一步：增加默认关闭的 Rust-only artifact opt-in，
写出 `l3-{slice_id}-clang-lowering-report.json`，但不影响 `ArtifactManifest.status`、
普通 translation errors、semantic pass 或 Python pipeline。

核心改动：
- `crates/c2r-translator/Cargo.toml`
  - 新增 feature：`clang-lowering-report = ["clang-frontend", "typed-ir"]`。
  - 默认仍为空；`clang-frontend` 单独开启时仍只写 dry-run artifact，不写 lowering report。
- `crates/c2r-translator/src/lib.rs`
  - `write_translation_artifacts()` 在 `#[cfg(feature = "clang-lowering-report")]` 下追加
    `write_clang_lowering_report_artifact()`。
  - 新 artifact 文件名：`l3-{slice_id}-clang-lowering-report.json`。
  - report source path 使用 `source_root.join(source_file)`，支持相对 `source_file`。
  - `manifest.status` 仍只来自 `translate_slice(spec).errors`；lowering report 的
    `unavailable/blocked/unsupported` 不回写普通翻译状态。
  - artifact JSON 包含：
    - `artifact_kind=clang-lowering-report`
    - `frontend=clang`
    - `status=lowered|unavailable|blocked|unsupported`
    - `source_file`, `function_name`
    - `claim_boundary.role=diagnostic_only`
    - `claim_boundary.affects_manifest_status=false`
    - `claim_boundary.affects_semantic_pass=false`
    - `claim_boundary.authoritative_evidence=false`
    - `diagnostics`, `errors`, `lowering_report`, `metadata`
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangLoweringReport.source_file` 统一将 Windows `\` 规范化为 `/`，避免 artifact 顶层和
    report 内部路径风格不一致。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 扩展默认测试：默认 feature 不写 dry-run，也不写 lowering report。
  - 新增 `clang_frontend_feature_does_not_emit_lowering_report_without_opt_in`。
  - 新增 `clang_lowering_report_feature_writes_report_artifact_without_changing_manifest_status`。

本轮未改 Python / cache：
- `validation/tools/auto_migrate.py` 仍只有 `--emit-clang-dry-run`，不复用该 flag 产出 lowering
  report。
- cache identity 暂不记录 `CLANG_PATH` / `LIBCLANG_PATH`。后续如果 Python 要产出/消费 lowering
  report，应新增独立 `--emit-clang-lowering-report`，并记录 feature set、clang 环境和版本身份。
- 未刷新仓库 `validation/evidence/**`。

TDD 红绿过程：
- 红灯 1：
  `cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_report_feature_writes_report_artifact_without_changing_manifest_status`
  初始失败：crate 没有 `clang-lowering-report` feature。
- 红灯 2：
  增加 feature 和 artifact writer 后，测试失败在 report 内部 `source_file` 仍含 Windows 反斜杠，
  与 artifact 顶层规范化路径不一致。
- 绿灯：
  增加 `normalized_report_path()`，report 内部路径也规范化为 `/` 后，聚焦测试通过。

本轮并行只读审查结论：
- Lorentz：建议 feature 默认关闭、只追加 artifact、不改变 manifest status；JSON 应显式声明
  diagnostic-only claim boundary。本轮实现与该建议一致。
- Gauss：确认 Python 本轮不应改；后续应新增独立 `--emit-clang-lowering-report`，不能复用
  `--emit-clang-dry-run`。本节已记录该边界。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_report_feature_writes_report_artifact_without_changing_manifest_status
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_frontend_feature_does_not_emit_lowering_report_without_opt_in
cargo test --manifest-path crates/c2r-translator/Cargo.toml default_translation_artifacts_do_not_emit_clang_dry_run
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH; $env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'; $env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'; $env:C2R_RUN_CLANG_AST_TESTS = '1'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features typed-ir,clang-frontend
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH; $env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'; $env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'; $env:C2R_RUN_CLANG_AST_TESTS = '1'; cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate
python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence validation.tools.test_real_fdb_calc_crc32_l3_evidence
```

完整结果：
- 默认 translator crate：`35 passed`。
- `--features clang-frontend` translator crate：`44 passed`。
- `--features typed-ir` translator crate：`37 passed`。
- `--features typed-ir,clang-frontend` translator crate：`50 passed`，真实 clang AST smoke 已执行。
- `--features clang-lowering-report` translator crate：`50 passed`，report artifact 测试已执行。
- `validation.tools.test_auto_migrate`：`Ran 47 tests ... OK`。
- 相关 Python 回归：`Ran 100 tests ... OK`。

当前核心翻译功能状态：
- 默认 generated candidate 路径仍不变。
- Rust 侧已有可显式 opt-in 的 clang lowering report artifact。
- artifact 是 diagnostic-only，不影响 manifest status、semantic pass 或 Python cache。
- real-fdb `fdb_calc_crc32` 仍未改为真实 AST 驱动。

下一步建议：
1. 给 Python 增加独立 `--emit-clang-lowering-report`，只在显式 opt-in 时启用
   `--features clang-lowering-report`。
2. 为该 opt-in 增加 cache identity：至少记录 command arg、feature set、`CLANG_PATH` /
   `LIBCLANG_PATH` 配置状态和 clang version。
3. 再做 real-fdb `fdb_calc_crc32` 的 AST 结构审计 report，不直接承诺全函数 lowering。

## 51. 2026-06-26 Python opt-in for clang lowering report artifact

本轮承接第 50 节第 1/2 条下一步：给 Python `auto_migrate.py` 增加独立、默认关闭的
`--emit-clang-lowering-report` opt-in。该 flag 只在显式传入时启用 Rust translator 的
`clang-lowering-report` feature，并记录 lowering report 相关 cache identity；不复用
`--emit-clang-dry-run`，不刷新仓库 `validation/evidence/**`，不改变默认 pipeline、
manifest status 或 semantic pass 边界。

核心改动：
- `validation/tools/auto_migrate.py`
  - 新增 CLI 参数 `--emit-clang-lowering-report`，默认 `False`。
  - `main()` 将该参数传入 `run_translator()` 和 `emit_cache_metadata()`。
  - `run_translator()` 新增 `emit_clang_lowering_report` 参数，并通过
    `translator_feature_set()` 统一构造 cargo feature：
    - 默认：不传 `--features`。
    - `--emit-clang-dry-run`：只传 `clang-frontend`。
    - `--emit-clang-lowering-report`：传 `clang-lowering-report`，位置仍在
      cargo 参数区、`--bin` 之前。
  - cache metadata 新增动态 `cache_input_fields()`：
    - 默认 cache input fields 保持原基线，不强制旧/默认 evidence 带新 clang 字段。
    - 只有 lowering report opt-in 时追加 `translator_feature_set` 和
      `clang_lowering_identity`。
  - `cache_identity()` 仅在 lowering report opt-in 时记录：
    - `command_arguments` 追加 `--emit-clang-lowering-report`。
    - `translator_feature_set`。
    - `clang_lowering_identity`，包含 `CLANG_PATH` / `LIBCLANG_PATH` 配置状态、路径和
      `clang_version`。`clang_version` 仅在 opt-in 且 `CLANG_PATH` 非空时通过
      `command_version([CLANG_PATH, "--version"])` 探测；不加入全局 `tool_versions()`。
  - `cache_drift_report()` 改为读取 previous/current payload 自带的 `cache_input_fields`
    并与基线字段取并集，确保 opt-in 字段变化会使 cache drift，但旧 cache 不被新字段硬性破坏。
- `validation/tools/test_auto_migrate.py`
  - 新增默认路径不启用 clang feature 的 mock 命令测试。
  - 新增 dry-run opt-in 不启用 lowering report feature 的测试。
  - 新增 lowering report opt-in 命令构造测试。
  - 新增默认 cache identity 不写 lowering 字段的测试。
  - 新增 lowering report opt-in cache identity 测试，mock `command_version()` 验证
    clang version 记录。
  - 新增真实 CLI + 临时 `--out-root` 的 real-fdb lowering report artifact 测试，
    并清空 `CLANG_PATH` / `LIBCLANG_PATH`，验证 fail-closed `status=unavailable`、
    `missing_clang_path`、`claim_boundary=diagnostic_only` 和 opt-in cache fields。
  - 新增 cache drift 测试，确认 `command_arguments`、`translator_feature_set`、
    `clang_lowering_identity` 变化会进入 `drifted_keys`。

TDD 红绿过程：
- 红灯：
  - 新增 focused tests 后，`run_translator()` 首先因为不接受
    `emit_clang_lowering_report` keyword 失败。
  - `cache_identity()` 因不接受 `emit_clang_lowering_report` / `environment` keyword 失败。
  - CLI 真实临时 out-root 测试因 argparse 不认识 `--emit-clang-lowering-report` 失败。
- 绿灯：
  - 增加 CLI flag、参数透传、cargo feature 注入、动态 cache identity 和 drift 字段选择后，
    focused tests 通过。
  - 根据并行只读审查建议，把 `translator_feature_set` / `clang_lowering_identity`
    从静态 `CACHE_INPUT_FIELDS` 移出，改成 lowering report opt-in 时动态加入，避免默认
    cache identity 漂移。

本轮并行只读审查结论：
- Aristotle：建议复用现有 dry-run 三层测试模式：mock cargo 命令、直接测 cache identity、
  真实 CLI + 临时 out-root；并补默认不变、dry-run 不启用 lowering、cache drift 覆盖。
  本轮已采纳。
- Wegener：确认最小实现应只改 `main()`、`run_translator()`、`emit_cache_metadata()`、
  `cache_identity()`；提醒不要刷新 repo evidence，不要把 clang version 放入全局
  `tool_versions()`，并建议 lowering identity 字段只在 opt-in cache input 中动态加入。
  本轮已采纳。

已通过命令：
```powershell
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_default_does_not_enable_clang_features validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_dry_run_does_not_enable_lowering_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_keeps_clang_lowering_report_fields_out_by_default validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_drift_invalidates_on_clang_lowering_report_identity_change validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact
python -B -m unittest validation.tools.test_auto_migrate
python -B -m unittest validation.tools.test_auto_migrate validation.tools.test_validate_auto_translation_evidence validation.tools.test_real_fdb_calc_crc32_l3_evidence
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_report_feature_writes_report_artifact_without_changing_manifest_status
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-frontend clang_frontend_feature_does_not_emit_lowering_report_without_opt_in
git diff --check -- validation/tools/auto_migrate.py validation/tools/test_auto_migrate.py
```

完整结果：
- focused Python opt-in tests：`Ran 7 tests ... OK`。
- `validation.tools.test_auto_migrate`：`Ran 54 tests ... OK`。
- 相关 Python 回归：`Ran 107 tests ... OK`。
- 两条 Rust focused tests 均通过。
- `git diff --check` 通过。

当前核心翻译功能状态：
- 默认 generated candidate 路径仍不启用 clang frontend/lowering report。
- `--emit-clang-dry-run` 仍只启用 dry-run artifact，不会启用 lowering report。
- `--emit-clang-lowering-report` 现在能通过 Python pipeline 在临时 out-root 中产出
  `l3-{slice_id}-clang-lowering-report.json`，并把该 opt-in 的 feature/env/version 身份写入
  cache metadata。
- lowering report 仍是 diagnostic-only，不影响 route、manifest status 或 semantic pass。
- real-fdb `fdb_calc_crc32` 仍未改为真实 AST 驱动生成；下一步应先做 AST 结构审计 report。

下一步建议：
1. 用 `--emit-clang-lowering-report` 和已安装 LLVM 环境对 real-fdb `fdb_calc_crc32` 做一次
   临时 out-root report，审计 AST 中真实未支持节点，而不是刷新仓库 evidence。
2. 基于 report 增加专门的 AST subset audit artifact 或测试，明确 `while(size--)`、
   `*p++`、table lookup 等节点的 lowering 缺口。
3. 再选择最小 AST lowering 子集，不要直接承诺全函数 lowering。

## 52. 2026-06-26 real-fdb clang lowering report crosses type layer

本轮承接第 51 节第 1 条下一步：用已安装 LLVM 和 `--emit-clang-lowering-report`
对 real-fdb `fdb_calc_crc32` 做临时 out-root report，并把 report 的失败点从环境/头文件/原型/类型层推进到语句层。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - 新增 `lower_function_from_clang_parse_spec_report()`，让 lowering report 复用
    `ClangParseSpec::clang_arguments()`，因此真实 AST dump 会带上 slice spec 中的 `-I...`
    和 `-D...` 参数。
  - `lower_function_from_clang_ast_dump()` 现在复用内部
    `lower_function_from_clang_ast_dump_with_arguments()`，避免裸 source-file 入口和
    parse-spec 入口逻辑分叉。
  - `find_function_decl()` 改为优先选择带 `CompoundStmt` body 的 `FunctionDecl`，
    再 fallback 到任意同名声明，避免 include header 中的 prototype 抢在函数定义前被选中。
  - `ClangTypeKind` 新增 `Void` 和 `Pointer`。
  - `type_from_qual_type()` 现在覆盖：
    - `uint32_t` / `unsigned int` -> unsigned 32-bit integer
    - `uint8_t` / `unsigned char` -> unsigned 8-bit integer
    - `size_t` -> canonical `size_t` 的 unsigned 64-bit integer
    - `unsigned long` / `unsigned long long` -> 保留自身 canonical 的 unsigned 64-bit integer
    - `void` / `const void`
    - `T *` pointer skeleton
  - `lower_type()` 现在能把 `Void` 和 `Pointer` lower 到 typed IR；`const void *`
    会被表示为非 const pointer，pointee 为 const void。
- `crates/c2r-translator/src/lib.rs`
  - `write_clang_lowering_report_artifact()` 改为调用 parse-spec aware 的 report 入口，
    使 artifact 路径不再丢失 include/define 参数。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增默认 skeleton 测试：
    `clang_lowering_skeleton_maps_const_void_pointer_and_size_t_params`。
  - 新增 opt-in 真实 clang 测试：
    `clang_parse_spec_report_uses_include_paths_for_real_ast_dump_when_enabled`。
  - 新增 opt-in 真实 clang 类型测试：
    `clang_ast_dump_lowers_uint32_integer_type_when_enabled`。
  - 新增 opt-in 真实 clang 参数测试：
    `clang_ast_dump_lowers_const_void_pointer_and_size_t_params_when_enabled`。

真实 real-fdb 临时 report 推进链：
- 修复前：`clang_ast_dump_failed`，`flashdb.h` not found。
- 带入 parse-spec include args 后：选中 header prototype，报
  `unsupported_function_body: FunctionDecl fdb_calc_crc32 does not contain a CompoundStmt body`。
- 优先选择函数定义后：报 `unsupported_clang_type: uint32_t is outside the current type skeleton`。
- 支持 `uint32_t` 后：报 `unsupported_clang_type: const void * is outside the current type skeleton`。
- 支持 `const void *` / `size_t` 后：当前真实 blocker 已推进到
  `unsupported_clang_stmt: DeclStmt is outside the current clang lowering skeleton`。

本轮并行只读审查结论：
- Meitner：确认 real-fdb 后续会依次遇到 `DeclStmt`、assignment、`WhileStmt`、
  postfix `UnaryOperator`、`ArraySubscriptExpr` 和 table lookup 等缺口；建议继续把 report
  作为 diagnostic-only surface，不要把字符串模式 translator 的 CRC32 成功误认为 clang AST lowering 成功。
- Cicero：确认 Python 侧当前 opt-in/report/cache 已够用；本轮不需要新增 Python artifact。
  如果后续加真实 clang Python 测试，应继续用临时 out-root 和 `C2R_RUN_CLANG_AST_TESTS=1`
  gate，断言 blocked/unsupported 而不是 lowered。
- Boyle：确认 IR 已经具备 `Void` / `Pointer` / `is_const` / `width_bits` 承载能力；
  建议 `const void *` 表示为非 const pointer + const void pointee，并提醒不要把普通
  `unsigned long` 误 canonical 成 `size_t`。本轮已采纳 canonical 修正。
- Bernoulli：采样真实 `fdb_calc_crc32` AST，确认函数体顶层顺序为
  `DeclStmt -> BinaryOperator("=") -> BinaryOperator("=") -> WhileStmt -> ReturnStmt`。
  因此当前第一层 blocker 是 `DeclStmt`；如果后续支持局部声明，下一层有价值 blocker
  会是 `p = (const uint8_t *)buf;` 对应的 assignment `BinaryOperator("=")`，再往后才是
  `WhileStmt`、postfix `--/++`、deref、`ArraySubscriptExpr` 和 `^/&/>>`。

已通过命令：
```powershell
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_const_void_pointer_and_size_t_params -- --nocapture
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_parse_spec_report_uses_include_paths_for_real_ast_dump_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_uint32_integer_type_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_const_void_pointer_and_size_t_params_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
git diff --check -- crates/c2r-translator/src/clang_frontend.rs crates/c2r-translator/src/lib.rs crates/c2r-translator/tests/bounded_translation.rs
```

完整结果：
- focused skeleton test：`1 passed`。
- 三条 opt-in 真实 clang smoke：均 `1 passed`。
- `--features clang-lowering-report` translator crate：`54 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。
- real-fdb 临时 out-root report：`status=unsupported`，
  `errors[0].kind=unsupported_clang_stmt`，
  `errors[0].message="DeclStmt is outside the current clang lowering skeleton"`。

当前核心翻译功能状态：
- 默认 generated candidate 路径仍不启用 clang frontend/lowering report。
- `--emit-clang-lowering-report` 能在真实 `fdb_calc_crc32` 上产出 diagnostic-only report，
  并且已经进入目标函数定义和参数类型层。
- real-fdb clang AST lowering 仍未完成；当前第一个真实语句层缺口是 `DeclStmt`。
- 已有字符串/typed-IR emitter 路径能生成 CRC32 candidate，但这不是 clang AST lowering 成功。

下一步建议：
1. 对 `DeclStmt` 做最小 AST subset audit/fixture，优先记录变量声明、初始化和局部指针类型，
   不要直接吞下整段 `while(size--)`。
2. 在 report 中显式 inventory unsupported statement/expression kinds，尤其是 `WhileStmt`、
   assignment `BinaryOperator("=")`、postfix `UnaryOperator("--"/"++")`、deref、`ArraySubscriptExpr`。
3. 再按真实 blocker 顺序选择最小 lowering 子集。

## 53. 2026-06-26 clang DeclStmt minimal lowering

本轮承接第 52 节的真实 blocker：只为 clang AST lowering report 增加最小 `DeclStmt`
支持，让 real-fdb `fdb_calc_crc32` 从局部声明层推进到下一层 assignment blocker。

核心改动：
- `crates/c2r-translator/src/clang_frontend.rs`
  - `ClangStmtSkeleton` 新增 `Decl { name, ty, init }`。
  - `stmt_skeleton_from_ast()` 现在识别 `DeclStmt`，并调用 `decl_stmt_skeleton_from_ast()`。
  - `decl_stmt_skeleton_from_ast()` 当前只接受单个、无 initializer 的 `VarDecl`：
    - 读取 `VarDecl.name`。
    - 读取 `VarDecl.type.qualType`。
    - 如果 `VarDecl` 存在 `init` 字段或 `inner` 子节点，则返回
      `Unsupported("VarDecl initializer is outside ...")`。
  - `type_from_qual_type()` 增加 `const ` qualifier peeling，使 `const uint8_t *`
    能 lower 成 pointer-to-const-uint8。
  - `lower_stmt()` 能把 `ClangStmtSkeleton::Decl` lower 成 `IrStmt::Decl`。
  - unsupported statement 诊断现在会带 opcode，例如
    `BinaryOperator opcode = is outside the current clang lowering skeleton`。
- `crates/c2r-translator/tests/bounded_translation.rs`
  - 新增 `clang_lowering_skeleton_maps_const_uint8_pointer_decl`，覆盖 deterministic
    skeleton -> typed IR declaration。
  - 新增 `clang_ast_dump_lowers_const_uint8_pointer_decl_when_enabled`，用真实 clang
    验证 `const uint8_t *p; return crc;`。
  - 新增 `clang_ast_dump_reports_assignment_opcode_statement_when_enabled`，确认 assignment
    仍 unsupported，但 report 明确给出 `BinaryOperator opcode =`。
  - 新增 `clang_ast_dump_rejects_initialized_decl_stmt_when_enabled`，确认
    `uint32_t next = crc;` 这类 initialized declaration 仍不被本轮误收。

TDD 红绿过程：
- 红灯 1：`clang_lowering_skeleton_maps_const_uint8_pointer_decl` 先失败在
  `ClangStmtSkeleton::Decl` variant 不存在。
- 绿灯 1：新增 `Decl` skeleton、`DeclStmt -> VarDecl` parser、`const uint8_t *`
  type lowering 和 `IrStmt::Decl` lowering 后，skeleton test 通过。
- 红灯 2：真实 clang `clang_ast_dump_reports_assignment_opcode_statement_when_enabled`
  先失败，错误信息只有 `BinaryOperator is outside ...`。
- 绿灯 2：unsupported statement reason 加入 `opcode` 后，该测试通过。
- 红灯 3：真实 clang `clang_ast_dump_rejects_initialized_decl_stmt_when_enabled`
  先失败，因为 initialized declaration 被误 lower 为 `lowered`。
- 绿灯 3：`decl_stmt_skeleton_from_ast()` 遇到 `init` 或 `inner` 时返回 unsupported，
  避免本轮越界支持 cast/init 表达式。

真实 real-fdb 临时 report 推进结果：
- 第 52 节末尾：`unsupported_clang_stmt: DeclStmt is outside the current clang lowering skeleton`。
- 本轮后：`unsupported_clang_stmt: BinaryOperator opcode = is outside the current clang lowering skeleton`。
- 这对应 `fdb_utils.c` 中 `p = (const uint8_t *)buf;` 的 assignment 层。

本轮并行只读审查结论：
- Mendel：采样真实 AST，确认 `const uint8_t *p;` 的形状为
  `DeclStmt -> VarDecl(name=p, type.qualType="const uint8_t *")`，无 initializer 时
  `VarDecl` 没有 `init` 和 `inner`；带 cast init 时才出现 `init` 和
  `inner[0]=CStyleCastExpr`。
- Linnaeus：确认 `IrStmt::Decl` 的最小契约是 `name/ty/init/source_span`；
  提醒 initialized declaration 会扩大支持面。本轮采纳该建议，显式拒绝 initializer。

已通过命令：
```powershell
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_lowering_skeleton_maps_const_uint8_pointer_decl -- --nocapture
$env:PATH = 'C:\Program Files\LLVM\bin;' + $env:PATH
$env:LIBCLANG_PATH = 'C:\Program Files\LLVM\bin\libclang.dll'
$env:CLANG_PATH = 'C:\Program Files\LLVM\bin\clang.exe'
$env:C2R_RUN_CLANG_AST_TESTS = '1'
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_lowers_const_uint8_pointer_decl_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_reports_assignment_opcode_statement_when_enabled -- --nocapture
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report clang_ast_dump_rejects_initialized_decl_stmt_when_enabled -- --nocapture
cargo fmt --manifest-path crates/c2r-translator/Cargo.toml
cargo test --manifest-path crates/c2r-translator/Cargo.toml --features clang-lowering-report
python -B validation/tools/auto_migrate.py --slice-spec validation/slice-specs/flashdb-real-fdb-calc-crc32.json --out-root <temp> --skip-c-oracle --skip-rust-check --emit-clang-lowering-report
python -B -m unittest validation.tools.test_auto_migrate.AutoMigrateTests.test_run_translator_emit_clang_lowering_report_enables_report_feature validation.tools.test_auto_migrate.AutoMigrateTests.test_real_fdb_calc_crc32_emit_clang_lowering_report_opt_in_writes_temp_artifact validation.tools.test_auto_migrate.AutoMigrateTests.test_cache_identity_records_emit_clang_lowering_report_opt_in
```

完整结果：
- focused DeclStmt skeleton test：`1 passed`。
- 三条真实 clang smoke：均 `1 passed`。
- `--features clang-lowering-report` translator crate：`58 passed`。
- focused Python opt-in tests：`Ran 3 tests ... OK`。
- real-fdb 临时 out-root report：`status=unsupported`，
  `errors[0].kind=unsupported_clang_stmt`，
  `errors[0].message="BinaryOperator opcode = is outside the current clang lowering skeleton"`。

当前核心翻译功能状态：
- clang AST lowering 已能跨过 real-fdb 的局部 `const uint8_t *p;` 声明。
- 当前真实 blocker 是 assignment `BinaryOperator("=")`，其中 RHS 是
  `CStyleCastExpr -> ImplicitCastExpr -> DeclRefExpr(buf)`。
- initialized declaration、assignment、while、postfix inc/dec、deref、array subscript、
  位运算仍未纳入 clang AST lowering subset。

下一步建议：
1. 先为 assignment `BinaryOperator("=")` 写最小 AST fixture，覆盖 `p = (const uint8_t *)buf;`。
2. 同时补 `CStyleCastExpr(BitCast)` 和 `DeclRefExpr` RHS 的最小表达式 lowering。
3. 继续保持 diagnostic-only report 边界，下一步目标只是把 real-fdb blocker 推进到
   `crc = crc ^ ~0U;` 或 `WhileStmt`，不是一次性 lower 完整 CRC32。
