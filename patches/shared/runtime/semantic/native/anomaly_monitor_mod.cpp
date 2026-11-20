#define AKAINE_STAGING_CLI 1
// Observe native gameplay and bind one local Anomaly Replay setting on the existing GL thread.
#include "bounds.h"
#include "perf_aggregate.h"
#include "maps_snapshot.h"
#include "sampler_read_probe.h"
#include "metadata_v2.h"
#include "pins_official.h"
#include "official_replay.h"
#include <type_traits>
#include "setting_toggle.h"
#include "catalog_v3.h"
#include <jni.h>
#include <android/log.h>
#include <elf.h>
#include <link.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <pthread.h>

namespace {
using namespace anomaly_monitor;
constexpr const char* TAG = "AkaineAnomalyMonitor";
constexpr Size MAX_RANGES = 16;
constexpr Address DIRECTOR_GETTER = 0xa4227c;
constexpr Address DIRECTOR_VTABLE = 0x1b5eaf8;
constexpr Address GAME_SCENE_VTABLE = 0x1ae6ef0;
constexpr Address RUNNING_SCENE_OFFSET = 0x140;
struct Module {
    Address base = 0;
    Range readable[MAX_RANGES] = {};
    Range executable[MAX_RANGES] = {};
    Range writable[MAX_RANGES] = {};
    Size readable_count = 0;
    Size executable_count = 0;
    Size writable_count = 0;
    bool mailbox_segment = false;
    bool build_id = false;
};
Module module;
enum class State { Pending, Ready, Rejected };
State state = State::Pending;
bool started = false;
pthread_t owner;
uint64_t started_ns = 0;
uint64_t report_ns = 0;
uint64_t scene_sample_ns = 0;
uint64_t frames = 0;
uint64_t report_frames = 0;
uint64_t game_frames = 0;
uint64_t transitions = 0;
Address last_scene = ~Address(0);
Address validated_director = 0;
char last_class[240] = {};
char last_song_id[65] = {};
char last_modifier_class[240] = {};
uint32_t last_difficulty = 99;
uint32_t last_partner = 999999, last_mode = 999999;
int last_sealed = -2, last_suppressed = -2, last_testify_replay_mode = -2;
bool last_game_scene = false;
bool invalid_logged = false;
Address settings_instance = 0;
bool preference_ready = false;
bool sampler_probe_enabled = false;
int last_anomaly_replay_enabled = -2;

struct ToggleMailbox {
    Address getter;
    Address setter;
    Address disabled;
    Address reserved;
    Address factory, init, update, finish, progress;
    Address active_last, is_last, scoped_tag, scoped_actor;
    Address failed_actor;
    Address pending_finale;
    Address reserved_tail;
};
static_assert(sizeof(ToggleMailbox) == 128);
static_assert(__builtin_offsetof(ToggleMailbox, factory) == 32);
static_assert(__builtin_offsetof(ToggleMailbox, init) == 40);
static_assert(__builtin_offsetof(ToggleMailbox, update) == 48);
static_assert(__builtin_offsetof(ToggleMailbox, finish) == 56);
static_assert(__builtin_offsetof(ToggleMailbox, progress) == 64);
static_assert(__builtin_offsetof(ToggleMailbox, active_last) == 72);
static_assert(__builtin_offsetof(ToggleMailbox, is_last) == 80);
static_assert(__builtin_offsetof(ToggleMailbox, scoped_tag) == 88);
static_assert(__builtin_offsetof(ToggleMailbox, scoped_actor) == 96);
static_assert(__builtin_offsetof(ToggleMailbox, failed_actor) == 104);
static_assert(__builtin_offsetof(ToggleMailbox, pending_finale) == 112);
static_assert(__builtin_offsetof(ToggleMailbox, getter) == 0);
static_assert(__builtin_offsetof(ToggleMailbox, setter) == 8);
static_assert(__builtin_offsetof(ToggleMailbox, disabled) == 16);
ToggleMailbox* toggle_mailbox = nullptr;
bool initialize_official_bridge();
bool song_id(Address song, char* output, Size capacity);

uint64_t monotonic_ns() {
    timespec value = {};
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) return 0;
    return uint64_t(value.tv_sec) * 1000000000ULL + uint64_t(value.tv_nsec);
}


struct PerfScope {
    monitor_perf::Aggregate& aggregate;
    uint64_t start;
    bool enabled;
    explicit PerfScope(monitor_perf::Aggregate& value) : aggregate(value), start(0),
        enabled(started && pthread_equal(owner, pthread_self())) { if (enabled) start = monotonic_ns(); }
    ~PerfScope() { if (enabled) aggregate.add(start, monotonic_ns()); }
};

bool in_ranges(const Range* ranges, Size count, Address address, Size bytes) {
    for (Size i = 0; i < count; ++i) if (contains(ranges[i], address, bytes)) return true;
    return false;
}

bool module_readable(Address address, Size bytes) {
    return address && in_ranges(module.readable, module.readable_count, address, bytes);
}

