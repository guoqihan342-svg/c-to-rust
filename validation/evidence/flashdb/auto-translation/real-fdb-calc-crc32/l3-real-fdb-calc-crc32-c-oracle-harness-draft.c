/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-calc-crc32 */
/* function: fdb_calc_crc32 */
/* fixture input: validation/l2_slices/fixtures/real-fdb-calc-crc32.json */
/* fixture cases: 2 */
/* observable outputs: return_code */
/* fixture case: empty-crc-zero input_ref=cases[0] expected_ref=validation/l2_slices/fixtures/real-fdb-calc-crc32.json expected_outputs={"return_code": 0} */
/* fixture case: ascii-123456789-crc-zero input_ref=cases[1] expected_ref=validation/l2_slices/fixtures/real-fdb-calc-crc32.json expected_outputs={"return_code": 3421780262} */
/* source file: src/fdb_utils.c (sha256: bb6d6bdf60d5176be307273f61bf1040b2bad668b018af612e026a58637d49c0) */
/* global dependency: crc32_table (same_file_top_level_declared) from src/fdb_utils.c */
static const uint8_t empty_crc_zero_buf[] = { 0 };

static const uint8_t ascii_123456789_crc_zero_buf[] = { 49u, 50u, 51u, 52u, 53u, 54u, 55u, 56u, 57u };

uint32_t fdb_calc_crc32(uint32_t crc, const void *buf, size_t size);

int main(void) {
  puts("oracle harness draft for fdb_calc_crc32");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-calc-crc32.json");
  uint32_t actual_empty_crc_zero_return_code = fdb_calc_crc32((uint32_t)0u, empty_crc_zero_buf, (size_t)0u);
  if (actual_empty_crc_zero_return_code != (uint32_t)0u) {
    fprintf(stderr, "empty-crc-zero return_code mismatch: expected 0 got %llu\n", (unsigned long long)actual_empty_crc_zero_return_code);
    return 1;
  }
  puts("fixture case empty-crc-zero return_code matched");
  uint32_t actual_ascii_123456789_crc_zero_return_code = fdb_calc_crc32((uint32_t)0u, ascii_123456789_crc_zero_buf, (size_t)9u);
  if (actual_ascii_123456789_crc_zero_return_code != (uint32_t)3421780262u) {
    fprintf(stderr, "ascii-123456789-crc-zero return_code mismatch: expected 3421780262 got %llu\n", (unsigned long long)actual_ascii_123456789_crc_zero_return_code);
    return 1;
  }
  puts("fixture case ascii-123456789-crc-zero return_code matched");
  return 0;
}
