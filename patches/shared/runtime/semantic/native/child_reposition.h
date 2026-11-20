#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace child_order {
template <typename T> inline T read(uintptr_t at) noexcept {
    T value;
    std::memcpy(&value, reinterpret_cast<const void*>(at), sizeof(value));
    return value;
}
struct Key { int32_t z, arrival; };
inline bool less(Key a, Key b) noexcept {
    return a.z < b.z || (a.z == b.z && a.arrival < b.arrival);
}
inline Key key(uintptr_t node) noexcept {
    return {read<int32_t>(node + 0x134), read<int32_t>(node + 0x1a0)};
}
inline bool getter(uintptr_t node, uintptr_t base) noexcept {
    if (!node) return false;
    const auto table = read<uintptr_t>(node);
    return table && read<uintptr_t>(table + 0x30) == base + 0x1924a58;
}
struct Result { bool skipped = false; uint64_t checked = 0; bool moved = false; };
inline Result inspect(uintptr_t begin, uintptr_t end, uintptr_t comparator,
                      uintptr_t parent, uintptr_t caller, uintptr_t base,
                      uintptr_t first_child, uintptr_t second_child) noexcept {
    Result result;
    if (!base || !parent || (caller != base + 0x109062c && caller != base + 0x9fd7b4) ||
        read<uintptr_t>(parent) != base + 0x1a993f0 || read<uint8_t>(parent + 0x1c0) ||
        !comparator || read<uintptr_t>(comparator) != base + 0xc4d284 || end <= begin ||
        (begin & 7) || ((end - begin) & 7) || (end - begin) / 8 > 65536) return result;
    const auto vector = read<uintptr_t>(parent + 0x140);
    if (!vector || read<uintptr_t>(vector) != begin || read<uintptr_t>(vector + 8) != end) return result;
    const auto child = caller == base + 0x109062c ? first_child : second_child;
    if (!child) return result;
    if (caller == base + 0x109062c) {
        if (read<uintptr_t>(end - 8) != child) return result;
    } else {
        uintptr_t at = begin;
        while (at != end && read<uintptr_t>(at) != child) at += 8;
        if (at == end) return result;
    }
    if (!getter(child, base)) return result;
    const auto moved_key = key(child);
    Key previous{};
    bool have_previous = false;
    size_t old_index = 0, new_index = 0, occurrences = 0;
    for (uintptr_t at = begin; at != end; at += 8) {
        const auto node = read<uintptr_t>(at);
        ++result.checked;
        if (node == child) { old_index = (at - begin) / 8; ++occurrences; continue; }
        if (!getter(node, base)) return result;
        const auto current = key(node);
        // Validate the whole remaining order and unique keys before any pointer write.
        if ((have_previous && !less(previous, current)) ||
            (!less(current, moved_key) && !less(moved_key, current))) return result;
        if (less(current, moved_key)) ++new_index;
        previous = current; have_previous = true;
    }
    if (occurrences != 1) return result;
    if (new_index < old_index) {
        std::memmove(reinterpret_cast<void*>(begin + (new_index + 1) * 8),
                     reinterpret_cast<const void*>(begin + new_index * 8), (old_index - new_index) * 8);
    } else if (new_index > old_index) {
        std::memmove(reinterpret_cast<void*>(begin + old_index * 8),
                     reinterpret_cast<const void*>(begin + (old_index + 1) * 8), (new_index - old_index) * 8);
    }
    if (new_index != old_index) {
        std::memcpy(reinterpret_cast<void*>(begin + new_index * 8), &child, sizeof(child));
        result.moved = true;
    }
    result.skipped = true;
    return result;
}
}