bool process_readable(Address address, Size bytes, bool writable = false) {
    PerfScope perf_scope(monitor_perf::counters.readable);
    if (!address || bytes > ~Address(0) - address) return false;
    if (sampler_probe_enabled && sampler_probe::active && !writable && bytes && bytes <= sampler_probe::LIMIT)
        return sampler_probe::readable(address, bytes);
    if (sampler_probe_enabled && sampler_probe::mod_read_active && !writable && bytes && bytes <= sampler_probe::LIMIT)
        return sampler_probe::readable(address, bytes);
    if (perf_scope.enabled) ++monitor_perf::counters.maps_open_attempts;
    FILE* maps = fopen("/proc/self/maps", "r");
    if (!maps) return false;
    if (perf_scope.enabled) ++monitor_perf::counters.maps_open_successes;
    bool valid = false;
    const auto scanned = monitor_maps::scan(maps, [&](const monitor_maps::Mapping& mapping) {
        if (!mapping.contains(address, bytes, writable)) return monitor_maps::Visit::Continue;
        valid = true; return monitor_maps::Visit::Stop;
    });
    const bool closed = fclose(maps) == 0;
    if (perf_scope.enabled) monitor_perf::counters.maps_lines += scanned.chunks;
    return valid && scanned.good && closed;
}

bool static_pointer(Address address, Address* value) {
    if (!address || !module_readable(address, sizeof(*value))) return false;
    memcpy(value, reinterpret_cast<const void*>(address), sizeof(*value));
    return true;
}

int find_module(dl_phdr_info* info, size_t, void*) {
    if (!info->dlpi_name) return 0;
    const char* name = strrchr(info->dlpi_name, '/');
    name = name ? name + 1 : info->dlpi_name;
    if (strcmp(name, "libcocos2dcpp.so") != 0) return 0;
    module.base = Address(info->dlpi_addr);
    for (Size i = 0; i < info->dlpi_phnum; ++i) {
        const ElfW(Phdr)& ph = info->dlpi_phdr[i];
        if (ph.p_type != PT_LOAD || ph.p_vaddr > ~Address(0) - module.base
            || ph.p_memsz > ~Address(0) - module.base - ph.p_vaddr) continue;
        Range range = {module.base + ph.p_vaddr, module.base + ph.p_vaddr + ph.p_memsz};
        if (ph.p_flags & PF_R) {
            if (module.readable_count == MAX_RANGES) return 1;
            module.readable[module.readable_count++] = range;
        }
        if (ph.p_flags & PF_W) {
            if (module.writable_count == MAX_RANGES) return 1;
            module.writable[module.writable_count++] = range;
        }
        if (ph.p_vaddr == TOGGLE_RW_SEGMENT_VA && ph.p_filesz == TOGGLE_RW_FILE_SIZE
            && ph.p_memsz == TOGGLE_RW_MEMORY_SIZE && ph.p_flags == (PF_R | PF_W)) module.mailbox_segment = true;
        if (ph.p_flags & PF_X) {
            if (module.executable_count == MAX_RANGES) return 1;
            module.executable[module.executable_count++] = range;
        }
    }
    for (Size i = 0; i < info->dlpi_phnum; ++i) {
        const ElfW(Phdr)& ph = info->dlpi_phdr[i];
        if (ph.p_vaddr > ~Address(0) - module.base) continue;
        Address address = module.base + ph.p_vaddr;
        if (ph.p_type == PT_NOTE && ph.p_memsz <= 4096 && module_readable(address, ph.p_memsz)
            && note_has_build_id(reinterpret_cast<const unsigned char*>(address), ph.p_memsz, EXPECTED_BUILD_ID, sizeof(EXPECTED_BUILD_ID))) {
            module.build_id = true;
        }
    }
    return 1;
}

bool validate_module() {
    if (!module.base || !module.build_id || !module.readable_count || !module.executable_count || !module.mailbox_segment) return false;
    Address mailbox = module.base + TOGGLE_MAILBOX_VA;
    if (!in_ranges(module.writable, module.writable_count, mailbox, sizeof(ToggleMailbox))
        || !process_readable(mailbox, sizeof(ToggleMailbox), true)) return false;
    for (const auto& pin : PINS) {
        Address address = module.base + pin.address;
        if (!in_ranges(module.executable, module.executable_count, address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(address), pin.bytes, pin.size)) return false;
    }
    for (const auto& pin : DATA_PINS) {
        Address address = module.base + pin.address;
        if (!module_readable(address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(address), pin.bytes, pin.size)) return false;
    }
    for (const auto& pin : RELOCATED_PINS) {
        Address pointer = 0;
        if (!static_pointer(module.base + pin.address, &pointer) || pointer != module.base + pin.expected) return false;
    }
    Address typeinfo = 0, name = 0;
    return module_readable(module.base + DIRECTOR_VTABLE - 16, 16)
        && static_pointer(module.base + USERDEFAULT_VTABLE - sizeof(Address), &typeinfo)
        && typeinfo == module.base + USERDEFAULT_TYPEINFO
        && static_pointer(typeinfo + sizeof(Address), &name)
        && name == module.base + USERDEFAULT_RTTI_ADDRESS
        && module_readable(name, sizeof(USERDEFAULT_RTTI))
        && same_bytes(reinterpret_cast<const unsigned char*>(name), reinterpret_cast<const unsigned char*>(USERDEFAULT_RTTI), sizeof(USERDEFAULT_RTTI))
        && module_readable(module.base + GAME_SCENE_VTABLE - 16, 16)
        && static_pointer(module.base + TESTIFY_CHALLENGE_VTABLE - sizeof(Address), &typeinfo)
        && typeinfo == module.base + TESTIFY_CHALLENGE_TYPEINFO
        && static_pointer(typeinfo + sizeof(Address), &name)
        && name == module.base + TESTIFY_CHALLENGE_RTTI_ADDRESS
        && module_readable(name, sizeof(TESTIFY_CHALLENGE_RTTI))
        && same_bytes(reinterpret_cast<const unsigned char*>(name), reinterpret_cast<const unsigned char*>(TESTIFY_CHALLENGE_RTTI), sizeof(TESTIFY_CHALLENGE_RTTI));
}


