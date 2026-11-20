#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

namespace monitor_maps {
struct Mapping {
    uintptr_t begin = 0, end = 0;
    bool readable = false, writable = false;
    bool contains(uintptr_t address, size_t bytes, bool write) const {
        return readable && (!write || writable) && address && begin <= end
            && address >= begin && address <= end && bytes <= end - address;
    }
};
inline bool hex(const char* text, size_t size, size_t& at, uintptr_t& value) {
    const size_t start = at;
    value = 0;
    while (at < size) {
        const unsigned char ch = static_cast<unsigned char>(text[at]);
        unsigned digit;
        if (ch >= '0' && ch <= '9') digit = ch - '0';
        else if (ch >= 'a' && ch <= 'f') digit = ch - 'a' + 10;
        else if (ch >= 'A' && ch <= 'F') digit = ch - 'A' + 10;
        else break;
        if (value > (~uintptr_t(0) - digit) / 16) return false;
        value = value * 16 + digit;
        ++at;
    }
    return at != start;
}
inline bool space(char ch) { return ch == ' ' || ch == '\t' || ch == '\r' || ch == '\n'; }
inline bool parse(const char* text, size_t size, Mapping& result) {
    size_t at = 0;
    Mapping value;
    if (!text || !hex(text, size, at, value.begin) || at >= size || text[at++] != '-'
        || !hex(text, size, at, value.end) || value.end <= value.begin || at >= size || !space(text[at])) return false;
    while (at < size && space(text[at])) ++at;
    if (size - at < 4 || (text[at] != 'r' && text[at] != '-')
        || (text[at + 1] != 'w' && text[at + 1] != '-') || (text[at + 2] != 'x' && text[at + 2] != '-')
        || (text[at + 3] != 'p' && text[at + 3] != 's') || (size - at > 4 && !space(text[at + 4]))) return false;
    value.readable = text[at] == 'r';
    value.writable = text[at + 1] == 'w';
    result = value;
    return true;
}
enum class Visit { Continue, Stop, Reject };
struct Scan {
    bool good = false;
    size_t chunks = 0, rows = 0;
};
template<class Visitor> Scan scan(FILE* file, Visitor visitor, size_t row_limit = 16384, size_t chunk_limit = 32768) {
    Scan result;
    if (!file) return result;
    char line[512];
    bool continuation = false;
    while (fgets(line, sizeof(line), file)) {
        if (++result.chunks > chunk_limit) return result;
        const size_t length = strlen(line);
        const bool more = length && line[length - 1] != '\n';
        if (continuation) { continuation = more; continue; }
        if (++result.rows > row_limit) return result;
        Mapping mapping;
        if (!parse(line, length, mapping)) return result;
        const Visit action = visitor(mapping);
        if (action == Visit::Reject) return result;
        if (action == Visit::Stop) { result.good = !ferror(file); return result; }
        continuation = more;
    }
    result.good = !ferror(file);
    return result;
}
struct Snapshot {
    static constexpr size_t LIMIT = 8192;
    Mapping ranges[LIMIT] = {};
    size_t count = 0;
    bool valid = false, opened = false;
    Scan scanned;
    explicit Snapshot(const char* path = "/proc/self/maps") {
        FILE* file = fopen(path, "r");
        if (!file) return;
        opened = true;
        scanned = scan(file, [&](const Mapping& mapping) {
            if (!mapping.readable) return Visit::Continue;
            if (count == LIMIT) return Visit::Reject;
            ranges[count++] = mapping;
            return Visit::Continue;
        });
        const bool closed = fclose(file) == 0;
        valid = scanned.good && closed;
    }
    bool contains(uintptr_t address, size_t bytes, bool write = false) const {
        if (!valid || !address || bytes > ~uintptr_t(0) - address) return false;
        for (size_t i = 0; i < count; ++i) if (ranges[i].contains(address, bytes, write)) return true;
        return false;
    }
};
inline thread_local const Snapshot* current_snapshot = nullptr;
struct Scope {
    Snapshot snapshot;
    const Snapshot* previous;
    explicit Scope(const char* path = "/proc/self/maps") : snapshot(path), previous(current_snapshot) { current_snapshot = &snapshot; }
    ~Scope() { current_snapshot = previous; }
    Scope(const Scope&) = delete;
    Scope& operator=(const Scope&) = delete;
};
}
