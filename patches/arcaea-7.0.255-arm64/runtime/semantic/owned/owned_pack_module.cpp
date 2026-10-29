#include "../native/child_reposition.h"
// This TU alone uses exceptions; existing monitor TU keeps its original flags.
#include "dynamic_owned_store.h"
#include "owned_core_pins.h"
#include "assetset_capability.h"
#include <android/log.h>
#include <jni.h>
#include <link.h>
#include <cstring>

namespace {
using owned_packs::DynamicOwnedStore;
using owned_packs::Token;
constexpr uintptr_t MAILBOX = 0x1c031c0;
constexpr uint64_t ABI_VERSION = 1;
struct Mailbox {
    uint64_t version, ready;
    uintptr_t reset, append, finish, pointer_member, id_member, invalidate, header;
    uint64_t reserved[7];
};
static_assert(sizeof(Mailbox) == 128);
std::mutex adapter_mutex;
DynamicOwnedStore store;
Token current;
uint64_t generation = 0;
size_t ordered_count = 0;
uintptr_t core_base = 0;
bool pinned_rx_segment = false;
std::atomic<bool> hooks_ready{false}, fault{false};
void child_order_sort(uintptr_t begin, uintptr_t end, uintptr_t comparator,
                      uintptr_t parent, uintptr_t caller, uintptr_t first_child, uintptr_t second_child) {
    const auto result = child_order::inspect(begin, end, comparator, parent, caller, core_base, first_child, second_child);
    if (!result.skipped) reinterpret_cast<void (*)(uintptr_t, uintptr_t, uintptr_t)>(core_base + 0x986f60)(begin, end, comparator);
}


void diagnostic_failure() noexcept {
    if (!fault.exchange(true)) __android_log_print(ANDROID_LOG_ERROR, "AkaineOwnedPacks",
        "dynamic_owned_store unavailable; legacy shadow bounded; capability disabled");
}
bool native_id(uintptr_t pack, const std::string** id) noexcept {
    if (!pack || !id) return false;
    *id = reinterpret_cast<const std::string*>(pack + 8);
    return !(*id)->empty();
}
void invalidate(uintptr_t) noexcept {
    try {
        std::lock_guard<std::mutex> lock(adapter_mutex);
        store.invalidate(); current = {}; ordered_count = 0;
    } catch (...) { diagnostic_failure(); }
}
void reset(uintptr_t manager) noexcept {
    try {
        std::lock_guard<std::mutex> lock(adapter_mutex);
        if (++generation == 0) { diagnostic_failure(); return; }
        current = store.begin(manager, generation); ordered_count = 0;
        if (!current) diagnostic_failure();
    } catch (...) { diagnostic_failure(); }
}
unsigned append(uintptr_t manager, uintptr_t pack, unsigned reserved) noexcept {
    try {
        std::lock_guard<std::mutex> lock(adapter_mutex);
        const std::string* id = nullptr;
        if (fault.load() || manager != current.manager || !native_id(pack, &id)) return 2;
        bool inserted = false;
        if (!store.append(current, pack, *id, reserved != 0, &inserted)) {
            diagnostic_failure(); return 2;
        }
        if (inserted) {
            ++ordered_count;
            if (reserved && ordered_count <= 64) {
                const auto index = ordered_count - 1;
                std::memcpy(reinterpret_cast<void*>(manager + 0x88 + index * 8), &pack, 8);
                const uint64_t count = ordered_count;
                std::memcpy(reinterpret_cast<void*>(manager + 0x288), &count, 8);
            }
        }
        return 1;
    } catch (...) { diagnostic_failure(); return 2; }
}
void finish(uintptr_t manager) noexcept {
    try {
        std::lock_guard<std::mutex> lock(adapter_mutex);
        if (manager != current.manager || !store.finish(current)) diagnostic_failure();
    } catch (...) { diagnostic_failure(); }
}
unsigned pointer_member(uintptr_t manager, uintptr_t pack) noexcept {
    if (!pack) return 1;
    try {
        std::lock_guard<std::mutex> lock(adapter_mutex);
        if (fault.load() || manager != current.manager || !store.ready(current)) return 2;
        return store.contains_pointer(current, pack) ? 1 : 0;
    } catch (...) { diagnostic_failure(); return 2; }
}
unsigned id_member(uintptr_t manager, const std::string* id) noexcept {
    try {
        std::lock_guard<std::mutex> lock(adapter_mutex);
        if (fault.load() || !id || manager != current.manager || !store.ready(current)) return 2;
        return store.contains_id(current, *id) ? 1 : 0;
    } catch (...) { diagnostic_failure(); return 2; }
}
void header(void* vector) noexcept {
    if (!hooks_ready.load(std::memory_order_acquire) || fault.load() || !vector) return;
    try {
        std::string value("Akaine-Packs: dynamic1");
        static_assert(sizeof(value) == 24);
        reinterpret_cast<void(*)(void*, std::string*)>(core_base + 0x1325c0c)(vector, &value);
        if (AKAINE_ASSETSET_VERIFIED) {
            std::string assets(AKAINE_ASSETSET_HEADER);
            reinterpret_cast<void(*)(void*, std::string*)>(core_base + 0x1325c0c)(vector, &assets);
        }
    } catch (...) { diagnostic_failure(); }
}
int discover(dl_phdr_info* info, size_t, void*) {
    const char* name = info->dlpi_name ? std::strrchr(info->dlpi_name, '/') : nullptr;
    name = name ? name + 1 : info->dlpi_name;
    if (name && std::strcmp(name, "libcocos2dcpp.so") == 0) {
        core_base = info->dlpi_addr;
        bool segment = false;
        for (size_t index = 0; index < info->dlpi_phnum; ++index) {
            const auto& ph = info->dlpi_phdr[index];
            if (ph.p_type == PT_LOAD && ph.p_vaddr == 0x1ba4920 && ph.p_filesz == 0x400b0
                    && ph.p_memsz == 0x5e920 && ph.p_flags == (PF_R | PF_W)) segment = true;
            if (ph.p_type == PT_LOAD && ph.p_vaddr == 0 && ph.p_filesz == OWNED_RX_END
                    && ph.p_memsz == OWNED_RX_END && ph.p_flags == (PF_R | PF_X)) pinned_rx_segment = true;
        }
        if (!segment) core_base = 0;
        return 1;
    }
    return 0;
}
bool prepare() noexcept {
    try {
        std::lock_guard<std::mutex> lock(adapter_mutex);
        if (hooks_ready.load()) return !fault.load();
        dl_iterate_phdr(discover, nullptr);
        if (!core_base || !pinned_rx_segment) return false;
        for (const auto& pin : OWNED_CORE_PINS)
            if (pin.address > OWNED_RX_END || pin.size > OWNED_RX_END - pin.address
                    || std::memcmp(reinterpret_cast<const void*>(core_base + pin.address), pin.bytes, pin.size)) return false;
        auto* mailbox = reinterpret_cast<Mailbox*>(core_base + MAILBOX);
        const Mailbox zero{};
        if (std::memcmp(mailbox, &zero, sizeof(zero))) return false;
        // Force allocation readiness before advertising a capability; state starts invalid.
        const Token probe = store.begin(1, 1);
        if (!probe || !store.append(probe, 1, "probe", false) || !store.finish(probe)) return false;
        store.invalidate();
        mailbox->version = ABI_VERSION;
        mailbox->reset = reinterpret_cast<uintptr_t>(&reset);
        mailbox->append = reinterpret_cast<uintptr_t>(&append);
        mailbox->finish = reinterpret_cast<uintptr_t>(&finish);
        mailbox->pointer_member = reinterpret_cast<uintptr_t>(&pointer_member);
        mailbox->id_member = reinterpret_cast<uintptr_t>(&id_member);
        mailbox->invalidate = reinterpret_cast<uintptr_t>(&invalidate);
        mailbox->header = reinterpret_cast<uintptr_t>(&header);
        mailbox->reserved[1] = reinterpret_cast<uintptr_t>(&child_order_sort);
        hooks_ready.store(true, std::memory_order_release);
        __atomic_store_n(&mailbox->ready, uint64_t{1}, __ATOMIC_RELEASE);
        __android_log_print(ANDROID_LOG_INFO, "AkaineOwnedPacks", "pack_prepare ready=1 bounded_shadow=64 dynamic_storage=1");
        return true;
    } catch (...) { diagnostic_failure(); return false; }
}
}
extern "C" JNIEXPORT jboolean JNICALL Java_low_moe_AnomalyMonitor_prepareNative(JNIEnv*, jclass) {
    return prepare() ? JNI_TRUE : JNI_FALSE;
}
