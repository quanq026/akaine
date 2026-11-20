#pragma once

namespace anomaly_monitor {
using Address = __UINTPTR_TYPE__;
using Size = __SIZE_TYPE__;

struct Range {
    Address begin;
    Address end;
};

inline bool contains(Range range, Address address, Size bytes) {
    return range.begin <= range.end && address >= range.begin && address <= range.end
        && bytes <= range.end - address;
}

inline unsigned read_u32(const unsigned char* bytes) {
    return unsigned(bytes[0]) | unsigned(bytes[1]) << 8 | unsigned(bytes[2]) << 16 | unsigned(bytes[3]) << 24;
}

inline bool same_bytes(const unsigned char* left, const unsigned char* right, Size size) {
    for (Size i = 0; i < size; ++i) if (left[i] != right[i]) return false;
    return true;
}

inline bool note_has_build_id(const unsigned char* bytes, Size size, const unsigned char* expected, Size expected_size) {
    Size cursor = 0;
    while (cursor < size) {
        if (size - cursor < 12) return false;
        unsigned name_size = read_u32(bytes + cursor);
        unsigned data_size = read_u32(bytes + cursor + 4);
        unsigned type = read_u32(bytes + cursor + 8);
        cursor += 12;
        Size padded_name = (Size(name_size) + 3) & ~Size(3);
        Size padded_data = (Size(data_size) + 3) & ~Size(3);
        if (padded_name < name_size || padded_data < data_size || padded_name > size - cursor) return false;
        if (padded_data > size - cursor - padded_name) return false;
        if (type == 3 && name_size == 4 && bytes[cursor] == 'G' && bytes[cursor + 1] == 'N'
            && bytes[cursor + 2] == 'U' && bytes[cursor + 3] == 0 && data_size == expected_size) {
            return same_bytes(bytes + cursor + padded_name, expected, expected_size);
        }
        cursor += padded_name + padded_data;
    }
    return false;
}

inline bool rtti_name(const char* bytes, Size available, char* output, Size capacity) {
    if (!capacity) return false;
    for (Size i = 0; i < available && i < capacity; ++i) {
        char value = bytes[i];
        if (!value) {
            if (i == 0) return false;
            output[i] = 0;
            return true;
        }
        bool valid = (value >= 'A' && value <= 'Z') || (value >= 'a' && value <= 'z')
            || (value >= '0' && value <= '9') || value == '_' || value == '$';
        if (!valid || i + 1 == capacity) return false;
        output[i] = value;
    }
    return false;
}
}
