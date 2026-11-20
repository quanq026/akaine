namespace tutorial73 {
struct Guide {
    const char* id = "unknown_progression_guide";
    EntryAction action = EntryAction::none;
    Address node = 0, button = 0, callback = 0, completion = 0, listener = 0, owner = 0;
    unsigned step = 0, remaining = 0, opacity = 0;
    bool active = false, visible = false, closing = false, registered = false;
    bool paused = false, enabled = false, swallow = false, owned_button = false;
    bool can_set_speed = false, owned_speed = false, terminal_callback = false;
    bool blocks() const { return registered && !paused && enabled && swallow; }
    bool ready() const { return active && !closing && blocks() && owned_button && button; }
};

bool pins() {
    for (const auto& pin : TUTORIAL_PINS)
        if (!in_ranges(module.executable,module.executable_count,core+pin.address,pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(core+pin.address),pin.bytes,pin.size))
            return false;
    return true;
}

bool flag(Reader& reader, Address at, bool& output) {
    const auto value=reader.get<uint8_t>(at);
    output=value==1;
    return !reader.fault && value<=1;
}

#ifdef AKAINE_PLAIN_GUIDES
#include "plain_guides73.h"

bool plain_pins() {
    for (const auto& pin : PLAIN_GUIDE_PINS)
        if (!in_ranges(module.executable,module.executable_count,core+pin.address,pin.size) ||
            !same_bytes(reinterpret_cast<const unsigned char*>(core+pin.address),pin.bytes,pin.size)) return false;
    return true;
}

bool pages_match(Reader& reader,Address begin,const char* const* pages,Size count) {
    for (Size i=0;i<count;++i) {
        const Address entry=begin+i*24;
        const auto tag=reader.get<uint8_t>(entry);
        const Size length=tag&1 ? reader.get<Size>(entry+8) : tag>>1;
        const Address text=tag&1 ? reader.get<Address>(entry+16) : entry+1;
        if (length!=strlen(pages[i]) || !reader.readable(text,length+1) ||
            memcmp(reinterpret_cast<const void*>(text),pages[i],length+1)) return false;
    }
    return !reader.fault;
}

bool plain_owner(Reader& reader,Address scene,const UiTree& tree,Address begin,Size count,Guide& guide) {
    const auto scene_type=reader.get<Address>(scene);
    if (!plain_pins() || guide.completion ||
        (scene_type!=core+song_scene_type && scene_type!=core+entry_menu_type)) return false;
    if (tree.character_modal && count==sizeof(PARTNER_GUIDE_PAGES)/sizeof(*PARTNER_GUIDE_PAGES) &&
        pages_match(reader,begin,PARTNER_GUIDE_PAGES,count)) {
        const Address dialog=tree.character_modal;
        const Address aside=reader.get<Address>(dialog+0x2d0), bside=reader.get<Address>(dialog+0x2d8);
        if (!reader.readable(aside,0x610) || !reader.readable(bside,0x4f0) ||
            reader.get<Address>(dialog+0x148)!=scene || reader.get<uint8_t>(dialog+0x1c0)!=1 ||
            reader.get<Address>(aside)!=core+character_aside_type || reader.get<Address>(bside)!=core+character_bside_type ||
            reader.get<Address>(aside+0x148)!=dialog || reader.get<Address>(bside+0x148)!=dialog ||
            reader.get<Address>(aside+0x5e8)!=dialog || reader.get<Address>(bside+0x4e8)!=dialog ||
            reader.get<uint8_t>(aside+0x1c0)!=1 || reader.get<uint8_t>(aside+0x1c1)!=1 || reader.fault) return false;
        guide.owner=dialog; guide.id="partner_selection_hint"; guide.action=EntryAction::partner_hint;
    } else if (scene_type==core+song_scene_type && !tree.character_modal && count==sizeof(CATEGORY_GUIDE_PAGES)/sizeof(*CATEGORY_GUIDE_PAGES) &&
               pages_match(reader,begin,CATEGORY_GUIDE_PAGES,count)) {
        const Address pack=reader.get<Address>(scene+0x3a8);
        if (!reader.readable(pack,0x1c2) || reader.get<Address>(pack)!=core+pack_type ||
            reader.get<Address>(pack+0x148)!=scene || reader.get<uint8_t>(pack+0x1c0)!=1 || reader.fault) return false;
        guide.owner=pack; guide.id="pack_selection_hint"; guide.action=EntryAction::pack_hint;
    }
    return !reader.fault;
}
#endif

Address active_dim_listener(Reader& reader,Address dim,Address owner) {
    if (reader.get<Address>(dim)!=core+filter_overlay_type || reader.get<Address>(dim+0x148)!=owner) return 0;
    const auto listener=reader.get<Address>(dim+0x318);
    if (!reader.readable(listener,0x159) || reader.get<Address>(listener)!=core+tutorial_listener_type ||
        reader.get<Address>(listener+0x68)!=dim || reader.get<uint8_t>(listener+0x60)!=1 ||
        reader.get<uint8_t>(listener+0x70)!=0 || reader.get<uint8_t>(listener+0x71)!=1 ||
        reader.get<uint8_t>(listener+0x158)!=1) return 0;
    const auto began=reader.get<Address>(listener+0xa0);
    if (!reader.readable(began,0x20) || reader.get<Address>(began)!=core+tutorial_began_type ||
        reader.get<Address>(began+8)!=0x548 || reader.get<Address>(began+0x10)!=1 ||
        reader.get<Address>(began+0x18)!=dim || !tutorial_pointer(tutorial_began_type+0x30,tutorial_began_invoke) ||
        !tutorial_pointer(filter_overlay_type+0x548,tutorial_dim_began)) return 0;
    return reader.fault?0:listener;
}

Address pack_hint_interceptor(const monitor_maps::Snapshot& memory,Address scene,Address dim) {
    Reader reader{memory};
    if (reader.get<Address>(scene)!=core+song_scene_type || reader.get<uint8_t>(scene+0x358)!=1 ||
        reader.get<Address>(scene+0x388)!=dim) return 0;
    return active_dim_listener(reader,dim,scene);
}

bool capture(Reader& reader, Address scene, Address type, const UiTree& tree, Guide& result) {
    const Address guide=tree.guide;
    if (!guide) return true;
    result.node=guide;
    if (!reader.readable(guide,0x388) || !pins()
        || !flag(reader,guide+0x1c0,result.active) || !flag(reader,guide+0x1c1,result.visible)
        || !flag(reader,guide+0x358,result.closing)) return false;
    result.opacity=reader.get<uint8_t>(guide+0x1d0);
    const auto index=reader.get<uint32_t>(guide+0x300);
    const auto begin=reader.get<Address>(guide+0x360);
    const auto end=reader.get<Address>(guide+0x368);
    const auto cap=reader.get<Address>(guide+0x370);
    if (end<begin || cap<end || (end-begin)%24 || (cap-begin)%24 || cap-begin>128*24
        || !begin || (end!=begin && !reader.readable(begin,end-begin)) || index>(end-begin)/24) return false;
    result.step=index;
    result.remaining=unsigned((end-begin)/24)-index;
    result.completion=reader.get<Address>(guide+0x330);
    const Address guide_type=reader.get<Address>(guide);
    if ((guide_type==core+tutorial_progression_type || guide_type==core+tutorial_base_type) && result.completion) {
        if (!reader.readable(result.completion,0x10)) return false;
        const auto callback_type=reader.get<Address>(result.completion);
        const auto callback_owner=reader.get<Address>(result.completion+8);
        for (const auto& role : TUTORIAL_OWNERS) {
            const Address expected_layer=role.action==EntryAction::song_hint?tutorial_base_type:tutorial_progression_type;
            if (guide_type==core+expected_layer && type==core+role.scene && callback_type==core+role.table && callback_owner==scene
                && tutorial_pointer(role.table+0x30,role.invoke)) {
                result.id=role.id;
                result.action=role.action;
                result.owner=scene;
            }
        }
        if (guide_type==core+tutorial_base_type && result.action==EntryAction::none) return false;
    }
#ifdef AKAINE_PLAIN_GUIDES
    else if (guide_type!=core+tutorial_base_type ||
             !plain_owner(reader,scene,tree,begin,(end-begin)/24,result)) return false;
#else
    else return !reader.fault;
#endif
    if (tree.pack_hint_dim && (result.action!=EntryAction::pack_hint || result.owner!=scene)) return false;
    const auto dim=reader.get<Address>(guide+0x340);
    if (!reader.readable(dim,0x323) || reader.get<Address>(dim)!=core+filter_overlay_type
        || reader.get<Address>(dim+0x148)!=guide) return false;
    result.listener=reader.get<Address>(dim+0x318);
    if (!reader.readable(result.listener,0x159) || reader.get<Address>(result.listener)!=core+tutorial_listener_type
        || reader.get<Address>(result.listener+0x68)!=dim
        || !flag(reader,result.listener+0x60,result.registered) || !flag(reader,result.listener+0x70,result.paused)
        || !flag(reader,result.listener+0x71,result.enabled) || !flag(reader,result.listener+0x158,result.swallow))
        return false;
    const auto began=reader.get<Address>(result.listener+0xa0);
    if (!reader.readable(began,0x20) || reader.get<Address>(began)!=core+tutorial_began_type
        || reader.get<Address>(began+8)!=0x548 || reader.get<Address>(began+0x10)!=1
        || reader.get<Address>(began+0x18)!=dim || !tutorial_pointer(tutorial_began_type+0x30,tutorial_began_invoke)
        || !tutorial_pointer(filter_overlay_type+0x548,tutorial_dim_began)) return false;

    const auto button=reader.get<Address>(guide+0x380);
    if (!reader.readable(button,0x449) || reader.get<Address>(button)!=core+filter_button_type
        || reader.get<Address>(button+0x148)!=guide) return false;
    result.callback=reader.get<Address>(button+0x3d0);
    if (!reader.readable(result.callback,0x10) || reader.get<Address>(result.callback)!=core+tutorial_next_type
        || reader.get<Address>(result.callback+8)!=guide || !tutorial_pointer(tutorial_next_type+0x30,tutorial_next_invoke)
        || !tutorial_pointer(filter_button_type+0x630,entry_pack_release)) return false;
    result.owned_button=true;
    if (!result.visible || !result.remaining) return !reader.fault;
    const bool enabled=reader.get<uint8_t>(button+0x1c0)==1
        && reader.get<uint8_t>(button+0x1c1)==1 && reader.get<uint8_t>(button+0x312)==1
        && reader.get<uint8_t>(button+0x314)==1 && !reader.get<uint8_t>(button+0x448)
        && !reader.get<Address>(button+0x398) && !reader.get<Address>(button+0x3a0)
        && !reader.get<Address>(button+0x3a8) && !reader.get<Address>(button+0x400);
    for (Size i=0;i<tree.count;++i) {
        const auto& item=tree.queue[i];
        if (item.node!=button || item.parent!=guide) continue;
        if (enabled && item.ancestors_enabled) result.button=button;
        else if (result.remaining==1 && result.action!=EntryAction::none && result.opacity==255) {
            result.button=button;
            result.terminal_callback=true;
        }
    }
    return !reader.fault;
}

void write(Json& json, const Guide& guide, bool complete) {
    const auto boolean=[&](const char* key,bool value) {
        json.add(","); json.string(key); json.add(value?":true":":false");
    };
    json.add(",\"overlays\":[");
    if (guide.node) {
        json.add("{\"kind\":\"tutorial\",\"id\":"); json.string(guide.id);
        boolean("active",guide.active);
        boolean("visible",guide.visible && guide.opacity>0);
        boolean("blocks_input",guide.blocks());
        boolean("advance_ready",guide.ready());
        boolean("can_advance",complete && guide.ready() && guide.action!=EntryAction::none);
        boolean("can_set_speed",complete && guide.can_set_speed);
        boolean("owner_validated",guide.action!=EntryAction::none || guide.owned_speed);
        boolean("callback_owned",guide.owned_button);
        boolean("listener_registered",guide.registered);
        boolean("listener_paused",guide.paused);
        boolean("listener_enabled",guide.enabled);
        boolean("listener_swallow",guide.swallow);
        char values[96];
        snprintf(values,sizeof(values),",\"opacity\":%u,\"step_index\":%u,\"pending_steps\":%u}",
                 guide.opacity,guide.step,guide.remaining);
        json.add(values);
    }
    json.add("],\"overlay_coverage\":[\"progression_guide\",\"note_speed_setup\","
             "\"category_tutorial\",\"partner_tutorial\"]");
    boolean("overlay_scan_complete",complete);
}
}
