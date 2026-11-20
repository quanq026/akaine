#include "play_guide_pins.h"
#include "note_speed73.h"

namespace preplay73 {
struct View {
    Item speed;
    Address dialog=0, button=0, outer=0, inner=0, dim_listener=0;
    bool speed_known=false, advanced=false;
};

bool pins() {
    for (const auto& pin : CLI_PLAY_GUIDE_PINS)
        if (!in_ranges(module.executable,module.executable_count,core+pin.address,pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(core+pin.address),pin.bytes,pin.size))
            return false;
    return speed_pins();
}

bool only_input_layer(Reader& reader,Address scene,const UiTree& tree,Address own) {
    for (Size i=0;i<tree.count;++i) {
        const auto& item=tree.queue[i];
        const Address node=item.node;
        if (node!=own && reader.get<Address>(node)==core+filter_overlay_type &&
            (reader.get<uint8_t>(node+0x1c0) || reader.get<uint8_t>(node+0x1c1)) &&
            !inactive_song_overlay(reader.memory,scene,node,item.parent)) return false;
    }
    return !reader.fault;
}

View capture(Reader& reader,Address scene,const UiTree& tree,const CliSongState& song) {
    View view;
    if (!tree.valid || tree.loading || tree.guide || tree.character_modal || tree.settings_modal ||
        tree.modal || !song.valid || !song.selected || !song.song[0] ||
        song.pack_open || song.filter_open || !pins()) return view;
    if (tree.preplay_speed && !tree.preplay_dialog) {
        view.speed_known=note_speed(reader,scene,tree.preplay_speed,true,true,view.speed);
        if (view.speed_known) {
            const Address dim=reader.get<Address>(tree.preplay_speed+0x2d0);
            view.speed.can_set_speed=view.speed.can_set_speed && only_input_layer(reader,scene,tree,dim) &&
                reader.get<Address>(view.speed.continuation+0x18)==song.selected &&
                reader.get<unsigned>(view.speed.continuation+0x20)==song.selected_difficulty &&
                song.difficulty==song.selected_difficulty && !reader.fault;
        }
        return view;
    }
    const Address dialog=tree.preplay_dialog;
    if (!dialog || tree.preplay_speed || !song.selected || song.difficulty!=song.selected_difficulty) return view;
    const Address topbar=reader.get<Address>(scene+0x378);
    if (!reader.readable(topbar,0x1c2) || reader.get<Address>(topbar)!=core+preplay_topbar_type ||
        !filter_widgets::member(tree,topbar,scene,true) || !filter_widgets::member(tree,dialog,topbar,true) ||
        reader.get<uint8_t>(topbar+0x1c0)!=1 || !reader.readable(dialog,0x310) ||
        reader.get<uint8_t>(dialog+0x1c0)!=1 || reader.get<uint8_t>(dialog+0x302)) return view;
    const Address dim=reader.get<Address>(dialog+0x310);
    const Address listener=tutorial73::active_dim_listener(reader,dim,dialog);
    if (!listener || !filter_widgets::member(tree,dim,dialog,true) ||
        !only_input_layer(reader,scene,tree,dim)) return view;
    const Address root=reader.get<Address>(dialog+0x308);
    if (!filter_widgets::member(tree,root,dialog,true) || reader.get<uint8_t>(root+0x1c0)!=1) return view;
    Address button=0;
    for (Size i=0;i<tree.count;++i) {
        const auto& item=tree.queue[i];
        if (item.parent!=root || !ui_name(reader,item.node,"button2")) continue;
        if (button) return view;
        button=item.node;
    }
    if (!character_cli::button(reader,button) || !filter_widgets::member(tree,button,root,true) ||
        reader.get<Address>(button+0x3d0)) return view;
    const Address outer=reader.get<Address>(button+0x400);
    if (!reader.readable(outer,0x48) || reader.get<Address>(outer)!=core+preplay_skip_outer ||
        reader.get<Address>(outer+0x10)!=dialog) return view;
    const Address inner=reader.get<Address>(outer+0x40);
    if (!reader.readable(inner,0x28) || reader.get<Address>(inner)!=core+preplay_skip_inner ||
        reader.get<Address>(inner+8)!=scene || reader.get<Address>(inner+0x10)!=song.selected ||
        reader.get<unsigned>(inner+0x18)!=song.selected_difficulty ||
        reader.get<unsigned>(inner+0x1c) || reader.get<Address>(inner+0x20) ||
        !speed_pointer(preplay_skip_outer+0x30,preplay_skip_outer_invoke) ||
        !speed_pointer(preplay_skip_inner+0x30,preplay_skip_inner_invoke) ||
        !speed_pointer(song_scene_type+0x5f0,preplay_skip_play)) return view;
    unsigned difficulty=0;
    if (cli_song_in_list(reader,song,song.song,&difficulty)!=song.selected ||
        difficulty!=song.selected_difficulty || reader.fault) return view;
    view.dialog=dialog; view.button=button; view.outer=outer; view.inner=inner;
    view.dim_listener=listener; view.advanced=true;
    return view;
}

void write_advanced(Json& json,const View& view,const CliSongState& song) {
    json.add("{\"available\":"); json.add(view.advanced?"true":"false");
    json.add(",\"can_skip\":"); json.add(view.advanced?"true":"false");
    json.add(",\"reason\":"); if (view.advanced) json.add("null"); else json.string("not_present");
    json.add(",\"priority\":"); json.string(view.advanced?"single_modal":"unavailable");
    json.add(",\"song_id\":"); if (view.advanced) json.string(song.song); else json.add("null");
    json.add(",\"difficulty\":");
    if (view.advanced) {
        char text[12]; snprintf(text,sizeof(text),"%u",song.selected_difficulty); json.add(text);
    } else json.add("null");
    json.add("}");
}
}
