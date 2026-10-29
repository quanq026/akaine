#pragma once
#include <android/log.h>
#include <atomic>
#include <pthread.h>
#include <stdint.h>
#include <time.h>

// QA only. Existing gates have NO_FDE_INSIDE_PROBE_CAVE. An unbalanced root
// invalidates its whole window; exception paths never supply causal timings.
namespace menu_geometry {
constexpr uint64_t WARMUP_NS = 2000000000ULL, WINDOW_NS = 10000000000ULL;
constexpr unsigned MAX_WINDOWS = 24;
struct Cost { uint64_t count = 0, sum = 0, maximum = 0; };
struct Interval { long long value = 0; unsigned error = 1; };
using IntervalReader = Interval (*)() noexcept;
inline IntervalReader interval_reader = nullptr;
inline std::atomic<bool> armed{false}, used{false}, foreign_thread{false};
inline pthread_t owner;
inline uint64_t warmup_end = 0, window_begin = 0, root_begin = 0, group_begin = 0, last_stamp = 0;
inline Cost costs[2] = {}, pending_group;
inline unsigned depth = 0, sequence = 0, errors = 0, clock_errors = 0, discarded = 0;
inline bool invalid_root = false;

inline uint64_t now() noexcept {
    timespec value = {};
    if (clock_gettime(CLOCK_MONOTONIC, &value) || value.tv_sec < 0 || value.tv_nsec < 0
        || value.tv_nsec >= 1000000000) return 0;
    return uint64_t(value.tv_sec) * 1000000000ULL + uint64_t(value.tv_nsec);
}
inline bool add(Cost& cost, uint64_t duration) noexcept {
    if (cost.count == UINT64_MAX || duration > UINT64_MAX - cost.sum) return false;
    ++cost.count; cost.sum += duration;
    if (duration > cost.maximum) cost.maximum = duration;
    return true;
}
inline bool merge(Cost& target, const Cost& source) noexcept {
    if (source.count > UINT64_MAX - target.count || source.sum > UINT64_MAX - target.sum) return false;
    target.count += source.count; target.sum += source.sum;
    if (source.maximum > target.maximum) target.maximum = source.maximum;
    return true;
}
inline void arm() noexcept {
    bool expected = false;
    if (!used.compare_exchange_strong(expected, true)) return;
    owner = pthread_self();
    const uint64_t stamp = now();
    if (!stamp || stamp > UINT64_MAX - WARMUP_NS) return;
    warmup_end = stamp + WARMUP_NS;
    last_stamp = stamp;
    armed.store(true, std::memory_order_release);
}
inline bool owner_ready() noexcept {
    if (!armed.load(std::memory_order_acquire)) return false;
    if (!pthread_equal(owner, pthread_self())) { foreign_thread.store(true); return false; }
    return true;
}
inline void flush(uint64_t end) noexcept {
    const bool valid = !errors && !clock_errors && !discarded && !foreign_thread.load();
    const Interval interval = interval_reader ? interval_reader() : Interval{};
    // One aggregate after the outer timing ends; never log individual calls.
    __android_log_print(ANDROID_LOG_INFO, "AkaineMenuGeometry",
        "v=1 window=%u begin=%llu end=%llu valid=%u errors=%u clock=%u discarded=%u foreign=%u c1=%llu s1=%llu m1=%llu c2=%llu s2=%llu m2=%llu interval_available=%u interval_error=%u requested_interval_ns=%lld",
        ++sequence, static_cast<unsigned long long>(window_begin), static_cast<unsigned long long>(end),
        unsigned(valid), errors, clock_errors, discarded, unsigned(foreign_thread.load()),
        static_cast<unsigned long long>(costs[0].count), static_cast<unsigned long long>(costs[0].sum),
        static_cast<unsigned long long>(costs[0].maximum), static_cast<unsigned long long>(costs[1].count),
        static_cast<unsigned long long>(costs[1].sum), static_cast<unsigned long long>(costs[1].maximum),
        unsigned(interval.error == 0), interval.error, interval.value);
    costs[0] = {}; costs[1] = {}; window_begin = 0;
    errors = clock_errors = discarded = 0;
    if (!valid || sequence == MAX_WINDOWS) armed.store(false, std::memory_order_release);
}
inline void event(unsigned id, unsigned kind) noexcept {
    if (!owner_ready()) return;
    if ((id != 1 && id != 2) || kind > 1) { ++errors; invalid_root = true; return; }
    const uint64_t stamp = now();
    if (!stamp) {
        ++clock_errors; invalid_root = true;
        if (id == 1 && kind == 1 && depth) { depth = 0; ++discarded; flush(last_stamp); }
        return;
    }
    if (stamp < last_stamp) { ++clock_errors; invalid_root = true; }
    else last_stamp = stamp;
    if (stamp < warmup_end && !depth) return;
    if (id == 1 && kind == 0) {
        if (depth) { ++errors; ++discarded; }
        depth = 1; root_begin = stamp; pending_group = {}; invalid_root = false;
        if (!window_begin) window_begin = stamp;
        return;
    }
    // The group helper can run outside the measured list traversal.
    if (!depth) return;
    if (id == 2 && kind == 0) {
        if (depth != 1) { ++errors; invalid_root = true; return; }
        depth = 2; group_begin = stamp; return;
    }
    if (id == 2) {
        if (depth != 2 || stamp < group_begin) { ++errors; invalid_root = true; return; }
        depth = 1;
        if (!add(pending_group, stamp - group_begin)) { ++errors; invalid_root = true; }
        return;
    }
    if (depth != 1 || stamp < root_begin) { ++errors; invalid_root = true; }
    depth = 0;
    if (invalid_root) ++discarded;
    else if (!add(costs[0], stamp - root_begin) || !merge(costs[1], pending_group)) ++errors;
    if (window_begin && (clock_errors || (stamp >= window_begin && stamp - window_begin >= WINDOW_NS))) flush(last_stamp);
}
} // namespace menu_geometry
