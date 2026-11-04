#pragma once

// Included inside overlay_cli after its exact reader/listener helpers.
namespace pack_tutorial71 {
constexpr Address VTABLE = 0x1abcc10;
constexpr Address TOUCH_INVOKE = 0x85ef60;
constexpr Address PARTNER_DIALOG = 0x1af6790;
constexpr const char* TEXT[] = {
    "Song Packs are organized by category. Scroll the category panel vertically\n"
    "to switch the current category, and horizontally to browse the Packs within.",
    "Alternatively, quickly toggle between categories\nby tapping the left category buttons. "
};
constexpr const char* PARTNER_TEXT[] = {
    "Select the desired Partner by scrolling from the list on the left.\n"
    "Find Partners easily by tapping the Filter icon or entering a name in the Search bar.",
    "Select an obtained Partner to level up, switch between base and\n"
    "Awakened forms, or add to favorites by tapping their icon once more.",
    "Selecting an unobtained Partner will preview their Skill and max level stats."
};

inline bool pins() {
    for (const auto& pin : CLI_PACK_TUTORIAL_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    Address invoke = 0;
    return static_pointer(module.base + 0x1b994e8 + 0x30, &invoke) && invoke == module.base + TOUCH_INVOKE;
}

inline bool text(Reader& h, Address at, const char* expected) {
    if (!h.readable(at, 24)) return false;
    const unsigned char tag = h.get<unsigned char>(at);
    const Size length = tag & 1 ? h.get<Size>(at + 8) : Size(tag >> 1);
    const Address data = tag & 1 ? h.get<Address>(at + 16) : at + 1;
    return length == strlen(expected) && h.readable(data, length + 1)
        && !memcmp(reinterpret_cast<const void*>(data), expected, length + 1) && !h.fault;
}

inline Address partner_owner(Reader& h, Address scene) {
    const Address type = h.get<Address>(scene);
    if (!h.readable(scene, 0x3b0) || type != module.base + 0x1b3a8c0) return 0;
    const Address vector = h.get<Address>(scene + 0x140);
    if (!h.readable(vector, 24)) return 0;
    const Address begin = h.get<Address>(vector), end = h.get<Address>(vector + 8), capacity = h.get<Address>(vector + 16);
    if (end < begin || capacity < end || (end - begin) % 8 || (capacity - begin) % 8
        || capacity - begin > 1024 * 8 || !h.readable(begin, end - begin)) return 0;
    Address dialog = 0;
    for (Address at = begin; at < end; at += 8) {
        const Address child = h.get<Address>(at);
        if (!h.readable(child, 0x1da) || h.get<Address>(child + 0x148) != scene) return 0;
        if (h.get<Address>(child) != module.base + PARTNER_DIALOG) continue;
        if (dialog || !exact(h, child, 0x2f0, PARTNER_DIALOG)) return 0;
        dialog = child;
    }
    if (!dialog) return 0;
    const Address aside = h.get<Address>(dialog + 0x2d0), bside = h.get<Address>(dialog + 0x2d8);
    if (!exact(h, aside, 0x610, 0x1b324a0) || !exact(h, bside, 0x4e0, 0x1b4f128)
        || h.get<Address>(aside + 0x148) != dialog || h.get<Address>(bside + 0x148) != dialog
        || h.get<Address>(aside + 0x5c8) != dialog || h.get<Address>(bside + 0x4d8) != dialog) return 0;
    bool running = false, visible = false, aside_running = false, aside_visible = false;
    if (!flag(h, dialog + 0x1c0, &running) || !flag(h, dialog + 0x1c1, &visible)
        || !flag(h, aside + 0x1c0, &aside_running) || !flag(h, aside + 0x1c1, &aside_visible)
        || !running || !visible || !aside_running || !aside_visible || h.fault) return 0;
    return dialog;
}

inline bool capture(Reader& h, Address scene, Address guide, bool ancestors_visible, bool ancestors_running, Item& item) {
    if (!pins() || !exact(h, guide, 0x370, VTABLE)
        || h.get<Address>(guide + 0x148) != scene) return false;
    bool running = false, visible = false, owner_running = false, closing = false;
    if (!flag(h, guide + 0x1c0, &running) || !flag(h, guide + 0x1c1, &visible)
        || !flag(h, guide + 0x348, &closing)) return false;
    const Address begin = h.get<Address>(guide + 0x350), end = h.get<Address>(guide + 0x358);
    const Address capacity = h.get<Address>(guide + 0x360);
    const int index = h.get<int>(guide + 0x368);
    if (end < begin || capacity < end || (end - begin != 48 && end - begin != 72) || (capacity - begin) % 24
        || capacity - begin > 128 * 24 || !h.readable(begin, end - begin) || index < 0
        || h.get<Address>(guide + 0x2f0) || h.get<Address>(guide + 0x320)) return false;
    const Size count = (end - begin) / 24;
    const bool partner = count == 3;
    if (Size(index) > count) return false;
    for (Size i = 0; i < count; ++i)
        if (!text(h, begin + i * 24, partner ? PARTNER_TEXT[i] : TEXT[i])) return false;
    if (partner) {
        item.gate = partner_owner(h, scene);
        if (!item.gate) return false;
        owner_running = true;
    } else {
        if (!exact(h, scene, 0x3b0, 0x1b3a8c0)) return false;
        const Address pack = h.get<Address>(scene + 0x3a8);
        if (!exact(h, pack, 0x470, 0x1b30540) || h.get<Address>(pack + 0x148) != scene
            || !flag(h, pack + 0x1c0, &owner_running)) return false;
    }
    const Address overlay = h.get<Address>(guide + 0x330);
    if (!speed_listener(h, overlay, guide, item) || h.get<Address>(overlay + 0x300)
        || h.get<Address>(overlay + 0x308)) return false;
    bool overlay_running = false, release_on_begin = false, release_on_end = false;
    if (!flag(h, overlay + 0x1c0, &overlay_running) || !flag(h, overlay + 0x321, &release_on_begin)
        || !flag(h, overlay + 0x322, &release_on_end) || release_on_begin || !release_on_end) return false;
    item.callback = h.get<Address>(overlay + 0x2f0);
    if (!exact(h, item.callback, 0x18, 0x1b994e8) || h.get<Address>(item.callback + 8) != guide
        || h.get<Address>(item.callback + 0x10) != guide) return false;
    item.banner = h.get<Address>(guide + 0x340);
    if (!h.readable(item.banner, 0x1da) || !module_readable(h.get<Address>(item.banner), sizeof(Address))
        || h.get<Address>(item.banner + 0x148) != guide) return false;
    bool banner_visible = false, banner_running = false;
    if (!flag(h, item.banner + 0x1c0, &banner_running) || !flag(h, item.banner + 0x1c1, &banner_visible)) return false;
    item.id = partner ? "partner_selection_hint" : "pack_selection_hint";
    item.node = guide; item.advance_invoke = TOUCH_INVOKE;
    item.active = ancestors_running && running;
    item.visible = ancestors_visible && visible && banner_visible;
    item.opacity = h.get<unsigned char>(item.banner + 0x1d0);
    item.step_index = Size(index); item.pending_steps = count - item.step_index;
    item.owner_validated = true; item.callback_owned = true;
    item.advance_ready = !closing && Size(index) < count && owner_running && overlay_running && banner_running;
    item.can_advance = item.advance_ready && item.active && item.blocks_input;
    return !h.fault;
}

template<class Tree> bool partner_modal_only(Reader& h, Address scene, const Tree& tree, const View& overlays) {
    if (!tree.valid || tree.loading || !tree.has_modal || tree.count > 1024 || !overlays.complete || overlays.count != 1) return false;
    const Item& item = overlays.items[0];
    if (strcmp(item.id, "partner_selection_hint") || !item.can_advance || !item.owner_validated || !item.callback_owned
        || item.advance_invoke != TOUCH_INVOKE || !item.gate || tree.modal != item.gate || tree.modal_type != module.base + PARTNER_DIALOG
        || partner_owner(h, scene) != item.gate) return false;
    const Address aside = h.get<Address>(item.gate + 0x2d0), bside = h.get<Address>(item.gate + 0x2d8);
    for (Size i = 0; i < tree.count; ++i) {
        const Address node = tree.queue[i].node;
        if (node == scene || node == item.node || node == item.gate || node == aside || node == bside
            || h.get<unsigned char>(node + 0x1c1) != 1) continue;
        char klass[240] = {}; bool game = false;
        if (!scene_type_name(h.get<Address>(node), klass, sizeof(klass), &game)
            || strstr(klass, "Dialog") || strstr(klass, "Overlay") || strstr(klass, "Popup")
            || strstr(klass, "Loading") || strstr(klass, "Transition")) return false;
    }
    return !h.fault;
}

template<class Ui, class Character> bool character_open_completed(Reader& h, Address scene, Address expected_scene,
        bool ready, bool transition, const Ui& ui, const Character& character) {
    if (!ready || transition || scene != expected_scene || !character.available || character.scene != scene
        || !character.dialog || !character.select_callback || !character.blocked || !character.reason
        || strcmp(character.reason, "input_blocked") || !ui.identity.available || ui.identity.scene != scene
        || !ui.modal_present || !ui.context || !ui.reason || strcmp(ui.reason, "input_blocked")
        || !ui.overlays.complete || !ui.overlays.blocked || ui.overlays.count != 1
        || ui.action_count != 1 || ui.identity.count != 1) return false;
    const Item& item = ui.overlays.items[0];
    const auto& action = ui.actions[0];
    if (strcmp(item.id, "partner_selection_hint") || !item.active || !item.blocks_input || !item.advance_ready
        || !item.can_advance || !item.owner_validated || !item.callback_owned || item.advance_invoke != TOUCH_INVOKE
        || item.gate != character.dialog || ui.identity.modal != character.dialog
        || ui.identity.modal_type != module.base + PARTNER_DIALOG || !action.name
        || strcmp(action.name, "partner_hint_continue") || action.node != item.node || action.closure != item.callback
        || ui.identity.nodes[0] != item.node || ui.identity.callbacks[0] != item.callback
        || partner_owner(h, scene) != character.dialog || character.aside != h.get<Address>(character.dialog + 0x2d0)) return false;
    return !h.fault;
}

inline const char* advance(Reader& h, const Item& item) {
    if (!official_thread() || !pins() || !item.can_advance || item.advance_invoke != TOUCH_INVOKE
        || !exact(h, item.node, 0x370, VTABLE)) return "NATIVE_GUARD";
    // The complete pinned invoke reads only its closure; Ref/Event arguments are unused.
    OfficialHost call;
    call.call<void>(TOUCH_INVOKE, item.callback);
    return call.fault ? "NATIVE_GUARD" : nullptr;
}

inline bool progressed(const View& before, const View& after) {
    if (!before.complete || before.count != 1 || !after.complete || after.count > 1) return false;
    const Item& old = before.items[0];
    for (Size i = 0; i < after.count; ++i) {
        const Item& item = after.items[i];
        if (item.node != old.node) continue;
        // Closing starts before native fade/removal finishes; wait for removal on the final step.
        return item.advance_invoke == TOUCH_INVOKE && item.owner_validated && item.callback_owned
            && item.callback == old.callback && item.gate == old.gate && !strcmp(item.id, old.id) && item.advance_ready
            && item.step_index == old.step_index + 1 && item.pending_steps + 1 == old.pending_steps;
    }
    return after.count == 0;
}
}
