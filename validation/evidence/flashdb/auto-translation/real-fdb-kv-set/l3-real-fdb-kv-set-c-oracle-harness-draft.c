/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <flashdb.h>

/* slice: flashdb/real-fdb-kv-set */
/* function: fdb_kv_set */
/* fixture input: validation/l2_slices/fixtures/real-fdb-kv-set.json */
/* fixture cases: 2 */
/* observable outputs: return_code */
/* fixture case: uninit-set-value input_ref=cases[0] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-set.json expected_outputs={"return_code": 7} */
/* fixture case: uninit-delete-null input_ref=cases[1] expected_ref=validation/l2_slices/fixtures/real-fdb-kv-set.json expected_outputs={"return_code": 7} */
/* source file: src/fdb_kvdb.c (sha256: f917a62faaa28bca738d9cd0b115e791e2d2a333ad0530fca8ba558a3750a030) */
fdb_err_t fdb_kv_set(fdb_kvdb_t db, const char *key, const char *value);

int main(void) {
  puts("oracle harness draft for fdb_kv_set");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-kv-set.json");
  struct fdb_kvdb uninit_set_value_db = {0};
  uninit_set_value_db.parent.name = "unit-kv";
  static const char uninit_set_value_key[] = "boot_count";
  static const char uninit_set_value_value[] = "123";
  fdb_err_t actual_uninit_set_value_return_code = fdb_kv_set(&uninit_set_value_db, uninit_set_value_key, uninit_set_value_value);
  if (actual_uninit_set_value_return_code != (fdb_err_t)7u) {
    fprintf(stderr, "uninit-set-value return_code mismatch: expected 7 got %d\n", (int)actual_uninit_set_value_return_code);
    return 1;
  }
  puts("fixture case uninit-set-value return_code matched");
  struct fdb_kvdb uninit_delete_null_db = {0};
  uninit_delete_null_db.parent.name = "unit-kv";
  static const char uninit_delete_null_key[] = "boot_count";
  fdb_err_t actual_uninit_delete_null_return_code = fdb_kv_set(&uninit_delete_null_db, uninit_delete_null_key, NULL);
  if (actual_uninit_delete_null_return_code != (fdb_err_t)7u) {
    fprintf(stderr, "uninit-delete-null return_code mismatch: expected 7 got %d\n", (int)actual_uninit_delete_null_return_code);
    return 1;
  }
  puts("fixture case uninit-delete-null return_code matched");
  return 0;
}
