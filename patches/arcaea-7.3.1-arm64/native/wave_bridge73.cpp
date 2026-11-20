// Private, process-local sound routing for the pinned Akaine 7.3.1 provider.
#include "sfx_files.h"
#include "sfx_provider_pins.h"
#include <android/log.h>
#include <atomic>
#include <cstdio>
#include <cstdint>
#include <dlfcn.h>
#include <jni.h>
#include <link.h>
#include <pthread.h>
#include <sys/mman.h>

namespace {
using Address = std::uintptr_t;
using CreateSound = int (*)(void*, const char*, unsigned, void*, void**);
pthread_mutex_t lifecycle = PTHREAD_MUTEX_INITIALIZER;
std::atomic<CreateSound> original{nullptr};
std::atomic<unsigned> active_epoch{0};
thread_local unsigned render_epoch = 0;
unsigned sequence = 0;
int cache_directory = -1;  // Published once via active_epoch.
bool installed = false;
bool protection_failed = false;

struct LifecycleLock {
    bool held = pthread_mutex_lock(&lifecycle) == 0;
    ~LifecycleLock() { if (held) pthread_mutex_unlock(&lifecycle); }
};

bool contains(Address start, Address length, Address address, std::size_t size) {
    return address >= start && size <= length && address - start <= length - size;
}

const char* leaf(const char* path) {
    if (!path) return "";
    const char* slash = std::strrchr(path, '/');
    return slash ? slash + 1 : path;
}

struct Provider {
    Address base = 0;
    const ElfW(Phdr)* headers = nullptr;
    std::size_t count = 0;
};

int find_provider(dl_phdr_info* info, size_t, void* data) {
    if (std::strcmp(leaf(info->dlpi_name), "libfmodProvider.so")) return 0;
    *static_cast<Provider*>(data) = {info->dlpi_addr, info->dlpi_phdr, info->dlpi_phnum};
    return 1;
}

bool has_span(const Provider& p, unsigned kind, unsigned flags, Address address, std::size_t size) {
    for (size_t i = 0; i < p.count; ++i) {
        const auto& ph = p.headers[i];
        if (ph.p_type == kind && (ph.p_flags & flags) == flags
            && contains(ph.p_vaddr, ph.p_memsz, address, size)) return true;
    }
    return false;
}

int local_sound(void* system, const char* name, unsigned mode, void* extra, void** sound) {
    const auto call = original.load(std::memory_order_acquire);
    if (!call) return -1;
    if (mode != 0x102 || extra || !render_epoch
        || render_epoch != active_epoch.load(std::memory_order_acquire)) {
        return call(system, name, mode, extra, sound);
    }
    const auto* wave = akaine_sfx71::find_wave(name, AKAINE_SFX_FILES,
                                              sizeof(AKAINE_SFX_FILES) / sizeof(AKAINE_SFX_FILES[0]));
    if (!wave) return call(system, name, mode, extra, sound);
    const int fd = akaine_sfx71::open_wave(cache_directory, *wave);
    if (fd < 0) return call(system, name, mode, extra, sound);
    char path[32] = {};
    const int length = std::snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);
    if (length <= 0 || static_cast<size_t>(length) >= sizeof(path)) {
        close(fd);
        return call(system, name, mode, extra, sound);
    }
    // The pinned provider requests synchronous CREATESAMPLE for these WAVs.
    const int result = call(system, path, mode, extra, sound);
    close(fd);
    return result;
}

int open_cache(JNIEnv* env, jstring files_dir) {
    if (!files_dir) return -1;
    const char* path = env->GetStringUTFChars(files_dir, nullptr);
    if (!path) return -1;
    constexpr auto flags = O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW;
    const int parent = open(path, flags);
    env->ReleaseStringUTFChars(files_dir, path);
    if (parent < 0) return -1;
    struct stat st = {};
    int child = -1;
    if (!fstat(parent, &st) && S_ISDIR(st.st_mode) && st.st_uid == geteuid()) {
        child = openat(parent, "dl", flags);
        if (child < 0 && errno == ENOENT && (!mkdirat(parent, "dl", 0700) || errno == EEXIST)) {
            child = openat(parent, "dl", flags);
        }
        if (child >= 0 && (fstat(child, &st) || !S_ISDIR(st.st_mode) || st.st_uid != geteuid())) {
            close(child);
            child = -1;
        }
    }
    close(parent);
    return child;
}

