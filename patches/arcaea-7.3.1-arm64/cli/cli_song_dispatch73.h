#include "bounds.h"
using anomaly_monitor::Size;
using anomaly_monitor::same_bytes;
struct CliPin { Address address; const unsigned char* bytes; Size size; };
struct Reader {
    const monitor_maps::Snapshot& memory;
    bool fault = false;
    bool readable(Address address, Size length) const {
        return !fault && memory.contains(address,length);
    }
    template<class T> T get(Address address) {
        T result{};
        if (!readable(address,sizeof(T)) || !read(memory,address,result)) fault = true;
        return result;
    }
};
struct CoreView { Address base; const Range* executable; size_t executable_count; };
CoreView module;

bool in_ranges(const Range* ranges,size_t size,Address address,Size length) {
    for (size_t i=0;i<size;++i)
        if (anomaly_monitor::contains(ranges[i],address,length)) return true;
    return false;
}
bool official_thread() { return pthread_equal(owner,pthread_self()); }
bool cli_dispatch_allowed() {
    return awaiting && official_thread() &&
        !akaine_cli::request_guard(pending,session,clock_value(CLOCK_REALTIME,1000));
}
struct OfficialHost {
    bool fault = false;
    template<class Return,class... Args> Return call(Address va,Args... args) {
        if (!in_ranges(module.executable,module.executable_count,core+va,4)) {
            fault = true;
            if constexpr (!std::is_void_v<Return>) return Return{};
            else return;
        }
        return reinterpret_cast<Return(*)(Args...)>(core+va)(args...);
    }
};

#include "cli_song_native.h"
#include "play_pins.h"

int target_difficulty = -1;

bool play_pins() {
    if (!cli_song_pins()) return false;
    for (const auto& pin : CLI_PLAY_PINS)
        if (!in_ranges(module.executable,module.executable_count,core+pin.address,pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(core+pin.address),pin.bytes,pin.size)) return false;
    return true;
}

const char* play(Reader& reader,const CliSongState& selection,const char* expected) {
    if (!play_pins()) return "NATIVE_GUARD";
    if (!selection.valid || selection.pack_open || selection.filter_open
        || reader.get<uint8_t>(selection.layer+0x1c1) != 1) return "WRONG_SCENE";
    if (!selection.selected || strcmp(selection.song,expected)
        || selection.difficulty!=selection.selected_difficulty) return "SELECTION_CHANGED";
    unsigned difficulty=0;
    if (cli_song_in_list(reader,selection,expected,&difficulty)!=selection.selected
        || difficulty!=selection.selected_difficulty) return "SONG_NOT_IN_CURRENT_LIST";
    const Address delegate = reader.get<Address>(selection.access+0x18);
    Address invoke=0;
    const Address slot=core+song_delegate_type+0x30;
    if (delegate!=selection.scene+0x308 || reader.get<Address>(delegate)!=core+song_delegate_type
        || !static_readable(slot,sizeof(Address)) || !read(reader.memory,slot,invoke)
        || invoke!=core+song_selected_thunk || reader.fault) return "NATIVE_GUARD";
    if (!cli_dispatch_allowed()) return "EXPIRED";
    target_difficulty = int(difficulty);
    OfficialHost call;
    call.call<void>(song_highlight,selection.access,selection.selected,uint32_t(difficulty),uint32_t(1),
        uint32_t(0),uint32_t(1),uint32_t(0),uint32_t(0),int32_t(-1));
    return call.fault ? "NATIVE_GUARD" : nullptr;
}

bool is_song_command(const char* name) {
    const char* commands[]={"song_select","pack_select","pack_close","difficulty","sort","group","reverse","play"};
    for (const char* command:commands) if (!strcmp(name,command)) return true;
    return false;
}

bool song_confirmed(const Request& request,const CliSongState& selection) {
    if (!selection.valid) return false;
    const auto* name = request.command;
    const auto* argument = request.argument;
    if (!strcmp(name,"song_select")) return !selection.pack_open && !strcmp(selection.song,argument);
    if (!strcmp(name,"pack_select")) return !selection.pack_open && !strcmp(selection.pack_id,argument);
    if (!strcmp(name,"pack_close")) return !selection.pack_open;
    const unsigned expected = unsigned(argument[0]-'0');
    if (!strcmp(name,"difficulty")) return selection.difficulty==expected;
    if (!strcmp(name,"sort")) return selection.sort==expected;
    if (!strcmp(name,"group")) return selection.group==expected;
    return !strcmp(name,"reverse") && selection.reverse==expected;
}
