/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include <limits.h>
#include <string.h>

/* slice: flashdb/real-fdb-calc-crc32 */
/* function: fdb_calc_crc32 */
/* fixture input: validation/l2_slices/fixtures/real-fdb-calc-crc32.json */
/* fixture cases: 2 */
/* observable outputs: return_code */
/* fixture case: empty-crc-zero input_ref=cases[0] expected_ref=validation/l2_slices/fixtures/real-fdb-calc-crc32.json expected_outputs={"return_code": 0} */
/* fixture case: ascii-123456789-crc-zero input_ref=cases[1] expected_ref=validation/l2_slices/fixtures/real-fdb-calc-crc32.json expected_outputs={"return_code": 3421780262} */
/* source file: src/fdb_utils.c (sha256: bb6d6bdf60d5176be307273f61bf1040b2bad668b018af612e026a58637d49c0) */
/* global dependency: crc32_table (same_file_top_level_declared) from src/fdb_utils.c */
/* COracleCallPlan-SHA256: 38096b4beab43f510e8a2cbdba15548b1fe72655ae9d261bf96783fb0cc859fe */
static const uint8_t case_empty_crc_zero_0_buf[] = { 0 };
static const uint8_t case_ascii_123456789_crc_zero_1_buf[] = { 49, 50, 51, 52, 53, 54, 55, 56, 57 };

uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size);

int main(void) {
  puts("oracle harness draft for fdb_calc_crc32");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-calc-crc32.json");
  uint32_t actual_empty_crc_zero_0 = fdb_calc_crc32(((uint32_t)0ULL), (const void *)case_empty_crc_zero_0_buf, ((size_t)0ULL));
  if (actual_empty_crc_zero_0 != ((uint32_t)0ULL)) {
    fprintf(stderr, "empty-crc-zero return_code mismatch\\n");
    return 1;
  }
  printf("C2R_C_ORACLE_JSON {\"case_id\":\"empty-crc-zero\",\"case_ordinal\":0,\"kind\":\"case_result\",\"outputs\":{\"return_code\":{\"encoding\":\"u32\",\"value\":\"%llu\"}},\"plan_sha256\":\"38096b4beab43f510e8a2cbdba15548b1fe72655ae9d261bf96783fb0cc859fe\",\"schema_version\":1}\n", (unsigned long long)actual_empty_crc_zero_0);
  uint32_t actual_ascii_123456789_crc_zero_1 = fdb_calc_crc32(((uint32_t)0ULL), (const void *)case_ascii_123456789_crc_zero_1_buf, ((size_t)9ULL));
  if (actual_ascii_123456789_crc_zero_1 != ((uint32_t)3421780262ULL)) {
    fprintf(stderr, "ascii-123456789-crc-zero return_code mismatch\\n");
    return 1;
  }
  printf("C2R_C_ORACLE_JSON {\"case_id\":\"ascii-123456789-crc-zero\",\"case_ordinal\":1,\"kind\":\"case_result\",\"outputs\":{\"return_code\":{\"encoding\":\"u32\",\"value\":\"%llu\"}},\"plan_sha256\":\"38096b4beab43f510e8a2cbdba15548b1fe72655ae9d261bf96783fb0cc859fe\",\"schema_version\":1}\n", (unsigned long long)actual_ascii_123456789_crc_zero_1);
  return 0;
}
