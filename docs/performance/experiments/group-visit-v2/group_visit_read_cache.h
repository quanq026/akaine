#pragma once
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace group_visit_read_cache {
// One Group predicate invocation only. Store exactly successful copied Node
// slabs; never round up a read, cache failures, or retain process pointers later.
struct Cache {
    static constexpr std::size_t SLAB = 0x1c3, CAPACITY = 32;
    struct Entry { uintptr_t address; unsigned char bytes[SLAB]; } entries[CAPACITY];
    unsigned count;
    Cache() : count(0) {} // Unused byte storage is not read or cleared per visit.
    void clear() { count = 0; }
    template<class Copy> bool read(uintptr_t address, void* output, std::size_t size, Copy copy) {
        if (!address || !output || !size || size > ~uintptr_t(0) - address) return false;
        for (unsigned i = 0; i < count; ++i) {
            const auto& entry = entries[i];
            if (address >= entry.address && address - entry.address <= SLAB
                    && size <= SLAB - (address - entry.address)) {
                std::memcpy(output, entry.bytes + address - entry.address, size); return true;
            }
        }
        if (!copy(address, output, size)) return false;
        if (size == SLAB && count < CAPACITY) {
            auto& entry = entries[count++]; entry.address = address;
            std::memcpy(entry.bytes, output, size);
        }
        return true;
    }
};
static_assert(sizeof(Cache) <= 32768, "Per-callback snapshot storage must remain bounded");
} // namespace group_visit_read_cache
