# Multi-Project C-to-Rust Validation

中文：本目录用于管理“十几个复杂 C 项目”的迁移验证候选集。当前阶段已完成 L0 目录校验、远程 HEAD 探测，以及 40/40 个项目的 L1 native C build/test smoke 尝试；这仍不代表这些项目已经迁移成功，也不代表语义等价已经证明。

English: this directory tracks candidate projects for broader C-to-Rust migration validation. The current milestone proves L0 catalog validity, remote HEAD reachability, and 40/40 L1 native C build/test smoke attempts; it does not claim migration success or semantic equivalence for the listed projects.

## Files

- `projects.json`: versioned catalog of complex C/C-major validation targets.
- `gates.md`: L0-L3 validation gates and evidence requirements.
- `evidence/catalog-validation.json`: latest offline catalog validation report.
- `evidence/catalog-remote-probe.json`: latest optional remote HEAD probe report.
- `evidence/l1-native-summary.json`: latest compact L1 native C build/test smoke summary.
- `evidence/wave2-l1-native-summary.json`: compact L1 summary for the 18 wave2 targets.
- `evidence/remaining-l1-native-summary.json`: compact L1 summary for the final 4 catalog targets that previously had no L1 attempt.
- `evidence/l1-failure-classification.json`: machine-readable classification for failed L1 attempts.
- `evidence/l1-failure-classification.md`: reviewer-friendly failed L1 classification summary.
- `evidence/l1-low-cost-remediation-summary.json`: machine-readable low-cost remediation rerun summary.
- `evidence/l1-low-cost-remediation-summary.md`: reviewer-friendly low-cost remediation rerun summary.
- `l3-template/`: reusable L3 evidence template, checklist, schema, and example for bounded C/Rust semantic-equivalence claims.
- `l3-template/config-profile.schema.json`: reusable schema for L3 macro/config/feature profile evidence.
- `l3-template/config-profile.example.json`: FlashDB example profile tied to `flashDB_rust/oracle/fdb_cfg.h`.
- `environment-profiles/huawei-competition-ubuntu-24.04/`: machine-readable competition environment profile, Huawei mirror configs, and a toolchain self-check script.
- `pointer-graph-template/`: reusable pointer dependency graph template for pointer-bearing L2/L3 migration slices.
- `test-translation-template/`: reusable code-test translation manifest template for mapping C tests, fixtures, or oracle expectations to Rust tests and invalidation keys.

## Fast Commands

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\validate-c-project-catalog.ps1 -ProbeRemote
```

The verifier is intentionally lightweight. It does not clone large repositories. Future per-project changes must pin commits, clone outside this repository, run the native C build/test smoke, define a bounded migration slice, and add C/Rust differential evidence before claiming deeper success.

## Competition Environment Profile

The default competition profile is `validation/environment-profiles/huawei-competition-ubuntu-24.04/environment.json`. L1/L3 evidence generated on the evaluation host should record the profile path and hash. The profile explicitly marks Go and CMake as unavailable, so default competition gates must use Cargo, Python, gcc/g++, and GNU Make paths unless a slice records a non-default environment.

## Real Source Slice Extraction

中文：真实源码函数必须先由 `validation/tools/extract_source_slice.py` 生成 slice spec，再交给 `validation/tools/auto_migrate.py`。手写 `c_source` 只能作为 demo 或临时 fixture，不能作为真实自动翻译能力证据。

English: real-source functions must first be converted into a generated slice spec by `validation/tools/extract_source_slice.py`, then passed to `validation/tools/auto_migrate.py`. A hand-written `c_source` string is only acceptable for demos or temporary fixtures; it is not evidence of real automatic translation capability.

```powershell
python validation/tools/extract_source_slice.py `
  --repo-root F:\path\to\CProject `
  --source-file src/example.c `
  --function add_one `
  --target-id example `
  --slice-id real-add-one `
  --source-commit <pinned-commit> `
  --compiler-command-source compile_commands.json `
  --out validation/slice-specs/example-real-add-one.json

python validation/tools/auto_migrate.py `
  --slice-spec validation/slice-specs/example-real-add-one.json `
  --skip-c-oracle
