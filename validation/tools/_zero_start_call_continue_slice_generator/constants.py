from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SLICE_ID = "real-fdb-kv-iterate-zero-start-next-sector-advance-continue"
TARGET_ID = "flashdb"
FUNCTION_NAME = "fdb_kv_iterate_zero_start_next_sector_advance_continue_probe"
DEFAULT_INPUT = (
    REPO_ROOT / "validation/l2_slices/generator_inputs" / f"{SLICE_ID}.json"
)
DEFAULT_SPEC = REPO_ROOT / "validation/slice-specs" / f"flashdb-{SLICE_ID}.json"
DEFAULT_FIXTURE = REPO_ROOT / "validation/l2_slices/fixtures" / f"{SLICE_ID}.json"
U32_MAX = (1 << 32) - 1
