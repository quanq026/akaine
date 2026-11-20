#include <android/log.h>
#include <jni.h>
#include <link.h>
#include <pthread.h>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <utility>
#include "mod_abi73.h"

namespace {
using Address = uintptr_t;
static_assert(sizeof(std::string) == 24);
constexpr uint32_t mod_section = 8;
constexpr uint32_t variety_section = 7;
constexpr char mod_pack[] = "xd_fan_album";
constexpr char sidebar_layout[] = "layouts/songselect/PackListModMenu.csb";
constexpr char heading_layout[] = "layouts/songselect/ModDividerNativeFrame.csb";
constexpr float stops[] = {-2395, -1905, -1415, -925, -435, 55};
constexpr size_t stock_stops_size = sizeof(stops) - sizeof(float);

std::atomic<Address> base{0};
std::atomic<pthread_t> owner{0};
thread_local Address pending_sidebar;

template<class T> T& field(Address object, size_t offset) {
    return *reinterpret_cast<T*>(object + offset);
}

template<class Return, class... Args>
Return native_call(Address va, Args... args) {
    return reinterpret_cast<Return (*)(Args...)>(base + va)(args...);
}

bool owner_thread() {
    return owner.load(std::memory_order_acquire) == pthread_self();
}

struct NativeAllocation {
    Address data = 0;
    ~NativeAllocation() { if (data) native_call<void>(deallocate, data); }
    Address take() { return std::exchange(data, 0); }
};

struct Stops {
    Address begin;
    Address end;
    Address capacity;
};
static_assert(sizeof(Stops) == 24);

bool six_stops(Address scene) {
    if (!scene) return false;
    const auto& values = field<Stops>(scene, 0x2e8);
    return values.begin && values.end >= values.begin && values.end - values.begin == sizeof(stops);
}

Address current_mod_pack() {
    const Address slot = field<Address>(base, manager_slot);
    if (slot != base + manager_global) return 0;
    const Address context = field<Address>(slot, 0);
    const Address manager = context ? field<Address>(context, 0x20) : 0;
    if (!manager) return 0;
    const std::string id(mod_pack);
    const Address pack = native_call<Address>(find_pack, manager, &id);
    return pack && field<const std::string>(pack, 8) == id ? pack : 0;
}

bool prepare_sidebar(Address scene) {
    if (!scene || pending_sidebar || !field<Address>(scene, 0x328)) return false;
    const Address pack = current_mod_pack();
    if (!pack) return false;
    auto& section = field<uint32_t>(pack, 0xc4);
    if (section != variety_section && section != mod_section) return false;

    auto& view_stops = field<Stops>(scene, 0x2e8);
    const auto old_stops = view_stops;
    if (!old_stops.begin || old_stops.begin % alignof(float) || old_stops.end < old_stops.begin
        || old_stops.capacity < old_stops.end || old_stops.capacity - old_stops.begin > 4096
        || (old_stops.capacity - old_stops.begin) % sizeof(float)
        || old_stops.end - old_stops.begin != stock_stops_size
        || std::memcmp(reinterpret_cast<const void*>(old_stops.begin), stops, stock_stops_size))
        return false;

    const std::string button_name("button6");
    Address parent = 0;
    auto* slot = native_call<Address*>(find_button, scene + 0x3b8, &parent, &button_name);
    const Address first = field<Address>(scene, 0x3b8);
    if (!slot || *slot || !first || !parent || field<size_t>(scene, 0x3c8) != 5) return false;

    const std::string layout(sidebar_layout);
    const Address new_sidebar = native_call<Address>(load_csb, &layout);
    if (!new_sidebar) return false;
    NativeAllocation button{native_call<Address>(allocate, size_t{0x40})};
    if (!button.data) return false;
    std::memset(reinterpret_cast<void*>(button.data), 0, 0x40);
    field<Address>(button.data, 0x10) = parent;
    // The tree node owns the name. A short libc++ string stores its bytes inline.
    uint8_t* key = reinterpret_cast<uint8_t*>(button.data + 0x20);
    key[0] = 2 * button_name.size();
    std::memcpy(key + 1, button_name.c_str(), button_name.size() + 1);
    field<uint32_t>(button.data, 0x38) = mod_section;

    NativeAllocation replacement;
    if (old_stops.capacity - old_stops.end < sizeof(float)) {
        replacement.data = native_call<Address>(allocate, sizeof(stops));
        if (!replacement.data) return false;
        std::memcpy(reinterpret_cast<void*>(replacement.data), stops, sizeof(stops));
    }

    native_call<void>(register_section, scene, mod_section);
    // Allocations and layout loading precede the stock tree/vector mutations.
    *slot = button.take();
    const Address new_first = field<Address>(first, 0);
    if (new_first) field<Address>(scene, 0x3b8) = new_first;
    native_call<void>(rebalance, field<Address>(scene, 0x3c0), *slot);
    ++field<size_t>(scene, 0x3c8);
    if (replacement.data) {
        const Address start = replacement.take();
        view_stops = {start, start + sizeof(stops), start + sizeof(stops)};
        native_call<void>(deallocate, old_stops.begin);
    } else {
        field<float>(old_stops.end, 0) = stops[5];
        view_stops.end += sizeof(float);
    }
    section = mod_section;
    pending_sidebar = new_sidebar;
    return true;
}

Address sidebar_loader(const std::string* path) {
    if (pending_sidebar) return std::exchange(pending_sidebar, 0);
    return native_call<Address>(load_csb, path);
}

void sidebar(Address scene) {
    bool ready = false;
    if (owner_thread()) {
        try { ready = prepare_sidebar(scene); } catch (...) { ready = false; }
        if (!ready) {
            try {
                const Address pack = current_mod_pack();
                if (pack && field<uint32_t>(pack, 0xc4) == mod_section && !six_stops(scene))
                    field<uint32_t>(pack, 0xc4) = variety_section;
            } catch (...) {}
        }
    }
    native_call<void>(stock_sidebar, scene);
    pending_sidebar = 0;
    if (!ready) return;
    const Address widget = field<Address>(scene, 0x338);
    if (!widget || field<Address>(widget, 0) != base + scroll_vtable || !six_stops(scene)) return;
    auto& maximum = field<float>(widget, 0x758);
    if (maximum != 0 && maximum != stops[5]) return;
    maximum = stops[5];
    field<uint8_t>(widget, 0x7e8) = 1;
    __android_log_print(ANDROID_LOG_INFO, "AkaineMod73", "sidebar section=8 scroll_stops=6");
}

struct Point { float x; float y; };

Address heading(Address scene, uint32_t section) {
    if (section != mod_section)
        return native_call<Address>(stock_heading, scene, section);
    const Address node = native_call<Address>(stock_heading, scene, variety_section);
    if (!owner_thread() || !node || field<Address>(node, 0) != base + heading_vtable) return node;
    try {
        const std::string path(heading_layout);
        const Address content = native_call<Address>(load_csb, &path);
        if (!content || field<Address>(content, 0) != base + node_vtable) return node;
        const Address children = field<Address>(node, 0x140);
        if (!children) return node;
        const Address begin = field<Address>(children, 0);
        if (!begin || field<Address>(children, 8) != begin + sizeof(Address)) return node;
        const Address sprite = field<Address>(begin, 0);
        if (!sprite || field<Address>(sprite, 0) != base + sprite_vtable) return node;
        const Point size = field<Point>(sprite, 0x5c);
        const Point position = field<Point>(sprite, 0x38);
        const Point anchor = field<Point>(content, 0x54);
        const Point content_size = field<Point>(content, 0x5c);
        const float scale = size.y / 457.0f;
        const bool valid_anchor = (anchor.x == 0 && anchor.y == 0)
            || (anchor.x == 0.5f && anchor.y == 0.5f);
        if (!(scale > 0.1f && scale < 8.0f) || !(std::fabs(size.x / 110.0f - scale) <= 0.001f)
            || !valid_anchor || content_size.x != 110 || content_size.y != 457)
            return node;
        const Point center{0.5f, 0.5f};
        native_call<void>(set_anchor, content, &center);
        native_call<void>(set_scale, content, scale);
        native_call<void>(set_position, content, &position);
        native_call<void>(add_child, node, content);
        native_call<void>(set_sprite_visible, sprite, false);
    } catch (...) {}
    return node;
}

int locate_core(dl_phdr_info* module, size_t, void* result) {
    const char* path = module->dlpi_name;
    if (!path) return 0;
    const char* slash = std::strrchr(path, '/');
    if (std::strcmp(slash ? slash + 1 : path, "libcocos2dcpp.so")) return 0;
    bool executable = false, writable = false;
    for (size_t i = 0; i < module->dlpi_phnum; ++i) {
        const auto& phdr = module->dlpi_phdr[i];
        if (phdr.p_type != PT_LOAD) continue;
        executable |= !phdr.p_vaddr && phdr.p_flags == (PF_R | PF_X)
            && phdr.p_filesz == rx_end && phdr.p_memsz == rx_end;
        writable |= phdr.p_vaddr == rw_va && phdr.p_flags == (PF_R | PF_W)
            && phdr.p_filesz == rw_file_size && phdr.p_memsz == rw_mem_size;
    }
    if (!executable || !writable) return 1;
    for (const auto& pin : mod_pins) {
        if (pin.address > rx_end || pin.length > rx_end - pin.address
            || std::memcmp(reinterpret_cast<const void*>(module->dlpi_addr + pin.address), pin.bytes, pin.length))
            return 1;
    }
    *static_cast<Address*>(result) = module->dlpi_addr;
    return 1;
}
}

extern "C" JNIEXPORT void JNICALL
Java_org_cocos2dx_lib_AkaineMod73_prepareNative(JNIEnv*, jclass) {
    Address found = 0;
    dl_iterate_phdr(locate_core, &found);
    if (!found) return;
    Address expected = 0;
    if (!base.compare_exchange_strong(expected, found) && expected != found) return;
    owner.store(pthread_self(), std::memory_order_release);
    auto* callbacks = reinterpret_cast<Address*>(base + mailbox);
    __atomic_store_n(callbacks + 2, reinterpret_cast<Address>(&sidebar_loader), __ATOMIC_RELEASE);
    __atomic_store_n(callbacks + 1, reinterpret_cast<Address>(&heading), __ATOMIC_RELEASE);
    __atomic_store_n(callbacks + 0, reinterpret_cast<Address>(&sidebar), __ATOMIC_RELEASE);
}
