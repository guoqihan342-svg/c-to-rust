---
name: c2rust-migration
description: Repo-owned scaffold for planning C2Rust-backed migration slices and reading validation evidence without claiming full verifier completion.
---

# C2Rust Migration

Use this skill when working on C-to-Rust migration slices in this repository.

## Contract

- Treat C2Rust output as baseline/oracle context, not final semantic proof.
- Prefer existing repo scripts before adding new runtime code.
- Keep tool operations repository-confined: accept only POSIX relative paths, reject absolute paths, drive prefixes, backslashes, `~`, and `..`.
- Do not edit `validation/tools/auto_migrate.py` or `validation/tools/test_auto_migrate.py` for this scaffold slice.
- Do not claim full verifier/runtime completion from this skill or MCP scaffold.

## Thin MCP Scaffold

The repo-local scaffold is `validation/tools/c2rust_verifier_mcp.py`.
It registers:

- `translate_slice`: plans the existing migration command for a slice.
- `run_oracle`: plans the existing verifier/oracle command path.
- `read_evidence`: reads existing JSON evidence inside the repository.
- `coverage_matrix`: delegates to the existing translator coverage matrix report.

Run the focused contract tests with:

```bash
python -B -m unittest validation.tools.test_c2rust_verifier_mcp
```
