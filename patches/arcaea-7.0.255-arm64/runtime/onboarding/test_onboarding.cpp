#include <cassert>
#include <cstdint>
#include <cstring>
#include <memory>
#include <vector>
#include <cstdio>
using Address = uintptr_t;
using Size = size_t;
struct Range { Address begin, end; };
struct CliPin { Address address; const unsigned char* bytes; Size size; };
bool in_ranges(const Range* ranges, Size n, Address a, Size z) {
    for (Size i = 0; i < n; ++i) if (a >= ranges[i].begin && a <= ranges[i].end && z <= ranges[i].end - a) return true;
    return false;
}
bool same_bytes(const unsigned char* a, const unsigned char* b, Size n) { return !memcmp(a,b,n); }
struct Module { Address base; Range executable[1]; Size executable_count = 1; } module;
std::vector<Range> heap;
std::vector<std::unique_ptr<unsigned char[]>> objects;
struct Reader {
    bool fault = false;
    bool readable(Address a, Size n) { return in_ranges(heap.data(),heap.size(),a,n); }
    template<class T> T get(Address a) {
        T result{}; if (!readable(a,sizeof(T))) { fault = true; return result; }
        memcpy(&result,reinterpret_cast<void*>(a),sizeof(T)); return result;
    }
};
bool static_pointer(Address a, Address* out) {
    if (!in_ranges(module.executable,1,a,sizeof(Address))) return false;
    memcpy(out,reinterpret_cast<void*>(a),sizeof(Address)); return true;
}
bool ui_name(Reader& h, Address node, const char* name) {
    return h.readable(node+0x160,24) && h.get<unsigned char>(node+0x160) == strlen(name)*2
        && !memcmp(reinterpret_cast<void*>(node+0x161),name,strlen(name)+1);
}
bool ui_class(Address vt, char (&out)[240]) {
    const char* name = vt == module.base+0x1af8480 ? "11DialogLayer" : vt == module.base+0x1ac3640 ? "15SettingsLayerV2"
        : vt == module.base+0x1ad4218 ? "21SettingsLayerV2Offset" : vt == module.base+0x123 ? "UnknownPopup" : "N7cocos2d4NodeE";
    strcpy(out,name); return true;
}
struct UiTree { bool valid = true, loading = false; struct Item { Address node; bool ancestors_enabled = true; } queue[32]{}; Size inspected = 0; };
struct CliUiAction { const char* name = nullptr; const char* label = nullptr; Address node = 0, closure = 0; };
struct CliUiState {
    struct { Address modal = 0, modal_type = 0, nodes[8]{}, callbacks[8]{}; uint32_t flags[8]{}; } identity;
    CliUiAction actions[2]; Size action_count = 0; const char* reason = "unsupported_modal";
    const char* onboarding_stage = nullptr;
    bool onboarding_settings_ready = false;
};
#include "cli_onboarding.h"
#include "cli_core.h"

