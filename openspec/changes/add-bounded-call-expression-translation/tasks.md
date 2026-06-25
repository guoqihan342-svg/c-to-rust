## 1. OpenSpec Contract

- [x] 1.1 Validate proposal, design, spec delta, and tasks with `openspec validate add-bounded-call-expression-translation --strict`

## 2. Translator TDD

- [x] 2.1 Add failing translator tests for return, declaration initializer, and assignment call expressions requiring `call_expression` and `bounded-call-expression`
- [x] 2.2 Add failing translator tests proving nested calls, function pointer calls, and side-effect arguments are blocked without Rust draft
- [x] 2.3 Preserve the existing simple call statement test and rule behavior

## 3. Translator Implementation

- [x] 3.1 Implement a bounded direct call expression parser for identifier callees and safe argument splitting
- [x] 3.2 Record call expression annotations in CFG statement kinds and translation rule ids
- [x] 3.3 Reject unsupported call expression forms with `unsupported_syntax` before Rust draft generation
- [x] 3.4 Keep generated Rust output compatible for supported call expressions
- [x] 3.5 Preserve call expression evidence in normalized `auto_migrate` plan and context pack

## 4. Validation And Delivery

- [x] 4.1 Run `cargo fmt --manifest-path crates/c2r-translator/Cargo.toml -- --check`
- [x] 4.2 Run `cargo test --manifest-path crates/c2r-translator/Cargo.toml`
- [x] 4.3 Run targeted `validation.tools.test_auto_migrate` call-expression evidence test
- [x] 4.4 Run `openspec validate add-bounded-call-expression-translation --strict` and `openspec validate --all`
- [x] 4.5 Run `git diff --check`
