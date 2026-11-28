#include <android/log.h>
#include <dlfcn.h>
#include <jni.h>
#include <link.h>
#include <pthread.h>
#include <sched.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>

namespace {

using Addr = uintptr_t;

constexpr const char* TAG = "AkainePerf73";

// Verified r5 libcocos2dcpp.so invariants
constexpr Addr kRxEnd = 0x1b16f24;
constexpr Addr kRwVa = 0x1b19690;

// Verified r5 vtables (unpinned by all existing Akaine modules)
constexpr Addr kVtDisplayLinkDirector = 0x1ba39c0;
constexpr Addr kVtPackSelectionCell = 0x1b7cb30;
constexpr Addr kVtSongGroupCell = 0x1c12a68;
constexpr Addr kVtSongSelectionCell = 0x1b4fcc8;
constexpr Addr kVtSongListLayer = 0x1b77930;

// Verified r5 direct helpers
constexpr Addr kFnSongListInnerPos = 0xfd6c34;
constexpr Addr kFnLayoutVisit = 0xaba3cc;

// Minimal GLES .got.plt relocations for VBO orphaning
constexpr Addr kGotBindBuffer = 0x1c36a90;
constexpr Addr kGotBufferData = 0x1c36b50;
constexpr Addr kGotDeleteBuffers = 0x1c36ba8;
constexpr Addr kGotBufferSubData = 0x1c36c88;

struct VboSizeSlot {
    uint32_t buf = 0xffffffffu;
    intptr_t size = -1;
};

std::atomic<Addr> g_base{0};
std::atomic<bool> g_installed{false};
std::atomic<pthread_t> g_owner_thread{0};

float g_win_w = 1280.0f;
float g_win_h = 720.0f;
uint64_t g_frame_count = 0;

uint32_t g_array_buf = 0xffffffffu;
VboSizeSlot g_vbo_sizes[256]{};

using FnMainLoop = void (*)(Addr);
using FnVisit5 = void (*)(Addr, Addr, const float*, uint32_t, uint32_t);
using FnGetLocalMat = const float* (*)(Addr);

FnMainLoop orig_mainLoop = nullptr;
FnVisit5 orig_packCellVisit = nullptr;
FnVisit5 orig_songGrpVisit = nullptr;
FnVisit5 orig_songCellVisit = nullptr;
FnVisit5 orig_songListVisit = nullptr;

void (*orig_glBindBuffer)(uint32_t, uint32_t) = nullptr;
void (*orig_glDeleteBuffers)(int32_t, const uint32_t*) = nullptr;
void (*orig_glBufferData)(uint32_t, intptr_t, const void*, uint32_t) = nullptr;
void (*orig_glBufferSubData)(uint32_t, intptr_t, intptr_t, const void*) = nullptr;

inline bool is_owner() {
    return pthread_self() == g_owner_thread.load(std::memory_order_relaxed);
}

inline int64_t monotonic_now_ns() {
    timespec ts{};
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return static_cast<int64_t>(ts.tv_sec) * 1000000000ll + static_cast<int64_t>(ts.tv_nsec);
}

inline void mul_mat4_2d(const float* p, const float* l, float* out16) {
    for (int col = 0; col < 4; ++col) {
        const float l0 = l[col * 4 + 0];
        const float l1 = l[col * 4 + 1];
        const float l2 = l[col * 4 + 2];
        const float l3 = l[col * 4 + 3];
        out16[col * 4 + 0] = p[0] * l0 + p[4] * l1 + p[8] * l2 + p[12] * l3;
        out16[col * 4 + 1] = p[1] * l0 + p[5] * l1 + p[9] * l2 + p[13] * l3;
        out16[col * 4 + 2] = p[2] * l0 + p[6] * l1 + p[10] * l2 + p[14] * l3;
        out16[col * 4 + 3] = p[3] * l0 + p[7] * l1 + p[11] * l2 + p[15] * l3;
    }
}

inline bool is_rect_outside_ortho(const float* m, float w, float h, float margin) {
    if (std::fabs(m[3]) > 1e-4f || std::fabs(m[7]) > 1e-4f ||
        std::fabs(m[11]) > 1e-4f || std::fabs(m[15] - 1.0f) > 1e-4f) {
        return false;
    }
    if (w <= 0.0f || h <= 0.0f) return false;
    const float tx = m[12], ty = m[13];
    const float ax = m[0] * w, ay = m[1] * w;
    const float bx = m[4] * h, by = m[5] * h;
    const float x0 = tx, x1 = tx + ax, x2 = tx + bx, x3 = tx + ax + bx;
    const float y0 = ty, y1 = ty + ay, y2 = ty + by, y3 = ty + ay + by;
    float minx = x0; if (x1 < minx) minx = x1; if (x2 < minx) minx = x2; if (x3 < minx) minx = x3;
    float maxx = x0; if (x1 > maxx) maxx = x1; if (x2 > maxx) maxx = x2; if (x3 > maxx) maxx = x3;
    float miny = y0; if (y1 < miny) miny = y1; if (y2 < miny) miny = y2; if (y3 < miny) miny = y3;
    float maxy = y0; if (y1 > maxy) maxy = y1; if (y2 > maxy) maxy = y2; if (y3 > maxy) maxy = y3;
    return (maxx < -margin) || (minx > g_win_w + margin) || (maxy < -margin) || (miny > g_win_h + margin);
}

inline bool cell_offscreen(Addr node, const float* parent_mat, float margin) {
    if (!node || !parent_mat) return false;
    if (*reinterpret_cast<const uint8_t*>(node + 0x1c1) == 0) return true;
    const float w = *reinterpret_cast<const float*>(node + 0x5c);
    const float h = *reinterpret_cast<const float*>(node + 0x60);
    const Addr vt = *reinterpret_cast<const Addr*>(node);
    const float* local = reinterpret_cast<FnGetLocalMat>(*reinterpret_cast<const Addr*>(vt + 0x3c8))(node);
    if (!local) return false;
    float world[16];
    mul_mat4_2d(parent_mat, local, world);
    return is_rect_outside_ortho(world, w, h, margin);
}

inline uint64_t fnv_mix(uint64_t h, uint64_t v) {
    h ^= v;
    return h * 1099511628211ull;
}

inline uint32_t fbits(float v) {
    uint32_t bits = 0;
    std::memcpy(&bits, &v, sizeof(bits));
    return bits;
}

void hook_mainLoop(Addr director) {
    if ((g_frame_count & 63) == 0) {
        const Addr glview = *reinterpret_cast<const Addr*>(director + 0xf0);
        if (glview) {
            const Addr gv_vt = *reinterpret_cast<const Addr*>(glview);
            if (gv_vt) {
                using FnGetSizeRef = const float* (*)(Addr);
                const float* sz = reinterpret_cast<FnGetSizeRef>(*reinterpret_cast<const Addr*>(gv_vt + 0xb0))(glview);
                if (sz && sz[0] > 100.0f && sz[1] > 100.0f) {
                    g_win_w = sz[0];
                    g_win_h = sz[1];
                }
            }
        }
    }
    ++g_frame_count;
    orig_mainLoop(director);
}

void hook_packCellVisit(Addr self, Addr renderer, const float* parent_mat, uint32_t flags, uint32_t arg4) {
    if (cell_offscreen(self, parent_mat, 64.0f)) return;
    orig_packCellVisit(self, renderer, parent_mat, flags, arg4);
}

void hook_songGrpVisit(Addr self, Addr renderer, const float* parent_mat, uint32_t flags, uint32_t arg4) {
    const float margin = (*reinterpret_cast<const uint8_t*>(self + 0x5a1) != 0) ? 48.0f : 120.0f;
    if (cell_offscreen(self, parent_mat, margin)) return;
    orig_songGrpVisit(self, renderer, parent_mat, flags, arg4);
}

void hook_songCellVisit(Addr self, Addr renderer, const float* parent_mat, uint32_t flags, uint32_t arg4) {
    if (cell_offscreen(self, parent_mat, 96.0f)) return;
    orig_songCellVisit(self, renderer, parent_mat, flags, arg4);
}

void hook_songListVisit(Addr self, Addr renderer, const float* parent_mat, uint32_t flags, uint32_t arg4) {
    if (!self || *reinterpret_cast<const uint8_t*>(self + 0x1c1) == 0) return;

    const Addr base = g_base.load(std::memory_order_relaxed);
    using FnGetChildren = const Addr* (*)(Addr);
    using FnGetPosRef = const float* (*)(Addr);
    using FnGetPosY = float (*)(Addr);

    const Addr sl_vt = *reinterpret_cast<const Addr*>(self);
    const Addr* children_vec = reinterpret_cast<FnGetChildren>(*reinterpret_cast<const Addr*>(sl_vt + 0x220))(self);
    const float* inner_pos = reinterpret_cast<FnGetPosRef>(base + kFnSongListInnerPos)(self);

    static Addr last_self = 0;
    static uint64_t last_hash = 0;
    static int settle_frames = 3;

    if (!children_vec || !inner_pos) {
        settle_frames = 3;
        orig_songListVisit(self, renderer, parent_mat, flags, arg4);
        return;
    }

    const Addr* beg = reinterpret_cast<const Addr*>(children_vec[0]);
    const Addr* end = reinterpret_cast<const Addr*>(children_vec[1]);
    uint64_t h = 14695981039346656037ull;
    h = fnv_mix(h, self);
    h = fnv_mix(h, static_cast<uint64_t>(end - beg));
    h = fnv_mix(h, fbits(g_win_w));
    h = fnv_mix(h, fbits(g_win_h));
    h = fnv_mix(h, fbits(inner_pos[0]));
    h = fnv_mix(h, fbits(inner_pos[1]));

    for (const Addr* it = beg; it != end; ++it) {
        const Addr c = *it;
        h = fnv_mix(h, c);
        if (!c) continue;
        const Addr cvt = *reinterpret_cast<const Addr*>(c);
        h = fnv_mix(h, *reinterpret_cast<const uint8_t*>(c + 0x1c1));
        const float cy = reinterpret_cast<FnGetPosY>(*reinterpret_cast<const Addr*>(cvt + 0xd0))(c);
        h = fnv_mix(h, fbits(cy));
        if (cvt == base + kVtSongGroupCell) {
            h = fnv_mix(h, *reinterpret_cast<const uint8_t*>(c + 0x5a1));
            h = fnv_mix(h, *reinterpret_cast<const uint8_t*>(c + 0x5a2));
            const Addr* gvec = reinterpret_cast<FnGetChildren>(*reinterpret_cast<const Addr*>(cvt + 0x220))(c);
            if (gvec) {
                const Addr* gbeg = reinterpret_cast<const Addr*>(gvec[0]);
                const Addr* gend = reinterpret_cast<const Addr*>(gvec[1]);
                h = fnv_mix(h, static_cast<uint64_t>(gend - gbeg));
            }
        }
    }

    if (self != last_self || h != last_hash) {
        last_self = self;
        last_hash = h;
        settle_frames = 3;
        orig_songListVisit(self, renderer, parent_mat, flags, arg4);
        return;
    }
    if (settle_frames > 0) {
        --settle_frames;
        orig_songListVisit(self, renderer, parent_mat, flags, arg4);
        return;
    }

    reinterpret_cast<FnVisit5>(base + kFnLayoutVisit)(self, renderer, parent_mat, flags, arg4);
}

void hook_glBindBuffer(uint32_t target, uint32_t buf) {
    if (is_owner() && target == 0x8892) g_array_buf = buf;
    orig_glBindBuffer(target, buf);
}

void hook_glDeleteBuffers(int32_t n, const uint32_t* buffers) {
    if (is_owner() && buffers && n > 0) {
        for (int i = 0; i < n; ++i) {
            if (g_array_buf == buffers[i]) g_array_buf = 0xffffffffu;
            auto& vs = g_vbo_sizes[buffers[i] & 255];
            if (vs.buf == buffers[i]) {
                vs.buf = 0xffffffffu;
                vs.size = -1;
            }
        }
    }
    orig_glDeleteBuffers(n, buffers);
}

void hook_glBufferData(uint32_t target, intptr_t size, const void* data, uint32_t usage) {
    if (is_owner() && target == 0x8892 && g_array_buf != 0xffffffffu && g_array_buf != 0) {
        g_vbo_sizes[g_array_buf & 255] = {g_array_buf, size};
    }
    orig_glBufferData(target, size, data, usage);
}

void hook_glBufferSubData(uint32_t target, intptr_t offset, intptr_t size, const void* data) {
    if (is_owner() && target == 0x8892 && offset == 0 && size >= 512 &&
        g_array_buf != 0xffffffffu && g_array_buf != 0) {
        const auto& vs = g_vbo_sizes[g_array_buf & 255];
        if (vs.buf == g_array_buf && vs.size == size) {
            orig_glBufferData(target, size, data, 0x88e0 /* GL_STREAM_DRAW */);
            return;
        }
    }
    orig_glBufferSubData(target, offset, size, data);
}

int locate_core(dl_phdr_info* module, size_t, void* result) {
    const char* path = module->dlpi_name;
    if (!path) return 0;
    const char* slash = std::strrchr(path, '/');
    if (std::strcmp(slash ? slash + 1 : path, "libcocos2dcpp.so")) return 0;
    bool ok_rx = false, ok_rw = false;
    for (size_t i = 0; i < module->dlpi_phnum; ++i) {
        const auto& p = module->dlpi_phdr[i];
        if (p.p_type != PT_LOAD) continue;
        if (!p.p_vaddr && p.p_flags == (PF_R | PF_X) && p.p_filesz == kRxEnd && p.p_memsz == kRxEnd) ok_rx = true;
        if (p.p_vaddr == kRwVa && p.p_flags == (PF_R | PF_W)) ok_rw = true;
    }
    if (!ok_rx || !ok_rw) return 1;
    *static_cast<Addr*>(result) = module->dlpi_addr;
    return 1;
}

bool patch_slot(Addr slot_addr, void* replacement, void** saved_orig, const char* sym_fallback = nullptr) {
    const long pg = sysconf(_SC_PAGESIZE);
    const Addr page = slot_addr & ~static_cast<Addr>(pg - 1);
    if (mprotect(reinterpret_cast<void*>(page), static_cast<size_t>(pg), PROT_READ | PROT_WRITE) != 0) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "mprotect failed @ %p", reinterpret_cast<void*>(slot_addr));
        return false;
    }
    Addr cur = *reinterpret_cast<Addr*>(slot_addr);
    const Addr base = g_base.load(std::memory_order_relaxed);
    if (sym_fallback && cur >= base && cur < base + 0x1c00000) {
        void* sym = dlsym(RTLD_DEFAULT, sym_fallback);
        if (sym) cur = reinterpret_cast<Addr>(sym);
    }
    if (saved_orig) *saved_orig = reinterpret_cast<void*>(cur);
    __atomic_store_n(reinterpret_cast<Addr*>(slot_addr), reinterpret_cast<Addr>(replacement), __ATOMIC_RELEASE);
    return true;
}

} // namespace

