enum class EntryAction { none, title_continue, main_music, pack_open,
                         setup, cancel_offset, skip_offset, pack_hint, main_hint, notification_hint, partner_hint, song_hint };

#ifdef AKAINE_ONBOARDING_CLI
struct CliUiAction { const char* name=nullptr; const char* label=nullptr; Address node=0,closure=0; };
struct CliUiState {
    akaine_cli::UiIdentity identity;
    CliUiAction actions[1];
    Size action_count=0;
    const char* reason=nullptr;
    const char* onboarding_stage=nullptr;
    bool onboarding_settings_ready=false;
};
#include "cli_onboarding73.h"
#include "tutorial_pins73.h"
#include "cli_tutorial73.h"
#endif

struct EntryUi {
    akaine_cli::UiIdentity identity;
    EntryAction action = EntryAction::none;
    const char* reason = "unsupported_scene";
    uint64_t context = 0;
    bool modal = false;
    bool pack_open = false;
#ifdef AKAINE_ONBOARDING_CLI
    tutorial73::Guide guide;
    const char* onboarding_stage = nullptr;
    bool scan_complete = false, onboarding_settings_ready = false;
#endif
#ifdef AKAINE_PREPLAY_CLI
    bool note_speed_modal_ready=false;
#endif
};

akaine_cli::UiContext entry_context;
EntryUi pending_entry;

#include "entry_callbacks73.h"

const char* entry_action_name(EntryAction action) {
    switch (action) {
        case EntryAction::title_continue: return "start_continue";
        case EntryAction::main_music: return "main_music";
        case EntryAction::pack_open: return "pack_open";
        case EntryAction::setup: return "onboarding_setup";
        case EntryAction::cancel_offset: return "onboarding_cancel";
        case EntryAction::skip_offset: return "onboarding_skip";
        case EntryAction::pack_hint: return "pack_hint_continue";
        case EntryAction::song_hint: return "song_hint_continue";
        case EntryAction::partner_hint: return "partner_hint_continue";
        case EntryAction::main_hint: return "main_hint_continue";
        case EntryAction::notification_hint: return "notification_hint_continue";
        default: return "";
    }
}

const char* entry_action_label(EntryAction action) {
    switch (action) {
        case EntryAction::title_continue: return "Continue";
        case EntryAction::main_music: return "Music";
        case EntryAction::pack_open: return "Pack Select";
        case EntryAction::setup: return "Setup";
        case EntryAction::cancel_offset: return "Cancel offset setup";
        case EntryAction::skip_offset: return "Confirm skip offset setup";
        case EntryAction::pack_hint: return "Continue pack selection guide";
        case EntryAction::song_hint: return "Continue song selection guide";
        case EntryAction::partner_hint: return "Continue partner selection guide";
        case EntryAction::main_hint: return "Continue main menu guide";
        case EntryAction::notification_hint: return "Continue notification guide (requests Android permission)";
        default: return "";
    }
}

bool entry_pins() {
    for (const auto& pin : ENTRY_PINS)
        if (!in_ranges(module.executable,module.executable_count,core+pin.address,pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(core+pin.address),pin.bytes,pin.size))
            return false;
    return true;
}

