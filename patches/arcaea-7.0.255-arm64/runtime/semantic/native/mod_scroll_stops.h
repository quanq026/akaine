#pragma once

static bool mod_add_scroll_stop(OfficialHost& h, Address scene) {
    const Address begin = h.get<Address>(scene + 0x2e8);
    const Address end = h.get<Address>(scene + 0x2f0);
    const Address capacity = h.get<Address>(scene + 0x2f8);
    if (h.fault || end < begin || capacity < end || (end - begin) % sizeof(float)
        || (capacity - begin) % sizeof(float)) return false;
    const Size count = (end - begin) / sizeof(float);
    if ((count != 5 && count != 6) || capacity - begin > 4096
        || !process_readable(begin, end - begin)) return false;
    constexpr float expected[] = {-2395, -1905, -1415, -925, -435, 55};
    for (Size i = 0; i < count; ++i)
        if (h.get<float>(begin + i * sizeof(float)) != expected[i]) return false;
    if (h.fault || count == 6) return !h.fault;
    if (capacity - end >= sizeof(float)) {
        h.put<float>(end, expected[5]);
        h.put<Address>(scene + 0x2f0, end + sizeof(float));
        return !h.fault;
    }
    // Use the same allocator/delete pair as the native vector-growth path.
    const Size bytes = 10 * sizeof(float);
    const Address replacement = h.call<Address>(0x1a6d9c0, Address(bytes));
    if (!replacement || !process_readable(replacement, bytes, true)) return false;
    memcpy(reinterpret_cast<void*>(replacement), reinterpret_cast<const void*>(begin), end - begin);
    h.put<float>(replacement + count * sizeof(float), expected[5]);
    if (h.fault) return false;
    h.put<Address>(scene + 0x2e8, replacement);
    h.put<Address>(scene + 0x2f0, replacement + 6 * sizeof(float));
    h.put<Address>(scene + 0x2f8, replacement + bytes);
    if (!h.fault) h.call<void>(0x1a6d9e0, begin);
    return !h.fault;
}
