#pragma once

// Read-only public play preferences. Native UserDefault key-to-field mappings
// are retained in SETTINGS_EVIDENCE.md; no generic memory or preference access.
namespace settings_cli {
struct View {
    bool available = false, panel_open = false;
    const char* reason = "settings_unavailable";
    int audio_preset = -1, offset_normal = 0, offset_bluetooth = 0;
    int highspeed_int = 0, sfx_normal = 0, sfx_bluetooth = 0;
    int lateearly_showall = -1, skillcutin_enabled = -1, colorblindfriendly = -1;
    int high_framerate = -1, performance_mode = -1;
};
inline View inspect(Reader& h, Address, const UiTree& tree) {
    View result;
    if (tree.valid) for (Size i = 0; i < tree.inspected; ++i) {
        const Address node = tree.queue[i].node;
        if (tree.queue[i].ancestors_enabled && h.readable(node, 0x1c2)
            && h.get<unsigned char>(node + 0x1c1) == 1 && h.get<Address>(node) == module.base + 0x1ac3640)
            result.panel_open = true;
    }
    const Address manager = h.get<Address>(module.base + 0x1bf23c0);
    if (!h.readable(manager, 0x78)) return result;
    const Address settings = h.get<Address>(manager + 0x70);
    if (!h.readable(settings, 0x20)) return result;
    result.audio_preset = h.get<int>(settings);
    if (result.audio_preset != 0 && result.audio_preset != 1) { result.reason = "audio_preset"; return result; }
    result.offset_normal = h.get<int>(settings + 4);
    result.offset_bluetooth = h.get<int>(settings + 8);
    result.highspeed_int = h.get<int>(settings + 0xc);
    result.sfx_normal = h.get<int>(settings + 0x10);
    result.sfx_bluetooth = h.get<int>(settings + 0x14);
    result.lateearly_showall = h.get<unsigned char>(settings + 0x18);
    result.skillcutin_enabled = h.get<unsigned char>(settings + 0x19);
    result.colorblindfriendly = h.get<unsigned char>(settings + 0x1a);
    result.high_framerate = h.get<unsigned char>(settings + 0x1b);
    result.performance_mode = h.get<unsigned char>(settings + 0x1c);
    if (h.fault || result.lateearly_showall > 1 || result.skillcutin_enabled > 1
        || result.colorblindfriendly > 1 || result.high_framerate > 1 || result.performance_mode > 1) {
        result.reason = h.fault ? "read_fault" : "boolean_field"; return result;
    }
    result.available = true; result.reason = nullptr;
    return result;
}
inline void number(Json& json, int value) { char text[24]; snprintf(text, sizeof(text), "%d", value); json.add(text); }
inline void field(Json& json, const char* key, int value, bool available) {
    json.add(","); json.string(key); json.add(":"); if (available) number(json, value); else json.add("null");
}
inline void boolean(Json& json, const char* key, int value, bool available) {
    json.add(","); json.string(key); json.add(":"); json.add(!available ? "null" : value ? "true" : "false");
}
inline void write_state(Json& json, const View& value) {
    json.add("{\"available\":"); json.add(value.available ? "true" : "false");
    json.add(",\"reason\":"); if (value.reason) json.string(value.reason); else json.add("null");
    json.add(",\"panel_open\":"); json.add(value.panel_open ? "true" : "false");
    json.add(",\"can_open\":false,\"can_close\":false,\"can_set\":false,\"control_reason\":\"native_panel_control_unmapped\"");
    field(json, "audio_preset", value.audio_preset, value.available);
    field(json, "highspeed_int", value.highspeed_int, value.available);
    json.add(",\"note_speed\":");
    if (value.available) {
        const int speed = value.highspeed_int < 10 ? 10 : value.highspeed_int > 65 ? 65 : value.highspeed_int;
        char text[16]; snprintf(text, sizeof(text), "%d.%d", speed / 10, speed % 10); json.add(text);
    } else json.add("null");
    field(json, "offset_int_2", value.offset_normal, value.available);
    field(json, "bt_offset", value.offset_bluetooth, value.available);
    field(json, "active_offset_ms", value.audio_preset ? value.offset_bluetooth : value.offset_normal, value.available);
    field(json, "sfx_int", value.sfx_normal, value.available);
    field(json, "bt_sfx", value.sfx_bluetooth, value.available);
    boolean(json, "lateearly_showall", value.lateearly_showall, value.available);
    boolean(json, "skillcutin_enabled", value.skillcutin_enabled, value.available);
    boolean(json, "colorblindfriendly", value.colorblindfriendly, value.available);
    boolean(json, "high_framerate_v2", value.high_framerate, value.available);
    boolean(json, "performancemode_v2", value.performance_mode, value.available);
    json.add("}");
}
} // namespace settings_cli
