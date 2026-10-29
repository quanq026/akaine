#include <cassert>
#include <cstdio>
#include <limits>
#include "group_visit_read_cache.h"
using group_visit_read_cache::Cache;
int main() {
    unsigned calls = 0; unsigned char source[Cache::SLAB + 32], output[Cache::SLAB + 32];
    for (unsigned i = 0; i < sizeof(source); ++i) source[i] = static_cast<unsigned char>(i);
    auto copy = [&](uintptr_t at, void* out, size_t size) {
        ++calls;
        if (at < 0x1000 || at - 0x1000 + size > sizeof(source)) return false;
        std::memcpy(out, source + at - 0x1000, size); return true;
    };
    Cache cache;
    assert(cache.read(0x1000, output, Cache::SLAB, copy) && calls == 1 && cache.count == 1);
    assert(cache.read(0x1140, output, 8, copy) && calls == 1 && output[0] == 0x40);
    assert(cache.read(0x1000, output, Cache::SLAB, copy) && calls == 1);
    assert(cache.read(0x11c0, output, 3, copy) && calls == 1);
    assert(cache.read(0x11c0, output, 4, copy) && calls == 2); // Crossing cached bound uses safe copier.
    assert(!cache.read(0x2000, output, Cache::SLAB, copy) && calls == 3 && cache.count == 1);
    source[0] = 0x99; assert(cache.read(0x1000, output, 1, copy) && output[0] == 0 && calls == 3);
    cache.clear(); assert(cache.read(0x1000, output, 1, copy) && output[0] == 0x99 && calls == 4 && !cache.count);
    Cache next_callback;
    assert(next_callback.read(0x1000, output, 1, copy) && calls == 5); // No snapshot crosses invocation lifetime.
    assert(!cache.read(std::numeric_limits<uintptr_t>::max() - 3, output, 8, copy) && calls == 5);
    assert(!cache.read(0x1000, nullptr, 1, copy) && calls == 5);
    Cache full; unsigned successes = 0;
    auto fill = [&](uintptr_t, void* out, size_t size) { ++successes; std::memset(out, 0x5a, size); return true; };
    for (unsigned i = 0; i < Cache::CAPACITY + 2; ++i) assert(full.read(0x1000 + i * 0x1000, output, Cache::SLAB, fill));
    assert(full.count == Cache::CAPACITY && successes == Cache::CAPACITY + 2);
    assert(full.read(0x1000, output, 8, fill) && successes == Cache::CAPACITY + 2);
    puts("PASS callback-local exact successful slab/subrange reuse, safe-copy fallback, failure exclusion, bounded capacity, invalidation and fresh callback");
}
