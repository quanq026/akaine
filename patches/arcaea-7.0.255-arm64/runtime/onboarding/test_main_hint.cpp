#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <string>
#include <vector>
using Address = uintptr_t;
using Size = size_t;
struct Range { Address begin, end; };
struct CliPin { Address address; const unsigned char* bytes; Size size; };
struct { Address base; Range executable[1]; Size executable_count = 1; } module;
bool in_ranges(const Range* ranges, Size count, Address at, Size size) {
    for (Size i = 0; i < count; ++i) if (at >= ranges[i].begin && at <= ranges[i].end && size <= ranges[i].end-at) return true;
    return false;
}
bool module_readable(Address at, Size n) { return in_ranges(module.executable, module.executable_count, at, n); }
bool same_bytes(const unsigned char* a, const unsigned char* b, Size n) { return !memcmp(a, b, n); }
bool static_pointer(Address a, Address* out) {
    if (!module_readable(a,8)) return false;
    memcpy(out,reinterpret_cast<void*>(a),8); return true;
}
bool owner_thread = true, deadline_open = true;
bool official_thread() { return owner_thread; }
bool cli_dispatch_allowed() { return deadline_open; }
unsigned called = 0; Address last_address = 0, last_argument = 0;
struct OfficialHost {
    bool fault = false;
    template<class R> R call(Address address, Address argument) { ++called; last_address = address; last_argument = argument; }
};
struct Reader {
    std::vector<Range> ranges;
    bool fault = false;
    bool readable(Address at, Size size) const { return !fault && at && in_ranges(ranges.data(), ranges.size(), at, size); }
    template<class T> T get(Address at) {
        T value = {};
        if (!readable(at, sizeof(value))) fault = true;
        else memcpy(&value, reinterpret_cast<const void*>(at), sizeof(value));
        return value;
    }
};
struct Json {
    std::string value;
    void add(const char* text) { value += text; }
    void string(const char* text) { value += '"'; value += text; value += '"'; }
};
#include "../semantic/overlays/overlay_state.h"

