bool static_pointer(Address address,Address* out) {
    if (!static_readable(address,sizeof(*out))) return false;
    memcpy(out,reinterpret_cast<const void*>(address),sizeof(*out));
    return true;
}
bool ui_name(Reader& h,Address node,const char* expected) {
    if (!h.readable(node+0x160,24)) return false;
    const auto tag=h.get<uint8_t>(node+0x160);
    const Size size=tag&1 ? h.get<Size>(node+0x168) : tag>>1;
    const Address bytes=tag&1 ? h.get<Address>(node+0x170) : node+0x161;
    return size==strlen(expected) && h.readable(bytes,size+1) &&
        !memcmp(reinterpret_cast<const void*>(bytes),expected,size+1);
}
bool ui_class(Address vt,char (&out)[240]) {
    const char* name=class_name(vt);
    if (!name) return false;
    memcpy(out,name,strlen(name)+1);
    return true;
}

#include "filter_widgets73.h"

namespace filter_widgets {
bool set_field(Address node,const char* text,Size size) {
    alignas(8) uint8_t input[24]{};
    OfficialHost host;
    host.call<void>(filter_string_assign,Address(&input),Address(text));
    host.call<void>(filter_field_set,node,Address(&input));
    const auto current=host.call<Address>(filter_field_get,node);
    bool equal=false;
    if (!host.fault) {
        monitor_maps::Snapshot memory;
        Reader reader{memory};
        if (reader.readable(current,24)) {
            const auto tag=reader.get<uint8_t>(current);
            const Size length=tag&1 ? reader.get<Size>(current+8) : tag>>1;
            const Address bytes=tag&1 ? reader.get<Address>(current+16) : current+1;
            equal=length==size && reader.readable(bytes,length+1) &&
                !memcmp(reinterpret_cast<const void*>(bytes),text,size+1);
        }
    }
    if (input[0]&1) {
        Address data=0;
        memcpy(&data,input+16,sizeof(data));
        OfficialHost cleanup;
        cleanup.call<void>(filter_string_free,data);
    }
    return equal;
}
}

#include "filter_adapter.h"

bool filter_confirmed(const char* argument,const filter_cli::View& view) {
    if (!view.valid || !view.ready) return false;
    if (!strcmp(argument,"open")) return view.open;
    if (!strcmp(argument,"close")) return !view.open;
    if (!strcmp(argument,"reset"))
        return view.query_size==0 && view.sort==1 && view.group==0 && view.reverse==0;
    char query[akaine_filter::QUERY_LIMIT+1]{};
    Size size=0;
    return !strncmp(argument,"query:",6) &&
        akaine_filter::decode_query(argument+6,strlen(argument+6),query,&size) &&
        filter_cli::query_confirmed(view,query,size);
}

const char* filter_action(Reader& reader,Address scene,const UiTree& tree,const char* argument) {
    if (!strcmp(argument,"open")) return filter_cli::open(reader,scene,tree);
    if (!strcmp(argument,"close")) return filter_cli::close(reader,scene,tree);
    if (!strcmp(argument,"reset")) return filter_cli::reset(reader,scene,tree);
    char query[akaine_filter::QUERY_LIMIT+1]{};
    Size size=0;
    if (strncmp(argument,"query:",6) ||
        !akaine_filter::decode_query(argument+6,strlen(argument+6),query,&size)) return "INVALID_ARGUMENT";
    return filter_cli::query(reader,scene,tree,query,size);
}
