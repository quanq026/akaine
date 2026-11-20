#pragma once
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <stdint.h>
#include <stddef.h>
#include <sys/uio.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>
#include <sys/mman.h>

namespace sampler_probe {
inline constexpr size_t LIMIT = 4096;
inline bool exact(ssize_t copied, size_t bytes) { return bytes && bytes <= LIMIT && copied == ssize_t(bytes); }
inline bool copy(uintptr_t address, void* output, size_t bytes) {
    if (!address || !output || !bytes || bytes > LIMIT || bytes > ~uintptr_t(0) - address) return false;
    const iovec local = {output, bytes};
    const iovec remote = {reinterpret_cast<void*>(address), bytes};
    return exact(process_vm_readv(getpid(), &local, 1, &remote, 1, 0), bytes);
}
inline thread_local bool mod_read_active = false;
struct ModReadScope {
    bool previous;
    ModReadScope() : previous(mod_read_active) { mod_read_active = true; }
    ~ModReadScope() { mod_read_active = previous; }
    ModReadScope(const ModReadScope&) = delete;
    ModReadScope& operator=(const ModReadScope&) = delete;
};
inline bool readable(uintptr_t address, size_t bytes) {
    if (!address || !bytes || bytes > LIMIT || bytes > ~uintptr_t(0) - address) return false;
    unsigned char scratch[LIMIT];
    const iovec local = {scratch, bytes};
    const iovec remote = {reinterpret_cast<void*>(address), bytes};
    const ssize_t copied = process_vm_readv(getpid(), &local, 1, &remote, 1, 0);
    return exact(copied, bytes);
}
inline thread_local bool active = false;
struct Capability {
    bool passed = false;
    int error = 0;
};
inline Capability self_test() {
    Capability result;
    unsigned char source[64]; memset(source, 0x5a, sizeof(source));
    if (!readable(uintptr_t(source), sizeof(source))) { result.error = errno; return result; }
    const long page_value = sysconf(_SC_PAGESIZE);
    if (page_value <= 0) { result.error = errno; return result; }
    const size_t page = size_t(page_value);
    if (page > ~size_t(0) / 2) return result;
    void* region = mmap(nullptr, page * 2, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (region == MAP_FAILED) { result.error = errno; return result; }
    bool valid = mprotect(region, page, PROT_READ) == 0;
    if (valid) valid = readable(uintptr_t(region), 64);
    if (valid) valid = mprotect(static_cast<char*>(region) + page, page, PROT_NONE) == 0;
    if (valid) valid = !readable(uintptr_t(region) + page, 1) && !readable(uintptr_t(region) + page - 16, 32);
    const int observed_error = errno;
    const bool released = munmap(region, page * 2) == 0;
    result.passed = valid && released;
    result.error = result.passed ? 0 : observed_error;
    return result;
}
struct Scope {
    bool previous;
    Scope() : previous(active) { active = true; }
    ~Scope() { active = previous; }
    Scope(const Scope&) = delete;
    Scope& operator=(const Scope&) = delete;
};
}
