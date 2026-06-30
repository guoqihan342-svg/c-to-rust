---
name: c2rust-migration
description: Repo-owned workflow for C-to-Rust migration harness work in this repository. Use when Codex works on FlashDB or other C-to-Rust slices, C2Rust baselines, oracle/replay/diff evidence, unsafe-reduction repair loops, typed-IR candidate diagnostics, migration evidence refreshes, or multi-agent worker handoffs.
---

# C2Rust Migration

Use this skill when working on C-to-Rust migration slices in this repository. The competition-facing priority is the harness / agent / workflow loop, not broad handwritten transpiler coverage.

## Mainline

1. Start from a real C unit or slice spec.
2. Produce or inspect the C2Rust/raw candidate baseline.
3. Compile the Rust candidate or record the compile failure as evidence.
4. Run C oracle / Rust replay / schema-aware diff when the slice supports it.
5. Record unsafe ledger, route decision, validation profile, and workflow metrics.
6. Only accept semantic progress when current evidence proves equivalence for the declared slice boundary.

Typed IR and generic emitter work is supporting infrastructure: use it for trivial fast paths, candidate diagnostics, and fail-closed feature gaps. Do not let typed-IR coverage expansion displace the verified harness loop.

## Repair Loop

- Default repair cap is 5 rounds.
- Each worker round proposes one minimal patch with one intended safety or compile effect.
- After each patch, rerun the narrow compile/test/oracle checks that cover the changed behavior.
- Accept a patch only when the candidate still passes the relevant oracle/diff gate and the unsafe delta or compile status improves.
- On failure, roll back to the last-good candidate, write a repair hint from the concrete error stack or diff, and continue until the cap is reached.
- Never repair by weakening fixtures, accepted-difference policy, public API boundaries, slice boundaries, unsafe budgets, or oracle expectations.

## Worker Handoff

- Give each worker one unit, one out-root, and one expected artifact set.
- Keep generated artifacts under repository-scoped or explicitly named output roots.
- Do not share mutable output directories between workers.
- Require each worker to report commands, artifact paths, status, and blocked reason.
- Merge worker output only after checking current files and evidence directly.

## Evidence Rules

- Prefer existing repo scripts before adding new runtime code.
- Treat C2Rust output as candidate context and baseline material, not final semantic proof.
- Keep tool operations repository-confined: accept only POSIX relative paths, reject absolute paths, drive prefixes, backslashes, `~`, and `..` for repo MCP inputs.
- For docs, keep the Chinese source and English mirror synchronized in the same change.
- For coverage claims, update the relevant coverage matrix or workflow metrics artifact instead of relying on checklist percentages.
- For competition environment work, make tool assumptions explicit; do not silently depend on locally installed Windows tools.
- Do not claim full verifier/runtime completion unless the current validation profile, oracle/replay/diff evidence, unsafe ledger, and final gates prove it.

## Common Commands

Run focused doc mirror validation after roadmap edits:

```bash
python -B -m unittest validation.tools.test_doc_mirror_contract
```

Run the MCP scaffold contract tests after editing the thin verifier MCP:

```bash
python -B -m unittest validation.tools.test_c2rust_verifier_mcp
```

Run the translator coverage matrix after changing typed-IR or route evidence:

```bash
python -B validation/tools/translator_coverage_matrix.py --matrix validation/translator-coverage-matrix.json
```

## Thin MCP / Stdio Server

The repo-local scaffold is `validation/tools/c2rust_verifier_mcp.py`.
It registers:

- `translate_slice`: plans the existing migration command for a slice.
- `run_oracle`: plans the existing verifier/oracle command path.
- `read_evidence`: reads existing JSON evidence inside the repository.
- `coverage_matrix`: delegates to the existing translator coverage matrix report.

It also exposes a minimal MCP-style stdio JSON-RPC server:

```bash
python -B validation/tools/c2rust_verifier_mcp.py --stdio
```

The server supports `initialize`, `tools/list`, `tools/call`, and `notifications/initialized`. Tool calls still only plan existing commands or read evidence; they do not execute semantic verification or turn any candidate into accepted evidence.

Run the focused contract tests with:

```bash
python -B -m unittest validation.tools.test_c2rust_verifier_mcp
```
