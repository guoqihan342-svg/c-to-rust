英文镜像见 `README.en.md`。

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
- Generated C2Rust baseline manifests must include `compile` evidence bound to the same output path/status/sha256. The compile check is compile-only candidate evidence, not semantic acceptance.
- 中文：`status=generated` 的 C2Rust baseline manifest 必须包含与同一 output path/status/sha256 绑定的 `compile` 证据；该检查只是候选产物 compile-only 证据，不能替代 oracle/diff 语义接受。
- Generated validation profiles must bind the default competition environment profile through `competition_environment.profile_id`, `path`, and `sha256`; cache metadata must carry the matching `competition_environment_identity` in `cache_input_fields`.
- 中文：新生成的 validation profile 必须通过 `competition_environment.profile_id`、`path` 和 `sha256` 绑定默认比赛环境 profile；cache metadata 必须在 `cache_input_fields` 中写入一致的 `competition_environment_identity`。
- Newly generated pointer graphs use schema v2. If pointer effects make the slice alias-sensitive, the validator requires `effect_graph`; cache metadata must include `effect_graph_identity` in `cache_input_fields`.
- 中文：新生成的 pointer graph 使用 schema v2。若指针 effect 让 slice 进入 alias-sensitive 状态，validator 会要求 `effect_graph`；cache metadata 必须在 `cache_input_fields` 中包含 `effect_graph_identity`。

## Alias Gate Summary

English: `translation_summary.alias_gate` carries the translator's current alias decision for the generated candidate. It is derived from the slice spec pointer contract and the pointer graph. It does not prove correctness by itself; it only records whether the candidate is not applicable, allowed by evidence, candidate-only, blocked, or requires an explicit noalias contract.

中文：`translation_summary.alias_gate` 记录生成候选代码时的 alias 决策，来源是 slice spec 的 pointer contract 和 pointer graph。它本身不证明正确性，只说明当前候选是 not applicable、已有证据允许、仅候选、被阻断，还是需要显式 noalias 契约。

English: if the alias decision changes, cache metadata must invalidate the Rust draft, C oracle binding, Rust replay, diff, unsafe evidence, final verification, and summary.

中文：如果 alias 决策变化，cache metadata 必须让 Rust draft、C oracle 绑定、Rust replay、diff、unsafe evidence、final verification 和 summary 失效或重新审核。

English: effect graph identity is part of the same cache boundary. If read/write effect counts, participating pointer nodes, alias-sensitive status, or the final alias-gate decision changes, generated candidates and downstream evidence must be regenerated or explicitly reviewed.

中文：effect graph identity 属于同一个缓存边界。只要 read/write effect 数量、参与的 pointer node、alias-sensitive 状态或最终 alias-gate decision 变化，生成候选和下游 evidence 都必须重新生成或显式复核。

## Rules

- Slice spec, type map, CFG, and pointer graph must be recorded before Rust draft generation.
- PatchPlan evidence must exist before automatic patch application.
- Default repair retry limit is five repair rounds.
- Repairs that edit oracle contracts, fixture expected behavior, accepted differences, public API outside the impact set, source slice boundaries, or unsafe budget policy must be blocked.
- Final acceptance still requires C oracle, Rust replay, schema-aware diff, negative diff, unsafe evidence, version/config binding, cache metadata, final verification, and Superpowers validation.
- A change to `config/competition-env/environment.json` invalidates generated translation cache identity until the affected artifacts are regenerated or explicitly reviewed as non-competition evidence.
- 中文：`config/competition-env/environment.json` 变化会让已生成翻译缓存身份失效；受影响 artifacts 必须重新生成，或显式标注为非比赛环境 evidence 并单独审核。
- A route may choose an L0 deterministic candidate path for scalar-only `GenericTypedIr` candidates whose `candidate_route.token_cost=0`, but that is route/cost/provenance classification only. The generated Rust draft remains candidate evidence until C oracle, Rust replay, schema-aware diff, negative diff, unsafe evidence, and final verification accept the exact draft.
- 中文：scalar-only 的 `GenericTypedIr` candidate 如果带有 `candidate_route.token_cost=0`，route 可以选择 L0 deterministic candidate path；这只表示 route/cost/provenance 分类。生成的 Rust draft 仍只是 candidate evidence，必须等 C oracle、Rust replay、schema-aware diff、negative diff、unsafe evidence 和 final verification 接受 exact draft 后才可进入最终接受结论。
- Schema-aware diff and negative-diff reports must carry their gate metadata (`diff_gate`, `negative_diff_gate`, accepted-evidence refs, required inputs, and mutation evidence) when the evidence manifest claims `passed`.
- 中文：C2Rust baseline 只是候选上下文或交叉检查；route 只选择候选路径；validation profile 才定义 required gates。三者缺失或 stale refs 漂移时，自动翻译产物不能 claim semantic pass。
