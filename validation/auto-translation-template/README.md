# Auto Translation Evidence Template

This directory defines evidence contracts for bounded automatic translation and compile self-healing.

中文说明：这些模板只记录候选生成、自愈补丁和阻断原因。自动翻译产物默认是 candidate，不是 accepted implementation。AI 输出也只能作为候选来源，不能作为正确性证据。

## Evidence Files

- `auto-translation-plan.schema.json`: generated artifacts, source/generated spans, translation rule ids, unsafe candidate count, and required verification gates.
- `auto-translation-event.schema.json`: one JSONL record for `l3-<slice>-auto-translation-events.jsonl`.
- `ai-candidate-manifest.schema.json`: optional AI usage manifest. Default local pipeline must not require AI.
- `patch-event.schema.json`: one JSONL PatchPlan/patch record for `l3-<slice>-patch-events.jsonl`.
- `blocked-repairs.schema.json`: blocked repair records for semantic or safety boundary violations.
- Auto-translation semantic-pass fixtures must also persist `l3-<slice>-c2rust-baseline-manifest.json`, `l3-<slice>-route-decision.json`, and `l3-<slice>-validation-profile.json`. The manifest refs must carry `path`, `status`, and `sha256`, while cache identities use canonical JSON hashes rather than file-byte hashes.
- 中文：自动翻译 fixture 如果要被当前 `--require-semantic-pass` 直接验证，必须把 `c2rust_baseline`、`route_decision`、`validation_profile` 三类证据落盘并写入 auto manifest、L3 evidence manifest、final verification 和 cache metadata。测试 helper 临时补字段不能作为可提交 evidence。

## Rules

- Slice spec, type map, CFG, and pointer graph must be recorded before Rust draft generation.
- PatchPlan evidence must exist before automatic patch application.
- Default repair retry limit is three rounds.
- Repairs that edit oracle contracts, fixture expected behavior, accepted differences, public API outside the impact set, source slice boundaries, or unsafe budget policy must be blocked.
- Final acceptance still requires C oracle, Rust replay, schema-aware diff, negative diff, unsafe evidence, version/config binding, cache metadata, final verification, and OpenSpec validation.
- Schema-aware diff and negative-diff reports must carry their gate metadata (`diff_gate`, `negative_diff_gate`, accepted-evidence refs, required inputs, and mutation evidence) when the evidence manifest claims `passed`.
- 中文：C2Rust baseline 只是候选上下文或交叉检查；route 只选择候选路径；validation profile 才定义 required gates。三者缺失或 stale refs 漂移时，自动翻译产物不能 claim semantic pass。
