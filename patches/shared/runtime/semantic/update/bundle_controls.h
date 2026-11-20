#pragma once
#include "bundle_pins.h"
#include "bundle_error_pins.h"

namespace bundle_cli {
struct View {
    bool available = false, can_confirm = false, has_pending_bytes = false, error_popup = false;
    const char* phase = "unavailable";
    const char* reason = "wrong_scene";
    char versions[8][32] = {};
    Size count = 0;
    uint64_t bytes = 0;
    Address button = 0, root = 0;
};
bool pins() {
    for (const auto& pin : CLI_BUNDLE_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
bool pointer(Address at, Address expected) {
    Address actual = 0;
    return static_pointer(module.base + at, &actual) && actual == module.base + expected;
}
bool member(Reader& h, const UiTree& tree, Address node, Address parent, Address type) {
    if (!node || !h.readable(node, 0x1c2) || h.get<Address>(node) != module.base + type
        || h.get<Address>(node + 0x148) != parent || h.get<unsigned char>(node + 0x1c0) != 1
        || h.get<unsigned char>(node + 0x1c1) != 1) return false;
    for (Size i = 0; i < tree.count; ++i)
        if (tree.queue[i].node == node && tree.queue[i].parent == parent) return true;
    return false;
}

bool error_pins() {
    for (const auto& pin : CLI_BUNDLE_ERROR_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return pointer(0x1ae5b98 + 0x30, 0x1619540) && pointer(0x1b72c18 + 0x30, 0xa571a0)
        && pointer(0x1a8ece0 + 0x630, 0xf66c9c);
}
// Match only the one-button ContentBundleError continuation owned by this StartScene.
bool inspect_error(Reader& h, Address scene, const UiTree& tree, View& v) {
    if (h.get<unsigned char>(scene + 0x3f0) != 1) return false;
    for (Size i = 0; i < tree.count; ++i) {
        const Address button = tree.queue[i].node;
        if (!h.readable(button, 0x449) || h.get<Address>(button) != module.base + 0x1a8ece0) continue;
        const Address outer = h.get<Address>(button + 0x400);
        if (!h.readable(outer, 0x68) || h.get<Address>(outer) != module.base + 0x1ae5b98) continue;
        const Address root = h.get<Address>(outer + 0x30), dim = h.get<Address>(outer + 0x20);
        const Address image = h.get<Address>(outer + 0x28), inner = h.get<Address>(outer + 0x60);
        if (h.get<Address>(outer + 0x10) != scene || h.get<Address>(outer + 0x18) != scene
            || h.get<Address>(outer + 0x38) != button || !member(h, tree, root, scene, 0x1b4d3e8)
            || !member(h, tree, dim, scene, 0x1b90800) || !member(h, tree, image, root, 0x1aa0128)
            || !member(h, tree, button, root, 0x1a8ece0) || !h.readable(inner, 0x10)
            || h.get<Address>(inner) != module.base + 0x1b72c18 || h.get<Address>(inner + 8) != scene
            || !error_pins()) continue;
        if (v.error_popup) { v.button = v.root = 0; v.reason = "ambiguous_bundle_error"; return true; }
        v.error_popup = true; v.phase = "failed"; v.reason = "native_bundle_error";
        v.button = button; v.root = root;
    }
    return v.error_popup;
}
bool error_button_ready(Reader& h, Address button) {
    return button && h.readable(button, 0x449) && h.get<unsigned char>(button + 0x312) == 1
        && h.get<unsigned char>(button + 0x314) == 1 && !h.get<unsigned char>(button + 0x448)
        && !h.get<Address>(button + 0x398) && !h.get<Address>(button + 0x3a0)
        && !h.get<Address>(button + 0x3a8) && !h.get<Address>(button + 0x3d0) && !h.fault;
}


// Transport failures use the same error factory with an exact Retry/Cancel pair.
// Observation only: the single-button dismiss command must not dispatch either one.
bool inspect_transport_error(Reader& h, Address scene, const UiTree& tree, View& v) {
    if (h.get<unsigned char>(scene + 0x3f0) != 1) return false;
    for (Size i = 0; i < tree.count; ++i) {
        const Address retry = tree.queue[i].node;
        if (!h.readable(retry, 0x449) || h.get<Address>(retry) != module.base + 0x1a8ece0) continue;
        const Address accept_outer = h.get<Address>(retry + 0x400);
        if (!h.readable(accept_outer, 0x78) || h.get<Address>(accept_outer) != module.base + 0x1b1a7c0) continue;
        const Address root = h.get<Address>(accept_outer + 0x30), dim = h.get<Address>(accept_outer + 0x20);
        const Address image = h.get<Address>(accept_outer + 0x28), cancel = h.get<Address>(accept_outer + 0x40);
        const Address retry_inner = h.get<Address>(accept_outer + 0x70);
        if (h.get<Address>(accept_outer + 0x10) != scene || h.get<Address>(accept_outer + 0x18) != scene
            || h.get<Address>(accept_outer + 0x38) != retry || !member(h, tree, root, scene, 0x1b4d3e8)
            || !member(h, tree, dim, scene, 0x1b90800) || !member(h, tree, image, root, 0x1aa0128)
            || !member(h, tree, retry, root, 0x1a8ece0) || !member(h, tree, cancel, root, 0x1a8ece0)
            || retry == cancel || !h.readable(cancel, 0x449) || !h.readable(retry_inner, 0x18)
            || h.get<Address>(retry_inner) != module.base + 0x1af9ad8 || h.get<Address>(retry_inner + 0x10) != scene) continue;
        const Address cancel_outer = h.get<Address>(cancel + 0x400);
        if (!h.readable(cancel_outer, 0x78) || h.get<Address>(cancel_outer) != module.base + 0x1b41a40
            || h.get<Address>(cancel_outer + 0x10) != scene || h.get<Address>(cancel_outer + 0x18) != scene
            || h.get<Address>(cancel_outer + 0x20) != dim || h.get<Address>(cancel_outer + 0x28) != image
            || h.get<Address>(cancel_outer + 0x30) != root || h.get<Address>(cancel_outer + 0x38) != retry
            || h.get<Address>(cancel_outer + 0x40) != cancel) continue;
        const Address cancel_inner = h.get<Address>(cancel_outer + 0x70);
        if (!h.readable(cancel_inner, 8) || h.get<Address>(cancel_inner) != module.base + 0x1ac9828
            || !error_pins() || !pointer(0x1b1a7c0 + 0x30, 0xf208c4) || !pointer(0x1b41a40 + 0x30, 0xcf77d8)
            || !pointer(0x1af9ad8 + 0x30, 0xc91f68) || !pointer(0x1ac9828 + 0x30, 0x142b6c8)) continue;
        v.error_popup = true; v.phase = "failed"; v.reason = "native_bundle_error";
        v.button = v.root = 0;
        return true;
    }
    return false;
}

bool version(Reader& h, Address at, char (&out)[32]) {
    if (!h.readable(at, 24)) return false;
    const unsigned char tag = h.get<unsigned char>(at);
    const Size length = tag & 1 ? h.get<Size>(at + 8) : Size(tag >> 1);
    const Address data = tag & 1 ? h.get<Address>(at + 16) : at + 1;
    if (length < 9 || length >= sizeof(out) || !h.readable(data, length + 1)) return false;
    const char* text = reinterpret_cast<const char*>(data);
    if (memcmp(text, "7.0.255.", 8) || text[length] || text[8] == '0') return false;
    for (Size i = 8; i < length; ++i) if (text[i] < '0' || text[i] > '9') return false;
    memcpy(out, text, length + 1);
    return !h.fault;
}
View inspect(Reader& h, Address scene, const UiTree& tree) {
    View v;
    if (!h.readable(scene, 0x3f1) || h.get<Address>(scene) != module.base + 0x1a9b4c0) return v;
    v.available = true; v.reason = "unavailable";
    if (!pins() || !tree.valid || h.get<unsigned char>(scene + 0x1c0) != 1) return v;
    const unsigned ready = h.get<unsigned char>(scene + 0x391), failed = h.get<unsigned char>(scene + 0x392);
    const unsigned popup = h.get<unsigned char>(scene + 0x3f0);
    if (ready > 1 || failed > 1 || popup > 1) return v;
    const Address begin = h.get<Address>(scene + 0x398), end = h.get<Address>(scene + 0x3a0);
    const Address cap = h.get<Address>(scene + 0x3a8);
    if (end < begin || cap < end || (end - begin) % 104 || (cap - begin) % 104
        || end - begin > 8 * 104 || cap - begin > 64 * 104 || (begin != end && !h.readable(begin, end - begin))) return v;
    v.count = (end - begin) / 104;
    uint64_t largest = 0;
    for (Size i = 0; i < v.count; ++i) {
        const Address entry = begin + i * 104;
        if (!version(h, entry + 24, v.versions[i])) return View{};
        const uint64_t metadata = h.get<uint64_t>(entry + 72);
        const Address parts = h.get<Address>(entry + 80), parts_end = h.get<Address>(entry + 88), parts_cap = h.get<Address>(entry + 96);
        if (metadata > (1ULL << 30) || parts_end < parts || parts_cap < parts_end || (parts_end - parts) % 40
            || (parts_cap - parts) % 40 || parts_end - parts > 64 * 40 || parts_cap - parts > 128 * 40
            || (parts != parts_end && !h.readable(parts, parts_end - parts))) return View{};
        v.bytes += metadata;
        for (Address at = parts; at < parts_end; at += 40) {
            const uint64_t size = h.get<uint64_t>(at + 24);
            if (!size || size > (1ULL << 34) || v.bytes > (1ULL << 38) - size) return View{};
            v.bytes += size;
            if (size > largest) largest = size;
        }
    }
    if (h.fault) return View{};
    v.has_pending_bytes = true; v.reason = nullptr;
    if (inspect_error(h, scene, tree, v)) return h.fault ? View{} : v;
    if (inspect_transport_error(h, scene, tree, v)) return h.fault ? View{} : v;
    if (h.fault) return View{};
    if (failed) { v.phase = "failed"; v.reason = "native_bundle_error"; return v; }
    const Address progress = h.get<Address>(scene + 0x320);
    if (popup && member(h, tree, progress, scene, 0x1b4d3e8)) {
        v.phase = "downloading"; return v;
    }
    if (!popup) {
        if (ready || h.get<unsigned char>(scene + 0x354) != 1) {
            v.phase = "unavailable"; v.reason = ready ? "native_update_pending" : "fetching"; return v;
        }
        v.phase = "ready"; v.count = 0; v.bytes = 0; return v;
    }
    v.phase = "confirmation"; v.reason = "unsupported_prompt";
    if (!ready || !v.count || !v.bytes || tree.has_modal) return v;
    for (Size i = 0; i < tree.count; ++i) {
        const Address button = tree.queue[i].node;
        if (!h.readable(button, 0x449) || h.get<Address>(button) != module.base + 0x1a8ece0) continue;
        const Address outer = h.get<Address>(button + 0x400);
        if (!h.readable(outer, 0x78) || h.get<Address>(outer) != module.base + 0x1afa520) continue;
        if (v.button) { v.button = 0; v.reason = "ambiguous_prompt"; return v; }
        const Address root = h.get<Address>(outer + 0x30), dim = h.get<Address>(outer + 0x20);
        const Address image = h.get<Address>(outer + 0x28), cancel = h.get<Address>(outer + 0x40);
        const Address inner = h.get<Address>(outer + 0x70);
        if (h.get<Address>(outer + 0x10) != scene || h.get<Address>(outer + 0x18) != scene
            || h.get<Address>(outer + 0x38) != button || !member(h, tree, root, scene, 0x1b4d3e8)
            || !member(h, tree, dim, scene, 0x1b90800) || !member(h, tree, image, root, 0x1aa0128)
            || !member(h, tree, button, root, 0x1a8ece0) || !member(h, tree, cancel, root, 0x1a8ece0)
            || !h.readable(inner, 0x28) || h.get<Address>(inner) != module.base + 0x1b70038
            || h.get<Address>(inner + 8) != scene || h.get<Address>(inner + 16) != scene
            || h.get<uint64_t>(inner + 24) != v.bytes || h.get<uint64_t>(inner + 32) != largest) continue;
        const Address cancel_outer = h.get<Address>(cancel + 0x400);
        if (!h.readable(cancel_outer, 0x78) || h.get<Address>(cancel_outer) != module.base + 0x1b56270
            || h.get<Address>(cancel_outer + 0x10) != scene || h.get<Address>(cancel_outer + 0x18) != scene
            || h.get<Address>(cancel_outer + 0x20) != dim || h.get<Address>(cancel_outer + 0x30) != root
            || h.get<Address>(cancel_outer + 0x38) != button || h.get<Address>(cancel_outer + 0x40) != cancel) continue;
        const Address cancel_inner = h.get<Address>(cancel_outer + 0x70);
        if (!h.readable(cancel_inner, 8) || h.get<Address>(cancel_inner) != module.base + 0x1b09a28
            || !pointer(0x1afa520 + 0x30, 0x14b215c) || !pointer(0x1b70038 + 0x30, 0xbd8c68)
            || !pointer(0x1b56270 + 0x30, 0x88920c) || !pointer(0x1b09a28 + 0x30, 0xf43c54)
            || !pointer(0x1a8ece0 + 0x630, 0xf66c9c)) continue;
        v.button = button; v.root = root;
    }
    if (h.fault || !v.button) return v;
    const unsigned enabled = h.get<unsigned char>(v.button + 0x312), touch = h.get<unsigned char>(v.button + 0x314);
    if (enabled != 1 || touch != 1 || h.get<unsigned char>(v.button + 0x448)
        || h.get<Address>(v.button + 0x398) || h.get<Address>(v.button + 0x3a0)
        || h.get<Address>(v.button + 0x3a8) || h.get<Address>(v.button + 0x3d0)) { v.reason = "not_ready"; return v; }
    v.can_confirm = true; v.reason = nullptr; return v;
}
const char* confirm(Reader& h, Address scene, const UiTree& tree, const View& expected) {
    if (!official_thread() || !pins()) return "NATIVE_GUARD";
    const View current = inspect(h, scene, tree);
    if (!current.can_confirm || !expected.can_confirm || current.button != expected.button
        || current.root != expected.root || current.bytes != expected.bytes || current.count != expected.count) return "BUNDLE_PROMPT_UNAVAILABLE";
    for (Size i = 0; i < current.count; ++i)
        if (strcmp(current.versions[i], expected.versions[i])) return "BUNDLE_TARGET_CHANGED";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host; host.call<void>(0xf66c9c, current.button);
    return host.fault ? "NATIVE_GUARD" : nullptr;
}

const char* dismiss_error(Reader& h, Address scene, const UiTree& tree, const View& expected) {
    if (!official_thread() || !pins() || !error_pins()) return "NATIVE_GUARD";
    const View current = inspect(h, scene, tree);
    if (tree.has_modal || !current.error_popup || !expected.error_popup || !current.button || current.button != expected.button
        || current.root != expected.root) return "BUNDLE_ERROR_UNAVAILABLE";
    if (!error_button_ready(h, current.button)) return "BUNDLE_ERROR_NOT_READY";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host; host.call<void>(0xf66c9c, current.button);
    return host.fault ? "NATIVE_GUARD" : nullptr;
}

void write_state(akaine_cli::Json& json, const View& v) {
    json.add("{\"available\":"); json.add(v.available ? "true" : "false");
    json.add(",\"phase\":"); json.string(v.phase);
    json.add(",\"can_confirm\":"); json.add(v.can_confirm ? "true" : "false");
    json.add(",\"pending_versions\":[");
    for (Size i = 0; i < v.count; ++i) { if (i) json.add(","); json.string(v.versions[i]); }
    json.add("],\"pending_bytes\":");
    if (v.has_pending_bytes) { char text[32]; snprintf(text, sizeof(text), "%llu", static_cast<unsigned long long>(v.bytes)); json.add(text); }
    else json.add("null");
    json.add(",\"reason\":"); if (v.reason) json.string(v.reason); else json.add("null"); json.add("}");
}
}
