#pragma once

// Runs only through the existing verified monitor on its owning GL thread.
// All strings below use the inspected native libc++ 24-byte string contract.
struct alignas(8) ModString { unsigned char bytes[24] = {}; };
static_assert(sizeof(ModString) == 24);

static ModString mod_short_string(const char* text) {
    ModString value;
    const Size size = strlen(text);
    if (size <= 22) {
        value.bytes[0] = static_cast<unsigned char>(size * 2);
        memcpy(value.bytes + 1, text, size + 1);
    }
    return value;
}

static bool mod_string_equals(OfficialHost& h, Address object, const char* expected) {
    const unsigned char tag = h.get<unsigned char>(object);
    const Size size = tag & 1 ? h.get<Size>(object + 8) : Size(tag >> 1);
    const Address data = tag & 1 ? h.get<Address>(object + 16) : object + 1;
    if (h.fault || size != strlen(expected)) return false;
    if (sampler_probe_enabled && sampler_probe::mod_read_active) {
        char local[64] = {};
        if (size > sizeof(local) || !sampler_probe::copy(data, local, size)) { h.fault = true; return false; }
        return memcmp(local, expected, size) == 0;
    }
    return process_readable(data, size) && memcmp(reinterpret_cast<const void*>(data), expected, size) == 0;
}

static void mod_destroy_string(OfficialHost& h, ModString& text) {
    if (text.bytes[0] & 1) {
        Address data = 0;
        memcpy(&data, text.bytes + 16, sizeof(data));
        h.call<void>(0x1a6d9e0, data);
    }
}

static bool mod_add_button(OfficialHost& h, Address scene) {
    ModString name = mod_short_string("button6");
    Address parent = 0;
    const Address slot = h.call<Address>(0xb0d8f8, scene + 0x3b8,
        Address(&parent), Address(&name));
    if (h.fault || !process_readable(slot, sizeof(Address), true)) return false;
    Address node = h.get<Address>(slot);
    if (node) return h.get<uint32_t>(node + 0x38) == 8;
    node = h.call<Address>(0x1a6d9c0, Address(0x40));
    if (!node || !process_readable(node, 0x40, true)) return false;
    memset(reinterpret_cast<void*>(node), 0, 0x40);
    h.put<Address>(node + 0x10, parent);
    h.call<void>(0x1a6da50, node + 0x20, Address(&name));
    h.put<uint32_t>(node + 0x38, 8);
    if (h.fault) return false;
    h.put<Address>(slot, node);
    const Address begin = h.get<Address>(scene + 0x3b8);
    const Address first = h.get<Address>(begin);
    if (first) h.put<Address>(scene + 0x3b8, first);
    h.call<void>(0x1257490, h.get<Address>(scene + 0x3c0), node);
    h.put<Size>(scene + 0x3c8, h.get<Size>(scene + 0x3c8) + 1);
    return !h.fault;
}

#include "mod_scroll_stops.h"
#include "mod_widget_bounds.h"

static void mod_sidebar(Address scene) {
    sampler_probe::ModReadScope read_scope;
    OfficialHost h;
    bool projected = false, registered = false;
    if (official_thread() && process_readable(scene, 0x440, true)) {
        const Address context_slot = h.get<Address>(module.base + 0x1b95f58);
        const Address context = h.get<Address>(context_slot);
        const Address manager = h.get<Address>(context + 0x20);
        ModString id = mod_short_string("xd_fan_album");
        const Address pack = manager && process_readable(manager, 0x90)
            ? h.call<Address>(0x193b304, manager, Address(&id)) : 0;
        if (pack && process_readable(pack, 0xc8, true)
            && mod_string_equals(h, pack + 8, "xd_fan_album")) {
            const uint32_t section = h.get<uint32_t>(pack + 0xc4);
            if ((section == 7 || section == 8) && mod_add_scroll_stop(h, scene)) {
                h.put<uint32_t>(pack + 0xc4, 8);
                projected = !h.fault;
            }
        }
        if (projected && mod_add_button(h, scene)) {
            h.call<Address>(0x13d91cc, scene, uint32_t(8));
            registered = !h.fault;
        }
    }
    __android_log_print(registered ? ANDROID_LOG_INFO : ANDROID_LOG_ERROR, TAG,
        "mod_category_sidebar pack_id=xd_fan_album section=8 projected=%d registered=%d owner_gl_thread=%d scroll_stop_count=%zu last_stop=%.0f",
        projected, registered, official_thread(),
        (h.get<Address>(scene + 0x2f0) - h.get<Address>(scene + 0x2e8)) / sizeof(float),
        double(h.get<float>(h.get<Address>(scene + 0x2f0) - sizeof(float))));
    // Preserve the original sidebar initialization and callback ownership.
    OfficialHost original;
    original.call<void>(0x1402a28, scene);
    if (registered) {
        OfficialHost bounds;
        const bool extended = mod_extend_widget_bound(bounds, scene);
        __android_log_print(extended ? ANDROID_LOG_INFO : ANDROID_LOG_ERROR, TAG,
            "mod_category_scroll_bound section=8 max_stop=55 committed=%d owner_gl_thread=%d",
            extended, official_thread());
    }
}

#include "mod_divider_alignment.h"

static Address mod_heading(Address original_argument, uint32_t section) {
    sampler_probe::ModReadScope read_scope;
    if (section != 8 || !official_thread()) {
        OfficialHost original;
        return original.call<Address>(0xc3a6e0, original_argument, section);
    }
    OfficialHost h;
    const Address node = h.call<Address>(0xc3a6e0, original_argument, uint32_t(7));
    ModString path;
    h.call<void>(0x1a6dba0, Address(&path), "layouts/songselect/ModDividerNativeFrame.csb");
    const Address content = h.call<Address>(0x95af50, Address(&path));
    mod_destroy_string(h, path);
    const ModDividerPoint anchor_before = content ? h.get<ModDividerPoint>(content + 0x54) : ModDividerPoint{};
    const bool aligned = mod_align_divider(h, node, content);
    if (!aligned) h.fault = true;
    __android_log_print(node && !h.fault ? ANDROID_LOG_INFO : ANDROID_LOG_ERROR, TAG,
        "mod_category_heading section=8 resource=ModDividerNativeFrame native_box=1 ready=%d owner_gl_thread=1 anchor_before=%.3f,%.3f",
        node && !h.fault, double(anchor_before.x), double(anchor_before.y));
    return node;
}

static bool initialize_mod_bridge() {
    if (!official_thread() || toggle_mailbox->reserved || toggle_mailbox->reserved_tail) return false;
    toggle_mailbox->reserved = Address(&mod_sidebar);
    toggle_mailbox->reserved_tail = Address(&mod_heading);
    __android_log_print(ANDROID_LOG_INFO, TAG,
        "mod_category_bridge status=ready section=8 pack_id=xd_fan_album owner_gl_thread=1");
    return true;
}
