#pragma once
#include "settings_panel_pins.h"
#include "highfps_pins.h"

// Included inside staging_cli after character and read-only settings controls.
namespace settings_panel_cli {
struct Control { Address node = 0, setter = 0, getter = 0; int current = 0; };
struct FpsControl { Address node = 0, setter = 0, getter = 0, button = 0, button_callback = 0; int current = -1; };
struct View {
    Address scene = 0, topbar = 0, panel = 0, open_button = 0, open_callback = 0;
    Address close_button = 0, close_callback = 0, delegate_type = 0, delegate_invoke = 0;
    Control note_speed, offset;
    FpsControl high_framerate;
    bool available = false, blocked = true;
    const char* reason = "wrong_scene";
};
inline bool pins() {
    for (const auto& pin : SETTINGS_PANEL_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    for (const auto& pin : HIGHFPS_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
inline bool reaches(Reader& h, Address child, Address parent) {
    Address seen[16] = {};
    for (Size i = 0; i < 16 && child; ++i) {
        if (child == parent) return true;
        if (!h.readable(child, 0x150)) return false;
        for (Size j = 0; j < i; ++j) if (seen[j] == child) return false;
        seen[i] = child; child = h.get<Address>(child + 0x148);
    }
    return false;
}
inline bool callback(Reader& h, Address closure, Address type, Address owner, Address invoke) {
    return character_cli::callback(h, closure, type, owner, invoke);
}
inline bool note_volume(Reader& h, Address setter, Address panel) {
    if (!h.readable(setter, 0x18)) return false;
    const Address volume = h.get<Address>(setter + 0x10);
    Address invoke = 0;
    if (!h.readable(volume, 0x5e8) || h.get<Address>(volume) != module.base + 0x1af1098
        || h.get<unsigned char>(volume + 0x1c0) != 1 || h.get<unsigned char>(volume + 0x1c1) != 1
        || h.get<unsigned char>(volume + 0x312) != 1 || h.get<unsigned char>(volume + 0x4b3)
        || !reaches(h, volume, panel) || h.get<int>(volume + 0x5a4) != 10
        || h.get<int>(volume + 0x5a8) != 0 || h.get<int>(volume + 0x5ac) != 200
        || h.get<uint16_t>(volume + 0x5b0) != 0x2502 || h.get<unsigned char>(volume + 0x5b2)
        || !static_pointer(module.base + 0x1af1098 + 0x660, &invoke) || invoke != module.base + 0xd7760c
        || !callback(h, h.get<Address>(volume + 0x590), 0x1b15968, panel, 0x17cc574)
        || !callback(h, h.get<Address>(volume + 0x560), 0x1b93558, panel, 0x8f1c9c)) return false;
    for (Size field = 0x5c8; field <= 0x5e0; field += 8) {
        const bool button = field == 0x5d0 || field == 0x5d8;
        const Address child = h.get<Address>(volume + field), type = button ? 0x1a8ece0 : 0x1adae68;
        if (!h.readable(child, 0x1c2) || h.get<Address>(child) != module.base + type
            || h.get<Address>(child + 0x148) != volume
            || !static_pointer(module.base + type + (button ? 0x558 : 0x560), &invoke)
            || invoke != module.base + (button ? 0x1556400 : 0x15556c8)) return false;
    }
    // Native refresh disables volume buttons when abs(offset) exceeds 100ms; allow recovery.
    return !h.fault;
}
inline bool control(Reader& h, Address node, Address panel, bool offset, Control& out) {
    const Address type = offset ? 0x1ad4218 : 0x1a93cf0;
    if (!h.readable(node, 0x5d0) || h.get<Address>(node) != module.base + type
        || h.get<unsigned char>(node + 0x1c0) != 1 || h.get<unsigned char>(node + 0x1c1) != 1
        || h.get<unsigned char>(node + 0x312) != 1 || h.get<unsigned char>(node + 0x4b3)
        || !reaches(h, node, panel)) return false;
    if (h.get<int>(node + 0x5a4) != 1 || h.get<int>(node + 0x5a8) != 10
        || h.get<int>(node + 0x5ac) != (offset ? -2000 : 10) || h.get<int>(node + 0x5b0) != (offset ? 2000 : 65)) return false;
    const Address setter = h.get<Address>(node + 0x560), getter = h.get<Address>(node + 0x590);
    if (!callback(h, setter, offset ? 0x1a9a6b0 : 0x1acf688, panel, offset ? 0x1646cf0 : 0xf638a0)
        || !callback(h, getter, offset ? 0x1b418a8 : 0x1b7d928, panel, offset ? 0xcd0fb8 : 0xd762e0)) return false;
    if (offset && !note_volume(h, setter, panel)) return false;
    const int value = h.get<int>(node + 0x5a0);
    if (h.fault || value < (offset ? -2000 : 10) || value > (offset ? 2000 : 65)) return false;
    out = {node, setter, getter, value}; return true;
}
inline bool fps_control(Reader& h, Address node, Address panel, FpsControl& out) {
    if (!h.readable(node, 0x5e0) || h.get<Address>(node) != module.base + 0x1b4b118
        || h.get<unsigned char>(node + 0x1c0) != 1 || h.get<unsigned char>(node + 0x1c1) != 1
        || h.get<unsigned char>(node + 0x312) != 1 || h.get<unsigned char>(node + 0x4b3)
        || !reaches(h, node, panel)) return false;
    const Address setter = h.get<Address>(node + 0x550), getter = h.get<Address>(node + 0x580);
    const Address begin = h.get<Address>(node + 0x598), end = h.get<Address>(node + 0x5a0), capacity = h.get<Address>(node + 0x5a8);
    const int current = h.get<int>(node + 0x590);
    if (!begin || end < begin || end - begin != 48 || capacity < end || capacity - begin > 4096
        || !h.readable(begin, 48) || current < 0 || current > 1
        || !callback(h, setter, 0x1b44d60, panel, 0x8b02a4)
        || !callback(h, getter, 0x1a93a38, panel, 0x14bd6cc)) return false;
    const Address button = h.get<Address>(node + 0x5c8);
    if (!character_cli::button(h, button)) return false;
    const Address closure = h.get<Address>(button + 0x400);
    if (!reaches(h, button, node) || h.get<Address>(button + 0x3d0)
        || !callback(h, closure, 0x1accb80, node, 0xa39168)) return false;
    out = {node, setter, getter, button, closure, current};
    return !h.fault;
}
inline View inspect(Reader& h, Address scene, const UiTree& tree) {
    View result; result.scene = scene;
    if (!tree.valid || tree.loading || !h.readable(scene, 0x300)) { result.reason = "ui_tree"; return result; }
    const Address type = h.get<Address>(scene);
    if (type == module.base + 0x1ad2260) { result.delegate_type = 0x1ad2898; result.delegate_invoke = 0x145778c; }
    else if (type == module.base + 0x1b2e5a0) { result.delegate_type = 0x1b2eb38; result.delegate_invoke = 0xd80924; }
    else return result;
    Address invoke = 0;
    if (h.get<Address>(scene + 0x2e8) != module.base + result.delegate_type
        || !static_pointer(module.base + result.delegate_type, &invoke) || invoke != module.base + result.delegate_invoke) {
        result.reason = "settings_delegate"; return result;
    }
    result.available = true; result.blocked = false;
    for (Size i = 0; i < tree.inspected; ++i) {
        const Address node = tree.queue[i].node;
        if (!tree.queue[i].ancestors_enabled || h.get<unsigned char>(node + 0x1c1) != 1) continue;
        const Address vt = h.get<Address>(node);
        if (vt == module.base + 0x1ac3640) {
            if (result.panel) { result.reason = "ambiguous_panel"; result.blocked = true; return result; }
            result.panel = node;
        } else if (vt == module.base + 0x1a94648 && h.get<Address>(node + 0x148) == scene) {
            if (result.topbar) { result.reason = "ambiguous_topbar"; result.blocked = true; return result; }
            result.topbar = node;
        }
        char klass[240] = {};
        if (!ui_class(vt, klass)) { result.reason = "node_type"; result.blocked = true; return result; }
        if (vt != module.base + 0x1ac3640 && (strstr(klass, "Dialog") || strstr(klass, "Overlay")
            || strstr(klass, "Popup") || strstr(klass, "Loading") || strstr(klass, "Transition"))) result.blocked = true;
    }
    if (result.blocked) { result.reason = "modal"; return result; }
    if (!result.panel) {
        if (!h.readable(result.topbar, 0x2c8) || h.get<Address>(result.topbar + 0x2c0) != scene + 0x2e8) {
            result.reason = "topbar_delegate"; return result;
        }
        for (Size i = 0; i < tree.inspected; ++i) {
            const Address node = tree.queue[i].node;
            if (!tree.queue[i].ancestors_enabled || !character_cli::button(h, node)
                || !reaches(h, node, result.topbar) || h.get<Address>(node + 0x400)) continue;
            const Address closure = h.get<Address>(node + 0x3d0);
            if (!callback(h, closure, 0x1b852e8, result.topbar, 0x1581e18)) continue;
            if (result.open_button) { result.reason = "ambiguous_open"; result.blocked = true; return result; }
            result.open_button = node; result.open_callback = closure;
        }
        result.reason = result.open_button ? nullptr : "settings_button";
        return result;
    }
    if (!h.readable(result.panel, 0x330) || h.get<Address>(result.panel + 0x148) != scene
        || h.get<Address>(result.panel + 0x328) != scene + 0x2f8) { result.reason = "panel_owner"; return result; }
    const Address close = h.get<Address>(result.panel + 0x2c8);
    if (character_cli::button(h, close) && reaches(h, close, result.panel) && !h.get<Address>(close + 0x3d0)) {
        const Address wrapper = h.get<Address>(close + 0x400);
        if (h.readable(wrapper, 0x48) && h.get<Address>(wrapper) == module.base + 0x1b73478
            && h.get<Address>(wrapper + 0x10) == result.panel) {
            const Address inner = h.get<Address>(wrapper + 0x40);
            if (callback(h, inner, 0x1b3f6a8, scene + 0x2f8, 0x1620450)) {
                result.close_button = close; result.close_callback = wrapper;
            }
        }
    }
    for (Size i = 0; i < tree.inspected; ++i) {
        if (!tree.queue[i].ancestors_enabled) continue;
        const Address node = tree.queue[i].node, vt = h.get<Address>(node);
        if (vt == module.base + 0x1b4b118) {
            FpsControl candidate;
            if (fps_control(h, node, result.panel, candidate)) {
                if (result.high_framerate.node) { result.reason = "ambiguous_fps"; result.blocked = true; return result; }
                result.high_framerate = candidate;
            }
            continue;
        }
        const bool offset = vt == module.base + 0x1ad4218;
        if (!offset && vt != module.base + 0x1a93cf0) continue;
        Control candidate;
        if (!control(h, node, result.panel, offset, candidate)) continue;
        Control& destination = offset ? result.offset : result.note_speed;
        if (destination.node) { result.reason = "ambiguous_setting"; result.blocked = true; return result; }
        destination = candidate;
    }
    result.reason = h.fault ? "read_fault" : nullptr;
    return result;
}
inline const char* open(Reader& h, const View& view) {
    if (view.panel) return nullptr;
    if (!view.available || view.blocked || view.reason || !view.open_button) return "SETTINGS_UNAVAILABLE";
    if (h.get<Address>(view.topbar + 0x2c0) != view.scene + 0x2e8
        || h.get<Address>(view.scene + 0x2e8) != module.base + view.delegate_type
        || !character_cli::button(h, view.open_button) || !reaches(h, view.open_button, view.topbar)
        || h.get<Address>(view.open_button + 0x3d0) != view.open_callback || h.get<Address>(view.open_button + 0x400)
        || !callback(h, view.open_callback, 0x1b852e8, view.topbar, 0x1581e18)
        || !pins() || !character_cli::pins() || h.fault) return "NATIVE_GUARD";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host; host.call<void>(0xf66c9c, view.open_button);
    return host.fault ? "NATIVE_GUARD" : nullptr;
}
inline const char* close(Reader& h, const View& view) {
    if (!view.panel) return nullptr;
    if (!view.available || view.blocked || view.reason || !view.close_button) return "SETTINGS_UNAVAILABLE";
    if (!character_cli::button(h, view.close_button) || h.get<Address>(view.close_button + 0x400) != view.close_callback
        || h.get<Address>(view.close_callback) != module.base + 0x1b73478
        || h.get<Address>(view.close_callback + 0x10) != view.panel
        || !callback(h, h.get<Address>(view.close_callback + 0x40), 0x1b3f6a8, view.scene + 0x2f8, 0x1620450)
        || h.get<Address>(view.panel + 0x148) != view.scene || !pins() || !character_cli::pins() || h.fault) return "NATIVE_GUARD";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host; host.call<void>(0xf66c9c, view.close_button);
    return host.fault ? "NATIVE_GUARD" : nullptr;
}
inline const char* set(Reader& h, const View& view, bool offset, int value) {
    if (value < (offset ? -2000 : 10) || value > (offset ? 2000 : 65)) return "SETTING_RANGE";
    const Control& old = offset ? view.offset : view.note_speed;
    if (!view.available || view.blocked || view.reason || !view.panel || !old.node) return "SETTING_UNAVAILABLE";
    Control current;
    if (h.get<Address>(view.panel + 0x148) != view.scene || !control(h, old.node, view.panel, offset, current)
        || current.setter != old.setter || current.getter != old.getter || current.current != old.current
        || !pins() || h.fault) return "NATIVE_GUARD";
    if (current.current == value) return nullptr;
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host;
    // This is the typed widget's ordinary persisted callback; refreshing through
    // its native getter keeps its displayed value and button bounds in sync.
    host.call<void>(offset ? 0x1646cf0 : 0xf638a0, current.setter, Address(&value));
    if (!host.fault) host.call<void>(0x1886b34, current.node);
    return host.fault ? "NATIVE_GUARD" : nullptr;
}
inline const char* set_speed(Reader& h, const View& view, int tenths) { return set(h, view, false, tenths); }
inline const char* set_offset(Reader& h, const View& view, int milliseconds) { return set(h, view, true, milliseconds); }
inline const char* set_fps(Reader& h, const View& view, int enabled, int preference) {
    if (enabled < 0 || enabled > 1) return "SETTING_RANGE";
    const auto& old = view.high_framerate;
    if (!view.available || view.blocked || view.reason || !view.panel || !old.node) return "SETTING_UNAVAILABLE";
    FpsControl current;
    if (h.get<Address>(view.panel + 0x148) != view.scene || !fps_control(h, old.node, view.panel, current)
        || current.setter != old.setter || current.getter != old.getter || current.button != old.button
        || current.button_callback != old.button_callback || current.current != old.current || current.current != preference
        || !pins() || h.fault) return "NATIVE_GUARD";
    if (current.current == enabled) return nullptr;
    if (!cli_dispatch_allowed()) return "EXPIRED";
    // The ordinary button toggles, persists and refreshes through the native widget.
    OfficialHost host;
    host.call<void>(0xf66c9c, current.button);
    return host.fault ? "NATIVE_GUARD" : nullptr;
}
inline void write_state(Json& json, const View& view) {
    json.add("{\"available\":"); json.add(view.available ? "true" : "false");
    json.add(",\"reason\":"); if (view.reason) json.string(view.reason); else json.add("null");
    json.add(",\"open\":"); json.add(view.panel ? "true" : "false");
    json.add(",\"can_open\":"); json.add(view.open_button && !view.blocked && !view.reason ? "true" : "false");
    json.add(",\"can_close\":"); json.add(view.close_button && !view.blocked && !view.reason ? "true" : "false");
    json.add(",\"can_set_note_speed\":"); json.add(view.note_speed.node && !view.blocked && !view.reason ? "true" : "false");
    json.add(",\"can_set_offset\":"); json.add(view.offset.node && !view.blocked && !view.reason ? "true" : "false");
    json.add(",\"can_set_high_framerate\":"); json.add(view.high_framerate.node && !view.blocked && !view.reason ? "true" : "false");
    json.add("}");
}
} // namespace settings_panel_cli