extern "C" JNIEXPORT jboolean JNICALL
Java_org_cocos2dx_lib_AkainePerf73_prepareNative(JNIEnv*, jclass) {
    g_owner_thread.store(pthread_self(), std::memory_order_release);
    g_array_buf = 0xffffffffu;

    if (g_installed.load(std::memory_order_acquire)) {
        return JNI_TRUE;
    }

    Addr base = 0;
    dl_iterate_phdr(locate_core, &base);
    if (!base) {
        __android_log_print(ANDROID_LOG_ERROR, TAG, "libcocos2dcpp.so validation failed");
        return JNI_FALSE;
    }
    g_base.store(base, std::memory_order_release);

    bool ok = true;
    ok &= patch_slot(base + kVtDisplayLinkDirector + 0x38, reinterpret_cast<void*>(&hook_mainLoop), reinterpret_cast<void**>(&orig_mainLoop));
    ok &= patch_slot(base + kVtPackSelectionCell + 0x338, reinterpret_cast<void*>(&hook_packCellVisit), reinterpret_cast<void**>(&orig_packCellVisit));
    ok &= patch_slot(base + kVtSongGroupCell + 0x338, reinterpret_cast<void*>(&hook_songGrpVisit), reinterpret_cast<void**>(&orig_songGrpVisit));
    ok &= patch_slot(base + kVtSongSelectionCell + 0x338, reinterpret_cast<void*>(&hook_songCellVisit), reinterpret_cast<void**>(&orig_songCellVisit));
    ok &= patch_slot(base + kVtSongListLayer + 0x338, reinterpret_cast<void*>(&hook_songListVisit), reinterpret_cast<void**>(&orig_songListVisit));

    ok &= patch_slot(base + kGotBindBuffer, reinterpret_cast<void*>(&hook_glBindBuffer), reinterpret_cast<void**>(&orig_glBindBuffer), "glBindBuffer");
    ok &= patch_slot(base + kGotDeleteBuffers, reinterpret_cast<void*>(&hook_glDeleteBuffers), reinterpret_cast<void**>(&orig_glDeleteBuffers), "glDeleteBuffers");
    ok &= patch_slot(base + kGotBufferData, reinterpret_cast<void*>(&hook_glBufferData), reinterpret_cast<void**>(&orig_glBufferData), "glBufferData");
    ok &= patch_slot(base + kGotBufferSubData, reinterpret_cast<void*>(&hook_glBufferSubData), reinterpret_cast<void**>(&orig_glBufferSubData), "glBufferSubData");

    g_installed.store(ok, std::memory_order_release);
    __android_log_print(ANDROID_LOG_INFO, TAG, "prepareNative ok=%d mode=production", ok ? 1 : 0);
    return ok ? JNI_TRUE : JNI_FALSE;
}

