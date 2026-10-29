// Exercises byte-identical production recognizers in a disposable include layout.
// Reader memory, UiTree enumeration and pin bytes are synthetic fixtures. This
// proves local guard/dispatch behavior, not shipped-binary compatibility or touch priority.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <functional>
#include <string>
#include <vector>

using Address = uintptr_t;
using Size = size_t;
struct Range { Address begin, end; };
struct CliPin { Address address; const unsigned char* bytes; Size size; };
struct { Address base; Range executable[1]; Size executable_count = 1; } module;
bool owner_thread = true, deadline_open = true, base_pins_valid = true;
unsigned called = 0, rejected = 0;
Address last_address = 0, last_argument = 0;
bool in_ranges(const Range* ranges, Size count, Address at, Size size) {
    for (Size i = 0; i < count; ++i)
        if (at >= ranges[i].begin && at <= ranges[i].end && size <= ranges[i].end - at) return true;
    return false;
}
bool same_bytes(const unsigned char* a, const unsigned char* b, Size size) { return !memcmp(a, b, size); }
bool static_pointer(Address at, Address* output) {
    if (!in_ranges(module.executable, module.executable_count, at, sizeof(*output))) return false;
    memcpy(output, reinterpret_cast<void*>(at), sizeof(*output)); return true;
}
bool official_thread() { return owner_thread; }
bool cli_dispatch_allowed() { return deadline_open; }
bool cli_play_pins() { return base_pins_valid; }
struct Reader {
    std::vector<Range> ranges;
    bool fault = false;
    bool readable(Address at, Size size) const { return at && in_ranges(ranges.data(), ranges.size(), at, size); }
    template<class T> T get(Address at) {
        T value{};
        if (!readable(at, sizeof(T))) fault = true;
        else memcpy(&value, reinterpret_cast<void*>(at), sizeof(T));
        return value;
    }
};
struct OfficialHost {
    bool fault = false;
    template<class R> R call(Address address, Address argument) {
        ++called; last_address = address; last_argument = argument;
    }
};
namespace akaine_cli {
struct Json {
    std::string value;
    void add(const char* text) { value += text; }
    void string(const char* text) { value += '"'; value += text; value += '"'; }
};
}
struct FixtureOverlay { const char* id = "pack_selection_hint"; };
struct FixtureOverlays {
    bool complete = true, blocked = false;
    Size count = 0;
    FixtureOverlay items[2];
};
struct CliUiState {
    Address context = 1;
    bool modal_present = true;
    struct Identity {
        bool available = true;
        Address scene = 0, scene_type = 0, modal = 0, modal_type = 0;
    } identity;
    FixtureOverlays overlays;
};
struct CliSongState {
    bool valid = true, filter_open = false, pack_open = false;
    Address selected = 0;
    unsigned difficulty = 2, selected_difficulty = 2;
    char song[65] = "testify";
};
CliSongState song_model;
Address listed_song = 0;
unsigned listed_difficulty = 2;
CliSongState cli_song_capture(Reader&, Address) { return song_model; }
Address cli_song_in_list(Reader&, const CliSongState&, const char*, unsigned* difficulty) {
    *difficulty = listed_difficulty; return listed_song;
}
struct UiTree;
const UiTree* tree_model = nullptr;
struct UiTree {
    struct Item { Address node, parent; } queue[16]{};
    Size count = 0;
    bool valid = true, has_modal = true, loading = false;
    Address modal = 0;
    UiTree() = default;
    UiTree(Reader&, Address, Address, Address) { assert(tree_model); *this = *tree_model; }
    void add(Address node, Address parent) { assert(count < 16); queue[count++] = {node, parent}; }
};
bool ui_name(Reader& reader, Address node, const char* expected) {
    const Size length = reader.get<unsigned char>(node + 0x160) >> 1;
    return length == strlen(expected) && reader.readable(node + 0x161, length + 1)
        && !memcmp(reinterpret_cast<void*>(node + 0x161), expected, length + 1);
}
bool ui_class(Address type, char (&output)[240]) {
    const Address offset = type - module.base;
    const char* name = offset == 0x200 ? "OtherDialog" : offset == 0x208 ? "OtherOverlay"
        : offset == 0x210 ? "OtherPopup" : offset == 0x218 ? "OtherLoading"
        : offset == 0x220 ? "OtherTransition" : "Node";
    if (offset == 0x228) return false;
    strcpy(output, name); return true;
}
#include "../semantic/play/guide/play_guide.h"

