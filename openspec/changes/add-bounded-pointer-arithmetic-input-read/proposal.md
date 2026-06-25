## Why

当前 bounded translator 已能把 `values[i]` 这类有 `i < len` 证明的只读输入 buffer 访问降到 safe Rust slice 读取，但真实 C 代码经常写成等价的 `*(values + i)`。如果右值指针算术读既不被安全识别，也不被明确拒绝，自动翻译管线会在含指针 slice 上留下假阴性或假成功风险。

本变更把 `*(values + i)` 纳入受限、可证明、只读 input-buffer read，而不是扩展到任意 C 指针算术。

## What Changes

- 在 translator 中识别 proven bounded loop 内的 `*(base + index)` 只读输入 buffer 访问，并 canonicalize 为 `base[index]` / `base[index as usize]` 的 safe Rust 读取。
- 在 context pack、CFG、pointer graph、translation plan、events 中记录原始读形态、规范化读形态、length companion 和翻译规则 id。
- 对无边界证明、复杂 base/index、副作用 index、写入形态 `*(out + i) = ...`、非只读 input pointer 的指针算术继续拒绝，不生成 false-success Rust draft。
- 增加 `sum_i32_ptr_arith` L3 demo slice，复用 C oracle + Rust replay + schema diff + negative diff + unsafe scan + version/cache binding + OpenSpec gate。
- 不引入 breaking change；现有 `values[i]`、output pointer write、FlashDB TSDB 和已有 L2/L3 evidence 语义保持不变。

## Capabilities

### New Capabilities

- `pointer-arithmetic-input-read-l3-demo-slice`: 记录 `sum_i32_ptr_arith` 作为受限 pointer arithmetic input read 的 L3 demo slice 验收合同。

### Modified Capabilities

- `bounded-auto-translation-pipeline`: 增加 `*(values + i)` 受限只读 input-buffer read 的自动翻译、拒绝条件、证据字段和 L3 接入要求。

## Impact

- `crates/c2r-translator/`: bounded read 检测、CFG kind/rule、pointer read effects、Rust expression lowering、负向拒绝。
- `validation/slice-specs/`: 新增 `demo-sum-i32-ptr-arith.json`。
- `validation/l2_slices/`: 新增 Rust replay slice、C oracle fixture generator、fixture、unit test、report emitter evidence。
- `validation/tools/`: auto_migrate normalization、evidence summary validator、L3 evidence tests。
- `validation/evidence/demo/`: 新增 committed L3 evidence artifacts 和 auto-translation evidence root。
- `scripts/run-full-regression.ps1`: 新增 short smoke semantic gate。
- `openspec/changes/add-bounded-pointer-arithmetic-input-read/`: proposal、design、spec delta、tasks。
