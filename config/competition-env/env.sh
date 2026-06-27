#!/usr/bin/env bash
set -euo pipefail

export COMPETITION_ENV_PROFILE_ID="huawei-competition-ubuntu-24.04"
export COMPETITION_ENV_PROFILE_PATH="config/competition-env/environment.json"
export MAVEN_HOME="/usr/local/maven3"
export PATH="${MAVEN_HOME}/bin:${PATH}"

export PIP_INDEX_URL="https://mirrors.tools.huawei.com/pypi/simple"
export PIP_TRUSTED_HOST="mirrors.tools.huawei.com"
export NPM_CONFIG_REGISTRY="https://mirrors.tools.huawei.com/npm/"

export CARGO_NET_GIT_FETCH_WITH_CLI="true"

echo "competition environment profile: ${COMPETITION_ENV_PROFILE_ID}"
echo "competition environment profile path: ${COMPETITION_ENV_PROFILE_PATH}"
