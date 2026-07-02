#!/usr/bin/env bash
set -euo pipefail

FLASHDB_REPOSITORY="https://gitcode.com/xwxf/FlashDB.git"
FLASHDB_BRANCH="competition"
FLASHDB_COMMIT="f9d0421315c564fb890a1b14eee77b290e0d7bbe"

find_repo_root() {
  local current
  current="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  while [ "${current}" != "/" ]; do
    if [ -f "${current}/config/competition-env/environment.json" ] && [ -d "${current}/validation/tools" ]; then
      printf '%s\n' "${current}"
      return 0
    fi
    current="$(dirname "${current}")"
  done
  return 1
}

repo_root="$(find_repo_root)"
target_dir="${1:-sources/FlashDB}"
target_path="${repo_root}/${target_dir}"

mkdir -p "$(dirname "${target_path}")"

if [ -e "${target_path}" ] && [ ! -d "${target_path}/.git" ]; then
  printf 'bootstrap target exists but is not a git checkout: %s\n' "${target_dir}" >&2
  exit 2
fi

if [ ! -d "${target_path}/.git" ]; then
  git clone "${FLASHDB_REPOSITORY}" "${target_path}"
fi

cd "${target_path}"
if git ls-remote --exit-code --heads origin "${FLASHDB_BRANCH}" >/dev/null 2>&1; then
  git fetch --tags origin "${FLASHDB_BRANCH}"
else
  git fetch --tags origin
fi
git checkout -B "${FLASHDB_BRANCH}" "${FLASHDB_COMMIT}"

actual_commit="$(git rev-parse HEAD)"
if [ "${actual_commit}" != "${FLASHDB_COMMIT}" ]; then
  printf 'FlashDB checkout drift: expected %s, got %s\n' "${FLASHDB_COMMIT}" "${actual_commit}" >&2
  exit 3
fi

printf 'FlashDB ready at %s (%s)\n' "${target_dir}" "${actual_commit}"
