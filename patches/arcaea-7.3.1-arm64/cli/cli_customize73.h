#pragma once

bool download_pins();

namespace customize73 {
constexpr Address panel_type=0x1b225d0, download_overlay_type=0x1b44078;
enum Tab { Bgm, Title, Scenery };
constexpr const char* tabs[]={"bgm","title","scenery"};
struct Binding { Address table,invoke; };
constexpr Binding open_button{0x1c1fb30,0xe3a5d8}, close_button{0x1b73a18,0x18215c4};
constexpr Binding tab_buttons[]={{0x1be2090,0x19af410},{0x1b8ecc8,0x176b53c},{0x1c05148,0xc224c0}};
constexpr Binding item_buttons[]={{0x1bcbf38,0x9768bc},{0x1b4dc50,0x120c5d8},{0x1b6fc98,0xb0198c}};
constexpr Address bgm_available=0xfa9f44;

struct Action { Address node=0, closure=0, invoke=0; bool click=false; };
struct Item { Action action; char id[65]{}; bool unlocked=false, selected=false; };
struct View {
    Address scene=0, panel=0;
    int tab=-1;
    bool ready=false, downloading=false;
    Action open,close,download,switch_tab[3];
    Item items[48];
    Size count=0;
};

bool pins() {
    for (const auto& pin : CUSTOMIZE_PINS)
        if (!in_ranges(module.executable,module.executable_count,core+pin.address,pin.size) ||
            !same_bytes(reinterpret_cast<const unsigned char*>(core+pin.address),pin.bytes,pin.size)) return false;
    return true;
}

bool item_id(Reader& reader, Address object, char (&result)[65]) {
    if (!reader.readable(object,24)) return false;
    const auto tag=reader.get<uint8_t>(object);
    const Size size=tag&1 ? reader.get<Size>(object+8) : tag>>1;
    const Address bytes=tag&1 ? reader.get<Address>(object+16) : object+1;
    if (!size || size>=sizeof(result) || !reader.readable(bytes,size+1)) return false;
    const auto text=reinterpret_cast<const char*>(bytes);
    if (text[size] || !akaine_cli::identifier(text,size)) return false;
    memcpy(result,text,size+1);
    return true;
}

Action action(Reader& reader, Address node, Address owner, Binding expected, bool click) {
    const Address closure=reader.get<Address>(node+(click?0x400:0x3d0));
    if (!reader.readable(closure,16) || reader.get<Address>(closure)!=core+expected.table ||
        reader.get<Address>(closure+8)!=owner || !tutorial_pointer(expected.table+0x30,expected.invoke)) return {};
    return {node,closure,expected.invoke,click};
}

bool descendant(const UiTree& tree, Size index, Address ancestor) {
    Address parent=tree.queue[index].parent;
    while (index && parent) {
        const auto& entry=tree.queue[--index];
        if (entry.node!=parent) continue;
        if (parent==ancestor) return true;
        parent=entry.parent;
    }
    return false;
}

Action download(Reader& reader, Address scene, Address panel, const UiTree& tree) {
    const Address dialog=tree.modal;
    if (!dialog || !download_pins() || !reader.readable(dialog,0x328) ||
        reader.get<Address>(dialog)!=core+download_dialog_type ||
        !filter_widgets::member(tree,dialog,scene,true) || reader.get<uint8_t>(dialog+0x302)) return {};
    const Address root=reader.get<Address>(dialog+0x308), button=reader.get<Address>(dialog+0x320);
    if (!filter_widgets::member(tree,root,dialog,true) || !filter_widgets::member(tree,button,root,true) ||
        !ui_name(reader,button,"button1") || !filter_widgets::widget(reader,button,filter_button_type)) return {};
    const Address outer=reader.get<Address>(button+0x400);
    if (!reader.readable(outer,0x48) || reader.get<Address>(outer)!=core+download_outer_type ||
        reader.get<Address>(outer+0x10)!=dialog ||
        !tutorial_pointer(download_outer_type+0x30,download_outer_invoke)) return {};
    const Address inner=reader.get<Address>(outer+0x40);
    if (!reader.readable(inner,0x68) || reader.get<Address>(inner)!=core+download_inner_type ||
        reader.get<Address>(inner+0x30)!=scene ||
        !tutorial_pointer(download_inner_type+0x30,download_inner_invoke)) return {};
    const Address begin=reader.get<Address>(inner+0x18), end=reader.get<Address>(inner+0x20);
    char song[65]{};
    if (!reader.readable(begin,8) || end!=begin+8 ||
        !cli_song_id(reader,reader.get<Address>(begin),song) || strcmp(song,"hascome") ||
        !tutorial_pointer(filter_button_type+0x630,entry_pack_release)) return {};
    const Address continuation=reader.get<Address>(inner+0x60);
    if (!reader.readable(continuation,16) || reader.get<Address>(continuation)!=core+0x1b65c08 ||
        reader.get<Address>(continuation+8)!=panel || !tutorial_pointer(0x1b65c38,0xca60d4)) return {};
    return {button,outer,entry_pack_release,false};
}

View inspect(Reader& reader, Address scene, Address type, const UiTree& tree) {
    View result;
    if (type!=core+entry_menu_type) return result;
    result.scene=scene;
    result.panel=tree.customize_panel;
    result.downloading=result.panel && tree.download_overlay;
    if (result.panel && reader.readable(result.panel,0x2cc))
        result.tab=reader.get<int>(result.panel+0x2c8);
    if (!tree.valid || tree.loading || result.downloading || tree.settings_modal ||
        tree.character_modal || tree.guide || tree.onboarding_modal) return result;
    if (!pins()) return result;
    Address highlight=0;
    if (result.panel) {
        if (!reader.readable(result.panel,0x36b) || reader.get<uint8_t>(result.panel+0x36a)) return result;
        result.tab=reader.get<int>(result.panel+0x2c8);
        if (result.tab<0 || result.tab>2) return result;
        highlight=reader.get<Address>(result.panel+0x340);
        if (tree.modal) {
            if (result.tab!=Title) return result;
            result.download=download(reader,scene,result.panel,tree);
            if (!result.download.node) return result;
        }
    } else if (tree.has_modal || tree.modal) return result;
    for (Size i=0;i<tree.count;++i) {
        const auto& entry=tree.queue[i];
        const Address node=entry.node;
        if (reader.get<Address>(node)!=core+filter_button_type || !reader.readable(node,0x449)) continue;
        if (!result.panel) {
            if (entry.ancestors_enabled && reader.get<uint8_t>(node+0x1c1)==1) {
                const auto matched=action(reader,node,scene,open_button,true);
                if (matched.node && result.open.node) return {};
                if (matched.node) result.open=matched;
            }
            continue;
        }
        if (!descendant(tree,i,result.panel)) continue;
        if (entry.ancestors_enabled && reader.get<uint8_t>(node+0x1c1)==1) {
            const auto close=action(reader,node,result.panel,close_button,false);
            if (close.node) {
                if (result.close.node) return {};
                result.close=close;
            }
            for (int tab=0;tab<3;++tab) {
                const auto matched=action(reader,node,result.panel,tab_buttons[tab],false);
                if (!matched.node) continue;
                if (result.switch_tab[tab].node) return {};
                result.switch_tab[tab]=matched;
            }
        }
        const auto matched=action(reader,node,result.panel,item_buttons[result.tab],false);
        if (!matched.node) continue;
        if (result.count==48 || !reader.readable(matched.closure,result.tab==Scenery?0x28:0x40)) return {};
        auto& item=result.items[result.count];
        item.action=matched;
        if (result.tab==Scenery) {
            const Address model=reader.get<Address>(matched.closure+0x20);
            const auto unlocked=reader.get<uint8_t>(matched.closure+0x18);
            if (unlocked>1 || !item_id(reader,model+0x10,item.id)) return {};
            item.unlocked=unlocked==1;
            item.selected=highlight!=0 && highlight==reader.get<Address>(matched.closure+0x10);
        } else {
            const auto id=reader.get<unsigned>(matched.closure+0x10);
            const auto model=reader.get<Address>(matched.closure+(result.tab==Title?0x18:0x38));
            if (id>999 || !reader.readable(model,8)) return {};
            snprintf(item.id,sizeof(item.id),"%u",id);
            item.selected=reader.get<unsigned>(model+(result.tab==Title?4:0))==id;
            if (result.tab==Title) {
                const auto unlocked=reader.get<uint8_t>(matched.closure+0x14);
                if (unlocked>1) return {};
                item.unlocked=unlocked==1;
            } else {
                OfficialHost host;
                item.unlocked=host.call<bool>(bgm_available,model,id);
                if (host.fault) return {};
            }
        }
        for (Size j=0;j<result.count;++j)
            if (!strcmp(result.items[j].id,item.id)) return {};
        ++result.count;
    }
    result.ready=!reader.fault && (result.panel ? result.count>0 : bool(result.open.node));
    return result;
}

const Item* find(const View& view, const char* id) {
    for (Size i=0;i<view.count;++i) if (!strcmp(view.items[i].id,id)) return &view.items[i];
    return nullptr;
}

int tab_id(const char* id) {
    for (int i=0;i<3;++i) if (!strcmp(id,tabs[i])) return i;
    return -1;
}

bool confirmed(const View& view, const char* argument) {
    if (!strcmp(argument,"open")) return view.panel && view.ready;
    if (!strcmp(argument,"close")) return !view.panel && view.ready;
    if (!strcmp(argument,"confirm-download"))
        return view.tab==Title && !view.download.node && (view.ready || view.downloading);
    if (!strncmp(argument,"tab:",4)) return view.ready && view.tab==tab_id(argument+4);
    const auto item=!strncmp(argument,"select:",7)?find(view,argument+7):nullptr;
    return view.ready && item && item->selected;
}

const char* dispatch(const View& view, const char* argument) {
    Action command;
    if (view.downloading) return "CUSTOMIZE_DOWNLOADING";
    if (!view.ready) return "CUSTOMIZE_UNAVAILABLE";
    if (!strcmp(argument,"confirm-download")) {
        if (!view.download.node || !pins()) return "CUSTOMIZE_DOWNLOAD_UNAVAILABLE";
        if (!cli_dispatch_allowed()) return "EXPIRED";
        OfficialHost host;
        host.call<void>(entry_pack_release,view.download.node);
        return host.fault?"NATIVE_GUARD":nullptr;
    }
    if (view.download.node) return "CUSTOMIZE_DOWNLOAD_REQUIRED";
    if (!strcmp(argument,"open")) command=view.open;
    else if (!strcmp(argument,"close")) command=view.close;
    else if (!strncmp(argument,"tab:",4)) {
        const int target=tab_id(argument+4);
        if (target<0) return "INVALID_ARGUMENT";
        command=view.switch_tab[target];
    } else if (!strncmp(argument,"select:",7)) {
        const auto item=find(view,argument+7);
        if (!item) return "CUSTOMIZE_ITEM_NOT_FOUND";
        if (!item->unlocked) return "CUSTOMIZE_ITEM_LOCKED";
        command=item->action;
    } else return "INVALID_ARGUMENT";
    if (!command.node || !pins()) return "CUSTOMIZE_ACTION_UNAVAILABLE";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    Address node=command.node;
    int release=2;
    OfficialHost host;
    if (command.click) host.call<void>(command.invoke,command.closure,&node);
    else {
        if (!strncmp(argument,"select:",7)) {
            int began=0;
            host.call<void>(command.invoke,command.closure,&node,&began);
        }
        if (!host.fault) host.call<void>(command.invoke,command.closure,&node,&release);
    }
    return host.fault?"NATIVE_GUARD":nullptr;
}

const char* surface(const View& view,const char* underlying) {
    if (view.downloading) return "customize_downloading";
    if (view.download.node) return "customize_download_confirmation";
    if (view.panel) return "customize";
    return underlying;
}

void write(Json& json,const View& view) {
    json.add("{\"available\":"); json.add(view.ready?"true":"false");
    json.add(",\"open\":"); json.add(view.panel?"true":"false");
    json.add(",\"tab\":");
    if (view.tab>=0 && view.tab<3) json.string(tabs[view.tab]); else json.add("null");
    json.add(",\"download_required\":"); json.add(view.download.node?"true":"false");
    json.add(",\"phase\":");
    json.string(view.downloading?"downloading":view.download.node?"confirmation":
                !view.panel?"closed":view.ready?"ready":"blocked");
    json.add(",\"download_song\":");
    if (view.download.node) json.string("hascome"); else json.add("null");
    json.add(",\"items\":[");
    for (Size i=0;i<view.count;++i) {
        const auto& item=view.items[i];
        if (i) json.add(",");
        json.add("{\"id\":"); json.string(item.id);
        json.add(",\"unlocked\":"); json.add(item.unlocked?"true":"false");
        json.add(",\"selected\":"); json.add(item.selected?"true":"false");
        json.add("}");
    }
    json.add("]}");
}
}
