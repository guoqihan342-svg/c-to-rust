英文镜像见 `full-regression-runner.en.md`。

# Full Regression Runner

中文说明：`scripts/run-full-regression.ps1` 是根目录级总控回归入口，用来把 FlashDB Rust、L2 slices、bounded translator、auto-translation evidence、Superpowers gates 和仓库 whitespace 检查串成可重复轮次。它不把合成负载冒充真实生产数据，也不声称 `cargo-llvm-cov` 分支覆盖率。

English summary: `scripts/run-full-regression.ps1` is the repository-level regression orchestrator for repeated validation rounds. It records machine-readable evidence under `target/full-regression/` and keeps correctness claims bounded to the executed gates.

## Recommended Local Gate

日常门禁运行一轮全量回归。默认不执行任何循环压力测试：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-full-regression.ps1 -Rounds 1
```

On Ubuntu, run the same script with the current PowerShell executable, usually `pwsh`, and bind the competition environment profile:

```bash
pwsh -File ./scripts/run-full-regression.ps1 \
  -Rounds 1 \
  -EnvironmentProfile config/competition-env/environment.json
```

This runs:

- L0 catalog validation.
- `crates/c2r-translator` fmt, tests, and clippy unless `-SkipClippy` is set.
- `validation/l2_slices` fmt and tests.
- Python auto-migration unit tests.
- auto-translation evidence schema plus semantic-pass validators for the accepted libuv and zlib slices.
- `flashDB_rust` fmt, check, tests, clippy unless `-SkipClippy` is set, smoke, replay/diff, unsafe scan, version manifest, and evidence validation. Loop stress is not included.
- evidence search for traceability.
- `git diff --check`.

## Repeated Full Rounds

需要检查 runner 自身的重复执行稳定性时，可以使用小批量轮次；这些轮次仍不包含循环压力测试：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-full-regression.ps1 -Rounds 3
```

每轮都会在以下目录写入日志和 JSONL 事件：

```text
target/full-regression/<run-id>/
```

If a run is interrupted, resume with the same run id and a later start round:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-full-regression.ps1 -RunId <run-id> -StartRound 2 -Rounds 3
```

By default the runner stops at the first failed step. Use `-ContinueOnFailure` only when collecting a failure matrix.

## Evidence Files

Each run emits:

- `events.jsonl`: one machine-readable event per step.
- `summary.json`: final status, failed step when present, coverage boundary, environment profile path/hash, and evidence root.
- `round-00001/*.log`: command output per step.
- round-local JSON reports for smoke, fixture replay/diff, version manifest, evidence search, and catalog validation.

All of these live under `target/`, which is ignored by git.

## Claim Boundaries

- Production data: default coverage uses committed fixtures, not real production data. Real or de-identified production fixtures must be replayed and diffed before claiming production-data equivalence.
- Abnormal data: covered by Rust tests, abnormal fixtures, and negative replay/diff cases.
- Performance: routine full regression does not run a performance stress step and does not claim a benchmark threshold.
- Reliability: routine full regression checks committed replay/diff behavior. It does not prove repeated file-backend, crash-power-loss, or hardware reliability.
- Routine runner policy: loop stress is disabled by default and is not part of normal acceptance. `flashDB_rust` retains a standalone stress command only for separately approved diagnostics.
- Branch coverage: cargo tests and Superpowers gates cover main behavior paths, but this runner does not claim line or branch coverage percentage.
- C/Rust equivalence: accepted L3 evidence is checked where committed. Full FlashDB C semantic equivalence still depends on the C oracle boundary and fixture scope.