extern "C" JNIEXPORT jlong JNICALL
Java_org_cocos2dx_lib_AkainePerf73_paceCap60(JNIEnv*, jclass, jlong next_target_ns) {
    constexpr int64_t kFrameNs = 16666668ll;
    constexpr int64_t kEarlyWakeNs = 450000ll;
    constexpr int64_t kMaxWaitCapNs = 35000000ll;

    int64_t now = monotonic_now_ns();
    int64_t rem = next_target_ns - now;
    if (rem <= 0) {
        return (now - next_target_ns >= kFrameNs) ? now : next_target_ns;
    }
    if (rem > kMaxWaitCapNs) {
        return now;
    }

    if (rem > kEarlyWakeNs + 400000ll) {
        const int64_t wake_ns = next_target_ns - kEarlyWakeNs;
        timespec ts{};
        ts.tv_sec = static_cast<time_t>(wake_ns / 1000000000ll);
        ts.tv_nsec = static_cast<long>(wake_ns % 1000000000ll);
        clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, nullptr);
    }

    const int64_t hard_limit = next_target_ns + 2000000ll;
    while (true) {
        now = monotonic_now_ns();
        if (now >= next_target_ns || now >= hard_limit) break;
        if (next_target_ns - now > 150000ll) sched_yield();
    }

    return (now - next_target_ns >= kFrameNs) ? now : next_target_ns;
}