struct Fixture {
    std::vector<unsigned char> native = std::vector<unsigned char>(0x1ba0000);
    unsigned char data[0x8000] = {};
    Reader reader;
    Address scene, guide, overlay, banner, listener, began, callback, done, gate, scene_array;
    template<class T> void put(Address at, T value) { memcpy(reinterpret_cast<void*>(at), &value, sizeof(value)); }
    void node(Address at, Address type, Address parent) {
        put(at, module.base + type); put(at + 0x148, parent);
        put(at + 0x1c0, uint8_t(1)); put(at + 0x1c1, uint8_t(1)); put(at + 0x1d0, uint8_t(255));
    }
    Fixture() {
        module.base = Address(native.data()); module.executable[0] = {module.base, module.base + native.size()};
        for (const auto& pin : CLI_OVERLAY_PINS) memcpy(native.data() + pin.address, pin.bytes, pin.size);
        for (const auto& pin : CLI_MAIN_HINT_PINS) memcpy(native.data() + pin.address, pin.bytes, pin.size);
        for (const auto& pin : CLI_NOTIFICATION_HINT_PINS) memcpy(native.data() + pin.address, pin.bytes, pin.size);
        put(module.base + 0x1b47628 + 0x30, module.base + 0xbac0a4);
        put(module.base + 0x1aea110 + 0xa0, module.base + 0x1026cac);
        const Address base = Address(data);
        reader.ranges.push_back({base, base + sizeof(data)});
        scene = base; guide = base + 0x500; overlay = base + 0x900; banner = base + 0xd00;
        listener = base + 0x1100; began = base + 0x1300; callback = base + 0x1400; done = base + 0x1500; gate = base + 0x1600;
        node(scene, 0x1ad2260, 0); node(guide, 0x1b20180, scene); node(overlay, 0x1b90800, guide);
        node(banner, 0x1aa0128, guide); node(gate, 0x1b4d3e8, 0);
        const Address scene_vector = base + 0x2000, guide_vector = base + 0x2100, guide_array = base + 0x2120;
        scene_array = base + 0x2020;
        put(scene + 0x140, scene_vector); put(scene_vector, scene_array); put(scene_vector + 8, scene_array + 8);
        put(scene_vector + 16, scene_array + 8); put(scene_array, guide);
        put(guide + 0x140, guide_vector); put(guide_vector, guide_array); put(guide_vector + 8, guide_array + 16);
        put(guide_vector + 16, guide_array + 16); put(guide_array, overlay); put(guide_array + 8, banner);
        put(guide + 0x2f0, done); put(done, module.base + 0x1b665d8); put(done + 8, scene);
        put(guide + 0x318, gate); put(guide + 0x338, uint8_t(1)); put(guide + 0x340, overlay); put(guide + 0x348, banner);
        put(guide + 0x370, Size(1)); put(guide + 0x378, Size(1));
        put(overlay + 0x318, listener); put(listener, module.base + 0x1a953c8);
        put(listener + 0x60, uint8_t(1)); put(listener + 0x68, overlay); put(listener + 0x71, uint8_t(1)); put(listener + 0x158, uint8_t(1));
        put(listener + 0xa0, began); put(began, module.base + 0x1adfd70); put(began + 8, Address(0x548));
        put(began + 0x10, Address(1)); put(began + 0x18, overlay);
        put(overlay + 0x2f0, callback); put(callback, module.base + 0x1b1c1e8); put(callback + 8, guide); put(callback + 0x10, guide);
        owner_thread = true; deadline_open = true; called = 0;
    }
    overlay_cli::View capture() { return overlay_cli::capture(reader, scene, "15SongSelectScene"); }
    void duplicate_guide() {
        const Address other = Address(data) + 0x4000, other_overlay = other + 0x400, other_banner = other + 0x800;
        const Address other_listener = other + 0xc00, other_began = other + 0xe00, other_callback = other + 0xf00;
        memcpy(data + 0x4000, data + 0x500, 0x380);
        memcpy(data + 0x4400, data + 0x900, 0x323);
        memcpy(data + 0x4800, data + 0xd00, 0x1da);
        memcpy(data + 0x4c00, data + 0x1100, 0x159);
        memcpy(data + 0x4e00, data + 0x1300, 0x20);
        memcpy(data + 0x4f00, data + 0x1400, 0x18);
        put(other + 0x140, Address(0)); put(other + 0x340, other_overlay); put(other + 0x348, other_banner);
        put(other_overlay + 0x148, other); put(other_overlay + 0x318, other_listener); put(other_overlay + 0x2f0, other_callback);
        put(other_banner + 0x148, other); put(other_listener + 0x68, other_overlay); put(other_listener + 0xa0, other_began);
        put(other_began + 0x18, other_overlay); put(other_callback + 8, other); put(other_callback + 0x10, other);
        const Address scene_vector = get_vector();
        put(scene_vector + 8, scene_array + 16); put(scene_vector + 16, scene_array + 16); put(scene_array + 8, other);
    }
    Address get_vector() { Address value = 0; memcpy(&value, reinterpret_cast<void*>(scene + 0x140), 8); return value; }
};
int main() {
    Fixture f;
    auto view = f.capture();
    assert(view.complete && view.count == 1 && view.blocked && overlay_cli::can_advance(view));
    const auto& item = view.items[0];
    assert(!strcmp(item.id, "pack_selection_hint") && item.active && item.visible && item.opacity == 255 && item.blocks_input);
    assert(!overlay_cli::advance(f.reader, f.scene, view) && called == 1 && last_address == 0x1934b7c && last_argument == f.callback);
    f.put(f.banner + 0x1d0, uint8_t(0)); f.put(f.guide + 0x1c1, uint8_t(0));
    view = f.capture();
    assert(view.complete && view.count == 1 && view.blocked && view.items[0].active && !view.items[0].visible
           && view.items[0].opacity == 0 && view.items[0].blocks_input);
    f.put(f.guide + 0x1c0, uint8_t(0)); f.put(f.overlay + 0x1c0, uint8_t(0));
    view = f.capture();
    assert(view.complete && view.blocked && !view.items[0].active && view.items[0].blocks_input && !overlay_cli::can_advance(view));
    f.put(f.guide + 0x1c0, uint8_t(1)); f.put(f.overlay + 0x1c0, uint8_t(1));
    f.put(f.listener + 0x70, uint8_t(1));
    view = f.capture(); assert(view.complete && view.blocked && !view.items[0].blocks_input && !overlay_cli::can_advance(view));
    f.put(f.listener + 0x70, uint8_t(0)); f.put(f.done, module.base + 0x1b665e0);
    view = f.capture(); assert(view.complete && view.blocked && !strcmp(view.items[0].id, "unknown_progression_guide") && !overlay_cli::can_advance(view));
    f.put(f.done, module.base + 0x1b665d8); f.put(f.callback + 0x10, f.scene);
    view = f.capture(); assert(view.complete && !overlay_cli::can_advance(view));
    f.put(f.callback + 0x10, f.guide); f.put(f.guide + 0x338, uint8_t(0));
    view = f.capture(); assert(view.complete && !overlay_cli::can_advance(view));
    f.put(f.guide + 0x338, uint8_t(1)); view = f.capture();
    f.put(f.guide + 0x370, Size(2));
    assert(!strcmp(overlay_cli::advance(f.reader, f.scene, view), "STALE_UI_CONTEXT"));
    f.put(f.guide + 0x370, Size(1)); view = f.capture(); deadline_open = false;
    assert(!strcmp(overlay_cli::advance(f.reader, f.scene, view), "EXPIRED")); deadline_open = true;
    owner_thread = false; assert(!strcmp(overlay_cli::advance(f.reader, f.scene, view), "NATIVE_GUARD")); owner_thread = true;
    Json json; overlay_cli::write_fields(json, view);
    assert(json.value.find("\"pack_selection_hint\"") != std::string::npos && json.value.find("\"overlay_scan_complete\":true") != std::string::npos);
    f.put(f.listener + 0x68, f.scene); view = f.capture();
    assert(!view.complete && view.blocked && view.count == 0 && !overlay_cli::can_advance(view));
    f.put(f.listener + 0x68, f.overlay); f.put(f.guide + 0x148, f.banner);
    view = f.capture(); assert(!view.complete && view.blocked && !strcmp(view.reason, "parent_link"));
    f.put(f.guide + 0x148, f.scene); f.put(f.scene_array, f.scene);
    view = f.capture(); assert(!view.complete && view.blocked && !strcmp(view.reason, "duplicate_node"));
    f.put(f.scene_array, f.guide); f.native[CLI_OVERLAY_PINS[0].address] ^= 1;
    view = f.capture(); assert(!view.complete && view.blocked && !strcmp(view.reason, "pin_mismatch_or_unavailable"));
    f.native[CLI_OVERLAY_PINS[0].address] ^= 1; f.duplicate_guide();
    view = f.capture(); assert(!view.complete && view.blocked && view.count == 1 && !strcmp(view.reason, "ambiguous_guide"));
    Fixture main;
    main.put(main.scene, module.base + 0x1b2e5a0); main.put(main.done, module.base + 0x1b153d8);
    view=main.capture(); assert(view.complete && view.blocked && overlay_cli::can_advance(view));
    assert(!strcmp(view.items[0].id, "main_menu_hint"));
    assert(!overlay_cli::advance(main.reader,main.scene,view) && called==1 && last_argument==main.callback);
    main.put(main.done+8, main.guide); view=main.capture(); assert(!overlay_cli::can_advance(view));
    main.put(main.done+8, main.scene); main.put(main.scene,module.base+0x1ad2260);
    view=main.capture(); assert(!overlay_cli::can_advance(view));
    main.put(main.scene,module.base+0x1b2e5a0); main.native[CLI_MAIN_HINT_PINS[0].address]^=1;
    view=main.capture(); assert(!view.complete && !overlay_cli::can_advance(view));
    Fixture notification;
    notification.put(notification.scene,module.base+0x1b2e5a0);
    notification.put(notification.done,module.base+0x1b47628);
    view=notification.capture(); assert(view.complete && overlay_cli::can_advance(view));
    assert(!strcmp(view.items[0].id,"notification_permission_guide"));
    assert(!overlay_cli::advance(notification.reader,notification.scene,view) && called==1 && last_argument==notification.callback);
    notification.put(notification.done+8,notification.guide); view=notification.capture(); assert(!overlay_cli::can_advance(view));
    notification.put(notification.done+8,notification.scene); notification.put(notification.scene,module.base+0x1ad2260);
    view=notification.capture(); assert(!overlay_cli::can_advance(view));
    notification.put(notification.scene,module.base+0x1b2e5a0);
    notification.put(module.base+0x1aea110+0xa0,module.base+0xa43d94);
    view=notification.capture(); assert(!view.complete && !overlay_cli::can_advance(view));
    notification.put(module.base+0x1aea110+0xa0,module.base+0x1026cac);
    notification.native[CLI_NOTIFICATION_HINT_PINS[0].address]^=1;
    view=notification.capture(); assert(!view.complete && !overlay_cli::can_advance(view));
    puts("PASS exact main-menu hint plus hidden tutorial state, independent opacity/input, exact ownership, unknown workflow, stale/deadline/thread/pin guards");
}
