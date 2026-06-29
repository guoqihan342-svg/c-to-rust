/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

/* slice: flashdb/real-fdb-blob-make */
/* function: fdb_blob_make */
/* fixture input: validation/l2_slices/fixtures/real-fdb-blob-make.json */
/* fixture cases: 3 */
/* observable outputs: return_same_blob, blob.buf, blob.size */
/* fixture case: null-empty input_ref=cases[0] expected_ref=validation/l2_slices/fixtures/real-fdb-blob-make.json expected_outputs={"blob.buf": "value_buf", "blob.size": 0, "return_same_blob": true} */
/* fixture case: nominal-bytes input_ref=cases[1] expected_ref=validation/l2_slices/fixtures/real-fdb-blob-make.json expected_outputs={"blob.buf": "value_buf", "blob.size": 3, "return_same_blob": true} */
/* fixture case: shorter-length-than-buffer input_ref=cases[2] expected_ref=validation/l2_slices/fixtures/real-fdb-blob-make.json expected_outputs={"blob.buf": "value_buf", "blob.size": 2, "return_same_blob": true} */
/* source file: src/fdb_utils.c (sha256: 207e1af49b7ee5cb26d31e66a0d8334bb3566b85bc727844be3c52fdbcf577cc) */
struct fdb_blob {
  void *buf;
  size_t size;
};
typedef struct fdb_blob *fdb_blob_t;

static const uint8_t nominal_bytes_value_buf[] = { 16u, 32u, 48u };

static const uint8_t shorter_length_than_buffer_value_buf[] = { 170u, 187u, 204u, 221u };

fdb_blob_t fdb_blob_make(fdb_blob_t blob, const void *value_buf, size_t buf_len);

int main(void) {
  puts("oracle harness draft for fdb_blob_make");
  puts("fixture input: validation/l2_slices/fixtures/real-fdb-blob-make.json");
  struct fdb_blob null_empty_blob = { NULL, (size_t)99u };
  fdb_blob_t actual_null_empty = fdb_blob_make(&null_empty_blob, NULL, (size_t)0u);
  if (actual_null_empty != &null_empty_blob) {
    fprintf(stderr, "null-empty return_same_blob mismatch\n");
    return 1;
  }
  puts("fixture case null-empty return_same_blob matched");
  if (null_empty_blob.buf != (void *)NULL) {
    fprintf(stderr, "null-empty blob.buf mismatch\n");
    return 1;
  }
  puts("fixture case null-empty blob.buf matched");
  if (null_empty_blob.size != (size_t)0u) {
    fprintf(stderr, "null-empty blob.size mismatch\n");
    return 1;
  }
  puts("fixture case null-empty blob.size matched");
  struct fdb_blob nominal_bytes_blob = { NULL, (size_t)0u };
  fdb_blob_t actual_nominal_bytes = fdb_blob_make(&nominal_bytes_blob, nominal_bytes_value_buf, (size_t)3u);
  if (actual_nominal_bytes != &nominal_bytes_blob) {
    fprintf(stderr, "nominal-bytes return_same_blob mismatch\n");
    return 1;
  }
  puts("fixture case nominal-bytes return_same_blob matched");
  if (nominal_bytes_blob.buf != (void *)nominal_bytes_value_buf) {
    fprintf(stderr, "nominal-bytes blob.buf mismatch\n");
    return 1;
  }
  puts("fixture case nominal-bytes blob.buf matched");
  if (nominal_bytes_blob.size != (size_t)3u) {
    fprintf(stderr, "nominal-bytes blob.size mismatch\n");
    return 1;
  }
  puts("fixture case nominal-bytes blob.size matched");
  struct fdb_blob shorter_length_than_buffer_blob = { NULL, (size_t)7u };
  fdb_blob_t actual_shorter_length_than_buffer = fdb_blob_make(&shorter_length_than_buffer_blob, shorter_length_than_buffer_value_buf, (size_t)2u);
  if (actual_shorter_length_than_buffer != &shorter_length_than_buffer_blob) {
    fprintf(stderr, "shorter-length-than-buffer return_same_blob mismatch\n");
    return 1;
  }
  puts("fixture case shorter-length-than-buffer return_same_blob matched");
  if (shorter_length_than_buffer_blob.buf != (void *)shorter_length_than_buffer_value_buf) {
    fprintf(stderr, "shorter-length-than-buffer blob.buf mismatch\n");
    return 1;
  }
  puts("fixture case shorter-length-than-buffer blob.buf matched");
  if (shorter_length_than_buffer_blob.size != (size_t)2u) {
    fprintf(stderr, "shorter-length-than-buffer blob.size mismatch\n");
    return 1;
  }
  puts("fixture case shorter-length-than-buffer blob.size matched");
  return 0;
}
