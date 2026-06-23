#!/usr/bin/env sh
set -eu

FLASHDB_URL=${FLASHDB_URL:-https://gitcode.com/xwxf/FlashDB.git}
FLASHDB_COMMIT=${FLASHDB_COMMIT:-93d175549da579b8abac07bd175ce4c3f9dde829}
CC=${CC:-gcc}
MAKE=${MAKE:-make}

ORACLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORK_DIR=${WORK_DIR:-"$ORACLE_DIR/.work"}
SRC_DIR=${SRC_DIR:-"$WORK_DIR/FlashDB"}
BUILD_DIR=${BUILD_DIR:-"$WORK_DIR/build"}
RUN_DIR=${RUN_DIR:-"$WORK_DIR/run"}
OUT_FILE=${OUT_FILE:-"$ORACLE_DIR/flashdb_c_oracle.json"}
FIXTURE_FILE=${FIXTURE_FILE:-}
EVIDENCE_FILE=${EVIDENCE_FILE:-}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --fixture)
            FIXTURE_FILE=$2
            shift 2
            ;;
        --report)
            OUT_FILE=$2
            shift 2
            ;;
        --evidence)
            EVIDENCE_FILE=$2
            shift 2
            ;;
        *)
            printf 'unknown option: %s\n' "$1" >&2
            exit 2
            ;;
    esac
done

json_escape() {
    value=$1
    value=$(printf '%s' "$value" | sed 's/\\/\\\\/g; s/"/\\"/g')
    printf '%s' "$value"
}

write_evidence() {
    marker=$1
    status=$2
    detail=$3
    if [ -z "$EVIDENCE_FILE" ]; then
        return 0
    fi
    mkdir -p "$(dirname "$EVIDENCE_FILE")"
    cat >"$EVIDENCE_FILE" <<EOF
{
  "marker": "$(json_escape "$marker")",
  "status": "$(json_escape "$status")",
  "detail": "$(json_escape "$detail")",
  "timestamp_utc": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
}

need_tool() {
    command -v "$1" >/dev/null 2>&1 || {
        printf 'missing required tool: %s\n' "$1" >&2
        printf 'Set CC or MAKE if your compiler/build tool has a non-default name.\n' >&2
        exit 127
    }
}

need_tool git
need_tool "$CC"
need_tool "$MAKE"

if [ -n "$FIXTURE_FILE" ] && [ ! -f "$FIXTURE_FILE" ]; then
    write_evidence "FAILED_C_ORACLE_FIXTURE_MISSING" "failed" "fixture file not found: $FIXTURE_FILE"
    printf 'fixture file not found: %s\n' "$FIXTURE_FILE" >&2
    exit 1
fi

if [ -z "$FIXTURE_FILE" ]; then
    write_evidence "FAILED_C_ORACLE_FIXTURE_MISSING" "failed" "missing required --fixture <file>"
    printf 'missing required --fixture <file>\n' >&2
    exit 2
fi

mkdir -p "$WORK_DIR"

if [ ! -d "$SRC_DIR/.git" ]; then
    git clone "$FLASHDB_URL" "$SRC_DIR"
fi

git -C "$SRC_DIR" fetch --tags origin
git -C "$SRC_DIR" checkout --detach "$FLASHDB_COMMIT"
actual_commit=$(git -C "$SRC_DIR" rev-parse HEAD)
if [ "$actual_commit" != "$FLASHDB_COMMIT" ]; then
    printf 'expected FlashDB commit %s, got %s\n' "$FLASHDB_COMMIT" "$actual_commit" >&2
    exit 1
fi

rm -rf "$BUILD_DIR" "$RUN_DIR"
mkdir -p "$BUILD_DIR" "$RUN_DIR"

"$MAKE" -f "$ORACLE_DIR/Makefile.c_oracle" \
    FLASHDB_DIR="$SRC_DIR" \
    ORACLE_DIR="$ORACLE_DIR" \
    BUILD_DIR="$BUILD_DIR" \
    CC="$CC" \
    all

"$BUILD_DIR/flashdb_c_oracle" --fixture "$FIXTURE_FILE" --work-dir "$RUN_DIR" > "$OUT_FILE"
write_evidence "C_ORACLE_GENERATED" "passed" "report=$OUT_FILE fixture=${FIXTURE_FILE:-none}"
printf 'wrote %s\n' "$OUT_FILE"
