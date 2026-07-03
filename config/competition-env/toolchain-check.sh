#!/usr/bin/env bash
set -u

failures=0
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

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

record_failure() {
  printf 'FAIL: %s\n' "$1" >&2
  failures=$((failures + 1))
}

expect_command() {
  command -v "$1" >/dev/null 2>&1 || record_failure "$1 is not installed"
}

expect_absent() {
  if command -v "$1" >/dev/null 2>&1; then
    record_failure "$1 should be absent in the competition baseline"
  else
    printf 'OK: %s absent\n' "$1"
  fi
}

expect_output_contains() {
  name="$1"
  command_text="$2"
  expected="$3"
  output="$(sh -c "$command_text" 2>&1)"
  case "$output" in
    *"$expected"*) printf 'OK: %s contains %s\n' "$name" "$expected" ;;
    *) record_failure "$name expected '$expected', got '$output'" ;;
  esac
}

expect_output_contains_case_insensitive() {
  name="$1"
  command_text="$2"
  expected="$3"
  output="$(sh -c "$command_text" 2>&1)"
  lower_output="$(printf '%s' "$output" | tr '[:upper:]' '[:lower:]')"
  lower_expected="$(printf '%s' "$expected" | tr '[:upper:]' '[:lower:]')"
  case "$lower_output" in
    *"$lower_expected"*) printf 'OK: %s contains %s\n' "$name" "$expected" ;;
    *) record_failure "$name expected '$expected', got '$output'" ;;
  esac
}

expect_file_contains() {
  name="$1"
  path="$2"
  expected="$3"
  if [ ! -r "$path" ]; then
    record_failure "$name file is not readable: $path"
    return
  fi
  if grep -Fq "$expected" "$path"; then
    printf 'OK: %s contains %s\n' "$name" "$expected"
  else
    record_failure "$name expected '$expected' in $path"
  fi
}

check_optional_clang_smoke() {
  clang_bin="$1"
  resource_dir="$("${clang_bin}" -print-resource-dir 2>&1)"
  clang_status_code="$?"
  if [ "$clang_status_code" -ne 0 ] || [ -z "$resource_dir" ]; then
    record_failure "clang resource-dir smoke failed for ${clang_bin}: ${resource_dir}"
    return
  fi
  printf 'OK: clang resource-dir %s\n' "$resource_dir"

  smoke_source="$(mktemp "${TMPDIR:-/tmp}/c2r-clang-smoke.XXXXXX.c")"
  cat >"$smoke_source" <<'EOF'
#include <stdint.h>
#include <stddef.h>
int c2r_clang_smoke(uint32_t value) {
  return (int)(value + sizeof(size_t));
}
EOF
  smoke_output="$("${clang_bin}" -fsyntax-only -Xclang -ast-dump=json "$smoke_source" 2>&1)"
  smoke_status_code="$?"
  rm -f "$smoke_source"
  if [ "$smoke_status_code" -ne 0 ]; then
    record_failure "clang minimum TU AST dump smoke failed for ${clang_bin}: ${smoke_output}"
  else
    printf 'OK: clang minimum TU AST dump smoke passed\n'
  fi
}

check_opencode_model_availability() {
  required_model="GLM-5.1"
  require_glm="${REQUIRE_OPENCODE_GLM:-0}"
  if ! command -v opencode >/dev/null 2>&1; then
    if [ "$require_glm" = "1" ]; then
      record_failure "opencode is not installed; required for OpenCode GLM-5.1 competition agent evidence"
    else
      printf 'opencode status: unavailable (required only for OpenCode GLM-5.1 competition agent evidence)\n'
    fi
    return
  fi

  models_output="$(opencode models 2>&1)"
  models_status_code="$?"
  if [ "$models_status_code" -ne 0 ]; then
    if [ "$require_glm" = "1" ]; then
      record_failure "opencode models failed; required for GLM-5.1 competition agent evidence: ${models_output}"
    else
      printf 'opencode status: model probe failed (required only for OpenCode GLM-5.1 competition agent evidence)\n'
    fi
    return
  fi

  if printf '%s\n' "$models_output" | grep -Eq '(^|[^A-Za-z0-9_.-])([^[:space:]/]+/)*GLM-5\.1([^A-Za-z0-9_.-]|$)'; then
    printf 'OK: opencode models lists %s\n' "$required_model"
  elif [ "$require_glm" = "1" ]; then
    record_failure "opencode models did not list ${required_model}; root_cause_key=opencode_model_unavailable reason=required_model_not_listed"
  else
    printf 'opencode status: %s not listed (required only for OpenCode competition agent evidence)\n' "$required_model"
  fi
}

