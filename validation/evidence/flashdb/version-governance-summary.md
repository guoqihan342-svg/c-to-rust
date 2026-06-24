# Version Governance Evidence

## English

- Change: `add-versioned-migration-governance`
- Version manifest: `validation/evidence/flashdb/version-governance-manifest.json`
- Manifest SHA256: `c676278f841eaa79c97d5444b6be219682873e82d0ee9aeadd709266760cb4fa`
- OpenSpec version: `1.4.1`
- Rust/Cargo: `rustc 1.95.0 (59807616e 2026-04-14)` / `cargo 1.95.0 (f2d3ce0bd 2026-03-21)`
- FlashDB source commit: `93d175549da579b8abac07bd175ce4c3f9dde829`
- Rust crate version: `flashdb_rust 0.1.0`

This slice adds an executable version-manifest gate for future FlashDB L3 migration slices. The gate records the agent contract, context schema, PatchPlan schema, fixture schema, evidence schema, Rust crate, source commit, toolchain, host, Cargo hashes, feature matrix, and cache key inputs before cached artifacts or previous evidence can be reused.

The red test was preserved at `validation/evidence/flashdb/version-governance-red-test.log`; it failed on `unknown command version-manifest` before implementation. The green check is `cargo test --test cli_smoke cli_version_manifest_writes_version_governance_report -- --nocapture`.

## 中文

- 变更：`add-versioned-migration-governance`
- 版本清单：`validation/evidence/flashdb/version-governance-manifest.json`
- 清单 SHA256：`c676278f841eaa79c97d5444b6be219682873e82d0ee9aeadd709266760cb4fa`
- OpenSpec 版本：`1.4.1`
- Rust/Cargo：`rustc 1.95.0 (59807616e 2026-04-14)` / `cargo 1.95.0 (f2d3ce0bd 2026-03-21)`
- FlashDB 源码提交：`93d175549da579b8abac07bd175ce4c3f9dde829`
- Rust crate 版本：`flashdb_rust 0.1.0`

本切片增加可执行的 version-manifest 门禁，供后续 FlashDB L3 迁移切片在复用缓存或历史证据前记录版本状态。门禁覆盖 Agent contract、context schema、PatchPlan schema、fixture schema、evidence schema、Rust crate、源码提交、工具链、主机、Cargo 哈希、特性矩阵和缓存键输入。

红灯测试保存在 `validation/evidence/flashdb/version-governance-red-test.log`，实现前失败原因为 `unknown command version-manifest`。绿灯验证命令是 `cargo test --test cli_smoke cli_version_manifest_writes_version_governance_report -- --nocapture`。

范围决策：这次只增加可执行版本门禁和未来 L3 需求，不批量迁移历史 fixture/evidence schema。后续若 `cache_key_inputs` 任一字段漂移，ContextPack、PatchPlan、AI 候选补丁、C oracle 报告和 schema-aware diff 结论必须重新生成或显式复核后才能复用。
