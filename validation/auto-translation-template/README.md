# Auto Translation Evidence Template

This directory defines evidence contracts for bounded automatic translation and compile self-healing.

中文说明：这些模板只记录候选生成、自愈补丁和阻断原因。自动翻译产物默认是 candidate，不是 accepted implementation。AI 输出也只能作为候选来源，不能作为正确性证据。

## Evidence Files

- `auto-translation-plan.schema.json`: generated artifacts, source/generated spans, translation rule ids, unsafe candidate count, and required verification gates.
- `auto-translation-event.schema.json`: one JSONL record for `l3-<slice>-auto-translation-events.jsonl`.
- `ai-candidate-manifest.schema.json`: optional AI usage manifest. Default local pipeline must not require AI.
- `patch-event.schema.json`: one JSONL PatchPlan/patch record for `l3-<slice>-patch-events.jsonl`.
- `blocked-repairs.schema.json`: blocked repair records for semantic or safety boundary violations.

## Rules

- Slice spec, type map, CFG, and pointer graph must be recorded before Rust draft generation.
- PatchPlan evidence must exist before automatic patch application.
- Default repair retry limit is three rounds.
- Repairs that edit oracle contracts, fixture expected behavior, accepted differences, public API outside the impact set, source slice boundaries, or unsafe budget policy must be blocked.
- Final acceptance still requires C oracle, Rust replay, schema-aware diff, negative diff, unsafe evidence, version/config binding, cache metadata, final verification, and OpenSpec validation.
