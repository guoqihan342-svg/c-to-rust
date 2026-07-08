const TABLE: [i32; 4] = [0, 0, 7, 0];

pub fn sparse_designated_array_lookup(index: i32) -> i32 {
    TABLE[index as usize]
}
