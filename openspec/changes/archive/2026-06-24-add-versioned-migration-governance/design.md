## Context

The repo already has a machine-readable `docs/c2rust-migration-agent/baseline-record.json`, a bilingual baseline policy document, and per-slice evidence fields such as `schema_version`, `fixture_hash`, `source.commit`, `rustc_version`, and cache file hashes. These are useful, but they are spread across documents and evidence files. A future agent needs one cheap command that can be run before edits to capture the current version state and decide whether caches or prior evidence are still reusable.

仓库已经有 `docs/c2rust-migration-agent/baseline-record.json`、中英双语 baseline policy，以及分散在每个切片证据里的 `schema_version`、`fixture_hash`、`source.commit`、`rustc_version` 和 cache file hashes。问题不是没有版本信息，而是缺少一个每次切片开始前都能便宜运行、可机器读取、可作为缓存复用门禁的统一 version manifest。

## Goals / Non-Goals

**Goals:**

- Provide `flashdb-rust version-manifest` as a deterministic, dependency-free metadata command.
- Record the version fields that affect C/Rust semantic claims: agent contract, schemas, crate, source commit, OpenSpec, Rust/Cargo/Git, fixture schema, evidence schema, and Cargo.lock hash.
- Make version drift a cache invalidation and evidence review input before self-healing or archive.
- Keep the command small, safe Rust, and usable by OpenCode, Codex, or another orchestrating agent.
- Add OpenSpec requirements so future L3 slices cannot skip version governance.

**Non-Goals:**

- Do not add online version lookup, package manager integration, or automatic tool installation.
- Do not infer semver compatibility beyond the documented policy.
- Do not change FlashDB KVDB/TSDB runtime behavior or existing replay/diff semantics.
- Do not introduce new dependencies, async runtime, multithreading, or unsafe code.

## Decisions

1. **Use a CLI manifest instead of another hand-written JSON file.**
   A command can be tested, regenerated, and called by other agents. Hand-written evidence is still allowed, but it should be derived from or compared with the CLI manifest.

2. **Use fixed schema identifiers for this milestone.**
   The manifest records `agent_contract_version`, `context_schema_version`, `patch_plan_schema_version`, `fixture_schema_version`, and `evidence_schema_version` as `0.1.0`/`1` values matching the current baseline. Later schema changes must bump these values through a new OpenSpec change.

3. **Treat unavailable tools as explicit version states.**
   If `rustc`, `cargo`, `git`, or `openspec` cannot be executed, the manifest records `NOT_FOUND` rather than failing. Specific gates may still fail later if a required tool is absent.

4. **Keep cache invalidation conservative.**
   The manifest exposes cache key inputs instead of deciding cache reuse internally. The orchestrator invalidates ContextPack, PatchPlan, C oracle, and AI candidate caches when any listed input drifts.

## Risks / Trade-offs

- **Tool versions may differ by host** -> The manifest records current host versions and does not claim portability unless CI/WSL evidence records matching or acceptable versions.
- **Static source commit can become stale** -> Future FlashDB source updates must change the manifest source commit and invalidate all old L3 semantic claims.
- **Extra metadata can grow noisy** -> Keep the first command minimal and add optional fields only through minor schema bumps.
- **PowerShell encoding can corrupt bilingual docs** -> Use UTF-8 no BOM and run `git diff --check` after edits.

## Migration Plan

1. Add OpenSpec artifacts and validate the change.
2. Add a red CLI test for `version-manifest`.
3. Implement the smallest manifest command.
4. Generate version-governance evidence and update docs.
5. Validate, archive, commit, and push before starting the next semantic slice.

## Open Questions

- None for this slice. Future changes can decide whether `version-manifest` should include AI provider/model metadata when AI is actually used.
