#pragma once
#include "bounds.h"

namespace anomaly_monitor {
struct SongStringView {
    Address address;
    Size size;
    bool short_string;
};

inline Address read_address(const unsigned char* bytes) {
    Address value = 0;
    for (Size i = 0; i < sizeof(Address); ++i) value |= Address(bytes[i]) << (i * 8);
    return value;
}

inline bool song_string_view(const unsigned char* object, SongStringView* result) {
    if (!(object[0] & 1)) {
        Size size = object[0] >> 1;
        if (!size || size > 22 || object[size + 1] != 0) return false;
        *result = {0, size, true};
        return true;
    }
    Address capacity = read_address(object) & ~Address(1);
    Size size = read_address(object + 8);
    Address data = read_address(object + 16);
    if (!size || size > 64 || capacity <= size || capacity > 4096 || !data
        || size + 1 > ~Address(0) - data) return false;
    *result = {data, size, false};
    return true;
}

inline bool copy_song_id(const char* data, Size size, char* output, Size capacity) {
    if (!size || size > 64 || capacity <= size || data[size] != 0) return false;
    for (Size i = 0; i < size; ++i) {
        char value = data[i];
        bool valid = (value >= 'a' && value <= 'z') || (value >= 'A' && value <= 'Z')
            || (value >= '0' && value <= '9') || value == '_' || value == '-';
        if (!valid) return false;
        output[i] = value;
    }
    output[size] = 0;
    return true;
}
}
