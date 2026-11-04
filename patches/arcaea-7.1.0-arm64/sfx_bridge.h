#pragma once
#include "sfx_cache_path.h"
#include "sfx_files.h"
#include "sfx_provider_pins.h"
#include <dlfcn.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <errno.h>

namespace sfx_bridge71 {
using anomaly_monitor::Address;
using anomaly_monitor::Range;
using anomaly_monitor::Size;
using anomaly_monitor::same_bytes;
inline bool in_ranges(const Range* ranges, Size count, Address address, Size bytes) {
    for (Size i = 0; i < count; ++i) if (anomaly_monitor::contains(ranges[i], address, bytes)) return true;
    return false;
}
using CreateSound = int (*)(void*, const char*, unsigned, void*, void**);
inline CreateSound original = nullptr;
inline int cache_directory = -1;
inline pthread_t owner;
inline bool installed = false;
inline const char* reason = "pending";
inline Address provider_base = 0;
inline Range readable[4] = {}, executable[4] = {};
inline Size readable_count = 0, executable_count = 0;

inline int find_provider(dl_phdr_info* info, size_t, void*) {
    const char* leaf = strrchr(info->dlpi_name, '/');
    leaf = leaf ? leaf + 1 : info->dlpi_name;
    if (!leaf || strcmp(leaf, "libfmodProvider.so")) return 0;
    if (provider_base) return 1;
    provider_base = Address(info->dlpi_addr);
    for (Size i = 0; i < info->dlpi_phnum; ++i) {
        const auto& ph = info->dlpi_phdr[i];
        if (ph.p_type != PT_LOAD || ph.p_vaddr > ~Address(0) - provider_base
            || ph.p_memsz > ~Address(0) - provider_base - ph.p_vaddr) continue;
        Range range = {provider_base + ph.p_vaddr, provider_base + ph.p_vaddr + ph.p_memsz};
        if (ph.p_flags & PF_R) {
            if (readable_count == 4) return 1;
            readable[readable_count++] = range;
        }
        if (ph.p_flags & PF_X) {
            if (executable_count == 4) return 1;
            executable[executable_count++] = range;
        }
    }
    return 1;
}

inline int create_sound(void* system, const char* name, unsigned mode, void* extra, void** sound) {
    const auto real = __atomic_load_n(&original, __ATOMIC_ACQUIRE);
    if (!real) return -1; // The hook is never published without its validated native target.
    if (mode != 0x102 || extra || !__atomic_load_n(&installed, __ATOMIC_ACQUIRE) || !pthread_equal(owner, pthread_self()) || !name)
        return real(system, name, mode, extra, sound);
    const auto* wave = akaine_sfx71::find_wave(name, AKAINE_SFX_FILES, sizeof(AKAINE_SFX_FILES) / sizeof(AKAINE_SFX_FILES[0]));
    if (!wave) return real(system, name, mode, extra, sound);
    const int fd = akaine_sfx71::open_wave(cache_directory, *wave);
    if (fd < 0) {
        __android_log_print(ANDROID_LOG_ERROR, "AkaineSfx", "cache_rejected song=%s file=%s errno=%d", wave->song, wave->name, errno);
        return real(system, name, mode, extra, sound);
    }
    char path[64] = {};
    snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);
    // CREATESAMPLE without NONBLOCKING completes its file read before returning.
    const int result = real(system, path, mode, extra, sound);
    close(fd);
    __android_log_print(result ? ANDROID_LOG_ERROR : ANDROID_LOG_INFO, "AkaineSfx",
        "cache_sample song=%s file=%s result=%d", wave->song, wave->name, result);
    return result;
}

