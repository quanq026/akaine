#pragma once
#include "cli_core.h"

namespace akaine_cli {
constexpr size_t UI_ACTION_LIMIT = 8;
constexpr size_t UI_OVERLAY_LIMIT = 16;
struct UiIdentity {
    uintptr_t scene = 0, scene_type = 0, modal = 0, modal_type = 0;
    uintptr_t nodes[UI_ACTION_LIMIT] = {}, callbacks[UI_ACTION_LIMIT] = {};
    uint32_t flags[UI_ACTION_LIMIT] = {};
    size_t count = 0;
    uintptr_t overlays[UI_OVERLAY_LIMIT] = {}, interceptors[UI_OVERLAY_LIMIT] = {};
    uint32_t overlay_flags[UI_OVERLAY_LIMIT] = {};
    size_t overlay_count = 0;
    bool available = false;
};
inline bool same_ui(const UiIdentity& left, const UiIdentity& right) {
    if (left.scene != right.scene || left.scene_type != right.scene_type || left.modal != right.modal
        || left.modal_type != right.modal_type || left.count != right.count || left.available != right.available
        || left.overlay_count != right.overlay_count) return false;
    for (size_t i = 0; i < UI_ACTION_LIMIT; ++i)
        if (left.nodes[i] != right.nodes[i] || left.callbacks[i] != right.callbacks[i] || left.flags[i] != right.flags[i]) return false;
    for (size_t i = 0; i < UI_OVERLAY_LIMIT; ++i)
        if (left.overlays[i] != right.overlays[i] || left.interceptors[i] != right.interceptors[i]
            || left.overlay_flags[i] != right.overlay_flags[i]) return false;
    return true;
}
struct UiContext {
    UiIdentity previous;
    uint64_t generation = 0;
    bool initialized = false, exhausted = false;
    uint64_t observe(const UiIdentity& identity) {
        if (exhausted) return 0;
        if (!initialized || !same_ui(previous, identity)) {
            if (generation == UINT64_MAX) { exhausted = true; return 0; }
            ++generation;
            previous = identity;
            initialized = true;
        }
        return generation;
    }
};
inline bool token_context(const char* token, uint64_t expected) {
    const size_t n = strlen(token);
    if (!action_token(token, n) || expected == 0) return false;
    uint64_t value = 0;
    for (size_t i = n - 16; i < n; ++i) {
        const char ch = token[i];
        value = (value << 4) | unsigned(ch <= '9' ? ch - '0' : ch - 'a' + 10);
    }
    return value == expected;
}
}