bool settings_guard() {
    Address vtable = 0, getter = 0, setter = 0;
    if (!process_readable(settings_instance, sizeof(Address))) return false;
    memcpy(&vtable, reinterpret_cast<const void*>(settings_instance), sizeof(vtable));
    return vtable == module.base + USERDEFAULT_VTABLE
        && static_pointer(vtable, &getter) && getter == module.base + USERDEFAULT_GET_BOOL
        && static_pointer(vtable + 0x30, &setter) && setter == module.base + USERDEFAULT_SET_BOOL;
}

int toggle_getter(void*) {
    if (!preference_ready || !pthread_equal(owner, pthread_self()) || !toggle_mailbox) return 1;
    return toggle_mailbox->disabled == 1 ? 0 : 1;
}

void toggle_setter(void*, const int* choice, const void*) {
    if (!preference_ready || state != State::Ready || !pthread_equal(owner, pthread_self()) || !toggle_mailbox) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "setting_change status=rejected reason=bridge_thread_or_state");
        return;
    }
    int index = -1;
    if (!process_readable(Address(choice), sizeof(index))) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "setting_change status=rejected reason=index_read_bounds");
        return;
    }
    memcpy(&index, choice, sizeof(index));
    if ((index != 0 && index != 1) || !settings_guard()) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "setting_change status=rejected reason=index_or_userdefault_guard");
        return;
    }
    bool committed = commit_toggle_choice(reinterpret_cast<void*>(settings_instance),
        reinterpret_cast<PersistToggle>(module.base + USERDEFAULT_SET_BOOL), index, &toggle_mailbox->disabled);
    __android_log_print(committed ? ANDROID_LOG_INFO : ANDROID_LOG_ERROR, TAG,
        "setting_change status=%s key=AkaineAnomalyReplay requested_enabled=%d anomaly_replay_enabled=%d",
        committed ? "committed" : "commit_failed", index, toggle_mailbox->disabled == 0 ? 1 : 0);
}

bool initialize_toggle() {
    using Singleton = void* (*)();
    using ReadBool = bool (*)(void*, const char*, bool);
    settings_instance = Address(reinterpret_cast<Singleton>(module.base + USERDEFAULT_GET_INSTANCE)());
    if (!settings_guard()) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "setting_bridge_init status=rejected reason=userdefault_guard");
        return false;
    }
    bool enabled = reinterpret_cast<ReadBool>(module.base + USERDEFAULT_GET_BOOL)(
        reinterpret_cast<void*>(settings_instance), ANOMALY_REPLAY_KEY, true);
    toggle_mailbox = reinterpret_cast<ToggleMailbox*>(module.base + TOGGLE_MAILBOX_VA);
    ToggleMailbox zero_mailbox = {};
    if (memcmp(toggle_mailbox, &zero_mailbox, sizeof(zero_mailbox)) != 0) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "setting_bridge_init status=rejected reason=mailbox_not_zero");
        return false;
    }
    toggle_mailbox->disabled = enabled ? 0 : 1;
    preference_ready = true;
    toggle_mailbox->getter = Address(&toggle_getter);
    toggle_mailbox->setter = Address(&toggle_setter);
    __android_log_print(ANDROID_LOG_INFO, TAG,
        "setting_bridge_init status=ready key=AkaineAnomalyReplay default_enabled=1 anomaly_replay_enabled=%d", enabled ? 1 : 0);
    return true;
}

bool scene_type_name(Address vtable, char* output, Size capacity, bool* game_scene) {
    Address typeinfo = 0, name = 0;
    if (vtable < sizeof(Address) || !static_pointer(vtable - sizeof(Address), &typeinfo)) return false;
    if (!static_pointer(typeinfo + sizeof(Address), &name)) return false;
    for (Size i = 0; i < module.readable_count; ++i) {
        if (contains(module.readable[i], name, 1)) {
            *game_scene = vtable == module.base + GAME_SCENE_VTABLE;
            return rtti_name(reinterpret_cast<const char*>(name), module.readable[i].end - name, output, capacity);
        }
    }
    return false;
}

bool scene_name(Address scene, char* output, Size capacity, bool* game_scene) {
    if (!process_readable(scene, sizeof(Address))) return false;
    Address vtable = 0;
    memcpy(&vtable, reinterpret_cast<const void*>(scene), sizeof(vtable));
    return scene_type_name(vtable, output, capacity, game_scene);
}

bool song_id(Address song, char* output, Size capacity) {
    if (!process_readable(song, 24)) return false;
    unsigned char object[24] = {};
    memcpy(object, reinterpret_cast<const void*>(song), sizeof(object));
    SongStringView view = {};
    if (!song_string_view(object, &view)) return false;
    if (view.short_string) return copy_song_id(reinterpret_cast<const char*>(object + 1), view.size, output, capacity);
    if (!process_readable(view.address, view.size + 1)) return false;
    char data[65] = {};
    memcpy(data, reinterpret_cast<const void*>(view.address), view.size + 1);
    return copy_song_id(data, view.size, output, capacity);
}