inline bool cache(JNIEnv* env) {
    if (env->PushLocalFrame(12) < 0) return false;
    const auto helper = env->FindClass("org/cocos2dx/lib/Cocos2dxHelper");
    const auto activity_method = helper ? env->GetStaticMethodID(helper, "getActivity", "()Landroid/app/Activity;") : nullptr;
    const auto activity = activity_method ? env->CallStaticObjectMethod(helper, activity_method) : nullptr;
    const auto context = activity ? env->GetObjectClass(activity) : nullptr;
    const auto files_method = context ? env->GetMethodID(context, "getFilesDir", "()Ljava/io/File;") : nullptr;
    const auto files = files_method ? env->CallObjectMethod(activity, files_method) : nullptr;
    const auto file_class = files ? env->GetObjectClass(files) : nullptr;
    const auto path_method = file_class ? env->GetMethodID(file_class, "getAbsolutePath", "()Ljava/lang/String;") : nullptr;
    const auto path = path_method ? static_cast<jstring>(env->CallObjectMethod(files, path_method)) : nullptr;
    bool good = false;
    if (!env->ExceptionCheck() && path) {
        const char* text = env->GetStringUTFChars(path, nullptr);
        if (text) {
            const int directory = open(text, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
            env->ReleaseStringUTFChars(path, text);
            if (directory >= 0) {
                struct stat st = {};
                if (!fstat(directory, &st) && S_ISDIR(st.st_mode) && st.st_uid == geteuid()) {
                    cache_directory = openat(directory, "dl", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
                    if (cache_directory < 0 && errno == ENOENT && !mkdirat(directory, "dl", 0700))
                        cache_directory = openat(directory, "dl", O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
                    if (cache_directory >= 0) good = !fstat(cache_directory, &st) && S_ISDIR(st.st_mode) && st.st_uid == geteuid();
                }
                close(directory);
            }
        }
    }
    if (env->ExceptionCheck()) env->ExceptionClear();
    env->PopLocalFrame(nullptr);
    if (!good && cache_directory >= 0) { close(cache_directory); cache_directory = -1; }
    return good;
}

inline bool initialize(JNIEnv* env) {
    if (__atomic_load_n(&installed, __ATOMIC_ACQUIRE)) return true;
    dl_iterate_phdr(find_provider, nullptr);
    reason = "provider_module";
    if (!provider_base || !readable_count || !executable_count) return false;
    reason = "provider_instruction_pins";
    for (const auto& pin : AKAINE_SFX_PROVIDER_PINS)
        if (!in_ranges(executable, executable_count, provider_base + pin.address, pin.size)
            || !same_bytes(reinterpret_cast<const unsigned char*>(provider_base + pin.address), pin.bytes, pin.size)) return false;
    const Address slot = provider_base + 0x536a0;
    reason = "provider_got_bounds";
    if (!in_ranges(readable, readable_count, slot, sizeof(Address))) return false;
    const Address observed = *reinterpret_cast<const Address*>(slot);
    Dl_info identity = {};
    reason = "native_createSound_identity";
    if (!observed || !dladdr(reinterpret_cast<void*>(observed), &identity) || !identity.dli_fname
        || !identity.dli_sname || Address(identity.dli_saddr) != observed
        || strcmp(identity.dli_sname, "_ZN4FMOD6System11createSoundEPKcjP22FMOD_CREATESOUNDEXINFOPPNS_5SoundE")) return false;
    const char* leaf = strrchr(identity.dli_fname, '/'); leaf = leaf ? leaf + 1 : identity.dli_fname;
    if (strcmp(leaf, "libfmod.so")) return false;
    reason = "private_cache_directory";
    if (!cache(env)) return false;
    const long page_size = sysconf(_SC_PAGESIZE);
    reason = "page_size";
    if (page_size != 4096 && page_size != 16384) return false;
    const Address page = slot & ~(Address(page_size) - 1);
    if (page < provider_base + 0x50000 || page > provider_base + 0x54000
        || Size(page_size) > provider_base + 0x54000 - page) return false;
    reason = "got_write_protection";
    if (mprotect(reinterpret_cast<void*>(page), Size(page_size), PROT_READ | PROT_WRITE)) return false;
    owner = pthread_self();
    __atomic_store_n(&original, reinterpret_cast<CreateSound>(observed), __ATOMIC_RELEASE);
    __atomic_store_n(&installed, true, __ATOMIC_RELEASE);
    __atomic_store_n(reinterpret_cast<Address*>(slot), Address(&create_sound), __ATOMIC_RELEASE);
    const bool restored = !mprotect(reinterpret_cast<void*>(page), Size(page_size), PROT_READ);
    if (!restored) {
        reason = "got_restore_protection";
        __atomic_store_n(&installed, false, __ATOMIC_RELEASE);
        __atomic_store_n(reinterpret_cast<Address*>(slot), observed, __ATOMIC_RELEASE);
        return false;
    }
    reason = "ready";
    __android_log_print(ANDROID_LOG_INFO, "AkaineSfx", "bridge_ready declared_waves=%zu", sizeof(AKAINE_SFX_FILES) / sizeof(AKAINE_SFX_FILES[0]));
    return true;
}
}
