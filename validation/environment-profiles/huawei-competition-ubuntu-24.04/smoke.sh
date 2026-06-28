#!/usr/bin/env bash
set -euo pipefail

find_repo_root() {
  local current
  current="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  while [ "${current}" != "/" ]; do
    if [ -f "${current}/config/competition-env/environment.json" ] && [ -d "${current}/validation/tools" ]; then
      printf '%s\n' "${current}"
      return 0
    fi
    current="$(dirname "${current}")"
  done
  return 1
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(find_repo_root)"

proof_class="${1:-local-simulation}"
out_root="${2:-target/competition-smoke}"

source "${script_dir}/env.sh"
cd "${repo_root}"
python validation/tools/run_competition_smoke.py \
  --proof-class "${proof_class}" \
  --out-root "${out_root}"
