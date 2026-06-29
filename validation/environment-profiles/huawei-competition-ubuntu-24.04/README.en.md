# Historical Competition Environment Profile Redirect

This directory is a README-only historical redirect. The executable competition environment config, mirror config, and self-check scripts are now archived under the single canonical directory `config/competition-env/`. This directory no longer stores copies of `environment.json`, `env.sh`, `toolchain-check.sh`, `smoke.sh`, or package-manager config files.

Current default entrypoint:

```bash
source config/competition-env/env.sh
bash config/competition-env/toolchain-check.sh
```

Rules:

- New scripts and new evidence must use `config/competition-env/environment.json` and record that file's profile id, path, and SHA256.
- Older evidence may mention `validation/environment-profiles/huawei-competition-ubuntu-24.04/` only as a historical path reference, not as a new executable configuration source.
- When competition environment constraints change, update only the canonical files under `config/competition-env/` so two config directories cannot drift.
