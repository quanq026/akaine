#pragma once
#include "result_pins.h"

// Included inside staging_cli after cli_song_id and skill_controls.h. Both
// native getters are read-only and are the same paths used by the result UI.
namespace result_cli {
struct View {
    bool available = false, score_available = false, clear_available = false;
    char song[65] = {};
    int difficulty = -1, score = -1, clear_type = -1;
    const char* reason = "unsupported_scene";
    const char* score_reason = "result_unavailable";
    const char* clear_reason = "result_unavailable";
};
inline bool pins() {
    for (const auto& pin : RESULT_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
inline bool pointer(Address at, Address value) {
    Address actual = 0;
    return static_pointer(module.base + at, &actual) && actual == module.base + value;
}
inline View inspect(Reader& h, Address scene, const char* klass) {
    View out;
    if (strcmp(klass, "21NormalGameResultScene") || !h.readable(scene, 0x2f0)
        || h.get<Address>(scene) != module.base + 0x1afe2a0) return out;
    out.reason = "native_guard";
    if (!official_thread() || !pins() || h.get<unsigned char>(scene + 0x1c0) != 1) return out;
    const Address model = h.get<Address>(scene + 0x2e8);
    if (!h.readable(model, 0x20)) return out;
    const Address result = h.get<Address>(model + 0x18);
    if (!h.readable(result, 0xc8) || h.get<Address>(result) != module.base + 0x1b054c0
        || !pointer(0x1b054c0 - 8, 0x1ad8f80) || !pointer(0x1ad8f80 + 8, 0x51c874)
        || !cli_song_id(h, result + 0x38, out.song)) return out;
    out.difficulty = h.get<int>(result + 0x50);
    if (out.difficulty < 0 || out.difficulty > 4 || h.fault) { out.song[0] = 0; out.difficulty = -1; return out; }
    out.available = true; out.reason = nullptr;
    out.score_reason = "score_fields";
    const unsigned override_score = h.get<unsigned char>(result + 0xb1);
    const unsigned alternate_score = h.get<unsigned char>(result + 0xb0);
    const int shiny = h.get<int>(result + 0x14), pure = h.get<int>(result + 0x18);
    const int far = h.get<int>(result + 0x1c), lost = h.get<int>(result + 0x20);
    // Bound the native division inputs before calling its score getter.
    const bool counts = shiny >= 0 && pure >= 0 && far >= 0 && lost >= 0
        && shiny <= pure && pure <= 1000000 && far <= 1000000 && lost <= 1000000
        && uint64_t(pure) + uint64_t(far) + uint64_t(lost) <= 1000000;
    OfficialHost call;
    if (override_score <= 1 && alternate_score <= 1 && counts
        && (override_score || pure + far + lost > 0)) {
        const int score = call.call<int>(0x1315038, result);
        if (!call.fault && score >= 0) { out.score = score; out.score_available = true; out.score_reason = nullptr; }
        else out.score_reason = "native_score_unavailable";
    }
    out.clear_reason = "clear_fields";
    const int gauge = h.get<int>(result + 0x54);
    const unsigned alternate_clear = h.get<unsigned char>(result + 0x84);
    const unsigned zero_health_clear = h.get<unsigned char>(result + 0xb3);
    const Address ability = h.get<Address>(result + 0xc0);
    bool ability_safe = !ability;
    if (ability) {
        const char* type = skill_cli::ability_type(h, ability);
        ability_safe = type != nullptr;
        if (type && !strcmp(type, "33CharacterAbilityClearBasedOnScore")) {
            ability_safe = h.readable(ability, 0xa8) && pointer(0x1aa4720 + 0x68, 0x1604390);
            const int custom_clear = ability_safe ? h.get<int>(ability + 0xa4) : -1;
            ability_safe = ability_safe && custom_clear >= 0 && custom_clear <= 5;
        }
        if (!ability_safe) out.clear_reason = "ability_type_unavailable";
    }
    if (counts && gauge >= 0 && gauge <= 13 && alternate_clear <= 1 && zero_health_clear <= 1 && ability_safe) {
        const int clear = call.call<int>(0x12a5574, result);
        if (!call.fault && clear >= 0 && clear <= 5) { out.clear_type = clear; out.clear_available = true; out.clear_reason = nullptr; }
        else out.clear_reason = "native_clear_unavailable";
    }
    if (h.fault) {
        out.score_available = out.clear_available = false; out.score = out.clear_type = -1;
        out.score_reason = out.clear_reason = "read_fault";
    }
    return out;
}
inline const char* clear_name(int value) {
    constexpr const char* names[] = {"track_lost", "normal_clear", "full_recall", "pure_memory", "easy_clear", "hard_clear"};
    return value >= 0 && value <= 5 ? names[value] : nullptr;
}
inline void number(Json& json, int value, bool available) {
    if (!available) { json.add("null"); return; }
    char text[24]; snprintf(text, sizeof(text), "%d", value); json.add(text);
}
inline void nullable(Json& json, const char* value) { if (value) json.string(value); else json.add("null"); }
inline void write_state(Json& json, const View& out) {
    json.add("{\"available\":"); json.add(out.available ? "true" : "false");
    json.add(",\"reason\":"); nullable(json, out.reason);
    json.add(",\"song_id\":"); nullable(json, out.available ? out.song : nullptr);
    json.add(",\"difficulty\":"); number(json, out.difficulty, out.available);
    json.add(",\"score\":"); number(json, out.score, out.score_available);
    json.add(",\"score_reason\":"); nullable(json, out.score_reason);
    json.add(",\"clear_type\":"); number(json, out.clear_type, out.clear_available);
    json.add(",\"clear\":"); nullable(json, out.clear_available ? clear_name(out.clear_type) : nullptr);
    json.add(",\"clear_reason\":"); nullable(json, out.clear_reason);
    json.add("}");
}
}
