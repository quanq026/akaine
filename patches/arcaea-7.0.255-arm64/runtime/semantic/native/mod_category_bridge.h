#pragma once
// Mod category controls, scrolling bounds and divider placement.

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


static bool mod_add_scroll_stop(OfficialHost& h, Address scene) {
    const Address begin = h.get<Address>(scene + 0x2e8);
    const Address end = h.get<Address>(scene + 0x2f0);
    const Address capacity = h.get<Address>(scene + 0x2f8);
    if (h.fault || end < begin || capacity < end || (end - begin) % sizeof(float)
        || (capacity - begin) % sizeof(float)) return false;
    const Size count = (end - begin) / sizeof(float);
    if ((count != 5 && count != 6) || capacity - begin > 4096
        || !process_readable(begin, end - begin)) return false;
    constexpr float expected[] = {-2395, -1905, -1415, -925, -435, 55};
    for (Size i = 0; i < count; ++i)
        if (h.get<float>(begin + i * sizeof(float)) != expected[i]) return false;
    if (h.fault || count == 6) return !h.fault;
    if (capacity - end >= sizeof(float)) {
        h.put<float>(end, expected[5]);
        h.put<Address>(scene + 0x2f0, end + sizeof(float));
        return !h.fault;
    }
    // Use the same allocator/delete pair as the native vector-growth path.
    const Size bytes = 10 * sizeof(float);
    const Address replacement = h.call<Address>(0x1a6d9c0, Address(bytes));
    if (!replacement || !process_readable(replacement, bytes, true)) return false;
    memcpy(reinterpret_cast<void*>(replacement), reinterpret_cast<const void*>(begin), end - begin);
    h.put<float>(replacement + count * sizeof(float), expected[5]);
    if (h.fault) return false;
    h.put<Address>(scene + 0x2e8, replacement);
    h.put<Address>(scene + 0x2f0, replacement + 6 * sizeof(float));
    h.put<Address>(scene + 0x2f8, replacement + bytes);
    if (!h.fault) h.call<void>(0x1a6d9e0, begin);
    return !h.fault;
}

static bool mod_extend_widget_bound(OfficialHost& h, Address scene) {
    const Address widget = h.get<Address>(scene + 0x338);
    if (h.fault || !process_readable(widget, 0x870, true)
        || h.get<Address>(widget) != module.base + 0x1b13b50) return false;
    const float maximum = h.get<float>(widget + 0x758);
    if (h.fault || (maximum != 0.0f && maximum != 55.0f)) return false;
    h.put<float>(widget + 0x758, 55.0f);
    h.put<unsigned char>(widget + 0x7e8, 1);
    return !h.fault;
}

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


struct ModDividerPoint { float x, y; };

static bool mod_align_divider(OfficialHost& h, Address node, Address content) {
    const Address base = module.base;
    if (!node || !content || h.get<Address>(node) != base + 0x1b0d7b0
        || h.get<Address>(content) != base + 0x1b4d3e8) return false;
    const Address children = h.get<Address>(node + 0x140);
    const Address begin = h.get<Address>(children);
    const Address end = h.get<Address>(children + 8);
    if (h.fault || !begin || end != begin + sizeof(Address)) return false;
    const Address sprite = h.get<Address>(begin);
    if (h.get<Address>(sprite) != base + 0x1aa0128) return false;
    const ModDividerPoint size = h.get<ModDividerPoint>(sprite + 0x5c);
    const ModDividerPoint position = h.get<ModDividerPoint>(sprite + 0x38);
    const ModDividerPoint anchor = h.get<ModDividerPoint>(content + 0x54);
    const ModDividerPoint content_size = h.get<ModDividerPoint>(content + 0x5c);
    const float scale = size.y / 457.0f;
    if (h.fault || !(scale > 0.1f && scale < 8.0f)
        || __builtin_fabsf(size.x / 110.0f - scale) > 0.001f
        || !((anchor.x == 0.0f && anchor.y == 0.0f)
             || (anchor.x == 0.5f && anchor.y == 0.5f))
        || content_size.x != 110.0f || content_size.y != 457.0f) return false;
    // This NodeReader skips the setter for CSB's default (.5,.5), leaving Node at (0,0).
    const ModDividerPoint centered = {0.5f, 0.5f};
    h.call<void>(0xec4b3c, content, Address(&centered));
    // Preserve the native box/anchor and its renderer-dependent sprite geometry.
    h.call<void>(0x134d7a4, sprite, false);
    if (h.get<unsigned char>(sprite + 0x1c1) != 0 || h.fault) return false;
    h.call<void>(0x18372e8, content, scale);
    h.call<void>(0xd8cbe8, content, Address(&position));
    h.call<void>(0xefd848, node, content);
    return !h.fault;
}

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
