#pragma once
#include "group_visit_adapter.h"
#include "group_visit_read_cache.h"
#include "../native/sampler_read_probe.h"
#include <pthread.h>
#include <android/log.h>

namespace group_visit_owned {
inline pthread_t owner;
inline uintptr_t base = 0;
inline bool ready = false;
inline uint64_t visited = 0, culled = 0, fallback = 0, report_start = 0;
inline unsigned reports = 0;
inline bool count_overflow = false;
inline void increment(uint64_t& value) { if (value == UINT64_MAX) count_overflow = true; else ++value; }
struct Reader {
    uintptr_t base;
    group_visit_read_cache::Cache cache;
    explicit Reader(uintptr_t module_base) : base(module_base) {}
    bool read(uintptr_t address, void* output, size_t size) {
        return cache.read(address, output, size, [](uintptr_t at, void* target, size_t bytes) {
            return sampler_probe::copy(at, target, bytes);
        });
    }
    bool members_hidden(const uintptr_t* addresses, unsigned count, uintptr_t expected_vtable) {
        if (count > 256) return false;
        if (!count) return true;
        uintptr_t vtables[256]{}; uint8_t visible[256]{};
        iovec local[512]{}, remote[512]{};
        for (unsigned index = 0; index < count; ++index) {
            const auto address = addresses[index];
            if (!address || address > ~uintptr_t(0) - 0x1c1) return false;
            local[index * 2] = {&vtables[index], sizeof(uintptr_t)};
            local[index * 2 + 1] = {&visible[index], sizeof(uint8_t)};
            remote[index * 2] = {reinterpret_cast<void*>(address), sizeof(uintptr_t)};
            remote[index * 2 + 1] = {reinterpret_cast<void*>(address + 0x1c1), sizeof(uint8_t)};
        }
        if (process_vm_readv(getpid(), local, count * 2, remote, count * 2, 0) != ssize_t(count * 9)) return false;
        for (unsigned index = 0; index < count; ++index) if (vtables[index] != expected_vtable || visible[index]) return false;
        return true;
    }
    bool label_clean(uintptr_t address) {
        if (!address || address > ~uintptr_t(0) - 0x5e3) return false;
        uint8_t flags[3]{}; iovec local[3]{}, remote[3]{};
        const uintptr_t offsets[] = {0x344, 0x2b4, 0x5e3};
        for (unsigned i = 0; i < 3; ++i) {
            local[i] = {&flags[i], 1}; remote[i] = {reinterpret_cast<void*>(address + offsets[i]), 1};
        }
        return process_vm_readv(getpid(), local, 3, remote, 3, 0) == 3 && !flags[0] && !flags[1] && !flags[2];
    }
    bool write_flags(uintptr_t address, uint32_t flags) {
        cache.clear();
        const iovec local{&flags, sizeof(flags)}, remote{reinterpret_cast<void*>(address), sizeof(flags)};
        return process_vm_writev(getpid(), &local, 1, &remote, 1, 0) == ssize_t(sizeof(flags));
    }
};
inline void visit(uintptr_t self, uintptr_t renderer, uintptr_t transform, uint32_t flags, uint32_t extra) {
    bool skip = false;
    const bool owner_call = ready && pthread_equal(owner, pthread_self());
    if (owner_call) {
        increment(visited);
        try { Reader reader{base}; skip = group_visit_adapter::should_skip(reader, self, renderer, transform, flags); }
        catch (...) { skip = false; }
    }
    if (owner_call) increment(skip ? culled : fallback);
    if (!skip) group_visit_adapter::forward_native(
        reinterpret_cast<void(*)(uintptr_t, uintptr_t, uintptr_t, uint32_t, uint32_t)>(base + 0x1882ca0),
        self, renderer, transform, flags, extra);
}
inline bool initialize(uintptr_t module_base) {
    base = module_base; owner = pthread_self(); ready = sampler_probe::self_test().passed;
    uint32_t local = 0x13579bdf;
    Reader reader{base};
    ready = ready && reader.write_flags(reinterpret_cast<uintptr_t>(&local), local) && local == 0x13579bdf;
    uintptr_t slot = 0;
    ready = ready && reader.read(base + 0x1a99728, &slot, sizeof(slot)) && slot == base + 0x1a7e5f0;
    return ready;
}
} // namespace group_visit_owned
extern "C" void akaine_qa_group_visit_report(uint64_t now) {
    using namespace group_visit_owned;
    if (!ready || !pthread_equal(owner, pthread_self()) || reports == 24 || !now) return;
    if (!report_start) { report_start = now; return; }
    if (now < report_start || now - report_start < 10000000000ULL) return;
    __android_log_print(ANDROID_LOG_INFO, "AkaineGroupVisitQA",
        "v=1 window=%u visited=%llu culled=%llu fallback=%llu overflow=%u",
        ++reports, static_cast<unsigned long long>(visited), static_cast<unsigned long long>(culled),
        static_cast<unsigned long long>(fallback), unsigned(count_overflow));
    visited = culled = fallback = 0; count_overflow = false; report_start = now;
}