if [ -r /etc/os-release ]; then
  . /etc/os-release
  [ "${ID:-}" = "ubuntu" ] || record_failure "OS ID expected ubuntu, got ${ID:-unknown}"
  [ "${VERSION_ID:-}" = "24.04" ] || record_failure "VERSION_ID expected 24.04, got ${VERSION_ID:-unknown}"
  [ "${VERSION_CODENAME:-}" = "noble" ] || record_failure "VERSION_CODENAME expected noble, got ${VERSION_CODENAME:-unknown}"
  [ "${VERSION:-}" = "24.04.4 LTS (Noble Numbat)" ] || record_failure "VERSION expected 24.04.4 LTS (Noble Numbat), got ${VERSION:-unknown}"
else
  record_failure "/etc/os-release is not readable"
fi

kernel="$(uname -r 2>/dev/null || true)"
[ "$kernel" = "5.10.0-182.0.0.95.r194_123.hce2.x86_64" ] || record_failure "kernel expected 5.10.0-182.0.0.95.r194_123.hce2.x86_64, got ${kernel:-unknown}"

expect_command python3
expect_command pip
expect_command node
expect_command npm
expect_command java
expect_command mvn
expect_command rustc
expect_command cargo
expect_command gcc
expect_command g++
expect_command make

expect_output_contains "python3" "python3 --version" "Python 3.12.3"
expect_output_contains "pip" "pip --version" "pip 24.0"
expect_output_contains "node" "node --version" "v24.13.0"
expect_output_contains "npm" "npm --version" "11.6.2"
expect_output_contains "java" "java -version" "21.0.10"
expect_output_contains_case_insensitive "java distribution" "java -version" "openjdk"
expect_output_contains_case_insensitive "java vendor" "java -version" "bisheng"
expect_output_contains "maven" "mvn --version" "Apache Maven 3.9.11"
expect_output_contains "rustc" "rustc --version" "rustc 1.96.0"
expect_output_contains "cargo" "cargo --version" "cargo 1.96.0"
expect_output_contains "gcc" "gcc --version | head -n 1" "13.3.0"
expect_output_contains "g++" "g++ --version | head -n 1" "13.3.0"
expect_output_contains "make" "make --version | head -n 1" "GNU Make 4.3"

[ "${MAVEN_HOME:-}" = "/usr/local/maven3" ] || record_failure "MAVEN_HOME expected /usr/local/maven3, got ${MAVEN_HOME:-unset}"

expect_file_contains "APT mirror profile" "${script_dir}/apt/sources.list" "http://mirrors.tools.huawei.com/ubuntu"
expect_file_contains "pip mirror profile" "${script_dir}/pip/pip.conf" "https://mirrors.tools.huawei.com/pypi/simple"
expect_file_contains "npm registry profile" "${script_dir}/npm/.npmrc" "https://mirrors.tools.huawei.com/npm/"
expect_file_contains "Cargo registry profile" "${script_dir}/cargo/config.toml" "sparse+http://rust.inhuawei.com/crates.io-index/"

expect_absent go
expect_absent cmake
check_opencode_model_availability

# clang is optional; note vendored or env-var status without failing
clang_status="absent"
clang_bin=""
if [ -n "${CLANG_PATH:-}" ] && command -v "${CLANG_PATH}" >/dev/null 2>&1; then
  clang_status="CLANG_PATH=${CLANG_PATH}"
  clang_bin="$(command -v "${CLANG_PATH}")"
else
  for vendored in \
    "${repo_root}/tools/llvm/bin/clang-18" \
    "${repo_root}/tools/llvm/bin/clang" \
    "${repo_root}/tools/clang/bin/clang"; do
    if [ -x "${vendored}" ]; then
      clang_status="vendored=${vendored}"
      clang_bin="${vendored}"
      break
    fi
  done
fi
printf 'clang status: %s (optional; only required for --competition-clang-lane)\n' "${clang_status}"
if [ -n "$clang_bin" ]; then
  check_optional_clang_smoke "$clang_bin"
fi

if [ "$failures" -eq 0 ]; then
  echo "competition environment check passed"
else
  echo "competition environment check failed: ${failures} issue(s)" >&2
  exit 1
fi