```

## C2Rust Baseline, Route, And Validation Profile

中文：`auto_migrate.py` 现在会为每个自动迁移 slice 生成三类一等证据：`l3-<slice>-c2rust-baseline-manifest.json`、`l3-<slice>-route-decision.json` 和 `l3-<slice>-validation-profile.json`。C2Rust baseline 只是候选上下文或交叉检查，不能替代原始 C oracle、Rust replay、schema-aware diff、negative diff、unsafe ledger 或 final verification。缺少 C2Rust 可执行文件时必须记录 `skipped` 或 `blocked`，不能伪造生成成功。

English: `auto_migrate.py` now emits three first-class evidence files for each automatic migration slice: `l3-<slice>-c2rust-baseline-manifest.json`, `l3-<slice>-route-decision.json`, and `l3-<slice>-validation-profile.json`. The C2Rust baseline is candidate context or cross-check evidence only; it never replaces the original C oracle, Rust replay, schema-aware diff, negative diff, unsafe ledger, or final verification. Missing executable C2Rust tooling must be recorded as `skipped` or `blocked`, never as a generated success.

中文：route decision 只决定候选生成路径和上下文预算；validation profile 决定本次运行必须通过的 gates。任何 Agent、C2Rust、手写规则或 Rust 编译通过的输出，只有在 selected validation profile 通过且没有 skipped required gate 时，才可以被绑定为 semantic pass。

English: the route decision controls candidate generation path and context budget only; the validation profile controls the required gates for the run. Output from an Agent, C2Rust, deterministic rules, or Rust compilation can be bound as a semantic pass only when the selected validation profile passes with no skipped required gate.

中文：`route_decision.level=L0` 是自动翻译内部的 deterministic zero-token candidate routing，只表示该候选不需要额外 AI/token 路线；它不是 catalog L0，不是 L1/L2/L3 evidence，也不证明 C/Rust 语义等价。`semantic_pass` 和 `generated_draft_semantic_pass` 在独立 validation gates 接受 exact draft 之前必须保持 `false`。

English: `route_decision.level=L0` is internal deterministic zero-token candidate routing for automatic translation; it only means the candidate path does not need an additional AI/token route. It is not catalog L0, not L1/L2/L3 evidence, and not proof of C/Rust semantic equivalence. `semantic_pass` and `generated_draft_semantic_pass` must remain `false` until independent validation gates accept the exact draft.

中文：历史 accepted auto-translation fixtures 若要被当前 `--require-semantic-pass` 直接验证，也必须持久化 baseline/route/profile refs，并补齐 schema-aware diff / negative-diff gate metadata。只在单元测试 helper 中临时补字段不是可提交的 pass evidence。

English: legacy accepted auto-translation fixtures must persist baseline/route/profile refs and schema-aware diff / negative-diff gate metadata before they can pass the current `--require-semantic-pass` path. Helper-only backfill inside unit tests is not committed pass evidence.

## Current Candidate Count

The catalog currently contains 40 targets across database/storage, networking, crypto, media, runtime, allocator, image/codec, terminal/system, kernel/virtualization, document processing, scientific data, VPN, packet analysis, and embedded domains.

## Wave2 Boundary

中文：Wave2 增加了 18 个 GitHub 可达的超复杂 C/C-major 目标。本轮已经对 18/18 个 wave2 目标执行 L1 native C build/test smoke：8 个通过，10 个失败，失败项目仍作为可审计 evidence 保留。L1 只证明 pinned native C baseline 的构建/烟测尝试，不证明 Rust 迁移、unsafe 预算、性能保持或 C/Rust 语义等价。

English: Wave2 adds 18 GitHub-reachable super-complex C/C-major targets. This round attempted L1 native C build/test smoke for 18/18 wave2 targets: 8 passed and 10 failed, with failures preserved as auditable evidence. L1 only proves pinned native C baseline build/smoke attempts; it does not prove Rust migration, unsafe budget, performance preservation, or C/Rust semantic equivalence.

## Full L1 Attempt Boundary

中文：当前 40 个 catalog 目标都已经有 L1 native C build/test smoke 尝试证据：31 个通过，9 个失败，`not_attempted_catalog_projects` 为空。失败项目仍保留为可审计 evidence，后续若要提升通过率，应针对失败命令和依赖开独立修复 change。

English: all 40 catalog targets now have L1 native C build/test smoke attempt evidence: 31 passed and 9 failed, with an empty `not_attempted_catalog_projects` list. Failed projects remain auditable evidence; improving their pass rate should be handled through separate changes focused on the failed commands and dependencies.

## L1 Failure Classification

中文：17 个 L1 failed 项目已经完成诊断分类。主要类别包括缺少开发包、缺少构建工具、git checkout 需要 bootstrap/autogen、构建配方冲突、环境限制、clone/network failure、timeout、evidence gap 等。该分类只用于决定后续修复顺序，不会把失败项目改为通过。

English: the 17 failed L1 projects have diagnostic classifications. Major categories include missing development packages, missing build tools, git-checkout bootstrap requirements, build recipe conflicts, environment restrictions, clone/network failure, timeout, and evidence gaps. The classification is only for remediation planning; it does not convert failed projects to passed.

## L1 Low-Cost Remediation

中文：本轮对 9 个低成本候选执行了 fresh L1 native C build/test smoke 重跑：8 个通过，1 个失败。新增通过项目为 `ffmpeg`、`hdf5`、`libevent`、`libgit2`、`libpcap`、`librdkafka`、`libuv` 和 `tcpdump`。`openvpn` 已通过 `--disable-dco` 绕过 DCO 的 libnl-genl 依赖，但当前 Linux configure 路径仍强依赖 `libcap-ng` 开发包，因此继续保留为失败证据。

English: the low-cost remediation batch reran 9 fresh L1 native C build/test smoke candidates: 8 passed and 1 failed. Newly passing projects are `ffmpeg`, `hdf5`, `libevent`, `libgit2`, `libpcap`, `librdkafka`, `libuv`, and `tcpdump`. `openvpn` bypassed the DCO libnl-genl dependency with `--disable-dco`, but the current Linux configure path still requires the `libcap-ng` development package, so it remains failed evidence.

## Non-Equivalence Boundary

Passing catalog validation means only:

- the catalog schema is valid,
- each target has required migration metadata,
- target ids are unique,
- optional remote probes can reach upstream HEADs when enabled.

It does not mean:

- the original C project builds locally,
- any Rust translation compiles,
- unsafe ratio is below the project budget,
- C/Rust behavior is equivalent,
- performance is preserved.

Those claims require L1-L3 evidence described in `gates.md`.
