constexpr char replay_preference_key[]="AkaineAnomalyReplay";

bool replay_cli_pins() {
    for (const auto& pin : REPLAY_CLI_PINS)
        if (!in_ranges(module.executable,module.executable_count,core+pin.address,pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(core+pin.address),pin.bytes,pin.size))
            return false;
    return true;
}

int replay_library(dl_phdr_info* info,size_t,void* data) {
    if (!info->dlpi_name) return 0;
    const char* leaf=strrchr(info->dlpi_name,'/');
    if (strcmp(leaf?leaf+1:info->dlpi_name,"libakaine_replay73.so")) return 0;
    auto& range=*static_cast<Range*>(data);
    for (size_t i=0;i<info->dlpi_phnum;++i) {
        const auto& ph=info->dlpi_phdr[i];
        if (ph.p_type==PT_LOAD && ph.p_flags==(PF_R|PF_X) &&
            ph.p_vaddr<=UINTPTR_MAX-info->dlpi_addr &&
            ph.p_memsz<=UINTPTR_MAX-info->dlpi_addr-ph.p_vaddr) {
            const Address start=info->dlpi_addr+ph.p_vaddr;
            range={start,start+ph.p_memsz};
            return 1;
        }
    }
    return 1;
}

int replay_value(const monitor_maps::Snapshot& memory) {
    const Address mailbox=core+replay_mailbox;
    if (!replay_cli_pins() || !static_readable(mailbox,24) || !memory.contains(mailbox,24)) return -1;
    const auto* state=reinterpret_cast<const Address*>(mailbox);
    const Address getter=__atomic_load_n(state,__ATOMIC_ACQUIRE);
    const Address setter=__atomic_load_n(state+1,__ATOMIC_ACQUIRE);
    const Address disabled=__atomic_load_n(state+2,__ATOMIC_ACQUIRE);
    if (!getter || !setter || disabled>1) return -1;
    Range executable{};
    dl_iterate_phdr(replay_library,&executable);
    if (!anomaly_monitor::contains(executable,getter,4) || !anomaly_monitor::contains(executable,setter,4)) return -1;
    OfficialHost host;
    const auto settings=host.call<Address>(replay_get_instance);
    Address vtable,callback;
    if (host.fault || !read(memory,settings,vtable) || vtable!=core+replay_user_default ||
        !static_pointer(vtable,&callback) || callback!=core+replay_get_bool) return -1;
    const bool persisted=host.call<bool>(replay_get_bool,settings,replay_preference_key,true);
    return !host.fault && persisted==(disabled==0)?int(persisted):-1;
}

const char* set_replay(const monitor_maps::Snapshot& memory,int expected) {
    int current=replay_value(memory);
    if (current<0) return "NATIVE_GUARD";
    if (current==expected) return nullptr;
    if (!cli_dispatch_allowed()) return "EXPIRED";
    OfficialHost host;
    host.call<void>(replay_setter_gate,Address(0),Address(&expected),Address(0));
    return host.fault?"NATIVE_GUARD":nullptr;
}
