#pragma once
#include "character_pins.h"

// Included inside staging_cli after Reader and UiTree. Native callbacks retain
// unlock, special-partner, audio and server persistence behavior.
namespace character_cli {
constexpr Size LIMIT = 512;
struct View {
    Address scene = 0, model = 0, dialog = 0, aside = 0, list = 0;
    Address open_button = 0, open_callback = 0, select_callback = 0;
    Address close_button = 0, close_callback = 0;
    Address characters[LIMIT] = {};
    int ids[LIMIT] = {}, owned_ids[LIMIT] = {};
    Size count = 0, owned_count = 0;
    int equipped_id = -1, preview_id = -1;
    bool available = false, blocked = true;
    const char* reason = "unavailable";
};
inline bool pins() {
    for (const auto& pin : CHARACTER_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
inline bool vector(Reader& h, Address object, Size offset, Size width, Address* begin, Size* count) {
    if (!h.readable(object + offset, 24)) return false;
    const Address first = h.get<Address>(object + offset), end = h.get<Address>(object + offset + 8);
    const Address cap = h.get<Address>(object + offset + 16);
    if (h.fault || end < first || cap < end || (end - first) % width || (cap - first) % width
        || cap - first > LIMIT * width || (end != first && !h.readable(first, end - first))) return false;
    *begin = first; *count = (end - first) / width;
    return true;
}
inline bool character(Reader& h, Address object, int* id, bool allow_sentinel = false) {
    if (!h.readable(object, 0x14) || h.get<Address>(object) != module.base + 0x1b67758) return false;
    *id = h.get<int>(object + 0xc);
    return !h.fault && *id >= (allow_sentinel ? -1 : 0) && *id <= 65535;
}
inline bool owned(const View& view, int id) {
    for (Size i = 0; i < view.owned_count; ++i) if (view.owned_ids[i] == id) return true;
    return false;
}
inline Address find(const View& view, int id) {
    for (Size i = 0; i < view.count; ++i) if (view.ids[i] == id) return view.characters[i];
    return 0;
}
inline bool read_model(Reader& h, View& view) {
    const Address manager = h.get<Address>(module.base + 0x1bf23c0);
    if (!h.readable(manager, 0x80)) return false;
    const Address settings = h.get<Address>(manager + 0x78);
    if (!h.readable(settings, 0x20)) return false;
    view.model = h.get<Address>(settings + 0x18);
    if (!h.readable(view.model, 0x70)) return false;
    Address definitions = 0, ownership = 0;
    if (!vector(h, view.model, 0x18, 8, &definitions, &view.count) || !view.count
        || !vector(h, view.model, 0, 4, &ownership, &view.owned_count)) return false;
    const Address fallback = h.get<Address>(view.model + 0x68);
    for (Size i = 0; i < view.count; ++i) {
        const Address object = h.get<Address>(definitions + i * 8);
        int id = -1;
        if (!character(h, object, &id, true) || (id == -1 && object != fallback)) return false;
        for (Size j = 0; j < i; ++j) if (view.ids[j] == id || view.characters[j] == object) return false;
        view.ids[i] = id; view.characters[i] = object;
    }
    for (Size i = 0; i < view.owned_count; ++i) {
        const int id = h.get<int>(ownership + i * 4);
        if (id < 0 || !find(view, id)) return false;
        for (Size j = 0; j < i; ++j) if (view.owned_ids[j] == id) return false;
        view.owned_ids[i] = id;
    }
    const Address equipped = h.get<Address>(view.model + 0x58);
    if (!character(h, equipped, &view.equipped_id) || find(view, view.equipped_id) != equipped
        || !owned(view, view.equipped_id)) return false;
    return !h.fault;
}
inline bool reachable(Reader& h, const UiTree& tree, Address node) {
    for (Size i = 0; i < tree.inspected; ++i)
        if (tree.queue[i].node == node && tree.queue[i].ancestors_enabled)
            return h.get<unsigned char>(node + 0x1c1) == 1;
    return false;
}
inline bool callback(Reader& h, Address object, Address type, Address owner, Address invoke) {
    Address target = 0;
    return h.readable(object, 16) && h.get<Address>(object) == module.base + type
        && h.get<Address>(object + 8) == owner
        && static_pointer(module.base + type + 0x30, &target) && target == module.base + invoke && !h.fault;
}
inline bool button(Reader& h, Address node) {
    Address release = 0;
    return h.readable(node, 0x449) && h.get<Address>(node) == module.base + 0x1a8ece0
        && h.get<unsigned char>(node + 0x1c0) == 1 && h.get<unsigned char>(node + 0x1c1) == 1
        && h.get<unsigned char>(node + 0x312) == 1 && h.get<unsigned char>(node + 0x314) == 1
        && h.get<unsigned char>(node + 0x448) == 0
        && !h.get<Address>(node + 0x398) && !h.get<Address>(node + 0x3a0) && !h.get<Address>(node + 0x3a8)
        && static_pointer(module.base + 0x1a8ece0 + 0x630, &release) && release == module.base + 0xf66c9c && !h.fault;
}
inline View inspect(Reader& h, Address scene, const UiTree& tree) {
    View result; result.scene = scene;
    if (!tree.valid || !h.readable(scene, sizeof(Address))) { result.reason = "ui_tree"; return result; }
    const Address scene_type = h.get<Address>(scene);
    if (scene_type != module.base + 0x1b2e5a0 && scene_type != module.base + 0x1ad2260) { result.reason = "wrong_scene"; return result; }
    if (!read_model(h, result)) { result.reason = "character_model"; return result; }
    result.available = true; result.blocked = tree.loading;
    Address usercell = 0;
    for (Size i = 0; i < tree.inspected; ++i) {
        const Address node = tree.queue[i].node;
        if (!reachable(h, tree, node)) continue;
        const Address type = h.get<Address>(node);
        if (type == module.base + 0x1b68ea0) {
            if (result.dialog) { result.blocked = true; result.reason = "ambiguous_dialog"; return result; }
            result.dialog = node;
        } else if (type == module.base + 0x1b31908) {
            if (usercell) { result.blocked = true; result.reason = "ambiguous_usercell"; return result; }
            usercell = node;
        }
        char name[240] = {};
        if (!ui_class(type, name)) { result.blocked = true; result.reason = "node_type"; return result; }
        const bool character_dialog = type == module.base + 0x1b68ea0 || type == module.base + 0x1ad8838 || type == module.base + 0x1a83750;
        if (!character_dialog && (strstr(name, "Dialog") || strstr(name, "Overlay") || strstr(name, "Popup")
            || strstr(name, "Loading") || strstr(name, "Transition"))) result.blocked = true;
    }
    if (!result.dialog) {
        if (!result.blocked && h.readable(usercell, 0x631) && h.get<unsigned char>(usercell + 0x630) == 1
            && h.get<unsigned char>(usercell + 0x1c0) == 1) {
            const Address control = h.get<Address>(usercell + 0x4e0);
            if (button(h, control) && h.get<Address>(control + 0x148) == usercell && !h.get<Address>(control + 0x400)) {
                const Address closure = h.get<Address>(control + 0x3d0);
                if (callback(h, closure, 0x1b45d98, usercell, 0x13fa258)) {
                    result.open_button = control; result.open_callback = closure;
                }
            }
        }
        result.reason = result.blocked ? "modal" : result.open_button ? nullptr : "open_control";
        return result;
    }
    if (result.blocked || !h.readable(result.dialog, 0x2f0)
        || h.get<Address>(result.dialog + 0x148) != scene) { result.reason = "modal"; return result; }
    result.aside = h.get<Address>(result.dialog + 0x2d0);
    const Address bside = h.get<Address>(result.dialog + 0x2d8);
    if (!h.readable(result.aside, 0x610) || h.get<Address>(result.aside) != module.base + 0x1ad8838
        || !h.readable(bside, 0x4e0) || h.get<Address>(bside) != module.base + 0x1a83750
        || h.get<Address>(result.aside + 0x148) != result.dialog || h.get<Address>(bside + 0x148) != result.dialog
        || h.get<Address>(result.aside + 0x5c8) != result.dialog || h.get<Address>(bside + 0x4d8) != result.dialog
        || !reachable(h, tree, result.aside)) {
        result.reason = "dialog_owner"; return result;
    }
    const Address preview = h.get<Address>(result.aside + 0x310);
    if (!character(h, preview, &result.preview_id) || find(result, result.preview_id) != preview) { result.reason = "preview"; return result; }
    result.list = h.get<Address>(result.aside + 0x448);
    if (!h.readable(result.list, 0x8f0) || h.get<Address>(result.list) != module.base + 0x1b85ce0
        || h.get<Address>(result.list + 0x148) != result.aside || !reachable(h, tree, result.list)) { result.reason = "list_owner"; return result; }
    const Address selection = h.get<Address>(result.list + 0x8b0);
    if (!callback(h, selection, 0x1b33e60, result.aside, 0x1331f60)) { result.reason = "selection_callback"; return result; }
    result.select_callback = selection;
    const Address close = h.get<Address>(result.aside + 0x3f8);
    if (button(h, close) && reachable(h, tree, close) && h.get<Address>(close + 0x148) == result.aside
        && !h.get<Address>(close + 0x3d0)) {
        const Address closure = h.get<Address>(close + 0x400);
        if (callback(h, closure, 0x1a908d8, result.aside, 0xa90950)) {
            result.close_button = close; result.close_callback = closure;
        }
    }
    result.reason = h.fault ? "read_fault" : nullptr;
    return result;
}
inline void write_state(Json& json, const View& value) {
    json.add("{\"available\":"); json.add(value.available ? "true" : "false");
    json.add(",\"dialog_open\":"); json.add(value.dialog ? "true" : "false");
    json.add(",\"reason\":"); if (value.reason) json.string(value.reason); else json.add("null");
    char number[24];
    json.add(",\"equipped_id\":"); snprintf(number, sizeof(number), "%d", value.equipped_id); json.add(value.available ? number : "null");
    json.add(",\"preview_id\":"); snprintf(number, sizeof(number), "%d", value.preview_id); json.add(value.preview_id >= 0 ? number : "null");
    json.add(",\"can_open\":"); json.add(value.open_button && !value.blocked ? "true" : "false");
    json.add(",\"can_select\":"); json.add(value.select_callback && !value.blocked && !value.reason ? "true" : "false");
    json.add(",\"can_close\":"); json.add(value.close_button && !value.blocked && !value.reason ? "true" : "false");
    json.add(",\"owned_ids\":[");
    if (value.available) for (Size i = 0; i < value.owned_count; ++i) {
        if (i) json.add(",");
        snprintf(number, sizeof(number), "%d", value.owned_ids[i]); json.add(number);
    }
    json.add("]}");
}
inline const char* open(Reader& h, const View& view) {
    if (view.dialog) return nullptr;
    if (!view.available || view.blocked || view.reason || !view.open_button) return "CHARACTER_UNAVAILABLE";
    const Address owner = h.get<Address>(view.open_button + 0x148);
    if (!button(h, view.open_button) || h.get<Address>(view.open_button + 0x3d0) != view.open_callback
        || !callback(h, view.open_callback, 0x1b45d98, owner, 0x13fa258) || !pins()) return "NATIVE_GUARD";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host; host.call<void>(0xf66c9c, view.open_button);
    return host.fault ? "NATIVE_GUARD" : nullptr;
}
inline const char* select(Reader& h, const View& view, int id) {
    if (!view.available || !view.dialog || view.blocked || view.reason || !view.select_callback) return "CHARACTER_UNAVAILABLE";
    if (!owned(view, id) || !find(view, id)) return "CHARACTER_NOT_OWNED";
    View current;
    if (!read_model(h, current) || current.model != view.model || !owned(current, id)
        || find(current, id) != find(view, id) || h.get<Address>(view.list + 0x8b0) != view.select_callback
        || !callback(h, view.select_callback, 0x1b33e60, view.aside, 0x1331f60) || !pins()) return "NATIVE_GUARD";
    int preview_id = -1;
    if (!character(h, h.get<Address>(view.aside + 0x310), &preview_id) || preview_id != view.preview_id) return "NATIVE_GUARD";
    if (view.preview_id == id) return nullptr; // Native repeat selection toggles favorite.
    const Address object = find(view, id);
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host; host.call<void>(0x1331f60, view.select_callback, Address(&object));
    return host.fault ? "NATIVE_GUARD" : nullptr;
}
inline const char* close(Reader& h, const View& view) {
    if (!view.dialog) return nullptr;
    if (!view.available || view.blocked || view.reason || !view.close_button) return "CHARACTER_UNAVAILABLE";
    if (!button(h, view.close_button) || h.get<Address>(view.close_button + 0x400) != view.close_callback
        || !callback(h, view.close_callback, 0x1a908d8, view.aside, 0xa90950) || !pins()) return "NATIVE_GUARD";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host; host.call<void>(0xf66c9c, view.close_button);
    return host.fault ? "NATIVE_GUARD" : nullptr;
}
} // namespace character_cli
