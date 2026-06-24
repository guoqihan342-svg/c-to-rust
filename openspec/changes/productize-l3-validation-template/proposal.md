## Why

FlashDB L3 slices already produce strong evidence chains, but the required files, pass/fail semantics, and verification order are still spread across individual slice artifacts. Productizing this as a reusable template prevents future C-to-Rust L3 work from copying an incomplete subset or making broader semantic-equivalence claims than the evidence supports.

FlashDB L3 已经有多条高质量验证链，但文件清单、通过语义和验证顺序仍分散在单个切片证据中。把它产品化为可复用模板，可以避免后续 C-to-Rust L3 工作漏掉关键证据或扩大语义等价声明。

## What Changes

- Add `validation/l3-template/` as a reusable L3 evidence template for FlashDB and future C project slices.
- Define required and optional L3 evidence files, including slice contract, context pack, C oracle, Rust replay, schema-aware diff, negative diff, unsafe scan/ledger, performance smoke, final verification, and version manifest references.
- Add a small machine-readable template manifest, JSON schema, and example so future agents can validate expected evidence names and statuses without reading every historical slice.
- Add a checklist and README that explain the minimum L3 pass semantics and non-goal boundary language.
- Add OpenSpec requirements for template completeness, negative evidence, version/cfg binding, and limited semantic-equivalence claims.

## Capabilities

### New Capabilities

- `l3-validation-template`: Covers reusable L3 evidence template files, required pass semantics, version binding, and claim boundaries for bounded C-to-Rust migration slices.

### Modified Capabilities

- None.

## Impact

- Affected docs/templates: `validation/l3-template/`, `validation/README.md`, `validation/gates.md`.
- Affected specs: new OpenSpec capability under this change.
- No Rust runtime behavior changes.
- No new dependencies.
- No changes to existing L3 evidence files beyond referencing them as examples.
