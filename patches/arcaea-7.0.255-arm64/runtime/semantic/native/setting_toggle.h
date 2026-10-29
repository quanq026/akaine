#pragma once
#include "bounds.h"

namespace anomaly_monitor {
inline constexpr char ANOMALY_REPLAY_KEY[] = "AkaineAnomalyReplay";
using PersistToggle = bool (*)(void*, const char*, bool);

inline bool commit_toggle_choice(void* settings, PersistToggle persist, int index, Address* disabled) {
    if (!settings || !persist || !disabled || (index != 0 && index != 1)) return false;
    if (!persist(settings, ANOMALY_REPLAY_KEY, index == 1)) return false;
    *disabled = index == 1 ? 0 : 1;
    return true;
}
}
