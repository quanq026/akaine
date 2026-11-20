#pragma once
#include "cli_song_pins.h"

// Include inside staging_cli after Reader. These functions require the caller's
// fresh scene/modal/context and request-deadline checks on the owning GL thread.
struct CliSongState {
    Address scene = 0, access = 0, state = 0, layer = 0, selected = 0, pack = 0;
    Address pairs_begin = 0, pairs_end = 0;
    unsigned difficulty = 0, selected_difficulty = 0, sort = 0, group = 0, reverse = 0;
    bool valid = false, filter_open = false, pack_open = false;
    char song[65] = {}, pack_id[65] = {};
};

bool cli_song_pins() {
    for (const auto& pin : CLI_SONG_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}

bool cli_song_id(Reader& h, Address object, char (&out)[65]) {
    if (!h.readable(object, 24)) return false;
    const unsigned char tag = h.get<unsigned char>(object);
    const Size size = tag & 1 ? h.get<Size>(object + 8) : Size(tag >> 1);
    const Address data = tag & 1 ? h.get<Address>(object + 16) : object + 1;
    if (!size || size > 64 || !h.readable(data, size + 1)) return false;
    const char* text = reinterpret_cast<const char*>(data);
    for (Size i = 0; i < size; ++i) {
        const char c = text[i];
        if (!(c >= 'a' && c <= 'z') && !(c >= 'A' && c <= 'Z')
            && !(c >= '0' && c <= '9') && c != '_' && c != '-') return false;
    }
    if (text[size] || h.fault) return false;
    memcpy(out, text, size + 1);
    return true;
}

CliSongState cli_song_capture(Reader& h, Address scene) {
    CliSongState out;
    if (!h.readable(scene, 0x3b0) || h.get<Address>(scene) != module.base + 0x1ad2260
        || h.get<unsigned char>(scene + 0x1c0) != 1 || h.get<unsigned char>(scene + 0x1c1) != 1) return out;
    const unsigned char pack_open = h.get<unsigned char>(scene + 0x391);
    if (pack_open > 1) return out;
    const Address access = h.get<Address>(scene + 0x368), layer = h.get<Address>(scene + 0x3a0);
    if (!h.readable(access, 0x30) || !h.readable(layer, 0x449)
        || h.get<Address>(layer) != module.base + 0x1ad50d8
        || h.get<Address>(layer + 0x330) != access
        || h.get<Address>(access + 0x10) != layer + 0x2c8) return out;
    const Address layer_parent = h.get<Address>(layer + 0x148);
    const unsigned char layer_running = h.get<unsigned char>(layer + 0x1c0);
    if (pack_open) {
        // Native Pack Select removes SelectedSongLayer from the scene but keeps
        // its exact state-access delegate. Its stopped/null-parent state is
        // valid only while the scene-owned PackListLayer is running and visible.
        const Address pack_layer = h.get<Address>(scene + 0x3a8);
        if (layer_parent || layer_running != 0 || !h.readable(pack_layer, 0x440)
            || h.get<Address>(pack_layer) != module.base + 0x1b828b8
            || h.get<Address>(pack_layer + 0x148) != scene
            || h.get<unsigned char>(pack_layer + 0x1c0) != 1
            || h.get<unsigned char>(pack_layer + 0x1c1) != 1) return out;
    } else if (layer_parent != scene || layer_running != 1) return out;
    const Address state = h.get<Address>(access);
    if (!h.readable(state, 0xd0)) return out;
    const unsigned difficulty = h.get<unsigned>(state + 0x28), selected_difficulty = h.get<unsigned>(state + 0x38);
    const unsigned sort = h.get<unsigned>(state + 0x70), group = h.get<unsigned>(state + 0x74);
    const unsigned reverse = h.get<unsigned>(state + 0xcc);
    const Address begin = h.get<Address>(state + 0x50), end = h.get<Address>(state + 0x58), cap = h.get<Address>(state + 0x60);
    if (difficulty > 4 || selected_difficulty > 4 || sort > 5 || group > 5 || reverse > 1
        || end < begin || cap < end || (end - begin) % 16 || (cap - begin) % 16
        || cap - begin > 8192 * 16 || (end != begin && !h.readable(begin, end - begin))) return out;
    out.scene = scene; out.access = access; out.state = state; out.layer = layer;
    out.selected = h.get<Address>(state + 0x30);
    if (out.selected && !cli_song_id(h, out.selected, out.song)) return CliSongState{};
    out.pack = h.get<Address>(state + 0x48);
    if (out.pack && !cli_song_id(h, out.pack + 8, out.pack_id)) return CliSongState{};
    if (!out.pack) memcpy(out.pack_id, "all", 4);
    out.pairs_begin = begin; out.pairs_end = end;
    out.difficulty = difficulty; out.selected_difficulty = selected_difficulty;
    out.sort = sort; out.group = group; out.reverse = reverse;
    out.filter_open = h.get<Address>(layer + 0x438) != 0;
    out.pack_open = pack_open == 1;
    out.valid = !h.fault;
    return out;
}

Address cli_song_in_list(Reader& h, const CliSongState& state, const char* id, unsigned* difficulty) {
    Address result = 0;
    unsigned chosen = 0;
    for (Address at = state.pairs_begin; at < state.pairs_end; at += 16) {
        const Address song = h.get<Address>(at);
        const unsigned item_difficulty = h.get<unsigned>(at + 8);
        char candidate[65] = {};
        if (item_difficulty > 4 || !cli_song_id(h, song, candidate)) return 0;
        if (strcmp(candidate, id)) continue;
        if (result && result != song) return 0;
        if (!result || item_difficulty == state.difficulty) chosen = item_difficulty;
        result = song;
    }
    if (h.fault || !result) return 0;
    *difficulty = chosen;
    return result;
}

// w3=0 preserves native highlighting. The ordinary cell uses w3=1, which
// can activate an already-selected chart; that flag is intentionally absent.
const char* cli_song_select(Reader& h, Address scene, const char* id) {
    if (!official_thread() || !cli_song_pins()) return "NATIVE_GUARD";
    const CliSongState state = cli_song_capture(h, scene);
    if (!state.valid || state.filter_open || state.pack_open
        || h.get<unsigned char>(state.layer + 0x1c1) != 1) return "WRONG_SCENE";
    unsigned difficulty = 0;
    const Address song = cli_song_in_list(h, state, id, &difficulty);
    if (!song) return "SONG_NOT_IN_CURRENT_LIST";
    if (state.selected == song && state.selected_difficulty == difficulty) return nullptr;
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost call;
    call.call<void>(0xfae834, state.access, song, uint32_t(difficulty), uint32_t(0), uint32_t(0),
                    uint32_t(1), uint32_t(0), uint32_t(0), int32_t(-1));
    return call.fault ? "NATIVE_GUARD" : nullptr;
}

// Native dialog setter rebuilds the real song list and persists the ordinary
// preference. It accepts the same six choices exposed by both button columns.
const char* cli_song_sort_group(Reader& h, Address scene, unsigned sort, unsigned group, unsigned reverse) {
    if (sort > 5 || group > 5 || reverse > 1) return "INVALID_ARGUMENT";
    if (!official_thread() || !cli_song_pins()) return "NATIVE_GUARD";
    const CliSongState state = cli_song_capture(h, scene);
    if (!state.valid || state.filter_open || state.pack_open
        || h.get<unsigned char>(state.layer + 0x1c1) != 1) return "WRONG_SCENE";
    if (state.sort == sort && state.group == group && state.reverse == reverse) return nullptr;
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost call;
    call.call<void>(0x181a7d4, state.access, uint32_t(sort), uint32_t(group), uint32_t(reverse));
    return call.fault ? "NATIVE_GUARD" : nullptr;
}

Address cli_song_difficulty_button(Reader& h, const CliSongState& state, unsigned difficulty) {
    const Address begin = h.get<Address>(state.layer + 0x340), end = h.get<Address>(state.layer + 0x348);
    const Address cap = h.get<Address>(state.layer + 0x350);
    if (difficulty > 4 || end < begin || cap < end || end - begin != 5 * 8
        || cap - begin > 256 || !h.readable(begin, 5 * 8)) return 0;
    const Address button = h.get<Address>(begin + difficulty * 8);
    if (!h.readable(button, 0x449) || h.get<Address>(button) != module.base + 0x1a8ece0
        || h.get<unsigned char>(button + 0x1c0) != 1 || h.get<unsigned char>(button + 0x1c1) != 1
        || h.get<unsigned char>(button + 0x312) != 1 || h.get<unsigned char>(button + 0x314) != 1
        || h.get<unsigned char>(button + 0x448) != 0) return 0;
    const Address closure = h.get<Address>(button + 0x3d0);
    if (!h.readable(closure, 0x18) || h.get<Address>(closure) != module.base + 0x1b52a20
        || h.get<Address>(closure + 8) != state.layer || h.get<unsigned>(closure + 16) != difficulty) return 0;
    Address ancestor = h.get<Address>(button + 0x148);
    for (unsigned depth = 0; ancestor && depth < 16; ++depth) {
        if (ancestor == state.layer) return h.fault ? 0 : button;
        if (!h.readable(ancestor, 0x1c2) || h.get<unsigned char>(ancestor + 0x1c1) != 1) return 0;
        const Address parent = h.get<Address>(ancestor + 0x148);
        if (parent == ancestor) return 0;
        ancestor = parent;
    }
    return 0;
}

const char* cli_song_difficulty(Reader& h, Address scene, unsigned difficulty) {
    if (difficulty > 4) return "INVALID_ARGUMENT";
    if (!official_thread() || !cli_song_pins()) return "NATIVE_GUARD";
    const CliSongState state = cli_song_capture(h, scene);
    if (!state.valid || state.filter_open || state.pack_open
        || h.get<unsigned char>(state.layer + 0x1c1) != 1) return "WRONG_SCENE";
    if (state.difficulty == difficulty) return nullptr;
    const Address button = cli_song_difficulty_button(h, state, difficulty);
    if (!button) return "DIFFICULTY_UNAVAILABLE";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost call;
    call.call<void>(0x13a3860, state.layer, uint32_t(difficulty), button);
    return call.fault ? "NATIVE_GUARD" : nullptr;
}

bool cli_pack_layer(Reader& h, const CliSongState& state) {
    const Address layer = h.get<Address>(state.scene + 0x3a8);
    return state.pack_open && h.readable(layer, 0x440)
        && h.get<Address>(layer) == module.base + 0x1b828b8
        && h.get<Address>(layer + 0x148) == state.scene
        && h.get<unsigned char>(layer + 0x1c0) == 1
        && h.get<unsigned char>(layer + 0x1c1) == 1 && !h.fault;
}

// Resolves existing native packs only. The native handler keeps its own
// special-mode guard, selects the pack, and closes an open pack selector.
const char* cli_pack_select(Reader& h, Address scene, const char* id) {
    const Size size = strlen(id);
    if (!size || size > 64) return "INVALID_ARGUMENT";
    for (Size i = 0; i < size; ++i) {
        const char c = id[i];
        if (!(c >= 'a' && c <= 'z') && !(c >= 'A' && c <= 'Z')
            && !(c >= '0' && c <= '9') && c != '_' && c != '-') return "INVALID_ARGUMENT";
    }
    if (!official_thread() || !cli_song_pins()) return "NATIVE_GUARD";
    const CliSongState state = cli_song_capture(h, scene);
    if (!state.valid || state.filter_open || !cli_pack_layer(h, state)) return "WRONG_SCENE";
    Address pack = 0;
    OfficialHost call;
    if (strcmp(id, "all")) {
        const Address slot = h.get<Address>(module.base + 0x1b95f58);
        if (!h.readable(slot, 8)) return "NATIVE_GUARD";
        const Address context = h.get<Address>(slot);
        if (!h.readable(context, 0x28)) return "NATIVE_GUARD";
        const Address manager = h.get<Address>(context + 0x20);
        if (!h.readable(manager, 0x90)) return "NATIVE_GUARD";
        struct alignas(8) NativeString { unsigned char bytes[24] = {}; } text;
        static_assert(sizeof(text) == 24);
        call.call<void>(0x1a6dba0, Address(&text), id);
        if (call.fault) return "NATIVE_GUARD";
        pack = call.call<Address>(0x193b304, manager, Address(&text));
        if (text.bytes[0] & 1) {
            Address allocated = 0; memcpy(&allocated, text.bytes + 16, sizeof(allocated));
            call.call<void>(0x1a6d9e0, allocated);
        }
        char actual[65] = {};
        if (call.fault || !h.readable(pack, 0xc8) || !cli_song_id(h, pack + 8, actual)
            || strcmp(actual, id)) return "PACK_NOT_FOUND";
    }
    if (!cli_dispatch_allowed()) return "EXPIRED";
    call.call<void>(0x7b7680, scene, pack, uint32_t(state.difficulty), Address(0));
    return call.fault ? "NATIVE_GUARD" : nullptr;
}

// Same native close sequence used by the ordinary pack-selection handler.
const char* cli_pack_close(Reader& h, Address scene) {
    if (!official_thread() || !cli_song_pins()) return "NATIVE_GUARD";
    const CliSongState state = cli_song_capture(h, scene);
    if (!state.valid || state.filter_open || !cli_pack_layer(h, state)) return "WRONG_SCENE";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost call;
    call.call<void>(0x1326458, scene);
    if (!call.fault) call.call<void>(0xb69d74, scene);
    return call.fault ? "NATIVE_GUARD" : nullptr;
}

