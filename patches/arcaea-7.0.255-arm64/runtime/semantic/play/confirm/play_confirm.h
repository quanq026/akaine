#pragma once
#include "play_confirm_pins.h"

bool cli_play_download_pins() {
    if (!cli_play_pins()) return false;
    for (const auto& pin : CLI_PLAY_DOWNLOAD_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
bool cli_download_pointer(Address at, Address expected) {
    Address actual = 0;
    return static_pointer(module.base + at, &actual) && actual == module.base + expected;
}
bool cli_download_member(Reader& h, const UiTree& tree, Address node, Address parent) {
    for (Size i = 0; i < tree.count; ++i)
        if (tree.queue[i].node == node && tree.queue[i].parent == parent)
            return h.get<Address>(node + 0x148) == parent;
    return false;
}
// Match only the native one-song DownloadManager prompt for the highlighted song.
const char* cli_song_download_prompt(Reader& h, Address scene, const char* expected, const CliUiState& ui, Address* target) {
    if (!official_thread() || !cli_play_download_pins()) return "NATIVE_GUARD";
    if (!ui.context || !ui.identity.available || ui.identity.scene != scene
        || ui.identity.scene_type != module.base + 0x1ad2260 || !ui.modal_present || !ui.identity.modal)
        return "DOWNLOAD_PROMPT_UNAVAILABLE";
    if (!ui.overlays.complete) return "OVERLAY_SCAN_INCOMPLETE";
    if (ui.overlays.blocked) return "INPUT_BLOCKED";
    const CliSongState state = cli_song_capture(h, scene);
    if (!state.valid || state.filter_open || state.pack_open) return "WRONG_SCENE";
    if (!state.selected || strcmp(state.song, expected) || state.difficulty != state.selected_difficulty)
        return "SELECTION_CHANGED";
    unsigned difficulty = 0;
    if (cli_song_in_list(h, state, expected, &difficulty) != state.selected || difficulty != state.selected_difficulty)
        return "SONG_NOT_IN_CURRENT_LIST";
    UiTree tree(h, scene, 0, h.get<Address>(scene + 0x380));
    const Address dialog = ui.identity.modal;
    if (!tree.valid || !tree.has_modal || tree.loading || tree.modal != dialog
        || ui.identity.modal_type != module.base + 0x1af8480
        || h.get<Address>(dialog) != module.base + 0x1af8480 || !h.readable(dialog, 0x328)
        || !cli_download_member(h, tree, dialog, scene) || h.get<unsigned char>(dialog + 0x302) != 0
        || h.get<unsigned char>(dialog + 0x1c0) != 1) return "DOWNLOAD_PROMPT_UNAVAILABLE";
    for (Size i = 0; i < tree.count; ++i) {
        const Address node = tree.queue[i].node;
        if (node == scene || node == dialog || h.get<unsigned char>(node + 0x1c1) != 1) continue;
        char klass[240] = {};
        if (!ui_class(h.get<Address>(node), klass)) return "NATIVE_GUARD";
        if (strstr(klass, "Dialog") || strstr(klass, "Overlay") || strstr(klass, "Popup")
            || strstr(klass, "Loading") || strstr(klass, "Transition")) return "DOWNLOAD_PROMPT_UNAVAILABLE";
    }
    const Address root = h.get<Address>(dialog + 0x308), button = h.get<Address>(dialog + 0x320);
    if (!cli_download_member(h, tree, root, dialog) || !cli_download_member(h, tree, button, root)
        || !ui_name(h, button, "button1") || !h.readable(button, 0x449)
        || h.get<Address>(button) != module.base + 0x1a8ece0 || h.get<unsigned char>(button + 0x1c0) != 1
        || h.get<unsigned char>(button + 0x1c1) != 1 || h.get<unsigned char>(button + 0x312) != 1
        || h.get<unsigned char>(button + 0x314) != 1 || h.get<unsigned char>(button + 0x448)
        || h.get<Address>(button + 0x398) || h.get<Address>(button + 0x3a0)
        || h.get<Address>(button + 0x3a8) || h.get<Address>(button + 0x3d0)) return "DOWNLOAD_PROMPT_UNAVAILABLE";
    const Address outer = h.get<Address>(button + 0x400), inner = h.get<Address>(outer + 0x40);
    if (!h.readable(outer, 0x48) || h.get<Address>(outer) != module.base + 0x1b4aec8
        || h.get<Address>(outer + 0x10) != dialog || !h.readable(inner, 0x70)
        || h.get<Address>(inner) != module.base + 0x1b892e8 || h.get<Address>(inner + 0x30) != scene
        || !cli_download_pointer(0x1b4aec8 + 0x30, 0x1411494)
        || !cli_download_pointer(0x1b892e8 + 0x30, 0xc8efa4)
        || !cli_download_pointer(0x1a8ece0 + 0x630, 0xf66c9c)) return "DOWNLOAD_PROMPT_UNAVAILABLE";
    const Address begin = h.get<Address>(inner + 0x18), end = h.get<Address>(inner + 0x20), cap = h.get<Address>(inner + 0x28);
    const Address continuation = h.get<Address>(inner + 0x60);
    if (!h.readable(begin, 8) || end != begin + 8 || cap < end || cap - begin > 256
        || h.get<Address>(begin) != state.selected || !h.readable(continuation, 0x10)
        || h.get<Address>(continuation) != module.base + 0x1b1c2c8 || h.get<Address>(continuation + 8) != scene
        || !cli_download_pointer(0x1b1c2c8 + 0x30, 0x1727c90) || h.fault) return "DOWNLOAD_PROMPT_UNAVAILABLE";
    *target = button;
    return nullptr;
}
// This typed dispatch requests download; it never reports gameplay success.
const char* cli_song_confirm_download(Reader& h, Address scene, const char* expected, const CliUiState& ui) {
    Address button = 0;
    if (const char* error = cli_song_download_prompt(h, scene, expected, ui, &button)) return error;
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost call;
    call.call<void>(0xf66c9c, button);
    return call.fault ? "NATIVE_GUARD" : nullptr;
}
