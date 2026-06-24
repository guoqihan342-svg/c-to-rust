const PRIME32_1: u32 = 2_654_435_761;
const PRIME32_2: u32 = 2_246_822_519;
const PRIME32_3: u32 = 3_266_489_917;
const PRIME32_4: u32 = 668_265_263;
const PRIME32_5: u32 = 374_761_393;

pub fn xxh32(input: &[u8], seed: u32) -> u32 {
    let mut index = 0;
    let mut hash;

    if input.len() >= 16 {
        let mut v1 = seed.wrapping_add(PRIME32_1).wrapping_add(PRIME32_2);
        let mut v2 = seed.wrapping_add(PRIME32_2);
        let mut v3 = seed;
        let mut v4 = seed.wrapping_sub(PRIME32_1);

        while index <= input.len() - 16 {
            v1 = round(v1, read_u32(input, index));
            index += 4;
            v2 = round(v2, read_u32(input, index));
            index += 4;
            v3 = round(v3, read_u32(input, index));
            index += 4;
            v4 = round(v4, read_u32(input, index));
            index += 4;
        }

        hash = v1
            .rotate_left(1)
            .wrapping_add(v2.rotate_left(7))
            .wrapping_add(v3.rotate_left(12))
            .wrapping_add(v4.rotate_left(18));
    } else {
        hash = seed.wrapping_add(PRIME32_5);
    }

    hash = hash.wrapping_add(input.len() as u32);

    while index + 4 <= input.len() {
        hash = hash
            .wrapping_add(read_u32(input, index).wrapping_mul(PRIME32_3))
            .rotate_left(17)
            .wrapping_mul(PRIME32_4);
        index += 4;
    }

    while index < input.len() {
        hash = hash
            .wrapping_add(u32::from(input[index]).wrapping_mul(PRIME32_5))
            .rotate_left(11)
            .wrapping_mul(PRIME32_1);
        index += 1;
    }

    avalanche(hash)
}

fn round(accumulator: u32, input: u32) -> u32 {
    accumulator
        .wrapping_add(input.wrapping_mul(PRIME32_2))
        .rotate_left(13)
        .wrapping_mul(PRIME32_1)
}

fn avalanche(mut hash: u32) -> u32 {
    hash ^= hash >> 15;
    hash = hash.wrapping_mul(PRIME32_2);
    hash ^= hash >> 13;
    hash = hash.wrapping_mul(PRIME32_3);
    hash ^= hash >> 16;
    hash
}

fn read_u32(input: &[u8], index: usize) -> u32 {
    u32::from_le_bytes([
        input[index],
        input[index + 1],
        input[index + 2],
        input[index + 3],
    ])
}