EntryUi capture_entry(Reader& reader,Address scene,Address type,const UiTree& tree,
                      Address visible_pack,bool foreign_input) {
    EntryUi ui;
    auto& identity=ui.identity;
    identity.scene=scene;
    identity.scene_type=type;
    const bool title=type==core+entry_title_type;
    const bool menu=type==core+entry_menu_type;
    const bool select=type==core+song_scene_type;
    if (title || menu || select) {
        ui.reason="not_ready";
        if (tree.has_modal || foreign_input) {
            ui.modal=true;
            identity.modal=scene;
            ui.reason=tree.loading?"loading":"input_blocked";
        } else if (!tree.valid) ui.reason="unsupported_ui_tree";
        else if (entry_pins() && reader.get<uint8_t>(scene+0x1c0)==1) {
            identity.available=true;
            if (title) {
                const auto popup=reader.get<uint8_t>(scene+0x3f0);
                identity.flags[1]=popup;
                if (popup==1) {
                    ui.modal=true;
                    identity.modal=scene;
                    ui.reason=reader.get<Address>(scene+0x320)?"loading":"unsupported_modal";
                } else if (!popup && !reader.fault) {
                    unsigned flags=0;
                    const auto closure=start_closure(reader,scene,&flags);
                    identity.flags[0]=flags;
                    if (closure) {
                        ui.action=EntryAction::title_continue;
                        identity.nodes[0]=scene;
                        identity.callbacks[0]=closure;
                    }
                }
            } else {
                const Address root=reader.get<Address>(scene+(menu?0x328:0x380));
                if (select && visible_pack) {
                    ui.pack_open=true;
                    identity.flags[1]=1;
                    ui.reason=nullptr;
                } else if (root) {
                    for (Size i=0;i<tree.count;++i) {
                        const auto& item=tree.queue[i];
                        if (item.parent!=root || !item.ancestors_enabled) continue;
                        Address closure=0;
                        if (!(menu?music_ready(reader,scene,item.node,&closure):
                                pack_button_ready(reader,scene,item.node,&closure))) continue;
                        if (identity.nodes[0]) {
                            reader.fault=true;
                            break;
                        }
                        ui.action=menu?EntryAction::main_music:EntryAction::pack_open;
                        identity.nodes[0]=item.node;
                        identity.callbacks[0]=closure;
                    }
                }
            }
        }
    }
#ifdef AKAINE_ONBOARDING_CLI
    if (tree.valid && !tree.loading && !tree.modal && !foreign_input &&
#if defined(AKAINE_CHARACTER_CLI) && !defined(AKAINE_PLAIN_GUIDES)
        !tree.character_modal &&
#endif
#ifdef AKAINE_PREPLAY_CLI
        !tree.preplay_speed && !tree.preplay_dialog &&
#endif
        !reader.fault && (title || menu || select)) {
        ui.scan_complete=!tree.guide && !tree.onboarding_modal && !tree.has_modal;
#ifdef AKAINE_PLAIN_GUIDES
        if (select && tree.character_modal && !tree.guide && !tree.onboarding_modal && !tree.settings_modal)
            ui.scan_complete=true;
#endif
        if (tree.guide) {
            ui.scan_complete=!tree.onboarding_modal &&
#ifdef AKAINE_ACCOUNT_CLI
                !tree.settings_modal &&
#endif
                tutorial73::capture(reader,scene,type,tree,ui.guide);
            const bool partner=ui.guide.action==EntryAction::partner_hint;
#ifdef AKAINE_PLAIN_GUIDES
            if (partner!=bool(tree.character_modal)) ui.scan_complete=false;
#endif
            identity.overlay_count=1;
            identity.overlays[0]=tree.guide;
            identity.interceptors[0]=ui.guide.listener;
            if (tree.pack_hint_dim) {
                identity.overlay_count=2;
                identity.overlays[1]=tree.pack_hint_dim;
                identity.interceptors[1]=tree.pack_hint_listener;
            }
            identity.callbacks[1]=ui.guide.completion;
            identity.callbacks[2]=ui.guide.owner;
            identity.overlay_flags[0]=uint32_t(ui.guide.step | (ui.guide.remaining<<8)
                | (unsigned(ui.guide.active)<<16) | (unsigned(ui.guide.blocks())<<17)
                | (unsigned(ui.guide.closing)<<18));
            if (ui.scan_complete && ui.guide.ready() && ui.guide.action!=EntryAction::none) {
                ui.modal=partner;
                identity.modal=partner?ui.guide.owner:0;
#ifdef AKAINE_PLAIN_GUIDES
                identity.modal_type=partner?core+character_dialog_type:0;
#endif
                identity.available=true;
                ui.action=ui.guide.action;
                identity.nodes[0]=ui.guide.button;
                identity.callbacks[0]=ui.guide.callback;
            }
        } else if (menu && tree.onboarding_modal) {
            CliUiState onboarding;
            if (capture_onboarding(reader,scene,tree,onboarding)) {
                ui.scan_complete=true;
                identity=onboarding.identity;
                identity.scene=scene;
                identity.scene_type=type;
                identity.available=true;
                ui.onboarding_stage=onboarding.onboarding_stage;
                identity.nodes[0]=onboarding.actions[0].node;
                identity.callbacks[0]=onboarding.actions[0].closure;
                ui.action=identity.flags[2]==1?EntryAction::setup:
                          identity.flags[2]==2?EntryAction::cancel_offset:EntryAction::skip_offset;
            } else if (!reader.fault && onboarding.onboarding_settings_ready) {
                ui.onboarding_settings_ready=true;
                ui.scan_complete=true;
            }
        }
    }
#endif
    if (reader.fault) {
        identity.available=false;
        ui.action=EntryAction::none;
        ui.reason="unavailable";
    }
    identity.count=ui.action==EntryAction::none?0:1;
    if (identity.count) ui.reason=ui.action==EntryAction::partner_hint?"input_blocked":nullptr;
    ui.context=entry_context.observe(identity);
    return ui;
}

