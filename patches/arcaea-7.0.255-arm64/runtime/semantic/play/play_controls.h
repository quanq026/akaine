#pragma once
#include "play_pins.h"

bool cli_play_pins() {
    if (!cli_song_pins()) return false;
    for (const auto& pin : CLI_PLAY_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}

// The caller supplies a fresh UI snapshot on the owning GL thread and confirms
// exact GameScene song/difficulty afterward; native prompts never mean success.
const char* cli_song_play(Reader& h, Address scene, const char* expected, const CliUiState& ui) {
    if (!official_thread() || !cli_play_pins()) return "NATIVE_GUARD";
    if (!ui.context || !ui.identity.available || ui.identity.scene != scene
        || ui.identity.scene_type != module.base + 0x1ad2260 || ui.modal_present || ui.identity.modal)
        return "UI_BLOCKED";
    if (!ui.overlays.complete) return "OVERLAY_SCAN_INCOMPLETE";
    if (ui.overlays.blocked) return "INPUT_BLOCKED";
    const CliSongState state = cli_song_capture(h, scene);
    if (!state.valid || state.filter_open || state.pack_open
        || h.get<unsigned char>(state.layer + 0x1c1) != 1) return "WRONG_SCENE";
    if (!state.selected || strcmp(state.song, expected) || state.difficulty != state.selected_difficulty)
        return "SELECTION_CHANGED";
    unsigned difficulty = 0;
    const Address listed = cli_song_in_list(h, state, expected, &difficulty);
    if (listed != state.selected || difficulty != state.selected_difficulty) return "SONG_NOT_IN_CURRENT_LIST";
    const Address delegate = h.get<Address>(state.access + 0x18);
    Address invoke = 0;
    if (delegate != scene + 0x308 || h.get<Address>(delegate) != module.base + 0x1ad29a8
        || !static_pointer(module.base + 0x1ad29a8 + 0x30, &invoke)
        || invoke != module.base + 0xa12308 || h.fault) return "NATIVE_GUARD";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost call;
    // Ordinary selected-cell activation enters native songSelected, preserving
    // its unlock, download, token and preplay checks.
    call.call<void>(0xfae834, state.access, state.selected, uint32_t(state.selected_difficulty), uint32_t(1),
                    uint32_t(0), uint32_t(1), uint32_t(0), uint32_t(0), int32_t(-1));
    return call.fault ? "NATIVE_GUARD" : nullptr;
}
