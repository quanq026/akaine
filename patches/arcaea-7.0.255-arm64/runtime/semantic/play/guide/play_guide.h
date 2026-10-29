#pragma once
#include "../confirm/play_confirm.h"
#include "play_guide_pins.h"

bool cli_play_guide_pins() {
    if (!cli_play_download_pins()) return false;
    for (const auto& pin : CLI_PLAY_GUIDE_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
// Recognize the registered Skip without dispatching; overlay priority is a separate guard.
const char* cli_song_advanced_guide_button(Reader& h, Address scene, const char* expected, const CliUiState& ui, Address* output) {
    if (!official_thread() || !cli_play_guide_pins()) return "NATIVE_GUARD";
    if (!ui.context || !ui.identity.available || ui.identity.scene != scene
        || ui.identity.scene_type != module.base + 0x1ad2260 || !ui.modal_present || !ui.identity.modal)
        return "ADVANCED_GUIDE_UNAVAILABLE";
    if (!ui.overlays.complete) return "OVERLAY_SCAN_INCOMPLETE";
    const CliSongState state = cli_song_capture(h, scene);
    if (!state.valid || state.filter_open || state.pack_open) return "WRONG_SCENE";
    if (!state.selected || strcmp(state.song, expected) || state.difficulty != state.selected_difficulty)
        return "SELECTION_CHANGED";
    unsigned difficulty = 0;
    if (cli_song_in_list(h, state, expected, &difficulty) != state.selected || difficulty != state.selected_difficulty)
        return "SONG_NOT_IN_CURRENT_LIST";
    UiTree tree(h, scene, 0, h.get<Address>(scene + 0x380));
    const Address dialog = ui.identity.modal, topbar = h.get<Address>(scene + 0x378);
    if (!tree.valid || !tree.has_modal || tree.loading || tree.modal != dialog
        || ui.identity.modal_type != module.base + 0x1af8480 || !h.readable(dialog, 0x310)
        || h.get<Address>(dialog) != module.base + 0x1af8480
        || !cli_download_member(h, tree, topbar, scene) || !cli_download_member(h, tree, dialog, topbar)
        || h.get<Address>(topbar) != module.base + 0x1a94648 || h.get<unsigned char>(topbar + 0x1c0) != 1
        || h.get<unsigned char>(topbar + 0x1c1) != 1 || h.get<unsigned char>(dialog + 0x302) != 0
        || h.get<unsigned char>(dialog + 0x1c0) != 1 || h.get<unsigned char>(dialog + 0x1c1) != 1)
        return "ADVANCED_GUIDE_UNAVAILABLE";
    const Address root = h.get<Address>(dialog + 0x308);
    if (!cli_download_member(h, tree, root, dialog) || h.get<unsigned char>(root + 0x1c0) != 1
        || h.get<unsigned char>(root + 0x1c1) != 1) return "ADVANCED_GUIDE_UNAVAILABLE";
    Address button = 0;
    for (Size i = 0; i < tree.count; ++i) {
        const Address node = tree.queue[i].node;
        if (node != scene && node != dialog && h.get<unsigned char>(node + 0x1c1) == 1) {
            char klass[240] = {};
            if (!ui_class(h.get<Address>(node), klass)) return "NATIVE_GUARD";
            if (strstr(klass, "Dialog") || strstr(klass, "Overlay") || strstr(klass, "Popup")
                || strstr(klass, "Loading") || strstr(klass, "Transition")) return "ADVANCED_GUIDE_UNAVAILABLE";
        }
        if (tree.queue[i].parent != root || !ui_name(h, node, "button2")) continue;
        if (button) return "ADVANCED_GUIDE_UNAVAILABLE";
        button = node;
    }
    if (!button || !cli_download_member(h, tree, button, root) || !h.readable(button, 0x449)
        || h.get<Address>(button) != module.base + 0x1a8ece0 || h.get<unsigned char>(button + 0x1c0) != 1
        || h.get<unsigned char>(button + 0x1c1) != 1 || h.get<unsigned char>(button + 0x312) != 1
        || h.get<unsigned char>(button + 0x314) != 1 || h.get<unsigned char>(button + 0x448)
        || h.get<Address>(button + 0x398) || h.get<Address>(button + 0x3a0)
        || h.get<Address>(button + 0x3a8) || h.get<Address>(button + 0x3d0)) return "ADVANCED_GUIDE_UNAVAILABLE";
    const Address outer = h.get<Address>(button + 0x400), inner = h.get<Address>(outer + 0x40);
    if (!h.readable(outer, 0x48) || h.get<Address>(outer) != module.base + 0x1ac34b0
        || h.get<Address>(outer + 0x10) != dialog || !h.readable(inner, 0x28)
        || h.get<Address>(inner) != module.base + 0x1acf880 || h.get<Address>(inner + 8) != scene
        || h.get<Address>(inner + 0x10) != state.selected || h.get<unsigned>(inner + 0x18) != state.selected_difficulty
        || h.get<unsigned>(inner + 0x1c) != 0 || h.get<Address>(inner + 0x20) != 0
        || !cli_download_pointer(0x1ac34b0 + 0x30, 0x11b1d84)
        || !cli_download_pointer(0x1acf880 + 0x30, 0x1870d58)
        || !cli_download_pointer(0x1ad2260 + 0x5f0, 0x13f3ce4)
        || !cli_download_pointer(0x1a8ece0 + 0x630, 0xf66c9c) || h.fault) return "ADVANCED_GUIDE_UNAVAILABLE";
    *output = button;
    return nullptr;
}
struct CliAdvancedGuide {
    bool available = false, can_skip = false;
    const char* reason = "not_present";
    const char* priority = "unavailable";
    char song[65] = {};
    unsigned difficulty = 0;
};
CliAdvancedGuide cli_capture_advanced_guide(Reader& h, Address scene, const CliUiState& ui) {
    CliAdvancedGuide result;
    if (!ui.modal_present) return result;
    const CliSongState song = cli_song_capture(h, scene);
    if (!song.valid || !song.song[0]) { result.reason = "wrong_scene"; return result; }
    Address button = 0;
    const char* error = cli_song_advanced_guide_button(h, scene, song.song, ui, &button);
    if (error) { result.reason = error; return result; }
    result.available = true;
    memcpy(result.song, song.song, sizeof(result.song)); result.difficulty = song.selected_difficulty;
    result.can_skip = !ui.overlays.blocked && ui.overlays.count == 0;
    result.reason = result.can_skip ? nullptr : "input_blocked";
    result.priority = result.can_skip ? "single_modal" : "unproven";
    // Existing topology validates owners, not touch order between the two layers.
    if (ui.overlays.count == 1 && !strcmp(ui.overlays.items[0].id, "pack_selection_hint"))
        result.reason = "pack_hint_priority_unproven";
    return result;
}
void cli_write_advanced_guide(akaine_cli::Json& json, const CliAdvancedGuide& value) {
    json.add("{\"available\":"); json.add(value.available ? "true" : "false");
    json.add(",\"can_skip\":"); json.add(value.can_skip ? "true" : "false");
    json.add(",\"reason\":"); if (value.reason) json.string(value.reason); else json.add("null");
    json.add(",\"priority\":"); json.string(value.priority);
    json.add(",\"song_id\":"); if (value.available) json.string(value.song); else json.add("null");
    json.add(",\"difficulty\":");
    if (value.available) { char text[16]; snprintf(text, sizeof(text), "%u", value.difficulty); json.add(text); }
    else json.add("null");
    json.add("}");
}
// Invoke only the normal Skip bound to the selected chart and an unblocked modal.
const char* cli_song_skip_advanced_guide(Reader& h, Address scene, const char* expected, const CliUiState& ui) {
    if (!official_thread() || !cli_play_guide_pins()) return "NATIVE_GUARD";
    if (!ui.overlays.complete) return "OVERLAY_SCAN_INCOMPLETE";
    if (ui.overlays.blocked || ui.overlays.count) return "INPUT_BLOCKED";
    Address button = 0;
    if (const char* error = cli_song_advanced_guide_button(h, scene, expected, ui, &button)) return error;
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost call;
    call.call<void>(0xf66c9c, button);
    return call.fault ? "NATIVE_GUARD" : nullptr;
}