void write_entry(Json& json,const EntryUi& ui) {
    char context[17]{};
    snprintf(context,sizeof(context),"%016llx",static_cast<unsigned long long>(ui.context));
    json.add("{\"context\":"); json.string(context);
    json.add(",\"actions\":[");
    if (ui.action!=EntryAction::none && ui.context) {
        char token[48]{};
        snprintf(token,sizeof(token),"%s.%s",entry_action_name(ui.action),context);
        json.add("{\"token\":"); json.string(token);
        json.add(",\"name\":"); json.string(entry_action_label(ui.action));
        json.add(",\"enabled\":true}");
    }
    json.add("],\"modal_present\":"); json.add(ui.modal?"true":"false");
    json.add(",\"reason\":"); if (ui.reason) json.string(ui.reason); else json.add("null");
#ifdef AKAINE_ONBOARDING_CLI
    json.add(",\"onboarding_stage\":");
    if (ui.onboarding_stage) json.string(ui.onboarding_stage); else json.add("null");
    json.add(",\"onboarding_settings_ready\":"); json.add(ui.onboarding_settings_ready?"true":"false");
#ifdef AKAINE_PREPLAY_CLI
    json.add(",\"guide_metadata_version\":1,\"note_speed_modal_ready\":");
    json.add(ui.note_speed_modal_ready?"true":"false");
#endif
    tutorial73::write(json,ui.guide,ui.scan_complete);
    json.add(",\"pack_select_open\":");
#else
    json.add(",\"overlays\":[],\"overlay_scan_complete\":false,\"overlay_coverage\":"
             "[\"progression_guide\",\"note_speed_setup\",\"category_tutorial\",\"partner_tutorial\"]"
             ",\"pack_select_open\":");
#endif
    json.add(ui.pack_open?"true":"false");
    json.add("}");
}

bool entry_token(const char* token,const EntryUi& ui) {
    if (ui.action==EntryAction::none || (ui.modal && ui.action!=EntryAction::setup && ui.action!=EntryAction::partner_hint &&
            ui.action!=EntryAction::cancel_offset && ui.action!=EntryAction::skip_offset) || !ui.identity.available ||
            !akaine_cli::token_context(token,ui.context)) return false;
    const char* action=entry_action_name(ui.action);
    const auto size=strlen(action);
    return !strncmp(token,action,size) && token[size]=='.';
}

const char* activate_entry(const EntryUi& ui) {
    if (!cli_dispatch_allowed()) return "EXPIRED";
    if (ui.action==EntryAction::none || !ui.identity.available || !entry_pins()) return "NATIVE_GUARD";
    OfficialHost host;
    switch (ui.action) {
        case EntryAction::title_continue:
            host.call<bool>(entry_title_continue,ui.identity.callbacks[0],Address(0),Address(0));
            break;
        case EntryAction::main_music:
            host.call<void>(entry_music_open,ui.identity.scene,false);
            break;
        case EntryAction::pack_open:
            host.call<void>(entry_pack_release,ui.identity.nodes[0]);
            break;
#ifdef AKAINE_ONBOARDING_CLI
        case EntryAction::setup:
        case EntryAction::cancel_offset:
        case EntryAction::skip_offset:
            if (!onboarding_pins()) return "NATIVE_GUARD";
            host.call<void>(entry_pack_release,ui.identity.nodes[0]);
            break;
        case EntryAction::pack_hint:
        case EntryAction::song_hint:
        case EntryAction::main_hint:
        case EntryAction::notification_hint:
        case EntryAction::partner_hint:
            if (!tutorial73::pins() || !ui.guide.ready()) return "NATIVE_GUARD";
#ifdef AKAINE_PLAIN_GUIDES
            if ((ui.action==EntryAction::partner_hint || !ui.guide.completion) && !tutorial73::plain_pins())
                return "NATIVE_GUARD";
#endif
            if (ui.guide.terminal_callback) {
                Address button=ui.guide.button;
                int release=2;
                host.call<void>(tutorial_next_invoke,ui.guide.callback,&button,&release);
            } else host.call<void>(entry_pack_release,ui.identity.nodes[0]);
            break;
#endif
        default: return "ACTION_UNAVAILABLE";
    }
    return host.fault?"NATIVE_GUARD":nullptr;
}

bool entry_confirmed(const EntryUi& initial,const EntryUi& next) {
    if (next.context==initial.context || !next.identity.scene) return false;
    bool same_scene=next.identity.scene==initial.identity.scene;
    const Address type=next.identity.scene_type;
    switch (initial.action) {
        case EntryAction::title_continue:
            return same_scene ? next.identity.available &&
                (next.identity.flags[0]!=initial.identity.flags[0] || next.identity.flags[1]!=initial.identity.flags[1])
                : type==core+entry_menu_type || type==core+song_scene_type;
        case EntryAction::main_music:
            return !same_scene && (type==core+song_scene_type || type==core+game_type);
        case EntryAction::pack_open:
            return same_scene && next.pack_open && next.identity.available && !next.modal;
#ifdef AKAINE_ONBOARDING_CLI
        case EntryAction::setup:
            return same_scene && next.action==EntryAction::cancel_offset;
        case EntryAction::cancel_offset:
            return same_scene && next.action==EntryAction::skip_offset;
        case EntryAction::skip_offset:
            return same_scene && next.onboarding_settings_ready;
        case EntryAction::pack_hint:
        case EntryAction::song_hint:
        case EntryAction::main_hint:
        case EntryAction::notification_hint:
        case EntryAction::partner_hint:
            return same_scene && next.scan_complete && (!next.guide.node ||
                   (next.guide.node==initial.guide.node && next.guide.owner==initial.guide.owner &&
                    next.guide.callback==initial.guide.callback && next.guide.step==initial.guide.step+1));
#endif
        default: return false;
    }
}
