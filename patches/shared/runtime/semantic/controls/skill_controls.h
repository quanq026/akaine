#pragma once
#include "skill_pins.h"

// Included inside staging_cli after character_controls.h. This observer never
// calls an ability, reads account strings, or modifies a gauge or preference.
namespace skill_cli {
struct Partner {
    int id = -1, level = -1, skill_unlock_level = -1, expected_gauge = -1;
    Address object = 0, ability = 0;
    const char* ability_type = nullptr;
    const char* reason = "unavailable";
    const char* gauge_reason = "unavailable";
    bool available = false;
};
struct View {
    Partner equipped, preview, active;
    bool available = false, gameplay = false, gameplay_available = false;
    int native_skill_sealed = -1, suppression = -1, native_skill_state = -1;
    int scene_gauge = -1, scene_gauge_secondary = -1;
    bool session_ability_matches = false, session_ability_known = false;
    const char* effective_ability_type = nullptr;
    const char* reason = "character_model";
    const char* sealed_reason = "settings_unavailable";
    const char* gameplay_reason = "not_gameplay";
    const char* life_bar_reason = "not_gameplay";
    unsigned life_bar_modes[16] = {};
    Size life_bar_count = 0;
    Address scene = 0, aside = 0, dialog = 0, seal_button = 0, seal_callback = 0;
    bool can_set_sealed = false;
};
inline bool pins() {
    for (const auto& pin : SKILL_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
inline const char* ability_type(Reader& h, Address object) {
    if (!h.readable(object, 15)) return nullptr;
    const Address type = h.get<Address>(object);
    for (const auto& entry : SKILL_ABILITY_TYPES)
        if (type == module.base + entry.vtable) return entry.name;
    return nullptr;
}
inline void expected_gauge(Reader& h, Partner& partner) {
    if (!partner.ability) { partner.gauge_reason = "no_ability"; return; }
    Address method = 0;
    if (!partner.ability_type || !pins()
        || !static_pointer(h.get<Address>(partner.ability) + 0x58, &method)) {
        partner.gauge_reason = "native_guard"; return;
    }
    if (method == module.base + 0xdce310) {
        const unsigned hard = h.get<unsigned char>(partner.ability + 0xc);
        const unsigned easy = h.get<unsigned char>(partner.ability + 0xd);
        const unsigned special = h.get<unsigned char>(partner.ability + 0xe);
        if (h.fault || hard > 1 || easy > 1 || special > 1) { partner.gauge_reason = "ability_flags"; return; }
        partner.expected_gauge = easy ? 1 : hard ? 2 : special ? 5 : 0;
    } else if (method == module.base + 0x179727c) partner.expected_gauge = 6;
    else if (method == module.base + 0x889a18) partner.expected_gauge = 9;
    else if (method == module.base + 0x1581ccc) partner.expected_gauge = 10;
    else if (method == module.base + 0x1003b90) partner.expected_gauge = 11;
    else { partner.gauge_reason = "native_dynamic_rule"; return; }
    partner.gauge_reason = nullptr;
}
inline Partner read_partner(Reader& h, Address object) {
    Partner result; result.object = object;
    if (!h.readable(object, 0xd8) || !character_cli::character(h, object, &result.id)) return result;
    result.level = h.get<int>(object + 0xc0);
    result.skill_unlock_level = h.get<int>(object + 0xc4);
    if (h.fault || result.level < 0 || result.level > 1000
        || result.skill_unlock_level < -1 || result.skill_unlock_level > 1000) {
        result.reason = "character_level"; return result;
    }
    result.ability = h.get<Address>(object + 0xd0);
    if (result.ability) {
        result.ability_type = ability_type(h, result.ability);
        if (!result.ability_type) { result.reason = "ability_type"; return result; }
    }
    result.available = true; result.reason = nullptr;
    expected_gauge(h, result);
    return result;
}
inline void life_bars(Reader& h, Address session, View& result) {
    unsigned modes[16] = {}; Size count = 0;
    result.life_bar_reason = "score_state";
    if (!h.readable(session, 0x88) || h.get<Address>(session) != module.base + 0x1b79978) return;
    const Address state = h.get<Address>(session + 0x38);
    if (!h.readable(state, 0xb8) || h.get<Address>(state) != module.base + 0x1b35178) return;
    const Address begin = h.get<Address>(state + 0xa0), end = h.get<Address>(state + 0xa8);
    const Address cap = h.get<Address>(state + 0xb0);
    if (h.fault || end < begin || cap < end || (end - begin) % 8 || (cap - begin) % 8
        || cap - begin > 64 * 8 || (begin != end && !h.readable(begin, end - begin))) {
        result.life_bar_reason = "component_vector"; return;
    }
    for (Address at = begin; at < end; at += 8) {
        const Address component = h.get<Address>(at);
        if (!h.readable(component, sizeof(Address))) { result.life_bar_reason = "component_type"; return; }
        if (h.get<Address>(component) != module.base + 0x1ad3848) continue;
        if (!h.readable(component, 0xa4) || count == 16) { result.life_bar_reason = "life_bar_bounds"; return; }
        const unsigned mode = h.get<unsigned>(component + 0xa0);
        if (mode > 13) { result.life_bar_reason = "life_bar_mode"; return; }
        modes[count++] = mode;
    }
    result.life_bar_reason = h.fault ? "read_fault" : count ? nullptr : "life_bar_absent";
    if (!result.life_bar_reason) {
        result.life_bar_count = count;
        for (Size i = 0; i < count; ++i) result.life_bar_modes[i] = modes[i];
    }
}
inline View inspect(Reader& h, Address scene, const char* klass, const character_cli::View& character) {
    View result; result.scene = scene;
    character_cli::View current;
    const character_cli::View* model = &character;
    if (!character.available) {
        if (!character_cli::read_model(h, current)) return result;
        model = &current;
    }
    result.equipped = read_partner(h, character_cli::find(*model, model->equipped_id));
    if (character.preview_id >= 0) result.preview = read_partner(h, character_cli::find(*model, character.preview_id));
    else result.preview.reason = "dialog_closed";
    result.available = result.equipped.available;
    result.reason = result.available ? nullptr : result.equipped.reason;
    const Address manager = h.get<Address>(module.base + 0x1bf23c0);
    if (h.readable(manager, 0xb8)) {
        const Address settings = h.get<Address>(manager + 0x78);
        if (h.readable(settings, 0xd)) {
            const unsigned value = h.get<unsigned char>(settings + 0xc);
            if (value <= 1) { result.native_skill_sealed = int(value); result.sealed_reason = nullptr; }
            else result.sealed_reason = "invalid_flag";
        }
        const Address context = h.get<Address>(manager + 0xb0);
        if (h.readable(context, 9)) {
            const unsigned value = h.get<unsigned char>(context + 8);
            if (value <= 1) result.suppression = int(value);
        }
    }
    if (character.available && character.dialog && character.aside && !character.blocked && !character.reason
        && result.native_skill_sealed >= 0 && h.readable(character.aside, 0x4f0)) {
        const Address button = h.get<Address>(character.aside + 0x4e8);
        if (character_cli::button(h, button) && h.get<Address>(button + 0x148) == character.aside
            && !h.get<Address>(button + 0x3d0)) {
            const Address closure = h.get<Address>(button + 0x400);
            if (character_cli::callback(h, closure, 0x1b16788, character.aside, 0x1622e90)) {
                result.aside = character.aside; result.dialog = character.dialog;
                result.seal_button = button; result.seal_callback = closure;
                result.can_set_sealed = true;
            }
        }
    }
    result.gameplay = klass && !strcmp(klass, "9GameScene");
    if (!result.gameplay) return result;
    result.gameplay_reason = "game_scene";
    if (!h.readable(scene, 0x3e8) || h.get<Address>(scene) != module.base + 0x1ae6ef0) return result;
    result.active = read_partner(h, h.get<Address>(scene + 0x330));
    if (!result.active.available) { result.gameplay_reason = result.active.reason; return result; }
    const Address ability = h.get<Address>(scene + 0x338);
    if (ability) {
        result.effective_ability_type = ability_type(h, ability);
        if (!result.effective_ability_type) { result.gameplay_reason = "effective_ability_type"; return result; }
    }
    const unsigned state = h.get<unsigned>(scene + 0x340);
    const unsigned gauge = h.get<unsigned>(scene + 0x324), secondary = h.get<unsigned>(scene + 0x328);
    if (h.fault || state > 4 || gauge > 13 || secondary > 13) { result.gameplay_reason = "game_state_bounds"; return result; }
    result.native_skill_state = int(state); result.scene_gauge = int(gauge); result.scene_gauge_secondary = int(secondary);
    const Address session = h.get<Address>(scene + 0x3e0);
    if (h.readable(session, 0x88) && h.get<Address>(session) == module.base + 0x1b79978) {
        result.session_ability_known = true;
        result.session_ability_matches = h.get<Address>(session + 0x80) == ability;
    }
    life_bars(h, session, result);
    result.gameplay_available = !h.fault;
    result.gameplay_reason = h.fault ? "read_fault" : nullptr;
    return result;
}
inline const char* seal(Reader& h, const View& view, bool sealed) {
    if (!view.available || view.native_skill_sealed < 0) return "SKILL_UNAVAILABLE";
    if (view.native_skill_sealed == int(sealed)) return nullptr;
    if (!view.can_set_sealed || !view.seal_button || !view.aside || !view.dialog) return "SKILL_SEAL_UNAVAILABLE";
    const Address manager = h.get<Address>(module.base + 0x1bf23c0);
    if (!h.readable(manager, 0x80)) return "NATIVE_GUARD";
    const Address settings = h.get<Address>(manager + 0x78);
    if (!h.readable(settings, 0x20) || h.get<unsigned char>(settings + 0xc) != view.native_skill_sealed) return "NATIVE_GUARD";
    const Address model = h.get<Address>(settings + 0x18);
    if (!h.readable(model, 0x60) || h.get<Address>(model + 0x58) != view.equipped.object
        || h.get<Address>(view.aside) != module.base + 0x1ad8838
        || h.get<Address>(view.aside + 0x148) != view.dialog || h.get<Address>(view.aside + 0x5c8) != view.dialog
        || h.get<Address>(view.dialog + 0x148) != view.scene
        || h.get<Address>(view.aside + 0x4e8) != view.seal_button
        || !character_cli::button(h, view.seal_button)
        || h.get<Address>(view.seal_button + 0x148) != view.aside || h.get<Address>(view.seal_button + 0x3d0)
        || h.get<Address>(view.seal_button + 0x400) != view.seal_callback
        || !character_cli::callback(h, view.seal_callback, 0x1b16788, view.aside, 0x1622e90)
        || !character_cli::pins() || !pins() || h.fault) return "NATIVE_GUARD";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host; host.call<void>(0xf66c9c, view.seal_button);
    return host.fault ? "NATIVE_GUARD" : nullptr;
}
inline void integer(Json& json, int value) {
    if (value < 0) { json.add("null"); return; }
    char text[24]; snprintf(text, sizeof(text), "%d", value); json.add(text);
}
inline void string_or_null(Json& json, const char* value) { if (value) json.string(value); else json.add("null"); }
inline void flag(Json& json, int value) { json.add(value < 0 ? "null" : value ? "true" : "false"); }
inline void write_partner(Json& json, const Partner& value) {
    json.add("{\"available\":"); json.add(value.available ? "true" : "false");
    json.add(",\"reason\":"); string_or_null(json, value.reason);
    json.add(",\"id\":"); integer(json, value.available ? value.id : -1);
    json.add(",\"level\":"); integer(json, value.available ? value.level : -1);
    json.add(",\"skill_unlock_level\":"); integer(json, value.available ? value.skill_unlock_level : -1);
    json.add(",\"skill_id\":null,\"skill_id_reason\":\"native_string_unmapped\",\"ability_type\":"); string_or_null(json, value.ability_type);
    json.add(",\"expected_gauge_mode\":"); integer(json, value.expected_gauge);
    json.add(",\"expected_gauge_reason\":"); string_or_null(json, value.gauge_reason); json.add("}");
}
inline const char* state_name(int value) {
    switch (value) {
        case 0: return "absent_or_ineligible";
        case 1: return "eligible";
        case 2: return "conditions_unmet";
        case 3: return "world_mode_unsupported";
        case 4: return "sealed";
        default: return nullptr;
    }
}
inline void write_state(Json& json, const View& value) {
    json.add("{\"available\":"); json.add(value.available ? "true" : "false");
    json.add(",\"reason\":"); string_or_null(json, value.reason);
    json.add(",\"native_skill_sealed\":"); flag(json, value.native_skill_sealed);
    json.add(",\"native_skill_sealed_reason\":"); string_or_null(json, value.sealed_reason);
    json.add(",\"can_set_sealed\":"); json.add(value.can_set_sealed ? "true" : "false");
    json.add(",\"suppression\":"); flag(json, value.suppression);
    json.add(",\"equipped\":"); write_partner(json, value.equipped);
    json.add(",\"preview\":"); write_partner(json, value.preview);
    json.add(",\"gameplay\":{\"available\":"); json.add(value.gameplay_available ? "true" : "false");
    json.add(",\"reason\":"); string_or_null(json, value.gameplay_reason);
    json.add(",\"partner\":"); write_partner(json, value.active);
    json.add(",\"effective_ability_type\":"); string_or_null(json, value.effective_ability_type);
    json.add(",\"native_skill_state\":"); integer(json, value.native_skill_state);
    json.add(",\"native_skill_state_name\":"); string_or_null(json, state_name(value.native_skill_state));
    json.add(",\"scene_gauge_mode\":"); integer(json, value.scene_gauge);
    json.add(",\"scene_secondary_gauge_mode\":"); integer(json, value.scene_gauge_secondary);
    json.add(",\"session_ability_matches\":"); flag(json, value.session_ability_known ? int(value.session_ability_matches) : -1);
    json.add(",\"life_bar_modes\":[");
    for (Size i = 0; i < value.life_bar_count; ++i) { if (i) json.add(","); integer(json, int(value.life_bar_modes[i])); }
    json.add("],\"life_bar_reason\":"); string_or_null(json, value.life_bar_reason); json.add("}}");
}
} // namespace skill_cli
