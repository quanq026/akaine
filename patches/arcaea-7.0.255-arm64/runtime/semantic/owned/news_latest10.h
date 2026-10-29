#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>

namespace news_latest10 {
constexpr std::size_t STRIDE = 56, LIMIT = 10, MAX_RECORDS = 16384;
// Caller resolves every rank first. Raw descriptor bytes only move; original
// vector bounds and every owning string/object remain intact for native cleanup.
inline bool reorder(void* begin, void* end, const std::vector<uint64_t>& dates,
                    std::size_t* selected) noexcept {
    if (!selected) return false;
    *selected = 0;
    const auto first = reinterpret_cast<uintptr_t>(begin), last = reinterpret_cast<uintptr_t>(end);
    if (last < first || (last - first) % STRIDE || (last - first) / STRIDE > MAX_RECORDS) return false;
    const std::size_t count = (last - first) / STRIDE;
    if ((!first && count) || dates.size() != count) return false;
    std::vector<std::size_t> order, destination;
    try {
        order.resize(count); destination.resize(count);
        for (std::size_t index = 0; index < count; ++index) order[index] = index;
        std::sort(order.begin(), order.end(), [&](std::size_t a, std::size_t b) {
            return dates[a] != dates[b] ? dates[a] > dates[b] : a < b;
        });
        for (std::size_t index = 0; index < count; ++index) destination[order[index]] = index;
    } catch (...) { return false; } // All potentially throwing work precedes mutation.
    auto* bytes = static_cast<unsigned char*>(begin);
    for (std::size_t index = 0; index < count; ++index) {
        while (destination[index] != index) {
            const std::size_t target = destination[index];
            unsigned char temporary[STRIDE];
            std::memcpy(temporary, bytes + index * STRIDE, STRIDE);
            std::memcpy(bytes + index * STRIDE, bytes + target * STRIDE, STRIDE);
            std::memcpy(bytes + target * STRIDE, temporary, STRIDE);
            std::swap(destination[index], destination[target]);
        }
    }
    *selected = std::min(count, LIMIT);
    return true;
}
} // namespace news_latest10
