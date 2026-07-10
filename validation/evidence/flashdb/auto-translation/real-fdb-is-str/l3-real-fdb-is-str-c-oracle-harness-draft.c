/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <flashdb.h>

/* slice: flashdb/real-fdb-is-str */
/* function: fdb_is_str */
/* fixture input: validation/l2_slices/fixtures/real-fdb-is-str.json */
/* fixture cases: 8 */
/* observable outputs: return_value */
/* fixture case: empty input_ref=cases[0] expected_ref=validation/l2_slices/fixtures/real-fdb-is-str.json expected_outputs={"return_value": true} */
/* fixture case: all-printable input_ref=cases[1] expected_ref=validation/l2_slices/fixtures/real-fdb-is-str.json expected_outputs={"return_value": true} */
/* fixture case: printable-boundaries input_ref=cases[2] expected_ref=validation/l2_slices/fixtures/real-fdb-is-str.json expected_outputs={"return_value": true} */
/* fixture case: below-printable-range input_ref=cases[3] expected_ref=validation/l2_slices/fixtures/real-fdb-is-str.json expected_outputs={"return_value": false} */
/* fixture case: upper-exclusive-boundary input_ref=cases[4] expected_ref=validation/l2_slices/fixtures/real-fdb-is-str.json expected_outputs={"return_value": false} */
/* fixture case: u8-max input_ref=cases[5] expected_ref=validation/l2_slices/fixtures/real-fdb-is-str.json expected_outputs={"return_value": false} */
/* fixture case: internal-nul input_ref=cases[6] expected_ref=validation/l2_slices/fixtures/real-fdb-is-str.json expected_outputs={"return_value": false} */
/* fixture case: prefix-length input_ref=cases[7] expected_ref=validation/l2_slices/fixtures/real-fdb-is-str.json expected_outputs={"return_value": true} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
static uint8_t empty_value[] = { 0 };
static uint8_t all_printable_value[] = { 70u, 108u, 97u, 115u, 104u, 68u, 66u, 32u, 49u, 46u, 48u, 33u };
static uint8_t printable_boundaries_value[] = { 32u, 126u };
static uint8_t below_printable_range_value[] = { 31u };
static uint8_t upper_exclusive_boundary_value[] = { 127u };
static uint8_t u8_max_value[] = { 255u };
static uint8_t internal_nul_value[] = { 65u, 66u, 0u, 67u, 68u };
static uint8_t prefix_length_value[] = { 65u, 66u, 127u, 0u, 255u };

static bool fdb_is_str(uint8_t *value, size_t len)
{
#define __is_print(ch)       ((unsigned int)((ch) - ' ') < 127u - ' ')
    size_t i;

    for (i = 0; i < len; i++) {
        if (!__is_print(value[i])) {
            return false;
        }
    }
    return true;
}

int main(void) {
  puts("oracle harness draft for fdb_is_str");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-is-str.json");
  bool actual_empty_return_value = fdb_is_str(empty_value, (size_t)0);
  if (actual_empty_return_value != true) {
    fprintf(stderr, "empty return_value mismatch: expected true got %d\\n", (int)actual_empty_return_value);
    return 1;
  }
  puts("fixture case empty return_value matched");
  bool actual_all_printable_return_value = fdb_is_str(all_printable_value, (size_t)12);
  if (actual_all_printable_return_value != true) {
    fprintf(stderr, "all-printable return_value mismatch: expected true got %d\\n", (int)actual_all_printable_return_value);
    return 1;
  }
  puts("fixture case all-printable return_value matched");
  bool actual_printable_boundaries_return_value = fdb_is_str(printable_boundaries_value, (size_t)2);
  if (actual_printable_boundaries_return_value != true) {
    fprintf(stderr, "printable-boundaries return_value mismatch: expected true got %d\\n", (int)actual_printable_boundaries_return_value);
    return 1;
  }
  puts("fixture case printable-boundaries return_value matched");
  bool actual_below_printable_range_return_value = fdb_is_str(below_printable_range_value, (size_t)1);
  if (actual_below_printable_range_return_value != false) {
    fprintf(stderr, "below-printable-range return_value mismatch: expected false got %d\\n", (int)actual_below_printable_range_return_value);
    return 1;
  }
  puts("fixture case below-printable-range return_value matched");
  bool actual_upper_exclusive_boundary_return_value = fdb_is_str(upper_exclusive_boundary_value, (size_t)1);
  if (actual_upper_exclusive_boundary_return_value != false) {
    fprintf(stderr, "upper-exclusive-boundary return_value mismatch: expected false got %d\\n", (int)actual_upper_exclusive_boundary_return_value);
    return 1;
  }
  puts("fixture case upper-exclusive-boundary return_value matched");
  bool actual_u8_max_return_value = fdb_is_str(u8_max_value, (size_t)1);
  if (actual_u8_max_return_value != false) {
    fprintf(stderr, "u8-max return_value mismatch: expected false got %d\\n", (int)actual_u8_max_return_value);
    return 1;
  }
  puts("fixture case u8-max return_value matched");
  bool actual_internal_nul_return_value = fdb_is_str(internal_nul_value, (size_t)5);
  if (actual_internal_nul_return_value != false) {
    fprintf(stderr, "internal-nul return_value mismatch: expected false got %d\\n", (int)actual_internal_nul_return_value);
    return 1;
  }
  puts("fixture case internal-nul return_value matched");
  bool actual_prefix_length_return_value = fdb_is_str(prefix_length_value, (size_t)2);
  if (actual_prefix_length_return_value != true) {
    fprintf(stderr, "prefix-length return_value mismatch: expected true got %d\\n", (int)actual_prefix_length_return_value);
    return 1;
  }
  puts("fixture case prefix-length return_value matched");
  return 0;
}