struct Fixture {
    std::vector<unsigned char> native = std::vector<unsigned char>(0x1c00000);
    unsigned char data[0x8000]{};
    Reader reader;
    UiTree tree;
    CliUiState ui;
    Address scene, topbar, dialog, root, button, outer, inner, selected, extra;
    template<class T> void put(Address at, T value) { memcpy(reinterpret_cast<void*>(at), &value, sizeof(value)); }
    void node(Address at, Address type, Address parent) {
        put(at, module.base + type); put(at + 0x148, parent);
        put(at + 0x1c0, uint8_t(1)); put(at + 0x1c1, uint8_t(1));
    }
    void name(Address at, const char* text) {
        put(at + 0x160, uint8_t(strlen(text) * 2));
        memcpy(reinterpret_cast<void*>(at + 0x161), text, strlen(text) + 1);
    }
    void pointer(Address offset, Address target) { put(module.base + offset, module.base + target); }
    Fixture() {
        module.base = Address(native.data()); module.executable[0] = {module.base, module.base + native.size()};
        for (const auto& pin : CLI_PLAY_GUIDE_PINS) memcpy(native.data() + pin.address, pin.bytes, pin.size);
        for (const auto& pin : CLI_PLAY_DOWNLOAD_PINS) memcpy(native.data() + pin.address, pin.bytes, pin.size);
        const Address base = Address(data);
        reader.ranges.push_back({base, base + sizeof(data)});
        scene = base; topbar = base + 0x800; dialog = base + 0x1000; root = base + 0x1800;
        button = base + 0x2000; outer = base + 0x2800; inner = base + 0x3000;
        selected = base + 0x3400; extra = base + 0x3800;
        node(scene, 0x1ad2260, 0); node(topbar, 0x1a94648, scene);
        node(dialog, 0x1af8480, topbar); node(root, 0x100, dialog); node(button, 0x1a8ece0, root);
        put(scene + 0x378, topbar); put(dialog + 0x308, root);
        name(button, "button2"); put(button + 0x312, uint8_t(1)); put(button + 0x314, uint8_t(1));
        put(button + 0x400, outer); put(outer, module.base + 0x1ac34b0);
        put(outer + 0x10, dialog); put(outer + 0x40, inner);
        put(inner, module.base + 0x1acf880); put(inner + 8, scene); put(inner + 0x10, selected);
        put(inner + 0x18, unsigned(2));
        pointer(0x1ac34b0 + 0x30, 0x11b1d84); pointer(0x1acf880 + 0x30, 0x1870d58);
        pointer(0x1ad2260 + 0x5f0, 0x13f3ce4); pointer(0x1a8ece0 + 0x630, 0xf66c9c);
        ui.identity.scene = scene; ui.identity.scene_type = module.base + 0x1ad2260;
        ui.identity.modal = dialog; ui.identity.modal_type = module.base + 0x1af8480;
        tree.modal = dialog;
        tree.add(scene, 0); tree.add(topbar, scene); tree.add(dialog, topbar); tree.add(root, dialog); tree.add(button, root);
        tree_model = &tree;
        song_model = CliSongState{}; song_model.selected = selected; listed_song = selected; listed_difficulty = 2;
        owner_thread = deadline_open = base_pins_valid = true; called = 0;
    }
    CliAdvancedGuide capture() { return cli_capture_advanced_guide(reader, scene, ui); }
    const char* skip(const char* expected = "testify") { return cli_song_skip_advanced_guide(reader, scene, expected, ui); }
};

void reject(const char* label, const std::function<void(Fixture&)>& change) {
    Fixture fixture; change(fixture);
    const auto view = fixture.capture();
    const char* error = fixture.skip();
    if (view.available || !error || called) {
        fprintf(stderr, "guard failed: %s available=%d error=%s calls=%u\n",
                label, int(view.available), error ? error : "none", called);
        assert(false);
    }
    ++rejected;
}

