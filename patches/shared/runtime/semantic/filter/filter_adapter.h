#pragma once
// Native filter controls and validation of their encoded query input.
#include "filter_pins.h"
#include <stddef.h>
#include <stdint.h>

namespace akaine_filter {
constexpr size_t QUERY_LIMIT = 128;
inline bool valid_query(const char* text, size_t size) {
    if (!text || size > QUERY_LIMIT || text[size]) return false;
    for (size_t at = 0; at < size;) {
        const unsigned first = static_cast<unsigned char>(text[at++]);
        unsigned code = first;
        size_t tails = 0;
        if (first >= 0xc2 && first <= 0xdf) { tails = 1; code &= 0x1f; }
        else if (first >= 0xe0 && first <= 0xef) { tails = 2; code &= 0x0f; }
        else if (first >= 0xf0 && first <= 0xf4) { tails = 3; code &= 7; }
        else if (first >= 0x80) return false;
        if (size - at < tails) return false;
        for (size_t i = 0; i < tails; ++i) {
            const unsigned next = static_cast<unsigned char>(text[at++]);
            if ((next & 0xc0) != 0x80) return false;
            code = (code << 6) | (next & 0x3f);
        }
        if ((tails == 1 && code < 0x80) || (tails == 2 && code < 0x800)
            || (tails == 3 && code < 0x10000) || code > 0x10ffff
            || (code >= 0xd800 && code <= 0xdfff) || code < 0x20
            || (code >= 0x7f && code <= 0x9f)) return false;
    }
    return true;
}
// Canonical, unpadded base64url. Empty query is available only through reset.
inline bool decode_query(const char* encoded, size_t size, char (&output)[QUERY_LIMIT + 1], size_t* length) {
    output[0] = 0;
    if (length) *length = 0;
    if (!encoded || !length || !size || size > (QUERY_LIMIT * 8 + 5) / 6 || size % 4 == 1) return false;
    unsigned bits = 0, buffer = 0;
    size_t count = 0;
    for (size_t i = 0; i < size; ++i) {
        const unsigned char c = static_cast<unsigned char>(encoded[i]);
        const unsigned value = c >= 'A' && c <= 'Z' ? c - 'A'
            : c >= 'a' && c <= 'z' ? c - 'a' + 26
            : c >= '0' && c <= '9' ? c - '0' + 52 : c == '-' ? 62 : c == '_' ? 63 : 64;
        if (value == 64) return false;
        buffer = (buffer << 6) | value; bits += 6;
        if (bits >= 8) {
            bits -= 8;
            if (count == QUERY_LIMIT) return false;
            output[count++] = static_cast<char>((buffer >> bits) & 255);
        }
        buffer &= (1u << bits) - 1;
    }
    output[count] = 0;
    if (buffer || !valid_query(output, count)) { output[0] = 0; return false; }
    *length = count;
    return true;
}
} // namespace akaine_filter

