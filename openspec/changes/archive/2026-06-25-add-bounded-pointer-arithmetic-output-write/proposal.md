## Why

当前 bounded translator 已经能处理 `values[i]` 和受限的 `*(values + i)` 输入读取，但真实 C slice 也常见 `*(out + i) = ...` 这种输出 buffer 写入。若继续把它作为完全 unsupported，自动翻译能力会停留在“读 buffer + 标量 out-param”阶段；若直接放开任意 pointer arithmetic，则会破坏当前安全边界。

This change adds a narrow, proven output-buffer write capability while keeping arbitrary C pointer arithmetic out of scope.

## What Changes

- 在 translator 中识别 proven bounded loop 内的 `*(out + i) = expr` 输出 buffer 写入，并降低为 safe Rust mutable slice 写入。
- 在 CFG、pointer graph、translation plan、events 中记录 raw write `*(out + i)`、canonical write `out[i]`、length companion、rule id `bounded-pointer-arithmetic-output-write`。
- 继续拒绝无 loop bound、复杂 base/index、副作用 index、compound assignment、未证明 aliasing、非 `int*` output buffer 的 pointer arithmetic 写入。
- 增加 `copy_i32_ptr_arith` L3 demo slice，用 C oracle + Rust replay + schema diff + negative diff + unsafe scan + version/cache binding + OpenSpec gate 验证实际 `out_values`。
- 不引入 breaking change；现有 `out[0]` 标量 out-param、`values[i]`、`*(values + i)` input read、FlashDB TSDB 和已有 L2/L3 evidence 语义保持不变。

## Capabilities

### New Capabilities

- `pointer-arithmetic-output-write-l3-demo-slice`: 记录 `copy_i32_ptr_arith` 作为受限 pointer arithmetic output write 的 L3 demo slice 验收合同。

### Modified Capabilities

- `bounded-auto-translation-pipeline`: 增加 `*(out + i) = expr` 受限 output-buffer write 的自动翻译、拒绝条件、证据字段和 L3 接入要求。

## Impact

- `crates/c2r-translator/`: lvalue parsing、bounded loop proof、CFG kind/rule、pointer write effects、safe Rust emit、负向拒绝。
- `validation/slice-specs/`: 新增 `demo-copy-i32-ptr-arith.json`。
- `validation/l2_slices/`: 新增 Rust replay slice、C oracle fixture generator、fixture、unit test、report emitter evidence。
- `validation/tools/`: auto_migrate normalization、evidence summary validator、L3 evidence tests。
- `validation/evidence/demo/`: 新增 committed L3 evidence artifacts 和 auto-translation evidence root。
- `scripts/run-full-regression.ps1`: 新增 short smoke semantic gate。
- `openspec/changes/add-bounded-pointer-arithmetic-output-write/`: proposal、design、spec delta、tasks。
