#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef _WIN32
#define AKAINE_MOD73_EXPORT __declspec(dllexport)
#else
#define AKAINE_MOD73_EXPORT __attribute__((visibility("default")))
#endif

enum result { rejected = 0, applied = 1, already_applied = 2 };
enum { abi_reviewed = 1, assets_reviewed = 2, section_consumers_reviewed = 4,
       gl_owner_bound = 8, explicitly_enabled = 16,
       required_flags = abi_reviewed | assets_reviewed | section_consumers_reviewed |
                        gl_owner_bound | explicitly_enabled };

struct guard {
    uintptr_t core_base;
    uintptr_t owner_thread;
    uintptr_t current_thread;
    uint32_t version_code;
    uint32_t checks;
};

#ifdef __cplusplus
extern "C" {
#endif

AKAINE_MOD73_EXPORT int akaine_mod73_append_stop(const struct guard *gate,
    unsigned char *scene, size_t scene_bytes, unsigned char *backing, size_t backing_bytes);
AKAINE_MOD73_EXPORT int akaine_mod73_extend_bound(const struct guard *gate,
    const unsigned char *scene, size_t scene_bytes, unsigned char *widget, size_t widget_bytes);

#ifdef __cplusplus
}
#endif
