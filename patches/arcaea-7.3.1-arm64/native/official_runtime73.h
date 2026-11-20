#pragma once

struct OfficialModule {
    Address base = 0;
    anomaly_monitor::Range readable[8] = {};
    anomaly_monitor::Range executable[4] = {};
    size_t readable_count = 0, executable_count = 0;
};
OfficialModule module;
Toggle* official_mailbox = nullptr;

bool in_ranges(const anomaly_monitor::Range* list, size_t count, Address address, size_t size) {
    for (size_t i = 0; i < count; ++i)
        if (anomaly_monitor::contains(list[i], address, size)) return true;
    return false;
}

bool module_readable(Address address, size_t size) {
    return in_ranges(module.readable, module.readable_count, address, size);
}

struct RetainedRanges {
    anomaly_monitor::Range actor, scene;
};
thread_local const RetainedRanges* retained = nullptr;

// Factory retains both native objects. The hot update path needs no procfs scan
// for accesses wholly within those objects, including nested lifecycle calls.
struct RetainedScope {
    RetainedRanges bounds;
    const RetainedRanges* previous = retained;
    RetainedScope(Address actor, size_t bytes, Address scene)
        : bounds{{actor, actor+bytes}, {scene, scene+0x338}} {
        if (actor && scene) retained = &bounds;
    }
    ~RetainedScope() { retained = previous; }
};

bool process_readable(Address address, size_t size, bool writable = false) {
    if (!address || size > ~Address(0)-address) return false;
    if (retained && (anomaly_monitor::contains(retained->actor, address, size)
                  || anomaly_monitor::contains(retained->scene, address, size))) return true;
    if (!writable && module_readable(address, size)) return true;
    if (monitor_maps::current_snapshot && monitor_maps::current_snapshot->contains(address, size, writable))
        return true;
    FILE* file = fopen("/proc/self/maps", "r");
    if (!file) return false;
    bool found = false;
    const auto scan = monitor_maps::scan(file, [&](const monitor_maps::Mapping& mapping) {
        if (!mapping.contains(address, size, writable)) return monitor_maps::Visit::Continue;
        found = true;
        return monitor_maps::Visit::Stop;
    });
    const bool closed = fclose(file) == 0;
    return found && scan.good && closed;
}

bool static_pointer(Address address, Address* value) {
    if (!address || !module_readable(address, sizeof(*value))) return false;
    std::memcpy(value, reinterpret_cast<const void*>(address), sizeof(*value));
    return true;
}

bool song_id(Address song, char* output, size_t capacity) {
    if (capacity < 65 || !process_readable(song, 24)) return false;
    unsigned char object[24];
    std::memcpy(object, reinterpret_cast<const void*>(song), sizeof(object));
    size_t size = object[0] >> 1;
    if (object[0] & 1) {
        Address data = 0;
        std::memcpy(&size, object+8, sizeof(size));
        std::memcpy(&data, object+16, sizeof(data));
        if (!size || size > 64 || !process_readable(data, size+1)) return false;
        std::memcpy(output, reinterpret_cast<const void*>(data), size+1);
    } else {
        if (!size || size > 22) return false;
        std::memcpy(output, object+1, size+1);
    }
    if (output[size]) return false;
    for (size_t i = 0; i < size; ++i) {
        const char c = output[i];
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_')) return false;
    }
    return true;
}

bool official_thread() {
    return official_mailbox && owner.load(std::memory_order_acquire) == pthread_self();
}

using anomaly_monitor::Size;
constexpr const char* TAG = tag;
#include "official_code73.h"

int find_official_module(dl_phdr_info* info, size_t, void* context) {
    auto& candidate = *static_cast<OfficialModule*>(context);
    if (info->dlpi_addr != candidate.base) return 0;
    for (size_t i = 0; i < info->dlpi_phnum; ++i) {
        const auto& ph = info->dlpi_phdr[i];
        if (ph.p_type != PT_LOAD) continue;
        if (ph.p_vaddr > ~Address(0)-candidate.base
            || ph.p_memsz > ~Address(0)-candidate.base-ph.p_vaddr) {
            candidate.readable_count = candidate.executable_count = 0;
            return 1;
        }
        const anomaly_monitor::Range range = {candidate.base+ph.p_vaddr,
                                              candidate.base+ph.p_vaddr+ph.p_memsz};
        if (ph.p_flags & PF_R) {
            if (candidate.readable_count == 8) {
                candidate.readable_count = candidate.executable_count = 0;
                return 1;
            }
            candidate.readable[candidate.readable_count++] = range;
        }
        if (ph.p_flags & PF_X) {
            if (candidate.executable_count == 4) {
                candidate.readable_count = candidate.executable_count = 0;
                return 1;
            }
            candidate.executable[candidate.executable_count++] = range;
        }
    }
    return 1;
}

void prepare_official(Address base) {
    if (official_mailbox) return;
    OfficialModule candidate;
    candidate.base = base;
    dl_iterate_phdr(find_official_module, &candidate);
    if (!candidate.readable_count || !candidate.executable_count) return;
    module = candidate;
    official_mailbox = &mailbox(base);
    if (!initialize_official_bridge()) official_mailbox = nullptr;
}
