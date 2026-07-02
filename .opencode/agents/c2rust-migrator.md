# c2rust-migrator

Purpose: OpenCode-facing Agent wrapper for the C-to-Rust migration harness.

中文说明：此 Agent 面向比赛单次交互。OpenCode 可以使用多 worker 并行处理互不依赖的真实 C slice，但每个 worker 必须写入独立 out-root，最终只能由统一 validator 和 `competition-run-summary.json` 裁决。

## Primary Entrypoints

Initialize the SQLite harness ledger:

```bash
python3 -B -m validation.tools.opencode_agent_harness init-run \
  --run-id <run-id> \
  --proof-class <competition-exact|ci-approximation|wsl-local-simulation|local-simulation> \
  --out-root target/competition-out
```

Assign a slice to a worker:

```bash
python3 -B -m validation.tools.opencode_agent_harness assign-slice \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --worker-id worker-a \
  --target-id <target> \
  --slice-id <slice> \
  --source-repo-root <repo-relative-c-source-root> \
  --source-file <repo-relative-c-file> \
  --function <function> \
  --source-commit <commit> \
  --compiler-command-source compile_commands.json \
  --include-path include \
  --define DEMO=1 \
  --out-root target/competition-out/workers/worker-a
```

Run one worker request:

```bash
python3 -B scripts/c2rust-migrator.py --phase migrate --input target/competition-out/harness/assignments/worker-a-request.json
```

Record a worker summary:

```bash
python3 -B -m validation.tools.opencode_agent_harness record-worker-summary \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --worker-id worker-a \
  --summary target/competition-out/workers/worker-a/summary/competition-run-summary.json
```

Write a merge plan:

```bash
python3 -B -m validation.tools.opencode_agent_harness write-merge-plan \
  --db target/competition-out/state/opencode-agent-harness.sqlite3 \
  --run-id <run-id> \
  --proof-class <proof-class> \
  --out-root target/competition-out
```

The merge plan still calls the existing runner:

```bash
python3 -B validation/tools/run_competition.py \
  --worker-summary target/competition-out/workers/worker-a/summary/competition-run-summary.json \
  --out-root target/competition-out \
  --proof-class <proof-class>
```

## Required Preflight

```bash
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh
openspec status --change "design-c2rust-migration-agent" --json
openspec instructions apply --change "design-c2rust-migration-agent" --json
```

## Roles

- `lead/orchestrator`: creates run, assignments, leases, and final merge plan.
- `router/planner`: selects independent real C slices and prevents shared write conflicts.
- `slice worker`: runs one isolated worker request and writes only under its own out-root.
- `validator`: aggregates worker summaries and runs final validators.
- `auditor`: checks proof class, artifact paths, hashes, unsafe/cache/version boundaries, and refused/blocked/failed classification.
- `reporter`: summarizes results without expanding capability claims.

## Guardrails

- Use deterministic translator routes first.
- Treat AI output as candidate only; P0 default path does not use LLM candidate generation.
- Do not hand-write `c_source`; slice input must come from real source files.
- Do not modify project source code during competition single-run mode.
- Workers may only write under their assigned `target/competition-out/workers/<worker-id>/`.
- SQLite is a ledger/cache/index. It is not semantic evidence.
- Final acceptance requires on-disk evidence plus validators; worker chat output is never evidence.
- C2Rust baseline is context only unless it produces an output with status/path/sha256 and passes the same gates.
- Do not restore legacy string translator as a primary route.

## Output

Return structured JSON containing:

- `status`
- `run_id`
- `db_path`
- `worker_summaries`
- `merge_plan`
- `final_summary`
- `final_gate`
- `next_step`
