#pragma once

// Include inside staging_cli, after Reader, UiTree and the frozen native helpers.
#include "account_pins.h"
#include "account_error_pins.h"
#include "logout_pins.h"

namespace account_controls {
enum class Result { ok, unavailable, blocked, field_rejected, pin_mismatch, fault };
struct AccountView {
    const char* kind = "unavailable";
    const char* error_code = nullptr, *error_text = nullptr;
    bool signed_in_known = false, signed_in = false, blocked = true;
    bool can_open = false, can_login_open = false, can_fill = false, can_submit = false, can_accept_terms = false;
    bool can_management_open = false, can_logout = false;
    Address scene = 0, modal = 0, root = 0, button = 0, closure = 0;
    Address username = 0, password = 0;
};

inline bool pins() {
    for (const auto& pin : ACCOUNT_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    for (const auto& pin : LOGOUT_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    for (const auto& pin : LOGIN_ERROR_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
inline bool pointer_pin(Address slot, Address expected) {
    Address actual = 0;
    return static_pointer(module.base + slot, &actual) && actual == module.base + expected;
}
inline bool member(const UiTree& tree, Address node, Address parent = 0, bool enabled = false) {
    if (!node || !tree.valid) return false;
    for (Size i = 0; i < tree.count; ++i)
        if (tree.queue[i].node == node)
            return (!parent || tree.queue[i].parent == parent)
                && (!enabled || tree.queue[i].ancestors_enabled);
    return false;
}
inline Address child(Reader& h, const UiTree& tree, Address parent, const char* name, Address vtable) {
    Address result = 0;
    for (Size i = 0; i < tree.count; ++i) {
        const auto& item = tree.queue[i];
        if (item.parent != parent || !item.ancestors_enabled || !h.readable(item.node, 0x315)
            || h.get<Address>(item.node) != module.base + vtable
            || h.get<unsigned char>(item.node + 0x1c1) != 1 || !ui_name(h, item.node, name)) continue;
        if (result) return 0;
        result = item.node;
    }
    return h.fault ? 0 : result;
}
inline bool widget(Reader& h, Address node, Address vtable) {
    return h.readable(node, 0x449) && h.get<Address>(node) == module.base + vtable
        && h.get<unsigned char>(node + 0x1c0) == 1 && h.get<unsigned char>(node + 0x1c1) == 1
        && h.get<unsigned char>(node + 0x312) == 1 && h.get<unsigned char>(node + 0x314) == 1 && !h.fault;
}
inline Address callback(Reader& h, Address node, Address vtable, Address invoke, Size size) {
    if (!widget(h, node, 0x1a8ece0)
        || h.get<unsigned char>(node + 0x448) != 0
        || h.get<Address>(node + 0x398) || h.get<Address>(node + 0x3a0)
        || h.get<Address>(node + 0x3a8) || h.get<Address>(node + 0x400)) return 0;
    const Address closure = h.get<Address>(node + 0x3d0);
    return h.readable(closure, size) && h.get<Address>(closure) == module.base + vtable
        && pointer_pin(vtable + 0x30, invoke) && pointer_pin(0x1a8ece0 + 0x630, 0xf66c9c)
        && !h.fault ? closure : 0;
}
inline bool field(Reader& h, Address node) {
    if (!widget(h, node, 0x1aea538) || !h.readable(node, 0x4f1)) return false;
    const Address renderer = h.get<Address>(node + 0x488);
    return h.readable(renderer, 0x7b0) && h.get<Address>(renderer) == module.base + 0x1a8fba8
        && pointer_pin(0x1a8fba8 + 0x568, 0x1529c24)
        && pointer_pin(0x1a8fba8 + 0x560, 0x14e7ef4)
        && pointer_pin(0x1a8fba8 + 0x640, 0xe3a1e0)
        && pointer_pin(0x1a8fba8 + 0x668, 0x1378124) && !h.fault;
}
inline void login_flag(Reader& h, AccountView& value) {
    if (!pointer_pin(0x1b95f58, 0x1bf23c0) || !pointer_pin(0x1ae06a8 + 0x10, 0xac5bc0)) return;
    const Address context = h.get<Address>(module.base + 0x1bf23c0);
    if (!h.readable(context, 0x88)) return;
    const Address online = h.get<Address>(context + 0x80);
    if (!h.readable(online, 0x126) || h.get<Address>(online) != module.base + 0x1ae06a8) return;
    const unsigned char flag = h.get<unsigned char>(online + 0x124);
    if (!h.fault && flag <= 1) { value.signed_in_known = true; value.signed_in = flag == 1; }
}
inline Address login_terms_required(Reader& h, Address scene, const UiTree& tree) {
    Address terms = 0, privacy = 0, dialog = 0;
    for (Size i = 0; i < tree.count; ++i) {
        const auto& item = tree.queue[i];
        if (h.get<unsigned char>(item.node + 0x1c1) != 1) continue;
        const Address vt = h.get<Address>(item.node);
        if (vt == module.base + 0x1af8480 && item.parent == scene) {
            if (dialog || !h.readable(item.node, 0x341) || h.get<unsigned char>(item.node + 0x340) != 1) return false;
            dialog = item.node;
        }
        if (vt != module.base + 0x1a8ece0 || !item.ancestors_enabled) continue;
        const bool tos = ui_name(h, item.node, "button_tos"), policy = ui_name(h, item.node, "button_privacy");
        if (!tos && !policy) continue;
        const Address closure = callback(h, item.node, tos ? 0x1afa800 : 0x1adb4c8,
                                          tos ? 0x18f81dc : 0x96a884, 0x10);
        if (!closure || h.get<Address>(closure + 8) != scene) return false;
        Address& target = tos ? terms : privacy;
        if (target) return false;
        target = item.node;
    }
    if (!dialog || !terms || !privacy || h.fault) return false;
    const Address contents = h.get<Address>(terms + 0x148);
    if (!contents || h.get<Address>(privacy + 0x148) != contents) return false;
    Address parent = contents;
    for (Size depth = 0; parent && depth < 32; ++depth) {
        if (parent == dialog) return h.fault ? 0 : dialog;
        if (!member(tree, parent) || !h.readable(parent, 0x150)) return false;
        parent = h.get<Address>(parent + 0x148);
    }
    return false;
}
inline Address terms_agree_button(Reader& h, Address scene, Address dialog, const UiTree& tree, Address* actual_closure) {
    if (!dialog || h.get<unsigned char>(dialog + 0x302) != 0 || h.get<unsigned char>(dialog + 0x1c0) != 1) return 0;
    // Only the source-built Terms dialog followed by its login continuation is accepted.
    for (Size i = 0; i < tree.count; ++i) {
        const Address node = tree.queue[i].node;
        if (node == dialog || node == scene || h.get<unsigned char>(node + 0x1c1) != 1) continue;
        char klass[240] = {};
        if (!ui_class(h.get<Address>(node), klass)) return 0;
        if ((strstr(klass, "Dialog") && h.get<Address>(node) != module.base + 0x1b503d8)
            || strstr(klass, "Overlay") || strstr(klass, "Popup") || strstr(klass, "Loading") || strstr(klass, "Transition")) return 0;
    }
    const Address root = h.get<Address>(dialog + 0x308), button = h.get<Address>(dialog + 0x320);
    if (!member(tree, root) || !member(tree, button, root, true) || !ui_name(h, button, "button1")
        || !widget(h, button, 0x1a8ece0) || h.get<unsigned char>(button + 0x448) != 0
        || h.get<Address>(button + 0x398) || h.get<Address>(button + 0x3a0)
        || h.get<Address>(button + 0x3a8) || h.get<Address>(button + 0x3d0)) return 0;
    const Address outer = h.get<Address>(button + 0x400);
    if (!h.readable(outer, 0x48) || h.get<Address>(outer) != module.base + 0x1b4aec8
        || h.get<Address>(outer + 0x10) != dialog || !pointer_pin(0x1b4aec8 + 0x30, 0x1411494)) return 0;
    const Address agree = h.get<Address>(outer + 0x40);
    if (!h.readable(agree, 0x48) || h.get<Address>(agree) != module.base + 0x1a99f50
        || h.get<Address>(agree + 0x10) != scene || !pointer_pin(0x1a99f50 + 0x30, 0xe25f24)) return 0;
    const Address continuation = h.get<Address>(agree + 0x40);
    if (!h.readable(continuation, 0x20) || h.get<Address>(continuation) != module.base + 0x1b7fb38
        || h.get<Address>(continuation + 0x10) != scene || !pointer_pin(0x1b7fb38 + 0x30, 0xb3e20c)) return 0;
    const Address network_modal = h.get<Address>(continuation + 8);
    if (!member(tree, network_modal, scene) || h.get<Address>(network_modal) != module.base + 0x1b503d8) return 0;
    const Address network_root = h.get<Address>(network_modal + 0x2d8);
    const Address login = child(h, tree, network_root, "login_button", 0x1a8ece0);
    const Address login_closure = callback(h, login, 0x1b93718, 0xba307c, 0x38);
    if (!member(tree, network_root) || !login_closure || h.get<Address>(login_closure + 8) != network_modal
        || h.get<Address>(login_closure + 0x10) != scene || h.get<Address>(login_closure + 0x18) != scene + 0x308
        || h.fault || !pointer_pin(0x1a8ece0 + 0x630, 0xf66c9c)) return 0;
    *actual_closure = outer;
    return button;
}
inline bool known_login_error(const char* code) {
    if (!code) return false;
    constexpr const char* codes[] = {"connection_failed", "invalid_credentials", "account_locked", "maintenance", "unknown_error"};
    for (const char* known : codes) if (!strcmp(code, known)) return true;
    return false;
}
inline void login_error(Reader& h, const UiTree& tree, AccountView& value) {
    const Address label = child(h, tree, value.root, "error_text", 0x1a98ce0);
    if (!label || !h.readable(label, 0x4c0) || h.get<unsigned char>(label + 0x1c0) != 1
        || h.get<Address>(label + 0x148) != value.root) return;
    const Address renderer = h.get<Address>(label + 0x4b8);
    if (!h.readable(renderer, 0x2e8) || h.get<Address>(renderer) != module.base + 0x1adae68
        || !pointer_pin(0x1adae68 + 0x568, 0xb9acbc)) return;
    struct Message { const char* code; const char* text; };
    constexpr Message messages[] = {
        {"connection_failed", "Could not connect to online server."},
        {"invalid_credentials", "Username or password incorrect."},
        {"account_locked", "This account is locked."},
        {"maintenance", "The Arcaea network is currently under maintenance."},
        {"unknown_error", "An unknown error has occurred."}
    };
    const Address string = renderer + 0x2d0;
    const unsigned char tag = h.get<unsigned char>(string);
    const Size length = tag & 1 ? h.get<Size>(string + 8) : Size(tag >> 1);
    if (!length) return;
    value.error_code = "unrecognized";
    if (!(tag & 1) && length > 22) return;
    if (tag & 1) {
        const Size capacity = h.get<Size>(string) & ~Size(1);
        if (capacity <= length || capacity > 4096) return;
    }
    for (const auto& message : messages) {
        if (length != strlen(message.text)) continue;
        const Address bytes = tag & 1 ? h.get<Address>(string + 16) : string + 1;
        if (!h.readable(bytes, length + 1)) return;
        if (!memcmp(reinterpret_cast<const void*>(bytes), message.text, length + 1)) {
            value.error_code = message.code; value.error_text = message.text; return;
        }
    }
}
struct SubmitCycle {
    Address scene = 0, modal = 0, root = 0, button = 0, closure = 0;
    bool observed_busy = false;
    void observe_busy(Reader& h, const AccountView& before) {
        *this = {};
        if (!before.can_submit || !h.readable(before.button, 0x408) || !h.readable(before.closure, 0x50)
            || h.get<Address>(before.button) != module.base + 0x1a8ece0
            || h.get<Address>(before.button + 0x3d0) != before.closure
            || h.get<Address>(before.closure) != module.base + 0x1a87cd8
            || h.get<Address>(before.closure + 8) != before.modal
            || h.get<Address>(before.closure + 0x10) != before.scene + 0x388
            || h.get<Address>(before.closure + 0x18) != before.scene
            || h.get<Address>(before.closure + 0x40) != before.button
            || h.get<unsigned char>(before.button + 0x312) != 0
            || h.get<unsigned char>(before.button + 0x313) != 0 || h.fault) return;
        scene = before.scene; modal = before.modal; root = before.root;
        button = before.button; closure = before.closure; observed_busy = true;
    }
    bool failed(const AccountView& fresh) const {
        return observed_busy && !fresh.blocked && fresh.can_submit && !strcmp(fresh.kind, "login")
            && fresh.scene == scene && fresh.modal == modal && fresh.root == root
            && fresh.button == button && fresh.closure == closure && known_login_error(fresh.error_code);
    }
};

inline bool management(Reader& h, Address scene, const UiTree& tree, AccountView& value) {
    Address dialog = 0, network = 0;
    for (Size i = 0; i < tree.count; ++i) {
        const Address node = tree.queue[i].node;
        if (node == scene || h.get<unsigned char>(node + 0x1c1) != 1) continue;
        const Address vt = h.get<Address>(node);
        if (vt == module.base + 0x1af8480) {
            if (dialog || !member(tree, node, scene, true)) return false;
            dialog = node;
        } else if (vt == module.base + 0x1b503d8) {
            if (network || !member(tree, node, scene, true)) return false;
            network = node;
        } else {
            char klass[240] = {};
            if (!ui_class(vt, klass) || strstr(klass, "Dialog") || strstr(klass, "Overlay")
                || strstr(klass, "Popup") || strstr(klass, "Loading") || strstr(klass, "Transition")) return false;
        }
    }
    if (!dialog || !network || !h.readable(dialog, 0x341)
        || h.get<unsigned char>(dialog + 0x1c0) != 1 || h.get<unsigned char>(dialog + 0x302) != 0
        || h.get<unsigned char>(dialog + 0x340) != 0 || !h.readable(network, 0x310)
        || h.get<unsigned char>(network + 0x308) != 0) return false;
    const Address owner = h.get<Address>(network + 0x2d8);
    if (!member(tree, owner) || !h.readable(owner, 0x2b8) || h.get<Address>(owner) != module.base + 0x1b2d7b0
        || h.get<Address>(owner + 0x2b0) != network) return false;
    const Address content = h.get<Address>(owner + 0x2a8);
    const Address menu_button = child(h, tree, content, "account_management_button", 0x1a8ece0);
    const Address menu_closure = callback(h, menu_button, 0x1ac75b0, 0x11b6808, 0x10);
    if (!member(tree, content, owner) || !menu_closure || h.get<Address>(menu_closure + 8) != owner) return false;
    const Address root = h.get<Address>(dialog + 0x308), custom = h.get<Address>(dialog + 0x318);
    if (!member(tree, root, dialog, true) || !member(tree, custom, root, true)) return false;
    Address logout = 0, logout_closure = 0;
    for (Size i = 0; i < tree.count; ++i) {
        const auto& item = tree.queue[i];
        if (item.parent != custom || !item.ancestors_enabled || h.get<Address>(item.node) != module.base + 0x1a8ece0) continue;
        const Address closure = h.get<Address>(item.node + 0x3d0);
        if (!h.readable(closure, 0x28) || h.get<Address>(closure) != module.base + 0x1adc920) continue;
        if (logout || callback(h, item.node, 0x1adc920, 0x16e130c, 0x28) != closure
            || h.get<Address>(closure + 8) != owner || h.get<Address>(closure + 0x18) != item.node
            || h.get<Address>(closure + 0x20) != dialog) return false;
        // The captured sibling is the separate delete button; it is never dispatched.
        const Address sibling = h.get<Address>(closure + 0x10);
        if (sibling == item.node || !member(tree, sibling, custom, true)
            || h.get<Address>(sibling) != module.base + 0x1a8ece0) return false;
        logout = item.node; logout_closure = closure;
    }
    if (!logout || h.fault) return false;
    value.kind = "account_management"; value.blocked = false; value.can_logout = true;
    value.modal = dialog; value.root = custom; value.button = logout; value.closure = logout_closure;
    return true;
}
inline AccountView inspect(Reader& h, Address scene, const UiTree& tree) {
    AccountView value;
    if (!tree.valid || tree.loading || !pins()) return value;
    login_flag(h, value);
    if (!h.readable(scene, 0x3e9) || h.get<Address>(scene) != module.base + 0x1b2e5a0) return value;
    value.scene = scene;
    const Address main = h.get<Address>(scene + 0x328);
    if (!member(tree, main)) return value;
    if (tree.has_modal) {
        if (value.signed_in_known && value.signed_in && management(h, scene, tree, value)) return value;
        if (h.fault) return value;
        const Address terms = login_terms_required(h, scene, tree);
        if (terms) {
            value.kind = "login_terms_required"; value.modal = terms;
            value.button = terms_agree_button(h, scene, terms, tree, &value.closure);
            value.can_accept_terms = value.button != 0;
            return value;
        }
    }
    if (!tree.has_modal) {
        const Address button = child(h, tree, main, "networkButton", 0x1a8ece0);
        const Address closure = callback(h, button, 0x1ad9788, 0x847f98, 0x10);
        if (closure && h.get<Address>(closure + 8) == scene && !h.fault) {
            value.kind = "main_menu"; value.blocked = false; value.can_open = true;
            value.root = main; value.button = button; value.closure = closure;
        }
        return value;
    }
    const Address modal = tree.modal;
    if (!member(tree, modal) || !h.readable(modal, 0x310)
        || h.get<Address>(modal) != module.base + 0x1b503d8
        || h.get<unsigned char>(modal + 0x1c0) != 1 || h.get<unsigned char>(modal + 0x1c1) != 1) return value;
    // Any additional modal or loading object blocks account dispatch.
    for (Size i = 0; i < tree.count; ++i) {
        const Address node = tree.queue[i].node;
        if (node == modal || node == scene || h.get<unsigned char>(node + 0x1c1) != 1) continue;
        char klass[240] = {};
        if (!ui_class(h.get<Address>(node), klass)) return value;
        if (strstr(klass, "Dialog") || strstr(klass, "Overlay") || strstr(klass, "Popup")
            || strstr(klass, "Loading") || strstr(klass, "Transition")) return value;
    }
    const Address root = h.get<Address>(modal + 0x2d8);
    if (!member(tree, root) || h.get<unsigned char>(root + 0x1c1) != 1) return value;
    value.modal = modal; value.root = root;
    const Address login = child(h, tree, root, "login_button", 0x1a8ece0);
    if (login) {
        const Address closure = callback(h, login, 0x1b93718, 0xba307c, 0x38);
        if (closure && h.get<Address>(closure + 8) == modal && h.get<Address>(closure + 0x10) == scene
            && h.get<Address>(closure + 0x18) == scene + 0x308 && !h.fault) {
            value.kind = "logged_out_menu"; value.blocked = false; value.can_login_open = true;
            value.button = login; value.closure = closure;
        }
        return value;
    }
    const Address username = child(h, tree, root, "username_field", 0x1aea538);
    const Address password = child(h, tree, root, "password_field", 0x1aea538);
    const Address submit = child(h, tree, root, "confirm_button", 0x1a8ece0);
    if (username || password) {
        value.kind = "login";
        const Address closure = callback(h, submit, 0x1a87cd8, 0xca27a8, 0x50);
        if (!field(h, username) || !field(h, password) || !closure
            || h.get<Address>(closure + 8) != modal || h.get<Address>(closure + 0x18) != scene
            || h.get<Address>(closure + 0x20) != scene + 0x308
            || h.get<Address>(closure + 0x30) != password || h.get<Address>(closure + 0x38) != username
            || h.get<Address>(closure + 0x40) != submit || h.fault) return value;
        value.blocked = false; value.can_fill = true; value.can_submit = true;
        value.username = username; value.password = password; value.button = submit; value.closure = closure;
        login_error(h, tree, value);
        return value;
    }
    if (value.signed_in_known && value.signed_in && h.readable(root, 0x2b0)
        && h.get<Address>(root) == module.base + 0x1b2d7b0) {
        const Address content = h.get<Address>(root + 0x2a8);
        const Address sync = child(h, tree, content, "sync_button", 0x1a8ece0);
        const Address closure = callback(h, sync, 0x1b6f640, 0x172fff8, 0x10);
        if (member(tree, content, root) && closure && h.get<Address>(closure + 8) == root && !h.fault) {
            value.kind = "logged_in_menu"; value.blocked = false;
            const Address button = child(h, tree, content, "account_management_button", 0x1a8ece0);
            const Address management_closure = callback(h, button, 0x1ac75b0, 0x11b6808, 0x10);
            if (management_closure && h.get<Address>(management_closure + 8) == root
                && h.readable(root, 0x2b8) && h.get<Address>(root + 0x2b0) == modal
                && h.get<unsigned char>(modal + 0x308) == 0 && !h.fault) {
                value.can_management_open = true; value.button = button; value.closure = management_closure;
            }
        }
    }
    return value;
}
inline void write_state(akaine_cli::Json& json, const AccountView& value) {
    json.add("{\"kind\":"); json.string(value.kind);
    json.add(",\"signed_in\":"); json.add(value.signed_in_known ? (value.signed_in ? "true" : "false") : "null");
    json.add(",\"blocked\":"); json.add(value.blocked ? "true" : "false");
    json.add(",\"can_open\":"); json.add(value.can_open ? "true" : "false");
    json.add(",\"can_login_open\":"); json.add(value.can_login_open ? "true" : "false");
    json.add(",\"can_fill\":"); json.add(value.can_fill ? "true" : "false");
    json.add(",\"can_submit\":"); json.add(value.can_submit ? "true" : "false");
    json.add(",\"can_accept_terms\":"); json.add(value.can_accept_terms ? "true" : "false");
    json.add(",\"can_management_open\":"); json.add(value.can_management_open ? "true" : "false");
    json.add(",\"can_logout\":"); json.add(value.can_logout ? "true" : "false");
    json.add(",\"error_code\":"); if (value.error_code) json.string(value.error_code); else json.add("null");
    json.add(",\"error_text\":"); if (value.error_text) json.string(value.error_text); else json.add("null"); json.add("}");
}
inline Result dispatch(const AccountView& value, bool ready) {
    if (!official_thread()) return Result::blocked;
    if (!pins()) return Result::pin_mismatch;
    if (!ready || value.blocked || !value.button || !value.closure) return Result::unavailable;
    OfficialHost host;
    if (!cli_dispatch_allowed()) return Result::blocked;
    host.call<void>(0xf66c9c, value.button);
    return host.fault ? Result::fault : Result::ok;
}
inline Result open(Reader& h, Address scene, const UiTree& tree) {
    const AccountView value = inspect(h, scene, tree); return dispatch(value, value.can_open);
}
inline Result login_open(Reader& h, Address scene, const UiTree& tree) {
    const AccountView value = inspect(h, scene, tree); return dispatch(value, value.can_login_open);
}
inline Result management_open(Reader& h, Address scene, const UiTree& tree) {
    const AccountView value = inspect(h, scene, tree); return dispatch(value, value.can_management_open);
}
inline Result logout(Reader& h, Address scene, const UiTree& tree) {
    const AccountView value = inspect(h, scene, tree); return dispatch(value, value.can_logout);
}
inline bool logout_confirmed(const AccountView& account, bool ready, bool transition,
                             bool overlays_complete, bool overlays_blocked) {
    return ready && !transition && account.signed_in_known && !account.signed_in
        && !account.blocked && account.can_open && !strcmp(account.kind, "main_menu")
        && overlays_complete && !overlays_blocked;
}
inline bool valid_input(const char* text, Size size) {
    if (!text || !size || size > 256 || text[size] != 0) return false;
    for (Size i = 0; i < size;) {
        const unsigned char first = static_cast<unsigned char>(text[i++]);
        if (first < 0x20 || first == 0x7f) return false;
        if (first < 0x80) continue;
        const Size remaining = first >= 0xc2 && first <= 0xdf ? 1
            : first >= 0xe0 && first <= 0xef ? 2 : first >= 0xf0 && first <= 0xf4 ? 3 : 0;
        if (!remaining || size - i < remaining) return false;
        const unsigned char second = static_cast<unsigned char>(text[i]);
        if ((first == 0xe0 && second < 0xa0) || (first == 0xed && second >= 0xa0)
            || (first == 0xf0 && second < 0x90) || (first == 0xf4 && second >= 0x90)) return false;
        for (Size n = 0; n < remaining; ++n)
            if ((static_cast<unsigned char>(text[i++]) & 0xc0) != 0x80) return false;
    }
    return true;
}
inline void wipe(void* data, Size size) {
    volatile unsigned char* bytes = static_cast<volatile unsigned char*>(data);
    while (size--) *bytes++ = 0;
}
inline bool set_field(Address node, const char* text, Size size) {
    OfficialHost host;
    ModString input;
    host.call<void>(0x1a6dba0, Address(&input), Address(text));
    host.call<void>(0x120e99c, node, Address(&input));
    const Address current = host.call<Address>(0xe160e0, node);
    bool equal = false;
    Reader reader;
    if (!host.fault && reader.readable(current, 24)) {
        const unsigned char tag = reader.get<unsigned char>(current);
        const Size length = tag & 1 ? reader.get<Size>(current + 8) : Size(tag >> 1);
        const Address bytes = tag & 1 ? reader.get<Address>(current + 16) : current + 1;
        equal = !reader.fault && length == size && reader.readable(bytes, length + 1)
            && !memcmp(reinterpret_cast<const void*>(bytes), text, size + 1);
    }
    // Destroy the native temporary after wiping its allocation. The form keeps its ordinary native copy.
    if (input.bytes[0] & 1) {
        Address data = 0; memcpy(&data, input.bytes + 16, sizeof(data));
        if (process_readable(data, size + 1, true)) wipe(reinterpret_cast<void*>(data), size + 1);
        OfficialHost cleanup;
        mod_destroy_string(cleanup, input);
    }
    wipe(&input, sizeof(input));
    return equal && !host.fault;
}
inline Result fill_login(Reader& h, Address scene, const UiTree& tree,
                         const char* username, Size username_size, const char* password, Size password_size) {
    if (!official_thread()) return Result::blocked;
    if (!pins()) return Result::pin_mismatch;
    const AccountView value = inspect(h, scene, tree);
    if (!value.can_fill) return Result::unavailable;
    if (!valid_input(username, username_size) || !valid_input(password, password_size)) return Result::field_rejected;
    if (!cli_dispatch_allowed()) return Result::blocked;
    if (!set_field(value.username, username, username_size) || !set_field(value.password, password, password_size)) {
        set_field(value.username, "", 0); set_field(value.password, "", 0);
        return Result::field_rejected;
    }
    return Result::ok;
}
inline Result submit_login(Reader& h, Address scene, const UiTree& tree, SubmitCycle* cycle = nullptr) {
    if (cycle) *cycle = {};
    const AccountView value = inspect(h, scene, tree);
    const Result result = dispatch(value, value.can_submit);
    if (cycle && result == Result::ok) cycle->observe_busy(h, value);
    return result;
}
inline Result accept_terms(Reader& h, Address scene, const UiTree& tree) {
    if (!official_thread()) return Result::blocked;
    if (!pins()) return Result::pin_mismatch;
    const AccountView value = inspect(h, scene, tree);
    if (strcmp(value.kind, "login_terms_required") || !value.can_accept_terms) return Result::unavailable;
    OfficialHost host;
    if (!cli_dispatch_allowed()) return Result::blocked;
    host.call<void>(0xf66c9c, value.button);
    return host.fault ? Result::fault : Result::ok;
}
} // namespace account_controls
