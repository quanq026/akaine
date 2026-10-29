#pragma once
#include "cli_ui_core.h"
#include "cli_ui_pins.h"
#include "cli_widget_types.h"
#include "../overlays/overlay_state.h"
#include "../update/bundle_pins.h"

struct CliUiAction {
    const char* name = nullptr;
    const char* label = nullptr;
    Address node = 0, closure = 0;
};
struct CliUiState {
    akaine_cli::UiIdentity identity;
    overlay_cli::View overlays;
    CliUiAction actions[2] = {};
    Size action_count = 0;
    uint64_t context = 0;
    const char* onboarding_stage = nullptr;
    bool onboarding_settings_ready = false;
    bool note_speed_modal_ready = false;
    bool modal_present = false;
    bool pack_select_open = false;
    const char* reason = "unavailable";
    unsigned start_flags = 0;
    Size inspected_nodes = 0;
    const char* failure = nullptr;
    char failure_class[240] = {};
    char expected_parent_class[240] = {}, actual_parent_class[240] = {}, node_name[65] = {};
    bool actual_parent_is_null = false;
    Size actual_ancestor_count = 0;
    Size skipped_usercell_alias = 0;
};
akaine_cli::UiContext cli_ui_context;

bool ui_pins() {
    for (const auto& pin : CLI_UI_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
bool ui_name(Reader& h, Address node, const char* expected) {
    if (!h.readable(node + 0x160, 24)) return false;
    const unsigned char tag = h.get<unsigned char>(node + 0x160);
    const Size length = tag & 1 ? h.get<Size>(node + 0x168) : Size(tag >> 1);
    const Address data = tag & 1 ? h.get<Address>(node + 0x170) : node + 0x161;
    return !h.fault && length == strlen(expected) && h.readable(data, length + 1)
        && !memcmp(reinterpret_cast<const void*>(data), expected, length + 1);
}
bool ui_safe_node_name(Reader& h, Address node, char (&output)[65]) {
    constexpr const char* public_names[] = {"soloButton", "bgButton", "button1", "button2", "button3", "button4"};
    for (const char* name : public_names) {
        if (ui_name(h, node, name)) { memcpy(output, name, strlen(name) + 1); return true; }
    }
    return false;
}
bool ui_class(Address vt, char (&output)[240]) {
    Address typeinfo = 0, name = 0;
    if (vt < sizeof(Address) || !static_pointer(vt - sizeof(Address), &typeinfo)
        || !static_pointer(typeinfo + sizeof(Address), &name)) return false;
    for (Size i = 0; i < module.readable_count; ++i)
        if (contains(module.readable[i], name, 1))
            return rtti_name(reinterpret_cast<const char*>(name), module.readable[i].end - name, output, sizeof(output));
    return false;
}
// Only inspects visible nodes descending from the current Director scene.
// Parent links must match the traversed relationship, not merely contain a
// readable pointer to some unrelated object.
bool music_ready(Reader& h, Address scene, Address node, Address* callback);
bool pack_button_ready(Reader& h, Address scene, Address node, Address* callback);
bool pack_fields(Reader& h, Address layer, int* ordinal);
struct UiTree {
    bool built = false;
    static constexpr Size LIMIT = 1024;
    struct Item { Address node, parent; bool ancestors_enabled; Address settings_owner = 0; } queue[LIMIT] = {};
    Address seen[LIMIT] = {};
    Size count = 0;
    Size inspected = 0;
    Address music_button = 0, modal = 0, modal_type = 0;
    Address pack_button = 0;
    Address pack_layer = 0;
    bool valid = true, has_modal = false, loading = false;
    bool music_ancestors_enabled = false;
    const char* failure = nullptr;
    char failure_class[240] = {};
    char expected_parent_class[240] = {}, actual_parent_class[240] = {}, node_name[65] = {};
    bool actual_parent_is_null = false;
    Size actual_ancestor_count = 0;
    Size skipped_usercell_alias = 0;
    void fail(const char* code, const char* klass = nullptr) {
        valid = false; failure = code;
        if (klass) {
            const Size n = strlen(klass);
            if (n < sizeof(failure_class)) memcpy(failure_class, klass, n + 1);
        }
    }
    UiTree() = default;
    UiTree(Reader& h, Address scene, Address music_root = 0, Address pack_root = 0) {
        built = true;
        queue[count++] = {scene, 0, true};
        Size cursor = 0, checked = 0;
        Address owned_settings = 0;
        while (cursor < count && checked < LIMIT) {
            const Item item = queue[cursor++];
            for (Size i = 0; i < checked; ++i) if (seen[i] == item.node) { fail("duplicate_node"); return; }
            seen[checked++] = item.node;
            inspected = checked;
            if (!h.readable(item.node, 0x1c2)) { fail("node_bounds"); return; }
            const Address vt = h.get<Address>(item.node);
            if (!module_readable(vt, sizeof(Address))) { fail("node_type_bounds"); return; }
            char klass[240] = {};
            if (!ui_class(vt, klass)) { fail("node_type_name"); return; }
            if (item.parent && h.get<Address>(item.node + 0x148) != item.parent) {
                const Address actual = h.get<Address>(item.node + 0x148);
                bool actual_reachable = false;
                for (Size i = 0; i < checked; ++i) if (seen[i] == actual) actual_reachable = true;
                char expected_type[240] = {}, actual_type[240] = {};
                // Exact live UserCell renderer proxy: a generic Node child
                // contains a Button whose logical parent is the UserCell.
                // This alias never supplies actions or nested traversal.
                if (vt == module.base + 0x1a8ece0 && actual_reachable
                    && h.readable(item.parent, 0x150) && h.get<Address>(item.parent) == module.base + 0x1b4d3e8
                    && h.get<Address>(item.parent + 0x148) == actual
                    && h.readable(actual, 0x1c2) && h.get<Address>(actual) == module.base + 0x1b31908
                    && ui_class(module.base + 0x1b4d3e8, expected_type) && !strcmp(expected_type, "N7cocos2d4NodeE")
                    && ui_class(module.base + 0x1b31908, actual_type) && !strcmp(actual_type, "8UserCell")) {
                    ++skipped_usercell_alias;
                    continue;
                }
                actual_parent_is_null = actual == 0;
                if (h.readable(item.parent, sizeof(Address))) ui_class(h.get<Address>(item.parent), expected_parent_class);
                if (h.readable(actual, sizeof(Address))) ui_class(h.get<Address>(actual), actual_parent_class);
                ui_safe_node_name(h, item.node, node_name);
                Address ancestor = actual, ancestry[16] = {};
                for (Size i = 0; ancestor && i < 16; ++i) {
                    if (!h.readable(ancestor, 0x150)) break;
                    bool cycle = false;
                    for (Size j = 0; j < i; ++j) if (ancestry[j] == ancestor) cycle = true;
                    if (cycle) break;
                    ancestry[i] = ancestor; ++actual_ancestor_count;
                    ancestor = h.get<Address>(ancestor + 0x148);
                }
                fail("parent_link", klass); return;
            }
            const unsigned char visible = h.get<unsigned char>(item.node + 0x1c1);
            if (visible > 1) { fail("visibility_value", klass); return; }
            if (!visible) continue;
            if (vt == module.base + 0x1ac3640) {
                if (owned_settings) { fail("ambiguous_settings", klass); return; }
                owned_settings = item.node;
            }
            const Address settings_owner = vt == module.base + 0x1ac3640 ? item.node : item.settings_owner;
            bool enabled = item.ancestors_enabled;
            for (Address widget_type : CLI_WIDGET_VTABLES) {
                if (vt != module.base + widget_type) continue;
                if (!h.readable(item.node + 0x312, 1)) { fail("widget_enabled_bounds", klass); return; }
                const unsigned char own_enabled = h.get<unsigned char>(item.node + 0x312);
                if (own_enabled > 1) { fail("widget_enabled_value", klass); return; }
                enabled = enabled && own_enabled == 1;
                break;
            }
            const bool is_loading = strstr(klass, "Loading") || strstr(klass, "Transition");
            const bool is_modal = is_loading || strstr(klass, "Dialog") || strstr(klass, "Overlay") || strstr(klass, "Popup")
                || vt == module.base + 0x1ac3640 || vt == module.base + 0x1b453b0; // Settings and Note Speed own swallowing input layers.
            if (item.node != scene && is_modal) {
                has_modal = true; loading = loading || is_loading;
                // Record a single deterministic modal identity. Multiple visible
                // modal-like nodes still block actions; no modal is activated.
                if (!modal) { modal = item.node; modal_type = vt; }
            }
            if (vt == module.base + 0x1b828b8) {
                if (pack_layer) { fail("ambiguous_pack_layer", klass); return; }
                pack_layer = item.node;
            }
            Address registered_callback = 0;
            if (item.parent == music_root && vt == module.base + 0x1a8ece0 && enabled
                && music_ready(h, scene, item.node, &registered_callback)) {
                if (music_button) { fail("ambiguous_music", klass); return; }
                music_button = item.node;
                music_ancestors_enabled = enabled;
            }
            if (item.parent == pack_root && vt == module.base + 0x1a8ece0 && enabled
                && pack_button_ready(h, scene, item.node, &registered_callback)) {
                if (pack_button) { fail("ambiguous_pack_button", klass); return; }
                pack_button = item.node;
            }
            const Address vector = h.get<Address>(item.node + 0x140);
            if (vector) {
                if (!h.readable(vector, 24)) { fail("children_bounds", klass); return; }
                const Address begin = h.get<Address>(vector), end = h.get<Address>(vector + 8), cap = h.get<Address>(vector + 16);
                if (h.fault || end < begin || cap < end || (end - begin) % 8 || (cap - begin) % 8
                    || cap - begin > 65536 || end - begin > (LIMIT - count) * 8
                    || (end != begin && !h.readable(begin, end - begin))) { fail("children_shape_or_limit", klass); return; }
                for (Address at = begin; at < end; at += 8) queue[count++] = {h.get<Address>(at), item.node, enabled, settings_owner};
            }
            // These two owned settings containers keep their Layout in protected children.
            if (settings_owner && (vt == module.base + 0x1a95f28 || vt == module.base + 0x1b05950)) {
                if (!h.readable(item.node, 0x750)) { fail("settings_container_bounds", klass); return; }
                const Address inner = h.get<Address>(item.node + 0x748);
                if (!h.readable(inner, 0x1c2) || h.get<Address>(inner) != module.base + 0x1af2d48
                    || h.get<Address>(inner + 0x148) != item.node || h.fault) { fail("settings_inner_owner", klass); return; }
                bool queued = false;
                for (Size i = 0; i < count; ++i) if (queue[i].node == inner) {
                    if (queue[i].parent != item.node) { fail("settings_inner_alias", klass); return; }
                    queued = true;
                }
                if (!queued) {
                    if (count == LIMIT) { fail("children_shape_or_limit", klass); return; }
                    queue[count++] = {inner, item.node, enabled, settings_owner};
                }
            }
        }
        if (cursor != count || h.fault) fail("traversal_limit_or_fault");
    }
};
bool note_speed_modal_only(Reader& h, Address scene, const UiTree& tree, const overlay_cli::View& overlays) {
    if (!tree.valid || tree.loading || !tree.has_modal || !overlays.complete || overlays.count != 1
        || !overlay_cli::has_note_speed(overlays) || tree.modal != overlays.items[0].node) return false;
    for (Size i = 0; i < tree.count; ++i) {
        const Address node = tree.queue[i].node;
        if (node == scene || node == overlays.items[0].node || h.get<unsigned char>(node + 0x1c1) != 1) continue;
        char klass[240] = {};
        if (!ui_class(h.get<Address>(node), klass) || strstr(klass, "Dialog") || strstr(klass, "Overlay")
            || strstr(klass, "Popup") || strstr(klass, "Loading") || strstr(klass, "Transition")) return false;
    }
    return !h.fault;
}
bool music_ready(Reader& h, Address scene, Address node, Address* callback) {
    if (!node || !h.readable(node, 0x449) || h.get<Address>(node) != module.base + 0x1a8ece0
        || h.get<unsigned char>(node + 0x1c0) != 1
        || h.get<unsigned char>(node + 0x1c1) != 1 || h.get<unsigned char>(node + 0x312) != 1
        || h.get<unsigned char>(node + 0x314) != 1 || !ui_name(h, node, "soloButton")) return false;
    const Address fn = h.get<Address>(node + 0x3d0);
    if (!h.readable(fn, 0x10) || h.get<Address>(fn) != module.base + 0x1accbf0
        || h.get<Address>(fn + 8) != scene) return false;
    Address invoke = 0;
    if (!static_pointer(module.base + 0x1accbf0 + 0x30, &invoke) || invoke != module.base + 0x1271084) return false;
    *callback = fn;
    return !h.fault;
}
bool pack_button_ready(Reader& h, Address scene, Address node, Address* callback) {
    if (!node || !h.readable(node, 0x449) || h.get<Address>(node) != module.base + 0x1a8ece0
        || h.get<unsigned char>(node + 0x1c0) != 1 || h.get<unsigned char>(node + 0x1c1) != 1
        || h.get<unsigned char>(node + 0x312) != 1 || h.get<unsigned char>(node + 0x314) != 1
        || h.get<unsigned char>(node + 0x448) != 0 || !ui_name(h, node, "bgButton")
        || h.get<Address>(node + 0x398) || h.get<Address>(node + 0x3a0) || h.get<Address>(node + 0x3a8)
        || h.get<Address>(node + 0x400)) return false;
    const Address fn = h.get<Address>(node + 0x3d0);
    if (!h.readable(fn, 0x10) || h.get<Address>(fn) != module.base + 0x1b37f20
        || h.get<Address>(fn + 8) != scene) return false;
    Address invoke = 0, release = 0;
    if (!static_pointer(module.base + 0x1b37f20 + 0x30, &invoke) || invoke != module.base + 0x12ccb44
        || !static_pointer(module.base + 0x1a8ece0 + 0x630, &release) || release != module.base + 0xf66c9c) return false;
    *callback = fn;
    return !h.fault;
}
bool validated_open_pack(Reader& h, Address scene, Address visible_layer) {
    if (!visible_layer || h.get<Address>(scene + 0x3a8) != visible_layer
        || h.get<Address>(visible_layer + 0x148) == 0
        || h.get<unsigned char>(visible_layer + 0x1c0) != 1) return false;
    int ordinal = -1;
    return pack_fields(h, visible_layer, &ordinal) && !h.fault;
}
// The real registered StartScene closure is discovered through the exact
// dispatcher node-listener map. Never construct a fake listener or closure.
Address start_closure(Reader& h, Address scene, unsigned* flags) {
    if (!h.readable(scene, 0x354)) return 0;
    unsigned bits = 0;
    for (Size i = 0; i < 6; ++i) {
        const unsigned char value = h.get<unsigned char>(scene + 0x34e + i);
        if (value > 1) return 0;
        bits |= unsigned(value) << i;
    }
    *flags = bits;
    if (!(bits & 1)) return 0;
    const Address dispatcher = h.get<Address>(scene + 0x1b8);
    if (!h.readable(dispatcher, 0x80)) return 0;
    const Address head = h.get<Address>(dispatcher + 0x70);
    const Size count = h.get<Size>(dispatcher + 0x78);
    if (h.fault || count == 0 || count > 1024 || !head) return 0;
    Address seen[1024] = {}, node = head, vector = 0;
    for (Size i = 0; i < count; ++i) {
        if (!h.readable(node, 0x20)) return 0;
        for (Size j = 0; j < i; ++j) if (seen[j] == node) return 0;
        seen[i] = node;
        if (h.get<Address>(node + 0x10) == scene) {
            if (vector) return 0;
            vector = h.get<Address>(node + 0x18);
        }
        node = h.get<Address>(node);
    }
    if (h.fault || node || !h.readable(vector, 24)) return 0;
    const Address begin = h.get<Address>(vector), end = h.get<Address>(vector + 8), cap = h.get<Address>(vector + 16);
    if (h.fault || end < begin || cap < end || (end - begin) % 8 || (cap - begin) % 8
        || end - begin > 64 * 8 || cap - begin > 4096 || (end != begin && !h.readable(begin, end - begin))) return 0;
    Address result = 0;
    for (Address at = begin; at < end; at += 8) {
        const Address listener = h.get<Address>(at);
        if (!h.readable(listener, 0xa8)) return 0;
        if (h.get<Address>(listener) != module.base + 0x1a953c8) continue;
        if (h.get<unsigned char>(listener + 0x60) != 1 || h.get<unsigned char>(listener + 0x70) != 0
            || h.get<unsigned char>(listener + 0x71) != 1 || h.get<Address>(listener + 0x68) != scene) continue;
        const Address closure = h.get<Address>(listener + 0xa0);
        if (!h.readable(closure, 0x18) || h.get<Address>(closure) != module.base + 0x1abb5a8) continue;
        if (h.get<Address>(closure + 8) != scene || h.get<unsigned char>(closure + 16) > 1) return 0;
        Address invoke = 0;
        if (!static_pointer(module.base + 0x1abb5a8 + 0x30, &invoke) || invoke != module.base + 0x1591420 || result) return 0;
        result = closure;
    }
    return h.fault ? 0 : result;
}
#include "cli_onboarding.h"
CliUiState capture_ui(Reader& h, Address scene, const char* klass, UiTree* observed_tree = nullptr) {
    CliUiState result;
    result.identity.scene = scene;
    if (!h.readable(scene, sizeof(Address)) || !ui_pins()) {
        result.context = cli_ui_context.observe(result.identity); return result;
    }
    const Address vt = h.get<Address>(scene);
    result.identity.scene_type = vt;
    result.overlays = overlay_cli::capture(h, scene, klass);
    // The independently bounded overlay observer cannot poison scene reporting.
    // Its incomplete result still prevents every mutation below.
    h.fault = false;
    result.identity.overlay_count = result.overlays.count;
    for (Size i = 0; i < result.overlays.count; ++i) {
        const auto& item = result.overlays.items[i];
        result.identity.overlays[i] = item.node;
        result.identity.interceptors[i] = item.listener;
        result.identity.overlay_flags[i] = uint32_t((item.active ? 1 : 0) | (item.blocks_input ? 2 : 0)
            | (item.can_advance ? 4 : 0) | (item.advance_ready ? 8 : 0)
            | (item.pending_steps << 4) | (item.step_index << 12));
    }
    if (h.get<unsigned char>(scene + 0x1c0) != 1) {
        result.reason = "not_ready";
        result.context = cli_ui_context.observe(result.identity); return result;
    }
    const bool start = !strcmp(klass, "10StartScene") && vt == module.base + 0x1a9b4c0;
    const bool menu = !strcmp(klass, "13MainMenuScene") && vt == module.base + 0x1b2e5a0;
    const bool select = !strcmp(klass, "15SongSelectScene") && vt == module.base + 0x1ad2260;
    if (!start && !menu && !select) {
        result.reason = "unsupported_scene";
        result.context = cli_ui_context.observe(result.identity); return result;
    }
    const Address music_root = menu ? h.get<Address>(scene + 0x328) : 0;
    const Address pack_root = select ? h.get<Address>(scene + 0x380) : 0;
    UiTree tree(h, scene, music_root, pack_root);
    if (observed_tree) *observed_tree = tree;
    result.inspected_nodes = tree.inspected;
    result.skipped_usercell_alias = tree.skipped_usercell_alias;
    if (!tree.valid) {
        result.reason = "unsupported_ui_tree";
        result.failure = tree.failure;
        memcpy(result.failure_class, tree.failure_class, sizeof(result.failure_class));
        memcpy(result.expected_parent_class, tree.expected_parent_class, sizeof(result.expected_parent_class));
        memcpy(result.actual_parent_class, tree.actual_parent_class, sizeof(result.actual_parent_class));
        memcpy(result.node_name, tree.node_name, sizeof(result.node_name));
        result.actual_parent_is_null = tree.actual_parent_is_null;
        result.actual_ancestor_count = tree.actual_ancestor_count;
        result.context = cli_ui_context.observe(result.identity); return result;
    }
    result.note_speed_modal_ready = note_speed_modal_only(h, scene, tree, result.overlays);
    result.identity.available = true;
    result.modal_present = tree.has_modal;
    result.identity.modal = tree.modal; result.identity.modal_type = tree.modal_type;
    if (tree.has_modal) {
        result.reason = tree.loading ? "loading" : "unsupported_modal";
        if (menu && !tree.loading) capture_onboarding(h, scene, tree, result);
    }
    else if (start) {
        // This native update popup uses generic Nodes, so class-name modal scanning misses it.
        if (!in_ranges(module.executable, module.executable_count, module.base + 0x16e9dc8, sizeof(CLI_BUNDLE_CREATE_POPUP))
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + 0x16e9dc8), CLI_BUNDLE_CREATE_POPUP, sizeof(CLI_BUNDLE_CREATE_POPUP))) {
            result.reason = "unavailable";
            result.context = cli_ui_context.observe(result.identity); return result;
        }
        const unsigned popup = h.get<unsigned char>(scene + 0x3f0);
        result.identity.flags[1] = popup;
        if (h.fault || popup > 1) {
            result.reason = "unavailable";
            result.context = cli_ui_context.observe(result.identity); return result;
        }
        if (popup) {
            result.modal_present = true; result.identity.modal = scene; result.identity.modal_type = vt;
            result.reason = h.get<Address>(scene + 0x320) ? "loading" : "unsupported_modal";
            result.context = cli_ui_context.observe(result.identity); return result;
        }
        const Address closure = start_closure(h, scene, &result.start_flags);
        result.identity.flags[0] = result.start_flags;
        result.reason = "not_ready";
        if (closure) {
            result.actions[0] = {"start_continue", "Continue", scene, closure};
            result.action_count = 1; result.reason = nullptr;
        }
    } else if (menu) {
        Address callback = 0;
        result.reason = "not_ready";
        if (tree.music_ancestors_enabled && music_ready(h, scene, tree.music_button, &callback)) {
            result.actions[0] = {"main_music", "Music", tree.music_button, callback};
            result.action_count = 1; result.reason = nullptr;
        }
    } else if (select) {
        result.reason = "not_ready";
        Address callback = 0;
        const bool open = validated_open_pack(h, scene, tree.pack_layer);
        result.pack_select_open = open;
        result.identity.flags[1] = open ? 1 : 0;
        if (open) result.reason = nullptr;
        if (!open && pack_button_ready(h, scene, tree.pack_button, &callback)) {
            result.actions[0] = {"pack_open", "Pack Select", tree.pack_button, callback};
            result.action_count = 1; result.reason = nullptr;
        }
    } else result.reason = "unsupported_scene";
    if (!result.overlays.complete) {
        result.action_count = 0; result.reason = "overlay_scan_incomplete"; result.identity.available = false;
    } else if (result.overlays.blocked) {
        result.action_count = 0; result.reason = "tutorial_active";
        for (Size i = 0; i < result.overlays.count; ++i)
            if (result.overlays.items[i].blocks_input) result.reason = "input_blocked";
        if (!tree.has_modal && overlay_cli::can_advance(result.overlays)) {
            const auto& item = result.overlays.items[0];
            result.actions[0] = !strcmp(item.id, "notification_permission_guide")
                ? CliUiAction{"notification_hint_continue", "Continue notification guide (requests Android permission)", item.node, item.callback}
                : !strcmp(item.id, "main_menu_hint")
                ? CliUiAction{"main_hint_continue", "Continue main menu guide", item.node, item.callback}
                : CliUiAction{"pack_hint_continue", "Continue pack selection guide", item.node, item.callback};
            result.action_count = 1;
        }
    }
    if (h.fault) { result.action_count = 0; result.reason = "unavailable"; result.identity.available = false; }
    result.identity.count = result.action_count;
    for (Size i = 0; i < result.action_count; ++i) {
        result.identity.nodes[i] = result.actions[i].node; result.identity.callbacks[i] = result.actions[i].closure;
    }
    result.context = cli_ui_context.observe(result.identity);
    if (!result.context) { result.action_count = 0; result.reason = "unavailable"; }
    return result;
}
void ui_json(akaine_cli::Json& json, const CliUiState& value) {
    char hex[17]; snprintf(hex, sizeof(hex), "%016llx", static_cast<unsigned long long>(value.context));
    json.add("{\"context\":"); json.string(hex);
    json.add(",\"onboarding_stage\":"); if (value.onboarding_stage) json.string(value.onboarding_stage); else json.add("null");
    json.add(",\"onboarding_settings_ready\":"); json.add(value.onboarding_settings_ready ? "true" : "false");
    json.add(",\"guide_metadata_version\":1");
    json.add(",\"note_speed_modal_ready\":"); json.add(value.note_speed_modal_ready ? "true" : "false");
    json.add(",\"modal_present\":"); json.add(value.modal_present ? "true" : "false");
    json.add(",\"pack_select_open\":"); json.add(value.pack_select_open ? "true" : "false");
    json.add(",\"reason\":"); if (value.reason) json.string(value.reason); else json.add("null");
    char nodes[24]; snprintf(nodes, sizeof(nodes), "%zu", value.inspected_nodes);
    json.add(",\"inspected_nodes\":"); json.add(nodes);
    char aliases[24]; snprintf(aliases, sizeof(aliases), "%zu", value.skipped_usercell_alias);
    json.add(",\"skipped_usercell_alias\":"); json.add(aliases);
    overlay_cli::write_fields(json, value.overlays);
    json.add(",\"diagnostic\":");
    if (value.failure) {
        json.add("{\"code\":"); json.string(value.failure);
        json.add(",\"class\":"); if (value.failure_class[0]) json.string(value.failure_class); else json.add("null");
        json.add(",\"expected_parent_class\":"); if (value.expected_parent_class[0]) json.string(value.expected_parent_class); else json.add("null");
        json.add(",\"actual_parent_class\":"); if (value.actual_parent_class[0]) json.string(value.actual_parent_class); else json.add("null");
        json.add(",\"node_name\":"); if (value.node_name[0]) json.string(value.node_name); else json.add("null");
        json.add(",\"actual_parent_is_null\":"); json.add(value.actual_parent_is_null ? "true" : "false");
        char ancestors[24]; snprintf(ancestors, sizeof(ancestors), "%zu", value.actual_ancestor_count);
        json.add(",\"actual_ancestor_count\":"); json.add(ancestors);
        json.add("}");
    } else json.add("null");
    json.add(",\"actions\":[");
    for (Size i = 0; i < value.action_count; ++i) {
        if (i) json.add(",");
        char token[65]; snprintf(token, sizeof(token), "%s.%s", value.actions[i].name, hex);
        json.add("{\"token\":"); json.string(token);
        json.add(",\"name\":"); json.string(value.actions[i].label); json.add(",\"enabled\":true}");
    }
    json.add("]}");
}