int main() {
    {
        Fixture f;
        const auto guide = f.capture();
        assert(guide.available && guide.can_skip && !guide.reason && !strcmp(guide.priority, "single_modal"));
        assert(!strcmp(guide.song, "testify") && guide.difficulty == 2 && called == 0);
        akaine_cli::Json json; cli_write_advanced_guide(json, guide);
        assert(json.value.find("\"song_id\":\"testify\"") != std::string::npos);
        assert(json.value.find("\"can_skip\":true") != std::string::npos);
        assert(!f.skip() && called == 1 && last_address == 0xf66c9c && last_argument == f.button);
    }
    reject("owner thread", [](Fixture&) { owner_thread = false; });
    reject("base pins", [](Fixture&) { base_pins_valid = false; });
    reject("guide pin bytes", [](Fixture& f) { f.native[CLI_PLAY_GUIDE_PINS[0].address] ^= 1; });
    reject("download pin bytes", [](Fixture& f) { f.native[CLI_PLAY_DOWNLOAD_PINS[0].address] ^= 1; });
    reject("pin unreadable", [](Fixture&) { module.executable[0].end = module.base + 1; });
    reject("missing context", [](Fixture& f) { f.ui.context = 0; });
    reject("identity unavailable", [](Fixture& f) { f.ui.identity.available = false; });
    reject("wrong scene", [](Fixture& f) { f.ui.identity.scene = f.root; });
    reject("wrong scene type", [](Fixture& f) { f.ui.identity.scene_type += 8; });
    reject("missing modal", [](Fixture& f) { f.ui.modal_present = false; });
    reject("unknown modal", [](Fixture& f) { f.ui.identity.modal = 0; });
    reject("overlay scan incomplete", [](Fixture& f) { f.ui.overlays.complete = false; });
    reject("invalid selection", [](Fixture&) { song_model.valid = false; });
    reject("filter open", [](Fixture&) { song_model.filter_open = true; });
    reject("pack open", [](Fixture&) { song_model.pack_open = true; });
    reject("selection missing", [](Fixture&) { song_model.selected = 0; });
    reject("difficulty drift", [](Fixture&) { song_model.difficulty = 1; });
    reject("song list membership", [](Fixture&) { listed_song = 0; });
    reject("song list difficulty", [](Fixture&) { listed_difficulty = 1; });
    reject("invalid tree", [](Fixture& f) { f.tree.valid = false; });
    reject("tree modal missing", [](Fixture& f) { f.tree.has_modal = false; });
    reject("loading", [](Fixture& f) { f.tree.loading = true; });
    reject("different modal", [](Fixture& f) { f.tree.modal = f.root; });
    reject("wrong modal identity", [](Fixture& f) { f.ui.identity.modal_type += 8; });
    reject("wrong dialog vtable", [](Fixture& f) { f.put(f.dialog, module.base + 0x1af8488); });
    reject("topbar parent", [](Fixture& f) { f.put(f.topbar + 0x148, f.root); });
    reject("dialog parent", [](Fixture& f) { f.put(f.dialog + 0x148, f.scene); });
    reject("root parent", [](Fixture& f) { f.put(f.root + 0x148, f.scene); });
    reject("button parent", [](Fixture& f) { f.put(f.button + 0x148, f.scene); });
    reject("wrong topbar", [](Fixture& f) { f.put(f.topbar, module.base + 0x1a94650); });
    for (auto offset : {Address(0x1c0), Address(0x1c1)}) {
        reject("inactive topbar", [offset](Fixture& f) { f.put(f.topbar + offset, uint8_t(0)); });
        reject("inactive dialog", [offset](Fixture& f) { f.put(f.dialog + offset, uint8_t(0)); });
        reject("inactive root", [offset](Fixture& f) { f.put(f.root + offset, uint8_t(0)); });
        reject("inactive button", [offset](Fixture& f) { f.put(f.button + offset, uint8_t(0)); });
    }
    reject("closing dialog", [](Fixture& f) { f.put(f.dialog + 0x302, uint8_t(1)); });
    reject("missing Skip", [](Fixture& f) { f.name(f.button, "button1"); });
    reject("duplicate Skip", [](Fixture& f) {
        f.node(f.extra, 0x1a8ece0, f.root); f.name(f.extra, "button2"); f.tree.add(f.extra, f.root);
    });
    for (auto type : {Address(0x200), Address(0x208), Address(0x210), Address(0x218), Address(0x220), Address(0x228)})
        reject("competing/unknown UI", [type](Fixture& f) { f.node(f.extra, type, f.scene); f.tree.add(f.extra, f.scene); });
    reject("wrong button vtable", [](Fixture& f) { f.put(f.button, module.base + 0x1a8ece8); });
    for (auto offset : {Address(0x312), Address(0x314)})
        reject("disabled button", [offset](Fixture& f) { f.put(f.button + offset, uint8_t(0)); });
    reject("button busy", [](Fixture& f) { f.put(f.button + 0x448, uint8_t(1)); });
    for (auto offset : {Address(0x398), Address(0x3a0), Address(0x3a8), Address(0x3d0)})
        reject("competing button callback", [offset](Fixture& f) { f.put(f.button + offset, f.outer); });
    reject("outer type", [](Fixture& f) { f.put(f.outer, module.base + 0x1ac34b8); });
    reject("outer unreadable", [](Fixture& f) { f.put(f.button + 0x400, Address(0)); });
    reject("outer owner", [](Fixture& f) { f.put(f.outer + 0x10, f.scene); });
    reject("inner type", [](Fixture& f) { f.put(f.inner, module.base + 0x1acf888); });
    reject("inner unreadable", [](Fixture& f) { f.put(f.outer + 0x40, Address(0)); });
    reject("inner owner", [](Fixture& f) { f.put(f.inner + 8, f.dialog); });
    reject("inner song", [](Fixture& f) { f.put(f.inner + 0x10, f.extra); });
    reject("inner difficulty", [](Fixture& f) { f.put(f.inner + 0x18, unsigned(1)); });
    reject("inner mode", [](Fixture& f) { f.put(f.inner + 0x1c, unsigned(1)); });
    reject("inner trailing capture", [](Fixture& f) { f.put(f.inner + 0x20, f.extra); });
    for (auto offset : {Address(0x1ac34b0 + 0x30), Address(0x1acf880 + 0x30),
                        Address(0x1ad2260 + 0x5f0), Address(0x1a8ece0 + 0x630)})
        reject("registered callback pointer", [offset](Fixture& f) { f.put(module.base + offset, f.extra); });
    reject("sticky reader fault", [](Fixture& f) { f.reader.fault = true; });
    {
        Fixture f;
        assert(!strcmp(f.skip("other"), "SELECTION_CHANGED") && called == 0);
        deadline_open = false;
        assert(f.capture().available && !strcmp(f.skip(), "EXPIRED") && called == 0);
    }
    {
        Fixture f;
        f.ui.overlays.count = 1; f.ui.overlays.blocked = true;
        auto guide = f.capture();
        assert(guide.available && !guide.can_skip && !strcmp(guide.priority, "unproven"));
        assert(!strcmp(guide.reason, "pack_hint_priority_unproven"));
        assert(!strcmp(f.skip(), "INPUT_BLOCKED") && called == 0);
        // Even an inactive known hint cannot prove modal listener precedence.
        f.ui.overlays.blocked = false; guide = f.capture();
        assert(guide.available && !guide.can_skip && !strcmp(guide.reason, "pack_hint_priority_unproven") && called == 0);
        assert(!strcmp(f.skip(), "INPUT_BLOCKED") && called == 0);
        f.ui.overlays.items[0].id = "unknown_progression_guide"; guide = f.capture();
        assert(guide.available && !guide.can_skip && !strcmp(guide.reason, "input_blocked") && called == 0);
        assert(!strcmp(f.skip(), "INPUT_BLOCKED") && called == 0);
    }
    printf("PASS advanced guide: %u negative graph/ownership/pin guards, read-only discovery, one ordinary release, expiry and unproven priority\n", rejected);
    puts("Fixture uses synthetic pin bytes; shipped-binary compatibility and native listener priority remain external gates.");
}
