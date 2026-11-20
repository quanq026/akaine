#pragma once
#include <stdint.h>

namespace monitor_perf {
struct Aggregate {
    uint64_t count = 0, sum_ns = 0, max_ns = 0, invalid_clock = 0;
    void add(uint64_t start, uint64_t end) {
        ++count;
        if (!start || end < start) { ++invalid_clock; return; }
        const uint64_t elapsed = end - start;
        sum_ns += elapsed;
        if (elapsed > max_ns) max_ns = elapsed;
    }
};
struct Counters {
    Aggregate frame, poll, sample, readable;
    uint64_t maps_open_attempts = 0, maps_open_successes = 0, maps_lines = 0;
};
inline Counters counters;
}