bool official_thread() {
    return state == State::Ready && preference_ready && toggle_mailbox
        && pthread_equal(owner, pthread_self());
}

struct OfficialHost {
    Address base = module.base;
    bool fault = false;
    template<class T> T get(Address address) {
        T value = {};
        if (sampler_probe_enabled && sampler_probe::mod_read_active && sizeof(T) <= sampler_probe::LIMIT) {
            if (fault || !sampler_probe::copy(address, &value, sizeof(T))) { fault = true; return T{}; }
            return value;
        }
        if (fault || !process_readable(address, sizeof(T))) fault = true;
        else memcpy(&value, reinterpret_cast<const void*>(address), sizeof(T));
        return value;
    }
    template<class T> void put(Address address, T value) {
        if (fault || !process_readable(address, sizeof(T), true)) fault = true;
        else memcpy(reinterpret_cast<void*>(address), &value, sizeof(T));
    }
    template<class R, class... Args> R call(Address va, Args... args) {
        if (fault || va > ~Address(0) - base
            || !in_ranges(module.executable, module.executable_count, base + va, 4)) {
            fault = true;
            if constexpr (!std::is_void_v<R>) return R{};
            else return;
        }
        return reinterpret_cast<R (*)(Args...)>(base + va)(args...);
    }
    Address song_id_string(Address scene) { return get<Address>(scene + 0x318); }
    Address makeNode(unsigned size, Address vtable) {
        if (size < 0x300 || size > 0x3a0 || !module_readable(base + vtable, 0x568)) {
            fault = true;
            return 0;
        }
        Address node = call<Address>(0x1a6d9c0, Address(size));
        if (!node || !process_readable(node, size, true)) { fault = true; return 0; }
        memset(reinterpret_cast<void*>(node), 0, size);
        call<void>(0x131419c, node);
        put<Address>(node, base + vtable);
        call<Address>(0x10ac6e8, node);
        return fault ? 0 : node;
    }
    void schedule(Address object, Address closure_vtable, Address capture) {
        if (!object || object != capture) { fault = true; return; }
        Address destroy = 0;
        if (!static_pointer(base + closure_vtable + 0x20, &destroy)
            || !in_ranges(module.executable, module.executable_count, destroy, 4)) {
            fault = true;
            return;
        }
        alignas(16) Address closure[5] = {base + closure_vtable, capture, 0, 0, 0};
        closure[4] = Address(closure);
        call<void>(0xd4c178, Address(closure));
        // Native std::function copies the capture; dispose only its stack wrapper.
        reinterpret_cast<void (*)(Address)>(destroy)(Address(closure));
    }
};

struct OfficialActor {
    Address modifier = 0, scene = 0;
    const akaine_official::OfficialProfile* profile = nullptr;
    bool init_done = false, failed = false;
};
OfficialActor official_actors[16] = {};
Size official_actor_count = 0;

bool actor_matches(const OfficialActor& a) {
    if (!a.modifier || !a.scene || !a.profile
        || !process_readable(a.modifier, a.profile->size, true)
        || !process_readable(a.scene, 0x338)) return false;
    Address vt = 0, scene_vt = 0;
    memcpy(&vt, reinterpret_cast<const void*>(a.modifier), sizeof(vt));
    memcpy(&scene_vt, reinterpret_cast<const void*>(a.scene), sizeof(scene_vt));
    return vt == module.base + a.profile->vtable && scene_vt == module.base + GAME_SCENE_VTABLE;
}

OfficialActor* registered_official_actor(Address modifier) {
    for (Size i = 0; i < official_actor_count; ++i)
        if (official_actors[i].modifier == modifier) return &official_actors[i];
    return nullptr;
}

akaine_official::CallbackPolicy official_callback_policy(OfficialActor* actor, const char* phase) {
    const bool ready = official_thread();
    const bool identity = actor && ready && actor_matches(*actor);
    const auto policy = akaine_official::callbackPolicy(actor != nullptr, ready, identity);
    if (policy == akaine_official::CallbackPolicy::Denied)
        __android_log_print(ANDROID_LOG_ERROR, TAG,
            "official_replay_callback song_id=%s phase=%s status=blocked reason=state_thread_or_identity",
            actor->profile->song, phase);
    return policy;
}

void clear_official_actors() {
    toggle_mailbox->active_last = 0;
    toggle_mailbox->is_last = 0;
    toggle_mailbox->scoped_tag = 0;
    toggle_mailbox->scoped_actor = 0;
    toggle_mailbox->failed_actor = 0;
    OfficialHost h;
    for (Size i = 0; i < official_actor_count; ++i) {
        auto& actor = official_actors[i];
        if (actor.modifier && actor.profile && process_readable(actor.modifier, actor.profile->size)) {
            Address vt = h.get<Address>(actor.modifier);
            if (vt == module.base + actor.profile->vtable) h.call<void>(0xd6dc98, actor.modifier);
        }
        if (actor.scene && process_readable(actor.scene, sizeof(Address))
            && h.get<Address>(actor.scene) == module.base + GAME_SCENE_VTABLE)
            h.call<void>(0xd6dc98, actor.scene);
        actor = {};
    }
    official_actor_count = 0;
}

