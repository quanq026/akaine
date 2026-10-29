#pragma once
#include "navigation_pins.h"

// Included inside staging_cli after Reader, UiTree and overlay_cli.
namespace navigation_cli {
enum Kind { Unsupported, SongSelect, Result, Gameplay };
enum Action { Back, Continue, Pause, Resume, Retry, Quit, ActionCount };
struct Binding { Address node = 0, closure = 0, type = 0, argument = 0; unsigned flags = 0; };
struct View {
    Address scene = 0, scene_type = 0, ui = 0, pause_layer = 0, model = 0;
    Kind kind = Unsupported;
    Binding actions[ActionCount] = {};
    char song[65] = {};
    int difficulty = -1;
    bool available = false, paused = false, paused_known = false;
    int pause_style = -1;
    const char* reason = "unsupported_scene";
};
inline bool pins() {
    for (const auto& pin : NAVIGATION_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
inline bool slot(Address type, Address offset, Address target) {
    Address value = 0;
    return static_pointer(module.base + type + offset, &value) && value == module.base + target;
}
inline bool reachable(Reader& h, const UiTree& tree, Address node) {
    for (Size i = 0; i < tree.inspected; ++i)
        if (tree.queue[i].node == node)
            return tree.queue[i].ancestors_enabled && h.readable(node, 0x1c2)
                && h.get<unsigned char>(node + 0x1c0) == 1 && h.get<unsigned char>(node + 0x1c1) == 1;
    return false;
}
inline Binding button(Reader& h, const UiTree& tree, Address node, Address owner, Address type, Address invoke) {
    Binding result;
    if (!reachable(h, tree, node) || !h.readable(node, 0x449)
        || h.get<Address>(node) != module.base + 0x1a8ece0
        || h.get<unsigned char>(node + 0x312) != 1 || h.get<unsigned char>(node + 0x314) != 1
        || h.get<unsigned char>(node + 0x448) != 0
        || h.get<Address>(node + 0x398) || h.get<Address>(node + 0x3a0)
        || h.get<Address>(node + 0x3a8) || h.get<Address>(node + 0x400)) return result;
    const Address closure = h.get<Address>(node + 0x3d0);
    if (!h.readable(closure, 0x10) || h.get<Address>(closure) != module.base + type
        || h.get<Address>(closure + 8) != owner || !slot(type, 0x30, invoke)
        || !slot(0x1a8ece0, 0x630, 0xf66c9c) || h.fault) return result;
    return {node, closure, type};
}
inline bool any(const View& view) {
    for (const auto& action : view.actions) if (action.node) return true;
    return false;
}
inline View inspect(Reader& h, Address scene, const char* klass, const UiTree& tree) {
    View view;
    view.scene = scene;
    if (!h.readable(scene, 0x1c2)) { view.reason = "unavailable"; return view; }
    view.scene_type = h.get<Address>(scene);
    if (!strcmp(klass, "15SongSelectScene") && view.scene_type == module.base + 0x1ad2260) view.kind = SongSelect;
    else if (!strcmp(klass, "21NormalGameResultScene") && view.scene_type == module.base + 0x1afe2a0) view.kind = Result;
    else if (!strcmp(klass, "9GameScene") && view.scene_type == module.base + 0x1ae6ef0) view.kind = Gameplay;
    if (view.kind == Unsupported) return view;
    view.reason = "native_guard";
    if (!pins() || h.get<unsigned char>(scene + 0x1c0) != 1 || h.get<unsigned char>(scene + 0x1c1) != 1) return view;
    if (!tree.valid || tree.loading) { view.reason = "ui_tree_unavailable"; return view; }
    auto overlays = overlay_cli::capture(h, scene, klass);
    if (!overlays.complete || overlays.blocked) { view.reason = "input_blocked"; return view; }
    if (tree.has_modal) { view.reason = "modal_present"; return view; }
    view.reason = "not_ready";
    if (view.kind == SongSelect) {
        if (!h.readable(scene, 0x492) || h.get<unsigned char>(scene + 0x491) != 0) return view;
        if (h.get<unsigned char>(scene + 0x391) != 0) { view.reason = "pack_select_open"; return view; }
        view.actions[Back] = button(h, tree, h.get<Address>(scene + 0x438), scene, 0x1a958a8, 0x121940c);
    } else if (view.kind == Result) {
        if (!h.readable(scene, 0x3b0)) return view;
        view.model = h.get<Address>(scene + 0x2e8);
        if (!h.readable(view.model, 0x20)) return view;
        const Address chart = h.get<Address>(view.model + 0x18);
        if (!h.readable(chart, 0x54) || !cli_song_id(h, chart + 0x38, view.song)) return view;
        view.difficulty = h.get<int>(chart + 0x50);
        if (view.difficulty < 0 || view.difficulty > 4) return view;
        auto next = button(h, tree, h.get<Address>(scene + 0x388), scene, 0x1b12f28, 0x148a4fc);
        if (next.node && (!h.readable(next.closure, 0x20)
            || h.get<unsigned char>(next.closure + 0x10) > 1 || h.get<unsigned char>(next.closure + 0x11) > 1
            || h.get<Address>(next.closure + 0x18) != h.get<Address>(view.model + 0x18))) next = {};
        if (next.node) {
            next.argument = h.get<Address>(next.closure + 0x18);
            next.flags = unsigned(h.get<unsigned char>(next.closure + 0x10))
                | unsigned(h.get<unsigned char>(next.closure + 0x11)) << 1;
        }
        view.actions[Continue] = next; view.actions[Back] = next;
        view.actions[Retry] = button(h, tree, h.get<Address>(scene + 0x3a8), scene, 0x1b501e0, 0xbd1c74);
    } else {
        if (!h.readable(scene, 0x4b1)) return view;
        const auto paused = h.get<unsigned char>(scene + 0x4b0);
        if (paused > 1) return view;
        view.paused = paused == 1; view.paused_known = true;
        view.model = h.get<Address>(scene + 0x3b0);
        if (!cli_song_id(h, h.get<Address>(scene + 0x318), view.song)) return view;
        view.difficulty = h.get<int>(scene + 0x320);
        if (view.difficulty < 0 || view.difficulty > 4) return view;
        view.ui = h.get<Address>(scene + 0x3c0);
        if (!reachable(h, tree, view.ui) || !h.readable(view.ui, 0x41c)
            || h.get<Address>(view.ui) != module.base + 0x1af4e98
            || h.get<Address>(view.ui + 0x308) != scene + 0x2f0
            || h.get<Address>(scene + 0x2f0) != module.base + 0x1ae7470
            || !slot(0x1ae7470, 0, 0x17effac) || !slot(0x1ae7470, 0x10, 0xdcb2e0)
            || !slot(0x1ae7470, 0x18, 0x186ac10)) return view;
        view.pause_layer = h.get<Address>(view.ui + 0x300);
        if (!h.readable(view.pause_layer, 0x310) || h.get<Address>(view.pause_layer) != module.base + 0x1b44720
            || h.get<Address>(view.pause_layer + 0x2e0) != scene + 0x2f0) return view;
        view.pause_style = h.get<int>(view.pause_layer + 0x2dc);
        if (view.pause_style < 0 || view.pause_style > 3) return view;
        if (view.paused) {
            if (!reachable(h, tree, view.pause_layer) || h.get<Address>(view.pause_layer + 0x148) != view.ui
                || h.get<unsigned char>(view.pause_layer + 0x2d8) != 1) return view;
            view.actions[Resume] = button(h, tree, h.get<Address>(view.pause_layer + 0x2f8), view.pause_layer, 0x1b7d700, 0x1632d78);
            view.actions[Retry] = button(h, tree, h.get<Address>(view.pause_layer + 0x300), view.pause_layer, 0x1af4320, 0xa90b80);
            view.actions[Quit] = button(h, tree, h.get<Address>(view.pause_layer + 0x308), view.pause_layer, 0x1b8a758, 0xf6793c);
        } else {
            if (h.get<Address>(view.pause_layer + 0x148) || h.get<unsigned char>(view.ui + 0x41b) != 0) return view;
            const Address node = h.get<Address>(view.ui + 0x398);
            view.actions[Pause] = button(h, tree, node, view.ui, 0x1aa9e78, 0x1346450);
            if (!view.actions[Pause].node) view.actions[Pause] = button(h, tree, node, view.ui, 0x1b85168, 0xc07304);
        }
    }
    if (h.fault) { for (auto& action : view.actions) action = {}; view.reason = "unavailable"; return view; }
    view.available = true;
    if (any(view)) view.reason = nullptr;
    return view;
}
inline bool same(const View& a, const View& b) {
    if (a.scene != b.scene || a.scene_type != b.scene_type || a.kind != b.kind || a.ui != b.ui
        || a.pause_layer != b.pause_layer || a.model != b.model || a.paused != b.paused
        || a.pause_style != b.pause_style || a.available != b.available || a.paused_known != b.paused_known
        || a.difficulty != b.difficulty || strcmp(a.song, b.song)) return false;
    for (Size i = 0; i < ActionCount; ++i)
        if (a.actions[i].node != b.actions[i].node || a.actions[i].closure != b.actions[i].closure
            || a.actions[i].type != b.actions[i].type || a.actions[i].argument != b.actions[i].argument
            || a.actions[i].flags != b.actions[i].flags) return false;
    return true;
}
inline Action action_id(const char* action) {
    constexpr const char* names[] = {"back", "continue", "pause", "resume", "retry", "quit"};
    for (Size i = 0; i < ActionCount; ++i) if (!strcmp(action, names[i])) return Action(i);
    return ActionCount;
}
inline const char* act(Reader& h, Address scene, const char* klass, const UiTree& tree, const View& expected, const char* action) {
    if (!official_thread() || !pins()) return "NATIVE_GUARD";
    const Action id = action_id(action);
    if (id == ActionCount) return "INVALID_ACTION";
    const View current = inspect(h, scene, klass, tree);
    if (!same(current, expected)) return "STALE_STATE";
    if (!current.available || !current.actions[id].node) return "ACTION_UNAVAILABLE";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost call;
    call.call<void>(0xf66c9c, current.actions[id].node);
    // The native double-tap setting needs its registered callback twice. The
    // first callback may already pause; never send the second after a change.
    if (!call.fault && id == Pause && current.actions[id].type == 0x1b85168
        && h.get<unsigned char>(scene + 0x4b0) == 0) {
        UiTree fresh(h, scene);
        const View after = inspect(h, scene, klass, fresh);
        if (!same(current, after)) return "STATE_CHANGED_AFTER_DISPATCH";
        if (!cli_dispatch_allowed()) return "EXPIRED_AFTER_DISPATCH";
        call.call<void>(0xf66c9c, after.actions[id].node);
    }
    return call.fault || h.fault ? "NATIVE_GUARD" : nullptr;
}
inline void write_state(Json& json, const View& view) {
    json.add("{\"available\":"); json.add(view.available ? "true" : "false");
    json.add(",\"scene\":");
    constexpr const char* scenes[] = {"unsupported", "song_select", "result", "gameplay"};
    json.string(scenes[view.kind]);
    json.add(",\"song_id\":"); if (view.song[0]) json.string(view.song); else json.add("null");
    json.add(",\"difficulty\":"); if (view.difficulty >= 0) { char value[4]; snprintf(value, sizeof(value), "%d", view.difficulty); json.add(value); } else json.add("null");
    json.add(",\"paused\":"); if (view.paused_known) json.add(view.paused ? "true" : "false"); else json.add("null");
    json.add(",\"reason\":"); if (view.reason) json.string(view.reason); else json.add("null");
    constexpr const char* fields[] = {",\"can_back\":", ",\"can_continue\":", ",\"can_pause\":", ",\"can_resume\":", ",\"can_retry\":", ",\"can_quit\":"};
    for (Size i = 0; i < ActionCount; ++i) { json.add(fields[i]); json.add(view.available && view.actions[i].node ? "true" : "false"); }
    json.add("}");
}
}
