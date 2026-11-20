#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <jni.h>
#include <link.h>
#include <pthread.h>
#include <time.h>
#include <type_traits>
#include "bounds.h"
#include "cli_core.h"
#include "cli_files.h"
#include "maps_snapshot.h"
#include "cli73_pins.h"
#ifdef AKAINE_ENTRY_CLI
#include "cli_ui_core.h"
#endif

namespace {
using Address = uintptr_t;
using akaine_cli::Json;
using akaine_cli::Request;
using anomaly_monitor::Range;
constexpr char package[] = "akai.arc.qa73";
constexpr char root_path[] = "/data/user/0/akai.arc.qa73";
Address core;
Range loads[4];
size_t load_count;
int directory = -1;
char session[33];
akaine_cli::Ledger ledger;
pthread_t owner;
uint64_t polled, frame;
bool attempted, awaiting;
Request pending;
Address expected_scene, expected_pack;

uint64_t clock_value(clockid_t clock, uint64_t unit) {
    timespec ts{};
    if (clock_gettime(clock,&ts) || ts.tv_sec < 0) return 0;
    return uint64_t(ts.tv_sec)*unit + uint64_t(ts.tv_nsec)/(1000000000/unit);
}

bool static_readable(Address address, size_t bytes) {
    for (size_t i=0;i<load_count;++i)
        if (anomaly_monitor::contains(loads[i],address,bytes)) return true;
    return false;
}

bool checked_core() {
    for (const auto& pin : cli73_pins)
        if (!static_readable(core+pin.address,pin.length) ||
                memcmp(reinterpret_cast<const void*>(core+pin.address),pin.bytes,pin.length))
            return false;
    return true;
}

int find_core(dl_phdr_info* module, size_t, void*) {
    if (!module->dlpi_name) return 0;
    const char* tail = strrchr(module->dlpi_name,'/');
    if (strcmp(tail ? tail+1 : module->dlpi_name,"libcocos2dcpp.so")) return 0;
    bool exact_rx = false;
    for (size_t i=0;i<module->dlpi_phnum;++i) {
        const auto& ph = module->dlpi_phdr[i];
        if (ph.p_type != PT_LOAD || !(ph.p_flags & PF_R)) continue;
        if (load_count == 4 || ph.p_vaddr > UINTPTR_MAX-module->dlpi_addr
                || ph.p_memsz > UINTPTR_MAX-module->dlpi_addr-ph.p_vaddr)
            return 1;
        const Address start = module->dlpi_addr+ph.p_vaddr;
        loads[load_count++] = {start,start+ph.p_memsz};
        exact_rx |= ph.p_flags == (PF_R|PF_X) && !ph.p_vaddr && ph.p_filesz == rx_size
            && ph.p_memsz == rx_size;
    }
    if (exact_rx) core = module->dlpi_addr;
    return 1;
}

template<class T> bool read(const monitor_maps::Snapshot& memory, Address address, T& value) {
    if (!memory.contains(address,sizeof(T))) return false;
    memcpy(&value,reinterpret_cast<const void*>(address),sizeof(T));
    return true;
}

const char* class_name(Address vtable) {
    if (vtable < sizeof(Address) || !static_readable(vtable-sizeof(Address),sizeof(Address))) return nullptr;
    const Address info = *reinterpret_cast<const Address*>(vtable-sizeof(Address));
    if (info > UINTPTR_MAX-sizeof(Address) || !static_readable(info+sizeof(Address),sizeof(Address))) return nullptr;
    const auto* name = *reinterpret_cast<const char* const*>(info+sizeof(Address));
    return static_readable(reinterpret_cast<Address>(name),240) && memchr(name,0,240) ? name : nullptr;
}

#ifdef AKAINE_SONG_CLI
#include "cli_song_dispatch73.h"
#endif

struct UiTree {
    struct Item { Address node,parent; bool ancestors_enabled; };
    static constexpr size_t capacity = 1024;
    Item queue[capacity]{};
    size_t count = 0;
    Address modal = 0;
#ifdef AKAINE_CUSTOMIZE_CLI
    Address customize_panel=0, download_overlay=0;
#endif
    bool valid = false, loading = false, has_modal = false;
#ifdef AKAINE_NAVIGATION_CLI
    bool navigation_blocked = false;
#endif
#ifdef AKAINE_PREPLAY_CLI
    Address preplay_speed=0, preplay_dialog=0;
#endif
#ifdef AKAINE_ONBOARDING_CLI
    Address guide = 0, pack_hint_dim = 0, pack_hint_listener = 0;
    bool onboarding_modal = false;
#endif
#ifdef AKAINE_ACCOUNT_CLI
    bool settings_modal = false;
#ifdef AKAINE_SETTINGS_CLI
    Address settings_panel = 0;
#endif
#endif
#ifdef AKAINE_CHARACTER_CLI
    Address character_modal = 0;
#endif
#ifdef AKAINE_BUNDLE_CLI
    Address bundle_dim = 0;
    bool bundle_popup = false;
#endif
};

#ifdef AKAINE_FILTER_CLI
#include "cli_filter_dispatch73.h"
#endif
#ifdef AKAINE_ENTRY_CLI
#include "cli_entry_dispatch73.h"
#endif
#ifdef AKAINE_ACCOUNT_CLI
#include "cli_account_dispatch73.h"
#endif
#ifdef AKAINE_SYNC_CLI
#include "cli_cloudsync73.h"
#endif
#ifdef AKAINE_CHARACTER_CLI
#include "character_controls73.h"

int pending_character=-1;

#ifdef AKAINE_CUSTOMIZE_CLI
#include "customize_pins73.h"
#include "cli_customize73.h"
#endif

bool character_confirmed(const char* argument,const character_cli::View& view,int id,const EntryUi& ui) {
    if (!view.available) return false;
#ifdef AKAINE_PLAIN_GUIDES
    if (view.blocked && !strcmp(argument,"open"))
        return view.dialog && view.select_callback && ui.scan_complete && ui.modal &&
            ui.action==EntryAction::partner_hint && ui.guide.owner==view.dialog && ui.guide.ready();
#else
    (void)ui;
#endif
    if (view.blocked) return false;
    if (!strcmp(argument,"open")) return view.dialog && view.select_callback && !view.reason;
    if (!strcmp(argument,"close")) return !view.dialog && view.equipped_id==id;
    return view.dialog && view.preview_id==id && !view.reason;
}
#endif
#ifdef AKAINE_SETTINGS_CLI
#include "cli_settings_dispatch73.h"
#endif
#ifdef AKAINE_SKILL_CLI
#include "skill_controls73.h"
#endif
#ifdef AKAINE_NAVIGATION_CLI
bool navigation_tree_current(Address scene,const monitor_maps::Snapshot& memory,UiTree& tree);
#include "navigation_controls73.h"
#include "result_state73.h"
navigation_cli::View pending_navigation;
bool navigation_departed=false;
#endif
#ifdef AKAINE_REPLAY_CLI
#include "cli_replay_dispatch73.h"
#endif
#ifdef AKAINE_DOWNLOAD_CLI
#include "cli_download_dispatch73.h"
#endif
#ifdef AKAINE_PREPLAY_CLI
bool inactive_song_overlay(const monitor_maps::Snapshot& memory,Address scene,Address node,Address parent);
#include "cli_preplay73.h"
int target_note_speed=-1;
#endif
#ifdef AKAINE_BUNDLE_CLI
#include "bundle_controls.h"
#endif

bool pack_fields(const monitor_maps::Snapshot& memory, Address layer, int& ordinal) {
    Address begin,end,cap,widget,type;
    float limit;
    int highlight;
    if (!memory.contains(layer,0x438) ||
        !read(memory,layer+0x2e8,begin) || !read(memory,layer+0x2f0,end) || !read(memory,layer+0x2f8,cap) ||
        end < begin || end-begin != 24 || cap < end || cap-begin > 4096 || (cap-begin)%4 ||
        !memory.contains(begin,24) || !read(memory,layer+0x338,widget) || !memory.contains(widget,0x870) ||
        !read(memory,widget,type) || type != core+scroll_vtable || !read(memory,widget+0x758,limit) ||
        limit != 55.0f || !read(memory,layer+0x430,highlight) || highlight < -1 || highlight > 5)
        return false;
    float stops[6];
    memcpy(stops,reinterpret_cast<const void*>(begin),sizeof(stops));
    return akaine_cli::six_stops(stops,6) && read(memory,layer+0x434,ordinal) && ordinal >= 0 && ordinal <= 5;
}

struct State {
    Address scene = 0, pack = 0;
    const char* name = nullptr;
    const char* screen = "unavailable";
    int ordinal = -1;
    bool blocked = true, game = false;
#ifdef AKAINE_SONG_CLI
    CliSongState selection;
    char game_song[65]{};
    int game_difficulty = -1;
#endif
#ifdef AKAINE_FILTER_CLI
    filter_cli::View filter;
#endif
#ifdef AKAINE_ENTRY_CLI
    EntryUi entry;
#endif
#ifdef AKAINE_DOWNLOAD_CLI
    DownloadPrompt download;
#endif
#ifdef AKAINE_BUNDLE_CLI
    bundle_cli::View bundle;
#endif
#ifdef AKAINE_ACCOUNT_CLI
    account_controls::AccountView account;
#endif
#ifdef AKAINE_SYNC_CLI
    cloudsync_cli::View sync;
#endif
#ifdef AKAINE_CHARACTER_CLI
    character_cli::View character;
#endif
#ifdef AKAINE_SETTINGS_CLI
    settings_cli::View settings;
    settings_panel_cli::View settings_control;
#endif
#ifdef AKAINE_SKILL_CLI
    skill_cli::View skill;
#endif
#ifdef AKAINE_NAVIGATION_CLI
    navigation_cli::View navigation;
#ifdef AKAINE_CUSTOMIZE_CLI
    customize73::View customize;
#endif
    result_cli::View result;
#endif
#ifdef AKAINE_REPLAY_CLI
    int replay=-1;
#endif
#ifdef AKAINE_PREPLAY_CLI
    preplay73::View preplay;
#endif
};

#ifdef AKAINE_NAVIGATION_CLI
bool tutorial_game_layer(const monitor_maps::Snapshot& memory,Address scene,Address parent,Address type) {
    Address scene_type, ui, owner_type, chart;
    if (type!=core+tutorial_game_layer_type || !parent || !read(memory,scene,scene_type) || scene_type!=core+game_type ||
        !read(memory,scene+0x3c0,ui) || ui!=parent || !read(memory,parent,owner_type) || owner_type!=core+gameplay_ui_layer_type ||
        !read(memory,scene+0x318,chart)) return false;
    Reader reader{memory};
    char song[65]{};
    return cli_song_id(reader,chart,song) && !strcmp(song,"tutorial");
}

bool pause_owned_dim(const monitor_maps::Snapshot& memory,Address scene,const UiTree& tree,Size item_index) {
    Address type, ui, layer, delegate;
    uint8_t paused;
    if (!read(memory,scene,type) || type!=core+game_type ||
        !read(memory,scene+0x4b0,paused) || paused!=1 ||
        !read(memory,scene+0x3c0,ui) || !read(memory,ui,type) || type!=core+0x1b8f0f0 ||
        !read(memory,ui+0x300,layer) || !read(memory,layer,type) || type!=core+0x1b61350 ||
        !read(memory,layer+0x148,delegate) || delegate!=ui ||
        !read(memory,layer+0x2e0,delegate) || delegate!=scene+0x2f0) return false;
    Address parent=tree.queue[item_index].parent;
    while (item_index>0 && parent) {
        const auto& item=tree.queue[--item_index];
        if (item.node!=parent) continue;
        if (parent==layer) return true;
        parent=item.parent;
    }
    return false;
}
#endif
#if defined(AKAINE_NAVIGATION_CLI) || defined(AKAINE_PREPLAY_CLI)
bool inactive_song_overlay(const monitor_maps::Snapshot& memory,Address scene,Address node,Address parent) {
    Address scene_type, parent_type, listener;
    if (!parent || !read(memory,scene,scene_type) || scene_type!=core+song_scene_type ||
        !read(memory,parent,parent_type) || !read(memory,node+0x318,listener) || listener) return false;
    const char* owner=class_name(parent_type);
    return owner && (!strcmp(owner,"22MultiplayerVotingLayer") || !strcmp(owner,"11StickerTray"));
}
#endif

void walk_song_tree(const monitor_maps::Snapshot& memory,Address scene,Address own_filter,
                    UiTree& tree,Address& pack,int& ordinal) {
#ifdef AKAINE_PREPLAY_CLI
    Address preplay_scene_type=0;
    if (!read(memory,scene,preplay_scene_type)) return;
    const bool preplay_scene=preplay_scene_type==core+song_scene_type;
#endif
    tree.queue[0]={scene,0,true};
    tree.count=1;
    for (size_t i=0;i<tree.count;++i) {
        auto& item=tree.queue[i];
        const Address node=item.node, parent=item.parent;
        Address type,actual;
        if (!memory.contains(node,0x1c2) || !read(memory,node,type)) return;
        for (size_t j=0;j<i;++j) if (tree.queue[j].node==node) return;
        uint8_t visible;
        if (!read(memory,node+0x1c1,visible) || visible>1) return;
#ifdef AKAINE_PREPLAY_CLI
        const bool speed=preplay_scene && parent==scene && type==core+speed_layer_type;
        if (speed) {
            if (tree.preplay_speed || !read(memory,node+0x148,actual) || actual!=scene) return;
            tree.preplay_speed=node;
            tree.has_modal=true;
        }
#endif
#ifdef AKAINE_ONBOARDING_CLI
        const bool guide=parent==scene && (type==core+tutorial_base_type || type==core+tutorial_progression_type);
        if (guide) {
            if (tree.guide || !read(memory,node+0x148,actual) || actual!=scene) return;
            tree.guide=node;
            tree.has_modal=true;
        }
#endif
#ifdef AKAINE_FILTER_CLI
        if (node==own_filter && (type!=core+filter_overlay_type || parent!=scene)) return;
#ifdef AKAINE_NAVIGATION_CLI
        if (type==core+filter_overlay_type) {
            uint8_t running;
            if (!read(memory,node+0x1c0,running) || running>1) return;
            if ((visible || running) && !pause_owned_dim(memory,scene,tree,i) &&
                !inactive_song_overlay(memory,scene,node,parent)) tree.navigation_blocked=true;
        }
#endif
        // A running input-swallowing layer can block actions even when invisible.
        if (type==core+filter_overlay_type && node!=own_filter &&
                (parent==scene
#ifdef AKAINE_BUNDLE_CLI
                || tree.bundle_popup
#endif
                )) {
            uint8_t running;
            if (!read(memory,node+0x1c0,running) || running>1) return;
            if (visible || running) {
#ifdef AKAINE_BUNDLE_CLI
                // Only the title updater may claim a sole, visible direct dim.
                if (tree.bundle_popup && parent==scene && visible && running && !tree.bundle_dim)
                    tree.bundle_dim=node;
                else
#endif
#ifdef AKAINE_ONBOARDING_CLI
                if (!tree.pack_hint_dim && parent==scene &&
                    (tree.pack_hint_listener=tutorial73::pack_hint_interceptor(memory,scene,node))) {
                    tree.pack_hint_dim=node;
                    tree.has_modal=true;
                } else
#endif
                {
                    tree.has_modal=true;
                    return;
                }
            }
        }
#endif
#ifdef AKAINE_CUSTOMIZE_CLI
        if (visible && parent==scene && type==core+customize73::download_overlay_type)
            tree.download_overlay=node;
        if (visible && parent==scene && type==core+customize73::panel_type) {
            if (tree.customize_panel) return;
            tree.customize_panel=node;
            tree.has_modal=true;
        }
#endif
        if (!visible) {
#ifdef AKAINE_ENTRY_CLI
            uint8_t running;
            if (!read(memory,node+0x1c0,running) || running>1) return;
            const char* hidden=running?class_name(type):nullptr;
#ifdef AKAINE_CHARACTER_CLI
            Address side=0;
            const bool owned_side=tree.character_modal && parent==tree.character_modal &&
                (type==core+character_aside_type || type==core+character_bside_type) &&
                read(memory,parent+(type==core+character_aside_type?0x2d0:0x2d8),side) && node==side &&
                read(memory,node+0x148,actual) && actual==parent;
#endif
            if (running &&
#ifdef AKAINE_ONBOARDING_CLI
                    !guide &&
#endif
#ifdef AKAINE_CHARACTER_CLI
                    !owned_side &&
#endif
#ifdef AKAINE_PREPLAY_CLI
                    !speed &&
#endif
                    (!hidden || strstr(hidden,"Guide") || strstr(hidden,"Hint") ||
                    strstr(hidden,"Tutorial") || strstr(hidden,"Dialog") || strstr(hidden,"Overlay"))) {
                tree.has_modal=true;
                return;
            }
#endif
            item.ancestors_enabled=false;
            continue;
        }
        if (parent && (!read(memory,node+0x148,actual) || actual!=parent)) return;
        const char* name=class_name(type);
        if (!name) return;
#ifdef AKAINE_SETTINGS_CLI
        if (parent==scene && type==core+settings_scene_type) {
            if (tree.settings_panel) return;
            tree.settings_panel=node;
        }
#endif
        if (node!=scene && node!=own_filter &&
#ifdef AKAINE_NAVIGATION_CLI
                !tutorial_game_layer(memory,scene,parent,type) &&
#endif
                (type==core+settings_scene_type || type==core+speed_layer_type
                || strstr(name,"Dialog") || strstr(name,"Overlay") || strstr(name,"Popup")
                || strstr(name,"Loading") || strstr(name,"Transition") || strstr(name,"Tutorial")
                || strstr(name,"Guide") || strstr(name,"Hint"))) {
            tree.has_modal=true;
            tree.loading=strstr(name,"Loading") || strstr(name,"Transition");
#ifdef AKAINE_ONBOARDING_CLI
            Address scene_type;
            if (!read(memory,scene,scene_type)) return;
            if (guide) {}
#ifdef AKAINE_PREPLAY_CLI
            else if (speed) {}
            else if (preplay_scene && parent && parent!=scene && type==core+download_dialog_type) {
                Address topbar,bar_type;
                if (tree.preplay_dialog || !read(memory,scene+0x378,topbar) || topbar!=parent ||
                    !read(memory,topbar,bar_type) || bar_type!=core+preplay_topbar_type) return;
                tree.preplay_dialog=node;
            }
#endif
#ifdef AKAINE_CUSTOMIZE_CLI
            else if (parent==scene && scene_type==core+entry_menu_type && tree.customize_panel &&
                     type==core+download_dialog_type && !tree.modal) tree.modal=node;
#endif
            else if (parent==scene && scene_type==core+entry_menu_type &&
                     (type==core+settings_scene_type || type==core+onboarding_dialog_type)) {
                tree.onboarding_modal=true;
#ifdef AKAINE_ACCOUNT_CLI
                if (type==core+settings_scene_type) tree.settings_modal=true;
#endif
            }
#ifdef AKAINE_SETTINGS_CLI
            else if (parent==scene && scene_type==core+song_scene_type && type==core+settings_scene_type)
                tree.settings_modal=true;
#endif
#ifdef AKAINE_ACCOUNT_CLI
            else if (parent==scene && scene_type==core+entry_menu_type &&
                     type==core+account_side_dialog_type && !tree.modal) tree.modal=node;
#endif
#ifdef AKAINE_CHARACTER_CLI
            else if (parent==scene && (scene_type==core+entry_menu_type || scene_type==core+song_scene_type)
                     && type==core+character_dialog_type && !tree.character_modal) tree.character_modal=node;
            else if (parent==tree.character_modal &&
                     (type==core+character_aside_type || type==core+character_bside_type)) {}
#endif
            else
#endif
#ifdef AKAINE_DOWNLOAD_CLI
            if (parent==scene && type==core+download_dialog_type && !tree.loading && !tree.modal && !own_filter)
                tree.modal=node;
            else
#endif
            return;
        }
#ifdef AKAINE_FILTER_CLI
        if (type==core+filter_button_type || type==core+filter_field_type || type==core+filter_tray_type) {
            uint8_t enabled;
            if (!read(memory,node+0x312,enabled) || enabled>1) return;
            item.ancestors_enabled=item.ancestors_enabled && enabled==1;
        }
#endif
        if (type==core+pack_type) {
            uint8_t active;
            if (pack || !parent || !read(memory,node+0x1c0,active) || active!=1
                || !read(memory,scene+0x3a8,actual) || actual!=node
                || !pack_fields(memory,node,ordinal)) return;
            pack=node;
        }
        Address inner=0;
#if defined(AKAINE_CUSTOMIZE_CLI) || defined(AKAINE_SETTINGS_CLI)
        bool owns_inner=false;
#ifdef AKAINE_CUSTOMIZE_CLI
        if (parent && parent==tree.customize_panel && !strcmp(name,"N7cocos2d2ui8ListViewE")) {
            Address list;
            if (!read(memory,parent+0x348,list)) return;
            owns_inner=node==list;
        }
#endif
#ifdef AKAINE_SETTINGS_CLI
        if (tree.settings_panel && (type==core+settings_list_view_type || type==core+settings_page_view_type)) {
            Reader reader{memory};
            owns_inner=owns_inner || settings_panel_cli::reaches(reader,node,tree.settings_panel);
            if (reader.fault) return;
        }
#endif
        if (owns_inner) {
            Address owner,inner_type;
            if (!read(memory,node+0x748,inner) || !read(memory,inner,inner_type) ||
                !read(memory,inner+0x148,owner) || owner!=node) return;
            const auto* inner_class=class_name(inner_type);
            if (!inner_class || strcmp(inner_class,"N7cocos2d2ui6LayoutE")) return;
        }
#endif
        Address vector,begin=0,end=0,capacity;
        if (!read(memory,node+0x140,vector)) return;
        if (vector && (!memory.contains(vector,24) || !read(memory,vector,begin) || !read(memory,vector+8,end)
                || !read(memory,vector+16,capacity) || end<begin || capacity<end
                || (end-begin)%8 || (capacity-begin)%8 || capacity-begin>65536
                || (end-begin)/8>UiTree::capacity-tree.count
                || (end!=begin && !memory.contains(begin,end-begin)))) return;
        for (Address at=begin;at<end;at+=8) {
            Address child;
            if (!read(memory,at,child)) return;
#ifdef AKAINE_CHARACTER_CLI
            Address owner_type,child_type,child_owner;
            // A UserCell visual proxy references its owner's button. Ignore
            // this alias and inspect the button through its real parent.
            if (type==core+character_proxy_type && parent &&
                read(memory,parent,owner_type) && owner_type==core+character_usercell_type &&
                read(memory,child,child_type) && child_type==core+filter_button_type &&
                read(memory,child+0x148,child_owner) && child_owner==parent) continue;
#endif
            tree.queue[tree.count++]={child,node,item.ancestors_enabled};
            if (child==inner) inner=0;
        }
        if (inner) {
            if (tree.count==UiTree::capacity) return;
            tree.queue[tree.count++]={inner,node,item.ancestors_enabled};
        }
    }
    tree.valid=true;
}

#ifdef AKAINE_NAVIGATION_CLI
bool navigation_tree_current(Address scene,const monitor_maps::Snapshot& memory,UiTree& tree) {
    const auto director=reinterpret_cast<Address(*)()>(core+director_get)();
    Address type,current,pack=0;
    int ordinal=-1;
    if (!read(memory,director,type) || type!=core+director_type ||
        !read(memory,director+0x140,current) || current!=scene ||
        !read(memory,scene,type) || type!=core+game_type) return false;
    walk_song_tree(memory,scene,0,tree,pack,ordinal);
    return tree.valid;
}
#endif

State state(UiTree& tree) {
    State result;
    monitor_maps::Snapshot memory;
    const auto director = reinterpret_cast<Address(*)()>(core+director_get)();
    Address type;
    if (!memory.contains(director,0x148) || !read(memory,director,type) || type != core+director_type
        || !read(memory,director+0x140,result.scene) || !read(memory,result.scene,type))
        return result;
    result.name = class_name(type);
    if (!result.name) return result;
    result.game = type == core+game_type;
    if (result.game) result.screen = "gameplay";
    else if (type == core+song_scene_type) result.screen = "song_select";
    else if (!strcmp(result.name,"10StartScene")) result.screen = "title";
    else if (!strcmp(result.name,"13MainMenuScene")) result.screen = "main_menu";
    else if (!strcmp(result.name,"21NormalGameResultScene")) result.screen = "result";
    else result.screen = "other";
#ifdef AKAINE_REPLAY_CLI
    result.replay=replay_value(memory);
#endif
#ifdef AKAINE_SONG_CLI
    if (result.game) {
        Reader reader{memory};
        const auto song=reader.get<Address>(result.scene+0x318);
        const auto difficulty=reader.get<uint32_t>(result.scene+0x320);
        if (!reader.fault && difficulty<=4 && cli_song_id(reader,song,result.game_song))
            result.game_difficulty=int(difficulty);
    }
#endif
    const bool song_select=type==core+song_scene_type;
#ifndef AKAINE_ENTRY_CLI
    if (!song_select) return result;
#endif
    Address own_filter=0;
#ifdef AKAINE_SONG_CLI
    Reader reader{memory};
    if (song_select) result.selection=cli_song_capture(reader,result.scene);
#endif
#ifdef AKAINE_FILTER_CLI
    if (result.selection.valid && result.selection.filter_open &&
        !read(memory,result.selection.layer+0x438,own_filter)) return result;
#endif
    bool supported=song_select;
#ifdef AKAINE_ENTRY_CLI
    supported=supported || type==core+entry_title_type || type==core+entry_menu_type;
#endif
#ifdef AKAINE_NAVIGATION_CLI
    supported=supported || result.game || type==core+result_scene_type;
    tree.navigation_blocked=own_filter!=0;
#endif
#ifdef AKAINE_BUNDLE_CLI
    uint8_t updater_popup=0;
    tree.bundle_popup=type==core+entry_title_type &&
        read(memory,result.scene+0x3f0,updater_popup) && updater_popup==1;
#endif
    if (supported) walk_song_tree(memory,result.scene,own_filter,tree,result.pack,result.ordinal);
#ifdef AKAINE_CUSTOMIZE_CLI
    Reader customize_reader{memory};
    result.customize=customize73::inspect(customize_reader,result.scene,type,tree);
#endif
    result.blocked = !song_select || !tree.valid || tree.has_modal || own_filter;
#ifdef AKAINE_FILTER_CLI
    if (tree.valid && result.selection.valid && !reader.fault)
        result.filter=filter_cli::inspect(reader,result.scene,tree);
#endif
#ifdef AKAINE_ENTRY_CLI
    Reader ui_reader{memory};
    result.entry=capture_entry(ui_reader,result.scene,type,tree,result.pack,own_filter!=0);
#endif
#ifdef AKAINE_PREPLAY_CLI
    if (result.game && tree.valid && !tree.has_modal && !tree.navigation_blocked)
        result.entry.scan_complete=true;
    if (song_select && (tree.preplay_speed || tree.preplay_dialog)) {
        Reader preplay_reader{memory};
        result.preplay=preplay73::capture(preplay_reader,result.scene,tree,result.selection);
        result.entry.scan_complete=result.preplay.advanced || result.preplay.speed_known;
        if (result.preplay.speed_known) {
            const auto& speed=result.preplay.speed;
            auto& guide=result.entry.guide;
            guide.node=speed.node; guide.id=speed.id; guide.active=speed.active;
            guide.visible=speed.visible; guide.opacity=speed.opacity; guide.step=unsigned(speed.step_index);
            guide.owned_button=speed.callback_owned; guide.owned_speed=speed.owner_validated;
            guide.can_set_speed=speed.can_set_speed;
            guide.registered=speed.listener_registered; guide.paused=speed.listener_paused;
            guide.enabled=speed.listener_enabled; guide.swallow=speed.listener_swallow;
            result.entry.note_speed_modal_ready=speed.can_set_speed;
        }
    }
#endif
#ifdef AKAINE_ACCOUNT_CLI
    if (type==core+entry_menu_type && tree.valid && !tree.loading && !tree.guide && !tree.settings_modal
#ifdef AKAINE_CHARACTER_CLI
        && !tree.character_modal
#endif
        ) {
        Reader account_reader{memory};
        result.account=account_controls::inspect(account_reader,result.scene,tree);
#ifdef AKAINE_SYNC_CLI
        Reader sync_reader{memory};
        result.sync=cloudsync_cli::inspect(sync_reader,result.scene,tree);
#endif
    }
#endif
#ifdef AKAINE_CHARACTER_CLI
    bool character_guide=false;
#ifdef AKAINE_PLAIN_GUIDES
    character_guide=tree.guide && tree.character_modal && result.entry.scan_complete &&
        result.entry.guide.action==EntryAction::partner_hint && result.entry.guide.owner==tree.character_modal;
#endif
    if ((type==core+entry_menu_type || song_select) && !own_filter &&
        (!tree.guide || character_guide) && !tree.settings_modal && !tree.onboarding_modal && !tree.modal
#ifdef AKAINE_PREPLAY_CLI
        && !tree.preplay_speed && !tree.preplay_dialog
#endif
        ) {
        Reader character_reader{memory};
        result.character=character_cli::inspect(character_reader,result.scene,tree);
        if (character_guide) {
            result.character.blocked=true;
            result.character.reason="input_blocked";
        }
    }
#endif
#ifdef AKAINE_SETTINGS_CLI
    {
        Reader preferences{memory};
        result.settings=settings_cli::inspect(preferences,result.scene,tree);
        if ((type==core+entry_menu_type || song_select) && !own_filter && !tree.guide &&
            !tree.character_modal && !tree.modal
#ifdef AKAINE_PREPLAY_CLI
            && !tree.preplay_speed && !tree.preplay_dialog
#endif
            ) {
            Reader settings_reader{memory};
            result.settings_control=settings_panel_cli::inspect(settings_reader,result.scene,tree);
        }
    }
#endif
#ifdef AKAINE_SKILL_CLI
    {
        Reader skill_reader{memory};
        result.skill=skill_cli::inspect(skill_reader,result.scene,result.name,result.character);
    }
#endif
#ifdef AKAINE_NAVIGATION_CLI
    {
        Reader navigation_reader{memory};
        result.navigation=navigation_cli::inspect(navigation_reader,result.scene,result.name,tree);
        Reader result_reader{memory};
        result.result=result_cli::inspect(result_reader,result.scene,result.name);
    }
#endif
#ifdef AKAINE_DOWNLOAD_CLI
    if (song_select && tree.valid && tree.modal && result.selection.valid
#ifdef AKAINE_ONBOARDING_CLI
        && !tree.guide
#endif
#ifdef AKAINE_CHARACTER_CLI
        && !tree.character_modal
#endif
#ifdef AKAINE_PREPLAY_CLI
        && !tree.preplay_speed && !tree.preplay_dialog
#endif
        ) {
        Reader download_reader{memory};
        result.download=download_prompt(download_reader,result.scene,tree,result.selection);
    }
#endif
#ifdef AKAINE_BUNDLE_CLI
    if (type==core+entry_title_type && !tree.has_modal) {
        Reader bundle_reader{memory};
        result.bundle=bundle_cli::inspect(bundle_reader,result.scene,tree);
    }
#endif
    return result;
}

State state() {
    UiTree tree;
    return state(tree);
}

void number(Json& json,uint64_t value) {
    char text[32];
    snprintf(text,sizeof(text),"%llu",static_cast<unsigned long long>(value));
    json.add(text);
}

void respond(const Request& request,const State& view,const char* error) {
    Json json;
    json.add("{\"protocol\":1,\"environment\":\"staging\",\"request_id\":"); json.string(request.id);
    json.add(",\"session\":"); json.string(session);
    json.add(",\"command\":"); json.string(request.command);
    json.add(",\"ok\":"); json.add(error ? "false" : "true");
    json.add(",\"state\":{\"screen\":"); json.string(view.screen);
    json.add(",\"frame\":"); number(json,frame);
    json.add(",\"scene\":"); if (view.name) json.string(view.name); else json.add("null");
    json.add(",\"gameplay\":"); json.add(view.game ? "true" : "false");
#ifdef AKAINE_REPLAY_CLI
    json.add(",\"anomaly_replay\":"); json.add(view.replay<0?"null":view.replay?"true":"false");
#endif
    json.add(",\"category\":");
    if (!view.blocked && view.ordinal >= 4) {
        json.add("{\"section\":"); number(json,view.ordinal == 5 ? 8 : 7);
        json.add(",\"name\":"); json.string(view.ordinal == 5 ? "mod" : "variety");
        json.add(",\"selected_ordinal\":"); number(json,view.ordinal); json.add("}");
    } else json.add("null");
#ifdef AKAINE_SONG_CLI
    json.add(",\"song_id\":"); if (view.game_song[0]) json.string(view.game_song); else json.add("null");
    json.add(",\"difficulty\":"); if (view.game_difficulty>=0) number(json,view.game_difficulty); else json.add("null");
    json.add(",\"song_selection\":");
    const auto& selection=view.selection;
    if (!selection.valid) json.add("null");
    else {
        json.add("{\"song_id\":"); if (selection.song[0]) json.string(selection.song); else json.add("null");
        json.add(",\"pack_id\":"); json.string(selection.pack_id);
        json.add(",\"difficulty\":"); number(json,selection.difficulty);
        json.add(",\"selected_difficulty\":"); number(json,selection.selected_difficulty);
        json.add(",\"sort\":"); number(json,selection.sort);
        json.add(",\"group\":"); number(json,selection.group);
        json.add(",\"reverse\":"); json.add(selection.reverse?"true":"false");
        json.add(",\"pack_open\":"); json.add(selection.pack_open?"true":"false");
        json.add(",\"filter_open\":"); json.add(selection.filter_open?"true":"false");
        json.add(",\"native_list_count\":"); number(json,(selection.pairs_end-selection.pairs_begin)/16);
        json.add("}");
    }
#endif
#ifdef AKAINE_FILTER_CLI
    json.add(",\"filter\":"); filter_cli::write_state(json,view.filter);
#endif
#ifdef AKAINE_ENTRY_CLI
    json.add(",\"ui\":"); write_entry(json,view.entry);
#endif
#ifdef AKAINE_PREPLAY_CLI
    json.add(",\"advanced_guide\":"); preplay73::write_advanced(json,view.preplay,view.selection);
#endif
#ifdef AKAINE_BUNDLE_CLI
    json.add(",\"bundle\":"); bundle_cli::write_state(json,view.bundle);
#endif
#ifdef AKAINE_ACCOUNT_CLI
    json.add(",\"account\":"); account_controls::write_state(json,view.account);
#endif
#ifdef AKAINE_SYNC_CLI
    json.add(",\"sync\":"); cloudsync_cli::write_state(json,view.sync);
#endif
#ifdef AKAINE_CHARACTER_CLI
    json.add(",\"character\":"); character_cli::write_state(json,view.character);
#endif
#ifdef AKAINE_SETTINGS_CLI
    json.add(",\"settings\":"); settings_cli::write_state(json,view.settings);
    json.add(",\"settings_control\":"); settings_panel_cli::write_state(json,view.settings_control);
#endif
#ifdef AKAINE_SKILL_CLI
    json.add(",\"skill\":"); skill_cli::write_state(json,view.skill);
#endif
#ifdef AKAINE_NAVIGATION_CLI
    json.add(",\"navigation\":"); navigation_cli::write_state(json,view.navigation);
    json.add(",\"result\":"); result_cli::write_state(json,view.result);
#endif
#ifdef AKAINE_DOWNLOAD_CLI
    json.add(",\"chart_download\":");
    const bool accepted=!error && !strcmp(request.command,"play_download");
    if ((!accepted && !view.download.button) || !view.selection.valid) json.add("null");
    else {
        json.add("{\"song_id\":"); json.string(view.selection.song);
        json.add(",\"difficulty\":"); number(json,view.selection.selected_difficulty);
        json.add(",\"can_confirm\":"); json.add(view.download.button?"true":"false");
        json.add(",\"prompt_dismissed\":"); json.add(accepted?"true":"false");
        json.add("}");
    }
#endif
#ifdef AKAINE_CUSTOMIZE_CLI
    json.add(",\"surface\":");
    json.string(customize73::surface(view.customize,view.screen));
    if (view.customize.panel || view.customize.downloading || !strcmp(request.command,"customize")) {
        json.add(",\"customize\":");
        customize73::write(json,view.customize);
    }
#endif
    json.add("},\"error\":");
    if (error) {
        json.add("{\"code\":"); json.string(error);
        json.add(",\"message\":\"Native request was rejected or could not be confirmed.\"}");
    } else json.add("null");
    json.add("}\n");
    akaine_cli::atomic_json(directory,".response.tmp","response.json",json);
}

bool initialize(uint64_t now) {
    if (!now || getuid()<10000 || getuid()>=20000) return false;
    char process[64]{};
    int cmd = open("/proc/self/cmdline",O_RDONLY|O_NONBLOCK|O_CLOEXEC);
    if (cmd < 0) return false;
    const ssize_t length = ::read(cmd,process,sizeof(process)-1);
    close(cmd);
    if (length <= 0 || strcmp(process,package)) return false;
    dl_iterate_phdr(find_core,nullptr);
    if (!core || !checked_core()) return false;
#ifdef AKAINE_SONG_CLI
    module={core,loads,1};
    if (loads[0].begin!=core || loads[0].end-core!=rx_size || !cli_song_pins() || !play_pins())
        return false;
#endif
#ifdef AKAINE_FILTER_CLI
    if (!filter_cli::pins()) return false;
#endif
#ifdef AKAINE_ENTRY_CLI
    if (!entry_pins()) return false;
#endif
#ifdef AKAINE_DOWNLOAD_CLI
    if (!download_pins()) return false;
#endif
#ifdef AKAINE_PREPLAY_CLI
    if (!preplay73::pins()) return false;
#endif
#ifdef AKAINE_BUNDLE_CLI
    if (!bundle_cli::pins() || !bundle_cli::error_pins()) return false;
#endif
#ifdef AKAINE_ACCOUNT_CLI
    if (!account_controls::pins()) return false;
#endif
#ifdef AKAINE_SYNC_CLI
    if (!cloudsync_cli::pins()) return false;
#endif
#ifdef AKAINE_CHARACTER_CLI
    if (!character_cli::pins()) return false;
#endif
#ifdef AKAINE_SETTINGS_CLI
    if (!settings_panel_cli::pins()) return false;
#endif
#ifdef AKAINE_SKILL_CLI
    if (!skill_cli::pins()) return false;
#endif
#ifdef AKAINE_NAVIGATION_CLI
    if (!navigation_cli::pins() || !result_cli::pins()) return false;
#endif
#ifdef AKAINE_REPLAY_CLI
    if (!replay_cli_pins()) return false;
#endif
    const int root = open(root_path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    int files = -1;
    if (akaine_cli::owned_directory(root,getuid()) && (!mkdirat(root,"files",0700) || errno==EEXIST))
        files = openat(root,"files",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if (root >= 0) close(root);
    if (akaine_cli::owned_files_parent(files,getuid(),getgid())
            && (!mkdirat(files,"akaine-cli-v1",0700) || errno==EEXIST))
        directory = openat(files,"akaine-cli-v1",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if (files >= 0) close(files);
    if (!akaine_cli::owned_directory(directory,getuid(),true)) return false;
    snprintf(session,sizeof(session),"%016llx%016llx",static_cast<unsigned long long>(getpid()),
             static_cast<unsigned long long>(now));
    Json json;
    json.add("{\"protocol\":1,\"environment\":\"staging\",\"package\":\"akai.arc.qa73\","
             "\"application_version\":\"7.3.1\",\"pid\":"); number(json,getpid());
    json.add(",\"session\":"); json.string(session);
    json.add(",\"commands\":[\"status\",\"category\"");
#ifdef AKAINE_SONG_CLI
    json.add(",\"song_select\",\"pack_select\",\"pack_close\",\"difficulty\",\"sort\",\"group\",\"reverse\",\"play\"");
#endif
#ifdef AKAINE_FILTER_CLI
    json.add(",\"filter\"");
#endif
#ifdef AKAINE_ENTRY_CLI
    json.add(",\"ui\"");
#endif
#ifdef AKAINE_DOWNLOAD_CLI
    json.add(",\"play_download\"");
#endif
#ifdef AKAINE_PREPLAY_CLI
    json.add(",\"play_guide\",\"play_set_speed\"");
#endif
#ifdef AKAINE_BUNDLE_CLI
    json.add(",\"bundle\"");
#endif
#ifdef AKAINE_ACCOUNT_CLI
    json.add(",\"account\"");
#endif
#ifdef AKAINE_SYNC_CLI
    json.add(",\"sync\"");
#endif
#ifdef AKAINE_CHARACTER_CLI
    json.add(",\"character\"");
#endif
#ifdef AKAINE_SETTINGS_CLI
    json.add(",\"settings\"");
#ifdef AKAINE_CUSTOMIZE_CLI
    json.add(",\"customize\"");
#endif
#endif
#ifdef AKAINE_SKILL_CLI
    json.add(",\"skill\"");
#endif
#ifdef AKAINE_NAVIGATION_CLI
    json.add(",\"navigation\",\"gameplay\"");
#endif
#ifdef AKAINE_REPLAY_CLI
    json.add(",\"replay\"");
#endif
    json.add("]}\n");
    return akaine_cli::atomic_json(directory,".bridge.tmp","bridge.json",json);
}
}

extern "C" JNIEXPORT void JNICALL
Java_org_cocos2dx_lib_AkaineCli73_pollNative(JNIEnv*,jclass) {
    const uint64_t now = clock_value(CLOCK_MONOTONIC,1000000000);
    if (!attempted) {
        attempted = true;
        owner = pthread_self();
        if (!initialize(now)) {
            if (directory>=0) close(directory);
            directory = -1;
        }
    }
    if (directory<0 || !pthread_equal(owner,pthread_self())) return;
    ++frame;
    if (!now || (polled && now>=polled && now-polled<100000000)) return;
    polled = now;
    if (awaiting) {
        const State view = state();
        const uint64_t wall = clock_value(CLOCK_REALTIME,1000);
#ifdef AKAINE_PREPLAY_CLI
        if (!strcmp(pending.command,"play_guide") || !strcmp(pending.command,"play_set_speed")) {
            const bool speed=!strcmp(pending.command,"play_set_speed");
            const auto& song=view.selection;
            const bool preference=!speed || (view.settings.available && view.settings.highspeed_int==target_note_speed);
            const char* error=!wall || wall>=pending.expires?"ACTION_TIMEOUT":nullptr;
            bool confirmed=false;
            if (!error && view.game) {
                const bool same=view.game_difficulty==target_difficulty && !strcmp(view.game_song,pending.argument);
                if (!same) error="PLAY_TARGET_CHANGED";
                else confirmed=preference && (!speed || view.entry.scan_complete);
            } else if (!error && view.scene==expected_scene && song.valid &&
                       song.selected_difficulty==unsigned(target_difficulty) &&
                       !strcmp(song.song,pending.argument)) {
                if (!speed && view.preplay.speed_known) error="NOTE_SPEED_SETUP_REQUIRED";
                else if (speed && preference && view.preplay.advanced) error="ADVANCED_GUIDE_REQUIRED";
#ifdef AKAINE_DOWNLOAD_CLI
                else if (preference && !view.preplay.speed_known && !view.preplay.advanced && view.download.button)
                    error="DOWNLOAD_CONFIRMATION_REQUIRED";
#endif
                else confirmed=preference && !view.blocked && !view.entry.modal && view.entry.scan_complete &&
                    !view.preplay.advanced && !view.preplay.speed_known &&
                    !song.pack_open && !song.filter_open && song.difficulty==song.selected_difficulty;
            }
            if (error || confirmed) {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
#ifdef AKAINE_REPLAY_CLI
        if (!strcmp(pending.command,"replay")) {
            const char* error=!wall || wall>=pending.expires?"ACTION_TIMEOUT":
                              view.scene!=expected_scene?"SCENE_CHANGED":nullptr;
            if (error || view.replay==pending.argument[0]-'0') {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
#ifdef AKAINE_NAVIGATION_CLI
        if (!strcmp(pending.command,"navigation") || !strcmp(pending.command,"gameplay")) {
            using namespace navigation_cli;
            const auto action=action_id(pending.argument);
            const auto& now=view.navigation;
            const bool changed=view.scene!=expected_scene;
            navigation_departed|=changed || (view.name && strstr(view.name,"Transition"));
            const bool local=action==Pause || action==Resume;
            const char* error=!wall || wall>=pending.expires?"ACTION_TIMEOUT":
                              local && changed?"SCENE_CHANGED":nullptr;
            bool confirmed=false;
            if (!error && local)
                confirmed=now.kind==Gameplay && now.available && now.paused_known && now.paused==(action==Pause);
            else if (!error && navigation_departed) {
                const bool selection=now.kind==SongSelect && view.selection.valid &&
                    !view.selection.pack_open && !view.selection.filter_open && !view.blocked;
                if (action==Retry) confirmed=view.game && view.game_difficulty==pending_navigation.difficulty &&
                    !strcmp(view.game_song,pending_navigation.song);
                else if (action==Quit || action==Continue) confirmed=selection ||
                    (action==Quit && !strcmp(pending_navigation.song,"tutorial") &&
                     (view.entry.identity.scene_type==core+entry_menu_type
#ifdef AKAINE_ONBOARDING_CLI
                      || (view.entry.identity.scene_type==core+song_scene_type && view.entry.scan_complete &&
                          view.entry.guide.action==EntryAction::song_hint)
#endif
                     ));
                else if (action==Back) confirmed=pending_navigation.kind==SongSelect ?
                    view.entry.identity.scene_type==core+entry_menu_type : selection;
            }
            if (error || confirmed) {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
#ifdef AKAINE_SKILL_CLI
        if (!strcmp(pending.command,"skill")) {
            const char* error=!wall || wall>=pending.expires?"ACTION_TIMEOUT":
                              view.scene!=expected_scene?"SCENE_CHANGED":nullptr;
            if (error || view.skill.native_skill_sealed==pending.argument[5]-'0') {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
#ifdef AKAINE_SETTINGS_CLI
#ifdef AKAINE_CUSTOMIZE_CLI
        if (!strcmp(pending.command,"customize")) {
            const char* error=!wall || wall>=pending.expires?"ACTION_TIMEOUT":
                              view.scene!=expected_scene?"SCENE_CHANGED":
                              view.customize.download.node && !strncmp(pending.argument,"select:",7) ?
                                  "CUSTOMIZE_DOWNLOAD_REQUIRED":nullptr;
            if (error || customize73::confirmed(view.customize,pending.argument)) {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
        if (!strcmp(pending.command,"settings")) {
            const char* error=!wall || wall>=pending.expires?"ACTION_TIMEOUT":
                              view.scene!=expected_scene?"SCENE_CHANGED":nullptr;
#ifdef AKAINE_ONBOARDING_CLI
            const bool guide_after_close=!strcmp(pending.argument,"close") &&
                view.entry.scan_complete && view.entry.guide.action==EntryAction::main_hint &&
                view.entry.guide.active && !view.settings.panel_open;
#else
            const bool guide_after_close=false;
#endif
            if (error || guide_after_close ||
                settings_confirmed(pending.argument,view.settings_control,view.settings,pending_setting)) {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
#ifdef AKAINE_CHARACTER_CLI
        if (!strcmp(pending.command,"character")) {
            const char* error=!wall || wall>=pending.expires?"ACTION_TIMEOUT":
                              view.scene!=expected_scene?"SCENE_CHANGED":nullptr;
            if (error || character_confirmed(pending.argument,view.character,pending_character,view.entry)) {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
#ifdef AKAINE_SYNC_CLI
        if (!strcmp(pending.command,"sync")) {
            const auto& account=view.account;
            const bool ready=!account.blocked && account.signed_in_known && account.signed_in &&
                (!strcmp(account.kind,"logged_in_menu") || !strcmp(account.kind,"main_menu"));
            monitor_maps::Snapshot memory;
            Reader reader{memory};
            cloudsync_cli::poll(reader,view.scene,pending,session,wall,ready);
            const State fresh=state();
            const char* error=!wall || wall>=pending.expires?"ACTION_TIMEOUT":
                view.scene!=expected_scene?"SCENE_CHANGED":
                !strcmp(fresh.sync.phase,"failed")?"SYNC_FAILED":nullptr;
            if (error || !strcmp(fresh.sync.phase,"success")) {
                awaiting=false;
                respond(pending,fresh,error);
            }
            return;
        }
#endif
#ifdef AKAINE_ACCOUNT_CLI
        if (!strcmp(pending.command,"account")) {
            const bool logout=!strcmp(pending.argument,"logout");
            const char* error=!wall || wall>=pending.expires?"ACTION_TIMEOUT":
                !logout && view.scene!=expected_scene?"SCENE_CHANGED":nullptr;
            const bool confirmed=!error && account_confirmed(pending.argument,view.account);
            if (!error && !confirmed && !strcmp(pending.argument,"submit") &&
                pending_login_submit.failed(view.account)) error="ACCOUNT_LOGIN_FAILED";
            if (error || confirmed) {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
#ifdef AKAINE_BUNDLE_CLI
        if (!strcmp(pending.command,"bundle")) {
            const bool dismiss=!strcmp(pending.argument,"dismiss-error");
            const auto& bundle=view.bundle;
            const char* error=!wall || wall>=pending.expires?"ACTION_TIMEOUT":
                view.scene!=expected_scene?"SCENE_CHANGED":nullptr;
            const bool failed=!strcmp(bundle.phase,"failed");
            if (!error && !dismiss && failed) error="BUNDLE_DOWNLOAD_FAILED";
            const bool confirmed=bundle.available && bundle.has_pending_bytes &&
                (dismiss ? !bundle.error_popup && !failed :
                 !bundle.reason && (!strcmp(bundle.phase,"downloading") || !strcmp(bundle.phase,"ready")));
            if (error || confirmed) {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
#ifdef AKAINE_DOWNLOAD_CLI
        if (!strcmp(pending.command,"play_download")) {
            const char* error=!wall || wall>=pending.expires?"ACTION_TIMEOUT":
                view.scene!=expected_scene?"SCENE_CHANGED":nullptr;
            const auto& selection=view.selection;
            const bool confirmed=!error && !view.blocked && !view.game && !view.download.button &&
                selection.valid && !selection.pack_open && !selection.filter_open &&
                !strcmp(selection.song,pending.argument) &&
                selection.selected_difficulty==unsigned(target_difficulty) &&
                selection.difficulty==selection.selected_difficulty;
            if (error || confirmed) {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
#ifdef AKAINE_ENTRY_CLI
        if (!strcmp(pending.command,"ui")) {
            const char* error=!wall || wall>=pending.expires?"ACTION_TIMEOUT":nullptr;
            if (error || entry_confirmed(pending_entry,view.entry)) {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
#ifdef AKAINE_FILTER_CLI
        if (!strcmp(pending.command,"filter")) {
            const char* error=!wall || wall>=pending.expires ? "ACTION_TIMEOUT" :
                view.scene!=expected_scene ? "SCENE_CHANGED" : nullptr;
            if (error || filter_confirmed(pending.argument,view.filter)) {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
#ifdef AKAINE_SONG_CLI
        if (is_song_command(pending.command)) {
            const bool playing=!strcmp(pending.command,"play");
            const char* error=!wall || wall>=pending.expires ? "ACTION_TIMEOUT" : nullptr;
            bool confirmed=false;
#ifdef AKAINE_PREPLAY_CLI
            if (!error && playing && view.scene==expected_scene &&
                view.selection.selected_difficulty==unsigned(target_difficulty) &&
                !strcmp(view.selection.song,pending.argument)) {
                if (view.preplay.speed_known) error="NOTE_SPEED_SETUP_REQUIRED";
                else if (view.preplay.advanced) error="ADVANCED_GUIDE_REQUIRED";
            }
#endif
#ifdef AKAINE_DOWNLOAD_CLI
            if (!error && playing && view.scene==expected_scene && view.download.button &&
                view.selection.selected_difficulty==unsigned(target_difficulty) &&
                !strcmp(view.selection.song,pending.argument)) error="DOWNLOAD_CONFIRMATION_REQUIRED";
#endif
            if (!error && playing && view.game) {
                confirmed=view.game_difficulty==target_difficulty && !strcmp(view.game_song,pending.argument);
                if (!confirmed) error="PLAY_TARGET_CHANGED";
            } else if (!error && !playing) {
                if (view.scene!=expected_scene) error="SCENE_CHANGED";
                else if (!view.blocked
#ifdef AKAINE_ONBOARDING_CLI
                         || (!strcmp(pending.command,"pack_select") && view.entry.guide.node &&
                             view.entry.guide.active && !view.entry.guide.closing)
#endif
                         ) confirmed=song_confirmed(pending,view.selection);
            }
            if (error || confirmed) {
                awaiting=false;
                respond(pending,view,error);
            }
            return;
        }
#endif
        const char* error = !wall || wall>=pending.expires ? "ACTION_TIMEOUT" :
            view.scene!=expected_scene || view.pack!=expected_pack ? "SCENE_CHANGED" :
            view.blocked ? "INPUT_BLOCKED" : nullptr;
        if (error || akaine_cli::section_ordinal(pending.section,view.ordinal)) {
            awaiting = false;
            respond(pending,view,error);
        }
        return;
    }
    char bytes[akaine_cli::REQUEST_LIMIT+1]{};
    Request request;
    if (!akaine_cli::parse(bytes,akaine_cli::consume(directory,bytes),&request)) return;
    const char* error = akaine_cli::request_guard(request,session,clock_value(CLOCK_REALTIME,1000));
    if (!error) error = ledger.remember(request.id);
    const State view = state();
#ifdef AKAINE_PREPLAY_CLI
    if (!error && (!strcmp(request.command,"play_guide") || !strcmp(request.command,"play_set_speed"))) {
        const bool speed=!strcmp(request.command,"play_set_speed");
        const State fresh=state();
        const auto& previous=view.preplay;
        const auto& next=fresh.preplay;
        const auto& song=fresh.selection;
        const bool same=checked_core() && view.scene==fresh.scene && song.valid && song.selected &&
            song.selected==view.selection.selected && song.selected_difficulty==view.selection.selected_difficulty &&
            song.difficulty==song.selected_difficulty && !strcmp(song.song,request.argument);
        const bool ready=speed ?
            previous.speed.can_set_speed && next.speed.can_set_speed &&
                next.speed.set_button==previous.speed.set_button && next.speed.listener==previous.speed.listener &&
                next.speed.callback==previous.speed.callback && next.speed.continuation==previous.speed.continuation &&
                next.speed.step_index==previous.speed.step_index :
            previous.advanced && next.advanced && next.dialog==previous.dialog &&
                next.button==previous.button && next.outer==previous.outer && next.inner==previous.inner &&
                next.dim_listener==previous.dim_listener;
        if (!same || !ready || !preplay73::pins()) {
            respond(request,fresh,speed?"NOTE_SPEED_UNAVAILABLE":"ADVANCED_GUIDE_UNAVAILABLE");
            return;
        }
        pending=request;
        expected_scene=fresh.scene;
        target_difficulty=int(song.selected_difficulty);
        target_note_speed=speed?int(next.speed.step_index):-1;
        awaiting=true;
        if (cli_dispatch_allowed()) {
            OfficialHost call;
            call.call<void>(entry_pack_release,speed?next.speed.set_button:next.button);
            if (call.fault) error="NATIVE_GUARD";
        } else error="EXPIRED";
        if (error) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
#ifdef AKAINE_REPLAY_CLI
    if (!error && !strcmp(request.command,"replay")) {
        const int expected=request.argument[0]-'0';
        if (!checked_core() || view.replay<0) {
            respond(request,view,"NATIVE_GUARD");
            return;
        }
        if (view.replay==expected) {
            respond(request,view,nullptr);
            return;
        }
        const State fresh=state();
        const auto& identity=fresh.entry.identity;
        if (fresh.scene!=view.scene || fresh.replay!=view.replay || !identity.available || fresh.entry.modal ||
            (identity.scene_type!=core+entry_menu_type && identity.scene_type!=core+song_scene_type)) {
            respond(request,fresh,"UI_BLOCKED");
            return;
        }
        monitor_maps::Snapshot memory;
        pending=request;
        expected_scene=fresh.scene;
        awaiting=true;
        error=set_replay(memory,expected);
        if (error) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
#ifdef AKAINE_NAVIGATION_CLI
    if (!error && (!strcmp(request.command,"navigation") || !strcmp(request.command,"gameplay"))) {
        using namespace navigation_cli;
        if (!strcmp(request.argument,"status")) {
            respond(request,view,nullptr);
            return;
        }
        const auto action=action_id(request.argument);
        if (action==ActionCount || !checked_core() || !view.navigation.available ||
            !view.navigation.actions[action].node) {
            respond(request,view,"ACTION_UNAVAILABLE");
            return;
        }
        UiTree tree;
        const State fresh=state(tree);
        if (!same(view.navigation,fresh.navigation)) {
            respond(request,fresh,"STALE_STATE");
            return;
        }
        monitor_maps::Snapshot memory;
        Reader reader{memory};
        pending=request;
        expected_scene=fresh.scene;
        navigation_departed=false;
        pending_navigation=fresh.navigation;
        awaiting=true;
        error=act(reader,fresh.scene,fresh.name,tree,fresh.navigation,request.argument);
        if (error) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
#ifdef AKAINE_SKILL_CLI
    if (!error && !strcmp(request.command,"skill")) {
        if (!strcmp(request.argument,"status")) {
            respond(request,view,nullptr);
            return;
        }
        const bool sealed=request.argument[5]=='1';
        const State fresh=state();
        const auto& current=fresh.skill;
        if (!checked_core() || !current.available || current.scene!=view.skill.scene ||
            current.dialog!=view.skill.dialog || current.equipped.object!=view.skill.equipped.object ||
            current.seal_callback!=view.skill.seal_callback) {
            respond(request,fresh,"SKILL_UNAVAILABLE");
            return;
        }
        if (current.native_skill_sealed==int(sealed)) {
            respond(request,fresh,nullptr);
            return;
        }
        monitor_maps::Snapshot memory;
        Reader reader{memory};
        pending=request;
        expected_scene=fresh.scene;
        awaiting=true;
        error=skill_cli::seal(reader,current,sealed);
        if (error) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
#ifdef AKAINE_SETTINGS_CLI
#ifdef AKAINE_CUSTOMIZE_CLI
    if (!error && !strcmp(request.command,"customize")) {
        if (!strcmp(request.argument,"status") || !strcmp(request.argument,"list")) {
            respond(request,view,nullptr);
            return;
        }
        const State fresh=state();
        if (!checked_core() || !fresh.customize.scene || fresh.scene!=view.scene ||
            fresh.customize.panel!=view.customize.panel || fresh.customize.tab!=view.customize.tab) {
            respond(request,fresh,"CUSTOMIZE_UNAVAILABLE");
            return;
        }
        if (!strcmp(request.argument,"confirm-download") && !fresh.customize.download.node) {
            respond(request,fresh,"CUSTOMIZE_DOWNLOAD_UNAVAILABLE");
            return;
        }
        if (customize73::confirmed(fresh.customize,request.argument)) {
            respond(request,fresh,nullptr);
            return;
        }
        expected_scene=fresh.scene;
        pending=request;
        awaiting=true;
        error=customize73::dispatch(fresh.customize,request.argument);
        if (error) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
    if (!error && !strcmp(request.command,"settings")) {
        const char* action=request.argument;
        if (!strcmp(action,"status")) {
            respond(request,view,nullptr);
            return;
        }
        const State fresh=state();
        const auto& before=view.settings_control;
        const auto& panel=fresh.settings_control;
        if (!checked_core() || !panel.available || panel.blocked || panel.reason ||
            !before.scene || panel.scene!=before.scene || panel.panel!=before.panel ||
            panel.topbar!=before.topbar || panel.open_callback!=before.open_callback ||
            panel.close_callback!=before.close_callback) {
            respond(request,fresh,"SETTINGS_UNAVAILABLE");
            return;
        }
        const char* argument=strchr(action,':');
        pending_setting=argument?int(std::strtol(argument+1,nullptr,10)):0;
        if (settings_confirmed(action,panel,fresh.settings,pending_setting)) {
            respond(request,fresh,nullptr);
            return;
        }
        monitor_maps::Snapshot memory;
        Reader reader{memory};
        pending=request;
        expected_scene=fresh.scene;
        awaiting=true;
        error=settings_action(action,reader,panel,fresh.settings,pending_setting);
        if (error) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
#ifdef AKAINE_CHARACTER_CLI
    if (!error && !strcmp(request.command,"character")) {
        const char* action=request.argument;
        if (!strcmp(action,"status") || !strcmp(action,"list")) {
            respond(request,view,nullptr);
            return;
        }
        const State fresh=state();
        const auto& before=view.character;
        const auto& character=fresh.character;
        if (!checked_core() || !character.available || character.blocked ||
            !before.scene || character.scene!=before.scene || character.model!=before.model ||
            character.dialog!=before.dialog || character.preview_id!=before.preview_id ||
            character.aside!=before.aside || character.list!=before.list ||
            character.open_callback!=before.open_callback || character.close_callback!=before.close_callback ||
            character.select_callback!=before.select_callback) {
            respond(request,fresh,"CHARACTER_UNAVAILABLE");
            return;
        }
        const bool open=!strcmp(action,"open"), close=!strcmp(action,"close");
        pending_character=close ? (character.dialog ? character.preview_id : character.equipped_id)
                                : open ? -1 : int(std::strtoul(action,nullptr,10));
        if (character_confirmed(action,character,pending_character,fresh.entry)) {
            respond(request,fresh,nullptr);
            return;
        }
        monitor_maps::Snapshot memory;
        Reader reader{memory};
        pending=request;
        expected_scene=fresh.scene;
        awaiting=true;
        if (open) error=character_cli::open(reader,character);
        else if (close) error=character_cli::close(reader,character);
        else error=character_cli::select(reader,character,pending_character);
        if (error) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
#ifdef AKAINE_SYNC_CLI
    if (!error && !strcmp(request.command,"sync")) {
        if (!strcmp(request.argument,"status")) {
            respond(request,view,nullptr);
            return;
        }
        UiTree tree;
        const State fresh=state(tree);
        if (!checked_core() || !view.sync.can_download || !fresh.sync.can_download ||
            fresh.scene!=view.scene || fresh.account.modal!=view.account.modal ||
            fresh.account.root!=view.account.root) {
            respond(request,fresh,"SYNC_UNAVAILABLE");
            return;
        }
        monitor_maps::Snapshot memory;
        Reader reader{memory};
        pending=request;
        expected_scene=fresh.scene;
        awaiting=true;
        if (cloudsync_cli::download(reader,fresh.scene,tree,request,session,clock_value(CLOCK_REALTIME,1000))
                !=cloudsync_cli::Result::ok) {
            awaiting=false;
            respond(request,state(),"SYNC_UNAVAILABLE");
        }
        return;
    }
#endif
#ifdef AKAINE_ACCOUNT_CLI
    if (!error && !strcmp(request.command,"account")) {
        const char* action=request.argument;
        if (!strcmp(action,"status")) {
            respond(request,view,nullptr);
            return;
        }
        UiTree tree;
        const State fresh=state(tree);
        const auto& before=view.account;
        const auto& after=fresh.account;
        if (!checked_core() || !tree.valid || tree.loading || tree.guide || tree.settings_modal ||
            !before.scene || before.scene!=after.scene || before.modal!=after.modal ||
            before.root!=after.root || before.button!=after.button || before.closure!=after.closure ||
            strcmp(before.kind,after.kind)) {
            respond(request,fresh,"ACCOUNT_UNAVAILABLE");
            return;
        }
        const bool fill=!strcmp(action,"fill");
        if (fill && !after.can_fill) {
            respond(request,fresh,"ACCOUNT_UNAVAILABLE");
            return;
        }
        monitor_maps::Snapshot memory;
        Reader reader{memory};
        pending=request;
        expected_scene=fresh.scene;
        awaiting=true;
        error=account_action(request,reader,fresh.scene,tree);
        if (error || fill) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
#ifdef AKAINE_BUNDLE_CLI
    if (!error && !strcmp(request.command,"bundle")) {
        if (!strcmp(request.argument,"status")) {
            respond(request,view,nullptr);
            return;
        }
        const bool dismiss=!strcmp(request.argument,"dismiss-error");
        if (!checked_core() || !view.bundle.button || (dismiss ? !view.bundle.error_popup : !view.bundle.can_confirm)) {
            respond(request,view,dismiss?"BUNDLE_ERROR_UNAVAILABLE":"BUNDLE_PROMPT_UNAVAILABLE");
            return;
        }
        UiTree tree;
        const State fresh=state(tree);
        if (fresh.scene!=view.scene || !tree.valid || tree.has_modal) {
            respond(request,fresh,"SCENE_CHANGED");
            return;
        }
        monitor_maps::Snapshot memory;
        Reader reader{memory};
        pending=request;
        expected_scene=fresh.scene;
        awaiting=true;
        error=dismiss ? bundle_cli::dismiss_error(reader,fresh.scene,tree,view.bundle)
                      : bundle_cli::confirm(reader,fresh.scene,tree,view.bundle);
        if (error) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
#ifdef AKAINE_DOWNLOAD_CLI
    if (!error && !strcmp(request.command,"play_download")) {
        if (!checked_core() || !view.download.button ||
                strcmp(request.argument,view.selection.song)) {
            respond(request,view,"DOWNLOAD_PROMPT_UNAVAILABLE");
            return;
        }
        const State fresh=state();
        if (!fresh.download.button || fresh.download.button!=view.download.button ||
            fresh.download.dialog!=view.download.dialog || fresh.scene!=view.scene ||
            strcmp(request.argument,fresh.selection.song) ||
            fresh.selection.selected_difficulty!=view.selection.selected_difficulty) {
            respond(request,fresh,"SELECTION_CHANGED");
            return;
        }
        pending=request;
        expected_scene=fresh.scene;
        target_difficulty=int(fresh.selection.selected_difficulty);
        awaiting=true;
        error=activate_download(fresh.download);
        if (error) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
#ifdef AKAINE_ENTRY_CLI
    if (!error && !strcmp(request.command,"ui")) {
        if (!strcmp(request.argument,"list")) {
            respond(request,view,nullptr);
            return;
        }
        if (!akaine_cli::token_context(request.argument,view.entry.context)) {
            respond(request,view,"STALE_UI");
            return;
        }
        if (!entry_token(request.argument,view.entry) || !checked_core()) {
            respond(request,view,"ACTION_UNAVAILABLE");
            return;
        }
        const State fresh=state();
        if (!entry_token(request.argument,fresh.entry) ||
                !akaine_cli::same_ui(view.entry.identity,fresh.entry.identity)) {
            respond(request,fresh,"STALE_UI");
            return;
        }
        pending=request;
        pending_entry=fresh.entry;
        awaiting=true;
        error=activate_entry(fresh.entry);
        if (error) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
#ifdef AKAINE_FILTER_CLI
    if (!error && !strcmp(request.command,"filter")) {
        if (!strcmp(request.argument,"status")) {
            respond(request,view,nullptr);
            return;
        }
        if (!checked_core() || !view.filter.valid || !view.filter.ready) {
            respond(request,view,"WRONG_SCENE");
            return;
        }
        if (filter_confirmed(request.argument,view.filter) && strcmp(request.argument,"reset")) {
            respond(request,view,nullptr);
            return;
        }
        pending=request;
        expected_scene=view.scene;
        awaiting=true;
        monitor_maps::Snapshot memory;
        UiTree tree;
        Address pack=0;
        int ordinal=-1;
        walk_song_tree(memory,view.scene,view.filter.overlay,tree,pack,ordinal);
        Reader reader{memory};
        error=filter_action(reader,view.scene,tree,request.argument);
        if (error) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
#ifdef AKAINE_SONG_CLI
    if (!error && is_song_command(request.command)) {
        if (!checked_core() || view.blocked || !view.selection.valid) {
            respond(request,view,"WRONG_SCENE");
            return;
        }
        const auto* name=request.command;
        const auto& selection=view.selection;
        if (song_confirmed(request,selection)) {
            respond(request,view,nullptr);
            return;
        }
        pending=request;
        expected_scene=view.scene;
        awaiting=true;
        monitor_maps::Snapshot memory;
        Reader reader{memory};
        if (!strcmp(name,"play")) error=play(reader,cli_song_capture(reader,view.scene),request.argument);
        else if (!strcmp(name,"song_select")) error=cli_song_select(reader,view.scene,request.argument);
        else if (!strcmp(name,"pack_select")) error=cli_pack_select(reader,view.scene,request.argument);
        else if (!strcmp(name,"pack_close")) error=cli_pack_close(reader,view.scene);
        else if (!strcmp(name,"difficulty")) error=cli_song_difficulty(reader,view.scene,request.argument[0]-'0');
        else {
            const unsigned expected=request.argument[0]-'0';
            error=cli_song_sort_group(reader,view.scene,!strcmp(name,"sort")?expected:selection.sort,
                !strcmp(name,"group")?expected:selection.group,!strcmp(name,"reverse")?expected:selection.reverse);
        }
        if (error) {
            awaiting=false;
            respond(request,state(),error);
        }
        return;
    }
#endif
    if (!error && strcmp(request.command,"status")) {
        if (strcmp(request.command,"category")) error = "UNSUPPORTED_COMMAND";
        else if (!checked_core() || view.blocked || !view.pack) error = "WRONG_SCENE";
        else if (!akaine_cli::section_ordinal(request.section,view.ordinal)) {
            error = akaine_cli::request_guard(request,session,clock_value(CLOCK_REALTIME,1000));
            if (!error) {
                pending = request;
                expected_scene = view.scene;
                expected_pack = view.pack;
                awaiting = true;
                reinterpret_cast<void(*)(Address,uint32_t)>(core+category_select)(view.pack,request.section);
                return;
            }
        }
    }
    respond(request,view,error);
}