bool permitted_official_scene(Address scene, char* song) {
    OfficialHost h;
    if (!process_readable(scene, 0x338, true)
        || h.get<Address>(scene) != module.base + GAME_SCENE_VTABLE
        || h.get<uint32_t>(scene + 0x310) != 0) return false;
    Address context_owner = 0;
    if (!static_pointer(module.base + 0x1bf23c0, &context_owner)) return false;
    Address suppression = h.get<Address>(context_owner + 0xb0);
    if (!suppression || h.get<uint8_t>(suppression + 8) != 0 || h.fault) return false;
    return song_id(h.song_id_string(scene), song, 65);
}

void official_factory(Address scene) {
    OfficialHost h;
    if (!official_thread()) { h.call<void>(0x1887128, scene); return; }
    const unsigned finale_intent = unsigned(toggle_mailbox->pending_finale);
    toggle_mailbox->pending_finale = 0;
    clear_official_actors();
    char song[65] = {};
    if (!permitted_official_scene(scene, song)) { h.call<void>(0x1887128, scene); return; }
    const auto* profile = akaine_official::officialProfile(song);
    if (!profile) { h.call<void>(0x1887128, scene); return; }
    bool enabled = toggle_mailbox->disabled == 0;
    Address existing = h.get<Address>(scene + 0x308);
    if (existing) {
        if (!process_readable(existing, 0x2bc, true)
            || h.get<Address>(existing) != module.base + profile->vtable
            || akaine_official::preserveStoryModifier(*profile, h.get<uint32_t>(existing + 0x2b8), enabled, finale_intent)) {
            __android_log_print(ANDROID_LOG_INFO, TAG,
                "official_replay_profile song_id=%s status=skipped reason=existing_story_or_foreign_modifier", song);
            h.call<void>(0x1887128, scene);
            return;
        }
    }
    if (!enabled) {
        if (akaine_official::mandatoryGameplay(*profile)) h.call<void>(0x1887128, scene);
        else {
            if (existing) {
                h.put<Address>(scene + 0x308, 0);
                h.call<void>(0xd6dc98, existing);
            }
        }
        __android_log_print(ANDROID_LOG_INFO, TAG,
            "official_replay_profile song_id=%s status=disabled mandatory_gameplay=%d", song,
            akaine_official::mandatoryGameplay(*profile) ? 1 : 0);
        return;
    }
    __android_log_print(ANDROID_LOG_INFO, TAG,
        "official_replay_profile song_id=%s status=selected family=%u difficulty=%u",
        song, unsigned(profile->family), h.get<uint32_t>(scene + 0x320));
    Address modifier = akaine_official::createOfficial(*profile, scene, h);
    if (!modifier || h.fault || !process_readable(modifier, profile->size, true)
        || h.get<Address>(modifier) != module.base + profile->vtable || official_actor_count == 16) {
        __android_log_print(ANDROID_LOG_ERROR, TAG,
            "official_replay_profile song_id=%s status=skipped reason=creation_or_identity_guard", song);
        return;
    }
    h.put<Address>(scene + 0x308, modifier);
    h.call<void>(0x147fe48, modifier);
    h.call<void>(0x147fe48, scene);
    if (existing) h.call<void>(0xd6dc98, existing);
    // This extra reference protects captured Last callbacks through the ending UI.
    h.call<void>(0x147fe48, modifier);
    official_actors[official_actor_count++] = {modifier, scene, profile, false, false};
    if (akaine_official::isLastProfile(*profile)) {
        toggle_mailbox->active_last = modifier;
        toggle_mailbox->is_last = 1;
    }
    __android_log_print(ANDROID_LOG_INFO, TAG,
        "official_replay_profile song_id=%s status=applied result_type=0 runtime_verified=false", song);
}

void fail_official_actor(OfficialActor& actor, const char* reason) {
    actor.init_done = true;
    actor.failed = true;
    toggle_mailbox->failed_actor = actor.modifier;
    OfficialHost safe;
    const auto& p = *actor.profile;
    if (p.family == akaine_official::Family::Modern) {
        if (p.variant == 0) safe.put<uint32_t>(actor.modifier + 0x2f4, 0);
        else if (p.variant == 1) safe.put<uint32_t>(actor.modifier + 0x2f8, 0);
        else if (p.variant == 2) safe.put<uint32_t>(actor.modifier + 0x330, 0);
        else safe.put<uint8_t>(actor.modifier + 0x2f4, 0);
    }
    __android_log_print(ANDROID_LOG_ERROR, TAG,
        "official_replay_init song_id=%s status=failed reason=%s", p.song, reason);
}

