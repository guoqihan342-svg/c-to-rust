# Auto Translation Evidence Checklist

- [ ] Slice spec is ready and references accepted L1 evidence.
- [ ] Type map, CFG, and pointer graph are recorded before Rust draft generation.
- [ ] Unsupported type or control-flow nodes are recorded and block false success claims.
- [ ] Auto-translation plan records generated artifacts, source spans, generated spans, translation rule ids, unsupported count, and unsafe candidate count.
- [ ] Auto-translation events JSONL records every major step, unsupported node, rustc failure, patch plan, patch application, verification rerun, and block.
- [ ] AI is not required for the default local pipeline.
- [ ] AI candidate manifest records prompt scope, input hashes, output hash, applied status, and gate outcome when AI is used.
- [ ] AI output is never cited as correctness evidence.
- [ ] PatchPlan exists before applying any automatic patch.
- [ ] Repair round is within the configured limit, default maximum three.
- [ ] Forbidden changes are blocked: C oracle contract, fixture expected behavior, accepted metadata differences, public API outside impact set, source slice boundary, and unsafe budget policy.
