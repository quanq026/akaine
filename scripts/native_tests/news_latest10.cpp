#include <array>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <numeric>
#include "news_latest10.h"
static bool fail_allocation = false;
void* operator new(std::size_t size) {
    if (fail_allocation) throw std::bad_alloc();
    if (void* pointer = std::malloc(size ? size : 1)) return pointer;
    throw std::bad_alloc();
}
void operator delete(void* pointer) noexcept { std::free(pointer); }
void operator delete(void* pointer, std::size_t) noexcept { std::free(pointer); }
using Record = std::array<unsigned char, news_latest10::STRIDE>;
static std::vector<Record> records(std::size_t count) {
    std::vector<Record> out(count);
    for (std::size_t i = 0; i < count; ++i) {
        for (std::size_t j = 0; j < out[i].size(); ++j) out[i][j] = static_cast<unsigned char>(i * 31 + j);
        std::memcpy(out[i].data(), &i, sizeof(i));
    }
    return out;
}
static void check(std::vector<Record> values, const std::vector<uint64_t>& dates) {
    const auto before = values;
    std::vector<std::size_t> expected(values.size());
    std::iota(expected.begin(), expected.end(), 0);
    std::stable_sort(expected.begin(), expected.end(), [&](auto a, auto b) { return dates[a] > dates[b]; });
    std::size_t selected = 999;
    void* end = values.empty() ? values.data() : values.data() + values.size();
    assert(news_latest10::reorder(values.data(), end, dates, &selected));
    assert(selected == std::min(values.size(), news_latest10::LIMIT));
    for (std::size_t i = 0; i < values.size(); ++i) assert(values[i] == before[expected[i]]);
    // Every full owning record remains exactly once, including the invisible tail.
    std::sort(values.begin(), values.end()); auto originals = before;
    std::sort(originals.begin(), originals.end()); assert(values == originals);
}
int main() {
    for (std::size_t n : {0u, 1u, 9u, 10u, 11u, 199u, 200u, 16384u}) {
        std::vector<uint64_t> dates(n, 9999999999ULL);
        for (std::size_t i = 0; i < std::min(n, std::size_t(7)); ++i) dates[n - 1 - i] = 16206912734ULL - i;
        check(records(n), dates); // Seven newer songs; tied placeholder order stays native.
        std::reverse(dates.begin(), dates.end()); check(records(n), dates);
    }
    auto all = records(200); std::vector<uint64_t> ranks(200, 9999999999ULL);
    ranks[198] = 16206912734ULL; ranks[199] = ranks[198]; // Song and pack max-date tie.
    check(all, ranks);
    const auto unchanged = all; std::size_t selected = 999;
    ranks.pop_back(); assert(!news_latest10::reorder(all.data(), all.data() + all.size(), ranks, &selected));
    assert(all == unchanged && !selected); // Unresolved/missing rank aborts before mutation.
    assert(!news_latest10::reorder(all.data(), reinterpret_cast<unsigned char*>(all.data()) + 57, ranks, &selected));
    assert(!news_latest10::reorder(all.data() + 1, all.data(), ranks, &selected));
    assert(!news_latest10::reorder(nullptr, reinterpret_cast<void*>(56), {1}, &selected));
    assert(!news_latest10::reorder(reinterpret_cast<void*>(1), reinterpret_cast<void*>(1 + 56 * 16385), {}, &selected));
    assert(!news_latest10::reorder(all.data(), all.data() + all.size(), {}, nullptr));
    ranks.push_back(9999999999ULL); fail_allocation = true;
    const bool allocated = news_latest10::reorder(all.data(), all.data() + all.size(), ranks, &selected);
    fail_allocation = false; assert(!allocated && all == unchanged && !selected);
    puts("PASS stable latest10/date ties/pack ranks, counts0..16384, all56B records and cleanup tail preserved, invalid span/ranks unchanged");
}