uint32_t official_init(Address modifier, Address original) {
    OfficialHost h;
    auto* actor = registered_official_actor(modifier);
    const auto policy = official_callback_policy(actor, "init");
    if (policy == akaine_official::CallbackPolicy::Native) return h.call<uint32_t>(original - module.base, modifier);
    if (policy == akaine_official::CallbackPolicy::Denied) {
        if (toggle_mailbox) toggle_mailbox->failed_actor = modifier;
        return 0;
    }
    if (original != module.base + actor->profile->init
        || h.get<Address>(modifier + 0x2a0) != actor->scene) {
        fail_official_actor(*actor, "target_or_bound_scene_identity");
        return 0;
    }
    Address scope = 0;
    if (actor->profile->family == akaine_official::Family::Legacy)
        scope = official32::legacy::initScope(static_cast<official32::legacy::Profile>(actor->profile->variant));
    const Address previous_tag = toggle_mailbox->scoped_tag, previous_actor = toggle_mailbox->scoped_actor;
    toggle_mailbox->scoped_actor = modifier;
    toggle_mailbox->scoped_tag = scope;
    bool ok = akaine_official::initOfficial(*actor->profile, modifier, h);
    toggle_mailbox->scoped_tag = previous_tag;
    toggle_mailbox->scoped_actor = previous_actor;
    actor->init_done = true;
    actor->failed = !ok || h.fault;
    if (actor->failed) {
        fail_official_actor(*actor, h.fault ? "read_write_or_call_bounds" : "native_initializer_returned_false");
        return 0;
    }
    __android_log_print(ANDROID_LOG_INFO, TAG,
        "official_replay_init song_id=%s status=ready", actor->profile->song);
    return 1;
}

uint64_t official_update(Address modifier, Address scene, Address original) {
    OfficialHost h;
    auto* actor = registered_official_actor(modifier);
    const auto policy = official_callback_policy(actor, "update");
    if (policy == akaine_official::CallbackPolicy::Native) return h.call<uint64_t>(original - module.base, modifier, scene);
    if (policy == akaine_official::CallbackPolicy::Denied) return 0;
    if (actor->failed || !actor->init_done || original != module.base + actor->profile->update || scene != actor->scene) return 0;
    const auto profile = *actor->profile;
    h.call<void>(0x147fe48, modifier);
    auto result = h.call<uint64_t>(original - module.base, modifier, scene);
    if (!(profile.family == akaine_official::Family::Legacy && profile.variant == 5))
        h.put<uint32_t>(modifier + 0x2b8, 0);
    h.call<void>(0xd6dc98, modifier);
    return result;
}

uint64_t official_finish(Address modifier, Address callback, uint32_t failed, Address original) {
    OfficialHost h;
    auto* actor = registered_official_actor(modifier);
    const auto policy = official_callback_policy(actor, "finish");
    if (policy == akaine_official::CallbackPolicy::Native) return h.call<uint64_t>(original - module.base, modifier, callback, failed);
    if (policy == akaine_official::CallbackPolicy::Denied) return 0;
    if (actor->failed || !actor->init_done || original != module.base + actor->profile->finish) return 0;
    const auto profile = *actor->profile;
    h.call<void>(0x147fe48, modifier);
    auto result = akaine_official::finishOfficial(profile, modifier, callback, failed, h);
    h.call<void>(0xd6dc98, modifier);
    return result;
}

uint64_t official_progress(Address arg0, Address arg1, Address arg2, Address arg3, Address modifier, uint32_t op) {
    OfficialHost h;
    auto* actor = registered_official_actor(modifier);
    if (official_callback_policy(actor, "progress") == akaine_official::CallbackPolicy::Denied) return 0;
    if (actor && akaine_official::skipLastProgress(actor->profile, true, actor->failed, op)) {
        __android_log_print(ANDROID_LOG_INFO, TAG,
            "official_replay_progress song_id=%s operation=%u status=skipped", actor->profile->song, op);
        return 0;
    }
    const Address original = akaine_official::progressOriginal(op);
    return original ? h.call<uint64_t>(original, arg0, arg1, arg2, arg3) : 0;
}

bool initialize_official_bridge() {
    if (!official_thread()) return false;
    for (const auto& profile : akaine_official::official_profiles) {
        const Address expected[] = {profile.init, profile.update, profile.finish};
        const Address slots[] = {0x4d8, 0x508, 0x510};
        for (Size i = 0; i < 3; ++i) {
            Address actual = 0;
            if (!static_pointer(module.base + profile.vtable + slots[i], &actual)
                || actual != module.base + expected[i]) return false;
        }
    }
    toggle_mailbox->factory = Address(&official_factory);
    toggle_mailbox->init = Address(&official_init);
    toggle_mailbox->update = Address(&official_update);
    toggle_mailbox->finish = Address(&official_finish);
    toggle_mailbox->progress = Address(&official_progress);
    __android_log_print(ANDROID_LOG_INFO, TAG,
        "official_replay_bridge status=ready profiles=32 runtime_all_verified=false");
    return true;
}

static_assert(__builtin_offsetof(ToggleMailbox, reserved) == 24);
static_assert(__builtin_offsetof(ToggleMailbox, reserved_tail) == 120);
#include "mod_category_bridge.h"

#include "cli_bridge.h"

