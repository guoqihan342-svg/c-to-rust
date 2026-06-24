## Why

当前 L2 slices 已有 C oracle、Rust report、schema-aware diff 和 `unsafe-scan.json`，但证据还没有形成完整 unsafe ledger，也没有 L2 negative diff 来证明差分门禁能捕获故意错误。`zlib-adler32` 现有 fixture 数量较少，适合作为第一个小而精的 deterministic differential corpus 扩展点。

## What Changes

- 为 `validation/l2_slices` 生成 `unsafe-ledger.json`，即使 first-party non-test unsafe 数量为 0 也必须产出账本证据。
- 扩展 `zlib-adler32` C oracle fixture，使用固定 seed 的 deterministic byte corpus 覆盖 Adler32 长度边界、NMAX 周边和随机形态输入。
- 生成 `zlib-adler32-negative-diff.json`，通过故意篡改一个 C oracle value 证明 L2 diff gate 能捕获 mismatch。
- 更新 L2 summary 和 `validation/gates.md`，让新的证据成为 L2 pass 的一部分。
- 不引入 `cargo-fuzz`、`proptest`、`quickcheck` 或 AI-dependent verification。

## Capabilities

### New Capabilities

- `supercomplex-l2-slice-validation`: Covers L2 unsafe ledger evidence, bounded deterministic differential corpus requirements, and L2 negative diff self-check evidence.

### Modified Capabilities

- None.

## Impact

- Affected code: `validation/l2_slices/tools/generate_oracles.py`, `validation/l2_slices/src/bin/emit_reports.rs`.
- Affected evidence: `validation/l2_slices/fixtures/zlib-adler32-c-oracle.json`, `validation/evidence/l2-slices/*.json`.
- Affected docs/gates: `validation/gates.md`.
- Dependencies: no new Rust or Python dependency.
