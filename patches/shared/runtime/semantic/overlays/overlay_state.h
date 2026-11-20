#pragma once
#include "overlay_pins.h"
#include "main_hint_pins.h"
#include "notification_hint_pins.h"
#include "note_speed_pins.h"

// Included in staging_cli after Reader. This walker includes hidden descendants;
// display state never substitutes for native listener or workflow state.
namespace overlay_cli {
constexpr Size MAX_ITEMS = 8;
struct Item {
    const char* kind = "tutorial";
    const char* id = "unknown_progression_guide";
    Address node = 0, listener = 0, callback = 0, gate = 0, banner = 0;
    bool active = false, visible = false, blocks_input = false, can_advance = false, advance_ready = false;
    unsigned opacity = 0;
    Size step_index = 0, pending_steps = 0;
    Address set_button = 0, continuation = 0;
    bool can_set_speed = false;
    bool listener_registered = false, listener_paused = false, listener_enabled = false, listener_swallow = false;
    bool owner_validated = false, callback_owned = false;
};
struct View {
    Item items[MAX_ITEMS] = {};
    Size count = 0, inspected = 0, skipped_aliases = 0;
    bool complete = false, blocked = true;
    const char* reason = "unavailable";
};

inline bool pins() {
    for (const auto& pin : CLI_OVERLAY_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    for (const auto& pin : CLI_MAIN_HINT_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    for (const auto& pin : CLI_NOTIFICATION_HINT_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    Address notification_invoke = 0;
    return static_pointer(module.base + 0x1b47628 + 0x30, &notification_invoke)
        && notification_invoke == module.base + 0xbac0a4
        && static_pointer(module.base + 0x1aea110 + 0xa0, &notification_invoke)
        && notification_invoke == module.base + 0x1026cac;
}
inline bool flag(Reader& h, Address at, bool* out) {
    if (!h.readable(at, 1)) return false;
    const unsigned char value = h.get<unsigned char>(at);
    if (value > 1 || h.fault) return false;
    *out = value == 1;
    return true;
}
inline bool exact(Reader& h, Address object, Size size, Address type) {
    return h.readable(object, size) && h.get<Address>(object) == module.base + type && !h.fault;
}
inline bool speed_pins() {
    for (const auto& pin : CLI_NOTE_SPEED_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
inline bool speed_pointer(Address at, Address expected) {
    Address actual = 0;
    return static_pointer(module.base + at, &actual) && actual == module.base + expected;
}
inline bool speed_name(Reader& h, Address node, const char* name) {
    const Size n = strlen(name);
    if (!h.readable(node + 0x160, 24) || n > 22 || h.get<unsigned char>(node + 0x160) != n * 2) return false;
    return !memcmp(reinterpret_cast<const void*>(node + 0x161), name, n + 1);
}
inline bool speed_child(Reader& h, Address node, Address parent) {
    return h.readable(node, 0x1da) && h.get<Address>(node + 0x148) == parent && !h.fault;
}
inline bool speed_listener(Reader& h, Address overlay, Address layer, Item& item) {
    if (!exact(h, overlay, 0x323, 0x1b90800) || !speed_child(h, overlay, layer)) return false;
    item.listener = h.get<Address>(overlay + 0x318);
    if (!exact(h, item.listener, 0x159, 0x1a953c8) || h.get<Address>(item.listener + 0x68) != overlay) return false;
    bool registered = false, paused = false, enabled = false, swallow = false;
    if (!flag(h, item.listener + 0x60, &registered) || !flag(h, item.listener + 0x70, &paused)
        || !flag(h, item.listener + 0x71, &enabled) || !flag(h, item.listener + 0x158, &swallow)) return false;
    const Address began = h.get<Address>(item.listener + 0xa0);
    if (!exact(h, began, 0x20, 0x1adfd70) || h.get<Address>(began + 8) != 0x548
        || h.get<Address>(began + 0x10) != 1 || h.get<Address>(began + 0x18) != overlay) return false;
    item.listener_registered = registered; item.listener_paused = paused;
    item.listener_enabled = enabled; item.listener_swallow = swallow;
    item.blocks_input = registered && !paused && enabled && swallow;
    return !h.fault;
}
inline bool note_speed(Reader& h, Address scene, Address layer, bool ancestors_visible, bool ancestors_running, Item& item) {
    if (!speed_pins() || !exact(h, scene, 0x3b0, 0x1ad2260) || !exact(h, layer, 0x320, 0x1b453b0)
        || !speed_child(h, layer, scene)) return false;
    item.id = "note_speed_setup"; item.node = layer;
    bool running = false, visible = false, closing = false;
    if (!flag(h, layer + 0x1c0, &running) || !flag(h, layer + 0x1c1, &visible)
        || !flag(h, layer + 0x31c, &closing)) return false;
    item.active = ancestors_running && running;
    item.visible = ancestors_visible && visible;
    item.opacity = h.get<unsigned char>(layer + 0x1d0);
    item.step_index = h.get<unsigned>(layer + 0x314);
    if (item.step_index < 10 || item.step_index > 65 || !speed_listener(h, h.get<Address>(layer + 0x2d0), layer, item)) return false;
    const Address root = h.get<Address>(layer + 0x2d8);
    if (!exact(h, root, 0x1da, 0x1b4d3e8) || !speed_child(h, root, layer)) return false;
    bool root_visible = false, root_running = false;
    if (!flag(h, root + 0x1c0, &root_running) || !flag(h, root + 0x1c1, &root_visible)) return false;
    item.visible = item.visible && root_visible;
    item.banner = root;
    const Address vector = h.get<Address>(root + 0x140);
    if (!h.readable(vector, 24)) return false;
    const Address begin = h.get<Address>(vector), end = h.get<Address>(vector + 8), cap = h.get<Address>(vector + 16);
    if (end < begin || cap < end || (end - begin) % 8 || (cap - begin) % 8 || cap - begin > 128 * 8
        || !h.readable(begin, end - begin)) return false;
    for (Address at = begin; at < end; at += 8) {
        const Address child = h.get<Address>(at);
        if (!speed_child(h, child, root)) return false;
        if (!speed_name(h, child, "set_button")) continue;
        if (item.set_button || !exact(h, child, 0x449, 0x1a8ece0)) return false;
        item.set_button = child;
    }
    if (!item.set_button) return false;
    const Address button = item.set_button;
    item.callback = h.get<Address>(button + 0x3d0);
    if (!exact(h, item.callback, 0x40, 0x1b2e030) || h.get<Address>(item.callback + 8) != layer
        || h.get<Address>(item.callback + 0x10) != layer || !speed_pointer(0x1b2e030 + 0x30, 0x107ab4c)
        || !speed_pointer(0x1a8ece0 + 0x630, 0xf66c9c)) return false;
    for (Address offset = 0x18; offset <= 0x38; offset += 8)
        if (!speed_child(h, h.get<Address>(item.callback + offset), root)) return false;
    item.continuation = h.get<Address>(layer + 0x300);
    if (!exact(h, item.continuation, 0x34, 0x1b7f9e0) || h.get<Address>(item.continuation + 8) != scene
        || h.get<Address>(item.continuation + 0x10) != scene || !speed_pointer(0x1b7f9e0 + 0x30, 0x1297db0)) return false;
    bool button_visible = false, button_running = false, enabled = false, touch = false;
    if (!flag(h, button + 0x1c0, &button_running) || !flag(h, button + 0x1c1, &button_visible)
        || !flag(h, button + 0x312, &enabled) || !flag(h, button + 0x314, &touch)) return false;
    const bool no_competing = !h.get<Address>(button + 0x398) && !h.get<Address>(button + 0x3a0)
        && !h.get<Address>(button + 0x3a8) && !h.get<Address>(button + 0x400) && h.get<unsigned char>(button + 0x448) == 0;
    item.owner_validated = true; item.callback_owned = true;
    item.can_set_speed = item.active && item.visible && root_running && !closing && item.blocks_input && button_running && button_visible
        && enabled && touch && no_competing && h.get<unsigned>(layer + 0x310) == 0
        && h.get<Address>(item.continuation + 0x28) == 0 && h.get<unsigned>(item.continuation + 0x30) == 0;
    return !h.fault;
}
inline bool progression(Reader& h, Address scene, Address guide, bool ancestors_visible, bool ancestors_running, Item& item) {
    if (!exact(h, guide, 0x380, 0x1b20180)) return false;
    item.node = guide;
    bool running = false, visible = false;
    if (!flag(h, guide + 0x1c0, &running) || !flag(h, guide + 0x1c1, &visible)
        || !flag(h, guide + 0x338, &item.advance_ready)) return false;
    item.active = ancestors_running && running;
    item.step_index = h.get<Size>(guide + 0x370);
    item.pending_steps = h.get<Size>(guide + 0x378);
    if (item.step_index > 4096 || item.pending_steps > 128) return false;
    item.gate = h.get<Address>(guide + 0x318);
    if (item.gate && !h.readable(item.gate, 0x1da)) return false;
    const Address done = h.get<Address>(guide + 0x2f0);
    const bool pack_hint = exact(h, scene, 0x390, 0x1ad2260)
        && h.get<Address>(guide + 0x148) == scene
        && exact(h, done, 0x10, 0x1b665d8) && h.get<Address>(done + 8) == scene;
    const bool main_hint = exact(h, scene, 0x390, 0x1b2e5a0)
        && h.get<Address>(guide + 0x148) == scene
        && exact(h, done, 0x10, 0x1b153d8) && h.get<Address>(done + 8) == scene;
    const bool notification_hint = exact(h, scene, 0x390, 0x1b2e5a0)
        && h.get<Address>(guide + 0x148) == scene
        && exact(h, done, 0x10, 0x1b47628) && h.get<Address>(done + 8) == scene;
    if (pack_hint) item.id = "pack_selection_hint";
    else if (main_hint) item.id = "main_menu_hint";
    else if (notification_hint) item.id = "notification_permission_guide";
    item.banner = h.get<Address>(guide + 0x348);
    if (!exact(h, item.banner, 0x1da, 0x1aa0128)
        || h.get<Address>(item.banner + 0x148) != guide) return false;
    bool banner_visible = false;
    if (!flag(h, item.banner + 0x1c1, &banner_visible)) return false;
    item.visible = ancestors_visible && visible && banner_visible;
    item.opacity = h.get<unsigned char>(item.banner + 0x1d0);

    const Address overlay = h.get<Address>(guide + 0x340);
    if (!exact(h, overlay, 0x323, 0x1b90800) || h.get<Address>(overlay + 0x148) != guide) return false;
    bool overlay_running = false;
    if (!flag(h, overlay + 0x1c0, &overlay_running)) return false;
    item.listener = h.get<Address>(overlay + 0x318);
    if (!exact(h, item.listener, 0x159, 0x1a953c8)
        || h.get<Address>(item.listener + 0x68) != overlay) return false;
    bool registered = false, paused = false, enabled = false, swallow = false;
    if (!flag(h, item.listener + 0x60, &registered) || !flag(h, item.listener + 0x70, &paused)
        || !flag(h, item.listener + 0x71, &enabled) || !flag(h, item.listener + 0x158, &swallow)) return false;
    const Address began = h.get<Address>(item.listener + 0xa0);
    if (!exact(h, began, 0x20, 0x1adfd70) || h.get<Address>(began + 8) != 0x548
        || h.get<Address>(began + 0x10) != 1 || h.get<Address>(began + 0x18) != overlay) return false;
    // TouchDisableLayer::onTouchBegan returns true regardless of node opacity or
    // visibility. Registered swallowing listeners can block invisible banners.
    item.blocks_input = registered && !paused && enabled && swallow;
    item.callback = h.get<Address>(overlay + 0x2f0);
    const bool callback_owned = exact(h, item.callback, 0x18, 0x1b1c1e8)
        && h.get<Address>(item.callback + 8) == guide && h.get<Address>(item.callback + 0x10) == guide;
    item.owner_validated = pack_hint || main_hint || notification_hint;
    item.callback_owned = callback_owned;
    item.listener_registered = registered; item.listener_paused = paused;
    item.listener_enabled = enabled; item.listener_swallow = swallow;
    item.can_advance = (pack_hint || main_hint || notification_hint) && item.active && item.advance_ready && item.blocks_input && callback_owned;
    return !h.fault;
}

inline View capture(Reader& h, Address scene, const char* klass) {
    View out;
    if (!klass || !scene || !pins()) { out.reason = "pin_mismatch_or_unavailable"; return out; }
    constexpr Size LIMIT = 1024;
    struct Entry { Address node, parent; bool visible, running; } queue[LIMIT] = {};
    queue[0] = {scene, 0, true, true};
    Size queued = 1, cursor = 0;
    while (cursor < queued) {
        const Entry current = queue[cursor++];
        for (Size i = 0; i + 1 < cursor; ++i) if (queue[i].node == current.node) {
            out.reason = "duplicate_node"; return out;
        }
        ++out.inspected;
        if (!h.readable(current.node, 0x1da)) { out.reason = "node_bounds"; return out; }
        const Address type = h.get<Address>(current.node);
        if (!module_readable(type, sizeof(Address))) { out.reason = "node_type"; return out; }
        if (current.parent && h.get<Address>(current.node + 0x148) != current.parent) {
            const Address actual = h.get<Address>(current.node + 0x148);
            // Preserve the already-proven UserCell renderer alias. It cannot
            // contain a guide and never supplies a continuation action.
            if (type == module.base + 0x1a8ece0 && h.readable(current.parent, 0x150)
                && h.get<Address>(current.parent) == module.base + 0x1b4d3e8
                && h.get<Address>(current.parent + 0x148) == actual
                && exact(h, actual, 0x1da, 0x1b31908)) { ++out.skipped_aliases; continue; }
            out.reason = "parent_link"; return out;
        }
        bool visible = false, running = false;
        if (!flag(h, current.node + 0x1c0, &running) || !flag(h, current.node + 0x1c1, &visible)) {
            out.reason = "node_flags"; return out;
        }
        if (type == module.base + 0x1b20180 || type == module.base + 0x1b453b0) {
            if (out.count == MAX_ITEMS) { out.reason = "overlay_limit"; return out; }
            Item item;
            if (!(type == module.base + 0x1b453b0
                    ? note_speed(h, scene, current.node, current.visible, current.running, item)
                    : progression(h, scene, current.node, current.visible, current.running, item))) {
                out.reason = "guide_contract"; return out;
            }
            for (Size i = 0; i < out.count; ++i) if (!strcmp(out.items[i].id, item.id)) {
                out.reason = "ambiguous_guide"; return out;
            }
            out.items[out.count++] = item;
        }
        const Address vector = h.get<Address>(current.node + 0x140);
        if (!vector) continue;
        if (!h.readable(vector, 24)) { out.reason = "children_bounds"; return out; }
        const Address begin = h.get<Address>(vector), end = h.get<Address>(vector + 8), cap = h.get<Address>(vector + 16);
        if (end < begin || cap < end || (end - begin) % 8 || (cap - begin) % 8 || cap - begin > 65536
            || end - begin > (LIMIT - queued) * 8 || (end != begin && !h.readable(begin, end - begin))) {
            out.reason = "children_shape_or_limit"; return out;
        }
        for (Address at = begin; at < end; at += 8)
            queue[queued++] = {h.get<Address>(at), current.node, current.visible && visible, current.running && running};
        if (h.fault) { out.reason = "read_fault"; return out; }
    }
    out.complete = true; out.reason = nullptr; out.blocked = false;
    for (Size i = 0; i < out.count; ++i) if (out.items[i].active || out.items[i].blocks_input) out.blocked = true;
    return out;
}

inline bool can_advance(const View& view) {
    return view.complete && view.count == 1 && view.items[0].can_advance;
}
inline bool has_note_speed(const View& view) {
    if (!view.complete) return false;
    for (Size i = 0; i < view.count; ++i)
        if (!strcmp(view.items[i].id, "note_speed_setup")) return true;
    return false;
}
inline const char* set_note_speed(Reader& h, Address scene, Address song, unsigned difficulty, const View& expected) {
    if (!official_thread() || !speed_pins()) return "NATIVE_GUARD";
    const View fresh = capture(h, scene, "15SongSelectScene");
    if (!expected.complete || expected.count != 1 || !fresh.complete || fresh.count != 1) return "NOTE_SPEED_UNAVAILABLE";
    const Item& old = expected.items[0]; const Item& item = fresh.items[0];
    if (strcmp(item.id, "note_speed_setup") || !old.can_set_speed || !item.can_set_speed) return "NOTE_SPEED_UNAVAILABLE";
    if (old.node != item.node || old.listener != item.listener || old.callback != item.callback
        || old.set_button != item.set_button || old.continuation != item.continuation || old.step_index != item.step_index)
        return "STALE_UI_CONTEXT";
    if (h.get<Address>(item.continuation + 0x18) != song || h.get<unsigned>(item.continuation + 0x20) != difficulty || h.fault)
        return "SELECTION_CHANGED";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost call;
    call.call<void>(0xf66c9c, item.set_button);
    return call.fault ? "NATIVE_GUARD" : nullptr;
}
inline const char* advance(Reader& h, Address scene, const View& expected) {
    if (!official_thread()) return "NATIVE_GUARD";
    const View fresh = capture(h, scene, "known_guide");
    if (!can_advance(expected) || !can_advance(fresh)) return "TUTORIAL_UNAVAILABLE";
    const Item& old = expected.items[0]; const Item& item = fresh.items[0];
    if (old.node != item.node || old.listener != item.listener || old.callback != item.callback
        || old.step_index != item.step_index || old.pending_steps != item.pending_steps) return "STALE_UI_CONTEXT";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost call;
    // Invoke the actual registered closure. Its pinned body ignores Ref/Event
    // parameters and advances the captured guide through its ordinary gates.
    call.call<void>(0x1934b7c, item.callback);
    return call.fault ? "NATIVE_GUARD" : nullptr;
}
inline void number(Json& json, Size value) {
    char text[32]; snprintf(text, sizeof(text), "%llu", static_cast<unsigned long long>(value)); json.add(text);
}
inline void write_fields(Json& json, const View& view) {
    json.add(",\"overlays\":[");
    for (Size i = 0; i < view.count; ++i) {
        if (i) json.add(",");
        const Item& item = view.items[i];
        json.add("{\"kind\":\"tutorial\",\"id\":"); json.string(item.id);
        json.add(",\"active\":"); json.add(item.active ? "true" : "false");
        json.add(",\"visible\":"); json.add(item.visible ? "true" : "false");
        json.add(",\"opacity\":"); number(json, item.opacity);
        json.add(",\"blocks_input\":"); json.add(item.blocks_input ? "true" : "false");
        json.add(",\"step_index\":"); number(json, item.step_index);
        json.add(",\"pending_steps\":"); number(json, item.pending_steps);
        json.add(",\"advance_ready\":"); json.add(item.advance_ready ? "true" : "false");
        json.add(",\"can_advance\":"); json.add(item.can_advance ? "true" : "false");
        json.add(",\"can_set_speed\":"); json.add(item.can_set_speed ? "true" : "false");
        json.add(",\"owner_validated\":"); json.add(item.owner_validated ? "true" : "false");
        json.add(",\"callback_owned\":"); json.add(item.callback_owned ? "true" : "false");
        json.add(",\"listener_registered\":"); json.add(item.listener_registered ? "true" : "false");
        json.add(",\"listener_paused\":"); json.add(item.listener_paused ? "true" : "false");
        json.add(",\"listener_enabled\":"); json.add(item.listener_enabled ? "true" : "false");
        json.add(",\"listener_swallow\":"); json.add(item.listener_swallow ? "true" : "false");
        json.add("}");
    }
    json.add("],\"overlay_coverage\":[\"progression_guide\",\"note_speed_setup\"],\"overlay_scan_complete\":"); json.add(view.complete ? "true" : "false");
    json.add(",\"overlay_scan_reason\":"); if (view.reason) json.string(view.reason); else json.add("null");
}
}