void sample_game_metadata(Address scene) {
    if (!process_readable(scene, 0x338)) return;
    uint32_t difficulty = 99;
    memcpy(&difficulty, reinterpret_cast<const void*>(scene + 0x320), sizeof(difficulty));
    if (difficulty > 4) return;
    uint32_t mode = 999999, partner_id = 999999;
    Address partner = 0, owner = 0, settings = 0, suppress_context = 0;
    int sealed = -1, suppressed = -1;
    memcpy(&mode, reinterpret_cast<const void*>(scene + 0x310), sizeof(mode));
    memcpy(&partner, reinterpret_cast<const void*>(scene + 0x330), sizeof(partner));
    if (process_readable(partner, 16)) {
        memcpy(&partner_id, reinterpret_cast<const void*>(partner + 12), sizeof(partner_id));
        if (partner_id > 10000) partner_id = 999999;
    }
    if (static_pointer(module.base + 0x1bf23c0, &owner) && process_readable(owner, 0xb8)) {
        memcpy(&settings, reinterpret_cast<const void*>(owner + 0x78), sizeof(settings));
        memcpy(&suppress_context, reinterpret_cast<const void*>(owner + 0xb0), sizeof(suppress_context));
        if (process_readable(settings, 13)) {
            unsigned char value = 0;
            memcpy(&value, reinterpret_cast<const void*>(settings + 12), 1);
            if (value <= 1) sealed = value;
        }
        if (process_readable(suppress_context, 9)) {
            unsigned char value = 0;
            memcpy(&value, reinterpret_cast<const void*>(suppress_context + 8), 1);
            if (value <= 1) suppressed = value;
        }
    }
    Address song = 0, modifier = 0;
    memcpy(&song, reinterpret_cast<const void*>(scene + 0x318), sizeof(song));
    memcpy(&modifier, reinterpret_cast<const void*>(scene + 0x308), sizeof(modifier));
    char current_song[65] = {};
    char modifier_class[240] = {};
    if (!song_id(song, current_song, sizeof(current_song))) return;
    bool unused_game_scene = false;
    if (modifier) {
        if (!scene_name(modifier, modifier_class, sizeof(modifier_class), &unused_game_scene)) return;
    } else {
        memcpy(modifier_class, "none", 5);
    }
    int testify_replay_mode = -1;
    if (modifier && strcmp(modifier_class, TESTIFY_CHALLENGE_RTTI) == 0 && process_readable(modifier, 0x2f8)) {
        Address vtable = 0, typeinfo = 0, name = 0;
        memcpy(&vtable, reinterpret_cast<const void*>(modifier), sizeof(vtable));
        if (vtable == module.base + TESTIFY_CHALLENGE_VTABLE
            && static_pointer(vtable - sizeof(Address), &typeinfo)
            && typeinfo == module.base + TESTIFY_CHALLENGE_TYPEINFO
            && static_pointer(typeinfo + sizeof(Address), &name)
            && name == module.base + TESTIFY_CHALLENGE_RTTI_ADDRESS) {
            uint32_t value = 0;
            memcpy(&value, reinterpret_cast<const void*>(modifier + 0x2f4), sizeof(value));
            if (value <= 2) testify_replay_mode = int(value);
        }
    }
    int anomaly_replay_enabled = preference_ready && toggle_mailbox ? (toggle_mailbox->disabled == 0 ? 1 : 0) : -1;
    if (anomaly_replay_enabled != last_anomaly_replay_enabled || strcmp(current_song, last_song_id) != 0 || strcmp(modifier_class, last_modifier_class) != 0 || difficulty != last_difficulty || partner_id != last_partner || mode != last_mode || sealed != last_sealed || suppressed != last_suppressed || testify_replay_mode != last_testify_replay_mode) {
        memcpy(last_song_id, current_song, sizeof(last_song_id));
        memcpy(last_modifier_class, modifier_class, sizeof(last_modifier_class));
        last_difficulty = difficulty;
        last_partner = partner_id; last_mode = mode; last_sealed = sealed; last_suppressed = suppressed;
        last_testify_replay_mode = testify_replay_mode;
        last_anomaly_replay_enabled = anomaly_replay_enabled;
        const char* album = album_for_song(current_song);
        __android_log_print(ANDROID_LOG_INFO, TAG, "game_metadata song_id=%s difficulty=%u album=%s modifier_class=%s partner_id=%u skill_sealed=%d mode_raw=%u suppression_flag=%d testify_replay_mode=%d anomaly_replay_enabled=%d", current_song, difficulty, album, modifier_class, partner_id, sealed, mode, suppressed, testify_replay_mode, anomaly_replay_enabled);
    }
}

void sample_scene() {
    PerfScope perf_scope(monitor_perf::counters.sample);
    using Getter = void* (*)();
    Address director = Address(reinterpret_cast<Getter>(module.base + DIRECTOR_GETTER)());
    sampler_probe::Scope sampler_reads;
    if (!director || (director != validated_director && !process_readable(director, RUNNING_SCENE_OFFSET + sizeof(Address)))) {
        state = State::Rejected;
        __android_log_print(ANDROID_LOG_ERROR, TAG, "diagnostic_disabled reason=director_read_bounds");
        return;
    }
    Address director_vtable = 0, scene = 0;
    memcpy(&director_vtable, reinterpret_cast<const void*>(director), sizeof(director_vtable));
    if (director_vtable != module.base + DIRECTOR_VTABLE) {
        state = State::Rejected;
        __android_log_print(ANDROID_LOG_ERROR, TAG, "diagnostic_disabled reason=director_vtable_guard");
        return;
    }
    validated_director = director;
    memcpy(&scene, reinterpret_cast<const void*>(director + RUNNING_SCENE_OFFSET), sizeof(scene));
    bool game_scene = false;
    char current_class[240] = {};
    bool valid = !scene;
    if (scene) valid = scene_name(scene, current_class, sizeof(current_class), &game_scene);
    else memcpy(current_class, "none", 5);
    if (!valid) {
        last_game_scene = false;
        if (!invalid_logged) {
            invalid_logged = true;
            __android_log_print(ANDROID_LOG_WARN, TAG, "scene_unavailable reason=rtti_read_bounds");
        }
        return;
    }
    last_game_scene = game_scene;
    if (scene != last_scene || strcmp(current_class, last_class) != 0) {
        last_scene = scene;
        memcpy(last_class, current_class, sizeof(last_class));
        ++transitions;
        last_song_id[0] = 0;
        last_modifier_class[0] = 0;
        last_difficulty = 99;
        __android_log_print(ANDROID_LOG_INFO, TAG, "scene_transition class=%s exact_gamescene_vtable=%s transitions=%llu frame=%llu",
            current_class, game_scene ? "true" : "false", static_cast<unsigned long long>(transitions), static_cast<unsigned long long>(frames));
    }
    if (game_scene) sample_game_metadata(scene);
}


