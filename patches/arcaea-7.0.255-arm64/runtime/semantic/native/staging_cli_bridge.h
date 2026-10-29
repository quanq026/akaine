#include "maps_snapshot.h"
#pragma once
#if !defined(AKAINE_STAGING_CLI) || AKAINE_STAGING_CLI != 1
#error The semantic bridge requires the production profile monitor.
#endif
#include "cli_core.h"
#include "cli_ui_core.h"
#include "cli_files.h"
#include "cli_pins.h"
#include <stdlib.h>

namespace staging_cli {
using akaine_cli::Json;
using akaine_cli::Request;
int directory = -1;
bool attempted = false;
char session[33] = {};
uint64_t polled_ns = 0;
akaine_cli::Ledger ledger;
Request pending;
bool waiting = false;
Address pending_scene = 0, pending_layer = 0;
unsigned pending_start_flags = 0;
int pending_number = -1;
char pending_song[65] = {};
bool pending_scene_changed = false;
int pending_navigation_kind = 0;
akaine_cli::UiIdentity pending_ui_identity;

uint64_t wall_ms() {
    timespec ts = {};
    return !clock_gettime(CLOCK_REALTIME, &ts) && ts.tv_sec > 0
        ? uint64_t(ts.tv_sec) * 1000 + uint64_t(ts.tv_nsec) / 1000000 : 0;
}
bool staging_pins() {
    for (const auto& pin : CLI_ROUTE_PINS)
        if (!module_readable(module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
bool action_pins() {
    for (const auto& pin : CLI_ACTION_PINS)
        if (!in_ranges(module.executable, module.executable_count, module.base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(module.base + pin.address), pin.bytes, pin.size)) return false;
    return true;
}
// One bounded map snapshot per served request/confirmation, avoiding hundreds
// of /proc opens while walking a scene. No tree is inspected while idle.
struct Reader {
    Range ranges[4096] = {};
    Size count = 0;
    bool fault = false;
    Reader() {
        FILE* file = fopen("/proc/self/maps", "r");
        if (!file) { fault = true; return; }
        const auto scanned = monitor_maps::scan(file, [&](const monitor_maps::Mapping& mapping) {
            if (!mapping.readable) return monitor_maps::Visit::Continue;
            if (count && ranges[count - 1].end == Address(mapping.begin)) ranges[count - 1].end = Address(mapping.end);
            else {
                if (count == 4096) return monitor_maps::Visit::Reject;
                ranges[count++] = {Address(mapping.begin), Address(mapping.end)};
            }
            return monitor_maps::Visit::Continue;
        });
        const bool closed = fclose(file) == 0;
        if (!scanned.good || !closed) fault = true;
    }
    bool readable(Address address, Size size) const {
        return !fault && address && in_ranges(ranges, count, address, size);
    }
    template<class T> T get(Address address) {
        T result = {};
        if (!readable(address, sizeof(T))) fault = true;
        else memcpy(&result, reinterpret_cast<const void*>(address), sizeof(T));
        return result;
    }
};
bool domain_dispatching = false;
bool cli_dispatch_allowed() {
    return domain_dispatching && official_thread() && !akaine_cli::request_guard(pending, session, wall_ms());
}
#include "cli_ui_native.h"
overlay_cli::View pending_overlays;
#include "../song-v9/cli_song_native.h"
#include "../play/play_controls.h"
#include "../play/confirm/play_confirm.h"
#include "../play/guide/play_guide.h"
#include "../character/character_controls.h"
#include "../controls/skill_controls.h"
#include "../controls/settings_controls.h"
#include "../settings-v12/settings_panel.h"
#include "../result/result_state.h"
#include "../account/account_adapter.h"
account_controls::SubmitCycle pending_login_submit;
#include "../account/account_credentials.h"
#include "../cloudsync/cli_cloudsync.h"
#include "../filter-v12/filter_adapter.h"
#include "../navigation/navigation_controls.h"
#include "../update/bundle_controls.h"
struct Snapshot {
    Address scene = 0, layer = 0;
    char klass[240] = {}, song[65] = {};
    const char* screen = "unavailable";
    int difficulty = -1, ordinal = -1;
    bool game = false, ready = false;
    bool transition = false;
    CliUiState ui;
    CliSongState song_state;
    character_cli::View character_state;
    account_controls::AccountView account_state;
    cloudsync_cli::View sync_state;
    skill_cli::View skill_state;
    filter_cli::View filter_state;
    navigation_cli::View navigation_state;
    settings_cli::View settings_state;
    settings_panel_cli::View settings_control;
    result_cli::View result_state;
    bundle_cli::View bundle_state;
    CliAdvancedGuide advanced_guide;
};
bool pack_fields(Reader& h, Address layer, int* ordinal) {
    if (!h.readable(layer, 0x440) || h.get<Address>(layer) != module.base + 0x1b828b8
        || h.get<unsigned char>(layer + 0x1c1) != 1) return false;
    const Address begin = h.get<Address>(layer + 0x2e8), end = h.get<Address>(layer + 0x2f0);
    const Address capacity = h.get<Address>(layer + 0x2f8), widget = h.get<Address>(layer + 0x338);
    if (h.fault || end < begin || capacity < end || end - begin != 24 || capacity - begin > 4096
        || (capacity - begin) % 4 || !h.readable(begin, 24) || !h.readable(widget, 0x870)
        || h.get<Address>(widget) != module.base + 0x1b13b50 || h.get<float>(widget + 0x758) != 55.0f) return false;
    float stops[6]; memcpy(stops, reinterpret_cast<const void*>(begin), sizeof(stops));
    if (!akaine_cli::six_stops(stops, 6)) return false;
    // +430 is a temporary highlight override; native d66f08 writes the
    // effective current ordinal to +434, including normal swipe updates.
    const int override = h.get<int>(layer + 0x430), selected = h.get<int>(layer + 0x434);
    if (h.fault || override < -1 || override > 5 || selected < 0 || selected > 5) return false;
    *ordinal = selected;
    return true;
}
Address visible_pack(Reader& h, Address scene, int* ordinal) {
    constexpr Size LIMIT = 384;
    Address queue[LIMIT] = {scene}, seen[LIMIT] = {};
    Size cursor = 0, count = 1, checked = 0;
    Address result = 0;
    while (cursor < count && checked < LIMIT) {
        const Address node = queue[cursor++];
        bool duplicate = false;
        for (Size i = 0; i < checked; ++i) if (seen[i] == node) duplicate = true;
        if (duplicate) continue;
        seen[checked++] = node;
        if (!h.readable(node, 0x1c2)) return 0;
        const Address vt = h.get<Address>(node);
        if (!module_readable(vt, sizeof(Address))) return 0;
        const unsigned char visible = h.get<unsigned char>(node + 0x1c1);
        if (visible > 1) return 0;
        if (!visible) continue; // Hidden ancestors hide their whole subtree.
        if (vt == module.base + 0x1b828b8) {
            int selected = -1;
            if (result || !pack_fields(h, node, &selected)) return 0;
            result = node; *ordinal = selected;
            continue;
        }
        const Address vector = h.get<Address>(node + 0x140);
        if (!vector) continue;
        if (!h.readable(vector, 24)) return 0;
        const Address begin = h.get<Address>(vector), end = h.get<Address>(vector + 8), cap = h.get<Address>(vector + 16);
        if (h.fault || end < begin || cap < end || (end - begin) % 8 || cap - begin > 32768
            || (cap - begin) % 8 || end - begin > (LIMIT - count) * 8 || (end != begin && !h.readable(begin, end - begin))) return 0;
        for (Address at = begin; at < end; at += 8) queue[count++] = h.get<Address>(at);
    }
    return h.fault || cursor != count ? 0 : result;
}
Snapshot snapshot() {
    Snapshot result;
    Reader h;
    // The monitor already pinned the Director singleton getter and its vtable.
    using Getter = void* (*)();
    const Address director = Address(reinterpret_cast<Getter>(module.base + DIRECTOR_GETTER)());
    if (!h.readable(director, RUNNING_SCENE_OFFSET + sizeof(Address))
        || h.get<Address>(director) != module.base + DIRECTOR_VTABLE) return result;
    result.scene = h.get<Address>(director + RUNNING_SCENE_OFFSET);
    if (!result.scene || h.fault || !scene_type_name(h.get<Address>(result.scene), result.klass, sizeof(result.klass), &result.game)) return result;
    result.ready = true;
    Address transition_type = 0, transition_name = 0;
    result.transition = !strcmp(result.klass, "17TransitionShutter") && h.get<Address>(result.scene) == module.base + 0x1af1868
        && static_pointer(module.base + 0x1af1868 - sizeof(Address), &transition_type)
        && transition_type == module.base + 0x1a9fff8
        && static_pointer(transition_type + sizeof(Address), &transition_name)
        && transition_name == module.base + 0x4e66e9;
    UiTree domain_tree;
    result.ui = capture_ui(h, result.scene, result.klass, &domain_tree);
    // A rejected optional observer must not poison the other bounded observers.
    h.fault = false;
    if (!domain_tree.built) domain_tree = UiTree(h, result.scene,
        !strcmp(result.klass, "13MainMenuScene") ? h.get<Address>(result.scene + 0x328) : 0,
        !strcmp(result.klass, "15SongSelectScene") ? h.get<Address>(result.scene + 0x380) : 0);
    h.fault = false; result.song_state = cli_song_capture(h, result.scene);
    h.fault = false; result.character_state = character_cli::inspect(h, result.scene, domain_tree);
    h.fault = false; result.account_state = account_controls::inspect(h, result.scene, domain_tree);
    h.fault = false; result.sync_state = cloudsync_cli::inspect(h, result.scene, domain_tree);
    h.fault = false; result.skill_state = skill_cli::inspect(h, result.scene, result.klass, result.character_state);
    h.fault = false; result.filter_state = filter_cli::inspect(h, result.scene, domain_tree);
    h.fault = false; result.navigation_state = navigation_cli::inspect(h, result.scene, result.klass, domain_tree);
    h.fault = false; result.settings_state = settings_cli::inspect(h, result.scene, domain_tree);
    h.fault = false; result.settings_control = settings_panel_cli::inspect(h, result.scene, domain_tree);
    h.fault = false; result.result_state = result_cli::inspect(h, result.scene, result.klass);
    h.fault = false; result.bundle_state = bundle_cli::inspect(h, result.scene, domain_tree);
    h.fault = false; result.advanced_guide = cli_capture_advanced_guide(h, result.scene, result.ui);
    if (result.bundle_state.error_popup) { result.ui.reason = "native_bundle_error"; result.ui.modal_present = true; result.ui.action_count = 0; }
    h.fault = false;
    if (!result.ui.overlays.complete || result.ui.overlays.blocked) {
        result.character_state.blocked = true;
        if (result.character_state.available) result.character_state.reason = result.ui.reason;
        result.account_state.blocked = true;
        result.account_state.can_open = result.account_state.can_login_open = result.account_state.can_fill = false;
        result.account_state.can_submit = result.account_state.can_accept_terms = false;
        result.account_state.can_management_open = result.account_state.can_logout = false;
        result.sync_state.can_download = false;
    }
    result.screen = "other";
    if (result.game) {
        result.screen = "gameplay";
        if (h.readable(result.scene, 0x338)) {
            unsigned difficulty = h.get<uint32_t>(result.scene + 0x320);
            const Address song = h.get<Address>(result.scene + 0x318);
            if (!h.fault && difficulty <= 4 && song_id(song, result.song, sizeof(result.song))) result.difficulty = int(difficulty);
        }
    } else if (!strcmp(result.klass, "15SongSelectScene")) {
        result.screen = "song_select";
        result.layer = visible_pack(h, result.scene, &result.ordinal);
    } else if (!strcmp(result.klass, "10StartScene")) result.screen = "title";
    else if (!strcmp(result.klass, "13MainMenuScene")) result.screen = "main_menu";
    else if (!strcmp(result.klass, "21NormalGameResultScene")) result.screen = "result";
    return result;
}
void number(Json& json, uint64_t value) {
    char text[32]; snprintf(text, sizeof(text), "%llu", static_cast<unsigned long long>(value)); json.add(text);
}
void state_json(Json& json, const Snapshot& value) {
    json.add("{\"screen\":"); json.string(value.screen);
    json.add(",\"scene\":"); if (value.ready) json.string(value.klass); else json.add("null");
    json.add(",\"frame\":"); number(json, frames);
    json.add(",\"gameplay\":"); json.add(value.game ? "true" : "false");
    json.add(",\"song_id\":"); if (value.song[0]) json.string(value.song); else json.add("null");
    json.add(",\"difficulty\":"); if (value.difficulty >= 0) number(json, unsigned(value.difficulty)); else json.add("null");
    json.add(",\"anomaly_replay\":");
    if (!preference_ready || !toggle_mailbox) json.add("null"); else json.add(toggle_mailbox->disabled == 0 ? "true" : "false");
    json.add(",\"category\":");
    if (value.layer && (value.ordinal == 4 || value.ordinal == 5)) {
        json.add("{\"section\":"); number(json, value.ordinal == 5 ? 8 : 7);
        json.add(",\"name\":"); json.string(value.ordinal == 5 ? "mod" : "variety");
        json.add(",\"selected_ordinal\":"); number(json, unsigned(value.ordinal)); json.add("}");
    } else json.add("null");
    json.add(",\"ui\":"); ui_json(json, value.ui);
    json.add(",\"advanced_guide\":"); cli_write_advanced_guide(json, value.advanced_guide);
    json.add(",\"song_selection\":");
    if (!value.song_state.valid) json.add("null");
    else {
        const auto& selection = value.song_state;
        json.add("{\"song_id\":"); if (selection.song[0]) json.string(selection.song); else json.add("null");
        json.add(",\"difficulty\":"); number(json, selection.difficulty);
        json.add(",\"selected_difficulty\":"); number(json, selection.selected_difficulty);
        json.add(",\"sort\":"); number(json, selection.sort);
        json.add(",\"group\":"); number(json, selection.group);
        json.add(",\"reverse\":"); json.add(selection.reverse ? "true" : "false");
        json.add(",\"native_list_count\":"); number(json, (selection.pairs_end - selection.pairs_begin) / 16);
        json.add(",\"pack_id\":"); json.string(selection.pack_id);
        json.add(",\"pack_open\":"); json.add(selection.pack_open ? "true" : "false");
        json.add(",\"filter_open\":"); json.add(selection.filter_open ? "true" : "false");
        json.add("}");
    }
    json.add(",\"character\":"); character_cli::write_state(json, value.character_state);
    json.add(",\"account\":"); account_controls::write_state(json, value.account_state);
    json.add(",\"sync\":"); cloudsync_cli::write_state(json, value.sync_state);
    json.add(",\"skill\":"); skill_cli::write_state(json, value.skill_state);
    json.add(",\"filter\":"); filter_cli::write_state(json, value.filter_state);
    json.add(",\"navigation\":"); navigation_cli::write_state(json, value.navigation_state);
    json.add(",\"settings\":"); settings_cli::write_state(json, value.settings_state);
    json.add(",\"settings_control\":"); settings_panel_cli::write_state(json, value.settings_control);
    json.add(",\"result\":"); result_cli::write_state(json, value.result_state);
    json.add(",\"bundle\":"); bundle_cli::write_state(json, value.bundle_state);
    json.add("}");
}
void respond(const Request& request, const Snapshot& value, const char* error, const char* message) {
    Json json;
    json.add("{\"protocol\":1,\"request_id\":"); json.string(request.id);
    json.add(",\"session\":"); json.string(session);
    json.add(",\"environment\":\"production\",\"command\":"); json.string(request.command);
    json.add(",\"ok\":"); json.add(error ? "false" : "true");
    json.add(",\"state\":"); state_json(json, value);
    json.add(",\"error\":");
    if (error) { json.add("{\"code\":"); json.string(error); json.add(",\"message\":"); json.string(message); json.add("}"); }
    else json.add("null");
    json.add("}\n");
    akaine_cli::atomic_json(directory, ".response.tmp", "response.json", json);
}
bool initialize(uint64_t now) {
    if (getuid() < 10000 || getuid() >= 20000 || !official_thread() || !staging_pins() || !action_pins()
        || !cli_song_pins() || !cli_play_guide_pins() || !character_cli::pins() || !account_controls::pins() || !cloudsync_cli::pins()
        || !skill_cli::pins() || !filter_cli::pins() || !navigation_cli::pins()
        || !settings_panel_cli::pins() || !result_cli::pins() || !bundle_cli::pins()) return false;
    char process[64] = {};
    int cmd = open("/proc/self/cmdline", O_RDONLY | O_CLOEXEC | O_NONBLOCK);
    if (cmd < 0) return false;
    const ssize_t n = read(cmd, process, sizeof(process) - 1); close(cmd);
    if (n <= 0 || strcmp(process, "akai.arc.lmao")) return false;
    int root = open("/data/user/0/akai.arc.lmao", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (!akaine_cli::owned_directory(root, getuid())) { if (root >= 0) close(root); return false; }
    if (mkdirat(root, "files", 0700) && errno != EEXIST) { close(root); return false; }
    int files = openat(root, "files", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC); close(root);
    if (!akaine_cli::owned_files_parent(files, getuid(), getgid())) { if (files >= 0) close(files); return false; }
    if (mkdirat(files, "akaine-cli-v1", 0700) && errno != EEXIST) { close(files); return false; }
    directory = openat(files, "akaine-cli-v1", O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC); close(files);
    if (!akaine_cli::owned_directory(directory, getuid(), true)) { if (directory >= 0) close(directory); directory = -1; return false; }
    snprintf(session, sizeof(session), "%016llx%016llx", static_cast<unsigned long long>(getpid()), static_cast<unsigned long long>(now));
    Json json;
    json.add("{\"protocol\":1,\"environment\":\"production\",\"package\":\"akai.arc.lmao\",\"pid\":"); number(json, unsigned(getpid()));
    json.add(",\"session\":"); json.string(session); json.add(",\"commands\":[\"status\",\"category\",\"ui\",\"song_select\",\"pack_select\",\"pack_close\",\"difficulty\",\"sort\",\"group\",\"reverse\",\"character\",\"account\",\"sync\",\"replay\",\"play\",\"play_download\",\"play_guide\",\"play_set_speed\",\"skill\",\"filter\",\"navigation\",\"gameplay\",\"settings\",\"bundle\"]}\n");
    return akaine_cli::atomic_json(directory, ".bridge.tmp", "bridge.json", json);
}
bool domain_confirmed(const Request& request, const Snapshot& value) {
    const auto& song = value.song_state;
    if (!strcmp(request.command, "bundle")) return value.scene == pending_scene && value.bundle_state.available
        && (!strcmp(request.argument, "dismiss-error") ? value.bundle_state.has_pending_bytes && !value.bundle_state.error_popup
            && strcmp(value.bundle_state.phase, "failed") : !strcmp(value.bundle_state.phase, "downloading"));
    if (!strcmp(request.command, "settings")) {
        const auto& panel = value.settings_control;
        if (value.scene != pending_scene || !panel.available || panel.blocked || panel.reason) return false;
        if (!strcmp(request.argument, "open")) return panel.panel && panel.close_button;
        if (!strcmp(request.argument, "close")) return !panel.panel && panel.open_button;
        if (!panel.panel || !value.settings_state.available) return false;
        if (!strncmp(request.argument, "fps:", 4)) return panel.high_framerate.node
            && panel.high_framerate.current == pending_number && value.settings_state.high_framerate == pending_number;
        if (!strncmp(request.argument, "speed:", 6)) return panel.note_speed.node
            && panel.note_speed.current == pending_number && value.settings_state.highspeed_int == pending_number;
        if (!strncmp(request.argument, "offset:", 7)) return panel.offset.node
            && panel.offset.current == pending_number
            && (value.settings_state.audio_preset ? value.settings_state.offset_bluetooth : value.settings_state.offset_normal) == pending_number;
        return false;
    }
    if (!strcmp(request.command, "navigation") || !strcmp(request.command, "gameplay")) {
        const auto& nav = value.navigation_state;
        if (!strcmp(request.argument, "pause")) return value.scene == pending_scene && nav.available && nav.paused;
        if (!strcmp(request.argument, "resume")) return value.scene == pending_scene && nav.available && !nav.paused;
        if (!strcmp(request.argument, "retry")) return pending_scene_changed && value.game
            && !strcmp(value.song, pending_song) && value.difficulty == pending_number;
        if (!strcmp(request.argument, "quit") || !strcmp(request.argument, "continue")) return pending_scene_changed && song.valid && nav.available;
        if (!strcmp(request.argument, "back")) return pending_scene_changed
            && ((pending_navigation_kind == navigation_cli::SongSelect && !strcmp(value.klass, "13MainMenuScene"))
                || (pending_navigation_kind == navigation_cli::Result && song.valid && nav.available));
        return false;
    }
    if (!strcmp(request.command, "skill"))
        return value.skill_state.native_skill_sealed == request.argument[5] - '0';
    if (!strcmp(request.command, "filter")) {
        const auto& filter = value.filter_state;
        if (!strcmp(request.argument, "open")) return filter.valid && filter.open && filter.ready;
        if (!strcmp(request.argument, "close")) return filter.valid && !filter.open && filter.ready;
        if (!strcmp(request.argument, "reset")) return filter.valid && filter.ready && filter.query_size == 0
            && filter.sort == 1 && filter.group == 0 && filter.reverse == 0;
        char query[akaine_filter::QUERY_LIMIT + 1] = {}; size_t size = 0;
        return !strncmp(request.argument, "query:", 6)
            && akaine_filter::decode_query(request.argument + 6, strlen(request.argument + 6), query, &size)
            && filter_cli::query_confirmed(filter, query, size);
    }
    if (!strcmp(request.command, "replay")) {
        if (!preference_ready || !toggle_mailbox || !settings_guard()) return false;
        using ReadBool = bool (*)(void*, const char*, bool);
        const bool persisted = reinterpret_cast<ReadBool>(module.base + USERDEFAULT_GET_BOOL)(
            reinterpret_cast<void*>(settings_instance), ANOMALY_REPLAY_KEY, true);
        return persisted == (pending_number == 1) && toggle_mailbox->disabled == unsigned(1 - pending_number);
    }
    if ((!strcmp(request.command, "play_guide") || !strcmp(request.command, "play_set_speed")) && value.game)
        return !strcmp(value.song, request.argument) && value.difficulty == pending_number;
    if (!strcmp(request.command, "play_set_speed"))
        return value.scene == pending_scene && song.valid && !strcmp(song.song, request.argument)
            && int(song.selected_difficulty) == pending_number && value.ui.identity.available
            && value.ui.overlays.complete && !overlay_cli::has_note_speed(value.ui.overlays);
    if (!strcmp(request.command, "play_download") || !strcmp(request.command, "play_guide"))
        return value.scene == pending_scene && song.valid && !strcmp(song.song, request.argument)
            && int(song.difficulty) == pending_number && value.ui.identity.available && !value.ui.modal_present
            && value.ui.overlays.complete && !value.ui.overlays.blocked;
    if (!strcmp(request.command, "play"))
        return value.game && !strcmp(value.song, request.argument) && value.difficulty == pending_number;
    if (!strcmp(request.command, "song_select")) return song.valid && !strcmp(song.song, request.argument);
    if (!strcmp(request.command, "pack_select")) return song.valid && !song.pack_open && !strcmp(song.pack_id, request.argument);
    if (!strcmp(request.command, "pack_close")) return song.valid && !song.pack_open;
    if (!strcmp(request.command, "difficulty")) return song.valid && int(song.difficulty) == pending_number;
    if (!strcmp(request.command, "sort")) return song.valid && int(song.sort) == pending_number;
    if (!strcmp(request.command, "group")) return song.valid && int(song.group) == pending_number;
    if (!strcmp(request.command, "reverse")) return song.valid && int(song.reverse) == pending_number;
    if (!strcmp(request.command, "character")) {
        const auto& character = value.character_state;
        if (!character.available) return false;
        if (!strcmp(request.argument, "open")) return character.dialog && character.select_callback && !character.blocked && !character.reason;
        if (!strcmp(request.argument, "close")) return !character.dialog && character.equipped_id == pending_number;
        return character.dialog && character.preview_id == pending_number;
    }
    if (!strcmp(request.command, "account")) {
        const auto& account = value.account_state;
        if (!strcmp(request.argument, "open")) return !strcmp(account.kind, "logged_out_menu") || !strcmp(account.kind, "logged_in_menu");
        if (!strcmp(request.argument, "login_open")) return (!account.blocked && !strcmp(account.kind, "login"))
            || !strcmp(account.kind, "login_terms_required");
        if (!strcmp(request.argument, "terms_accept")) return !account.blocked && !strcmp(account.kind, "login");
        if (!strcmp(request.argument, "submit")) return account.signed_in_known && account.signed_in;
        if (!strcmp(request.argument, "management_open")) return !account.blocked && account.can_logout
            && account.signed_in_known && account.signed_in && !strcmp(account.kind, "account_management");
        if (!strcmp(request.argument, "logout")) return account_controls::logout_confirmed(account, value.ready,
            value.transition, value.ui.overlays.complete, value.ui.overlays.blocked);
    }
    if (!strcmp(request.command, "sync")) return !strcmp(value.sync_state.phase, "success");
    return false;
}
const char* account_error(account_controls::Result result) {
    using Result = account_controls::Result;
    switch (result) {
        case Result::ok: return nullptr;
        case Result::unavailable: return "ACCOUNT_UNAVAILABLE";
        case Result::blocked: return "ACCOUNT_BLOCKED";
        case Result::field_rejected: return "FIELD_REJECTED";
        case Result::pin_mismatch: return "NATIVE_GUARD";
        case Result::fault: return "NATIVE_GUARD";
    }
    return "NATIVE_GUARD";
}
const char* overlay_error(const Snapshot& value) {
    if (!value.ui.overlays.complete) return "OVERLAY_SCAN_INCOMPLETE";
    return value.ui.overlays.blocked ? "INPUT_BLOCKED" : nullptr;
}
bool guide_progressed(const overlay_cli::View& before, const overlay_cli::View& after) {
    if (!before.complete || before.count != 1 || !after.complete) return false;
    for (Size i = 0; i < after.count; ++i) {
        const auto& item = after.items[i];
        if (item.node == before.items[0].node)
            return item.step_index != before.items[0].step_index || item.pending_steps != before.items[0].pending_steps
                || (before.items[0].active && !item.active);
    }
    return true;
}
void dispatch_domain(const Request& request, const Snapshot& value) {
    if ((!strcmp(request.command, "character") && (!strcmp(request.argument, "list") || !strcmp(request.argument, "status")))
        || (!strcmp(request.command, "account") && !strcmp(request.argument, "status"))
        || (!strcmp(request.command, "sync") && !strcmp(request.argument, "status"))) {
        respond(request, value, nullptr, nullptr); return;
    }
    if ((!strcmp(request.command, "skill") || !strcmp(request.command, "filter") || !strcmp(request.command, "navigation")
        || !strcmp(request.command, "gameplay") || !strcmp(request.command, "settings") || !strcmp(request.command, "bundle")) && !strcmp(request.argument, "status")) {
        respond(request, value, nullptr, nullptr); return;
    }
    if (!strcmp(request.command, "play_set_speed")) {
        const auto& song = value.song_state;
        if (!value.ready || value.transition || value.game || !song.valid || song.pack_open || song.filter_open
            || strcmp(song.song, request.argument) || song.difficulty != song.selected_difficulty
            || !value.ui.identity.available || !value.ui.overlays.complete || value.ui.overlays.count != 1
            || !overlay_cli::has_note_speed(value.ui.overlays) || !value.ui.overlays.items[0].can_set_speed
            || value.ui.identity.modal != value.ui.overlays.items[0].node) {
            respond(request, value, "NOTE_SPEED_UNAVAILABLE", "The exact native Note Speed setup is unavailable for this selected chart."); return;
        }
        Reader h; UiTree tree(h, value.scene);
        if (!note_speed_modal_only(h, value.scene, tree, value.ui.overlays)) {
            respond(request, value, "UI_BLOCKED", "Another native modal blocks Note Speed confirmation."); return;
        }
        pending = request; pending_scene = value.scene; pending_number = int(song.selected_difficulty);
        domain_dispatching = true;
        const char* error = overlay_cli::set_note_speed(h, value.scene, song.selected, song.selected_difficulty, value.ui.overlays);
        domain_dispatching = false;
        if (error) { respond(request, snapshot(), error, "Native Note Speed Set rejected the action."); return; }
        waiting = true; return;
    }
    if (!strcmp(request.command, "bundle")) {
        if (!value.ready || value.transition || !value.ui.overlays.complete || value.ui.overlays.blocked) {
            respond(request, value, "INPUT_BLOCKED", "Native scene or overlay blocks bundle confirmation."); return;
        }
        pending = request; pending_scene = value.scene;
        Reader h; UiTree tree(h, value.scene);
        domain_dispatching = true;
        const char* error = !strcmp(request.argument, "dismiss-error")
            ? bundle_cli::dismiss_error(h, value.scene, tree, value.bundle_state)
            : bundle_cli::confirm(h, value.scene, tree, value.bundle_state);
        domain_dispatching = false;
        if (error) { respond(request, snapshot(), error, "The native bundle prompt rejected confirmation."); return; }
        waiting = true; return;
    }
    if (!strcmp(request.command, "navigation") || !strcmp(request.command, "gameplay")) {
        if (!value.ready || value.transition || !value.ui.overlays.complete || value.ui.overlays.blocked) {
            respond(request, value, "INPUT_BLOCKED", "Native scene or overlay blocks navigation."); return;
        }
        if ((!strcmp(request.command, "gameplay") && !value.game)
            || (!strcmp(request.command, "navigation") && value.game)) {
            respond(request, value, "WRONG_SCENE", "This navigation command does not apply to the current scene."); return;
        }
        pending = request; pending_scene = value.scene; pending_scene_changed = false; pending_song[0] = 0;
        pending_navigation_kind = int(value.navigation_state.kind);
        pending_number = value.game ? value.difficulty : value.navigation_state.difficulty;
        if (value.song[0]) memcpy(pending_song, value.song, sizeof(pending_song));
        else memcpy(pending_song, value.navigation_state.song, sizeof(pending_song));
        Reader h;
        UiTree tree(h, value.scene, 0, !strcmp(value.klass, "15SongSelectScene") ? h.get<Address>(value.scene + 0x380) : 0);
        domain_dispatching = true;
        const char* error = navigation_cli::act(h, value.scene, value.klass, tree, value.navigation_state, request.argument);
        domain_dispatching = false;
        if (error) { respond(request, snapshot(), error, "Native navigation callback rejected the action; inspect fresh status."); return; }
        waiting = true;
        return;
    }
    if (const char* error = overlay_error(value)) {
        respond(request, value, error, "Native overlay state blocks this action; inspect ui list."); return;
    }
    if (!value.ready || value.transition || value.game) {
        respond(request, value, "WRONG_SCENE", "This operation requires its current native menu."); return;
    }
    if (const char* error = akaine_cli::request_guard(request, session, wall_ms())) {
        respond(request, value, error, "The request expired before native dispatch."); return;
    }
    Reader h;
    if (h.fault) { respond(request, value, "NATIVE_GUARD", "Native memory ranges are unavailable."); return; }
    pending = request; pending_scene = value.scene; pending_layer = 0; pending_number = -1;
    domain_dispatching = true;
    const char* error = nullptr;
    if (!strcmp(request.command, "settings")) {
        UiTree tree(h, value.scene, !strcmp(value.klass, "13MainMenuScene") ? h.get<Address>(value.scene + 0x328) : 0,
            !strcmp(value.klass, "15SongSelectScene") ? h.get<Address>(value.scene + 0x380) : 0);
        const auto panel = settings_panel_cli::inspect(h, value.scene, tree);
        if (!strcmp(request.argument, "open")) error = settings_panel_cli::open(h, panel);
        else if (!strcmp(request.argument, "close")) error = settings_panel_cli::close(h, panel);
        else if (!strncmp(request.argument, "fps:", 4)) {
            pending_number = request.argument[4] - '0';
            const auto preferences = settings_cli::inspect(h, value.scene, tree);
            error = settings_panel_cli::set_fps(h, panel, pending_number, preferences.available ? preferences.high_framerate : -1);
        }
        else if (!strncmp(request.argument, "speed:", 6)) {
            pending_number = int(strtol(request.argument + 6, nullptr, 10));
            error = settings_panel_cli::set_speed(h, panel, pending_number);
        } else if (!strncmp(request.argument, "offset:", 7)) {
            pending_number = int(strtol(request.argument + 7, nullptr, 10));
            error = settings_panel_cli::set_offset(h, panel, pending_number);
        } else error = "INVALID_ARGUMENT";
    } else if (!strcmp(request.command, "filter")) {
        UiTree tree(h, value.scene, 0, h.get<Address>(value.scene + 0x380));
        if (!value.ui.identity.available || value.ui.modal_present) error = "UI_BLOCKED";
        else if (!strcmp(request.argument, "open")) error = filter_cli::open(h, value.scene, tree);
        else if (!strcmp(request.argument, "close")) error = filter_cli::close(h, value.scene, tree);
        else if (!strcmp(request.argument, "reset")) error = filter_cli::reset(h, value.scene, tree);
        else {
            char query[akaine_filter::QUERY_LIMIT + 1] = {}; size_t size = 0;
            if (strncmp(request.argument, "query:", 6)
                || !akaine_filter::decode_query(request.argument + 6, strlen(request.argument + 6), query, &size)) error = "INVALID_ARGUMENT";
            else error = filter_cli::query(h, value.scene, tree, query, size);
        }
    } else if (!strcmp(request.command, "skill")) {
        if (strncmp(request.argument, "seal:", 5)) error = "INVALID_ARGUMENT";
        else error = skill_cli::seal(h, value.skill_state, request.argument[5] == '1');
    } else if (!strcmp(request.command, "replay")) {
        pending_number = request.argument[0] - '0';
        if (!value.ui.identity.available || value.ui.modal_present) error = "UI_BLOCKED";
        else if (!preference_ready || !toggle_mailbox || !settings_guard()) error = "NATIVE_GUARD";
        else if (!cli_dispatch_allowed()) error = "EXPIRED";
        else toggle_setter(nullptr, &pending_number, nullptr);
    } else if (!strcmp(request.command, "play_guide")) {
        pending_number = int(value.song_state.selected_difficulty);
        error = cli_song_skip_advanced_guide(h, value.scene, request.argument, value.ui);
    } else if (!strcmp(request.command, "play_download")) {
        pending_number = int(value.song_state.selected_difficulty);
        error = cli_song_confirm_download(h, value.scene, request.argument, value.ui);
    } else if (!strcmp(request.command, "play")) {
        pending_number = int(value.song_state.selected_difficulty);
        error = cli_song_play(h, value.scene, request.argument, value.ui);
    } else if (!strcmp(request.command, "sync")) {
        UiTree tree(h, value.scene, !strcmp(value.klass, "13MainMenuScene") ? h.get<Address>(value.scene + 0x328) : 0, 0);
        const auto result = cloudsync_cli::download(h, value.scene, tree, request, session, wall_ms());
        if (result != cloudsync_cli::Result::ok) error = "SYNC_UNAVAILABLE";
    } else if (!strcmp(request.command, "character")) {
        UiTree tree(h, value.scene, !strcmp(value.klass, "13MainMenuScene") ? h.get<Address>(value.scene + 0x328) : 0,
            !strcmp(value.klass, "15SongSelectScene") ? h.get<Address>(value.scene + 0x380) : 0);
        const auto view = character_cli::inspect(h, value.scene, tree);
        if (!strcmp(request.argument, "open")) error = character_cli::open(h, view);
        else if (!strcmp(request.argument, "close")) {
            pending_number = view.dialog ? view.preview_id : view.equipped_id;
            error = character_cli::close(h, view);
        } else {
            pending_number = int(strtoul(request.argument, nullptr, 10));
            error = character_cli::select(h, view, pending_number);
        }
    } else if (!strcmp(request.command, "account")) {
        UiTree tree(h, value.scene, !strcmp(value.klass, "13MainMenuScene") ? h.get<Address>(value.scene + 0x328) : 0, 0);
        using namespace account_controls;
        if (!strcmp(request.argument, "open")) error = account_error(account_controls::open(h, value.scene, tree));
        else if (!strcmp(request.argument, "login_open")) error = account_error(login_open(h, value.scene, tree));
        else if (!strcmp(request.argument, "terms_accept")) error = account_error(accept_terms(h, value.scene, tree));
        else if (!strcmp(request.argument, "submit")) error = account_error(submit_login(h, value.scene, tree, &pending_login_submit));
        else if (!strcmp(request.argument, "management_open")) error = account_error(management_open(h, value.scene, tree));
        else if (!strcmp(request.argument, "logout")) error = account_error(logout(h, value.scene, tree));
        else {
            CredentialBuffer credentials;
            const CredentialResult loaded = load_credential(directory, request, session, wall_ms(), credentials);
            if (loaded != CredentialResult::ok) error = "CREDENTIAL_REJECTED";
            else if (akaine_cli::request_guard(request, session, wall_ms())) error = "EXPIRED";
            else error = account_error(fill_login(h, value.scene, tree, credentials.username, credentials.username_size,
                credentials.password, credentials.password_size));
            credentials.clear();
            domain_dispatching = false;
            respond(request, snapshot(), error, error ? "The native login fields rejected the private input." : nullptr);
            return;
        }
    } else {
        if (!value.ui.identity.available || value.ui.modal_present) error = "UI_BLOCKED";
        else if (!strcmp(request.command, "song_select")) error = cli_song_select(h, value.scene, request.argument);
        else if (!strcmp(request.command, "pack_select")) error = cli_pack_select(h, value.scene, request.argument);
        else if (!strcmp(request.command, "pack_close")) error = cli_pack_close(h, value.scene);
        else {
            pending_number = int(strtoul(request.argument, nullptr, 10));
            if (!strcmp(request.command, "difficulty")) error = cli_song_difficulty(h, value.scene, unsigned(pending_number));
            else if (!value.song_state.valid) error = "WRONG_SCENE";
            else error = cli_song_sort_group(h, value.scene,
                !strcmp(request.command, "sort") ? unsigned(pending_number) : value.song_state.sort,
                !strcmp(request.command, "group") ? unsigned(pending_number) : value.song_state.group,
                !strcmp(request.command, "reverse") ? unsigned(pending_number) : value.song_state.reverse);
        }
    }
    domain_dispatching = false;
    if (error) { respond(request, snapshot(), error, "The current native control rejected this operation."); return; }
    waiting = true;
}
void poll(uint64_t now) {
    if (!official_thread()) return;
    if (!attempted) {
        attempted = true;
        const bool ready = initialize(now);
        __android_log_print(ready ? ANDROID_LOG_INFO : ANDROID_LOG_ERROR, TAG, "production_cli_init status=%s protocol=1 owner_gl_thread=1", ready ? "ready" : "rejected");
        if (!ready) { if (directory >= 0) close(directory); directory = -1; }
    }
    if (directory < 0 || (polled_ns && now >= polled_ns && now - polled_ns < 100000000ULL)) return;
    polled_ns = now;
    if (!staging_pins() || !action_pins()) { close(directory); directory = -1; return; }
    if (waiting) {
        if (!strcmp(pending.command, "sync")) {
            const Snapshot current = snapshot();
            Reader sync_reader;
            domain_dispatching = true;
            cloudsync_cli::poll(sync_reader, current.scene, pending, session, wall_ms());
            domain_dispatching = false;
        }
        const Snapshot value = snapshot();
        const char* error = nullptr;
        const uint64_t wall_now = wall_ms();
        if (!strcmp(pending.command, "bundle")) {
            if (!wall_now || wall_now >= pending.expires) error = "ACTION_TIMEOUT";
            else if (domain_confirmed(pending, value)) { waiting = false; respond(pending, value, nullptr, nullptr); return; }
            else if (value.scene != pending_scene) error = "SCENE_CHANGED";
            else if (strcmp(pending.argument, "dismiss-error") && !strcmp(value.bundle_state.phase, "failed")) error = "BUNDLE_DOWNLOAD_FAILED";
            if (error) { waiting = false; respond(pending, value, error, "Native bundle download start is unconfirmed; do not automatically retry."); }
            return;
        }
        if (!strcmp(pending.command, "navigation") || !strcmp(pending.command, "gameplay")) {
            if (value.scene != pending_scene || value.transition) pending_scene_changed = true;
            if (!wall_now || wall_now >= pending.expires) error = "ACTION_TIMEOUT";
            else if (domain_confirmed(pending, value)) { waiting = false; respond(pending, value, nullptr, nullptr); return; }
            if (error) { waiting = false; respond(pending, value, error, "Native navigation outcome is unconfirmed; do not automatically retry."); }
            return;
        }
        if (!strcmp(pending.command, "account") && !strcmp(pending.argument, "logout")) {
            if (!wall_now || wall_now >= pending.expires) error = "ACTION_TIMEOUT";
            else if (domain_confirmed(pending, value)) { waiting = false; respond(pending, value, nullptr, nullptr); return; }
            if (error) { waiting = false; respond(pending, value, error, "Native logout outcome is unconfirmed; do not automatically retry."); }
            return;
        }
        if (!strcmp(pending.command, "ui")) {
            if (!wall_now || wall_now >= pending.expires) error = "ACTION_TIMEOUT";
            else if (!value.ready) error = "SCENE_CHANGED";
            else if (!strncmp(pending.argument, "onboarding_", 11)) {
                const unsigned stage = pending_ui_identity.flags[2];
                const bool same_scene = value.scene == pending_scene && !strcmp(value.klass, "13MainMenuScene");
                const bool progressed = stage == 1 ? value.ui.onboarding_stage && !strcmp(value.ui.onboarding_stage, "offset_setup")
                    : stage == 2 ? value.ui.onboarding_stage && !strcmp(value.ui.onboarding_stage, "offset_skip_confirmation")
                    : stage == 3 && value.ui.identity.available && value.ui.onboarding_settings_ready
                        && value.ui.overlays.complete && !value.ui.overlays.blocked;
                if (same_scene && progressed) {
                    waiting = false; respond(pending, value, nullptr, nullptr); return;
                }
                if (!same_scene && !value.transition) error = "SCENE_CHANGED";
            }
            else if (!strncmp(pending.argument, "pack_hint_continue.", 19) || !strncmp(pending.argument, "main_hint_continue.", 19) || !strncmp(pending.argument, "notification_hint_continue.", 27)) {
                if (value.scene != pending_scene) error = "SCENE_CHANGED";
                else if (guide_progressed(pending_overlays, value.ui.overlays)) {
                    waiting = false; respond(pending, value, nullptr, nullptr); return;
                }
            }
            else {
                const bool start_action = !strncmp(pending.argument, "start_continue.", 15);
                const bool pack_action = !strncmp(pending.argument, "pack_open.", 10);
                const bool same_scene = value.scene == pending_scene;
                const bool expected_scene = !strcmp(value.klass, "15SongSelectScene") || (start_action && !strcmp(value.klass, "13MainMenuScene"))
                    || (!start_action && value.game);
                const bool start_progress = start_action && same_scene && (value.ui.start_flags != pending_start_flags || value.ui.modal_present != bool(pending_ui_identity.modal));
                Reader pack_confirmation;
                const bool pack_progress = pack_action && same_scene && value.layer != 0 && value.ui.identity.available && !value.ui.modal_present
                    && pack_confirmation.get<Address>(value.scene + 0x3a8) == value.layer
                    && pack_confirmation.get<Address>(value.layer + 0x148) != 0 && !pack_confirmation.fault;
                if ((!same_scene && expected_scene && !pack_action) || start_progress || pack_progress) {
                    waiting = false; respond(pending, value, nullptr, nullptr); return;
                }
                if (!same_scene && !value.transition) error = "SCENE_CHANGED";
            }
            if (error) { waiting = false; respond(pending, value, error, "UI action outcome could not be confirmed; do not automatically retry."); }
            return;
        }
        if (!strcmp(pending.command, "account") && !strcmp(pending.argument, "submit")
            && wall_now && wall_now < pending.expires && value.scene == pending_scene
            && !domain_confirmed(pending, value) && pending_login_submit.failed(value.account_state)) {
            waiting = false;
            respond(pending, value, "ACCOUNT_LOGIN_FAILED", "Native login returned a recognized inline failure; do not automatically retry.");
            return;
        }
        if (strcmp(pending.command, "category")) {
            if (!strcmp(pending.command, "play") || !strcmp(pending.command, "play_guide") || !strcmp(pending.command, "play_set_speed")) {
                if (!wall_now || wall_now >= pending.expires) error = "ACTION_TIMEOUT";
                else if (domain_confirmed(pending, value)) { waiting = false; respond(pending, value, nullptr, nullptr); return; }
                else if (strcmp(pending.command, "play_set_speed") && overlay_cli::has_note_speed(value.ui.overlays)) error = "NOTE_SPEED_SETUP_REQUIRED";
                else if (!strcmp(pending.command, "play") && !value.game && value.scene == pending_scene && value.ui.modal_present
                    && value.song_state.valid && int(value.song_state.selected_difficulty) == pending_number) {
                    Reader h;
                    Address button = 0;
                    if (!cli_song_download_prompt(h, value.scene, pending.argument, value.ui, &button)) {
                        waiting = false;
                        respond(pending, value, "DOWNLOAD_CONFIRMATION_REQUIRED", "Confirm this chart download with play_download; gameplay has not started.");
                        return;
                    }
                }
                else if (value.game) error = "PLAY_TARGET_CHANGED";
                if (error) { waiting = false; respond(pending, value, error, "Gameplay was not confirmed for the requested chart; do not automatically retry."); }
                return;
            }
            if (!wall_now || wall_now >= pending.expires) error = "ACTION_TIMEOUT";
            else if (!value.ready || value.scene != pending_scene) error = "SCENE_CHANGED";
            else if (!strcmp(pending.command, "sync") && !strcmp(value.sync_state.phase, "failed")) error = "SYNC_FAILED";
            else if (domain_confirmed(pending, value)) { waiting = false; respond(pending, value, nullptr, nullptr); return; }
            if (error) { waiting = false; respond(pending, value, error, "Native action outcome could not be confirmed; do not automatically retry."); }
            return;
        }
        if (!value.ready || value.scene != pending_scene || value.layer != pending_layer) error = "SCENE_CHANGED";
        else if (!wall_now || wall_now >= pending.expires) error = "ACTION_TIMEOUT";
        else if (akaine_cli::section_ordinal(pending.section, value.ordinal)) {
            waiting = false; respond(pending, value, nullptr, nullptr); return;
        }
        if (error) { waiting = false; respond(pending, value, error, "Category selection could not be confirmed."); }
        return;
    }
    char bytes[akaine_cli::REQUEST_LIMIT + 1] = {};
    const Size n = akaine_cli::consume(directory, bytes);
    if (!n) return;
    Request request;
    if (!akaine_cli::parse(bytes, n, &request)) return;
    const char* error = akaine_cli::request_guard(request, session, wall_ms());
    if (!error) error = ledger.remember(request.id);
    const Snapshot value = snapshot();
    if (error) { respond(request, value, error, "Request identity or deadline was rejected."); return; }
    if (!strcmp(request.command, "status")) { respond(request, value, nullptr, nullptr); return; }
    if (!strcmp(request.command, "ui")) {
        if (!strcmp(request.argument, "list")) { respond(request, value, nullptr, nullptr); return; }
        if (!akaine_cli::token_context(request.argument, value.ui.context)) {
            respond(request, value, "STALE_UI", "The action token does not match the current UI context."); return;
        }
        CliUiAction action;
        for (Size i = 0; i < value.ui.action_count; ++i) {
            const Size length = strlen(value.ui.actions[i].name);
            if (!strncmp(request.argument, value.ui.actions[i].name, length) && request.argument[length] == '.') action = value.ui.actions[i];
        }
        if (!action.name) { respond(request, value, "ACTION_UNAVAILABLE", "The named action is not currently available."); return; }
        const Snapshot fresh = snapshot();
        if (!fresh.ready || fresh.scene != value.scene || fresh.ui.context != value.ui.context
            || !akaine_cli::same_ui(fresh.ui.identity, value.ui.identity) || !ui_pins() || !staging_pins()) {
            respond(request, fresh, "STALE_UI", "The UI changed before action dispatch."); return;
        }
        if (const char* deadline = akaine_cli::request_guard(request, session, wall_ms())) {
            respond(request, fresh, deadline, "The request expired before UI dispatch."); return;
        }
        pending = request; pending_scene = value.scene; pending_layer = 0;
        pending_start_flags = value.ui.start_flags; pending_ui_identity = value.ui.identity;
        pending_overlays = fresh.ui.overlays;
        waiting = true;
        if (!strcmp(action.name, "pack_hint_continue") || !strcmp(action.name, "main_hint_continue") || !strcmp(action.name, "notification_hint_continue")) {
            Reader reader;
            domain_dispatching = true;
            const char* error = overlay_cli::advance(reader, value.scene, pending_overlays);
            domain_dispatching = false;
            if (error) { waiting = false; respond(request, snapshot(), error, "The native tutorial callback rejected this action."); }
        } else if (!strncmp(action.name, "onboarding_", 11)) {
            if (!onboarding_pins()) { waiting = false; respond(request, snapshot(), "NATIVE_GUARD", "Onboarding callback pins changed."); return; }
            reinterpret_cast<void (*)(Address)>(module.base + 0xf66c9c)(action.node);
        } else if (!strcmp(action.name, "start_continue"))
            reinterpret_cast<bool (*)(Address, void*, void*)>(module.base + 0x1591420)(action.closure, nullptr, nullptr);
        else if (!strcmp(action.name, "pack_open"))
            reinterpret_cast<void (*)(Address)>(module.base + 0xf66c9c)(action.node);
        else
            reinterpret_cast<void (*)(Address, bool)>(module.base + 0x13d5f98)(value.scene, false);
        return;
    }
    if (strcmp(request.command, "category")) { dispatch_domain(request, value); return; }
    if (const char* error = overlay_error(value)) {
        respond(request, value, error, "Native overlay state blocks category selection; inspect ui list."); return;
    }
    if (!value.ready || !value.layer || strcmp(value.klass, "15SongSelectScene") || value.ui.modal_present || !value.ui.identity.available) {
        respond(request, value, "WRONG_SCENE", "Category selection requires the visible pack selector."); return;
    }
    // Read guards again just before the single typed native call. The target is
    // the exact visible PackListLayer, never the SongSelectScene root.
    Reader guard;
    int ordinal = -1;
    if (!pack_fields(guard, value.layer, &ordinal) || !action_pins() || !staging_pins()) {
        respond(request, value, "NATIVE_GUARD", "The pack selector no longer matches the pinned layout."); return;
    }
    if (const char* deadline = akaine_cli::request_guard(request, session, wall_ms())) {
        respond(request, value, deadline, "The request expired before category dispatch."); return;
    }
    pending = request; pending_scene = value.scene; pending_layer = value.layer;
    reinterpret_cast<void (*)(Address, uint32_t)>(module.base + 0xa04a00)(value.layer, uint32_t(request.section));
    waiting = true;
}
}