template<class T> void put(Address a, T x) { memcpy(reinterpret_cast<void*>(a),&x,sizeof(T)); }
Address object(Address vt = 0) {
    auto bytes = std::make_unique<unsigned char[]>(0x800); memset(bytes.get(),0,0x800);
    const Address a = reinterpret_cast<Address>(bytes.get());
    heap.push_back({a,a+0x800}); objects.push_back(std::move(bytes));
    put(a, module.base+vt); put<unsigned char>(a+0x1c0,1); put<unsigned char>(a+0x1c1,1); return a;
}
void callback_pin(Address vt, Address invoke) { put(module.base+vt+0x30,module.base+invoke); }
struct Fixture {
    Reader reader; UiTree tree; Address scene, panel = 0, offset = 0;
    Fixture() { scene=object(0x1b2e5a0); add(scene); }
    void add(Address a) { tree.queue[tree.inspected++].node=a; }
    void setup() {
        panel=object(0x1ac3640); put(panel+0x148,scene); put(panel+0x328,scene+0x2f8); add(panel);
        offset=object(0x1ad4218); put(offset+0x148,panel); add(offset);
    }
    Address dialog(bool single) {
        const Address d=object(0x1af8480); put(d+0x148,scene);
        put<unsigned char>(d+0x301,single); put<unsigned char>(d+0x340,1); add(d); return d;
    }
    Address button(Address d, bool single, bool secondary, Address inner_type, Address owner, Address invoke) {
        const Address node=object(0x1a8ece0), layout=object(), wrapper=object(), inner=object();
        put(node+0x148,layout); put(layout+0x148,d);
        put<unsigned char>(node+0x312,1); put<unsigned char>(node+0x314,1);
        const char* name=single ? "button3" : secondary ? "button2" : "button1";
        put<unsigned char>(node+0x160,strlen(name)*2); memcpy(reinterpret_cast<void*>(node+0x161),name,strlen(name)+1);
        const Address vt=single?0x1b1a2d8:secondary?0x1ac34b0:0x1b4aec8;
        callback_pin(vt,single?0x9ad6f4:secondary?0x11b1d84:0x1411494);
        callback_pin(inner_type,invoke);
        put(wrapper,module.base+vt); put(wrapper+0x10,d); put(wrapper+0x40,inner);
        put(inner,module.base+inner_type); put(inner+8,owner); put(node+0x400,wrapper);
        put(d+(single?0x330:secondary?0x328:0x320),node); add(layout); add(node); return node;
    }
    bool capture(unsigned stage) {
        reader.fault=false; CliUiState out;
        const bool ok=capture_onboarding(reader,scene,tree,out);
        return ok && out.action_count==1 && out.identity.flags[2]==stage && out.onboarding_stage && !out.reason;
    }
};
int main() {
    std::vector<unsigned char> image(0x1c00000); module.base=reinterpret_cast<Address>(image.data());
    module.executable[0]={module.base,module.base+image.size()};
    for (const auto& p:CLI_ONBOARDING_PINS) memcpy(image.data()+p.address,p.bytes,p.size);
    assert(onboarding_pins()); image[CLI_ONBOARDING_PINS[0].address]^=1; assert(!onboarding_pins()); image[CLI_ONBOARDING_PINS[0].address]^=1;
    Fixture welcome; const Address wd=welcome.dialog(true);
    const Address wb=welcome.button(wd,true,false,0x1b6e038,welcome.scene,0x98ab54);
    assert(welcome.capture(1));
    memcpy(reinterpret_cast<void*>(wb+0x161),"button4",8); assert(!welcome.capture(1));
    memcpy(reinterpret_cast<void*>(wb+0x161),"button3",8); assert(welcome.capture(1));
    for (Size i=0;i<welcome.tree.inspected;++i) if (welcome.tree.queue[i].node==wb) welcome.tree.queue[i].ancestors_enabled=false;
    assert(!welcome.capture(1));
    for (Size i=0;i<welcome.tree.inspected;++i) welcome.tree.queue[i].ancestors_enabled=true;
    put<unsigned char>(wd+0x1c0,0); assert(!welcome.capture(1)); put<unsigned char>(wd+0x1c0,1);
    put<unsigned char>(wb+0x448,1); assert(!welcome.capture(1)); put<unsigned char>(wb+0x448,0);
    put(wb+0x3d0,Address(1)); assert(!welcome.capture(1)); put(wb+0x3d0,Address(0));
    const Address wrap=welcome.reader.get<Address>(wb+0x400), inner=welcome.reader.get<Address>(wrap+0x40);
    put(inner+8,Address(1)); assert(!welcome.capture(1)); put(inner+8,welcome.scene);
    put<unsigned char>(wd+0x302,1); assert(!welcome.capture(1)); put<unsigned char>(wd+0x302,0);
    const Address alien=object(0x123); welcome.add(alien); assert(!welcome.capture(1)); --welcome.tree.inspected;
    assert(welcome.capture(1)); welcome.tree.loading=true; assert(!welcome.capture(1));
    Fixture cancel; cancel.setup(); const Address cd=cancel.dialog(false);
    cancel.button(cd,false,true,0x1b31300,cancel.offset,0x185aee4); assert(cancel.capture(2));
    put<unsigned char>(cancel.panel+0x1c0,0); assert(!cancel.capture(2)); put<unsigned char>(cancel.panel+0x1c0,1);
    put<unsigned char>(cancel.offset+0x5d8,1); assert(!cancel.capture(2)); put<unsigned char>(cancel.offset+0x5d8,0);
    put(cancel.offset+0x5e8,Address(8)); assert(!cancel.capture(2)); put(cancel.offset+0x5e8,Address(0));
    const Address warning=cancel.dialog(false);
    const Address yes=cancel.button(warning,false,false,0x1a99ce0,cancel.offset,0x9ef864);
    const Address yw=cancel.reader.get<Address>(yes+0x400), yi=cancel.reader.get<Address>(yw+0x40);
    put(yi+0x10,cd); assert(cancel.capture(3));
    put(yi+0x10,wd); assert(!cancel.capture(3)); put(yi+0x10,cd);
    callback_pin(0x1a99ce0,0x98ab54); assert(!cancel.capture(3)); callback_pin(0x1a99ce0,0x9ef864);
    assert(cancel.capture(3));
    cancel.tree.inspected=3;
    const Address close=object(0x1a8ece0), cw=object(), ci=object();
    put(close+0x148,cancel.panel); put<unsigned char>(close+0x312,1); put<unsigned char>(close+0x314,1);
    put(close+0x400,cw); put(cw,module.base+0x1b73478); put(cw+0x10,cancel.panel); put(cw+0x40,ci);
    put(ci,module.base+0x1b3f6a8); put(ci+8,cancel.scene+0x2f8); callback_pin(0x1b3f6a8,0x1620450);
    put(cancel.panel+0x2c8,close); cancel.add(close);
    cancel.reader.fault=false; CliUiState ready;
    assert(!capture_onboarding(cancel.reader,cancel.scene,cancel.tree,ready) && ready.onboarding_settings_ready);
    cancel.add(warning); ready=CliUiState{}; cancel.reader.fault=false;
    capture_onboarding(cancel.reader,cancel.scene,cancel.tree,ready); assert(!ready.onboarding_settings_ready);
    for (const char* name : {"onboarding_setup", "onboarding_cancel", "onboarding_skip"}) {
        char token[65]; snprintf(token,sizeof(token),"%s.0000000000000001",name);
        assert(akaine_cli::action_token(token,strlen(token)));
    }
    const char* unknown="onboarding_accept.0000000000000001";
    assert(!akaine_cli::action_token(unknown,strlen(unknown)));
    puts("PASS: exact welcome/cancel/skip stages; pin mutation, wrong owner, alternate listeners, drag, disabled dialog, unknown popup, loading, completed calibration, samples, wrong warning target and invoke reject.");
}
