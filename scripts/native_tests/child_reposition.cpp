#include "child_reposition.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <climits>
#include <cstdio>
#include <random>
#include <vector>

template <typename T> void put(uintptr_t at, T value) { std::memcpy(reinterpret_cast<void*>(at), &value, sizeof(value)); }
constexpr uintptr_t base = 0x10000000;
bool native_less(uintptr_t a, uintptr_t b) { return child_order::less(child_order::key(a), child_order::key(b)); }
int main() {
    std::array<unsigned char, 0x200> parent{};
    std::array<uintptr_t, 7> table{};
    std::array<uintptr_t, 3> native_vector{};
    uintptr_t comparator = base + 0xc4d284;
    const auto p = reinterpret_cast<uintptr_t>(parent.data());
    put(p, base + 0x1a993f0); put(p + 0x140, reinterpret_cast<uintptr_t>(native_vector.data())); table[6] = base + 0x1924a58;
    std::mt19937 random(0x415243);
    unsigned cases = 0, moved = 0, fallback = 0;
    for (unsigned trial = 0; trial != 40000; ++trial) {
        const size_t count = 1 + trial % 101;
        std::vector<std::array<unsigned char, 0x1a8>> nodes(count);
        std::vector<uintptr_t> order;
        for (size_t i = 0; i < count; ++i) {
            const auto n = reinterpret_cast<uintptr_t>(nodes[i].data());
            put(n, reinterpret_cast<uintptr_t>(table.data()));
            put<int32_t>(n + 0x134, int32_t(random() % 7) - 3); put<int32_t>(n + 0x1a0, int32_t(random())); order.push_back(n);
        }
        std::sort(order.begin(), order.end(), native_less);
        const bool first = trial % 2 == 0;
        const size_t index = first ? count - 1 : random() % count;
        const auto child = order[index];
        put<int32_t>(child + 0x134, trial % 11 ? int32_t(random() % 7) - 3 : INT_MIN);
        put<int32_t>(child + 0x1a0, trial % 13 ? int32_t(random()) : INT_MAX);
        if (trial % 5 == 0 && count > 1) {
            const auto other = order[index ? 0 : 1];
            put<int32_t>(child + 0x134, child_order::key(other).z);
            put<int32_t>(child + 0x1a0, child_order::key(other).arrival);
        }
        if (trial % 7 == 0 && count > 3) std::swap(order[0], order[1]);
        const auto begin = reinterpret_cast<uintptr_t>(order.data()), end = begin + count * 8;
        native_vector = {begin, end, end};
        const auto before_nodes = nodes; const auto before_parent = parent; const auto before = order;
        std::vector<uintptr_t> remaining;
        for (auto n : order) if (n != child) remaining.push_back(n);
        bool valid = !first || order.back() == child;
        for (size_t i = 1; i < remaining.size(); ++i) valid &= native_less(remaining[i - 1], remaining[i]);
        for (auto n : remaining) valid &= native_less(n, child) || native_less(child, n);
        const auto result = child_order::inspect(begin, end, reinterpret_cast<uintptr_t>(&comparator), p,
            base + (first ? 0x109062c : 0x9fd7b4), base, first ? child : 0, first ? 0 : child);
        assert(result.skipped == valid); assert(result.checked <= count);
        assert(nodes == before_nodes && parent == before_parent);
        if (result.skipped) {
            auto expected = before; std::sort(expected.begin(), expected.end(), native_less); assert(order == expected);
            assert(result.moved == (order != before)); moved += result.moved;
        } else { assert(order == before); assert(!result.moved); ++fallback; }
        ++cases;
    }
    // Match append with an old arrival, followed by the outer add's new arrival assignment.
    std::vector<std::array<unsigned char, 0x1a8>> nodes(2000);
    std::vector<uintptr_t> order; order.reserve(nodes.size());
    for (size_t i = 0; i < nodes.size(); ++i) {
        const auto n = reinterpret_cast<uintptr_t>(nodes[i].data()); put(n, reinterpret_cast<uintptr_t>(table.data()));
        put<int32_t>(n + 0x134, 0); put<int32_t>(n + 0x1a0, -int32_t(i + 1)); order.push_back(n);
        for (unsigned phase = 0; phase != 2; ++phase) {
            if (phase) put<int32_t>(n + 0x1a0, int32_t(i + 1));
            const auto begin = reinterpret_cast<uintptr_t>(order.data()), end = begin + order.size() * 8;
            native_vector = {begin, end, end}; auto expected = order; std::sort(expected.begin(), expected.end(), native_less);
            const auto result = child_order::inspect(begin, end, reinterpret_cast<uintptr_t>(&comparator), p,
                base + (phase ? 0x9fd7b4 : 0x109062c), base, n, n);
            assert(result.skipped && order == expected); moved += result.moved; ++cases;
        }
    }
    std::array<unsigned char, 0x1a8> node{};
    const auto n = reinterpret_cast<uintptr_t>(node.data()); put(n, reinterpret_cast<uintptr_t>(table.data()));
    uintptr_t one[] = {n, n}; const auto begin = reinterpret_cast<uintptr_t>(one);
    native_vector = {begin, begin + 8, begin + 8};
    const auto inspect = [&](uintptr_t caller = 0x1109062c, uintptr_t a = 0, uintptr_t b = 0) {
        return child_order::inspect(begin, native_vector[1], reinterpret_cast<uintptr_t>(&comparator), p, caller, base, a ? a : n, b ? b : n).skipped;
    };
    assert(inspect()); put<uint8_t>(p + 0x1c0, 1); assert(!inspect()); put<uint8_t>(p + 0x1c0, 0);
    put(p, base + 0x1a993f8); assert(!inspect()); put(p, base + 0x1a993f0);
    comparator++; assert(!inspect()); comparator--; assert(!inspect(base + 0x1234));
    native_vector[0] += 8; assert(!inspect()); native_vector[0] -= 8;
    table[6]++; assert(!inspect()); table[6]--; one[0] = 0; assert(!inspect()); one[0] = n;
    native_vector[1] = begin + 16; assert(!inspect()); native_vector[1] = begin + 8;
    assert(!inspect(0x1109062c, 1, 1)); assert(!inspect(0x109fd7b4, 1, 1));
    native_vector[1] = begin; assert(!inspect()); native_vector[1] = begin + 9; assert(!inspect());
    native_vector[1] = begin - 8; assert(!inspect()); native_vector[1] = begin + 65537ULL * 8; assert(!inspect());
    std::printf("{\"status\":\"PASS_CHILD_REPOSITION\",\"property_and_pipeline_cases\":%u,\"moved\":%u,\"fallback\":%u,\"guard_cases\":14,\"no_node_parent_writes\":true,\"native_unique_order_exact\":true}\n", cases, moved, fallback);
}
