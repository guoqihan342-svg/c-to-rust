#!/usr/bin/env bash
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

find_repo_root() {
  current="${script_dir}"
  while [ -n "${current}" ] && [ "${current}" != "/" ]; do
    if [ -r "${current}/config/competition-env/environment.json" ]; then
      printf '%s\n' "${current}"
      return 0
    fi
    next="$(dirname -- "${current}")"
    if [ "${next}" = "${current}" ]; then
      break
    fi
    current="${next}"
  done
  printf 'cannot locate repository root from %s\n' "${script_dir}" >&2
  return 1
}

repo_root="$(find_repo_root)"

export COMPETITION_ENV_PROFILE_ID="huawei-competition-ubuntu-24.04"
export COMPETITION_ENV_PROFILE_PATH="validation/environment-profiles/huawei-competition-ubuntu-24.04/environment.json"
export MAVEN_HOME="/usr/local/maven3"
export PATH="${MAVEN_HOME}/bin:${PATH}"

export PIP_INDEX_URL="https://mirrors.tools.huawei.com/pypi/simple"
export PIP_TRUSTED_HOST="mirrors.tools.huawei.com"
export NPM_CONFIG_REGISTRY="https://mirrors.tools.huawei.com/npm/"

export CARGO_HOME="${script_dir}/cargo"
export CARGO_NET_GIT_FETCH_WITH_CLI="true"

detect_vendored_clang() {
  if [ -n "${CLANG_PATH:-}" ] && command -v "${CLANG_PATH}" >/dev/null 2>&1; then
    printf 'clang: using CLANG_PATH=%s\n' "${CLANG_PATH}"
    return 0
  fi
  for candidate in \
    "${repo_root}/tools/llvm/bin/clang-18" \
    "${repo_root}/tools/llvm/bin/clang" \
    "${repo_root}/tools/clang/bin/clang"; do
    if [ -x "${candidate}" ]; then
      printf 'clang: detected vendored clang at %s (set CLANG_PATH to override)\n' "${candidate}"
      export CLANG_PATH="${candidate}"
      return 0
    fi
  done
  printf 'clang: not found (vendored paths and CLANG_PATH are both empty). The competition clang lane will use missing_clang_path status.\n'
}

detect_vendored_clang

echo "competition environment profile: ${COMPETITION_ENV_PROFILE_ID}"
echo "competition environment profile path: ${COMPETITION_ENV_PROFILE_PATH}"
echo "competition cargo home: ${CARGO_HOME}"
