#include <android/log.h>
#include <jni.h>
#include <link.h>
#include <pthread.h>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include "setting_toggle.h"
#include "replay_abi73.h"
#ifdef AKAINE_OFFICIAL_REPLAY
#include <type_traits>
#include "maps_snapshot.h"
#include "official_profiles73.h"
#endif

namespace {
using Address = uintptr_t;
using Persist = anomaly_monitor::PersistToggle;
using ReadBool = bool (*)(void*, const char*, bool);
using Singleton = void* (*)();

struct Toggle {
    Address getter;
    Address setter;
    Address disabled;
#ifdef AKAINE_OFFICIAL_REPLAY
    Address reserved;
    Address factory, init, update, finish, progress;
    Address active_last, is_last, scoped_tag, scoped_actor;
    Address failed_actor, pending_finale, reserved_tail;
#endif
};
static_assert(offsetof(Toggle, disabled) == 16);
#ifdef AKAINE_OFFICIAL_REPLAY
static_assert(sizeof(Toggle) == 128 && offsetof(Toggle, factory) == 32
    && offsetof(Toggle, progress) == 64 && offsetof(Toggle, pending_finale) == 112);
#endif
constexpr char tag[] = "AkaineReplay73";
std::atomic<Address> core{0};
std::atomic<pthread_t> owner{0};

Toggle& mailbox(Address base) {
    return *reinterpret_cast<Toggle*>(base + toggle_mailbox);
}

void* checked_settings(Address base) {
    void* settings = reinterpret_cast<Singleton>(base + get_instance)();
    if (!settings) return nullptr;
    const auto* vtable = *reinterpret_cast<Address* const*>(settings);
    if (reinterpret_cast<Address>(vtable) != base + user_default) return nullptr;
    return vtable[0] == base + get_bool && vtable[6] == base + set_bool ? settings : nullptr;
}

int setting_getter(void*) {
    const auto base = core.load(std::memory_order_acquire);
    return base && __atomic_load_n(&mailbox(base).disabled, __ATOMIC_ACQUIRE) == 1 ? 0 : 1;
}

void setting_setter(void*, const int* choice, const void*) {
    if (!choice || owner.load(std::memory_order_acquire) != pthread_self()) return;
    const auto base = core.load(std::memory_order_acquire);
    if (!base) return;
    int index = -1;
    std::memcpy(&index, choice, sizeof(index));
    if (index != 0 && index != 1) return;
    Address disabled = 0;
    if (!anomaly_monitor::commit_toggle_choice(checked_settings(base),
            reinterpret_cast<Persist>(base + set_bool), index, &disabled))
        return;
    __atomic_store_n(&mailbox(base).disabled, disabled, __ATOMIC_RELEASE);
    __android_log_print(ANDROID_LOG_INFO, tag, "anomaly_replay_enabled=%d", index);
}

int find_core(dl_phdr_info* module, size_t, void* result) {
    if (!module->dlpi_name) return 0;
    const char* name = std::strrchr(module->dlpi_name, '/');
    if (std::strcmp(name ? name + 1 : module->dlpi_name, "libcocos2dcpp.so")) return 0;
    bool executable = false, writable = false;
    for (size_t i = 0; i < module->dlpi_phnum; ++i) {
        const auto& ph = module->dlpi_phdr[i];
        if (ph.p_type != PT_LOAD) continue;
        executable |= ph.p_flags == (PF_R | PF_X) && !ph.p_vaddr
            && ph.p_filesz == rx_end && ph.p_memsz == rx_end;
        writable |= ph.p_flags == (PF_R | PF_W) && ph.p_vaddr == rw_start
            && ph.p_filesz == rw_file_size && ph.p_memsz == rw_mem_size;
    }
    if (!executable || !writable) return 1;
    for (const auto& pin : replay_pins) {
        if (pin.va > rx_end || pin.length > rx_end - pin.va
            || std::memcmp(reinterpret_cast<const void*>(module->dlpi_addr + pin.va), pin.bytes, pin.length))
            return 1;
    }
    *static_cast<Address*>(result) = module->dlpi_addr;
    return 1;
}
#ifdef AKAINE_OFFICIAL_REPLAY
#include "official_runtime73.h"
#endif
}

extern "C" JNIEXPORT void JNICALL
Java_org_cocos2dx_lib_AkaineReplay73_prepareNative(JNIEnv*, jclass) {
    Address found = 0;
    dl_iterate_phdr(find_core, &found);
    if (!found) return;
    void* settings = checked_settings(found);
    if (!settings) return;
    const bool enabled = reinterpret_cast<ReadBool>(found + get_bool)(
        settings, anomaly_monitor::ANOMALY_REPLAY_KEY, true);
    Address expected = 0;
    if (!core.compare_exchange_strong(expected, found) && expected != found) return;
    owner.store(pthread_self(), std::memory_order_release);
    auto& state = mailbox(found);
    __atomic_store_n(&state.disabled, enabled ? Address{0} : Address{1}, __ATOMIC_RELEASE);
#ifdef AKAINE_OFFICIAL_REPLAY
    prepare_official(found);
#endif
    __atomic_store_n(&state.setter, reinterpret_cast<Address>(&setting_setter), __ATOMIC_RELEASE);
    __atomic_store_n(&state.getter, reinterpret_cast<Address>(&setting_getter), __ATOMIC_RELEASE);
}