// Include inside staging_cli after CliSongState, UiTree and account_controls.
// The caller must also check its fresh request session/context and deadline.
namespace filter_cli {
struct View {
    bool valid = false, open = false, ready = false;
    Address scene = 0, layer = 0, state = 0, root = 0, overlay = 0;
    Address field = 0, query_callback = 0, reset = 0;
    unsigned sort = 0, group = 0, reverse = 0;
    Size count = 0, query_size = 0;
    char query[akaine_filter::QUERY_LIMIT + 1] = {};
};
inline bool pins() {
    for (const auto& pin : FILTER_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
inline bool read_query(Reader& h, Address object, char (&output)[akaine_filter::QUERY_LIMIT + 1], Size* length) {
    if (!h.readable(object, 24)) return false;
    const unsigned char tag = h.get<unsigned char>(object);
    const Size size = tag & 1 ? h.get<Size>(object + 8) : Size(tag >> 1);
    const Address bytes = tag & 1 ? h.get<Address>(object + 16) : object + 1;
    if (size > akaine_filter::QUERY_LIMIT || (!(tag & 1) && size > 22) || !h.readable(bytes, size + 1)) return false;
    memcpy(output, reinterpret_cast<const void*>(bytes), size + 1);
    if (h.fault || !akaine_filter::valid_query(output, size)) return false;
    *length = size;
    return true;
}
inline bool running(Reader& h, Address node, Size size) {
    return h.readable(node, size) && h.get<unsigned char>(node + 0x1c0) == 1
        && h.get<unsigned char>(node + 0x1c1) == 1 && !h.fault;
}
inline bool own_tree(Reader& h, const UiTree& tree, Address scene, Address overlay) {
    if (!tree.valid || tree.loading || tree.has_modal) return false;
    for (Size i = 0; i < tree.count; ++i) {
        const Address node = tree.queue[i].node;
        if (node == scene || !h.readable(node, 0x1c2) || h.get<unsigned char>(node + 0x1c1) != 1) continue;
        // Native filter overlays attach directly to the scene. Nested layers also
        // belong to ordinary voting/sticker controls and do not identify a modal.
        if (tree.queue[i].parent == scene && h.get<Address>(node) == module.base + 0x1b90800 && node != overlay) return false;
    }
    return !h.fault;
}
inline View inspect(Reader& h, Address scene, const UiTree& tree) {
    View out;
    if (!pins() || !cli_song_pins() || !account_controls::pins()) return out;
    const CliSongState song = cli_song_capture(h, scene);
    if (!song.valid || song.pack_open || !running(h, song.layer, 0x449)
        || !account_controls::member(tree, song.layer, scene, true)) return out;
    out.scene = scene; out.layer = song.layer; out.state = song.state;
    out.sort = song.sort; out.group = song.group; out.reverse = song.reverse;
    out.count = (song.pairs_end - song.pairs_begin) / 16;
    if (!read_query(h, song.state + 0x80, out.query, &out.query_size)) return View{};
    out.overlay = h.get<Address>(song.layer + 0x438);
    if (!own_tree(h, tree, scene, out.overlay)) return View{};
    if (!out.overlay) { out.valid = !h.fault; out.ready = out.valid; return out; }
    out.open = true;
    out.root = h.get<Address>(song.layer + 0x430);
    if (!running(h, out.overlay, 0x323) || h.get<Address>(out.overlay) != module.base + 0x1b90800
        || !account_controls::member(tree, out.overlay, scene, true)
        || !running(h, out.root, 0x1c2) || !account_controls::member(tree, out.root, out.overlay, true)) return out;
    Address owned_tray = 0;
    for (Size i = 0; i < tree.count; ++i)
        if (tree.queue[i].parent == out.root && tree.queue[i].ancestors_enabled
            && ui_name(h, tree.queue[i].node, "trayImage")) {
            char klass[240] = {};
            if (owned_tray || !ui_class(h.get<Address>(tree.queue[i].node), klass)
                || strcmp(klass, "N7cocos2d2ui9ImageViewE")) return out;
            owned_tray = tree.queue[i].node;
        }
    if (!owned_tray) return out;
    const Address search = account_controls::child(h, tree, owned_tray, "filterbutton", 0x1a8ece0);
    out.field = account_controls::child(h, tree, search, "filtertextfield", 0x1aea538);
    if (!account_controls::field(h, out.field)) return out;
    out.query_callback = h.get<Address>(out.field + 0x4e0);
    if (!h.readable(out.query_callback, 24) || h.get<Address>(out.query_callback) != module.base + 0x1ad34b8
        || h.get<Address>(out.query_callback + 8) != out.layer
        || h.get<Address>(out.query_callback + 16) != out.field
        || !account_controls::pointer_pin(0x1ad34b8 + 0x30, 0x16bf2e4)) return out;
    out.reset = account_controls::child(h, tree, owned_tray, "resetbutton", 0x1a8ece0);
    const Address reset_callback = account_controls::callback(h, out.reset, 0x1aa4f10, 0x1246b14, 24);
    if (!reset_callback || h.get<Address>(reset_callback + 8) != out.layer
        || h.get<Address>(reset_callback + 16) != out.field) return out;
    const unsigned char delaying = h.get<unsigned char>(out.overlay + 0x321), dismissing = h.get<unsigned char>(out.overlay + 0x322);
    if (delaying > 1 || dismissing > 1) return out;
    out.valid = !h.fault;
    out.ready = out.valid && !delaying && !dismissing;
    return out;
}
inline void write_state(akaine_cli::Json& json, const View& value) {
    json.add("{\"valid\":"); json.add(value.valid ? "true" : "false");
    json.add(",\"open\":"); json.add(value.open ? "true" : "false");
    json.add(",\"ready\":"); json.add(value.ready ? "true" : "false");
    json.add(",\"query\":"); if (value.valid) json.string(value.query); else json.add("null");
    char numbers[160] = {};
    snprintf(numbers, sizeof(numbers), ",\"count\":%zu,\"sort\":%u,\"group\":%u,\"reverse\":%u",
             value.count, value.sort, value.group, value.reverse);
    json.add(numbers);
    json.add(",\"count_scope\":\"pack_membership\",\"native_side_filter\":false,\"native_level_filter\":false}");
}
inline const char* open(Reader& h, Address scene, const UiTree& tree) {
    if (!official_thread() || !pins()) return "NATIVE_GUARD";
    const View value = inspect(h, scene, tree);
    if (!value.valid || !value.ready) return "WRONG_SCENE";
    if (value.open) return nullptr;
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host;
    host.call<void>(0xe5eb84, value.layer, uint32_t(0));
    return host.fault ? "NATIVE_GUARD" : nullptr;
}
inline const char* close(Reader& h, Address scene, const UiTree& tree) {
    if (!official_thread() || !pins()) return "NATIVE_GUARD";
    const View value = inspect(h, scene, tree);
    if (!value.valid || !value.ready) return "WRONG_SCENE";
    if (!value.open) return nullptr;
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host;
    host.call<void>(0x1575a80, value.layer);
    return host.fault ? "NATIVE_GUARD" : nullptr;
}
inline const char* query(Reader& h, Address scene, const UiTree& tree, const char* text, Size size) {
    if (!akaine_filter::valid_query(text, size)) return "INVALID_ARGUMENT";
    if (!official_thread() || !pins()) return "NATIVE_GUARD";
    const View value = inspect(h, scene, tree);
    if (!value.valid || !value.ready || !value.open) return "FILTER_NOT_OPEN";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    if (!account_controls::set_field(value.field, text, size)) return "FIELD_REJECTED";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    // Invoke the registered native text-change closure; it owns the debounce
    // and list rebuild. No query/state/save fields are written by this adapter.
    OfficialHost host;
    const uint32_t event = 2;
    host.call<void>(0x16bf2e4, value.query_callback, value.field, Address(&event));
    return host.fault ? "NATIVE_GUARD" : nullptr;
}
inline const char* reset(Reader& h, Address scene, const UiTree& tree) {
    if (!official_thread() || !pins()) return "NATIVE_GUARD";
    const View value = inspect(h, scene, tree);
    if (!value.valid || !value.ready || !value.open) return "FILTER_NOT_OPEN";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host;
    host.call<void>(0xf66c9c, value.reset);
    return host.fault ? "NATIVE_GUARD" : nullptr;
}
// Query equality is reached only after the native deferred callback updates
// state+0x80 and synchronously rebuilds its song/difficulty vector.
inline bool query_confirmed(const View& value, const char* text, Size size) {
    return value.valid && value.ready && value.open && value.query_size == size
        && !memcmp(value.query, text, size + 1);
}
} // namespace filter_cli