bool install(JNIEnv* env, jstring files_dir) {
    Provider p;
    dl_iterate_phdr(find_provider, &p);
    if (!p.base) return false;
    for (const auto& pin : AKAINE_SFX_PROVIDER_PINS) {
        if (!has_span(p, PT_LOAD, PF_R | PF_X, pin.address, pin.size)
            || std::memcmp(reinterpret_cast<const void*>(p.base + pin.address), pin.bytes, pin.size)) {
            return false;
        }
    }
    constexpr auto offset = AKAINE_SFX_PROVIDER_CREATE_SOUND_GOT_VA;
    if (!has_span(p, PT_LOAD, PF_R | PF_W, offset, sizeof(Address))
        || !has_span(p, PT_GNU_RELRO, 0, offset, sizeof(Address))) return false;
    auto* slot = reinterpret_cast<Address*>(p.base + offset);
    const Address approved = __atomic_load_n(slot, __ATOMIC_ACQUIRE);
    Dl_info original_id = {};
    if (!approved || !dladdr(reinterpret_cast<void*>(approved), &original_id)
        || original_id.dli_saddr != reinterpret_cast<void*>(approved)
        || std::strcmp(leaf(original_id.dli_fname), "libfmod.so")
        || !original_id.dli_sname
        || std::strcmp(original_id.dli_sname,
                       "_ZN4FMOD6System11createSoundEPKcjP22FMOD_CREATESOUNDEXINFOPPNS_5SoundE")) {
        return false;
    }
    const long page_size = sysconf(_SC_PAGESIZE);
    if (page_size != 4096 && page_size != 16384) return false;
    const Address page = reinterpret_cast<Address>(slot) & ~(static_cast<Address>(page_size) - 1);
    // The reviewed provider's page-rounded RELRO region is 0x50000..0x54000.
    if (page < p.base || !contains(0x50000, 0x4000, page - p.base, page_size)) return false;
    const int fd = open_cache(env, files_dir);
    if (fd < 0) return false;
    void* page_address = reinterpret_cast<void*>(page);
    if (mprotect(page_address, page_size, PROT_READ | PROT_WRITE)) {
        close(fd);
        return false;
    }
    original.store(reinterpret_cast<CreateSound>(approved), std::memory_order_release);
    __atomic_store_n(slot, reinterpret_cast<Address>(&local_sound), __ATOMIC_RELEASE);
    if (mprotect(page_address, page_size, PROT_READ)) {
        __atomic_store_n(slot, approved, __ATOMIC_RELEASE);
        const int restore = mprotect(page_address, page_size, PROT_READ);
        if (restore) __android_log_write(ANDROID_LOG_ERROR, "AkaineWav73", "Provider page restore failed");
        close(fd);
        protection_failed = true;
        return false;
    }
    cache_directory = fd;
    __android_log_write(ANDROID_LOG_INFO, "AkaineWav73", "WAV bridge ready");
    return true;
}
}  // namespace

extern "C" JNIEXPORT void JNICALL
Java_org_cocos2dx_lib_AkaineWav73_nativeResume(JNIEnv* env, jclass, jstring files_dir) {
    LifecycleLock lock;
    if (!lock.held) return;
    if (!installed && !protection_failed) installed = install(env, files_dir);
    if (!installed) return;
    if (render_epoch && render_epoch == active_epoch.load(std::memory_order_relaxed)) return;
    if (sequence == ~0u) return;
    render_epoch = ++sequence;
    active_epoch.store(render_epoch, std::memory_order_release);
}

extern "C" JNIEXPORT void JNICALL
Java_org_cocos2dx_lib_AkaineWav73_nativePause(JNIEnv*, jclass) {
    LifecycleLock lock;
    if (!lock.held) return;
    if (active_epoch.load(std::memory_order_relaxed) == render_epoch) {
        active_epoch.store(0, std::memory_order_release);
    }
    render_epoch = 0;
}
