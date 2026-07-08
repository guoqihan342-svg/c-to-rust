const TABLE: [i32; 4] = [0i32, 0i32, 7i32, 0i32];

pub fn sparse_designated_array_lookup(index: i32) -> i32 {
    return TABLE[index as usize];
}
