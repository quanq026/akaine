#pragma once
#include <stddef.h>
#include <stdint.h>

namespace akaine_filter {
constexpr size_t QUERY_LIMIT = 128;
inline bool valid_query(const char* text, size_t size) {
    if (!text || size > QUERY_LIMIT || text[size]) return false;
    for (size_t at = 0; at < size;) {
        const unsigned first = static_cast<unsigned char>(text[at++]);
        unsigned code = first;
        size_t tails = 0;
        if (first >= 0xc2 && first <= 0xdf) { tails = 1; code &= 0x1f; }
        else if (first >= 0xe0 && first <= 0xef) { tails = 2; code &= 0x0f; }
        else if (first >= 0xf0 && first <= 0xf4) { tails = 3; code &= 7; }
        else if (first >= 0x80) return false;
        if (size - at < tails) return false;
        for (size_t i = 0; i < tails; ++i) {
            const unsigned next = static_cast<unsigned char>(text[at++]);
            if ((next & 0xc0) != 0x80) return false;
            code = (code << 6) | (next & 0x3f);
        }
        if ((tails == 1 && code < 0x80) || (tails == 2 && code < 0x800)
            || (tails == 3 && code < 0x10000) || code > 0x10ffff
            || (code >= 0xd800 && code <= 0xdfff) || code < 0x20
            || (code >= 0x7f && code <= 0x9f)) return false;
    }
    return true;
}
// Canonical, unpadded base64url. Empty query is available only through reset.
inline bool decode_query(const char* encoded, size_t size, char (&output)[QUERY_LIMIT + 1], size_t* length) {
    output[0] = 0;
    if (length) *length = 0;
    if (!encoded || !length || !size || size > (QUERY_LIMIT * 8 + 5) / 6 || size % 4 == 1) return false;
    unsigned bits = 0, buffer = 0;
    size_t count = 0;
    for (size_t i = 0; i < size; ++i) {
        const unsigned char c = static_cast<unsigned char>(encoded[i]);
        const unsigned value = c >= 'A' && c <= 'Z' ? c - 'A'
            : c >= 'a' && c <= 'z' ? c - 'a' + 26
            : c >= '0' && c <= '9' ? c - '0' + 52 : c == '-' ? 62 : c == '_' ? 63 : 64;
        if (value == 64) return false;
        buffer = (buffer << 6) | value; bits += 6;
        if (bits >= 8) {
            bits -= 8;
            if (count == QUERY_LIMIT) return false;
            output[count++] = static_cast<char>((buffer >> bits) & 255);
        }
        buffer &= (1u << bits) - 1;
    }
    output[count] = 0;
    if (buffer || !valid_query(output, count)) { output[0] = 0; return false; }
    *length = count;
    return true;
}
} // namespace akaine_filter