void report_performance() {
    const auto& p = monitor_perf::counters;
    __android_log_print(ANDROID_LOG_INFO, TAG,
        "perf_aggregate frame_count=%llu frame_sum_ns=%llu frame_max_ns=%llu poll_count=%llu poll_sum_ns=%llu poll_max_ns=%llu sample_count=%llu sample_sum_ns=%llu sample_max_ns=%llu readable_count=%llu readable_sum_ns=%llu readable_max_ns=%llu maps_open_attempts=%llu maps_open_successes=%llu maps_lines=%llu clock_errors=%llu",
        static_cast<unsigned long long>(p.frame.count), static_cast<unsigned long long>(p.frame.sum_ns), static_cast<unsigned long long>(p.frame.max_ns),
        static_cast<unsigned long long>(p.poll.count), static_cast<unsigned long long>(p.poll.sum_ns), static_cast<unsigned long long>(p.poll.max_ns),
        static_cast<unsigned long long>(p.sample.count), static_cast<unsigned long long>(p.sample.sum_ns), static_cast<unsigned long long>(p.sample.max_ns),
        static_cast<unsigned long long>(p.readable.count), static_cast<unsigned long long>(p.readable.sum_ns), static_cast<unsigned long long>(p.readable.max_ns),
        static_cast<unsigned long long>(p.maps_open_attempts), static_cast<unsigned long long>(p.maps_open_successes), static_cast<unsigned long long>(p.maps_lines),
        static_cast<unsigned long long>(p.frame.invalid_clock + p.poll.invalid_clock + p.sample.invalid_clock + p.readable.invalid_clock));
    monitor_perf::counters = {};
}

void frame() {
    uint64_t now = monotonic_ns();
    if (!started) {
        started = true;
        owner = pthread_self();
        started_ns = now;
        report_ns = now;
        dl_iterate_phdr(find_module, nullptr);
        state = validate_module() ? State::Ready : State::Rejected;
        if (state == State::Ready) {
            const auto capability = sampler_probe::self_test();
            sampler_probe_enabled = capability.passed;
            __android_log_print(ANDROID_LOG_INFO, TAG,
                "sampler_probe_capability passed=%u errno=%d self_read_mode=%u",
                unsigned(capability.passed), capability.error, unsigned(sampler_probe_enabled));
        }
        if (state == State::Ready && (!initialize_toggle() || !initialize_official_bridge() || !initialize_mod_bridge())) state = State::Rejected;
        __android_log_print(state == State::Ready ? ANDROID_LOG_INFO : ANDROID_LOG_ERROR, TAG,
            "diagnostic_init status=%s build_id_and_instruction_pins=%s renderer_support=false",
            state == State::Ready ? "ready" : "rejected", state == State::Ready ? "pass" : "fail");
    }
    if (!pthread_equal(owner, pthread_self())) {
        if (!invalid_logged) {
            invalid_logged = true;
            __android_log_print(ANDROID_LOG_ERROR, TAG, "diagnostic_disabled reason=frame_thread_changed");
        }
        state = State::Rejected;
    }
    if (state != State::Ready) return;
    {
    PerfScope perf_scope(monitor_perf::counters.frame);
    ++frames;
    { PerfScope perf_poll(monitor_perf::counters.poll); staging_cli::poll(now); }
    if (!scene_sample_ns || (now >= scene_sample_ns && now - scene_sample_ns >= 500000000ULL)) {
        scene_sample_ns = now;
        sample_scene();
    }
    if (state != State::Ready) return;
    if (last_game_scene) ++game_frames;
    }
    if (now && now >= report_ns && now - report_ns >= 10000000000ULL) {
        double seconds = double(now - report_ns) / 1000000000.0;
        __android_log_print(ANDROID_LOG_INFO, TAG, "frame_counters interval_fps=%.2f frames=%llu game_frames=%llu scene_transitions=%llu uptime_seconds=%.1f",
            double(frames - report_frames) / seconds, static_cast<unsigned long long>(frames), static_cast<unsigned long long>(game_frames),
            static_cast<unsigned long long>(transitions), double(now - started_ns) / 1000000000.0);
        report_performance();
        report_frames = frames;
        report_ns = now;
    }
}
}

extern "C" JNIEXPORT void JNICALL Java_low_moe_AnomalyMonitor_frameNative(JNIEnv*, jclass) {
    frame();
}
